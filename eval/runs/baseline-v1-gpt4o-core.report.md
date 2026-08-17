# Eval report
engine=openai model=gpt-4o scope=core prompt_sha=db340b261ae1 run=20260803-212936

## Headline: strict full-rule match 27/40 (68%)

parse: {'ok': 40}   clarification-asks (over-asking, queries are fully specified): 0

## Slot accuracy (among parsed rules)
- trigger: 35/40 (88%)
- conditions: 29/40 (72%)
- actions: 40/40 (100%)

## By difficulty
- easy: 22/33 (67%)
- medium: 5/7 (71%)

## By category
- keyword_route: 7/8 (88%)
- recipient_route: 2/7 (29%)
- keyword_tag: 3/4 (75%)
- sender_route: 4/4 (100%)
- keyword_close: 3/4 (75%)
- sender_tag: 2/3 (67%)
- multi_condition: 3/3 (100%)
- sender_close: 0/2 (0%)
- recipient_tag: 0/2 (0%)
- domain_tag: 2/2 (100%)
- domain_route: 1/1 (100%)

## By scope flag
- (core): 27/40 (68%)

## Tier-3 (needs judge): 7 records

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

### rw-014  [recipient_route / medium]
parse: ok
query: Incoming emails addressed to loui@windmill-events.example, or sent from exactly that address, should be assigned to Loui and tagged 'Windmill', 'Client', and 'Priority'.
- trigger: expected new_conversation_inbound, got new_conversation
- conditions missing: (('from', 'is', ('loui@windmill-events.example',), ()), ('to', 'contains', ('loui@windmill-events.example',), ()))
- conditions hallucinated: (('from', 'is', ('loui@windmill-events.example',), ()), ('to', 'is', ('loui@windmill-events.example',), ()))

### rw-015  [keyword_close / easy]  → needs_judge
parse: ok
query: Dutch review notifications — new incoming emails whose subject contains any of 'heeft een review toegevoegd voor', 'er staat een nieuwe foto op uw bedrijfsprofiel'' — close them and tag 'Google Reviews'.
- conditions missing: (('subject', 'contains', ("er staat een nieuwe foto op uw bedrijfsprofiel'", 'heeft een review toegevoegd voor'), ()),)
- conditions hallucinated: (('subject', 'contains', ('er staat een nieuwe foto op uw bedrijfsprofiel', 'heeft een review toegevoegd voor'), ()),)

### rw-017  [sender_close / medium]  → needs_judge
parse: ok
query: Internal mail: anything arriving from one of these addresses — 'person85@company-51.example', 'person82@company-49.example', 'person83@company-48.example', 'person84@company-50.example', 'person81@company-48.example', 'team@company-52.example' — tag 
- conditions missing: (('from', 'contains', ('person81@company-48.example', 'person82@company-49.example', 'person83@company-48.example', 'person84@company-50.example', 'person85@company-51.example', 'team@company-52.examp
- conditions hallucinated: (('from', 'is', ('person81@company-48.example', 'person82@company-49.example', 'person83@company-48.example', 'person84@company-50.example', 'person85@company-51.example', 'team@company-52.example'), 

### rw-019  [keyword_tag / easy]
parse: ok
query: Tag emails about continuing-education certificates — body contains 'CME/CE/CEU Certificate' — with 'CME'.
- conditions missing: (('body', 'contains', ('cme/ce/ceu certificate',), ()),)
- conditions hallucinated: (('body', 'contains', ('ce', 'ceu certificate', 'cme'), ()),)

### rw-020  [recipient_route / easy]  → needs_judge
parse: ok
query: Anything addressed to or CC'd to jade@brightpath.example: assign to Jade and tag 'Jade'.
- conditions missing: (('cc', 'contains', ('jade@brightpath.example',), ()), ('to', 'contains', ('jade@brightpath.example',), ()))
- conditions hallucinated: (('cc', 'is', ('jade@brightpath.example',), ()), ('to', 'is', ('jade@brightpath.example',), ()))

### rw-021  [recipient_tag / easy]  → needs_judge
parse: ok
query: Auto-label incoming emails sent to yashwi@northwind.example with the 'Yashwi' tag.
- conditions missing: (('to', 'contains', ('yashwi@northwind.example',), ()),)
- conditions hallucinated: (('to', 'is', ('yashwi@northwind.example',), ()),)

### rw-025  [recipient_route / easy]  → needs_judge
parse: ok
query: Emails addressed to celine@chartreuse-restoration.example get assigned to Loui with tags 'Chartreuse', 'Restoration', and 'Priority'.
- conditions missing: (('to', 'contains', ('celine@chartreuse-restoration.example',), ()),)
- conditions hallucinated: (('to', 'is', ('celine@chartreuse-restoration.example',), ()),)

### rw-027  [recipient_route / easy]
parse: ok
query: Load inquiries sent to or CC'd to alvin@freightlane.example get assigned to Alvin.
- trigger: expected new_conversation_inbound, got new_conversation
- conditions missing: (('cc', 'contains', ('alvin@freightlane.example',), ()), ('to', 'contains', ('alvin@freightlane.example',), ()))
- conditions hallucinated: (('cc', 'is', ('alvin@freightlane.example',), ()), ('to', 'is', ('alvin@freightlane.example',), ()))

### rw-029  [keyword_route / easy]  → needs_judge
parse: ok
query: Our web store's contact-form emails have this line in the body: 'You received a new message from your online store's contact form.' Tag those 'Contact Form' and assign them to Priya.
- conditions missing: (('body', 'contains', ("you received a new message from your online store's contact form.",), ()),)
- conditions hallucinated: (('body', 'contains', ("you received a new message from your online store's contact form",), ()),)

### rw-037  [recipient_route / easy]
parse: ok
query: Emails addressed to tmteam.lilah@maplethorpe.example — or sent from exactly that address — assign to Lilah.
- trigger: expected new_conversation_inbound, got new_conversation
- conditions missing: (('from', 'is', ('tmteam.lilah@maplethorpe.example',), ()), ('to', 'contains', ('tmteam.lilah@maplethorpe.example',), ()))
- conditions hallucinated: (('from', 'is', ('tmteam.lilah@maplethorpe.example',), ()), ('to', 'is', ('tmteam.lilah@maplethorpe.example',), ()))

### rw-038  [recipient_tag / easy]
parse: ok
query: Tag Patrick's emails: if the To or Reply-To field contains patrick@harborcrest.example, add the 'Patrick' tag.
- trigger: expected new_conversation_inbound, got new_conversation
