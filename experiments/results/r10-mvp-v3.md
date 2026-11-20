# Round 10, MVP version 3: answers that name things, today's date, rules beyond timing, understanding, integrations (counts only)

13 to 14 Nov 2026. Derrick's library (`data/all`, 136,445 items once 463 friends' items are left out), `gpt-5.4-mini`,
prompts `interpret_v5`, `compose_v5`, `extract_v3`. The design is `experiments/mvp/DESIGN.md` sections 12 to 15.
Conversations from the live checks are outside git.

## What was asked (13 Nov, after trying version 2), and what was built

| Asked | Built |
| --- | --- |
| "Context seems weird" on a follow-up | A follow-up that changes the request ("something that isn't X", "not from that creator", "shorter") runs a new search with the change. The rejected pick's series is left out. The opening line names the merged request |
| "It says 2024 but it's 2026" | The bot knows today's date and when each post was posted. Passed deadlines never lead. Old "now open" posts go last with their date. A post from an earlier year gives nothing to a time-sensitive answer |
| "A CONCRETE answer and CITE the link" | A new kind of detail, `items`: the named things a post's own text lists, each with the post's own words, under the post's title, dates and link |
| "The exact opportunities that were mentioned in the specific post" | Same. Each thing keeps its name. A follow-up can act on one thing by number or by name |
| "Think more carefully about the rules" | Reminders before a thing's own deadline; rules that stay quiet when empty; reminders that repeat until done; one nudge for an overdue to-do |
| "Integrations" | A read-only MCP server for the person's own agent (prototype); "export my data"; a message ready to forward |
| "Tie everything back to the first vision" | Trends ("what have I been into lately"), the theme check (pursue, practise, someday, enjoy, not me), a recap. See the scorecard below |

## Where a post's date comes from

| Platform | Source | Coverage |
| --- | --- | --- |
| Instagram | The post's link holds its creation time (the shortcode read as a number). Nothing is fetched | 20,496 of 20,500 items decode to a date on or before the day the person kept them |
| YouTube | `publishedAt` from the official API call already made for lengths | Kept in the same cache |

## The founder's four cases, live on the real library (14 Nov, after the last fix pass)

| Case | Result | Still wrong |
| --- | --- | --- |
| 2026 opportunities, winter or next summer | 6 named programmes from 1 post, each with the post's own words; every name is in its post's text; 0 junk; 2 "Also in your saves" lines | Posts whose names are only in the video are listed, not read |
| Three asks in one message | 3 labelled parts. The opportunities part names the same 6 programmes. The 2024 post gives nothing. The deadlines part says nothing in the saves has a readable deadline still ahead, then the closest | Each part is short (2 picks) |
| Blender, then "something that isn't a donut" | A new search; 0 picks from the rejected series; the opening line names the change; the closest pick says what is missing | Only close picks came back. The first answer's 2 picks are both from one series |
| UI/UX libraries | Honest, not good. It opens "Nothing I found is a clear fit" and lists the closest things. No component type is counted as a library. 5 of 6 listed icon sites are shown | The first close source is a post of component types. The posts that do name libraries keep the names in their slides, and the small model picks differently between runs |

The UI/UX case needs a change to a prompt or the model (the small model marked component types as libraries).
A prompt change needs a run of the 20 draft requests before and after. That did not fit under the spending cap.

## Rules beyond timing (DESIGN section 13)

| Rule | Example | What happens |
| --- | --- | --- |
| Before a thing's deadline | "remind me 3 days before the second one closes" | Read by code, 0 model calls. A one-time reminder at 9am. Default 3 days. No date in the post: one question. Optional all-day calendar entry |
| Quiet when empty | Any new repeating rule that searches the library | Sends nothing on a day with nothing new. One line the first time. "Tell me even if there's nothing" turns it off |
| Until done | "remind me every morning at 8 to apply until I've done it" | Repeats until the person says "done" |
| Overdue to-do | A to-do more than a day past due | One nudge: "done", "tomorrow" or "drop it". One at a time |
| With each new export | "every export" after a trends answer | Sends the trends when a new export is imported |
| A recap on a schedule | "every sunday at 6pm send me a recap" | At most 6 lines. An empty week sends nothing |

## Understanding (DESIGN section 14)

| Part | What it does | Live count on the real library |
| --- | --- | --- |
| Trends | Compares the last 56 days with the 182 days before, by share of what was kept, per profile topic. No model call | 144 kept lately, 834 before. Of 8 topics: 2 rising, 2 fading, 2 steady, 2 too few to tell. Counted in 1.2 s |
| Theme check | Each topic gets one label: pursue, practise, someday, enjoy or not me. Asked once, after the first trends answer | Offline tests only |
| Recap | Rules sent, quiet and skipped; to-dos; what is coming up; the library's age. One rule suggestion from 3 or more repeated asks | 3 lines on a copy of the test store |

## Integrations (DESIGN section 15)

| Integration | What it does | Limits |
| --- | --- | --- |
| The person's own agent (MCP, prototype) | 7 read-only tools over stdio for one person: search, one save, recent saves, profile, rules, to-dos, trends | Runs on the person's own machine. Friends' posts never. Personal topics hidden by default. Proposed as A-011; the design critic advised waiting |
| Export | "export my data" writes rules, to-dos, profile, answers and a list of saves (links and dates, no captions) | To a folder or the person's own email |
| Share | "send this to my sister" gives one message ready to forward | The bot never sends to anyone but the person |
| Calendar | A deadline can be added as an all-day entry (link and file) | No sign-in; the person taps the link |

MCP live check over stdio: 7 tools, started in 0.9 s; first search 36.7 s (engine start), second 0.7 s; every result
starts with the line that post text is data; 3 log rows with counts only.

## Scorecard against `docs/00-vision.md`

| The vision says people want to | Now | Missing |
| --- | --- | --- |
| Remember it | Search over the whole library, with honest "nothing" and "closest" | A person's grades |
| Get the gist | Ingredients, steps, key points and named things from the post's own text | Posts whose content is only in slides or video |
| Act on it | To-do and grocery lists, calendar, email, reminders before a deadline, until-done reminders | Lists live in the bot, not in outside task apps |
| Understand themselves | Trends, the theme check, "what did I park?", the recap | The first report after an upload; English only |
| Share it with the right person | A message ready to forward | The bot cannot send to other people |

| Core loop step | Now |
| --- | --- |
| 1. Onboarding | Five-message setup with a guessed profile |
| 2. Upload and first report | Upload and import work. No report after the import |
| 3. Theme check | Built, asked once after the first trends answer |
| 4. Ongoing capture | Not built. Reminders to export, and an upload box |
| 5. Requests and rules | Built |
| 6. Digest | A recap on request or as the person's own rule. Never sent unasked |
| The person's own agent (the paid core) | A read-only prototype for one person on their own machine |

## Measured

| Measure | Result |
| --- | --- |
| Offline tests (`experiments/mvp/tests`) | 1,043 pass (755 at version 2). The demo's 10 still pass |
| 20 draft requests, `extract_v2` to `extract_v3` | handled 20 to 20; errors 0 to 0; answers with picks 19 to 19; items answers 3 to 3; cost per run $0.158 to $0.178 |
| 20 draft requests, before items to after (round 7) | handled 20 to 20; errors 0 to 0; answers with picks 19 to 19; items answers 0 to 3; cost per run $0.125 to $0.158 |
| Recipe, workout and tutorial answers | Byte for byte the same as before round 7 on the fakes, after every round |
| Live defects written down this version | 10 (findings 93 to 102), each fixed with tests and checked by a second agent, except the UI/UX case above |
| Code size | about 20,800 lines of Python and about 17,200 lines of tests |
| Spend on the MVP ledger | $9.73 of the $10 cap (the bot refuses at $9.95) |

## Left as is

- The UI/UX libraries case (above).
- A rule made from a message with several asks runs as one request. "Another" after a split answer repeats the whole message.
- "Add them all" after an items answer adds the source posts, not each thing.
- Date wording, trends and recap text are English only.
- A search leaves its query text in the library's query cache; "delete my data" does not clear it.
- The MCP personal-topic filter reads a post's text and collection names, not the creator's handle.
- New repeating rules are quiet on empty days by default. This is one line to change if the founders prefer the old default.
- Two wordings of a deadline reminder behave differently with too little time left (one refuses, one sets the next 9am).
- Everything under "Left as is" in `r10-mvp-v2.md` still holds.

## For the founders to decide

- A-010 (recap, quiet-when-empty, done-reminders, nudges, trends and theme check): Proposed.
- A-011 (the MCP prototype ahead of the query API): Proposed, both founders. The design critic advised deferring it.
- A new spending cap. The UI/UX case needs a prompt change and two runs of the 20 requests (about $0.40), plus live checks.
- Capture between exports: a link texted to the bot, or a YouTube playlist. Neither is built.
- Whether lists should also go to an outside task app. That needs an app registration.
