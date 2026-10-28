# 04 · Intake

**Owner: Eason.** Intake gets data in from platforms and enrichment providers and writes it to `raw_records` **exactly as received**. It does not interpret content; that is processor 1's job (`05-processor.md`).

## Rules of the road

1. **Preference order for every source** (Agreed):
   1. Data the user hands us: exports, Takeout, DM shares to our account.
   2. Official APIs: Instagram messaging webhooks, YouTube Data API.
   3. Paid providers with clear terms (e.g. Apify), only where 1 and 2 fall short, and only behind the enricher interface so they are replaceable.

   No logged-in bot accounts, no scraping that evades blocks or rate limits, no downloading media where the platform's terms forbid it. If a route is unclear, flag it in the PR and in `09-roadmap-and-ownership.md` › Open questions.
2. **Write raw, then stop.** One `raw_record` per entry with `source`, `kind`, `format_version`, `payload`. Never edit a raw record. Enqueue the IDs on `adapt.raw`.
3. **Minimum necessary.** Extract only the files and fields listed below. Never read or store DM message text.
4. **Idempotent.** Re-uploading the same export or receiving the same webhook twice must not create duplicates (hash payloads; the adapter dedups items by `dedup_key`).
5. **Measure.** Log counts and timings per upload into `uploads.timings` and `job_runs`.

## Instagram

### History export (`source=instagram_export`)

Users request their data from Instagram (Accounts Center › Your information and permissions › Download your information). They must choose **JSON** format and **All time**. Guide them to select only the categories below.

| File in the export zip | `kind` | Used for |
| --- | --- | --- |
| `your_instagram_activity/saved/saved_posts.json` | `saved_post` | Saves (weight 0.8) |
| `your_instagram_activity/saved/saved_collections.json` | `collection_entry` | Collection names and members (no timestamps) |
| `your_instagram_activity/likes/liked_posts.json` | `liked_post` | Likes (0.3) |
| `your_instagram_activity/comments/post_comments_*.json`, `reels_comments.json` | `comment` | Comment text, media owner, time (classified for support/question bias) |
| `ads_information/ads_and_topics/videos_watched.json` | `video_watched` | Views, last ~7–11 days only (0.1) |
| `ads_information/ads_and_topics/posts_viewed.json` | `post_viewed` | Same |
| `connections/followers_and_following/followers_1.json`, `following.json` | `followers`, `following` | Mutual-follow detection (friends' posts) |
| `your_instagram_activity/messages/inbox/*/message_*.json` | `dm_thread`, `dm_share` | Shares (see below) |

Notes from the prototype run on a real export (~250 MB, ~20k unique items):
- Entries use a `label_values` structure (URL, Caption, Hashtags, Owner with Username/Name/URL) plus `timestamp`. Keep payloads as-is; the adapter parses them.
- Text is UTF-8 mis-decoded as Latin-1; the adapter fixes it (not intake).
- Content ID comes from the URL: `instagram.com/(…/)?(reel|reels|p|tv)/<code>`.

**DM messages are special.** They contain private conversations. Intake reads each `message_*.json` and writes only:
- one `dm_thread` record per thread: `{ thread_key (salted hash of thread_path), participants: [display names], message_counts_by_sender: {name: n}, share_counts_by_sender: {name: n} }`
- one `dm_share` record per message that has a `share.link`: `{ thread_key, sender, timestamp_ms, share: { link, share_text, original_content_owner } }`

Message `content` fields are never read into records, logs or memory beyond the parse. Received shares are written too (the adapter decides what counts); they are needed for counts and for "received then acted on".

*Proposed for later:* do this extraction in the browser before upload so message files never leave the user's device.

### Live capture: DM share to our account (`source=instagram_dm`)

- Our product account is an Instagram professional account connected to a Meta app with Instagram messaging.
- Meta sends a webhook for each message. A shared reel arrives as an attachment carrying a URL, the caption (title) and an ID; a shared post similarly. **Capture a real webhook body as a sanitized fixture before writing the parser**, and confirm field names against Meta's current docs.
- Handler: verify the signature, write one `raw_record` (`kind=dm_share`, payload = the message object), enqueue, return 200 fast. Any reply to the user is sent asynchronously by the actions layer.
- Any text the user types with the share ("todo", "recipe", "for Eason") is kept: it becomes an explicit intent label that outranks inference.
- Constraints to design around: the app needs Meta review for messaging permissions (start early; development mode works for accounts that have a role on the app); replies outside 24 hours of the user's last message are restricted, so periodic notifications go by email.
- Sign-up by DM ("sign up" → link to connect their account) exists in an earlier prototype; reuse the idea.

## YouTube

### History import: Google Takeout (`source=youtube_takeout`)

- Users export **YouTube and YouTube Music** from Google Takeout, choosing **JSON** for history.
- `history/watch-history.json`: entries with `title`, `titleUrl` (video URL), `subtitles` (channel name/URL), `time`. `kind=watch_history`. Weight as view (0.1) per watch; repeats raise importance.
- Playlists (including likes, depending on the account) come as CSV files under `playlists/`. `kind=playlist_item`. *Verify the exact file names on a real Takeout and record them here.*
- Takeout does not include how much of each video was watched.

### Ongoing capture: dedicated playlist (`source=youtube_api`)

- The Data API cannot read Watch Later, so users add videos to a playlist we create for them ("Scroll Digest").
- OAuth with the read-only YouTube scope. Poll `playlistItems.list` for new entries (cheap in quota), then `videos.list` (snippet, contentDetails) for details. Optionally `commentThreads.list` for top comments.
- Each new playlist entry is a `share`-strength capture: `kind=playlist_item`, `capture_method=playlist`.
- API data has retention rules: set `refresh_by` (30 days) so a job refreshes or deletes it.

## Enrichment

The processor decides **when** an item needs more understanding (`05-processor.md` › Tiers) and enqueues `intake.enrich {item_id, tier, reason}`. Intake decides **how** to get it.

### Enricher interface (Proposed)

```python
class Enricher(Protocol):
    name: str                      # e.g. "youtube_captions", "apify_instagram", "whisper_api"
    platforms: frozenset[Platform]
    tiers: frozenset[int]          # which tiers it can serve

    async def enrich(self, item: ItemRef, tier: int) -> EnrichmentResult: ...
    def estimate_cost_usd(self, n_items: int, tier: int) -> float: ...
```

`EnrichmentResult` maps onto the `enrichments` fields (caption, creator, top_comments, transcript text for the processor to summarise and discard, on_screen_text, duration, cost). Results are written as `raw_records` (`source=enricher`) and cached per content in `content_cache` so each public item is enriched once for all users.

### What the processor needs, by tier

| Tier | Needs | Budget guide |
| --- | --- | --- |
| 0 | Caption, hashtags, creator, date (usually already in exports/DM payloads) | Free |
| 2 | Transcript, for high-value or thin items (YouTube captions first; speech-to-text second) | Low cents per item, measured |
| 3 | On-screen text, short visual description, for top items or on demand | Highest; sample only |

### The enrichment benchmark (first enrichment task)

Build a fixed benchmark and improve against it. This is the transcript experiment from the processor backlog.

- **Test set:** ~100 Instagram reels and ~30 YouTube videos (links only, stored in `evals/enrichment/items.jsonl`), including known hard cases: reels whose content is only spoken or on screen, captions like "Day 6", a reel that must be findable as "guy making chai".
- **Per method, measure:** coverage (% items with a usable transcript or caption), cost per 1,000 items, median latency, failure rate, and the downstream effect: how many "too thin" items become placeable, and search hit rate on the search eval set.
- **Report:** one table per run in `evals/enrichment/results/`, so the cheapest method that meets the need wins.

## Intake milestones (in order)

1. Download your own Instagram export and YouTube Takeout; write down exactly which files and fields exist (update this doc).
2. Instagram export reader → `raw_records` (all kinds above, DM extraction rules enforced), with tests on a synthetic fixture zip.
3. YouTube Takeout reader → `raw_records`.
4. Instagram DM webhook in development mode: share a reel to the product account, see a `raw_record` and an Item appear.
5. YouTube playlist poller.
6. Enricher interface + benchmark + first two providers.

After intake: triggers, output actions and the executor (`06-rules-and-actions.md`).
