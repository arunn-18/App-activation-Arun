"""Structural guardrails for a dynamically-composed connector plan
(automation/planner.py) — the safety gate a hand-vetted RECIPES entry never
needed, because a human already wrote and tested those chains. A
model-proposed plan gets NO benefit of the doubt:

  - every object and field it references must be real, per
    salesforce_schema.OBJECTS — nothing else exists as far as this is
    concerned, however plausible a made-up name sounds
  - every step's filter value must chain from the seed context or a
    variable an EARLIER step actually extracted — never a forward or
    undefined reference
  - the terminal action's value must come from a field explicitly marked
    usable for that action kind (assignable_fields for assign,
    taggable_fields for add_tag) — a real field that happens to hold a
    string (e.g. Case.Subject) is NOT automatically a legal assign/tag
    source; marking a field is a deliberate claim, not an accident of type
  - the plan is bounded in size (MAX_PLAN_STEPS)

validate_plan() returns a list of error strings; ANY error means the plan
is rejected outright — automation/validator.py never lets a failing plan
reach the executor, the same "never trust the model's own say-so" stance
entity resolution and the fixed-recipe prerequisite check already take.
to_chain() converts an already-validated plan into the exact
{"app", "chain"} shape automation/executor.run_chain() expects — a
validated dynamic plan and a hand-vetted RECIPES entry are run through the
identical executor, by construction.
"""
import re

import salesforce_schema

MAX_PLAN_STEPS = 4
TERMINAL_SOURCE_FLAG = {"assign": "assignable_fields", "add_tag": "taggable_fields"}

_VAR_ONLY_RE = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")


def _ref(value):
    """The variable name if `value` is EXACTLY one {{var}} reference (not
    mixed with literal text) — a terminal's value must be a pure reference
    to something a step actually extracted, never a partial/literal
    string dressed up to look like one."""
    m = _VAR_ONLY_RE.match(str(value or "").strip())
    return m.group(1) if m else None


def validate_plan(plan, seed_variables):
    """plan: the custom_plan dict a connector action carries (steps +
    terminal). seed_variables: the seed context available before any step
    runs (e.g. {"contact_email": ...}). Returns a list of error strings;
    empty means the plan is safe to convert (to_chain) and execute."""
    errors = []
    steps = plan.get("steps") or []
    terminal = plan.get("terminal") or {}

    if not steps:
        return ["plan has no lookup steps"]
    if len(steps) > MAX_PLAN_STEPS:
        return [f"plan has {len(steps)} steps, more than the {MAX_PLAN_STEPS} allowed"]

    known_vars = set(seed_variables)
    var_sources = {}  # var_name -> (object_name, field)
    for i, step in enumerate(steps, 1):
        obj_name = step.get("object")
        obj = salesforce_schema.OBJECTS.get(obj_name)
        if obj is None:
            errors.append(f"step {i}: unknown object '{obj_name}'")
            continue
        for w in step.get("where") or []:
            field = w.get("field")
            if field not in obj["fields"]:
                errors.append(f"step {i}: '{field}' is not a real field on {obj_name}")
            ref = _ref(w.get("eq"))
            if ref and ref not in known_vars:
                errors.append(f"step {i}: references '{{{{{ref}}}}}' before any earlier "
                              "step extracts it")
        # extract_variables is a [{"variable", "field"}, ...] list, not a
        # {name: field} dict — strict-mode JSON schema can't express an
        # arbitrary-key object (see automation/extract.py's RESPONSE_SCHEMA
        # comment on this same field).
        for pair in step.get("extract_variables") or []:
            var_name, field = pair.get("variable"), pair.get("field")
            if field not in obj["fields"]:
                errors.append(f"step {i}: extract_variables refers to unknown field "
                              f"'{field}' on {obj_name}")
            else:
                var_sources[var_name] = (obj_name, field)
            known_vars.add(var_name)

    kind = terminal.get("kind")
    flag = TERMINAL_SOURCE_FLAG.get(kind)
    if flag is None:
        errors.append(f"terminal action '{kind}' isn't a supported plan terminal "
                      f"({', '.join(TERMINAL_SOURCE_FLAG)})")
        return errors

    value_refs = [terminal.get("target")] if kind == "assign" else list(terminal.get("tags") or [])
    if not value_refs or any(not v for v in value_refs):
        errors.append(f"terminal '{kind}' has no value to use")
        return errors
    for v in value_refs:
        ref = _ref(v)
        if ref is None:
            errors.append(f"terminal '{kind}' value '{v}' must come from a step's "
                          "extracted variable, not a literal")
            continue
        source = var_sources.get(ref)
        if source is None:
            errors.append(f"terminal references '{{{{{ref}}}}}', which no step extracts")
            continue
        obj_name, field = source
        if field not in salesforce_schema.OBJECTS[obj_name].get(flag, []):
            article = "an" if kind == "assign" else "a"
            errors.append(f"'{obj_name}.{field}' isn't marked usable as {article} "
                          f"{kind.replace('_', ' ')} value")
    return errors


def to_chain(plan):
    """A validated plan -> the {"app", "chain"} shape run_chain() expects.
    Only call this AFTER validate_plan() returns no errors — this function
    does no safety checking of its own, the same division of labor
    run_chain() itself keeps with its caller."""
    chain = []
    for step in plan.get("steps") or []:
        pairs = step.get("extract_variables") or []
        chain.append({
            # salesforce_mock.query()'s first param is named object_name (the
            # wire/vocab word "object" shadows a Python builtin) — this is the
            # one place that naming difference is bridged.
            "kind": "api_call", "op": "query",
            "args": {"object_name": step.get("object"), "where": step.get("where") or [],
                     "fields": step.get("fields") or []},
            "extract_variables": {p["variable"]: p["field"] for p in pairs},
        })
    terminal = plan.get("terminal") or {}
    if terminal.get("kind") == "assign":
        chain.append({"kind": "assign", "target": terminal.get("target")})
    elif terminal.get("kind") == "add_tag":
        chain.append({"kind": "add_tag", "tags": terminal.get("tags") or []})
    return {"app": plan.get("app", "salesforce"), "chain": chain}
