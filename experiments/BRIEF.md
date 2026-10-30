# Brief: the search and enrichment loop

You are running an autonomous research loop on Scroll Digest's search and enrichment. Work unattended: don't stop to ask questions. Record each assumption in `STATE.md` and keep going. The founders read `LOG.md`, `STATE.md` and the final pull request.

## Goal

Find everything Muse could find in a person's saved and shared media: what's **said, shown and played**, not just what's captioned. Do it much faster and cheaper. The design must:

- run the first report in the cloud and later processing **locally on a desktop app** (a small local embedding model);
- extend beyond Instagram reels to YouTube, posts, articles and podcasts;
- fit the data we actually receive (see "What we have").

## Read first

1. `AGENTS.md`: the rules. Especially 1 (data contract), 5 (the processor reads), 7 (intake within platform terms), 8 (privacy), 9 (no real data in git) and 11 (log every AI call).
2. `docs/05-processor.md` (Tiers, Search, Query API), `docs/04-intake.md` (Enrichment), `docs/07-privacy-and-safety.md`, `docs/08-evals-and-quality.md`.
3. `docs/research/2026-10-30-search-storage.md` and `docs/research/2026-10-30-enrichment-cascade.md`: what has been measured so far.
4. `docs/amendments.md` A-001 and A-002: the proposed storage design and how media might be obtained.
5. `experiments/README.md`: code and data layout.

## What we have (and don't)

**From the Instagram export, per item:**
- caption and hashtags;
- creator handle and name, and whether the user follows them;
- media kind (reel or post);
- collections;
- the user's interactions with dates: save, like, collection, share to self, share to a friend (counts only, no names, no message text).

**Not in the export:**
- video, audio or thumbnails;
- comments;
- song names;
- view history.

1,091 items have no text at all. 26% fail the information gate.

**From a live DM share:** per Meta's docs, the webhook carries "the URL for the shared media or post". Whether that is a media file is unconfirmed (A-002).

**YouTube (later):**
- Takeout gives watch history, likes and playlists.
- The official Data API gives title, description, tags, thumbnails, duration and chapters (in the description).
- Captions only for videos the user owns.

**You may not fetch Instagram pages or Instagram CDN media.** No scraping and no third-party scrapers; A-002 is not accepted. Experiments needing images or audio for Instagram must say so, and stop at a design plus a cost estimate. Media experiments are allowed on YouTube through the official API (`YOUTUBE_API_KEY`, if set), or on any media the founders attach.

## The Muse export (if attached)

The founders may attach a Muse export: what Muse built its answers from. For each item that is likely the caption plus Muse's own video description ("MU"), and possibly more.

1. **Unzip it to `data/evals/labels/muse_export/`.** It is evaluator-side by default, because the answers in the eval set were found by matching words in this MU text.
2. **First step, done by an evaluator agent:** write `experiments/results/muse-export-inventory.md`. Cover the files and fields, the item count, how many match our corpus by shortcode, and whether it holds any media (thumbnails, frames, audio) or comments. Report counts and field names only, no content.
3. **Allowed uses:**
   - **Ceiling.** Append MU text to the search text and re-score. This gives an upper bound on what a perfect description pass could add, per search kind. It is inflated because the labels came from MU, so report it as a ceiling and never adopt it as a method.
   - **Reference.** The evaluator compares our own description pass against MU on a 200-item sample. Measure how many facets each covers (shown, said, audio, place, vibe…), and how often ours misses something MU has. Builders get only these aggregate rates.
   - **Media.** If the export contains media files, they may be used for image and audio experiments on those items, through `lib/ai.py`.
4. **Not allowed:** MU text as an input to any method that could be adopted, or to the query rewrite; builders reading MU text.

## Where things stand (30 Oct 2026, reproduced by the harness)

**Best method:**
1. AI query rewrite into phrases and keywords;
2. bge-small dense search over info-ok items, with Rocchio pseudo-relevance feedback from the top 5;
3. BM25 over the `full` text view;
4. reciprocal rank fusion.

**Scores:**

| Split | nDCG@10 | P@10 | success@5 | MRR | R@100 |
| --- | --- | --- | --- | --- | --- |
| Dev (16 searches) | 0.51 | 0.58 | 0.94 | 0.86 | 0.43 |
| All 22 | 0.49 | — | — | — | — |

- OpenAI 512d is about the same.
- Unjudged share of the top 10: about 20%.
- Query p50: 0.09 s.
- Cost: 0.

**Known weak spots:**
- audio: 0
- people/structure: 0.20
- task (weekend with friends)
- vibe
- more like this: 0.2–0.4
- recall@100 only 0.43, so most right answers never reach a reranker.
- 37% of right answers share no word with the search.
- Thin items are 7% findable.
- An item's caption quality does not predict whether it's missed (AUC 0.52–0.67). Misses depend on the aspect searched.

**Known biases to fix:**
- The query rewrites in `query_parses.json` were hand-simulated by an assistant that had read the answer reports. Replace them with a real, logged LLM rewrite, and report both.
- The answers came from Muse matching words in captions plus Muse's video descriptions. So search over captions only is capped, and word-matching methods are favoured.
- success@5 is near saturated. Judge by nDCG@10 and R@100, and look at the single-answer searches (hk_tailor, instant_pot, gun_trend) separately.

## Roles: who evaluates is never who builds

Run as an orchestrator that spawns subagents:

| Role | Does | Must not |
| --- | --- | --- |
| **Orchestrator** (you) | Plans; keeps `LOG.md` and `STATE.md`; picks the next experiment from aggregate reports; commits and pushes | Read or edit `data/evals/labels/`; judge items |
| **Researcher** (subagent) | Web research on one flaw; writes `experiments/research/<topic>.md` with sources, cost, local/desktop fit and a recommendation | Run evaluations |
| **Experimenter** (subagent, per experiment) | Implements one method in `experiments/methods/`, writes run files for **dev** queries to `data/runs/`, records cost and latency in the run's `meta` | Read `data/evals/labels/` or the Muse reports; read per-query or per-item scores; tune on test |
| **Evaluator** (a fresh subagent each round, spawned without the experimenter's context) | Runs `eval/score_run.py`. If `unjudged10` > 0.15 it pools the unjudged top-10 results and judges them blind with `eval/judge.py` (sheet → grade → merge), then re-scores. Writes the aggregate report to `experiments/results/`. Runs **test** only at milestones | Change method code; see method names while judging; report per-item labels to anyone |

**Rules:**
- **Preregister.** Before each experiment the experimenter adds a `LOG.md` row: hypothesis, the one variable changed, expected gain, expected cost.
- **Report everything.** The evaluator fills in the result. Failed and negative results stay in the log.
- **Adopt a change** only if dev nDCG@10 gains ≥ 0.03 with the paired 95% CI above 0, or ≥ 0.02 with more wins than losses and no extra cost. Cost and latency count: state the gain per dollar per 1,000 items.
- **The test split** is scored at most **3 times in total**, all reported. Never tune on it.
- **Judged pools grow the label set for everyone.** Re-score earlier finalists after merges, so comparisons use the same labels.
- **Separation is by protocol.** You share a filesystem. Don't game it; if a rule gets broken, say so in the log.

## Budget and keys

- Keys come from the environment only: `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `YOUTUBE_API_KEY` if set. Never print, log, commit or echo them. If one is missing, skip the experiments that need it and note it.
- **Every** paid call goes through `experiments/lib/ai.py`. It logs to `data/ai_runs.jsonl` and enforces a separate cap per provider:
  - `DIGESTER_OPENAI_BUDGET_USD` (founders set $18 of $20 credit);
  - `DIGESTER_GEMINI_BUDGET_USD` (founders set $18 of $20).
- Ledger costs are list-price estimates. Compare them with the billing pages when you can; if the gap is above 10%, lower your own pace.
- Before the first paid call, check current prices and model IDs on the providers' pricing and model pages. Fill in `lib/ai_prices.json` with the date. This includes Gemini Embedding 2's exact model ID and price.
- **How to spend.** Treat each $18 as the budget for the whole loop, not for one experiment.
  1. Pilot every paid method on 200 items first, to check output quality and the real cost per item.
  2. Then run a label-independent sample: the union of the baseline's top 200 for every dev query, plus 2,000 random items.
  3. Run the full corpus (about 21k items) only for finalists, at most about 3 full passes per provider.
  4. Use Batch APIs when you can wait; both providers discount them.
  5. Use the cheapest model that works; test a smaller one before a larger one.
  6. Compare providers on the same task where it matters: quality, cost per 1,000 items and latency.
  7. Stop paid work for a provider when less than $1.00 of its cap remains.
- **What Gemini is for here.**
  - Text passes, as an alternative to OpenAI.
  - Gemini Embedding 2 for text, and multimodal once media exists.
  - Images and audio only for media we may legitimately use: attachments from the founders, YouTube thumbnails through the official API, and media files inside the Muse export if it contains any. Never media fetched from Instagram.
- **Free and local:** bge-small, other small open embedders through fastembed or sentence-transformers on CPU, BM25 variants, and fusion settings.

## Phases

1. **Set up and reproduce.**
   - Unzip the attached data zips at the repo root; they hold a `data/` folder.
   - If the embeddings zip wasn't attached:
     - run `methods/build_embeddings.py` in the background (~50 min on CPU; it is resumable);
     - re-embed OpenAI 512d with `lib/ai.py` (~$0.04) only if needed.
   - Install dependencies.
   - Run the baseline and score it with a fresh evaluator. It must match the numbers above (±0.01). If not, stop and report.
   - Fill in `ai_prices.json`.
   - Make one tiny paid call per provider through `lib/ai.py` to confirm the keys, network and ledger work.
   - If the Muse export is attached: have the evaluator write the inventory, then run the MU **ceiling** (see "The Muse export"). The ceiling per search kind shows which facets are worth paying to fill, and that sets the order of phases 3–5.
2. **Benchmark the current system.** Measure:
   - Quality by search kind.
   - Indexing time per 1,000 items (CPU, and GPU if available).
   - Query latency.
   - Storage per item.
   - Cost per 1,000 items and per user.
   - Projected behaviour at 100k items per user and at 1,000 users.
   - Fit to the desktop app.

   Write `experiments/results/benchmark-baseline.md`.
3. **List flaws.** Rank them by expected gain × how many searches they hurt ÷ cost. Weigh:
   - cheap and scalable;
   - fits what the export and shares actually contain;
   - works locally;
   - user effort (prefer zero-effort; small confirmations are fine).
4. **Research each top flaw** (researcher subagents, in parallel). Starting points to check, not a fixed list:
   - a real LLM query rewrite and query-type routing;
   - a one-pass, content-aware text enrichment per item: one-sentence summary, facets, unknown facets, "questions this answers" (doc2query, contextual retrieval);
   - HyDE;
   - learned sparse retrieval (SPLADE-style) versus BM25;
   - newer small embedders that run locally (bge-base/m3, gte, nomic, EmbeddingGemma, arctic-embed);
   - late interaction (ColBERT-style) cost;
   - cheap LLM listwise reranking of the top 20–50;
   - interaction-weighted priors (self-shares, saves, collections);
   - creator and collection signals;
   - better "more like this";
   - the per-facet enrichment cascade from the cascade note;
   - multimodal options for later (Gemini Embedding 2, local SigLIP on YouTube thumbnails).
5. **Experiment.**
   - Change one variable at a time.
   - Free ideas before paid ones.
   - Evaluate after each one.
   - Keep going while experiments are still finding gains and budget remains.
6. **Converge and hand over.**
   - Pick the best pipeline overall: quality, cost, speed and local fit.
   - Have the evaluator score it on **test**.
   - Write `docs/research/<date>-search-loop.md`: what was tried, what won, numbers with CIs, cost per 1,000 items, and what still needs media.
   - Where the winner changes the docs, add a **Proposed** amendment in `docs/amendments.md`. Don't edit the docs it would change.
   - Open a **draft** pull request into `main` and don't merge it. Its description says which docs sections it touches and whether the contract changes.

## Housekeeping

- Commit and push after every experiment: code, `LOG.md`, `STATE.md` and aggregate results.
- **Never commit:**
  - anything under `data/`;
  - run files;
  - captions, item IDs, or query texts tied to answers;
  - keys.
- Scripts start with a `PROTOTYPE ONLY` docstring.
- Every batch job logs items processed, items per second and wall time.
- Keep `STATE.md` current: phase, done, next, open assumptions, budget left. A fresh session must be able to resume from it.
- Finish with a short summary in `STATE.md` and the pull request: the top three findings, the recommendation, money spent, and what the founders need to decide or provide.
