# Brief, round 10 (DRAFT): pilot before platform. Ten outside testers and a payment decision by 4 January

> **Status: DRAFT, not binding.** Written by the agent on 10 Nov 2026 from the outside review "Scroll Digest: outside review and 8-week plan" (a private doc; ask Derrick for the link). It becomes binding only when both founders accept it **and** amendment A-008 in `docs/amendments.md`. Until then, an agent may build the Phase 1 code on this branch and nothing else.

This is not a search-research round. There are no new arms, no new judges and no adoption rule. The roles, the `lib/ai.py` ledger and the privacy rules are the same as in `BRIEF.md` and `BRIEF-8.md`: the agent that evaluates never builds, builders never open `data/all/evals/labels/` or `eval_work/`, and nothing under `data/` goes into git.

**The question for this round is not "is the search better" but "does anyone want this".** Will ten people who are not founders import their history, connect their own AI agent, come back, and pay? And is there a reason to use it beside Meta's Muse and Google's Gemini?

## Who does what

Each item below is marked **Agent** or **Founder**. The agent builds code, tests, pages and reports. Only a founder may:

- publish anything outside the repo (a page, a post, a Meta app);
- contact, recruit or onboard a person, or accept a file from one;
- run tasks on a personal Muse, Gemini, Claude or ChatGPT account;
- take money;
- accept or reject an amendment.

An agent that reaches a Founder item stops there, writes what is ready into `STATE.md`, and waits. Do not work unattended past a gate.

## Setup

1. **Decisions first (item 3).** Nothing after Phase 1 starts until the founders have ruled on A-001 to A-008 and the list under "Open decisions" below, and the outcome is in `docs/10-decisions.md`.
2. **Data for regression checks.** Same as round 9: keep `data/all/` or rebuild it as in `BRIEF-8.md` setup step 1. Check that `r8.5/q8` (Q8) reproduces on `known_dev` before anything else.
3. **Keys** come from the founders and live only in the environment. Set the caps in `lib/ai.py` to what they say. Never print, log or commit them.
4. **Tester data never enters a cloud agent session or the repo.** It lives only on the pilot server. Agents see aggregates: counts, timings, pass or fail.

## Where we are

- Q8 is the recommended pipeline (`docs/research/2026-11-09-current-state.md`). Its gain over H0 on real held-out searches is inside the noise band on every set (`results/r8-final.md`, `results/r9-final.md`).
- Exact-post finding is the weak spot: 30% on 11 real exact-post searches, 45% on 216 real YouTube searches, named creators 40% (`results/r9-scorecard.md`).
- The information audit puts 70% of the lost score on `dev` and 41% on `known_dev` on information that is present but unused (`docs/research/2026-11-09-information-audit.md`).
- Everything was measured on one library. No one but its owner has used the system. No product code exists on any branch.
- The held-out sets are not touched in this brief. Each keeps its 2 remaining scorings.

## Rules that hold throughout

- `AGENTS.md` rules 7, 8 and 9 apply to the pilot exactly as to product code.
- **Nothing is fetched from instagram.com or its CDN.** oEmbed output is never stored. A YouTube item may be enriched only through the YouTube Data API, with `refresh_by` set to 30 days.
- **Friends' posts never reach a model or an MCP response.** The importer refuses an Instagram export that lacks the followers and following files.
- **No outsider's file is accepted before Gate 0 passes.**
- **Testers** are adults living in the US. Each signs the consent note. Their data is deleted 30 days after the pilot ends unless they ask to stay.
- **Logs** hold IDs, timestamps and tool names. Search text is kept only for testers who tick the second consent box.
- **MCP tools are read-only.** Third-party text (captions, titles) is returned in a marked field with a length cap.
- **Nothing personal in git:** no task texts, no tester names, no webhook payload bodies. Fixtures are synthetic. Results files hold aggregates only, as in `eval/PROTOCOL.md`.
- All pilot code is prototype code under `experiments/pilot/`. It is not product code and is rewritten after a Go.

## Phase 1 (10 to 23 November): a reason to exist

| # | Item | Who | Pass or fail |
| --- | --- | --- | --- |
| 1 | **Head-to-head against Muse and Gemini**, on Derrick's library and the founders' own accounts only. Freeze 20 tasks before running anything: 14 on one platform, 6 that need both. Eason grades with the system names hidden. Confirm first that Gemini's YouTube History access is on. | Founder (both). Agent: a blind grading sheet. | Pass: the demo beats the incumbent on 8 of the 14. If not, single-platform search is not the promise: say so on the demand page and let item 2 decide. The 6 cross-platform tasks show what the promise can honestly claim. |
| 2 | **Demand page.** One page with the paid promise and the $8 price, posted in three or four places where the first segment gathers. The sign-up asks what the person would ask first, and asks them to request both exports now. | Agent: page text and static page. Founder (Eason): publishes and posts. | Pass: 15 sign-ups from the first 100 visits, and 10 people who request their exports. Fail: rewrite the promise once. A second fail means stop, or pick one vertical job. |
| 3 | **Decide.** A-001 to A-008; the transcript rule (rule 8) against "what is said" descriptions; the advertiser-access idea; desktop scope; the embedding model named in `02-tech-stack.md`; whether to form a company now. | Founder (both) | Pass: nothing the pilot depends on is left Proposed. |
| 4 | **DM-share payloads.** Publish the Meta app (Live needs no review). Share 10 reels and 10 posts from the founders' own role accounts. | Founder (Eason). Agent: the receiver and a sanitiser that keeps field names and presence counts only. | Pass: 18 of 20 carry caption text and a stable ID. Fail: live Instagram capture means a link plus the user's note. Either way, decide A-002 on this evidence. |
| 5 | **Pilot stack** (see spec below). | Agent (Derrick reviews) | Pass: connects from Claude and from ChatGPT; scores within 0.03 mrr2 of Q8 on `known_dev`; one server holds 12 synthetic libraries. Fail: move the tester dates, not the checks. |

**Gate A, 23 November:** items 1 and 2. Item 2 is the stop signal. Item 1 decides what the page may promise.

### Item 5: pilot stack spec

- **Reuse** the engine and importers in `experiments/demo/` and `experiments/youtube/`. Put new code in `experiments/pilot/`.
- **Core only:** one embedding model (text-embedding-3-large, 1,024 d, int8), BM25, rank fusion, the te field on Instagram items. No platform prior and no LLM rerank on the default path.
- **Server-side rewrite** (`qr-v1`) stays behind an `expand` flag, off by default. Item 7 decides whether it stays.
- **Filters as first-class inputs:** platform, behaviour (saved, liked, watched, shared), creator, date range.
- **MCP tools, all read-only:** `search_library`, `find_similar`, `list_by_creator`, `list_recent`, `get_item`. Each result carries id, URL, platform, creator, date, behaviour and a capped, marked snippet. Results are paged and in a fixed order. Tool descriptions are prompts: version them.
- **Access:** revocable and per user. The founders choose between OAuth and an unguessable per-user URL in item 3; the data policy names the choice and its risk.
- **Isolation:** one library per user, loaded on demand and dropped when idle.
- **Delete:** one command removes a user's items, vectors, te rows, caches and logs. A count test proves it.
- **Logging:** a pseudonymous user ID, timestamp, tool name, result count and opened item IDs.
- **Regression check:** a fresh evaluator scores the pilot core and Q8 on `known_dev` (381 searches, mrr2). No AI judging is needed.

## Phase 2 (24 November to 7 December): ready, then ten people in

| # | Item | Who | Pass or fail |
| --- | --- | --- | --- |
| 6 | **Exact-post fixes.** Use the filters; add creator and exact-phrase matching in the query. Code only, no LLM. | Agent (Derrick reviews) | Pass: named-creator searches "work" 70% of the time on the `known_dev` creator subset (0.42 today; metric as in `results/r9-scorecard.md` row 4), with no loss beyond 0.03 mrr2 on `known_dev` and `ig_known_dev`. A fresh evaluator scores it. |
| 7 | **Second library.** Eason's Instagram export and Takeout through the pilot stack with no hand edits. He runs 20 tasks of his own through his agent twice: `expand` off, then on. | Founder (Eason). Agent: fixes what the import breaks. | Pass: 95% of export records become items; 16 of 20 tasks succeed (the Gate 1 bar in `docs/09`). Keep `expand` off unless it wins by 3 tasks. Fail: fix the importer before item 9. |
| 8 | **Gate 0: data readiness.** All of: (a) one user's access returns nothing of another's on every route and tool; (b) delete removes everything, proved by counts; (c) raw zips are not kept; (d) both API keys sit on billed projects, with the providers' data-use and retention terms recorded in `07-privacy-and-safety.md` and dated; (e) no friend caption reaches a model call or an MCP response, tested on a synthetic export with mutual follows; (f) the data policy and the three-box consent note exist and match what the code does. | Agent: tests (a), (b), (c), (e) and drafts for (f). Founder: (d) and approval of (f). | Pass: every check passes. Fail: no outsider's file is accepted. |
| 9 | **Onboard ten outsiders.** At least five from the sign-up page; five on a call, five from an emailed link. Before seeing any result, each names five items they remember saving or watching. | Founder (Eason) | Pass: 6 of 10 upload and are searchable by 7 December; 5 of 10 connect their own agent within 7 days of upload; 60% of the named items are found in the top 5. Record each export wait. Below 4 of 10 searchable, export upload is not an on-ramp. |

**Gate B, 7 December:** items 7, 8 and 9.

**What testers are asked for.** Instagram export: saved, likes and connections. Messages are left out, so DM shares do not reach the library. Google Takeout: YouTube only, with My Activity. They should download each file when its email arrives, because the links expire within days.

**The consent note has three boxes:** (1) run the service; (2) keep my search texts to improve search; (3) let a founder look at my library with me on a call. Box 1 alone is enough to take part.

## Phase 3 (8 December to 4 January): do they return and pay

| # | Item | Who | Pass or fail |
| --- | --- | --- | --- |
| 10 | **Use, hands off.** Days 8 to 21 after each tester's upload. No check-ins in the window; one exit interview after it. Count sessions, not tool calls: calls less than 30 minutes apart are one session. Report agent-originated and search-box use separately. | Founder (both). Agent: the aggregate report. | Pass: 4 of 10 start 3 or more sessions in each week, at least 3 of them through their own agent. |
| 11 | **Payment.** A real charge of $8 for the first month, asked after the window closes. Hosted checkout, one-page terms, one-click cancellation. | Founder (Eason) | Pass: 3 of 10 pay, at least 2 of them people neither founder knew before. |
| 12 | *Optional.* First report v0: top themes, and what is rising or fading. | Agent | A reading, not a gate: do testers recognise 4 of their 5 themes (the Gate 1 bar)? |
| 13 | *Optional.* Share-sheet capture with a note. An Instagram share stores the link and the note. A YouTube share adds the title through the Data API. | Agent | Pass: a later search on the note or title finds the item in the top 5. Build only after item 4 has reported. |

**Gate C, 4 January:** items 10 and 11.

| Use (item 10) | Payment (item 11) | Decision |
| --- | --- | --- |
| Pass | Pass | Go. It earns the next six weeks: 50 users, a Claude directory listing, the product skeleton (M0), Meta App Review. |
| Pass | Fail | Re-price or narrow. Three more weeks with ten new strangers at another price; stop unless 2 pay. |
| Fail | Pass | Goodwill payments. Narrow to the job the payers used, or stop. |
| Fail | Fail | Stop. |

With ten people these marks give direction, not proof. A mark made or missed by one person is a tie, and a tie earns one two-week extension of the same test.

**If time runs short,** drop items 13 and 12, then onboard all ten from an emailed link. Gate 0 is never cut.

## What this brief stops

- New search arms, judges and rounds. Ranking changes other than item 6 wait for the decision.
- Adopting anything on AI grades or synthetic searches. The judge-free sets stay as the regression check.
- Cost-per-search and vector-storage tuning, and tuning for a desktop app.
- Whole-library media passes.
- The rules-and-actions engine, the hub, and the product skeleton, until a Go.

## Open decisions for the founders (item 3)

1. A-008: run a pilot on prototype code before the platform, with agent access first.
2. A-001 to A-007: accept, reject or defer each. The pilot depends on A-003 (te on Instagram items), A-004 (YouTube items) and the tool surface in A-006.
3. Rule 8 against "what is said" descriptions.
4. The advertiser-access idea: drop it in writing, or say why not.
5. Access to the MCP server: OAuth, or an unguessable per-user URL for ten testers.
6. Form a company now? Meta's Business Verification and App Review appear to need one.
7. The hours each founder can give a week through December. The dates assume about 20 each.
8. Whether the "Muse" in the earlier briefs is Meta's Muse. Item 1 assumes it is.
9. Every pass mark above except the two Gate 1 bars (16 of 20; 4 of 5 themes). Agree them before the first result arrives.

## Deliverables

- `experiments/pilot/`: the stack, its tests, the demand page, the DM receiver and sanitiser.
- `results/r10-head-to-head.md`, `r10-demand-page.md`, `r10-dm-payload.md`: counts only.
- `results/r10-pilot-stack.md` and `r10-exact-post.md`: the two regression checks, by a fresh evaluator.
- `results/r10-second-library.md`, `r10-gate0.md`, `r10-onboarding.md`, `r10-use.md`, `r10-payment.md`: aggregates only.
- Drafts for the founders to approve: a one-page data policy and the consent note.
- A **founders' summary at the top of `STATE.md`** at each gate: what passed, what failed, what needs their decision.

Commit and push after each item. Personal data stays out of git.

## Budget

- API: te and embeddings for up to 12 libraries, plus the two regression checks: at most $40.
- Hosting through 4 January: about $50. Domain: about $15.
- **Total cap: $105** (or what the founders say, if lower). Stop and report at the cap.
- Founder time: about 20 working days in all, 18.5 of them in the first four weeks.
