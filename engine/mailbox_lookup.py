"""Bridges the demo mailbox (mailbox.json, via preview.py) and an app's own
fixture — the "test on a real conversation" capability: instead of asking
an admin to type an arbitrary test contact email, offer REAL conversations
from the mailbox to test the capability (a Track B connector, a Track A
view feature, or a Track A write feature) against.

GENERIC (contact matching): works for any app whose fixture keys contacts
by email in the same shape salesforce_mock.load()["contacts"] already uses
— a future app needs its own contacts list in that shape (a `{"email":
...}` field per contact record) to plug into testable_conversations()
below via its own mock module's load(); nothing here is Salesforce-
specific except which mock module this pass happens to call. Not every app
needs this at all, though — see `require_contact_match` below.
"""
import salesforce_mock
from preview import load_mailbox


def testable_conversations(limit=5, fixture=None, inboxes=None, require_contact_match=True):
    """Real mailbox conversations to test a capability against — most
    recent first. Returns [{"id", "from", "subject", "received_at",
    "inbox"}, ...].

    `inboxes` (optional, capability 7's mailbox picker, 2026-08-26):
    restrict to conversations in these shared inbox(es) only — the write-
    test flow scopes this to whichever inbox(es) the feature was actually
    ENABLED for (feature['inboxes']), never every inbox in the workspace,
    same "don't offer what isn't in scope" stance the rest of this engine
    already holds. None (default) keeps every inbox, unfiltered — the
    original behavior, still used by Track B's own testable-conversations
    endpoint, which has no per-inbox scoping concept.

    `require_contact_match` (default True — the ORIGINAL, Salesforce-
    shaped behavior): only conversations whose sender is a KNOWN contact
    in the app's fixture qualify, since a Salesforce lookup genuinely needs
    one. False (ClickUp's write feature, which has no contact concept at
    all — clickup_mock.create_task takes no sender argument) makes EVERY
    conversation in scope testable; filtering by Salesforce contacts for an
    app that doesn't use them would just be noise, not an honest 'no
    match'."""
    emails = load_mailbox()
    if inboxes:
        wanted = {i.lower() for i in inboxes}
        emails = [e for e in emails if str(e.get("inbox", "")).lower() in wanted]
    if require_contact_match:
        fixture = fixture if fixture is not None else salesforce_mock.load()
        contact_emails = {c["email"].lower() for c in fixture.get("contacts", [])}
        emails = [e for e in emails if e["from"].lower() in contact_emails]
    emails = sorted(emails, key=lambda e: e["received_at"], reverse=True)
    return [{"id": e["id"], "from": e["from"], "subject": e["subject"],
             "received_at": e["received_at"], "inbox": e.get("inbox")}
            for e in emails[:limit]]


def find_conversation(conversation_id):
    """One mailbox conversation by id, or None. Used once a test-conversation
    choice comes back from the admin (its `id`, not its email, is the value
    a choice question composes — see copilot.py) to recover the sender
    email the test-run actually needs."""
    for e in load_mailbox():
        if e["id"] == conversation_id:
            return e
    return None
