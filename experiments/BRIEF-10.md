# Brief, round 10 (DRAFT): run the product by hand. Ten outside testers and a decision on the consumer direction by 7 December

> **Status: DRAFT, not binding.** Written by the agent on 10 Nov 2026 from the outside review "Scroll Digest: outside review and 9-week plan" (a private doc; ask Derrick for the link), after Derrick supplied his vision notes as the frame for it. It replaces the first draft of this brief, a hosted agent-access pilot, which is kept, unscheduled, in `PARKED-agent-layer-pilot.md`. It becomes binding only when both founders accept it **and** amendment A-008 in `docs/amendments.md`.
>
> **Until then,** an agent may write the templates and the tally script for Phase 1 on this branch and test them on synthetic data only. Nothing is published, nobody is contacted, and no real person's data is touched.

This is not a search-research round and, until Gate B, not a build round. There are no new arms, judges or adoption rules, and no product code. The roles and privacy rules of `BRIEF.md` and `BRIEF-8.md` still hold: the agent that evaluates never builds, builders never open `data/all/evals/labels/` or `eval_work/`, and nothing under `data/` goes into git.

**The question for this round: does a plan made from what people send lead them to act, and does the sending add anything?** Derrick's notes describe the product as a loop: a person sends posts while scrolling, gets a plan that cites them, and acts on it. Nine rounds of the research loop measured search, which only supports that product. No plan has been made for anyone. This round runs the product by hand for ten people before anything is built.

## Who does what

Every item has an **owner**, a founder. Phases 1 and 2 are founders' work; the agent prepares templates, a tally script and reports. Only a founder may:

- publish anything outside the repo (a video, a post, a page, a Meta app);
- contact, recruit or onboard a person, read what a tester sends, write or send a plan, or read a tester's answers;
- spend money, open an account with a provider, or take money;
- run tasks on a personal Muse, Claude or ChatGPT account;
- accept or reject an amendment.

An agent that reaches one of these stops, writes what is ready into `STATE.md`, and waits. Do not work unattended past a gate.

**Each founder writes one kind of action, and neither counts by hand.** Derrick writes the item actions. Eason writes the goal actions, sends the plans and receives the answers. Answers arrive through a form, and the tally script computes the marks from the form's export. Both founders can see the tally. The split is a proposal: it gives each kind of action an author who wants it to do well.

## Setup

1. **Decisions first (item 1).** No tester starts until the marks and the decision table are committed (see "The marks"), and the outcome of the other decisions is in `docs/10-decisions.md`.
2. **The founders' store.** Directions, sent items, plans, answers, tallies, sign-ups and consent records live in one place that only the founders can open, outside git and outside every cloud agent session. The founders name it in item 1.
3. **Tester data never enters a cloud agent session or the repo.** The agent sees only the counts listed under "What the tally reports", pasted by a founder.
4. **Keys.** Phases 1 and 2 need none. Phase 3 keys come from the founders and live only in the environment. Never print, log or commit them.
5. **A deadline inside this round.** The YouTube Data API reference text (`data/yt/ref`, `data/all/yt_ref`) must be deleted by 29 November 2026 (`docs/research/2026-11-09-current-state.md` section 1.4). A founder confirms it is gone from every copy and records that in `STATE.md`.

## Where we are

- Search (Q8) gains nothing over the earlier finalist on real held-out searches beyond the noise band (`results/r8-final.md`, `results/r9-final.md`). Exact-post finding works 30 to 45% of the time. Everything was measured on one library.
- Nothing of the product loop exists as code: no capture, no plan, no delivery. `04-intake.md` mentions an earlier prototype with sign-up by DM; its code and logs are not in this repo.
- The design holds the parts on paper: the filter (0.84 accuracy on one library), goals and direction, and the opportunity finder in `05-processor.md`; `actions` rows (`title`, `why`, `evidence[]`, `due_at`, `state`) and `placements` into email, calendar or a document in `03-data-contract.md`.
- The roadmap measures "actions marked done" at M5, its last milestone (`09-roadmap-and-ownership.md`). This brief measures it first.
- Published studies say a written plan adds a few points of follow-through, more with a day and a time (the review, Part 2). Meta's Muse already writes action plans from goals. So the test needs a control: actions written from the goal alone.

## Rules that hold throughout

- **`AGENTS.md`** rules 7 to 9 apply as written. Rule 8 needs a reading for a hand-run test, and A-008 records it. **DMs to the product account carry shares only:** the shared post and the one word typed with it (`04-intake.md` › Live capture keeps the words typed with a share as an intent label). Sign-up, consent, the direction and every answer go through a form or email that a founder sends in reply to a person's first message. A founder reads other DM text only to point the sender to the form, and copies none of it. No tester's other conversations are involved: this round takes no export.
- **No code fetches anything from instagram.com or its CDN.** A founder opens a shared post in the app, as any recipient would. No scraping service is used, for any platform.
- **Public creators' posts only.** A post from a private account, or one that looks like a friend's, is counted and not used in a plan (`07-privacy-and-safety.md` › Friends). This round has no follow lists, so the founder decides by eye and records the count.
- **No advice, and no health goals.** An action is a small first step that the item or the goal itself suggests. No medical, legal or financial advice. Goals about a medical or mental-health condition, weight loss or diet are out of scope: decline them at sign-up, and leave out of every plan any item about them.
- **No model sees tester data in Phases 1 and 2.** The founders write the plans. A model's help is Phase 3: it needs Gate 0 and consent box 2.
- **Testers** are adults living in the US. If anything suggests a tester is under 18, stop, delete their records and take no payment. No gifts or payment for taking part. A tester's records are deleted 30 days after the Gate B decision, or 30 days after Gate C for those who continue, unless they ask to stay.
- **Nothing personal in git:** no directions, items, plans, names, handles, sign-ups or message text. Results files hold the tally's counts only.
- **Consent record,** one per tester, in the founders' store: a pseudonymous ID, the consent-note version, which boxes are ticked, the timestamp, the 18-or-over and US confirmations, where the tester came from, whether either founder knew them before 10 November, and their answer to one question: how much do you already do toward this goal (nothing, a little, a lot).
- **If something goes wrong** (tester data exposed): a founder tells the affected testers within 72 hours and records what happened in `STATE.md` without personal details.

## Phase 1 (10 to 16 November): decide and recruit

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 1 | **Decide.** See "Open decisions". | Both | Nothing. | Pass: by 16 November the marks and the decision table are committed with their date, and nothing the test depends on is left open. |
| 2 | **What free looks like** (a reading, not a gate). Each founder writes three lines of direction and gets a plan from Muse and from a general assistant, on his own accounts. The other founder writes a third plan from 20 items the first one sent. | Both | Make a comparison sheet template. The agent never sees the plans. | Output: one sentence on what the hand-written plan has that the free ones lack, used in item 3. If that sentence cannot be written, say so in `STATE.md` before recruiting. |
| 3 | **The message.** Three to five short videos from the product's accounts, each ending with one instruction: send us the word "plan". A founder answers each message by hand with a link to the consent form. Recruit a few more than ten, so that ten start. | Eason | Draft scripts and captions if asked. The agent sees counts. | Pass: at least five strangers start by 20 November. Report views, messages and sign-ups as a reading. Fail: fill the places from the founders' circle, record that the message drew too few strangers, and record that mark 4 will not be read. |
| 4 | **Prepare.** The consent form, the plan template, the check-in form, the day-14 form, the tally sheet and a payment link. | Derrick | Draft all of them, and write `experiments/action_test/tally.py`, which turns the forms' export of counts into the four marks. Test it on synthetic sheets. | Pass: one founder completes a dry run from first send to tally. |

**Gate A, 16 November:** items 1 and 4. The marks are committed and the dry run is done. Testers start between Tuesday 17 and Friday 20 November.

## Phase 2 (17 November to 7 December): the product by hand

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 5 | **The product by hand, 14 days for each tester** (protocol below). The ten who count are the first ten to complete day 0 between 17 and 20 November, with five places held for strangers until 20 November. Anyone else is reported, not counted. | Derrick writes the item actions and records what is sent. Eason writes the goal actions, sends the plans and the forms, and holds the forms' export | Nothing with testers. Fix the tally script from counts. | Marks 1 to 3. |
| 6 | **Payment.** On day 14, a one-time charge of $4.99 for four more weekly plans, with no renewal. Hosted checkout in the name of whichever founder agrees to hold it. The terms say the service is a prototype, that the four plans are delivered whatever the 7 December decision, and that the payment is refunded in full if fewer than four are delivered, or on request once the two kinds of action have been explained. | Eason | Draft the one-page terms; both founders approve them. The agent sees the number of payments and refunds. | Mark 4. Payments made within two days of the request count. |
| 7 | **The business-data idea.** Five to ten conversations with businesses, and with people who keep swipe files of posts (marketers, agencies, creators). `09-roadmap-and-ownership.md` lists the idea as an open question. | Eason | Nothing. | Pass: one named workflow with its input and its output, and three people who ask to see it. Fail: the idea stays an open question. |
| 8 | **Gate B.** Read the marks and decide. | Both | Run `tally.py` on the pasted counts and write `results/r10-action-test.md`. | The decision is recorded in `STATE.md` and `docs/10-decisions.md` on 7 December. |

### The protocol (item 5)

- **Day 0.** The tester fills in the consent form and writes three lines of direction in it (what they want, in their own words). They send up to 20 items they already saved or sent to themselves. An Instagram post goes by DM to the product's account with one word typed in the share: "do", "someday" or "liked". Anything else goes through the form as a link with the same one word. They are told once that they can keep sending whenever they scroll. Nobody reminds them.
- **Day 2: plan 1,** by email. Four actions in one template and in random order. Two are **item actions**: Derrick draws each from an item the tester sent, and it cites that item. Two are **goal actions**: Eason writes them from the three lines of direction alone, without seeing the items.
- **Each action** is a first step that takes under 30 minutes and names what to do and where, in if-then form: "If it is [day, time], then I will [step]". Before a plan goes out, Eason checks that all four actions fit the template, and sends back to its author any that does not. The tester replies with a day and a time for each action they accept, and gets a calendar invite for each.
- **Replies and answers go to an address and forms that only Eason reads** until Gate B. Derrick sees new items, not answers, so he writes plan 2 without knowing what was done.
- **Day 7: check-in form.** For each action: was it done, what was done and when, and did it leave a trace (a photo, a booking, a file, a link). It never asks for items.
- **Day 9: plan 2,** in the same format, from items sent since day 0. If there are none, from day-0 items not yet used.
- **Day 14: closing form or call.** The same questions for plan 2, and which two of the eight actions were most worth doing. Then the payment link.
- **The explanation.** The two kinds of action are explained to each tester when their two-day payment window closes, or at once if they ask. Anyone who paid may then ask for a full refund.
- **Thanksgiving.** Nothing is sent or asked on 26 or 27 November. A plan or form due then moves to the next working day, and the shift is recorded.
- **For every item,** the store records when it was sent and its one-word label. **For every item action,** Derrick records whether writing it needed the video or image itself, or only the caption and the tester's word. **For every completed action,** the form's export shows whether it came before or after a check-in.

### The marks (commit them before the first tester starts)

| Mark | What is counted | Pass | Stop signal |
| --- | --- | --- | --- |
| 1. They act | Testers who complete at least one item action from each of their two plans, and say what they did and when | 5 of 10 | 1 or none |
| 2. The items add something | Completed item actions minus completed goal actions, out of 40 issued of each | Ahead by 8 or more: supported. Within 7 either way: not shown | Behind by 8 or more |
| 3. They keep sending | Testers who send an item after day 2, with no reminder | 4 of 10 | 1 or none |
| 4. They pay | Testers who pay $4.99 within two days of being asked | 3 of 10, at least 2 of them strangers | No stranger pays |

- A **stranger** is a tester whose consent record says neither founder knew them before 10 November.
- A tester who drops out counts as not acting, not sending and not paying.
- **Mark 4 is read only if at least four strangers reach day 14.** If fewer do, mark 4 is "not read", no Go can be given, and the result is the last row of the decision table.
- **If fewer than 40 actions of a kind are issued,** the line in mark 2 is 8 for 32 to 39 issued, 7 for 23 to 31, 6 for 16 to 22 and 5 for 10 to 15. Under 10, mark 2 is not read.
- **The marks use every completion a tester reports.** Completions that left a trace are reported beside them. The founders may not switch between the two after the results arrive.

**What these marks can and cannot see** (the agent's arithmetic, in the review's working files; it assumes about 45% of actions get done, which has no source):

- Mark 1 passes about six times in ten if 45% of actions get done, and about one time in ten if 30% do.
- Mark 2: if the items add nothing, chance alone puts item actions 8 or more ahead about one time in twenty, and either kind 8 or more ahead about one time in ten. The likely result is then "not shown", about nine times in ten. A true gap of 20 points is missed about half the time. A gap must reach about 30 points to be seen 85% of the time.
- Mark 4 is strict. If each stranger pays with a chance of 20% and each friend with 30%, it passes about one time in four, and no stranger pays about one time in three. The founders may prefer 2 of 10 with at least 1 stranger, which then passes about six times in ten. Choose before the first tester starts.

Readings reported beside the marks, which are not gates:

| Reading | What it shows |
| --- | --- |
| Of the 20 "most worth doing" picks, how many are item actions | 14 or more: testers prefer item actions. 6 or fewer: they prefer goal actions. Chance alone gives either about one time in twenty |
| The share of sent items labelled "do" at the time of sending | How much of what people send they mean to act on. No line is set: there is no evidence for one. A low share supports the business-data idea |
| The share of item actions that needed the video | How far a text-only pipeline could go |
| Sign-ups per 1,000 video views | Whether the message draws strangers. With a new account's view counts this is an anecdote |
| Marks 1 and 2 for testers who said "nothing" or "a little" at sign-up, and for those who said "a lot" | Counts only, labelled as too few to compare. Not used in the decision |

### The decision on 7 December

The first row that fits decides. "Go" means this decision to continue to Phase 3.

| Result | Decision |
| --- | --- |
| A stop signal on mark 1, or two or more stop signals | Stop the consumer direction. If strangers paid anyway, ask each what they paid for. Take the business workflow from item 7 if it passed; if not, stop. |
| Goal actions lead by 8 or more | The sending added nothing. That is another AI planner, which is free elsewhere. Rebuild the promise around the check-ins and rerun once, or stop. |
| Marks 1 and 4 pass, and mark 2 is supported or mark 3 passes | Go to Phase 3: build the plan writer, and keep the control in every plan. If mark 3 showed its stop signal, collect items in a weekly batch instead of live sending. |
| Marks 1 and 4 pass, mark 2 is not shown and mark 3 does not pass | They act and pay, but nothing shows that the sending matters. Do not build capture. Rerun once, collecting items in a weekly batch, with the control kept. |
| Mark 1 passes and mark 4 does not | They act but do not pay. One rerun with ten new strangers at $2.99; stop unless 2 pay. |
| Anything else | A tie. One rerun with ten new strangers and the same marks. A second miss ends the consumer direction. |

With ten people these marks give direction, not proof. A rerun recruits from 4 January and is read on 1 February, so that it does not run through the holidays.

**What the tally reports.** These are the only numbers that leave the founders' store: testers started, and how many are strangers; the count for each mark; item and goal actions issued, accepted and completed, split by before or after a check-in and by trace or no trace; the "most worth doing" picks by kind; the number of items each tester sent, as a list of counts, and the gaps between sends in minutes; the counts labelled "do", "someday" and "liked"; item actions that needed the video; payments and refunds; video views, messages and sign-ups; and the number of private or friends' posts counted and not used.

**The consent form has three boxes.** (1) Run the test: the founders read my direction and what I send, write my plans, ask what I did, and keep these records until 30 days after the decision. (2) Let software draft my later plans: my direction, my own words and the public text of items I sent go to a named model provider, under terms that exclude training. (3) The founders may quote what I said, without my name. Box 1 alone is enough to take part. The form also says: that the plans mix suggestions made in different ways, which the founders explain at the end; that a one-time payment will be asked for on day 14; that taking part does not depend on paying; that testers may withdraw their records at any time; and that they should send only posts they are content for a founder to see.

## Phase 3 (8 December to 11 January): build what passed. Only on a Go

A full brief for Phase 3 is written after Gate B, from what the tally shows. In outline:

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 9 | **DM-share payloads,** founders' accounts only. Before the app goes Live, Eason posts a short privacy note for the receiver at a public URL (Meta appears to require one: check its current page). Then publish the Meta app (Live needs no App Review) and share 10 reels and 10 posts from the founders' own role accounts, never a tester's. | Eason | Write the receiver and the sanitiser. The receiver checks Meta's signature, keeps the share and the words typed with it, drops every other message text field in memory before any write, keeps raw bodies only on the receiving machine, deletes them once the summary of field names and presence counts is written, and is switched off when the item reports. | Pass: 18 of 20 carry caption text and a stable ID. Fail: Instagram capture means a link plus the person's word. Either way, record in `04-intake.md` what a share delivers and that webhook data is Meta Platform Data, and correct its "development mode works" line. |
| 10 | **Gate 0: data readiness,** before software touches a tester's data. All of: (a) each model provider's data-use and retention terms are recorded and dated in `07-privacy-and-safety.md`, every key sits on a billed project, and no preview-only feature touches tester data; (b) no private or friend's post reaches a model call, tested on synthetic input; (c) one command deletes a tester's rows, the writer's cache and its logs, proved by counts; (d) logs and `ai_runs` rows hold IDs, counts and costs, never directions, words or captions; (e) the writer runs only for testers who ticked box 2; (f) the consent form and a short data policy exist and match what the code does. | Both | Write the tests for (b) to (e) and drafts for (f). A founder does (a) and approves (f). | Pass: every check passes on synthetic data. Fail: plans stay hand-written. |
| 11 | **The plan writer,** prototype code in `experiments/plan_writer/`: a script a founder runs on his own machine against the founders' store. In: the direction, the items and the tester's words. For each item it sees only what an official route would deliver (the review's Intake table), entered by the founder. Out: rows in the contract's `actions` shape, validated before use (rule 6); each item action cites its items in `evidence[]`, and a goal action carries `goal_id` and no evidence. A founder edits and sends; no model sends anything. Every call goes through the `lib/ai.py` ledger (rule 11). It drafts the payers' plans from 21 December. | Derrick | Build it and test it on synthetic input and on the founders' own items. A founder runs it on tester data. | Pass: the founder sends at least half of the drafted item actions with wording changes only. Report the cost of each plan and the share of drafted actions the founder discarded. |
| 12 | **Do they stay.** Payers get their four weekly plans, with the control kept, and anyone may keep sending. These plans are owed in every outcome of Gate B, not only on a Go; until item 11 passes, the founders write them by hand. | Both | Extend `tally.py`. | Pass: 3 of the ten send an item in days 22 to 28 of their own run, and 2 payers pay a second $4.99 within two days of being asked on 4 January. |

**Gate C, 11 January:** items 11 and 12. A Go at Gate C earns a second cohort of 20 to 30 strangers with software-drafted plans and the control kept, and starts the long-lead items (a company, Business Verification, App Review). Anything else: narrow to the job the payers named, or stop.

## What this brief stops or parks

- New search arms, judges and rounds, and adopting anything on AI grades or synthetic searches.
- The hosted agent-access pilot, the exact-post fixes, the second-library run and the search head-to-head. They are parked in `PARKED-agent-layer-pilot.md` until paying testers ask for agent access.
- Export onboarding for testers. The product starts from what people send.
- Forming a company, Business Verification and App Review, until a Go at Gate C.
- A local-first build, and cost or storage tuning.
- Any scraping service.
- Ads, selling insight, and keeping data after deletion. `10-decisions.md` already rules them out: "Real deletion; no ads; no selling data".
- The rules-and-actions engine, the hub and the product skeleton, until a Go at Gate C.
- New amendments from the research loop. Decide the open ones first.

## Open decisions for the founders (item 1)

1. A-008: run the product by hand before building, and charge for the plan first. Both founders, in their own words: why, or why not.
2. The four marks, the lines in them and the decision table. Agree them or change them, then commit them before the first tester starts. Mark 4 has two candidate thresholds (see "What these marks can and cannot see").
3. The price: $4.99 (the agent's proposal: anyone who pays it would very likely pay $2.99), or $2.99 from the start.
4. Agent access. `10-decisions.md` calls MCP the paid core; Derrick's notes also place it third in the order of work. Does charging for the plan first change that decision, or only postpone it?
5. Ads, selling insight and keeping deleted data: confirm that the Agreed decision stands.
6. A third-party enrichment or scraping service: never, or only as `04-intake.md` allows (a paid provider with clear terms, last in the order). The agent's suggestion: not in this round.
7. The reading of rule 8 for the product account's inbox (see "Rules that hold throughout").
8. Where the founders' store is and who may open it; which founder holds the checkout, with the personal tax and liability point checked first; and whether a lawyer reads the consent form and the payment terms.
9. Hours. The dates assume 20 hours a week each, and Eason's part needs about ten days in four weeks. If either founder has fewer, move the dates, not the marks. The smallest version of Eason's part is the goal actions and an audit of the tally, about two days; Derrick then takes the rest and item 7 waits.
10. Whether the "Muse" in the earlier briefs is Meta's Muse, and whether it is available on the founders' accounts for item 2.
11. A-001 to A-007: accept, reject or defer each. Nothing in Phases 1 and 2 depends on them.
12. The privacy design for any later hosted build (a shared store, a private vault, a revocable key; A-006 item 6). Phase 3 as outlined stores nothing on a server; decide the design before anything does.
13. Where the code and logs of the earlier DM prototype are. They would show what a DM share delivered and how often people sent.
14. The tone of the videos. `07-privacy-and-safety.md` says "Entertainment is never shamed in outputs"; decide how far the message may lean on regret about scrolling.

## Deliverables

- `experiments/action_test/`: drafts for the founders of the consent form, the plan template, the check-in and day-14 forms and the comparison sheet; `tally.py` and its tests on synthetic sheets.
- `results/r10-marks.md`: the marks and the decision table as the founders agreed them, committed before the first tester starts.
- `results/r10-action-test.md`: the tally's counts and the decision. Aggregates only.
- `results/r10-message.md` and `results/r10-business.md`: counts and a one-paragraph outcome each, from what a founder pastes.
- On a Go: the Phase 3 brief, then `experiments/plan_writer/`, `results/r10-dm-payload.md`, `r10-gate0.md`, `r10-plan-writer.md` and `r10-stay.md`.
- A **founders' summary at the top of `STATE.md`** at each gate: what passed, what failed, what needs their decision.

Commit and push after each item. Personal data stays out of git.

## Budget

- **Phases 1 and 2:** no API spend and no hosting; card fees on the payments. Founder time: about 17 working days as the review counts them (Derrick about 7, Eason about 10), against about 20 available at 20 hours a week each. That is tight for Eason: confirm hours before 12 November.
- **In every outcome of Gate B:** the payers' four weekly plans, about one and a half founder-days in all.
- **Phase 3, only on a Go:** API cap $10, enforced through the ledger; about 11 founder-days.
- **Total cash cap: $25** (or what the founders say, if lower). Report at the cap.
