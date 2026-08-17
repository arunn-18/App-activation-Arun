"""Generate mailbox.json: one synthetic week of Brightpath Logistics mail.

The preview dry-run (preview.py) replays a draft rule over this fixture so the
user sees blast radius BEFORE creating the rule ("would have matched 37 of 214").
Deterministic (seeded) so counts quoted in docs/demos stay true. Timestamps are
absolute but preview measures the window from the newest email, so the fixture
never goes stale. Production would swap this file for a Hiver search API call.

Run:  python make_mailbox.py   ->  rewrites mailbox.json
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

rng = random.Random(42)
BASE = datetime(2026, 8, 8, 18, 0)  # newest mail; window counts back from here

INBOXES = {"Support": "support@brightpath.example",
           "Billing": "billing@brightpath.example",
           "Events": "events@brightpath.example"}

FIRST = ["alex", "sam", "priya", "diego", "mei", "tom", "lena", "ravi", "nora", "omar"]
CUSTOMER_DOMAINS = ["acme.com", "globex.example", "initech.example", "umbrella.example",
                    "wayne-freight.example", "stark-shipping.example", "oscorp.example"]

SUBJECTS = [
    ("Where is my shipment #%d?", "Hi team, tracking shows no movement since Tuesday. "
     "Can you check where container %d is right now?"),
    ("Quote request — %d pallets to Rotterdam", "Hello, we need a quote for %d pallets, "
     "pickup next week. What are your rates?"),
    ("Delivery delay on order %d", "Our customer is waiting on order %d and the ETA "
     "slipped again. Please advise."),
    ("Customs paperwork for shipment %d", "Attached the commercial invoice for shipment "
     "%d. Anything else you need for clearance?"),
    ("Damaged carton on arrival (PO %d)", "One carton from PO %d arrived crushed. "
     "Sending photos. How do we proceed with a claim?"),
]

emails, _id = [], 0


def add(*, direction="inbound", new_conversation=True, frm, to=None, cc=None,
        reply_to=None, subject, body, status="open", inbox="Support", days_ago=None,
        hour=None):
    global _id
    _id += 1
    when = BASE - timedelta(days=days_ago if days_ago is not None else rng.uniform(0, 6.9),
                            hours=rng.uniform(0, 5) if hour is None else 0)
    if hour is not None:
        when = when.replace(hour=hour, minute=rng.randrange(60))
    emails.append({
        "id": f"em-{_id:04d}",
        "direction": direction,
        "new_conversation": new_conversation,
        "from": frm,
        "to": to or [INBOXES[inbox]],
        "cc": cc or [],
        "reply_to": reply_to or frm,
        "subject": subject,
        "body": body,
        "status": status,
        "inbox": inbox,
        "received_at": when.isoformat(timespec="seconds"),
    })


# ---- the bulk: ordinary customer mail into Support (~120)
for i in range(120):
    dom = rng.choice(CUSTOMER_DOMAINS)
    subj, body = rng.choice(SUBJECTS)
    n = rng.randrange(10000, 99999)
    add(frm=f"{rng.choice(FIRST)}.{rng.choice(FIRST)}@{dom}",
        subject=subj % n, body=body % n,
        status=rng.choice(["open", "open", "open", "pending", "close"]))

# ---- streamliner system notifications (2/day)
for d in range(7):
    for h in (7, 15):
        add(frm="notifications@streamliner.example", days_ago=d, hour=h,
            subject=f"Streamliner: nightly sync report {d}",
            body="This is an automated notification from Streamliner. Do not reply.")

# ---- newsletters
for i in range(8):
    add(frm=f"digest@logi-news-{i % 3}.example",
        subject="Weekly logistics newsletter — market rates digest",
        body="Unsubscribe anytime. This week in freight: rates, lanes, fuel.")

# ---- invoices: invoice@acme.com into Billing
for i in range(9):
    add(frm="invoice@acme.com", inbox="Billing",
        subject=f"Invoice INV-2026-{700 + i}",
        body="Please find attached invoice for services rendered. Payment due in 30 days.")

# ---- acme-corp billing
for i in range(5):
    add(frm="billing@acme-corp.example", inbox="Billing",
        subject=f"Statement of account — August (ref {i})",
        body="Monthly statement attached. Contact us with any billing questions.")

# ---- refund requests
for i in range(6):
    dom = rng.choice(CUSTOMER_DOMAINS)
    add(frm=f"{rng.choice(FIRST)}@{dom}", inbox="Billing",
        subject="Refund request for cancelled shipment",
        body="We cancelled this booking within the window and would like a refund.")

# ---- mail meant for Jade (addressed or cc'd to her)
for i in range(9):
    dom = rng.choice(CUSTOMER_DOMAINS)
    if i % 2:
        add(frm=f"{rng.choice(FIRST)}@{dom}",
            to=[INBOXES["Support"], "jade@brightpath.example"],
            subject=f"Follow-up for Jade — carrier onboarding {i}",
            body="Jade helped us last time, looping her in on the next steps.")
    else:
        add(frm=f"{rng.choice(FIRST)}@{dom}", cc=["jade@brightpath.example"],
            subject=f"Re: carrier onboarding question {i}",
            body="Adding Jade on cc as she knows the history here.")

# ---- LG&E (rachel)
for i in range(4):
    add(frm="rachel.kim@lge-power.example",
        subject=f"LG&E coal delivery schedule week {32 + i}",
        body="Updated delivery windows for the plant, please confirm receipt.")

# ---- EQT open orders (secure subject)
for i in range(3):
    add(frm="ops@eqt-partners.example",
        subject="<secure> EQT Open Orders",
        body="Encrypted order roster attached. Standard weekly sync.")

# ---- partner domains
for i in range(6):
    dom = "partner-one.example" if i % 2 else "partner-two.example"
    add(frm=f"dispatch@{dom}",
        subject=f"Partner capacity update {i}",
        body="Capacity and lane availability for next week attached.")

# ---- vendor auto-generated
for i in range(5):
    add(frm="noreply@vendor-x.example",
        subject=f"[auto-generated] System alert {i}",
        body="This message is auto-generated by Vendor-X monitoring.")

# ---- HTS / customs-classification replies from contacts (existing threads)
for i in range(4):
    add(frm=f"{rng.choice(FIRST)}@{rng.choice(CUSTOMER_DOMAINS)}",
        new_conversation=False,
        subject="Re: HTS codes and country of origin",
        body="Per your question: HTS code 8471.30 and country of origin Vietnam for "
             "this SKU. COO certificates attached.")

# ---- other inbound replies on existing threads
for i in range(16):
    dom = rng.choice(CUSTOMER_DOMAINS)
    add(frm=f"{rng.choice(FIRST)}@{dom}", new_conversation=False,
        subject=f"Re: shipment update {i}",
        body="Thanks — confirming receipt, we will get back to you tomorrow.",
        status=rng.choice(["open", "pending"]))

# ---- outbound (sent by the team)
for i in range(14):
    agent = rng.choice(["sarah.lee", "john.doe", "teresa", "dana", "jade"])
    add(direction="outbound", new_conversation=(i % 4 == 0),
        frm=f"{agent}@brightpath.example",
        to=[f"{rng.choice(FIRST)}@{rng.choice(CUSTOMER_DOMAINS)}"],
        subject=f"Re: your request {i}",
        body="Following up on your request — details below.",
        status="pending")

rng.shuffle(emails)
out = Path(__file__).parent / "mailbox.json"
out.write_text(json.dumps({"emails": emails}, indent=1))
print(f"wrote {out.name}: {len(emails)} emails "
      f"({sum(1 for e in emails if e['direction'] == 'inbound')} inbound)")
