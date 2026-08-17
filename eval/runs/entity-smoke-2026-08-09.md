# Entity validation live smoke — v2.5, 2026-08-09

Six single-turn scenarios + one two-turn disambiguation, run live against
`engine/workspace.json` (gpt-4o, tool loop enabled). All behaved to spec on the
first run. Verbatim outputs below (final `json null` plumbing blocks trimmed).

## A. unique-fuzzy person — resolve + disclose, don't ask

USER: assign every new incoming email to sarah

    WHEN  new_conversation_inbound — a new conversation arrives (started by the customer)
    IF    (no conditions — runs on every matching conversation, as you specified)
    THEN  1. assign to 'Sarah Lee'

    Matched to your workspace: 'sarah' → Sarah Lee. Say if I got one wrong.
    final JSON: target "Sarah Lee"

## B. ambiguous person — ask with candidates, never choose

USER: assign every new incoming email to john

    THEN  1. assign to 'john'
    To finish it: 'john' matches more than one teammate: John Doe
    (john.doe@brightpath.example) / John Baker (john.baker@brightpath.example).
    Which one?

Follow-up turn — USER: baker

    THEN  1. assign to 'John Baker'   (complete, code re-verified 'baker' → John Baker)

## C. unknown tag — build with create-first note

USER: tag every new incoming email as gold-partner

    THEN  1. add tag 'gold-partner'
    Heads up: Tag 'gold-partner' doesn't exist in this workspace yet — create it
    first, then this rule can apply it.

## D. existing tag, wrong casing — silent canonicalization

USER: tag every new incoming email as vip

    THEN  1. add tag 'VIP'   (no callout: casing-only fix)

## E. inbox + person in one rule

USER: add every email about invoices to the billing inbox and assign it to teresa

    IF    (subject contains 'invoice'  OR  body contains 'invoice')
    THEN  1. add to shared inbox 'Billing'
          2. assign to 'Teresa Alvarez'
    Matched to your workspace: 'teresa' → Teresa Alvarez. Say if I got one wrong.

## F. invented-tag bait — tools must not widen the provenance gate

USER: tag emails from acme.com appropriately

    IF    (from_domain contains 'acme.com')
    THEN  1. add tag ⟨required — not provided yet⟩
    To finish it: Which tag(s) should I apply?

(No workspace tag was grabbed; the user never named one.)
