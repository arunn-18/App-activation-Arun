"""Mine eval-set candidates from the 90d automations dump.

Pipeline: clean -> parse step chains into canonical specs -> anonymize PII ->
dedupe exact structures -> stratified sample with tail quotas -> emit JSONL.
"""
import pandas as pd
import json, re, hashlib, random
from collections import Counter, defaultdict

random.seed(42)
DIR = "/Users/mithilverma/Downloads/automations_sync_triggers_dump_90d"
OUT = "/private/tmp/claude-502/-Users-mithilverma-Documents-Claude-product-projects/734ec0b5-853c-4689-88c6-24422f3aaae4/scratchpad/candidates.jsonl"

autos = pd.read_csv(f"{DIR}/automations_last90d_sync_triggers.csv")
steps = pd.read_csv(f"{DIR}/automation_steps_last90d_sync_triggers.csv")

# ---------- clean ----------
DEMO_NAMES = {'Send Mail as', 'Demo Automation', 'Subject contains bulk order',
              'Subject contains damaged', 'Subject contains change address'}
autos['name_s'] = autos['name'].astype(str).str.strip()
mask = (autos['is_active'] == 1) & (~autos['name_s'].isin(DEMO_NAMES)) & (autos['old_automation_id'].isna())
clean = autos[mask].copy()
print(f"clean pool: {len(clean)} automations, {clean['ug_id'].nunique()} tenants")

# ---------- anonymization ----------
GENERIC_LOCALS = {'support','info','billing','sales','help','orders','order','admin','noreply',
    'no-reply','hello','contact','team','hr','finance','accounts','accounting','service',
    'customerservice','enquiries','inquiries','office','invoices','invoice','ap','ar',
    'careers','jobs','marketing','ops','operations','dispatch','bookings','reservations',
    'claims','returns','shipping','quotes','quote','payroll','it','helpdesk','legal'}
_dom_map, _loc_map = {}, {}
def anon_domain(d):
    d = d.lower()
    if d not in _dom_map:
        _dom_map[d] = f"company-{len(_dom_map)+1:02d}.example"
    return _dom_map[d]
def anon_email(m):
    local, dom = m.group(1), m.group(2)
    ll = local.lower()
    if ll not in GENERIC_LOCALS:
        if ll not in _loc_map:
            _loc_map[ll] = f"person{len(_loc_map)+1:02d}"
        local = _loc_map[ll]
    return f"{local}@{anon_domain(dom)}"
EMAIL_RE = re.compile(r'([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')
DOMAIN_RE = re.compile(r'^(?:@)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})$')
def anon_text(s):
    if not isinstance(s, str):
        return s
    s = EMAIL_RE.sub(anon_email, s)
    m = DOMAIN_RE.match(s.strip())
    if m and not s.strip().lower().endswith('.example'):
        return anon_domain(m.group(1))
    return s

# ---------- parse step chains ----------
steps_by_auto = defaultdict(list)
for r in steps.itertuples():
    steps_by_auto[r.automation_id].append(r)

def order_chain(rows):
    by_id = {r.id: r for r in rows}
    kids = {}
    roots = []
    for r in rows:
        if pd.isna(r.parent_step_id):
            roots.append(r)
        else:
            kids[int(r.parent_step_id)] = r
    out = []
    cur = roots[0] if roots else None
    seen = set()
    while cur is not None and cur.id not in seen:
        out.append(cur); seen.add(cur.id)
        cur = kids.get(cur.id)
    for r in rows:  # safety: append any stragglers in id order
        if r.id not in seen:
            out.append(r)
    return out

def parse_condition(c, anon):
    prop = str(c.get('property', '')).lower()
    vals = c.get('values', []) or []
    if anon and prop in ('from','to','cc','bcc','reply_to','from_domain','to_domain','reply_to_domain','body','subject'):
        vals = [anon_text(v) if isinstance(v, str) else v for v in vals]
    out = {'property': prop, 'op': c.get('op'), 'values': vals}
    if c.get('variable'):
        v = c['variable']
        out['ai_variable'] = {'name': v.get('variable_name'), 'type': v.get('variable_type'),
                              'options': [o.get('name') for o in (v.get('options') or [])]}
    ts = c.get('time_slot') or {}
    uts = c.get('utc_time_slots')
    if ts or uts:
        out['time_slot'] = ts or uts
    opts = c.get('options') or []
    if opts:
        out['options'] = opts
    return out

def parse_action(action_type, data, anon):
    a = {'type': action_type}
    if not isinstance(data, dict):
        return a
    if action_type == 'add_tag':
        a['tags'] = [f"<tag:{t}>" for t in data.get('tag_ids', [])]
    elif action_type == 'remove_tag':
        a['tags'] = [f"<tag:{t}>" for t in data.get('tag_ids', [])]
    elif action_type == 'assign':
        uid = data.get('user_id')
        a['target'] = 'UNASSIGN' if uid == -1 else f"<agent:{uid}>"
    elif action_type == 'assign_among':
        a['targets'] = [f"<agent:{u}>" for u in data.get('user_ids', data.get('userids', []))]
        a['raw_keys'] = sorted(data.keys())
    elif action_type == 'status':
        a['status'] = data.get('status')
    elif action_type == 'add_note':
        a['content'] = anon_text(data.get('content', ''))
        a['mentions'] = len(data.get('userids', []) or [])
        a['pinned'] = bool(data.get('pin_note'))
    elif action_type == 'send_mail':
        a['fields'] = {k: (anon_text(v) if isinstance(v, str) else v) for k, v in data.items()
                       if k in ('subject','to','cc','bcc','send_as','reply_type')}
        body = data.get('body') or data.get('content') or ''
        a['body_preview'] = anon_text(str(body))[:200]
    elif action_type == 'send_notification':
        a['detail'] = {k: v for k, v in data.items() if not isinstance(v, (dict, list))}
        a['userids'] = len(data.get('userids', []) or [])
    elif action_type in ('add_to_sm', 'remove_from_sm'):
        a['detail'] = data
    elif action_type == 'add_followers':
        a['followers'] = len(data.get('userids', data.get('user_ids', [])) or [])
    elif action_type == 'create_approval_request':
        a['detail_keys'] = sorted(data.keys())
    elif action_type and action_type.startswith('cf_'):
        a['custom_field'] = action_type
        a['detail'] = {k: (anon_text(v) if isinstance(v, str) else v) for k, v in data.items()}
    elif action_type and action_type.startswith('connector_'):
        a['connector'] = action_type
        a['detail_keys'] = sorted(data.keys())
    elif action_type == 'connector_http_request' or action_type == 'http_request':
        a['detail_keys'] = sorted(data.keys())
    else:
        a['raw'] = {k: v for k, v in list(data.items())[:6]}
    return a

def parse_automation(auto_row, anon=True):
    rows = order_chain(steps_by_auto[auto_row.id])
    condition_groups, actions, ai_extract = [], [], None
    multi_eval = 0
    for r in rows:
        try:
            data = json.loads(r.step_data) if isinstance(r.step_data, str) else None
        except Exception:
            data = None
        if r.step_type == 'evaluation' and data is not None:
            multi_eval += 1
            groups = [[parse_condition(c, anon) for c in g] for g in data]
            condition_groups.append(groups)
        elif r.step_type == 'ai_agent' and data is not None:
            ai_extract = {'variables': [{'name': v.get('variable_name'), 'type': v.get('variable_type'),
                                         'description': anon_text(v.get('description','')),
                                         'options': [o.get('name') for o in (v.get('options') or [])]}
                                        for v in data.get('variables', [])]}
        elif r.step_type == 'action':
            actions.append(parse_action(r.action_type, data, anon))
    return {
        'trigger': auto_row.trigger_name,
        'condition_groups': condition_groups[0] if len(condition_groups) == 1 else condition_groups,
        'n_eval_steps': multi_eval,
        'ai_extract': ai_extract,
        'actions': actions,
    }

# ---------- build pool with metadata ----------
RARE_OPS = {'matches','no_email_outgoing','is_outside_business_hours','is_within_business_hours',
            'no_status_change','no_tag_change','no_assignee_change','ends_with','is_empty',
            'is_before','is_after','is_on','contains_any_value_from','is_present_in'}
TIME_PROPS = {'hours_passed_since','email_creation_time','date','day'}
CORE_ACTIONS = {'add_tag','add_note','assign','status'}

pool = []
for row in clean.itertuples():
    spec = parse_automation(row)
    conds = []
    def flatten(cg):
        for g in cg:
            if isinstance(g, list):
                for c in g:
                    if isinstance(c, dict): conds.append(c)
                    elif isinstance(c, list): flatten([c])
    flatten(spec['condition_groups'] if spec['n_eval_steps'] <= 1 else [g for cg in spec['condition_groups'] for g in cg])
    props = [c['property'] for c in conds]
    ops = [c['op'] for c in conds]
    atypes = [a['type'] for a in spec['actions'] if a.get('type')]
    n_groups = len(spec['condition_groups']) if spec['n_eval_steps'] == 1 else sum(len(cg) for cg in spec['condition_groups'])

    flags = set()
    if spec['ai_extract'] or 'ai_variable' in props: flags.add('ai')
    if any(p in TIME_PROPS for p in props) or any(o in {'is_between','is_within','is_outside_business_hours','is_within_business_hours','is_before','is_after','is_on'} for o in ops) or any(c.get('time_slot') for c in conds): flags.add('time')
    if any(str(t).startswith('connector') for t in atypes) or 'http_api_variable' in props or any(str(p).startswith('connector') for p in props): flags.add('connector')
    if any(str(t).startswith('cf_') for t in atypes) or any(str(p).startswith('cf_') for p in props): flags.add('custom_field')
    if any(t in {'send_mail','create_approval_request','assign_among','add_to_sm','remove_from_sm','add_followers','send_notification','remove_tag'} for t in atypes): flags.add('rare_action')
    if any(o in RARE_OPS for o in ops): flags.add('rare_op')
    if spec['n_eval_steps'] >= 2: flags.add('multi_eval')
    if n_groups >= 2 or len(conds) >= 3: flags.add('multi_cond')
    if row.trigger_name not in ('new_conversation_inbound', 'new_conversation'): flags.add('alt_trigger')

    # structural hash for dedupe (structure + values, ignoring tenant-local ids)
    def strip_ids(o):
        if isinstance(o, dict):
            return {k: strip_ids(v) for k, v in o.items() if k not in ('tags','target','targets','mentions','userids','followers')}
        if isinstance(o, list):
            return [strip_ids(x) for x in o]
        return o
    h = hashlib.md5(json.dumps({'t': spec['trigger'], 'c': strip_ids(spec['condition_groups']),
                                'a': [strip_ids(a) for a in spec['actions']]}, sort_keys=True).encode()).hexdigest()

    pool.append({
        'automation_id': int(row.id), 'name': row.name_s, 'tenant': int(row.ug_id),
        'trigger': row.trigger_name, 'spec': spec, 'flags': sorted(flags),
        'n_conds': len(conds), 'n_actions': len(atypes), 'hash': h,
        'sig': (row.trigger_name, tuple(sorted(props)), tuple(sorted(atypes))),
    })

# exact-structure dedupe
seen_h = set()
deduped = []
for p in pool:
    if p['hash'] in seen_h: continue
    seen_h.add(p['hash']); deduped.append(p)
print(f"after exact-structure dedupe: {len(deduped)}")

# ---------- stratified sample ----------
QUOTAS = [('ai', 10), ('time', 8), ('connector', 6), ('custom_field', 4),
          ('multi_eval', 5), ('rare_action', 8), ('rare_op', 6), ('alt_trigger', 8), ('multi_cond', 10)]
tenant_count = Counter()
picked, picked_ids = [], set()

def try_pick(p):
    if p['automation_id'] in picked_ids: return False
    if tenant_count[p['tenant']] >= 3: return False
    picked.append(p); picked_ids.add(p['automation_id']); tenant_count[p['tenant']] += 1
    return True

for flag, quota in QUOTAS:
    cands = [p for p in deduped if flag in p['flags'] and p['automation_id'] not in picked_ids]
    random.shuffle(cands)
    got = 0
    for p in cands:
        if got >= quota: break
        if try_pick(p): got += 1
    print(f"quota {flag}: wanted {quota}, got {got} (pool {len(cands)})")

# head: plain automations (no flags), sampled across distinct signatures
plain = [p for p in deduped if not p['flags'] and p['automation_id'] not in picked_ids]
by_sig = defaultdict(list)
for p in plain: by_sig[p['sig']].append(p)
sigs_sorted = sorted(by_sig.items(), key=lambda kv: -len(kv[1]))
head_target = 105 - len(picked)
got = 0
i = 0
sig_cycle = [v for k, v in sigs_sorted]
for v in sig_cycle: random.shuffle(v)
while got < head_target and any(sig_cycle):
    v = sig_cycle[i % len(sig_cycle)]
    while v:
        if try_pick(v.pop()): got += 1; break
    i += 1
    if i > 5000: break
print(f"head sample: {got} | total picked: {len(picked)}")

# ---------- emit ----------
with open(OUT, 'w') as f:
    for n, p in enumerate(sorted(picked, key=lambda x: (x['flags'], x['trigger'])), 1):
        rec = {'cand_id': f"rw-{n:03d}", 'automation_id': p['automation_id'],
               'name': anon_text(p['name']), 'trigger': p['trigger'], 'flags': p['flags'],
               'spec': p['spec']}
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
print(f"wrote {len(picked)} candidates -> {OUT}")
print(f"anonymized: {len(_dom_map)} domains, {len(_loc_map)} personal local-parts")
print("flag coverage:", Counter(fl for p in picked for fl in p['flags']))
