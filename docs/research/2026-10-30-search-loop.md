# Research: the search and enrichment loop

*30 Oct 2026 · processor · proposes [Amendment A-003](../amendments.md) · loop record: `experiments/LOG.md`, `experiments/STATE.md`, `experiments/results/`*

**In one line:** an honest search over captions scores dev nDCG@10 **0.49**. One cheap LLM text pass per item, indexed as its **own** keyword field and vector, adds **+0.06**. Turning the rewrite's invented captions into an extra query vector (HyDE) adds **+0.02** more, to **0.57**: +0.08 [+0.04, +0.13] on dev, **+0.065 [+0.03, +0.10] over all 22 searches**, at ~$0.18 per 1,000 items once and ~$0.12 per 1,000 searches. On the 6 held-out test searches alone the gain is smaller and not significant (+0.023 [−0.01, +0.05]; recall@100 +0.06 [+0.01, +0.11]), and HyDE's share is not confirmed there. Everything else we tried (17 more ideas) didn't clear the bar. The remaining gap is media: what is **said, shown and played** needs audio and frames we can't fetch for Instagram.

## The test

- **Corpus:** one founder's Instagram export, 21,293 items (20,202 with any text). No media, comments or song names.
- **Searches:** 22 real searches (16 dev, 6 test). Answers were found by Muse matching words in captions and its own video descriptions ("MU"), then reviewed.
- **Protocol** (`experiments/BRIEF.md`): every method was built by one agent and scored by a **fresh evaluator agent** that never saw the method. Each round, the evaluator blind-judged the unjudged top-10 results of every run (655 new judgments over 11 rounds: 10 on dev, 1 on test), so new methods were not penalised for surfacing unlabelled items. One variable per experiment, preregistered. **Adopt** only if Δ nDCG@10 ≥ 0.03 with the paired 95% CI above 0, or ≥ 0.02 with more wins than losses and no extra cost.
- **Rewrite noise:** the LLM rewrite varies between calls (mean per-search range 0.13), so every experiment ran on three cached rewrite sets and Δ is averaged per search over the three before bootstrapping.
- **Limits:** one person; 16 dev searches (8 kinds, five of them a single search); differences under ~0.02 are noise.

## Two biases found and fixed

1. **The old rewrite was leaked.** The hand-simulated rewrites behind the previous "0.51" were written by an assistant that had read the answers. A real logged gpt-5-nano rewrite scores **0.49 vs 0.58** for the leaked one (−0.08 [−0.19, −0.01]); the biggest drops are on vibe (0.87 → 0.21) and place. All later numbers use the real rewrite.
2. **MU presence leaks labels.** Muse described 5% of the corpus but 95% of the right answers. Merely moving MU items to the top, with no MU text, scores +0.16. So the MU "ceiling" (+0.04 appended to captions, +0.20 as separate fields) is mostly leakage, not headroom (`experiments/results/muse-ceiling.md`). Its one robust lesson: description text must be indexed **as its own field**, not appended to the caption; appending hurt vibe and people searches.

## What won

| Step | Dev nDCG@10 (latest labels) | Δ [paired 95% CI], W/L/T | R@100 | Cost |
| --- | --- | --- | --- | --- |
| Hand (leaked) rewrite baseline | 0.578 | — (reference only) | 0.49 | $0 |
| No rewrite | 0.411 | — | 0.42 | $0 |
| **Honest base:** gpt-5-nano rewrite (qr-v1) + bge-small dense (gate, PRF) + BM25 + RRF | **0.489** | +0.085 [+0.02, +0.15] vs no rewrite | 0.51 | $0.12 / 1k searches; +2.3 s |
| **+ tier-1 enrichment** (B2): gemini-3.1-flash-lite writes summary, facets, unknown facets and likely searches per item; BM25 over that text and bge-small over it join the RRF as two extra lists | 0.548 | **+0.059 [+0.016, +0.108], 13/3/0** | 0.52 | $0.18 / 1k items (Batch); +0.05 s |
| **+ HyDE** (B3, **finalist**): the rewrite's 3 invented captions → one extra query vector, 0.3·query + 0.7·mean(captions), in both dense lists | **0.570** | **+0.022 [+0.008, +0.037], 10/1/5** vs B2; **+0.080 [+0.036, +0.133], 13/3/0** vs honest base | 0.53 | $0 extra (captions come from the same rewrite call); +0.1 s |

**Test split (6 held-out searches: 5 typed + 1 more-like-this; scored once for all finalists after blind judging of 88 pooled items; test scoring 2 of the 3 allowed):**

| System | nDCG@10 [CI] | R@100 | P@10 | MRR |
| --- | --- | --- | --- | --- |
| **B3 (finalist)** | **0.565** [0.39, 0.78] | **0.475** | 0.750 | 0.972 |
| B2 (no HyDE) | 0.556 | 0.473 | 0.739 | 0.963 |
| Honest base | 0.543 | 0.415 | 0.739 | 1.000 |
| Hand (leaked) rewrite baseline | 0.590 | 0.420 | 0.800 | 1.000 |

- B3 vs honest base: **+0.023 [−0.010, +0.053]**, 4/1/1, positive in all three repeats; R@100 **+0.060 [+0.007, +0.107]**.
- B3 vs B2 (HyDE alone): +0.009 [−0.027, +0.054], 2/3/1. **Not confirmed on test.**
- B3 vs the leaked hand baseline: −0.025 [−0.17, +0.08]; almost all of it is the one place search (0.31 vs 0.65), where the leaked rewrite knew the answer. B3 has the better recall (+0.055 R@100).
- **All 22 searches (dev + test, same labels):** B3 0.569 vs honest base 0.504: **+0.065 [+0.028, +0.103], 17/4/1**; R@100 +0.033 [+0.001, +0.062]. The honest base is 0.073 below the leaked baseline; B3 closes that gap to −0.008 [−0.09, +0.07].
- Reading: the enrichment gain holds up in direction and in recall; with n = 6 the test can't confirm its size. HyDE should be treated as a free, optional extra, not a proven gain.

**By kind (dev, r10 labels, honest base → B3):**

| topic (5) | name (3) | more like this (3) | people (1) | said/shown (1) | vibe (1) | place (1) | audio (1) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.43 → 0.56 | 0.56 → 0.63 | 0.65 → 0.69 | 0.62 → 0.89 | 0.66 → 0.72 | 0.21 → 0.31 | **0.51 → 0.43** | 0.06 → 0.00 |

Kinds with one search are anecdotes. Place and audio got worse; vibe stays far below what the leaked rewrite reached.

**Why enrichment works without media:** it doesn't add facts so much as vocabulary. "What kind of thing this is", topics and likely searches bridge the 37% of answers that share no word with the query. A reference check against MU on 200 items (`experiments/results/e9-reference-vs-mu.md`) shows text-only enrichment gets topic (4% missed) and people (13%) right, but misses 96% of the audio, 60% of the place and 50% of the speech MU had, and contradicts MU on 9% of items.

## What didn't (dev, Δ vs its base; full rows in `experiments/LOG.md`)

| Idea | Δ nDCG@10 | Note |
| --- | --- | --- |
| PRF from the fused list | −0.025 | |
| BM25 feedback (RM3) | 0.000 | no recall gain either |
| Per-phrase rank fusion | −0.014 | 1.9× slower |
| Interaction prior (saves, self-shares) | −0.003 | |
| Same-creator expansion | +0.011 | |
| Union of 3 rewrites | +0.028 [−0.02, +0.08] | 3× rewrite cost |
| Wider rewrite prompt (qr-v2) | +0.025 → +0.007 on B2 | |
| LLM graded rerank of top 30 (gpt-5-nano) | +0.016; +0.013 on B3 with summaries | +$0.26–0.28 / 1k searches, **+2.8–3.7 s**; best single-answer MRR (0.51 → 0.62) — a candidate opt-in "precise" mode |
| ColBERT re-score leg | +0.020 | 19.5 KB/item |
| EmbeddingGemma-300M (local) | +0.043 on honest base; +0.017 on B2 | 9× model, licence check |
| Gemini Embedding 2 (cloud) | +0.069 [−0.004, +0.136] on honest base; +0.020 on B2 | breaks local search |
| More-like-this: same-collection list | −0.002 | |
| More-like-this: LLM "what makes these alike" plan | +0.020 overall; **+0.049 to +0.109 on every MLT search** | only 3 dev MLT searches; a per-kind decision |
| Gate-failing items rejoin dense by enrichment kind | −0.008 | |
| Enrichment prompt v2 (fixes "unknown" hedging, kind known 65% → 89%) | −0.025 | more labels, worse top 10 |

Lessons: (1) with an LLM rewrite in place, classic feedback and fusion tweaks are worth ~0; (2) a better embedder helps the caption-only system but most of that gain overlaps with what enrichment already adds; (3) rerankers help precision a little but cost seconds; (4) **recall@100 barely moved (0.51 → 0.53) with any text method** — the missing half of the right answers needs what is said, shown and played.

## Cost, speed and the desktop

| | Finalist (B3) |
| --- | --- |
| Enrichment, once per item | $0.18 / 1k items with Gemini Batch ($0.36 standard); 21k items $3.7, 100k $18; Batch finished 15.8k items in ~5 min |
| Enrichment storage | ~1.1 KB / item (text + 384d fp16 vector); total ~2.9 KB / item with the caption index |
| Query | rewrite ~2.3 s + search 0.3–0.5 s; ~$0.12 / 1k searches |
| Per user (21k items, 100 searches/month) | ~$3.7 once, then ~$0.01/month + new items (~$0.0002 each) |
| 1,000 users × 21k | ~$3,700 once, less with a shared content cache |
| Local fit | bge-small everywhere (cloud and desktop share vectors); BM25 local; **the enrichment pass and the rewrite need a cloud LLM** (or the user's own agent via MCP). A 1–4B local LLM would take days of CPU for a 21k backfill (`experiments/research/item-text-enrichment.md`), so: cloud Batch for the first report, then per-item calls for new items. |

## What still needs media

- **Audio** (0.04 nDCG): song title/artist is not in the export; MU had it for 36% of items. Needs permitted audio (DM-share media if it is a file, on-device capture, founders' files) plus fingerprinting (ShazamKit on device; AudD ~$2–5 / 1k). See `experiments/research/mlt-multimodal-audio-media.md`.
- **Shown / said / place / vibe:** a description pass over one thumbnail or keyframes (~$0.5–0.65 / 1k reels with Flash-Lite) or 30 s of audio (~$0.8 / 1k). Index it the same way as tier 1: its own field and vector.
- **More like this:** visual vectors (local SigLIP2 on thumbnails, or Gemini Embedding 2 on keyframes ~$0.36 / 1k).
- All of these wait on A-002 for Instagram, or on a `YOUTUBE_API_KEY` for YouTube thumbnails (none was set). Projected full-corpus spend for a Flash-Lite video pass: ~$14 with Batch.

## Spend

OpenAI **$0.09** (rewrites, rerank, pilot); Gemini **$6.70** (enrichment pilot, sample, full corpus, prompt v2, Gemini Embedding 2 indexes). Ledger list-price estimates; not reconciled with the billing pages (no access from the loop).
