# Round 6 (stronger rewrite models, larger embedding model) · evaluator report

*7 Nov 2026 · Evaluator (did not build the methods) · label round **c4-r6** (dev only) · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. Searches are described by scope and kind only.*

Code: `experiments/eval/score_c4.py` (unchanged). The evaluator-side tools (sheet builder, calibration sample, analysis), the sheet, the grades and the per-search detail are in `data/all/eval_work/r6/` (gitignored). The scorer reads `runs/r6/g{1..5}_r*` and `r4.2/c0x_r*` through symlinks in `eval_work/r6/runs/`. No run or method file was touched, and `tmp/` was not read. Only `dev` was scored: no `yt_holdout`, `test` or `test2` row was scored or read. Aggregates are in `r6-eval.json`.

## Bottom line

- **No round-6 arm passes clause 1 against C0.** The finalist stays **C0** (0.482).
- **Best arm: G4** (text-embedding-3-large at 1,024 d, C0's nano rewrites). Dev 0.505 [0.425, 0.587].
  - vs C0: **+0.022 [−0.008, +0.051], 25/12/7**; repeats +0.025, +0.007, +0.035. This is a near miss: Δ < 0.03, and the lower bound is below 0 on all 20 seeds.
  - ig +0.031 [−0.003, +0.060], 16/5/1 (lower bound −0.003 to −0.001, 0/20 seeds). yt +0.014 [−0.034, +0.060], 9/7/6.
  - More-like-this +0.042 (6 searches); typed +0.019.
  - Cost +$0.011 per 1k searches (+9%) plus $0.0043 per 1k items once. Latency +0.1 s at p50 and p95.
- **G5** (3-large + gpt-5.4-mini): +0.014 [−0.011, +0.039], 23/15/6.
  - **ig +0.038 [+0.008, +0.068], 15/5/2.** This is robust: the lower bound is +0.009 to +0.010 on 20/20 seeds, and still +0.004 without the best search.
  - yt −0.009, 8/10.
  - vs G4 −0.008 (yt −0.023); vs G1 **+0.027 [+0.004, +0.049]**, robust (20/20 seeds).
- **Stronger rewrite models alone do not help.**
  - G1 (gpt-5.4-mini) −0.012, 15/16.
  - G2 (gpt-5.5) +0.005, 19/15, at ≈ 95× C0's cost and +2.4 s p50.
  - G3 (escalation) −0.012, 7/9. It equals G1 on the escalated searches, which are where mini does worst.
- **Stronger rewrites do reduce the spread between repeats per search**, but not the aggregate spread (see below).
- **Clause 2 does not apply:** every arm costs more than C0.
- **Judging:** 290 pooled items over 40 searches, judged blind by the evaluator (18 graded 2, 57 graded 1, 215 graded 0). Cost $0. Unjudged@10 is now 0.00 for every run.

## Method

- **Scoring.**
  - All 15 round-6 files and `c0x` were scored on dev: 44 searches (22 `ig`, 22 `yt`; 38 typed, 6 more-like-this).
  - Each search's metrics are averaged over the 3 repeats. CIs are 2,000-sample bootstraps over searches (seed 0 for levels, seed 1 for Δ).
  - Comparisons pair repeat k with repeat k, average each search's Δ over the repeats, then bootstrap. W/L/T uses |Δ| > 0.005.
  - Per-kind rows count a search under every kind it carries, so they overlap.
  - These are the round 4.1–5 conventions.
- **Pooling.**
  - Every unjudged dev top-10 item over all r6 runs was pooled: **290 items over 40 searches**. In ig searches: 44 Instagram and 96 YouTube items. In yt searches: 115 YouTube and 35 Instagram items.
  - Seed unjudged@10 on c4-t2 labels: G5 0.14, G2 0.11, G4 0.09 (ig 0.13), G1 0.06, G3 0.03, C0 0.00.
  - The pool is smaller than the experimenter expected, because earlier rounds had already judged many of the newly surfaced items.
  - Backup before the merge: `evalset.pre_r6.jsonl`. Merged with `judge.py merge`, judge `claude-evaluator-r6`.
- **Blind judging, using the round 4.1–5 conventions.**
  - The sheet was built with the 4.3 builder. It is grouped by search and shuffled within each search, with no run identity or rank shown.
  - Text shown: own text, interactions and duration.
  - Before grading, I read a calibration sample of existing 2/1/0 grades for every pooled search: up to 3 per grade, from labels only, with no run information. The conventions held:
    - behaviour and time searches need the stated behaviour or period (rewatch counts, watch dates);
    - same-topic non-target items on name searches are 0;
    - shorts lose a grade where the intent rules them out;
    - other-platform items are graded by meaning.
  - Grades by scope and item platform (2/1/0):
    - ig: Instagram 12/15/17, YouTube 2/15/79;
    - yt: YouTube 4/13/98, Instagram 0/14/21.
- **Seed vs pooled** (Δ vs C0, c4-t2 → c4-r6):
  - G1 −0.020 → −0.012; G2 −0.008 → +0.005; G3 −0.014 → −0.012;
  - **G4 +0.009 → +0.022; G5 −0.008 → +0.014**;
  - G5 vs G1 +0.012 → +0.027.
  - Pooling moved the 3-large arms most, because they surface the most new items. No verdict changed.
- **Grade sensitivity.** I re-scored with every grade-1 from this round set to 0. The results were:
  - G4 +0.017 (ig +0.023);
  - G5 +0.006 (ig +0.029 [+0.003, +0.057]);
  - G5 vs G1 +0.024 [+0.001, +0.045];
  - G1 −0.018; G2 −0.004.
  - No verdict changed.

## Dev scores (pooled c4-r6, mean of 3 repeats)

| Run | nDCG@10 all [95% CI] | Repeats | ig (spread) | yt (spread) | R@10 | R@50 | R@100 | MRR | success@5 | P@10 ig / yt | Other-platform share ig / yt | Seed unj@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **c0x (C0)** | **0.482** [0.401, 0.564] | 0.482–0.483 | 0.505 (0.024) | 0.459 (0.026) | 0.158 | 0.288 | 0.342 | 0.777 | 0.864 | 0.655 / 0.545 | 0.46 / 0.20 | 0.00 |
| g1 (mini) | 0.470 [0.389, 0.553] | 0.461–0.476 | 0.493 (0.019) | 0.447 (0.018) | 0.159 | 0.290 | 0.346 | 0.757 | 0.864 | 0.656 / 0.539 | 0.44 / 0.21 | 0.06 |
| g2 (gpt-5.5) | 0.487 [0.409, 0.568] | 0.480–0.497 | 0.518 (0.025) | 0.456 (0.033) | 0.169 | 0.299 | 0.353 | 0.793 | 0.856 | 0.665 / 0.564 | 0.48 / 0.24 | 0.11 |
| g3 (escalation) | 0.471 [0.389, 0.554] | 0.469–0.474 | 0.502 (0.010) | 0.439 (0.020) | 0.157 | 0.286 | 0.341 | 0.748 | 0.841 | 0.635 / 0.536 | 0.46 / 0.23 | 0.03 |
| **g4 (3-large)** | **0.505** [0.425, 0.587] | 0.489–0.518 | 0.536 (0.028) | **0.473** (0.059) | 0.148 | 0.296 | 0.350 | **0.827** | **0.871** | 0.688 / **0.577** | 0.46 / **0.16** | 0.09 |
| g5 (3-large + mini) | 0.497 [0.416, 0.581] | 0.496–0.498 | **0.543** (0.011) | 0.450 (0.008) | 0.164 | 0.298 | **0.357** | 0.791 | 0.864 | **0.689** / 0.548 | 0.44 / 0.18 | 0.14 |

The three Instagram single-answer searches still score 0 in every run.

### Per kind, Δ nDCG@10 vs C0 (pooled; n searches; C0 level in brackets)

**Instagram scope**

| Kind (n) [C0] | G1 | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|
| topic (9) [0.58] | −0.02 | −0.01 | −0.02 | +0.02 | +0.03 |
| name (4) [0.55] | −0.05 | +0.05 | −0.01 | **+0.07** | **+0.07** |
| more_like_this (4) [0.69] | 0 | 0 | 0 | **+0.07** | **+0.07** |
| structure (3) [0.60] | **−0.11** | +0.01 | 0.00 | −0.01 | −0.00 |
| vibe (2) [0.21] | +0.07 | −0.02 | +0.03 | +0.02 | +0.03 |
| place (2) [0.49] | −0.02 | +0.07 | +0.00 | **+0.11** | **+0.11** |
| said_shown (2) [0.33] | +0.06 | **+0.19** | +0.03 | −0.00 | +0.04 |
| task (2) [0.48] | −0.00 | −0.01 | −0.00 | +0.01 | +0.01 |
| time / audio / people (1 each) | +0.00 / 0 / −0.13 | +0.01 / +0.02 / −0.12 | +0.00 / 0 / 0 | +0.15 / +0.04 / −0.21 | +0.15 / 0 / −0.10 |

**YouTube scope**

| Kind (n) [C0] | G1 | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|
| topic (11) [0.50] | −0.01 | +0.00 | −0.03 | +0.03 | −0.01 |
| task (8) [0.58] | +0.05 | +0.03 | +0.02 | −0.01 | +0.02 |
| structure (5) [0.62] | +0.01 | +0.02 | −0.01 | +0.02 | −0.02 |
| name (4) [0.65] | −0.07 | −0.08 | −0.07 | −0.03 | −0.01 |
| time (4) [0.32] | **−0.12** | **−0.12** | **−0.12** | −0.07 | **−0.10** |
| personal (4) [0.18] | −0.05 | −0.02 | −0.05 | +0.06 | −0.02 |
| vibe (3) [0.30] | +0.06 | +0.07 | +0.03 | +0.02 | +0.04 |
| behaviour (3) [0.03] | −0.00 | +0.04 | 0.00 | +0.08 | +0.02 |
| more_like_this (2) [0.33] | 0 | 0 | 0 | −0.02 | −0.02 |
| said_shown, moment (1) | +0.00 | +0.01 | +0.00 | **+0.17** | **+0.19** |
| people, shown, audio (1) | +0.03 | +0.04 | +0.03 | −0.09 | −0.09 |

- **yt time −0.12 for every rewrite arm** comes from two searches: a single-answer name/time search and a time/topic search. The stronger models' parses differ from nano's there, and the rewrite's date filters are not used by the search, so better date reading cannot help. G4 loses on the single-answer one too.
- The 3-large gains concentrate in ig name, place and more-like-this, and in one yt said/shown search.

## Comparisons (pooled dev labels)

**Adoption rule:** Δ ≥ 0.03 with the paired 95% CI above 0 (clause 1). Clause 2 (Δ ≥ 0.02, more wins than losses, no extra cost) is closed to every arm: all of them cost more than C0.

| Comparison | Scope | **Δ nDCG@10** [95% CI] | W/L/T | Per repeat | Δ R@10 | Δ R@50 | Δ MRR | Rule |
|---|---|---|---|---|---|---|---|---|
| **G1 vs C0** | all | −0.012 [−0.036, +0.009] | 15/16/13 | −0.006, −0.008, −0.022 | +0.001 | +0.002 | −0.020 | fail |
| | ig | −0.013 [−0.044, +0.016] | 7/9/6 | −0.019, −0.012, −0.007 | | | | |
| | yt | −0.012 [−0.049, +0.022] | 8/7/7 | +0.006, −0.005, −0.037 | | | | |
| **G2 vs C0** | all | +0.005 [−0.027, +0.034] | 19/15/10 | −0.002, +0.016, +0.001 | +0.011 | +0.011 | +0.016 | fail |
| | ig | +0.013 [−0.026, +0.053] | 9/8/5 | +0.012, +0.015, +0.012 | | | | |
| | yt | −0.003 [−0.051, +0.037] | 10/7/5 | −0.016, +0.016, −0.010 | | | | |
| **G3 vs C0** | all | −0.012 [−0.033, +0.007] | 7/9/28 | −0.008, −0.013, −0.014 | −0.001 | −0.002 | −0.028 | fail |
| | ig | −0.003 [−0.025, +0.016] | 4/4/14 | | | | | |
| | yt | −0.020 [−0.056, +0.012] | 3/5/14 | | | | | |
| **G4 vs C0** | all | **+0.022** [−0.008, +0.051] | **25/12/7** | +0.025, +0.007, +0.035 | −0.010 | +0.008 | **+0.050** | fail (near miss) |
| | ig | +0.031 [−0.003, +0.060] | 16/5/1 | +0.041, +0.014, +0.038 | | | | |
| | yt | +0.014 [−0.034, +0.060] | 9/7/6 | +0.010, −0.001, +0.033 | | | | |
| **G5 vs C0** | all | +0.014 [−0.011, +0.039] | 23/15/6 | +0.014, +0.016, +0.013 | +0.006 | +0.010 | +0.014 | fail |
| | ig | **+0.038 [+0.008, +0.068]** | 15/5/2 | +0.024, +0.037, +0.052 | | | | |
| | yt | −0.009 [−0.050, +0.030] | 8/10/4 | +0.005, −0.005, −0.027 | | | | |
| G5 vs G4 | all | −0.008 [−0.034, +0.014] | 16/13/15 | −0.011, +0.009, −0.023 | +0.016 | +0.002 | −0.036 | — |
| | ig / yt | +0.007 [−0.016, +0.028] / −0.023 [−0.070, +0.016] | 9/6/7 · 7/7/8 | | | | | |
| **G5 vs G1** | all | **+0.027 [+0.004, +0.049]** | 20/16/8 | +0.020, +0.024, +0.035 | +0.005 | +0.008 | +0.034 | 3-large helps under mini |
| | ig / yt | **+0.050 [+0.018, +0.085]** / +0.003 [−0.022, +0.031] | 13/6/3 · 7/10/5 | | | | | |
| G2 vs G1 | all | +0.017 [−0.010, +0.045] | 17/14/13 | +0.004, +0.024, +0.023 | +0.010 | +0.009 | +0.035 | — |

### Robustness

Paired bootstrap lower bound over 20 seeds at 10,000 samples:

| Arm vs base | Δ all | Lower bound, all (seeds > 0) | Δ ig, lower bound (seeds > 0) | Δ yt, lower bound | Top 3 / top 5 share of net gain (all) | Without the best search (lower bound) | Drops of best searches to Δ ≤ 0 |
|---|---|---|---|---|---|---|---|
| G1 vs C0 | −0.012 | −0.038 to −0.037 (0/20) | −0.013, −0.044 to −0.042 (0/20) | −0.012, −0.054 to −0.050 | — | −0.015 | — |
| G2 vs C0 | +0.005 | −0.026 to −0.024 (0/20) | +0.013, −0.025 to −0.023 (0/20) | −0.003, −0.050 to −0.047 | 296% / 432% | −0.002 (−0.030) | 1 |
| G3 vs C0 | −0.012 | −0.033 (0/20) | −0.003, −0.025 to −0.024 (0/20) | −0.020, −0.059 to −0.056 | — | −0.014 | — |
| **G4 vs C0** | **+0.022** | −0.007 to −0.006 (0/20) | +0.031, −0.003 to −0.001 (0/20) | +0.014, −0.036 to −0.032 | 66% / 94% | +0.017 (−0.011) | 6 (ig 7) |
| **G5 vs C0** | +0.014 | −0.012 to −0.011 (0/20) | **+0.038, +0.009 to +0.010 (20/20)** | −0.009, −0.050 to −0.048 | 91% / 120% | +0.009 (−0.015); ig +0.028 (**+0.004**) | 4 (ig 8) |
| G5 vs G4 | −0.008 | −0.036 to −0.034 (0/20) | +0.007, −0.017 to −0.015 | −0.023, −0.073 to −0.070 | — | −0.011 | — |
| **G5 vs G1** | +0.027 | **+0.005 to +0.006 (20/20)** | **+0.050, +0.018 to +0.020 (20/20)** | +0.003, −0.023 to −0.022 | 48% / 72% | +0.022 (**+0.002**) | 8 (ig 9) |

- **G4 per repeat:** +0.025 [−0.021, +0.069], +0.007 [−0.025, +0.034] and +0.035 [+0.004, +0.068]. Only repeat 3 alone has a lower bound above 0. Over all 9 repeat pairings (k vs j), Δ is +0.006 to +0.036.
  - The gain is broad on Instagram: 16/5, 3 searches above +0.1. Dropping the best 7 ig searches takes it to ≤ 0.
  - On YouTube it rests on a few searches. The top 3 are 212% of the net, and without the best search yt is +0.001.
- **G5 per repeat:** +0.014, +0.016, +0.013, the most stable arm. Each repeat's CI spans 0 overall.
  - ig: +0.024, +0.037, +0.052. The ig gain survives dropping the best search, with the lower bound still above 0. It takes 8 drops to erase it.
- **G2's small overall gain is carried by a handful of searches.** Without the best search it is −0.002. Its 6 large wins (> +0.1) are offset by 5 large losses.

## Do stronger rewrites reduce the spread between repeats?

| Run | Aggregate nDCG spread, all / ig / yt | Per-search SD over repeats, typed (ig / yt) | Per-search range, typed | Typed searches with range > 0.1 (of 38) | Top-10 Jaccard between repeats, typed | Keyword Jaccard (experimenter, 47 typed) |
|---|---|---|---|---|---|---|
| C0 (nano) | 0.001 / 0.024 / 0.026 | 0.060 (0.058 / 0.061) | 0.138 | 19 | 0.50 | 0.280 |
| G1 (mini) | 0.015 / 0.019 / 0.018 | 0.041 (0.057 / **0.028**) | 0.093 | 15 | 0.56 | 0.469 |
| G2 (gpt-5.5) | 0.017 / 0.025 / 0.033 | **0.039** (0.043 / 0.035) | 0.091 | 11 | 0.56 | 0.556 |
| G3 (composite) | 0.005 / 0.010 / 0.020 | 0.048 (0.053 / 0.043) | 0.110 | 19 | 0.55 | 0.393 |
| G4 (nano, 3-large) | 0.029 / 0.028 / **0.059** | 0.067 (0.071 / 0.063) | 0.152 | 16 | 0.52 | 0.280 |
| G5 (mini, 3-large) | **0.002 / 0.011 / 0.008** | **0.034** (0.042 / 0.027) | **0.078** | **9** | **0.60** | 0.469 |

- **Per search, yes.** The mean per-search SD across repeats falls by about a third with mini (0.060 → 0.041) or gpt-5.5 (0.039).
  - The searches whose nDCG moves by > 0.1 between repeats fall from 19 to 15 (mini) and 11 (gpt-5.5).
  - The top 10 overlaps more between repeats (Jaccard 0.50 → 0.56).
  - This follows the experimenter's keyword Jaccard (0.28 → 0.47 / 0.56).
  - G5 is the most stable arm on every measure.
- **In aggregate, no.** C0's all-searches spread of 0.001 is a cancellation: its ig and yt spreads are 0.024 and 0.026 in opposite directions. G1's and G2's aggregate spreads (0.015, 0.017) are larger, but their scope-level spreads are similar to C0's.
- **G4 is the least stable.** With nano's variable parses, the 3-large vectors make each repeat's top 10 move more, and its yt repeats are 0.460 / 0.450 / 0.509. Part of G4's yt gain is one good repeat.
- **Stability did not buy quality.** G1 is more stable than C0 and worse, and G2 is more stable and level.

## G3 (escalation): escalated vs non-escalated searches

On dev, 21 of 38 typed searches are escalated (9 ig, 12 yt; 55%). The rankings were checked 1,000 deep: G3 equals G1 on all escalated searches and C0 on all others, in every repeat.

| Subset (n) | C0 level | G3 = G1 | G2 | G4 | G5 |
|---|---|---|---|---|---|
| escalated (21) | 0.497 | **−0.024** [−0.067, +0.016], 7/9 | −0.006, 10/8 | +0.025, 12/4 | +0.012, 11/7 |
| not escalated (17) | 0.434 | 0 (= C0) · G1 −0.002, 8/7 | **+0.020**, 9/7 | +0.013, 9/7 | +0.008, 8/7 |

- **The hard rule picks the wrong searches.** Escalated searches are not harder for C0: they average 0.497, against 0.434 for the rest.
- On escalated searches mini is worse than nano (−0.024). On the searches the rule leaves to nano, mini is level (−0.002) and gpt-5.5 is better (+0.020).
- So G3 keeps G1's loss and drops the searches where a stronger model was neutral. With a rule that picked better, it could not beat G1 (−0.012) by much either.

## Mechanisms (top-10 diagnostics, pooled labels, 3 repeats)

Mean per search: items per top 10 @ share relevant.

| Run | ig: own | ig: cross | yt: own | yt: cross |
|---|---|---|---|---|
| c0x | 5.44 @ 0.75 | 4.56 @ 0.53 | 7.95 @ 0.59 | 2.05 @ 0.39 |
| g1 | 5.62 @ 0.73 | 4.38 @ 0.56 | 7.86 @ 0.57 | 2.14 @ 0.43 |
| g2 | 5.15 @ 0.77 | 4.85 @ 0.55 | 7.64 @ 0.58 | 2.36 @ 0.51 |
| g3 | 5.41 @ 0.74 | 4.59 @ 0.51 | 7.74 @ 0.58 | 2.26 @ 0.38 |
| **g4** | 5.39 @ **0.77** | 4.61 @ **0.60** | **8.41** @ 0.60 | **1.59** @ 0.46 |
| g5 | 5.56 @ 0.77 | 4.44 @ 0.59 | 8.17 @ 0.57 | 1.83 @ 0.44 |

- **3-large raises precision on both platforms' items in Instagram searches.** YouTube items in ig searches rise from 0.53 to 0.60 relevant, and Instagram items from 0.75 to 0.77. This is where G4/G5's ig gain comes from: name, place, more-like-this.
- **3-large lets fewer Instagram items into YouTube searches** (2.05 → 1.59 per top 10), and those it keeps are more often relevant (0.39 → 0.46). This is the slot-competition problem of rounds 4.3–5 easing, without any fusion change.
  - The YouTube ordering itself barely improves: own precision is 0.59 → 0.60.
- **Mini under 3-large** (G5 vs G4) gives back some of that: yt own precision falls to 0.57, and yt −0.023 vs G4.
- **gpt-5.5** lets more cross-platform items into both scopes (ig 4.85, yt 2.36), but those it adds are better (yt cross 0.51 relevant). The net is level.
- **MRR:** G4 +0.050 and success@5 +0.007, while R@10 −0.010. G4 puts a relevant item first more often, but it covers slightly fewer of the labelled items in the top 10.

## Cost and latency

Typed searches. Cost uses the per-1k-search figures in `r6-methods.md` (ledger list prices, uncached input price). Latency is from the run `meta`, in the round-6 footing (local + rewrite call(s) + one live query-embedding call). The C0 row is the experimenter's same-runner control, because `c0x`'s own meta predates this latency model.

| Arm | $/1k searches | Extra vs C0 | Δ nDCG@10 vs C0 | **Cost per +0.01 nDCG, per 1k searches** | Total p50 / p95 (s) | Δ p50 / p95 vs C0 |
|---|---|---|---|---|---|---|
| C0 | $0.120 | — | — | — | 1.91 / 2.52–2.84 | — |
| G1 | $1.48 | +$1.36 | −0.012 | no gain | 1.80–1.99 / 2.07–2.33 | ≈ 0 / −0.4 |
| G2 | $11.34 | +$11.22 | +0.005 | **$22.4** | 4.18–4.40 / 5.81–6.04 | **+2.4 / +3.2** |
| G3 (as specified) | $0.94 | +$0.82 | −0.012 | no gain | 3.07–3.18 / 3.86–4.18 | +1.2 / +1.3 |
| G3 (routed, same rankings) | $0.87 | +$0.75 | −0.012 | no gain | 1.85–1.94 / 2.20–2.43 | ≈ 0 / −0.4 |
| **G4** | **$0.131** | **+$0.011** (+ $0.0043 per 1k items once; $0.52 for this library) | **+0.022** | **$0.005** (one-off ≈ $0.24 per point for this library) | 1.98–2.02 / 2.78–2.89 | **+0.1 / +0.1** (local p95 0.21–0.24 s vs 0.16) |
| G5 | $1.49 | +$1.37 | +0.014 (ig +0.038) | $0.98 (ig only: $0.36) | 1.87–2.02 / 2.07–2.55 | ≈ 0 / −0.3 |

- G4 is the only arm whose gain is cheap: about half a cent per point per 1k searches.
- G5's extra over G4 is $1.36 per 1k searches for −0.008.
- G2 costs ≈ 95× C0 per search and adds 2–3 s for a gain that is noise.
- gpt-5.4-mini is no slower than nano at p50 and faster at p95, because nano's p95 calls are slower. So G1's and G5's latency is not a reason against them; their quality is.
- **Spend:** round 6 was $2.385 OpenAI (experimenter's ledger figure), and **judging cost $0**. The OpenAI total is $2.578 of $9.50, and the ledger total is $6.354.

## Decision

- **Adopted: nothing.** The finalist stays **C0**.
- **Round-6 dev leader: G4** (3-large 1,024 d).
  - It fails clause 1: +0.022, and the CI touches 0 on every seed.
  - It is the best arm overall: 25/12 wins, best MRR and P@10.
  - It costs almost nothing more than C0: +$0.011 per 1k searches and +0.1 s.
  - Its ig part (+0.031) is broad but not robust (lower bound −0.003 to −0.001). Its yt part rests on a few searches and one repeat.
- **G5** has the only robust scope-level gain this round: ig +0.038, lower bound > 0 on 20/20 seeds and still > 0 without the best search.
  - Overall it is +0.014, and it is below G4 (−0.008) at 11× G4's cost.
  - Its yt side is −0.009, from mini's YouTube losses.
- **G5 vs G1 (+0.027, robust)** and the G4 diagnostics agree: **the embedding model is the variable that helps.** The rewrite model does not:
  - G1 −0.012;
  - G2 +0.005 at $22 per point;
  - G3 −0.012, and its escalation rule targets the wrong searches.
- **Candidates for one held-out scoring on test2** (2 scorings left; test2 is clean for every round-6 arm):
  1. **C0**, the finalist (always included).
  2. **G4**, the dev leader, at near-zero extra cost. On test2 it tests whether 3-large's gains hold on fresh searches. test2 has 4 `yt` and 6 `both` searches, so the test leans on its fewer-Instagram-in-YouTube effect and its ig-side precision.
  3. **Optional G5.** Its robust part is ig scope, which test2 lacks, except through the Instagram items in `both` searches. It is dominated by G4 on dev. Include it only if a second rewrite model on fresh searches is wanted. Otherwise leave it out.
  - **Not recommended:** G1, G2, G3.
- **Runs needed:** none of the candidates has `test2` runs with 3-large.
  - G4 needs 3-large vectors of C0's test2 query, phrase and HyDE strings (≈ $0.001; C0's nano test2 parses exist in `runs/final2/`).
  - G5 also needs fresh gpt-5.4-mini qr-v1 parses (≈ $0.02).
  - The orchestrator must arrange these, because builders never see test2.
- **Splits:** keep `yt_holdout`'s last scoring for the final. `test` (2 left) is a secondary check.

## Problems with the runs

1. **The runs behaved as documented.**
   - All 15 files cover the 55 searches at depth 1,000.
   - G1–G3 equal C0 on every more-like-this search (Δ 0).
   - G3 equals G1 on escalated searches and C0 elsewhere, 1,000 deep, in all repeats.
   - C0's dev score reproduces round 5 exactly (0.482).
2. **The search ignores the rewrite's filters, by design.** A stronger model's better date reading therefore cannot help time searches. The two yt time searches that lose under every rewrite arm (−0.12 on the kind) do so through changed keywords and phrases, not filters. This limits what G1/G2 could show on time and behaviour searches.
3. **G4 is unstable across repeats on YouTube** (0.460 / 0.450 / 0.509), even though it uses C0's nano parses. The larger vectors amplify the parse variation. Part of its yt gain is one repeat.
4. **The pool was smaller than the experimenter expected** (290, not ≈ 1/3 × 10 × 44 × 5). Many surfaced items were already judged. Seed unjudged@10 was at most 0.15 (G5 ig), but pooling still moved G4 by +0.013 and G5 by +0.022.
5. **A single judge** (this evaluator) produced all 290 new grades. Setting this round's 1s to 0 keeps every verdict (G4 +0.017, G5 ig +0.029 [+0.003, +0.057]).
6. **Cost is booked at the uncached input price.** mini and gpt-5.5 got prompt-cache hits on the shared prefix, so their real per-search cost is lower. That does not change any conclusion: G2 would still be > $10 per 1k searches.
7. **Latency includes a live query-embedding call (≈ 0.3 s).** It is not comparable with earlier rounds' totals, so the C0 row is the experimenter's same-runner control.
8. **One gpt-5.5 call was not logged** (≤ $0.012), as disclosed.
