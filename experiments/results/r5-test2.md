# Round 5 · held-out `test2` · evaluator report

*3 Nov 2026 · Held-out evaluator (did not build any method) · label round **c4-t2** · aggregates only. No captions, titles, creators, IDs, query or intent texts appear here. Searches are referred to by `g`-number, scope and kind only.*

**Scorings used by this report:** `test2` scoring **1 of 3** (2 left). `test` (2 left) and `yt_holdout` (1 left) were not scored or read. No dev row was scored.

Four frozen methods were scored once, after pooling and blind judging: **C0** (baseline, finalist), **E1** (coverage-fair te fusion + guarded qi-v3 intent), **F0** (te lists for caption-type items only, coverage-fair fusion) and **F2** (qs-v1 typed slots + creator search). No run or method file was touched.

Code: `experiments/eval/score_c4.py`. One change: `test2` was added to the splits `load_labels` accepts (`("dev", "test", "test2", "yt_holdout")`). Without it the split loads no rows. Nothing else changed. The sheet builder, analysis script, sheet, grades and per-search deltas (by `g`-number) are in `data/all/eval_work/test2/`, which is gitignored. Aggregates: `r5-test2.json`.

## Bottom line

- **E1 vs C0: +0.030 [−0.015, +0.076], 6/3/1.** E1 0.479 vs C0 0.448. This is the same size as on `test` (+0.030, 7/5).
  - `both` scope (6 searches): **+0.054 [+0.008, +0.107], 5/0/1.** `yt` (4): −0.006, 1/3.
  - The intent step acted on **1 of 30** search × repeat cells. So on test2, E1 is in effect D1 (te fusion everywhere).
  - It is fragile. The lower bound is below 0 on 20 of 20 seeds. Dropping the best search leaves +0.015; dropping the best two leaves +0.002.
- **F0 vs C0: +0.005 [−0.034, +0.051], 4/4/2.** It repeats its dev pattern exactly:
  - `both` **+0.040 [+0.003, +0.093], 4/0/2**;
  - `yt` **−0.049 [−0.095, −0.016], 0/4/0**, significantly worse. Instagram items fill 2.17 of each YouTube search's top 10 (C0: 0.50), and only 4% of them are relevant.
- **F2 vs C0: +0.008 [0.000, +0.022], 2/0/8.** Creator search fired on g04, g05 and g08 (8 of 30 cells). Every other search equals C0 exactly.
  - On the 3 creator searches: +0.027, 2/0/1. The two wins are searches that **name** the creator.
  - On g05, the only search that **describes** a creator without naming them, every method scores 0. Creator search pushed the target creator's first item further down: from rank 57–64 (C0) to rank 74–90 (F2).
- **Verdicts.** Confirmed means positive on test2, with more wins than losses, and consistent with dev.
  - **E1: confirmed, narrowly, for its te-fusion part only.** Its YouTube side and the intent step are still not confirmed.
  - **F0: not confirmed.**
  - **F2: not confirmed.**
- **Pooling raised E1 the most.** Seed-only Δ → pooled Δ:
  - E1 +0.004 (3/4/3) → +0.030;
  - F0 +0.009 → +0.005;
  - F2 +0.004 → +0.008.
  - Seed unjudged@10 was 0.78–0.79. Pooled, it is 0.00 for every run.

## Method

- **Runs.** `runs/final2/{c0x,e1,f0,f2}_test2_r{1,2,3}`, read through symlinks in `eval_work/test2/runs/`. `tmp/final2_pass1/` was ignored.
- **Searches.** The 10 searches are 4 `yt` and 6 `both`; none is `ig`. Kinds (overlapping): topic 7, structure 6, name 3, task 3, vibe 3, time 1.
- **Conventions, as in the 4.x and milestone reports.**
  - Each search's metrics are the mean over 3 repeats.
  - CIs are 2,000-sample bootstraps over searches (seed 0 for levels, seed 1 for Δ). Comparisons pair repeat k with repeat k.
  - W/L/T uses |Δ| > 0.005.
  - Per-kind rows count a search under every kind it has.
- **Labels.**
  - Derrick's `relevant` grades and `judged_nonrelevant` zeros are gold and were not touched; I checked this after the merge with 0 differences.
  - His `unvetted_candidates` (rule guesses) were treated as unjudged. They were judged only where they surfaced in a top 10.
  - Backup: `evalset.pre_test2.jsonl`. Merged with `judge.py merge`, judge `claude-evaluator-test2`.
- **Pool.** Every unjudged top-10 item of the four methods over 3 repeats, cross-platform items included: **159 items over 9 searches**.
  - 59 of them were `unvetted_candidates`.
  - g02 was already fully judged.
  - By search scope and item platform: yt/YouTube 60, yt/Instagram 13, both/YouTube 50, both/Instagram 36.
- **Blind judging, $0, no paid judge.**
  - The sheet is grouped by search and shuffled within each search. It shows no run, rank or vetted/unvetted status. It shows the item's own text, interactions and duration; te text is not shown.
  - **Calibration first:** for every search I read up to 10 of Derrick's 2s, 10 of his 1s and his 0s. His scale varies by search:
    - strict on the name/time search (g05): only the target creator's items are 2; every other creator is 0;
    - literal and lenient on the structure-only search (g09): any title in the stated format is 2, and near-formats are 1;
    - lenient on one task/topic search (g10): broad practical matches are 2;
    - lenient on the two name searches (g04, g08): the target's own closely related videos are often 2, and looser related videos are 1;
    - on the topic/structure searches (g01, g03, g06), 2 goes only to the core of the intent; on-topic items without the stated structure or depth get 1.
    - I matched each search's own scale.
  - **Grades:** 37 / 44 / 78 (2 / 1 / 0).
    - YouTube items 28 / 22 / 60; Instagram items 9 / 22 / 18.
    - Unvetted candidates that surfaced: 29 / 26 / 4.
    - All 21 pooled items on g05 are 0: none is by the target creator.
- **Whose grades the pooled score rests on.** Across methods, 32–36% of the relevant top-10 items carry Derrick's own grades, and 34–38% of the grade-2 items do. The rest are my calibrated judgments. That is slightly more Derrick coverage than on `test` (26%).

## Scores (mean of 3 repeats)

Seed-only = Derrick's test2 labels before this pooling. Pooled = c4-t2.

| Method | Scope (n) | nDCG@10 pooled [95% CI] | seed-only | Repeats (pooled) | R@10 pooled / seed | R@50 pooled / seed | MRR pooled / seed | P@10 pooled / seed | Seed unj@10 | Other-platform share of top 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| **C0** | all (10) | **0.448** [0.303, 0.603] | 0.180 | 0.434–0.459 | 0.142 / 0.070 | 0.302 / 0.200 | 0.714 / 0.351 | 0.633 / 0.210 | 0.79 | 0.02* |
| C0 | yt (4) | 0.301 | 0.127 | 0.282–0.328 | 0.102 / 0.044 | 0.217 / 0.135 | 0.572 / 0.229 | 0.475 / 0.142 | 0.86 | 0.05 |
| C0 | both (6) | 0.547 | 0.215 | 0.505–0.577 | 0.168 / 0.087 | 0.359 / 0.244 | 0.808 / 0.433 | 0.739 / 0.256 | 0.74 | — |
| **E1** | all (10) | **0.479** [0.314, 0.647] | 0.184 | 0.466–0.495 | 0.142 / 0.068 | 0.318 / 0.210 | 0.707 / 0.342 | 0.643 / 0.207 | 0.79 | 0.03* |
| E1 | yt (4) | 0.296 | 0.101 | 0.260–0.328 | 0.090 / 0.030 | 0.216 / 0.133 | 0.569 / 0.219 | 0.442 / 0.100 | 0.90 | 0.08 |
| E1 | both (6) | 0.601 | 0.239 | 0.558–0.626 | 0.177 / 0.094 | 0.386 / 0.261 | 0.799 / 0.424 | 0.778 / 0.278 | 0.72 | — |
| **F0** | all (10) | **0.453** [0.288, 0.633] | 0.189 | 0.446–0.460 | 0.139 / 0.072 | 0.318 / 0.211 | 0.708 / 0.343 | 0.610 / 0.217 | 0.78 | 0.09* |
| F0 | yt (4) | 0.252 | 0.122 | 0.231–0.286 | 0.082 / 0.041 | 0.209 / 0.129 | 0.572 / 0.223 | 0.358 / 0.133 | 0.87 | **0.22** |
| F0 | both (6) | 0.587 | 0.234 | 0.552–0.607 | 0.177 / 0.093 | 0.391 / 0.266 | 0.799 / 0.423 | 0.778 / 0.272 | 0.72 | — |
| **F2** | all (10) | **0.457** [0.311, 0.611] | 0.184 | 0.446–0.464 | 0.143 / 0.070 | 0.304 / 0.202 | 0.730 / 0.371 | 0.637 / 0.210 | 0.79 | 0.02* |
| F2 | yt (4) | 0.321 | 0.138 | 0.293–0.357 | 0.104 / 0.044 | 0.221 / 0.140 | 0.614 / 0.280 | 0.483 / 0.142 | 0.86 | 0.06 |
| F2 | both (6) | 0.547 | 0.215 | 0.505–0.577 | 0.168 / 0.087 | 0.359 / 0.244 | 0.808 / 0.432 | 0.739 / 0.256 | 0.74 | — |

\* In the `all` rows, `both` searches count as 0 cross share.

Every method scores 0 on g05 (both · name/time).

## Comparisons vs C0 (paired)

| Comparison | Scope (n) | **Δ nDCG@10 pooled** [95% CI] | W/L/T | Per repeat | Δ R@10 | Δ R@50 | Δ MRR | Seed-only Δ [CI], W/L/T |
|---|---|---|---|---|---|---|---|---|
| **E1 vs C0** | all (10) | **+0.030** [−0.015, +0.076] | 6/3/1 | +0.043, +0.016, +0.032 | +0.001 | +0.016 | −0.007 | +0.004 [−0.027, +0.040], 3/4/3 |
| | yt (4) | −0.006 [−0.075, +0.067] | 1/3/0 | +0.005, −0.021, +0.000 | −0.012 | −0.001 | −0.003 | −0.026 [−0.071, 0.000], 0/2/2 |
| | both (6) | **+0.054 [+0.008, +0.107]** | 5/0/1 | +0.069, +0.040, +0.052 | +0.009 | +0.027 | −0.010 | +0.024 [−0.007, +0.068], 3/2/1 |
| **F0 vs C0** | all (10) | +0.005 [−0.034, +0.051] | 4/4/2 | +0.001, +0.001, +0.012 | −0.002 | +0.016 | −0.006 | +0.009 [−0.009, +0.039], 2/3/5 |
| | yt (4) | **−0.049 [−0.095, −0.016]** | 0/4/0 | −0.063, −0.043, −0.042 | −0.020 | −0.008 | 0.000 | −0.006 [−0.017, 0.000], 0/1/3 |
| | both (6) | **+0.040 [+0.003, +0.093]** | 4/0/2 | +0.044, +0.030, +0.047 | +0.009 | +0.032 | −0.009 | +0.019 [−0.008, +0.065], 2/2/2 |
| **F2 vs C0** | all (10) | +0.008 [0.000, +0.022] | 2/0/8 | +0.008, +0.005, +0.012 | +0.001 | +0.002 | +0.016 | +0.004 [−0.002, +0.015], 1/1/8 |
| | yt (4) | +0.020 [0.000, +0.052] | 2/0/2 | +0.020, +0.012, +0.029 | +0.003 | +0.005 | +0.042 | +0.011 [−0.005, +0.038], 1/1/2 |
| | both (6) | 0.000 | 0/0/6 | 0, 0, 0 | 0 | 0 | −0.001 | 0.000, 0/0/6 |

### Per kind, Δ nDCG@10 vs C0 (pooled; seed-only in brackets)

| Kind (n) | E1 | F0 | F2 |
|---|---|---|---|
| topic (7) | +0.044 (+0.003) | +0.008 (+0.013) | +0.002 (−0.001) |
| structure (6) | +0.019 (+0.003) | −0.026 (−0.001) | +0.012 (+0.009) |
| name (3) | −0.036 (−0.035) | −0.010 (−0.007) | **+0.027** (+0.015) |
| task (3) | **+0.100** (+0.043) | +0.077 (+0.041) | 0 (0) |
| vibe (3) | +0.035 (−0.008) | +0.002 (−0.005) | +0.023 (+0.017) |
| time (1) | 0 | 0 | 0 |

### Robustness (pooled; paired bootstrap, 20 seeds × 10k samples)

| Arm vs C0 | Δ | Lower bound range | Seeds with lower bound > 0 | Drop best 1 / 2 searches | Top-3 share of net gain |
|---|---|---|---|---|---|
| E1 | +0.030 | −0.015 to −0.013 | 0 / 20 | +0.015 / +0.002 | 126% |
| F0 | +0.005 | −0.037 to −0.035 | 0 / 20 | −0.013 / −0.022 | >100% |
| F2 | +0.008 | 0.000 | 0 / 20 | +0.001 / 0.000 | 100% (two searches) |

**Where the gains and losses are, by `g`-number:**
- **E1.** Wins: g10 (both · task/topic) +0.17, g07 (both · topic/vibe/task) +0.12, g06 (yt · topic/structure) +0.09; three small wins under +0.02. Largest loss: g08 (yt · name/topic) −0.10.
- **F0.** It shares the g10 (+0.16) and g07 (+0.06) wins. It loses g06 (−0.12) and g01 (yt · topic/vibe/structure, −0.05).
  - On g06, E1 keeps the YouTube te rows and wins, while F0 drops them and lets Instagram items in.
- **F2.** Two wins, g04 (yt · name/structure/vibe) +0.07 and g08 +0.01. Ties everywhere else.

## F2: creator search on the searches where it fired

- `creator_lookup` fired on g05 (3 of 3 repeats), g08 (3 of 3) and g04 (2 of 3): 2, 3 and 3 searches per repeat, as the runner reported.
- On the 22 cells where it did not fire, F2 equals C0 exactly (Δ 0.000 on every metric).

| Subset | Searches / cells | C0 nDCG@10 | F2 nDCG@10 | Δ (pooled) | W/L | Δ seed-only | Δ MRR | Δ P@10 |
|---|---|---|---|---|---|---|---|---|
| Creator searches (g04, g05, g08) | 3 searches | 0.239 | 0.266 | **+0.027** | 2/0 (1 tie) | +0.015, 1/1 | | |
| Fired cells | 8 cells | | | +0.030 | 3/1 | | +0.061 | +0.013 |
| Other searches | 7 searches / 22 cells | 0.538 | 0.538 | 0.000 | 0/0 | 0.000 | 0 | 0 |

**Rank of the first gold-2 item** (Derrick's own grade 2), C0 vs F2, per repeat r1 / r2 / r3. A * marks a repeat where creator lookup fired.

| Search (scope · kinds) | C0 | F2 | Derrick 2s in top 10, C0 → F2 | What happened |
|---|---|---|---|---|
| g04 (yt · name/structure/vibe) | 3 / 1 / 3 | 3 / 1* / **1*** | 1 / 1 / 1 → 1 / 1 / 1 | Creator search lifted a target item to rank 1 in r3. nDCG +0.07. |
| g05 (both · name/time) | 57 / 64 / 62 | **89* / 74* / 90*** | 0 → 0 | The one *described* creator search. The pick did not choose the target creator, and its items fell further. nDCG 0 for every method. |
| g08 (yt · name/topic) | 3 / 7 / 3 | 3* / 6* / 4* | 4 / 2 / 4 → 4 / 2 / 4 | Almost no change. +0.01. |

For comparison, first gold-2 on g05: E1 64 / 70 / 68 and F0 61 / 66 / 65. No method reaches the target creator in its top 50.

**Reading.**
- Creator search helps slightly when the search **names** the creator: g04 and g08. There the creator's items are already in C0's top 10, so the margin to gain is small.
- On the search it was designed for, a creator remembered only by description, it **made the result worse**. The profile text (te topics, hashtags, own-text words) and the pick did not connect the description to the right creator.
- This is the first held-out search of that type. It is one search, so it is a strong warning, not a measurement.

## Mechanisms: top-10 platform mix

Mean per search, items per top 10 @ share relevant (pooled labels):

| Run | yt searches: YouTube items | yt searches: Instagram items | both searches: Instagram items | both searches: YouTube items |
|---|---|---|---|---|
| C0 | 9.50 @ 0.50 | 0.50 @ 0.00 | 3.22 @ 0.81 | 6.78 @ 0.70 |
| E1 | 9.25 @ 0.48 | 0.75 @ 0.00 | 3.61 @ **0.92** | 6.39 @ 0.70 |
| F0 | 7.83 @ 0.45 | **2.17 @ 0.04** | 3.94 @ 0.90 | 6.06 @ 0.70 |
| F2 | 9.42 @ 0.51 | 0.58 @ 0.00 | 3.39 @ 0.77 | 6.61 @ 0.72 |

- **`both` searches (E1, F0).** te fusion moves 0.4–0.7 slots to Instagram items, and those are more often relevant (0.90–0.92 vs C0's 0.81). This is the confirmed round-4 component, reproduced on fresh searches.
- **`yt` searches (F0).** F0 lets in 4× C0's Instagram items, and almost none are relevant. This is the slot competition found in 4.3, at the milestone and on dev in round 5 (dev yt: 3.02 per top 10 at 0.37), and it is stronger here. E1 keeps the YouTube te rows, so its crowding is mild (0.75).

## Consistency with dev, and verdicts

| Arm | Dev (c4-r5) vs C0 | test2 vs C0 | Rule: positive, W > L, consistent with dev | Verdict |
|---|---|---|---|---|
| **E1** | +0.056 [+0.010, +0.105], 30/8/6; ig +0.073, yt +0.038 (mostly the intent step) | **+0.030 [−0.015, +0.076], 6/3/1**; both +0.054 (5/0), yt −0.006 (1/3) | Positive; 6 > 3; the sign matches dev. The `both` gain matches dev's ig gain. The yt part does not match, and the intent step acted on only 1 of 30 cells. | **Confirmed (narrow), te-fusion part only.** The YouTube side and the intent step stay unconfirmed. It does not meet adoption clause 1: the CI includes 0 and +0.002 is left without the best 2 searches. |
| **F0** | +0.027 [−0.004, +0.062], 20/14/10; ig +0.067, yt −0.014 | +0.005 [−0.034, +0.051], 4/4/2; both +0.040, **yt −0.049 [−0.095, −0.016]** | Not positive in a meaningful sense, and W = L. The scope pattern matches dev, with a larger yt loss. | **Not confirmed.** |
| **F2** | +0.003, 1/0/43 (fired on one search; not judgeable) | +0.008 [0.000, +0.022], 2/0/8 | The sign and W/L pass on 2 searches. There is no dev evidence to be consistent with, and it failed the described-creator search. | **Not confirmed.** It gives a small gain on named-creator searches and fails the case it was built for. |

**Held-out record of E1 over three sets.** This uses the milestone's numbers; `test` and `yt_holdout` were not rescored here.
- `test`: +0.030, 7/5.
- `yt_holdout`: −0.024, 3/6.
- `test2`: +0.030, 6/3.
- In all three sets the gain is on the Instagram and mixed-platform side, and it is absent or negative on pure YouTube searches.

## Cost and latency (run `meta`)

| Run | Calls per search | Per 1k searches | Latency |
|---|---|---|---|
| C0 | qr-v1 | $0.116–0.119 | rewrite p50 1.70–2.05 / p95 1.80–3.35 s; local p95 0.12–0.14 s |
| E1 | qr-v1 + qi-v3 (+ te pass) | $0.29 (+ te pass ≈ $0.18 per 1k items) | rewrite as C0, intent p50 1.95–2.16 s; local p95 0.15–0.30 s |
| F0 | qr-v1 (+ te pass on caption-type items) | $0.116–0.119 (+ te) | total p50 1.84–2.18 / p95 1.93–3.51 s |
| F2 | qr-v1 ∥ qs-v1 + pick on lookup searches | $0.33–0.39† | total p50 2.13–2.48 / **p95 5.43–7.55 s**; lookup searches 4.8–9.0 s |

† Overstated by about $0.12 per 1k, because the run pays for both qr-v1 and qs-v1.

**Spend.** This scoring cost **$0**, with no paid judging. The orchestrator's test2 runs, including F2's 8 pick calls ($0.0025), bring OpenAI to **$0.194** of $9.50. Ledger total, both providers: **$3.969**.

## Problems and caveats

1. **Small n.** 10 searches: 4 `yt` and 6 `both`, with no `ig` scope. Every per-scope CI is wide.
2. **Pooling decides E1's result.** Seed-only, E1 is +0.004 (3/4/3). Pooled, it is +0.030. Its three largest wins (g10, g07, g06) rest mostly on my blind judgments of unvetted or new items. Only about a third of the relevant top-10 items carry Derrick's grades. A Derrick spot-check of the pooled grades on those three searches would firm up the verdict.
3. **te text was not shown to the judge**, as in every round. This slightly disfavours the te arms (E1, F0).
4. **g05 scores 0 for every method,** because the target creator is never in a top 10. It therefore adds only ties to the comparisons, but it is the most informative search for F2.
5. **E1's intent step was tested on only 1 cell.** In repeat 1, qi-v3 returned some intent on 6 of 10 searches, and the guards removed all but one (one more and none in repeats 2 and 3). So the intent step is still untested on held-out data, as at the milestone.
6. **Scorer change** (disclosed above): `test2` was added to the accepted splits. Other splits are unaffected.
7. **Calibration fidelity.** Derrick's scale varies a lot between searches. I followed each search's own scale. A few of his 1s (on g03 and g06) are items that share only a surface word with the search. I did not copy that: surface-only matches got 0. This may make my grades slightly stricter than his on those two searches.
8. **No rule slips** to report. No captions, query texts or IDs were printed to a committed file. Nothing under `/tmp/claude-0/` was read.
