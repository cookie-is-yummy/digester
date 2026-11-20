# Round 6 · held-out `test2` (scoring 2 of 3) · evaluator report

*7 Nov 2026 · Held-out evaluator (did not build any method) · label round **c4-t2b** · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. Searches are referred to by `g`-number, scope and kind only.*

**Scorings used by this report:** `test2` scoring **2 of 3** (**1 left**). `test` (2 left) and `yt_holdout` (1 left) were not scored or read. No dev row was scored.

Three frozen methods were scored once, after pooling and blind judging:
- **C0**, the finalist;
- **G4**, text-embedding-3-large at 1,024 d, with C0's nano rewrites;
- **G5**, G4 plus gpt-5.4-mini rewrites.

No run or method file was touched. Code: `experiments/eval/score_c4.py`, unchanged. The sheet builder, analysis script, sheet, grades, per-search deltas (by `g`-number) and the three label-set score files are in `data/all/eval_work/test2b/`, which is gitignored. Aggregates are in `r6-test2.json`.

## Bottom line

- **G4 vs C0: +0.053 [−0.001, +0.134], 7/2/1.** G4 scores 0.501 and C0 0.448.
  - By scope:
    - `yt` (4 searches): +0.109 [−0.018, +0.293], 3/1;
    - `both` (6 searches): +0.015 [−0.006, +0.039], 4/1/1.
  - On Derrick's own labels only (seed), the result is **+0.022 [−0.013, +0.056], 7/2/1**. That is the same size and direction as dev (+0.022, 25/12).
  - **It is concentrated.** g06 (yt · topic/structure) is +0.38 and carries 72% of the net gain.
    - Without the best search, +0.017 is left; without the best three, +0.003.
    - The paired lower bound is −0.001 to 0.000, below 0 on 20/20 seeds.
    - Every one of the 9 repeat pairings is positive (+0.020 to +0.109).
- **G5 vs C0: +0.032 [−0.026, +0.085], 5/4/1.**
  - By scope: `yt` +0.053 (3/1); `both` +0.017, but 2/3, so it loses more `both` searches than it wins.
  - Seed only: +0.009, 4/4/2.
  - Judge sensitivity flips its sign. With this round's 1s set to 0 it is −0.017; with its 2s demoted to 1 it is −0.006.
  - Its largest loss is g08 (yt · name/topic), −0.15.
- **G5 vs G4: −0.021 [−0.083, +0.032], 4/5/1**; seed only −0.014, 2/6/2. On dev it was −0.008. **The mini rewrites add nothing on top of 3-large.**
- **Verdicts.** Confirmed means positive on test2, with more wins than losses, and consistent with dev.
  - **G4: confirmed** in direction and in wins. Its size is not established, because it rests on one search.
  - **G5: not confirmed.**
- **Pooling.** 73 items were pooled over 10 searches: 41 surfaced only by G5, 21 by both G4 and G5, and 11 only by G4.
  - Before pooling, unjudged@10 was C0 0.00, G4 0.19 and G5 0.30. After pooling it is 0.00 for every run.
  - Pre-pool Δ, which counts unjudged items as 0: G4 +0.003, G5 −0.073. Pooling was necessary.

## Method

- **Runs.**
  - C0: `runs/final2/c0x_test2_r{1,2,3}`.
  - G4 and G5: `runs/final3/{g4,g5}_test2_r{1,2,3}`.
  - All are read through symlinks in `eval_work/test2b/runs/`.
  - All 9 files cover the 10 searches at depth 1,000. G4's meta names C0's nano test2 parses (`qr-v1_gpt-5-nano_r{k}`); G5's names gpt-5.4-mini parses.
- **Searches.** 4 are `yt` and 6 are `both`; none is `ig`. Kinds, which overlap: topic 7, structure 6, name 3, task 3, vibe 3, time 1.
- **Conventions,** as in `r5-test2.md` and `r6-eval.md`:
  - each search's metrics are the mean over 3 repeats, and comparisons pair repeat k with repeat k;
  - CIs are 2,000-sample bootstraps over searches (seed 0 for levels, seed 1 for Δ);
  - W/L/T uses |Δ| > 0.005;
  - per-kind rows count a search under every kind it has.
- **Labels.**
  - Derrick's `relevant` grades and `judged_nonrelevant` zeros are gold and were not touched. I checked this after the merge: 0 differences. The earlier test2 evaluator's 159 grades are also unchanged.
  - `unvetted_candidates` were treated as unjudged, and were judged only where they surfaced in a top 10.
  - Backup: `evalset.pre_test2b.jsonl`. Merged with `judge.py merge`, judge `claude-evaluator-test2b`. No non-test2 row changed.
- **Pool.** Every unjudged top-10 item of the three methods over 3 repeats, cross-platform items included: **73 items over 10 searches**.
  - 35 of them were `unvetted_candidates`.
  - By search scope and item platform: yt/YouTube 29, yt/Instagram 2, both/YouTube 27, both/Instagram 15.
  - The largest pools were g06 (17), g07 (13) and g05 (10).
- **Blind judging, $0, no paid judge.**
  - The sheet uses the test2 builder. It is grouped by search and shuffled within each search. It shows no run, rank or vetted/unvetted status. It shows the item's own text, interactions and duration; te text is not shown.
  - **Calibration first.** For every search I read up to 10 of Derrick's 2s, 10 of his 1s and his 0s (from `evalset.pre_test2.jsonl`), then up to 5 per grade of the earlier test2 evaluator's grades. I kept that evaluator's per-search scales:
    - strict on g05: only the confirmed target creator is 2, and every other creator is 0;
    - literal on g09: a title in the stated format is 2, and near-formats or rankings are 1;
    - lenient on g10 and g07, where broad matches to the intent get 2;
    - on g04 and g08, the target's own related items get 1–2 and same-topic items by others get 0;
    - on g01, g03 and g06, 2 goes only to the core of the intent; on-topic items without the stated structure or depth get 1;
    - surface-word matches get 0.
  - **Grades: 20 / 31 / 22** (2 / 1 / 0).
    - By scope and platform: yt/YouTube 13/8/8; yt/Instagram 0/1/1; both/YouTube 5/10/12; both/Instagram 2/12/1.
    - Unvetted candidates that surfaced: 15/18/2.
    - All 10 pooled items on g05 are 0, because none is by the target creator.
- **Whose grades the pooled score rests on.**
  - Of the relevant top-10 items, Derrick's grades cover 33% for C0, 35% for G4 and 30% for G5. This round's grades cover 0%, 15% and 30%.
  - Of the grade-2 items in the top 10, Derrick's grades cover 34–37%.

## Scores (mean of 3 repeats; spread = max − min over repeats)

Seed-only = Derrick's own test2 labels (`evalset.pre_test2.jsonl`). Pooled = c4-t2b (Derrick + the earlier test2 evaluator + this round).

| Method | Scope (n) | **nDCG@10 pooled** [95% CI] (spread) | nDCG@10 seed (spread) | R@10 pooled / seed | MRR pooled / seed (pooled spread) | P@10 pooled / seed (pooled spread) | Seed unj@10 | Other-platform share of top 10 |
|---|---|---|---|---|---|---|---|---|
| **C0** | all (10) | **0.448** [0.303, 0.603] (0.025) | 0.180 (0.002) | 0.131 / 0.070 | 0.714 / 0.351 (0.130) | 0.633 / 0.210 (0.010) | 0.79 | 0.02* |
| C0 | yt (4) | 0.301 (0.046) | 0.127 (0.032) | 0.095 / 0.044 | 0.572 / 0.229 (0.208) | 0.475 / 0.142 (0.100) | 0.86 | 0.05 |
| C0 | both (6) | 0.547 (0.072) | 0.215 (0.022) | 0.155 / 0.087 | 0.808 / 0.433 (0.083) | 0.739 / 0.256 (0.050) | 0.74 | — |
| **G4** | all (10) | **0.501** [0.345, 0.657] (0.064) | 0.202 (0.019) | 0.139 / 0.075 | 0.726 / 0.402 (0.017) | 0.690 / 0.240 (0.040) | 0.76 | 0.01* |
| G4 | yt (4) | 0.410 (0.129) | 0.159 (0.029) | 0.107 / 0.047 | 0.562 / 0.329 (0.041) | 0.567 / 0.183 (0.100) | 0.82 | 0.03 |
| G4 | both (6) | 0.562 (0.070) | 0.231 (0.052) | 0.161 / 0.093 | 0.835 / 0.450 (0.002) | 0.772 / 0.278 (0.033) | 0.72 | — |
| **G5** | all (10) | **0.480** [0.322, 0.637] (0.061) | 0.189 (0.042) | 0.140 / 0.066 | 0.752 / 0.383 (0.050) | 0.697 / 0.210 (0.070) | 0.79 | 0.02* |
| G5 | yt (4) | 0.354 (0.130) | 0.155 (0.097) | 0.102 / 0.042 | 0.628 / 0.366 (0.126) | 0.550 / 0.175 (0.125) | 0.82 | 0.06 |
| G5 | both (6) | 0.564 (0.033) | 0.211 (0.016) | 0.166 / 0.082 | 0.834 / 0.395 (0.000) | 0.794 / 0.233 (0.050) | 0.76 | — |

\* In the `all` rows, `both` searches count as 0 cross share.

- **Repeat levels, all searches** (nDCG@10 pooled, r1 / r2 / r3): C0 0.452 / 0.459 / 0.434; G4 0.543 / 0.479 / 0.482; G5 0.486 / 0.447 / 0.508.
- C0 reproduces its round-5 test2 score exactly (0.448). The new judgments only add relevant items that C0 did not retrieve, which lowers its R@10 from 0.142 to 0.131.
- Every method scores 0 on g05 (both · name/time).

## Comparisons (paired)

| Comparison | Scope (n) | **Δ nDCG@10 pooled** [95% CI] | W/L/T | Per repeat | Δ R@10 | Δ MRR | Δ P@10 | Seed-only Δ [CI], W/L/T |
|---|---|---|---|---|---|---|---|---|
| **G4 vs C0** | all (10) | **+0.053** [−0.001, +0.134] | **7/2/1** | +0.091, +0.020, +0.048 | +0.009 | +0.012 | +0.057 | **+0.022** [−0.013, +0.056], 7/2/1 |
| | yt (4) | +0.109 [−0.018, +0.293] | 3/1/0 | +0.175, +0.058, +0.094 | +0.012 | −0.010 | +0.092 | +0.032 [−0.048, +0.099], 3/1/0 |
| | both (6) | +0.015 [−0.006, +0.039] | 4/1/1 | +0.034, −0.005, +0.017 | +0.006 | +0.027 | +0.033 | +0.016 [−0.001, +0.038], 4/1/1 |
| **G5 vs C0** | all (10) | +0.032 [−0.026, +0.085] | 5/4/1 | +0.033, −0.012, +0.074 | +0.009 | +0.038 | +0.064 | +0.009 [−0.051, +0.061], 4/4/2 |
| | yt (4) | +0.053 [−0.081, +0.132] | 3/1/0 | +0.099, −0.012, +0.072 | +0.007 | +0.056 | +0.075 | +0.028 [−0.117, +0.108], 3/1/0 |
| | both (6) | +0.017 [−0.024, +0.067] | **2/3/1** | −0.010, −0.012, +0.075 | +0.011 | +0.026 | +0.055 | −0.004 [−0.038, +0.039], 1/3/2 |
| **G5 vs G4** | all (10) | −0.021 [−0.083, +0.032] | 4/5/1 | −0.057, −0.032, +0.026 | +0.001 | +0.025 | +0.007 | −0.014 [−0.041, +0.015], 2/6/2 |
| | yt (4) | −0.056 [−0.183, +0.066] | 2/2/0 | −0.076, −0.070, −0.022 | −0.005 | +0.065 | −0.017 | −0.004, 1/2/1 |
| | both (6) | +0.002 [−0.030, +0.034] | 2/3/1 | −0.045, −0.007, +0.058 | +0.005 | −0.001 | +0.022 | −0.020 [−0.040, +0.002], 1/4/1 |

### Per kind, Δ nDCG@10 (pooled; seed-only in brackets; C0 pooled level in the first column)

| Kind (n) [C0] | G4 vs C0 | G5 vs C0 | G5 vs G4 |
|---|---|---|---|
| topic (7) [0.48] | +0.064 (+0.025) | +0.022 (−0.004) | −0.041 (−0.028) |
| structure (6) [0.51] | **+0.079** (+0.041) | +0.059 (+0.033) | −0.020 (−0.008) |
| name (3) [0.24] | +0.007 (−0.024) | −0.017 (−0.025) | −0.025 (−0.001) |
| task (3) [0.65] | +0.036 (+0.028) | +0.031 (+0.016) | −0.005 (−0.012) |
| vibe (3) [0.33] | +0.049 (+0.044) | **+0.077** (+0.065) | +0.027 (+0.021) |
| time (1) [0.00] | 0 | 0 | 0 |

### Robustness (pooled; paired bootstrap, 20 seeds × 10k samples)

| Arm | Δ | Lower bound range | Seeds with lower bound > 0 | Drop best 1 / 2 / 3 searches | Best search's share / top-3 share of net gain | All 9 repeat pairings (k vs j) |
|---|---|---|---|---|---|---|
| G4 vs C0 | +0.053 | −0.001 to 0.000 | 0 / 20 | +0.017 / +0.010 / +0.003 | 72% / 96% | +0.020 to +0.109 (all > 0) |
| G5 vs C0 | +0.032 | −0.027 to −0.023 | 0 / 20 | +0.020 / +0.007 / −0.010 | 44% / 122% | −0.012 to +0.074 |
| G5 vs G4 | −0.021 | −0.087 to −0.084 | 0 / 20 | −0.035 / −0.048 / −0.061 | — | −0.096 to +0.029 |

### Grade sensitivity (this round's 73 grades only; Derrick's and the earlier evaluator's grades unchanged)

| Label variant | G4 vs C0 | G5 vs C0 | G5 vs G4 |
|---|---|---|---|
| Pooled, as judged | +0.053, 7/2 | +0.032, 5/4 | −0.021, 4/5 |
| This round's 1s → 0 | +0.033, 5/3 (yt +0.101, both −0.013) | **−0.017**, 5/4 | −0.050, 4/5 |
| This round's 2s → 1 | +0.033, 6/3 | **−0.006**, 4/5 | −0.039, 3/6 |
| Seed only (Derrick) | +0.022, 7/2 | +0.009, 4/4 | −0.014, 2/6 |

- G4 stays positive with more wins than losses under every variant. Its `both` part does not: with my 1s set to 0 it becomes −0.013, because most of the new `both` items are 1s.
- G5's gain over C0 depends on how this round's grades are scaled.

**Where the gains and losses are, by `g`-number:**
- **G4.**
  - Wins: g06 (yt · topic/structure) **+0.38** (seed +0.10), g04 (yt · name/structure/vibe) +0.07, g10 (both · task/topic) +0.06, g07 (both · topic/vibe/task) +0.04, g01 (yt · topic/vibe/structure) +0.03, and two smaller wins.
  - Losses: g08 (yt · name/topic) −0.05 (seed −0.10) and g03 (both · topic/structure) −0.03.
  - On g06, G4 fills its top 10 with core items that C0 ranked lower. Most of them were unvetted candidates, which I graded 2 on the search's own scale. Derrick's own 2s on that search already move G4 up by +0.10.
- **G5.**
  - Wins: g01 +0.14, g06 +0.13, g10 +0.12, g04 +0.10 and g09 (both · structure) +0.06.
  - Losses: **g08 −0.15** (seed −0.19), g03 −0.05, g02 (both · task/structure/topic) −0.02, and g07 −0.01.
  - Against G4, G5 gives back −0.25 on g06 and −0.10 on g08, and gains on g01 (+0.10) and g10 (+0.06).

## Mechanisms: top-10 platform mix

Mean per search: items per top 10 @ share relevant (pooled labels).

| Run | yt searches: YouTube items | yt searches: Instagram items | both searches: Instagram items | both searches: YouTube items |
|---|---|---|---|---|
| C0 | 9.50 @ 0.50 | 0.50 @ 0.00 | 3.22 @ 0.81 | 6.78 @ 0.70 |
| G4 | **9.67 @ 0.58** | 0.33 @ 0.25 | 2.72 @ **0.96** | 7.28 @ 0.70 |
| G5 | 9.42 @ 0.56 | 0.58 @ 0.43 | 2.78 @ **0.98** | 7.22 @ 0.72 |

- **On `yt` searches, 3-large lets fewer Instagram items in** (0.50 → 0.33 per top 10), and its YouTube items are more often relevant (0.50 → 0.58). This repeats dev, where Instagram items in yt top 10s fell from 2.05 to 1.59. On test2 the YouTube ordering itself also improves, mostly on g06.
- **On `both` searches, 3-large keeps fewer Instagram items but better ones** (3.22 @ 0.81 → 2.72 @ 0.96). That is the dev ig-side precision effect. The YouTube items' precision is unchanged, so the `both` net is small (+0.015).
- **G5** keeps G4's `both` precision but lets slightly more Instagram items into `yt` searches. Its YouTube precision there is a little lower (0.56).

## Consistency with dev, and verdicts

| Arm | Dev (c4-r6) vs C0 | test2 vs C0 | Rule: positive, W > L, consistent with dev | Verdict |
|---|---|---|---|---|
| **G4** | +0.022 [−0.008, +0.051], 25/12/7; ig +0.031 (16/5), yt +0.014 (9/7); MRR +0.050 | **+0.053 [−0.001, +0.134], 7/2/1**; yt +0.109 (3/1), both +0.015 (4/1); seed only +0.022, 7/2 | Positive, and 7 > 2. Consistent with dev: same sign, clearly more wins than losses in both (25/12, 7/2), seed-only Δ equal to the dev Δ, a positive `both` part (dev's ig gain via precision of Instagram items) and the same cross-platform mechanism. The size is larger than dev because of one search (g06); without it, +0.017. | **CONFIRMED.** The direction and the wins are confirmed. The size is not: the CI touches 0, the best search is 72% of the gain, and with the best 3 dropped +0.003 is left. On test2 alone it misses adoption clause 1 narrowly (Δ ≥ 0.03, but the lower bound is −0.001). |
| **G5** | +0.014 [−0.011, +0.039], 23/15/6; **ig +0.038 (robust)**, yt −0.009 (8/10) | +0.032 [−0.026, +0.085], 5/4/1; yt +0.053 (3/1), **both +0.017, 2/3**; seed only +0.009, 4/4 | Positive, and 5 > 4 by one search. **Not consistent with dev.** Its robust dev part (Instagram side) does not reappear: on `both` it loses more searches than it wins. Its test2 gain is on `yt`, where dev was negative. The sign flips under both grade-sensitivity variants. | **NOT CONFIRMED.** |
| G5 vs G4 | −0.008, 16/13/15 (yt −0.023) | −0.021, 4/5/1; seed only −0.014, 2/6 | Same direction as dev. | gpt-5.4-mini rewrites do not help on top of 3-large; dev's conclusion stands. |

**Answer to "is the dev result consistent?":**
- **G4: yes in direction**. Seed only reproduces the dev Δ exactly (+0.022). The pooled size (+0.053) is inflated by one search.
- **G5: no.** Its dev Instagram gain (+0.038) is not visible on the mixed-platform searches, and its overall gain is within judging noise.

## Cost and latency (run `meta`)

| Run | $/1k searches | Typed total latency p50 / p95 (s) | Notes |
|---|---|---|---|
| C0 | $0.116–0.119 (rewrite only) | rewrite + local p50 1.81–2.16 (old footing, no embedding call) | Same as round 5 |
| G4 | $0.128–0.131 | 2.19–2.54 / 2.30–3.94 | Plus $0.0043 per 1k items once ($0.52 for this library, already paid) |
| G5 | $1.46–1.48 | 1.92–2.13 / 2.11–2.80 | About 11× G4 |

- The test2 latency totals include a live query-embedding call (≈ 0.3 s), as in round 6, so they are not directly comparable with C0's round-5 footing.
- On dev, the same-runner C0 control was 1.91 / 2.52–2.84 s, and G4 was +0.1 s.
- **Spend.** This scoring cost **$0**, with no paid judging. The ledger now stands at OpenAI **$2.623** of $9.50 (the orchestrator's test2 runs for G4 and G5 are included) and Gemini $3.776, for a total of **$6.399**.

## Problems and caveats

1. **Small n, and no `ig` scope.**
   - There are 10 searches; one of them (g05) is 0 for every method, so it adds only a tie.
   - test2 cannot test G5's robust dev part directly, which was ig scope.
2. **G4's gain rests on g06.** It is +0.38 there, 72% of the net. That search's newly surfaced items are mostly unvetted candidates graded by me.
   - Derrick's own grades on g06 already give +0.10, so the direction does not depend on my grades.
   - The size does. A Derrick spot-check of the g06 pooled items would firm up the size.
3. **A single judge** (this evaluator) produced all 73 new grades. The sensitivity rows above bound the effect:
   - G4's verdict holds under every variant;
   - G5's does not.
4. **The pool was G5-heavy.** 41 of the 73 items were surfaced only by G5. Before pooling, G5's unjudged@10 was 0.30. That is why its pre-pool Δ (−0.073) was misleading.
5. **te text was not shown to the judge.** This does not matter here: none of these arms uses te lists.
6. **G4 is less stable across repeats than C0 on `yt`** (spread 0.129 vs 0.046), as on dev (0.059). Repeat 1 carries most of the gain: per repeat +0.091 / +0.020 / +0.048. Every cross-repeat pairing is still positive.
7. **Calibration fidelity.**
   - On g10, Derrick's scale is very lenient: he gave 2 to on-theme items that do not do what the intent asks. I followed the earlier evaluator, who gave such items 1, and 0 to the kind the intent excludes. This may make my g10 grades slightly stricter than his.
   - On g07, I gave promotional items with no content signal 0 or 1, as the earlier evaluator did.
8. **No rule slips** to report.
   - No captions, query texts, intents, creators or IDs were written to a committed file.
   - Nothing under `/tmp/claude-0/` was read.
   - No key was printed.
   - `test`, `yt_holdout` and dev were not scored.

## Remaining held-out scorings

- `test2`: **1 left**;
- `test`: 2 left;
- `yt_holdout`: 1 left.
