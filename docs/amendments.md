# Amendments

Proposed changes that **don't fit the current docs**: a request to build something differently from what `docs/` says. They are recorded here before or alongside the code, so the reasoning isn't lost and the docs stay the source of truth.

## When to add one

A coding agent (or a person) adds an amendment when someone asks for a change that would:

- contradict a rule in `AGENTS.md` or a decision in `10-decisions.md`,
- change the data contract (`03-data-contract.md`) or the RuleSpec / query API shapes,
- change the stack, the architecture boundaries (raw records, query API, action registry) or ownership,
- or otherwise do something the docs describe differently.

Small changes that fit the docs don't need one. Fixing a bug, or doing what a doc already describes, is just a normal PR.

## How it works

1. **Stop and say so.** The agent tells the person which doc and section the request conflicts with, quoting it briefly. It does not silently implement the change.
2. **Get the reason.** The person requesting it must explain *why* they want it. If they haven't, the agent asks: what problem does the current approach cause, and what does the new one fix?
3. **Make the case.** The agent writes down why the change is better than what the docs say now, *and* what it costs or risks. If the agent thinks it is not better, it says so plainly and records that too; the requester can still go ahead, but the disagreement is on record.
4. **Record it** as a new entry at the top of the log below, with status **Proposed**.
5. **Decide.**
   - Changes to the data contract, `schema/`, migrations, architecture boundaries, stack or ownership need **both founders** to accept them (in the PR or here).
   - Other changes can be accepted by the requester, noted with their name.
6. **When accepted:** update the affected docs in the same PR as the code, add a row to `10-decisions.md` that points to the amendment, and set the status to **Accepted** with the date. When rejected: set **Rejected** with the reason, and don't merge the code.
7. **Code may be written while Proposed** (e.g. on a branch to try it), but it isn't merged until the amendment is Accepted.

## Template

Copy this block to the top of the log:

```markdown
### A-NNN · Short title
- **Date:** YYYY-MM-DD
- **Requested by:** name
- **Status:** Proposed | Accepted (date, by whom) | Rejected (date, reason) | Superseded by A-NNN
- **Conflicts with:** doc and section (quote the line)

**What is requested**
One or two sentences.

**Why the requester wants it**
Their explanation, in their words where possible: the problem with the current approach.

**Why it is better than the current approach**
The concrete improvement (speed, cost, simplicity, accuracy, user value), with evidence if there is any: a measurement, an eval result, a failing case.

**Costs and risks**
What gets worse or harder: migrations, rework, lost guarantees (privacy, stability, terms), effect on the other founder's area.

**Agent's assessment**
Agree / agree with changes / disagree, and why.

**Affected**
Docs: … · Code: … · Contract change: yes/no · Needs both founders: yes/no
```

## Log

### A-009 · MVP v2: every kind of rule, a guessed-then-confirmed profile, outputs beyond chat, and YouTube picks from outside the library
- **Date:** 2026-11-12
- **Requested by:** Derrick, on 12 Nov 2026 after trying the first skeleton; written up by the agent
- **Status:** Proposed
- **Conflicts with:**
  - `docs/00-vision.md` › Out of scope for now: "Recommendations from outside the user's own data, habits, screen-time measurement." The request adds a block of related YouTube videos that are not in the person's library.
  - `docs/07-privacy-and-safety.md` › Honesty in outputs: "Inferred statements are labelled as inferred, with evidence; no personality labels or psychological claims." The request guesses a person's interests and skill level from their library. This is allowed only in the labelled, evidenced form; the amendment records how.
  - `docs/07-privacy-and-safety.md` › Third-party data: the open check "YouTube's derived-data clause before building YouTube summaries". The bot now reads a video's description and length from the official API and quotes lines from the description.
  - `docs/06-rules-and-actions.md` › RuleSpec (Proposed) and Action registry: the prototype's rule form grows well past the documented subset (random times, every N days, windows, exceptions, to-dos, reminders, acting on an earlier answer), and the registry gains `todo.add` and a calendar action that needs no sign-in.
  - `docs/09-roadmap-and-ownership.md` › Ownership: scheduler, executor, actions and the registry are Eason's. As in A-008, the agent builds them for the prototype.
  - Everything in A-008 still applies (prototype code, SQLite, the message channel).

**What is requested**
Make the skeleton cover what a person would really ask of it. `experiments/mvp/DESIGN.md` is the contract. In short:
- Rules for any timing a person can say (every 2 days, at random, the first Monday, several times a day, until a date) and rules that are not about timing (plain reminders, to-do lists, when new items arrive).
- Answers that give the person what they asked for: one recommended post with a reason checked against the post, the ingredients or steps, then alternatives and a wider selection. The same question must give the same answer.
- The person's context: a guess of their interests and level from their own library, which they confirm or correct in a sentence or two during setup.
- Outputs: email, a calendar link and file, a to-do list.
- Related videos from outside the library, shown apart from the person's own.
- An export routine set up during onboarding.

**Why the requester wants it**
In Derrick's words, shortened: "think of and implement all possible rules"; "it shouldn't say Why, it should give exactly what the users want"; "sometimes it says it can't find something but when I ask again it finds it"; "these should lead to a final product"; "base it upon the user's own context … make a guess, then have them validate it"; "we want to get as much as possible out of them during onboarding so that everything after feels frictionless"; "extra recommendations outside of their history but strongly related could be really good too".

**Why it is better than the current approach**
- The first skeleton handled weekly rules only. On 24 timing phrasings it read 13 correctly before the first fix. A tester who says "every other day" and gets a wrong rule stops trusting it.
- Measured on the founder's library: the "nothing found" flip came from a score cutoff, not from search. Verdicts, caches and a separate details step removed it in repeat runs (6 requests, 5 repeats each, identical every time).
- Without a level, "beginner" requests return advanced posts; without outputs, a recipe stays in a chat thread.

**Costs and risks**
- **Outside picks reverse a stated scope line.** They are limited to YouTube's official search, at most one search per answer, shown in a separate labelled block with YouTube's own title and channel. No model reads, ranks or rewords them, and the search text comes only from the person's own request. Sensitive topics are refused. YouTube's rules also require a terms page and a privacy page that name the YouTube API before outsiders use it: neither exists yet. Instagram has no lawful route, so there are no outside Instagram picks.
- **Profile inference.** The guess is shown to the person with counts as evidence and is theirs to correct. It never covers health, relationships, money, religion, politics or sexuality (a prompt rule and a code filter). It is a new store of personal statements; "delete my data" must remove it.
- **YouTube API data** (description, length) is kept at most 30 days and is quoted, not summarised. Whether quoting description lines is "derived data" under YouTube's terms is still the open check in `docs/07`; a human should read that clause before outsiders use it.
- **The export routine cannot be automatic for US accounts.** Google's data-portability API is not offered in the US and Meta documents repeating exports for the EU only. Onboarding gives links, the choices to tick and a reminder; the person still taps through the export.
- **Email needs a sending account.** Without SMTP settings, emails go to a local outbox. No sending domain exists.
- **Size.** The prototype's Python code grew from about 3,700 lines to about 17,100 lines in two days, plus about 12,200 lines of tests (measured on 13 Nov 2026). It was written by agents and checked by other agents and by tests. It is still throwaway code, and nobody has read all of it by hand.
- **Cost per message** rose: interpretation about $0.003, an answer about $0.009.

**Agent's assessment**
Agree with most of it; two parts carry real doubt.
- Rules, answers, consistency, to-dos and outputs: agree. They make the test honest.
- Profile: agree in the labelled, confirmed form above.
- Outside picks: agree only as built (YouTube, separate block, off unless asked or switched on). They move the product toward a recommender, which the vision ruled out for a reason: the promise is "use what you saved". Watch whether testers value the block or ignore it before it goes any further.
- Scope: this is a lot to put in front of the first testers at once. Sessions should start from the core (ask, rule, answer) and reach the rest only if the person goes there.

**Affected**
Docs: `docs/00-vision.md` (out-of-scope list), `docs/06-rules-and-actions.md` (RuleSpec, registry), `docs/07-privacy-and-safety.md` (profile inference, YouTube API data), `docs/10-decisions.md` · Code: `experiments/mvp/` (prototype) · Contract change: no (prototype only; the product contract is untouched) · Needs both founders: yes

### A-008 · A three-day MVP skeleton: text a request, get cited answers from your own saves on a schedule, on prototype code
- **Date:** 2026-11-12 (third version; the first proposed a hosted agent-access pilot, now in `experiments/PARKED-agent-layer-pilot.md`; the second a hand-run action test, now in `experiments/PARKED-action-test.md`)
- **Requested by:** Derrick, on 12 Nov 2026; written up by the agent
- **Status:** Proposed
- **Conflicts with:**
  - `docs/06-rules-and-actions.md` › Action registry: "`email.send` … Build first: no OAuth", and "Avoid SMS for now (US carrier registration, per-message cost)". The MVP's only action is a text message, sent by iMessage from a Mac.
  - `docs/00-vision.md` › MVP scope: outputs are "**Email** (first, no OAuth needed) and **Google Calendar** (second)", and "**Text messages** as an output" is listed as planned later.
  - `docs/09-roadmap-and-ownership.md` › Milestones: rules end to end are M4, after M0 to M3, and testers come at M5. The MVP builds rules first, on the prototype engine, and shows them to testers.
  - `docs/10-decisions.md` (28 Oct, Agreed): "Supabase for database, vectors, auth, storage and queues". The MVP uses SQLite and the demo's files on one Mac.
  - `docs/06-rules-and-actions.md` › RuleSpec (Proposed): the MVP uses a subset, with days and a time in place of a cron string, and one action.
  - `AGENTS.md` › Prototype code: "prototype scripts are not product code". Outsiders use prototype code under `experiments/mvp/`. `AGENTS.md` rules 1, 3 and 4 are set aside there.
  - `docs/07-privacy-and-safety.md` › Personal data › Sensitive categories: "hidden from agents and digests unless the user opts in". There is no tagger. The consent note says the bot reads the whole library, and health goals are declined.
  - `docs/09-roadmap-and-ownership.md` › Ownership: triggers, scheduler, executor and output actions are Eason's. The agent builds them for this prototype; Eason reviews them.

**What is requested**
Spend three days, 13 to 15 November, building a rough MVP: a person texts a request, the bot turns it into a rule with a preview, searches that person's own library of saved and watched posts, and replies on schedule with picks that link to their posts. Then show it to 5 to 10 people from 17 November. `experiments/BRIEF-10.md` (a draft) is the build plan.

**Why the requester wants it**
In Derrick's words, summarised: the product makes it easier to use what people have saved and watched; it cannot make anyone act. People see that value by trying it on their own saves, not by reading a hand-written plan or answering a test. A working skeleton shows the shape of the product, exposes its holes, and is something to put in front of users to see whether they want it.

**Why it is better than the current approach**
- The roadmap reaches a rule that runs for a real person at M4 and testers at M5. The MVP reaches both in a week.
- About 70% of the hard part exists: the demo imports exports and searches a library. The new parts are small: interpreter, composer, schedule, channel.
- It tests the product's own promise on people's own data, which the review's earlier test designs did not.

**Costs and risks**
- **Prototype debt.** The code is thrown away and rewritten after the decision that follows the sessions.
- **The channel is unofficial.** Sending iMessage from a Mac by script is not an Apple-approved route; an account can be flagged. Volume stays low and Telegram is the backup.
- **Privacy.** Testers' libraries sit on a founder's Mac, and item text and requests go to OpenAI. A consent note, a delete command, and no raw zips kept are the controls; no lawyer has read them.
- **Thin text.** About two in three of Derrick's saved recipe posts have no ingredients in the caption, and YouTube items have titles only. Answers say so plainly.
- **Strangers and payment are still the real answer.** A good demo to friends proves little; the sessions keep the earlier review's strangers, real price and marks agreed beforehand.

**Agent's assessment**
Agree. The skeleton is small given what exists, and it tests the product as Derrick describes it. Two conditions: the reliability rules in BRIEF-10 section 5 are enforced in code, not left to prompts; and the session marks are agreed before the first session. The agent drafted the two earlier versions of this amendment, which proposed other first steps.

**Affected**
Docs: `docs/06-rules-and-actions.md` (channel, RuleSpec subset), `docs/00-vision.md` (MVP outputs), `docs/09-roadmap-and-ownership.md` (milestone order, who builds the executor), `docs/10-decisions.md`, `docs/07-privacy-and-safety.md` (consent note, sensitive items) · Code: `experiments/mvp/` (new, prototype) · Contract change: no · Needs both founders: yes

### A-007 · An optional, soft "direction" input on search requests
- **Date:** 2026-11-09
- **Requested by:** Derrick (BRIEF-9 Track 3, design only), written up by the round-9 search loop (`docs/research/2026-11-09-round9.md` section 8)
- **Status:** Proposed
- **Conflicts with:**
  - `05-processor.md` › Query API, `search` params: "`query?`, `types?`, `themes?`, `kinds?`, `platforms?`, `since?`, `until?`, `exclude_item_ids?`, `limit`". There is no field for the user's current direction.
  - `AGENTS.md` rule 1: "Do not invent fields ad hoc."
  - The name: `glossary.md` already defines **Direction** as "the user's goals and theme relations, compared with where attention actually goes", and the query API has a `direction` op.

**What is requested**
- Add an optional `direction` to `search` params: `{ text?: str (≤ 300 chars), goal_ids?: [gol_…] }`. It is null by default.
- When set, the planner may sharpen the search toward it **softly**:
  - one extra low-weight list (weight ≈ 0.3);
  - a small boost (≤ ×1.1) to items close to the direction;
  - no filtering, no removal or replacement of typed words, and no effect on the instant keyword path.
- The user writes the stored direction, can edit it, and can switch it off. It lives in the private vault as user-created core data, which is never regenerated.

**Why the requester wants it**
Derrick expects the same words to mean different things depending on what the user is working toward: a search for packaging ideas from someone opening a bakery probably means packaging for baked goods. Today every search is read without that context.

**Why it is better than the current approach**
- No evidence yet. It was not built or tested in round 9.
- What supports trying it:
  - real searches are short and topical (Phase A);
  - round 9's frame showed that reading intent from the words alone does not help;
  - a stated direction is information the search text cannot carry.

**Costs and risks**
- **Contract change:** a new field in `schema/query.py` and in `05-processor.md`.
- **Overlap with `goals`:** if a direction is not simply an active goal, there will be two concepts for one idea. Recommend storing it as a goal and passing `goal_ids`.
- **Privacy:**
  - The direction is user data. It goes to the model provider inside the frame call, as the search itself does.
  - It must never reach the shared content store or a cross-user cache. A rewrite cache must key on it, or skip caching.
  - The vault privacy section (A-006 item 6) is still missing.
- **Quality risk:** a direction can pull results away from what was typed. Round 9's A1 lost −0.043 on dev by replacing the typed words.
- **Evaluation cost:** about 45 on-direction searches written by the person whose direction it is (MDE ≈ 0.05), plus about 20 off-direction searches for a no-harm check. That means roughly 300–450 of that person's grades.

**Agent's assessment**
Agree with changes. Reserve the field now, and wire it only after the evaluation above shows a gain and no harm off-direction. Prefer `goal_ids` over free text, so one concept serves both direction reports and search. If free text stays, rename the request field (for example `steer`) to avoid clashing with the `direction` op.

**Affected**
Docs: 05-processor (Query API `search` params), 03-data-contract (if a new stored field rather than `goals`), 07-privacy-and-safety (vault), glossary · Code: `schema/query.py` (none built; the experiment frame `qi-v1` already reserves a null `direction`) · Contract change: yes · Needs both founders: yes

### A-006 · Search as one index with a deterministic query planner, per-platform list sets and a tool surface for agents
- **Date:** 2026-11-08
- **Requested by:** the search loop, round 8 phase B (`docs/research/2026-11-08-architecture-review.md`), for the founders
- **Status:** Proposed (items 1–4 only after their round-8 experiments pass on `known_test_clean` / `ig_known_test`)
- **Conflicts with:** `05-processor.md` › Query API `search` ("Hybrid: vectors + keywords + facet filters, reranked") and › Performance targets; A-003's universal rewrite + HyDE.

**What is requested**
1. A code (no-LLM) query planner choosing a keyword, descriptive or structured path by query shape and the user's vault priors (platform split, creators).
2. te lists only for caption-type or untitled items, with coverage-fair fusion.
3. A creator index in the shared content store; era and affinity per user in the vault.
4. An optional second-stage refine (LLM listwise on the top 20).
5. MCP `search` accepting `mode` and structured filters, skipping our rewrite when the caller (the user's agent) supplies them.
6. A written privacy section (shared store vs private vault, key revocation) in `05-processor.md`, which is missing today.

**Why the requester wants it**
The founders asked for the cost- and performance-optimal architecture. The rewrite is ~92% of per-search cost and ~1.8 s of 2.0 s p50, never tested on short keyword searches, and redundant when the user's own agent writes the query.

**Why it is better than the current approach**
Evidence in sections 1–4 of the review: only item representation (3-large, te on Instagram) has held up on held-out; query-side add-ons are ~0 or negative there; one pipeline for both platforms costs YouTube searches.

**Costs and risks**
Unproven until the round-8 experiments pass; a planner adds a routing error mode (the round-7 router read the platform right only 55% of the time); creator profiles touch privacy (no shared profiles for mutual-follow creators).

**Agent's assessment**
Agree in direction; accept only the parts that pass held-out tests.

**Round 8 evidence per item (2026-11-09; `docs/research/2026-11-08-round8.md`, `experiments/results/r8-final.md`; status unchanged, still Proposed)**

How the evidence was gathered:
- Held-out = one scoring each of `known_test_clean` (216 real YouTube searches, primary), full `known_test` (381) and `ig_known_test` (150 LLM-written Instagram searches).
- Three pipelines were scored: H0r8 (old base), B8.5 = Q8 (items 1, 2 and 4 together, plus int8 vectors) and FM (Q8 with a gpt-5-mini refine).
- The items were **not scored separately on held-out**, so any held-out support below belongs to the package.

Per item:
1. **Planner and keyword path. Held-out support: yes (cost); quality level.**
   - On real YouTube, Q8 − H0r8 is +0.003 [−0.026, +0.031] mrr2. On the 189 instant-routed searches it is +0.010 [−0.020, +0.039].
   - Not established on `s10_2`: CI [−0.042, +0.042] on the instant-routed searches.
   - Cost is −61% per 1k typed searches ($0.049 vs $0.127). First screen p50 is 0.58 s vs 1.97 s on keyword searches.
   - Instagram instant-routed searches (50) are flat on mrr2, with `s10_2` −0.060 [−0.14, +0.013].
   - The vault platform prior (prior-p1) is part of the package's Instagram gain. It was not tested alone on held-out.
   - Wider routing (route-r2) failed on dev.
2. **te lists for caption-type items only (Instagram only). Held-out support: in direction, on a biased set.**
   - The package gains +0.110 [+0.057, +0.162] mrr2 on `ig_known_test` (Holm 1e-4), about 85% of the dev size. No YouTube loss appeared.
   - The set shares the generator's te bias. Searches with no te-only word gain +0.088 [+0.023, +0.152].
   - Needs real human Instagram searches before acceptance.
3. **Creator index. Held-out support: none; not tested on held-out.**
   - On dev, a creator list lost on both known-item sets (CI: `known_dev` −0.019 [−0.033, −0.006], `ig_known_dev` −0.022 [−0.040, −0.005]; H5d −0.018 on `known_dev`), by displacing singleton-creator targets.
   - Only the determinism fix (sorted ties) has earned its place.
   - Recommend deferring this item.
4. **Second-stage refine. Held-out support: none for the refine's own effect.**
   - The nano refine gated to YouTube-read rewrite searches rests on dev nDCG alone (TFY +0.038 [+0.010, +0.071], Holm 0.021, below its MDE of 0.045). No graded held-out set was scored.
   - On held-out refined YouTube searches the package is −0.038 (23, clean) and −0.018 (43, full) against H0r8, within noise.
   - The gpt-5-mini upgrade (FM) gains +0.026 [+0.006, +0.049] on `ig_known_test` (Holm 0.011, below the 0.03 bar and its MDE of 0.031) and +0.008 [−0.001, +0.018] on clean YouTube (Holm 0.16). It costs +$0.043 per 1k (+86%).
   - The refine costs total p95 +1.3 s (nano) to +1.5 s (mini).
   - Keep it optional and off the critical path.
5. **MCP `search` with `mode` and filters. Held-out support: n/a** (not evaluable offline). The case rests on the instant path's held-out result: when the caller supplies the query, skipping our rewrite costs no measured quality on keyword searches.
6. **Privacy section in `05-processor.md`. Held-out support: n/a** (documentation). Still missing, and still needed before items 1–4 ship.

**Related but outside the six items:** int8 item vectors (1,024 B per item, −75% RAM) were non-inferior on dev and are inside Q8's held-out result. Item vectors are part of the contract, so they belong here or in A-003. They need an int8 kernel on desktop.

**Updated assessment:**
- Accept 1 and 2 in direction now, with 2 conditional on a real Instagram search set.
- Defer 3.
- Make 4 optional. The recommended B8.5 keeps the gated nano refine on dev evidence alone; whether it stays on by default is a founder call. FM (mini) should not be the default until real Instagram searches confirm it.
- 5 and 6 are unchanged.

**Affected**
Docs: 05-processor (Query API, Performance targets, new privacy section), 07-privacy-and-safety, A-003 · Code: prototype only · Contract change: yes (creator index; `search` params) · Needs both founders: yes

### A-005 · Make search verdicts match the noise: screen on dev, confirm on large held-out sets, two judges and a human anchor
- **Date:** 2026-11-08
- **Requested by:** the search loop, round 8 phase A (validation audit; `experiments/BRIEF-8.md`), for Derrick
- **Status:** Proposed
- **Conflicts with:** `experiments/BRIEF.md` › Rules: "Adopt a change only if dev nDCG@10 gains ≥ 0.03 with the paired 95% CI above 0, or ≥ 0.02 with more wins than losses and no extra cost". Also `experiments/BRIEF-8.md` › Searches, on how `known_*` and `ig_known` are built and scored. `docs/08-evals-and-quality.md` has no requirement on judge agreement.

**What is requested**
1. **Dev becomes a screen.** An arm advances if it passes the current rule *and* survives Holm across the round's arms (one-sided paired test, α 0.025).
   - **Adoption** needs a preregistered confirmation on large held-out sets: `known_test_clean` (216), `ig_known_test` (150) and a fresh Derrick set of 40–45. Each comparison states its minimum detectable Δ beforehand.
   - Clause 2 (no-cost arms) also needs CI > 0.
2. **Two independent judges per pooled item.** Fresh Claude agents grade independently and a third adjudicates disagreements. Score with the adjudicated grade and report the single-judge result next to it. A non-Claude model may be a third vote but never the sole judge.
3. **A human anchor per held-out set.** Derrick grades a blind 60–80-item calibration sheet drawn from the pooled items (weighted to thin, low-text items). Each held-out report states AI–Derrick κ.
4. **Known-item label repair, kept separate from scoring.**
   - Hand-verify a 100-search subset of `known_test_clean` (Derrick or a blind judge).
   - Accept as target a query-matching video watched ≤ 2 minutes before the logged search time.
   - Do **not** clean labels by word overlap.
5. **`ig_known`.** Add a slice of searches generated without the te summary (caption + creator only), or report te-arm gains on `ig_known` with the lexical-match caveat.

**Why the requester wants it**
The audit (`experiments/results/validation-audit.md`) found:
- **Power.** The median per-search SD of Δ nDCG@10 is 0.12, so the minimum detectable Δ at 80% power is 0.05 on 44 dev searches, 0.075 on 21 and 0.12 on 10. Every dev near miss and every single held-out result so far sits below its MDE.
- **The rule.** Clause 1 detects a true +0.03 only 38% of the time. Clause 2 passes a zero-effect arm 13% of the time.
- **Multiplicity.** Of 30 primary dev comparisons in rounds 4.1–7, 3 passed (near-identical variants in one round). None survives Holm or Benjamini–Hochberg. The one adoption (E1) failed held-out.
- **Judges.** Single-judge pooled grades agree with a fresh judge at κ 0.54–0.66 and with Derrick at only κ 0.39–0.43, with a suggestive under-crediting of low-text items. Before the audit no Derrick–AI overlap existed, so this had never been measured.
- **Known-item labels.** 12.5% are clear noise and up to 27.5% are noise or doubtful. Grade-1 "later" videos are mostly autoplay or unrelated. The known split leaked across sessions; that part is already fixed in the protocol.

**Why it is better than the current approach**
- Most past verdicts (adopt / near miss / not confirmed) were decided by noise of the same size as the effects.
- Large known-item sets give MDEs of about 0.02–0.05 in MRR at no judging cost. That is enough to see +0.03 effects that 10–21 graded searches cannot.
- Two judges plus adjudication cut single-judge noise. In the audit, a median of three judges raised κ with Derrick from about 0.41 to 0.49.
- A small human sheet is the only way to know whether the AI judge drifts from what the user means.

**Costs and risks**
- **Fewer adoptions.** Dev wins of +0.03–0.05 will often be "screen passed, not confirmed" until the large sets confirm them.
- **Contamination.** Every held-out scoring uses up a set's clean status, so known-item sets must be refreshed (more My Activity years, more saved posts) and `ig_known` rebuilt.
- **Two judges** double the agent judging time; it is $0 in API calls with agent judges. A gpt-5-mini third vote costs about $0.12 per 1,000 items.
- **Derrick's time:** about 30–45 minutes per held-out set.
- **Known-item MRR** rewards finding one video, not good lists. Keep a graded nDCG set (dev + fresh Derrick set) for list quality and kinds.
- **Label repair** by hand can itself bias toward what the checker finds obvious, so it stays a reported subset and does not replace the auto labels.

**Agent's assessment**
Agree with all five.
- Items 1 and 3 matter most: without them the loop keeps adopting or rejecting on noise.
- Item 2 is cheap.
- Items 4 and 5 are refinements.
- The protocol-level fixes that are not contestable (grade-2-only known-item metrics, the session-disjoint `known_test` subset, MDE / Holm / grade-sensitivity reporting, pool-everything, held-out cache hygiene) are already applied in `experiments/eval/PROTOCOL.md`, marked "changed in round 8, see audit".

**Affected**
Docs: `experiments/BRIEF.md` (adoption rule), `experiments/eval/PROTOCOL.md`, `docs/08-evals-and-quality.md` (judge-agreement line) · Code: `experiments/eval/score_c4.py`, `judge.py` (two-judge merge) · Contract change: no · Needs both founders: no (Derrick as requester / eval owner)

### A-004 · YouTube items, interactions and search history in the data contract
- **Date:** 2026-10-30
- **Requested by:** the search loop, round 2 (`experiments/BRIEF-2.md` › Q5), for the founders
- **Status:** Proposed
- **Conflicts with:** `03-data-contract.md` › InteractionKind (no `playlist`), › Item (`caption` described as third-party caption text; no title field), › Enrichment (`enrichments` fields), and AGENTS.md rule 1 ("Do not invent fields ad hoc").

**What is requested**
The prototype YouTube importer and API enricher (`experiments/youtube/`, synthetic fixtures only) need contract decisions before product code:
1. A YouTube playlist add maps to `collection` with `collection_name` (weight 0.8), not a new `playlist` kind; the user's capture playlist maps to `share` with `share_audience=self`.
2. For YouTube, `items.caption` holds the video **title**; the description goes to enrichment.
3. `enrichments` gains optional `title`, `description`, `tags[]`, `topic_categories[]`, `category_id`, `default_audio_language`, `live`, `chapters[]` (`{start_s, title}`), with `refresh_by` = fetched + 30 days (YouTube API terms).
4. YouTube search history stays in `raw_records` only (no table); it is a signal for later, not an item.
5. The eval format adds a `moment` search kind whose answers carry `{start_s, end_s}` (`experiments/youtube/eval_format.md`).

**Why the requester wants it**
Derrick is preparing a Takeout and YouTube searches; the next round should start without contract questions.

**Why it is better than the current approach**
The current contract has the `platform_data.youtube` fields but no place for API metadata, chapters or search history, and no interaction kind for playlists. Mapping onto existing kinds keeps rule 4 (only adapters know the platform).

**Costs and risks**
- YouTube Developer Policies III.E.4.h ("no derived data") may cover tier-1 summaries and embeddings of API text: needs a legal read before the product stores them.
- Takeout field names and file layouts were checked against Google's documentation and community sources, not a real export; verify on Derrick's Takeout.
- Captions via the API need edit permission on the video (only the user's own uploads).

**Agent's assessment**
Agree with 1–5; verify the formats on a real Takeout first.

**Round 3 update (2026-10-31, real Takeout; `docs/research/2026-10-31-youtube-round.md`)**
- **Formats verified on a real export:**
  - watch history is HTML by default, with local times and zone abbreviations;
  - playlist CSVs carry video IDs only;
  - the YouTube product's watch history is truncated (11.5 months).
- **"My Activity" (YouTube) holds the full history from 2014 plus likes.**
  - Intake docs should ask users for both products.
  - Store import coverage dates (`watch_first_at`, `watch_last_at`).
  - Likes map to `like` (0.3).
- **Item 3 (API fields in `enrichments`) is in doubt.** Developer Policies III.E.4 item 08 bars "new or derived data" from API data. Summaries and embeddings of descriptions, tags and chapters likely count (`experiments/research/youtube-api-terms.md`).
  - Proposed instead: `items.caption` = Takeout title; API fields only for display and filtering (duration, availability), each with `refresh_by` = fetched + 30 days.
  - A legal read decides whether refreshed API text may be keyword-indexed.
  - Measured cost of not using API text: nothing overall, but real on moment and named-video searches.
- **New: video-understanding enrichment** via the Gemini API's YouTube-URL input. It doesn't use YouTube API data and is allowed in our reading; it is a preview feature.
  - Its output (description, spoken summary, timestamped segments, on-screen text) needs a home: `enrichments` with `source = video_url`, `segments[] {start_s, end_s, text}`.
  - Gate it to saved videos with no text.
- **New: intent filters on the `search` op.** These are structured filters the rewrite infers: `time_window`, `interaction` (liked / saved / never watched / rewatched), `min_duration_s`, `max_duration_s`, `shorts`. Each is applied to the user's own interactions.

**Affected**
Docs: 03-data-contract (InteractionKind, Item, Enrichment), 04-intake (YouTube), 08-evals-and-quality (moment kind) · Code: none in `scrolldigest/` (prototype in `experiments/youtube/`) · Contract change: yes · Needs both founders: yes

### A-003 · Enrich every item with one cheap text pass, index it separately, and add HyDE to search
- **Date:** 2026-10-30
- **Requested by:** the search loop (`experiments/BRIEF.md`), for the founders
- **Status:** Proposed
- **Conflicts with:**
  - `10-decisions.md` › 18 Oct: "Tiered, on-demand enrichment with a shared cache for public content · Enriching everything is too expensive."
  - `05-processor.md` › Stage 1 tiers: tier 1 = "Embedding, filter, info gate, simple facets"; LLM summaries only for "High value … or on demand".
  - `03-data-contract.md` › ItemCard: "`summary` … 1–2 lines (LLM; full-depth items only)"; › Embedding: one `item_embeddings` row per item, text = "`caption[:600]` + … hashtags".
  - `05-processor.md` › Stage 2 Index ("Keyword index: Postgres full-text search over caption, hashtags, transcript summary, facets") and › Query API `search` ("Hybrid: vectors + keywords + facet filters, reranked").

**What is requested**
1. **Tier 1 becomes an LLM text pass for every item** (except friends' posts): from caption, hashtags, creator, media kind and the user's collection names, a cheap model writes a one-line summary, facet slots (kind, topics, shown, said, place, people, vibe, use), the facets it can't know (`unknown`) and 3–5 likely searches. Run in Batch for history imports; per item for new captures.
2. **Index it separately:** its own keyword field/index and its **own vector** (same model as the caption vector), each fused into search by rank fusion as extra lists. Never concatenated into the caption text.
3. **Search adds HyDE:** the AI rewrite also writes three short invented captions for a matching post; their mean vector, mixed 0.3 query / 0.7 captions, joins the query phrases in both dense lists.
4. Keep bge-small as the one embedding model (A-001); the swap experiments did not justify a change.

**Why the requester wants it**
The brief asks to find what Muse finds, faster and cheaper, and to run later processing on the desktop. Captions alone top out: 37% of right answers share no word with the search.

**Why it is better than the current approach**
Measured with a fresh, blind evaluator per round on 16 dev searches over one 21k-item history (`research/2026-10-30-search-loop.md`):
- Honest caption-only search with a real AI rewrite: nDCG@10 0.49.
- + text pass indexed separately: **+0.059 [+0.016, +0.108]**, 13 searches better, 3 worse.
- + HyDE: **+0.022 [+0.008, +0.037]**, 10/1. Total **0.57, +0.080 [+0.036, +0.133]**.
- Held-out test (6 searches): **+0.023 [−0.010, +0.053]**, 4/1/1, recall@100 **+0.060 [+0.007, +0.107]**; HyDE alone not confirmed (+0.009, 2/3/1). All 22 searches: **+0.065 [+0.028, +0.103]**, 17/4/1.
- Appending descriptions to the caption instead of indexing them separately *hurt* vibe and people searches in the Muse ceiling test.
- Cost: **$0.18 per 1,000 items** with Gemini Flash-Lite Batch ($3.7 for a 21k history; ~15.8k items done in ~5 minutes), ~1.1 KB per item, +0.05 s per search. HyDE costs nothing extra (same rewrite call), +0.1 s.
- "Too expensive" in the 18 Oct decision assumed transcripts and video; a text pass is ~100× cheaper than a video description pass.

**Costs and risks**
- **Contract change:** ItemCard gains `facet_slots`, `unknown_facets`, `likely_searches`, `prompt_version`, `ai_run_id` for every item; `item_embeddings` gains a `view` (caption | enrichment), so two rows per item.
- **Privacy:** the user's collection names go to the LLM with the item. They must stay out of the shared content cache (cache the caption-only part per content, add collection names per user, or drop them). Friends' posts are never sent (463 items here). Queries already go to a cloud LLM for the rewrite.
- **Hallucination:** a reference check against Muse on 200 items found our text pass contradicts Muse on 9% of items, mostly the item kind; it misses 96% of audio, 60% of place and 50% of speech, which needs media.
- **Local fit:** the pass and the rewrite need a cloud LLM (or the user's agent over MCP); a local 1–4B model would take days of CPU for a backfill. Search itself stays local (bge-small + keyword index).
- **Evidence limits:** one person, 16 dev + 6 test searches; place searches got worse (one search); labels were partly grown by one judge per round.

**Round 2 update (2026-10-30, `experiments/BRIEF-2.md`)**
- **Search flow becomes two-stage.** No LLM rewrite can meet `05-processor.md`'s "search p95 ≤ 500 ms" from our infrastructure (a bare provider call is ~0.9 s p50). An instant first screen (no rewrite: 0.12 / 0.17 s p50 / p95) followed by the refined list (~2–3 s) keeps the target as **time to first screen**; add a second target for the refined list (proposed p95 ≤ 3 s) and a `stage: instant | refined` field (or streaming) on the `search` op. The instant screen scores ~0.07 below the refined list over all 22 searches.
- **Enrichment is background, not on demand.** Under the finalist, 52% of missed answers rank beyond 1,000 and only 12% sit in the top 200, so "enrich a weak search's nearest candidates" (`05-processor.md` › Tiers, "On demand") can reach at most ~12% of misses. Keep on-demand only as a supplement.
- **Gap flags pick facets, not items.** The per-item `unknown` facets predict a search miss only weakly (AUC 0.60, below a caption-richness score's 0.67), and no item-level gate selected misses better than chance. Use the flags to choose *which* facet a selected item's next media rung should fill, with the rule "unknown OR empty". Proposed media gate (no spend yet): one image for everything (~$0.30 / 1k items, Batch); audio for music/dance/trend and how-to/talking-head reels with an audio or said gap (~25% of items); full video for reels with weight ≥ 0.8 (~15%). Details: `experiments/results/r2-q1-gap-flags.md`.
- **Not adopted in round 2:** a library profile in the rewrite prompt (+0.006), a "look first" rewrite (+0.024 on dev, −0.038 on the held-out test, +0.007 over all 22), faster or shorter rewrite models (−0.011 to +0.010 at 3–5× the cost), and routing lookups past the rewrite (fires on 2 of 13 searches).

**Round 3–4 update (2026-11-03; `docs/research/2026-10-31-youtube-round.md`, `docs/research/2026-11-03-combined-loop.md`)**
- **The text pass is a per-platform decision, not a universal one.**
  - It helps Instagram: +0.059 in round 1; +0.051 on Derrick's fresh held-out searches in round 4.
  - It does not help YouTube, whose Takeout titles are already descriptive: −0.046 in round 3; −0.02 on held-out in round 4.
  - Item 1 should read "every **Instagram** item", plus YouTube items with no title. It should not cover all YouTube items.
- **Item 2 needs coverage-fair fusion.** Adding the text pass as extra RRF lists rewards items just for being in more lists. In one index with both platforms, that let enriched Instagram items take about half of YouTube searches' top 10.
  - **Coverage-fair fusion:** an item outside a list gets its own-list score in that list's place. It removes most of the crowding (from 53% to 24% of YouTube's top 10) and was +0.059 over plain fusion on dev.
  - Some crowding remains, so YouTube searches still lose a little on held-out.
- **"Enrich only where the text is thin" needs care in how it's built.**
  - Separate lists for thin items only gave those items two full votes and failed (−0.18).
  - Routing under coverage-fair fusion worked on dev (+0.050 with te on about 60% of items) but was not confirmed on held-out.

**Agent's assessment**
Agree. It is the only change in 24 experiments that clearly cleared the bar, it is cheap and fully batchable, and it fits the derived-data rules (rebuildable, versioned by prompt and model). Recommend accepting 1, 2 and 4 now, with collection names kept per user; accept 3 (HyDE) as an optional extra, since it is free but was not confirmed on the test split; and revisiting when media arrives (the same separate-field pattern should carry a media description pass).

**Affected**
Docs: 03-data-contract (ItemCard, Embedding), 05-processor (Stage 1 incl. › On demand, Stage 2, Query API › search, Performance targets), 07-privacy-and-safety (collection names to the LLM), 10-decisions (18 Oct row) · Code: none in `scrolldigest/` yet (prototype in `experiments/methods/`) · Contract change: yes · Needs both founders: yes

### A-002 · Getting thumbnails, keyframes and audio for each reel
- **Date:** 2026-10-30
- **Requested by:** Derrick
- **Status:** Proposed
- **Conflicts with:**
  - `AGENTS.md` › rule 7: "Preference order: data the user hands us (exports, DM shares, Takeout) → official APIs → paid providers with clear terms. No logged-in bot accounts, no evading rate limits or blocks."
  - `04-intake.md` › Rules of the road, and `10-decisions.md` › Sep: "Official Instagram API only for capture; no logged-in automation."

**What is requested**
Get visual and audio content for each reel without depending on a scraping vendor, ideally with "microdownloads": fetch only the streaming manifest, the audio track and a few keyframes instead of whole videos, and feed those to the description pass and to multimodal embeddings.

**Why the requester wants it**
Thumbnails and frames likely carry the most information about a reel, and search results show captions are the ceiling (37% of right answers share no words with the query). Meta's oEmbed stopped returning thumbnails in Nov 2025. Relying on a third-party scraper (Apify) is fragile and outside our control.

**Why it is better than the current approach**
The docs give no route to images or audio at all, so the visual/audio searches (vibe, said/shown, audio, more-like-this) stay capped. Partial downloads cut bandwidth and model cost: a few keyframes plus audio costs roughly 2–4× fewer Gemini tokens than the full video (video ~100–300 tokens/s; audio 32 tokens/s; an image ≤384 px 258 tokens, per Google's token docs).

**Options considered**

| Route | What it gives | Platform-terms risk | Verdict |
| --- | --- | --- | --- |
| A. Official DM-share webhook, then partial (HTTP range) reads of the media we receive | Ongoing captures. Meta's docs only say "the URL for the shared media or post" is included; whether it's a media file must be confirmed with a real webhook | Low: official API, user-initiated | **Do first:** capture one real webhook as a fixture |
| B. On-device capture in the desktop app / browser extension (the user's own client already loads the media they view or share) | History and ongoing; data stays local; fits local-first | Low–medium: the user's own session on their own device; no bots | **Plan with the desktop app** |
| C. Public post-page metadata (og:image) fetched logged-out, rate-limited, only for items in the user's import | Thumbnails for history imports | Medium: Meta's terms forbid automated collection without permission; a 2024 ruling (Meta v. Bright Data) didn't find logged-out scraping of public data breached them on that record, but it is not a green light, and Meta could revoke the app we need for DM capture | **Only after legal review**, thumbnails only |
| D. Private streaming manifests (DASH) via Instagram's internal web/app APIs | Audio + keyframes, cheapest bandwidth | High: private endpoints, usually logged-in sessions, actively blocked, fragile; conflicts with rule 7 | **Not recommended** |
| E. Third-party providers (Apify etc.) | Metadata incl. song title/artist, thumbnails | Medium; vendor dependency | Fallback only, behind the enricher interface |

**Costs and risks**
Routes B–E carry platform risk to the one Meta relationship we depend on (DM capture). Partial reads of official media (A) still need the media URL to be a file; if it's only a post link, A gives no media.

**Agent's assessment**
Agree with the goal; disagree with D. Recommend A now, B as the main route for history once the desktop app exists, C only after a legal check, E as fallback. The microdownload idea itself is good and applies to A and B: range reads of keyframes + audio instead of whole files.

**Affected**
Docs: AGENTS.md (rule 7 wording if C is accepted), 04-intake, 07-privacy-and-safety, 10-decisions · Code: intake enrichers · Contract change: no (new enrichment fields covered by A-001) · Needs both founders: yes

### A-001 · How reels are stored and searched
- **Date:** 2026-10-30
- **Requested by:** Derrick
- **Status:** Proposed
- **Conflicts with:**
  - `03-data-contract.md` › Item: "One piece of content, stored once per user however many times they touch it." (proposes shared content + per-user items)
  - `03-data-contract.md` › Embedding: one vector per item, "Index with HNSW (cosine)". (proposes item + chunk vectors, a versioned search text, exact search per user for now)
  - `02-tech-stack.md` › Embeddings: bge-small only. (confirms bge-small as the single model for cloud and desktop; adds OpenAI 512d as a tested fallback)
  - `07-privacy-and-safety.md` › Friends: "The recipient of a friend share is not stored on the interaction." (proposes opt-in storage)
  - `10-decisions.md` › 15 Oct: "Transcripts not stored." (proposes a per-source rule)

**What is requested**
Adopt the storage and search design in [research/2026-10-30-search-storage.md](research/2026-10-30-search-storage.md): shared `content` rows with an assembled, versioned `search_text`; item and chunk vectors; a weighted keyword index; facets; audio title/artist; and a search flow of AI rewrite + meaning + keyword search, rank fusion and pseudo-relevance feedback, with thin items held out of meaning search until enriched.

**Why the requester wants it**
Search is the part every later feature uses (rules, boards, digests, MCP). Captions-only, one-vector-per-item search found the right reel in the top 10 well under half the time on real searches, and failed outright on audio and on content that is only said or shown.

**Why it is better than the current approach**
Measured on 22 real searches over a 20k-item history: meaning search alone 0.22–0.34 nDCG@10; the proposed flow 0.50–0.51, with ~57% of the top 10 correct and the first right answer usually near the top (MRR ~0.9). Sharing content means each public reel is enriched and embedded once for every user. One open model everywhere lets the cloud's first report hand vectors straight to the desktop app.

**Costs and risks**
A data contract change before any production data exists (cheap now, expensive later). More derived tables (chunk vectors, search text versions). Storing share counterparts, even opt-in, weakens a privacy default and needs clear consent. Per-source transcript rules need a terms check per platform. Results come from one person's data and 22 searches.

**Agent's assessment**
Agree. The measured gains are large compared with the noise, the changes are additive to the existing raw/core/derived rules, and the riskiest part (share counterparts) is opt-in. Recommend accepting items 1, 2 and 5 now, and 3 and 4 after the privacy and terms checks.

**Affected**
Docs: 03-data-contract, 02-tech-stack, 05-processor (Index, Query API, Search), 04-intake (audio metadata, description pass in the benchmark), 07-privacy-and-safety, 10-decisions · Code: none yet · Contract change: yes · Needs both founders: yes
