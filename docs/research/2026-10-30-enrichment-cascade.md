# Research: when an item needs enriching

*30 Oct 2026 · processor · refines `05-processor.md` › Tiers; storage fields are covered by [Amendment A-001](../amendments.md)*

**In one line:** one "how much information does this item have" score can't decide what to enrich. Only truly thin items are reliably lost. For everything else, whether search finds an item depends on *which aspect* the search is about, not on how good the caption is. So the cascade should track sufficiency **per facet** (what it is, what's shown, what's said, the audio, the place…), escalate one cheap source at a time for the facets that are missing, and use search misses and interaction weight to decide where to spend.

## The question

Derrick's proposal: benchmark how much information each item has, and enrich only the ones below a bar. Caption descriptive enough → stop. Not enough → try the thumbnail → then the next source, and so on, for any kind of media.

To test it, a cheap score has to predict which items search *can't* find from their text.

## The test

- Same corpus and eval set as [search storage](2026-10-30-search-storage.md): 20,202 items; 18 typed searches; 879 (search, right answer) pairs.
- Search: the best caption-only setup (AI rewrite + bge-small + keywords, rank fusion, pseudo-relevance feedback).
- An answer counts as **found** if it ranks within max(50, 2 × the number of answers for that search).
- Item scores are computed without seeing the search.

## Results

**1. Only the thin items are clearly lost.** "Short", "medium" and "rich" below are counts of content words in the caption.

| Caption | Right answers | Found |
| --- | --- | --- |
| Thin (fails the information gate) | 98 | 7% |
| Short (< 8 content words) | 308 | 55% |
| Medium (8–24) | 259 | 61% |
| Rich (25+) | 214 | 52% |

A long caption is no more findable than a short one. Long captions are often stories, calls to action or promotions about something other than what the reel shows.

**2. Cheap text measures barely predict misses.** These are AUCs for predicting "found"; 0.5 is chance.

| Measure | AUC |
| --- | --- |
| Passes the gate | 0.57 |
| Content words | 0.56 |
| Rare-word information (sum of IDF) | 0.56 |
| Topical hashtags | 0.67 |
| Distance from the average caption | 0.53 |
| All combined (5-fold CV) | 0.67 |

Enriching the lowest-scoring 30% of the corpus would reach only 21% of the missed answers. The bottom 50% reaches 41%.

**3. An AI "does the caption say what this reel is?" judgement does no better.**

- Method: a blind sample of 120 relevant, gate-passing items (60 found, 60 missed). Each was judged 0/1/2 on whether the caption says what the reel is. Claude did the judging, without seeing the search or whether the item was found.
- AUC: 0.52.
- Captions judged clearly descriptive were found 49% of the time; vague ones 33%. The sample is small (±0.1), but the signal is weak at best.

**4. Misses depend on the aspect being searched.**

- Medium and rich captions that share a word with the search are found 69% of the time; those that share none, 6%.
- Typical misses:
  - a clearly captioned cat-flight reel that is also a "Europe trip" answer;
  - a painting-process reel that is also "cozy";
  - a well-described ad that the search wants by its song.
- The caption is good about one facet and silent about the one being asked.
- Worst by search type:
  - audio: 0 of 2
  - task ("weekend with friends"): 6%
  - niche hobbies: 17%
  - place (Europe trip): 20%
- Topic searches with specific words do best: 35–78%.

## What this means for the design

Keep Derrick's cascade: try the cheapest source first and stop when it's enough. Change what "enough" means.

1. **The gate stays.** A thin item from a meaningful interaction (self-share, save) is always enriched: 7% findable is effectively lost.
2. **Sufficiency is per facet, not one number.** Every item, of any media type, has the same facet slots:

   | Facet | Example |
   | --- | --- |
   | What it is | Recipe, tutorial, meme, ad, vlog, review |
   | Topic and entities | Blender, geometry nodes, Gordon Ramsay |
   | Shown | Jellyfish tank, man pulling a chai |
   | Said | Spoken words and on-screen text |
   | Audio | Song title and artist, original sound |
   | Place | Interlaken, Causeway Bay |
   | People | Creator, who appears, friends (counts only) |
   | Vibe | Cozy, chaotic, nostalgic |

   Each slot records its value and which source filled it.
3. **One cheap text pass for everything** (tier 1). An LLM reads the free metadata and writes three things:
   - the **one-sentence summary**;
   - the facets it can fill from text;
   - which facets are **unknown**.

   This is the "benchmark" as a per-item output: not "is it good enough?" but "what don't we know?".
4. **Escalate per missing facet, one source at a time**, cheapest first. A source is skipped if the facets it fills are already known.

   | Tier | Source | Fills | Rough cost |
   | --- | --- | --- | --- |
   | 0 | Free metadata (see the media table) | What, topic, place, people | 0 |
   | 1 | Text pass over tier 0 | Summary, facets, unknowns | Fractions of a cent |
   | 2 | One image (thumbnail, cover or a keyframe) | Shown, on-screen text, vibe | ~258 image tokens |
   | 3 | Audio track | Said, song | ~32 tokens/s |
   | 4 | Full media at low resolution | Everything | ~100 tokens/s |
5. **Decide *where* to spend from use, not from the caption.** Results 2–3 show you can't tell from the text which items will be missed. So, in priority order:
   - (a) thin items from strong interactions;
   - (b) items in the user's active themes (pursue / practise);
   - (c) facets that matter for the item's kind (audio for trend and dance reels, said for tutorials);
   - (d) **on demand**: candidates ranked just below the cut-off for a low-confidence search are enriched and the search re-run. `05-processor.md` already plans (d).
6. **Same slots for every medium.** Only tier 0 and the sources differ:

   | Medium | Tier 0 (free) | Tier 2 image | Tier 3 audio / text |
   | --- | --- | --- | --- |
   | Instagram reel / TikTok | Caption, hashtags, creator, user's note or share text, song name if the platform gives it | Thumbnail or keyframe | Audio track |
   | YouTube video | Title, description, chapters, tags | Thumbnail | Transcript where terms allow, else audio |
   | Image / carousel post | Caption, alt text if present | The image itself | — |
   | Article / link | Title, page text | Lead image | — (text is already there) |
   | Podcast | Show notes | Cover (low value) | Transcript if published, else audio |

   Getting the image or audio for reels is the open question in [A-002](../amendments.md).

## What we couldn't test yet

Whether enrichment actually recovers the misses needs descriptive data for the corpus. Options:

- Muse's video descriptions for the same items, which also serve as a ceiling for what a description pass can add;
- or our own tier 1–3 passes on a sample.

**Next run:** add descriptions to the search text, re-run the eval, and report the gain per facet and per tier against cost.

Prototype code (not product code): `searchlab/info_bench.py`, `info_bench_why.py`, `judge_sample.py`.
