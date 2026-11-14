# Muse export inventory (30 Oct 2026)

- **Who wrote this:** the evaluator. It holds counts and field names only, no content.
- **Location:** `data/evals/labels/muse_export/` (gitignored). The export is evaluator-side only.
- **Parser:** `experiments/eval/muse.py` (`load_records()`, `load_mu()`, `load_captions()`).

## Files

| | |
| --- | --- |
| Folder | `muse_export/caption-mu/` |
| Files | 24 `.txt` files, 6.4 MB, about 62,700 lines |
| What the files cover | 23 are one Muse report each (the same reports as `labels/muse_reports/*.md`); 1 is an "interests summary" report |
| Other files | None: no images, video, audio, frames, thumbnails, JSON or CSV |
| Records per file | min 3, median 39, max 224; 1,358 records in total |

## Record format

Each file opens with a `# Caption + MU text for items in: <report>.md` line and a count line. Records follow, separated by lines of `=`. Each record looks like this:

```
@<handle> — https://www.instagram.com/{reel|p|tv}/<shortcode>/
Type: reel|post | Sources: liked[, saved] | Date: YYYY-MM-DD HH:MM:SS
Music: <track> / <artist>             (optional; 403 of 1,130 unique items, 36%)
--- CAPTION ---
<caption text>
--- MU (video description) ---
<MU text>
```

The MU text has a free-text video description, followed by semi-structured sections. Counts are unique items carrying each section:

| Section | Items |
| --- | --- |
| `## Searches` (suggested search phrases) | 947 |
| `## Author & Community Breakdown` (bullets: Author, Date, Inferred Role, Stated Purpose, Key Quote from Caption, Community Focus, Community Sentiment, Community Discussion and Discourse, Main Discussion Themes & Quotes) | 903 |
| `## Media Pivots` | 886 |
| `Cultural Context` (Cultural Origin, Cultural Moment, Cultural Significance) | 603 |
| `Humor Context` (Humor Type, Humor Target, Humor Explanation) | 370 |
| `Temporal Context` (`Data of event in content: <date>, Details: ...`) | 145 |
| `## Social Context & Synthesis`, `## Overall Synthesis`, `## Author Breakdown` (older format) | 81, 43, 43 |
| `Key Quotes from audio_transcript` | 39 |

MU lengths:
- Full MU: median 4,443 characters, mean 4,246.
- Description only (before the first section): median 1,928 characters.

## Counts

| | |
| --- | --- |
| Records | 1,358 |
| Unique items (shortcodes) | 1,130 (reel 1,030, post 100). 173 items appear in more than one file; the parser keeps the longest MU. |
| Items with a non-empty caption / MU | 1,130 / 1,130 |
| Source in the header (records) | liked only 1,210; liked and saved 96; saved only 52 |
| **Match our corpus by shortcode** (`items.jsonl` `dedup_key` after `instagram:`) | **1,105 of 1,130 (97.8%)**, which is 5.2% of the 21,293 corpus items |
| Matched items with a bge_full vector | 1,096. The 9 others have no caption or hashtags in our export, yet do have a caption in Muse's. |
| Matched items by our information gate | ok 960, low 139, non_english 6 |
| Eval-set relevant items (all 22 searches, grade > 0) that have MU | 989 of 1,040 unique (95%). Grade-2 items: 558 of 564. Item-search pairs: 1,164 of 1,215. |

## Media and comments

- **Media: none.** There are no thumbnails, frames, audio or video files, so the "Media" use in the brief does not apply.
- **Raw comments: none.** But 865 items carry `Community Discussion and Discourse` and 868 carry `Main Discussion Themes & Quotes`. These are Muse's summaries of, and quotes from, the comments. So MU is partly comment-derived, and our export cannot reproduce that part.
- **Transcripts:** no full transcripts. 39 items quote an `audio_transcript`, so Muse had transcripts for at least those items.
- **Music:** song and artist names appear in a `Music:` header line on 36% of items. Our export does not have them.

## Facets in the MU description (keyword heuristics)

These counts use the description part only, over 1,130 items. The heuristics are crude regexes: read them as rough rates, not as precise facet labels.

| Facet (heuristic) | Items | Rate |
| --- | --- | --- |
| Audio / music mentioned (music, song, track, beat, lyrics, sound, voiceover…) | 718 | 0.64 |
| Song and artist named (`Music:` header line, outside MU) | 403 | 0.36 |
| On-screen text (on-screen text, text overlay, "reads '…'", subtitles…) | 453 | 0.40 |
| Speech (says, speaks, explains, narrates, interview, transcript…) | 538 | 0.48 |
| Place: generic setting (street, restaurant, beach, kitchen, studio, city…) | 560 | 0.50 |
| Place: named city or country (small fixed list) | 198 | 0.18 |
| People shown (man, woman, person, group, friends…) | 703 | 0.62 |
| Visual style (colour, lighting, cinematic, animation, 3D, camera, shot…) | 672 | 0.59 |
| Tone / vibe (tone, mood, vibe, cozy, playful, nostalgic…) | 775 | 0.69 |
| Has `audio_transcript` quotes | 39 | 0.03 |

## Implications

- MU covers only the items Muse surfaced for its reports. That is 5% of the corpus but 95% of the labelled answers. Any comparison that uses MU, including the ceiling in `muse-ceiling.md`, is biased by MU **presence** as well as by its words.
- MU covers what is shown (people, style, tone), what is said (speech, on-screen text) and what is played (audio and named tracks). It also includes comment-derived community context. Our export has none of these, so a description pass would need media, which we cannot fetch for Instagram (BRIEF "What we have").
