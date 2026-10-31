# Run notes, round 3 (YouTube), as run on 30–31 Oct 2026

This adapts `BRIEF-3.md` to this run. Where the two differ, this file wins.

## Data

The data root is `data/yt/` (gitignored); set `DIGESTER_DATA=$PWD/data/yt`. Its layout matches the Instagram root, so `lib/corpus.py`, `eval/score_run.py` and `eval/judge.py` work unchanged.

- **`corpus/items.jsonl`:** 115,615 videos from Takeout. The YouTube product and My Activity are merged, which gives full watch history since 2015, likes and playlists.
  - `caption` is the Takeout title, present for 100,967 videos.
  - `platform_data.owner_name` is the Takeout channel name.
  - `platform_data.collections` holds the user's playlist names.
  - `platform_data.duration_s` and `available` come from the YouTube API, for display and filtering only.
- **`corpus/interactions.jsonl`:** watch (0.1), like (0.3) and playlist (0.8) interactions with dates. Watch later is a playlist.
- **`evals/queries.jsonl`:** 33 searches, method side. More-like-this searches carry `examples`. Examples outside the library carry `examples_outside_library` with a title.
- **`evals/split.json`:** dev 22, test 11. Fixed before any run. Test may be scored at most 3 times.
- **`evals/labels/`:** EVALUATOR ONLY.
- **`ref/api_tier0.jsonl`:** RESEARCH-ONLY reference arm: YouTube API title, description, tags, chapters, category and topics. Never ship it. Delete the folder by 2026-11-29.

## Terms decision (Derrick, 30 Oct)

YouTube Developer Policies III.E.4 item 08: API clients must not "access or use API Data to create new or derived data or metrics".

- **Allowed track:** the user's own Takeout text (titles, channels, playlist names, dates), plus Gemini's YouTube-URL video understanding. The latter is a Google Gemini API feature, so no YouTube API Data is involved.
- **API data:** may be used only for display and filtering (duration, availability).
- **Reference track, research only:** API descriptions, tags and chapters, to measure what the policy costs. Report it separately and never adopt it.
- **No thumbnails:** III.E.1 bars caching or storing audiovisual content.

## Changes from BRIEF-3

- **Embeddings:** OpenAI `text-embedding-3-small` at 512d, because 2 CPUs can't run bge-small over 115k items in reasonable time. Round 1 found the two equal in quality.
- **Tier 2 (thumbnails):** skipped; see terms.
- **Q4 (Instagram + YouTube together):** skipped, because the Instagram enrichment data isn't on this machine.
- **Budget for this round:** Gemini $8, OpenAI $4. These are enforced by `lib/ai.py` through env caps.
- **Keys:** `source` the env file given in the agent prompt. Never print, log or commit keys.
- **New method question (Derrick):** what a user says isn't always what they mean. Test an *intent* step: the rewrite also outputs structured filters (time window, saved/liked/never watched, minimum duration, Shorts or not, rewatched). Those filters are applied to the user's own interaction data.
