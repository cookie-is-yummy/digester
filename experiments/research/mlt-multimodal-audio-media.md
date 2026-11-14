# Research: more-like-this, media (shown / said / played) and other sources

*30 Oct 2026 · researcher subagent · experiments/search-loop · no evaluations run, no labels read*

**In one line:** "more like this" can get cheaper text-only gains now (an LLM-abstracted "what makes this
alike" query, the user's own collections, smarter example-term selection), but the 3 dev MLT queries are
too few to clear the adoption rule on their own. The big MLT gain is visual. The cheapest permitted media
pass is a thumbnail or 3 keyframes: about $0.12–0.36 per 1,000 for Gemini Embedding 2 vectors and about $0.25–0.65 per 1,000 for a
Flash-Lite description. A full 30 s video costs about $24 per 1,000 to embed and about $1.34 per 1,000 to describe. Use local
SigLIP2/CLIP on the desktop. Song names need fingerprinting (AudD/ACRCloud/ShazamKit) on media we may
legitimately hold; no LLM or export gives them.

## 0. What the eval can and can't show (method-side facts only)

- There are 4 MLT searches (3 dev, 1 test), **each with exactly one example**. So "per-example max instead
  of centroid" and MMR-style example coverage don't apply to the current eval. Build them, but they can't
  be measured here.
- All 4 examples belong to one of the user's 16 collections (sizes 144–500; 1,109 items are in any
  collection). Their creators have 1–33 items in the corpus. Co-saves within 15 min of the example's save:
  1, 2, 3 and 20, so the session signal is sparse.
- With 3 of 16 dev queries, a change that only touches MLT moves dev nDCG@10 by 3/16 of its MLT effect.
  For example, +0.10 on MLT is only +0.019 overall, which misses the ≥0.03 rule. **Recommendation to the orchestrator:** judge MLT
  changes on the MLT kind, require no change on typed queries (by construction), and add a
  label-independent proxy (§5).

## 1. More like this without media

| Idea | Evidence | Fit here |
| --- | --- | --- |
| **LLM-abstracted query** ("what makes these alike": genre, format, technique, topic, at one level of abstraction above the example), then run the normal typed pipeline | Query-by-example via a generated intermediate query is the standard approach in the IARPA BETTER cross-language task ([arXiv 2310.09350](https://arxiv.org/pdf/2310.09350)). QueRec: LLM-generated queries, then similarity retrieval, training-free, up to +57% ([arXiv 2504.11889](https://arxiv.org/abs/2504.11889)). Risk: QBE "is prone to concept drift and highly sensitive to the query generation method" ([arXiv 2311.11226](https://arxiv.org/abs/2311.11226)). In our own data the AI rewrite was the single biggest typed gain (+0.06–0.09 dense) ([search-storage](../../docs/research/2026-10-30-search-storage.md)) | Strong: about 1 call per query, about $0.0005, +1–2 s |
| **Example-term selection** (Lucene MoreLikeThis: top-k terms by tf·idf, with min/max document-frequency cutoffs) instead of the whole example text as a BM25 query | Long captions are often stories or calls to action about something else ([cascade](../../docs/research/2026-10-30-enrichment-cascade.md) §1). Keywords on the example's own text was the best single MLT leg (0.50) | Free, but a small gain at best |
| **User's own collections** as a co-occurrence leg (items sharing a collection with the example, ordered by dense similarity) | Item co-occurrence and nearest-neighbour signals are hard to beat in session recommenders ([Ludewig & Jannach, arXiv 1803.09587](https://arxiv.org/abs/1803.09587)). Collections are user-created core data, so this is zero-effort intent | Free. Collections of 144–500 items may be too coarse |
| Creator co-occurrence | Already measured: ±0.02 ([search-storage](../../docs/research/2026-10-30-search-storage.md)) | Drop as a standalone experiment |
| Dense PRF on the MLT leg (Rocchio, as typed searches already do) | +0.02–0.04 on typed searches | Free. Backup experiment |
| MMR / diversification | Trades relevance for novelty, so it usually lowers nDCG on graded relevance | UI feature, not a score lever |
| Per-example max vs centroid; multi-example PRF | Correct design for 2–3 examples (centroids blur multi-modal sets) | Build it; can't be measured (1 example per query) |

## 2. Multimodal options (exact limits and prices, checked 2026-10-30)

**Gemini Embedding 2 (`gemini-embedding-2`)** ([embeddings docs](https://ai.google.dev/gemini-api/docs/embeddings), [pricing](https://ai.google.dev/gemini-api/docs/pricing))
- One space for text, image, audio, video and PDF.
- 8,192 input tokens in total across modalities. Over-limit input is **silently truncated**.
- ≤6 images per request (PNG/JPEG); audio ≤180 s (MP3/WAV); video ≤120 s (MP4/MOV), sampled at 1 fps up to 32 s and
  at 32 frames uniformly beyond that.
- **The audio track inside a video is not embedded.**
- Several parts in one `contents` give one aggregated vector, so 3 keyframes plus the caption make one vector.
- MRL dimensions 128–3072 (768 recommended). No `task_type`: use prompt prefixes for text.
- Price per item: image $0.00012 (about 267 tokens at $0.45/M); audio $0.00016/s (about 25 tokens/s at $6.50/M); video
  $0.00079 **per frame** (about 66 tokens at $12/M). Batch is half price.
- The paper reports a lead on image, text↔image and text→video retrieval (MSCOCO R@1 62.9, Vatex nDCG@10 68.8)
  ([arXiv 2605.27295](https://arxiv.org/pdf/2605.27295)). It gives no SigLIP head-to-head.
- **Cloud-only.** It can't run on the desktop. That conflicts with A-001's "one model everywhere", so visual vectors
  would be a second, cloud-built index.

**Gemini 3.x Flash-Lite description pass** ([media resolution](https://ai.google.dev/gemini-api/docs/media-resolution), [video understanding](https://ai.google.dev/gemini-api/docs/video-understanding))
- Image tokens: low 280, medium 560, default/high 1,120.
- Video tokens: 70 per frame (280 at high); audio 25 tokens/s.
- Video defaults to 1 fps; `fps` is settable (for example 0.5).
- Price: $0.25/M for text, image and video input; $0.50/M for audio; $1.50/M for output.
- Note: the older video page still says 258 or 66 tokens per frame and 32 tokens/s. We use the Gemini 3 table.
- **Output tokens dominate the cheap tiers:** 250 output tokens cost $0.375 per 1,000. Keep the facet JSON short.

**Local image embedders (desktop fit)**
- Measured here with fastembed ONNX on 4 shared Xeon cores. The sandbox was heavily contended (load
  average 14), so treat these as lower bounds:

  | Model | Images/s | Size | Dims |
  | --- | --- | --- | --- |
  | CLIP ViT-B/32 | 6.5 | 0.34 GB | 512 |
  | nomic-embed-vision-v1.5-Q | 2.1 | 0.10 GB | 768 |
  | SigLIP2-base-patch16-224 | 1.7 | 0.37 GB | 768 |
  | jina-clip-v1 | 1.5 | 0.34 GB | 768 |

- External reference: SigLIP2-base-256 runs at about 21 images/s on an Apple M5 CPU (fp32, 4 threads) and about 200 images/s on the
  Core ML GPU path ([HF model card](https://huggingface.co/ChaseLean/siglip2-base-patch16-256-coreml-fp16)).
- So 20k thumbnails take about 15 min on a laptop CPU, or about 2 min on its GPU. Fine for background indexing.
- SigLIP2 and nomic-vision have paired text encoders (nomic-vision shares nomic-embed-text's space), so
  text→image search also works locally.

**Local speech (said facet):** faster-whisper small int8 transcribes 13 min of audio in 51 s on an 8-thread i7, about 2 s per 30 s reel
([README](https://github.com/SYSTRAN/faster-whisper)). Free on the desktop. Keep the summary and keywords and discard the transcript
(07 › Retention).

### Cost per 1,000 items (Instagram reel, 30 s, cloud list price; batch is half)

Assumes a 250-token prompt plus caption and a 250-token facet-JSON output.

| Tier / input | Facets filled | Flash-Lite describe | Emb-2 vector | Local alternative |
| --- | --- | --- | --- | --- |
| 1 · text only (tier 0 metadata) | summary, what, topic, unknowns | $0.44 ($0.22) | $0.06 (text) | bge-small, $0 |
| 2a · thumbnail, low res | shown (cover only), on-screen title text, vibe (partial), place (landmarks) | $0.51 ($0.25); $0.72 at default res | $0.12 ($0.06) | SigLIP2/CLIP, $0 |
| 2b · 3 keyframes, low res | shown, on-screen text, vibe, place, people appearing | $0.65 ($0.32) | $0.36 ($0.18), one vector | SigLIP2 ×3, $0 |
| 3 · audio track, 30 s | said, song *lyrics*, music mood (no reliable song name) | $0.81 ($0.41) | $4.80 ($2.40) | faster-whisper, $0 (said only) |
| 4 · full video, 30 s at 1 fps | everything except a reliable song name | $1.34 ($0.67); $1.08 at 0.5 fps | $23.70 ($11.85), **no audio** | — |
| Song ID (fingerprint) | audio: title, artist | AudD $2–5 (first 300 free) | — | ShazamKit on macOS (see §3) |

**Per user (21k items):**
- Describe, full video: about $28 ($14 batch). Keyframes: about $14 ($7). Thumbnail embedding: about $2.50 ($1.25).
- Video embedding costs about **66×** keyframe embedding, gives no audio, and is not worth it for similarity. Embed 1–3 keyframes and *describe* the
  video if anything.

## 3. Song and audio identification within platform terms

- **Not available as metadata.** The export has no song names. The DM-share webhook's `ig_reel` attachment carries title, url
  and video id per Meta's changelog, but no music ([changelog](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/changelog/)).
  The paid metadata providers (Apify `musicInfo`) are scrapers, which the brief and A-002 rule out.
- **Free text first.** Tier-1 can pull song mentions from captions and hashtags (🎵, "song:", artist hashtags) into the
  audio slot with source=`caption`.
- **Fingerprinting (only on audio we may hold):**

  | Service | Fit | Terms / cost |
  | --- | --- | --- |
  | **AudD** | Robust to short clips | $2–5 per 1,000 file requests, first 300 free ([audd.io](https://audd.io/)) |
  | **ACRCloud** | Industry standard, robust to noise and voice-over | 14-day trial; prices sit behind a console login (an old forum figure is $5.8 per 1,000, unverified) ([docs](https://docs.acrcloud.com/get-started/tutorials/recognize-music)) |
  | **AcoustID/Chromaprint** | **Poor fit**: "optimized for matching near-identical audio" (full tracks), so reels with speech over music miss | Free for non-commercial use only; commercial via acoustid.biz ([acoustid.org](https://acoustid.org/)) |
  | **ShazamKit** | Best desktop fit (macOS/iOS; there is an Android SDK). Matches against Apple's catalog, built from full songs | No server-side API was found; terms and limits must be checked ([Apple docs](https://developer.apple.com/documentation/shazamkit)) |

- **Do not rely on an LLM to name songs from audio.** It can transcribe lyrics, which a lyrics or keyword search can then match. This is an
  assumption to test in M3.
- **Legitimate audio sources:**
  - the DM-share webhook media, *if* it proves to be a file (A-002 route A);
  - on-device capture in the desktop app (route B);
  - the founders' attachments;
  - for YouTube, nothing: Developer Policies III.E.1/III.I.7 forbid downloading, caching or separating the audio or video
    ([policies](https://developers.google.com/youtube/terms/developer-policies)).

## 4. Beyond Instagram reels: tier 0 and where each facet comes from

| Medium | Tier 0 (free) | Shown / vibe | Said | Audio | Terms notes |
| --- | --- | --- | --- | --- | --- |
| **YouTube** | Takeout: title, URL, channel, time (user-provided, *not* API Data). Data API `videos.list` (1 unit per call of ≤50 ids; 10,000 units/day per project, so ~500k videos/day): title, description (chapters), tags, duration, thumbnails | Thumbnail (Emb-2 or SigLIP2); Gemini's YouTube-URL input for public videos (preview, "available at no charge", limits may change) | Captions via `captions.download` need **edit permission** on the video (200 units), so owned videos only. Else Gemini YouTube-URL | Gemini YouTube-URL (song mood/lyrics); no fingerprinting (no download allowed) | III.E.4: delete or refresh API data within 30 days; delete within 7 days on request. **III.E.4.h: must not "use API Data to create new or derived data or metrics"**, so summaries or embeddings of API titles and descriptions may fall under it. Safest: derive from Takeout fields where possible; tie API-derived rows to `refresh_by` and re-derive on refresh. Needs a legal read (open check in 07) |
| **Article / link** | Title plus page text extracted locally (trafilatura F1 0.84 vs Readability 0.74 on the WCXB test set; [arXiv 2605.21097](https://arxiv.org/pdf/2605.21097)) | Lead image (`og:image`) | Already in the text | — | Fetching a URL the user shared is normal link-preview behaviour; respect robots and paywalls; store a summary, not the full text |
| **Podcast** | RSS: show and episode title, show notes, chapters (Podcasting 2.0) | Cover art (low value) | `podcast:transcript` where published: ~80k shows of ~4.5M (~1.8%) by May 2025 ([Blubrry](https://blubrry.com/?p=92916)). Else local Whisper (60 min in ~4 min) or Flash-Lite audio (~$0.045 per hour-long episode) | Music rarely matters | Transcripts not stored (07); keep summary and chapter "moments" |
| **Image / carousel post** | Caption, hashtags, alt text if present | The image(s); cover first, ≤6 per Emb-2 call | On-image text via describe pass | — | Instagram media blocked until A-002 |

## 5. Recommendation

### (a) Text-only MLT experiments, runnable now (preregister one variable each)

Shared baseline is the current MLT path: example vector (bge-small) plus BM25 on the example text, fused with RRF. Each experiment
changes MLT only, so the typed-query scores must be identical. Expected deltas are on the MLT kind (3 dev
queries; noise on 3 queries is large, so read these as direction, not precision).

1. **MLT-1 · collection co-membership leg (free).**
   - Variable: add a third RRF leg listing items that share ≥1 collection with the example, ordered by bge cosine to the example.
   - Hypothesis: the user's collection is an explicit "these belong together" signal that captures visual or format similarity text misses.
   - Expected Δ nDCG@10 (MLT): +0.03 to +0.08. It could be ~0 if collections are coarse (144–500 items).
   - Cost: $0, <5 ms.
2. **MLT-2 · LLM-abstracted "what makes this alike" query (paid, tiny).**
   - Variable: replace the BM25-on-example-text leg with the typed pipeline (dense max over phrases + PRF + BM25 on keywords) driven by an
     LLM rewrite of the example.
   - The rewrite uses `gemini-3.1-flash-lite` via `lib/ai.py`, with prompt version logged. Input: caption, hashtags, creator, collection names, as delimited data. Output: 3 phrases + 8 keywords naming format, technique and topic one level more general than the example.
   - Hypothesis: the example's caption describes *this* item, while users mean "this kind of thing". The typed rewrite was our biggest single gain.
   - Expected Δ (MLT): +0.05 to +0.10.
   - Cost: ~$0.0005 per query (4 queries < $0.01); +1–2 s latency. Concept-drift risk.
   - Report a gpt-5-nano run too only if the first one is positive.
3. **MLT-3 · MoreLikeThis term selection (free).**
   - Variable: the BM25 query becomes the top 12 terms of the example's full view by tf·idf (doc freq ≥2 and ≤5% of the corpus; hashtags split; creator handle kept).
   - Hypothesis: story or CTA words dilute the keyword leg.
   - Expected Δ (MLT): 0 to +0.04.
   - Cost: $0.
   - Backup if a slot frees: dense PRF on the MLT leg (expected +0.02).

**Label-independent proxy (for the evaluator):** leave-one-out over the user's own collections. Take one member as the example and
the other members as relevant, over ~100 sampled members. It is not valid for MLT-1, which uses collections, but gives
MLT-2 and MLT-3 enough queries for a CI.

### (b) Media experiments that must wait (design + cost)

**Blocked by:** Instagram media needs A-002 (route A fixture first, route B desktop capture), or founders attaching
files. YouTube needs `YOUTUBE_API_KEY` (not set) plus a new YouTube eval set, since the corpus has no YouTube items.

- **M1 · visual leg for MLT.** For each MLT example and its top-200 text candidates (~800 items, the label-independent pool), embed the
  thumbnail or 3 keyframes with (i) local SigLIP2-base and (ii) Gemini Emb-2 at 768d. Add example→candidate visual cosine as an RRF leg.
  - One variable per run: the visual model.
  - Cost: Emb-2 ~800 × $0.00036 ≈ **$0.29** (keyframes), or $0.10 (thumbnail); SigLIP2 $0, ~1 min on a laptop.
  - Expected Δ (MLT): +0.10 to +0.20 (visual and style similarity is the stated failure). Unverified.
- **M2 · describe pass by tier** (feeds the per-facet cascade). Pilot 200 items, then the label-independent sample (~5k items):

  | Tier | Pilot (200 items) | Sample (~5k items, batch) | Full corpus (21k, batch) |
  | --- | --- | --- | --- |
  | Thumbnail | $0.10 | $1.27 | $5.30 |
  | 3 keyframes | $0.13 | $1.62 | $6.80 |
  | Full video at 1 fps | $0.27 | $3.35 | $14 |

  - Measure facet coverage against the MU reference (evaluator-side) and Δ nDCG per kind.
  - Run keyframes before full video; only escalate if the "said" and "audio" kinds stay at 0.
  - The full corpus at standard price ($28) would exceed the $18 Gemini cap, so use batch, and only for a finalist.
- **M3 · song ID.** On ~100 permitted music-bearing clips, compare AudD (free 300), Flash-Lite audio "lyrics + song guess" (~$0.08) and the
  caption-mention extractor (free). Report hit rate and wrong-song rate. The audio searches move from 0 only with a correct title and artist in the
  audio slot.
- **M4 · YouTube (when a key exists).**
  - Takeout + `videos.list` tier 0 (quota is ample).
  - Thumbnail through Emb-2 / SigLIP2.
  - Gemini YouTube-URL describe for videos whose tier 0 leaves facets unknown: ~$18 per 1,000 ten-minute videos at low res if billed, currently "no charge" in preview.
  - Hold until the III.E.4.h derived-data question has a legal answer.

**Desktop fit:**
- SigLIP2 (or nomic-vision, which pairs with nomic-embed-text) plus faster-whisper plus ShazamKit cover shown, said and song on-device at $0.
- Gemini Emb-2 and the Flash-Lite describe pass are cloud-only. Use them for the first report and for items the desktop can't process.
- Store facets and summaries, not media or transcripts.

## Sources

- Gemini embeddings, pricing, media resolution, video understanding: ai.google.dev/gemini-api/docs/{embeddings, pricing, media-resolution, video-understanding}
- Gemini Embedding 2 paper: https://arxiv.org/pdf/2605.27295
- QBE / query generation: https://arxiv.org/pdf/2310.09350 · https://arxiv.org/abs/2311.11226 · https://arxiv.org/abs/2504.11889
- Session kNN baselines: https://arxiv.org/abs/1803.09587
- SigLIP2 CPU reference: https://huggingface.co/ChaseLean/siglip2-base-patch16-256-coreml-fp16 · faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Song ID: https://audd.io/ · https://docs.acrcloud.com/get-started/tutorials/recognize-music · https://acoustid.org/ · https://developer.apple.com/documentation/shazamkit
- Meta IG messaging changelog (ig_reel payload): https://developers.facebook.com/documentation/business-messaging/instagram-messaging/changelog/
- YouTube: https://developers.google.com/youtube/terms/developer-policies · https://developers.google.com/youtube/v3/determine_quota_cost · https://developers.google.com/youtube/v3/docs/captions/download
- Articles: https://arxiv.org/pdf/2605.21097 · Podcasts: https://blubrry.com/?p=92916
