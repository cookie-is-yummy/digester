# Round r3: free experiments 2–8 against the honest base

Evaluator round r3, 2026-10-30. Split: **dev** (16 searches). Aggregates only.

The base is the real gpt-5-nano rewrite (qr-v1), three repeats `e1_rewrite_r{1,2,3}`. Each experiment has three runs. Repeat k is scored against base repeat k. Experiment 6 is a single run, scored against each of the three base repeats.

## How to read these numbers

- **nDCG@10** is the mean over the three repeats. The CI is a bootstrap over searches of each search's repeat-averaged nDCG@10.
- **Δ** is computed per search: average the search's paired difference over the three repeats, then take the mean over searches. The CI is a 2,000-sample bootstrap over searches.
- **W/L/T** counts searches whose Δ is above +0.005, below −0.005, or in between.
- The helper that computes all of this is `experiments/eval/score_multi.py`.

## Labels

- **No run met the pooling threshold.** On r2 labels, no run had `unjudged10` above 0.15. The highest was 0.119 (experiment 8, repeat 3), and most runs were between 0.02 and 0.10.
- **I pooled anyway.** Unjudged items count as non-relevant, so even a small residue biases the comparison against new methods. I therefore pooled every unjudged top-10 item from all 19 experiment runs into one pool: **110 items** across 12 searches. No more-like-this lines were in the pool.
- **Judging was blind.** I graded from the sheet content only. Grades were 2 / 1 / 0 = **6 / 21 / 83**. I merged them as round **r3** (judge `claude-evaluator-r3`). The backup is `data/evals/labels/evalset.pre_r3.jsonl`.
- **After the merge, `unjudged10` is 0.00 for every run in this round and for the base repeats.**
- This judge did not read the Muse export, the Muse reports, the Muse eval scripts or the method code before judging. For ambiguous searches, I calibrated against grades already in the label set, so that borderline cases are graded consistently across rounds.

## Base on r3 labels

**Honest base (real rewrite, 3 repeats): nDCG@10 0.491** [0.386, 0.600], repeats 0.497 / 0.507 / 0.470. Other metrics:

| P@10 | MRR | R@100 | success@5 |
| --- | --- | --- | --- |
| 0.617 | 0.821 | 0.491 (0.488–0.493) | 0.896 |

Single-answer group:

| nDCG@10 | MRR | R@100 |
| --- | --- | --- |
| 0.333 | 0.470 | 0.667 |

On r2 labels the base was 0.496. The base moves down slightly because the r3 pool added relevant items to the ideal ranking that the base does not retrieve.

## All experiments (r3 labels)

| # | Experiment | nDCG@10 mean (range) [CI] | Δ vs base [paired 95% CI] | W/L/T | Δ per repeat | P@10 | MRR | R@100 | success@5 | Single-answer nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | Base (real rewrite) | 0.491 (0.470–0.507) [0.386, 0.600] | — | — | — | 0.617 | 0.821 | 0.491 | 0.896 | 0.333 |
| 2 | PRF from fused list | 0.466 (0.451–0.480) [0.351, 0.581] | −0.025 [−0.095, +0.020] | 8/4/4 | −0.046 / −0.027 / −0.002 | 0.627 | 0.787 | 0.493 | 0.875 | 0.147 |
| 3 | BM25 RM3 feedback | 0.492 (0.469–0.507) [0.376, 0.609] | +0.000 [−0.031, +0.027] | 7/5/4 | +0.002 / +0.000 / −0.001 | 0.602 | 0.791 | 0.491 | 0.896 | 0.299 |
| 4 | Per-phrase RRF (dense) | 0.477 (0.466–0.483) [0.367, 0.587] | −0.014 [−0.063, +0.018] | 5/6/5 | −0.031 / −0.024 / +0.013 | 0.621 | 0.805 | 0.495 | 0.917 | 0.216 |
| 5 | HyDE vector mix | 0.505 (0.496–0.520) [0.394, 0.616] | +0.014 [−0.020, +0.050] | 8/4/4 | +0.023 / −0.007 / +0.026 | 0.652 | 0.817 | 0.489 | 0.875 | 0.243 |
| 6 | Rewrite union (×3) | 0.519 (single run) [0.402, 0.639] | **+0.028 [−0.024, +0.078]** | **10/2/4** | +0.022 / +0.012 / +0.049 | 0.669 | 0.871 | 0.504 | 0.938 | 0.225 |
| 7 | Capped interaction prior | 0.489 (0.480–0.494) [0.382, 0.599] | −0.003 [−0.031, +0.019] | 8/4/4 | −0.005 / −0.013 / +0.010 | 0.625 | 0.808 | 0.490 | 0.917 | 0.261 |
| 8 | Same-creator expansion | 0.503 (0.488–0.516) [0.392, 0.617] | +0.011 [−0.022, +0.044] | 8/5/3 | −0.010 / −0.002 / +0.046 | 0.625 | 0.814 | 0.490 | 0.896 | 0.304 |

`unjudged10` is 0.00 for all of these rows.

Several rows have more wins than losses but a mean Δ at or below zero (experiments 2 and 7). In those runs, many small wins are outweighed by a few large losses on single searches.

## R@100 (r3 labels)

Δ is the per-search mean over repeats, with a paired bootstrap CI.

| # | R@100 mean | Δ R@100 [95% CI] | W/L/T | Δ per repeat |
| --- | --- | --- | --- | --- |
| — | Base 0.491 | — | — | — |
| 2 | 0.493 | +0.002 [−0.003, +0.008] | 4/2/10 | −0.002 / +0.004 / +0.005 |
| 3 | 0.491 | +0.000 [−0.009, +0.009] | 3/3/10 | −0.003 / −0.002 / +0.005 |
| 4 | 0.495 | +0.004 [−0.007, +0.020] | 3/4/9 | −0.001 / +0.010 / +0.004 |
| 5 | 0.489 | −0.002 [−0.016, +0.011] | 5/4/7 | −0.001 / +0.005 / −0.010 |
| 6 | 0.504 | +0.013 [−0.002, +0.031] | 5/3/8 | +0.013 / +0.016 / +0.011 |
| 7 | 0.490 | −0.001 [−0.006, +0.003] | 2/2/12 | +0.001 / −0.005 / −0.000 |
| 8 | 0.490 | −0.000 [−0.001, +0.000] | 0/1/15 | −0.001 / +0.000 / −0.000 |

No experiment moves recall meaningfully. The two expansion methods (3, RM3 feedback; 8, same-creator) were preregistered for R@100 gains and show none.

## By search kind (r3 labels, nDCG@10, mean over repeats)

Counts are in brackets. Kinds with n = 1 are anecdotes.

| Kind | Base | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| topic (5) | 0.439 | 0.457 | 0.441 | 0.448 | 0.476 | **0.520** | 0.459 | 0.477 |
| name (3) | 0.556 | 0.538 | 0.522 | 0.574 | 0.534 | 0.548 | 0.548 | **0.614** |
| more_like_this (3) | 0.645 | 0.645 | 0.645 | 0.645 | 0.645 | 0.645 | 0.645 | 0.645 |
| audio (1) | 0.058 | 0.066 | 0.047 | 0.047 | 0.000 | 0.086 | 0.068 | 0.025 |
| people (1) | 0.620 | 0.687 | 0.537 | 0.684 | 0.767 | **0.842** | 0.634 | 0.576 |
| place (1) | 0.513 | 0.455 | 0.582 | 0.475 | 0.514 | 0.511 | 0.516 | 0.520 |
| said_shown (1) | 0.662 | 0.184 | 0.741 | 0.323 | 0.535 | 0.440 | 0.497 | 0.511 |
| vibe (1) | 0.210 | 0.235 | 0.252 | 0.210 | **0.353** | 0.248 | 0.229 | 0.249 |

More-like-this searches are identical to the base in every experiment, because every method here changes the typed path only.

R@100 by kind:

| Kind | Base | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| topic (5) | 0.532 | 0.543 | 0.542 | 0.553 | 0.540 | 0.581 | 0.525 | 0.531 |
| name (3) | 0.625 | 0.621 | 0.607 | 0.605 | 0.622 | 0.612 | 0.627 | 0.623 |
| more_like_this (3) | 0.416 | 0.416 | 0.416 | 0.416 | 0.416 | 0.416 | 0.416 | 0.416 |
| audio (1) | 0.500 | 0.500 | 0.500 | 0.500 | 0.417 | 0.500 | 0.500 | 0.500 |
| people (1) | 0.382 | 0.382 | 0.375 | 0.382 | 0.375 | 0.417 | 0.382 | 0.382 |
| place (1) | 0.168 | 0.152 | 0.178 | 0.166 | 0.174 | 0.144 | 0.168 | 0.168 |
| said_shown (1) | 0.750 | 0.750 | 0.750 | 0.750 | 0.750 | 0.750 | 0.750 | 0.750 |
| vibe (1) | 0.271 | 0.281 | 0.271 | 0.294 | 0.290 | 0.267 | 0.274 | 0.274 |

## Single-answer group (r3 labels)

The group is hk_tailor, instant_pot and gun_trend, scored as one group of 3.

| | nDCG@10 | MRR | R@100 |
| --- | --- | --- | --- |
| Base | 0.333 | 0.470 | 0.667 |
| 2 | 0.147 | 0.171 | 0.667 |
| 3 | 0.299 | 0.426 | 0.667 |
| 4 | 0.216 | 0.237 | 0.667 |
| 5 | 0.243 | 0.281 | 0.639 |
| 6 | 0.225 | 0.478 | 0.667 |
| 7 | 0.261 | 0.337 | 0.667 |
| 8 | 0.304 | 0.441 | 0.667 |

Every method lowers the single-answer group's nDCG@10. Experiments 2 and 4 lower it the most. Any feedback or fusion change that broadens the dense leg pushes the one right answer down. In this pool, none of these three searches gained a new grade-2 item.

## Cost and latency (from run `meta`)

`latency_ratio_vs_base` is the retrieval-only ratio: the median over typed dev searches of warm, interleaved timings, on a shared and noisy 4-core box. All runs add the rewrite's ~2.3 s on top.

| # | Cost | Retrieval latency vs base | Notes |
| --- | --- | --- | --- |
| 2 | as base, $0.12/1k searches | 1.21× | — |
| 3 | as base | 1.17× | — |
| 4 | as base | 1.87× | — |
| 5 | as base here; ~+$0.05/1k in production for caption tokens | 1.36× | — |
| 6 | **~$0.36/1k searches** (3 rewrite calls) | 1.09× | Rewrite p50 2.64 s vs 2.32 s: the slowest of 3 parallel calls |
| 7 | as base | 0.97× | — |
| 8 | as base | 1.00× | — |

Gain per dollar, experiment 6 against the base: +0.028 nDCG@10 for an extra ~$0.24 per 1,000 searches, with no per-item cost. That is about +0.12 nDCG@10 per extra $1 per 1,000 searches. The CI includes 0.

## r2-label scores (before this round's pooling)

On r2 labels the base was 0.496. `unjudged10` was 0.02–0.12 for every run, so none required pooling.

| # | nDCG@10 (r2) | Δ (r2) [CI] | W/L/T |
| --- | --- | --- | --- |
| 2 | 0.466 | −0.030 [−0.099, +0.013] | 7/5/4 |
| 3 | 0.486 | −0.009 [−0.041, +0.017] | 5/8/3 |
| 4 | 0.479 | −0.016 [−0.066, +0.016] | 5/7/4 |
| 5 | 0.499 | +0.003 [−0.029, +0.035] | 8/4/4 |
| 6 | 0.515 | +0.020 [−0.031, +0.065] | 9/2/5 |
| 7 | 0.489 | −0.006 [−0.034, +0.015] | 6/5/5 |
| 8 | 0.494 | −0.002 [−0.034, +0.029] | 7/6/3 |

Pooling moved each method up by 0.002–0.013 relative to the base. The largest move was experiment 8, at +0.013, because it had the most unjudged items.

## Verdicts

The adoption rule: Δ ≥ 0.03 with a paired CI above 0, or Δ ≥ 0.02 with W > L and no extra cost.

| # | Verdict | Δ (r3) | Preregistered expectation | Result vs expectation |
| --- | --- | --- | --- | --- |
| 2 | **Not adopted** | −0.025 | +0.01..+0.03 | Below range; single-answer group drops to 0.147 |
| 3 | **Not adopted** | +0.000 | R@100 +0.02..+0.05 | No change; R@100 Δ +0.000 |
| 4 | **Not adopted** | −0.014 | 0..+0.02 | Below range, and 1.87× retrieval time |
| 5 | **Not adopted** | +0.014 [−0.020, +0.050] | +0.02..+0.04 | Below range; R@100 −0.002. Largest per-kind gain: vibe +0.14 (n = 1) |
| 6 | **Not adopted** | +0.028 [−0.024, +0.078] | +0.01..+0.03 | At the top of the range; 10 W / 2 L; R@100 +0.013 [−0.002, +0.031] |
| 7 | **Not adopted** | −0.003 | 0..+0.02 | No change |
| 8 | **Not adopted** | +0.011 [−0.022, +0.044] | R@100 0..+0.03 | No R@100 gain; the nDCG gain comes from one repeat (+0.046) |

Why experiment 6 fails the rule:

- **First clause:** Δ is below 0.03 and the CI includes 0.
- **Second clause:** Δ ≥ 0.02 and W > L both hold, but the clause requires no extra cost. The method costs 3× the rewrite (~$0.36 vs $0.12 per 1k searches), with slightly higher rewrite latency.

It is the strongest result of the round. Being a single run, it removes the base's repeat-to-repeat variance. A cheaper variant would clear the second clause, for example one rewrite call that asks for more phrases.

## Judging notes

- For five ambiguous searches the judge kept the grading conventions of earlier rounds (matched against existing grades). The per-search conventions are kept in the gitignored `data/eval_work/` because they tie search texts to answers.
