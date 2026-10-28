# 05 · Processor

**Owner: Derrick.** Two parts:

- **Processor 1 · adapters:** platform-specific raw records → shared Items and Interactions.
- **Processor 2 · core:** everything after, identical for every platform. Exposed through the **query API** (JSON in, JSON out). Read-only toward the outside world.

## Principles

1. **Platform-agnostic after the adapters.**
2. **Pay for understanding only when it earns its keep.** Cheap processing for every item; transcripts and visual descriptions only for high-value items or on demand. Public content is enriched once and shared.
3. **Embeddings are the backbone** for search, themes, collections and direction.
4. **Themes are for browsing; search is for finding.** Search always runs over all items; themes filter or boost, never gate.
5. **Stable by design.** Theme IDs, embedding versions and user corrections survive reprocessing.
6. **Clean before anything else.**
7. **Default to the simple explanation.** Most interactions mean "liked the content". Only systematic biases (supporting friends) get rules.
8. **Learn from the user cheaply.** Lightweight per-user layers on top of shared models; never train a model per user.

## Pipeline

| Stage | Does | Cost | Status (prototype) |
| --- | --- | --- | --- |
| P1 · Adapters | Raw → Items + Interactions; own-account suggestion | Free | Instagram export + DM shares done |
| 0 · Clean | Encoding fix, dedup, language, information gate, deleted posts, "recipe in bio" | Near free | Encoding + gate done |
| 1 · Understand | Tiered enrichment: metadata → embedding → transcript → visual | Free → moderate | Tiers 0–1 done |
| 1b · Filter | Content vs entertainment vs friends; support signals | Near free | 84% accurate |
| 2 · Index | Vectors, keyword index, facets | Cheap | Vectors only |
| 3 · Organize | Stable two-level themes; trends | Cheap | Done incl. incremental assignment |
| 4 · Personalize | Questions, corrections, per-user layers | Cheap | First test done |
| Query API | Search, themes, reports, direction for everything downstream | Cheap per call | Not started |

## Processor 1 · Adapters

One adapter per `(source, kind)`; each declares the `format_version`s it accepts.

**Instagram export adapter** (port of the prototype importer):
- Parse `label_values` entries: URL, Caption, Hashtags (nested dict), Owner (Username, Name, URL); `timestamp`.
- Fix text encoding: `s.encode("latin-1").decode("utf-8")`, fall back to `s`.
- `dedup_key = "instagram:" + code` where code comes from the URL. A repeat touch adds an Interaction, never a second Item.
- `media_kind` = reel if URL path is `/reel/` or `/reels/`, else post.
- Collections: one `collection` interaction per (item, collection name); create the item if it only appears in a collection.
- Creator relation: `mutual` if the owner handle is in both followers and following, `following` if only following, else `none`.
- `importance = min(1, Σ weights)`; `processing_depth` from the strongest interaction; `interaction_kinds` denormalized.

**Instagram DM adapter:**
- **Owner** = the most frequent sender across all threads.
- **Self-share thread** = every participant is a confirmed own account (or the owner). All shares in it, from either side, become `share` with `share_audience=self`.
- **Friend share** = shares sent by the owner in any other thread → `share_audience=friend`. Recipients are not stored on the interaction.
- **Received** shares → counted only.
- **Own-account suggestion:** compute per thread the share ratio (shares / all messages, all senders) and how much others write. Propose threads with high share ratios as `own_accounts` with `status=suggested`, then ask one verification question. *Never decide by rule alone:* on real data, "nobody else writes" missed 2 of 3 self-share threads (the user's other accounts send things back), and a friend's thread scored a share ratio of 0.90, between the user's own two at 0.96 and 0.92.
- Prototype result: 3,954 shares sent (~5× saves); 2,465 unique self-shared items (~3× saves), 954 of them seen nowhere else, only 59 also saved. Self-sharing is a separate saving habit and must not be missed.

**YouTube adapters:** Takeout watch history → Item (video) + `watch` interactions; playlist items → `share`-strength interaction (`capture_method=playlist`). `dedup_key = "youtube:" + video_id`.

## Stage 0 · Clean

- **Information gate** (`info_class`): strip `#tags`, `@mentions`, URLs from the caption; count Latin vs other letters.
  - `non_english` if other letters > Latin and ≥ 10
  - `ok` if ≥ 40 Latin letters of real text, or ≥ 3 topical hashtags (not generic like fyp, viral, reels, explore, funny, meme…, and ≥ 3 letters)
  - else `low` ("too thin" → candidate for tier 2 enrichment if valuable)
- Planned: language detection, repost/duplicate merge, deleted-post marking, "recipe in bio / comment for link" patterns.

## Stage 1 · Understand (tiers)

| Tier | Adds | Runs when |
| --- | --- | --- |
| 0 | Caption, hashtags, creator, dates, platform metadata | Always |
| 1 | Embedding, filter, info gate, simple facets (regex dates, prices, URLs) | Always |
| 2 | Transcript (platform captions first, then speech-to-text) → summary, moments, facets; transcript discarded | High value (self-share/save) **and** (thin or near an active pursue theme), or on demand |
| 3 | On-screen text, visual description, entity extraction (ingredients, places, products, people) | Top items, type-specific, or on demand |

- **On demand:** when search confidence is low, enrich the nearest candidates one tier up and search again.
- **Type-specific extractors** only on items of that type (ingredients for recipes, deadline/eligibility for opportunities, name/city for places).
- **Embed every item with any text**, including likes and views, not only full-depth items: related-media search and future boards must reach the user's whole history.
- **Embedding:** `BAAI/bge-small-en-v1.5` via fastembed, L2-normalized; text = `caption[:600]` + up to 15 hashtags (+ transcript summary when present). Goals and queries use `query_embed`. Batch embedding is resumable in chunks of 1,000. Prototype speed: ~7.5 items/s on 2 CPU cores.

## Stage 1b · Filter

Classes: `content` (useful or interest), `entertainment`, `social` (friends).

- **Model:** logistic regression (`C=0.5`, `class_weight="balanced"`, `max_iter=3000`) on handcrafted features concatenated with the embedding.
- **Features:** log caption length, hashtag count, emoji ratio, laugh-emoji presence, comedy-tag presence, generic-tag ratio, utility-word regex (how to, tutorial, recipe, steps, tips…), digit ratio, question marks, "link in bio"/"comment" call-to-action, social tags (class of, birthday…), creator mutual/following flags, reel flag, empty caption.
- **Training:** ~200 hand labels (weighted 3×) plus weak labels from Instagram collections. Hand-label codes: U useful, I interest (→ content), E entertainment, S social, X excluded.
- **Decision rule:** entertainment or social only if that class has p ≥ 0.6; otherwise content (keeps useful content when unsure).
- **Prototype accuracy on unseen hand labels:** signals only 0.79, embedding only 0.76, both 0.84. Content precision 0.81 / recall 0.92; entertainment 0.85 / 0.72; social 0.91 / 0.83.
- **Support bias rules:** creator is a mutual follow → social (excluded from interests); short supportive comment → support; comment tagging a friend → social; comment asking for something ("recipe?", "where is this?") → strong interest.
- Friends' posts (social) are counts only in every output.

## Stage 2 · Index

- `item_embeddings` with an HNSW cosine index.
- Keyword index: Postgres full-text search over caption, hashtags, transcript summary, facets.
- Facets as filterable columns/JSON: type, ingredients, places, dates, creator, interaction kind, theme.

## Stage 3 · Organize (themes)

**First build** (per user, once enough items exist):
1. Take items with a main interaction (save, like, share), filter class `content` and `info_class=ok`.
2. Center embeddings (subtract the mean), L2-normalize, PCA to 20 dimensions, normalize again. *Centering was the key fix: raw bge vectors are too similar to cluster.*
3. One Ward linkage tree.
4. **Themes:** choose k at the biggest gap in merge heights within `[tmin, tmax]` (saves only: 10–18; saves + likes: 14–30).
5. **Sub-themes:** cut at height 2.0 (saves only) or 3.0 (joint); fold sub-themes with < 3 members into the nearest one in the same theme.
6. **Labels:** distinctive terms by share-of-items × log1p(lift), with English and platform stopwords removed. An LLM pass writes human names later; flag `mixed` themes for splitting.
7. Store the transform (`mean`, `pca_components`, `pca_center`) as a `theme_space`, plus centroids and cohesion.
Prototype: ~7,300 content items → 26 themes, 160 sub-themes; 3 mixed bags.

**Incremental update (always, after the first build):**
1. Project new items with the frozen transform of the active theme space.
2. Consider only coherent sub-themes (cohesion ≥ 25th percentile).
3. Join the nearest sub-theme if similarity ≥ the median similarity of existing members to their own sub-theme centroid (0.76 in the prototype).
4. Leftovers: Ward at height 3.0; groups of ≥ 15 become **candidate themes** (`status=candidate`). Merge overlapping candidates and fold any that fit existing themes **before** asking the user.
Prototype: adding ~9% more items, re-clustering from scratch kept only 9 of 23 themes; incremental assignment kept all 26. 305 of 647 new items joined; 342 formed 12 candidates.

**Never re-cluster live.** Periodic offline re-clustering must match new clusters to old themes by shared members (both directions ≥ 0.5 = same theme), keep IDs, make splits children of the original, and only *propose* merges. Pinned themes are never removed or renamed automatically. Changing the embedding model re-embeds everything and maps old themes before switching.

**Trends:**
- Weights per kind (see data contract); attention = weighted share of placed items.
- Share per half-year period; recent = last 6 months, before = 6–18 months ago.
- `rising`: +1 point and ≥ 1.25× before. `fading`: −1 point and ≤ 0.8× before. `dormant`: nothing in 183 days. Otherwise `steady`.

## Stage 4 · Personalize

- **Relations** on themes: pursue (a goal: actions, opportunities), practise (a hobby: resurfacing, low-pressure ideas), someday (wanted but parked: kept, never nagged, resurfaced when time frees up), enjoy (watching only: trends, Wrapped), mute.
- **Watching is not wanting:** no theme is called misaligned until the user has labelled it.
- **Self-sharing means keep, not act:** in the first test, 4 of 12 candidate themes made almost entirely of self-shares came back as enjoy or not me.
- **Questions are chosen by information value:** cluster checks ("are these five the same interest?"), theme labels, own-account confirmation, the filter's least-certain items, search checks ("is this the reel you meant?"). Merge overlaps first (overlapping pairs got identical answers).
- **Answers update per-user layers:** theme prototypes (pull centroids toward confirmed examples), filter thresholds, label propagation to near neighbours. Every answer is stored and becomes part of that user's eval set.

## Direction (goals vs attention)

- Goals are embedded with `query_embed`. Per goal, compute similarity to every placed item.
- An item matches a goal if similarity ≥ the 99th percentile for that goal, **or** it contains a goal keyword and similarity ≥ the 90th percentile. *Theme-level matching failed in the prototype; match items, not theme averages.*
- Per goal: matching items, recent vs before attention share, trend (growing > 1.2×, shrinking < 0.8×). Verdicts only make sense alongside the user's relation labels.

## Opportunity finder

An item is an opportunity if it has opportunity signals (internship, apply, deadline, hackathon, fellowship, scholarship, grant, accelerator, residency, hiring, register, sign up, waitlist, submissions, call for, prize, open now/until, cohort, summit, conference…): **two or more**, or one plus a date; **and** its similarity to the opportunities goal is ≥ the 75th percentile; entertainment excluded. An LLM pass extracts the real deadline and eligibility into an `opportunity` facet.

## First report

The moment of value after upload. Built when saves and shares are processed; refreshed when likes finish.

| Section | Contents |
| --- | --- |
| `summary` | Counts by platform and kind, time span, top creators |
| `useful_share` | Their onboarding guess vs measured content share ("you guessed 40%, your data says 31%"); counts of content, entertainment, friends |
| `highlights` | "Chess report" of recent activity: the few items that mattered per session or week, skipping the rest |
| `themes` | Top themes with trend, sparkline data, evidence items; rising and fading |
| `candidate_themes` | For the theme check |
| `opportunities` | Recent first, with signals and dates |
| `questions` | The few highest-value questions to ask next |
| `known_gaps` | e.g. "N items too thin to place; transcripts would help" |

Friends' posts appear only as counts. Every claim carries evidence item IDs.

## Query API

The processor's only public interface. Every request and response is a Pydantic model in `schema/query.py`. Read-only.

**Request envelope:**
```json
{ "op": "search", "user_id": "usr_…", "params": { … }, "budget": { "max_items": 20, "detail": "brief" } }
```
**Response envelope:**
```json
{ "data": { … }, "evidence": ["itm_…"], "meta": { "processor_version": "0.9.0", "took_ms": 42, "truncated": false } }
```

| `op` | Params | Returns |
| --- | --- | --- |
| `search` | `query?`, `types?`, `themes?`, `kinds?`, `platforms?`, `since?`, `until?`, `exclude_item_ids?`, `limit` | Ranked items with `why_matched` (caption line or moment) and confidence. Hybrid: vectors + keywords + facet filters, reranked. Low confidence may enqueue enrichment |
| `get_items` | `ids`, `include?` (enrichment, transcript_live) | Item cards |
| `list_themes` | `status?`, `relation?`, `trend?` | Themes with trend data |
| `get_theme` | `id` | Theme, sub-themes, evidence, recent items |
| `report` | `kind: first | refresh` | Report sections |
| `direction` | — | Goals vs attention |
| `opportunities` | `since?`, `limit` | Opportunity items with facets |
| `summarize` | `item_ids` or a `search` request, `style` | Short summary with evidence (LLM; logged to `ai_runs`) |
| `questions` | `limit` | Next highest-value questions |
| `what_changed` | `since` | New/rising/fading themes, new opportunities |
| `similar` | `item_ids` (1+), `exclude_item_ids?`, `types?`, `platforms?`, `limit` | Items closest to the centroid of the given items ("more like these"), across all platforms and interaction kinds, with similarity scores |
| `suggest_for_board` | `board_id`, `limit` | Like `similar` on the board's items (plus its saved query if set), excluding items already on the board or dismissed for it. *Later, with boards* |

The interpreter and the executor build these requests; later the hub and MCP call the same API.

## Performance targets (Proposed)

| Metric | Target |
| --- | --- |
| Upload → first report (saves + shares, ~3k items) | ≤ 5 minutes |
| Full export (~20k items) processed | ≤ 60 minutes, in the background |
| Live share → processed item | ≤ 30 seconds (tiers 0–1) |
| `search` p95 | ≤ 500 ms without on-demand enrichment |

Process in priority order: self-shares and saves, then friend shares, then likes, then views. Every batch logs items, items/s and wall time to `job_runs`.

## Known issues and backlog

High: real search eval set (15–20 real queries with answers); hybrid search prototype (must find "tomato recipes I saved" and "the guy making chai"); transcript benchmark with intake; someday resurfacing behaviour; comments as interactions with support rules.
Medium: cleaning stage; type extractors (ingredients, deadlines, places); split the 3 mixed themes; LLM theme naming; question selection by information value; cost model per user per month.
Low: multilingual embeddings for non-English captions; visual description tier sample; visual (image) embeddings of thumbnails for look-alike matching on boards.
Open: transcript source for Instagram at scale under platform terms; how long users will wait for on-demand enrichment; sharing enriched public content across users without leaking anyone's interactions; whether shares to a close friend sometimes mean "save this for us".
