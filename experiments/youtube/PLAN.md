# YouTube round: plan

PROTOTYPE. Prepared in round 2 (brief Q5) on **synthetic data only**. The next round can start as soon as Derrick
provides the items under "Needed from Derrick". Everything here runs on the fixtures today:

```bash
uv pip install --python .venv/bin/python pytest     # once
.venv/bin/python -m pytest experiments/youtube/test_youtube.py -q
export DIGESTER_DATA=$PWD/data
.venv/bin/python experiments/youtube/takeout_import.py data/youtube/takeout          # -> data/youtube/corpus/
.venv/bin/python experiments/youtube/api_enrich.py --items data/youtube/corpus/items.jsonl   # -> data/youtube/enrich/
```

| File | What it does |
| --- | --- |
| [`takeout_import.py`](takeout_import.py) | Takeout → `items.jsonl`, `interactions.jsonl` (Instagram shapes), `searches.jsonl`, `subscriptions.jsonl`, `import_stats.json` |
| [`api_enrich.py`](api_enrich.py) | `videos.list` tier-0 enricher → `enrich.jsonl` (enrichment rows), `text.json` ({video_id: tier-0 text}, plugs into `Corpus(extra_text=…)`), `raw/` responses with `refresh_by` |
| [`eval_format.md`](eval_format.md) | queries/answers/run formats, the `moment` kind and how moments are scored |
| [`fixtures/`](fixtures/) | synthetic Takeout (current CSV layout + legacy two-block CSV), synthetic `videos.list` response, eval examples |
| [`test_youtube.py`](test_youtube.py) | 34 tests on the fixtures |

## 1. Intake

**Takeout (user-provided, not API Data).** Watch history and search history as JSON (My Activity records), playlists
and subscriptions as CSV.

- Interactions: `watch` 0.1 per watch (repeats add up; `watch_count`), `like` 0.3 (the "Liked videos" playlist),
  `playlist` 0.8 (any other playlist, Watch later included, `collection_name` = playlist title), `share_self` 1.0
  (the product's capture playlist "Scroll Digest", which docs/04 treats as share-strength). Takeout has no shares.
- Skipped and counted: ads (`details: From Google Ads`), removed videos (no URL at all), non-video activity
  (community posts). Private/unavailable videos (Takeout shows the URL as the title) become items with an empty title.
- Search history becomes `searches.jsonl`, its own record kind, never an item. Subscriptions set
  `creator_relation = following`.

**What Takeout lacks:** description, tags, chapters, duration, thumbnail, publish date, and how much of a video was
watched. Playlist CSVs carry only the video ID (no title, no channel). Removed videos have no ID. Titles are as of
watch time. The "Watched"/"Searched for" prefixes are localized, so the importer relies on URLs.

**Official API (`api_enrich.py`).** `videos.list?part=snippet,contentDetails,topicDetails`, 50 IDs per call, key in
the `X-Goog-Api-Key` header (never in the URL or logs). It parses ISO-8601 durations, chapters from description lines
(YouTube's rules: first at 0:00, ≥3, ascending, ≥10 s each), and thumbnails as returned (best size first). IDs that
come back empty are marked `unavailable`.

**Quota:** 1 unit per call whatever the parts or ID count; default 10,000 units/day.

| | Calls = units | Share of a day |
| --- | --- | --- |
| 20,000 videos (backfill) | 400 | 4% |
| Refresh every 30 days | 400 per 30 days | 4% |
| Users backfilled per day at default quota | 25 | |

Fine for the experiment. The product needs a quota extension (YouTube API compliance audit) before it has more than
a handful of users. `search.list` and `captions.download` are never used.

## 2. Tiers

| Tier | Text | Source | Cost |
| --- | --- | --- | --- |
| **0** | title + channel + tags + chapter titles + description (URLs and chapter lines removed, 600 chars) + topic categories | Takeout title/channel; API for the rest | free (quota only) |
| **1** | the same text pass as Instagram (te-v1c prompt: summary, facets, unknowns, likely searches) over the tier-0 text, indexed as its own BM25 and vector lists | Gemini Flash-Lite, Batch | ~$0.18/1k on Instagram; YouTube descriptions are longer, so plan ~$0.3/1k (measure on a 200 pilot) |
| **2** | thumbnail: image embedding and/or a one-image describe pass (shown, vibe, on-screen text) | thumbnail URL as returned by the API | measure; one image per item |
| transcript | only where terms allow (below) | | |

- Tier 1 runs on `light`/`full` items (like, playlist, capture) and on any item in an eval pool. Watch-only
  (`count_only`) items stay at tier 0, matching the contract's processing depth. That also keeps the round under the
  $3 plan: a 20k history that is ~80% watch-only costs ~$1.2 for tier 1.
- **Moments.** Chapters give moment candidates for free: each chapter is indexed as a sub-document (video title +
  chapter title), and a moment search returns `[chapter.start_s, next.start_s)`. Videos without chapters return the
  whole video (video credit only; see eval_format.md). Measure how many saved videos have chapters first: that bounds
  what tier 0 can do for moment searches.

## 3. Terms

- **API Data retention.** Every raw response and enrichment row carries `refresh_by` = fetched + 30 days (Developer
  Policies III.E.4.c). A refresh job re-fetches IDs whose `refresh_by` is near (400 units per 20k). Rows that come back
  unavailable are deleted together with everything derived from them (tier-0 text, tier-1 output, vectors). Delete
  within 7 days of a user's request (III.E.4.g).
- **Derived data (III.E.4.h)** forbids using API Data "to create new or derived data or metrics". Tier-1 summaries and
  embeddings of API descriptions may fall under it. For the experiment: allowed as a prototype on Derrick's own data,
  rebuilt on every refresh. Before product: a legal read (docs/07 open check). Fallback that is clearly safe:
  derive only from Takeout fields (title, channel), which are user-provided, not API Data.
- **Transcripts.** `captions.download` requires permission to edit the video (owner) and costs 200 units, so only
  Derrick's own uploads qualify. No unofficial transcript endpoints or scrapers (AGENTS.md rule 7; III.E.1 forbids
  downloading or caching audiovisual content). For "said" and moment searches on others' videos, the candidate
  is Gemini's documented YouTube-URL input for public videos (preview pricing), on demand and never stored
  (summaries and moments are kept, not the transcript; docs/07).
- **Thumbnails** are API Data: used by URL, refreshed with the row, not stored as images.

## 4. The YouTube eval set

**Writing.** Derrick writes ~30 searches from memory of things he watched or saved, before seeing any results, in the
method-side format (`id, query, kinds, examples, filters`). Suggested mix: topic 6, name 4 (channel or title words),
**moment 6** ("the part where…"), said_shown 4, task 3, more_like_this 3 (video IDs as examples), vibe/structure 2,
time/filter 2. Use `filters.kinds` for "something I liked / saved / put in a playlist". Searches stay in
`data/evals/youtube/` (personal data). Takeout search history can jog memory but is not copied in as eval searches:
those were searches of YouTube, not of his library.

**Labelling (evaluator role only).**
1. Derrick's own known answers for each search (the video he had in mind), recorded when he writes it.
2. Pool the top 20 of each method (tier-0 BM25, tier-0 dense, B3 on tier 0, B3 + tier 1) plus his answers.
3. Derrick grades the pool 2/1/0 (blind to method). For moment searches he also marks each matching span
   (`start_s`, `end_s`, rounded to 5 s) by watching on YouTube.
4. Split dev ~22 / test ~8; test scored once, at the end.

**Runs to compare:** Takeout-only tier 0 (title + channel) → + API tier 0 → + tier 1 → + chapters as moment
sub-documents → + thumbnail tier 2. Report overall, per kind, and the moment metrics.

## 5. Needed from Derrick

1. **Google Takeout**: "YouTube and YouTube Music", all data, **history format JSON**; attach the zip as with the
   Instagram data; it is unpacked to `data/youtube/takeout/` (never committed).
2. **`YOUTUBE_API_KEY`**: a Google Cloud project with YouTube Data API v3 enabled, an API key restricted to that API,
   set in the session's environment (not in a file in the repo). OAuth is not needed for public videos.
3. The name of his capture playlist if it is not "Scroll Digest".
4. ~30 written searches (above), then about an hour to grade pools and mark moment spans.

## 6. Verify on the real Takeout, then update docs/04

Field names below come from Google's Data Portability schema references; file names and the legacy layout come from
community sources and memory, so they are **unverified** until the real Takeout arrives:

- playlist video files are `playlists/<title>-videos.csv` (`Video ID, Playlist Video Creation Timestamp`) next to
  `playlists/playlists.csv`; older exports used `<title>.csv` with a header block (`Playlist Id, …, Title, …`), a blank
  line, then `Video Id, Time Added`. Both are handled.
- whether "Liked videos" and "Watch later" are exported at all (reports differ);
- `subscriptions.csv` header case (`Channel ID` vs `Channel Id`); both handled;
- how Shorts and YouTube Music entries appear in watch history; how removed and private videos appear.
Then record the exact files and fields in docs/04 › YouTube (intake milestone 1).

## 7. Contract and code gaps (raise as a Proposed amendment before product code)

1. **Interaction kind.** The brief's `playlist` is not an `InteractionKind`. The importer emits `playlist` with
   `collection_name` in the experiment corpus; in the contract it would map to `collection`. Decide: map, or add
   `playlist`.
2. **Enrichment fields.** `enrichments` has no `title`, `topic_categories`, `category_id`, `default_audio_language` or
   `live`. The prototype rows carry them; the contract needs them or a `platform_data`-style extension on enrichments.
3. **Search history.** No table holds a user's platform searches. Proposed: keep them as `raw_records`
   (`kind=search_history`) only, used for nothing derived until a use is agreed (privacy: these are personal).
4. **Item caption.** For YouTube, `items.caption` = title; the description lives in the enrichment `caption`. Write
   that down in docs/03.
5. **`experiments/lib`.** `common.info_class` (and so `Corpus()`) reads `platform_data["hashtags"]`, which YouTube
   items don't have; it needs `.get("hashtags") or []`. Everything else in `Corpus` (BM25, filters, `extra_text`)
   works on the YouTube files unchanged (checked on the fixtures with that one line patched).

## Sources

- videos.list (parts, 1 unit per call): https://developers.google.com/youtube/v3/docs/videos/list
- Video resource (snippet, thumbnails keys, ISO-8601 `contentDetails.duration`, `topicDetails.topicCategories`): https://developers.google.com/youtube/v3/docs/videos
- Quota costs, 10,000 units/day default: https://developers.google.com/youtube/v3/determine_quota_cost
- captions.download (edit permission, 200 units): https://developers.google.com/youtube/v3/docs/captions/download
- Developer Policies III.E.1, III.E.4.c/g/h: https://developers.google.com/youtube/terms/developer-policies
- Chapter rules: https://support.google.com/youtube/answer/9884579
- Takeout CSV fields (playlists, playlist videos, subscriptions): https://developers.google.com/data-portability/schema-reference/youtube
- My Activity record fields (header, title, titleUrl, subtitles, time, products, details "From Google Ads", activityControls): https://developers.google.com/data-portability/schema-reference/my_activity
- Takeout file layout (community, unverified): https://takeoutday.org/guides/how-to-export-youtube-data
- The 50-IDs-per-call limit is not on the official videos.list page (it documents `maxResults` 1–50, which does not
  apply with `id`); 50 is the widely reported limit (e.g. https://www.technetexperts.com/youtube-api-videos-list-id-limit/amp/).
  The enricher batches at 50 and stops cleanly on an HTTP error.
