"""Workspace fixture + deterministic entity resolution.

Two consumers, by design:
  1. extract.py exposes these lookups to the model as TOOLS, so it can fill slots
     with canonical workspace names ("john" -> "John Doe").
  2. validator.py re-runs the SAME resolution in code over the user's own words,
     so every lookup the model made is re-verified — the model can use the
     workspace, but it cannot invent from it or silently pick among ambiguous
     matches. Prototype reads workspace.json; production would hit Hiver's APIs.

resolve_*(query) -> {"status": "exact" | "resolved" | "ambiguous" | "none",
                     "matches": [...]}   (matches are canonical entities)
  exact     the query IS the entity (case-insensitive full name/label/address)
  resolved  exactly one entity plausibly matches a partial/fuzzy query
  ambiguous several entities match — never choose, ask
  none      nothing matches
"""
import difflib
import json
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "workspace.json"


def load(path=DEFAULT_PATH):
    return json.loads(Path(path).read_text())


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _fuzzy(a, b, threshold=0.85):
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _result(query_norm, matches, exact_key):
    if len(matches) == 1:
        status = "exact" if exact_key(matches[0]) == query_norm else "resolved"
        return {"status": status, "matches": matches}
    if matches:
        return {"status": "ambiguous", "matches": matches}
    return {"status": "none", "matches": []}


def resolve_user(ws, query):
    q = _norm(query)
    if not q:
        return {"status": "none", "matches": []}
    matches = []
    for a in ws.get("agents", []):
        name, email = _norm(a["name"]), _norm(a["email"])
        parts = name.split()
        if (q == name or q == email or q == email.split("@")[0]
                or q in parts                       # first or last name
                or name.startswith(q) or _fuzzy(q, name)):
            matches.append(a)
    exact = [a for a in matches if _norm(a["name"]) == q or _norm(a["email"]) == q]
    if len(exact) == 1:
        return {"status": "exact", "matches": exact}
    return _result(q, matches, lambda a: _norm(a["name"]))


def resolve_tag(ws, query):
    q = _norm(query)
    if not q:
        return {"status": "none", "matches": []}
    matches = [t for t in ws.get("tags", [])
               if q == _norm(t) or q in _norm(t) or _norm(t) in q or _fuzzy(q, _norm(t))]
    exact = [t for t in matches if _norm(t) == q]
    if len(exact) == 1:
        return {"status": "exact", "matches": exact}
    return _result(q, matches, _norm)


def resolve_inbox(ws, query):
    q = _norm(query)
    if not q:
        return {"status": "none", "matches": []}
    matches = []
    for i in ws.get("shared_inboxes", []):
        name, addr = _norm(i["name"]), _norm(i["address"])
        if q == name or q == addr or q == addr.split("@")[0] or q in name:
            matches.append(i)
    exact = [i for i in matches if _norm(i["name"]) == q or _norm(i["address"]) == q]
    if len(exact) == 1:
        return {"status": "exact", "matches": exact}
    return _result(q, matches, lambda i: _norm(i["name"]))


RESOLVERS = {"user": resolve_user, "tag": resolve_tag, "inbox": resolve_inbox}


def canonical(kind, entity):
    """The string the rule spec should carry for a matched entity."""
    if kind == "user":
        return entity["name"]
    if kind == "inbox":
        return entity["name"]
    return entity


def label(kind, entity):
    """Human-readable form for disclosures and pick-one questions."""
    if kind == "user":
        return f"{entity['name']} ({entity['email']})"
    if kind == "inbox":
        return f"{entity['name']} ({entity['address']})"
    return f"'{entity}'"


def verified_source(ws, kind, value, conversation_text):
    """Code-side re-verification of a model lookup: does any word/phrase in the
    user's own messages resolve (uniquely) to the entity `value` names?
    Returns the source phrase, or None. This is what keeps tool use inside the
    provenance guarantee."""
    target = _norm(value)
    resolver = RESOLVERS[kind]
    words = re.findall(r"[\w.@&/'-]+", conversation_text)
    grams = set()
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            grams.add(" ".join(words[i:i + n]))
    for g in sorted(grams, key=len, reverse=True):
        r = resolver(ws, g)
        if r["status"] in ("exact", "resolved"):
            got = _norm(canonical(kind, r["matches"][0]))
            if got == target:
                return g
    return None


def ambiguous_source(ws, kind, value, conversation_text):
    """The user phrase that AMBIGUOUSLY resolves to a set containing `value`.

    Counterpart to verified_source: that one accepts a model lookup when the
    user's words land uniquely on it. This one explains the common failure —
    the user said 'john', the workspace has two, and the model picked one (or
    both). Returns (phrase, matches) so the caller can ask "which one?" instead
    of the useless "I couldn't confirm 'John Doe'". Without this, an ambiguous
    reference is scrubbed and re-asked as if the user never said it."""
    target = _norm(value)
    resolver = RESOLVERS[kind]
    words = re.findall(r"[\w.@&/'-]+", conversation_text)
    grams = set()
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            grams.add(" ".join(words[i:i + n]))
    for g in sorted(grams, key=len, reverse=True):
        r = resolver(ws, g)
        if r["status"] == "ambiguous" and any(
                _norm(canonical(kind, m)) == target for m in r["matches"]):
            return g, r["matches"]
    return None, []


def suggest(ws, kind, query, threshold=0.6):
    """Looser near-miss scan for "did you mean X?" questions — below the
    auto-resolve threshold (0.85), above noise. Typos land here: 'urgnet' vs
    'Urgent' scores 0.833, so resolve_* rightly refuses, but a QUESTION offering
    the candidate is safe where silent correction wouldn't be."""
    q = _norm(query)
    if not q:
        return []
    if kind == "tag":
        pool = [(t, _norm(t)) for t in ws.get("tags", [])]
    elif kind == "user":
        pool = [(a, _norm(a["name"])) for a in ws.get("agents", [])]
    else:
        pool = [(i, _norm(i["name"])) for i in ws.get("shared_inboxes", [])]
    out = [ent for ent, name in pool
           if q == name or q in name or name in q or _fuzzy(q, name, threshold)]
    return out[:3]


# ------------------------------------------------------------------ LLM tools
TOOLS = [
    {"type": "function", "function": {
        "name": "list_tags",
        "description": "List every tag that exists in this Hiver workspace.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "find_user",
        "description": "Find workspace agents matching a name, first name, or email.",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "list_inboxes",
        "description": "List the shared inboxes in this Hiver workspace.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def dispatch(ws, name, arguments):
    """Execute a tool call. Returns a JSON string for the tool message."""
    if name == "list_tags":
        return json.dumps({"tags": ws.get("tags", [])})
    if name == "find_user":
        r = resolve_user(ws, (arguments or {}).get("name", ""))
        return json.dumps({"status": r["status"], "matches": r["matches"]})
    if name == "list_inboxes":
        return json.dumps({"shared_inboxes": ws.get("shared_inboxes", [])})
    return json.dumps({"error": f"unknown tool '{name}'"})
