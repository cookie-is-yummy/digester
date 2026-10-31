# Free experiments 2–8: exact method definitions

*30 Oct 2026 · Experimenter · no labels, scores or Muse files read.* Scores are filled in by the evaluator in `LOG.md`.

All variants run through `experiments/methods/pipeline.py`, which reimplements the honest base (`baseline.py --variant hybrid_prf --parses qr-v1_gpt-5-nano_r{k}.json`) as one function with options. **With default options it reproduces `data/runs/e1_rewrite_r{1,2,3}.json` exactly** (all 16 dev rankings identical, top 1000, all three repeats).

## The base, as implemented

- **Typed searches.** Phrases = [query] + rewrite phrases, embedded with bge-small `query_embed`.
  - Dense score = max over phrases of the cosine, info-ok items only.
  - Rocchio PRF: top 5 of that dense score; q2 = normalize(mean(phrase vectors) + mean(top-5 item vectors)); dense score = max(dense score, cos(q2)).
  - BM25 over the `full` text view; query = query text + rewrite keywords; every query term weighs 1 (binarised).
  - RRF, k = 60, depth 1000 per list.
- **More-like-this** (searches with examples): centroid of the example vectors (dense, info-ok) + BM25 on the examples' `full` text, RRF. Unchanged in every experiment below.
- Filters always come from `queries.jsonl`.

## Variants (each changes one thing; three runs, one per cached rewrite set, unless noted)

| # | Run files | Option | Exact change |
| --- | --- | --- | --- |
| 2 | `e2_prf_fused_r{1,2,3}` | `prf=fused` | First pass: dense (no PRF) and BM25 fused by RRF. Feedback set = the first 5 **info-ok** items of that fused list. The same q2 formula, max with the phrase scores, then the final RRF with the same BM25 list. |
| 3 | `e3_bm25_rm3_r{1,2,3}` | `rm3=1` | After the base fusion, take the fused top 10. For each unigram of the BM25 vocabulary in those items' `full` text, weight = Σ over the 10 items of (count / item's unigram count) × BM25 idf. Drop terms in `lib/common.STOP`, terms of the BM25 query itself (query + keywords) and all-digit tokens. The top 10 terms are added to the BM25 query vector at weight 0.5 (original unigrams and bigrams stay at 1). BM25 is re-run and re-fused with the unchanged dense list (dense keeps its PRF). |
| 4 | `e4_phrase_rrf_r{1,2,3}` | `dense_fusion=rrf` | Each phrase vector ranks the info-ok items separately; the dense list = RRF (k = 60, depth 1000) of those rankings instead of the max of scores. PRF keeps its form: the feedback top 5 are the first 5 of that per-phrase RRF list, and the q2 ranking joins the dense RRF as one more list (as q2 joins the max in the base). |
| 5 | `e5_hyde_r{1,2,3}` | `hyde=1` | The 3 cached `hypothetical_captions` are embedded with bge-small plain `embed` (passage style, no query instruction) and normalised; h = their mean. One extra vector v = normalize(0.3·q + 0.7·h), where q is the raw-query vector (the first phrase vector). v joins the phrase set, so it enters both the max over phrases and the PRF mean. α = 0.7 from the TREC RAG 2025 report; not tuned. |
| 6 | `e6_union` (one run) | three `--parses` | One parse from all three rewrite sets: phrases taken round-robin (r1[0], r2[0], r3[0], r1[1], …), deduplicated case- and whitespace-insensitively, capped at 6; keywords the same way, lowercase dedup, capped at 12. Everything else is the base. Compared by the evaluator with each base repeat. Meta records the cost of all three calls and latency = slowest of the three (parallel calls). |
| 7 | `e7_prior_r{1,2,3}` | `prior=0.003` | Final score = base RRF score + 0.003 × max(0, importance − 0.3), with `importance` read from `items.jsonl` (contract: min(1, Σ interaction weights)). Applied only to items already in the fused list; typed searches only. Maximum lift +0.0021, about 5 places near the top 10. |
| 8 | `e8_creator_r{1,2,3}` | `creator=1` | Seeds = fused top 10. For each seed whose creator (`owner_handle`, case-insensitive) has 2–30 items in the whole corpus (21,293 items, including items without text or vector), that creator's other items are added to an expansion list. Seeds themselves are excluded, the search's filters are applied, and duplicates are kept once. Order: by the seed's rank, then by the item's position in the fused list (items not in it last), then corpus order. The list joins the RRF as a third list at **weight 0.5** (from the research note), k = 60. Typed searches only. Items with no vector can now appear in the ranking. |

## Cost and latency

- **No paid calls were made.** Every run reuses the cached qr-v1 rewrites. Each run's meta carries that rewrite's cost: about $0.0015 for the 13 typed dev searches per set, and $0.0046 for the union.
- **HyDE captions** come from the same cached call. A production rewrite that dropped them would save about 120 output tokens per search (about $0.05 per 1,000).
- **Latency:**
  - Per-run `query_p50_s` was measured on a shared 4-core box under load 3–9 from other agents, so it is noisy (0.11–0.41 s).
  - A cleaner comparison interleaved warm timings (typed dev searches, repeat-1 parses, 4 reps). Median ratio to the base: e2 1.21, e3 1.17, e4 1.87, e5 1.36, e6 1.09, e7 0.97, e8 1.00.
  - Base typed p50 in that pass was 0.26 s.
  - The rewrite call (about 2.3 s p50; 2.6 s for the slowest of three in e6) dominates every variant.
