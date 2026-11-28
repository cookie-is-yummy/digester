# Round 7 (cheap classifiers plus the combined package) · evaluator report

*7 Nov 2026 · Evaluator (did not build the methods) · label round **c4-r7** (dev only) · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. Searches are described by scope and kind only; per-kind rows with fewer than 3 searches are left out.*

Code: `experiments/eval/score_c4.py` (unchanged). The evaluator-side tools (sheet builder, calibration sample, analysis), the sheet, the grades and the per-search detail are in `data/all/eval_work/r7/` (gitignored). The scorer reads `runs/r7/{h0,h1,h2,h3,h4,h5,h5b}_r*` and `r4.2/c0x_r*` through symlinks in `eval_work/r7/runs/`. No run or method file was touched, and nothing under `/tmp/claude-0/` was read. Only `dev` was scored: no `yt_holdout`, `test` or `test2` row was scored or read (the run files contain `yt_holdout` searches; they were ignored, including their firing data). Aggregates are in `r7-eval.json`.

## Bottom line

- **No round-7 arm passes clause 1, against C0 or against H0.** The finalist stays **C0** (0.481 on c4-r7).
- **Dev levels (mean of 3 repeats):** C0 0.481, **H0 0.504**, H1 0.505, H2 0.504, H3 0.500, H4 0.507, **H5 0.510**, **H5b 0.516**.
- **Headline per scope:**
  - **Instagram searches gain, robustly.** vs C0: H5 **+0.057 [+0.012, +0.101]**, H5b **+0.087 [+0.034, +0.151]**; both lower bounds > 0 on 20/20 seeds, and both stay > 0 without the best search.
  - **YouTube searches do not.** vs C0: H5 −0.000, H5b −0.018 (8/11). vs H0: H5 −0.014, H5b −0.032. Everything the package adds on top of 3-large costs YouTube searches.
- **H5b vs C0: +0.034 [−0.012, +0.085], 24/15/5.** Δ ≥ 0.03, but the lower bound is below 0 on all 20 seeds, so it fails clause 1. H5 vs C0: +0.028 [−0.012, +0.069], 24/14/6.
- **vs H0, every single part is near zero overall:** H1 +0.002, H2 +0.000, H3 −0.003, H4 +0.004, H5 +0.006, H5b +0.012. Most of the package's gain over C0 is H0's (3-large) +0.022.
- **Where parts fired (vs H0, dev typed cells):**
  - helped: H1's guarded **filters** (3 searches, one large YouTube behaviour win), H3's calibration **when the router reads the platform right** (+0.031 [+0.005, +0.062], 18 searches), H4's creator profiles (1 search, +0.24), H2's **tone** boost (3 searches, +0.015, tiny);
  - hurt: H1's **soft time** (−0.032 per cell, 18 searches), H3 calibration **when the router misreads the platform** (−0.071 [−0.155, −0.001], 7 searches; YouTube −0.104), H3's router-triggered creator search (2 searches, −0.12);
  - nothing: H2's **format** boost (0.000 over 7 searches).
- **All three flagged weaknesses show up in the scores** (section "Flagged weaknesses").
- **Package for the last test2 scoring: H5b**, with C0 and H0 as references. It is the better of H5 / H5b on dev, narrowly. No run isolates a pared-down package, and the te lists do not clearly hurt. Expect it to lose on test2's `yt` searches.
- **Cost:** H5 / H5b $0.294 per 1k (+$0.174 vs C0; $0.062 / $0.051 per +0.01) as run. If qs-v1 were merged into the rewrite call, $0.131 (≈ H0). **Latency:** +0.8 to +1.0 s at p50 and p95 vs C0, all of it the separate qs-v1 call.
- **Judging:** 51 pooled items over 16 searches, judged blind by the evaluator (2 / 11 / 38). Cost $0. Unjudged@10 is now 0.00 for every run.

## Method

- **Scoring.** Every r7 file and `c0x` on dev: 44 searches (22 `ig`, 22 `yt`; 38 typed, 6 more-like-this). Each search's metrics are averaged over the 3 repeats. CIs are 2,000-sample bootstraps over searches (seed 0 for levels, seed 1 for Δ). Comparisons pair repeat k with repeat k and average each search's Δ over the repeats. W/L/T uses |Δ| > 0.005. Per-kind rows count a search under every kind it carries. These are the round 4.1–6 conventions.
- **Pairing.** H1–H5b are paired against `r7/h0_r*` (H0 rebuilt this round; `r6/g4` is not reproducible, see `r7-methods.md`). H0, H5 and H5b are also paired against C0 (`r4.2/c0x_r*`). On dev, `r7/h0` scores exactly as `r6/g4` did (0.505 on c4-r6, 0.504 on c4-r7).
- **Pooling.** Every unjudged dev top-10 item over all 21 r7 files: **51 items over 16 searches** (11 ig, 5 yt). In ig searches: 11 Instagram and 19 YouTube items. In yt searches: 17 YouTube and 4 Instagram items.
  - Seed unjudged@10 on c4-t2b: H5 0.04, H5b 0.02 (ig 0.04), H1 0.02, H3 0.02, H0 / H2 / H4 0.00. The pool is small because rounds 4–6 had already judged most items these arms surface.
  - Backup before the merge: `evalset.pre_r7.jsonl`. Merged with `judge.py merge`, judge `claude-evaluator-r7`.
- **Blind judging, round 4.1–6 conventions.** The sheet was built with the r6 builder: grouped by search, shuffled within each search, no run identity or rank, own text, interactions and duration shown.
  - Before grading, I read a calibration sample of existing 2/1/0 grades for every pooled search (up to 3 per grade, labels only, no run information). The conventions held: behaviour searches need the stated behaviour (rewatch counts); exclusions in a search are honoured (excluded items are 0); same-topic non-target items on name searches are 0; other-platform items are graded by meaning.
  - Grades by scope and item platform (2/1/0): ig: Instagram 1/3/7, YouTube 1/2/16; yt: YouTube 0/3/14, Instagram 0/3/1.
- **Seed vs pooled** (Δ, c4-t2b → c4-r7): H1:H0 +0.000 → +0.002; H3:H0 −0.006 → −0.003; H5:H0 +0.002 → +0.006; H5b:H0 +0.009 → +0.012; H5b:H5 +0.006 → +0.006; H5:C0 +0.025 → +0.028; H5b:C0 +0.031 → +0.034. H0, H2 and H4 do not move. No verdict changed.
- **Grade sensitivity.** With this round's 11 grade-1s set to 0: H5:C0 +0.026 (ig +0.054 [+0.010, +0.098]); H5b:C0 +0.033 (ig +0.084 [+0.031, +0.149]); H5b:H5 +0.007; H3:H0 −0.005 (ig +0.025 [+0.003, +0.051]). No verdict changed.

## Dev scores (pooled c4-r7, mean of 3 repeats)

| Run | nDCG@10 all [95% CI] | Repeats | ig (repeats) | yt (repeats) | typed / MLT | R@10 | R@50 | R@100 | MRR | success@5 | P@10 ig / yt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **c0x (C0)** | **0.481** [0.401, 0.563] | 0.481–0.482 | 0.504 (0.488–0.512) | 0.459 (0.450–0.476) | 0.468 / 0.567 | 0.154 | 0.289 | 0.344 | 0.777 | 0.864 | 0.655 / 0.545 |
| **h0 (= G4)** | **0.504** [0.424, 0.586] | 0.488–0.517 | 0.534 (0.525–0.552) | 0.473 (0.450–0.509) | 0.487 / 0.609 | 0.144 | 0.299 | 0.353 | 0.827 | 0.871 | 0.688 / 0.577 |
| h1 (filters + soft time) | 0.505 [0.429, 0.585] | 0.491–0.513 | 0.529 (0.510–0.551) | **0.482** (0.473–0.498) | 0.489 / 0.609 | 0.143 | 0.299 | 0.354 | 0.837 | 0.886 | 0.676 / **0.603** |
| h2 (facet boosts) | 0.504 [0.425, 0.588] | 0.486–0.521 | 0.534 (0.523–0.550) | 0.474 (0.448–0.514) | 0.487 / 0.609 | 0.144 | 0.299 | 0.354 | 0.824 | 0.871 | 0.691 / 0.579 |
| h3 (router) | 0.500 [0.421, 0.582] | 0.489–0.514 | 0.560 (0.545–0.573) | 0.440 (0.415–0.483) | 0.483 / 0.609 | 0.153 | 0.300 | 0.352 | 0.828 | 0.894 | 0.695 / 0.558 |
| h4 (creator profiles) | 0.507 [0.428, 0.589] | 0.491–0.525 | 0.541 (0.532–0.552) | 0.473 (0.450–0.509) | 0.491 / 0.609 | 0.151 | 0.299 | 0.353 | 0.828 | 0.871 | 0.692 / 0.577 |
| **h5 (package)** | **0.510** [0.434, 0.587] | 0.495–0.529 | 0.561 (0.553–0.568) | 0.459 (0.436–0.498) | 0.494 / 0.609 | **0.155** | 0.299 | 0.354 | **0.842** | 0.902 | 0.689 / 0.585 |
| **h5b (package + te)** | **0.516** [0.439, 0.598] | 0.500–0.541 | **0.591** (0.583–0.602) | 0.441 (0.417–0.479) | **0.506** / 0.580 | 0.152 | **0.318** | **0.372** | 0.828 | **0.909** | **0.715** / 0.579 |

(Full metrics per run and scope, including R@100 and success@5 per scope, are in `r7-eval.json` under `extra`.)

The three Instagram single-answer searches still score 0 in every run.

### Per kind, Δ nDCG@10 (pooled; kinds with ≥ 3 searches; H0 level in brackets)

**Instagram scope**

| Kind (n) [H0] | H1 | H2 | H3 | H4 | H5 | H5b | H0 vs C0 | H5 vs C0 | H5b vs C0 |
|---|---|---|---|---|---|---|---|---|---|
| topic (9) [0.60] | −0.00 | +0.00 | +0.02 | 0 | +0.02 | **+0.08** | +0.02 | +0.04 | **+0.10** |
| more_like_this (4) [0.76] | 0 | 0 | 0 | 0 | 0 | −0.02 | +0.07 | +0.07 | +0.05 |
| name (4) [0.61] | −0.01 | −0.01 | **+0.05** | 0 | **+0.05** | +0.04 | +0.07 | **+0.11** | **+0.10** |
| structure (3) [0.57] | −0.01 | −0.02 | −0.02 | 0 | −0.03 | +0.02 | −0.01 | −0.04 | +0.01 |

**YouTube scope**

| Kind (n) [H0] | H1 | H2 | H3 | H4 | H5 | H5b | H0 vs C0 | H5 vs C0 | H5b vs C0 |
|---|---|---|---|---|---|---|---|---|---|
| topic (11) [0.53] | +0.03 | +0.00 | **−0.06** | 0 | −0.03 | **−0.06** | +0.03 | −0.01 | −0.04 |
| task (8) [0.57] | −0.01 | +0.00 | −0.02 | 0 | −0.03 | **−0.06** | −0.01 | −0.04 | **−0.07** |
| structure (5) [0.63] | −0.02 | +0.00 | **−0.07** | 0 | **−0.09** | **−0.09** | +0.02 | **−0.08** | **−0.07** |
| name (4) [0.62] | −0.04 | 0 | 0 | 0 | 0 | −0.00 | −0.03 | −0.03 | −0.03 |
| personal (4) [0.24] | +0.01 | 0 | −0.00 | 0 | +0.01 | −0.00 | +0.06 | +0.06 | +0.06 |
| time (4) [0.25] | **+0.08** | 0 | 0 | 0 | **+0.11** | **+0.11** | −0.07 | +0.05 | +0.04 |
| behaviour (3) [0.10] | **+0.16** | 0 | −0.00 | 0 | **+0.16** | **+0.16** | +0.08 | **+0.23** | **+0.24** |
| vibe (3) [0.31] | −0.00 | +0.00 | −0.01 | 0 | −0.01 | +0.01 | +0.02 | +0.01 | +0.02 |

- **YouTube time / behaviour gains come from H1's filters** (one behaviour search where the guarded filter keeps a stated behaviour gains ≈ +0.44), and they carry into both packages.
- **YouTube topic, task and structure lose under H3 and both packages.** That is the router's calibration on yt searches it does not read as yt (next sections).
- **Instagram topic is where H5b's te lists help** (+0.08 vs H0; +0.10 vs C0).

## Comparisons (pooled dev labels)

**Adoption rule:** Δ ≥ 0.03 with the paired 95% CI above 0 (clause 1). Clause 2 (Δ ≥ 0.02, more wins than losses, no extra cost) is open only to H1 and H3 against H0 (same cost) and fails on Δ.

| Comparison | Scope | **Δ nDCG@10** [95% CI] | W/L/T | Per repeat | Δ R@10 | Δ R@50 | Δ MRR | Rule |
|---|---|---|---|---|---|---|---|---|
| **H0 vs C0** | all | **+0.022** [−0.008, +0.050] | 25/12/7 | +0.025, +0.007, +0.035 | −0.010 | +0.010 | +0.050 | fail (near miss, = G4) |
| | ig / yt | +0.031 [−0.004, +0.059] / +0.014 [−0.034, +0.060] | 16/5/1 · 9/7/6 | | | | | |
| **H1 vs H0** | all | +0.002 [−0.015, +0.025] | 4/10/30 | +0.007, +0.004, −0.006 | −0.001 | 0.000 | +0.010 | fail |
| | ig / yt | −0.006 [−0.017, +0.004] / +0.009 [−0.023, +0.055] | 2/3/17 · 2/7/13 | | | | | |
| **H2 vs H0** | all | +0.000 [−0.003, +0.003] | 4/1/39 | −0.001, −0.002, +0.004 | 0.000 | 0.000 | −0.004 | fail (no effect) |
| | ig / yt | −0.001 / +0.001 [0.000, +0.003] | 2/1/19 · 2/0/20 | | | | | |
| **H3 vs H0** | all | −0.003 [−0.030, +0.019] | 14/9/21 | −0.009, +0.002, −0.003 | +0.010 | +0.002 | 0.000 | fail |
| | ig | **+0.026 [+0.004, +0.051]** | 11/3/8 | +0.021, +0.038, +0.019 | | | | |
| | yt | −0.033 [−0.071, +0.002] | 3/6/13 | −0.038, −0.035, −0.025 | | | | |
| **H4 vs H0** | all | +0.004 [0.000, +0.011] | 1/0/43 | 0.000, +0.003, +0.007 | +0.008 | 0.000 | +0.001 | fail (fires on 1 search) |
| **H5 vs H0** | all | +0.006 [−0.027, +0.040] | 15/11/18 | −0.001, +0.007, +0.012 | +0.011 | +0.001 | +0.014 | fail |
| | ig / yt | **+0.026 [+0.001, +0.058]** / −0.014 [−0.069, +0.046] | 10/5/7 · 5/6/11 | | | | | |
| **H5b vs H0** | all | +0.012 [−0.034, +0.063] | 18/18/8 | +0.001, +0.012, +0.023 | +0.009 | +0.019 | +0.001 | fail |
| | ig / yt | +0.056 [−0.005, +0.133] / −0.032 [−0.092, +0.033] | 13/7/2 · 5/11/6 | | | | | |
| **H5b vs H5** | all | +0.006 [−0.023, +0.039] | 16/17/11 | +0.002, +0.005, +0.012 | −0.003 | +0.018 | −0.013 | — |
| | ig / yt | +0.030 [−0.019, +0.089] / −0.018 [−0.047, +0.008] | 12/7/3 · 4/10/8 | ig +0.018, +0.029, +0.042 · yt −0.015, −0.019, −0.019 | | | | |
| | MLT | −0.029 (6 searches) | 1/4/1 | | | | | |
| **H5 vs C0** | all | **+0.028** [−0.012, +0.069] | 24/14/6 | +0.024, +0.014, +0.047 | +0.001 | +0.010 | **+0.065** | fail |
| | ig / yt | **+0.057 [+0.012, +0.101]** / −0.000 [−0.065, +0.065] | 16/5/1 · 8/9/5 | | | | | |
| **H5b vs C0** | all | **+0.034** [−0.012, +0.085] | 24/15/5 | +0.025, +0.019, +0.059 | −0.002 | +0.029 | +0.052 | **fail** (Δ ≥ 0.03, CI spans 0) |
| | ig / yt | **+0.087 [+0.034, +0.151]** / −0.018 [−0.085, +0.052] | 16/4/2 · 8/11/3 | | | | | |

### Robustness

Paired bootstrap lower bound over 20 seeds at 10,000 samples:

| Arm vs base | Δ all | Lower bound, all (seeds > 0) | Δ ig, lower bound (seeds > 0) | Δ yt, lower bound | Top 3 / top 5 share of net gain (all) | Without the best search (lower bound) | Drops of best searches to Δ ≤ 0 | All 9 repeat pairings |
|---|---|---|---|---|---|---|---|---|
| H0 vs C0 | +0.022 | −0.007 to −0.006 (0/20) | +0.031, −0.003 to −0.001 (0/20) | +0.014, −0.036 to −0.032 | 66% / 95% | +0.016 (−0.011) | 6 (ig 7, yt 2) | +0.006 to +0.036 |
| H1 vs H0 | +0.002 | −0.015 (0/20) | −0.006, −0.017 (0/20) | +0.009, −0.022 | 673% / 692% | −0.008 | 1 | −0.026 to +0.026 |
| H2 vs H0 | +0.000 | −0.003 (0/20) | −0.001 | +0.001, 0.000 (20/20) | — | −0.000 | 1 | −0.031 to +0.033 |
| H3 vs H0 | −0.003 | −0.030 to −0.028 (0/20) | **+0.026, +0.003 to +0.004 (20/20)** | −0.033, −0.075 to −0.073 | — | −0.009; ig +0.017 (−0.000) | — (ig 6) | −0.028 to +0.026 |
| H4 vs H0 | +0.004 | 0.000 (0/20) | +0.007, 0.000 | 0 | 100% (1 search) | 0.000 | 1 | −0.026 to +0.037 |
| H5 vs H0 | +0.006 | −0.027 to −0.025 (0/20) | **+0.026, 0.000 to +0.001 (20/20, barely)** | −0.014, −0.071 to −0.068 | 322% / 387% | −0.004; ig +0.014 (−0.004) | 1 (ig 5) | −0.023 to +0.041 |
| H5b vs H0 | +0.012 | −0.035 to −0.033 (0/20) | +0.056, −0.009 to −0.005 (0/20) | −0.032, −0.094 to −0.091 | 259% / 330% | 0.000 | 2 (ig 4) | −0.017 to +0.053 |
| H5b vs H5 | +0.006 | −0.024 to −0.023 (0/20) | +0.030, −0.021 to −0.019 (0/20) | −0.018, −0.050 to −0.048 | 308% / 394% | −0.003 | 1 (ig 3) | −0.029 to +0.046 |
| **H5 vs C0** | +0.028 | −0.012 to −0.011 (0/20) | **+0.057, +0.013 to +0.015 (20/20)** | −0.000, −0.066 to −0.063 | 80% / 119% | +0.018 (−0.019); ig +0.046 (**+0.006**) | 5 (ig 8) | +0.013 to +0.048 |
| **H5b vs C0** | +0.034 | −0.014 to −0.012 (0/20) | **+0.087, +0.031 to +0.034 (20/20)** | −0.018, −0.088 to −0.085 | 82% / 112% | +0.023 (−0.020); ig +0.065 (**+0.023**) | 5 (ig 9) | +0.018 to +0.060 |

- **Per repeat vs C0:** H5 +0.024, +0.014, +0.047; H5b +0.025, +0.019, +0.059. Only repeat 3 has a lower bound above 0 (H5 [+0.002, +0.092], H5b [+0.007, +0.115]). Every one of the 9 repeat pairings is positive for both.
- **Large moves:** H5b vs H0 has 7 searches above +0.1 and 7 below −0.1; H5b vs C0 11 and 6. The packages move many searches a lot in both directions. The overall gain vs H0 is carried by 1–2 searches.
- **The Instagram gain vs C0 is broad:** 16/5 (H5) and 16/4 (H5b). It takes 8–9 drops of the best ig searches to erase it.
- **H5b vs H5 is a consistent trade, not noise per scope:** ig is positive in all 3 repeats (+0.018, +0.029, +0.042) and yt negative in all 3 (−0.015, −0.019, −0.019). Overall it nets to about zero (16/17).

## Effect where each part fired vs where it did not (vs H0; dev typed searches × repeats, 114 cells over 38 searches; from run `meta.per_search`)

"Search mean" averages a search's fired cells first; its CI is a bootstrap over the fired searches.

| Part (arm) | Fired: cells / searches (ig / yt) | **Δ where fired, per cell** (W/L/T) | Search mean [95% CI] (W/L) | Δ where not fired, per cell |
|---|---|---|---|---|
| H1, any part | 33 / 21 (9 / 12) | +0.007 (9/13/11) | −0.016 [−0.071, +0.049] (6/10) | 0.000 (equal to H0 on all 81 cells) |
| H1 guarded filter | 7 / 3 (2 / 1) | **+0.150** (3/1/3) | +0.059 (1/1); ig −0.131, yt +0.438 | −0.008 |
| H1 soft time, all | 26 / 18 (7 / 11) | **−0.032** (6/12/8) | −0.029 [−0.066, +0.010] (5/9) | +0.012 |
| · from a guard-dropped window | 20 / 16 | −0.021 (6/10/4) | −0.024 [−0.067, +0.016] | |
| · from the lexicon | 6 / 2 (yt) | −0.065 (0/2/4) | −0.065 [−0.123, −0.008] | |
| · direction new | 16 / 14 | −0.035 (4/9/3) | −0.037 [−0.079, +0.005]; yt −0.063 | |
| · direction old | 10 / 5 | −0.027 (2/3/5) | −0.001 | |
| · on time / behaviour / personal searches | 12 / 6 | −0.025 | −0.007 | |
| · on other searches | 14 / 12 | −0.037 (4/8/2) | −0.040 [−0.087, +0.006] | |
| H2, any facet | 21 / 10 (5 / 5) | +0.002 (7/3/11) | +0.005 [−0.010, +0.018] (5/1) | 0.000 (equal to H0 on all 93) |
| · format | 14 / 7 | −0.005 | 0.000 [−0.020, +0.019] | |
| · tone | 7 / 3 | +0.016 (3/1/3) | +0.015 [+0.001, +0.032] (2/0) | |
| H3 router = creator (creator search) | 6 / 2 (1 / 1) | **−0.119** (2/3/1) | ig +0.051, yt −0.289 | +0.002 |
| H3 calibration, strong (\|q−0.5\| ≥ 0.25) | 42 / 14 (9 / 5) | +0.021 (19/6/17) | +0.021 [−0.038, +0.070]; ig +0.049, yt −0.028 | |
| H3 calibration, weak | 66 / 22 (8 / 14) | −0.010 (13/16/37) | −0.010 [−0.033, +0.012] | |
| H3, router platform = scope | 54 / 18 (11 / 7) | **+0.031** (24/5/25) | **+0.031 [+0.005, +0.062]** (10/2) | |
| H3, router platform = both | 33 / 11 (4 / 7) | +0.002 | +0.002 [−0.017, +0.023] | |
| H3, router platform = the other app | 21 / 7 (2 / 5) | **−0.071** (2/10/9) | **−0.071 [−0.155, −0.001]**; yt −0.104 | |
| H4 creator profiles (qs-v1 lookup) | 2 / 1 (ig) | **+0.236** (2/0/0) | one search | 0.000 (equal to H0 on all 112) |
| H5, creator search (either trigger) | 8 / 3 | +0.010 | +0.055; ig +0.243, yt −0.322 | |
| H5, facet active | 21 / 10 | −0.015 | −0.014; ig +0.042, yt −0.071 | |
| H5, soft time | 26 / 18 | −0.006 | −0.013; ig +0.026, yt −0.038 | |
| H5, filter | 7 / 3 | +0.156 | +0.063 | |
| H5, only calibration fired | 59 / 27 | −0.002 | −0.004 [−0.032, +0.017]; ig +0.015, yt −0.019 | +0.016 (other cells) |
| H5, router platform = scope / both / other app | 60 / 33 / 21 | +0.013 / +0.047 / **−0.072** | other app: −0.072 [−0.154, −0.001]; yt −0.107 | |
| H5b, router platform = scope / both / other app | 60 / 33 / 21 | +0.049 / +0.055 / **−0.125** | other app: −0.125 [−0.239, −0.021]; yt −0.190 | |
| H5b, facet active / soft time | 21 / 26 | −0.056 / −0.030 | yt −0.096 / −0.065 | |

Reading:
- **Helped where fired:** H1's guarded filters (few searches, one large yt win, two small ig losses), H3 calibration when the router reads the platform right, H4 (one search), H2 tone (tiny).
- **Hurt where fired:** H1's soft time (both sources and both directions; worst on non-time searches and on yt), H3 calibration when the router reads the wrong app, H3's router-triggered creator search on its yt search.
- **H2's format boost does nothing** (0.000 over 7 searches). With a +0.008 boost on centred probabilities, it rarely changes a top 10.
- **Inside the packages the parts interact.** Facet and soft-time cells are worse in H5 / H5b than alone, because on those same yt searches calibration and the te lists also act. Fired-subset numbers for the packages are therefore not separable effects.
- **The sanity checks hold on dev:** H1, H2 and H4 equal H0 1,000 deep on every typed cell where they did not fire (81/81, 93/93, 112/112). H1–H5 equal H0 on all more-like-this cells (18/18).

## Flagged weaknesses: do they show in the scores?

1. **Router platform head (0.55 on synthetic data).** **Yes, and it is the largest single loss.**
   - On dev typed searches, the router's platform argmax is: ig searches → ig 12, both 4, yt 2; **yt searches → yt 8, both 7, ig 5**. Mean q_ig is 0.705 on ig searches and 0.404 on yt searches.
   - On the 7 dev searches read as the other app (5 of them yt), calibration costs **H3 −0.071 [−0.155, −0.001], H5 −0.072, H5b −0.125** (yt: −0.104 / −0.107 / −0.190).
   - Where the read is right it gains +0.031 [+0.005, +0.062]. The router helps Instagram searches (ig +0.026, robust) and hurts YouTube searches (−0.033) because it reads Instagram searches much better.
2. **H1's soft-time boosts mostly come from undated "new" windows.** **Yes.** Of 26 dev soft-time cells, 20 come from a guard-dropped window and 16 are "new". Soft time loses where it fires: −0.032 per cell overall, −0.035 for "new", −0.040 per search on searches with no time / behaviour / personal kind. The 2 lexicon searches lose too (−0.065). H1's small yt gain is its filter on one behaviour search, not soft time.
3. **H5b adds Instagram items to yt searches.** **Yes.**
   - Instagram items per yt top 10: H0 1.59, H5 1.61, **H5b 2.27** (C0 2.05). They are a bit more often relevant (0.49 vs 0.48), but they displace YouTube items: 8.39 → 7.73 per top 10.
   - H5b vs H5 on yt: −0.018, 4/10, negative in every repeat. On more-like-this: −0.029, 1/4.

## Mechanisms (top-10 diagnostics, pooled labels, 3 repeats)

Mean per search: items per top 10 @ share relevant.

| Run | ig: own | ig: cross | yt: own | yt: cross |
|---|---|---|---|---|
| c0x | 5.44 @ 0.75 | 4.56 @ 0.53 | 7.95 @ 0.59 | 2.05 @ 0.39 |
| h0 | 5.39 @ 0.77 | 4.61 @ 0.60 | 8.41 @ 0.60 | 1.59 @ 0.46 |
| h1 | 5.52 @ 0.77 | 4.48 @ 0.56 | **8.50 @ 0.63** | 1.50 @ 0.47 |
| h2 | 5.35 @ 0.77 | 4.65 @ 0.60 | 8.44 @ 0.60 | 1.56 @ 0.46 |
| h3 | **6.38** @ 0.71 | 3.62 @ **0.67** | 8.36 @ 0.58 | 1.64 @ 0.46 |
| h4 | 5.42 @ 0.77 | 4.58 @ 0.60 | 8.41 @ 0.60 | 1.59 @ 0.46 |
| h5 | 6.44 @ 0.71 | 3.56 @ 0.65 | 8.39 @ 0.60 | 1.61 @ 0.48 |
| h5b | **6.82 @ 0.76** | 3.18 @ 0.61 | **7.73** @ 0.61 | **2.27** @ 0.49 |

- **Calibration's Instagram-side gain is a mix shift.** In ig searches it swaps about one YouTube item per top 10 for an Instagram one. The YouTube items it keeps are more precise (0.60 → 0.67), and the added Instagram items are a little less precise (0.77 → 0.71). It does not cut Instagram items in yt searches (1.59 → 1.64), as the experimenter predicted.
- **H5b's te lists add precise Instagram items to ig searches** (6.82 @ 0.76), and the same lists push Instagram items into yt searches.
- **Spread:** per-search SD over repeats is about the same for every arm (typed 0.060–0.070; C0 0.060, H0 0.067, H5 0.066, H5b 0.068). H5b's yt SD is the highest (0.077). Top-10 Jaccard between repeats is 0.48–0.52. The classifiers are deterministic, but the nano parses still drive repeat variation.

## Cost and latency

Typed searches, from the run `meta` (round-6/7 footing: local + rewrite call(s) + one live query-embedding call). C0's row is round 6's same-runner control ($0.120 per 1k; p50 1.91 s, p95 2.52–2.84 s), because `c0x`'s own meta predates this latency model.

| Arm | $/1k searches | Extra vs C0 | Δ nDCG@10 vs C0 | **Cost per +0.01 nDCG, per 1k searches** | Total p50 / p95 (s) | Δ p50 / p95 vs C0 |
|---|---|---|---|---|---|---|
| C0 | $0.120 | — | — | — | 1.91 / 2.52–2.84 | — |
| H0 | $0.131 | +$0.011 | +0.022 | $0.005 | 1.99–2.04 / 2.56–2.92 | +0.1 / +0.1 |
| H1 | $0.131 | +$0.011 | +0.024 | $0.005 | 1.99–2.04 / 2.55–2.93 | +0.1 / +0.1 |
| H2 | $0.294 (merged $0.131) | +$0.174 | +0.023 | $0.076 (merged $0.005) | 2.62–2.86 / 3.30–3.82 | +0.7–1.0 / +0.8–1.0 |
| H3 | $0.131 | +$0.011 | +0.019 | $0.006 | 1.99–2.05 / 2.56–2.92 | +0.1 / +0.1 |
| H4 | $0.294 (merged $0.131) | +$0.174 | +0.026 | $0.067 (merged $0.004) | 2.61–2.84 / 3.30–3.83 | +0.7–0.9 / +0.8–1.0 |
| **H5** | $0.294 (merged $0.131) | +$0.174 | +0.028 | **$0.062** (merged $0.004) | 2.70–2.85 / 3.30–3.82 | +0.8–0.9 / +0.8–1.0 |
| **H5b** | $0.294 (merged $0.131) + te pass $0.18 per 1k caption-type items once | +$0.174 | +0.034 | **$0.051** (merged $0.003) | 2.71–2.89 / 3.33–3.88 | +0.8–1.0 / +0.8–1.0 |

- **All extra latency in H2 / H4 / H5 / H5b is the separate qs-v1 call.** Local search adds only +0.06 s (H5) and +0.09 s (H5b) at p95. "Merged" is the experimenter's estimate if qs-v1's fields went into the qr-v1 call; it was not measured.
- **One-off costs:** router training searches $0.257 (this round); the te pass for H5b's Instagram rows already exists (round 4). For a new library it would be ≈ $0.18 per 1k caption-type items.
- Against H0, H5 buys +0.006 for +$0.164 per 1k and +0.8 s; H5b +0.012 for the same, plus the te pass.
- **Spend:** round 7 $0.258 OpenAI (experimenter's ledger figure); **judging $0**. OpenAI $2.882 of $9.50; ledger $6.657.

## Decision

- **Adopted: nothing. The finalist stays C0.**
  - H5b vs C0 is +0.034, but the CI spans 0 on all 20 seeds.
  - H5 vs C0 is +0.028, and fails the same way.
  - Against H0, no part and no package is distinguishable from 0 overall.
- **What the round shows:**
  - **3-large (H0) remains the bulk of every gain.** Over H0, the classifiers add little:
    - Instagram searches gain robustly from the router's calibration (+0.026) and from te lists in the package (H5b ig +0.056 vs H0);
    - YouTube searches lose, from the router's weak platform reading and from te lists crowding.
  - **Useful parts:** H1's guarded filters (stated behaviours, kept windows) and H4's creator profiles. Both fire on very few dev searches.
  - **Parts to drop or fix:**
    - **H1's soft time:** it loses where it fires, mostly through undated "new" windows on non-time searches.
    - **H2's format boost:** no effect at this strength.
    - **H3's router-gated creator search:** loses on its yt search.
    - **H3's calibration on low-confidence platform reads:** it loses −0.07 to −0.13 where the platform is misread.
- **Package for the last `test2` scoring: H5b** (`r7/h5b` config), with **C0** and **H0** as references.
  - **Why H5b and not H5:**
    - H5b is the better of the two on dev: 0.516 vs 0.510, ahead in all 3 repeats, typed +0.012, R@50 +0.018. It is the only arm with Δ ≥ 0.03 vs C0, and its ig gain vs C0 is the most robust of the loop (lower bound +0.031 to +0.034, still +0.023 without the best search).
    - The preregistered rule (LOG Y7-H5b) sends the better of the two.
    - A pared-down package would need a part that clearly hurts and a run without it. The clearly harmful parts (misread calibration, soft time) sit inside both packages, and no run removes them. The te lists that separate H5b from H5 do not clearly hurt overall: +0.006, 16/17, yt CI spans 0.
  - **Risk, stated in advance:**
    - test2 has 4 `yt` and 6 `both` searches and no `ig` scope. H5b's strength (ig) is tested only through the Instagram items of `both` searches, while its weakness (yt: −0.018 vs H5, −0.032 vs H0, all repeats negative) is tested directly.
    - Round 5's F0 (the same te lists) went yt −0.049, both +0.040 on test2.
    - Expect H5b to lose to H0 on test2's yt searches. Whether it wins overall depends on the `both` searches and on how the router reads test2's platforms.
  - If the orchestrator would rather test the cheaper, simpler package, H5 is the fallback. On dev it is 24/14 vs C0, with ig robust (+0.057), yt level, no te pass, and better more-like-this.
- **Runs needed for test2** (orchestrator, builders never see test2): C0's test2 qr-v1 parses (exist), fresh qs-v1 parses (≈ $0.01), 3-large vectors of the strings (≈ $0.001), 3-small vectors for H5b's te dense lists, then `c7_search.py --configs h0 h5b` with the test2 CLI in `r7-methods.md`. `yt_holdout` has 1 scoring left for the same package; it was not scored here.

## Problems with the runs

1. **The runs behaved as documented.** All 21 files cover the 55 searches at depth 1,000. On dev, H1 / H2 / H4 equal H0 exactly wherever their parts did not fire, and H1–H5 equal H0 on every more-like-this search. H0 reproduces G4's dev score exactly (0.505 on c4-r6), although its rankings differ from `r6/g4` in the deep tail (the experimenter's float16 explanation is consistent with that).
2. **Firing is sparse on dev.**
   - H4 fires on 1 dev search and H3's creator gate on 2. H1's filter fires on 3, H2's tone on 3.
   - The "where fired" numbers for these parts are single-search anecdotes, not findings.
   - Fire counts here are lower than in `r7-methods.md` because that note also counts `yt_holdout` searches.
3. **Calibration fires on every typed search,** so H3, H5 and H5b change most top 10s. Their per-part effects inside the packages cannot be separated.
4. **The router also over-predicts behaviour_time on dev** (15 of 38 typed searches). This is harmless today, because no part reads the type except the creator gate.
5. **H6 was not run** (PyTorch install), as the brief allows.
6. **The pool was small** (51 items). A single judge (this evaluator) produced all the new grades. Setting this round's 1s to 0 changes no verdict.
7. **Latency includes a live query-embedding call** and the qs-v1 call at its original uncached seconds. It is not comparable with rounds before 6, so the C0 row is round 6's same-runner control.
8. **The experimenter's own slip** (reading their own preregistration draft back from a scratch file) does not affect any run or score.
