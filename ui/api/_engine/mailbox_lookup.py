"""Bridges the demo mailbox (mailbox.json, via preview.py) and an app's own
fixture — the "test on a real conversation" capability: instead of asking
an admin to type an arbitrary test contact email, offer REAL conversations
from the mailbox whose sender is a known contact in the connected app, and
test the capability (a Track B connector, or a Track A view feature)
against that conversation's actual sender.

GENERIC: works for any app whose fixture keys contacts by email in the
same shape salesforce_mock.load()["contacts"] already uses — a future app
needs its own contacts list in that shape (a `{"email": ...}` field per
contact record) to plug into testable_conversations() below via its own
mock module's load(); nothing here is Salesforce-specific except which
mock module this pass happens to call.
"""
import salesforce_mock
from preview import load_mailbox


def testable_conversations(limit=5, fixture=None):
    """Real mailbox conversations whose sender is a KNOWN contact in the
    app's fixture — the honest "test on a real conversation" set: offering
    every mailbox conversation regardless of whether its sender matches
    anything would just make most test-runs a no_match, which is a valid
    but far less useful default to lead with. Returns
    [{"id", "from", "subject", "received_at"}, ...], most recent first."""
    emails = load_mailbox()
    fixture = fixture if fixture is not None else salesforce_mock.load()
    contact_emails = {c["email"].lower() for c in fixture.get("contacts", [])}
    matches = [e for e in emails if e["from"].lower() in contact_emails]
    matches.sort(key=lambda e: e["received_at"], reverse=True)
    return [{"id": e["id"], "from": e["from"], "subject": e["subject"],
             "received_at": e["received_at"]} for e in matches[:limit]]


def find_conversation(conversation_id):
    """One mailbox conversation by id, or None. Used once a test-conversation
    choice comes back from the admin (its `id`, not its email, is the value
    a choice question composes — see copilot.py) to recover the sender
    email the test-run actually needs."""
    for e in load_mailbox():
        if e["id"] == conversation_id:
            return e
    return None
