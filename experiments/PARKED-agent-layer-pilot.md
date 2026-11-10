# Parked spec: the agent-access pilot (first draft of the round-10 brief)

> **Status: PARKED on 10 Nov 2026. Not scheduled, not binding, and nothing here may be built.** This was the first draft of `BRIEF-10.md`, written from the outside review before the founder's notes reframed it. `BRIEF-10.md` now runs the product's loop by hand first. This spec is kept so the work is not lost. It has been corrected against `05-processor.md`, `03-data-contract.md` and the architecture review of 8 November.
>
> **To revive it:** the action test in `BRIEF-10.md` must end in a Go, and paying testers must ask for agent access. It then needs its own amendment (the conflict list is at the end of this file), new dates, and both founders' acceptance. Every date and gate below is from the first draft and is kept for reference only. Item numbers are this file's own, and "the pilot" means this parked pilot, not the test in `BRIEF-10.md`.

This is not a search-research round. There are no new arms, no new judges and no adoption rule. The roles, the `lib/ai.py` ledger and the privacy rules are the same as in `BRIEF.md` and `BRIEF-8.md`: the agent that evaluates never builds, builders never open `data/all/evals/labels/` or `eval_work/`, and nothing under `data/` goes into git.

**The question for this pilot is not "is the search better" but "does anyone want this".** Will ten people who are not founders import their history, connect their own AI agent, come back, and pay? And is there a reason to use it beside Meta's Muse and Google's Gemini?

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
3. **A deadline** (now tracked in `BRIEF-10.md`, setup step 5). The YouTube Data API reference text (`data/yt/ref`, `data/all/yt_ref`) must be deleted by 29 November 2026 (`docs/research/2026-11-09-current-state.md` section 1.4). A founder confirms it is gone from every copy and records that in `STATE.md`.
4. **Keys** come from the founders and live only in the environment. Never print, log or commit them.
5. **The founders' store.** Task texts, sign-ups, tester records and consent records live in one place that only the founders can open, outside git and outside every cloud agent session. The founders name it in item 3.
6. **Tester data, and any new founder data, never enters a cloud agent session or the repo.** It lives only on the pilot server, and agents hold no credentials for it. Aggregates (counts, timings, pass or fail) come from scripts that a founder runs on the server; the founder pastes the output. The second library in item 7 is treated like a tester's: the agent sees file names, field names, counts and error classes, never content.

## Where we are

- Q8 is the recommended pipeline (`docs/research/2026-11-09-current-state.md`). Its gain over H0 on real held-out searches is inside the noise band on every set (`results/r8-final.md`, `results/r9-final.md`).
- Exact-post finding is the weak spot: 30% on 11 real exact-post searches, 45% on 216 real YouTube searches, named creators 40% (`results/r9-scorecard.md`, `results/r9-final.md`).
- The information audit puts 70% of the lost score on `dev` and 41% on `known_dev` on information that is present but unused (`docs/research/2026-11-09-information-audit.md`).
- Everything was measured on one library. No record shows anyone but its owner using the system. No product code exists on any branch.
- The held-out sets are not touched in this brief. Each keeps its 2 remaining scorings.

## Rules that hold throughout

- **`AGENTS.md`.** Rules 2 and 5 to 11 apply to the pilot exactly as to product code: every derived row and vector records `processor_version` and `embedding_model`, and every AI call goes through the `lib/ai.py` ledger. Rules 1, 3 and 4 are set aside for `experiments/pilot/` only; the conflict list at the end of this file records it.
- **Nothing is fetched from instagram.com or its CDN.** oEmbed output is never stored.
- **YouTube Data API.** If it is used at all (item 13), each stored field carries `refresh_by` (30 days) and a daily job refreshes or deletes it. A tester's API-derived data is deleted within 7 days of their leaving. The data policy says the service uses YouTube API Services and links the YouTube Terms of Service and Google's privacy policy. What the terms allow is recorded in `04-intake.md` before the first call on tester data.
- **Friends' posts never reach a model or an MCP response.** The importer refuses an Instagram export that lacks the followers and following files.
- **Sensitive items.** `07-privacy-and-safety.md` hides health, relationships and money items from agents unless the user opts in. The pilot has no tagger, so a tester's MCP access is switched on only if they tick that opt-in in the consent note. Without it they use the search box only.
- **No outsider's file is accepted before Gate 0 passes.** The demand page collects only what item 2 lists.
- **Testers** are adults living in the US. No gifts or payment for taking part. Their data is deleted within 30 days of Gate C, or within 7 days if Gate C ends in Stop, unless they ask to stay.
- **Logs and caches.** Logs hold a pseudonymous user ID, timestamp, tool name, route and item IDs. Search text, and anything derived from it, is kept only for testers who tick consent box 2, and no agent uses it in this round. The reused engine writes both to disk (the query-vector stores and the rewrite cache); see the item 5 spec.
- **MCP tools are read-only.** By default a result carries IDs, the title and the user's own note. Longer third-party text (captions, descriptions) comes only from `get_items`, in a marked field with a length cap. When a tester connects, the page says that whatever the tools return is then held by their assistant provider under that provider's terms.
- **Nothing personal in git:** no task texts, no tester names, no sign-ups, no webhook payload bodies. Fixtures are synthetic. Results files hold aggregates only, as in `eval/PROTOCOL.md`. Tasks are frozen by committing the SHA-256 of the task file, not the file.
- **Consent record,** one per tester, kept in the founders' store: pseudonymous user ID, consent-note version, which boxes are ticked, the timestamp, the 18-or-over and US confirmations, where the tester came from, and whether either founder knew them before 10 November.
- **If something goes wrong** (tester data exposed, a key leaked): a founder takes the server offline, rotates the keys, tells the affected testers within 72 hours, and records what happened in `STATE.md` without personal details.
- All pilot code is prototype code under `experiments/pilot/`. It is rewritten after a Go.

## Phase 1 (10 to 23 November): a reason to exist

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 1 | **Head-to-head against Muse and Gemini**, on Derrick's library and the founders' own accounts only. Freeze 20 tasks before running anything: 14 on one platform, 6 that need both. Eason grades with the system names hidden. Check first that Gemini's YouTube History access is switched on. | Both | Make a blind grading sheet template. A founder runs the 20 tasks through the demo on his own machine, on a copy of the library outside every agent session. The agent never runs the tasks; task texts and answers stay in the founders' store. | Pass: the demo beats the incumbent on 8 of the 14. If not, single-platform search is not the promise: say so on the demand page and let item 2 decide. The 6 cross-platform tasks show what the promise can honestly claim. |
| 2 | **Demand page.** One page with the paid promise and the $8 price, posted in three or four places where the first segment gathers, named by the middle of week 1. The sign-up asks only for an email, what the person would ask first, and two ticks (18 or over; living in the US). It asks people to request both exports now. A notice above the form says who holds the answers, for what, and that they are deleted on request, or within 30 days of the pilot's decision. Keep the page open until about 50 people have signed up: about one in five follows through. | Eason | Write the page text, the notice and a static page. Sign-ups go to a form service Eason chooses and then to the founders' store. The agent sees counts. Visits are counted without cookies. | Pass: 15 sign-ups from the first 100 visits, and 10 people who request their exports, read on 17 November. Fail: rewrite the promise once and judge the new page on its own first 100 visits by 23 November. A second fail means stop, or pick one vertical job. |
| 3 | **Decide.** See "Open decisions". | Both | Nothing. | Pass: by 13 November nothing the pilot depends on is left Proposed or open. Item 2 is not posted before then. |
| 4 | **DM-share payloads.** Moved to `BRIEF-10.md`, item 9. | Eason | See there. | See there. |
| 5 | **Pilot stack** (spec below). Weeks 1 to 3: it runs into Phase 2 and is due on 27 November. Item 7 starts when it passes. | Derrick | Build and test it locally, and write the deploy and load-test scripts and a short runbook. After acceptance a founder provides the host, the domain and the keys, deploys, and runs pass marks 1 and 3 on the server. The agent holds no server credentials. | Pass: all four marks in the spec. Fail: move the tester dates and Gate C together, not the checks. |

**Gate A, 23 November:** items 1 and 2. 15 of the first 100 visitors sign up and 10 request their exports. Item 2 is the stop signal. Item 1 decides what the page may promise.

### Item 5: pilot stack spec

- **Reuse** the engine and importers in `experiments/demo/` and `experiments/youtube/`. Put new code in `experiments/pilot/`. Do not expose the demo's `app.py`: it is local, single-user and holds keys in the page.
- **Core:** text-embedding-3-large (1,024 d, int8) for items and searches, BM25, rank fusion, and filters. No platform prior and no LLM rerank. Build the index without `PlatformPrior`, so that no library needs `r7/router.npz`.
- **te is off unless the founders switch it on** (open decision 10). With te off the pilot uses one embedding model and one provider. With te on it also needs text-embedding-3-small (512 d) and gemini-3.1-flash-lite at import, and Google becomes a processor in the data policy.
- **Server-side rewrite** (`qr-v1`). MCP calls skip it unless the caller sets `expand`: the user's agent writes its own queries, as the architecture review of 8 November proposed. The tester's web search box keeps Q8's code router (`route-r1`), which sends only long searches to the rewrite. Item 7 decides whether `expand` stays.
- **Filters as first-class inputs,** with the query API's parameter names and the contract's values (`05-processor.md` › Query API; `03-data-contract.md`): `kinds` (`InteractionKind`: share, save, collection, like, comment, watch, view), `platforms` (`Platform`), `since` and `until`. A creator filter is the one new parameter.
- **MCP tools, all read-only, named after the query API's ops and using its envelope:** `search` (`query?`, `kinds?`, `platforms?`, `since?`, `until?`, `creator?`, `exclude_item_ids?`, `limit`), `similar` (`item_ids`, `limit`) and `get_items` (`ids`). Listing by creator or by date is `search` without a query. A request carries `budget` (`max_items`, `detail`); a response carries `data`, `evidence` and `meta` (`processor_version`, `took_ms`, `truncated`). A result carries id, URL, platform, creator, date, interaction kinds, the YouTube title (Instagram items have none) and the user's own note if there is one. The demo's result row also carries caption text and a summary: drop both from search results, and leave out `why_matched`, which quotes the caption. Captions come only from `get_items` (open decision 13). Results are paged and in a fixed order. Tool descriptions are prompts: version them. The agent sees search only: `list_themes`, `what_changed`, `direction` and `opportunities` are not in the pilot.
- **Tester web surface, the minimum:** sign-in by the chosen access method; upload of the two zips, read in place and deleted when the import ends; import status and counts; a search box over the same core; the page that connects an agent; a delete button that runs the delete command. The pilot has no export of a tester's data, so no page promises one.
- **Raw layer:** the import writes one raw record per export entry, append-only, and one upload row with counts and timings, as `03-data-contract.md` and `04-intake.md` (rule 5) require.
- **Access:** revocable and per user. The founders choose between OAuth and an unguessable per-user URL (open decision 5). The data policy names the choice and its risk.
- **Isolation:** one library per user, and one isolated worker process per loaded library. The round-8 modules read `$DIGESTER_DATA` at import, which is why each library gets its own process.
- **Logging and caches:** log rows take the contract's `events` shape (`type`, `subject`, `created_at`) and hold user ID, timestamp, tool name, route (`mcp` or `web`), result count, and the item IDs asked for through `get_items`. For a tester without consent box 2, nothing derived from a search is written to disk: query vectors and rewrite output (phrases, keywords, captions) stay in memory and go when the worker unloads. Searches travel in POST bodies, and access logs drop query strings and per-user URL tokens.
- **Delete:** one command removes a user's items, vectors, te rows, query stores, caches and logs. Their `ai_runs.jsonl` rows hold no content (provider, model, purpose, tokens, cost); they move to the pilot-wide ledger under a deleted-user marker, without `input_refs` and `output_refs`, so the caps and rule 11 still count them.

**The four pass marks.**

1. **It connects.** A founder connects the deployed server from a founder's Claude account and a founder's ChatGPT account, runs one search in each, and records pass or fail.
2. **It still searches as well.** The builder writes run files for the pilot core, three repeats, to `data/all/runs/r10/`. A fresh evaluator scores them with `experiments/eval/score_c4.py`. Two readings: (a) parity: with te and `expand` off, the pilot core scores within 0.005 mrr2 of `runs/r8.1/inst_r1` on `known_dev` (raw query, 3-large dense, BM25 and fusion; that run read float vectors, so a small int8 gap is expected); (b) the cost of the cuts: the CI lower bound of pilot core minus Q8 is above −0.03 mrr2 on `known_dev` (381). The same difference on `ig_known_dev` (150) is reported, not gated, because that set is synthetic: once on all 150 searches, and once on those with no word found only in the te text. A loss there beyond 0.05 goes to the founders before item 9. No AI judging and no pooling.
3. **It holds ten people.** A founder runs the load-test script on the server: 12 synthetic libraries, two of 140,000 items and ten of 20,000, one isolated worker per loaded library, with the first screen within 1 s at p95 and `expand` off. Record memory per worker.
4. **It forgets.** One test proves that, for a tester without box 2, no file on the server holds a search string or a rewrite output: not the library folder, the caches, the service's error log or the web server's access log. Another proves by counts that the delete command leaves nothing but the ledger rows.

## Phase 2 (24 November to 7 December): ready, then ten people in

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 6 | **Exact-post fixes.** Use the filters; add creator and exact-phrase matching in the query. Code only, no LLM. A platform filter applies only on an explicit `platforms` parameter or a platform word in the search, and a date filter only to a date written in the search. Nothing uses the time the search was made. Report results with and without a watched-or-liked filter. | Derrick | Build it. A fresh evaluator scores it. | Pass: named-creator searches "work" 70% of the time on the `known_dev` creator subset (0.42 today, n 46; metric as in `results/r9-scorecard.md` row 4), and the change is non-inferior on `known_dev` and `ig_known_dev` (point at or above −0.005 mrr2, CI lower bound at or above −0.03). The held-out figure of 0.40 is not touched. |
| 7 | **Second library.** A second person's Instagram export and Takeout, given with their consent, through the pilot stack with no hand edits. That person runs 20 tasks of their own through their agent twice, `expand` off and on, in shuffled order. | Eason | Fix what the import breaks, working from `import_stats` only. | Pass: of the export records that carry a post or video URL and are not ads, 95% end as an interaction on an item or as a counted exclusion (a friend's post, a received share), checked against the upload row's counts. 16 of 20 tasks succeed in the `expand`-off run, the Gate 1 bar in `docs/09`; a task succeeds when the wanted item is in the top 5, recorded before the next task. Keep `expand` off unless it wins by 3 tasks. Fail: fix the importer before item 9. |
| 8 | **Gate 0: data readiness.** Target 30 November. All of: (a) one user's access returns nothing of another's on every route and tool; (b) the delete test passes; (c) uploaded zips are gone when the import ends; (d) every API key sits on a billed project, the providers' data-use and retention terms are recorded and dated in `07-privacy-and-safety.md`, and no preview-only feature touches tester data; (e) no friend caption reaches a model call or an MCP response, tested on a synthetic export with mutual follows; (f) the data policy and the consent note exist and match what the code does; (g) the no-search-text test passes; (h) MCP access is off for a tester without the sensitive-items opt-in; (i) no message text from an export is written to any record, log or cache, tested on a synthetic export with message threads. | Both | Write the tests for (a), (b), (c), (e), (g), (h), (i) and drafts for (f). A founder does (d) and approves (f). | Pass: every check passes. Fail: no outsider's file is accepted. |
| 9 | **Onboard ten outsiders,** 1 to 7 December. Ten people who already pay for Claude or ChatGPT, use Instagram or YouTube daily, and have a job in mind (a trip, a course, a swipe file of ideas). At least five from the sign-up page, because friends tend to be generous; five on a call, five from an emailed link. Each gets the data policy first, then the consent note. Before seeing any result, each names five items they remember saving or watching. | Eason | Nothing with testers. Fix bugs from counts and error classes. | Pass: 6 of 10 upload and are searchable by 7 December. 5 of 10 connect their own agent within 7 days of upload, read on 14 December. 60% of the named items are in the top 5 when the tester types one search per item into the search box and records the rank. Record each export wait. Below 4 of 10 searchable, export upload is not an on-ramp. |

**Gate B, 7 December:** items 7, 8 and 9. Gate 0 passed with no exceptions. Item 7: 95% of export records counted and 16 of 20 tasks. Item 9: 6 of 10 testers searchable and 60% of the named items in the top 5. The connection mark (5 of 10 within 7 days of upload) is read on 14 December and does not hold up Phase 3.

**Dates.** The last upload that counts is 7 December, so every use window closes by 28 December. Later uploads are reported, not counted. If item 3, item 5 or Gate 0 slips, every later date, Gate C included, moves by the same number of days.

**Changes after Gate 0.** Once Gate 0 has passed, a change to the importer, the search path or the MCP tools goes live only after checks (a), (c), (e), (g), (h) and (i) are run again. Item 6 goes live only after it passes its own mark. Item 9's named-items mark is read on the engine as it stood when each tester uploaded.

**What testers are asked for.** Instagram export: JSON, all time, and only saved posts, likes, followers and following, and Messages if the tester agrees. `05-processor.md` calls self-sharing a separate saving habit that must not be missed, and in the first library self-shared items are about three times the saves. The importer reads only shared-post objects and per-thread counts, never message text (`04-intake.md`). A tester who leaves Messages out is recorded as such, and their DM shares do not reach the library. Contacts are always left out. Google Takeout: two products only, "YouTube and YouTube Music" (history as JSON, playlists, subscriptions) and "My Activity" with its filter set to YouTube. They download each file when its email arrives, because the links expire within days. The importer reads only the watch history, playlists, subscriptions and the YouTube My Activity file, and skips search records. Subscriptions and the My Activity file are added to `04-intake.md` before Gate 0.

**The data policy** names each model provider that is switched on as a processor, with how long it keeps inputs. It says what is stored and for how long, that whatever the tester's own assistant receives falls under that assistant's terms, and that agent query logs never feed themes or reports. A draft is linked from the demand page in week 1. The founders say in item 3 whether to get a legal read of it.

**The consent note has four boxes:** (1) run the service; (2) keep my search texts so that the founders can read what people look for; they stay on the pilot server and are deleted with the rest of my data; (3) let a founder look at my library with me on a call; (4) let my own agent see every item, including ones about health, relationships or money. Box 1 alone is enough to take part. Without box 4 a tester's agent is not connected, so they cannot count toward the connect mark in item 9 or the MCP clause in item 10: report at Gate B how many ticked it.

## Phase 3 (8 December to 4 January): do they return and pay

| # | Item | Owner | The agent may | Pass or fail |
| --- | --- | --- | --- | --- |
| 10 | **Use, hands off.** Days 8 to 21 after each tester's upload. No check-ins in the window. One exit interview after it: what they tried first, what they found, why they stopped. | Both | Write `experiments/pilot/use_report.py`. A founder runs it on the server. | Pass: 4 of 10 testers each have 3 or more sessions in days 8 to 14 and again in days 15 to 21, and at least 3 of those testers have an MCP session in each of the two weeks. A session is a run of calls from one user ID with gaps under 30 minutes, the contract's capture-session gap. Use sessions are computed from the log, not stored as `sessions` rows. An MCP session came through the `mcp` route. Founders' IDs are left out. |
| 11 | **Payment.** A real charge of $8 for one month of continued service from the day of payment, asked on the day after each tester's window closes (the last on 29 December). Payments made by 3 January count. Hosted checkout in a founder's or the company's name, one-click cancellation. The terms say the service is a prototype, and that the payment is refunded in full within 7 days of the decision if Gate C ends in Stop, and on request if it narrows to a job the payer did not use. | Eason | Draft the one-page terms; both founders approve them. The agent sees the number of payments and refunds. | Pass: 3 of 10 pay, at least 2 of them testers whose consent record says neither founder knew them before 10 November. |
| 12 | *Optional.* First report v0: top themes, and what is rising or fading. It needs the information gate, the filter model and the themes ported first (`05-processor.md`). Agent query logs never feed it. | Derrick | Build it. A founder shows it. | A reading, not a gate: do testers recognise 4 of their 5 themes (the Gate 1 bar)? Report how many themes formed. |
| 13 | *Optional.* Share-sheet capture with a note. An Instagram share stores the link and the note. The note is a `notes` row; adding notes to the embedded text is a contract change. A YouTube share adds the title through the Data API, under the rule above. | Eason | Build it. A founder gives it to testers. | Pass: a later search on the note or title finds the item in the top 5. |

**Gate C, 4 January:** items 10 and 11. 4 of 10 have 3 or more sessions in each week, at least 3 of them with an MCP session in each week. 3 of 10 pay $8, at least 2 of them testers neither founder knew before 10 November.

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

1. A new amendment for this pilot (its conflict list is at the end of this file): run it on prototype code before the platform, with agent access first. Both founders, in their own words: why, or why not.
2. A-001 to A-007: accept, reject or defer each. The pilot depends on A-004 (YouTube items) and the tool surface in A-006.
3. Short said-and-shown descriptions. Rule 8 is not the obstacle: summaries and moments are kept (`10-decisions.md`, 15 Oct). The open point is the platforms' terms: YouTube's derived-data clause, and Gemini's preview terms for video URLs.
4. The advertiser-access idea: drop it in writing.
5. Access to the MCP server: OAuth, or an unguessable per-user URL for ten testers.
6. Form a company now? Meta's Business Verification and App Review appear to need one, and the checkout needs a name.
7. The hours each founder can give a week through December, including Phase 3. The dates assume about 20 each.
8. Whether the "Muse" in the earlier briefs is Meta's Muse. Item 1 assumes it is.
9. Every pass mark above except the two Gate 1 bars (16 of 20; 4 of 5 themes), and the session gap. Agree them before the first result arrives.
10. te in the pilot: off (one model, OpenAI only) or on (a second model, and Google as a processor). The agent's suggestion: start with it off.
11. Where the founders' store is, who hosts the pilot server, and whether a lawyer reads the data policy and the payment terms.
12. Desktop scope, and the embedding model: `02-tech-stack.md` and `03-data-contract.md` pin bge-small at 384 dimensions (`vector(384)`), and the pilot uses text-embedding-3-large.
13. Search results for Instagram items carry no caption text by default. Allow a short marked snippet, or keep captions to `get_items` only?
14. The privacy design (a shared content store, a private per-user vault, a revocable key; A-006 item 6) is unwritten. Accept none for the pilot and say so in the data policy, or build it first.

## Deliverables

- `experiments/pilot/`: the stack, its tests, the deploy and load-test scripts and a runbook, the demand page, the DM receiver and sanitiser, `use_report.py`.
- `results/r10-head-to-head.md`, `r10-demand-page.md`, `r10-dm-payload.md`: counts only.
- `results/r10-pilot-stack.md` and `r10-exact-post.md`: the regression checks, by a fresh evaluator.
- `results/r10-second-library.md`, `r10-gate0.md`, `r10-onboarding.md`, `r10-use.md`, `r10-payment.md`: aggregates only, from output a founder pastes.
- Drafts for the founders to approve: the data policy, the consent note, the receiver's privacy note, the payment terms.
- A **founders' summary at the top of `STATE.md`** at each gate: what passed, what failed, what needs their decision.

Commit and push after each item. Personal data stays out of git.

## Budget

- **Caps are enforced in code.** One pilot-wide ledger adds up every library's `ai_runs.jsonl`. API cap: $40 across all libraries and $3 per library. If te is on, it may use at most $2 per library, through the Batch API where the wait allows, on saved, collection and shared Instagram items, newest first; liked items only if A-003 is accepted. Query embeddings for searches are exempt from the per-library cap and count only toward the pilot-wide one, so a library at its cap stays searchable. At the pilot-wide cap, new imports and te passes stop, searches continue, and a founder decides whether to raise it.
- Hosting through 4 January: about $50, and one more week if Gate C ends in Stop. Domain: about $15. A founder pays and records the amounts in `STATE.md`. A Go or a re-price brings its own budget.
- **Total cap: $105** (or what the founders say, if lower). Report at the cap.
- **Founder time:** about 20 working days as the review counts them, with the founders building beside the agent; 18.5 of them fall in the first four weeks, which is tight. The more the agent builds, the less of that is founder time. Time for Phase 3 is agreed in item 3.

## Conflicts to record if this is revived

The first draft of A-008 listed these. A-008 now covers the action test in `BRIEF-10.md`, so a revived pilot needs a new amendment that carries this list. The last four entries were added after the design-doc check of 10 November.

- `AGENTS.md` › What we are building: "Current focus: **the backend only.** The frontend (hub, onboarding screens) is deliberately deferred." The pilot needs a demand page, an upload step and a search box.
- `AGENTS.md` › Prototype code: "Port the ideas, not the files: prototype scripts are not product code." The pilot serves outsiders from the prototype engine.
- `AGENTS.md` rules 1 ("Do not invent fields ad hoc"), 3 ("All reads and writes go through `scrolldigest/db/`") and 4 ("must not branch on `platform` except through `platform_data`"). The pilot has no database layer, and if te is switched on it applies to Instagram items only.
- `00-vision.md` › Out of scope for now: "**MCP server.** Designed (`01-architecture.md`), built after the query API is stable." `09-roadmap-and-ownership.md` lists the MCP server under "Later" and testers at M5, after M0 to M4.
- `10-decisions.md` (28 Oct, Agreed): "Backend first; frontend deferred"; "Supabase for database, vectors, auth, storage and queues"; and (18 Oct) "One processing path for all platforms; only adapters differ".
- `09-roadmap-and-ownership.md` › Ownership: intake is Eason's. Where the agent builds importer fixes, Eason, not Derrick, should review them.
- `02-tech-stack.md`: embeddings "`fastembed` with `BAAI/bge-small-en-v1.5`"; auth "Supabase Auth (Google sign-in)" with row-level security; and under Later, "**MCP server:** Python MCP SDK in the same codebase, calling the query API in-process." The pilot uses text-embedding-3-large, its own per-user access, and no query API.
- `01-architecture.md`: "**MCP server**: exposes `get_profile`, `get_context(task)`, `search`, `list_themes`, `get_items`, `what_changed`, `list_actions`". The pilot exposes `search`, `similar` and `get_items` only.
- `07-privacy-and-safety.md` › Personal data: "**Sensitive categories** (health, relationships, money) are tagged on item cards and hidden from agents and digests unless the user opts in." The pilot has no tagger; it gates agent access on the opt-in instead. › Retention and deletion: "**Full export** of a user's data in open formats". The pilot has none.
- `04-intake.md` › YouTube lists only `history/watch-history.json` and `playlists/`; the pilot also reads `subscriptions/` and the My Activity file, against `07-privacy-and-safety.md` › Personal data: "**Minimum necessary.**"
- `05-processor.md` › Query API: `search` returns "`why_matched` (caption line or moment) and confidence"; the pilot leaves `why_matched` out by default. The API also offers `list_themes`, `what_changed`, `direction` and `opportunities`; the pilot's agent sees search only. › Performance targets: "`search` p95 ≤ 500 ms"; the pilot's mark is 1 s.
- `05-processor.md` and `02-tech-stack.md` choose a local embedder, so that search text never leaves the server. The pilot sends every search to a cloud embedding API.
- `03-data-contract.md`: `vector(384)` and the 384-dimension theme space; no table for search requests or tool calls; notes are not part of the embedded text. **Contract change: yes, if text-embedding-3-large is kept beyond the pilot.**
- The privacy design that the architecture review of 8 November proposed (a shared content store, a private per-user vault, a revocable key; A-006 item 6) is unwritten. The pilot would store tester libraries without it.
