# Round 7 · what the experimenter built and ran

*7 Nov 2026 · Experimenter (builder) · no scores. The experimenter saw no labels, no `eval_work/`, no `runs/final*/`, no `runs/rewrites/test*/` and no per-search scores. This note has no captions, titles, search texts or search ids. Preregistration: the "Round 7 fixed parameters" block and rows Y7-H0 … Y7-H6 in `LOG.md`, committed in `3f9da0f` before any paid call, training or run. One deviation note (H0, below) was added to that block before any H run.*

Code:
- `experiments/methods/c7_synth.py`: prompt syn-v1 and the synthetic-search generator for the router;
- `c7_lib.py`: facet classifiers (`train_facets`, `Facets7`), the router (`train_router`, `Router`), platform-share calibration (`calibrate`), creator profiles on 3-large vectors (`Creators7`, with H4's channel-type / era words and priors), the soft time direction (`lexicon_dir`, `time_dir`, `TimePct`), the centred top-300 boosts (`boost_top`) and the qr-v1 filter → intent mapping (`qr_intent`);
- `c7_train.py`: trains both facets and the router on training-side data only and writes their quality files;
- `c7_search.py`: configs `h0chk`, `h0`, `h1`–`h5`, `h5b` (and `h6`, not run), run files with cost and latency in `meta`; `--stats` writes the fire counts below.

Models, synthetic searches and quality files are in `data/all/r7/` (gitignored).

## Runs written (`data/all/runs/r7/`, 21 files)

All runs cover `dev` (44) + `yt_holdout` (11) = 55 searches (47 typed, 8 more-like-this), with 3 repeats. Repeat k uses C0's cached gpt-5-nano qr-v1 repeat k and, where read, the cached guarded qs-v1 repeat k (round 5). No LLM call is made at search time.

| Runs | Variable vs H0 | Reads qs-v1 | Pair with |
| --- | --- | --- | --- |
| `h0_r*` | **H0 = G4** (C0 + 3-large 1,024 d), rebuilt this round (see Deviations) | no | C0 `r4.2/c0x_r*` |
| `h1_r*` | qr-v1's own filters with E1's guards (widen only) + soft old / new time boost | no | `h0` |
| `h2_r*` | format / tone facet classifiers as a centred soft boost on qs-v1 format / tone searches | yes | `h0` |
| `h3_r*` | query router: platform-share calibration + creator search on router-creator searches | no | `h0` |
| `h4_r*` | creator search with era, affinity and channel-type profiles on qs-v1 creator-lookup searches | yes | `h0` |
| `h5_r*` | the package H0 + H1 + H2 + H3 + H4 (composition fixed in LOG.md) | yes | `h0`, C0 |
| `h5b_r*` | H5 + F0's te lists for caption-type / untitled items, coverage-fair fusion | yes | `h5`, `h0`, C0 |

**H6 was not run.** The cross-encoder needs PyTorch, and its install did not go through cleanly: pip could not reach the PyPI file host for torch's dependencies from this machine. The brief makes H6 optional "only if it installs cleanly", so it was skipped. The code path (`h6`) exists but is untested.

**Sanity checks (1,000 deep, every repeat).** H1, H2 and H4 equal H0 exactly on every search where none of their parts fired: 40–44, 43–44 and 53–54 of 55 searches. H3 equals H0 on the 8 more-like-this searches. Calibration runs on every typed search, so H3 changes all of them.

## Definitions

### H0: rebuilt, not the r6 files

- H0 is G4's code with G4's inputs: `c4_lib.Combined`, `c6_lib.swap_to_3l` and C0's nano qr-v1.
- The `r6/g4` files cannot be reproduced exactly. That is why `h0` has its own files.

### Facet classifiers (H2, and H4's channel type)

**Training data.** Only te-v1c `ok` rows whose item has a 3-large vector: 24,974 rows for the format facet and 23,767 for the tone facet.
- The features are the item's 3-large own-view vector alone, with no platform feature.
- No new LLM labels were made. The optional nano labelling was skipped.

**Split.** 80 / 20 by a hash of the item code. The held-out 20% (19.9%) was never used to fit or choose anything. C was chosen by 5-fold CV on the 80%. The model fitted on the 80% is the one used at search time.

**Format facet.** Single label, multinomial logistic regression, 8 classes:

| Class | te kinds |
| --- | --- |
| howto | tutorial, tips, recipe, art_process |
| review | review, product_ad |
| explainer | news_info |
| vlog | vlog, travel |
| comedy | meme_joke, skit |
| music | music_dance |
| motivation | motivation |
| other | other, pets_animals |

Rows with te kind `unknown` are left out of training.

**Tone facet.** One binary logistic regression for each of round 5's 9 `TONE_MAP` classes. A row is positive when one of its te vibes is in the class's vibe set, or its te kind is in the class's kind set. Rows with no vibe are left out.

**Inference.** Every item with a 3-large vector, 121,169 in all, gets 8 format and 9 tone probabilities. Training plus prediction took 97 s on 2 CPUs. The probabilities are precomputed, so search time pays nothing for them.

### Query slots → facet classes, and the H2 boost

The cached guarded qs-v1 slots are mapped to facet classes:

| qs-v1 slot | Facet class |
| --- | --- |
| tutorial, recipe | howto |
| review | review |
| explainer | explainer |
| vlog | vlog |
| skit_meme | comedy |
| music_performance | music |
| reaction, compilation, list, clip, interview_podcast, other | none (no te class exists for them) |
| each tone value | the tone class of the same name |

For a slot with several tone values, an item's tone score is the max over those classes.

**The boost.** It touches only the top 300: score′ = F + 0.008 · mean over the active facets of (p − mean p in the top 300). Items without a vector get 0. The top 300 are then re-sorted stably.

### H1: the rewrite's own filters and soft time

**Filters.**
1. qr-v1 `filters` are mapped to a qi-v3 intent:
   - the window → after / before;
   - save / collection → `saved`, like → `liked`, share_self / share_friend → `shared`.
2. The intent goes through E1's `guard_v43` and `apply(..., unknown_watch=True, widen_only=True)`.

**Soft direction.** The direction (old or new) comes from one of two places:
- a fixed English lexicon (LOG.md), written without reading any eval text;
- otherwise, a window that the guard dropped. Its midpoint more than a year before 2026-10-30 means old; within the last 120 days means new.

A soft direction is used only when no window survives the guard.

**The time boost.** It is added on the top 300 and scaled to the facet boost: +0.008 · centred u, where u = 1 − percentile of the item's first dated interaction (old), or the percentile of its last dated interaction (new). The guarded filters run after the boost.

### H3: router, calibration and creator gating

**The router** has two multinomial logistic-regression heads over the raw query's 3-large vector, the cached vector H0 already embeds:
- type: topic, creator, behaviour_time, format or vibe;
- platform: ig, yt or both.

**Training data: 2,699 synthetic searches** (prompt syn-v1: gpt-5.4-mini, reasoning `none`).
- There are 15 cells (type × platform), each with 15 calls × 12 searches; 1 exact duplicate was dropped. That gives 180 per cell.
- Each call showed 8 seed items as data, drawn with fixed seeds from non-friend items:
  - Instagram seeds were te summaries, topics, kind, moods and creator, with no raw captions;
  - YouTube seeds were 4 te rows plus 4 title + channel lines.
- The type definitions are abstract, and there are no example searches.
- The split is 80 / 20 stratified by cell, so 540 searches are held out.

**Calibration.** q_ig = p_ig + p_both / 2 and q_yt = p_yt + p_both / 2. Every fused item's score is multiplied by exp(0.5 · (q_{its group} − 0.5)), and the list is re-sorted stably. The group comes from an item attribute through one per-item array; no code branches on a platform name.

**Creator search** fires when the router's argmax type is creator.
- It uses F2's machinery, except:
  - profile vectors are means of the members' 3-large own vectors (the te vectors are 3-small, so they are left out);
  - there is no LLM pick.
- The creator ranking is an RRF of three lists:
  1. dense: [query, qr-v1 phrases];
  2. profile BM25: query + keywords;
  3. creators in order of their best item in the fused list.
- The creator-item list and the coverage-fair fusion are exactly F2's. Calibration runs after that fusion.

### H4: richer creator profiles

H4 fires on qs-v1 `creator_lookup`, F2's trigger.
- **Description.** The qs-v1 description is added to the dense texts and to the BM25 query.
- **Channel-type words in the profile text:**
  - the majority predicted format class, if it is not `other` and covers ≥ 40% of the members;
  - every tone class with mean p ≥ 0.4.
  - 36,166 of the 47,573 creator profiles get such words. Single-item creators often qualify.
- **Era words:** every calendar year from the creator's first to last dated interaction (47,528 creators).
- **Priors on the creator RRF score:**
  - affinity: × (1 + 0.3 · percentile of log interaction count);
  - era: × (1 + 0.3 · e), where e is the creator's last-interaction percentile (or 1 minus it) when the lexicon says new (or old).
- Building both creator indexes takes 13.5–13.8 s.

### H5 / H5b

**H5 runs these steps in order:**
1. H0's own lists.
2. Creator search, if router = creator or qs-v1 says lookup, using H4's profiles and priors.
3. H3 calibration on all fused scores.
4. The H2 facet boost and H1 time boost, added together on the top 300, then one stable re-sort.
5. H1's guarded filters.

**H5b** adds F0's te lists (20,829 rankable rows) as one more coverage-fair group. te dense uses the 3-small vectors of the same query strings, because the te vectors are 3-small. More-like-this searches get F0's te example lists.

## Classifier and router quality (held-out training-side data only)

### Format facet (4,948 held-out rows; C = 4)

| | Accuracy | Macro-F1 |
| --- | --- | --- |
| All | **0.730** | **0.710** |
| Instagram rows (3,762) | 0.730 | 0.713 |
| YouTube rows (1,186) | 0.728 | 0.675 |

- Majority-class accuracy is 0.334. Top-label ECE is **0.016**.
- CV macro-F1 by C: 0.671 (0.25), 0.709 (1), 0.718 (4).

| Class | howto | review | explainer | vlog | comedy | music | motivation | other |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | 0.82 | 0.54 | 0.78 | 0.64 | 0.71 | 0.78 | 0.70 | 0.71 |

**Predicted argmax shares over all items with a vector:**
- Instagram: howto 18%, explainer 12%, comedy 12%, vlog 10%, other 37%.
- YouTube: explainer 19%, comedy 12%, howto 8%, vlog 8%, other 47%.

**Caveat:** YouTube te rows are round 3's gated items (heavily watched, or light/full depth). The YouTube held-out figure is measured on that population, not on all 100k titled videos.

### Tone facet (4,681 held-out rows; C = 4)

The 9 classes are scored at a 0.5 threshold.
- **Macro-F1 0.569**, mean accuracy 0.946. Per platform, macro-F1 is ig 0.553 and yt 0.577.
- CV mean F1 by C: 0.317 (0.25), 0.473 (1), 0.545 (4).

| Class | Positive share | Accuracy | F1 | AUC | Brier | ECE |
| --- | --- | --- | --- | --- | --- | --- |
| funny | 0.252 | 0.884 | 0.759 | 0.939 | 0.083 | 0.010 |
| cute_wholesome | 0.038 | 0.977 | 0.623 | 0.969 | 0.019 | 0.003 |
| serious | 0.056 | 0.955 | 0.457 | 0.929 | 0.035 | 0.004 |
| motivational | 0.079 | 0.951 | 0.624 | 0.949 | 0.039 | 0.008 |
| calm | 0.021 | 0.985 | 0.493 | 0.962 | 0.013 | 0.004 |
| intense | 0.087 | 0.927 | 0.489 | 0.910 | 0.053 | 0.010 |
| nostalgic | 0.043 | 0.966 | 0.472 | 0.952 | 0.024 | 0.010 |
| emotional | 0.023 | 0.981 | 0.411 | 0.956 | 0.014 | 0.006 |
| informative | 0.292 | 0.884 | 0.794 | 0.945 | 0.084 | 0.012 |

- **Ranking quality is high (AUC 0.91–0.97) and calibration is good (ECE ≤ 0.012).** F1 at 0.5 is low for rare tones, because their probabilities rarely pass 0.5.
- The boost uses centred probabilities, not the 0.5 threshold.

### Router (540 held-out synthetic searches)

| Head | C | Accuracy | Macro-F1 | Top-label ECE | Per-class F1 |
| --- | --- | --- | --- | --- | --- |
| type (5) | 1 | **0.680** | 0.683 | 0.142 | topic 0.53, creator 0.70, behaviour_time 0.91, format 0.55, vibe 0.73 |
| platform (3) | 4 | **0.554** | 0.553 | 0.087 | ig 0.59, yt 0.57, both 0.50 |

**Type confusion** (rows = true, columns = predicted; topic, creator, behaviour_time, format, vibe):
- topic 58 / 5 / 0 / 32 / 13;
- creator 16 / 75 / 1 / 9 / 7;
- behaviour_time 2 / 6 / 94 / 5 / 1;
- format 21 / 15 / 2 / 61 / 9;
- vibe 14 / 5 / 2 / 8 / 79.
- Topic and format are the classes most often confused.

**Platform confusion** (rows = true, columns = predicted ig / yt / both):

| True | ig | yt | both |
| --- | --- | --- | --- |
| ig (180) | 106 | 34 | 40 |
| yt (180) | 33 | 105 | 42 |
| both (180) | 41 | 51 | 88 |

- The mean calibration weight for the true group is q = 0.658 on ig searches and 0.643 on yt searches; on both searches, |q − 0.5| is 0.169 on average.
- So the calibration multiplier for the right platform averages about exp(0.5 · 0.15) ≈ 1.08, and the ratio between the two platforms, exp(q − 0.5), about 1.16. On the eval searches each multiplier ranges 0.81–1.27.
- **Caveat:** the platform head is weak. Synthetic platform labels come from which app the seed items were on, and many topics occur on both apps.

**On the eval searches** (method side; the platform scope is read only from the public `ig_` / `yt_` id prefix, as earlier rounds' diagnostics did):
- **Platform argmax:**
  - ig searches (18 typed): ig 12, both 4, yt 2;
  - yt searches (29 typed): yt 10, both 12, **ig 7**.
- **Mean q_ig:** 0.705 on ig searches, 0.446 on yt searches (range 0.08–0.99).
- **Router type over 47 typed searches:**
  - behaviour_time 17, format 12, topic 7, vibe 7, creator 4;
  - it over-predicts behaviour_time against the `kinds` field: time 5, behaviour 4, personal 5.

## How often each part fires (typed search × repeat cells; 141 cells over 47 typed searches)

Rows count a search under every `queries.jsonl` kind it carries (reporting only; no method reads `kinds`).

| Kind (cells) | H1 soft time (lexicon) | H1 filter active | H2 format | H2 tone | H3 router = creator | H3 calibration \|q−0.5\| ≥ 0.25 | H4 creator (qs-v1) | H5 creator (either) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **all (141)** | **30 (6)** | **8** | **22** | **13** | **12** | **54** | **5** | **14** |
| topic (72) | 14 (0) | 3 | 19 | 3 | 6 | 27 | 0 | 6 |
| task (36) | 8 (0) | 1 | 7 | 1 | 0 | 9 | 0 | 0 |
| name (33) | 6 (3) | 0 | 11 | 0 | 3 | 18 | 3 | 3 |
| structure (27) | 5 (0) | 4 | 7 | 0 | 3 | 15 | 0 | 3 |
| vibe (21) | 5 (3) | 0 | 0 | 13 | 0 | 3 | 0 | 0 |
| time (15) | 10 (6) | 3 | 0 | 3 | 0 | 3 | 0 | 0 |
| personal (15) | 8 (3) | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| people (12) | 0 | 3 | 2 | 0 | 6 | 3 | 3 | 6 |
| behaviour (12) | 2 (0) | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| said_shown (9) | 0 | 0 | 0 | 0 | 0 | 3 | 2 | 2 |
| audio (9) | 0 | 0 | 0 | 0 | 3 | 6 | 0 | 3 |
| place (6) | 5 (0) | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| moment (3), shown (3) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**H1, soft time.**
- Of the 30 soft-time cells, **24 come from a window the guard dropped** (new 20, old 4) and **6 from the lexicon** (all old).
- The dropped-window rule fires on topic and task searches too, wherever nano set a date the text does not support.
- Most of those are "new": nano sets recent windows without calendar words.
- The rule was preregistered, but expect H1 to move several non-time searches slightly.

**H1, filters.** The guarded filter changes the ranking in 2–3 searches per repeat, in mode "filter, text order, then pool by interaction weight".

**H2.** The format facets that fired were howto and explainer only. Tone fired on 4–5 searches per repeat, all of them vibe searches (some also carry time or personal): calm+informative, nostalgic(+emotional), informative+intense, motivational / serious + informative.

**H3.**
- Router = creator on the same 4 typed searches in every repeat, because the router is deterministic on the query vector.
- Their creator-item lists hold 396–693 items.
- Calibration makes at least a 1.28× ratio between the platforms (|q − 0.5| ≥ 0.25; the ratio is exp(q_ig − 0.5)) on 18 of 47 searches.

**H4 / H5.** qs-v1 lookup fires on 1–2 searches per repeat. In H5, creator search fires on 4–5 searches per repeat: router alone 3, both 1, qs-v1 alone 0–1.

## Label-free diagnostics (method side only)

| Run | Top 10 differs from `h0` (r1, r2, r3) | Mean top-10 overlap with `h0` | Other platform's share of top 10: `ig_` / `yt_` searches |
| --- | --- | --- | --- |
| h0 (vs `r6/g4`) | 1, 2, 0 | 1.00 | 0.46–0.47 / 0.19–0.21 |
| h1 | 11, 10, 14 | 0.93–0.94 | 0.43–0.46 / 0.17–0.21 |
| h2 | 11, 11, 11 | 0.97 | 0.46–0.47 / 0.19–0.21 |
| h3 | 33, 34, 38 | 0.87–0.89 | **0.34–0.38** / 0.21–0.23 |
| h4 | 1, 2, 2 | 0.99–1.00 | 0.45–0.46 / 0.19–0.22 |
| h5 | 37, 37, 41 | 0.82 | 0.35–0.36 / 0.20–0.24 |
| h5b | 50, 52, 52 | 0.70–0.73 | 0.31–0.34 / **0.26–0.28** |

**Reading:**
- **H3 calibration mostly acts on Instagram searches.** It removes about a fifth of the YouTube items from their top 10.
- It does not reduce Instagram items in YouTube searches, because the router often reads yt searches as both or ig.
- **H5b puts more Instagram items into YouTube searches than H5 does** (0.26–0.28 against 0.20–0.24), as F0 did in round 5. Calibration does not offset the te lists' votes.
- Expect a sizeable unjudged pool for H3, H5 and H5b. They change 33–52 of the 55 top 10s against H0.

## Cost and latency

Typed searches; ranges are over the 3 repeats.
- **Total** = local search + max(qr-v1, qs-v1 where read; original uncached seconds, run in parallel) + one live 3-large query-embedding call.
- That embedding call is measured once per search and repeat and shared by every arm; its vectors are not used.
- The router, calibration, boosts, creator search and the te lists are included in local time.

| Arm | Local p50 / p95 | **Total p50 / p95** | $/1k searches (as run) | $/1k if qs-v1 is merged into the rewrite |
| --- | --- | --- | --- | --- |
| H0 | 0.18–0.19 / 0.20–0.21 s | **1.99–2.04 / 2.56–2.92 s** | $0.131 | — |
| H1 | 0.18–0.19 / 0.21–0.23 s | 1.99–2.04 / 2.55–2.93 s | $0.131 | — |
| H2 | 0.18 / 0.20–0.21 s | 2.62–2.86 / 3.30–3.82 s | $0.294 | $0.131 |
| H3 | 0.18–0.19 / 0.25 s | 1.99–2.05 / 2.56–2.92 s | $0.131 | — |
| H4 | 0.18–0.19 / 0.22–0.25 s | 2.61–2.84 / 3.30–3.83 s | $0.294 | $0.131 |
| H5 | 0.18–0.19 / 0.26–0.27 s | 2.70–2.85 / 3.30–3.82 s | $0.294 | $0.131 |
| H5b | 0.21–0.22 / 0.29–0.30 s | 2.71–2.89 / 3.33–3.88 s | $0.294 (+ te pass $0.18 per 1k caption-type items) | $0.131 |

- **H1 and H3 add no API cost or measurable latency.** The router uses the query vector H0 already embeds.
- H2, H4 and the packages read the qs-v1 slots: +$0.164 per 1k as a second nano call, and +0.6–0.9 s at p50, because qs-v1's calls are slower than qr-v1's.
  - If its few fields were merged into the qr-v1 call, these arms would cost as H0, plus some output tokens.
  - That is an estimate, not measured here.
- H5's local p95 rises by +0.06 s, from the creator search and the calibration sort over the full fused list. H5b adds +0.03 s for the te lists.
- **Index build:** H0 14.8–19.1 s, plus creators 13.5–13.8 s and the te index, for 33–40 s in all. Facet probabilities and models load from `r7/`.

**One-off costs:**

| Step | Calls / items | Cost |
| --- | --- | --- |
| syn-v1 synthetic searches (gpt-5.4-mini; pilot 3 + 222 calls) | 225 | $0.2545 |
| 3-large vectors of the 2,699 synthetic searches and new query strings | 9 calls | $0.0022 |
| Live query-embedding timing calls (3 × 47) | 141 | $0.0017 |
| Facet and router training, inference, all search runs | local | $0 |
| **Round 7 total** | | **$0.258** |

- OpenAI is now **$2.882 of $9.50**, leaving $6.62. Gemini is unchanged at $3.776; the ledger total is $6.657.
- The round cap was $4.62 (start $2.623 + $2.00).

## Comparisons the runs support

| Comparison | What it measures |
| --- | --- |
| H0 − C0 (`r7/h0` vs `r4.2/c0x`) | 3-large, rebuilt (≈ G4) |
| H1 − H0 | the rewrite's own filters (guarded) + soft time |
| H2 − H0 | facet classifiers as soft boosts on format / tone searches (fires on 11–12 searches) |
| H3 − H0 | router: platform calibration + creator gating (all typed searches) |
| H4 − H0 | richer creator profiles on qs-v1 lookup searches (1–2 searches) |
| H5 − H0, H5 − C0 | the package |
| H5b − H5 | te lists for caption-type items on top of the package |

**test2 / yt_holdout.**
- The brief spends test2's last scoring on the better of H5 / H5b on dev, with C0 and H0.
- test2 runs need C0's test2 qr-v1 parses (they exist in `runs/final2/`), fresh qs-v1 parses (≈ $0.01) and 3-large vectors of the strings (≈ $0.001). The orchestrator arranges these, because builders never see test2.
- `c7_search.py --queries FILE --rewrites-dir DIR --outdir DIR --suffix _test2 --ref RUN_{rep}.json` mirrors the round-6 CLI.
- `yt_holdout` runs already exist in every file.

## Deviations and rule notes (honest record)

1. **H0 does not reproduce `r6/g4` exactly** (recorded in LOG.md before any H run).
   - The round-7 runner matches 6, 10 and 8 of 55 rankings at 1,000 deep. The top 10 differs in 1, 2 and 0 searches.
   - Round 6's own `c6_search.py --configs g4`, re-run today, gives exactly the round-7 rankings (55/55). It too differs from `r6/g4` (13/55).
   - Probable cause: round 6 ran with query vectors held in float32 right after embedding them, while the store keeps float16 and was rewritten after `g4_r1`.
   - So **H0 = `r7/h0_r*`**. Every H arm is paired against it, and C0 stays `r4.2/c0x_r*`.
2. **H6 was skipped**: the PyTorch install did not go through cleanly (above).
3. **No new LLM labels for the facets.** This was preregistered, so the YouTube held-out figure covers the gated te population only.
4. **Router seeds include raw YouTube titles and channel names** (public titles), as preregistered. Instagram seeds used te summaries only, and friends' items were never sent.
5. **Slips:**
   - I wrote my own LOG block draft to a scratch file under `/tmp/claude-0/…/scratchpad/` and read it back once to insert it into LOG.md. It was my own preregistration text, but the rule says to read nothing under `/tmp/claude-0/` except the key file.
   - A background pip install wrote its log there; it was not read.
   - Later scratch went to `data/all/tmp/r7/`.
6. **Not seen:**
   - No labels, `eval_work/`, `runs/final*/` or `runs/rewrites/test*/`, and no per-search scores.
   - No eval search text was printed, written or used in any prompt, lexicon or training set.
   - The time lexicon was written from general English. BRIEF-5's category table names one of its phrases as an example of a behaviour / time phrase; it is a common phrase and was not looked up in any search.
   - The synthetic prompt has no example searches.
7. **Scratch and caches** (gitignored):
   - `data/all/r7/`: models, probabilities, synthetic searches, quality and fire-count JSON, embedding timings;
   - `data/all/cache/r7/` and `data/all/tmp/r7_checks/`;
   - `data/all/runs/r7_run.log`.
