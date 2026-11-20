# Round r10: experiments 21–22 (embedder swaps on B2), with B3, B2 and the honest base re-scored

Evaluator: fresh agent, round r10. Split: **dev** (16 searches: 13 typed, 3 more-like-this). 3 repeats per run. Repeat k is paired with **B2** `e9b_full_r{k}`, the adoption comparison. For reference it is also paired with **B3** `e20_hyde_b2_r{k}` and the honest base `e1_rewrite_r{k}`. Scoring uses `experiments/eval/score_multi.py`: each query's delta is averaged over the repeats, the 95% CI is a 2000-sample bootstrap over queries, and W/L/T counts a win or loss at |Δ| > 0.005.

Both runs change one variable versus B2: the embedding model of both dense lists (caption and enrichment). The BM25 lists, PRF, gates and RRF are unchanged.

## Labels

- **On r9 labels, before pooling:** 21 scored 0.557 with `unjudged10` 0.062 / 0.038 / 0.062. 22 scored 0.562 with `unjudged10` 0.081 / 0.038 / 0.062. All are under 0.15. As the task asked, I pooled the unjudged top 10 of all 6 runs anyway.
- **Pool:** 26 items, judged blind from the sheet only. The sheet was built **without `--extra`**, so each line shows caption, hashtags and creator. 3 of the lines were more-like-this, judged against the example item from `queries.jsonl`. Grades 2/1/0 = **2/9/15**. Merged as `claude-evaluator-r10`, with backup `evalset.pre_r10.jsonl`.
- After the merge, every run and every base has `unjudged10` = 0.00.
- **On r10 labels:** B3 0.570 (r9: 0.570), B2 0.548 (r9: 0.548), honest base 0.489. None of the newly judged items were in the bases' top 10s, so the base scores are unchanged.

## Summary (dev, r10 labels, mean of 3 repeats; Δ vs B2)

| Run | nDCG@10 [CI] | range | Δ vs B2 [paired CI] | W/L/T | P@10 | MRR | R@100 | ΔR@100 [CI] | success@5 | single-answer nDCG / MRR / R@100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **B2** (e9b_full) | 0.548 [0.428, 0.664] | 0.532–0.558 | — | — | 0.677 | 0.855 | 0.521 | — | 0.958 | 0.371 / 0.506 / 0.611 |
| 21 · EmbeddingGemma-300M | 0.566 [0.444, 0.680] | 0.558–0.573 | **+0.017 [−0.008, +0.041]** | 11/4/1 | 0.710 | 0.876 | 0.524 | +0.004 [−0.035, +0.037] | 0.938 | 0.348 / 0.506 / 0.500 |
| 22 · Gemini Embedding 2 (768d) | 0.568 [0.444, 0.684] | 0.566–0.571 | **+0.020 [−0.004, +0.043]** | 10/6/0 | 0.715 | 0.878 | 0.540 | +0.020 [−0.012, +0.047] | 0.938 | 0.379 / 0.515 / 0.556 |
| B3 (e20_hyde_b2, reference) | 0.570 [0.444, 0.687] | 0.563–0.574 | +0.022 [+0.008, +0.037] | 10/1/5 | 0.679 | 0.867 | 0.528 | +0.008 [−0.012, +0.030] | 0.938 | 0.372 / 0.511 / 0.611 |

Per-repeat Δ nDCG@10 vs B2: 21 +0.011 / +0.001 / +0.041; 22 +0.012 / +0.010 / +0.039. In both runs, repeat 3 carries much of the gain.

## Versus B3, each other and the honest base (reference)

| Run | Δ vs B3 [paired CI] | W/L/T | Δ vs honest base [paired CI] | W/L/T | ΔR@100 vs honest [CI] |
| --- | --- | --- | --- | --- | --- |
| B2 | −0.022 | 1/10/5 | +0.059 [+0.016, +0.108] | 13/3/0 | +0.014 [−0.011, +0.043] |
| B3 | — | — | **+0.080 [+0.036, +0.133]** | 13/3/0 | +0.022 [−0.013, +0.059] |
| 21 | −0.004 [−0.024, +0.013] | 6/7/3 | +0.076 [+0.031, +0.126] | 13/3/0 | +0.018 [−0.043, +0.075] |
| 22 | −0.002 [−0.026, +0.018] | 8/7/1 | +0.079 [+0.018, +0.139] | 13/3/0 | +0.034 [−0.018, +0.081] |

22 vs 21 (head to head): Δ **+0.003 [−0.021, +0.025]**, W/L/T 8/4/4, ΔR@100 +0.016 [−0.003, +0.042].

## Subsets

| Comparison | Subset | Δ nDCG@10 | W/L/T | ΔR@100 |
| --- | --- | --- | --- | --- |
| 21 vs B2 | typed (13) | +0.019 | 9/3/1 | −0.002 |
| 21 vs B2 | more_like_this (3) | +0.009 | 2/1/0 | +0.031 |
| 22 vs B2 | typed (13) | +0.022 | 9/4/0 | +0.015 |
| 22 vs B2 | more_like_this (3) | +0.013 | 1/2/0 | +0.039 |
| 21 vs B3 | typed (13) | −0.007 | 4/6/3 | −0.012 |
| 22 vs B3 | typed (13) | −0.005 | 7/5/1 | +0.006 |
| 22 vs 21 | typed (13) | +0.002 | 6/3/4 | +0.018 |

## Per-kind nDCG@10 (mean over repeats; kind counts: topic 5, name 3, MLT 3, and 1 each for audio, people, place, said_shown, vibe)

| Kind | Honest base | B2 | B3 | 21 | 22 |
| --- | --- | --- | --- | --- | --- |
| topic (5) | 0.433 | 0.528 | 0.564 | 0.567 | 0.568 |
| name (3) | 0.556 | 0.597 | 0.629 | 0.637 | 0.650 |
| more_like_this (3) | 0.645 | 0.692 | 0.692 | 0.701 | 0.705 |
| people (1) | 0.620 | 0.882 | 0.887 | 0.791 | 0.867 |
| place (1) | 0.513 | 0.376 | 0.426 | 0.406 | 0.282 |
| said_shown (1) | 0.662 | 0.717 | 0.717 | 0.667 | 0.698 |
| vibe (1) | 0.210 | 0.247 | 0.306 | 0.338 | 0.341 |
| audio (1) | 0.058 | 0.043 | 0.000 | 0.000 | 0.000 |

## Per-kind R@100

| Kind | Honest base | B2 | B3 | 21 | 22 |
| --- | --- | --- | --- | --- | --- |
| topic | 0.537 | 0.592 | 0.615 | 0.633 | 0.644 |
| name | 0.631 | 0.641 | 0.629 | 0.674 | 0.664 |
| more_like_this | 0.476 | 0.479 | 0.479 | 0.510 | 0.518 |
| people | 0.403 | 0.453 | 0.453 | 0.459 | 0.472 |
| place | 0.185 | 0.202 | 0.208 | 0.214 | 0.212 |
| said_shown | 0.750 | 0.667 | 0.750 | 0.500 | 0.667 |
| vibe | 0.257 | 0.273 | 0.312 | 0.249 | 0.281 |
| audio | 0.500 | 0.417 | 0.333 | 0.250 | 0.250 |

Kinds with a single search (n = 1) are signals, not findings. In the single-answer group, 21 drops versus B2 (nDCG 0.348 vs 0.371, R@100 0.500 vs 0.611). 22 is level on nDCG (0.379) but also loses R@100 (0.556).

## Cost and latency (from run `meta`)

| Run | Extra $ vs B2 | Latency | Other costs | Gain per $ |
| --- | --- | --- | --- | --- |
| B2 | — | query p50 0.29 s (+ rewrite ≈ 2.3 s) | bge-small 384d, 0.77 KB/item/index | — |
| 21 | **$0** | query p50 0.32 / 0.31 / 0.31 s (query embed ≈ 0.10–0.11 s) | 1.26 GB fp32 model (≈ 9× bge-small); 1.5 KB/item/index (2×); index build ≈ 2.3 h CPU (6,300 s captions + 2,163 s enrichment); Gemma Terms of Use licence | n/a ($0) |
| 22 | index **$0.74** for both indexes (caption $0.393 + enrichment $0.346, ledger estimate at standard price) ≈ **$0.036 per 1k items**; query embedding ≈ $0.013 per 1k searches | query p50 0.39 / 0.35 / 0.34 s **plus** an API embed call ≈ 0.48–0.50 s → **0.82–0.89 s** p50 vs 0.29 s | cloud-only: breaks local/desktop search, sends text off-device | ≈ 0.020 / $0.036 ≈ **0.55 nDCG@10 per $ per 1k items** (CI spans 0) |

## Verdicts (rule: Δ ≥ 0.03 with paired CI > 0, or Δ ≥ 0.02 with W > L and no extra cost)

- **21 · EmbeddingGemma-300M on B2: NO.** Δ +0.017 [−0.008, +0.041], W/L/T 11/4/1. That is below 0.02, so neither clause applies, whatever counts as cost. The gain is on typed searches (+0.019, 9/3/1). Name and vibe go up, people and said_shown go down. R@100 is flat (+0.004), and the single-answer group gets worse.
  - **Does it count as cost?** I count the non-dollar costs as extra cost: a 9× larger model, 2× vector storage, about 2.3 h of CPU to re-index, and a separate licence (Gemma Terms of Use, which needs a legal check before it ships in a desktop app). So clause 2 would not have been clean even at Δ = 0.02. The point is moot here.
- **22 · Gemini Embedding 2 (768d) on B2: NO.** Δ +0.020 [−0.004, +0.043], W/L/T 10/6/0. It just reaches the 0.02 threshold with W > L, but it has extra cost: $0.036 per 1k items to index, about $0.013 per 1k searches, and about +0.5 s per search. It is also cloud-only, so clause 2 fails. Clause 1 fails too (Δ < 0.03, CI spans 0). Against 21 it gains only **+0.003 [−0.021, +0.025]**, far below the +0.03 needed to justify paid, cloud-only search. R@100 (+0.020 vs B2, +0.016 vs 21) is its only consistent edge.
- **Swap vs HyDE:** neither swap beats B3. Against B3, 21 scores −0.004 [−0.024, +0.013] and 22 −0.002 [−0.026, +0.018]. HyDE on bge (+0.022 vs B2, CI [+0.008, +0.037], 10/1/5) is the same size as either swap. It has a much tighter CI and fewer losses, at no index cost. An embedder swap is not worth more than HyDE. Stacking a swap on HyDE is untested.
- **B3 on r10:** 0.570 [0.444, 0.687] (0.563–0.574), R@100 0.528. Δ vs honest base **+0.080 [+0.036, +0.133]**, 13/3/0. Δ vs B2 +0.022 [+0.008, +0.037], 10/1/5. **B3 stays the base.**
