# Round 9 setup (evaluator): Derrick's sets, facet_real and the two-judge harness

Written 9 Nov 2026 by the round-9 evaluator (setup role), which built no method. This file holds aggregates only. Per-item data lives under `data/all/evals/labels/` and `data/all/eval_work/r9/`, both gitignored.

Scripts:
- `experiments/eval/build_r9_sets.py` (idempotent) builds the sets.
- `experiments/eval/judges9.py` is the two-judge harness.

Before anything changed, these were backed up as `*.pre_r9.0.*`: `labels/evalset.jsonl`, `queries.jsonl` and `split.json`.

## 1. Intent updates

- **The two `intent_updates` were not in `evalset.jsonl` yet.** BRIEF-9 says they were; it was wrong. Both searches had an empty or missing `intent`.
- Both are now applied: appended to `intent`, and a second build run applies nothing new.
- Judges see `intent` as the MEANING line, so 6 of the 72 calibration items now carry a clarification Derrick wrote after grading them. κ without those 6 items is reported below.

## 2. ig_real (31 searches, 32 targets, scope `ig`)

| Slice (`search_kind`) | Searches | Scoring (BRIEF-9) | MDE at median sd_d 0.117 |
| --- | --- | --- | --- |
| known_item | 8 | mrr2 / s10_2 on the target | ≈ 0.14 |
| topic | 22 | target = 3, pool-judge the rest; nDCG@10 | ≈ 0.07 |
| meta | 1 | target = 3, pool-judge the rest (intent says instances) | n/a (one search) |
| all | 31 | | ≈ 0.06 |

Notes:
- 6 searches carry the note "caption was revealed before writing". One search has two targets.
- **Files:**
  - the seed labels (Derrick's only) are in `labels/ig_real.jsonl`;
  - the same rows are in `labels/evalset.jsonl`, which is where pooled grades get merged;
  - the texts are hidden in `labels/ig_real_queries.jsonl`, like `known_test`;
  - split `ig_real` is in `split.json`.
- **Grades:**
  - Rows use the 4-point scale; the field is `grade_scale`.
  - Each target is 3, because Derrick wrote the search for that post (it was 2 on his 3-point sheet).
  - mrr2 / s10_2 count grade ≥ 2, so the known-item slice is unaffected.
- **Hygiene:** no hidden text (ig_real or facet_test) appears in `queries.jsonl` or in any of the 51 method-side query or rewrite cache files checked.

## 3. facet_real (from the round-9 search sheet)

- **Sheet:** 40 items in total. 9 were skipped, leaving 31 searches (17 Instagram, 14 YouTube). Every kept item has exactly one search line; none has two.
- **Labels:**
  - target = 3;
  - `specificity` = want: 6 `exact` and 25 `like`;
  - `facets` = `based_on`;
  - one item has no facet ticked;
  - no caption was revealed.
- **Split:** by item, stratified by the rarest ticked facet, seed 9, alternating within strata (platforms interleaved).

| | n | Platform | want exact / like | Facet ticks |
| --- | --- | --- | --- | --- |
| **facet_dev** (ids `fdv00`–`fdv15`) | 16 | 8 IG / 8 YT | 3 / 13 | topic 13, type 11, looks 7, examples 6, creator 5, sound 1 (1 unticked) |
| **facet_test** (ids `fts00`–`fts14`) | 15 | 9 IG / 6 YT | 3 / 12 | type 13, topic 12, looks 6, examples 5, creator 3, sound 1, tone 1 |

- No search was ticked `said`, `when` or `other`. `tone` occurs once (test only).
- **Visibility:**
  - facet_dev texts are method-side in `queries.jsonl`, with `kinds` = the ticked facets only. `want`, `specificity` and the strata stay evaluator-side.
  - facet_test texts are hidden in `labels/facet_test_queries.jsonl`.
- **Labels:** the working labels are in `labels/evalset.jsonl` (rows carry `grade_scale`, `specificity` and `facets`). The seed copy is in `labels/facet_real.jsonl`.
- **MDE at median sd_d:** about 0.09 on either half. Per-facet cells below about 6 searches are descriptive only.

## 4. Two-judge harness (A-005), fixed before any call

**Judges:**
- **A = gpt-5.4-mini** (OpenAI), reasoning effort low, strict JSON schema.
- **B = gemini-3-flash-preview** (Google), thinking level low, JSON schema.
- Prices are already in `lib/ai_prices.json`: gpt-5.4-mini checked 7 Nov, gemini-3-flash-preview checked 30 Oct. No new price was added.
- Neither model is used by a current method or by the ig_known writer.
- **Caveat:** gpt-5.4-mini wrote round 7's synthetic router training searches (`syn-v1`), and that router's text guess feeds Q8's prior-p1. The self-preference risk is indirect and small, but it is recorded here.

**Combination rule (fixed up front):**
- both agree → that grade;
- they disagree → the lower grade;
- sensitivity = the higher grade;
- only one judge graded → that judge's grade.

**Rubric `j9-v1`:**
- the 4-point scale (0 wrong / 1 related / 2 good / 3 exactly meant);
- the person's MEANING (`intent`) overrides a literal reading;
- wrapper words are not the subject;
- **instance vs about**: when a search asks for examples of a kind or quality, content about that kind is at most 1;
- a named kind of item on the right subject but of the wrong kind is at most 1;
- judge from the text shown, with a thin-text rule;
- item text is untrusted data inside `<item>` tags.

**Sheet and calls:**
- Each item shows caption or title (≤ 400 characters), hashtags, creator and format (Instagram reel/post; YouTube duration). It does not show te summaries, so judging does not favour te-based methods; round 8 did the same.
- Each call holds up to 8 items of one search. Outputs are cached per model and rubric.
- Commands: `judge` → `combine` → `report` (disagreements) → `merge`.
- `merge` writes 4-point grades as they are on 4-point rows. On old 3-point rows it writes the collapsed grade to `relevant` and the 4-point grade to `relevant4`. It never overwrites an existing grade.

## 5. Calibration: both judges on Derrick's 72 items, rubric j9-v1 (one run, no revision needed)

Mapping: judge grades 3 and 2 → 2, 1 → 1, 0 → 0. Derrick's grades are used as given. Brackets are bootstrap 95% CIs.

| Judge | Exact | κ 3-grade | κ linear | κ relevant vs not | κ rel., Instagram | κ rel., YouTube | κ rel., excluding 6 intent-updated items | Mean grade (Derrick 1.01) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A gpt-5.4-mini | 0.58 | 0.37 [0.20, 0.54] | 0.43 | **0.60** [0.39, 0.80] | 0.60 | 0.58 | 0.65 | 1.15 |
| B gemini-3-flash-preview | 0.53 | 0.28 [0.11, 0.46] | 0.37 | **0.45** [0.21, 0.66] | **0.34** | 0.51 | 0.48 | 1.21 |
| Combined, lower (primary) | 0.56 | 0.32 [0.15, 0.50] | 0.39 | 0.55 [0.32, 0.75] | 0.47 | 0.58 | 0.59 | 1.04 |
| Combined, higher (sensitivity) | 0.56 | 0.33 [0.16, 0.49] | 0.41 | 0.51 [0.29, 0.72] | 0.47 | 0.51 | 0.55 | 1.32 |
| Round-8 single judge (as given) | 0.61 | 0.42 [0.25, 0.58] | 0.51 | 0.55 [0.34, 0.73] | 0.47 | 0.60 | 0.59 | 1.00 |

**Rubric check.**
- Both judges clear κ 0.40 on relevant vs not overall, so the rubric was not revised. No second run was made, so the rubric was not tuned on these 72 items.
- Judge B falls below 0.40 on the Instagram slice (0.34). Instagram grades should therefore be read through the combined grade and the seed-only sensitivity.

**What the numbers show.**
- **Fewer exact matches on three grades:** both new judges agree with Derrick less often than the round-8 judge (κ 0.37 / 0.28 vs 0.42).
- **Lenient:** both new judges grade higher than Derrick (mean 1.15 / 1.21 vs 1.01). The lower-grade rule cancels most of this (1.04).
- **Spread-out errors:** most disagreements are one step apart. Derrick's 2s are often a judge 1, and his 1s are often a judge 2 or 3.
- **Alternative mapping (descriptive):** mapping judge 2 to 1 and 3 to 2 is worse for both judges (κ 3-grade 0.31 / 0.21).

**Judge A vs judge B (4-point):**
- exact 69%; κ 0.57, linear 0.70;
- 50 of 72 agree, 21 are one step apart, 1 is two steps apart;
- collapsed to 3 points: κ 0.59, relevant vs not 0.73.

**Reading:** two judges plus the lower-grade rule match the round-8 single judge on relevant vs not (0.55). They do not beat it on three grades. Treat pooled AI grades as noisy; the seed-only and grade-1→0 sensitivity analyses stay required.

## 6. Flags for the orchestrator

- **The scorer's gains are not the brief's.** `score_c4.py` computes nDCG with gains 2^g − 1, so a grade-3 target counts 7. BRIEF-9 asks for gains 0/1/2/3 and a collapsed 3-point version. The scorer needs an option for both before Phase 0 scores `ig_real` or `facet_*`.
- **The brief was wrong about the intent updates:** they had not been applied (see section 1).
- **Facet coverage is thin:** facet_real has no `said` or `when` search and only one `tone` search. Those facets need `dev` + `known_dev` tagging (Phase A).

## Spend

| Provider | Model | Calls | Cost |
| --- | --- | --- | --- |
| OpenAI | gpt-5.4-mini | 33 | $0.042 |
| Gemini | gemini-3-flash-preview | 33 | $0.019 |
| **Total** | | | **$0.061** |

Ledger after setup: OpenAI $4.735 of the $9.70 cap, Gemini $3.896 of the $6.88 cap.
