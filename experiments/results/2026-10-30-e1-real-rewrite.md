# Experiment 1: real LLM query rewrite vs the hand-simulated rewrite

Evaluator round r2, 2026-10-30. Split: **dev** (16 searches). Aggregates only.

Runs: the current base (hand-simulated rewrite, `baseline:hybrid_prf`); the real rewrite (gpt-5-nano, prompt qr-v1, minimal reasoning), three independent repeats; and no rewrite (raw query only). Everything else is the baseline hybrid_prf pipeline.

## Labels

- On r1 labels, every e1 run had `unjudged10` above 0.15: real rewrite 0.294 / 0.250 / 0.319, no rewrite 0.294. The baseline had 0.00.
- I pooled the unjudged top 10 of all five runs into one pool: **127 items**. I judged them blind from the sheet only and merged them as round **r2** (judge `claude-evaluator-r2`). Grades: 2 / 1 / 0 = **3 / 32 / 92**. The backup is `data/evals/labels/evalset.pre_r2.jsonl`.
- After the merge, `unjudged10` is 0.00 for all five runs.
- This judge did not read the Muse export, the Muse reports or the method code. No more-like-this lines were in the pool.

## Headline (r2 labels)

| Run | nDCG@10 [95% CI] | Δ vs hand rewrite [paired CI] | W/L/T | P@10 | MRR | R@100 | success@5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Hand rewrite (baseline) | **0.578** [0.461, 0.697] | — | — | 0.706 | 0.860 | 0.493 | 0.938 |
| Real rewrite r1 | 0.503 [0.403, 0.611] | −0.076 [−0.185, +0.007] | 5/7/4 | 0.619 | 0.801 | 0.467 | 0.938 |
| Real rewrite r2 | 0.511 [0.407, 0.619] | −0.067 [−0.180, +0.017] | 5/7/4 | 0.619 | 0.885 | 0.467 | 0.938 |
| Real rewrite r3 | 0.473 [0.345, 0.596] | −0.105 [−0.215, −0.026] | 2/9/5 | 0.613 | 0.773 | 0.468 | 0.812 |
| **Real rewrite, 3 repeats** | **mean 0.496 (range 0.473–0.511)** | mean-of-repeats −0.083 [−0.186, −0.009] | 2/10/4 | — | — | 0.467 | — |
| No rewrite | 0.411 [0.285, 0.558] | −0.168 [−0.284, −0.063] | 2/10/4 | 0.519 | 0.743 | 0.418 | 0.875 |

The mean-of-repeats row averages each search's nDCG@10 over the three repeats before taking the paired difference.

**Real rewrite vs no rewrite** (the honest gain from rewriting at all):

| Repeat | Δ nDCG@10 [paired CI] | W/L/T |
| --- | --- | --- |
| r1 | +0.092 [+0.033, +0.161] | 11/2/3 |
| r2 | +0.101 [+0.029, +0.182] | 8/4/4 |
| r3 | +0.062 [−0.015, +0.150] | 8/4/4 |
| Mean of repeats | **+0.085 [+0.022, +0.152]** | 11/2/3 |

**Stability across repeats.** The three repeats agree on the overall level (0.473–0.511). Per search, the spread is large: the mean range across repeats is 0.131, and 8 of 16 searches vary by more than 0.1. The rewrite is nondeterministic. A single repeat is not a reliable measurement.

## By search kind (r2 labels)

nDCG@10 (counts in brackets; n = 1 kinds are anecdotes):

| Kind | Hand rewrite | Real rewrite r1 / r2 / r3 (mean) | No rewrite |
| --- | --- | --- | --- |
| topic (5) | 0.505 | 0.510 / 0.472 / 0.360 (0.447) | 0.367 |
| name (3) | 0.557 | 0.581 / 0.600 / 0.508 (0.563) | 0.533 |
| more_like_this (3) | 0.645 | 0.645 / 0.645 / 0.645 | 0.645 |
| audio (1) | 0.000 | 0.072 / 0.117 / 0.000 (0.063) | 0.000 |
| people (1) | 0.697 | 0.344 / 0.761 / 0.756 (0.620) | 0.272 |
| place (1) | 0.842 | 0.478 / 0.450 / 0.610 (0.513) | 0.465 |
| said_shown (1) | 0.717 | 0.659 / 0.567 / 0.759 (0.662) | 0.277 |
| vibe (1) | 0.865 | 0.260 / 0.189 / 0.181 (0.210) | 0.186 |

R@100:

| Kind | Hand rewrite | Real rewrite r1 / r2 / r3 | No rewrite |
| --- | --- | --- | --- |
| topic (5) | 0.548 | 0.518 / 0.532 / 0.506 | 0.412 |
| name (3) | 0.592 | 0.598 / 0.592 / 0.600 | 0.570 |
| more_like_this (3) | 0.416 | 0.416 / 0.416 / 0.416 | 0.416 |
| audio (1) | 0.333 | 0.333 / 0.333 / 0.333 | 0.333 |
| people (1) | 0.422 | 0.333 / 0.356 / 0.400 | 0.289 |
| place (1) | 0.295 | 0.175 / 0.145 / 0.175 | 0.127 |
| said_shown (1) | 0.750 | 0.750 / 0.750 / 0.750 | 0.750 |
| vibe (1) | 0.315 | 0.239 / 0.196 / 0.250 | 0.163 |

**Single-answer group** (hk_tailor, instant_pot, gun_trend, as one group of 3):

| | nDCG@10 | MRR | R@100 |
| --- | --- | --- | --- |
| Hand rewrite | 0.311 | 0.421 | 0.583 |
| Real rewrite r1 / r2 / r3 | 0.353 / 0.352 / 0.319 (mean 0.341) | 0.437 / 0.556 / 0.398 | 0.583 each |
| No rewrite | 0.151 | 0.212 | 0.583 |

In the r2 pool, two of these three searches gained one borderline (grade 1) label, so they are no longer strictly single-answer.

**Where the gap to the hand rewrite comes from:** the vibe, place and people searches (one search each), and topic in repeat r3. The real rewrite matches or beats the hand rewrite on name and on the single-answer group.

## Cost and latency (from run `meta`)

- **Real rewrite:**
  - Cost: $0.00153–0.00155 per run of 13 rewrites, about **$0.12 per 1,000 queries**.
  - Indexing cost: $0 per 1,000 items (query-time only).
  - Rewrite p50: 2.32–2.36 s. Query plus rewrite p50: about 2.57 s, against 0.10 s for the baseline and for no rewrite.
- **Hand rewrite and no rewrite:** $0. The hand rewrite isn't a deployable method.
- **Gain per dollar:** against no rewrite, +0.085 nDCG@10 for about $0.12 per 1,000 queries. There is no per-item cost.
- **Latency:** the cost that matters is +2.5 s per search at p50.

## r1-label scores (before this round's pooling, for the record)

| Run | nDCG@10 | Δ vs hand [CI] | W/L/T | unjudged10 |
| --- | --- | --- | --- | --- |
| Real rewrite r1 / r2 / r3 | 0.476 / 0.486 / 0.453 | −0.109 / −0.099 / −0.132 (all CIs below 0) | 1/9/6, 3/8/5, 1/9/6 | 0.29 / 0.25 / 0.32 |
| No rewrite | 0.389 | −0.195 [−0.325, −0.084] | 1/11/4 | 0.29 |

Pooling narrowed the gap to the hand rewrite by about 0.03. The hand rewrite was fully judged on r1 labels, so it was favoured.

## Verdict (rule: Δ ≥ 0.03 with paired CI > 0, or Δ ≥ 0.02 with W > L and no extra cost)

- **Real rewrite vs hand rewrite: not adopted on merit.** Δ = −0.083 (mean of repeats) [−0.186, −0.009], 2 W / 10 L. As preregistered, the real rewrite is below the hand rewrite. The hand rewrite was written with knowledge of the answers, so this gap measures that bias plus real rewrite quality.

  **However, the brief requires replacing the biased hand rewrite.** The real rewrite becomes the honest base: dev nDCG@10 **0.496** (mean of 3 repeats, r2 labels). Future experiments should compare against it. Because per-search variance is high, they should either fix the rewrite outputs (cache one repeat) or average over repeats.
- **Real rewrite vs no rewrite: passes the rule.** Δ = +0.085 [+0.022, +0.152], 11 W / 2 L. Two of three repeats clear the rule on their own; r3 has a CI touching 0. Rewriting is worth its $0.12 per 1,000 queries. Its real cost is about 2.5 s of added latency.
- **Preregistered expectations:**
  - vs hand: expected −0.03 (−0.08..+0.02); observed −0.083, at the pessimistic end.
  - vs no rewrite: expected +0.04..+0.10; observed +0.085, inside the range.

## Judging notes

- **One vibe-style search has ambiguous wording.** It could mean catchy or satisfying audio, or musical theatre. I graded sound-design and novelty-music items for it as borderline (1). That accounts for a large share of this round's 1s.
- **Searches whose wording depends on information a caption cannot show.** Two searches name whether an item was shared or saved, or when it was seen. I graded them on topic match only.
