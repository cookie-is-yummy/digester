# Brief, round 10 (DRAFT): the MVP skeleton. Text a request, get cited answers from your own saves, on a schedule

> **Status: DRAFT, not binding.** Written by the agent on 12 Nov 2026 at Derrick's request, as the build plan for a three-day MVP. It replaces the earlier draft of this brief (a hand-run action test), which is kept, unscheduled, in `PARKED-action-test.md`. The hosted agent-access pilot stays parked in `PARKED-agent-layer-pilot.md`. This brief becomes binding when both founders accept it and amendment A-008 in `docs/amendments.md`.
>
> **Until then,** an agent may build and test the code below on this branch, on Derrick's library and on synthetic data only. Nobody outside the founders uses it, and no tester data is touched.

## 1. What we are building, in one paragraph

A person texts the product in plain words: "send me a new pasta recipe every Friday at 7pm", or "what can I make with chicken and rice from my saved recipes?". The product turns the text into a rule and shows a preview: "Every Friday 7pm, one pasta recipe from your saves. Reply YES to start." It searches that person's own saved, shared, liked and watched posts from Instagram and YouTube. It picks what fits and replies in the same message thread. Each pick links to its post and says why it was chosen. Where the post's own text has the ingredients, the reply lists them. Where it does not, the reply says "the recipe is in the video". When nothing good fits, it says so instead of padding.

This is the skeleton the product grows from, and the version shown to the first outside users. It is prototype code under `experiments/mvp/`. It is rewritten as product code after the decision that follows the first sessions.

## 2. Why this, and what it tests

- **Why build now.** Derrick's view, which this brief adopts: people judge value by trying it on their own saves, not by reading a plan. The aim is not that users act on every message. The aim is that they see their saves become easy to use, and want to keep it.
- **What already exists.** The `experiments/demo/` app imports Instagram and YouTube exports into a library and searches it with the round-8 pipeline (Q8), and it leaves friends' posts out. About 70% of the MVP's hard part is therefore built. The new parts are the request-to-rule step, the answer step, the schedule and the message channel.
- **What the skeleton must show** by the end of day 3:
  1. A request in plain words becomes a correct rule, with a preview, every time or nearly.
  2. The answers are good enough that Derrick would send most of them unchanged.
  3. It never invents: every cited post is from the person's library, and every extracted ingredient is in that post's own text.
  4. A second person can set it up on their own library without help.
- **What the sessions afterwards test** (section 10): whether people keep a rule running, reply to it, and pay.

**Library check (counts only, run on 12 Nov on Derrick's library).** Of about 400 recipe posts he saved or sent to himself, about 140 have the ingredients written in the caption, including 19 pasta posts. The pasta example works from captions alone for a few months. About two in three recipe posts carry the recipe only in speech or on screen, so the reply must say "the recipe is in the video" for those. His saves also hold about 120 photography or editing posts. His YouTube history holds titles only; the export has no descriptions.

## 3. Scope

| In the MVP | Not in the MVP |
| --- | --- |
| Requests and replies by text message (channel in section 6) | A web app, a hub or a phone app |
| Recurring rules: a day or days of the week and a time, in the person's timezone | Rules triggered by events ("when I save a recipe…"), deadlines |
| One-off questions over the library, and follow-up questions on the last answer | Searching for new content outside the person's library |
| Extracting ingredients, steps or key points only when they are in the post's own text | Transcripts, audio or video understanding |
| Managing rules by text (list, pause, resume, change, stop), "delete my data", help | Sharing rules between people |
| Feedback replies: 👍, 👎, "more like 2", "stop", "pause" | Learned personalisation beyond the feedback rules in section 5 |
| Libraries built from the Instagram export and Google Takeout, with the demo's importer | Live capture of new saves (a later step: share-to-account) |
| One machine runs everything; data stays on it | Hosting, accounts, payments inside the product |
| Founders plus up to 10 testers who consent | The public |

## 4. What the person sees

The conversations below are the spec for the message flows. The wording is a draft.

**First message.**
> Person: hi
> Bot: Hi, I'm the digest bot. I find things in what you've saved and watched on Instagram and YouTube, and send them when you want them. Before we start, please read and agree to this note: [link]. What city are you in, so I get the times right?

Libraries are loaded by a founder before the first message, from the person's exports. The bot knows the person by their handle in the message app.

**A recurring rule.**
> Person: send me a new pasta recipe every friday night for pasta night
> Bot: Here's what that would look like this week:
> 🍝 **Creamy lemon garlic pasta** from @creator · you saved it in March
> Why: a weeknight pasta with the ingredients listed.
> Ingredients (from the caption): spaghetti 200 g, lemon, garlic, parmesan, butter
> [link to the post]
> Every Friday at 7pm I'll send one pasta recipe you haven't had from me before. Reply YES to start, or tell me what to change.
> Person: yes but nothing with cream
> Bot: Got it: every Friday 7pm, one pasta recipe, no cream. Starting this Friday.

**A one-off question, then a follow-up.**
> Person: what can I make tonight with chicken and rice?
> Bot: Three from your saves: (1) … (2) … (3) … The second one has the recipe only in the video.
> Person: which of those has the fewest ingredients?
> Bot: Number 1: six ingredients, all listed in its caption. [link]

**A reminder of inspiration.**
> Person: every sunday at 4pm remind me of photo editing ideas I've saved, I edit then
> Bot: (preview) … Reply YES to start.

**Nothing good.**
> Bot: No new pasta recipe this week. I've sent you all 19 I could find with ingredients listed. Want ones where the recipe is in the video too?

**Managing rules.** "my rules" lists them with numbers. "pause 2", "stop 2", "change 1 to Saturday" and "stop everything" work. "delete my data" removes the person's library, rules, runs, deliveries and feedback, and deletes their conversation from Messages on the bot Mac, after a YES. A founder confirms by message within 24 hours.

**Feedback.** 👍 or 👎 as a reply to a pick, "more like 2" or "less like this" change what later runs pick (section 5).

## 5. Reliability rules (hard rules, enforced in code, for every reply that cites items: previews, scheduled runs, one-off questions and follow-ups)

1. **Only the person's own library.** Every pick is an item from their library, with its link. The code rejects any item ID that was not in the candidate list sent to the model. A follow-up may use only the items in the last answer, plus any new search it states.
2. **Nothing invented.** An extracted ingredient, step or quote must appear in the item's own text, by a normalised string match. A line that does not match is dropped, and the item is marked "the details are in the video". The match is against the full caption from `items.jsonl`. Counts and comparisons ("six ingredients", "fewest") are computed by code from the matched lines, not stated by the model.
3. **Abstain rather than pad.** If fewer good candidates exist than asked for, send fewer, or none, and say why. The model gives each pick a fit score; picks under the threshold are not sent.
4. **No repeats.** A recurring rule never sends the same item twice, through a deliveries table checked before every send. One-off answers and follow-ups may cite items sent before.
5. **Friends' posts are never used.** The Instagram importer removes posts by mutual follows when the library is built, and `library.is_friend` is checked again in retrieve. A library whose import warned that the follower lists were missing is not used until the export is redone with them.
6. **Captions are data, not instructions.** Third-party text goes to the model inside marked data fields, with a system instruction to treat it as data. Captions are cut to 600 characters, taken from `items.jsonl`, not from the 260-character search rows.
7. **A preview before any recurring rule starts.** Nothing is scheduled until the person replies YES. A preview is not a delivery: after YES, the edited request is run again, so the first send obeys any change ("no cream") and may differ from the preview.
8. **Caps.** At most 5 scheduled messages a day per person, no messages between 10pm and 8am local unless the rule asks for it, and a cost cap of $1 a day per person.
9. **Feedback is obeyed.** An item with 👎 is never sent again by any rule or answer. "Less like this" lowers items from that creator and that topic for that rule. "More like 2" adds item 2 as an example to the rule.
10. **No advice.** The bot finds and quotes. It gives no medical, legal or financial advice, and declines health goals, as the earlier briefs did.

## 6. Message channel

**Recommendation: iMessage, through a Mac that runs the bot and holds the libraries.** Keep Telegram as a backup for anyone without an iPhone. Start SMS registration only if the founders want SMS for the public later.

| Option | Setup for this week | Can it message people days later? | Cost | Main risk |
| --- | --- | --- | --- | --- |
| **iMessage from a Mac** (a script sends through Messages and reads replies from its database; open-source tools such as `imsg` do this) | An afternoon. No approval | Yes | $0 | Unofficial. The Mac must stay awake and online. Forum reports (not Apple's own text) describe accounts flagged as spam. Only Apple users can receive it |
| Telegram bot | An hour. No approval | Yes, once the person has started the bot (common practice; Telegram's pages do not state it) | $0 | Testers must install Telegram |
| SMS through Twilio | US carrier registration first: about 2 days to a few weeks. Unregistered traffic is blocked | Yes, after opt-in | A few dollars a month | Timing of approval |
| A paid iMessage service (for example Sendblue, LoopMessage) | Minutes to days; free sandboxes cannot send first | Plans differ: Sendblue's $100 plan answers people who wrote first; LoopMessage needs add-ons to write first | About $60 to $150 a month per line | Not approved by Apple; messages pass through the vendor |
| Instagram DMs | Needs a published Meta app, and testers added as app roles | No: replies are limited to 24 hours after the person's last message | $0 | Weekly messages are not allowed |
| WhatsApp | Same day with a test number for up to 5 people | Only with approved template messages | Per message | Meta's January 2026 policy restricts general AI assistants |

Sources: the channel notes from 12 Nov 2026 in the review's working files (Telegram Bot FAQ, Twilio pricing and registration pages, Apple Business Register guide, vendor pages, Meta's Instagram and WhatsApp messaging docs). Vendor prices come from vendors' own or rivals' pages and are unconfirmed.

**How the iMessage channel works.**
- A separate Apple Account for the bot, signed in to Messages on the Mac. People text its email address, so no founder's personal number is shown. Apple asks for a phone number to secure a new account; a founder's number is fine for that.
- Sending: AppleScript tells Messages to send to a handle.
- Receiving: the bot polls the Messages database (`~/Library/Messages/chat.db`, opened read-only) every few seconds for rows above the last one seen with `is_from_me = 0`, so it never answers itself. On recent macOS the text is often only in the `attributedBody` blob, so the reader decodes that when `text` is empty. A tapback (👍, 👎) is a separate row pointing at the bot's message; after each send the bot records the ID of its own outgoing row, so a tapback maps to that delivery. A tapback on a message with several picks counts for all of them; for one pick the person types "👎 2". The terminal that runs the bot needs Full Disk Access and permission to control Messages. Each read is kept short.
- The channel sits behind one small interface (`receive()` and `send(handle, text)`), so Telegram, SMS or a paid service can replace it without touching anything else. A console channel is used for development and tests.

## 7. How it works

```
message in ─► handler ─► interpreter (LLM, JSON) ─► validated rule ─► preview run ─► "Reply YES"
                                                                         │
scheduler (every 30 s) ─► due rules ─► executor ─► retrieve ─► compose (LLM, JSON) ─► checks ─► message out
                                                    │                                     │
                                         demo engine (Q8 search)              deliveries · feedback · ledger
```

**Parts and where they come from.**

| Part | New or reused | What it does |
| --- | --- | --- |
| Library and search | Reused with a small change: `experiments/demo/engine.py` gets a `depth` option on its `search` command that returns the friend-filtered ID order (up to 300) instead of 20 rows. `ingest.py`, `ig_import.py`, `library.py` are unchanged | Runs Q8 search in one `engine.py serve` process per library. `mvp/retrieve.py` reads the library's own `corpus/items.jsonl` and `interactions.jsonl` for full captions, interaction kinds and the date of each kind (the save date, not the first-seen date), then filters by kind and date and removes items already sent |
| Engine processes | New: `mvp/engines.py`, adapted from the demo app's `Worker` | One engine process per library, because the engine allows one library per process. Starts, restarts and talks to them over JSON lines. Up to about 4 resident on a 16 GB Mac; beyond that, a library's process starts about 2 minutes before its rule is due, and a one-off question gets "one moment" while it loads |
| Store | New: `mvp/store.py`, SQLite | People, rules, runs, deliveries, feedback, pending confirmations |
| Interpreter | New: `mvp/interpret.py` | Turns a message into an intent and, for rules and questions, a rule spec. One LLM call, JSON out, validated with Pydantic. Code, not the model, works out dates and times |
| Retrieve | New: `mvp/retrieve.py` | Runs 2 to 4 searches from the spec, merges them, filters friends, applies kind and date filters, removes sent and disliked items, and keeps the top 40 |
| Compose | New: `mvp/compose.py` | One LLM call: picks items that fit, gives a short reason and a fit score, and extracts details from the item text. Then the checks in section 5 |
| Render | New: `mvp/render.py` | Turns picks into a short message with links |
| Executor and scheduler | New: `mvp/run.py`, `mvp/schedule.py` | Fires due rules, sends, records deliveries; a fake clock for tests |
| Channels | New: `mvp/channels/console.py`, `imessage_mac.py`, `telegram.py` | Receive and send |
| Ledger | Reused: `experiments/lib/ai.py` | Every model call logged with purpose, prompt version, tokens and cost |

**The rule spec** is a subset of RuleSpec v1 in `docs/06-rules-and-actions.md`. The only action is `message.send`. `when` uses days and a time instead of a cron string, because code builds the schedule.

```json
{
  "v": 1,
  "when": {"type": "schedule", "days": ["FRI"], "time": "19:00", "timezone": "America/New_York"},
  "content": {
    "goal": "a pasta recipe for pasta night",
    "searches": ["pasta recipe", "easy pasta dinner", "spaghetti sauce"],
    "kinds": ["save", "collection", "share_self", "playlist", "like", "watch"],
    "platforms": ["instagram", "youtube"],
    "count": 1,
    "extract": "ingredients",
    "avoid": ["cream"],
    "exclude_sent": true
  },
  "do": [{"action": "message.send"}]
}
```

`when.type` can be `now`, `once` or `schedule`. `extract` can be `none`, `ingredients`, `steps` or `key_points`. `kinds` is an order of preference over the kinds the importers write: Instagram `save`, `collection`, `share_self`, `like`, `watch`, `view`; YouTube `playlist`, `share_self`, `like`, `watch`. Saves, playlists and posts sent to yourself rank first, then likes, then watches. A filter that removes every item of a listed platform is a validation error. `exclude_sent` drops items this rule has already delivered (rule 4). A date filter uses `saved_after` and `saved_before`, worked out by code from the request and checked against the date of the matching interaction.

**Intents the interpreter returns:** `new_rule`, `ask` (a one-off question), `follow_up` (about the last answer), `change_rule`, `list_rules`, `pause`, `resume`, `stop`, `feedback`, `delete_data`, `help`, `unsupported`. An unsupported request gets the nearest thing the bot can do, and is logged as a feature request.

**Prompts** live in `mvp/prompts/` with a version in each file name: `interpret_v1.md` and `compose_v1.md`. Changing a prompt means a new version and a rerun of the test set (section 9).

**Packages.** `pydantic>=2` goes in a new `experiments/mvp/requirements.txt`, next to the demo's requirements.

**Models.** `gpt-5.4-mini` for the interpreter and the composer, with the OpenAI key already used by the demo. The estimate is under 1 cent per run, so a weekly rule costs a few cents a month. Search embeddings work as in the demo.

**Data kept.**

| Table | Holds | Does not hold |
| --- | --- | --- |
| `people` | Handle, display name, library folder, timezone, consent version and time, paused flag | Anything from their messages beyond the above |
| `rules` | The person's request text, the spec, status, next run time | |
| `runs` | Rule, time, candidate count, picks, fit scores, cost, errors | Captions |
| `deliveries` | Rule, item ID, run, time | |
| `feedback` | Delivery, kind (up, down, more, less), time | |
| `requests` | Requests the bot could not do, for the backlog | |

The message database of the Mac is Apple's own; the bot only reads it. Libraries stay in `data/` on the Mac, outside git. Raw export zips are deleted once the library is built. OpenAI receives item text and requests under API terms that exclude training, and the consent note says so.

## 8. The three days

Founder hours are about 20 a week each; most of the building is the agent's. Times are the agent's estimate.

**Day 0, Thursday 12 November (today): decide and prepare.** About two founder-hours.

| Task | Owner |
| --- | --- |
| Accept or change this brief, and decide section 12 | Both |
| Write 20 test requests from real life, before anything is built: 8 recurring rules, 8 one-off questions, 4 hard cases (vague, unsupported, nothing to find, a follow-up). Keep them in `data/mvp/requests.jsonl`, outside git; commit only their SHA-256 | Derrick |
| Ask Eason and three to five other people to request their Instagram export and Takeout now, because exports take days | Eason |
| Create the bot's Apple Account, and choose the Mac that will run the bot | Derrick |
| Scaffold `experiments/mvp/`, the store, the console channel and a fake clock | Agent |
| Standing deadline from round 9: delete the YouTube Data API reference text (`data/yt/ref`, `data/all/yt_ref`) from every copy by 29 November 2026, and record it in `STATE.md` | Derrick |

**Day 1, Friday 13 November: the answer works.**

| Task | Owner | Done when |
| --- | --- | --- |
| Interpreter and the rule spec, with validation and time handling | Agent | |
| A 20-line iMessage test on the Mac: send to Derrick's phone, read his reply from the Messages database, including the `attributedBody` case | Agent writes; Derrick runs | Works by Friday evening |
| Engine `depth` option, the engine process pool and the retrieve step; the demo's parity test still passes | Agent | |
| Composer, the checks in section 5, and rendering | Agent | |
| Run the 20 requests end to end in the console on Derrick's library; write `results/r10-mvp-day1.md` with counts only | Agent | 18 of 20 give a valid rule or a sensible question back. No check in section 5 fails |
| Grade each answer: send as is, send after a small edit, or not sendable | Derrick | 15 of 20 sendable as is. For the 4 hard cases, "sendable" means the right question back, the nearest alternative, or an honest "nothing found" |

**Day 2, Saturday 14 November: it lives in Messages.**

| Task | Owner | Done when |
| --- | --- | --- |
| iMessage channel, and the Telegram channel as backup. The agent cannot run macOS here, so Derrick runs each version and reports errors | Agent writes; Derrick runs it on the Mac | If the Friday test failed, or iMessage is not working by Saturday noon, Telegram is used for days 2 and 3 |
| All message flows in section 4: preview and YES, rules list, pause, stop, change, feedback, follow-up, delete my data, help | Agent | |
| Scheduler, deliveries, cost caps over the ledgers, quiet hours | Agent | A fast-forwarded month sends every rule on time in the right timezone, with no repeated item |
| Derrick sets up the pasta and photography rules from his phone | Derrick | Two test copies set for later that Saturday both arrive on time. The real rules are set for Friday 7pm and Sunday 4pm; the Sunday one is checked on day 3 |

**Day 3, Sunday 15 November: a second person can use it.**

| Task | Owner | Done when |
| --- | --- | --- |
| Import Eason's exports with the demo's importer on the bot Mac, copy the router file from Derrick's library, run the demo's Prepare step (embeddings; the te pass if a Gemini key is set, about 5 to 10 minutes per 1,000 Instagram posts), and check the library loads | Eason, with Derrick | If his exports have not arrived by Saturday evening, use a synthetic second library built from the demo's fixtures, and move his real library to the first session |
| Onboarding: consent note, timezone question, the handle-to-library link | Agent drafts; both approve | |
| Reliability pass on 10 requests Eason writes himself; fix what fails | Agent; Eason grades | 8 of 10 sendable as is |
| Kill switch, a one-page runbook, and a one-page guide for testers | Agent | |
| Dry run: Eason sets up two rules from his phone without help | Eason | Both rules work |

**If time runs short,** drop whichever of iMessage or Telegram is not yet working, then "change rule", then follow-up questions. Do not drop the checks in section 5, the preview, or "delete my data".

**Stretch, only if day 3 ends early:** a short YouTube description for the top candidates through the YouTube Data API, under its 30-day rule. Without it, YouTube picks rest on titles, which suits "motivating videos I watched" less well than recipes.

## 9. How it is tested

- **The 20 requests** are frozen before building (their hash is committed on day 0). The agent runs them after every prompt change. The day-1 marks above are the bar.
- **Automatic checks on every run:** each cited ID is in the candidate list; each extracted line is in the item's text; no repeats per rule; no friend's post; no message in quiet hours; cost under the cap.
- **Unit tests** for the time handling (timezones, the change to winter time, "tonight", "every weekday"), the store, the dedupe and each message flow, with the console channel and the fake clock.
- **A fake message database** to test the iMessage reader, since this environment is not a Mac.
- **Derrick grades** day 1, and Eason grades day 3. Grades go in a sheet outside git; the result files hold counts only.

## 10. After day 3: showing it to people

From Tuesday 17 November, as exports arrive.

- **Who:** 5 to 10 adults in the US with an iPhone, who save things on Instagram or YouTube. At least half should be strangers: people neither founder knew before 10 November. The consent note asks each person to confirm they are 18 or over.
- **How:** each person consents and sends their exports. A founder builds their library on the bot Mac, then sets up the first rule with them on a 15-minute call. After that they use it alone.
- **What counts** (agree the numbers before the first session):

| Signal | Proposed mark |
| --- | --- |
| Sets up a second rule or asks a second question without being prompted, in the first session | Half of them |
| Replies to a scheduled message (feedback, follow-up or a new request) in week 1 | Half of them |
| Still has a rule running after 7 days | Half of them |
| Pays $4.99 for the next month when asked on day 7 | 2, at least 1 of them a stranger |

- **What else is recorded:** every unsupported request, every 👎 with its reason if given, and how many picks said "the recipe is in the video".

## 11. Rules from `AGENTS.md` and what A-008 must record

| Rule | In the MVP |
| --- | --- |
| 2, raw and derived kept apart | Libraries are built by the demo's importer, as before; derived rows are rebuildable |
| 5, the processor reads and the executor writes | Retrieve and compose only read. Only the executor sends |
| 6, the LLM fills forms and code acts | The interpreter returns JSON; code validates it and builds the schedule. The model never sends anything |
| 7, intake within platform terms | Exports only. Nothing fetched from Instagram. No scraping service |
| 8, privacy defaults | No Instagram DMs are read. Friends' posts are never used. The person's messages to the bot are kept only as rule and request text, with consent. No transcripts, audio or video are fetched or stored. Captions go to the model as marked data (section 5, rule 6) |
| 9, no real data in git | Requests, grades, libraries and the store live in `data/` |
| 10 and 11, pin versions and measure | Prompt versions in file names; every call in the ledger; timings in `runs` |
| 1, 3 and 4 | Set aside for `experiments/mvp/`, as prototype code |

A-008 must record these conflicts with the docs:
- `docs/06-rules-and-actions.md`: "Avoid SMS for now" and email as the first action. The MVP's only action is a text message, by iMessage.
- `docs/00-vision.md`: the MVP outputs are email and Google Calendar, and text messages are "planned later".
- `docs/09-roadmap-and-ownership.md`: rules (M4) are built before M0 to M3, and testers come before M5.
- `docs/10-decisions.md`: Supabase for the database. The MVP uses SQLite on one Mac.
- `AGENTS.md` › Prototype code: outsiders use prototype code.
- `docs/09-roadmap-and-ownership.md` › Ownership: triggers, scheduler, executor and output actions are Eason's, and the interpreter is Derrick's. The agent builds them for this prototype; Eason reviews the scheduler and executor, and Derrick the interpreter.
- `docs/07-privacy-and-safety.md` › Sensitive categories: there is no tagger. Health goals are declined, and the consent note says the bot reads the whole library.
- `docs/06-rules-and-actions.md` › RuleSpec: a subset, with days and a time in place of cron.

## 12. Decisions needed today

1. **Channel:** iMessage from a Mac (recommended), Telegram, or start SMS registration now for later.
2. **The Mac:** which one runs the bot, and can it stay on and awake from 15 November to the end of the sessions?
3. **The bot's Apple Account:** a new one (recommended), not a founder's own.
4. **Scope:** answers come only from the person's own library (recommended). Searching for new content is a later step.
5. **Models:** `gpt-5.4-mini` with the existing OpenAI key. The consent note names OpenAI as the provider that sees item text and requests.
6. **Price** for the sessions: $4.99 for the next month, asked on day 7.
7. **The session marks** in section 10.
8. **A-008:** already rewritten for this MVP (Proposed). Both founders accept it, and this brief, before anyone outside the founders uses the bot.

## 13. Risks

| Risk | What reduces it |
| --- | --- |
| Captions are thin: about two in three recipe posts have no ingredients written | Say "the recipe is in the video" plainly. Prefer items with text when the rule asks for details |
| YouTube items have titles only | Use them for "videos I watched" requests, and say so. The YouTube description is the stretch step |
| The Mac sleeps, loses its network, or Apple flags the bot's account | Keep the Mac on power with sleep off. Keep volume low. Telegram is the backup |
| Loading a large library takes about a minute and 2.5 GB of memory | The engine process pool in section 7 keeps up to about 4 loaded, and starts others ahead of their rules |
| Slop: picks that technically match but are not good | The fit threshold, abstaining, feedback, and Derrick's grades on day 1 |
| Exports arrive late | Ask for them on day 0 |
| Muse already turns a saved recipe reel into a grocery list | The MVP shows what Muse does not: YouTube and Instagram together, and rules on a schedule |

## 14. Budget

- API: a $10 cap for the build and tests, and $1 a day per tester. The existing ledger caps each ledger file as a whole ($4 by default) and keeps no person or day split, so the MVP points each person's calls at their own library's ledger, sets that ledger's budget, and `mvp/run.py` sums the day's rows before each run and skips a run that would pass $1. The $10 build cap is the sum over all ledgers, also checked by `mvp/run.py`.
- Channel: $0 for iMessage and Telegram.
- Founder time: about 2 hours on day 0, then about half a day each on days 1 to 3.

## 15. Deliverables

- `experiments/mvp/`: the code above, its tests, `prompts/`, a runbook and a tester guide.
- `results/r10-mvp-day1.md` and `results/r10-mvp-day3.md`: counts only.
- A founders' summary at the top of `STATE.md` at the end of each day.

Commit and push at the end of each day. Personal data stays out of git.
