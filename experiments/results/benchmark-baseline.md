# Benchmark: the current system (phase 2, 30 Oct 2026)

**System:** hand-simulated query rewrite → bge-small dense (info-ok items, max over phrases, Rocchio PRF from the top 5) + BM25 over the `full` text view → RRF (k = 60). Measured on one founder's export (21,293 items, 20,202 with any text) on a 4-vCPU cloud container, no GPU. Script: `methods/bench_system.py` (no labels). Quality numbers come from the evaluator (`2026-10-30-phase1-repro-dev.json`, `2026-10-30-baseline-dev-r1labels.json`).

## Quality by search kind (dev, 16 searches)

| Kind (n) | nDCG@10, r0 labels | nDCG@10, r1 labels | R@100, r0 |
| --- | --- | --- | --- |
| topic (5) | 0.48 | 0.52 | 0.49 |
| name (3) | 0.56 | 0.56 | 0.59 |
| more like this (3) | 0.43 | 0.65 | 0.37 |
| said / shown (1) | 0.77 | 0.77 | 0.67 |
| place (1) | 0.84 | 0.84 | 0.29 |
| vibe (1) | 0.86 | 0.86 | 0.35 |
| people (1) | 0.31 | 0.70 | 0.33 |
| audio (1) | 0.00 | 0.00 | 0.00 |
| **All dev** | **0.508** [0.38, 0.63] | **0.585** [0.47, 0.71] | **0.43** (r1: 0.46) |

- r1 = after blind judging of the baseline's 31 unjudged top-10 items (20 relevant). The jump for people and more-like-this means the baseline was finding right answers the original labels missed.
- Kinds with n = 1 are anecdotes. success@5 is 0.94 (saturated); MRR 0.86.
- The real weakness is **recall**: only 43–46% of the right answers reach the top 100, so no reranker can fix most misses.
- All 22 searches (r0): 0.486.

## Speed

| Step | Measured here | Notes |
| --- | --- | --- |
| Load corpus + vectors | 1.7 s | 21k items, JSONL |
| Embed with bge-small (fastembed, ONNX, 4 threads) | **2.7–4.8 items/s** = 3.5–6 min per 1,000 items | Measured while other loop jobs shared the CPU (load 3–6), so pessimistic. Earlier note: ~7.5 items/s on 2 dedicated cores. Average text 459 characters (~115 tokens) |
| Build the BM25 index (1–2-grams, 658k terms) | 10.8–11.6 s for 20k items | scikit-learn sparse; rebuilt from scratch |
| Query, excluding the rewrite | p50 0.10–0.18 s, p95 0.28–0.42 s | Embeds 1–4 phrases on CPU, exact dot product, BM25, RRF. 0.09 s p50 on an idle box |
| Real LLM rewrite (gpt-5-nano, experiment 1) | **p50 2.3 s**, p95 2.6–3.5 s | Dominates query latency; the 500 ms p95 target is missed whenever the rewrite runs |
| 100k items (synthetic) | dense 0.05 s, BM25 0.12 s per query | Exact search, full argsort; argpartition / an inverted index would be faster |

**GPU:** none available in this environment, so not measured. Published throughput for bge-small on one T4-class GPU is in the high hundreds to low thousands of short texts per second, i.e. a 20k-item first report in well under a minute of GPU time (to confirm when a GPU is available).

## Storage per item

| Part | Bytes |
| --- | --- |
| bge-small vector, 384d float16 | 768 |
| Search text (UTF-8) | ~386 |
| BM25 postings (est. 8 B per posting, 83 postings per item with bigrams) | ~664 |
| **Total** | **~1.8 KB** |

## Cost

| | Now (hand rewrite) | With a real rewrite |
| --- | --- | --- |
| Indexing per 1,000 items | $0 (local CPU) | $0 |
| Per 1,000 searches | $0 | ~$0.12 (gpt-5-nano, measured in experiment 1) |
| Per user (21k items, 100 searches a month) | $0 + compute | ~$0.012 a month for rewrites |
| Fallback: OpenAI 3-small 512d embeddings | ~$0.002 per 1,000 items (measured 2.2M tokens ≈ $0.04 for 20k) | — |

## Projection

| | 1 user, 21k items | 1 user, 100k items | 1,000 users × 21k | 1,000 users × 100k |
| --- | --- | --- | --- | --- |
| Storage (no sharing) | 38 MB | 180 MB | 38 GB | 180 GB |
| Embedding, 4 CPU cores at ~5 items/s | ~70 min | ~5.5 h | ~1,200 CPU-hours | ~5,500 CPU-hours |
| Embedding on one GPU (est. ~1,000 items/s) | ~20 s | ~2 min | ~6 GPU-hours | ~28 GPU-hours |
| Query latency (excl. rewrite) | ~0.1 s | ~0.2 s | unchanged (per-user index) | unchanged |

- Shared `content` rows (A-001) cut storage and embedding by the overlap between users' items; unknown until a second user exists.
- **First-report target** (`05-processor.md`: ≤ 5 min for ~3k saves and shares): on 4 CPU cores at ~5 items/s, 3k items take ~10 min, so the cloud first report needs a GPU burst or ~10+ cores. The full 20k-item export (≤ 60 min target) is borderline on 4 cores.
- **Search p95 target** (≤ 500 ms): met without the LLM rewrite; missed with it (2–3.5 s). Options: cache rewrites, show un-rewritten results first and refine, or a faster model.

## Desktop fit

| Part | Fit |
| --- | --- |
| bge-small (33M params, ~130 MB ONNX) | Good: runs on any laptop CPU; new items embed in well under a second each |
| Vectors | 100k items × 768 B = 77 MB fp16; exact search 0.05 s, no ANN index needed |
| Keyword index | Good: SQLite FTS5 or tantivy would replace the scikit-learn matrix |
| Query rewrite | **Poor locally**: needs a cloud LLM call (~2.3 s, $0.0001) or the user's own agent via MCP. A 1–3B local LLM on CPU would take 10–25 s per rewrite (research note `query-rewrite-routing-hyde.md`) |
| Vector compatibility | Same bge-small vectors in cloud and desktop: no re-embedding on hand-over |
