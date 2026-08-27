# Eval report
engine=command model=None scope=core prompt_sha=- run=20260807-105952

## Headline: strict full-rule match 16/40 (40%)

parse: {'ok': 27, 'declined': 13}   clarification-asks (over-asking, queries are fully specified): 13

## Slot accuracy (among parsed rules)
- trigger: 19/27 (70%)
- conditions: 23/27 (85%)
- actions: 27/27 (100%)

## By difficulty
- easy: 15/33 (45%)
- medium: 1/7 (14%)

## By category
- keyword_route: 5/8 (62%)
- recipient_route: 3/7 (43%)
- keyword_tag: 2/4 (50%)
- sender_route: 1/4 (25%)
- keyword_close: 2/4 (50%)
- sender_tag: 1/3 (33%)
- multi_condition: 0/3 (0%)
- sender_close: 0/2 (0%)
- recipient_tag: 1/2 (50%)
- domain_tag: 1/2 (50%)
- domain_route: 0/1 (0%)

## By scope flag
- (core): 16/40 (40%)

## Tier-3 (needs judge): 2 records

## Failure dump
### rw-004  [sender_tag / easy]
parse: ok
query: Tag every new conversation where the sender address contains brayweller.example with the 'Brayweller' tag.
- trigger: expected new_conversation, got new_conversation_inbound

### rw-010  [sender_close / easy]  → needs_judge
parse: ok
query: Auto-close anything that comes in from notifications@streamliner.example.
- conditions missing: (('from', 'contains', ('notifications@streamliner.example',), ()),)
- conditions hallucinated: (('from', 'is', ('notifications@streamliner.example',), ()),)

### rw-015  [keyword_close / easy]
parse: ok
query: Dutch review notifications — new incoming emails whose subject contains any of 'heeft een review toegevoegd voor', 'er staat een nieuwe foto op uw bedrijfsprofiel'' — close them and tag 'Google Reviews'.
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone
- conditions missing: (('subject', 'contains', ("er staat een nieuwe foto op uw bedrijfsprofiel'", 'heeft een review toegevoegd voor'), ()),)
- conditions hallucinated: (('subject', 'contains', ('er staat een nieuwe foto op uw bedrijfsprofiel', 'heeft een review toegevoegd voor'), ()),)

### rw-016  [keyword_route / medium]
parse: ok
query: We handle these clinical study codes: 'J2T-MC-KGBU', 'INCB018424-112', 'M-27134-10', 'V712-308', 'CLOU064AUS02', 'IM011-1130', 'BBT001-001', 'NAV-240-201', 'KT621-AD-201', 'DRI20674', 'OG0505-3104', 'CL-BFB759-002', 'ATI-052-PKPD-101', 'ATD002', 'ATI
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone

### rw-017  [sender_close / medium]  → needs_judge
parse: ok
query: Internal mail: anything arriving from one of these addresses — 'person85@company-51.example', 'person82@company-49.example', 'person83@company-48.example', 'person84@company-50.example', 'person81@company-48.example', 'team@company-52.example' — tag 
- conditions missing: (('from', 'contains', ('person81@company-48.example', 'person82@company-49.example', 'person83@company-48.example', 'person84@company-50.example', 'person85@company-51.example', 'team@company-52.examp
- conditions hallucinated: (('from', 'is', ('person81@company-48.example', 'person82@company-49.example', 'person83@company-48.example', 'person84@company-50.example', 'person85@company-51.example', 'team@company-52.example'), 

### rw-018  [keyword_route / easy]
parse: ok
query: If an incoming email body mentions 'Tawfiq Kapery', assign the conversation to Tawfiq.
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone

### rw-019  [keyword_tag / easy]
parse: declined
query: Tag emails about continuing-education certificates — body contains 'CME/CE/CEU Certificate' — with 'CME'.

### rw-020  [recipient_route / easy]
parse: declined
query: Anything addressed to or CC'd to jade@brightpath.example: assign to Jade and tag 'Jade'.

### rw-022  [keyword_tag / medium]
parse: declined
query: Credit-card help requests: if the subject contains any of 'credit card', 'locked out', 'hacked', or the body contains any of 'credit card', 'locked out', 'hacked', 'new credit card', 'update credit card', tag the conversation 'CC Help'.

### rw-023  [sender_route / easy]
parse: ok
query: New incoming emails from anyone whose address contains vintiq.example: assign to Eszter and tag 'Vintiq'.
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone

### rw-024  [recipient_route / medium]
parse: ok
query: When arne@studionoha.example is CC'd on an incoming email, assign it to Maya, set the status to Pending, and add the tags 'Studio NOHA' and 'Design'.
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone

### rw-025  [recipient_route / easy]
parse: declined
query: Emails addressed to celine@chartreuse-restoration.example get assigned to Loui with tags 'Chartreuse', 'Restoration', and 'Priority'.

### rw-026  [keyword_close / easy]
parse: declined
query: When an incoming email's subject contains 'Fulfillment requested', unassign the conversation and close it.

### rw-030  [sender_route / easy]
parse: declined
query: Emails from exactly lucas.bruna@andina-imports.example: assign to Lucas and close the conversation.

### rw-031  [domain_tag / easy]
parse: ok
query: Any incoming email whose sender domain is exactly redline-logistics.example gets the 'Urgent' tag.
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone

### rw-032  [multi_condition / medium]
parse: ok
query: Auto-close wine order confirmations: the sender address contains orders@casewine.example, or the subject contains '([Casewinelife.com Order Wine Online] Order #)'.
- conditions missing: (('from', 'contains', ('orders@casewine.example',), ()), ('subject', 'contains', ('([casewinelife.com order wine online] order #)',), ()))
- conditions hallucinated: (('from', 'contains', ('orders@casewine.example',), ()),)
- conditions hallucinated: (('subject', 'contains', ('[casewinelife.com order wine online] order #',), ()),)

### rw-033  [sender_tag / easy]
parse: declined
query: Emails from exactly broker1@eliteinsure.example or broker2@eliteinsure.example get the 'Elite Broker' tag.

### rw-034  [sender_route / easy]
parse: declined
query: Anything from accounting@pcbank.example or billing@pcbank.example goes to Megan.

### rw-035  [keyword_route / medium]
parse: declined
query: Problem reports: subject contains any of 'Issue', 'not able to upload', 'error', 'failed', 'not uploading', 'payment failed', or body contains any of 'issue', 'not able to upload', 'error', 'failed', 'not uploading', 'payment failed' — assign those t

### rw-036  [multi_condition / easy]
parse: declined
query: Quality Flashings invoices: sender is exactly accounts@qualityflashings.example, or the subject is exactly 'from Quality Flashings' — assign them to Renee.

### rw-037  [recipient_route / easy]
parse: declined
query: Emails addressed to tmteam.lilah@maplethorpe.example — or sent from exactly that address — assign to Lilah.

### rw-038  [recipient_tag / easy]
parse: declined
query: Tag Patrick's emails: if the To or Reply-To field contains patrick@harborcrest.example, add the 'Patrick' tag.

### rw-039  [multi_condition / easy]
parse: declined
query: Emails from exactly ops@eqt-partners.example, or with the exact subject '<secure> EQT Open Orders', get tagged 'OOR'.

### rw-040  [domain_route / easy]
parse: ok
query: Incoming email with sender domain exactly meridianbuild.example: assign to Tom.
- trigger: expected new_conversation_inbound, got new_email_incoming_from_anyone
