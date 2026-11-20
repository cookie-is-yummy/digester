# Architecture review: is rewrite → dense + BM25 → RRF the right shape?

*8 Nov 2026 · round 8, phase B (`experiments/BRIEF-8.md`) · researcher, no evaluations run, no labels or `eval_work/` read · numbers from `experiments/STATE.md` and `experiments/results/` (aggregates) plus the web sources at the end. Everything here that changes an architecture boundary is **Proposed** and needs both founders (AGENTS.md › "When a request doesn't fit the docs"); a draft amendment is in section 8.*

**Doc gap, flagged:** the brief points to "the processor doc's section 8" for the privacy design (shared content store + private per-user vault with a revocable key). `docs/05-processor.md` has no section 8 and no vault. The nearest written pieces are A-001 (shared `content` rows + thin `user_items`), `07-privacy-and-safety.md` › Retention ("shared enrichment cache holds public content only… no user IDs") and › Security (revocable OAuth). This review assumes the design as the brief states it (section 3). The doc should be written before any of this ships.

## 0. Bottom line

1. **The current shape is roughly right, and the quality gains came from item representation, not from the query side.** 3-large vectors (+0.055 held-out) and the Instagram te pass (+0.05 to +0.09 on Instagram) are the only confirmed wins in 8 rounds. Every query-side add-on (stronger rewrites, typed slots, checker, PRF, router, soft time) is ≈ 0 or negative on held-out.
2. **The LLM rewrite is about 92% of the cost per search ($0.12 of $0.131 per 1k) and about 1.8 s of the 2.0 s p50.** It was worth +0.085 on descriptive Instagram searches in round 1. It has never been measured on short keyword searches, and over MCP the user's own agent already writes the query. This is the biggest open cost and latency lever.
3. **One index is fine; one pipeline is not.** Mixing the two platforms in one index costs only −0.007 (Instagram) and −0.017 (YouTube). But the add-ons act differently by platform: te lists help Instagram and hurt YouTube every time. The answer is **one index with per-platform list sets and per-query-shape paths behind one deterministic planner**, using platform as a soft prior. Do not use hard federated routing: the router's platform guess is 55% accurate.
4. **Ranked by expected value per dollar:**
   - (1) shape-routed planner with a no-rewrite keyword path ($0, saves money and about 1.8 s on routed searches);
   - (2) a deterministic creator index searched alongside items ($0 per search);
   - (3) an LLM listwise "refine" over the top 20 in the second stage (+$0.15–0.20 per 1k);
   - (4) learning fusion from search → watch feedback ($0 in API calls, but it needs a clean training pool);
   - (5) an MCP tool surface for the user's agent. Build it, but don't run our own agent loop by default;
   - (6) local learned sparse / late interaction / quantization, for desktop independence rather than quality.
5. **The new known-item sets measure a narrower task than the product's:** literal title recall on YouTube, LLM-written recall on Instagram. Verdicts on them need the caveats in section 7. Above all, **no method may use the search's timestamp**, because the label is defined by the watch that followed it.

## 1. The current design and what each part bought

Base H0 = C0 (gpt-5-nano rewrite qr-v1 → dense over 1–3 phrases + HyDE captions, BM25, PRF, RRF) with text-embedding-3-large 1,024 d. Library 136,908 items. "dev" = 44 searches; held-out = test / test2 / `yt_holdout` (now used up).

| Part | Evidence (Δ nDCG@10 unless noted) | Cost / latency | Verdict |
| --- | --- | --- | --- |
| LLM rewrite (qr-v1, nano) | +0.085 [+0.02, +0.15] vs no rewrite (round 1, Instagram, descriptive searches); instant path −0.077 dev, −0.066 over 22 | $0.12 / 1k; ~1.8 s (bare provider call ~0.9 s p50) | **Earned on descriptive searches; untested on keyword searches** |
| Stronger rewrite models | mini −0.012, gpt-5.5 +0.005 (round 6); flash-lite / 5.4-nano −0.01 to +0.01 | 3–95× cost | Dead line |
| HyDE (3 invented captions) | +0.022 dev; held-out +0.009 (2/3) | $0; +0.1 s | Free; unconfirmed |
| PRF / RM3 / per-phrase fusion | −0.025 / 0.000 / −0.014 | $0 | Not worth more work |
| 3-large vectors (H0) | dev +0.022; **held-out +0.055 [+0.013, +0.103], 15/4**; `yt_holdout` +0.056 | +$0.011 / 1k; $0.52 per library once; +0.1 s | **Confirmed** |
| te pass as separate lists (Instagram) | round 1 +0.059; test ig +0.051; F0 ig +0.067 [+0.020, +0.126]; H5b−H5 ig +0.030 | $0.18 / 1k items (Batch) | **Confirmed for Instagram** |
| te pass on YouTube / YouTube searches | −0.046 (round 3); F0 yt −0.014 dev, −0.049 test2; H5b−H5 yt −0.018 dev, −0.020 `yt_holdout` | same | **Hurts: crowding plus noise on titled videos** |
| Coverage-fair fusion | +0.059 over plain fusion; crowding 53% → 24% of YouTube top 10 | $0 | Required whenever lists cover different items |
| Guarded intent filters | +0.150 per cell (3 dev searches); one held-out win +0.21; round 3 ≈ +0.6 on behaviour/time searches | $0 (from the rewrite) | Keep; rare but large |
| Router platform calibration | right read +0.031 [+0.005, +0.062] (18); **misread −0.071** (7); held-out misread −0.064 / −0.083; head accuracy 0.55 | $0 | Net ≈ 0; needs a better prior |
| Soft time / format boost / tone | −0.032 per cell (18) / 0.000 (7) / +0.015 (3) | $0 (+0.8 s as a separate call) | Drop / drop / lead |
| Creator search | named creators +0.027 (test2, 2/0); described creators fail; H4 +0.24 on 1 search; **non-deterministic** | $0; p95 5–7 s with the LLM pick | Promising, unproven |
| LLM graded rerank top 30 | +0.016 (honest base), +0.013 [+0.001, +0.026] on B3; **single-answer MRR 0.51 → 0.62** | +$0.26–0.28 / 1k; +2.8–3.7 s | Best MRR lever measured; too slow as default |
| ColBERT re-score leg | +0.020 [−0.014, +0.053], 8/4/4 | $0; 19.5 KB/item; warm +0.06–0.10 s | Near miss on the bge-small base |
| Per-property checker | 0.000 | p95 +3.8 s | Dead |
| H5 package over H0 | dev +0.006; held-out +0.021 [−0.006, +0.051] | +$0.164 / 1k, +0.8 s as run | Not confirmed |

**What the table says about the shape:**

- **Recall is set by item text, and the query side mostly reorders.** Recall@100 stayed at about 0.51–0.53 across every text method in round 1. The wins came when item text or vectors changed.
- **Add-ons fail through cross-platform side effects,** not within-platform ordering. Within-YouTube ordering under F0 was identical to C0; the loss was Instagram items taking slots.
- **Anything that relies on a hard guess (router platform, invented time windows, format words) loses more on misreads than it gains on hits.** Soft, confidence-gated or word-guarded signals survive.
- **Latency and cost are almost all one LLM call.** Local search is 0.1–0.3 s.

## 2. What is now different

- **Known-item searches dominate personal search.** Email and desktop studies find about 95% of personal searches are lookups or re-finding. Queries are shorter than web queries and people reformulate about twice per task ([Dumais et al., via 2412.12330](https://arxiv.org/pdf/2412.12330); [Elsweiler et al.](https://strathprints.strath.ac.uk/32918/)).
  - The new eval sets (381 YouTube keyword searches; 150 Instagram half-remembered searches) finally measure this.
- **Query expansion helps weak retrievers and hurts strong ones and precise queries:** 28 of 30 analysed failures came from added terms ([Weller et al. 2024](https://arxiv.org/abs/2309.08541)). Short title-like keyword searches are the precise case.
- **Users' own agents will call us over MCP.** Then the agent writes the query, chooses filters and can call several times. Our rewrite duplicates its work and adds about 2 s per tool call.

## 3. Privacy frame used below

| Lives in the **shared content store** (public content, no user ids) | Lives in the **private vault** (per user, readable only with the user's key; revoking the key ends server-side access, MCP included) |
| --- | --- |
| Item text (caption / title, hashtags, creator), te pass on public captions (no collection names), item vectors (3-large, and any sparse or late-interaction vectors), classifier outputs (format/tone), public creator profiles built from public items | Interactions (likes, saves, shares, watches, collections), collection names, the query log and rewrite cache, click/watch feedback, per-user priors (platform split, creator affinity and era), learned per-user weights, friends' items (counts only, never sent to an LLM) |

**Rules this implies:**

- Anything computed per item from public text is computed **once** for all users.
- Anything keyed by a query, a click or an interaction is vault-only.
- An LLM call at query time sees the query plus public candidate text. That pairing reveals interest to the provider, as the rewrite already does today (07 › third-party text; no-training terms).
- Friends' items keep their slot and are never sent.

## 4. Alternatives

List prices from `experiments/lib/ai_prices.json`:
- gpt-5-nano $0.05 / $0.40 per M (cached input $0.005);
- gpt-5.4-nano $0.20 / $1.25;
- 3-large $0.13 per M.

Latency is p50 / p95 from this cloud container unless marked *est.*

### A1. Per-platform pipelines behind one deterministic planner (one index)

**What.** A code planner, with no LLM, reads three inputs:
- query shape: token count, question/description words, quoted names, time and behaviour words;
- a cheap query-performance signal: BM25 top-score gap, title-match coverage, whether a creator handle matches;
- the user's priors from the vault: platform share of matched creators and topics, the platform split of their saves.

It then picks a path:
- **Keyword path** (short, title-like, high title-match): no rewrite; raw-query 3-large vector + BM25 over own text, YouTube without te lists.
- **Descriptive path:** H0 as now, with te lists only for caption-type or untitled items (F0 eligibility), and coverage-fair fusion.
- **Structured path:** behaviour or time words; guarded filters from the rewrite.

**Platform** is a soft multiplier from the user's prior plus the router text guess, gated by confidence. It is never a filter, and never applied on a low-confidence read.

**Why.**
- Platform interference in one index is small (−0.007 / −0.017).
- The losses come from per-platform lists and misreads, which this removes.
- Routing by shape avoids the 55%-accurate platform guess.
- Federated search would add a separate merge problem and resource-selection errors ([Shokouhi & Si, FnTIR](https://nowpublishers.com/article/DownloadSummary/INR-010)), and we have one index already.
- QPP-based routers are cheap. kNN over past performance often matches learned routers ([2505.12601](https://arxiv.org/html/2505.12601v1)).

**Expected quality:**
- `known_dev` MRR −0.02 to +0.03 vs H0. The sign is uncertain: the rewrite might fix misspellings and add channel names, or it might paraphrase away exact title words.
- `dev` ±0.01: routing should rarely fire on dev's descriptive searches.
- `ig_known_dev` ≈ 0.
- The yt-side te removal is worth about +0.02 on YouTube searches (H5b−H5 −0.018 / −0.020, reversed).

**Cost:**
- Routed searches about $0.001 per 1k (one raw-query embedding; $0 with a local embedder).
- If about half of searches are keyword-shaped, the blended cost falls from about $0.131 to about $0.07 per 1k.
- $0 per item.

**Latency:** routed searches about 0.15 s local + 0.2–0.4 s for the embedding call (*est.*) ≈ 0.4 / 0.7 s; unrouted as H0 (2.0 / 2.6–2.9 s).

**CPU/desktop:** fully local except the 3-large query embedding (see A6).

**Privacy:** fewer LLM calls is strictly better. The priors are vault data, used locally at query time.

### A2. A creator-level index searched alongside items

**What.**
- One profile per creator with ≥ 2 items, in the shared store:
  - handle, display name, a profile vector (mean of members' 3-large vectors), a profile BM25 text (top member terms);
  - optionally one cheap LLM channel description from public titles/captions, and the H4 channel-type words.
- At query time, the creator list (dense + BM25 over profiles → creators → their items ordered by item score) joins RRF as a coverage-fair list.
- Per-user era and affinity priors come from the vault.
- Ties are sorted by id, which fixes the hash-order bug.

**Why.**
- Named creators win (+0.027, 2/0; H4 +0.24).
- Described creators fail on titles alone, because the target's titles rarely carry the identity the user remembers.
- Real YouTube keyword searches often carry a channel name (an expectation; `known_dev` will show it).

**Expected quality:**
- `known_dev` MRR +0.00 to +0.03 (named-channel searches);
- `ig_known_dev` +0.00 to +0.02, if half-remembered searches mention "that guy who…";
- `dev` ≈ 0 (fires rarely).
- Risk: a creator list pushes same-creator non-targets up on topic searches. Gate it on a handle/name match or a confident creator QPP.

**Cost:**
- $0 per search.
- Profiles: local, about 14 s for 47.6k creators.
- Optional LLM descriptions for creators with ≥ 3 items at nano Batch: about 300 in / 60 out tokens ≈ **$0.02 per 1k creators** ($1 for all 47.6k). Computed once in the shared store.

**Latency:** +0.01–0.05 s; no LLM pick (the LLM pick made p95 5–7 s).

**CPU/desktop:** yes.

**Privacy:**
- Profiles built from public content are shared.
- Era and affinity are vault data.
- **Mutual-follow creators get no shared profile and no LLM description** (friends are counts only).

### A3. LLM listwise "refine" over the top 20 (second stage)

**What.** After the instant or H0 list is shown, one call gets the query and 20 candidates (public text, fenced as data, friends' slots fixed) and returns an ordered top 5–10, or graded ids. That order replaces the top 20; everything else stays. It fits the two-stage flow already proposed in A-003 (instant screen, then refined list).

**Evidence.**
- Ours: graded rerank of the top 30 gave +0.013–0.016 nDCG but lifted **single-answer MRR 0.51 → 0.62**, the largest MRR change measured. Known-item metrics are exactly where it should show.
- Literature: listwise with small models is weak and order-sensitive, so present candidates in fused order ([Setwise](https://arxiv.org/abs/2310.09497); [2508.16757](https://arxiv.org/pdf/2508.16757)). A calibrated cross-encoder often matches listwise LLMs at far lower cost (vendor claim, [ZeroEntropy](https://www.zeroentropy.dev/articles/should-you-use-llms-for-reranking-a-deep-dive-into-pointwise-listwise-and-cross-encoders/)). In agentic search the reranker setting mattered most among search-tool settings (vendor, [Contextual AI](https://contextual.ai/blog/making-search-agents-faster-and-smarter)).

**Local alternatives.** BEIR nDCG@10 reranking jina-embeddings-v3's top 100 ([jina-reranker-v3 paper](https://arxiv.org/html/2509.25085v4)):

| Model | BEIR | Licence |
| --- | --- | --- |
| jina-reranker-v3 | 61.85 | **CC BY-NC 4.0**, unusable commercially without a licence ([card](https://huggingface.co/jinaai/jina-reranker-v3)) |
| mxbai-rerank-base-v2 | 58.40 | Apache-2.0 ([card](https://huggingface.co/mixedbread-ai/mxbai-rerank-base-v2)) |
| bge-reranker-v2-m3 | 56.51 | Apache-2.0 |
| Qwen3-Reranker-0.6B | 56.28 | Apache-2.0; instruction-aware |

All of these are 0.5–0.6B, which is about 1–4 s for 20 short candidates on 4 vCPUs (*est.*; no trustworthy CPU benchmark found). Off-the-shelf MS MARCO cross-encoders hurt our captions earlier (0.42 → 0.33), and the CPU torch install failed in round 7, so the ONNX/GGUF route would be needed.

**Expected quality** (vs H0, top 20 only, so recall is unchanged):
- `known_dev` MRR +0.01 to +0.05 (the first stage is already strong on titles);
- `ig_known_dev` MRR +0.03 to +0.08;
- `dev` nDCG +0.00 to +0.02.

**Cost:**
- gpt-5-nano, about 2.1k in / about 200 out (incl. minimal reasoning) ≈ **$0.18 per 1k searches**;
- gpt-5.4-nano ≈ $0.67 per 1k;
- local $0.
- $0 per item.

**Latency:** refined list +1.5–3 s (measured graded rerank p50 2.8–3.75 s for 30) → about 4 / 6 s total for the refined stage. The first screen is unaffected.

**CPU/desktop:** the API version needs the network; a local 0.6B is feasible but slow.

**Privacy:** the provider sees query + 20 public texts, the same exposure class as the rewrite. The local reranker keeps it on device. Never send collection names or friends' items.

### A4. Agentic planner with tools (MCP)

**What.** Expose tools rather than one smart endpoint:
- `search(query, platforms?, since?, until?, interaction?, creator?, mode: keyword|descriptive)`;
- `creator_lookup(name_or_description)`;
- `similar(item_ids)`;
- `get_items(ids)`;
- `time_histogram(query)`.

Two ways to run it:
- **(a) The user's agent plans.** We skip our rewrite when `mode` is given.
- **(b) Our own planner** (nano tool-calling, 2–4 turns) for the hub.

**Evidence.**
- Agents' accuracy depends heavily on the retriever under them: on BrowseComp-Plus GPT-5 went from 55.9% with BM25 to 70.1% with a strong embedder, *and* made fewer calls ([BrowseComp-Plus](https://preview.aclanthology.org/ingest-acl/2026.acl-long.1023/)). So the tools must be good first.
- Tool design guidance favours few, consolidated, well-described tools that return concise fields with `has_more` ([Anthropic, Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)).
- Our own evidence: structured filters win when grounded in words; typed slots and checkers added nothing.

**Expected quality:**
- (a): unknown; it depends on the user's agent. Our job is tool quality.
- (b) vs H0: dev +0.00 to +0.04 on behaviour, time and creator searches; ≈ 0 or negative on keyword known-item (extra turns, drift).

**Cost:**
- (a) to us ≈ $0.001–0.01 per 1k tool calls (embedding only), because the agent pays its own tokens. It is *cheaper* than H0.
- (b) about 1.5–2k input tokens per turn (tool schemas; mostly cache hits at $0.005/M) + about 150 out ≈ $0.25–0.6 per 1k searches.

**Latency:** (a) 0.2–0.5 s per tool call; (b) +2–6 s, p95 about 8–10 s (*est.*: 2–4 × 0.9–1.5 s calls).

**CPU/desktop:** (a) yes, with tools served locally; (b) needs a cloud LLM.

**Privacy:**
- Tool responses go to the user's own agent, but they must carry friends as counts only and hide sensitive categories unless opted in (07).
- Captions in tool output are third-party text. Mark them as data, because the agent's prompt is now the injection target.
- The MCP token is the vault key, so revoking it ends agent access.

### A5. Learning from usage (click / watch feedback)

**What.** Replace hand-set RRF and boost weights with a small learned ranker: a logistic or LambdaMART model over the top 100.
- **Features:** each list's rank, BM25 title-match coverage, creator match, platform prior, item interaction strength, rewatches, recency of *last interaction relative to now*.
- **Trained on** search → open/watch events.
- **Later, online:** click-model debiasing and interleaved comparisons.

**Evidence.**
- Personal search at Google learns from clicks with position-bias estimation and no randomisation, and pairwise models use the debiased signal best ([Wang et al. WSDM 2018](https://research.google/pubs/pub46485/)).
- Interleaving and multileaving need orders of magnitude fewer interactions than A/B tests ([Schuth et al.](https://dare.uva.nl/id/3b83ab17-72f0-4f95-9ec9-2f54b087bcf1)).
- One user produces few clicks, so the realistic form is a **shared model over non-content features**, with per-user feature values from the vault. That matches 05 › Principle 8: per-user layers, never a model per user.

**Expected quality:** `known_dev` MRR +0.01 to +0.05 if trained on a disjoint pool of real search → watch pairs. It is ≈ 0 to negative if trained on 44 dev searches (overfit).

**Cost:** $0 API; training seconds; inference < 10 ms.

**CPU/desktop:** yes.

**Privacy:**
- Logs and per-user values stay in the vault.
- A cross-user model would need consent and aggregated, content-free features.
- **Leakage hazard:** in the eval sets the target's watch time ≈ the search time, so any feature using the search timestamp is forbidden.

### A6. Local-first representations: learned sparse, late interaction, quantization

**What.** One or more of:
- (i) inference-free learned sparse (opensearch doc-v3-gte: queries are tokenizer + IDF, no model);
- (ii) answerai-colbert-small token vectors as a re-score leg (or MUVERA single-vector encodings for first-stage multi-vector retrieval);
- (iii) int8 or binary + rescoring of the 3-large vectors;
- (iv) a local query embedder, so the desktop needs no API.

**Evidence.**
- doc-v3-gte: BEIR-13 54.6 vs BM25 about 43–44 ([card](https://huggingface.co/opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte); [SBERT table](https://sbert.net/docs/sparse_encoder/pretrained_models.html)). Li-LSR beats SPLADE-v3-Doc by +1.8 BEIR ([2505.01452](https://arxiv.org/pdf/2505.01452)). There is no evaluation on captions or titles, and the te pass already does the vocabulary-expansion job for Instagram.
- ColBERT: our own +0.020 (CI spans 0) on the weaker bge-small base. MUVERA matches PLAID recall with 2–5× fewer candidates and about 90% lower latency ([MUVERA](https://arxiv.org/pdf/2405.19504)), but at 137k items brute-force MaxSim over the top 100 already costs < 5 ms.
- Quantization: 1,024-d binary keeps about 92.5% of retrieval quality, about 96% with rescoring; int8 keeps 97%, about 99% with rescoring; 32× / 4× smaller, 25× / 3.7× faster ([HF blog](https://huggingface.co/blog/embedding-quantization)).

**Expected quality:** (i), (ii) +0.00 to +0.02 on top of H0 (they overlap with 3-large and te); (iii) −0.005 to 0; (iv) about −0.02 to −0.05 vs 3-large (H0's own gain, reversed), unless EmbeddingGemma closes it (+0.017 on B2 in round 1).

**Cost:**
- $0 per search.
- Per 1k items, on 4 vCPUs:
  - sparse about 5.5 min and about 3 MB;
  - ColBERT about 0.5 min and 6–21 MB fp16;
  - a GPU burst (about $0.8/h) does 137k in minutes.
- 3-large vectors: 560 MB fp32 → 140 MB int8 → 18 MB binary for 137k items.

**Latency:** ±0.01–0.1 s.

**CPU/desktop:** yes. This is the only alternative that removes the per-query API dependency of 3-large.

**Privacy:** all content-side, so it goes in the shared store, computed once per public item. Queries stay local.

### Summary

Δ is vs H0 (*est.*). Cost is extra over H0's $0.131 per 1k searches; "items" is extra per 1k items.

| | Δ expected (primary set) | $/1k searches | $/1k items | p50 / p95 | Desktop | Privacy fit |
| --- | --- | --- | --- | --- | --- | --- |
| A1 planner + keyword path | −0.02 to +0.03 MRR (`known_dev`) | **−$0.06** (blended) | 0 | 0.4 / 0.7 s routed | yes | better (fewer LLM calls) |
| A2 creator index | 0 to +0.03 MRR | 0 | ≤ $0.02 per 1k creators | +0.03 s | yes | good (mutuals excluded) |
| A3 listwise refine | +0.01 to +0.08 MRR | +$0.18 (nano) | 0 | refined +1.5–3 s | API or slow local | same as rewrite |
| A4a MCP tools | n/a (user's agent) | −$0.12 per tool call | 0 | 0.2–0.5 s | yes | needs output hygiene |
| A4b our planner | 0 to +0.04 nDCG (dev) | +$0.25–0.6 | 0 | +2–6 s | no | as rewrite |
| A5 learned fusion | +0.01 to +0.05 MRR | 0 | 0 | < 0.01 s | yes | vault-only logs |
| A6 sparse / ColBERT / quant | 0 to +0.02 | 0 | CPU minutes | ±0.1 s | **yes, fully** | shared store |

## 5. Ranked by expected value per dollar

1. **A1, the shape-routed planner with a keyword path.** It is free and saves money and latency. The worst plausible outcome (−0.02 MRR on routed searches) is cheap to detect. It also fixes the te-on-YouTube loss by construction.
2. **A2, the deterministic creator index.** It is free at query time, and the determinism fix is needed anyway (agenda item 1). The expected gain is concentrated in named-channel searches, which the 381 real searches should finally contain in numbers.
3. **A3, listwise refine on the top 20, second stage only.** It is the largest MRR lever we have measured. At about $0.18 per 1k, a +0.03 MRR gain costs about $0.06 per +0.01, comparable to H5's $0.062 but on a metric that matters for known-item search.
4. **A5, learned fusion from search → watch pairs.** High upside at $0. It is ranked 4 because a clean, disjoint training pool must exist first (section 7). If it doesn't, it waits for product click logs.
5. **A4, MCP tools: build the surface (A4a), don't run our own loop (A4b).** A4a is product-necessary and cheaper per call than H0, but it is not loop-evaluable without simulating an agent. A4b costs 2–5× H0 for gains that guarded filters already capture.
6. **A6, local representations.** Low quality value on top of 3-large + te; the case for them is the desktop. int8 + rescoring is a free parity check to run whenever the desktop work starts.

**Not recommended:** hard per-platform federation (merge and selection errors, a 55% router), stronger rewrite models, our own multi-turn agent as the default, jina-reranker-v3 (licence), off-the-shelf MS MARCO cross-encoders.

## 6. Prototype experiments for rounds 8.x

Each experiment is one variable vs H0 (rebuilt and reproduced as `r7/h0_r1`), uses cached qr-v1 repeats where a rewrite is used, and gets its own LOG row before any run.

The H0-vs-arm decision follows the round-8 protocol (Phase A may change the adoption rule and add multiple-comparison control; use whatever PROTOCOL.md says at the time). Primary metric on known-item sets: **MRR**, secondary success@10; on `dev`: nDCG@10.

### X1 (A1): the keyword path, routed by query shape

**Variable.** For searches the rule marks keyword-shaped, skip qr-v1 and HyDE. Use raw-query 3-large + BM25 (own text) + PRF, with no te lists. Everything else is H0.
- Rule, fixed before any run:
  - ≤ 5 tokens;
  - no description, question or behaviour/time words (lexicon in LOG);
  - BM25 top-1 title-coverage ≥ 0.6 OR an exact creator-handle/name match.
- Also report an "instant for all" sub-arm (no routing) as a diagnostic, not as a candidate.

**Sets.**
- Primary: `known_dev`.
- Guard: `dev` (must not lose) and `ig_known_dev` (report the fire rate).

**Expected:**
- `known_dev` MRR −0.02 to +0.03;
- routed share 40–70% of `known_dev` and < 15% of `dev`;
- cost on routed searches −$0.12 per 1k; p50 −1.6 s.

**Falsified if:**
- routed `known_dev` searches lose MRR with the CI upper bound < 0 (then the rewrite earns its cost on keyword searches too), **or**
- `dev` loses ≥ 0.01 nDCG (the rule misfires).

If MRR is tied (|Δ| < 0.01, CI spanning 0), adopt on cost and latency under clause 2.

**Cost:** $0.

### X2 (A2): a deterministic creator list, gated

**Variable.** Add H4's creator list as one coverage-fair RRF list on H0, with three changes:
- ties sorted by creator id, which makes it deterministic;
- it fires only when the query matches a creator handle/name token, or the creator-profile BM25 top score clears a fixed gap;
- no LLM pick and no te.

The era prior is used only with an explicit time word (no soft time).

**Sets.**
- Primary: `known_dev`.
- Secondary: `ig_known_dev`, and `dev` creator searches.
- Run 3 repeats with different `PYTHONHASHSEED` values; all three must be identical.

**Expected:** `known_dev` MRR +0.00 to +0.03 overall; about +0.05–0.15 on fired searches.

**Falsified if:**
- fired searches show MRR Δ ≤ 0, **or**
- the not-fired share differs from H0 at all (a sanity failure), **or**
- runs differ across hash seeds.

**Cost:** $0.

### X3 (A3): listwise refine of the top 20

**Variable.** One gpt-5-nano call per typed search over H0's top 20.
- Prompt `refine-l1`, fixed in LOG: candidates in fused order as c01–c20, public own text ≤ 200 chars + creator, fenced as data.
- It returns an ordered list of up to 10 ids from an enum.
- Missing ids keep their fused order below the returned ones; friends' slots are fixed; a failed call means no change.
- Two repeats (the call is non-deterministic).
- The model must differ in family from the `ig_known` query writer. If the writer was an OpenAI model, use Gemini flash-lite at ≈ $0.5 per 1k instead.

**Sets.**
- Primary: `ig_known_dev` and `known_dev` (MRR).
- Guard: `dev` nDCG.

**Expected:** `ig_known_dev` MRR +0.03 to +0.08; `known_dev` +0.01 to +0.05; `dev` 0 to +0.02. Cost +$0.18 per 1k; refined-stage latency +1.5–3 s.

**Falsified if:**
- MRR Δ < +0.01 on both known-item sets, **or**
- the two repeats disagree in sign on either set, **or**
- `dev` loses ≥ 0.01.

Note the success@10 ceiling: refine cannot reach targets outside the top 20, so report the share of searches with the target in H0's top 20 first. That share bounds the possible gain.

**Cost:** (381 + 150 + 38) × 2 calls × about $0.0002 ≈ **$0.25**.

### X4 (A5, conditional): learned fusion weights from search → watch pairs

**Precondition.** The evaluator confirms a pool of My Activity search → watch pairs that is disjoint from `known_dev` / `known_test`, for example other years or unsampled pairs, with no query texts shown to the builder beyond what training needs.

If no such pool exists, **skip X4** and note it as waiting on product logs.

**Variable.** Replace H0's equal RRF weights with a pairwise logistic ranker over the top 100.
- **Features:** each list's reciprocal rank, BM25 title-coverage, creator match, interaction count and rewatch flag, platform prior.
- **No timestamp-relative features.**
- Trained on the pool, with model and features fixed before scoring.

**Set.** `known_dev`; guard `dev`.

**Expected:** MRR +0.01 to +0.05.

**Falsified if:**
- MRR Δ ≤ 0 with the CI upper bound < +0.01, **or**
- `dev` loses ≥ 0.01, **or**
- a feature ablation shows > 50% of the gain comes from one interaction-strength feature. That would be a library-selection artefact: watched videos are in the library *because* they were watched.

**Cost:** $0.

**Free side check (no adoption decision):** H0 with int8 vectors + 4× rescoring, and binary + rescoring, on `known_dev` + `dev`. Expect |Δ| < 0.005. Report the storage and latency it buys for the desktop.

**Re-ranking after each round:** if X1 shows the rewrite earns its cost on keyword searches, A1 drops to "routing for te lists only" and A3 (which can replace the rewrite in a two-stage flow) moves up. If X3 fails on `ig_known_dev`, drop A3 and A4b together (both bet on LLM reading of candidates).

## 7. Validation: what these sets can and cannot say

- **One known target per search.** The YouTube labels are watched videos (first = 2, later = 1); the Instagram labels are the seed item. MRR and success@10 are right for that, but equally good unlabelled items count as misses.
  - This penalises arms that surface *other* plausible items: refine (X3) and creator lists (X2).
  - Do not pool-judge them (per the brief). Report "target in top 20/100" alongside, so recall and ordering effects can be told apart.
- **`known_dev` is literal title recall, not re-finding.**
  - These were 2019–21 searches of YouTube's *global* catalogue. The target often entered the library *because* of that search's watch.
  - So the set favours exact title matching (and keyword paths) and says little about half-remembered re-finding months later.
  - Any prior on interaction time relative to the search is leakage; any interaction-strength prior partly measures library selection.
  - Autoplay and next-video noise in "watched within 10 minutes" is Phase A's check.
- **`ig_known` queries were written by an LLM that saw the caption, creator and te summary.**
  - **Arms that index the te text (te lists, X3 if it shows summaries) get an advantage from shared vocabulary.**
  - Simulated known-item queries rank systems more reliably than they score them absolutely ([Azzopardi et al. 2006](https://www.dcs.gla.ac.uk/~leif/papers/azzopardi2006simulatedqueries.pdf); [Huurnink et al. 2010](https://staff.fnwi.uva.nl/m.derijke/wp-content/papercite-data/pdf/huurnink-validating-2010.pdf)). LLM-written collections showed little same-family bias in TREC DL ([Rahmani et al. 2024](https://arxiv.org/pdf/2405.07767)). But that finding concerns model family, not shared source text.
  - Judge te arms on `ig_known` with this caveat. A cheap control: regenerate 30 queries without the te summary and check that the te arm's Δ holds.
- **Power (rough, pending Phase A's measured variances).** With a per-search SD of paired ΔRR of about 0.2 (*assumed*), 80% power at α = 0.05 detects about 2.8 · SD / √n:
  - `known_dev` (381): Δ ≈ 0.03;
  - `ig_known_dev` (150): ≈ 0.045;
  - `dev` (44, nDCG SD ≈ 0.08): ≈ 0.035.
  - Gated arms (X2, and X1 on its fired share) have smaller n, so report fired-subset CIs and don't read overall ties as nulls.
- **`dev` has been read by builders for 8 rounds,** and prompts were written after seeing outputs. Use it as a guard against breakage, not as evidence of gains.
- **Multiple arms.** Four arms per round on three sets is 12 primary comparisons. Phase A should decide the correction. Preregistering one primary set per arm (as above) keeps it to 4.
- **One person.** Every verdict holds for one library. The planner's user priors (A1) and learned fusion (A5) are exactly the parts that a second user's data would test.

## 8. Draft amendment, for the orchestrator to file (Proposed, both founders)

**A-00x · Search as one index with a deterministic query planner, per-platform list sets and a tool surface for agents.**

- **Conflicts with:**
  - `05-processor.md` › Query API `search` ("Hybrid: vectors + keywords + facet filters, reranked") and › Performance targets;
  - A-003's universal rewrite + HyDE.
- **Requests:**
  - (1) a code planner choosing the keyword, descriptive or structured path by query shape and the user's vault priors;
  - (2) te lists only for caption-type or untitled items, coverage-fair fusion;
  - (3) a creator index in the shared store, with era and affinity in the vault;
  - (4) an optional second-stage refine;
  - (5) MCP `search` accepting `mode` and structured filters, skipping our rewrite when the caller supplies them;
  - (6) a written privacy section (shared store vs vault, key revocation) in `05-processor.md`, which is missing today.
- **Evidence:** sections 1–4 of this review. Items 1–4 are only to be accepted after X1–X3 pass on `known_test` / `ig_known_test`.

## Sources

- Our evidence: `experiments/STATE.md` (rounds 1–7); `experiments/results/r2-q3-speed.md`, `r7-eval.md`, `r7-final.md`, `r7-methods.md`; `docs/research/2026-10-30-search-loop.md`, `2026-10-31-youtube-round.md`, `2026-11-03-combined-loop.md`, `2026-11-03-query-understanding.md`, `2026-11-07-models-and-classifiers.md`; `experiments/research/local-embedders-sparse-late-interaction.md`, `rerank-priors-graph.md`, `query-rewrite-routing-hyde.md`.
- Personal search and known-item search:
  - [Searching Personal Collections (2412.12330)](https://arxiv.org/pdf/2412.12330)
  - [Elsweiler et al., email re-finding](https://strathprints.strath.ac.uk/32918/)
  - [Azzopardi, de Rijke & Balog 2006](https://www.dcs.gla.ac.uk/~leif/papers/azzopardi2006simulatedqueries.pdf)
  - [Huurnink et al. 2010](https://staff.fnwi.uva.nl/m.derijke/wp-content/papercite-data/pdf/huurnink-validating-2010.pdf)
  - [Rahmani et al. 2024, synthetic test collections](https://arxiv.org/pdf/2405.07767)
- Query side and routing:
  - [Weller et al. 2024, when expansion fails](https://arxiv.org/abs/2309.08541)
  - [kNN routers (2505.12601)](https://arxiv.org/html/2505.12601v1)
  - [Routing survey (2502.00409)](https://arxiv.org/pdf/2502.00409)
  - [Shokouhi & Si, Federated Search](https://nowpublishers.com/article/DownloadSummary/INR-010)
- Rerankers:
  - [jina-reranker-v3 (2509.25085)](https://arxiv.org/html/2509.25085v4) and [model card](https://huggingface.co/jinaai/jina-reranker-v3)
  - [mxbai-rerank-base-v2](https://huggingface.co/mixedbread-ai/mxbai-rerank-base-v2)
  - [Setwise (2310.09497)](https://arxiv.org/abs/2310.09497)
  - [How good are LLM rerankers (2508.16757)](https://arxiv.org/pdf/2508.16757)
  - [ZeroEntropy (vendor)](https://www.zeroentropy.dev/articles/should-you-use-llms-for-reranking-a-deep-dive-into-pointwise-listwise-and-cross-encoders/)
- Agents and MCP:
  - [BrowseComp-Plus (ACL 2026)](https://preview.aclanthology.org/ingest-acl/2026.acl-long.1023/)
  - [Contextual AI (vendor)](https://contextual.ai/blog/making-search-agents-faster-and-smarter)
  - [Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Learned sparse, late interaction and quantization:
  - [opensearch doc-v3-gte](https://huggingface.co/opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte)
  - [SBERT sparse models](https://sbert.net/docs/sparse_encoder/pretrained_models.html)
  - [Li-LSR (2505.01452)](https://arxiv.org/pdf/2505.01452)
  - [MUVERA (2405.19504)](https://arxiv.org/pdf/2405.19504)
  - [PLAID](https://huggingface.co/papers/2205.09707)
  - [HF embedding quantization](https://huggingface.co/blog/embedding-quantization)
- Feedback learning:
  - [Wang et al. WSDM 2018, position bias in personal search](https://research.google/pubs/pub46485/)
  - [Schuth et al., multileave / online LTR](https://dare.uva.nl/id/3b83ab17-72f0-4f95-9ec9-2f54b087bcf1)
- Embedding API prices (third-party trackers, check before use): [Voyage 3.5 lite ≈ $0.02/M](https://costbench.com/software/embedding-apis/voyage-ai/); Cohere Embed v4 ≈ $0.12/M ([devtoollab](https://devtoollab.com/blog/best-embedding-models-apis)). Ours: 3-large $0.13/M, 3-small $0.02/M, gemini-embedding-2 $0.20/M (`ai_prices.json`). At about 33–110 tokens per item, any of these is ≤ $0.015 per 1k items. **Embedding price is not a design driver; query-time API dependence is.**
