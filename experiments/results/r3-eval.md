# Round 3 (YouTube) · evaluator report

*31 Oct 2026 · Evaluator (did not build the methods) · label rounds yt-r3 (dev) and yt-t1 (test) · aggregates only. Searches are named by the S01–S33 key or by kind. No titles, channels, IDs, query or intent texts appear here.*

Code: `experiments/eval/score_yt.py` (new; adds R@10/R@50, per-kind membership, non-library check, seed vs pooled label files). Per-search detail, sheets, grades and the LLM judge outputs are in `data/yt/eval_work/r3/` (gitignored). Aggregates: `r3-eval.json`.

## Bottom line

- **Nothing passes the adoption rule against A0, the allowed baseline.** A0 stays the YouTube base.
- **On test, A0 wins clearly.** It scores 0.437; the best dev configuration (A3v2 intent on A1) scores 0.293 (Δ −0.144 [−0.315, +0.027], 2/8/1).
- **A1 is net harmful.** The tier-1 text lists over Takeout text cost −0.046 on dev and are the main cause of the test loss.
  - They help vibe, time and personal searches.
  - They hurt topic, task, structure, more-like-this and the specific-name searches.
- **The intent step (qi-v2) is the one real positive.**
  - Filters only: +0.054 [−0.010, +0.140] on A1 and +0.049 on A2-gated.
  - Full: +0.079 [+0.003, +0.171] on A2-gated, the only clause-1 pass, but against a base that is itself 0.061 below A0.
  - Nearly all of the gain is on the behaviour and time-window searches.
  - It has not been tested on A0, so its value over the shipped base is unproven.
- **Gate vs random at equal spend:** gated is better, +0.018 [−0.009, +0.048], 10/5/7. That misses the rule, and both arms are below A1.
  - The gate reaches untitled saved videos that were unreachable before.
  - The random arm mostly reshuffles titled items that were already findable.
- **API terms cost:** R0 vs A0 is −0.005 [−0.088, +0.077]; R1 vs A1 is +0.007. On this eval, the policy costs nothing measurable overall, though it does cost on the moment and name kinds.

## Method

- **Scoring.**
  - All 42 run files were scored on dev (22 searches). Each search's metrics are averaged over the 3 rewrite repeats.
  - CIs are 2,000-sample bootstraps over searches. Comparisons pair repeat k with repeat k, average each search's Δ over the repeats, then bootstrap. W/L/T uses |Δ| > 0.005.
  - Per-kind results count a search under every kind it carries (a search has 1–3 kinds), so the kind rows overlap.
  - Recall is standard (hits / |relevant|). Several searches have hundreds to thousands of answers, so R@10 is small by construction. Capped recall is in the JSON.
- **Pooling.**
  - Seed-only unjudged@10 was 0.56–0.71 for every run.
  - All 1,015 unjudged dev top-10 items, the union over all 42 files, were pooled and judged blind by the evaluator. The sheet was grouped by search, items were shuffled, and no run identity or rank was shown.
  - Judging was against the intent, with the literal query shown, using allowed text only: title, channel, playlist names, watch/like/save dates and counts, and duration for display.
  - For the 180 untitled pooled items, the video-pass description was shown, because there was nothing else to judge from. 65 of them had no text at all.
  - Grades: 57 × 2, 130 × 1, 828 × 0. A backup was taken before the merge (`evalset.pre_r3.jsonl`).
- **Test.**
  - Before the single test scoring, the 265 unjudged test top-10 items of the three scored configurations were pooled and judged the same way (25 × 2, 40 × 1, 200 × 0).

## Dev scores (22 searches, mean of 3 repeats)

| Run | nDCG@10 seed | nDCG@10 pooled [95% CI] | repeat range (spread) | R@10 | R@50 | MRR | P@10 | unjudged@10 seed → pooled |
|---|---|---|---|---|---|---|---|---|
| a0 | 0.403 | **0.463** [0.323, 0.604] | 0.457–0.466 (0.009) | 0.147 | 0.246 | 0.760 | 0.533 | 0.56 → 0.00 |
| a1 | 0.345 | **0.417** [0.314, 0.527] | 0.412–0.426 (0.014) | 0.154 | 0.261 | 0.735 | 0.474 | 0.66 → 0.00 |
| a2_gated | 0.333 | **0.402** [0.294, 0.514] | 0.392–0.414 (0.022) | 0.148 | 0.244 | 0.728 | 0.461 | 0.67 → 0.00 |
| a2_random | 0.306 | **0.383** [0.278, 0.497] | 0.377–0.389 (0.012) | 0.144 | 0.236 | 0.726 | 0.438 | 0.71 → 0.00 |
| a3_filtersonly_on_a1 | 0.372 | **0.453** [0.355, 0.565] | 0.428–0.484 (0.056) | 0.150 | 0.245 | 0.749 | 0.515 | 0.64 → 0.00 |
| a3_intent_on_a1 | 0.369 | **0.456** [0.359, 0.564] | 0.453–0.461 (0.008) | 0.153 | 0.238 | 0.741 | 0.544 | 0.62 → 0.00 |
| a3_filtersonly_on_a2_gated | 0.359 | **0.436** [0.334, 0.554] | 0.411–0.462 (0.051) | 0.144 | 0.231 | 0.753 | 0.489 | 0.66 → 0.00 |
| a3_intent_on_a2_gated | 0.363 | **0.446** [0.347, 0.557] | 0.431–0.468 (0.037) | 0.149 | 0.234 | 0.757 | 0.517 | 0.64 → 0.00 |
| a3v2_filtersonly_on_a1 | 0.391 | **0.471** [0.374, 0.580] | 0.461–0.477 (0.016) | 0.154 | 0.260 | 0.768 | 0.536 | 0.60 → 0.00 |
| a3v2_intent_on_a1 | 0.395 | **0.484** [0.385, 0.594] | 0.473–0.501 (0.028) | 0.155 | 0.256 | 0.823 | 0.558 | 0.60 → 0.00 |
| a3v2_filtersonly_on_a2_gated | 0.373 | **0.451** [0.348, 0.563] | 0.432–0.462 (0.030) | 0.148 | 0.247 | 0.763 | 0.523 | 0.62 → 0.00 |
| a3v2_intent_on_a2_gated | 0.388 | **0.481** [0.375, 0.595] | 0.473–0.489 (0.016) | 0.153 | 0.250 | 0.827 | 0.544 | 0.62 → 0.00 |
| ref_r0 (research only) | 0.394 | **0.458** [0.332, 0.590] | 0.431–0.478 (0.047) | 0.167 | 0.290 | 0.741 | 0.517 | 0.62 → 0.00 |
| ref_r1 (research only) | 0.387 | **0.424** [0.293, 0.552] | 0.399–0.439 (0.040) | 0.155 | 0.307 | 0.755 | 0.456 | 0.61 → 0.00 |

**Seed vs pooled.**
- Pooling raised every run by 0.04 to 0.09.
- The ranking barely moved: A0 stays above A1, A2 and R1.
- Seed labels were built partly from title and channel rules, which favour title-text views. Pooling corrects the false negatives but not that bias, so A0's lead on topic, task and name searches may be slightly overstated.

### Per kind, nDCG@10 pooled (n = searches carrying the kind)

| Kind (n) | a0 | a1 | a2_gated | a2_random | a3v1 filt/a1 | a3v1 int/a1 | a3v1 filt/a2g | a3v1 int/a2g | a3v2 filt/a1 | a3v2 int/a1 | a3v2 filt/a2g | a3v2 int/a2g | ref_r0 | ref_r1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| topic (11) | **0.55** | 0.38 | 0.37 | 0.36 | 0.41 | 0.42 | 0.38 | 0.41 | 0.43 | 0.45 | 0.40 | 0.43 | 0.48 | 0.42 |
| task (8) | **0.64** | 0.53 | 0.51 | 0.48 | 0.49 | 0.49 | 0.47 | 0.47 | 0.53 | 0.53 | 0.51 | 0.51 | 0.54 | 0.51 |
| structure (5) | **0.69** | 0.55 | 0.53 | 0.55 | 0.52 | 0.53 | 0.50 | 0.53 | 0.55 | 0.59 | 0.53 | 0.58 | 0.55 | 0.57 |
| name (4) | 0.56 | 0.66 | 0.66 | 0.67 | 0.66 | 0.63 | 0.69 | 0.66 | 0.66 | 0.66 | 0.66 | 0.69 | **0.75** | 0.71 |
| personal (4) | 0.17 | 0.23 | 0.23 | 0.19 | 0.34 | 0.36 | 0.31 | 0.31 | 0.36 | **0.39** | 0.36 | **0.39** | 0.15 | 0.14 |
| time (4) | 0.20 | 0.38 | 0.40 | 0.35 | 0.56 | 0.54 | 0.56 | 0.55 | 0.53 | 0.55 | 0.53 | **0.57** | 0.32 | 0.39 |
| behaviour (3) | 0.04 | 0.10 | 0.06 | 0.07 | 0.47 | 0.53 | 0.43 | 0.47 | 0.52 | **0.54** | 0.44 | 0.49 | 0.03 | 0.01 |
| vibe (3) | 0.26 | 0.44 | 0.42 | 0.33 | 0.48 | 0.48 | 0.45 | 0.45 | 0.48 | **0.50** | 0.47 | **0.50** | 0.28 | 0.37 |
| more_like_this (2) | **0.30** | 0.17 | 0.13 | 0.14 | 0.17 | 0.17 | 0.13 | 0.13 | 0.17 | 0.17 | 0.13 | 0.13 | 0.25 | 0.14 |
| moment / said_shown (1) | 0.29 | 0.30 | 0.30 | 0.30 | 0.30 | 0.27 | 0.30 | 0.24 | 0.30 | 0.26 | 0.30 | 0.27 | **0.69** | 0.42 |
| people / shown / audio (1) | 0.36 | 0.45 | 0.41 | 0.41 | 0.44 | 0.42 | 0.41 | 0.42 | 0.45 | 0.45 | 0.41 | 0.42 | 0.41 | 0.45 |

Per-kind R@50 and MRR for the main arms are in `r3-eval.json`. In brief:
- R@50 hardly differs between arms (most searches have far more than 50 answers).
- The intent step lifts behaviour MRR from 0.18–0.34 to 0.75, and time MRR from 0.31 to 0.83.

## Comparisons (pooled dev labels)

Adoption rule: Δ ≥ 0.03 with the paired 95% CI above 0, or Δ ≥ 0.02 with more wins than losses at no extra cost.

| Comparison | Δ seed | Δ pooled [95% CI] | W/L/T | per repeat | Δ R@50 | Δ MRR | Rule |
|---|---|---|---|---|---|---|---|
| A1 vs A0 (tier-1 text, gated) | −0.058 | **−0.046** [−0.158, +0.067] | 10/10/2 | −0.053, −0.043, −0.040 | +0.014 | −0.025 | fail |
| A2 gated vs A1 | −0.011 | **−0.015** [−0.032, +0.005] | 1/12/9 | −0.012, −0.022, −0.012 | −0.017 | −0.007 | fail |
| A2 random vs A1 | −0.039 | **−0.034** [−0.059, −0.010] | 4/14/4 | −0.027, −0.037, −0.037 | −0.024 | −0.010 | fail (significantly worse) |
| A2 gated vs A2 random (gate test) | +0.028 | **+0.018** [−0.009, +0.048] | 10/5/7 | +0.015, +0.015, +0.025 | +0.007 | +0.003 | fail (Δ < 0.02) |
| A3 v1 filters only vs A1 | +0.027 | **+0.036** [−0.037, +0.122] | 3/6/13 | +0.035, +0.071, +0.002 | −0.016 | +0.013 | fail |
| A3 v1 filters only vs A2 gated | +0.026 | **+0.034** [−0.042, +0.117] | 6/4/12 | +0.034, +0.070, −0.003 | −0.013 | +0.025 | fail (CI; extra call) |
| A3 v1 full vs A1 | +0.024 | **+0.039** [−0.041, +0.136] | 9/9/4 | +0.041, +0.048, +0.029 | −0.022 | +0.006 | fail |
| A3 v1 full vs A2 gated | +0.029 | **+0.044** [−0.038, +0.136] | 10/8/4 | +0.031, +0.076, +0.026 | −0.010 | +0.029 | fail (CI; +$0.05/1k) |
| **A3 v2 filters only vs A1** | +0.046 | **+0.054** [−0.010, +0.140] | 3/2/17 | +0.064, +0.048, +0.051 | −0.000 | +0.032 | near miss (CI touches 0; extra call) |
| **A3 v2 filters only vs A2 gated** | +0.040 | **+0.049** [−0.012, +0.126] | 3/1/18 | +0.062, +0.040, +0.045 | +0.003 | +0.035 | near miss |
| A3 v2 full vs A1 | +0.050 | **+0.067** [−0.010, +0.159] | 8/9/5 | +0.061, +0.066, +0.075 | −0.005 | +0.088 | near miss |
| **A3 v2 full vs A2 gated** | +0.055 | **+0.079** [+0.003, +0.171] | 11/6/5 | +0.081, +0.081, +0.075 | +0.006 | +0.099 | **passes clause 1 vs its base** |
| A3 v2 vs v1, filters only on A1 | +0.019 | +0.018 [−0.009, +0.047] | 7/2/13 | +0.028, −0.023, +0.049 | | | |
| A3 v2 vs v1, full on A1 | | +0.028 [−0.006, +0.064] | 9/9/4 | | | | |
| R0 vs A0 (research only) | −0.009 | **−0.005** [−0.088, +0.077] | 9/11/2 | −0.001, +0.022, −0.035 | +0.044 | −0.019 | never adopt |
| R1 vs A1 (research only) | +0.043 | **+0.007** [−0.062, +0.072] | 8/11/3 | +0.027, +0.021, −0.026 | +0.046 | +0.019 | never adopt |
| R1 vs R0 | −0.007 | −0.034 [−0.107, +0.042] | 8/11/3 | | | | |
| Best stack vs A0: A3v2 full on A1 | | +0.022 [−0.135, +0.176] | 11/10/1 | +0.008, +0.022, +0.034 | | +0.063 | fail |
| Best stack vs A0: A3v2 full on A2 gated | | +0.018 [−0.132, +0.176] | 10/10/2 | | | | fail |

### A1: why the tier-1 lists hurt

Per-kind Δ vs A0:

| Helped | Hurt |
| --- | --- |
| vibe +0.18 | topic −0.17 |
| time +0.17 | structure −0.14 |
| name +0.10 | more-like-this −0.14 |
| personal +0.06 | task −0.11 |

- On name searches, one childhood search gains a lot while the specific-title searches lose.
- The te-v1c rows exist only for the 6.5k gated items: liked, saved or rewatched videos.
- As two extra RRF lists, they pull that subset into the top 10 for every search. That helps searches about the user's own taste or past, and crowds out precise topical matches.
- On test, the same pattern costs about −0.6 on two specific-name searches and about −0.3 on each more-like-this search, and gains +0.40 on the vibe/essay search.

The te lists may still be worth routing to vibe/personal searches, but not as an always-on RRF leg.

## The gate (A2 gated vs A2 random)

**Equal spend:** gated $1.82 for 377 videos; random $1.70 for 790 videos.

- **Overall.** Gated − random = +0.018 [−0.009, +0.048], 10/5/7. Positive in all 3 repeats, but below the 0.02 and 0.03 bars. On seed labels it was +0.028 [+0.010, +0.049], 10/0/12.
- **By kind (Δ gated − random).**
  - Gated is ahead on vibe +0.089, time +0.052, personal +0.044, task +0.030 and topic +0.016.
  - It is behind on structure −0.028, and slightly behind (about −0.01) on name, behaviour and more-like-this.
- **Restricted to each arm's enriched set** (dev top 10, summed over 22 searches, mean of 3 repeats):

| | Gated | Random |
| --- | --- | --- |
| Enriched items newly entering the top 10 | 45.0 | 62.0 |
| … of which relevant | 11.0 (24%) | 14.3 (23%) |
| Relevant items they push out of A1's top 10 | 14.0 | 22.3 |
| Net relevant in the top 10 | **−3.0** | **−8.0** |
| New relevant that are untitled (unreachable in A1) | **10.7 of 11.0** | 0.3 of 14.3 |
| New relevant that were already in A1's top 1000 | 0.3 | 8.3 |
| Labelled answers (dev) inside the arm's set | 106 (100 untitled, 0 Shorts) | 125 (8 untitled, 22 Shorts) |

**Reading.**
- Per enriched item that reaches the top 10, the two arms are equally precise (about 24%). The confound the builder flagged is real: the gated arm is long saved videos with no title, and the random arm is half Shorts. It shows up in what the gains are:
  - The gated arm's gains are almost all **new reach**: saved videos with no Takeout title, which had no text at all before.
  - The random arm's gains are mostly **reshuffles** of titled items the text lists could already find.
- The gate wins because it displaces fewer good results, not because its enriched items are more precise.
- At this budget neither arm pays its way against A1: −0.015 gated, −0.034 random.
- On test, the gate's reach mattered for the saved-never-watched-long behaviour search: 0.17 with A1 + intent, 0.33 with A2-gated + intent.

**Judging caveat.**
- Untitled items could only be judged from their video-pass description, which is the A2 arms' own index text.
- 115 of the 180 untitled pooled items were judged that way. This favours the A2 arms, mostly the gated one.
- The gate result is therefore an upper bound.

**Selection caveat.** The gate's `demand` weights were computed from the kinds of all 33 method-side searches, test included. That is method-side information, so it is not label leakage, but it is tuned to the eval's kind mix.

## The intent step (A3)

**Clean test (filters only; the text plan is identical to the base).**
- qi-v1: +0.036 on A1 and +0.034 on A2-gated, with CIs that cross 0.
- qi-v2: +0.054 on A1 and +0.049 on A2-gated, positive in all 3 repeats, with only 1–2 losing searches.
- Neither passes, because of the CI and the extra rewrite call (production qi-v2 is $0.18/1k searches vs qr-v1's $0.12/1k).
- The full variants add qi's own text plan: v2 full is +0.067 on A1 and +0.079 [+0.003, +0.171] on A2-gated.

**Per search, nDCG@10 Δ vs base for each repeat (r1, r2, r3).**
- Searches not listed were unchanged in all repeats.
- Filters are the builder's logged intents (see `r3-methods.md`).

| Search (kinds) | Filters that fired | v1 on A1 | v2 on A1 | v1 on A2g | v2 on A2g | Helped? |
| --- | --- | --- | --- | --- | --- | --- |
| S16 (behaviour, personal) | v1: watches ≥ 3 (r2), saved+watched + sort most-watched (r1), none effective (r3). v2: watches ≥ 3 in all 3 | +0.56, +0.69, 0 | +0.77, +0.35, +0.61 | +0.58, +0.69, 0 | +0.80, +0.35, +0.63 | **Yes, large** |
| S31 (time, topic, behaviour) | summer window in all 6 repeats | +0.65, +0.83, +0.65 | +0.65, +0.77, +0.62 | +0.65, +0.66, +0.65 | +0.57, +0.60, +0.50 | **Yes, large** |
| S07 (vibe, time, personal) | v1: wide windows + saved / era (r2, r3) helped, exclude-all (r1) did nothing. v2: tiny-pool window (r3) helped, others did nothing | −0.02, +0.53, +0.30 | −0.02, 0, +0.36 | 0, +0.39, +0.25 | 0, 0, +0.40 | Yes, when the window is old enough |
| S19 (time, personal, topic) | v1: three different guessed windows. v2: era boost / liked+saved / one-year window | +0.15, −0.47, −0.40 | 0, −0.07, −0.40 | +0.13, −0.60, −0.55 | 0, −0.06, −0.55 | **No: guessed dates hurt** |
| S18 (vibe, task) | v1 r3: topic-free → behaviour-only ranking | 0, 0, −0.46 | 0, 0, 0 | 0, 0, −0.46 | 0, 0, 0 | v1 hurt; v2 fixed it |
| S02 (task, topic, structure) | v1 r1: require liked+saved (pool 10k) | −0.41, +0.05, −0.02 | 0, 0, 0 | −0.41, +0.05, −0.02 | 0, 0, 0 | v1 hurt; v2 fixed it |
| S05 (task, topic) | v1: date window / require saved. v2: require liked+saved | −0.16, −0.05, 0 | 0, 0, −0.06 | −0.19, −0.05, 0 | 0, 0, 0 | No (spurious) |
| S23 (name, time) | era boost (v1 r2) | 0 | 0 | 0, +0.37, 0 | 0 | Once, by chance |
| S13, S15, S33 | stray require / topic-free | ≤ ±0.07 | 0 | ≤ ±0.07 | 0 | Neutral |

**Takeaways.**
- **Behaviour and time-window searches are where the step earns its keep.**
  - Rewatched: +0.6 on average under v2.
  - Summer window: +0.65 under both versions.
- **"Era of my life" without dates is where it does harm.** Guessed windows wipe out a working text ranking.
- **qi-v2 removed v1's spurious filters on topic searches.** S02, S05 and S18 go to 0 Δ. It kept the behaviour wins.
- **Overfitting risk.** qi-v2 was written after its author saw qi-v1's outputs on all 33 searches, test included. Its rule examples also reuse eval search wording:
  - phrases from two dev searches (behaviour, time);
  - phrases from two test searches (behaviour, name/audio);
  - in v2, a mood word from a test vibe search.
  - The rule mapping "long" to ≥ 1,200 s coincides with the S30 label threshold. It is not in any method-side doc found.
- **Test evidence for v2 is therefore weak.** It should not be used to confirm v2.
- **One gap.** Neither version set a duration bound for the long-videos search on test.

## Literal vs intended meaning

**Sample.**
- All 247 pooled dev items from the 6 dev searches whose intent differs from the query: S01 2, S03 15, S04 23, S07 75, S13 96, S18 36.
- Each item was judged twice by gpt-5-mini (low reasoning), blind to run and order:
  - once against the literal query only;
  - once against the query plus the person's clarification.
- 46 calls cost $0.057.

**Result.**

| | Agreement |
| --- | --- |
| Exact grade | 0.56 |
| Relevant vs not | **0.71** (κ = 0.41) |
| Transitions | 138 unchanged; 66 lower under intent (2→1: 24, 2→0: 17, 1→0: 25); 43 higher (0→1: 21, 0→2: 9, 1→2: 13) |

| Search (kinds) | n | Binary agreement | Relevant share, literal → intent |
| --- | --- | --- | --- |
| S03 (task, topic, structure) | 15 | 0.60 | 0.73 → 0.33 |
| S07 (vibe, time, personal) | 75 | 0.63 | 0.75 → 0.56 |
| S13 (personal, behaviour, topic) | 96 | 0.71 | 0.43 → 0.45 |
| S04 (topic) | 23 | 0.74 | 0.61 → 0.78 |
| S18 (vibe, task) | 36 | 0.89 | 0.69 → 0.75 |

**Which searches diverge.** The literal and intended readings diverge most where the clarification narrows the meaning:
- **S03:** it narrows the kind of content wanted.
- **S07:** it redefines a mood as the person's own viewing history.

Where the clarification mainly adds "deprioritise Shorts" (S04, S18), the two readings agree, and the LLM judge largely ignored that part.

**Judge calibration.**
- The LLM judge is far more lenient than the evaluator: relevant share 0.55 vs 0.24 on the same items.
- It agrees with the evaluator's intent grades on relevant-vs-not only 0.62 of the time (κ = 0.27).
- It gave grade 1 to items with no text at all, and ignored "watched briefly" and "no Shorts".

**What this means for the labels.**
- The pooled qrels are the evaluator's own grades.
- The LLM pass was used only for the literal-vs-intent comparison.
- About 3 in 10 relevance decisions on clarified searches flip depending on the reading. Seed labels and any LLM-judged pool should be read against the intent, not the query text.

## The moment search (S29)

Moments exist only in the A2 and A3-on-A2 runs.

| Arm | Top segment's video | Top-3 / top-20 segments in labelled videos |
| --- | --- | --- |
| Gated (12 run files) | always in a labelled video | 2–3 / 10–12 |
| Random | never in a labelled video | 0 / 0 |

**Is the segment the described moment?** No.
- The gated "hit" is a single untitled biography-style video. It was judged relevant at grade 1, from its video-pass text.
- Its top segments are the introduction and a general "function theory and complex analysis" passage.
- None describes the spiral or rotation explanation the search asks for.
- The two grade-2 answers, the actual explanatory videos, are in neither video arm, so no segment could be right.

**Format notes.**
- Several segments are zero-length (start = end) at the 20-minute clip end. They come from clamping.
- Videos clipped at 20 minutes cannot answer moments after that point.

**Video-level credit.** The reference arm R0 reaches 0.69 on this search from description and chapter text, vs 0.29–0.30 on the allowed track.

## What the API terms cost (research only; never adopt)

| | Overall Δ | Kinds that gain | Kinds that lose |
| --- | --- | --- | --- |
| R0 vs A0 | −0.005 [−0.088, +0.077], R@50 +0.044 | moment +0.40, name +0.19, time +0.11 | structure −0.14, task −0.10, topic −0.07, more-like-this −0.06 |
| R1 vs A1 | +0.007 [−0.062, +0.072] | | |

- **At tier 0, the policy costs nothing measurable overall.** API descriptions and tags help find a named video or a moment, and add noise to topical searches.
- **At tier 1, it costs nothing measurable either.** R1 costs $2.05 vs A1's $1.11 and shows the same "tier-1 lists hurt" pattern (R1 vs R0 −0.034).
- **Caveat.** Seed labels were built from Takeout title/channel rules, which favours the allowed view. Treat "no cost" as "no cost detectable here". On name and moment searches, the policy's cost is real.

## Test split (scoring 1 of 3 for YouTube)

**What was scored.**
- The best allowed configuration on dev (A3v2 full on A1).
- Its nearest rival (A3v2 full on A2-gated).
- A0.

All three were scored once, after the test pool was judged.

| Run | nDCG@10 seed | nDCG@10 pooled [95% CI] | repeat range | R@10 | R@50 | MRR | P@10 |
|---|---|---|---|---|---|---|---|
| **a0** | 0.370 | **0.437** [0.255, 0.605] | 0.033 | 0.098 | 0.145 | 0.677 | 0.509 |
| a3v2_intent_on_a1 | 0.130 | 0.293 [0.168, 0.420] | 0.026 | 0.049 | 0.118 | 0.656 | 0.448 |
| a3v2_intent_on_a2_gated | 0.140 | 0.293 [0.175, 0.415] | 0.056 | 0.049 | 0.119 | 0.691 | 0.491 |

**Comparisons.**

| Comparison | Δ | W/L/T |
| --- | --- | --- |
| A3v2 full on A1 vs A0 | −0.144 [−0.315, +0.027] | 2/8/1 |
| A3v2 full on A2-gated vs A0 | −0.144 [−0.323, +0.041] | 2/8/1 |
| A1 base vs A2-gated base | 0.000 | 5/2/4 |

**Per kind on test, A0 vs A3v2 full on A1:**

| Kind | A0 | A3v2 full on A1 |
| --- | --- | --- |
| name | 0.48 | 0.09 |
| more-like-this | 0.68 | 0.38 |
| topic | 0.51 | 0.38 |
| task | 0.42 | 0.26 |
| vibe | 0.43 | 0.62 |
| behaviour | 0.00 | 0.17 (0.33 on A2-gated) |

The test loss is the A1 te-list effect from dev, larger on test because test has more name and more-like-this searches. The intent step's behaviour gain shows up on test as well.

## Cost per point of nDCG@10 (dev, pooled; 1 point = 0.01)

| Step | Spend | Δ nDCG@10 | Cost per point |
| --- | --- | --- | --- |
| A1 te-v1c (Takeout text, gated) | $1.105 one-off ($0.170/1k items) | −4.6 vs A0 | no gain |
| A2 gated video pass | $1.82 ($4.83/1k videos) | −1.5 vs A1 (+1.8 vs random) | no gain vs A1 |
| A2 random video pass | $1.70 ($2.16/1k videos) | −3.4 vs A1 | no gain |
| A3 qi-v2, filters only (extra call) | +$0.18/1k searches | +5.4 vs A1 | ≈ $0.033 per 1k searches per point |
| A3 qi-v2, full (replaces qr-v1) | +$0.06/1k searches | +6.7 vs A1 | ≈ $0.009 per 1k searches per point |
| R0 API view (research) | +$0.27 one-off embeddings | −0.5 vs A0 | no gain |
| R1 te over API text (research) | $2.05 one-off ($0.194/1k items) | +0.7 vs A1 | ≈ $2.9 per point (this library) |

## Problems found in the builder's runs

1. **Non-library results.**
   - The three outside-library more-like-this example videos appear in other searches' result lists.
   - They have an enrichment row but are not in the user's library: 1,274 placements across the run files, 11 of them in a top 10. On test, A2-gated has nonlib@10 = 0.012.
   - They were scored as non-relevant and excluded from pooling. A search must only return library items.
2. **Truncated lists.** A small intent pool truncates a ranking to 5–8 items (one dev search in qi-v1 r3 and one in qi-v2 r3). Recall is capped, and nDCG suffers if the pool misses.
3. **Zero-length and clamped moment segments.** See the moment section.
4. **Mild leakage in the intent prompt.** Its rule examples quote eval search phrasing from dev and test searches, and the "long" threshold equals a test label rule. qi-v2 was also written after seeing outputs on the test searches. This favours A3 on behaviour searches; it does not change any verdict.
5. **Stale cost snapshot.** Run `meta.offline_cost_usd_by_purpose` reports $1.397 for the R1 API batch; the ledger has $2.048.
6. **Labels (not the builder).**
   - Two dev topic searches (S04, S05) had identical seed answer sets (104 / 104).
   - Several single-answer searches are nested inside large topic sets.
   - Seed answers came from title/channel rules, as noted above.

**No sign of label access by the method code.** The two method files that mention "labels" do so only in a docstring and a prompt word.

## Recommendation

1. **Keep A0** as the YouTube base. Adopt nothing from this round.
2. **Do not ship A1's te lists as always-on RRF legs.** Their gain is confined to vibe, time and personal searches. If they are kept, route them by kind (a new experiment).
3. **Next experiment: qi-v2 filters only on A0.** The intent step is the strongest signal of the round: +0.05 with almost no losers, and +0.6 on behaviour and time searches. It has only been tested on bases that lose to A0.
   - Before the run: drop guessed date windows for "era of my life" searches (the main loss), and remove eval-specific phrases from the rule examples.
   - Judge it on fresh searches or the remaining test scorings.
4. **Video pass.** If it is run again, the gate beats random selection, and its value is reach into untitled saved videos (behaviour searches). At $1.8 per arm, it does not pay as a general search leg.
5. **API text.** No measurable overall cost from the terms decision. The real cost is on name and moment searches, where description and chapter text matter.

## Spend (ledger)

- **Evaluator judging:** $0.057 OpenAI (46 gpt-5-mini calls, 35k in / 24k out tokens). Gemini $0.
- **Round totals:** OpenAI $0.473 of $4; Gemini $6.758 of $8.
- **Evaluator self-judging:** 1,015 dev + 265 test items, free.
