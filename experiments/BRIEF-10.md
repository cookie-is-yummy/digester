# Brief, round 10 (DRAFT): pilot before platform. Ten outside testers and a payment decision by 4 January

> **Status: DRAFT, not binding.** Written by the agent on 10 Nov 2026 from the outside review "Scroll Digest: outside review and 8-week plan" (a private doc; ask Derrick for the link). It becomes binding only when both founders accept it **and** amendment A-008 in `docs/amendments.md`.
>
> **Until then,** an agent may build and test Phase 1 code on this branch, locally and on synthetic data only: no deployment to a public address, no Meta app, no sign-up form, and no real library other than the existing `data/all/`.

This is not a search-research round. There are no new arms, no new judges and no adoption rule. The roles, the `lib/ai.py` ledger and the privacy rules are the same as in `BRIEF.md` and `BRIEF-8.md`: the agent that evaluates never builds, builders never open `data/all/evals/labels/` or `eval_work/`, and nothing under `data/` goes into git.

**The question for this round is not "is the search better" but "does anyone want this".** Will ten people who are not founders import their history, connect their own AI agent, come back, and pay? And is there a reason to use it beside Meta's Muse and Google's Gemini?

## Who does what

Every item has an **owner**, a founder, as in the review. The agent builds code, tests, page text and reports for that owner. Only a founder may:

- publish anything outside the repo (a page, a post, a Meta app), or deploy anything to a public address (the pilot server, the webhook receiver, the demand page);
- spend money, or open an account with a provider;
- contact, recruit or onboard a person, accept a file from one, or show a tester anything;
- run tasks on a personal Muse, Gemini, Claude or ChatGPT account;
- take money;
- accept or reject an amendment.

An agent that reaches one of these stops, writes what is ready into `STATE.md`, and waits. Do not work unattended past a gate.

## Setup

1. **Decisions first (item 3).** Nothing that touches an outsider starts until the founders have ruled on everything the pilot depends on (see "Open decisions"), and the outcome is in `docs/10-decisions.md`.
2. **Data for regression checks.** Same as round 9: keep `data/all/` or rebuild it as in `BRIEF-8.md` setup step 1. Check that `r8.5/q8` (Q8) reproduces on `known_dev` before anything else.
3. **A deadline inside this round.** The YouTube Data API reference text (`data/yt/ref`, `data/all/yt_ref`) must be deleted by 29 November 2026 (`docs/research/2026-11-09-current-state.md` section 1.4). A founder confirms it is gone from every copy and records that in `STATE.md`.
4. **Keys** come from the founders and live only in the environment. Never print, log or commit them.
5. **The founders' store.** Task texts, sign-ups, tester records and consent records live in one place that only the founders can open, outside git and outside every cloud agent session. The founders name it in item 3.
6. **Tester data, and any new founder data, never enters a cloud agent session or the repo.** It lives only on the pilot server, and agents hold no credentials for it. Aggregates (counts, timings, pass or fail) come from scripts that a founder runs on the server; the founder pastes the output. Eason's export in item 7 is treated like a tester's: the agent sees file names, field names, counts and error classes, never content.

## Where we are

- Q8 is the recommended pipeline (`docs/research/2026-11-09-current-state.md`). Its gain over H0 on real held-out searches is inside the noise band on every set (`results/r8-final.md`, `results/r9-final.md`).
- Exact-post finding is the weak spot: 30% on 11 real exact-post searches, 45% on 216 real YouTube searches, named creators 40% (`results/r9-scorecard.md`, `results/r9-final.md`).
- The information audit puts 70% of the lost score on `dev` and 41% on `known_dev` on information that is present but unused (`docs/research/2026-11-09-information-audit.md`).
- Everything was measured on one library. No record shows anyone but its owner using the system. No product code exists on any branch.
- The held-out sets are not touched in this brief. Each keeps its 2 remaining scorings.

## Rules that hold throughout

- **`AGENTS.md`.** Rules 2 and 5 to 11 apply to the pilot exactly as to product code: every derived row and vector records `processor_version` and `embedding_model`, and every AI call goes through the `lib/ai.py` ledger. Rules 1, 3 and 4 are set aside for `experiments/pilot/` only, as A-008 records.
- **Nothing is fetched from instagram.com or its CDN.** oEmbed output is never stored.
- **YouTube Data API.** If it is used at all (item 13), each stored field carries `refresh_by` (30 days) and a daily job refreshes or deletes it. A tester's API-derived data is deleted within 7 days of their leaving. The data policy says the service uses YouTube API Services and links the YouTube Terms of Service and Google's privacy policy. What the terms allow is recorded in `04-intake.md` before the first call on tester data.
- **Friends' posts never reach a model or an MCP response.** The importer refuses an Instagram export that lacks the followers and following files.
- **Sensitive items.** `07-privacy-and-safety.md` hides health, relationships and money items from agents unless the user opts in. The pilot has no tagger, so a tester's MCP access is switched on only if they tick that opt-in in the consent note. Without it they use the search box only.
- **No outsider's file is accepted before Gate 0 passes.** The demand page collects only what item 2 lists.
- **Testers** are adults living in the US. No gifts or payment for taking part. Their data is deleted 30 days after the pilot ends unless they ask to stay.
- **Logs and caches.** Logs hold a pseudonymous user ID, timestamp, tool name, route and item IDs. Search text is kept only for testers who tick consent box 2, and no agent uses it in this round. The reused engine writes search text to disk in two places (the query-vector stores and the rewrite cache); see the item 5 spec.
- **MCP tools are read-only.** By default a result carries IDs, the title and the user's own note. Longer third-party text (captions, descriptions) comes only from `get_item`, in a marked field with a length cap. When a tester connects, the page says that whatever the tools return is then held by their assistant provider under that provider's terms.
- **Nothing personal in git:** no task texts, no tester names, no sign-ups, no webhook payload bodies. Fixtures are synthetic. Results files hold aggregates only, as in `eval/PROTOCOL.md`. Tasks are frozen by committing the SHA-256 of the task file, not the file.
- **Consent record,** one per tester, kept in the founders' store: pseudonymous user ID, consent-note version, which boxes are ticked, the timestamp, the 18-or-over and US confirmations, where the tester came from, and whether either founder knew them before 10 November.
- **If something goes wrong** (tester data exposed, a key leaked): a founder takes the server offline, rotates the keys, tells the affected testers within 72 hours, and records what happened in `STATE.md` without personal details.
- All pilot code is prototype code under `experiments/pilot/`. It is rewritten after a Go.

## Phase 1 (10 to 23 November): a reason to exist

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 1 | **Head-to-head against Muse and Gemini**, on Derrick's library and the founders' own accounts only. Freeze 20 tasks before running anything: 14 on one platform, 6 that need both. Eason grades with the system names hidden. Check first that Gemini's YouTube History access is switched on. | Both | Make a blind grading sheet. Task texts and answers stay in the founders' store. | Pass: the demo beats the incumbent on 8 of the 14. If not, single-platform search is not the promise: say so on the demand page and let item 2 decide. The 6 cross-platform tasks show what the promise can honestly claim. |
| 2 | **Demand page.** One page with the paid promise and the $8 price, posted in three or four places where the first segment gathers, named by the middle of week 1. The sign-up asks only for an email, what the person would ask first, and two ticks (18 or over; living in the US). It asks people to request both exports now. A notice above the form says who holds the answers, for what, and that they are deleted on request or 30 days after the pilot. Keep the page open until about 50 people have signed up: about one in five follows through. | Eason | Write the page text, the notice and a static page. Sign-ups go to a form service Eason chooses and then to the founders' store. The agent sees counts. Visits are counted without cookies. | Pass: 15 sign-ups from the first 100 visits, and 10 people who request their exports. Fail: rewrite the promise once. A second fail means stop, or pick one vertical job. |
| 3 | **Decide.** See "Open decisions". | Both | Nothing. | Pass: nothing the pilot depends on is left Proposed or open. |
| 4 | **DM-share payloads.** Before the app goes Live, Eason posts a short privacy note for the receiver at a public URL (Meta appears to require one: check its current page). Then publish the Meta app (Live needs no App Review) and share 10 reels and 10 posts from the founders' own role accounts, never a tester's. | Eason | Write the receiver and the sanitiser. The receiver checks Meta's signature, drops every message text field in memory before any write (rule 8), keeps raw bodies only on the receiving machine, deletes them once the summary of field names and presence counts is written, and is switched off when item 4 reports. | Pass: 18 of 20 carry caption text and a stable ID. Fail: live Instagram capture means a link plus the user's note. Either way, record in `04-intake.md` what a share delivers and that webhook data is Meta Platform Data, and correct its "development mode works" line. |
| 5 | **Pilot stack** (spec below). Weeks 1 to 3: it runs into Phase 2 and is due on 27 November. Item 7 starts when it passes. | Derrick | Build and test it. After acceptance a founder provides the host, the domain and the keys; the agent deploys. | Pass: all four marks in the spec. Fail: move the tester dates and Gate C together, not the checks. |

**Gate A, 23 November:** items 1 and 2. 15 of the first 100 visitors sign up and 10 request their exports. Item 2 is the stop signal. Item 1 decides what the page may promise.

### Item 5: pilot stack spec

- **Reuse** the engine and importers in `experiments/demo/` and `experiments/youtube/`. Put new code in `experiments/pilot/`. Do not expose the demo's `app.py`: it is local, single-user and holds keys in the page.
- **Core:** text-embedding-3-large (1,024 d, int8) for items and searches, BM25, rank fusion, and filters. No platform prior and no LLM rerank. Build the index without `PlatformPrior`, so that no library needs `r7/router.npz`.
- **te is off unless the founders switch it on** (open decision 10). With te off the pilot uses one embedding model and one provider. With te on it also needs text-embedding-3-small (512 d) and gemini-3.1-flash-lite at import, and Google becomes a processor in the data policy.
- **Server-side rewrite** (`qr-v1`) stays behind an `expand` flag, off by default. Item 7 decides whether it stays.
- **Filters as first-class inputs:** platform, behaviour (saved, liked, watched, shared), creator, date range.
- **MCP tools, all read-only:** `search_library`, `find_similar`, `list_by_creator`, `list_recent`, `get_item`. A result carries id, URL, platform, creator, date, behaviour, the title and the user's own note. Results are paged and in a fixed order. Tool descriptions are prompts: version them.
- **Tester web surface, the minimum:** sign-in by the chosen access method; upload of the two zips, read in place and deleted when the import ends; import status and counts; a search box over the same core; the page that connects an agent; a delete button that runs the delete command.
- **Access:** revocable and per user. The founders choose between OAuth and an unguessable per-user URL (open decision 5). The data policy names the choice and its risk.
- **Isolation:** one library per user. The round-8 modules read `$DIGESTER_DATA` at import, so run one worker process per loaded library, or change the loaders to take a path.
- **Logging and caches:** user ID, timestamp, tool name, route (`mcp` or `web`), result count, and the item IDs asked for through `get_item`. For a tester without consent box 2, the query-vector stores and the rewrite cache are keyed by a salted hash or kept in memory only.
- **Delete:** one command removes a user's items, vectors, te rows, query stores, caches, logs and `ai_runs.jsonl`.

**The four pass marks.**

1. **It connects.** A founder connects the deployed server from a founder's Claude account and a founder's ChatGPT account, runs one search in each, and records pass or fail.
2. **It still searches as well.** The builder writes run files for the pilot core, three repeats, to `data/all/runs/r10/`. A fresh evaluator scores them with `experiments/eval/score_c4.py`. Two readings: (a) parity: the pilot core scores within 0.005 mrr2 of the prototype engine run with the same settings on `known_dev`; (b) the cost of the cuts: the CI lower bound of pilot core minus Q8 is above −0.03 mrr2 on `known_dev` (381). The same difference on `ig_known_dev` (150) is reported, not gated, because that set is synthetic; a loss there beyond 0.05 goes to the founders before item 9. No AI judging and no pooling.
3. **It holds ten people.** 12 synthetic libraries of 20,000 items each run on the one server, and the first screen arrives within 1 s at p95 with `expand` off.
4. **It forgets.** One test proves that no file under a no-box-2 library holds a search string. Another proves by counts that the delete command leaves nothing.

## Phase 2 (24 November to 7 December): ready, then ten people in

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 6 | **Exact-post fixes.** Use the filters; add creator and exact-phrase matching in the query. Code only, no LLM. | Derrick | Build it. A fresh evaluator scores it. | Pass: named-creator searches "work" 70% of the time on the `known_dev` creator subset (0.42 today, n 46; metric as in `results/r9-scorecard.md` row 4), and the change is non-inferior on `known_dev` and `ig_known_dev` (point at or above −0.005 mrr2, CI lower bound at or above −0.03). The held-out figure of 0.40 is not touched. |
| 7 | **Second library.** Eason's Instagram export and Takeout through the pilot stack with no hand edits. He runs 20 tasks of his own through his agent twice, `expand` off and on, in shuffled order. | Eason | Fix what the import breaks, working from `import_stats` only. | Pass: of the export records that carry a post or video URL and are not ads, 95% end as an item or as a counted exclusion (a friend's post, a repeat watch). 16 of 20 tasks succeed, the Gate 1 bar in `docs/09`; a task succeeds when the item he wanted is in the top 5, recorded before the next task. Keep `expand` off unless it wins by 3 tasks. Fail: fix the importer before item 9. |
| 8 | **Gate 0: data readiness.** Target 30 November. All of: (a) one user's access returns nothing of another's on every route and tool; (b) the delete test passes; (c) uploaded zips are gone when the import ends; (d) every API key sits on a billed project, the providers' data-use and retention terms are recorded and dated in `07-privacy-and-safety.md`, and no preview-only feature touches tester data; (e) no friend caption reaches a model call or an MCP response, tested on a synthetic export with mutual follows; (f) the data policy and the consent note exist and match what the code does; (g) the no-search-text test passes; (h) MCP access is off for a tester without the sensitive-items opt-in. | Both | Write the tests for (a), (b), (c), (e), (g), (h) and drafts for (f). A founder does (d) and approves (f). | Pass: every check passes. Fail: no outsider's file is accepted. |
| 9 | **Onboard ten outsiders,** 1 to 7 December. Ten people who already pay for Claude or ChatGPT, use Instagram or YouTube daily, and have a job in mind (a trip, a course, a swipe file of ideas). At least five from the sign-up page, because friends tend to be generous; five on a call, five from an emailed link. Each gets the data policy first, then the consent note. Before seeing any result, each names five items they remember saving or watching. | Eason | Nothing with testers. Fix bugs from counts and error classes. | Pass: 6 of 10 upload and are searchable by 7 December. 5 of 10 connect their own agent within 7 days of upload, read on 14 December. 60% of the named items are in the top 5 when the tester types one search per item into the search box and records the rank. Record each export wait. Below 4 of 10 searchable, export upload is not an on-ramp. |

**Gate B, 7 December:** items 7, 8 and 9. Gate 0 passed with no exceptions; 6 of 10 testers searchable; 5 of 10 connected (read on 14 December).

**Dates.** The last upload that counts is 7 December, so every use window closes by 28 December. Later uploads are reported, not counted. If item 5 or Gate 0 slips, every later date, Gate C included, moves by the same number of days.

**What testers are asked for.** Instagram export: JSON, all time, and only saved posts, likes, and followers and following. Messages and contacts are left out, so DM shares do not reach the library. Google Takeout: YouTube only, with the My Activity file filtered to YouTube. They download each file when its email arrives, because the links expire within days. The importer reads only the files listed in `04-intake.md`, plus the YouTube My Activity file.

**The data policy** names each model provider that is switched on as a processor, with how long it keeps inputs. It says what is stored and for how long, that whatever the tester's own assistant receives falls under that assistant's terms, and that agent query logs never feed themes or reports. A draft is linked from the demand page in week 1. The founders say in item 3 whether to get a legal read of it.

**The consent note has four boxes:** (1) run the service; (2) keep my search texts to improve search; (3) let a founder look at my library with me on a call; (4) let my own agent see every item, including ones about health, relationships or money. Box 1 alone is enough to take part.

## Phase 3 (8 December to 4 January): do they return and pay

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 10 | **Use, hands off.** Days 8 to 21 after each tester's upload. No check-ins in the window. One exit interview after it: what they tried first, what they found, why they stopped. | Both | Write `experiments/pilot/use_report.py`. A founder runs it on the server. | Pass: 4 of 10 testers each have 3 or more sessions in days 8 to 14 and again in days 15 to 21, and at least 3 of those testers have an MCP session in each of the two weeks. A session is a run of calls from one user ID with gaps under 30 minutes (the agent's proposal; fix it in item 3). An MCP session came through the `mcp` route. Founders' IDs are left out. |
| 11 | **Payment.** A real charge of $8 for one month of continued service from the day of payment, asked after the window closes. Hosted checkout in a founder's or the company's name, one-click cancellation. The terms say the service is a prototype, and that the payment is refunded in full within 7 days if Gate C ends in Stop or narrows to a job the payer did not use. | Eason | Draft the one-page terms; both founders approve them. The agent sees the number of payments and refunds. | Pass: 3 of 10 pay, at least 2 of them testers whose consent record says neither founder knew them before 10 November. |
| 12 | *Optional.* First report v0: top themes, and what is rising or fading. Agent query logs never feed it. | Derrick | Build it. A founder shows it. | A reading, not a gate: do testers recognise 4 of their 5 themes (the Gate 1 bar)? |
| 13 | *Optional.* Share-sheet capture with a note. An Instagram share stores the link and the note. A YouTube share adds the title through the Data API, under the rule above. | Eason | Build it. A founder gives it to testers. | Pass: a later search on the note or title finds the item in the top 5. |

**Gate C, 4 January:** items 10 and 11. 4 of 10 return in both weeks; 3 of 10 pay $8.

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
- Whole-library media passes, and any promise to find what was said or shown.
- The rules-and-actions engine, the hub, and the product skeleton, until a Go.
- New amendments from the research loop. Decide the open ones first.
- The advertiser-access idea. It gives away the one position Meta cannot copy.

## Open decisions for the founders (item 3)

1. A-008: run a pilot on prototype code before the platform, with agent access first. Both founders, in their own words: why, or why not.
2. A-001 to A-007: accept, reject or defer each. The pilot depends on A-004 (YouTube items) and the tool surface in A-006.
3. Rule 8 against "what is said" descriptions.
4. The advertiser-access idea: drop it in writing.
5. Access to the MCP server: OAuth, or an unguessable per-user URL for ten testers.
6. Form a company now? Meta's Business Verification and App Review appear to need one, and the checkout needs a name.
7. The hours each founder can give a week through December, including Phase 3. The dates assume about 20 each.
8. Whether the "Muse" in the earlier briefs is Meta's Muse. Item 1 assumes it is.
9. Every pass mark above except the two Gate 1 bars (16 of 20; 4 of 5 themes), and the session gap. Agree them before the first result arrives.
10. te in the pilot: off (one model, OpenAI only) or on (a second model, and Google as a processor). The agent's suggestion: start with it off.
11. Where the founders' store is, who hosts the pilot server, and whether a lawyer reads the data policy and the payment terms.
12. Desktop scope, and the embedding model named in `02-tech-stack.md`: the docs still say bge-small.

## Deliverables

- `experiments/pilot/`: the stack, its tests, the demand page, the DM receiver and sanitiser, `use_report.py`.
- `results/r10-head-to-head.md`, `r10-demand-page.md`, `r10-dm-payload.md`: counts only.
- `results/r10-pilot-stack.md` and `r10-exact-post.md`: the regression checks, by a fresh evaluator.
- `results/r10-second-library.md`, `r10-gate0.md`, `r10-onboarding.md`, `r10-use.md`, `r10-payment.md`: aggregates only, from output a founder pastes.
- Drafts for the founders to approve: the data policy, the consent note, the receiver's privacy note, the payment terms.
- A **founders' summary at the top of `STATE.md`** at each gate: what passed, what failed, what needs their decision.

Commit and push after each item. Personal data stays out of git.

## Budget

- **Caps are enforced in code.** One pilot-wide ledger adds up every library's `ai_runs.jsonl`. API cap: $40 across all libraries and $3 per library. If te is on, it may use at most $2 per library, through the Batch API where the wait allows, on saved, collection, shared and liked Instagram items, newest first. A library at its cap stays searchable.
- Hosting through 4 January: about $50. Domain: about $15. A founder pays and records the amounts in `STATE.md`.
- **Total cap: $105** (or what the founders say, if lower). Stop and report at the cap.
- **Founder time:** about 20 working days as the review counts them, with the founders building beside the agent; 18.5 of them fall in the first four weeks, which is tight. The more the agent builds, the less of that is founder time. Time for Phase 3 is agreed in item 3.
