# Test-split milestone (T1): finalist B3 vs B2 vs honest base vs hand baseline

Evaluator round **t1**, 2026-10-30. **Test scoring 2 of 3** for the whole loop. Nothing was tuned on these numbers.

- Split: **test**, 6 searches (5 typed, 1 more-like-this). Each kind (more_like_this, name, place, task, topic, vibe) occurs **once**, so per-kind values below are single searches. With n = 6 every CI is wide.
- Labels: scored first on **r10**, then pooled, judged blind and merged as round **t1**; all runs re-scored once on t1. **Headline = after pooling (t1 labels).**
- Repeats: B3, B2, honest base and B3 + MLT plan have 3 repeats each (repeat k paired with repeat k); the hand baseline is one run, paired with each repeat.
- Aggregates via `experiments/eval/score_multi.py --split test`; paired Δ = per-search Δ averaged over repeats, 2,000-sample bootstrap 95% CI over searches, W/L/T at |Δ| > 0.005. Full numbers in `2026-10-30-test-milestone.json`.

## Runs

| Name | Files | What |
| --- | --- | --- |
| **B3** (finalist) | `test_b3_r{1,2,3}` | real LLM rewrite (qr-v1, gpt-5-nano) + full-corpus tier-1 enrichment as separate BM25 + vector lists + HyDE |
| B2 | `test_b2_r{1,2,3}` | B3 without HyDE |
| Honest base | `test_honest_r{1,2,3}` | real LLM rewrite, captions only |
| Hand baseline | `test_handbase` | original hand-simulated rewrite (biased; single run) |
| B3 + MLT plan | `test_b3_mltplan_r{1,2,3}` | B3 with the more-like-this LLM plan (only the MLT search differs) |

## Pooling and judging

Before pooling, unjudged10 was 0.42–0.48 for every LLM-rewrite run and 0.28 for the hand baseline, far above the 0.15 threshold, so the r10 numbers are not trustworthy on their own. The unjudged top 10 of all 13 test run files went into one pool: **88 items**, judged blind from the sheet only (no `--extra` enrichment text; the more-like-this lines against the example item in `queries.jsonl`). Grades: **28 × 2, 32 × 1, 28 × 0**. Labels backed up to `evalset.pre_t1.jsonl`, merged with judge `claude-evaluator-t1`. After the merge unjudged10 = **0.00** for every run.

## Headline (t1 labels, after pooling)

| System | nDCG@10 mean (range over repeats) [95% CI] | P@10 | MRR | success@5 | R@100 | unjudged10 |
| --- | --- | --- | --- | --- | --- | --- |
| **B3** | **0.565** (0.549–0.580) [0.386, 0.776] | 0.750 | 0.972 | 1.00 | 0.475 | 0.00 |
| B2 | 0.556 (0.546–0.570) [0.369, 0.778] | 0.739 | 0.963 | 1.00 | 0.473 | 0.00 |
| Honest base | 0.543 (0.533–0.550) [0.383, 0.741] | 0.739 | 1.000 | 1.00 | 0.415 | 0.00 |
| Hand baseline (1 run) | 0.590 [0.438, 0.757] | 0.800 | 1.000 | 1.00 | 0.420 | 0.00 |
| B3 + MLT plan | 0.558 (0.542–0.573) [0.386, 0.758] | 0.750 | 0.972 | 1.00 | 0.477 | 0.00 |

### Paired deltas (t1 labels, n = 6)

| Comparison | Δ nDCG@10 [95% CI] | W/L/T | per repeat | Δ R@100 [95% CI] (W/L/T) |
| --- | --- | --- | --- | --- |
| **B3 vs honest base** | **+0.023 [−0.010, +0.053]** | 4/1/1 | +0.029 / +0.034 / +0.004 | +0.060 [+0.007, +0.107] (5/1/0) |
| **B3 vs B2** (HyDE) | +0.009 [−0.027, +0.054] | 2/3/1 | +0.034 / +0.015 / −0.021 | +0.002 [−0.010, +0.014] (3/2/1) |
| **B3 vs hand baseline** | −0.025 [−0.169, +0.084] | 4/2/0 | −0.010 / −0.023 / −0.041 | +0.055 [+0.029, +0.081] (5/0/1) |
| B2 vs honest base | +0.013 [−0.032, +0.049] | 4/2/0 | −0.004 / +0.019 / +0.025 | +0.057 [+0.002, +0.113] (5/1/0) |
| B2 vs hand baseline | −0.034 [−0.207, +0.085] | 4/2/0 | −0.044 / −0.038 / −0.020 | +0.052 [+0.019, +0.082] (5/1/0) |
| Honest base vs hand baseline | −0.047 [−0.186, +0.063] | 3/2/1 | −0.040 / −0.057 / −0.045 | −0.005 [−0.057, +0.048] (2/2/2) |
| B3 + MLT plan vs B3 | −0.007 [−0.021, 0.000] | 0/1/5 | −0.007 each | +0.002 [0.000, +0.007] (1/0/5) |

### Per kind, nDCG@10 (t1 labels; mean over repeats; one search per kind)

| Kind | B3 | B2 | Honest base | Hand baseline | B3 + MLT plan |
| --- | --- | --- | --- | --- | --- |
| more_like_this | 1.000 | 1.000 | 0.956 | 0.956 | 0.958 |
| name | 0.448 | 0.483 | 0.419 | 0.562 | 0.448 |
| place | 0.313 | 0.205 | 0.292 | 0.651 | 0.313 |
| task | 0.405 | 0.432 | 0.451 | 0.343 | 0.405 |
| topic | 0.796 | 0.758 | 0.711 | 0.651 | 0.796 |
| vibe | 0.429 | 0.456 | 0.427 | 0.376 | 0.429 |

Per kind, R@100 (t1): B3 MLT 0.453, name 0.628, place 0.420, task 0.184, topic 0.543, vibe 0.620; honest base 0.347 / 0.673 / 0.348 / 0.156 / 0.385 / 0.583; hand baseline 0.347 / 0.577 / 0.348 / 0.181 / 0.513 / 0.556.

The test split has no single-answer searches, so the single-answer group is not reported here.

## Before pooling (r10 labels, for the record)

| System | nDCG@10 mean (range) [95% CI] | unjudged10 |
| --- | --- | --- |
| B3 | 0.373 (0.348–0.387) [0.225, 0.556] | 0.44 |
| B2 | 0.374 (0.357–0.394) [0.244, 0.534] | 0.44 |
| Honest base | 0.349 (0.326–0.380) [0.232, 0.500] | 0.44 |
| Hand baseline (1 run) | 0.428 [0.312, 0.552] | 0.28 |
| B3 + MLT plan | 0.369 (0.344–0.384) [0.225, 0.551] | 0.46 |

| Comparison (r10) | Δ nDCG@10 [95% CI] | W/L/T |
| --- | --- | --- |
| B3 vs honest base | +0.024 [−0.023, +0.064] | 4/2/0 |
| B3 vs B2 | −0.001 [−0.046, +0.050] | 2/3/1 |
| B3 vs hand baseline | −0.056 [−0.202, +0.077] | 3/3/0 |
| B2 vs honest base | +0.025 [−0.024, +0.068] | 4/1/1 |
| Honest base vs hand baseline | −0.080 [−0.208, +0.022] | 1/4/1 |
| B3 + MLT plan vs B3 | −0.003 [−0.010, 0.000] | 0/1/5 |

Pooling lifted every system by about 0.17–0.19 and narrowed the gap to the hand baseline, which had the fewest unjudged top-10 items before pooling (0.28 vs ≈ 0.44). Per kind before pooling, B3: MLT 0.489, name 0.211, place 0.306, task 0.179, topic 0.788, vibe 0.263; hand baseline 0.444 / 0.391 / 0.651 / 0.293 / 0.588 / 0.204.

## All 22 searches (dev + test), t1 labels

Combined run files (dev lists from the dev runs, test lists from the test runs) under `data/eval_work/t1/combined/`; scored with `--split all`. **Caveat:** 16 of the 22 are dev searches the methods were chosen on; only the 6 test searches are held out.

| System | Dev runs + test runs | nDCG@10 (range) [95% CI] | P@10 | MRR | success@5 | R@100 | single-answer nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **B3** | `e20_hyde_b2_r{k}` + `test_b3_r{k}` | **0.569** (0.564–0.576) [0.469, 0.669] | 0.698 | 0.895 | 0.955 | 0.514 | 0.372 |
| Honest base | `e1_rewrite_r{k}` + `test_honest_r{k}` | 0.504 (0.489–0.513) [0.416, 0.595] | 0.650 | 0.870 | 0.924 | 0.481 | 0.333 |
| Hand baseline | `baseline` + `test_handbase` | 0.577 [0.477, 0.671] | 0.732 | 0.898 | 0.955 | 0.488 | 0.305 |

unjudged10 = 0.00 for all three on all 22.

| Comparison (22) | Δ nDCG@10 [95% CI] | W/L/T | per repeat | Δ R@100 [95% CI] (W/L/T) |
| --- | --- | --- | --- | --- |
| **B3 vs honest base** | **+0.065 [+0.028, +0.103]** | 17/4/1 | +0.066 / +0.051 / +0.076 | +0.033 [+0.001, +0.062] (13/5/4) |
| **B3 vs hand baseline** | −0.008 [−0.094, +0.069] | 14/5/3 | −0.001 / −0.012 / −0.011 | +0.026 [−0.005, +0.056] (13/4/5) |
| Honest base vs hand baseline | −0.073 [−0.148, −0.009] | 5/12/5 | −0.067 / −0.064 / −0.087 | −0.007 [−0.030, +0.015] (8/6/8) |

Per first kind on 22 (B3 / honest base / hand): audio (1) 0.000 / 0.058 / 0.000; more_like_this (4) 0.769 / 0.723 / 0.723; name (4) 0.584 / 0.522 / 0.554; people (1) 0.887 / 0.620 / 0.697; place (2) 0.370 / 0.402 / 0.746; said_shown (1) 0.717 / 0.662 / 0.717; task (1) 0.405 / 0.451 / 0.343; topic (6) 0.602 / 0.480 / 0.515; vibe (2) 0.368 / 0.318 / 0.620.

## Cost and latency (from run `meta`, mean over repeats)

| System | Paid cost | Typed search p50 incl. rewrite | MLT p50 |
| --- | --- | --- | --- |
| B3 | rewrite ≈ $0.12 / 1k searches (HyDE captions come from the same call) | 2.58 s | 0.17 s |
| B2 | ≈ $0.12 / 1k searches | 2.52 s | 0.17 s |
| Honest base | ≈ $0.12 / 1k searches | 2.38 s | — |
| B3 + MLT plan | ≈ $0.12 / 1k + MLT plan call (run cost $0.0009 vs $0.0006 for 6 searches) | 2.53 s | 0.34 s |
| Hand baseline | $0 (hand-written parses; not a real system) | 0.11 s (no rewrite) | — |

B3 and B2 also carry the one-off full-corpus enrichment cost (te-v1c, reported in earlier rounds), not repeated here.

## Reading

- **B3 beats the honest base on held-out test** in direction and size close to dev: +0.023 nDCG@10 (4/1/1, CI crosses 0 at n = 6) and +0.060 R@100 (CI above 0). On all 22 searches the gain is +0.065 [+0.028, +0.103], 17/4/1. By the adoption rule's second clause (Δ ≥ 0.02, more wins than losses, no extra per-search cost) the test result is consistent with adopting B3 over the honest base; the first clause (CI above 0) is not met on 6 searches alone.
- **HyDE (B3 vs B2) is not confirmed on test:** +0.009, 2/3/1, one repeat negative. Not a regression either; it costs nothing extra per search.
- **The hand baseline is still ahead at the top of the list** on test (−0.025, CI −0.169..+0.084) and roughly tied on all 22 (−0.008); the gap is one search: the single place search (0.651 vs 0.313). B3 wins more searches than it loses against it (4/2 on test, 14/5 on 22) and has clearly better R@100 (+0.055 [+0.029, +0.081] on test). The hand baseline used hand-written parses and is biased upward; it is not a deployable system.
- **MLT plan** changes only the more-like-this search and costs −0.007 there (0/1/5 at the run level). Not confirmed on test.
- Caution: one judge (this evaluator) graded the whole 88-item pool; all 13 run files were pooled together, so every system is judged on the same terms. n = 6.

## Rule notes

- This evaluator did not read the Muse export or reports, `muse*.py`, `reference_compare.py`, method code or method notes before or during judging. The MLT line was judged against the example item looked up in `data/corpus/items.jsonl`.
- Per-search detail, sheet, grades and combined run files are under `data/eval_work/t1/`, `data/eval_work/pool_t1.json`, `sheet_t1.txt`, `grades_t1.json` (gitignored).
