# Round 5 (understand the query in parts) · evaluator report

*3 Nov 2026 · Evaluator (did not build the methods) · label round **c4-r5** (dev only) · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. Searches are described by scope and kind only.*

Code: `experiments/eval/score_c4.py` (unchanged). Evaluator-side tools (sheet builder, calibration sample, diagnostics), the sheet, grades and per-search detail are in `data/all/eval_work/r5/` (gitignored). The scorer reads `runs/r5/*` and the references `r4.2/c0x_r*`, `r4.2/d1_r*`, `r4.3/e1_r*` through symlinks in `eval_work/r5/runs/`. No run or method file was touched. Only `dev` was scored: no `yt_holdout`, `test` or `test2` row was scored or read. Aggregates: `r5-eval.json`.

## Bottom line

- **No round-5 arm passes clause 1 against C0.** The finalist stays **C0** (0.482).
- **Best arm: F0** (te lists only for caption-type items, coverage-fair fusion). Dev 0.509 [0.424, 0.595].
  - vs C0: **+0.027 [−0.004, +0.062], 20/14/10**; repeats +0.026, +0.023, +0.031. A near miss: Δ < 0.03, and the lower bound is below 0 on all 20 seeds.
  - **ig +0.067 [+0.020, +0.126], 15/3/4.** This holds on 20 of 20 seeds (lower bound +0.018 to +0.021).
  - **yt −0.014 [−0.042, +0.010], 5/11/6.** The within-YouTube ordering is now exactly C0's: the yt-only projection is 0.487, the same as C0. The whole yt loss is Instagram items crowding into YouTube searches: 3.02 per top 10 at 0.37 relevant, against C0's 2.05 and D1's 2.39.
  - vs D1: −0.011 [−0.029, +0.012], 7/17/20 (yt −0.016, 3/12). Dropping YouTube's te rows did not recover the YouTube loss. It made the crowding worse, as the experimenter cautioned before scoring.
- **F1** (typed-slot rewrite) **does not pass**: −0.007 [−0.032, +0.019], 16/17/11.
  - It splits by scope: ig −0.032 [−0.064, −0.000], 5/11; yt +0.019 [−0.019, +0.057], 11/6.
  - It is unstable across repeats: +0.014, −0.011, −0.023.
- **F2** (creator search): +0.003, 1/0/43. It acted on **one** dev search. Nothing can be concluded from that.
- **F3** (facet boosts): −0.017 [−0.055, +0.005], 6/7/31.
  - yt −0.038, with one search at −0.71. Without that search, F3 is −0.001.
- **F4** (checker): −0.000 [−0.006, +0.004], 6/8/30. It reorders the top 20 almost without effect.
- **F5** (the stack): +0.009 [−0.034, +0.050], 20/19/5.
  - vs E1: **−0.046 [−0.082, −0.010], 13/24/7**. It is significantly worse than the round-4 dev finalist.
- **Clause 2 is available to no arm.** F0 needs the te pass; F1–F5 add LLM calls.
- **Judging:** 279 pooled items, judged blind by the evaluator (14 graded 2, 55 graded 1, 210 graded 0). Cost $0. Unjudged@10 is now 0.00 for every run.

## Method

- **Scoring.**
  - All 21 round-5 files, plus `c0x`, `d1` and `e1`, were scored on dev: 44 searches, 22 `ig` and 22 `yt`.
  - Each search's metrics are averaged over the 3 repeats. CIs are 2,000-sample bootstraps over searches (seed 0 for levels, seed 1 for Δ).
  - Comparisons pair repeat k with repeat k, average each search's Δ over the repeats, then bootstrap. W/L/T uses |Δ| > 0.005.
  - Per-kind rows count a search under every kind it carries, so they overlap.
  - These are the 4.1–4.3 conventions.
- **Pooling.**
  - Every unjudged dev top-10 item over all r5 runs and the references was pooled: **279 items over 33 searches**. In ig searches: 43 Instagram and 93 YouTube items. In yt searches: 109 YouTube and 34 Instagram items.
  - Seed unjudged@10 (c4-m1): F1 0.17, F5 0.16, F3 0.03, F4 0.00–0.01, all others 0.00. F1 and F5 put new items in the top 10 because their query plan has no raw query.
  - Backup before the merge: `evalset.pre_r5.jsonl`. Merged with `judge.py merge`, judge `claude-evaluator-r5`.
- **Blind judging, using 4.1–4.3 conventions.**
  - The sheet was built with the 4.3 builder. It is grouped by search and shuffled within each search, with no run identity or rank shown.
  - Text shown: own text, interactions, duration. **te text was not shown.**
  - Before grading, I read a sample of the existing 2/1/0 grades for every pooled search (label reads only, no run information) to keep the scale consistent:
    - same-topic non-target items on YouTube name searches are 0;
    - shorts lose a grade where the intent rules them out;
    - behaviour searches need the stated behaviour (for example, rewatched);
    - other-platform items are graded by meaning.
  - Grades by item platform: YouTube 11 / 25 / 166, Instagram 3 / 30 / 44.
- **Seed vs pooled** (Δ vs C0, c4-m1 → c4-r5):
  - F1 −0.030 → −0.007; F5 −0.013 → +0.009; F3 −0.019 → −0.017.
  - F0, F2, F4, D1 and E1 did not change. No verdict changed.

## Dev scores (pooled c4-r5, mean of 3 repeats)

| Run | nDCG@10 all [95% CI] | Repeats | ig (spread) | yt (spread) | R@10 | R@50 | MRR | success@5 | P@10 ig / yt | Other-platform share ig / yt | Seed unj@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **c0x (C0)** | **0.482** [0.401, 0.564] | 0.482–0.483 | 0.505 (0.024) | 0.459 (0.026) | 0.162 | 0.288 | 0.777 | 0.864 | 0.655 / 0.545 | 0.46 / 0.21 | 0.00 |
| d1 (ref.) | 0.519 [0.436, 0.604] | 0.507–0.531 | 0.578 (0.019) | 0.460 (0.030) | 0.172 | 0.312 | 0.803 | 0.894 | 0.715 / 0.545 | 0.44 / 0.24 | 0.00 |
| e1 (ref.) | 0.538 [0.459, 0.618] | 0.520–0.547 | 0.578 (0.019) | 0.497 (0.051) | 0.173 | 0.314 | 0.833 | 0.924 | 0.715 / 0.591 | 0.44 / 0.22 | 0.00 |
| **f0** | **0.509** [0.424, 0.595] | 0.504–0.514 | **0.573** (0.015) | 0.445 (0.004) | 0.167 | 0.306 | 0.794 | 0.871 | 0.706 / 0.533 | 0.42 / **0.30** | 0.00 |
| f1 | 0.476 [0.399, 0.554] | 0.459–0.496 | 0.474 (0.055) | **0.477** (0.027) | 0.164 | 0.282 | 0.803 | 0.909 | 0.655 / 0.564 | 0.46 / **0.16** | 0.17 |
| f2 | 0.486 [0.405, 0.568] | 0.482–0.492 | 0.512 (0.005) | 0.459 (0.026) | 0.167 | 0.288 | 0.778 | 0.871 | 0.658 / 0.545 | 0.46 / 0.21 | 0.00 |
| f2n | 0.485 [0.404, 0.568] | 0.481–0.491 | 0.510 (0.007) | 0.459 (0.026) | 0.167 | 0.288 | 0.776 | 0.871 | 0.658 / 0.545 | 0.46 / 0.21 | 0.00 |
| f3 | 0.465 [0.383, 0.548] | 0.461–0.467 | 0.509 (0.023) | 0.421 (0.022) | 0.161 | 0.283 | 0.761 | 0.848 | 0.652 / 0.502 | 0.45 / 0.20 | 0.03 |
| f4 | 0.482 [0.402, 0.563] | 0.481–0.482 | 0.510 (0.019) | 0.454 (0.022) | 0.162 | 0.288 | 0.770 | 0.864 | 0.658 / 0.547 | 0.45 / 0.21 | 0.00 |
| f5 | 0.492 [0.420, 0.566] | 0.484–0.505 | 0.524 (0.032) | 0.459 (0.021) | 0.171 | 0.303 | 0.813 | **0.932** | 0.695 / 0.568 | 0.41 / 0.23 | 0.16 |

The three Instagram single-answer searches still score 0 in every run.

### Per kind, Δ nDCG@10 vs C0 (pooled; n searches)

**Instagram scope**

| Kind (n) | F0 | F1 | F3 | F4 | F5 | F5 − E1 | F0 − D1 |
|---|---|---|---|---|---|---|---|
| topic (9) | +0.06 | −0.05 | +0.00 | +0.00 | +0.01 | −0.05 | −0.00 |
| more_like_this (4) | +0.04 | 0 | 0 | 0 | +0.04 | −0.02 | −0.02 |
| name (4) | −0.00 | −0.03 | +0.03 | +0.00 | −0.06 | −0.05 | +0.00 |
| structure (3) | +0.01 | −0.12 | +0.01 | +0.01 | −0.08 | −0.11 | −0.02 |
| place (2) | +0.04 | −0.05 | +0.01 | 0 | −0.00 | −0.09 | −0.05 |
| said_shown (2) | +0.24 | −0.00 | −0.00 | −0.00 | +0.16 | −0.08 | 0 |
| task (2) | +0.08 | −0.14 | −0.04 | −0.01 | −0.11 | −0.18 | +0.02 |
| vibe (2) | +0.00 | **+0.11** | +0.01 | +0.02 | +0.11 | +0.11 | −0.00 |
| people / time / audio (1 each) | +0.24 / +0.11 / 0 | −0.18 / +0.00 / +0.06 | 0 / 0 / 0 | 0 / 0 / 0 | −0.00 / +0.01 / 0 | −0.24 / −0.14 / 0 | 0 / −0.04 / 0 |

**YouTube scope**

| Kind (n) | F0 | F1 | F3 | F4 | F5 | F5 − E1 | F0 − D1 |
|---|---|---|---|---|---|---|---|
| topic (11) | −0.04 | **+0.06** | −0.08 | −0.01 | +0.01 | +0.00 | +0.01 |
| task (8) | −0.04 | +0.03 | −0.10 | −0.01 | −0.08 | −0.02 | +0.02 |
| structure (5) | −0.04 | **+0.09** | −0.14 | −0.00 | −0.03 | +0.06 | +0.05 |
| name (4) | +0.01 | −0.01 | −0.00 | +0.00 | −0.00 | −0.09 | −0.08 |
| personal (4) | −0.00 | −0.01 | −0.01 | −0.00 | +0.03 | −0.03 | −0.02 |
| time (4) | +0.01 | −0.02 | −0.00 | +0.00 | +0.04 | −0.19 | −0.07 |
| behaviour (3) | +0.00 | +0.04 | −0.01 | −0.00 | **+0.19** | −0.09 | −0.01 |
| vibe (3) | +0.03 | −0.06 | +0.00 | −0.00 | −0.08 | −0.13 | −0.01 |
| more_like_this (2) | −0.01 | 0 | 0 | 0 | −0.01 | −0.02 | −0.02 |
| moment, said_shown (1) | +0.00 | +0.08 | −0.01 | +0.01 | +0.09 | +0.00 | −0.08 |
| people, shown, audio (1) | 0 | −0.02 | 0 | 0 | −0.02 | −0.08 | −0.06 |

## Comparisons (pooled dev labels)

**Adoption rule:** Δ ≥ 0.03 with the paired 95% CI above 0 (clause 1), or Δ ≥ 0.02 with more wins than losses at no extra cost (clause 2). Clause 2 is closed to every arm: F0 needs the te pass, and F1–F5 add LLM calls.

| Comparison | Scope | **Δ nDCG@10** [95% CI] | W/L/T | Per repeat | Δ R@10 | Δ R@50 | Δ MRR | Rule |
|---|---|---|---|---|---|---|---|---|
| **F0 vs C0** | all | **+0.027** [−0.004, +0.062] | 20/14/10 | +0.026, +0.023, +0.031 | +0.005 | +0.017 | +0.018 | fail (near miss) |
| | ig | **+0.067 [+0.020, +0.126]** | 15/3/4 | +0.059, +0.053, +0.091 | +0.010 | +0.038 | +0.039 | |
| | yt | −0.014 [−0.042, +0.010] | 5/11/6 | −0.007, −0.008, −0.028 | −0.001 | −0.003 | −0.003 | |
| **F1 vs C0** | all | −0.007 [−0.032, +0.019] | 16/17/11 | +0.014, −0.011, −0.023 | +0.002 | −0.006 | +0.027 | fail |
| | ig | −0.032 [−0.064, −0.000] | 5/11/6 | −0.014, −0.037, −0.045 | −0.004 | −0.030 | +0.018 | |
| | yt | +0.019 [−0.019, +0.057] | 11/6/5 | +0.043, +0.015, −0.002 | +0.007 | +0.017 | +0.035 | |
| **F2 vs C0** | all | +0.003 [0.000, +0.010] | 1/0/43 | +0.000, +0.001, +0.009 | +0.005 | 0.000 | +0.002 | fail (one search) |
| | ig / yt | +0.007 / 0.000 | 1/0/21 · 0/0/22 | | | | | |
| F2 vs F2n (pick) | all | +0.001 [0.000, +0.003] | 1/0/43 | +0.000, +0.002, +0.001 | 0.000 | 0.000 | +0.002 | same search |
| **F3 vs C0** | all | −0.017 [−0.055, +0.005] | 6/7/31 | −0.015, −0.020, −0.016 | −0.001 | −0.005 | −0.015 | fail |
| | ig | +0.003 [−0.008, +0.017] | 4/2/16 | | | | +0.007 | |
| | yt | −0.038 [−0.107, +0.001] | 2/5/15 | −0.039, −0.034, −0.042 | −0.001 | −0.005 | −0.038 | |
| **F4 vs C0** | all | −0.000 [−0.006, +0.004] | 6/8/30 | −0.001, −0.000, −0.000 | 0.000 | 0.000 | −0.006 | fail |
| | ig / yt | +0.004 [−0.002, +0.011] / −0.005 [−0.012, −0.000] | 4/3/15 · 2/5/15 | | | | | |
| **F5 vs C0** | all | +0.009 [−0.034, +0.050] | 20/19/5 | +0.023, +0.004, +0.001 | +0.009 | +0.014 | +0.037 | fail |
| | ig | +0.019 [−0.026, +0.064] | 11/8/3 | +0.027, +0.009, +0.019 | +0.011 | +0.013 | +0.022 | |
| | yt | +0.000 [−0.074, +0.067] | 9/11/2 | +0.020, −0.002, −0.016 | +0.007 | +0.016 | +0.051 | |
| **F5 vs E1** | all | **−0.046 [−0.082, −0.010]** | 13/24/7 | −0.042, −0.035, −0.062 | −0.002 | −0.011 | −0.020 | significantly worse |
| | ig / yt | −0.055 [−0.097, −0.014] / −0.038 [−0.094, +0.022] | 5/13/4 · 8/11/3 | | | | | |
| F0 vs D1 | all | −0.011 [−0.029, +0.012] | 7/17/20 | −0.012, −0.002, −0.017 | −0.006 | −0.007 | −0.009 | — |
| | ig / yt | −0.006 [−0.015, +0.002] / −0.016 [−0.049, +0.028] | 4/5/13 · 3/12/7 | | | | | |
| F5 vs F0 | all | −0.017 [−0.058, +0.021] | 14/21/9 | | | | | ig −0.049 [−0.093, −0.009]; yt +0.015 |
| F1 vs F0 | all | −0.033 [−0.083, +0.012] | 18/24/2 | | | | | ig −0.099; yt +0.033 |
| E1 vs F0 | all | +0.029 [−0.003, +0.066] | 19/7/18 | | | | | ig +0.006; yt +0.053 |
| D1 vs C0 (ref.) | all | +0.037 [−0.002, +0.078] | 29/8/7 | | | | | as in 4.2 |
| E1 vs C0 (ref.) | all | +0.056 [+0.010, +0.105] | 30/8/6 | | | | | as in 4.3 |

### Robustness

Paired bootstrap lower bound over 20 seeds at 10,000 samples:

| Arm vs base | Δ all | Lower bound, all (seeds > 0) | Δ ig, lower bound (seeds > 0) | Δ yt, lower bound | Top 3 / top 5 share of net gain | Without the best search |
|---|---|---|---|---|---|---|
| **F0 vs C0** | +0.027 | −0.004 to −0.002 (0/20) | **+0.067, +0.018 to +0.021 (20/20)** | −0.014, −0.043 to −0.041 | 74% / 99% | +0.016, lower bound −0.008 |
| F1 vs C0 | −0.007 | −0.033 to −0.032 (0/20) | −0.032, −0.065 to −0.063 (0/20) | +0.019, −0.020 to −0.019 | — | −0.012 |
| F2 vs C0 | +0.003 | 0.000 (0/20) | +0.007 | 0.000 | 100% (one search) | 0.000 |
| F3 vs C0 | −0.017 | −0.055 to −0.053 (0/20) | +0.003 | −0.038, −0.109 to −0.108 | — | −0.020 (without the worst: −0.001) |
| F4 vs C0 | −0.000 | −0.006 to −0.005 (0/20) | +0.004 | −0.005 | — | −0.002 |
| F5 vs C0 | +0.009 | −0.034 to −0.032 (0/20) | +0.019, −0.029 to −0.027 | +0.000 | >100% | +0.003 |
| E1 vs C0 (ref.) | +0.056 | +0.009 to +0.012 (20/20) | +0.073, +0.025 to +0.027 (20/20) | +0.038 | 56% / 73% | +0.042, lower bound +0.003 |

**What drives F0's gain:**
- **The top three wins are all Instagram searches:** said/shown +0.47, people/structure +0.24, task +0.16. These are the same te wins D1 had.
- **The largest losses** are two YouTube task/topic(/structure) searches (−0.14, −0.19) and one Instagram name/structure search (−0.18).
- The top 5 searches give 99% of the net gain.
- **F0's only robust part is its Instagram scope.** That is the round-4 milestone's confirmed component, so F0 adds no new evidence beyond it.

## Mechanisms (top-10 diagnostics, pooled labels, 3 repeats)

Mean per search: items per top 10 @ share relevant. "te" = items holding any te row; "yt te" = YouTube items with a te row.

| Run | ig: own | ig: cross | yt: own | yt: cross | ig: te | yt: te | yt: yt te |
|---|---|---|---|---|---|---|---|
| c0x | 5.44 @ 0.76 | 4.56 @ 0.54 | 7.95 @ 0.59 | 2.05 @ 0.39 | 5.59 @ 0.74 | 3.52 @ 0.51 | 1.47 @ 0.68 |
| d1 | 5.61 @ 0.83 | 4.39 @ 0.57 | 7.61 @ 0.59 | 2.39 @ 0.42 | 5.86 @ 0.82 | 4.20 @ 0.55 | 1.80 @ 0.72 |
| e1 | 5.61 @ 0.83 | 4.39 @ 0.57 | 7.79 @ 0.63 | 2.21 @ 0.45 | 5.86 @ 0.82 | 4.26 @ 0.60 | 2.05 @ 0.76 |
| **f0** | 5.80 @ 0.82 | 4.20 @ 0.55 | 6.98 @ 0.61 | **3.02 @ 0.37** | 5.95 @ 0.81 | 4.36 @ 0.46 | 1.35 @ 0.66 |
| f1 | 5.45 @ 0.75 | 4.55 @ 0.54 | **8.41 @ 0.60** | **1.59 @ 0.36** | 5.64 @ 0.73 | 2.82 @ 0.52 | 1.23 @ 0.73 |
| f3 | 5.47 @ 0.76 | 4.53 @ 0.52 | 8.03 @ **0.53** | 1.97 @ 0.39 | 5.67 @ 0.74 | 3.11 @ 0.46 | 1.14 @ 0.60 |
| f4 | 5.53 @ 0.75 | 4.47 @ 0.55 | 7.91 @ 0.59 | 2.09 @ 0.39 | 5.71 @ 0.74 | 3.58 @ 0.50 | 1.48 @ 0.66 |
| f5 | 5.95 @ 0.79 | 4.05 @ 0.55 | 7.68 @ 0.60 | 2.32 @ 0.45 | 6.21 @ 0.78 | 3.41 @ 0.54 | 1.09 @ 0.72 |

(f2 and f2n equal c0x to two decimals.)

**Own-platform projection** (drop the other platform's items, order kept) vs the 4.1 per-platform controls `c0ig` / `c0yt`:

| Run | ig-only nDCG@10 | vs `c0ig` [CI], W/L | yt-only nDCG@10 | vs `c0yt` [CI], W/L |
|---|---|---|---|---|
| c0x | 0.490 | −0.022 [−0.050, +0.006], 4/12 | 0.487 | +0.011 [−0.002, +0.025], 7/4 |
| d1 | 0.565 | +0.052 [+0.002, +0.108], 15/6 | 0.491 | +0.015 [−0.057, +0.066], 15/4 |
| e1 | 0.565 | +0.052 [+0.002, +0.108], 15/6 | 0.528 | +0.052 [−0.034, +0.133], 17/2 |
| **f0** | **0.568** | **+0.055 [+0.008, +0.110], 15/5** | 0.487 | +0.011 (= C0 exactly) |
| f1 | 0.479 | −0.034 [−0.081, +0.015], 6/11 | 0.492 | +0.016 [−0.020, +0.054], 12/6 |
| f3 | 0.497 | −0.016 [−0.046, +0.014], 5/12 | 0.442 | −0.033 [−0.114, +0.014], 5/7 |
| f5 | 0.551 | +0.039 [−0.023, +0.107], 13/7 | 0.489 | +0.013 [−0.068, +0.084], 14/5 |

### F0: the per-platform rule works within each platform, but it worsens cross-platform crowding

- **Within Instagram, F0 is D1's te gain, slightly cleaner.** The ig-only projection is 0.568, against D1's 0.565 and +0.055 vs `c0ig`.
- **Within YouTube, F0 is C0 exactly.** No titled YouTube item keeps a rankable te row, so the yt-only projection equals C0's 0.487. That removes D1's te reordering among YouTube items, which was slightly positive on dev (+0.015 vs +0.011).
- **The cost is in YouTube searches, which take more Instagram items.**
  - Enriched YouTube items lose their te votes, while Instagram items keep theirs. Instagram items in the yt top 10 rise from C0's 2.05 (D1 2.39) to **3.02**.
  - Those items are 37% relevant, against 61% for the YouTube items they replace.
  - So yt is −0.014 vs C0 and −0.016 vs D1. Topic −0.04, task −0.04 and structure −0.04 vs C0; name and time hold.
- **This is the slot-competition effect of round 4.3 and the milestone, made stronger.** A per-platform te rule must be paired with a fusion that does not let one platform's extra votes cross into the other's searches.

### F1: the typed plan helps YouTube topic and structure searches and hurts Instagram searches; no single slot carries it

- **yt +0.019** (11/6): topic +0.06, structure +0.09, task +0.03; vibe −0.06.
  - F1 lets fewer Instagram items into YouTube searches: 1.59 per top 10 against C0's 2.05. The YouTube items' precision rises slightly, from 0.59 to 0.60.
  - The yt-only projection is +0.016 vs `c0yt`, against C0's +0.011.
- **ig −0.032** (5/11): people/structure −0.18, task −0.14, structure −0.12, topic −0.05; vibe +0.11.
  - The ig-only projection falls to 0.479, from C0's 0.490. Within Instagram, the ordering is worse without the raw query and request words.
- **Unstable:** the repeats are +0.014, −0.011 and −0.023, and the ig spread is 0.055 against C0's 0.024. The slot split varies between nano calls more than qr-v1's plan did.
- **MRR +0.027 and success@5 +0.045:** F1 more often puts one relevant item near the top. P@10 is unchanged on ig and +0.02 on yt.

**Slot split, search × repeat cells** (114 typed dev cells over 38 searches; the 6 more-like-this searches are C0 by construction):

| F1 − C0 per cell | Fired: cells (searches), mean Δ, W/L | Not fired: cells, mean Δ, W/L |
|---|---|---|
| guarded `format` | 37 (21), −0.011, 14/21 | 77, −0.006, 31/32 |
| guarded `tone` | 7 (3, all vibe), **+0.021**, 3/2 | 107, −0.010, 42/51 |
| `request_words` non-empty (removed from BM25) | 61 (32), −0.005, 24/26 | 53, −0.011, 21/27 |
| `behaviour_time` non-empty | 16 (7), −0.006, 7/4 | 98, −0.008, 38/49 |
| `creator_lookup` | 2 (1), +0.087, 1/1 | 112, −0.009, 44/52 |

- **The typed slots do not explain F1's result.** Searches with a format slot do slightly worse than those without (−0.011 vs −0.006).
- Searches whose request words were removed from BM25 do slightly better than those without (−0.005 vs −0.011). That is the expected direction, but the gap is within noise.
- Tone is the only slot with a positive sign, on 3 vibe searches. That matches F1's ig vibe +0.11, but n = 3.
- The yt gain and ig loss come from the whole plan change: topic phrases and expansions instead of the raw query, and no raw-query vector.

### F2: creator search, judged on one search

- On dev, `creator_lookup` fired on **2 of 132 cells, both on the same Instagram said/shown search** (repeats 2 and 3). The other 3 of the experimenter's 5 cells are `yt_holdout` searches, which were not scored.
- On those 2 cells:
  - F2 − C0 = +0.226 per cell (2/0). Averaged over the 3 repeats, that search gains +0.15.
  - F2n − C0 = +0.161 (1/1).
  - The pick adds +0.065 (2/0).
- This shows that the path runs and can put the creator's items in the top 10. It says **nothing** about whether creator search helps in general.
- The `name`/`people` searches, where creator lookup was expected to matter, did not trigger it on dev. Neither did the YouTube searches that describe a channel without naming it. F2 needs a set of creator-lookup searches before it can be judged.

### F3: soft facet boosts mostly lose, and one misread format slot does most of the damage

- F3 was active on 42 cells over 22 searches; outside them it is C0 exactly, as checked.
- **Per active cell: −0.055, 8/15, with P@10 −0.074.**
- **Format slot:** 37 cells, −0.063, 6/14. One YouTube task/topic/structure search had format `list` in all three repeats. There the boost lifted list-titled items that were off-topic, giving −0.71. Without that search, the active-cell mean is **−0.004** (8/12).
- **Tone slot:** 7 cells on 3 vibe searches, **+0.012**, 3/2.
- **Reading:**
  - A boost of 0.008 is about half a rank-1 vote. That is large enough to move many top-300 items into the top 10 whenever a cue matches, and the matched items are not more relevant. YouTube own precision falls from 0.59 to 0.53.
  - A count in the request ("N things") is not a list format. The guard does not distinguish the two.
  - Where the slot is tone, the boost is neutral to slightly positive. The evidence (3 searches) is too thin to claim it.

### F4: the checker barely moves nDCG

- F4 checked 43 cells over 22 searches. The top-20 order changed in 20 cells. Ranks 21+ and the top-20 set equal C0's in every cell, as documented.
- **Per checked cell: −0.0015, 7/9; P@10 +0.007.**
  - Format property: 38 cells, −0.005, 4/9.
  - Tone property: 7 cells on the 3 vibe searches, **+0.020, 3/0**.
- Re-sorting inside the top 20 by yes-share improves the share of relevant items in the top 10 only slightly. The yes answers do not separate relevant from non-relevant items well on format: 40% of items were judged yes on every property.
- As with F3, the only positive sign is on tone, and it rests on 3 searches.

### F5: the stack keeps the intent wins, but loses everywhere else to F1 and F3

- **Per typed cell:**
  - cells where E1's guarded intent acted: 9 cells over 4 searches, **+0.185**, 7/2 (yt behaviour +0.19);
  - creator lookup: 2 cells, +0.37;
  - facet-active cells: 42, **−0.070**, 16/23;
  - more-like-this (F0 lists): 18 cells, +0.025.
- **vs E1 (−0.046):**
  - ig −0.055, 5/13: F1's ig loss (−0.03 to −0.10 vs F0) and F3/F4 on top of F0's ig gain.
  - yt −0.038: F0's crowding, F3's `list` loss (−0.48 on that search) and the missing YouTube te rows. Only yt structure is better (+0.06).
- **vs F0 (−0.017):** ig −0.049, yt +0.015. The slot stages cost Instagram more than intent and F1 add on YouTube.
- The preregistered reasoning that "F3 widens and F4 removes F3's false boosts" did not hold. F4's yes-share re-sort cannot undo F3's boosts, because F3 changes which items reach the top 20.

## Cost and latency (run `meta`; pooled over 3 repeats × 47 typed searches)

| Run | Calls per typed search | Per 1k searches | Total p50 / p95 (s) | Δ p50 / p95 vs C0 | Local p95 |
|---|---|---|---|---|---|
| C0 (`c0x`) | qr-v1 | $0.119 | 1.56–1.62 (per repeat) / ≈ 2.5\* | — | 0.14–0.17 s |
| f0 | qr-v1 (+ te pass, caption-type items) | $0.119 + te | 1.62 / 2.54 | +0.03 / +0.03 | 0.18 s |
| f1 | qs-v1 | $0.164 | 2.33 / 3.24 | **+0.7 / +0.7** | 0.15 s |
| f2 | qr-v1 ∥ qs-v1 + pick | $0.289–0.297† | 2.36 / 3.66 | +0.8 / +1.2 | 0.16 s |
| f2n | qr-v1 ∥ qs-v1 | $0.282† | 2.36 / 3.26 | +0.8 / +0.8 | 0.17 s |
| f3 | qr-v1 ∥ qs-v1 | $0.282† | 2.36 / 3.26 | +0.8 / +0.8 | 0.17 s |
| f4 | qr-v1 ∥ qs-v1 + checker | $0.349–0.368† | 3.11 / **6.31** | +1.5 / **+3.8** | 0.15 s |
| f5 | qs-v1 ∥ qi-v3 + pick + checker | $0.419–0.435 (+ te) | 3.39 / **6.10** | +1.8 / **+3.6** | 0.26 s |

\* C0's meta records local and rewrite times separately. Its total p95 is taken from F0, which uses the same qr-v1 call times, minus F0's ≈ 0.03 s extra local time.
† Overstated by ≈ $0.12 per 1k, because the experiment kept qr-v1 beside qs-v1. A product would merge them into one call.

- F1's +0.7 s is the qs-v1 call itself (2.20 s p50 against qr-v1's ≈ 1.5 s), because the typed schema is longer.
- F4's and F5's p95 is the checker running after the first search, including 9–10 retries over 62 checked cells.
- **Spend:** round 5 is $0.071 OpenAI (experimenter's ledger figure), and **judging cost $0**. OpenAI to date is $0.174 of its $9.50 cap. The whole ledger, both providers, is $3.950.

## Decision

- **Adopted: nothing.** The finalist stays **C0**.
- **Round-5 dev leader: F0.** It fails clause 1 (+0.027, CI touches 0 on every seed), but it is the only arm with a robust part: ig +0.067, lower bound > 0 on 20/20 seeds. That part is the milestone's confirmed component.
- **F1–F5 fail.**
  - F1 trades Instagram for YouTube.
  - F2 cannot be judged (one search).
  - F3 loses (one misread format slot drives most of it).
  - F4 has no effect.
  - F5 is significantly worse than E1.
  - Tone, wherever it fired, was the only slot with a positive sign (F1 +0.021, F3 +0.012, F4 +0.020). That covers 3 vibe searches only, so it is a lead, not a finding.
- **Candidates for held-out scoring (test2 first):**
  1. **C0**, the finalist (always included).
  2. **F0**, the best round-5 arm. Its idea came from the round-4 milestone's per-scope result, so `test` and `yt_holdout` are **not clean for F0 either**. Only `test2` is.
  3. **E1** (optional third), the best dev method overall (0.538; vs F0 +0.029, 19/7, almost all on yt). Its YouTube side failed the milestone. On test2 it would show whether the intent step acts on fresh searches, if test2 has behaviour or time searches.
  - **Not recommended:** F1, F3, F4 and F5 (no dev case), and F2 (untestable on dev).
- **Splits:**
  - `test2` is the clean check for every candidate.
  - `test` (2 scorings left) is a secondary check and contaminated for F0.
  - Keep `yt_holdout`'s last scoring for the final. F0 cannot gain there by construction: its YouTube ordering is C0's, and it adds crowding.
- **Runs needed:** none of the candidates has `test2` runs. They need fresh qr-v1 parses, and qi-v3 for E1, on the test2 file (≈ $0.01). The orchestrator must arrange them, because builders never see test2.
- **Stop rule:** round 5 adopts nothing. If the round-4 count carries over, this is the fourth round in a row without a confirmed win.

## Problems with the runs

1. **F2 was effectively not tested on dev.** `creator_lookup` fired on one dev search (2 of 132 cells). The intended targets did not trigger it: YouTube searches that describe a channel without naming it, and `people` searches.
2. **F1 and F5 had seed unjudged@10 of 0.16–0.17.** The pooling fixed this, and F1's Δ moved from −0.030 to −0.007. The method surfaces new items, so labels before pooling understated it.
3. **F3's mapping treats a stated count as a list format.** That one search accounts for nearly all of F3's loss and for F5's single worst loss (−0.48). This is a design issue, not a run error.
4. **F2–F4's per-1k cost is overstated by ≈ $0.12,** because qr-v1 and qs-v1 both ran. The latency figures are not affected: the calls run in parallel.
5. **F0 keeps 1 YouTube te row** (placeholder title), against the LOG row's "none". This is disclosed and negligible.
6. **The qs-v1 first pass was replaced before any run.** The change was decided from aggregate slot counts only and is disclosed; it is not a scoring issue.
7. **te text is still not shown to the judge.** This slightly disfavours the te arms (F0, F5).
8. **Otherwise the runs behaved as documented.** All 21 files cover 55 searches at depth 1,000.
   - F2/F2n equal C0 exactly on non-lookup searches.
   - F3 equals C0 in the top 300 where no slot is active.
   - F4 keeps the top-20 set and ranks 21+.
   - F1's top 10 equals C0's only on the 8 more-like-this searches.
