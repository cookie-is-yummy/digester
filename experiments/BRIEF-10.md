# Brief, round 10 (DRAFT): run the loop by hand. Ten outside testers and a decision on the consumer direction by 7 December

> **Status: DRAFT, not binding.** Written by the agent on 10 Nov 2026 from the outside review "Scroll Digest: outside review and 8-week plan" (a private doc; ask Derrick for the link), after Derrick supplied his founding notes as the frame for it. It replaces the first draft of this brief, a hosted agent-access pilot, which is kept, unscheduled, in `PARKED-agent-layer-pilot.md`. It becomes binding only when both founders accept it **and** amendment A-008 in `docs/amendments.md`.
>
> **Until then,** an agent may write the templates and the tally script for Phase 1 on this branch and test them on synthetic data only. Nothing is published, nobody is contacted, and no real person's data is touched.

This is not a search-research round and, until Gate B, not a build round. There are no new arms, judges or adoption rules, and no product code. The roles and privacy rules of `BRIEF.md` and `BRIEF-8.md` still hold: the agent that evaluates never builds, builders never open `data/all/evals/labels/` or `eval_work/`, and nothing under `data/` goes into git.

**The question for this round: does a plan made from what people send lead them to act, and does the sending add anything?** The founders' notes describe the product as a loop: a person sends posts while scrolling, gets a plan that cites them, and acts on it. Nine rounds measured search, a supporting layer of that loop. No plan has been made for anyone. This round runs the loop by hand for ten people before anything is built.

## Who does what

Every item has an **owner**, a founder. Phases 1 and 2 are founders' work; the agent prepares templates, a tally script and reports. Only a founder may:

- publish anything outside the repo (a video, a post, a page, a Meta app);
- contact, recruit or onboard a person, read what a tester sends, write or send a plan, or run a check-in;
- spend money, open an account with a provider, or take money;
- run tasks on a personal Muse, Claude or ChatGPT account;
- accept or reject an amendment.

An agent that reaches one of these stops, writes what is ready into `STATE.md`, and waits. Do not work unattended past a gate.

**The founder who writes the plans does not count the results.** Derrick writes the plans. Eason runs the check-ins and holds the tally.

## Setup

1. **Decisions first (item 1).** No tester starts until the marks and the decision table are committed (see "The marks"), and the outcome of the other decisions is in `docs/10-decisions.md`.
2. **The founders' store.** Directions, sent items, plans, tallies, sign-ups and consent records live in one place that only the founders can open, outside git and outside every cloud agent session. The founders name it in item 1.
3. **Tester data never enters a cloud agent session or the repo.** The agent sees only the counts listed under "What the tally reports", pasted by a founder.
4. **Keys.** Phases 1 and 2 need none. Phase 3 keys come from the founders and live only in the environment. Never print, log or commit them.
5. **A deadline inside this round.** The YouTube Data API reference text (`data/yt/ref`, `data/all/yt_ref`) must be deleted by 29 November 2026 (`docs/research/2026-11-09-current-state.md` section 1.4). A founder confirms it is gone from every copy and records that in `STATE.md`.

## Where we are

- Search (Q8) gains nothing over the earlier finalist on real held-out searches beyond the noise band (`results/r8-final.md`, `results/r9-final.md`). Exact-post finding works 30 to 45% of the time. Everything was measured on one library.
- Nothing of the loop exists as code: no capture, no plan, no delivery. `04-intake.md` mentions an earlier prototype with sign-up by DM; its code and logs are not in this repo.
- The design holds the loop's parts on paper: the filter (0.84 accuracy on one library), goals and direction, and the opportunity finder in `05-processor.md`; `actions` rows (`title`, `why`, `evidence[]`, `due_at`, `state`) and `placements` into email, calendar or a document in `03-data-contract.md`.
- The roadmap measures "actions marked done" at M5, its last milestone (`09-roadmap-and-ownership.md`). This brief measures it first.
- Published studies say a plan adds a few points of follow-through, more with a day and a time (the review, Part 2). Meta's Muse already writes action plans from goals. So the test needs a control: actions written from the goal alone.

## Rules that hold throughout

- **`AGENTS.md`** rules 7 to 9 apply as written. Rule 8 needs a reading for a hand-run test. A founder reads the product account's inbox, and records only the shared post and the words typed with that share; `04-intake.md` › Live capture keeps those words as an intent label. Anything else a tester writes there is not copied anywhere. No tester's other conversations are involved: this round takes no export. A-008 records this.
- **No code fetches anything from instagram.com or its CDN.** A founder opens a shared post in the app, as any recipient would. No scraping service is used, for any platform.
- **Public creators' posts only.** A post from a private account, or one that looks like a friend's, is counted and not used in a plan (`07-privacy-and-safety.md` › Friends). This round has no follow lists, so the founder decides by eye and records the count.
- **No advice.** An action is a small first step that the item or the goal itself suggests. No medical, legal or financial advice.
- **No model sees tester data in Phases 1 and 2.** A founder writes the plans. A model's help is Phase 3: it needs Gate 0 and consent box 2.
- **Testers** are adults living in the US. No gifts or payment for taking part. A tester's records are deleted 30 days after the Gate B decision, or 30 days after Gate C for those who continue, unless they ask to stay.
- **Nothing personal in git:** no directions, items, plans, names, handles, sign-ups or message text. Results files hold the tally's counts only.
- **Consent record,** one per tester, in the founders' store: a pseudonymous ID, the consent-note version, which boxes are ticked, the timestamp, the 18-or-over and US confirmations, where the tester came from, whether either founder knew them before 10 November, and their answer to one question: how much do you already do toward this goal (nothing, a little, a lot).
- **If something goes wrong** (tester data exposed): a founder tells the affected testers within 72 hours and records what happened in `STATE.md` without personal details.

## Phase 1 (10 to 16 November): decide and recruit

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 1 | **Decide.** See "Open decisions". | Both | Nothing. | Pass: by 16 November the marks and the decision table are committed with their date, and nothing the test depends on is left open. |
| 2 | **What free looks like** (a reading, not a gate). Each founder writes three lines of direction and gets a plan from Muse and from a general assistant, on his own accounts. The other founder writes a third plan from 20 items the first one sent. | Both | Make a comparison sheet template. The agent never sees the plans. | Output: one sentence on what the hand-written plan has that the free ones lack, used in item 3. If that sentence cannot be written, say so in `STATE.md` before recruiting. |
| 3 | **The message.** Three to five short videos from the product's accounts, each ending with one instruction: send us the word "plan". A founder answers each message by hand with the consent note. | Eason | Draft scripts and captions if asked. The agent sees counts. | Pass: at least five strangers start by 21 November. Report views, messages and sign-ups per 1,000 views. Fail: fill the places from the founders' circle and record that the message did not pull. |
| 4 | **Prepare.** The consent note, the plan template, the check-in script, the day-14 questions, the tally sheet and a payment link. | Derrick | Draft all of them, and write `experiments/action_test/tally.py`, which turns a sheet of counts into the four marks. Test it on synthetic sheets. | Pass: one founder completes a dry run from first send to tally. |

**Gate A, 16 November:** items 1 and 4. The marks are committed and the dry run is done. The first testers start on 17 November.

## Phase 2 (17 November to 7 December): the loop by hand

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 5 | **The loop, 14 days for each tester** (protocol below). Ten testers start between 17 and 21 November. A later starter is reported, not counted. | Derrick writes the plans; Eason runs the check-ins and holds the tally | Nothing with testers. Fix the tally script from counts. | Marks 1 to 3. |
| 6 | **Payment.** On day 14, a real charge of $4.99 for the next month of weekly plans. Hosted checkout in a founder's name, one-click cancellation. The terms say the service is a prototype, and that the payment is refunded in full if the Gate B decision is to stop. | Eason | Draft the one-page terms; both founders approve them. The agent sees the number of payments and refunds. | Mark 4. Payments made within two days of the request count. |
| 7 | **The other direction.** About ten conversations with businesses, and with people who keep swipe files of posts (marketers, agencies, creators). `09-roadmap-and-ownership.md` lists the business-data idea as an open question. | Eason | Nothing. | Pass: one named workflow with its input and its output, and three people who ask to see it. Fail: the idea stays an open question. |
| 8 | **Gate B.** Read the marks and decide. | Both | Run `tally.py` on the pasted counts and write `results/r10-action-test.md`. | The decision is recorded in `STATE.md` and `docs/10-decisions.md` on 7 December. |

### The protocol (item 5)

- **Day 0.** The tester ticks the consent note, writes three lines of direction (what they want, in their own words), and sends up to 20 items they already saved or sent to themselves. Instagram posts go by DM to the product's account, with a few words in the share's own message box. Anything else goes as a link with a line. They are told once that they can keep sending whenever they scroll. Nobody reminds them.
- **Day 2: plan 1,** by email. Four actions in one format and in random order. Two are **item actions**: each is drawn from an item the tester sent and cites it. Two are **goal actions**: written from the direction alone. The founder writes the goal actions first, before opening the tester's items.
- **Each action** is a first step that takes under 30 minutes, in if-then form: "If it is [day, time], then I will [step]". The tester replies with a day and a time for each action they accept, and gets a calendar invite for each.
- **Day 7: check-in,** from the script. It asks which actions were done, what was done and when. It never asks for items.
- **Day 9: plan 2,** in the same format, from items sent since day 0. If there are none, from day-0 items not yet used.
- **Day 14: a call or a message,** from the script. Which actions were done. A label for each item sent: "do", "someday" or "just liked it". Which two of the eight actions were most worth doing. Then the founder explains the two kinds of action and sends the payment link.
- **For every item action,** the plan writer records whether writing it needed the video or image itself, or only the caption and the tester's line.
- **For every completed action,** the tally records whether it came before or after a check-in.

### The marks (commit them before the first tester starts)

| Mark | What is counted | Pass | Stop signal |
| --- | --- | --- | --- |
| 1. They act | Testers who complete at least one item action within their 14 days, and say what they did and when | 6 of 10 | 2 or fewer |
| 2. The items add something | Completed item actions minus completed goal actions, out of 40 issued of each | Ahead by 8 or more: supported. Within 7 either way: not shown | Behind by 8 or more |
| 3. They keep sending | Testers who send an item after day 2, with no reminder | 4 of 10 | 1 or none |
| 4. They pay | Testers who pay $4.99 within two days of being asked | 3 of 10, at least 2 of them strangers | No stranger pays |

A **stranger** is a tester whose consent record says neither founder knew them before 10 November. A tester who drops out counts as not acting, not sending and not paying. If fewer than 40 actions of a kind are issued, the line in mark 2 is a fifth of the number issued, rounded up.

Three readings are reported beside the marks and are not gates: the share of sent items labelled "do" (under 15% says the feed is the problem, as the business case argues); the share of item actions that needed the video; and sign-ups per 1,000 video views. Marks 1 and 2 are also reported apart for testers who said "nothing" or "a little" at sign-up and for those who said "a lot".

**The line of 8** is the agent's arithmetic. With 40 actions on each side and about 45% of them done, chance alone gives a gap of 8 or more about one time in twenty. So mark 2 can only see a large gap. A level result means "not shown", and the control stays in every later plan until it shows.

### The decision on 7 December

The first row that fits decides.

| Result | Decision |
| --- | --- |
| Two or more stop signals | Stop the consumer direction. Take the business workflow from item 7 if it passed; if not, stop. |
| Marks 1 and 4 pass, with no stop signal on mark 2 | Go to Phase 3. If mark 3 shows its stop signal, collect items in a weekly batch instead of live sending. |
| Marks 1 and 4 pass, but goal actions lead by 8 or more | They act and pay, and the sending added nothing. That is another AI planner, which is free elsewhere. Rebuild the promise around the check-ins, or stop. |
| Mark 1 passes and mark 4 does not | They act but do not pay. One rerun with ten new strangers at $2.99; stop unless 2 pay. |
| Mark 4 passes and mark 1 does not | Goodwill payments. Ask each payer what they paid for; narrow to that, or stop. |
| Anything else | A tie. One rerun with ten new strangers and the same marks. A second miss ends the consumer direction. |

With ten people these marks give direction, not proof.

**What the tally reports.** These are the only numbers that leave the founders' store: testers started, and how many are strangers; the count for each mark; item and goal actions issued, accepted and completed, split by before or after a check-in; the number of items each tester sent, as a list of counts; the counts labelled "do", "someday" and "just liked it"; item actions that needed the video; payments and refunds; video views, messages and sign-ups; and the number of private or friends' posts counted and not used.

**The consent note has three boxes.** (1) Run the test: a founder reads my direction and what I send, writes my plans, asks what I did, and keeps these records until 30 days after the decision. (2) Let software draft my later plans: my direction, my own lines and the public text of items I sent go to a named model provider, under terms that exclude training. (3) The founders may quote what I said, without my name. Box 1 alone is enough to take part. The note also says that a payment will be asked for on day 14, that taking part does not depend on paying, and that testers should send only posts they are content for a founder to see.

## Phase 3 (8 December to 4 January): build what passed. Only on a Go

A full brief for Phase 3 is written after Gate B, from what the tally shows. In outline:

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 9 | **DM-share payloads,** founders' accounts only. Before the app goes Live, Eason posts a short privacy note for the receiver at a public URL (Meta appears to require one: check its current page). Then publish the Meta app (Live needs no App Review) and share 10 reels and 10 posts from the founders' own role accounts, never a tester's. | Eason | Write the receiver and the sanitiser. The receiver checks Meta's signature, keeps the share and the words typed with it, drops every other message text field in memory before any write, keeps raw bodies only on the receiving machine, deletes them once the summary of field names and presence counts is written, and is switched off when the item reports. | Pass: 18 of 20 carry caption text and a stable ID. Fail: Instagram capture means a link plus the person's line. Either way, record in `04-intake.md` what a share delivers and that webhook data is Meta Platform Data, and correct its "development mode works" line. |
| 10 | **Gate 0: data readiness,** before software touches a tester's data. All of: (a) each model provider's data-use and retention terms are recorded and dated in `07-privacy-and-safety.md`, every key sits on a billed project, and no preview-only feature touches tester data; (b) no private or friend's post reaches a model call, tested on synthetic input; (c) one command deletes a tester's rows, the writer's cache and its logs, proved by counts; (d) logs and `ai_runs` rows hold IDs, counts and costs, never directions, lines or captions; (e) the writer runs only for testers who ticked box 2; (f) the consent note and a short data policy exist and match what the code does. | Both | Write the tests for (b) to (e) and drafts for (f). A founder does (a) and approves (f). | Pass: every check passes on synthetic data. Fail: plans stay hand-written. |
| 11 | **The plan writer,** prototype code in `experiments/plan_writer/`: a script a founder runs on his own machine against the founders' store. In: the direction, the items and the tester's lines. For each item it sees only what an official route would deliver (the review's Intake table), entered by the founder. Out: rows in the contract's `actions` shape, validated before use (rule 6); each item action cites its items in `evidence[]`, and a goal action carries `goal_id` and no evidence. A founder edits and sends; no model sends anything. Every call goes through the `lib/ai.py` ledger (rule 11). It drafts the payers' plans from 21 December. | Derrick | Build it and test it on synthetic input and on the founders' own items. A founder runs it on tester data. | Pass: the founder sends at least half of the drafted item actions with wording changes only. Report the cost of each plan and the share of drafted actions the founder discarded. |
| 12 | **Do they stay.** Payers get a plan each week and keep sending. Until item 11 passes, a founder writes those plans by hand. | Both | Extend `tally.py`. | Pass: 3 of the ten send an item in week 4, and 2 payers are still active on 4 January. Active means: sent an item or reported an action in the last 14 days, and has not cancelled. |

**Gate C, 4 January:** items 11 and 12. A Go earns a second cohort of 20 to 30 strangers with software-drafted plans and the control kept, and starts the long-lead items (a company, Business Verification, App Review). Anything else: narrow to the job the payers named, or stop.

## What this brief stops or parks

- New search arms, judges and rounds, and adopting anything on AI grades or synthetic searches.
- The hosted agent-access pilot, the exact-post fixes, the second-library run and the search head-to-head. They are parked in `PARKED-agent-layer-pilot.md` until paying testers ask for agent access.
- Export onboarding for testers. The loop starts from what people send.
- Forming a company, Business Verification and App Review, until a Go.
- A local-first build, and cost or storage tuning.
- Any scraping service.
- Ads, selling insight, and keeping data after deletion. `10-decisions.md` says: "Real deletion; no ads; no selling data".
- The rules-and-actions engine, the hub and the product skeleton, until a Go.
- New amendments from the research loop. Decide the open ones first.

## Open decisions for the founders (item 1)

1. A-008: run the loop by hand before building, and charge for the plan first. Both founders, in their own words: why, or why not.
2. The four marks, the line of 8, the 15% reading and the decision table. Agree them or change them, then commit them before the first tester starts.
3. The price: $4.99 (the agent's proposal: anyone who pays it would pay $2.99), or $2.99 from the start.
4. Agent access. The founding notes hold two views of it: hard to market, and "above all". `10-decisions.md` calls MCP the paid core. Which view holds, and does charging for the plan first change that decision or only postpone it?
5. Ads, selling insight and keeping deleted data: drop all three in writing, or propose an amendment to the Agreed decision.
6. A scraping service for enrichment: never, or only as `04-intake.md` allows (a paid provider with clear terms, last in the order). The agent's suggestion: not in this round.
7. The reading of rule 8 for the product account's inbox (see "Rules that hold throughout").
8. Where the founders' store is and who may open it, and whether a lawyer reads the consent note and the payment terms.
9. The hours each founder can give a week through December. The dates assume about 20 each.
10. Whether the "Muse" in the earlier briefs is Meta's Muse, and whether it is available on the founders' accounts for item 2.
11. A-001 to A-007: accept, reject or defer each. Nothing in Phases 1 and 2 depends on them.
12. The privacy design for any later hosted build (a shared store, a private vault, a revocable key; A-006 item 6). Phase 3 as outlined stores nothing on a server; decide the design before anything does.
13. Where the code and logs of the earlier DM prototype are. They would show what a DM share delivered and how often people sent.

## Deliverables

- `experiments/action_test/`: drafts for the founders of the consent note, the plan template, the check-in script, the day-14 questions and the comparison sheet; `tally.py` and its tests on synthetic sheets.
- `results/r10-marks.md`: the marks and the decision table as the founders agreed them, committed before the first tester starts.
- `results/r10-action-test.md`: the tally's counts and the decision. Aggregates only.
- `results/r10-message.md` and `results/r10-business.md`: counts and a one-paragraph outcome each, from what a founder pastes.
- On a Go: the Phase 3 brief, then `experiments/plan_writer/`, `results/r10-dm-payload.md`, `r10-gate0.md`, `r10-plan-writer.md` and `r10-stay.md`.
- A **founders' summary at the top of `STATE.md`** at each gate: what passed, what failed, what needs their decision.

Commit and push after each item. Personal data stays out of git.

## Budget

- **Phases 1 and 2:** no API spend and no hosting; card fees on the payments. Founder time: about 16 working days as the review counts them (Derrick about 7, Eason about 9), against about 20 available at 20 hours a week each.
- **Phase 3, only on a Go:** API cap $10, enforced through the ledger; about 11 founder-days.
- **Total cash cap: $25** (or what the founders say, if lower). Report at the cap.
