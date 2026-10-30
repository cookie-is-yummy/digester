# Experiment log

One row per experiment. The experimenter fills in the first columns **before** running; the evaluator fills in the result. Negative results stay. Scores are dev nDCG@10 unless stated.

| # | Date | Hypothesis (one variable) | Expected | Cost | Result (dev nDCG@10, Δ vs base, CI) | Adopted? |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 2026-10-30 | Baseline: hand-simulated rewrite + bge-small dense (gate, PRF) + BM25 full + RRF | — | $0, query p50 0.09 s | 0.508 [0.38, 0.63]; P@10 0.58, success@5 0.94, MRR 0.86, R@100 0.43, unjudged10 0.19. PRF vs none: +0.038. All 22: 0.486 | Base |
| 1 | 2026-10-30 | Real LLM rewrite (gpt-5-nano, prompt qr-v1, minimal reasoning) replaces hand-simulated parses; everything else = baseline hybrid_prf. Second arm: no rewrite (raw query only). | vs hand rewrite: −0.03 (−0.08..+0.02); vs no-rewrite: +0.04..+0.10 | ~$0.001 per 22 rewrites ×3 | (evaluator) | (evaluator) |
