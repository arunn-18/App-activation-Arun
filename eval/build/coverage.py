"""Coverage: what share of organic production automations can the copilot build?

Classifies every organic automation in the 90d dump against the engine's supported
surface (engine/schema.py, v2.6.1) and ranks the blockers. Stdlib only; prints
aggregates only (no tenant values leave the machine).

Run:  python3 coverage.py [dump_dir]
"""
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "engine"))
from automation import schema  # noqa: E402

DIR = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/mithilverma/Downloads/automations_sync_triggers_dump_90d"

DEMO_NAMES = {'Send Mail as', 'Demo Automation', 'Subject contains bulk order',
              'Subject contains damaged', 'Subject contains change address'}

SUPPORTED_ACTIONS = set(schema.ACTIONS)
SUPPORTED_PROPS = set(schema.CONDITION_PROPERTIES)


def load():
    autos = []
    with open(f"{DIR}/automations_last90d_sync_triggers.csv") as f:
        for row in csv.DictReader(f):
            if row["is_active"] != "1":
                continue
            if row["name"].strip() in DEMO_NAMES:
                continue
            if row["old_automation_id"] not in ("", None):
                continue
            autos.append(row)
    steps = defaultdict(list)
    with open(f"{DIR}/automation_steps_last90d_sync_triggers.csv") as f:
        for row in csv.DictReader(f):
            steps[row["automation_id"]].append(row)
    return autos, steps


def classify(auto, rows):
    """Returns (blockers: set[str], sig: str) for one automation."""
    blockers = set()
    trigger = auto["trigger_name"]
    if trigger not in schema.TRIGGERS:
        blockers.add(f"trigger:{trigger}")

    ai_types = []
    sig_parts = [trigger]
    for r in sorted(rows, key=lambda r: int(r["id"])):
        try:
            data = json.loads(r["step_data"]) if r["step_data"] else None
        except json.JSONDecodeError:
            data = None
        if r["step_type"] == "evaluation" and data:
            for group in data:
                for c in group:
                    prop = str(c.get("property", "")).lower()
                    op = c.get("op")
                    sig_parts.append(f"c:{prop}.{op}")
                    if prop.startswith("cf_"):
                        blockers.add("custom_field")
                        continue
                    if prop in ("http_api_variable", "custom_object"):
                        blockers.add("connector" if prop == "http_api_variable"
                                     else "custom_object")
                        continue
                    if prop not in SUPPORTED_PROPS:
                        blockers.add(f"property:{prop}")
                        continue
                    if op not in schema.CONDITION_PROPERTIES[prop]["ops"]:
                        blockers.add(f"op:{prop}.{op}")
                    ts = c.get("time_slot") or c.get("utc_time_slots")
                    if ts and any(v not in (None, "", [], {}) for v in
                                  (ts.values() if isinstance(ts, dict) else [ts])):
                        blockers.add("time_slot")
        elif r["step_type"] == "ai_agent" and data:
            for v in data.get("variables", []):
                ai_types.append(v.get("variable_type"))
                if v.get("variable_type") not in schema.AI_VARIABLE_TYPES:
                    blockers.add(f"ai_type:{v.get('variable_type')}")
        elif r["step_type"] == "action":
            at = r["action_type"]
            sig_parts.append(f"a:{at}")
            if at in SUPPORTED_ACTIONS:
                continue
            if at.startswith("cf_"):
                blockers.add("custom_field")
            elif at.startswith("connector") or at == "http_request":
                blockers.add("connector")
            elif at == "create_approval_request":
                blockers.add("approval")
            else:
                blockers.add(f"action:{at}")
    sig = hashlib.md5("|".join(sorted(sig_parts)).encode()).hexdigest()
    return blockers, sig


def main():
    autos, steps = load()
    per_tenant = defaultdict(lambda: [0, 0])  # tenant -> [covered, total]
    blocked_by = Counter()          # blocker -> automations touched
    sole_blocker = Counter()        # blocker -> automations where it's the ONLY one
    results = []                    # (blockers, sig)
    for a in autos:
        blockers, sig = classify(a, steps.get(a["id"], []))
        results.append((blockers, sig))
        t = per_tenant[a["ug_id"]]
        t[1] += 1
        if not blockers:
            t[0] += 1
        for b in blockers:
            blocked_by[b] += 1
        if len(blockers) == 1:
            sole_blocker[next(iter(blockers))] += 1

    n = len(results)
    covered = sum(1 for b, _ in results if not b)
    seen, dd_total, dd_cov = set(), 0, 0
    for b, sig in results:
        if sig in seen:
            continue
        seen.add(sig)
        dd_total += 1
        if not b:
            dd_cov += 1

    full_tenants = sum(1 for c, t in per_tenant.values() if c == t)
    print(f"organic automations: {n} across {len(per_tenant)} tenants")
    print(f"COVERED: {covered}/{n} = {100*covered/n:.1f}%")
    print(f"deduped structures: {dd_cov}/{dd_total} = {100*dd_cov/dd_total:.1f}%")
    print(f"tenants fully covered: {full_tenants}/{len(per_tenant)} "
          f"= {100*full_tenants/len(per_tenant):.1f}%")

    print("\nblockers (automations touched | sole blocker):")
    for b, cnt in blocked_by.most_common(20):
        print(f"  {b:<40} {cnt:>5}  | {sole_blocker.get(b, 0):>5}")

    # greedy cumulative unlock over blocker FAMILIES
    def family(b):
        return b.split(":")[0] if b.split(":")[0] in (
            "trigger", "op", "property", "action", "ai_type") else b
    remaining = [set(map(family, b)) for b, _ in results if b]
    granted = set()
    print("\ncumulative unlock (greedy, by blocker family):")
    print(f"  {'(current surface)':<28} covered {covered:>5} ({100*covered/n:.1f}%)")
    total_cov = covered
    for _ in range(6):
        gains = Counter()
        for bs in remaining:
            left = bs - granted
            if len(left) == 1:
                gains[next(iter(left))] += 1
        if not gains:
            break
        best, gain = gains.most_common(1)[0]
        granted.add(best)
        total_cov += gain
        print(f"  + {best:<26} covered {total_cov:>5} ({100*total_cov/n:.1f}%)  [+{gain}]")


if __name__ == "__main__":
    main()
