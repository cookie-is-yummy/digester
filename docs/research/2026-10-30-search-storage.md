# Research: how to store reels for search

*30 Oct 2026 · processor · proposes [Amendment A-001](../amendments.md)*

**In one line:** store each reel once as shared *content* with an assembled search text, one small vector per item (plus chunk vectors for long text), a keyword index and facets. Search with an AI query rewrite + meaning search + keyword search merged by rank, then refine with the top results. Use one open embedding model (bge-small) everywhere so the cloud and the desktop share vectors. Spend enrichment money only where captions run out, starting with one cheap "describe this reel" pass and song metadata.

## The test

- **Corpus:** one founder's Instagram history, 20,202 items with any caption (saves, likes, shares). 5,238 (26%) have almost no caption ("#reels", an emoji).
- **Eval set:** 22 real searches written from memory: 18 typed (topic, name, said/shown, vibe, audio, place, time, task, people/structure) and 4 "more like this" from an example reel. Answers were found by an independent assistant reading captions *and* video descriptions, then reviewed by hand: 926 graded answers (confirmed = 2, borderline = 1) plus known wrong answers. The eval set holds personal data and stays out of this repo (`data/evals/`).
- **Fairness fix:** answers were found partly by keyword matching, so correct results from meaning search could go unlabelled. The best setups' unlabelled top-10 results (164 items) were judged by hand; 46 were relevant and were added.
- **Metrics:** nDCG@10 (graded), P@10, MRR (how high the first right answer is).
- **Limits:** one person, captions only, 22 searches. Differences under ~0.03 are noise.

## Results (18 typed searches, nDCG@10)

| Setup | bge-small, caption template | bge-small, rich template | OpenAI 3-small 1536d | OpenAI 3-small 512d half precision |
| --- | --- | --- | --- | --- |
| Meaning only | 0.22 | 0.26 | 0.34 | 0.34 |
| Meaning + AI query rewrite | 0.28 | 0.33 | 0.43 | 0.39 |
| Keywords + rewrite | 0.39 | 0.39 | 0.39 | 0.39 |
| Meaning + keywords + rewrite (rank fusion) | 0.47 | 0.47 | 0.49 | 0.48 |
| **+ refine with top results (pseudo-relevance feedback)** | — | **0.51** | — | **0.50** |
| + off-the-shelf re-ranker (MiniLM-L12 or Jina turbo) | — | — | 0.33 (from 0.42, unpooled) | — |
| + thin items borrow their creator's vector | — | 0.46 | — | 0.48 |

Best setup: P@10 ≈ 0.56–0.59, MRR ≈ 0.90–0.92.

"More like this" (4 searches): keywords on the example's own text 0.50; OpenAI vector 0.44; bge-small vector 0.32–0.33; merged 0.42–0.45; adding the same creator's other reels ±0.02.

*Rich template* = caption + hashtags + creator handle and name + hashtags split into words (`#geometrynodes` → geometry nodes).

## What we learned

1. **Combine an AI query rewrite, meaning search and keyword search**, merged by reciprocal rank fusion with equal weights. Each alone tops out at 0.34–0.39; together 0.47–0.49. The rewrite (search phrases, keywords, filters) is the biggest single gain; weighting changed little.
2. **Refine each search with its own top results** (Rocchio: add the mean of the top 5 meaning hits to the query vector, search again). Free, no API, +0.02 to +0.04. With it, local bge-small (0.51) matches OpenAI (0.50).
3. **Thin captions poison meaning search.** They sit near every vague query. Hold items that fail the information gate out of meaning search until enriched (+25% for meaning search). They stay findable by keyword. Borrowing the creator's vector didn't help: most thin items' creators have no other captioned reels.
4. **Captions have a ceiling.** For 37% of right answers the caption contains none of the query's words; 12% have almost no caption. What is said, shown and played is the biggest remaining gain.
5. **Off-the-shelf re-rankers hurt** (trained on web questions) and are slow on CPU. An LLM re-rank of the top 20–30 is the one worth testing later.
6. **Small vectors are fine.** OpenAI 512d half precision ≈ full size. Exact search over one user's 20k vectors takes 0.04–0.07 s; no approximate index needed per user yet.
7. **By search type:** topic, name, place + time are good (0.5–0.8); task and people/structure middling (0.3–0.4); vibe unstable; **audio zero** (no music data); **"more like this" weak** (0.2–0.4) because similarity is often visual.

## Working smart: where to spend effort and money

| Idea | Cost | Expected gain | Verdict |
| --- | --- | --- | --- |
| Pseudo-relevance feedback | Free | Measured +0.02–0.04 | **Do now** |
| Thin items out of meaning search | Free | Measured | **Do now** |
| **One "describe this reel" pass** with a video-capable model, producing one structured description (what's shown, spoken summary, on-screen text, song if recognisable, place, vibe tags, entities, "questions this reel answers") appended to the search text | Gemini Flash reads ~300 tokens per second of video: about $0.003 per 30 s reel at default resolution, ~$0.001 at low resolution, half again in batch ([Fora Soft, May 2026](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/real-cost-of-ai-in-video-products-gemini-openai-pricing)) | Targets the 37% "no query word" and 12% thin answers; replaces separate transcription, OCR and image captioning for most items | **Test first** in the enrichment benchmark; needs a permitted way to get the video file |
| **Song title and artist from metadata** (not audio embeddings) | Providers return `musicInfo.songName/artistName` with no login, from ~$0.60 per 1,000 reels ([example](https://apify.com/xmolodtsov/instagram-reel-scraper)); terms check required | Turns audio searches from 0 to findable by name | **Do in intake**, behind the enricher interface |
| Enrich lazily, driven by search: only items that appear in the top 50 with low confidence, plus thin saves and self-shares | Pays only for what people look for | Same quality at a fraction of the cost | **Design rule** |
| Shared cache: enrich and embed each public reel once for all users | Cost per user falls with overlap | — | **Already decided**; keep |
| Transcription only where the description pass isn't enough (long videos, YouTube moments) | ~$0.003 per minute ([same source](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/real-cost-of-ai-in-video-products-gemini-openai-pricing)) | Chunk vectors for "the part where…" | **Later**, YouTube first |
| Visual vectors for "more like this" and boards: Gemini Embedding 2 puts text, image, video (≤128 s) and audio in one space ([overview](https://smallest.ai/blog/google-s-multimodal-embedding-model-text-image-video-audio-pdf-in-one-vector-space)); or a local CLIP/SigLIP model on thumbnails | Preview pricing; thumbnails are no longer returned by Meta oEmbed since Nov 2025 ([Meta](https://developers.facebook.com/blog/post/2025/04/08/oembed-updates/)) | Fixes visual similarity | **Later**, small sample test |
| Comment text | The official API reads comments only on the connected account's own media; providers give counts, not text | Crowd answers ("song?", "recipe?") | **Not now.** Use the user's own comments from the export (strong intent signal); revisit only if the benchmark shows a gap the description pass can't fill |
| Creator backfill for thin items | Free | Measured: none | **Drop** |
| Off-the-shelf re-rankers | CPU seconds per query | Measured: negative | **Drop** |

## Cloud first report, then local

The first report runs in the cloud; ongoing processing can run locally on the user's machine. One constraint drives the design: **a query must be embedded with the same model as the items it searches, and vectors from different models can't be mixed.**

- **Recommended:** use **bge-small everywhere.** The cloud runs it on a GPU burst for the first report (to measure: expected minutes rather than the ~50 min on 2 CPU cores), then hands the same vectors to the desktop app, which keeps embedding new items locally. With rewrite + fusion + feedback it scores 0.51, on par with OpenAI.
- **Fallback:** OpenAI `text-embedding-3-small` at 512d embedded 20,202 items in 72 s for 2.2M tokens (roughly 4 cents at published prices). If used for the first report, the desktop app must re-embed the whole history with its local model in the background before local search works, or keep calling the API.

## Recommended storage

**Shared content vs the user's relationship to it**

- `content` (one row per public reel/video, shared): platform, content ID, URL, creator, caption, hashtags, media kind, duration, posted date, **audio `{title, artist}`**, enrichment results (description, transcript summary, on-screen text, entities), facets, `info_class`.
- `user_items` (thin): user, content, interactions (kinds, dates, share audience, and the share counterpart only if the user opts in), optional note and share text, derived filter class and theme.

**Per content (derived, rebuildable)**

| Representation | Built from | Used for |
| --- | --- | --- |
| `search_text` (template v1, versioned) | caption, hashtags, split hashtags, creator, description, transcript summary, on-screen text, audio title, facet summary | Everything below |
| Item vector (bge-small 384d half precision; tagged with model + template version) | `search_text` | Meaning search, more like this, boards, themes |
| Chunk vectors (start/end seconds) | Transcripts and long text; a short reel is one chunk | "The part where…", YouTube moments |
| Keyword index (Postgres full-text, weighted caption/creator > hashtags > description/transcript) | `search_text` | Names, exact terms, creators, songs |
| Facets (jsonb + indexes) | Extractors | Filters |
| Visual vector (later) | Thumbnail or video | Look-alike search, boards |

**Search flow:** AI rewrite → meaning search over 1–3 phrases (max score) + keyword search, within filters → rank fusion → refine with the top 5 → show why each matched → if confidence is low, enrich the nearest candidates and retry.

## Decisions needed (Amendment A-001)

1. Content / user-item split (data contract).
2. bge-small as the single embedding model for cloud and desktop; OpenAI 512d as a tested fallback.
3. Opt-in storage of the share counterpart ("what I sent Sam").
4. Transcripts: summary + keywords + chunk vectors by default; full text per source only where terms allow.
5. Enrichment priorities: song metadata and one description pass first; transcription and visual vectors later; comment text not now.

## Next experiments

1. Enrichment benchmark with the description pass on the thin and "no query word" answers, then re-run this eval.
2. bge-small on a cloud GPU: time to embed 20k items.
3. LLM re-rank of the top 20–30.
4. A second person's searches.
5. Visual vectors on a small sample for "more like this".
