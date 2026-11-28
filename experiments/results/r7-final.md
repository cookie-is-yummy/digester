# Round 7 · final held-out (`test2` 3 of 3, `yt_holdout` 3 of 3) · evaluator report

*7 Nov 2026 · Final held-out evaluator (did not build any method) · label round **c4-f7** · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. test2 searches are referred to by `g`-number, scope and kind; `yt_holdout` searches by kind only.*

**Scorings used by this report:** `test2` scoring **3 of 3** and `yt_holdout` scoring **3 of 3**. **Both sets are now used up.** `test` (2 left) and dev were not scored.

Four frozen methods were scored once per set, after pooling and blind judging:
- **C0**, the finalist;
- **H0** = G4 (C0 with text-embedding-3-large 1,024 d). Its test2 top 10s equal round 6's G4 in all 30 cells;
- **H5**, the package H0 + H1 + H2 + H3 + H4 (the fallback);
- **H5b**, H5 + te lists for caption-type items (**the preregistered package**, better of H5 / H5b on dev).

No run or method file was touched. Code: `experiments/eval/score_c4.py`, unchanged. The sheet builder, analysis script, sheets, calibration samples, grades and per-search detail are in `data/all/eval_work/final7/` (gitignored). Aggregates are in `r7-final.json`.

## Bottom line

| | test2 (10: 4 yt, 6 both) | yt_holdout (11, all yt) | Both sets (21) |
|---|---|---|---|
| Levels C0 / H0 / H5 / **H5b** | 0.448 / 0.501 / 0.519 / **0.538** | 0.388 / 0.445 / **0.470** / 0.450 | — |
| **H5b vs C0** | **+0.089 [+0.022, +0.174], 8/1/1** | +0.061 [−0.005, +0.126], 7/3/1 | **+0.075 [+0.026, +0.128], 15/4/2** |
| H5 vs C0 | +0.070 [+0.006, +0.155], 7/2/1 | +0.081 [−0.001, +0.162], 8/2/1 | **+0.076 [+0.022, +0.135], 15/4/2** |
| **H0 vs C0** | +0.053 [−0.001, +0.134], 7/2/1 (= round 6) | **+0.056 [+0.003, +0.119], 8/2/1** | **+0.055 [+0.013, +0.103], 15/4/2** |
| **H5b vs H0** | **+0.036 [+0.007, +0.069], 6/1/3** | +0.005 [−0.037, +0.047], 6/4/1 | +0.020 [−0.008, +0.047], 12/5/4 |
| H5 vs H0 | +0.017 [−0.016, +0.051], 5/3/2 | +0.025 [−0.015, +0.072], 5/3/3 | +0.021 [−0.006, +0.051], 10/6/5 |
| H5b vs H5 | +0.019 [−0.010, +0.059], 5/1/4 | −0.020 [−0.046, +0.008], 2/6/3 | −0.001 [−0.023, +0.024], 7/7/7 |

- **3-large (H0) is now confirmed on a second held-out set.** On `yt_holdout` it is +0.056 with the CI above 0 (lower bound > 0 on 19 of 20 seeds), 8/2, and the same on the round-3 seed labels (+0.058 [+0.002, +0.124], 7/3). Over all 21 held-out searches it is +0.055 [+0.013, +0.103], 15/4, lower bound > 0 on 20/20 seeds and still +0.019 with the best 3 searches dropped. The test2 half of that is round 6's number reused (the H0 top 10s are G4's), so the new evidence is the `yt_holdout` half.
- **Both packages beat C0 on held-out, more than H0 does,** and both pass clause 1 on the 21 searches pooled (H5 +0.076, H5b +0.075; lower bounds > 0 on 20/20 seeds; still +0.034 / +0.041 with the best 3 dropped).
- **What the packages add on top of 3-large is not established.** Against H0: H5b +0.020, H5 +0.021 over 21 searches, both with the CI spanning 0 (lower bound −0.008 / −0.006), on dev +0.012 / +0.006. On Derrick's own test2 marks H5b vs H0 is +0.030 [+0.002, +0.065], but on `yt_holdout` it is +0.005 (seed −0.015).
- **The te lists (H5b − H5) repeat their dev trade exactly:** they help `both` searches (test2 both +0.032, 2/0) and cost YouTube searches (`yt_holdout` −0.020, 2/6; seed −0.017, 0/5, CI below 0). Net over 21 searches: −0.001, 7/7.
- **The preregistered risk did not materialise on test2.** H5b was expected to lose to H0 on test2's `yt` searches; it gained (+0.048, 3/0/1), because the router read 3 of the 4 `yt` searches as YouTube and none as Instagram. On `yt_holdout` the router read 2 of 9 typed searches as Instagram, and there the packages lose to H0 (H5 −0.064, H5b −0.083 per search), as on dev.
- **Recommendation: adopt H0 (3-large) as the new processor now. Do not adopt H5b. Keep H5, not H5b, as the package candidate,** pared down and with qs-v1 merged into the rewrite call, until a fresh held-out set settles its increment over H0 (section "Recommendation").

## Method

- **Runs** (all 3 repeats, read through symlinks in `eval_work/final7/runs_{t2,yth}/`):
  - test2: C0 `final2/c0x_test2_r*`; H0 / H5 / H5b `final4/{h0,h5,h5b}_test2_r*`. All 12 files cover the 10 searches at depth 1,000. Their meta names C0's nano test2 parses (`qr-v1_gpt-5-nano_r{k}`); H5 / H5b also read nano qs-v1 test2 parses (`qs-v1_gpt-5-nano_r{k}`).
  - `yt_holdout`: C0 `r4.2/c0x_r*`; H0 / H5 / H5b `r7/{h0,h5,h5b}_r*`, restricted to the 11 `yt_holdout` searches (9 typed, 2 more-like-this).
  - H0's test2 top 10 equals round 6's `final3/g4_test2_r*` in all 30 cells (the deep tail differs, as `r7-methods.md` explains).
- **Conventions**, as in `r6-test2.md` and `r5-test2.md`:
  - each search's metrics are the mean over 3 repeats; comparisons pair repeat k with repeat k;
  - CIs are 2,000-sample bootstraps over searches (seed 0 for levels, seed 1 for Δ); robustness uses 20 seeds × 10k samples;
  - W/L/T uses |Δ| > 0.005; per-kind rows count a search under every kind it has.
  - "Both sets (21)" concatenates the per-search Δs of the two sets and bootstraps over the 21 searches.
- **Labels.**
  - **Seed labels.** test2: Derrick's own marks (`evalset.pre_test2.jsonl`). `yt_holdout`: round 3's labels (`evalset.pre_milestone.jsonl`), the set's labels before any combined-root pooling. Pooled = c4-f7.
  - Derrick's `relevant` grades and `judged_nonrelevant` zeros are gold and were not touched; `unvetted_candidates` were treated as unjudged. After the merge, 0 earlier grades, 0 gold zeros and 0 non-held-out rows differ from the backup.
  - Backup: `evalset.pre_final7.jsonl`. Merged with `judge.py merge`, judge `claude-evaluator-final7`.
- **Pool.** Every unjudged top-10 item of the four methods over 3 repeats, cross-platform items included.
  - **test2: 18 items over 6 searches** (g01, g03, g04, g06, g07, g10). 12 were surfaced only by H5, 4 only by H5b, 2 by both; 5 were `unvetted_candidates`. Rounds 5 and 6 had already judged everything C0 and H0 surface. Seed unjudged@10 before pooling: H5 0.05, H5b 0.02, C0 / H0 0.00.
  - **`yt_holdout`: 58 items over 9 searches,** 22 of them Instagram items. Unjudged@10 before pooling: H0 0.16, H5 0.19, H5b 0.15, C0 0.00. (This set was last pooled at the milestone, before 3-large existed.)
  - The pool step ran the scorer with `--pool` on the pre-pool labels, as the protocol does. The one scoring of record per set is the pooled one below.
- **Blind judging, $0, no paid judge.**
  - Sheets built with a copy of the test2b / milestone builder: grouped by search, shuffled within each search, no run, rank or vetted status; the item's own text, interactions and duration; no te text.
  - **Calibration first.** test2: for each pooled search, up to 10 of Derrick's 2s, 10 of his 1s and his 0s, then up to 5 per grade of the earlier test2 evaluators' grades. `yt_holdout`: up to 8 per grade of round 3's labels and up to 5 per grade of the milestone evaluator's.
  - **Conventions kept** (from `r5-test2.md` / `r6-test2.md` and the milestone):
    - g01, g03 and g06: 2 only for the core of the intent; on-topic items without the stated structure or depth (including short clips) 1;
    - g04: the target's own related items 1, same-topic items by others 0;
    - g07 and g10: lenient for broad matches to the intent, but the kinds the intent explicitly excludes are 0;
    - `yt_holdout`: shorts lose a grade where the intent rules them out; same-topic non-target items on name and more-like-this searches 0; the behaviour search graded by its stated rule (saved, never watched, ≥ 20 min = 2, 10–20 min = 1).
  - **Grades:** test2 **6 / 6 / 6** (2 / 1 / 0; YouTube 5/4/5, Instagram 1/2/1); `yt_holdout` **5 / 7 / 46** (YouTube 3/5/28, Instagram 2/2/18).
- **Whose grades the scores rest on.** test2: Derrick's marks cover 33–38% of the relevant top-10 items, this round's 0–5%. `yt_holdout`: round 3's labels cover 70–75%, this round's 0–8%. Both results therefore rest mostly on earlier labels.

## Scores (mean of 3 repeats; spread = max − min over repeats)

### test2 (10 searches: 4 `yt`, 6 `both`)

| Method | Scope (n) | **nDCG@10 pooled** [95% CI] (spread) | nDCG@10 seed (spread) | P@10 pooled / seed (pooled spread) | MRR pooled / seed (pooled spread) | R@10 pooled |
|---|---|---|---|---|---|---|
| **C0** | all (10) | **0.448** [0.303, 0.603] (0.025) | 0.180 (0.002) | 0.633 / 0.210 (0.010) | 0.714 / 0.351 (0.130) | 0.129 |
| | yt (4) | 0.301 (0.046) | 0.127 (0.032) | 0.475 / 0.142 (0.100) | 0.572 / 0.229 (0.208) | 0.093 |
| | both (6) | 0.547 (0.072) | 0.215 (0.022) | 0.739 / 0.256 (0.050) | 0.808 / 0.433 (0.084) | 0.153 |
| **H0** | all (10) | **0.501** [0.345, 0.657] (0.064) | 0.202 (0.019) | 0.690 / 0.240 (0.040) | 0.726 / 0.402 (0.017) | 0.137 |
| | yt (4) | 0.410 (0.129) | 0.159 (0.030) | 0.567 / 0.183 (0.100) | 0.562 / 0.329 (0.042) | 0.105 |
| | both (6) | 0.562 (0.070) | 0.231 (0.052) | 0.772 / 0.278 (0.033) | 0.835 / 0.450 (0.002) | 0.159 |
| **H5** | all (10) | **0.519** [0.368, 0.667] (0.054) | 0.217 (0.003) | 0.707 / 0.257 (0.040) | 0.745 / 0.409 (0.040) | 0.142 |
| | yt (4) | 0.458 (0.032) | 0.183 (0.050) | 0.642 / 0.225 (0.025) | 0.604 / 0.346 (0.104) | 0.124 |
| | both (6) | 0.559 (0.084) | 0.240 (0.039) | 0.750 / 0.278 (0.067) | 0.838 / 0.451 (0.007) | 0.154 |
| **H5b** | all (10) | **0.538** [0.377, 0.697] (0.059) | 0.232 (0.011) | 0.717 / 0.270 (0.040) | 0.731 / 0.401 (0.014) | 0.145 |
| | yt (4) | 0.458 (0.095) | 0.191 (0.025) | 0.633 / 0.242 (0.100) | 0.572 / 0.325 (0.033) | 0.124 |
| | both (6) | 0.591 (0.068) | 0.259 (0.024) | 0.772 / 0.289 (0.017) | 0.837 / 0.452 (0.004) | 0.159 |

- C0 and H0 reproduce their round-6 test2 levels exactly (0.448, 0.501): no pooled item came from their top 10s.
- Every method still scores 0 on g05 (both · name/time).

### yt_holdout (11 searches, all `yt`; 9 typed, 2 more-like-this)

| Method | **nDCG@10 pooled** [95% CI] (spread) | nDCG@10 seed (spread) | P@10 pooled / seed (spread) | MRR pooled / seed (spread) | R@10 pooled | Instagram share of top 10 |
|---|---|---|---|---|---|---|
| **C0** | **0.388** [0.203, 0.568] (0.014) | 0.303 (0.031) | 0.464 / 0.330 (0.036) | 0.667 / 0.531 (0.061) | 0.082 | 0.36 |
| **H0** | **0.445** [0.247, 0.632] (0.050) | 0.361 (0.022) | 0.524 / 0.391 (0.036) | 0.749 / 0.626 (0.069) | 0.079 | 0.28 |
| **H5** | **0.470** [0.271, 0.657] (0.032) | 0.364 (0.042) | 0.539 / 0.388 (0.009) | 0.771 / 0.611 (0.070) | 0.076 | 0.33 |
| **H5b** | **0.450** [0.262, 0.632] (0.051) | 0.346 (0.045) | 0.530 / 0.370 (0.036) | 0.728 / 0.604 (0.125) | 0.082 | 0.36 |

- C0 reproduces its milestone `yt_holdout` score exactly (0.388).
- Repeat levels (nDCG@10 pooled, r1 / r2 / r3): C0 0.387 / 0.382 / 0.396; H0 0.446 / 0.419 / 0.469; H5 0.478 / 0.449 / 0.481; H5b 0.456 / 0.421 / 0.472. test2: C0 0.452 / 0.459 / 0.434; H0 0.543 / 0.479 / 0.482; H5 0.552 / 0.505 / 0.498; H5b 0.576 / 0.517 / 0.520.

## Comparisons (paired)

| Comparison | Set (n) | **Δ nDCG@10 pooled** [95% CI] | W/L/T | Per repeat | Δ P@10 | Δ MRR | **Seed-only Δ** [CI], W/L/T |
|---|---|---|---|---|---|---|---|
| **H5b vs C0** | test2 (10) | **+0.089 [+0.022, +0.174]** | 8/1/1 | +0.124, +0.058, +0.086 | +0.083 | +0.017 | **+0.052 [+0.017, +0.095]**, 8/1/1 |
| | · yt (4) / both (6) | +0.157 [+0.067, +0.326] / +0.044 [−0.015, +0.107] | 4/0/0 · 4/1/1 | | | | |
| | yt_holdout (11) | +0.061 [−0.005, +0.126] | 7/3/1 | +0.069, +0.039, +0.076 | +0.067 | +0.061 | +0.044 [−0.044, +0.123], 6/4/1 |
| | **both sets (21)** | **+0.075 [+0.026, +0.128]** | **15/4/2** | | | | +0.048 [−0.002, +0.094], 14/5 |
| **H5 vs C0** | test2 | **+0.070 [+0.006, +0.155]** | 7/2/1 | +0.100, +0.046, +0.064 | +0.073 | +0.031 | **+0.037 [+0.014, +0.065]**, 7/0/3 |
| | · yt / both | +0.157 [+0.049, +0.316] / +0.012 [−0.028, +0.055] | 4/0/0 · 3/2/1 | | | | |
| | yt_holdout | +0.081 [−0.001, +0.162] | 8/2/1 | +0.092, +0.067, +0.085 | +0.076 | +0.103 | +0.061 [−0.029, +0.149], 6/4/1 |
| | **both sets** | **+0.076 [+0.022, +0.135]** | **15/4/2** | | | | +0.050 [+0.001, +0.099], 13/4 |
| **H0 vs C0** | test2 | +0.053 [−0.001, +0.134] | 7/2/1 | +0.091, +0.020, +0.048 | +0.057 | +0.012 | +0.022 [−0.013, +0.056], 7/2/1 |
| | · yt / both | +0.109 / +0.015 | 3/1/0 · 4/1/1 | | | | |
| | yt_holdout | **+0.056 [+0.003, +0.119]** | **8/2/1** | +0.060, +0.037, +0.072 | +0.061 | +0.081 | **+0.058 [+0.002, +0.124]**, 7/3/1 |
| | **both sets** | **+0.055 [+0.013, +0.103]** | **15/4/2** | | | | +0.041 [+0.006, +0.079], 14/5 |
| **H5b vs H0** | test2 | **+0.036 [+0.007, +0.069]** | 6/1/3 | +0.033, +0.038, +0.038 | +0.027 | +0.005 | +0.030 [+0.002, +0.065], 5/1/4 |
| | · yt / both | +0.048 [+0.006, +0.105] / +0.029 [−0.008, +0.067] | 3/0/1 · 3/1/2 | | | | |
| | yt_holdout | +0.005 [−0.037, +0.047] | 6/4/1 | +0.010, +0.002, +0.003 | +0.006 | −0.020 | −0.015 [−0.086, +0.046], 5/5/1 |
| | both sets | +0.020 [−0.008, +0.047] | 12/5/4 | | | | +0.007 [−0.033, +0.043], 10/6 |
| **H5 vs H0** | test2 | +0.017 [−0.016, +0.051] | 5/3/2 | +0.010, +0.026, +0.016 | +0.017 | +0.019 | +0.015 [−0.004, +0.038], 4/2/4 |
| | · yt / both | +0.048 [−0.005, +0.101] / −0.003 [−0.040, +0.034] | 3/1/0 · 2/2/2 | | | | |
| | yt_holdout | +0.025 [−0.015, +0.072] | 5/3/3 | +0.032, +0.030, +0.012 | +0.015 | +0.022 | +0.003 [−0.070, +0.065], 5/3/3 |
| | both sets | +0.021 [−0.006, +0.051] | 10/6/5 | | | | +0.009 [−0.029, +0.044], 9/5 |
| H5b vs H5 | test2 | +0.019 [−0.010, +0.059] | 5/1/4 | +0.023, +0.012, +0.022 | +0.010 | −0.014 | +0.015 [−0.009, +0.046], 5/2/3 |
| | · yt / both | −0.000 / **+0.032 [0.000, +0.090]** | 3/1/0 · 2/0/4 | | | | |
| | yt_holdout | −0.020 [−0.046, +0.008] | **2/6/3** | −0.022, −0.028, −0.009 | −0.009 | −0.043 | **−0.017 [−0.034, −0.004]**, 0/5/6 |
| | both sets | −0.001 [−0.023, +0.024] | 7/7/7 | | | | −0.002, 5/7 |

### Robustness (pooled; 20 seeds × 10k samples)

| Comparison | Set | Δ | Lower bound range (seeds > 0) | Drop best 1 / 2 / 3 | Best / top-3 share of net | All 9 repeat pairings |
|---|---|---|---|---|---|---|
| H5b vs C0 | test2 | +0.089 | +0.022 to +0.024 (20/20) | +0.053 / +0.040 / +0.031 | 46% / 76% | +0.058 to +0.142 |
| | yt_holdout | +0.061 | −0.007 to −0.003 (0/20) | +0.046 / +0.028 / +0.007 | 32% / 92% | +0.025 to +0.090 |
| | both sets | +0.075 | +0.025 to +0.027 (20/20) | +0.058 / +0.050 / +0.041 | 26% / 53% | |
| H5 vs C0 | test2 | +0.070 | +0.005 to +0.007 (20/20) | +0.033 / +0.021 / +0.011 | 57% / 89% | +0.039 to +0.118 |
| | yt_holdout | +0.081 | −0.005 to 0.000 (0/20) | +0.059 / +0.034 / +0.013 | 34% / 89% | +0.053 to +0.099 |
| | both sets | +0.076 | +0.020 to +0.022 (20/20) | +0.060 / +0.047 / +0.034 | 25% / 62% | |
| H0 vs C0 | test2 | +0.053 | −0.001 to 0.000 (0/20) | +0.017 / +0.010 / +0.003 | 72% / 96% | +0.020 to +0.109 |
| | yt_holdout | +0.056 | 0.000 to +0.003 (19/20) | +0.032 / +0.021 / +0.013 | 48% / 84% | +0.023 to +0.086 |
| | both sets | +0.055 | +0.013 to +0.014 (20/20) | +0.038 / +0.025 / +0.019 | 33% / 70% | |
| H5b vs H0 | test2 | +0.036 | +0.006 to +0.007 (20/20) | +0.026 / +0.017 / +0.010 | 36% / 81% | −0.025 to +0.097 |
| | yt_holdout | +0.005 | −0.038 to −0.035 (0/20) | −0.008 / −0.016 / −0.027 | — | −0.048 to +0.053 |
| | both sets | +0.020 | −0.008 to −0.007 (0/20) | +0.014 / +0.008 / +0.003 | 31% / 86% | |
| H5 vs H0 | test2 | +0.017 | −0.018 to −0.017 (0/20) | +0.007 / −0.004 / −0.012 | 62% / 148% | −0.045 to +0.073 |
| | yt_holdout | +0.025 | −0.017 to −0.015 (0/20) | +0.007 / −0.001 / −0.012 | 73% / 134% | −0.019 to +0.062 |
| | both sets | +0.021 | −0.007 to −0.005 (0/20) | +0.012 / +0.007 / +0.003 | 45% / 90% | |
| H5b vs H5 | both sets | −0.001 | −0.024 to −0.023 (0/20) | −0.010 / −0.014 / −0.017 | — | |

- Every repeat is positive for every comparison against C0 on both sets.
- Against H0, the packages' gains are carried by few searches: drop the best 3 and +0.003 is left for either package over 21 searches.

### Grade sensitivity (this round's 76 grades only)

| Variant | H5b vs C0 (test2 / yth / 21) | H5 vs C0 | H0 vs C0 | H5b vs H0 | H5 vs H0 | H5b vs H5 |
|---|---|---|---|---|---|---|
| Pooled, as judged | +0.089 / +0.061 / +0.075 | +0.070 / +0.081 / +0.076 | +0.053 / +0.056 / +0.055 | +0.036 / +0.005 / +0.020 | +0.017 / +0.025 / +0.021 | +0.019 / −0.020 / −0.001 |
| This round's 1s → 0 | +0.087 / +0.056 / +0.071 | +0.067 / +0.074 / +0.071 | +0.053 / +0.051 / +0.052 | +0.034 / +0.005 / +0.019 | +0.014 / +0.022 / +0.019 | +0.020 / −0.018 / 0.000 |
| This round's 2s → 1 | +0.085 / +0.057 / +0.070 | +0.061 / +0.072 / +0.067 | +0.053 / +0.053 / +0.053 | +0.032 / +0.004 / +0.017 | +0.008 / +0.019 / +0.014 | +0.024 / −0.015 / +0.004 |
| This round's items → 0 (pre-pool) | +0.080 / +0.050 | +0.053 / +0.061 | +0.053 / +0.047 | +0.027 / +0.003 | 0.000 / +0.014 | +0.027 / −0.011 |
| Seed only | +0.052 / +0.044 / +0.048 | +0.037 / +0.061 / +0.050 | +0.022 / +0.058 / +0.041 | +0.030 / −0.015 / +0.007 | +0.015 / +0.003 / +0.009 | +0.015 / −0.017 / −0.002 |

- Signs hold under every variant except for near-zero comparisons: H5b vs H0 on `yt_holdout` (+0.005 pooled, −0.015 seed) and H5b vs H5 over 21 (−0.002 to +0.004).
- This round's grades move each Δ by at most +0.020 (pre-pool → pooled; largest: H5 vs C0 on `yt_holdout`, +0.061 → +0.081). Every verdict holds with all of this round's items set to 0.

### Per kind, Δ nDCG@10 (pooled; seed in brackets; kinds with ≥ 3 searches)

**test2**

| Kind (n) [C0] | H0 vs C0 | H5 vs C0 | H5b vs C0 | H5b vs H0 | H5 vs H0 | H5b vs H5 |
|---|---|---|---|---|---|---|
| topic (7) [0.48] | +0.064 (+0.025) | +0.093 (+0.047) | **+0.116** (+0.065) | +0.052 (+0.041) | +0.029 (+0.022) | +0.023 (+0.019) |
| structure (6) [0.51] | +0.079 (+0.041) | +0.095 (+0.051) | +0.091 (+0.047) | +0.012 (+0.006) | +0.015 (+0.010) | −0.004 (−0.004) |
| name (3) [0.24] | +0.007 (−0.024) | +0.032 (+0.007) | +0.050 (+0.018) | +0.042 (+0.043) | +0.025 (+0.031) | +0.017 (+0.012) |
| task (3) [0.65] | +0.036 (+0.028) | +0.045 (+0.043) | **+0.109** (+0.092) | +0.073 (+0.064) | +0.009 (+0.015) | +0.064 (+0.050) |
| vibe (3) [0.33] | +0.049 (+0.044) | +0.086 (+0.052) | +0.081 (+0.051) | +0.032 (+0.007) | +0.037 (+0.008) | −0.005 (−0.001) |

**yt_holdout** (only `topic` reaches 3 searches; the other kinds have 1–3 and are given in `r7-final.json` only as pooled values)

| Kind (n) [C0] | H0 vs C0 | H5 vs C0 | H5b vs C0 | H5b vs H0 | H5 vs H0 | H5b vs H5 |
|---|---|---|---|---|---|---|
| topic (4) [0.49] | +0.064 (+0.070) | +0.120 (+0.076) | +0.085 (+0.065) | +0.020 (−0.005) | +0.056 (+0.005) | −0.036 (−0.011) |
| name (3) [0.42] | −0.027 (−0.035) | −0.044 (−0.038) | −0.031 (−0.048) | −0.004 (−0.013) | −0.017 (−0.003) | +0.013 (−0.010) |

- The two `yt_holdout` more-like-this searches: H0 vs C0 +0.133 (both from the 3-large example vectors); H5 = H0 there by design; H5b −0.009 vs H0.
- The `yt_holdout` name/audio search is the largest loss for every arm vs C0 (H0 −0.11, H5 −0.20, H5b −0.17); the router reads it as Instagram.

## Where the parts helped or hurt on held-out (vs H0, typed search × repeat cells, from run `meta.per_search`)

Search mean = average of a search's fired cells, then over the fired searches. Parts overlap inside the packages, so these are not separable effects. Fire counts are small; treat single-search rows as anecdotes.

| Part (cells / searches) | test2 H5 | test2 H5b | yt_holdout H5 | yt_holdout H5b |
|---|---|---|---|---|
| All typed (30/10 · 27/9) | +0.017, 5/3 | **+0.036 [+0.007, +0.069]**, 6/1 | +0.030, 5/3 | +0.008, 5/3 |
| **Router platform = search scope** (15/5 · 6/2) | +0.005, 2/2 | **+0.052 [+0.006, +0.098]**, 3/0 | +0.062, 2/0 | +0.056, 2/0 |
| Router = both (3/1 · 15/5) | +0.094 (g01) | +0.031 (g01) | +0.056 [−0.006, +0.137], 3/1 | +0.026, 3/1 |
| Router = one app on a `both` search (12/4 · —) | +0.014, 2/1 | +0.018, 2/1 | — | — |
| **Router = the other app** (— · 6/2) | none on test2 | none on test2 | **−0.064 [−0.093, −0.035]**, 0/2 | **−0.083 [−0.110, −0.056]**, 0/2 |
| Calibration strong, \|q−0.5\| ≥ 0.25 (15/5 · 6/2) | +0.030, 3/1 | **+0.043 [+0.006, +0.088]**, 3/0 | −0.064, 0/2 (the two misreads) | −0.083, 0/2 |
| Calibration weak (15/5 · 21/7) | +0.004, 2/2 | +0.030, 3/1 | **+0.058 [+0.011, +0.110]**, 5/1 | +0.035, 5/1 |
| Facet boost active (16/6 · 14/5) | +0.011, 4/2 | **+0.041 [+0.003, +0.071]**, 5/1 | **+0.070 [+0.001, +0.154]**, 4/1 | +0.028, 4/1 |
| **H1 soft time** (7/4 · 4/3) | **−0.048 [−0.096, 0.000]**, 0/2 | +0.017, 1/1 | +0.007, 1/0 | −0.014 [−0.025, −0.002], 0/2 |
| H1 guarded filter (0 · 1/1) | — | — | +0.21 (behaviour search, 1 cell) | +0.20 (1 cell) |
| Creator search (9/3 · 6/2) | +0.025, 1/1 | +0.042, 1/0 | +0.100, 1/0 | +0.065, 1/0 |
| Calibration only, nothing else fired (5/3 · 6/3) | +0.003 | +0.039 | −0.049, 1/2 | −0.054, 0/2 |

Reading:
- **Calibration helps when the router reads the platform right and hurts when it reads the other app**, exactly as on dev (dev: +0.031 right, −0.071 other app). The difference between the sets is how often it misreads: 0 of 4 `yt` searches on test2 (yt 3, both 1), but 2 of 9 typed `yt_holdout` searches read as Instagram (and 5 as both, 2 as YouTube). On dev it was 5 of 22 `yt` searches. On test2's 6 `both` searches it read both on 2, YouTube on 3 and Instagram on 1.
- **The misread losses are the same size as on dev** (H5 −0.064 vs dev −0.072; H5b −0.083 vs −0.125), and they fall on the `yt_holdout` name/audio and task/topic searches.
- **H1's soft time loses again where it fires** in H5 (test2 −0.048, 0/2; dev −0.032). In H5b it is mixed. Small n.
- **H1's guarded filter** fired once (the `yt_holdout` behaviour search, repeat 1 only) and gained +0.21, like its one large dev win.
- **Facet cells gain in both packages on both sets,** but the facet boost is tiny (dev: 0.000 for format) and those cells are also calibration cells; the gain is most likely calibration plus te lists, not the facets.
- **Creator search** fired on g04, g05, g08 (test2) and on the two `yt_holdout` people searches. Against H0 it gained on 2 (g08; the `yt_holdout` topic/people search), tied on 2 (g05, which every method scores 0; the `yt_holdout` name/people search) and, in H5, lost on g04 (−0.03; H5b tied). See the next section for the determinism caveat.

### Creator-search cells (known non-determinism)

Creator search depends on Python string hashing, so its rankings are one draw. It fired on **9 of 30** test2 cells per package (g04, g05, g08 in every repeat) and on **6 of 27** typed `yt_holdout` cells (the two people searches; same code, so the same caveat applies there).

| Comparison | test2 without g04/g05/g08 (7) | test2 creator searches (3) | yt_holdout without the 2 creator searches (9) | Both sets without creator searches (16) |
|---|---|---|---|---|
| H5b vs C0 | **+0.106 [+0.016, +0.220]**, 6/1 (seed +0.066, 6/1) | +0.050, 2/0/1 | +0.051, 6/3 | **+0.075 [+0.015, +0.140]**, 12/4 |
| H5 vs C0 | +0.086 [−0.002, +0.203], 5/2 (seed +0.051, 6/0) | +0.032, 2/0/1 | +0.068, 7/2 | **+0.076 [+0.009, +0.145]**, 12/4 |
| H0 vs C0 | +0.072 [+0.005, +0.178], 6/1 | +0.007, 1/1/1 | +0.059, 7/2 | **+0.065 [+0.014, +0.125]**, 13/3 |
| H5b vs H0 | +0.034 [−0.001, +0.065], 5/1 | +0.042, 1/0/2 | −0.008, 5/4 | +0.010 [−0.022, +0.039], 10/5 |
| H5 vs H0 | +0.014 [−0.027, +0.054], 4/2 | +0.025, 1/1/1 | +0.008, 4/3 | +0.011 [−0.018, +0.038], 8/5 |
| H5b vs H5 | +0.020, 3/1 | +0.017, 2/0/1 | −0.017, 2/5 | −0.001, 5/6 |

- **Against C0 nothing depends on the creator cells:** both packages and H0 keep their size and stay above 0 on the 16 searches without them.
- **Against H0, about half of each package's small increment sits in the creator cells** (21 searches +0.020 / +0.021 → 16 searches +0.010 / +0.011). That half is one hash draw and could not be reproduced as run.

## Mechanisms: top-10 platform mix (items per top 10 @ share relevant, pooled labels)

| Run | test2 yt: YouTube / Instagram | test2 both: Instagram / YouTube | yt_holdout: YouTube / Instagram |
|---|---|---|---|
| C0 | 9.50 @ 0.50 / 0.50 @ 0.00 | 3.22 @ 0.81 / 6.78 @ 0.70 | 6.42 @ 0.53 / 3.58 @ 0.35 |
| H0 | 9.67 @ 0.58 / 0.33 @ 0.25 | 2.72 @ 0.96 / 7.28 @ 0.70 | 7.18 @ 0.57 / 2.82 @ 0.40 |
| H5 | **10.00 @ 0.64** / 0.00 | 2.61 @ 0.96 / 7.39 @ 0.68 | 6.70 @ **0.63** / 3.30 @ 0.36 |
| H5b | 9.83 @ 0.64 / 0.17 @ 0.50 | **3.22 @ 0.93** / 6.78 @ 0.70 | 6.36 @ 0.62 / **3.64** @ 0.38 |

- **3-large lets fewer Instagram items into YouTube searches** on both sets (test2 0.50 → 0.33; `yt_holdout` 3.58 → 2.82), and its YouTube items are more often relevant. This is the dev and round-6 mechanism, now seen on `yt_holdout` too.
- **The packages raise YouTube precision further** (test2 0.58 → 0.64; `yt_holdout` 0.57 → 0.62–0.63). On test2 H5 removes Instagram items from `yt` top 10s entirely, because the router reads those searches as YouTube.
- **On `yt_holdout` the packages put Instagram items back in** (H5 3.30, H5b 3.64 per top 10, at 36–38% relevant), because the router reads 7 of 9 typed searches as both or Instagram. H5 still beats H0 there, through better YouTube ordering; H5b does not, because its te lists add the most Instagram items.
- **The te lists (H5b vs H5) do what they did on dev and in rounds 4–5:** more and still-precise Instagram items in `both` searches (2.61 → 3.22 @ 0.93), more Instagram items in YouTube searches (`yt_holdout` 3.30 → 3.64).

## Consistency with dev and earlier held-out

| Arm vs base | Dev (c4-r7) | Earlier held-out | This scoring | Verdict |
|---|---|---|---|---|
| **H0 vs C0** | +0.022 [−0.008, +0.050], 25/12; ig +0.031, yt +0.014 | test2 (r6, as G4) +0.053 [−0.001, +0.134], 7/2; seed +0.022 | **yt_holdout +0.056 [+0.003, +0.119], 8/2; seed +0.058 [+0.002, +0.124]**; 21 searches +0.055 [+0.013, +0.103], 15/4 | **CONFIRMED.** Positive with more wins than losses on dev and both held-out sets, same mechanism everywhere, CI above 0 on `yt_holdout` alone and on the 21 searches, robust to dropping the best 3 searches (+0.019) and to every grade variant. The held-out size (+0.05) is larger than dev (+0.022); the honest size is +0.02 to +0.05. |
| **H5b vs C0** | +0.034 [−0.012, +0.085], 24/15; ig +0.087, yt −0.018 | — | test2 +0.089 [+0.022, +0.174], 8/1; yth +0.061, 7/3; 21 +0.075 [+0.026, +0.128], 15/4 | **CONFIRMED vs C0** (positive, W > L, CI above 0 on test2 and on 21). Its YouTube side is better than dev predicted (held-out `yt`-scope 15 searches +0.087, 11/3, vs dev yt −0.018). |
| **H5 vs C0** | +0.028 [−0.012, +0.069], 24/14; ig +0.057, yt −0.000 | — | test2 +0.070 [+0.006, +0.155], 7/2; yth +0.081, 8/2; 21 +0.076 [+0.022, +0.135], 15/4 | **CONFIRMED vs C0.** The same caveat on the dev yt side. |
| **H5b vs H0** | +0.012 [−0.034, +0.063], 18/18; ig +0.056, yt −0.032 | — | test2 **+0.036 [+0.007, +0.069], 6/1**; yth +0.005, 6/4 (seed −0.015); 21 +0.020 [−0.008, +0.047], 12/5 | **NOT CONFIRMED.** Positive with more wins on 21, but the CI spans 0, half the 21-search gain is in creator cells, dev is +0.012 at 18/18, and on the all-YouTube set it is ≈ 0 (seed negative). |
| **H5 vs H0** | +0.006 [−0.027, +0.040], 15/11; ig +0.026, yt −0.014 | — | test2 +0.017, 5/3; yth +0.025, 5/3; 21 +0.021 [−0.006, +0.051], 10/6 | **NOT CONFIRMED.** Same pattern: consistently small and positive, never distinguishable from 0. |
| H5b vs H5 (te lists) | +0.006, 16/17; ig +0.030, yt −0.018 | rounds 4–5: te lists help ig / both, hurt yt | test2 both +0.032 (2/0), yth −0.020 (2/6; seed −0.017 [−0.034, −0.004]); 21 −0.001, 7/7 | **The dev trade is confirmed**: te lists help mixed searches and cost YouTube searches; net 0. |

## Recommendation

**Adopt H0 (C0 + text-embedding-3-large at 1,024 d) as the new processor.**
- Confirmed on dev and on both held-out sets. It meets adoption clause 1's terms on the 21 held-out searches (+0.055, CI above 0) and on `yt_holdout` alone. On dev it was a near miss (+0.022, 25/12, CI spanning 0).
- It is the cheapest gain of the loop: +$0.011 per 1k searches, about +0.1 s, plus $0.0043 per 1k items once to embed the library.
- It is the round-7 base, so every later arm already builds on it.

**Do not adopt H5b.** Its extra part (te lists) nets 0 over the 21 held-out searches and loses on YouTube searches in every repeat on `yt_holdout`, as on dev. It needs a te pass for every new library.

**Keep H5 as the package candidate, not adopted yet:**
- It beats C0 on held-out by more than H0 (+0.076 vs +0.055), but its own increment over H0 (+0.021 held-out, +0.006 dev) is unconfirmed. Half of it is in creator-search cells that are not reproducible as run.
- It costs $0.294 per 1k (+$0.164) and +0.8 s as run, all from the separate qs-v1 call. Merged into the rewrite call it would cost about H0's $0.131 (estimate, not measured).
- **What is clear about its parts, from dev plus held-out:**
  - keep: router calibration when the platform read is right or confident (held-out right-read cells +0.05 to +0.06; dev +0.031), the guarded filter (one large win on each of dev and `yt_holdout`), creator search (held-out: 2 wins, 2 ties, 1 small loss);
  - fix or drop: calibration on reads of the other app (−0.064 to −0.083 on held-out, −0.071 on dev), H1's soft time (loses where it fires in H5 on both test2 and dev), the format boost (no effect on dev);
  - fix: creator search's dependence on Python string hashing (set a fixed hash seed or sort deterministically) so its cells can be reproduced.
- A pared-down **H5-lite** (H0 + calibration gated on router confidence, guarded filters, creator search made deterministic, H4 profiles, qs-v1 merged into qr-v1; no soft time, no format boost, no te lists) is the natural next candidate. It has not been run on anything, so nothing here supports adopting it now.

**What is confirmed and what is not:**
- Confirmed: 3-large over C0; both packages over C0; the te-list trade (help mixed / Instagram, hurt YouTube); router misreads hurting YouTube searches; the 3-large mechanism (fewer, better Instagram items in YouTube searches).
- Not confirmed: any part's increment over H0 overall; the packages' YouTube side in general (it depends on how often the router misreads, 0 of 4 on test2 vs 2 of 9 on `yt_holdout` vs 5 of 22 on dev); H4's creator profiles and creator search beyond single searches; the soft-time and facet parts.

**What new held-out data would settle the rest:**
- **A fresh Derrick set of about 40–45 searches.** The per-search SD of the H5 − H0 Δ on these sets is 0.065–0.068, so a +0.02 increment needs about 40–45 searches for a CI that clears 0.
- **It needs `ig` scope** (test2 had none and `yt_holdout` is YouTube-only): about a third each `ig`, `yt` and `both`.
- **Enough searches of the kinds where parts fire:** 6–8 creator recalls (named and described), 5+ time or behaviour searches, and YouTube searches whose wording is not obviously about YouTube (the router-misread case).
- **Make creator search deterministic first,** and run H0 vs H5-lite (and H5 as a reference) with qs-v1 merged, so cost and latency are measured, not estimated.
- `test` has 2 scorings left. It is contaminated for round-5 ideas (qs-v1, creator search, te lists), so it cannot fairly judge the packages, but it could give H0 vs C0 a third held-out check, including `ig` searches.

## Cost and latency (run `meta`, typed searches)

| Run | $/1k searches | Total p50 / p95 (s), test2 | Total p50 / p95 (s), yt_holdout |
|---|---|---|---|
| C0 | $0.120 (round-6 same-runner control) | — (meta predates the latency model) | — |
| H0 | $0.128–0.131 | 2.25–2.81 / 2.31–4.43 | 1.99–2.04 / 2.56–2.92 |
| H5 | $0.294–0.298 (≈ $0.131 if qs-v1 is merged) | 2.50–2.88 / 2.65–4.44 | 2.70–2.85 / 3.30–3.82 |
| H5b | as H5, + te pass $0.18 per 1k caption-type items once | 2.52–2.91 / 2.67–4.45 | 2.71–2.89 / 3.33–3.88 |

- test2 latencies include fresh qs-v1 calls and a live query-embedding call; the r1 p95 (≈ 4.4 s) is one slow call shared by all three arms.
- Per +0.01 nDCG over C0 on the 21 held-out searches: H0 $0.002, H5 $0.023 (≈ $0.0015 merged), H5b $0.023 (+ te pass).
- **Spend.** This scoring cost **$0**, with no paid judging and no API calls. The ledger is unchanged by it: OpenAI $2.882 of $9.50, Gemini $3.776, total $6.657 as of `r7-eval.md`. The test2 run files for H0 / H5 / H5b record $0 new spend in their meta (cached parses); any orchestrator spend for the fresh qs-v1 test2 parses is outside this report.

## Problems and caveats

1. **Creator search is not deterministic** (Python string hashing). It fired on 9 of 30 test2 cells and 6 of 27 typed `yt_holdout` cells per package; those rankings are one draw. All verdicts against C0 hold without them; half of each package's increment over H0 sits in them.
2. **test2's H0 vs C0 is not new evidence.** H0's test2 top 10s equal round 6's G4, and no new label touched C0 or H0 top 10s, so test2 reproduces round 6's +0.053. The new evidence for 3-large is `yt_holdout`.
3. **Small n and uneven scopes.** 21 searches in all; no `ig`-scope held-out search; g05 is 0 for every method. Per-kind rows on `yt_holdout` have 1–4 searches.
4. **One judge** (this evaluator) produced all 76 new grades. They cover at most 8% of relevant top-10 items; every verdict holds with all of them set to 0.
5. **Calibration fidelity.** On g10 I graded items of the kind the intent excludes 0, as the earlier test2 evaluators did; Derrick's own scale on g10 is more lenient, so my g10 grades may be slightly strict. On the pooled `yt_holdout` more-like-this search the example is outside the library and was judged from its title only; two short same-surface-topic clips were graded 0, as the milestone evaluator graded items of that kind.
6. **The preregistered package (H5b) is not the better one on held-out.** H5 matches it against C0 (+0.076 vs +0.075) and beats it on `yt_holdout`. Choosing H5 now uses the held-out result; that is why H5 is recommended only as a candidate, not adopted.
7. **No rule slips.** No captions, query texts, intents, creators or IDs were written to a committed file; nothing under `/tmp/claude-0/` was read; no key was printed; dev and `test` were not scored.

## Remaining held-out scorings

- `test2`: **0 left (used up)**;
- `yt_holdout`: **0 left (used up)**;
- `test`: 2 left (contaminated for round-5 ideas).
