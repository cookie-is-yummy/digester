# Round r6: experiments 10–12 (dense-model swaps, ColBERT re-score) (+ base and exp 9 re-scored)

Evaluator: fresh agent, round r6. Split: **dev** (16 searches: 13 typed, 3 more-like-this). 3 repeats per run; repeat k is paired with honest base `e1_rewrite_r{k}`. Scored with `experiments/eval/score_multi.py`: per-query delta averaged over repeats, 2000-sample bootstrap 95% CI over queries, W/L/T at |Δ| > 0.005.

## Labels

- On r5 labels, before pooling: `unjudged10` was 0.163/0.175/0.131 for exp 10, 0.112/0.138/0.144 for exp 11 and 0.031/0.019/0.031 for exp 12. Exp 10 was above 0.15 in two repeats. As the task asked, the unjudged top 10 of all 9 runs was pooled.
- Pool: **73 items**, judged blind from the sheet only. More-like-this lines were judged against the example item's caption, hashtags and creator in `queries.jsonl` / `items.jsonl`. To find which example each line used, the evaluator read the query id from the sheet key; the key gives no run names. Grades 2/1/0 = **5/25/43**. Merged as `claude-evaluator-r6`; backup `evalset.pre_r6.jsonl`.
- After the merge every run (and the base) has `unjudged10` = 0.00.
- Pre-pool mean nDCG@10 on r5 labels: exp 10 0.506, exp 11 0.534, exp 12 0.509. Both embedder runs gained about +0.026 from the new judgments, so a good part of their measured gain rests on one judge's labels for this round.
- Base on r6: nDCG@10 **0.490** (unchanged), R@100 0.504 → **0.511**.

## Summary (dev, r6 labels, mean of 3 repeats)

| Run | nDCG@10 [CI] | range | Δ vs base [paired CI] | W/L/T | P@10 | MRR | R@100 | ΔR@100 [CI] | success@5 | single-answer nDCG / MRR / R@100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Base (e1_rewrite) | **0.490** [0.385, 0.600] | 0.469–0.506 | — | — | 0.617 | 0.821 | 0.511 | — | 0.896 | 0.333 / 0.470 / 0.667 |
| 10 EmbeddingGemma-300M | 0.533 [0.426, 0.632] | 0.525–0.544 | **+0.043** [−0.031, +0.108] | 10/6/0 | 0.681 | 0.862 | 0.510 | −0.002 [−0.033, +0.028] | 0.917 | 0.282 / 0.317 / 0.583 |
| 11 Gemini Embedding 2 | **0.560** [0.441, 0.671] | 0.547–0.573 | **+0.069** [−0.004, +0.136] | 12/4/0 | 0.702 | 0.866 | 0.531 | +0.019 [−0.003, +0.043] | 0.917 | 0.328 / 0.342 / 0.639 |
| 12 ColBERT re-score | 0.510 [0.399, 0.623] | 0.500–0.524 | **+0.020** [−0.014, +0.053] | 8/4/4 | 0.637 | 0.822 | 0.511 | 0.000 (by construction) | 0.938 | 0.396 / 0.473 / 0.667 |
| 9 enrich (sample, provisional) | 0.550 [0.431, 0.664] | 0.534–0.563 | **+0.059** [+0.019, +0.103] | 13/2/1 | 0.673 | 0.852 | 0.521 | +0.009 [−0.005, +0.025] | 0.979 | 0.376 / 0.542 / 0.667 |

Per-repeat Δ nDCG@10: exp 10 +0.029 / +0.025 / +0.075; exp 11 +0.078 / +0.041 / +0.090; exp 12 +0.028 / 0.000 / +0.031; exp 9 +0.056 / +0.057 / +0.065. Unrounded Δ: exp 10 +0.0427, exp 11 +0.0694, exp 12 **+0.0197**, exp 9 +0.0594.

**Exp 11 vs exp 10** (paired by repeat): Δ nDCG@10 **+0.027 [−0.007, +0.062]**, W/L/T 10/3/3 (per repeat +0.049 / +0.016 / +0.015); Δ R@100 +0.021 [−0.004, +0.049].

## Subsets

| Run | Subset | Run | Base | Δ | W/L/T | ΔR@100 |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | typed (13) | 0.494 | 0.454 | +0.039 | 8/5/0 | −0.005 |
| 10 | more_like_this (3) | 0.704 | 0.645 | +0.059 | 2/1/0 | +0.013 |
| 11 | typed (13) | 0.521 | 0.454 | +0.066 | 10/3/0 | +0.015 |
| 11 | more_like_this (3) | 0.731 | 0.645 | +0.086 | 2/1/0 | +0.040 |
| 12 | typed (13) | 0.479 | 0.454 | +0.024 | 8/4/1 | 0 |
| 12 | more_like_this (3) | 0.645 | 0.645 | 0 (MLT = base) | 0/0/3 | 0 |
| 9 | typed (13) | 0.517 | 0.454 | +0.062 | 11/1/1 | +0.013 |
| 9 | more_like_this (3) | 0.693 | 0.645 | +0.048 | 2/1/0 | −0.007 |

## Per-kind nDCG@10 (mean over repeats; kind counts: topic 5, name 3, MLT 3, and 1 each for audio, people, place, said_shown, vibe)

| Kind | Base | 10 | 11 | 12 | 9 |
| --- | --- | --- | --- | --- | --- |
| topic (5) | 0.436 | 0.562 | 0.564 | 0.455 | 0.540 |
| name (3) | 0.556 | 0.641 | 0.699 | 0.634 | 0.600 |
| more_like_this (3) | 0.645 | 0.704 | 0.731 | 0.645 | 0.693 |
| people (1) | 0.620 | 0.591 | 0.771 | 0.475 | 0.835 |
| place (1) | 0.513 | 0.481 | 0.397 | 0.567 | 0.374 |
| said_shown (1) | 0.662 | **0.304** | **0.357** | 0.702 | 0.717 |
| vibe (1) | 0.210 | 0.309 | 0.324 | 0.285 | 0.236 |
| audio (1) | 0.058 | 0.000 | 0.000 | 0.019 | 0.057 |

## Per-kind R@100

| Kind | Base | 10 | 11 | 12 | 9 |
| --- | --- | --- | --- | --- | --- |
| topic | 0.560 | 0.593 | 0.609 | 0.560 | 0.579 |
| name | 0.628 | 0.642 | 0.639 | 0.628 | 0.630 |
| more_like_this | 0.469 | 0.482 | 0.509 | 0.469 | 0.463 |
| people | 0.399 | 0.418 | 0.412 | 0.399 | 0.438 |
| place | 0.178 | 0.175 | 0.190 | 0.178 | 0.190 |
| said_shown | 0.750 | 0.583 | 0.750 | 0.750 | 0.750 |
| vibe | 0.262 | 0.223 | 0.231 | 0.262 | 0.278 |
| audio | 0.500 | 0.417 | 0.417 | 0.500 | 0.500 |

The two embedder swaps gain mostly on topic, name, MLT and vibe searches. They lose on the said_shown search (nDCG@10 roughly halves) and on the single-answer group (exp 10 MRR 0.317 vs 0.470; exp 11 0.342). Both swaps change only the dense leg. The base's bge-small evidently ranked those exact-item searches better. ColBERT is the reverse: small broad gain, best of the three on said_shown, place and single-answer, and a loss on people.

## Cost and latency (from run `meta`)

| Run | Extra cost | Extra latency / footprint | Gain per $ per 1k items |
| --- | --- | --- | --- |
| 10 EmbeddingGemma | $0 | query p50 0.29–0.35 s vs 0.22–0.24 s (query embed ≈0.19 s on shared CPU); indexing 6,300 s CPU for 20,202 items (3.2 items/s, 2 threads); 1,536 B/item (768d fp16), same as bge-small's 384d fp32; model 1.26 GB fp32 ONNX (≈300M vs ≈33M params for bge-small); **Gemma Terms of Use** licence | n/a ($0) |
| 11 Gemini Embedding 2 | $0.39 ledger for 20,202 items (**$0.019 per 1k items**, standard; ledger estimate at chars/4); queries ≈$0.00001 each | query + embed p50 0.65–0.68 s vs 0.22–0.24 s (+≈0.45 s API call); 1,536 B/item; **cloud-only: no offline or local desktop search** | ≈3.6 nDCG@10 per $ per 1k items |
| 12 ColBERT | $0 | 19.5 KB/item fp16 token vectors (≈13× a dense vector; ≈390 MB for 20k items); model 0.134 GB; warm MaxSim + query encode p50 0.06–0.10 s, but cold-cache query p50 9.0 s → 3.9 s → 2.4 s as candidate docs got encoded | n/a ($0) |
| 9 enrich | $0.356 per 1k items ($0.178 batch), one-off | query +~0.05 s | ≈0.17 per $ per 1k items (0.33 batch) |

## Verdicts (rule: Δ ≥ 0.03 with paired CI > 0, or Δ ≥ 0.02 with W > L and no extra cost)

- **10 · EmbeddingGemma-300M:** **Not adopted by the letter.** Clause 1 fails: Δ +0.043 but the CI [−0.031, +0.108] spans 0, and repeats vary (+0.025 to +0.075). Clause 2 hinges on "no extra cost". The dollar cost is $0 (Δ ≥ 0.02, W/L 10/6), so it passes if only dollars count. It is not cost-free in footprint: a 1.26 GB model (the brief's "4×" understates it; by parameters it is ≈9× bge-small), a slower query embed (≈+0.1 s p50), hours of CPU re-indexing, and the Gemma Terms of Use licence instead of MIT. It also gives back the single-answer and said_shown searches and R@100 (−0.002). My call: a near miss; don't adopt as-is.
- **11 · Gemini Embedding 2:** **Not adopted.** Δ +0.069 (largest of the round, 12/4/0) but the CI lower bound is −0.004, just under 0. Clause 2 fails because it is paid and cloud-only. It beats exp 10 by only **+0.027 [−0.007, +0.062]**, under the research note's ≥ 0.03 bar for giving up local desktop search. Cheap per item ($0.019/1k, ≈3.6 nDCG per $ per 1k items), so it is a strong candidate to re-test stacked with exp 9 or as an optional cloud tier. It should not replace the local dense leg.
- **12 · ColBERT re-score:** **Not adopted.** Δ +0.020 (unrounded +0.0197, just under 0.02), CI [−0.014, +0.053], W/L/T 8/4/4. It also has an extra footprint (19.5 KB/item token store, cold-cache latency of seconds). It helps the single-answer group (nDCG 0.396 vs 0.333) but not overall.
- **9 · enrichment (sample), re-scored on r6:** still **passes clause 1**: 0.550, Δ **+0.059 [+0.019, +0.103]**, 13/2/1, stable per repeat. It remains the provisional finalist.
