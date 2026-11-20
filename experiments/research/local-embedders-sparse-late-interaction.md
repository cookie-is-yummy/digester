# Research: retrieval models that run locally

*30 Oct 2026 · Researcher subagent · topic: local dense embedders, learned sparse, late interaction, cloud references. No evaluation was run; nothing under `data/evals/labels/` was read.*

**In one line:** bge-small is still a reasonable desktop default. Three free changes are worth testing, one variable each:

- a stronger dense model of about the same CPU cost: EmbeddingGemma-300M, which is also multilingual;
- a ColBERT re-score of the fused top 100 (answerai-colbert-small, same speed as bge-small);
- an inference-free learned-sparse leg (opensearch doc-v3-gte) for the 37% of answers that share no word with the search.

Separately, **sorting texts by length before batching makes local embedding about 1.7× faster for free.**

## How the speeds were measured

- **Setup:** fastembed 0.9.1, ONNX Runtime, `threads=4`, batch 32. The machine is a 4-vCPU Xeon @ 2.8 GHz with AVX-512 VNNI and no GPU.
- **Texts:** 120–200 synthetic caption-like texts, about 64 BERT tokens on average, built from generic words with a log-normal length distribution matched to the corpus character-length percentiles (p50 206, p90 655 chars). No corpus text was used.
- **Caveat: shared box.** Other agents were running at the same time (load average 2.4–14), so absolute numbers are noisy. Read them as relative speeds. The table uses round 2 of a 2-round A/B pass at load 2.4–6; the two rounds agreed within about 10% once the load fell below 6.
- **Converting to corpus speed:** corpus items run about 110 OpenAI tokens each (2.2M tokens over 20,202 items, see `docs/research/2026-10-30-search-storage.md`). That is about 1.7× the synthetic texts, so **corpus items/s ≈ synthetic ÷ 1.7**.
  - Sanity check: unsorted bge-small gives 28.7 ÷ 1.7 ≈ 17 items/s on 4 cores, against the 7.5 items/s measured earlier on 2 cores.
- **Free speedup, measured on every model:** sorting texts by length before batching cuts padding. It gave **1.6–1.9× more items/s** (bge-small 28.7 → 49.5). `methods/build_embeddings.py` does not sort today.
- Raw logs, outside the repo: `/tmp/claude-0/-home-user-digester/859ff419-2ec3-52f1-a7dd-2ab1b038b8ed/scratchpad/textemb_bench/out2.txt`.

## Comparison table

Column notes:

- **Retrieval score** is a public number, not ours. BEIR = BEIR average nDCG@10. MTEB-R(en) = MTEB English v2 retrieval. MTEB-R(ml) = MTEB Multilingual v2 retrieval.
- **CPU items/s** is the synthetic rate with texts sorted by length.
- **21k time** is the estimated time to embed 20.2k corpus items on 4 CPUs with sorting (synthetic ÷ 1.7).
- **Storage per item** assumes fp16 dense vectors, 8 bytes per sparse non-zero, and fp16 token vectors at about 1.7× the synthetic token count.

| Model | Params | Dims | License | Retrieval score (public) | CPU items/s (synthetic, sorted) | 21k time, 4 CPU | Storage per item | Multilingual | fastembed |
|---|---|---|---|---|---|---|---|---|---|
| **bge-small-en-v1.5** (baseline, Qdrant int8 ONNX) | 33M | 384 | MIT | BEIR 51.7; MTEB-R(en) 53.9 [1] | 49 (29 unsorted) | ~12 min (20 unsorted) | 768 B | no | yes |
| snowflake-arctic-embed-xs | 23M | 384 | Apache-2.0 | MTEB-R ~50 (v1 card) | 128 | ~5 min | 768 B | no | yes |
| snowflake-arctic-embed-s (v1) | 33M | 384 | Apache-2.0 | BEIR 52.0 [3] | 58 | ~10 min | 768 B | no | yes |
| granite-embedding-small-english-r2 | 47M | 384 | Apache-2.0 | BEIR 50.9; MTEB-R(en) 53.9 [1] | 40 | ~14 min | 768 B | no | yes |
| bge-base-en-v1.5 | 109M | 768 | MIT | BEIR 53.2; MTEB-R(en) 54.8 [1] | 17 | ~35 min | 1.5 KB | no | yes |
| nomic-embed-text-v1.5 (Q) | 137M | 768 (MRL to 64) | Apache-2.0 | MTEB-R ~53 | ~15 (unsorted 7.9, contended) | ~40 min | 1.5 KB (or 512 B at 256d) | no | yes |
| **EmbeddingGemma-300M** | 308M (≈100M non-embedding) | 768 (MRL 512/256/128) | Gemma terms [5] | MTEB-R(en) 55.7, MTEB-R(ml) 62.5 [2] | 17 | ~34 min | 1.5 KB (768 B at 384d) | **yes, 100+ languages** | yes (prefixes by hand) |
| arctic-embed-m-v2.0 | 305M | 768 (MRL 256) | Apache-2.0 | BEIR 55.5; MTEB-R(en) 58.4 [1]; MTEB-R(ml) 54.8 [2] | not measured (≈ EmbeddingGemma) | ~35–45 min (est.) | 1.5 KB | yes | custom ONNX |
| gte-modernbert-base | 149M | 768 | Apache-2.0 | BEIR 55.2; MTEB-R(en) 57.0 [1] | not measured | ~40 min (est.) | 1.5 KB | no | custom ONNX |
| LightOn DenseOn | ~149M | — | — | BEIR 56.2 [4] | not measured | ~40 min (est.) | — | mDenseOn | no |
| multilingual-e5-small | 118M (22M active) | 384 | MIT | MTEB-R(ml) 49.3 [2] | not measured (≈ bge-small) | ~12–15 min (est.) | 768 B | yes | custom ONNX |
| granite-embedding-97m-multilingual-r2 | 97M (28M active) | 384 | Apache-2.0 | MMTEB retrieval 60.3 [6] | not measured (≈ bge-small) | ~15 min (est.) | 768 B | yes (200+) | custom ONNX [7] |
| bekko-embedding-v1-a25m (Jul 2026) | 123M (25M active) | 384 (MRL) | MIT | MMTEB retrieval 57.5 [6] | 134/s on a Ryzen 7950X [6] | ~15 min (est.) | 768 B | yes | custom ONNX |
| potion-retrieval-32M / potion-multilingual-128M (static) | 32M / 128M | 512 / 256 | MIT | well below transformers | **~800** | <1 min | 1 KB / 512 B | multilingual variant | yes |
| bge-m3 (dense + sparse + ColBERT) | 568M | 1024 | MIT | MTEB-R(ml) 54.6 [2]; BEIR-15 dense 48.8 [8] | not measured (≈3× bge-base) | ~2 h (est.) | 2 KB + sparse + multi-vector | yes | no |
| Qwen3-Embedding-0.6B (Q) | 596M | 1024 (MRL) | Apache-2.0 | MTEB-R(en) 61.8, MTEB-R(ml) 64.7 [2][9] | ~1 (unsorted, contended) | ~3–5 h | 2 KB | yes | yes |
| jina-embeddings-v3 / v5-text-nano | 570M / 239M | 1024 / 768 | **CC BY-NC 4.0** [10] | v5-nano MMTEB 65.5 | — | — | — | yes | v3 only |
| *Learned sparse* | | | | | | | | | |
| BM25 (current, sklearn) | — | sparse | — | BEIR ~43–44 | ~9,600 | seconds | ~34 nnz ≈ 0.3–0.5 KB | tokenizer-dependent | yes (`Qdrant/bm25`) |
| miniCOIL v1 | ~0.1 GB | sparse (4d per stem) | Apache-2.0 | +0.9 pt over BM25 on 5 BEIR sets [11] | 70 | ~5 min | ~128 nnz ≈ 1.7 KB | no | yes |
| SPLADE++ ED (`prithivida/Splade_PP_en_v1`) | 110M | 30.5k vocab | Apache-2.0 | BEIR 50.1–50.7 [12] | 5.7 | **~100 min** | ~111 nnz ≈ 1.5 KB | no | yes |
| **opensearch neural-sparse doc-v3-gte** (inference-free queries) | 133M | 30.5k vocab | Apache-2.0 | BEIR-13 54.6 [13] | 5.6 | **~100 min** (~75 min on info-ok items only) | ~222 nnz ≈ 3 KB | no | yes |
| *Late interaction* | | | | | | | | | |
| **answerai-colbert-small-v1** | 33M | 96 per token | Apache-2.0 | BEIR 53.8 (vs bge-small 51.7, ColBERTv2 50.0) [14] | 55 | ~11 min | ~110 tok × 96 × 2 B ≈ **21 KB** | no | yes |
| colbertv2.0 | 110M | 128 per token | MIT | BEIR 50.0 | ~5 (unsorted, contended) | ~60 min (est.) | ≈ 28 KB | no | yes |
| LightOn LateOn (Apr 2026) | 149M | 128 per token | Apache-2.0 | BEIR 57.2 (self-reported) [4] | ~5 (unsorted, contended; 6× slower than answerai-small in the same window) | ~60 min (est.) | ≈ 32 KB | mLateOn | yes |

**Query-side cost (ms per query, synthetic):**

| Model | ms per query |
|---|---|
| bge-small | 2–5 |
| EmbeddingGemma | 5–6 |
| bge-base | 6 |
| answerai-colbert-small | 12 |
| SPLADE++ | 10–25 |
| opensearch doc-v3-gte | 0 (tokenizer + IDF lookup) |
| miniCOIL | 2–3 |
| Qwen3-0.6B | ~110 |

All are well under the 0.09 s query p50.

## Findings

1. **Small English dense models have plateaued; nothing at bge-small's cost is clearly better.**
   - Public numbers: arctic-s 52.0 BEIR, granite-small-r2 50.9, bge-small 51.7 [1][3].
   - A real gain needs the base tier (bge-base +1.5 BEIR; gte-modernbert / arctic-m-v2 +3.5–3.8) at about 3× the CPU time.
   - In our system the dense leg is diluted by BM25 + RRF + PRF, and earlier OpenAI-3-small ≈ bge-small after fusion. So expect at most a fraction of the public gap.
2. **EmbeddingGemma-300M is the best desktop candidate in the "base" cost class.**
   - It runs at bge-base speed here, about 3× slower than bge-small. Most of its 308M parameters are a 262k-token embedding table.
   - It is #1 under 500M on MTEB multilingual and English [2][15]. MTEB-R(en) is 55.7 vs 53.9; multilingual retrieval is 62.5, against 49.3 for multilingual-e5-small.
   - Matryoshka truncation to 512d costs −1.0 (multilingual) to −1.7 (English) points [2]. The 768d → 384d storage choice must be part of the experiment, not assumed.
   - It is the only candidate that also solves "multilingual some day" without a later model change.
   - License: Gemma Terms of Use (commercial use allowed under a use policy) [5]. Check with the founders before adopting.
   - fastembed does **not** add its prefixes. We must send `task: search result | query: …` for queries and `title: none | text: …` for items.
3. **Smaller multilingual options exist if 3× is too slow for the desktop.**
   - granite-embedding-97m-multilingual-r2 (Apache, 384d, 28M active parameters, MMTEB retrieval 60.3) and bekko-a25m (MIT, 57.5) [6] run at roughly bge-small cost.
   - Neither is built into fastembed. Both have ONNX exports, so they would need `TextEmbedding.add_custom_model`.
4. **Learned sparse vs BM25 on short text.**
   - No published evaluation covers captions or tweets. The closest is web-document titles, where SPLADE beats BM25 at higher compute cost [16].
   - BEIR gains over BM25 are large for SPLADE++ (about +6 points) and doc-v3-gte (about +10), but small for miniCOIL (+0.9).
   - miniCOIL only re-weights exact matches [11], so it cannot help the 37% of answers that share no word with the search. It is cheap but not worth a slot.
   - SPLADE-style document expansion is exactly the mechanism for vocabulary mismatch.
   - doc-v3-gte is "inference-free": queries are just tokenized and weighted by IDF [13], so a query costs nothing on desktop or in the cloud.
   - Its cost is indexing: about 3 corpus items/s, roughly 100 min for 21k on 4 cores and 8 h for 100k. On a cloud GPU it would take minutes.
   - Index size: about 220 nnz × 8 B ≈ 2–3 KB per item, about 60 MB for 21k. That is negligible.
   - **Hashtag risk:** BERT-WordPiece vocabularies split `#geometrynodes` into word pieces. Feed the expansion the `full` view, which already holds the split words.
5. **Late interaction.**
   - answerai-colbert-small-v1 is the same size and speed as bge-small (55 vs 49 items/s here) and scores +2.1 BEIR over bge-small [14].
   - As a **re-scorer of the fused top 100**, precomputed token vectors cost about 21 KB per item fp16: ≈ 0.45 GB for 21k, ≈ 2.1 GB for 100k, half with int8, and less again with PLAID-style 2-bit residuals (ColBERTv2 shrank 154 → 25 GB with no loss [17]).
   - A query costs 12 ms to encode plus about 100 × 110 × 32 × 96 ≈ 34 MFLOP of MaxSim, which is under 5 ms.
   - Encoding the 100 candidates at query time instead would take about 3 s on CPU, so precompute, or store vectors only for info-ok items.
   - **Risk:** last round's off-the-shelf cross-encoders *hurt* (0.42 → 0.33). ColBERT is a bi-encoder trained on the same MS MARCO-style data, so it may hurt too. Fuse it as an extra RRF leg rather than letting it replace the order.
   - A full ColBERT index (LateOn, 57.2 BEIR) is a bigger bet. It means about 60 min of indexing here and roughly 0.2–0.5 s per query for brute-force MaxSim over about 2.3M token vectors. It is a follow-up only if the re-score helps.
6. **Cloud references.**
   - **OpenAI `text-embedding-3-small`:** $0.02 per 1M tokens ($0.01 in batch). It is not open, so the desktop must call the API or re-embed locally.
   - **Gemini Embedding 2:** model ID `gemini-embedding-2`, **$0.20 per 1M text tokens, $0.10 in batch** (verified on Google's pricing page [18]). It has 128–3072 Matryoshka dims (768/1536/3072 recommended, auto-normalized) and an 8,192-token limit. It uses text prefixes (`task: search result | query:`) instead of `task_type`, and is **incompatible with gemini-embedding-001** [19]. Its draw is multimodal (image, audio, video in one space), not text quality per dollar.
7. **The cloud-to-desktop constraint is weaker than assumed; the real constraint is the query.**
   - With length sorting, a desktop with 4 cores re-embeds 21k items with bge-small in about 12 min, or EmbeddingGemma in about 35 min. So "same vectors in cloud and desktop" is a convenience, not a hard requirement.
   - What *is* hard: every query must be embedded by the same model as the index. A cloud-only model (OpenAI, Gemini) makes desktop search depend on the network and the API forever.
   - "Same model" must mean the **same ONNX build**. fastembed's bge-small is Qdrant's **int8-quantized** export (`Qdrant/bge-small-en-v1.5-onnx-Q`). A PyTorch or GPU fp16 run in the cloud gives slightly different vectors.
   - Record the exact artifact in `embedding_model` (rule 10). Before handing cloud vectors to a desktop, check the cross-runtime cosine on 200 synthetic texts (expect > 0.99).

## Cost: 21k and 100k items

Token counts: about 2.3M tokens for 21k items and about 11M for 100k, at about 110 tokens per item.

| Option | 21k items | 100k items | Notes |
|---|---|---|---|
| bge-small local, 4 CPU, sorted | ~12 min, $0 | ~1 h, $0 | desktop-viable |
| EmbeddingGemma / bge-base local | ~35 min, $0 | ~3 h, $0 | desktop background job |
| answerai-colbert-small (re-score vectors) | ~11 min + 0.45 GB | ~55 min + 2.1 GB | int8 halves storage |
| opensearch doc-v3-gte sparse | ~100 min, $0 | ~8 h CPU; minutes on a GPU | queries free |
| SPLADE++ | ~100 min | ~8 h | query 10–25 ms |
| OpenAI 3-small | $0.05 ($0.02 batch), ~72 s | $0.22 ($0.11 batch) | not local |
| Gemini Embedding 2 | $0.46 ($0.23 batch) | $2.20 ($1.10 batch) | not local; multimodal later |
| Cloud GPU burst for local models (e.g. an L4 at about $0.8/h) | <5 min, ~$0.10 | ~10 min, ~$0.20 | same ONNX build, so the vectors are reusable |

## Recommendation: preregisterable experiments

Each experiment changes ONE thing against the current best (rewrite + bge-small dense with PRF + BM25 + RRF). All are free and run on this box. Order: cheapest and most informative first.

**Prerequisite, an engineering change that does not affect quality:** sort texts by length within `build_embeddings.py`, restoring the original order before saving. That gives about 1.7× faster embedding. Vectors are unchanged except for numeric noise from batch padding; verify cosine > 0.999.

### E1: ColBERT re-score leg (answerai-colbert-small-v1)

- **Variable:** add a 4th RRF leg. It is the MaxSim ranking, by answerai-colbert-small-v1, of the current fused top 100.
- **Query:** the rewrite's phrases, max over phrases.
- **Item text:** the `full` view.
- **Hypothesis:** token-level matching re-orders the top 10 better than single-vector bge-small, especially for name and topic searches.
- **Expected Δ nDCG@10:** −0.02 to +0.03, centred on +0.01. R@100 unchanged by construction, because it only re-orders the top 100.
- **Compute:** about 11 min to encode 20.2k items on 4 CPUs (or only the union of the dev top 100s, under 1 min). Storage ≈ 0.45 GB fp16. About 15 ms per query.
- **Fits in under 1 h here:** yes.

### E2: Dense-model swap bge-small → EmbeddingGemma-300M (768d, prefixes as specified)

- **Everything else unchanged:** PRF, the info gate, BM25 and RRF.
- **Hypothesis:** a stronger, multilingual dense leg improves recall of paraphrase answers and non-English captions.
- **Expected Δ nDCG@10:** +0.01 to +0.03. Expected Δ R@100 is +0.02 to +0.05.
- **Compute:** about 35 min to embed 20.2k on 4 CPUs with sorting. 1.5 KB per item.
- **Fits in under 1 h here:** yes, if run in the background.
- **Optional follow-up (a separate experiment):** the same model truncated to 384d, to match today's storage.

### E3: Add a learned-sparse leg, opensearch-neural-sparse-encoding-doc-v3-gte

- **Variable:** a 4th RRF leg. Items are expanded on the `full` view. The query is the rewrite's keyword string, encoded with the tokenizer and the IDF table (inference-free).
- **Hypothesis:** document expansion adds related terms, targeting the 37% of answers with no word in common with the search and the low R@100 (0.43).
- **Expected Δ nDCG@10:** +0.00 to +0.03. Expected Δ R@100 is +0.03 to +0.06.
- **Compute:** about 100 min on 4 CPUs for 20.2k, or about 75 min for info-ok items only. Index about 60 MB. Queries cost about 0 ms.
- **Fits in under 1 h here:** **no.** Run it in the background, or on the label-independent sample (union of the baseline top 200 + 2,000 random ≈ 4.5k items, about 25 min). The sample cannot measure R@100, so treat it as a pilot.
- **Fallback if too slow:** SPLADE++ has the same cost and is not better, so it is not a fallback. miniCOIL (5 min) is a cheap control but is expected to give about 0.

### E4 (paid reference, after E2): dense swap bge-small → Gemini Embedding 2 at 768d

- **Cost:** batch, about $0.23 for 21k. Pilot 200 items first via `lib/ai.py`.
- **Purpose:** an upper reference for "how much does a frontier text embedder buy after fusion".
- **Expected Δ nDCG@10:** +0.00 to +0.04, given that OpenAI-3-small ≈ bge-small after fusion.
- **Adoption:** only if the gain beats E2 by at least 0.03. Otherwise it stays a reference, because it breaks local search.

**Not recommended now:**

- **Qwen3-Embedding-0.6B:** about 3–5 h for 21k on CPU, too slow for a desktop.
- **bge-m3:** too slow, and its sparse head is weak (BEIR-15 40.2 [8]).
- **jina v3/v5:** non-commercial license.
- **miniCOIL:** exact-match only.
- **potion static models:** about 800 items/s and good for an instant first pass, but far weaker. Revisit as a "preview while the real model runs" on desktop.
- **Full LateOn index:** only if E1 is positive.

## Sources

1. Granite Embedding R2, Tables 4/9/10 (BEIR, MTEB-v2 retrieval, speed): https://arxiv.org/html/2508.21085
2. EmbeddingGemma paper, Tables 5–7 and MRL ablation: https://arxiv.org/html/2509.20354
3. snowflake-arctic-embed-s v1 (cited in the answerai card): https://huggingface.co/answerdotai/answerai-colbert-small-v1
4. LightOn DenseOn / LateOn: https://blog.lighton.ai/blog-posts/the-retriever-you-actually-need · https://lighton.ai/benchmarks
5. Gemma terms: https://ai.google.dev/gemma/terms · ONNX build: https://huggingface.co/onnx-community/embeddinggemma-300m-ONNX
6. Bekko Embedding (with granite-97m-r2 numbers): https://huggingface.co/blog/hotchpotch/bekko-embedding
7. Granite Embedding Multilingual R2: https://arxiv.org/abs/2605.13521 · https://www.ibm.com/granite/docs/models/embedding
8. bge-m3 numbers via LightOn model cards: https://huggingface.co/lightonai/mLateOn · https://huggingface.co/lightonai/mSlideOn
9. Qwen3 Embedding: https://arxiv.org/pdf/2506.05176 · https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF
10. jina-embeddings-v5-text: https://jina.ai/news/jina-embeddings-v5-text-distilling-4b-quality-into-sub-1b-multilingual-embeddings/
11. miniCOIL: https://qdrant.tech/articles/minicoil/ · https://huggingface.co/Qdrant/minicoil-v1
12. SPLADE++: https://arxiv.org/abs/2109.10086 and the BEIR reproduction in https://arxiv.org/pdf/2306.11293 · Anserini BEIR regressions: https://github.com/castorini/anserini
13. OpenSearch doc-v3-gte card (BEIR-13 table, inference-free queries): https://huggingface.co/opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte
14. answerai-colbert-small-v1 card: https://huggingface.co/answerdotai/answerai-colbert-small-v1
15. EmbeddingGemma launch: https://huggingface.co/blog/embeddinggemma · https://deepmind.google/models/gemma/embeddinggemma/
16. SPLADE on web-document titles: https://arxiv.org/html/2511.22263v1 · SPRINT toolkit: https://arxiv.org/pdf/2307.10488
17. ColBERTv2 / PLAID compression: https://arxiv.org/pdf/2112.01488 · https://arxiv.org/pdf/2205.09707
18. Gemini API pricing (gemini-embedding-2 $0.20 / batch $0.10 per 1M tokens): https://ai.google.dev/gemini-api/docs/pricing
19. Gemini embeddings docs (dims, prefixes, incompatibility with 001): https://ai.google.dev/gemini-api/docs/embeddings
20. OpenAI embedding pricing ($0.02 per 1M tokens for 3-small): https://openai.com/api/pricing/ (the page refused automated fetches; price as published since 2024)
