# Round 4 milestone (held-out) · evaluator report

*3 Nov 2026 · Milestone evaluator (did not build any method) · label round **c4-m1** · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. Test searches are referred to by `f`-number and kind; `yt_holdout` searches by kind only.*

**Scorings used by this report:**
- `test`: scoring **1 of 3** (2 left);
- `yt_holdout`: scoring **2 of 3** (round 3 used one; **1 left**).

Each set was scored once, after pooling, with the three frozen methods C0, E1 and E3. No run or method file was touched.

Code: `experiments/eval/score_c4.py`, extended for the test split. It now reads Derrick's `judged_nonrelevant` gold zeros, handles scope `both` (no own platform, so no cross share) and reports a `both` subset. `unvetted_candidates` stay unjudged unless pooled. The sheet builder, analysis script, sheets, grades and per-search deltas (by `f`-number) are in `data/all/eval_work/milestone/`, which is gitignored. Aggregates: `r4-milestone.json`.

## Bottom line

- **Verdict: not confirmed.** E1's dev gain over C0 (+0.056) does not hold on held-out searches.
  - **`test`** (13 searches): **+0.030 [−0.005, +0.068], 7/5/1**. That is about half the dev gain, and the CI includes 0. Its lower bound is below 0 on all 20 bootstrap seeds, and dropping the best search leaves +0.018.
  - **`yt_holdout`** (11 searches): **−0.024 [−0.077, +0.012], 3/6/2**. All three repeats give −0.024.
  - **Both sets together** (24 searches): **+0.005 [−0.027, +0.035], 10/11**. Wins do not outnumber losses.
- **What holds is the Instagram side of the te fusion.**
  - Test `ig`: E1 vs C0 +0.051 [+0.012, +0.100], 3/0/1 (dev ig: +0.073).
  - Test `both`: +0.053 [−0.011, +0.116], 3/2/0.
- **What fails is every YouTube search.**
  - Test `yt`: −0.021 [−0.075, +0.025], 1/3/0.
  - `yt_holdout`: −0.024.
  - On dev, `yt` was +0.038. That came almost entirely from the intent step on behaviour and time searches, and held-out has no search where the intent step acts (see Drivers).
- **E3 is no better.**
  - Test +0.024 [−0.011, +0.063], 6/6/1; `yt_holdout` −0.023, 3/5/3.
  - On test `yt`, E3 is significantly worse than C0: −0.042 [−0.072, −0.013], 0/4/0.
  - E1 vs E3 cannot be told apart: test +0.006, `yt_holdout` −0.001, together +0.003 (4/4).
- **Pooling changed no direction.** Seed-only vs pooled Δ for E1 vs C0:
  - test +0.022 → +0.030;
  - `yt_holdout` −0.026 → −0.024.

## Method

- **Runs.**
  - `test`: `runs/final/{c0x,e1,e3}_test_r{1,2,3}`. These are fresh qr-v1 rewrites and qi-v3 intents made by the orchestrator. The guards dropped every intent on test, so here E1 is D1 and E3 is E2.
  - `yt_holdout`: `runs/r4.2/c0x_r*`, `runs/r4.3/e1_r*` and `runs/r4.3/e3_r*`, restricted to the 11 `yt_holdout` searches. The scorer reads all of them through symlinks in `eval_work/milestone/runs/`.
- **Conventions, as in 4.1–4.3.**
  - Each search's metrics are the mean over its 3 repeats.
  - CIs are 2,000-sample bootstraps over searches. Comparisons pair repeat k with repeat k, then bootstrap.
  - W/L/T uses |Δ| > 0.005.
  - Per-kind rows count a search under every kind it has.
- **Pooling.**
  - The pool is every unjudged top-10 item of the three methods, over 3 repeats each, cross-platform items included.
  - `test`: **243 items** over 13 searches, 38 of them `unvetted_candidates`. Before pooling, unjudged@10 was 0.81–0.83: Derrick's vetted set covered few top-10 items.
  - `yt_holdout`: **115 items** over 11 searches, 100 of them Instagram items. Round 3's labels covered YouTube only. Unjudged@10 was 0.40–0.46 before pooling.
  - After merging, unjudged@10 is **0.00** for every run on both sets.
  - Labels were backed up first to `evalset.pre_milestone.jsonl`, then merged with `judge.py merge`, judge `claude-evaluator-milestone`.
  - My grades of 0 go to `judged_not_relevant`. Derrick's `relevant` and `judged_nonrelevant` were not touched.
- **Blind judging, $0, no paid judge.**
  - The sheet is grouped by search and shuffled within each search. It shows no run identity, rank or vetted/unvetted status. It shows own text, interactions and duration, but no te text.
  - **Calibration before grading:**
    - On test, I read a sample of Derrick's own 2, 1 and 0 marks for every search. His pattern: the target creator or a clear on-topic match is 2; same-topic items that are not the target are 1. Surface-word matches that miss the meaning are 0, and so are items in the right topic but the wrong tone or format where the intent names one.
    - On `yt_holdout`, I read a sample of round 3's labels. Same-topic items that are not the target are 0 on its name and more-like-this searches, and short-form items lose a grade where the intent rules out shorts.
  - **Grades:**
    - test: 37 / 103 / 103 (2 / 1 / 0). Cross-platform items: 3 / 18 / 31. Unvetted candidates that surfaced: 26 / 12 / 0.
    - `yt_holdout`: 13 / 19 / 83. Instagram items: 12 / 17 / 71.
  - **`f01`** has no grade-2 answer (Derrick has not confirmed the exact item). Every relevant item in it is a 1, so its nDCG@10 measures only partial-credit ordering. Excluding it is reported below.
- **Whose grades the test score rests on.**
  - Across the three methods, 25–27% of the relevant top-10 items on test carry Derrick's own grades. So do 52–54% of the grade-2 items.
  - The rest are my calibrated judgments. Test is therefore "Derrick's searches and intents, Derrick-calibrated grades", not fully Derrick-graded.

## Scores (pooled c4-m1, mean of 3 repeats; seed-only = labels before this milestone)

### `test` (13 searches: 4 `ig`, 4 `yt`, 5 `both`)

| Method | Scope (n) | nDCG@10 pooled [95% CI] | nDCG@10 seed-only | Repeat range | R@10 | R@50 | MRR | Seed unjudged@10 | Other-platform share of top 10 |
|---|---|---|---|---|---|---|---|---|---|
| C0 | all (13) | 0.480 [0.356, 0.608] | 0.198 | 0.461–0.515 | 0.236 | 0.423 | 0.847 | 0.83 | 0.16* |
| C0 | ig (4) | 0.546 | 0.221 | 0.500–0.607 | 0.442 | 0.661 | 0.861 | 0.85 | 0.41 |
| C0 | yt (4) | 0.536 | 0.187 | 0.515–0.563 | 0.115 | 0.284 | 0.778 | 0.84 | 0.11 |
| C0 | both (5) | 0.383 | 0.189 | 0.362–0.404 | 0.168 | 0.344 | 0.892 | 0.80 | — |
| **E1** | all (13) | **0.510** [0.380, 0.642] | 0.221 | 0.482–0.536 | 0.255 | 0.458 | 0.871 | 0.81 | 0.19* |
| E1 | ig (4) | 0.597 | 0.271 | 0.560–0.637 | 0.472 | 0.704 | 0.917 | 0.82 | 0.35 |
| E1 | yt (4) | 0.515 | 0.169 | 0.474–0.553 | 0.105 | 0.319 | 0.815 | 0.85 | 0.26 |
| E1 | both (5) | 0.436 | 0.222 | 0.362–0.503 | 0.202 | 0.373 | 0.880 | 0.77 | — |
| E3 | all (13) | 0.504 [0.378, 0.635] | 0.219 | 0.469–0.531 | 0.254 | 0.453 | 0.882 | 0.82 | 0.20* |
| E3 | ig (4) | 0.597 | 0.281 | 0.560–0.637 | 0.472 | 0.706 | 0.917 | 0.82 | 0.34 |
| E3 | yt (4) | 0.494 | 0.155 | 0.469–0.536 | 0.102 | 0.299 | 0.808 | 0.88 | 0.30 |
| E3 | both (5) | 0.438 | 0.221 | 0.362–0.505 | 0.202 | 0.372 | 0.913 | 0.77 | — |

\* In the `all` rows, `both` searches count as 0 cross share.

### `yt_holdout` (11 searches, all `yt`)

| Method | nDCG@10 pooled [95% CI] | nDCG@10 seed-only | Repeat range | R@10 | R@50 | MRR | Seed unjudged@10 | Other-platform share of top 10 |
|---|---|---|---|---|---|---|---|---|
| C0 | **0.388** [0.203, 0.568] | 0.303 | 0.382–0.396 | 0.082 | 0.145 | 0.667 | 0.40 | 0.36 |
| E1 | 0.364 [0.185, 0.540] | 0.276 | 0.358–0.372 | 0.087 | 0.143 | 0.614 | 0.43 | 0.41 |
| E3 | 0.366 [0.184, 0.545] | 0.271 | 0.355–0.380 | 0.086 | 0.140 | 0.605 | 0.46 | 0.43 |

## Comparisons (paired, pooled labels; seed-only alongside)

| Comparison | Set · scope (n) | **Δ nDCG@10** [95% CI] | W/L/T | Per repeat | Δ R@10 | Δ R@50 | Δ MRR | Seed-only Δ [CI], W/L/T |
|---|---|---|---|---|---|---|---|---|
| **E1 vs C0** | test · all (13) | **+0.030** [−0.005, +0.068] | 7/5/1 | +0.020, +0.072, −0.003 | +0.019 | +0.035 | +0.024 | +0.022 [−0.011, +0.058], 6/3/4 |
| | test · ig (4) | +0.051 [+0.012, +0.100] | 3/0/1 | +0.063, +0.060, +0.031 | +0.030 | +0.042 | +0.056 | +0.050 [0.000, +0.114], 2/0/2 |
| | test · yt (4) | −0.021 [−0.075, +0.025] | 1/3/0 | +0.003, +0.024, −0.090 | −0.010 | +0.035 | +0.037 | −0.018 [−0.079, +0.037], 1/2/1 |
| | test · both (5) | +0.053 [−0.011, +0.116] | 3/2/0 | −0.000, +0.119, +0.039 | +0.034 | +0.029 | −0.012 | +0.033 [−0.004, +0.079], 3/1/1 |
| | **yt_holdout (11)** | **−0.024** [−0.077, +0.012] | 3/6/2 | −0.024, −0.024, −0.024 | +0.005 | −0.002 | −0.052 | −0.026 [−0.082, +0.018], 4/5/2 |
| | **both sets (24)** | **+0.005** [−0.027, +0.035] | 10/11/3 | | | | | |
| **E3 vs C0** | test · all (13) | +0.024 [−0.011, +0.063] | 6/6/1 | +0.007, +0.067, −0.003 | +0.018 | +0.030 | +0.035 | +0.020 [−0.012, +0.059], 5/4/4 |
| | test · ig (4) | +0.051 [+0.012, +0.099] | 3/0/1 | +0.063, +0.060, +0.030 | +0.030 | +0.045 | +0.056 | +0.059 [0.000, +0.143], 2/0/2 |
| | test · yt (4) | **−0.042 [−0.072, −0.013]** | 0/4/0 | −0.039, +0.007, −0.095 | −0.013 | +0.015 | +0.030 | −0.032 [−0.068, −0.006], 0/3/1 |
| | test · both (5) | +0.055 [−0.009, +0.117] | 3/2/0 | +0.000, +0.121, +0.044 | +0.034 | +0.029 | +0.022 | +0.031 [−0.004, +0.075], 3/1/1 |
| | yt_holdout (11) | −0.023 [−0.078, +0.016] | 3/5/3 | −0.025, −0.027, −0.017 | +0.005 | −0.005 | −0.061 | −0.032 [−0.088, +0.014], 2/6/3 |
| | both sets (24) | +0.002 [−0.029, +0.032] | 9/11/4 | | | | | |
| **E1 vs E3** | test · all (13) | +0.006 [−0.003, +0.016] | 2/2/9 | +0.013, +0.005, −0.000 | +0.001 | +0.006 | −0.011 | +0.002 [−0.010, +0.017], 2/2/9 |
| | test · ig / yt / both | +0.000 / +0.022 / −0.003 | 0/0/4 · 2/1/1 · 0/1/4 | | | | | |
| | yt_holdout (11) | −0.001 [−0.014, +0.011] | 2/2/7 | +0.001, +0.003, −0.008 | +0.001 | +0.003 | +0.009 | +0.005 [−0.008, +0.018], 4/1/6 |
| | both sets (24) | +0.003 [−0.006, +0.011] | 4/4/16 | | | | | |

### Robustness

| Arm vs C0 | Set | Δ | Lower bound over 20 seeds × 10k | Seeds with lower bound > 0 | Drop best 1 / 2 / 3 searches | Without `f01` |
|---|---|---|---|---|---|---|
| E1 | test | +0.030 | −0.008 to −0.006 | 0 / 20 | +0.018 / +0.009 / +0.001 | +0.022 [−0.011, +0.060], 6/5 |
| E3 | test | +0.024 | −0.014 to −0.012 | 0 / 20 | +0.012 / +0.002 / −0.007 | +0.016 [−0.018, +0.055], 5/6 |
| E1 | yt_holdout | −0.024 | −0.078 to −0.075 | 0 / 20 | −0.031 / −0.040 / −0.048 | — |
| E3 | yt_holdout | −0.023 | −0.080 to −0.076 | 0 / 20 | −0.033 / −0.041 / −0.049 | — |

The largest single test win for both arms is the partial-credit-only search `f01`. Without it, E1's test gain is +0.022 with 6 wins and 5 losses. Per-search deltas by `f`-number are in `eval_work/milestone/per_search_deltas.json`.

### Per kind, Δ nDCG@10 vs C0 (pooled; kinds with n ≥ 2)

| Set · kind (n) | E1 − C0 | E3 − C0 |
|---|---|---|
| test · topic (8) | +0.029 | +0.026 |
| test · name (6) | +0.052 | +0.043 |
| test · vibe (3) | −0.052 | −0.044 |
| test · task (2) | +0.127 | +0.129 |
| test · shown (2) | +0.039 | +0.039 |
| test · structure (1) | −0.009 | −0.011 |
| yt_holdout · topic (4) | −0.014 | −0.028 |
| yt_holdout · name (3) | +0.002 | +0.002 |
| yt_holdout · more_like_this (2) | **−0.102** | −0.091 |
| yt_holdout · task (2) | −0.030 | −0.030 |
| yt_holdout · people (2) | −0.004 | −0.022 |
| yt_holdout · vibe (2) | −0.001 | +0.014 |
| yt_holdout · behaviour, structure, personal, audio (1 each) | 0.000 / 0.000 / −0.024 / +0.043 | 0.000 / 0.000 / −0.025 / +0.043 |

By scope on test (E1 − C0):
- `ig` (4 searches; name ×4, topic, shown): +0.051.
- `both` (5; topic/task ×2, topic/vibe, topic/name, vibe/shown): +0.053. Task searches gain most (+0.13). The two vibe searches lose (−0.03).
- `yt` (4; topic ×3, vibe, structure, name): −0.021. Topic −0.04, vibe −0.10, name +0.04.

On `yt_holdout`, most of the more-like-this loss comes from one search. There, the te lists bring in other-platform items that share the example's surface topic but not its meaning; these were graded 0, as round 3 graded its own-platform items of that kind.

## Drivers of the gap between dev and held-out

1. **The intent step, which carried dev's YouTube gain, never acts on held-out searches.**
   - On dev, E1's `yt` gain (+0.038) came from the guarded qi-v3 intent on behaviour and time searches (dev yt behaviour +0.29, time +0.23). One YouTube time/behaviour search alone gave +0.63.
   - On held-out:
     - `test` has no behaviour or time searches by design, and the guards dropped every intent (13 of 13).
     - On `yt_holdout`, the guards dropped every intent except the one on the behaviour search. All three methods score 0 there, so it is a tie.
   - So **held-out measures only E1's te-fusion part, which is D1.** On dev, D1 vs C0 was +0.037 with yt +0.001, and yt topic, task and structure were −0.05 to −0.09. Held-out YouTube (−0.021 test, −0.024 `yt_holdout`) is exactly that loss.
   - The intent step itself is therefore **neither confirmed nor refuted** by this milestone.
2. **te fusion shifts top-10 slots toward Instagram.** te covers 98% of Instagram items but only 6% of YouTube items. The shift helps where Instagram holds the answers and hurts YouTube searches.
   - Mean per search, items per top 10 @ share relevant (pooled labels):

     | Run | test ig: own / cross | test yt: own / cross | test both: IG / YT items | yt_holdout: own / cross |
     |---|---|---|---|---|
     | C0 | 5.92 @ 0.86 / 4.08 @ 0.43 | 8.92 @ 0.79 / 1.08 @ 0.15 | 4.47 @ 0.82 / 5.53 @ 0.42 | 6.42 @ 0.53 / 3.58 @ 0.35 |
     | E1 | 6.50 @ 0.87 / 3.50 @ 0.55 | 7.42 @ 0.81 / 2.58 @ 0.39 | 6.20 @ 0.80 / 3.80 @ 0.51 | 5.94 @ 0.54 / 4.06 @ 0.34 |
     | E3 | 6.58 @ 0.86 / 3.42 @ 0.56 | 7.00 @ 0.80 / 3.00 @ 0.42 | 6.20 @ 0.80 / 3.80 @ 0.51 | 5.70 @ 0.53 / 4.30 @ 0.35 |

   - In `ig` and `both` searches, E1 moves about 0.6–1.7 slots per top 10 to Instagram items, which are relevant 80–87% of the time. That is the confirmed gain.
   - In YouTube searches, E1 gives 0.5–1.5 slots to Instagram items. On `yt_holdout` those are relevant 34–35% of the time, against 53–54% for the YouTube items they replace. On test `yt`, the figures are 39–42% against 80–81%. That is the loss.
3. **E3's descriptive-title rule makes YouTube worse, not better.**
   - Withholding te from titled YouTube items pushes more Instagram items into YouTube searches (test yt cross 3.00 vs E1's 2.58; `yt_holdout` 4.30 vs 4.06). This is 4.3's slot-competition finding, now on held-out.
4. **Concentration and tuning.**
   - On dev, the pass failed once the 2 best searches were removed. On test, removing 1 search already leaves +0.018, and the best one is the partial-credit-only `f01`.
   - E1's widen-only guard fix was designed from one dev search. On held-out it never matters: no held-out intent survives to be narrowed.

## Verdict and what follows

- **Milestone verdict: NOT CONFIRMED.**
  - By the milestone rule (positive on held-out, with more wins than losses): `test` alone passes narrowly (+0.030, 7/5); `yt_holdout` fails (−0.024, 3/6); together they fail (+0.005, 10/11).
  - Under the round's adoption rule, E1 vs C0 would fail even on `test`: Δ ≥ 0.03, but the CI includes 0.
- **Confirmed component: te fusion on Instagram-side searches.**
  - Test `ig` +0.051 [+0.012, +0.100], 3/0/1, and `both` +0.053, at the te-pass cost ($0.18 per 1k items).
  - This matches round 1's Instagram te result (+0.059) and dev 4.2–4.3 (ig +0.07).
- **Not confirmed:**
  - the YouTube side of E1 and E3 (held-out −0.02 to −0.04);
  - the intent step (never active on held-out);
  - E3's descriptive rule (no better than E1 and worse on test `yt`).
- **For the founders:**
  - C0 remains at least as good as E1 for YouTube-heavy searching.
  - E1's te fusion is worth having only if its YouTube slot competition is fixed, for example te lists that rerank only within the own lists' top N (4.3's agenda item 2).
  - The intent step needs held-out behaviour and time searches before it can be claimed. Derrick's next fresh searches should include some.
- **Remaining scorings:** `test` **2 left**; `yt_holdout` **1 left**. Spend the next `test` scoring only on a materially different finalist. Keep `yt_holdout`'s last scoring for the final.
- **Spend:** this milestone $0, with no paid judging. Round 4 to date is **$3.879** (Gemini $3.776, OpenAI $0.103), per the ledger `data/all/ai_runs.jsonl`. The ≈ $0.012 above 4.3's $3.867 is the orchestrator's `test` runs.
- **Not done here:** BRIEF-4's Finish write-up (`docs/research/<date>-combined-loop.md`) and the A-003/A-004 amendment updates. They are left to the orchestrator.

## Problems and caveats

1. **Small n.** There are 13 and 11 searches, and test scopes have only 4, 4 and 5. Every per-scope CI is wide.
2. **Test grading is mostly the evaluator's.** Derrick's grades cover about 26% of the relevant top-10 items, and the remainder are my blind judgments calibrated to his marks. A Derrick spot-check of a sample of the 243 pooled test grades would firm up the test result.
3. **`f01` is partial credit only.** No item in it can earn a 2, and it is the largest single test win.
4. **te text was not shown to the judge**, as on dev. This slightly disfavours te arms.
5. **`yt_holdout`'s seed labels were YouTube-only.** 87% of its pool was Instagram items, judged now for the first time. Pooling raised all three arms about equally (seed to pooled: C0 +0.085, E1 +0.088, E3 +0.095), slightly favouring the te arms, so missing labels do not explain the loss.
6. **Scorer change.** `score_c4.py` gained `judged_nonrelevant`, scope `both` and the `both` subset. Dev results are unaffected: dev rows have neither field.
