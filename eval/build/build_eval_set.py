"""Build the real-world eval set: merge mined candidate specs with authored annotations.

- Flattens multi-eval-step condition groups into one AND'd group list
  (semantics: groups are AND'd; conditions within a group are OR'd).
- Applies per-record renames (opaque tenant IDs -> semantic names) to the spec JSON.
- Expands [[gI.cJ]] tokens in user queries with the (renamed) condition values.
- Emits final JSONL + a summary table.
"""
import json, re, sys
from collections import Counter

SCRATCH = "/private/tmp/claude-502/-Users-mithilverma-Documents-Claude-product-projects/734ec0b5-853c-4689-88c6-24422f3aaae4/scratchpad"
OUT_PATH = f"{SCRATCH}/real-world-eval-set.jsonl"

FLAG_NAMES = {
    'ai': 'uses_ai', 'time': 'uses_time_condition', 'connector': 'uses_connector',
    'custom_field': 'uses_custom_field', 'rare_action': 'uses_uncommon_action',
    'rare_op': 'uses_uncommon_operator', 'multi_eval': 'multi_step_conditions',
    'multi_cond': 'multi_condition', 'alt_trigger': 'non_inbound_trigger',
    'custom_object': 'uses_custom_object',
}

cands = {json.loads(l)['cand_id']: json.loads(l) for l in open(f"{SCRATCH}/candidates.jsonl")}
ann = {}
for i in (1, 2, 3):
    ann.update(json.load(open(f"{SCRATCH}/annotations_{i}.json")))

missing = set(cands) - set(ann)
extra = set(ann) - set(cands)
assert not missing and not extra, f"missing={missing} extra={extra}"

def flatten_groups(spec):
    cg, n = spec['condition_groups'], spec['n_eval_steps']
    if n <= 1:
        return cg
    flat = []
    for eval_step_groups in cg:
        flat.extend(eval_step_groups)
    return flat

records, problems = [], []
for cid in sorted(cands):
    c, a = cands[cid], ann[cid]
    spec = dict(c['spec'])
    spec['condition_groups'] = flatten_groups(spec)
    n_evals = spec.pop('n_eval_steps')

    s = json.dumps(spec, ensure_ascii=False)
    for old, new in a.get('renames', {}).items():
        if old not in s and old not in a['q']:
            problems.append(f"{cid}: rename source not found: {old!r}")
        s = s.replace(old, new)
    spec = json.loads(s)

    def expand(m):
        gi, cj = int(m.group(1)), int(m.group(2))
        try:
            vals = spec['condition_groups'][gi][cj]['values']
        except (IndexError, KeyError):
            problems.append(f"{cid}: bad token g{gi}.c{cj}")
            return m.group(0)
        return ", ".join(f"'{v}'" for v in vals)
    query = re.sub(r"\[\[g(\d+)\.c(\d+)\]\]", expand, a['q'])
    if '[[' in query:
        problems.append(f"{cid}: unexpanded token in query")

    flags = sorted({FLAG_NAMES[f] for f in c['flags']} | set(a.get('extra_flags', [])))
    rec = {
        'id': cid,
        'source_automation_id': c['automation_id'],
        'category': a['cat'],
        'difficulty': a['diff'],
        'scope_flags': flags,
        'user_query': query,
        'ideal_output': {
            'trigger': spec['trigger'],
            'condition_groups': spec['condition_groups'],
            'ai_extract': spec['ai_extract'],
            'actions': spec['actions'],
        },
    }
    if n_evals >= 2:
        rec['ideal_output']['source_eval_steps'] = n_evals
    if a.get('notes'):
        rec['notes'] = a['notes']
    records.append(rec)

if problems:
    print("PROBLEMS:")
    for p in problems:
        print(" -", p)
    sys.exit(1)

with open(OUT_PATH, 'w') as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

print(f"wrote {len(records)} records -> {OUT_PATH}")
print("\nby difficulty:", dict(Counter(r['difficulty'] for r in records)))
print("\nby category:")
for k, v in Counter(r['category'] for r in records).most_common():
    print(f"  {k}: {v}")
print("\nby scope flag:")
for k, v in Counter(fl for r in records for fl in r['scope_flags']).most_common():
    print(f"  {k}: {v}")
print("\nno flags (core scope):", sum(1 for r in records if not r['scope_flags']))
# sanity: no leftover opaque numeric ids (dynamic custom-object lookups are allowed)
leftover = sum(1 for r in records if re.search(r'<(?:tag|agent):\d+>', json.dumps(r)))
print("records still containing opaque <tag:N>/<agent:N> ids:", leftover)
