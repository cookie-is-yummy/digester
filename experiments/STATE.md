# State

## Round 4 (`BRIEF-4.md`): one library, two platforms, as a loop

### Round 4.2 (evaluated 3 Nov 2026; `results/r4.2-eval.md`)

- **Finalist: C0 (unchanged)**, 0.483 [0.401, 0.565] on dev under label round c4-r2 (ig 0.506, yt 0.459). Nothing passed the adoption rule. **Best rival: D1** (two near misses, D1 and D4).
- **Labels:** c4-r2 = c4-r1 + 81 blind evaluator judgments (3/17/61) of every unjudged dev top-10 item from the 4.2 runs. Backup `evalset.pre_r4.2.jsonl`. `yt_holdout`: 2 scorings left. `test`: 3 left. Both untouched.
- **D1, coverage-fair fusion of the te lists:** 0.520.
  - vs C0: +0.037 [−0.002, +0.078], 29/8/7. The CI lower bound stays at −0.002 to −0.001 over 20 bootstrap seeds. Clause 2 fails on the te-pass cost.
  - ig +0.073 [+0.026, +0.131], 17/1/4; yt +0.001.
  - vs C1: +0.059 [+0.012, +0.110]; yt +0.107. The crowding is fixed.
  - The YouTube topic/task/structure te loss from round 3 remains (−0.05 to −0.09).
- **D4 = D1 + guarded intent:** 0.528.
  - vs C0: +0.045 [−0.001, +0.095], 29/9/6. A near miss for the same reasons.
  - vs D1: +0.008.
  - A guard flaw costs about 0.01. Dropping one flag of an ORed multi-flag `require` *narrows* the pool, which cost one Instagram search −0.45.
- **D3 (guarded qi-v3 on C0):** +0.004.
  - yt +0.025, 3/0/19. The guards removed every C3 loss.
  - ig −0.017, from the same flaw.
  - The watch-rule deviation (≥ 50% coverage instead of "any watch event") has no measurable effect.
- **D2 (te merged into thin items' own view):** +0.007 overall.
  - yt +0.025; yt-only projection +0.042 [+0.008, +0.087].
  - ig −0.010; ig-only projection −0.050. It gives up te on sufficient Instagram captions.
- **D1p (te ranks rescaled):** significantly worse than D1, −0.026 [−0.044, −0.008]. It overcorrects.
- **Spend, round 4 (ledger `data/all/ai_runs.jsonl`):** **$3.867** of $15.
  - Gemini $3.776 ($1.72 left of its cap); OpenAI $0.092 ($9.41 left).
  - Round 4.2: $0.016 building, $0 judging.
- **Stop rule: rounds adopting nothing in a row = 2.** One more round without an adoption ends the loop; then comes the Finish step: finalist, 4.1 baseline and best rival on `test` and `yt_holdout`.

**Agenda for round 4.3** (ranked by expected value per dollar; all $0 in API calls):

1. **D4′ = D1 + D3 with guards that only widen.**
   - If any flag of a multi-flag `require` fails its word check, drop the whole `require`.
   - Extend the share lexicon to sending (send / sent / DM'd).
   - Expected vs C0: +0.05 to +0.06; evaluator counterfactual +0.056 [+0.010, +0.105].
   - It is the arm most likely to clear clause 1. The fix was motivated by one dev search, so the finish splits are the real check.
2. **D1 with te eligibility limited to items whose own text is not a descriptive title** (caption-type or insufficient).
   - Set from an adapter field in `platform_data` (AGENTS rule 4).
   - It targets D1's YouTube topic/task/structure loss, while D2 shows te helps thin YouTube items.
   - Expected vs D1: yt +0.02 to +0.05, ig 0.
3. **Per-platform BM25 statistics** (idf and length normalisation per item group).
   - It targets C0's −0.025 Instagram ordering loss (ig-only projection).
   - Expected +0.00 to +0.02 on ig. Low expected value.

Not recommended: Gemini spend (YouTube te parity ≈ $10 against $1.72 left) or an LLM judge. Keep the OpenAI budget for the finish.

### Round 4.1 (evaluated 3 Nov 2026; `results/r4.1-eval.md`)

- **Finalist: C0**, the combined platform-blind baseline (A0/B3-without-enrichment recipe over all 136,908 items). It scores 0.483 [0.401, 0.565] on dev under label round c4-r1: ig 0.506, yt 0.459. Nothing passed the adoption rule.
- **Labels:** c4-r1 = +1,066 blind evaluator judgments of every unjudged dev top-10 item, cross-platform items included (77/242/747). Backup `evalset.pre_r4.1.jsonl`. `yt_holdout`: 2 scorings left. `test`: 3 left, both untouched.
- **Interference is small:**
  - ig −0.007 vs the Instagram-only control;
  - yt −0.017 vs the YouTube-only control;
  - MRR −0.04/−0.05.
  - The other platform fills 46% of the ig top 10 and 20% of the yt top 10, with 54% and 38% relevant.
  - Seed-only labels had badly overstated interference (−0.165 / −0.055), so pool every round.
- **C1 (te lists everywhere):** −0.022 overall.
  - ig +0.063 [−0.004, +0.143], a near miss.
  - yt −0.106. About −0.095 of that is Instagram items crowding YouTube searches: te coverage is 98% of Instagram items vs 6% of YouTube items.
  - The YouTube-internal te effect is about −0.03, as in round 3.
- **C2 (te only for insufficient items):** −0.181. Restricting the te *lists* to thin items gives them two RRF votes on every search. This is a design flaw, not a verdict on routing.
- **C3 (qi-v3 filters):** −0.013.
  - It helps behaviour and named-window searches.
  - It is cancelled by guessed calendar windows, topic-free ordering on vibe searches and spurious Instagram save/date filters.
  - `require watched` silently drops Instagram.
- **Spend, round 4 (ledger `data/all/ai_runs.jsonl`):** $3.852 of $15.
  - Gemini $3.776 of its $5.50 cap, $1.72 left;
  - OpenAI $0.076.
  - Round-4.1 judging cost $0. Rounds adopting nothing in a row: 1.

**Agenda for round 4.2** (ranked by expected value per dollar; all three reuse existing outputs):

1. **Coverage-fair fusion of the te lists** (free; expected +0.02 to +0.04 overall vs C0).
   - Let each item's RRF score count only the lists that *could* rank it: the mean over eligible lists, or own-text lists standing in for missing te lists.
   - This is platform-blind and comes from an item property, not the platform.
   - Projections say it keeps C1's ig gain (+0.05 to +0.08) and cuts the yt loss from −0.106 to about −0.03.
   - Pair it with a yt-side guard for topic/task searches if the loss stays.
2. **Item-level sufficiency routing (the cascade, rebuilt; free; expected +0.01 to +0.03 on top of 1).**
   - Put an insufficient item's te text into *its own* BM25 view and blend its te vector into its own dense vector, instead of adding separate lists for a subset.
   - Sufficient items stay text-only.
   - This tests the routing idea C2 could not.
3. **qi-v3 with code-side guards (≈ $0.03 for 3 repeats; expected +0.01 to +0.03, on yt behaviour/time searches only).**
   - Keep a date window only if the search contains a calendar word (a year, month or season). Keep a behaviour filter only if it contains a behaviour word.
   - Disable topic-free → behaviour-only ordering when the parse has topic phrases.
   - Treat `watched` as "watched OR an Instagram interaction" so it no longer acts as a hidden platform filter.

Not recommended yet:
- YouTube te coverage parity: more Gemini spend, with only $1.72 left, and round 3 found te hurts titled YouTube items.
- Per-platform BM25 normalisation: interference is only about −0.01 to −0.02.

## Round 3 (`BRIEF-3.md`, run as `RUN-3.md`): YouTube, done

- **YouTube base: A0** (B3 recipe on Takeout titles and channels, OpenAI 3-small 512d). Dev 0.463, test 0.437. Nothing passed the adoption rule. **YouTube test scorings: 1 of 3 used.**
- **Spend:** Gemini $6.76, OpenAI $0.47. Ledger: `data/yt/ai_runs.jsonl`.
- **A1, the text pass:** −0.046. It does not transfer from Instagram because titles are already descriptive.
- **A2, the Gemini video pass:** the gate beats random at equal spend by +0.018 (fails the rule). Its value is reach into untitled saved videos. No correct moment was found.
- **A3, the intent filters (qi-v2):** +0.05, with about +0.6 on behaviour and time searches. **Next: run filters only on A0**, without guessed era windows.
- **Literal vs intent:** 71% agreement on relevant-vs-not (κ 0.41).
- **Reference arm (API text):** no measurable overall cost; it helps moment and name searches. **Delete `data/yt/ref/` by 2026-11-29.**
- **Write-ups:** `docs/research/2026-10-31-youtube-round.md`, `results/r3-methods.md`, `results/r3-eval.md`, `research/youtube-api-terms.md`. A-004 updated.

## Round 2 (`BRIEF-2.md`) — done except Q4 (waiting for Derrick's grades)

- **Finalist unchanged: B3.** Labels: round t2 is current. **Test-split scorings: 3 of 3 used** (none left).
- **Spend in round 2:** OpenAI $0.096, Gemini $0.058 (**$0.15**, plan was < $3). Loop totals: OpenAI $0.189, Gemini $6.758.
- **Q1 (gap flags):** weak predictors of misses (AUC 0.60 vs caption richness 0.67). 52% of misses rank beyond 1,000; on-demand enrichment of the top 200 reaches ≤ 12%. Flags should choose the facet, not the item; gap rule "unknown OR empty". Media gate proposed (image for all; audio for music/how-to gaps; video for weight ≥ 0.8 reels). `results/r2-q1-gap-flags.md`.
- **Q2 (library-aware rewrite):** profile +0.006 (cheaper with caching); look-first +0.024 on dev but −0.038 on test, +0.007 over all 22 → withdrawn; gpt-5-mini no better. `results/2026-10-30-r11-q2-q3.md`, `results/2026-10-30-test-milestone-2.md`.
- **Q3 (speed):** only the instant path (no rewrite) meets p95 ≤ 0.5 s (0.17 s), at ~−0.07 nDCG@10; LLM rewrites are 2.1–3.1 s p95 with a ~0.9 s network floor; faster/shorter models and routing don't help; recommend two-stage search. `results/r2-q3-speed.md`, chart `results/r2-q3-speed-chart.html`.
- **Q4 (AI judge vs Derrick):** blind 60-line sheet at `data/eval_work/human_check/sheet.md` (key hidden in `key.json`); scorer `eval/human_check.py`. **Next:** put Derrick's 60 grades in `data/eval_work/human_check/derrick_grades.json` and have a fresh evaluator run `python experiments/eval/human_check.py`.
- **Q5 (YouTube):** `experiments/youtube/` (synthetic importer, API enricher, eval format with `moment`, PLAN.md; 34 tests). Needs from Derrick: Takeout (JSON), `YOUTUBE_API_KEY`, ~30 YouTube searches.
- **Amendments:** A-003 updated (two-stage search, background enrichment, gap-flag findings); A-004 Proposed (YouTube contract gaps).
- **Code notes:** look-first context ordering is hash-seed dependent for tied counts (sort ties to make it deterministic before reuse). gpt-4.1-nano is no longer served (404) though still listed.
- **Round-2 assumptions:**
  1. Q1 used the dev split only, so test labels stayed untouched until the last test scoring.
  2. Q2 and Q3 runs were judged together in one evaluator round (r11).
  3. Experiment 26 was adopted provisionally under clause 2 (cache-adjusted cost below B3; its first pass equals the instant screen) and then withdrawn when the last test scoring did not confirm it.
  4. Q4 excludes friends' items from the human sheet.
  5. Rule slip: the Q3 experimenter made three diagnostic API probes outside `lib/ai.py` (one billed, $0.00001, logged by hand).

---

# Round 1 (closed)

- **Phase:** 6 done — converged and handed over. Draft pull request into `main`: https://github.com/cookie-is-yummy/digester/pull/2 (squash-merge).
- **Finalist:** **B3** = real gpt-5-nano query rewrite (qr-v1) + bge-small dense (gate, PRF) + BM25 + RRF, **plus** tier-1 text enrichment of every non-friend item (gemini-3.1-flash-lite, prompt te-v1c, Batch) indexed as its own BM25 list and its own bge-small vector list, **plus** HyDE (the rewrite's 3 invented captions as one extra query vector). Code: `methods/stack.py --opt hyde=1` (with `e9_enrich_search.py`, `pipeline.py`).
- **Labels:** round t1 is current (r0 + 567 dev judgments over rounds r1–r10 + 88 test judgments in t1). Backups `data/evals/labels/evalset.pre_*.jsonl`.
- **Test-split scorings used: 2 of 3.** One left.
- **Budget (ledger `data/ai_runs.jsonl`, list-price estimates):** OpenAI **$0.09** of $18; Gemini **$6.70** of $18. Not reconciled with the billing pages (no access from the loop).

## Summary for the founders

**Top three findings**

1. **One cheap text pass per item, indexed separately, is the only clear win.** A Gemini Flash-Lite pass writes a summary, facet slots, unknown facets and likely searches for every item; searched as its own keyword field and vector, it adds **+0.059 [+0.016, +0.108]** dev nDCG@10 (13/3/0) for **$0.18 per 1,000 items** in Batch (~$3.7 for a 21k history). With HyDE the finalist reaches 0.570 vs 0.489 for the honest base on dev; on the 6 held-out test searches it is +0.023 [−0.010, +0.053] (recall@100 +0.060 [+0.007, +0.107]); over all 22 searches **+0.065 [+0.028, +0.103]**.
2. **The previous numbers were inflated twice.** The hand-simulated rewrite had seen the answers (real rewrite: 0.49 vs 0.58), and Muse's descriptions leak labels by *which* items they cover (presence alone: +0.16). Every result in this loop was scored by a fresh blind evaluator with pooled judging.
3. **Text has hit its ceiling; the rest needs media.** 17 other ideas — feedback, fusion tweaks, priors, creator expansion, rewrite variants, three embedder swaps, ColBERT, two LLM rerankers, a second enrichment prompt — gained under 0.02 or cost too much latency. Recall@100 stayed ~0.51–0.53 with every text method. Text enrichment misses 96% of audio, 60% of place and 50% of speech that Muse had.

**Recommendation:** adopt A-003 items 1, 2 and 4 (enrich every item with one text pass, index it separately, keep bge-small); add HyDE as a free option. Keep the LLM rerank only as an opt-in "precise" mode (+0.013–0.016, +3 s). Spend the next money on a permitted media route (A-002), starting with thumbnails/keyframes for shown/vibe/more-like-this and audio fingerprints for songs, indexed the same separate-field way.

**What the founders need to decide or provide**

- Accept / reject **A-003** (contract change: ItemCard gains facet slots, unknown facets and likely searches for every item; a second embedding row per item; the 18 Oct "on-demand only" decision changes). Both founders.
- Whether the user's **collection names** may go to the LLM (kept per user, out of the shared cache), or be dropped.
- **Media:** a decision on A-002, or media files for a sample; a `YOUTUBE_API_KEY` to test YouTube thumbnails.
- **More-like-this:** an LLM "what makes these alike" plan gained on every dev MLT search (+0.05–0.11) but not on the single test one; more MLT searches are needed to decide.
- **More searches:** 16 dev searches with 5 single-search kinds can't resolve gains under ~0.02; a second person's searches and more audio/place/vibe searches would.
- Check the **Gemma licence** if EmbeddingGemma (local, multilingual) is ever reconsidered.

## Done (in order)

- Phase 1: data unzipped; baseline reproduced exactly (dev 0.508, all 0.486); prices verified (`lib/ai_prices.json`, 30 Oct); key checks; Muse inventory and ceiling (`results/muse-*.md`).
- Phase 2: `results/benchmark-baseline.md`.
- Phase 3: `results/flaws-ranked.md`. Phase 4: five research notes in `research/`.
- Phase 5: experiments 1–24 (+9b), rounds r1–r10; every row in `LOG.md`.
- Phase 6: test milestone (`results/2026-10-30-test-milestone.md`), write-up `docs/research/2026-10-30-search-loop.md`, Proposed amendment A-003 in `docs/amendments.md`.

## If resuming

- Data needed: `data/` from the zips plus `data/enrich/` (te-v1c full-corpus enrichment, ~20k rows) and `data/runs/rewrites/` (cached rewrites). Without them, rebuild with `methods/enrich_batch.py` (~$2.9) and `methods/llm_rewrite.py` (~$0.002).
- Next experiments worth running only with new inputs: media description pass on permitted media; more MLT searches; a second user's eval set.

## Assumptions

1. **No `YOUTUBE_API_KEY`**, so no YouTube media experiments; YouTube/podcast/article fit is by design and cost estimate only.
2. **`gemini-2.5-flash-lite` is unavailable** to this key (404); the cheapest Gemini text model used is `gemini-3.1-flash-lite`.
3. **Gemini Embedding 2's model ID is `gemini-embedding-2`** ($0.20/M text standard, $0.10 batch). It doesn't accept `task_type`; text prefixes were used.
4. **The phase-1 "all 22" repro counts as test scoring #1 of 3.** The T1 milestone (score, pool/judge, re-score once, all finalists together) counts as #2.
5. **MU ceiling and Muse parser are evaluator-side code** (`eval/muse*.py`, `eval/reference_compare.py`); builders never ran or read them.
6. **One experimenter may run a small batch of independent one-variable experiments**, each preregistered as its own LOG row.
7. **Experiments run on all three cached rewrite sets** and report the mean paired Δ against the same-repeat base. In production the rewrite would be cached per query.
8. **Evaluators pooled and judged every round**, even when `unjudged10` was below 0.15, so methods surfacing new items were never penalised by missing labels.
9. **HyDE adopted under clause 2 ("no extra cost")** because its captions come from the rewrite call the base already makes; it adds ~0.1 s of local embedding. Not confirmed on test.
10. **Friends' posts** (`owner_relation == "mutual"`, 463 items) were never sent to any LLM; they stay rankable from their caption only.
11. **Collection names** (the user's own data) were sent with each item to the enrichment LLM; flagged as a product decision in A-003.
12. **Rule slips, recorded:** one Gemini diagnostic curl call bypassed `lib/ai.py` (~$0.00004, logged by hand); evaluator round 1 had read MU text before judging the r1 pool; one experimenter printed one item code to its console (not written anywhere); one experimenter's `grep` of LOG.md showed two dev-score rows (aggregate, dev only); two evaluator notes quoted five search texts next to grading conventions — redacted in the final commit, but still in earlier commits on this branch, so squash-merge.
