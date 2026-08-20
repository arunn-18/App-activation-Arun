"""Connector chain executor: fires a RECIPES chain for real (against the
recipe's mock service today; a real integration would swap in the live app
API behind the same op names) — template-filling {{variable}} references
between steps and capturing real raw responses, the same "prove it, don't
just describe it" stance the rest of this engine takes toward provenance.

Wired into copilot.py (connector_test_run) so a connector-type rule gets a
real test run before being marked done, the executor's analogue of the
draft -> final step every other action type already goes through — those
have no external side effect to verify, so they need no such check; this
one calls a real service (mocked for now), so it does.

GENERIC (the mechanism — holds for recipe #2+): run_chain() walks
recipe["chain"] in order. For each api_call step it template-fills `args`
from the variables collected so far, calls the named op on the recipe's app
service, and — if extract_variables is set — pulls named fields out of the
FIRST record in the response into the variable namespace for later steps.
The moment a step can't produce what's needed (no records, an unresolved
{{var}}), the chain stops CLEANLY with status "no_match" — never an
exception, never a half-run side effect. An `assign` step is terminal: it
reports what WOULD be assigned; it does not mutate Hiver (this stays a
test-run capture, like preview.py's dry-run of a final rule).

MOCK_SERVICES only knows Salesforce; the chain runner understands
api_call/assign/add_tag steps. A hand-vetted RECIPES entry only ever uses
one named op per api_call step; a dynamically-composed plan (see
automation/planner.py, plan_validator.py) uses the SAME api_call/extract_
variables shape but calls the generic salesforce_mock.query() op with a
structured {"object", "where", "fields"} arg instead of a literal one —
run_chain() itself doesn't know or care which kind of chain it's running,
which is exactly why the dynamic path needed no executor changes beyond
_fill()/_unresolved() learning to recurse into that structured arg.
"""
import re

import salesforce_mock
from . import plan_validator
from . import schema

MOCK_SERVICES = {"salesforce": salesforce_mock}

_VAR_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _fill(value, variables):
    """Template-fill {{name}} refs in a string from `variables`, recursing
    into lists/dicts so a structured arg (a dynamic plan's query `where`
    clause, e.g. [{"field": "account_id", "eq": "{{account_id}}"}]) gets
    every embedded ref filled, not just a top-level string. A ref with no
    known value is left as literal text (so the caller can detect an
    unresolved template rather than silently sending '{{csm_email}}' to a
    mock call, or worse, a real one)."""
    if isinstance(value, str):
        return _VAR_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), value)
    if isinstance(value, list):
        return [_fill(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, variables) for k, v in value.items()}
    return value


def _unresolved(value):
    if isinstance(value, str):
        return bool(_VAR_RE.search(value))
    if isinstance(value, list):
        return any(_unresolved(v) for v in value)
    if isinstance(value, dict):
        return any(_unresolved(v) for v in value.values())
    return False


def run_chain(recipe, seed_variables):
    """Runs recipe["chain"] (see schema.RECIPES) starting from seed_variables
    (e.g. {"contact_email": "jordan@acme.example"}).

    Returns {"status": "ok" | "no_match" | "error", "steps": [...],
             "variables": {...}, "final": {...} | None, "reason"?: str}
    — "steps" carries the raw request/response of every api_call actually
    made, so a UI can show the admin exactly what happened, not a summary."""
    service = MOCK_SERVICES.get(recipe["app"])
    if service is None:
        return {"status": "error", "steps": [], "variables": dict(seed_variables),
                "final": None, "reason": f"no service wired for app '{recipe['app']}'"}

    variables = dict(seed_variables)
    steps_log = []
    for step in recipe["chain"]:
        kind = step.get("kind")
        if kind == "api_call":
            args = {k: _fill(v, variables) for k, v in (step.get("args") or {}).items()}
            unresolved = [k for k, v in args.items() if _unresolved(v)]
            if unresolved:
                return {"status": "no_match", "steps": steps_log, "variables": variables,
                        "final": None,
                        "reason": f"'{step['op']}': couldn't resolve {unresolved} from "
                                  "earlier steps"}
            op = getattr(service, step["op"], None)
            if op is None:
                return {"status": "error", "steps": steps_log, "variables": variables,
                        "final": None,
                        "reason": f"unknown op '{step['op']}' for app '{recipe['app']}'"}
            response = op(**args)
            steps_log.append({"kind": "api_call", "op": step["op"], "args": args,
                              "response": response})
            records = response.get("records") or []
            if not records:
                return {"status": "no_match", "steps": steps_log, "variables": variables,
                        "final": None,
                        "reason": f"'{step['op']}' returned no records for {args}"}
            record = records[0]
            for var_name, field in (step.get("extract_variables") or {}).items():
                variables[var_name] = record.get(field)
        elif kind == "assign":
            target = _fill(step.get("target"), variables)
            if not target or _unresolved(target):
                return {"status": "no_match", "steps": steps_log, "variables": variables,
                        "final": None,
                        "reason": "assign target could not be resolved from earlier steps"}
            steps_log.append({"kind": "assign", "target": target})
            return {"status": "ok", "steps": steps_log, "variables": variables,
                    "final": {"type": "assign", "target": target}}
        elif kind == "add_tag":
            tags = [_fill(t, variables) for t in (step.get("tags") or [])]
            if not tags or any(not t or _unresolved(t) for t in tags):
                return {"status": "no_match", "steps": steps_log, "variables": variables,
                        "final": None,
                        "reason": "tag value could not be resolved from earlier steps"}
            steps_log.append({"kind": "add_tag", "tags": tags})
            return {"status": "ok", "steps": steps_log, "variables": variables,
                    "final": {"type": "add_tag", "tags": tags}}
        else:
            return {"status": "error", "steps": steps_log, "variables": variables,
                    "final": None, "reason": f"unknown chain step kind '{kind}'"}
    return {"status": "error", "steps": steps_log, "variables": variables, "final": None,
            "reason": "chain ended without reaching a terminal action"}


def test_run(recipe_id, test_contact_email):
    """copilot.py's entry point: run a recipe (already validated to exist)
    against one real contact email, the way a test-run-before-done check
    should — a live call, not a description of one."""
    recipe = schema.RECIPES[recipe_id]
    return run_chain(recipe, {"contact_email": test_contact_email})


def test_run_plan(plan, test_contact_email):
    """The dynamic-plan analogue of test_run(): plan is the raw custom_plan
    dict a connector action carries (steps + terminal — see plan_validator.py),
    already validated structurally (plan_validator.validate_plan) — not a
    schema.RECIPES lookup, since a dynamically-composed plan has no id in
    that table. Converts it to the {"app", "chain"} shape via
    plan_validator.to_chain() and runs it through the exact same run_chain(),
    because a validated plan and a hand-vetted recipe are the same shape by
    construction once converted."""
    return run_chain(plan_validator.to_chain(plan), {"contact_email": test_contact_email})
