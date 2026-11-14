# Round 3 (YouTube) · what the experimenter built and ran

*31 Oct 2026 · Experimenter (builder) · no scores: the experimenter has seen no labels. This note has no titles, no search texts and no video IDs. Searches are referred to as S01–S33 by kind. The key to those labels is in `data/yt/notes/r3_search_key.json` (gitignored).*

Code is in `experiments/methods/yt_*.py`, plus two additions to `lib/ai.py`: `youtube_video_request` / `gemini_youtube_json` and `gemini_modality_cost`. Run files are in `data/yt/runs/`: 42 files, each covering all 33 searches (22 dev, 11 test). Every run is written by `lib/corpus.py`'s format and carries cost and latency in `meta`.

## Corpus and gate counts

| | Count |
| --- | --- |
| Items (videos) | 115,615 |
| … with a Takeout title (get an allowed-view vector) | 100,967 |
| … with an API row (reference view) | 105,090. Vectors cover 111,106 items: API row or Takeout title |
| **Tier-1 gate** (depth light/full, or watched ≥ 3 times) | **11,101** |
| … with a Takeout title (A1 set) | 6,481. Plus 4 more-like-this examples, so 6,485 were sent and 6,479 came back ok |
| … with an API row (R1 set) | 10,557. Plus the in-library example, so 10,558 were sent and 10,545 came back ok |
| Video-pass eligible pool (available, known duration) | 105,085 |
| Typed searches / more-like-this searches | 29 / 4 (S17, S26, S27, S28). 3 of the 4 have their example outside the library |

## Runs

The base recipe for every run is **B3 ported to YouTube**:
- the qr-v1 rewrite (gpt-5-nano, minimal reasoning, cached, 3 repeats → `_r1/_r2/_r3`);
- dense search: max over [query + phrases + HyDE vector], with Rocchio PRF from the top 5;
- BM25 over the view text (query + keywords);
- for each enrichment index, a BM25 list and a dense list (max over the same vectors);
- RRF (k = 60) in content-code space.

More-like-this uses:
- the centroid of the examples' vectors. Examples outside the library are embedded from their given "Channel - Title", rewritten as "Title by Channel".
- BM25 on the examples' text;
- the examples' enrichment text and vectors.

Examples are excluded from the results. The search's own `filters` are applied; all are empty in this set.

**Differences from Instagram B3** (each the same in every run):
- **Embeddings:** OpenAI `text-embedding-3-small` at 512 d instead of bge-small (RUN-3).
- **No caption information gate:** every item with a title is in the dense leg, because titles are too short for the Instagram gate.
- **Allowed view text:** title + "by <channel>" + the user's named playlists. "Watch later" is left out because it is an interaction, used only by A3.

| Run files | What it is | Lists fused (typed search) |
| --- | --- | --- |
| `a0_r{1,2,3}` | **A0:** allowed baseline | dense (allowed view) + BM25 (allowed view) |
| `a1_r*` | **A1:** A0 + te-v1c over Takeout text, gated | + te BM25 + te dense |
| `a2_gated_r*` | **A2 gated:** A1 + video pass, gated arm (377 videos + 4 example videos) | + video BM25 + video dense |
| `a2_random_r*` | **A2 random:** A1 + video pass, random arm (790 videos + the same 4 example videos) | + video BM25 + video dense |
| `a3_intent_on_a1_r*`, `a3_intent_on_a2_gated_r*` | **A3 (qi-v1), full:** qi-v1's own text plan + its intent, applied on A1 / A2-gated | as the base, then intent filter/re-order |
| `a3_filtersonly_on_{a1,a2_gated}_r*` | **A3 (qi-v1), filters only:** qr-v1 text plan (identical to the base run) + qi-v1's intent. **Only the intent differs from the base** | as the base, then intent |
| `a3v2_intent_on_{a1,a2_gated}_r*`, `a3v2_filtersonly_on_{a1,a2_gated}_r*` | The same four with **qi-v2**: tighter intent rules (see below) | as above |
| `ref_r0_r*` | **R0, research only:** A0 with the API view: title + description[:600] (URLs and chapter lines removed) + tags + chapter titles + channel + playlists | dense + BM25 (API view) |
| `ref_r1_r*` | **R1, research only:** R0 + te-v1c over the API text, same gate. Outside-library MLT examples use their allowed te-v1c row, built from the given title | + te(API) BM25 + te(API) dense |

**Moments.** Runs with the video index (A2 and A3-on-A2) carry a `moments` block for the moment search (S29): 20 segments, ranked by RRF of three lists, using segments of videos in the fused top 100:
- segment-summary dense;
- segment BM25;
- the parent video's rank.

No other run has moments. There, the scorer gives video credit only.

**Comparisons the runs are built for** (one variable each):

| Comparison | Variable |
| --- | --- |
| A1 vs A0 | tier-1 text lists |
| A2 gated vs A2 random | **video selection rule at equal spend** (the gate test) |
| A2 * vs A1 | the video lists |
| A3 filters-only vs its base | the intent step only |
| A3 full vs its base | intent + the qi prompt's text plan |
| R0 vs A0 | API text in place of Takeout text |
| R1 vs R0 | tier-1 over API text |
| R1 vs A1 | what the terms decision costs at tier 1 |

## Cost and latency (measured, ledger `data/yt/ai_runs.jsonl`, list prices)

| Step | Items | Cost | Per 1k | Wall / latency |
| --- | --- | --- | --- | --- |
| Allowed-view embeddings (3-small, 512 d) | 100,967 | $0.036 | $0.0004 / 1k items | 42 s (2,430 items/s, 4 threads) |
| API-view embeddings (ref) | 111,106 | $0.306 | $0.0028 / 1k items | rate-limited (429); ~10 min with backoff |
| Enrichment / segment embeddings | 6,479 + 10,545 + 1,168 + 6,597 segments | $0.032 | — | seconds |
| Query + HyDE vectors | 1,521 strings | $0.0004 | — | p50 0.27 s, p95 0.38 s per call |
| qr-v1 rewrite, 3 repeats × 29 | 87 calls | $0.010 | $0.12 / 1k searches | p50 1.39 s |
| qi-v1 intent rewrite, 3 × 29 | 87 | $0.015 | $0.17 / 1k searches | p50 1.59 s |
| qi-v2 intent rewrite, 3 × 29 | 87 | $0.016 | $0.18 / 1k searches | p50 1.56 s |
| **A1 te-v1c, Takeout text** (Batch) | 6,485 | **$1.105** | **$0.170 / 1k items** | 2 jobs, 125–140 s each; 582 in / 130 out tokens per item |
| **R1 te-v1c, API text** (Batch, ref) | 10,558 | **$2.048** | **$0.194 / 1k items** | 3 jobs, 84–164 s; 699 in / 142 out tokens per item |
| Video pilot (sync, 14 calls) | 10 videos | $0.075 | — | p50 6.2 s (config B) |
| **Video pass, gated arm** (Batch) | 377 | **$1.820** | **$4.83 / 1k videos**; $0.020 per video-hour processed | 92.9 h of video processed (clip ≤ 20 min) |
| **Video pass, random arm** (Batch) | 790 | **$1.703** | **$2.16 / 1k videos**; $0.021 per video-hour | 79.6 h |
| Video pass, MLT example videos | 4 | $0.018 | — | |
| Video sync retries (8 failed batch rows) | 8 | $0.051 | — | p50 6.0 s |
| Video Batch jobs | 6 jobs of 169–200 | | | 128–250 s per job |

**Search latency (local, query vectors cached):**
- A0 p50 0.08 s; A1 0.11 s; A2 0.10–0.13 s; A3 0.10–0.13 s; R0/R1 0.21 s (larger BM25 vocabulary).
- Add one query-embedding call (p50 0.27 s) and the rewrite (p50 1.4–1.6 s).
- Index build: ~9 s for the allowed view, ~25 s for the API view.

**Totals this round:** OpenAI **$0.415** of $4; Gemini **$6.758** of $8. Gemini paid work stopped there: $1.24 left, above the $0.75 stop rule, but nothing paid remained to run.

## Tier-1 pass: what came back (no scores)

| | A1 (Takeout text) | R1 (API text) |
| --- | --- | --- |
| Mean `unknown` facets per item (of 9) | 5.7 | 3.6 |
| `kind` unknown/other | 38.6% | 22.5% |

The prompt is round 1's te-v1c unchanged. The pilot showed no need for a YouTube variant: the outputs parsed and validated at 99.9%.

## Video pass (tv-v1): pilot findings

**Model and output.** gemini-3.1-flash-lite, by public YouTube URL; no download, and only the model's text is stored. The output holds:
- a description, kind, topics, people, place and vibe;
- on-screen text;
- music;
- ≤ 12 timestamped segment summaries (paraphrased, at most 5 quoted words);
- 3–5 likely searches.

**Pilot results** (10 random eligible videos):

1. **Clipping by URL works.** With `videoMetadata.end_offset = 1200 s`, three videos of 25–85 min each billed 45.8k input tokens, exactly 1,200 s × 38.2.
   - The model sometimes wrote segment times **past the clip end** (2 of 3 clipped videos). They are clamped to the clip.
2. **fps and resolution work by URL.**
   - Config A (defaults: 1 fps, default resolution) costs **~92–111 tokens/s**.
   - Config B (`fps 0.2`, `MEDIA_RESOLUTION_LOW`) costs **38.2 tokens/s**: 2.4× cheaper.
   - Config B gave as many or more segments (7.4 vs 4.0 on the shared videos), so it was used for both arms.
3. **Audio is not reported separately.** `promptTokensDetails` lists only VIDEO (+ TEXT) for URL input, and everything is billed at the media rate.
4. **Cost.** A 20-min clip costs $0.0127 standard and ~$0.0063 in Batch; a Short costs ~$0.0007 standard. Latency: 2.5–16 s sync.
5. **The Batch API did not enforce `responseJsonSchema`** for these requests, though sync calls did.
   - About half the outputs were a one-element list around the object, `kind` was always missing, and segments came in at least six shapes: `"start_s: 0, end_s: 9, summary: …"` strings, flattened `[0, 9, "text", …]`, `"00:00 text"`, `"0, 4, text"`, `"0_6: text"`, and objects.
   - The first collection marked 37% of rows invalid. A lenient parser recovered them from the stored job results, with no re-spend.
   - Final: 1,168 of 1,169 videos ok. 76% (gated) / 70% (random) have segments. `kind` is "other" for 99%.
   - **Product note:** with URL video in Batch, validate leniently or use sync with the schema.
6. **Failures.** 8 videos failed in Batch (1 internal error, the rest unparseable); all 8 succeeded on sync retry. No video was refused as private or restricted.

## Video arms (equal budget, $1.80 each)

**Gate.** Round 2's media gate, adapted: score = w × Σ_f gap(f) × kind_rel(f) × demand(f).
- **w:** max interaction weight (playlist 0.8, like 0.3, watch 0.1), or 0.1 × watch count capped at 0.6, so that rewatches count.
- **gap:** te-v1c (allowed) says unknown or empty. Every facet is a gap when the item has no te-v1c row (no title).
- **kind_rel:** 0.3 for audio/said when off-kind.
- **demand:** the share of all 33 method-side searches whose kinds need the facet: kind 0.79, topics 0.76, use 0.42, vibe 0.27, people 0.21, shown 0.18, audio 0.18, said 0.15, place 0.12.
- Ties are broken at random with a fixed seed.

**Random arm.** A seeded shuffle of the same 105,085-video pool.

**Selection.** Each arm takes videos in its order until the pilot-based Batch cost estimate reaches $1.80, so the N differs per arm.

| Arm | N | Real cost | Saved (playlist / Watch later) | Liked | No Takeout title | Has a te-v1c row | ≤ 60 s | Median length | Clipped at 20 min |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gated | **377** | $1.820 | 100% | 0.5% | **95.8%** | 4.2% | 0.3% | 17 min | 41.6% |
| Random | **790** | $1.703 | 5.7% | 4.7% | 4.8% | 6.8% | 46.7% | 69 s | 13.5% |

The arms share 2 videos. **The gate in effect selects saved videos with no Takeout text**, which had no searchable text at all before (no title means no vector and no BM25 text). About 361 such items become searchable in the gated arm and ~38 in the random arm. That is the gate doing what it was designed to do. It also means that "gated vs random" mixes "which items" with "long vs short videos" at equal spend.

## A3 intent step

**Prompt qi-v1** = qr-v1 with its Instagram `filters` field replaced by an `intent` block:
- watched_after / watched_before (on the user's interaction dates);
- require / exclude (liked, saved, watched);
- min/max watch count, min/max duration;
- shorts only/exclude;
- sort (relevance, most_watched, longest, shortest, newest, oldest);
- topic_free and era_of_topic.

The few-shots are qr-v1's two synthetic pairs, plus one synthetic YouTube behaviour pair.

**Applying it** (`yt_intent.apply`, on the user's interactions and API durations only, no other API data):
- **Pool filter.**
  - A date window keeps items that have an interaction in the window (of the required kind, if one is given).
  - require / exclude / watch-count / duration / Shorts work as masks.
  - Shorts = ≤ 60 s, or ≤ 180 s with "#short" in the title (orientation is unknown).
- **No filter active and sort = relevance:** the ranking is unchanged.
- **Pool < 5:** the filter is applied softly (pool items first, then the rest).
- **topic_free:** the ranking is the behaviour order of the pool.
- **sort ≠ relevance:** RRF(text order in the pool, behaviour order).
- **Otherwise:** text order in the pool, then the rest of the pool by interaction weight. Items with no text, such as untitled saved videos, can therefore surface.
- **era_of_topic:** the 10th–90th percentile of the interaction dates of the top 30 text hits, padded by 30 days, becomes a soft RRF boost.
- **A small pool truncates the list.** When the pool is small (5–8 items), the run lists only those items for that search (S07 qi-v2 r3, S19 qi-v1 r3).

**qi-v2.** qi-v1's outputs on the 29 typed searches (method side, no scores) showed generic misreadings, so qi-v2 was written *after seeing them*. That is a mild overfitting risk, so both are delivered.

| qi-v1 misreading | Example |
| --- | --- |
| `require` used as a loose list | require saved+watched for "never watched" |
| `exclude` used for topics to avoid | — |
| `topic_free` set for mood or purpose searches | two repeats replaced the text ranking with a behaviour order |
| Dates guessed for vague life periods | — |

qi-v2 tightens each rule: require only liked/saved when stated; exclude only interactions said not to have happened; topic_free only with no subject, mood or purpose; no guessed dates. In code, require ∩ exclude is dropped from require (this only affects qi-v2, since the qi-v1 parses were stored before the change). The model and reasoning effort are unchanged.

**Finding:** intent extraction with gpt-5-nano at minimal reasoning is **unstable across repeats**. In several searches each repeat gets a different filter. qi-v2 is quieter (12–14 of 29 searches get any intent, vs 14–18 for qi-v1) but still varies.

**Filters per search, qi-v1, three repeats.** "none" = no intent; "→" = how it was applied; pool = items passing the hard filter.

| Search | Split | Kinds | r1 | r2 | r3 |
| --- | --- | --- | --- | --- | --- |
| S01 | dev | task, topic, structure | none | none | none |
| S02 | dev | task, topic, structure | require liked+saved → filter, pool 10,114 | require watched → filter, pool 108,685 | require watched → filter, pool 108,685 |
| S03 | dev | task, topic, structure | none | none | none |
| S04 | dev | topic | none | none | none |
| S05 | dev | task, topic | window 2026-01-01..2026-10-30; require liked+saved → filter, pool 1,659 | require saved+watched → filter, pool 112,973 | require liked+saved+watched → filter, pool 115,615 |
| S06 | dev | name | none | none | none |
| S07 | dev | vibe, time, personal | window 2005..2015; exclude all; era → soft (pool 0) | window 2000..2020; require saved+watched → filter, pool 8,409 | window 2000..2020; era → filter, pool 9,680 |
| S08 | test | task, topic | require liked+saved → filter, pool 10,114 | require saved → filter, pool 5,213 | none |
| S09 | test | name, topic | none | none | none |
| S10 | test | vibe | topic-free (no effect) | topic-free (no effect) | topic-free (no effect) |
| S11 | test | name, people | require watched → filter, pool 108,685 | none | require liked+saved → filter, pool 10,114 |
| S12 | dev | task, topic | none | none | none |
| S13 | dev | personal, behaviour, topic | topic-free (no effect) | topic-free (no effect) | require watched; watches ≥ 1 → filter, pool 108,685 |
| S14 | test | task, personal | none | require liked+saved; topic-free → behaviour only, pool 10,114 | topic-free (no effect) |
| S15 | dev | vibe, task | none | require liked+saved → filter, pool 10,114 | topic-free (no effect) |
| S16 | dev | behaviour, personal | window 2015..2026; require saved+watched; sort most_watched → rrf, pool 112,962 | require watched; watches ≥ 3; sort most_watched → rrf, pool 1,065 | topic-free (no effect) |
| S18 | dev | vibe, task | topic-free (no effect) | topic-free (no effect) | require watched; topic-free → behaviour only, pool 108,685 |
| S19 | dev | time, personal, topic | window 2020..2022; require saved+watched → filter, pool 22,426 | window 2021..2022; require liked+saved → filter, pool 537 | window 2015..2018; require saved+watched; era → filter, pool 8 |
| S20 | test | vibe, topic | none | none | none |
| S21 | dev | topic, structure | exclude all → soft (pool 0) | exclude all → soft (pool 0) | exclude all → soft (pool 0) |
| S22 | dev | task, topic, structure | topic-free (no effect) | require all three → filter, pool 115,615 | topic-free (no effect) |
| S23 | dev | name, time | none | era → era boost | era → era boost |
| S24 | dev | name | none | none | none |
| S25 | test | topic, people | none | none | none |
| S29 | dev | said_shown, moment, name | none | none | none |
| S30 | test | behaviour, structure | require saved+watched; sort oldest; topic-free → behaviour only, pool 112,973 | require saved+watched; exclude watched; sort oldest → rrf, pool 4,288 | require saved+watched; exclude liked; sort oldest → rrf, pool 110,584 |
| S31 | dev | time, topic, behaviour | window 2020-06-01..2020-08-31; require watched; era → filter, pool 3,200 | window 2020-06-01..2020-08-31 → filter, pool 3,300 | window 2020-06-01..2020-08-31; require watched → filter, pool 3,200 |
| S32 | test | name, audio | none | require liked+saved → filter, pool 10,114 | require liked → filter, pool 5,031 |
| S33 | dev | people, shown, audio | none | none | require liked+saved → filter, pool 10,114 |

**qi-v2, three repeats** (same conventions):

| Search | Split | r1 | r2 | r3 |
| --- | --- | --- | --- | --- |
| S01 | dev | none | none | require saved+watched → filter, pool 112,973 |
| S05 | dev | require liked+saved → filter, pool 10,114 | none | require liked+saved → filter, pool 10,114 |
| S07 | dev | window 2020-01-01..2026-10-30; era → filter, pool 114,499 | era → era boost | window 1995..2015; dur ≤ 600 s; era → filter, **pool 5** |
| S08 | test | none | require saved → filter, pool 5,213 | none |
| S10 | test | topic-free (no effect) | topic-free (no effect) | topic-free (no effect) |
| S13 | dev | topic-free (no effect) | none | none |
| S14 | test | none | none | topic-free (no effect) |
| S15 | dev | none | topic-free (no effect) | none |
| S16 | dev | require saved+watched; watches ≥ 3; sort most_watched → rrf, pool 1,065 | require watched; watches ≥ 3 → filter, pool 1,065 | require watched; watches ≥ 3; sort most_watched → rrf, pool 1,065 |
| S18 | dev | topic-free (no effect) | topic-free (no effect) | topic-free (no effect) |
| S19 | dev | era → era boost | require liked+saved; era → filter, pool 10,114 | window 2025-01-01..2025-12-31; era → filter, pool 25,153 |
| S20 | test | none | topic-free (no effect) | topic-free (no effect) |
| S21 | dev | exclude all → soft (pool 0) | exclude all → soft (pool 0) | exclude all → soft (pool 0) |
| S22 | dev | none | none | topic-free (no effect) |
| S23 | dev | era → era boost | topic-free (no effect) | era → era boost |
| S30 | test | topic-free (no effect) | require saved; exclude liked+watched → filter, pool 4,189 | require saved → filter, pool 5,213 |
| S31 | dev | window 2020-06-01..2020-08-31; require all three → filter, pool 3,300 | window 2020-06-01..2020-09-01; era → filter, pool 3,353 | window 2020-06-01..2020-08-31; require all three → filter, pool 3,300 |
| S32 | test | require liked → filter, pool 5,031 | require liked → filter, pool 5,031 | none |
| other 11 typed searches | | none | none | none |

Neither version ever set a duration bound for the "long" behaviour search (S30). The behaviour searches were filtered as follows:

| Search | Filter |
| --- | --- |
| S16 | watches ≥ 3 in 5 of 6 repeats |
| S30 | exclude watched in 2 of 6 repeats |
| S31 | the right summer window in 6 of 6 repeats |

## Rule notes (honest record)

1. **One model summary on the console.** While diagnosing the Batch output format, one console print showed one video's model-written segment summaries (a public video, no title or ID). It was not written to any file or note.
2. **One blocked read.** One attempt to read a background task's output file under `/tmp/claude-0/` was blocked by the permission system before anything was read. After that, logs were written to `data/yt/` only.
3. **Round-1 score in LOG.md.** Reading LOG.md's header for the row format showed round-1 Instagram protocol notes, which include one aggregate Instagram dev score. No YouTube scores exist, and none were seen.
4. **Not seen:** no labels, `eval/` result files or per-query scores were opened.
