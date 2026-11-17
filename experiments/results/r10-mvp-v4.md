# Round 10, MVP version 4: the bot does the work (counts only)

17 Nov 2026. Derrick's library (`data/all`, 136,445 items once 463 friends' items are left out), `gpt-5.4-mini`
for the interpreter, composer, extractor and email drafts, `gpt-5.5` for one judge call per kind request.
Prompts `interpret_v5`, `compose_v5`, `extract_v4`, `judge_kind_v2`, `draft_v2`. The design is
`experiments/mvp/DESIGN.md` section 12 ("Round 9" parts) and section 16. Conversations from the live checks are
outside git.

## What was asked (17 Nov), and what was built

The request: iterate on the bot from the vision; add more connectors than email; cancel a subscription for the
person; put something in their email; draft and send an email; "make it easier for them to do the work and do the
work for them"; "the idea is Instinct but for social media".

Two answers from Derrick set the limits: the spending cap is now $20 in total, and for anything that reaches other
people or outside accounts the rule is **"always show, then wait for yes"**.

| Asked | Built | What the bot never does |
| --- | --- | --- |
| Draft and send an email | A draft card (to, subject, body) written as a complete short email, then a tap-to-send link. For the operator with their own mailbox set up: "send" sends it from their address after a 2-minute hold | Send before "send" on the exact last version. Take a recipient from a post. Say "sent" before the mail server accepted it |
| Put something in my email | A link that opens it as a new message. For the operator with the mailbox: a real draft in the Drafts folder | Read the inbox. The mailbox code can only add a draft and delete that same draft |
| Cancel my subscription | The checked steps and the merchant's own cancel link, the Apple or Google Play route, or a written notice as a draft card; then an offered reminder to check it went through | Sign in as the person. Take a password. Say "cancelled" |
| Act on a saved post | "apply to the second one": a deadline reminder, a calendar entry, a checklist from the post's own lines. "book it": a Maps link and a calendar hold. "buy the ingredients": a shopping list | Fill in forms, book, pay. A caption line like "send $5" never becomes a step |
| More connectors | Apple Reminders and Calendar on the operator's Mac; TickTick and Todoist by token; a webhook. Every add shows a preview and waits for "yes" | Take a token in the chat. Write from a timed rule. Remove anything it did not place |
| Do the work | "do 2 for me" hands a to-do to the helper that fits. "add them all" adds each named thing. "what did you do for me" lists what was done and what was only prepared | Claim more than its own records show |
| A concrete answer for "UI/UX libraries" | A stronger model judges the named things in one call; code searches and reads by the kind asked for | Count an icon pack, a component type or an account as a library |

## What "Instinct" is, and what was taken from it

Instinct is an invite-only personal assistant (launched August 2026). The person texts or calls it and it acts:
it reads and sends from connected mail, makes phone calls, books, buys and cancels, by driving a cloud browser
with stored logins. Reported failures: email sent before approval, instructions planted in an email being
followed, a user's account banned by a booking site, a provider cutting off access, no undo.

| Lesson | In this bot |
| --- | --- |
| Ask for the one missing thing, show exactly what will change, ask yes, report the real outcome | Every helper follows this order |
| A send before approval is the worst failure | The yes is bound to a hash of the exact text last shown. Any change voids it. One send per yes |
| Text from outside can carry instructions | Captions and post text are data. They can never name a recipient, a link or an action |
| Logged-in bots get accounts banned | No sign-in as the person, anywhere. Only links, the person's own mail app, their own token |
| No undo | Everything the bot places can be removed by "undo", except a webhook, which says so before the yes |

Sources for the product facts are listed in the founders' document (TechCrunch, Fortune, Android Authority, the
company's own terms). Nothing here was taken from the model's memory.

## Connectors

| Place | Who | How it is set up | Undo | Tried for real |
| --- | --- | --- | --- | --- |
| The bot's own lists and reminders | Everyone | Nothing | Yes | Yes |
| Calendar link, email link (`mailto:`) | Everyone | Nothing | The person does not tap it | The link text only; not on a phone |
| The operator's mailbox: send | Operator | `MVP_OPERATOR`, `MVP_MAILBOX_ADDRESS`, `MVP_MAILBOX_APP_PASSWORD` in a private file | "undo" within the 2-minute hold | No (fake server only) |
| The operator's mailbox: Drafts | Operator | Same | Deletes that draft | No (fake server only) |
| Apple Reminders and Calendar | Operator, bot running on their Mac | "connect my mac", then allow the prompt | Deletes what the bot added | No (fake AppleScript runner only) |
| TickTick | Operator | `MVP_TICKTICK_TOKEN` in the private file | Deletes the task | No (fake HTTP only). Creating in the inbox is unverified |
| Todoist | Operator | `MVP_TODOIST_TOKEN` | Deletes the task | No (fake HTTP only) |
| Webhook (IFTTT, Make, Zapier) | Operator | `MVP_WEBHOOK_URL` | None, and the preview says so | No (fake HTTP only) |
| Apps with no connector (Notion and others) | Everyone | Nothing | Yes | Says "I can't reach Notion, so I added it to your list here" |

Secrets come only from the environment. A token or password typed in the chat gets a fixed line, is not kept, and
reaches no model.

## Cancelling: the route file

`mvp/cancel_routes.json`: 15 merchants plus the Apple and Google Play subscription pages.

| Entries | Count |
| --- | --- |
| With a link, from the merchant's own help page read on 17 Nov | 7 |
| With steps only (the page gives only a sign-in link) | 2 |
| With no source (page blocked or not found): the person is asked how they pay | 6 |
| Days a checked link stays valid | 60 |

## Answers that name things ("UI/UX libraries")

| Step | Change | Measured |
| --- | --- | --- |
| Slice U | The extractor is told the kind asked for. A clear post that names nothing leads | 16 requests: things truly of the kind 22 of 36, then 32 of 41 |
| Slice U2 | One batched call to a stronger model judges every named thing. A thing two posts name is shown once | 22 requests: truly of the kind 44 of 57, then 46 of 54. Wrongly counted in "I found N": 5, then 0. Cost of the judge: $0.0035 per kind request |
| Live fix | The read step knows a run-together word ("uiux", "gamedev"). A trailing purpose ("for my next project") is not a test each post must pass. Code adds a search of the kind phrase. Spanish kinds | 22 requests: truly of the kind 47 of 56, wrongly counted 0 |

Derrick's own wording, fresh runs with his profile:

| Measure | Before round 9 | After |
| --- | --- | --- |
| Answer kind | "Nothing I found is a clear fit" | A list of named things in 4 of 4 runs |
| A real UI library counted | 0 | 1, the same one in all 4 runs |
| Icon pack or component type counted as a library | no (shown as closest) | 0 of 4 runs |
| The "close" posts under it | n/a | Differ between runs |
| Cost per answer | about $0.02 | about $0.03 |

Still true: two wordings of one request can give different close posts. The cause is the interpreter's search
words and the composer's verdicts, which vary between runs.

## Email drafts: the new prompt

`mvp/evalset/drafts_dev.jsonl`, 25 synthetic cases, `draft_v1` against `draft_v2` (two runs each):

| Count | v1 | v2 |
| --- | --- | --- |
| Forms valid | 24, 24 | 25, 25 |
| Passed the fact checks on the first try | 24, 24 | 25, 25 |
| Fell back to code-built words | 1, 1 | 0, 0 |
| Drafts of 2 to 5 sentences | 4, 3 | 22, 23 |
| Complete emails a person would send as is (builder's reading) | 16 | 25, 24 |
| Complete (checker's own run and reading) | n/a | 23 |
| Invented facts, reasons, promises or claims (checker's reading) | n/a | 0 |

The checks in code are unchanged or stricter: every number, date, day, amount, address, link and capitalised name
in a draft must be in the person's own message or the checked post lines. A brief that says its own claim is
untrue gets no draft.

## Adversarial checks

| Check | Attacks | Broke and fixed | Examples of what broke |
| --- | --- | --- | --- |
| Email and cancelling | 27 | 15 | "send it?" started a send. A second "send" dropped the first waiting email silently. A to-do taken from a post named the recipient. A rewrite could add a day or "I already took care of it". After an uncertain send the bot said "It went to" |
| Acting, connectors, receipts, routing | 55 | 15 | "book me a table" after a recipe opened a booking menu. "do 2" ran an older menu's offer. Caption lines like "send $5 to register" became checklist steps. A retry after a time-out could add twice without a warning |
| The live fix pass | 3 groups | 7 | A title before an address was not read. A Spanish kind request got none of the fix. "none" then a date lost the date question |

| Routing measure | Result |
| --- | --- |
| Earlier test messages re-run on the code before and after round 9 | 1,725 runs; 11 answers changed, all intended |
| Ordinary messages that only contain a trigger word | 144 runs; 0 taken by a new helper |
| The 20 draft requests taken by any new code read | 0 of 20 |
| Rule-eval texts taken by any new code read | 1 of 159 (an allowed one) |
| Earlier stop, pause and change phrasings taken by the cancel helper | 0 of 123 |
| Secrets typed in chat, 71 combinations of wording and place | 0 kept, 0 shown, 0 logged |

## My live check on the real library (17 Nov)

| Flow | Result |
| --- | --- |
| UI/UX libraries, short wording | 2 libraries from 2 posts, 1 close post |
| UI/UX libraries, Derrick's wording | Before the fix: "I recommend" on a post whose names are in its slides. After: 1 library counted first, 2 close posts |
| Opportunities; the three-part message; the donut follow-up | All as in version 3 |
| "what's number 2?", "add them all to my reading list" | Answered from the thing's own words; 3 things added |
| Email to a typed address; "make it friendlier"; "put this in my email"; "send" as a tester | Card with the address filled in; a changed version; the link again with a plain line; "I can't send from your address" with the tap line |
| "cancel my netflix subscription", "yes", "friday" | Checked steps and link; a reminder set for Friday 9am |
| "apply to the first one" | No date in the post: asked for the date (now also a menu) |
| "buy the ingredients" | 3 ingredient lines on the shopping list. The main ingredient is only in the post's steps, so it is missing |
| "what did you do for me" | Added, prepared and waiting, with the undo line |
| A token typed in chat | The fixed line; not kept |

5 defects written down (findings 104 to 108) and 1 on kind requests (103). All fixed and checked by a second agent.

## Measured

| Measure | Result |
| --- | --- |
| Offline tests (`experiments/mvp/tests`) | 2,086 pass (1,043 at version 3). The demo's 10 still pass |
| 20 draft requests on the real library, after each step | handled 20, errors 0 every time; answers with picks 18 or 19; "I recommend" 14 to 17 (run-to-run variation) |
| Recipe, workout and tutorial answers | Byte for byte the same as before round 7 on the fakes, after every step |
| A store made by version 3's code | Loads and gains the new tables |
| Code size | about 30,900 lines of Python and about 25,900 lines of tests |
| Spend on the MVP ledger | $16.16 of the $20 cap |

## Left as is

- Nothing outside the bot has run for real: the mailbox, Reminders and Calendar, TickTick, Todoist, the webhook, the `mailto:` link on a phone.
- TickTick's own page does not confirm that a task can be created in the inbox without a project id. `MVP_TICKTICK_PROJECT` overrides it.
- Two wordings of one request can still show different close posts.
- A Spanish items answer says "cosas" for the kind. The email, cancel and post-action phrasings are read in English only.
- The fact checks on a draft cannot see a lower-case name or an intent with no fact words.
- With a rule preview and an outside preview both open, "yes" goes to the outside one.
- "buy the ingredients" uses only the lines the post gives as ingredients.
- An earlier local commit held test wording close to a real post; the tree now has made-up text, and that commit is in the branch history.
- Everything under "Left as is" in `r10-mvp-v3.md` still holds, except "add them all" and the UI/UX case.

## For the founders to decide

- A-012 (emails to other people as drafts, the cancel helper, acting on a post): Proposed.
- A-013 (the operator's own mailbox: a draft, and a send after "send"): Proposed, both founders.
- A-014 (connectors: the registry fields, the Mac, token connectors, the webhook): Proposed, both founders.
- Whether an add to the person's own task app needs a "yes" each time. It does now, by the rule Derrick chose. It could be "add at once, with undo".
- A-008 to A-011 are still open.
