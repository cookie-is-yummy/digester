# Flaws, ranked (phase 3, 30 Oct 2026)

Ranked by expected gain × searches hurt ÷ cost, then by fit: what the export and shares contain, local/desktop fit, zero user effort. Sources: the benchmark (`benchmark-baseline.md`), the MU ceiling (`muse-ceiling.md`), experiment 1 (`2026-10-30-e1-real-rewrite.md`) and the five research notes in `../research/`.

**Honest base now:** real gpt-5-nano rewrite (qr-v1) + bge-small dense with PRF + BM25 + RRF: dev nDCG@10 **0.496** (mean of 3 rewrite repeats, r2 labels), R@100 0.47.

| Rank | Flaw | Evidence | Searches hurt | Fix to test | Cost | Local fit |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Recall: half the right answers never reach the top 100** | R@100 0.47; the MU ceiling's gains were mostly recall (0.43 → 0.62–0.77) | All | Feedback on the BM25 leg from the fused top 10; PRF from the fused list instead of the dense list; per-phrase rank fusion; HyDE phrases | Free | Yes |
| 2 | **The real rewrite is unstable and weaker than the leaked one** | Three repeats differ by 0.13 per search; vibe 0.87 → 0.21, place 0.84 → 0.51 vs the hand rewrite | Typed (13 dev) | Union of several rewrite samples; HyDE captions (already produced by qr-v1) as extra dense phrases | ~$0.12–0.36 per 1,000 searches | Needs a cloud LLM or the user's agent |
| 3 | **What is shown, said and felt is missing from the text** | 37% of right answers share no word with the search; ceiling R@100 for people/vibe/topic rises to 0.80+ only with separate description fields | Topic, vibe, people, task, place | Tier-1 text enrichment per item (summary, facets, likely searches) indexed as its **own BM25 field and vector**, fused by RRF (the ceiling showed appending hurts) | ~$0.05 per 1,000 items (gpt-5-nano batch); ~$1 for the corpus | Cloud batch for backfill; new items via cloud or the user's agent |
| 4 | **Ranking inside the top 30** | success@5 saturated but P@10 0.62; web cross-encoders hurt earlier | All | LLM graded rerank of the fused top 30 | ~$0.25 per 1,000 searches, +1.5–4 s | Cloud only (local 0.6B reranker too slow on CPU) |
| 5 | **More like this** is visual | 0.65 on r1 labels but 3 searches; every MLT example sits in a collection | MLT | Same-collection leg; LLM "what makes this alike" query | Free / <$0.01 | Yes / cloud |
| 6 | **Embedder** may be outdated | bge-small (2023) vs 2025–26 small models | Dense leg | Swap bge-small for a newer small local model | Free (CPU time) | Must stay small |
| 7 | **Thin items** (1,091 with no text, 26% fail the gate) | 7% findable | Any whose answers are thin | Same-creator expansion; collection names as text; enrichment flags | Free | Yes |
| 8 | **Audio** = 0 | Song names are not in the export; MU had them for 36% of items | Audio | Needs permitted media (A-002) or fingerprinting; **design + cost only** | — | ShazamKit-style on device |
| 9 | **Rewrite latency** 2.3 s p50 | Benchmark | All typed | Cache; show un-rewritten results first, then refine; faster model | — | — |
| 10 | **Interaction priors** unused | Personal-search literature | All | Small capped boost for saves/self-shares | Free | Yes |

## Order of experiments (free before paid, one variable each, base = honest base)

1. Fusion and feedback, free: PRF from the fused top 5; BM25 feedback from the fused top 10; per-phrase rank fusion.
2. Query side, near-free (rewrites already cached): HyDE captions as extra dense phrases; union of three rewrite samples.
3. Priors and creators, free: capped importance boost; same-creator expansion.
4. Embedder swap, free CPU time (after the embedder research note).
5. Tier-1 item enrichment as a separate field + vector: pilot 200 → label-independent sample → full corpus if it wins.
6. LLM rerank of the top 30.
7. More-like-this: collection leg; LLM "what makes these alike".
8. Media (audio, shown) for later: design and cost only, per `../research/mlt-multimodal-audio-media.md`.
