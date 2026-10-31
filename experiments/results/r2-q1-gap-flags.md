# Round 2 · Q1: do the per-facet gap flags predict what search misses?

*30 Oct 2026 · Evaluator (fresh agent, built no method) · dev split only, current labels (t1) · aggregate only. This note has no captions, item codes, MU text, search texts or per-search scores. The numbers are in `r2-q1-gap-flags.json`, and the evaluator-side code is in `experiments/eval/gap_flags.py`. No paid calls were made.*

## Answer in brief

- **The flags predict misses only weakly. None of them beats the caption-richness bar.** The AUCs for predicting a miss under B3:

  | Flag | AUC | Note |
  | --- | --- | --- |
  | (a) `unknown` | **0.60** [0.53–0.64] | |
  | (b) empty | 0.53 | |
  | (c) hedge | 0.55 | |
  | (d) caption richness from round 0, ported | **0.67** [0.59–0.73] | Reproduces round 0's 0.67 |
  | Flags and richness combined | 0.69 | |

  Within a single search, the gap between the flags and richness grows: `unknown` scores 0.575 against 0.668 for richness.
- **The flags describe the text correctly, but they do not track the misses.**
  - When the flag says "known", Muse agrees 75–100% of the time. Audio is the exception at 0.57, with n = 14.
  - When MU has a facet and our text truly lacks it, the flag fires 92–98% of the time for shown, place, people and audio. It fires only 58% of the time for said and 52% for kind.
  - Yet the matching facet flag barely separates found from missed answers:

    | Facet | AUC |
    | --- | --- |
    | place | 0.62 |
    | kind (on topic and name searches) | 0.60 |
    | vibe | 0.55 |
    | shown | 0.50 |
    | people | 0.39 (inverted) |
- **Most misses are deep in the ranking.** The rank of each missed answer under B3:

  | Rank | Share of misses |
  | --- | --- |
  | Top 200 | 12% |
  | 201–1,000 | 36% |
  | Beyond 1,000 or never ranked | 52% |

  On-demand enrichment of a weak search's top 200 could reach at most **12%** of current misses, and its top 1,000 at most 48%.
- **No item-level gate concentrates the misses.** At a fixed share of the corpus, the planned gate (gap × kind relevance × interaction weight × demand) covers about as many current misses as a random pick. Ordering by interaction weight alone covers more, mostly because the labelled answers are skewed toward saved items. So gate sizes should be set by budget and by what the user values, not by the flags.
- **Recommendation:**
  - Run the image rung on everything. It costs $0.30 per 1,000 items with Batch, or $0 locally.
  - Gate audio by kind and gap.
  - Gate full video by interaction weight (self-share, save, collection), with on-demand as a small top-up.

  The gate design section below has the figures for each rung.

## Setup

| | |
| --- | --- |
| Runs | B3 = `e20_hyde_b2_r{1,2,3}`, 16 dev searches, stored 1,000 deep |
| Pairs | 980 (search, right answer) pairs. 447 are grade 2. 4 answers are not enriched (friends' items), and 8 have no caption vector |
| Found | Rank < max(50, 2 × number of answers), per repeat. Miss rate: 0.431 / 0.443 / 0.438. The three repeats agree on 88% of pairs |
| AUC | AUC for predicting a miss, computed per repeat, then averaged. The CI is a bootstrap over searches |
| Facet mapping | The brief's table, using the union over **all** of a search's kinds. Unmapped kinds (time, structure) are ignored. Using the first kind only changes the AUCs by at most 0.01 (overall 0.594 against 0.595) |
| Pair score for (a)–(c) | The share of the search's facets that carry the flag |
| Item flags | Taken from te-v1c, the last valid row per item |
| unknown | The facet is listed in `unknown` |
| empty | The field has no value after the FILLER filter. For kind, the value is `other` or `unknown`. For audio, no field names music or a sound (the same regex as `reference_compare.py`) |
| hedge | Listed unknown but filled |
| Items with no enrichment | Count as unknown and empty on every facet |
| (d) caption richness | `info_bench.py` ported. Six query-independent features (gate ok, content words, IDF sum, topical hashtags, specificity, negative hubness) go into a logistic regression with balanced classes, scored by 5-fold CV on these pairs. Unlike (a)–(c), it is **fitted** on the outcome, so it gets a small advantage |

## Step 2: AUC for predicting a miss

### Overall (n = 16 searches, 980 pairs)

| Predictor | AUC, pooled | 95% CI (by search) | AUC within search (pair-weighted) | Share of pairs flagged |
| --- | --- | --- | --- | --- |
| (a) facet `unknown` | **0.595** (repeats 0.605 / 0.586 / 0.595) | 0.53–0.64 | 0.575 | 0.30 |
| (b) facet empty | 0.532 | 0.46–0.58 | 0.541 | 0.14 |
| (c) hedge | 0.549 | 0.50–0.60 | 0.532 | 0.18 |
| unknown or empty | 0.590 | | | 0.31 |
| **(d) caption richness (CV)** | **0.666** (repeats 0.664 / 0.672 / 0.661) | 0.59–0.73 | **0.668** | — |
| (a)–(c) + (d), CV | 0.687 | | | — |

**Single richness features, unfitted:**

| Feature | AUC |
| --- | --- |
| Topical hashtags | 0.64 |
| Gate ok | 0.58 |
| Content words | 0.55 |
| IDF sum | 0.55 |
| Specificity | 0.45 |
| Hubness | 0.44 |

On caption-vector items only, richness scores 0.660.

**Robustness checks:**

| Subset | Pairs | (a) unknown | (d) richness | Flags + richness |
| --- | --- | --- | --- | --- |
| Grade 2 only | 447 | 0.61 | 0.67 | |
| Answers in the labels before any AI judging (pre-r1) | 796; miss rate 0.49 | 0.62 | 0.69 | 0.72 |
| Answers added later by judged pools | 184; miss rate 0.20 | 0.51 | 0.47 | |

- Pool-added answers come from the runs' top 10, so they are mostly found. Neither predictor works on them.
- The pooling confound does **not** inflate the flags' AUC: it is higher on the original labels.

### Per kind

A pair counts under each kind of its search, so the rows overlap. Kinds with fewer than 3 searches show AUCs only. Treat n = 1 as direction only.

| Kind (dev searches, pairs) | Miss rate | (a) unknown | (b) empty | (c) hedge | (d) richness | (a), within search | (d), within search |
| --- | --- | --- | --- | --- | --- | --- | --- |
| topic (7, 421) | 0.32 | 0.61 | 0.57 | 0.56 | **0.71** | 0.61 | 0.73 |
| name (3, 231) | 0.23 | 0.60 | 0.60 | 0.54 | **0.73** | 0.63 | 0.72 |
| more_like_this (3, 182) | 0.48 | 0.51 | 0.48 | 0.50 | **0.61** | 0.51 | 0.57 |
| place (1, 173) | — | 0.62 | 0.62 | 0.50 | 0.65 | | |
| vibe (1, 139) | — | 0.58 | 0.47 | 0.61 | 0.64 | | |
| people (1, 53) | — | 0.39 | 0.37 | 0.50 | 0.60 | | |
| task → use (1, 48) | — | 0.49 | 0.43 | 0.56 | 0.63 | | |
| said_shown (2, 25) | — | 0.71 | 0.59 | 0.50 | 0.88 | | |
| audio (1, 4) | suppressed (< 20 pairs) | | | | | | |
| **Group: topic + name** (8, 425) | 0.32 | 0.61 | 0.56 | 0.56 | **0.71** | 0.60 | 0.73 |
| **Group: facet kinds** (place, vibe, people, said_shown, audio, task; 7, 442) | 0.54 | 0.57 | 0.51 | 0.54 | **0.65** | 0.57 | 0.66 |

### Per facet: does the facet's own flag separate misses, on searches that need that facet?

| Facet (searches, pairs) | Rate flagged unknown | AUC: unknown | AUC: empty | AUC: hedge | Miss rate if unknown / if not |
| --- | --- | --- | --- | --- | --- |
| kind (8, 425) | 0.26 | **0.60** | 0.56 | 0.54 | 0.48 / 0.26 |
| topics (8, 425) | 0.05 | 0.53 | 0.51 | 0.52 | 0.61 / 0.31 (rare flag) |
| shown (5, 207) | 0.27 | **0.50** | 0.49 | 0.50 | 0.46 / 0.47 |
| vibe (4, 321) | 0.55 | 0.55 | 0.50 | 0.55 | 0.55 / 0.44 |
| place (1, 173) | 0.27 | 0.62 | 0.62 | 0.50 | — |
| people (1, 53) | 0.43 | 0.39 | 0.37 | 0.50 | — |
| use (1, 48) | 0.38 | 0.49 | 0.47 | 0.51 | — |
| said (2, 25) | 0.40 | 0.57 | 0.41 | 0.50 | — |
| audio (1, 4) | suppressed | | | | |

**Reading:**
- The `unknown` flag carries some signal where the missing facet is what the search is about:
  - kind on topic and name searches: misses are 48% when flagged against 26% when not;
  - place.
- It carries none for shown, which matters for more-like-this, and is inverted for people.
- Hedges, meaning a value that was guessed and flagged, are no worse than the other flags at predicting a miss. The hedge flag adds almost nothing.
- Richness wins mostly through topical hashtags and the information gate. Items with few hashtags and thin captions are missed regardless of which facet is asked for.

## Step 3: flag accuracy against Muse (evaluator reading)

**Source:**
- The evaluator's own MU reading from round 1, `refcmp/judged.jsonl`: 126 read items, being the 112 read sample items plus 14 extra thin items.
- Our flags were recomputed from the current te-v1c rows.
- "MU states" means the reader marked the facet covered in MU's description. The definitions are in `e9-reference-vs-mu.md`.

**Columns:**
- **Recall** = P(flag says unknown | MU states the facet). This is low wherever our text often does capture the facet, so we also give:
- **Gap recall** = P(flag | MU states the facet *and* our field is empty or conflicts with MU). This is the case the flag exists for.
- **Precision** = P(MU states the facet and does not contradict ours | flag says known).
- **False alarm** = P(MU is silent on the facet | flag says unknown). Media would add nothing in these cases.

### Read items (n = 126)

| Facet | MU states | Flag rate (unknown) | Recall | **Gap recall** (n gap) | **Precision** (n known) | False alarm |
| --- | --- | --- | --- | --- | --- | --- |
| kind | 1.00 | 0.24 | 0.24 | **0.52** (25) | 0.93 (96) | 0 |
| topic | 1.00 | 0.05 | 0.05 | 0.00 (2) | 0.98 (120) | 0 |
| shown | 1.00 | 0.34 | 0.34 | **0.98** (43) | 1.00 (83) | 0 |
| said | 0.77 | 0.28 | 0.30 | **0.58** (45) | 0.75 (91) | 0.17 |
| audio | 0.68 | 0.89 | 0.91 | **0.93** (69) | 0.57 (14) | 0.31 |
| place | 0.60 | 0.71 | 0.59 | **0.96** (47) | 0.86 (36) | **0.50** |
| people | 0.77 | 0.21 | 0.19 | **0.92** (13) | 0.80 (99) | 0.33 |
| vibe | 0.81 | 0.52 | 0.49 | 0.78 (9) | 0.82 (61) | 0.23 |

- On the 112 sample items alone, every rate is within 0.1 of these. The JSON has the full 2 × 2 tables.
- **Regex extension (cross-check).** The round-1 regex reading of MU (`mu_regex`) was run over every enriched item that has MU text (n = 972). It agrees with the reading on direction:

  | Facet | Gap recall | Precision |
  | --- | --- | --- |
  | shown | 0.98 | 0.93 |
  | place | 0.95 | 0.81 |
  | audio | 0.94 | 0.76 |
  | people | 0.75 | 0.88 |
  | said | 0.57 | 0.79 |
  | kind | 0.79 | 1.00 |

**What this means for builders:**
- "Known" is reliable. When the flag says known, a later media pass rarely has anything to correct: precision is 0.80–1.00, except said (0.75) and audio.
- `unknown` alone under-marks two gaps:
  - **said:** 42% of real said gaps are an empty `said` that is not listed unknown;
  - **kind:** 48% of kind gaps are `other` without the flag, or a confidently wrong kind.

  So a gate should use **unknown OR empty** (step 5 does). Kind errors that the flag cannot see need a media pass or a better kind prompt.
- `place` and `audio` over-flag: half and a third of flagged items, respectively, have no place or audio for MU to state. A gate keyed on them alone spends on nothing about a third to a half of the time.

## Step 4: where the misses sit

The rank of each missed answer, using the median over the 3 repeats. A pair counts as missed if it is missed in ≥ 2 repeats: 424 missed pairs. "Beyond" means not in the stored top 1,000, which includes items never retrieved.

| Group (searches, missed pairs) | Top 200 | 201–1,000 | Beyond 1,000 or unranked |
| --- | --- | --- | --- |
| **All** (16, 424) | **0.12** | **0.36** | **0.52** |
| topic + name (8, 137) | 0.24 | 0.37 | 0.39 |
| more_like_this (3, 87) | 0.17 | 0.39 | 0.44 |
| facet kinds (7, 233) | 0.04 | 0.34 | 0.62 |

- 184 of the 424 misses are absent from the top 1,000 in all three repeats.
- **On-demand enrichment of a weak search's top-N candidates** can reach at most:

  | Candidates enriched | Share of misses reachable |
  | --- | --- |
  | Top 50 | 0% |
  | Top 200 | 12% |
  | Top 1,000 | 48% |

  This is an upper bound: reaching a candidate does not guarantee the new description lifts it into the top K.
- Facet searches (place, vibe, people, said, audio, task) are the ones media is meant to fix, yet only 4% of their misses are in the top 200. Most of the reach has to come from background enrichment.

## Step 5: the media gate (design only, no media spend)

### Cost per 1,000 items enriched

The cost is for a gemini-3.1-flash-lite describe pass at the prices verified on 2026-10-30 in `lib/ai_prices.json`.

**Assumptions:**
- Input: the te-v1c mean of 641 text tokens (prompt plus caption) and 250 output tokens.
- Media tokens, from the Gemini 3 table in `research/mlt-multimodal-audio-media.md`:
  - image at low resolution: 280 tokens;
  - audio: 25 tokens per second, billed at the audio price;
  - video: 70 tokens per frame at 1 fps, plus its audio.
- Each reel is assumed to be 30 s long, because the export has no durations.

| Rung | Fills | Standard | Batch | Local alternative |
| --- | --- | --- | --- | --- |
| Image (thumbnail or 1 frame) | shown, on-screen text, vibe, place | $0.61 | $0.30 | SigLIP2 / CLIP, $0 |
| Audio (30 s) | said, song or lyrics | $0.91 | $0.46 | faster-whisper (said only), $0. Song names need fingerprinting |
| Full video (30 s, 1 fps) | Everything except a reliable song name | $1.44 | $0.72 | — |

**Universe:** 20,829 enrichable items (friends' items excluded), of which 17,583 are reels and 3,246 are posts. The audio and video rungs apply to reels only.

### Rule candidates

- **Share** is the share of enrichable items the rule selects.
- **$ / 1k corpus** is the Batch cost spread over every corpus item.
- **Misses covered** is the share of the 424 current misses whose answer item is selected. A second number also requires that the rung fills a facet the search needs (image: shown, vibe, said, place; audio: said, audio; video: all).

| Rung | Rule | Share | $ / 1k corpus (Batch) | Misses covered: item | Misses covered: item + facet |
| --- | --- | --- | --- | --- | --- |
| Image | gap(shown or vibe) and w ≥ 0.8 | 0.12 | $0.036 | 0.18 | 0.08 |
| Image | gap(shown, vibe or place) and w ≥ 0.6 | 0.19 | $0.058 | 0.28 | 0.13 |
| Image | gap(shown or vibe) and (w ≥ 0.8 or thin caption) | 0.34 | $0.104 | 0.29 | 0.16 |
| Image | gap(shown, vibe or place) | 0.89 | $0.270 | 0.83 | 0.49 |
| Image | **Everything** | 1.00 | **$0.303** | 1.00 | 0.63 |
| Audio | reel and ((audio gap and kind ∈ music_dance, meme_joke, skit) or (said gap and kind ∈ tutorial, tips, review, news_info, motivation, vlog, recipe)) | 0.25 | $0.115 | 0.23 | 0.01 |
| Audio | the same, and w ≥ 0.8 | 0.035 | $0.016 | 0.06 | 0.00 |
| Audio | **Everything (all reels)** | 0.84 | $0.384 | 0.94 | 0.03 |
| Video | reel and w ≥ 0.8 and thin caption | 0.037 | $0.026 | 0.04 | 0.04 |
| Video | reel and w ≥ 0.8 and ≥ 4 of 7 facets with a gap | 0.08 | $0.058 | 0.11 | 0.11 |
| Video | **reel and w ≥ 0.8** | 0.145 | $0.104 | 0.26 | 0.26 |
| Video | **Everything (all reels)** | 0.84 | $0.606 | 0.94 | 0.94 |

In these rules, **w** is the item's highest interaction weight: self-share 1.0, save or collection 0.8, friend share 0.6, like 0.3, watch 0.1. **gap** means the facet is unknown or empty.

**On-demand only.** A weak search triggers the rung on its own top N, synchronously and at standard price.

| N | Misses reachable | … where image fills the facet | … audio | … video | $ per 1,000 weak searches (image / audio / video) | Share of corpus touched by the 16 dev searches |
| --- | --- | --- | --- | --- | --- | --- |
| 50 | 0.00 | 0.00 | 0.00 | 0.00 | $30 / $46 / $72 | 3.5% |
| 200 | 0.12 | 0.04 | 0.005 | 0.12 | $121 / $182 / $287 | 13% |
| 1,000 | 0.48 | 0.25 | 0.01 | 0.48 | $605 / $910 / $1,435 | 46% |

It also adds latency: 200 describe calls per search.

### Does the gate target misses better than chance?

The table below holds the corpus share fixed at **25%**. Each cell is the share of current misses whose answer item is selected; the second number, in brackets, is the share of *found* answers selected. A gate that targets misses has the first number well above the second and above random.

| Order (top 25% selected) | Image | Audio (reels) | Video (reels) |
| --- | --- | --- | --- |
| Gate: w × Σ gap × kind relevance × search demand | 0.26 (0.30) | 0.24 (0.26) | 0.25 (0.19) |
| Gate without interaction weight | 0.14 (0.10) | 0.23 (0.20) | 0.18 (0.10) |
| Interaction weight only | 0.36 (0.45) | 0.38 (0.38) | 0.38 (0.38) |
| Caption richness, lowest first (in-sample fit) | 0.16 (0.02) | 0.18 (0.02) | 0.18 (0.02) |
| Random | 0.27 (0.25) | 0.27 (0.26) | 0.27 (0.26) |

- **Search demand** is the share of all 22 searches whose kinds need the facet, from the method-side `queries.jsonl` (kind and topics 0.45, shown and vibe 0.27, place, said and use 0.09, audio and people 0.05).
- **Kind relevance** is 1.0 for audio on music, dance and trend kinds, and for said on how-to and talking-head kinds; 0.3 off-kind; 1.0 for every other facet.
- The JSON also has the curves at 10% and 50%. They show the same pattern.

**Reading:**
- **The flags add no targeting at the corpus level.**
  - The gap-based gate covers misses at about the random rate.
  - Without the weight term it does worse than random.
  - Richness (lowest first) picks items that are rarely answers at all. Thin, untagged items are seldom relevant to any search, so its AUC of 0.67 among answers does not carry over to choosing items.
- **Interaction weight covers the most misses, but it is not targeting either.** It selects found answers even more often (0.45 against 0.36 for image), because the labelled answers skew toward saved items:

  | Population | Share with w ≥ 0.8 |
  | --- | --- |
  | Corpus | 17% |
  | Missed answers | 27% |
  | Found answers | 38% |

  Weight is a product reason (what the user keeps), not a miss predictor.
- **The audio rung's value cannot be measured on this eval.** Only 3 dev searches need said or audio (29 answers), so 0–3% of misses are "audio-fixable" by facet. The audio rung's corpus share and cost are real, but its benefit is unmeasured here.
- Facet coverage is an upper bound. A selected item is only *eligible* to be fixed. The round-1 MU ceiling, not repeated here, is the better bound on what a description can add per kind.

### Proposed gate (design; for the orchestrator and builders)

1. **Image rung: everything.**
   - Cost: $0.30 per 1,000 items with Batch, about $6.3 per 21k-item user. Locally on the desktop with SigLIP2 it costs $0.
   - It reaches every miss, and 63% of misses are on searches whose facet an image can fill.
   - A gate saves at most $0.30 per 1,000 items and loses coverage roughly in proportion.
   - If a cap is needed: weight first, then gap(shown, vibe or place).
2. **Audio rung: kind-gated.** Select reels with (audio gap and a music, dance or trend kind) or (said gap and a how-to or talking-head kind).
   - That is 25% of the corpus, $0.115 per 1,000 corpus items with Batch (about $2.4 per user).
   - Use local whisper for said where the desktop allows.
   - Validate it on a said/audio search set first, because the current eval cannot show its value.
3. **Full-video rung: reels with w ≥ 0.8** (self-share, save, collection).
   - That is 14.5% of the corpus, $0.104 per 1,000 corpus items with Batch (about $2.2 per user), and covers 26% of current misses.
   - All reels would cost $0.61 per 1,000 (about $12.6 per user) for 94%.
   - Add more by budget in weight order. The flags do not pick better than weight or random.
4. **On-demand: a top-up only.**
   - For a weak search, enrich its top 200 at the image or video rung.
   - That reaches at most 12% of misses, at $121–287 per 1,000 weak searches and a multi-second wait.
   - Run it in the background after the first screen, not in the query path.
5. **Use unknown OR empty as the gap definition.** Do not rely on `unknown` alone: it misses 42% of said gaps and 48% of kind gaps.
   - Do not treat `hedge` as a separate trigger; it predicts nothing extra.
   - The flags are still worth keeping. They are accurate as descriptions (when the flag says known, MU agrees in 0.80–1.00 of cases, said and audio excepted) and say *which* facet to fill once an item is selected.
   - They just should not decide *which items* are selected.

## Caveats

- **Small and skewed eval.**
  - 16 dev searches.
  - The facet kinds have 1–2 searches each, so per-facet AUCs for place, vibe, people, use, said and audio are direction only.
  - Labels mostly come from Muse's MU matching (pre-r1 answers make up 81% of pairs), so "miss" partly means "Muse found it from the video, text search did not".
- **Richness gets the advantage.** It is fitted (CV) on the same pairs, while the flags are unfitted. Even so, unfitted topical hashtags alone (0.64) beat the best flag.
- **Flag accuracy uses one reader's MU reading** (126 items, 24 of them thin). MU is model output, not ground truth.
- **The cost model assumes 30 s reels and a 250-token output.** Media remains blocked by A-002 for Instagram, so these are design figures only.
