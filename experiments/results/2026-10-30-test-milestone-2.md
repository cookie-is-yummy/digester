# Test-split milestone 2 (T2): B4 vs B3 vs instant path vs honest base vs hand baseline

Evaluator round **t2**, 2026-10-30. **Test scoring 3 of 3**, the last one for the whole loop. Nothing was tuned on these numbers.

- Split: **test**, 6 searches (5 typed, 1 more-like-this). Each kind (more_like_this, name, place, task, topic, vibe) occurs **once**, so per-kind values below are single searches. **With n = 6 every CI is wide**; a 1-search swing moves the mean by ~0.02–0.05.
- Labels: scored first on the current labels (**r11**; the test labels are as merged at t1), then the unjudged top 10 of all 11 run files were pooled, judged blind and merged as round **t2**; all runs re-scored once on t2. **Headline = after pooling (t2 labels).**
- Repeats: B4, B3 and honest base have 3 repeats each (repeat k paired with repeat k). The instant path and the hand baseline are single runs, paired with each repeat.
- Aggregates via `experiments/eval/score_multi.py --split test`; paired Δ = per-search Δ averaged over repeats, 2,000-sample bootstrap 95% CI over searches, W/L/T at |Δ| > 0.005. Full numbers in `2026-10-30-test-milestone-2.json`.

## Runs

| Name | Files | What |
| --- | --- | --- |
| **B4** (round-2 finalist candidate) | `test_b4_qrl1_r{1,2,3}` | B3 with the "look first" rewrite (qr-l1: a first-pass search's hashtags/creators/topics fed to the rewrite) |
| **B3** (round-1 finalist) | `test_b3_r{1,2,3}` | LLM rewrite (qr-v1, gpt-5-nano) + tier-1 enrichment lists + HyDE |
| **Instant path** | `test_instant` | B3's search on the raw query: no rewrite, no HyDE (first screen of a two-stage flow) |
| Honest base (reference) | `test_honest_r{1,2,3}` | LLM rewrite, captions only |
| Hand baseline (reference) | `test_handbase` | hand-simulated rewrite (leaked, biased upward; single run) |

## Pooling and judging

Before pooling, unjudged10 was **0.178** for B4 (0.13–0.23 per repeat) and **0.167** for the instant path, above the 0.15 threshold; B3, honest base and hand baseline were already fully judged (0.00) from t1. One pool from all 11 run files: **29 items** over the 5 typed searches (the MLT search had no unjudged top-10 items). Judged blind from the sheet only (no `--extra`). Grades: **7 × 2, 9 × 1, 13 × 0**. Labels backed up to `evalset.pre_t2.jsonl`, merged with judge `claude-evaluator-t2`. After the merge unjudged10 = **0.00** for every run.

## Headline (t2 labels, after pooling)

| System | nDCG@10 mean (range over repeats) [95% CI] | P@10 | MRR | success@5 | R@100 | unjudged10 |
| --- | --- | --- | --- | --- | --- | --- |
| **B4** | **0.527** (0.496–0.554) [0.309, 0.764] | 0.722 | 0.856 | 0.944 | 0.473 | 0.00 |
| **B3** | **0.565** (0.549–0.580) [0.386, 0.776] | 0.750 | 0.972 | 1.00 | 0.488 | 0.00 |
| Instant path (1 run) | 0.528 [0.312, 0.771] | 0.633 | 0.917 | 1.00 | 0.426 | 0.00 |
| Honest base | 0.543 (0.533–0.550) [0.383, 0.741] | 0.739 | 1.000 | 1.00 | 0.431 | 0.00 |
| Hand baseline (1 run) | 0.590 [0.438, 0.757] | 0.800 | 1.000 | 1.00 | 0.436 | 0.00 |

### Paired deltas (t2 labels, n = 6)

| Comparison | Δ nDCG@10 [95% CI] | W/L/T | per repeat | Δ R@100 [95% CI] (W/L/T) |
| --- | --- | --- | --- | --- |
| **B4 vs B3** | **−0.038 [−0.095, +0.010]** | 2/3/1 | −0.049 / −0.071 / +0.005 | −0.015 [−0.036, +0.004] (2/3/1) |
| **B4 vs honest base** | −0.016 [−0.082, +0.049] | 4/2/0 | −0.020 / −0.037 / +0.009 | +0.042 [−0.005, +0.083] (5/1/0) |
| **B3 vs honest base** | +0.023 [−0.010, +0.053] | 4/1/1 | +0.029 / +0.034 / +0.004 | +0.056 [+0.003, +0.103] (5/1/0) |
| **Instant vs B3** | −0.037 [−0.103, +0.046] | 1/4/1 | −0.052 / −0.039 / −0.021 | −0.062 [−0.162, +0.003] (1/4/1) |
| **Instant vs B4** | +0.001 [−0.062, +0.064] | 2/3/1 | −0.002 / +0.032 / −0.026 | −0.047 [−0.146, +0.031] (1/3/2) |
| Instant vs honest base | −0.015 [−0.102, +0.068] | 3/3/0 | −0.022 / −0.005 / −0.017 | −0.006 [−0.125, +0.099] (4/2/0) |
| B4 vs hand baseline | −0.063 [−0.246, +0.068] | 3/3/0 | −0.060 / −0.094 / −0.036 | +0.037 [−0.003, +0.077] (4/2/0) |
| B3 vs hand baseline | −0.025 [−0.169, +0.084] | 4/2/0 | −0.010 / −0.023 / −0.041 | +0.051 [+0.026, +0.079] (5/0/1) |
| Honest base vs hand baseline | −0.047 [−0.186, +0.063] | 3/2/1 | −0.040 / −0.057 / −0.045 | −0.005 [−0.054, +0.045] (2/2/2) |
| Instant vs hand baseline | −0.062 [−0.246, +0.096] | 3/3/0 | — | −0.011 [−0.107, +0.064] (3/3/0) |

### Per kind, nDCG@10 (t2 labels; mean over repeats; one search per kind)

| Kind | B4 | B3 | Instant | Honest base | Hand baseline |
| --- | --- | --- | --- | --- | --- |
| more_like_this | 1.000 | 1.000 | 1.000 | 0.956 | 0.956 |
| name | 0.465 | 0.448 | 0.334 | 0.419 | 0.562 |
| place | 0.159 | 0.313 | 0.205 | 0.292 | 0.651 |
| task | 0.305 | 0.405 | 0.291 | 0.451 | 0.343 |
| topic | 0.780 | 0.796 | 0.748 | 0.711 | 0.651 |
| vibe | 0.452 | 0.429 | 0.591 | 0.427 | 0.376 |

### Per kind, R@100 (t2 labels)

| Kind | B4 | B3 | Instant | Honest base | Hand baseline |
| --- | --- | --- | --- | --- | --- |
| more_like_this | 0.453 | 0.453 | 0.453 | 0.347 | 0.347 |
| name | 0.638 | 0.633 | 0.576 | 0.684 | 0.593 |
| place | 0.458 | 0.444 | 0.417 | 0.375 | 0.375 |
| task | 0.168 | 0.190 | 0.168 | 0.162 | 0.187 |
| topic | 0.504 | 0.565 | 0.598 | 0.415 | 0.537 |
| vibe | 0.614 | 0.640 | 0.342 | 0.605 | 0.579 |

The test split has no single-answer searches, so the single-answer group is reported only on all 22 below.

## Before pooling (r11 labels, for the record)

| System | nDCG@10 mean (range) [95% CI] | R@100 | unjudged10 |
| --- | --- | --- | --- |
| B4 | 0.474 (0.445–0.497) [0.258, 0.728] | 0.451 | 0.178 |
| B3 | 0.565 (0.549–0.580) [0.386, 0.776] | 0.475 | 0.00 |
| Instant path | 0.494 [0.261, 0.752] | 0.418 | 0.167 |
| Honest base | 0.543 (0.533–0.550) [0.383, 0.741] | 0.415 | 0.00 |
| Hand baseline | 0.590 [0.438, 0.757] | 0.420 | 0.00 |

| Comparison (r11) | Δ nDCG@10 [95% CI] | W/L/T |
| --- | --- | --- |
| B4 vs B3 | −0.091 [−0.153, −0.032] | 1/4/1 |
| B4 vs honest base | −0.069 [−0.152, +0.001] | 2/3/1 |
| B3 vs honest base | +0.023 [−0.010, +0.053] | 4/1/1 |
| Instant vs B3 | −0.071 [−0.156, +0.019] | 1/4/1 |
| Instant vs B4 | +0.020 [−0.011, +0.058] | 2/2/2 |

Pooling lifted only the two runs that had unjudged items (B4 +0.053, instant +0.034); the fully judged runs' nDCG@10 did not move (their R@100 shifted slightly as new right answers joined the label set). The pre-pool B4 deficit was about half an artefact of missing judgments; the rest survives pooling.

## All 22 searches (dev + test), t2 labels

Combined run files (dev lists from the dev runs, test lists from the test runs) under `data/eval_work/t2/combined/`; scored with `--split all`. B4 = `e26_qrl1_r{k}` + `test_b4_qrl1_r{k}`; B3 = `e20_hyde_b2_r{k}` + `test_b3_r{k}`; honest base = `e1_rewrite_r{k}` + `test_honest_r{k}`; instant = `e30_instant` + `test_instant`; hand = `baseline` (already holds the identical test lists). **Caveat:** 16 of the 22 are dev searches the methods were chosen on (B4 was adopted on them); only the 6 test searches are held out.

| System | nDCG@10 (range) [95% CI] | P@10 | MRR | success@5 | R@100 | single-answer nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- |
| **B4** | **0.576** (0.570–0.579) [0.469, 0.678] | 0.703 | 0.853 | 0.939 | 0.505 | 0.357 |
| **B3** | **0.569** (0.564–0.576) [0.469, 0.669] | 0.698 | 0.895 | 0.955 | 0.520 | 0.372 |
| Instant path | 0.503 [0.396, 0.614] | 0.600 | 0.869 | 0.955 | 0.470 | 0.363 |
| Honest base | 0.504 (0.489–0.513) [0.415, 0.595] | 0.650 | 0.870 | 0.924 | 0.474 | 0.331 |
| Hand baseline | 0.577 [0.477, 0.671] | 0.732 | 0.898 | 0.955 | 0.495 | 0.305 |

unjudged10 = 0.00 for all on all 22.

| Comparison (22) | Δ nDCG@10 [95% CI] | W/L/T | per repeat | Δ R@100 [95% CI] (W/L/T) |
| --- | --- | --- | --- | --- |
| **B4 vs B3** | **+0.007 [−0.022, +0.038]** | 9/6/7 | +0.003 / +0.005 / +0.013 | −0.015 [−0.049, +0.019] (6/11/5) |
| **B4 vs honest base** | +0.072 [+0.028, +0.120] | 18/4/0 | +0.070 / +0.057 / +0.089 | +0.031 [+0.001, +0.062] (15/6/1) |
| **B3 vs honest base** | +0.065 [+0.028, +0.103] | 17/4/1 | +0.066 / +0.052 / +0.076 | +0.046 [+0.019, +0.073] (13/4/5) |
| Instant vs B3 | −0.066 [−0.117, −0.023] | 4/14/4 | −0.073 / −0.061 / −0.063 | −0.050 [−0.097, −0.006] (3/13/6) |
| Instant vs B4 | −0.073 [−0.129, −0.026] | 4/13/5 | −0.076 / −0.067 / −0.076 | −0.036 [−0.078, +0.017] (3/14/5) |
| Instant vs honest base | −0.001 [−0.041, +0.044] | 9/12/1 | — | −0.005 [−0.050, +0.038] (8/11/3) |
| B4 vs hand baseline | −0.001 [−0.078, +0.070] | 13/7/2 | +0.002 / −0.007 / +0.002 | +0.010 [−0.033, +0.046] (12/8/2) |
| B3 vs hand baseline | −0.008 [−0.094, +0.069] | 14/5/3 | −0.001 / −0.012 / −0.011 | +0.024 [−0.009, +0.058] (13/5/4) |

Per first kind on 22, nDCG@10 (B4 / B3 / instant / honest base / hand): audio (1) 0.000 / 0.000 / 0.048 / 0.055 / 0.000; more_like_this (4) 0.769 / 0.769 / 0.769 / 0.723 / 0.723; name (4) 0.593 / 0.584 / 0.560 / 0.522 / 0.554; people (1) 0.811 / 0.887 / 0.523 / 0.620 / 0.697; place (2) 0.370 / 0.370 / 0.287 / 0.402 / 0.746; said_shown (1) 0.717 / 0.717 / 0.629 / 0.662 / 0.717; task (1) 0.305 / 0.405 / 0.291 / 0.451 / 0.343; topic (6) 0.624 / 0.602 / 0.480 / 0.480 / 0.515; vibe (2) 0.450 / 0.368 / 0.399 / 0.318 / 0.620.

## Cost and latency (from run `meta`, test runs)

| System | Paid cost per 1k searches | Typed search latency |
| --- | --- | --- |
| B4 | $0.149 list, **$0.109** cache-adjusted (mean of 3 repeats) | total p50 2.19 s, p95 2.53 s (first pass p50 0.11 s + rewrite + final search) |
| B3 | $0.118 | p50 2.61 s incl. rewrite (MLT 0.15 s) |
| Instant path | $0 | p50 0.114 s, p95 0.137 s |
| Honest base | $0.118 | p50 2.38 s incl. rewrite |
| Hand baseline | $0 (hand-written parses; not a real system) | p50 0.11 s |

B4 and B3 also carry the one-off full-corpus enrichment cost (te-v1c), reported in earlier rounds.

## Reading

- **B4 does not replicate on test.** −0.038 [−0.095, +0.010] vs B3, 2/3/1, two of three repeats clearly negative. The losses are the single place search (0.159 vs 0.313) and the single task search (0.305 vs 0.405); B4 is slightly ahead on name and vibe. On all 22 searches the dev gain (+0.024 on 16 at r11) shrinks to **+0.007 [−0.022, +0.038], 9/6/7**, with R@100 −0.015 and MRR 0.853 vs 0.895. By the adoption rule (Δ ≥ 0.02 with W > L) B4 does **not** clear the bar on held-out data, and on all 22 it is a tie with B3. The test evidence favours keeping **B3** as the finalist; B4's dev gain looks like noise or dev-specific.
- **B3 vs honest base holds** at +0.023 on test (4/1/1, CI −0.010..+0.053, R@100 +0.056 with CI above 0) and +0.065 [+0.028, +0.103] (17/4/1) on all 22: unchanged from T1.
- **The rewrite is worth about 0.04–0.07 nDCG@10.** The instant path (no rewrite, no HyDE) trails B3 by −0.037 on test (1/4/1, CI spans 0) and by **−0.066 [−0.117, −0.023]** on all 22 (4/14/4), with lower R@100 (−0.050). It ties the honest base on 22 (−0.001) at ~0.11 s vs ~2.4 s and $0. As a first screen in a two-stage flow it is about honest-base quality; the rewrite-backed result should replace it.
- **Hand baseline** is still ahead on test top-of-list (B3 −0.025, B4 −0.063), driven by the one place search; on all 22 B3 and B4 tie it (−0.008, −0.001) with better R@100. It remains biased and not deployable.
- **Pooling matters for new runs:** B4 rose from 0.474 to 0.527 after its 18% unjudged top-10 was judged; the pre-pool −0.091 vs B3 would have overstated the loss.
- Caution: n = 6, one search per kind; one judge (this evaluator) graded the whole 29-item pool; all 11 run files were pooled together so every system is judged on the same terms. This was the last allowed test scoring.

## Rule notes

- This evaluator did not read the Muse export or reports, `muse*.py`, `reference_compare.py`, `gap_flags.py`, method code or method notes before or during judging. The sheet was built without `--extra`. The MLT search contributed no pool items, so no MLT lines needed judging.
- Per-search detail, sheet, grades and combined run files are under `data/eval_work/t2/`, `data/eval_work/pool_t2.json`, `sheet_t2.txt`, `grades_t2.json` (gitignored). Labels backup: `data/evals/labels/evalset.pre_t2.jsonl`.
