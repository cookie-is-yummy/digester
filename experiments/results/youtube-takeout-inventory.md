# YouTube Takeout: what a real export contains

*30 Oct 2026 · one founder's export, imported with `experiments/youtube/takeout_import.py`. Counts and formats only; no titles, searches or playlist names.*

## Format (differs from the synthetic fixtures)

- **History is HTML by default:** `history/watch-history.html` and `search-history.html`. JSON needs the format option changed at export time. The importer now reads both.
  - Times are local, with a zone abbreviation and a narrow no-break space before AM/PM: "Oct 30, 2026, 9:12:39 AM EDT". They are converted to UTC.
- **Playlists:** one `<title>-videos.csv` per playlist ("Video ID, Playlist Video Creation Timestamp"), plus `playlists.csv` (ID, title, create/update time, visibility). **Video IDs only**: no title, channel or duration.
- **No "Liked videos" file** in this export. Likes are missing; the API would need OAuth (`videos.list?myRating=like`) to get them.
- **Other files:**
  - `subscriptions.csv`;
  - `comments.csv` (the user's own comments, with video IDs);
  - `live chats`;
  - the user's own channel settings and uploads (`channels/`, `video metadata/`, `videos/*.mp4`). The uploads were hundreds of MB and are irrelevant; drop them.

## Counts

| | Count | Note |
| --- | --- | --- |
| Watch-history records | 33,300 | |
| – ads ("From Google Ads") | 4,184 | skipped |
| – community posts / channel views | 3,065 | not videos; skipped |
| – removed (no URL) | 78 | can't be keyed |
| Video watches kept | 25,973 | **covers only 15 Nov 2025 → 30 Oct 2026.** It starts abruptly, with ~2,400 watches in the second half of that November, though Derrick has history back to 2018. Possible causes: a cut-off in this export, another account, or history living in Takeout's separate "My Activity" product. The importer merges `My Activity/YouTube/MyActivity.(json\|html)` when present. Single watches are a weak signal (0.1) |
| – watched video now unavailable (URL shown as title) | 3,579 (14%) | the API can't recover these either |
| Watch later | 5,000 | YouTube's cap, so the user has hit it; dates from 2014; IDs only. Main "save" signal (0.8). Only 64 also in watch history |
| Named playlists | 30, 259 videos | the user's own collections, like Instagram collections; only 12 also in watch history |
| Subscriptions | 906 | |
| Own comments | 133 (121 on videos) | strong intent signal; not imported yet |
| Search history | 2,826 searches | **2014–2021 only**, no overlap with watch history, so no search → watch pairs. Not usable as click labels |
| **Unique videos** | **30,669** | 8,667 have no title in Takeout (playlist/watch-later only, or unavailable) |

Importer speed: 2.2 s wall, ~13.6k items/s.

## Second export, JSON (same day, same account)

- **Its watch history is shorter: 13,700 records, 23 Apr → 30 Oct 2026.** All 10,336 of its video watches are already in the HTML export, which goes back to 15 Nov 2025. Search history, playlists and subscriptions are identical.
- **Both exports cut off at a different point** although the user reports history back to 2018. So Takeout's YouTube watch history looks **truncated by the export itself**, not missing from the account. This is not confirmed: check myactivity.google.com, and try the separate "My Activity" product.
- **Product implications:**
  - Don't promise users their full watch history from Takeout. Show the coverage dates (`watch_first_at` / `watch_last_at` in import stats).
  - Lean on saves (Watch later, playlists), which come complete.
- **Importer:** JSON times carry milliseconds and HTML times only seconds, so watches are now deduplicated to the second when exports are merged.

## What this means

- **Text depends entirely on the YouTube Data API.** The strongest signals (5,259 saved videos) have no text at all in Takeout. `videos.list` for 30,669 IDs is ~614 quota units (free quota 10,000/day).
- **The interesting history is the saves, not the watches.**
  - The 5,259 watch-later and playlist videos span 12 years.
  - The watches cover 11.5 months and are mostly single plays.
  - Processing depth should follow the docs: watches `count_only` unless repeated or saved.
- **Video understanding route:** the Gemini API accepts a public YouTube URL directly (preview; public videos only; no daily length limit on the paid tier; ~100 tokens per second of video at default resolution), so no download is needed ([docs](https://ai.google.dev/gemini-api/docs/video-understanding)). At Flash-Lite prices a 10-minute video is roughly $0.015 standard or $0.008 in Batch. Gate it; don't run it on everything.
