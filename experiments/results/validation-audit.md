# Validation audit (round 8, phase A)

8 Nov 2026. Written by a fresh evaluator-side auditor that built nothing.

- **Scripts:**
  - `experiments/eval/audit_r8.py` covers the sheet, the LLM judge, agreement, power, pooling, depth, leakage and robustness.
  - `score_c4.py` gets the fixes listed below.
- **Per-item work:** `data/all/eval_work/r8_audit/` (gitignored). Aggregates are in `validation-audit.json`.
- **Spend:** $0.051 (gpt-5-mini $0.025, gemini-3.5-flash-lite $0.026; 420 one-line calls through `lib/ai.py`).
- **Labels:** current `evalset.jsonl` (c4-f7 plus the round-8 known-item sets). Recomputed deltas reproduce the reported ones; for example dev H0 − C0 is +0.022, and test2 H5b − C0 is +0.089.
- `data/all/eval_work/` from rounds 4–7 did not survive the upload. Per-search numbers were rebuilt from the surviving run files (`runs/r4.2`, `runs/r7`, `runs/final2`, `runs/final4`) and the label backups.

## Summary

1. **The AI judge is consistent with itself, but only moderately close to Derrick.**
   - Two fresh Claude judges agree at κ 0.66 (relevant vs not). The original round-4–7 grades agree with them at κ 0.54–0.66.
   - Against Derrick's own grades, the same judges reach only κ 0.39–0.43 (60–62% exact).
   - They are slightly *stricter* than Derrick, not more lenient. They grade low-text items about 0.2 points below him (suggestive, CI includes 0).
   - Before this audit there was **no overlap at all** between Derrick-graded and AI-graded pairs, so this had never been measured.
2. **Most past verdicts sit inside the noise.**
   - At the observed per-search spread (median SD of Δ 0.12), the minimum detectable Δ nDCG@10 at 80% power is **0.12 on 10 searches, 0.075 on 21 and 0.05 on 44**.
   - Every dev "near miss" (D1, D4, E4, F0, G4/H0, H5, H5b) and every single held-out set result is below its MDE.
   - The only result well supported in direction is **3-large (H0) over C0**: positive on dev (+0.022), test2 (+0.053) and `yt_holdout` (+0.056), and positive in every re-judging simulation. Its size is not established.
3. **The adoption rule is mis-tuned for this noise.**
   - On 44 searches, clause 1's real bar is "CI > 0", about Δ ≥ 0.036. It catches a true +0.03 only 38% of the time.
   - Clause 2 lets a zero-effect, zero-cost arm through 13% of the time.
   - Across 30 primary dev comparisons, the 3 that passed were near-identical round-4.3 variants. None survives Holm within its round or Benjamini–Hochberg across rounds. The adopted one (E1) failed held-out.
4. **Known-item sets need two fixes before they can carry decisions** (applied):
   - The `known_dev` / `known_test` split leaks: 24% of `known_test` targets are relevant items in `known_dev`, and 91 of 381 test searches sit within 5 minutes of a dev search. Use the session-disjoint 216-search subset.
   - The scorer's MRR counted the grade-1 "later" videos, which are mostly not answers to the search. Use `mrr2` / `s10_2` on the target only.
   - The labels themselves are usable: in the 40-pair hand check, 12.5% are clear noise and 27.5% are noise or doubtful.
5. **Pooling.**
   - It moves deltas in the direction expected (unjudged-as-0 penalises novel arms): +0.07 per unit of unjudged-share gap, r = 0.53.
   - There is no sign that same-family judging inflates novel arms relative to Derrick.
   - Depth-10 is enough for nDCG@10. R@100 and nDCG@20 are too unjudged to decide anything.

## 1. Who graded what

**Inventory** (judged pairs on the 78 graded searches; counts by source):

| Split | AI evaluators, rounds 4–7 (rel / 0) | Seeds | Derrick (rel / 0) |
| --- | --- | --- | --- |
| dev (44) | 503 / 1,285 | Instagram: Muse round-0 seeds 1,215 / 255; YouTube: title/channel rule seeds + round-3 Claude pooling 15,414 / 828 (no provenance log survives for round 3) | 0 |
| `yt_holdout` (11) | 44 / 129 | rule seeds + round 3: 5,637 / 200 | 0 |
| test (13) | 140 / 103 | — | 387 / 30 |
| test2 (10) | 144 / 106 | — | 447 / 17 |

- **The AI judgments log** holds 2,454 grades under 10 judge names:
  - r4.1: 1,066;
  - milestone: 358;
  - r6: 290;
  - r5: 279;
  - test2: 159;
  - r4.2: 81;
  - final7: 76;
  - test2b: 73;
  - r7: 51;
  - r4.3: 21.
- **Derrick's grades** are 881 vetted rule candidates on `test` / `test2` (2: 525, 1: 309, 0: 47). His 5,465 `unvetted_candidates` are unjudged. His round-2 Instagram human-check sheet was never graded.
- **Auto labels:**
  - `known_dev` / `known_test`: 762 search→watch pairs;
  - `ig_known_dev` / `ig_known_test`: 300 model-written searches.
- **Whose grade the relevant top-10 items rest on:**
  - dev (H0): 38% AI, 62% seeds, **0% Derrick**;
  - `yt_holdout`: 25% AI, 75% seeds;
  - test2: 65–67% AI, 33–35% Derrick.
- **Derrick ∩ AI = 0 pairs.** Pooling skips judged items. The held-out evaluators read Derrick's marks to calibrate, but never graded his items blind.

**Measurement made now.** The blind sheet has 210 lines in one shuffle:
- 150 AI-pooled items, stratified over rounds 4–7 by grade (≈ 13 / 13 / 12 per round), at most 3 per search;
- 60 of Derrick's items, 20 per grade.
- It shows the search, Derrick's clarification where one exists, and the item's own text. Friends' items are excluded.
- Four judges graded it independently: two fresh Claude agents (j1, j2), gpt-5-mini (minimal reasoning) and gemini-3.5-flash-lite (minimal thinking). The two LLMs got one call per line, with the rubric text and the item as delimited data.

| Pair (n) | Exact | κ rel vs not | κ 2 vs rest | κ 3-level linear / quadratic | Mean grade (first → second) |
| --- | --- | --- | --- | --- | --- |
| j1 ~ j2, AI items (150) | 0.75 | 0.66 | 0.67 | 0.67 / 0.70 | 1.03 → 1.01 |
| original ~ j1 (150) | 0.66 | 0.54 | 0.62 | 0.58 / 0.67 | 1.03 → 1.03 |
| original ~ j2 (150) | 0.76 | 0.66 | 0.76 | 0.71 / 0.78 | 1.03 → 1.01 |
| original ~ gpt-5-mini (150) | 0.59 | 0.37 | 0.50 | 0.45 / 0.51 | 1.03 → **1.39** |
| original ~ gemini-3.5-flash-lite (150) | 0.70 | 0.61 | 0.63 | 0.62 / 0.69 | 1.03 → 1.28 |
| **Derrick ~ j1 (60)** | 0.62 | **0.39** | 0.55 | 0.47 / 0.51 | 1.00 → 0.95 |
| **Derrick ~ j2 (60)** | 0.60 | **0.43** | 0.49 | 0.46 / 0.52 | 1.00 → 0.88 |
| Derrick ~ gpt-5-mini (60) | 0.63 | 0.48 | 0.59 | 0.54 / 0.61 | 1.00 → 0.90 |
| Derrick ~ gemini (60) | 0.55 | 0.36 | 0.57 | 0.46 / 0.59 | 1.00 → 1.00 |
| Derrick ~ median(j1, j2, gpt-5-mini) (60) | 0.67 | 0.49 | 0.62 | 0.55 / 0.60 | 1.00 → 0.93 |

**Self-consistency:**
- The original grades are as close to a fresh judge as two fresh judges are to each other.
- Weighted back to the real grade mix (mostly 0s), exact agreement is 0.57–0.67. Fresh judges give a 1 to 21–27% of the original 0s and a 0 to about 20% of the original 1s.
- By round, agreement with the original was lowest for round 4 (κ 0.28 / 0.49; r4.1 graded 1,066 items in one pass) and for `both`-scope searches (κ 0.11 / 0.43). It was highest for round 5 (κ 0.82 / 0.88).

**Against Derrick** (Derrick's grade in rows, j1's in columns):

| Derrick | j1: 0 | 1 | 2 |
| --- | --- | --- | --- |
| 0 | 13 | 4 | 3 |
| 1 | 7 | 10 | 3 |
| 2 | 3 | 3 | 14 |

- About a third of Derrick's 1s and 15–20% of his 2s get a 0 from every judge family.
- Caveats:
  - His 0s are rejected rule candidates (hard negatives).
  - His scale varies by search.
  - He can see the video, and the judges see text only.
- **Non-Claude judges are not closer to Derrick in a meaningful way:** κ 0.36 (Gemini) to 0.48 (gpt-5-mini) against 0.39–0.43 for Claude. Self-preference by the Claude family is not visible here.
- gpt-5-mini is much more lenient than everyone on the pooled items (14 of 48 original 0s → 2). It is **not suitable as a sole judge**.

**Does the AI judge lean toward text-rich items?**
- Measured against Derrick, the Claude judges grade `low`-information items 0.22 below him and `ok` items 0.05 above him: a difference of −0.27 [−0.64, +0.11] over 30 / 30 items.
- By caption-length tercile: short −0.42, mid +0.25, long −0.18.
- The LLM judges show a smaller lean (−0.07).
- The original round-4–7 grades show no richness pattern against the fresh judges (+0.08 / −0.06 / +0.01).
- **Reading:** a modest, not significant under-crediting of thin items. If real, it penalises arms that surface thin items: te lists, a future visual pass, creator recall.

**Robustness of verdicts to judge noise.**
- Method: every one of the 2,454 AI grades was redrawn 100 times from the measured original → fresh-judge transition matrix. Seeds and Derrick's grades stayed fixed.

| Comparison | Δ now | Δ under re-judging, mean [5%, 95%] | Share of draws with CI > 0 |
| --- | --- | --- | --- |
| dev H0 − C0 | +0.022 | +0.020 [+0.010, +0.030] | 0.15 |
| dev H5b − C0 | +0.035 | +0.029 [+0.018, +0.041] | 0.02 |
| dev D4 − C0 | +0.045 | +0.034 [+0.027, +0.041] | 0.09 |
| `yt_holdout` H0 − C0 | +0.056 | +0.064 [+0.045, +0.079] | 0.65 |
| test2 H0 − C0 | +0.053 | +0.041 [+0.009, +0.068] | 0.11 |
| test2 H5b − C0 | +0.089 | +0.072 [+0.036, +0.103] | 0.56 |
| test2 H5b − H0 | +0.036 | +0.032 [+0.015, +0.044] | 0.50 |
| test2 E1 − C0 | +0.030 | +0.022 [+0.001, +0.042] | 0.03 |

- Directions survive re-judging.
- "CI > 0" verdicts on 10–11 searches are a coin flip with respect to who graded the pooled items. On test2, where 2 of 3 relevant top-10 items rest on AI grades, the size moves by about −0.01 to −0.02.

## 2. Power

The per-search paired Δ (mean over 3 repeats) was rebuilt for 18 past comparisons.

- **Spread:**
  - SD of Δ is 0.073–0.165 on dev (median 0.121), 0.081–0.147 on `yt_holdout` and 0.073–0.130 on test2.
  - 52–91% of searches change in an arm-vs-base comparison.
  - Within-repeat rewrite noise alone gives a per-search SD of 0.13 between two repeats of the same run. A single-repeat run differs from another repeat by up to 0.027 in aggregate, so keep three repeats.
- **Minimum detectable Δ nDCG@10** (paired t, 80% power, α = 0.05 two-sided):

| SD of Δ | n = 10 | 21 | 44 | 150 | 381 |
| --- | --- | --- | --- | --- | --- |
| 0.05 (arm touching few searches) | 0.050 | 0.032 | 0.022 | 0.012 | 0.007 |
| **0.117 (median arm)** | **0.116** | **0.075** | **0.050** | 0.027 | 0.017 |
| 0.15 (large arm) | 0.149 | 0.096 | 0.065 | 0.035 | 0.022 |

- **Known-item MRR** (proxy, using two BM25 variants on `known_dev` with the grade-2 target):
  - SD of ΔMRR is 0.135 for a mild change (40% of searches move), giving an MDE of 0.019 on 381 and 0.026 on the 216 clean test searches.
  - success@10 is coarser: SD 0.23, MDE 0.034 on 381.
  - Real arm pairs differ more; with SD 0.25 the MDE is about 0.036 on 381 and 0.048 on 216.
  - Label noise (§6) shrinks true effects by about ×0.75, so in true units these MDEs are about 1.3× larger.
  - Dev nDCG searches' MRR is noisier than nDCG (SD 0.10–0.27).
- **Past verdicts against the MDE:**
  - **Dev (44):**
    - The adopted E1 (+0.056, SD ≈ 0.16 → MDE ≈ 0.068) and its siblings E3 (+0.050) and E2 (+0.034) passed the rule below their own MDE.
    - The "near misses" D1 +0.037, D4 +0.045, E4 +0.050, F0 +0.027, G4 / H0 +0.022, H5 +0.028 and H5b +0.034 are all within noise.
    - Every "part vs H0" result in round 7 (|Δ| ≤ 0.006) is within noise. The data cannot tell "nothing" from "+0.03" for them.
  - **Held-out singles:**
    - milestone test (13) E1 +0.030 and `yt_holdout` −0.024;
    - test2 (10) E1 +0.030, F0 +0.005, G4 +0.053, G5 +0.032.
    - All are within noise (MDE ≈ 0.10–0.12). "G4 confirmed" (round 6) is a direction, not a size.
  - **21 searches pooled (test2 + `yt_holdout`):**
    - H0 − C0 +0.055 [+0.013, +0.103] is below its MDE (≈ 0.075) but has CI > 0. With dev agreeing in sign, it is the best-supported finding of the loop.
    - H5 / H5b − C0 +0.076 / +0.075 reach the MDE.
    - H5b − H0 +0.020 (MDE ≈ 0.044) is within noise.

## 3. Rules and their reuse

- **Clause 1** (Δ ≥ 0.03 and paired CI > 0) on 44 searches, SD 0.12:
  - The CI half-width is 0.035, so the binding bar is CI > 0, about Δ̂ ≥ 0.036.
  - P(pass) is 0.025 at true Δ 0, 0.20 at 0.02, **0.38 at 0.03** and 0.79 at 0.05.
  - On 10 searches, a true +0.05 passes 26% of the time.
  - The rule is strict about false positives per arm and weak at finding real +0.03 gains.
- **Clause 2** (Δ ≥ 0.02, more wins than losses, no extra cost):
  - P(pass | true Δ = 0) ≈ **0.13** on 44 searches and 0.30 on 10.
  - It was used for HyDE (round 1) and for look-first B4, which was withdrawn after test.
  - It should require CI > 0 too, or a held-out confirmation.
- **Many arms:**
  - Rounds 4.1–7 made 30 primary dev comparisons (3–7 per round). Under an all-null world that gives 0.75 expected false passes.
  - 3 passed, all in round 4.3 (E1, E2, E3: near-identical variants on the same searches).
  - With Holm per round (one-sided α 0.025) **none** passes. With Benjamini–Hochberg across all 30, **none** passes.
  - The one adoption (E1) did not hold on held-out (+0.005 over 24).
- **Reuse:**
  - The same 44 dev searches carried about 30 arms over 6 rounds, with per-kind diagnostics given back to builders.
  - Rounds 4–5 dev picks (E1, E3, F0) averaged dev +0.044 → held-out ≈ +0.004: classic winner's curse.
  - Rounds 6–7 picks (G4 / H0, H5, H5b) went from dev +0.022–0.034 to held-out +0.055–0.076. 3-large's gain is larger on the YouTube-heavy held-out sets.
  - So dev deltas are not a reliable estimate in either direction.
- **Diagnosis on test:**
  - test2 and `yt_holdout` were each scored 3 times.
  - test2's per-search failures were diagnosed in `STATE.md`, results notes and `docs/research/` before H5 / H5b and this brief's agenda were written: creator search on named vs described creators, one search carrying 72% of G4's gain, router misreads.
  - H5b − H0 is +0.036 on test2 but +0.005 on `yt_holdout`. That fits optimism on the diagnosed set.
  - One test2 search was paraphrased together with answer details in a committed doc (`docs/research/2026-11-03-query-understanding.md`). It is now redacted to a kind-level description, as are the per-search held-out details in `STATE.md`.
  - `test` keeps 2 scorings but is contaminated for round-5+ ideas.
  - Both test2 and `yt_holdout` are used up; nothing further should be concluded from them.

## 4. Pooling bias

- **Seed → pooled shift:**
  - Over 21 arm comparisons, the shift correlates with the arm's extra unjudged share in its top 10: r = 0.53, slope +0.072 nDCG@10 per unit of share.
  - 15 shifts were up and 1 down.
  - Largest: test2 E1 +0.026 (87% of its reported Δ came from pooled grades); `yt_holdout` H5 +0.021; test2 H5 +0.017.
  - On dev the shifts are ≤ 0.004, because dev labels are deep.
- **Same-agent effect:**
  - The pooling judge is as consistent with fresh judges as fresh judges are with each other.
  - It is slightly stricter than Derrick (−0.05 to −0.12 per item), not more lenient.
  - So arms that surface many unjudged items are not visibly flattered by Claude judging. If anything, thin new items are under-credited (§1).
  - This cannot be separated from true quality without more human grades.
- **Depth:**
  - After pooling, unjudged@10 is 0. But unjudged is 14–24% at ranks 11–20 on dev and 29–41% on held-out, and 65–82% at ranks 21–100.
  - nDCG@20 brackets (unjudged = 0 vs = 1): ±0.01–0.03 on dev, ±0.04–0.06 on held-out.
  - If unjudged items at ranks 21–100 were relevant at the judged rate of ranks 11–20, R@100 would move from 0.34–0.37 to 0.47–0.50 on dev and from 0.40–0.43 to 0.62–0.65 on test2.
  - **Depth-10 is enough for nDCG@10 verdicts. R@100 and nDCG@20 are descriptive only.** A recall-stage decision (candidate depth for a reranker) needs depth-20 pooling for those arms (about 2× judging).

## 5. Leakage paths

| Path | Finding |
| --- | --- |
| Dev texts visible to builders | By design: `queries.jsonl` holds 40 dev, 11 `yt_holdout`, 362 `known_dev` and 150 `ig_known_dev` texts exactly; `evals/qcache` holds 18 dev texts. |
| Held-out texts in method-side files | `test` 13/13 and `test2` 10/10 texts are in `corpus/emb/*_queries/ids.json`. `test2` also appears in `runs/rewrites/test2/` and LLM caches (`cache/r5–r7`). `known_test`: none (only coincidental one-word rewrite keywords). `ig_known_test`: none. |
| Prompt few-shots | 0 five-word overlaps between `experiments/methods/*.py` and any eval search. |
| Committed prose | One dev search (round-1 research note) and one test2 search (docs research note, with answer details) are quoted or paraphrased. |
| Router training searches (`r7/synth_searches`) | 0 dev / held-out copies (1 coincidental short `known_dev` string). |
| `known_dev` ↔ `known_test` split | Random over session-correlated searches: 90 of 381 test targets (24%) are relevant in dev; 119 share some relevant video; 91 test searches sit within 5 min of a dev search; 65 are near-duplicates (word Jaccard ≥ 0.5). Session-disjoint subset: **216**. |
| Known-item labels from method-side data | Targets come from the watch history methods can read. `searched_at` is hidden, so labels can't be rebuilt directly. But any watch-date / watch-count prior favours exactly the 2019–21 watches the labels are made of: judge such features on `known_*` with a control (the same prior on the dev nDCG set). |
| `ig_known` wording | Written from caption + creator + te summary. 42% of query words are in the item's own text, 25% only in te text, 33% in neither. Derrick's real searches against his grade-2 Instagram items: 13% / 7% / 80%. The set is about 3× more lexically matched than real searches: absolute levels are inflated, and te and lexical arms are favoured. The te-to-own ratio is similar (0.60 vs 0.52). |
| Evaluator calibration | Held-out evaluators read Derrick's marks before grading. That is label-side and allowed, but it is why judge-vs-Derrick agreement was never measured. |

## 6. Known-item labels

- **Hand check:** 40 random `known_dev` search→watch pairs (seed 8), using watch timestamps:
  - 25 clear targets (62.5%);
  - 4 broad searches where many videos fit (a channel or topic name; 10%);
  - 6 doubtful (15%);
  - **5 clear noise (12.5%):** an unrelated video watched next. In 2 of them, the query-matching video was watched just *before* the logged search time.
  - No target was autoplay. Search → watch has a median of 12.5 s; 5 of 40 took more than 60 s, and 3 of those 5 were noise.
- **Over all 381 `known_dev`:**
  - 33% of targets share no word of 3+ letters with the search in title or channel. That is an upper bound for noise; it includes paraphrases, misspellings and creator nicknames.
  - In 17%, a query-matching video was watched within 2 minutes before the logged search.
  - The 426 grade-1 "later" videos: 75% share no word with the search, 21% start when the previous video ends (±30 s, autoplay-like), and 14% are bounces (< 20 s).
- **Metrics:**
  - **MRR and success@10 on the grade-2 target are the right primary metrics** (`mrr2`, `s10_2`, added to `score_c4.py`).
  - The scorer's `mrr` / `success5` counted grade-1 later videos as hits. Recall@k with those videos measures autoplay, not search.
  - Unjudged other relevant items (broad searches, about 10%) make MRR a lower bound and compress differences. Arms that diversify or surface other right items lose a little. This is acceptable for paired comparisons, but report success@10 next to MRR, and never compare known-item levels with nDCG sets.
  - The label noise (≈ 12–28%) dilutes effects (≈ ×0.75–0.88) rather than biasing their sign.
  - Reference levels: BM25 over title + channel reaches MRR 0.249 and success@10 0.365 on the target, and misses the target from its top 1,000 in 34% of searches.

## Ranked fixes

| # | Fix | Why | Status |
| --- | --- | --- | --- |
| 1 | Known-item metrics on the grade-2 target only (`mrr2`, `s10_2`); scorer honours every `split.json` split | The old scorer counted autoplay as hits and scored every search in the run for unknown splits | **Applied** (`score_c4.py`, `PROTOCOL.md`) |
| 2 | Score `known_test` on the session-disjoint `known_test_clean` (216) as primary | 24% target overlap with `known_dev` | **Applied** (`labels/known_test_clean_ids.json`, scorer, protocol) |
| 3 | Every report states `sd_d`, MDE, Holm across the round's arms, grade sensitivity (1s → 0, seed-only) and the pooled share; "within noise" replaces "near miss" | Verdicts so far mostly sit inside noise | **Applied** (`PROTOCOL.md`) |
| 4 | Pool every unjudged top-10 item every round; R@100 / nDCG@20 descriptive only | Pool shift +0.07 per unit of unjudged gap; ranks 21–100 are 65–82% unjudged | **Applied** |
| 5 | Held-out hygiene: no held-out texts in method-side caches before scoring; no per-search held-out diagnosis in builder-read files | test / test2 texts are in method-side caches; test2 diagnosis shaped round 7 | **Applied** (protocol); orchestrator to enforce |
| 6 | Judge sheets show the intent and the more-like-this examples | Rubric parity with held-out sheets | **Applied** (`judge.py`) |
| 7 | Adoption: dev is a screen (Holm per round); adoption needs a large, fresh held-out confirmation (`known_test_clean` + `ig_known_test` + a fresh Derrick set), with clause 2 requiring CI > 0 | 0 of 30 passes survive multiplicity; clause 2's null pass rate is 13% | **Proposed** (A-005) |
| 8 | Two independent judges per pooled item, adjudicating disagreements; no non-Claude judge as sole grader | Single-judge κ 0.54–0.66; gpt-5-mini is lenient | **Proposed** (A-005) |
| 9 | Derrick grades a 60–80-item blind calibration sheet per new held-out set, weighted to thin items | The only human anchor; κ 0.39–0.43 | **Proposed** (A-005) |
| 10 | Known-item label repair: accept a query-matching video watched ≤ 2 min before the logged search; hand-verify a 100-search subset | 17% possible mis-targeted labels | **Proposed** (A-005): cleaning by word overlap would favour lexical arms |
| 11 | `ig_known`: add a slice generated without te text, or report te arms with this caveat | Query words are 3× more lexically matched than real searches | **Proposed** (A-005) |
| 12 | Redact the test2 paraphrase in `docs/research/2026-11-03-query-understanding.md`, and per-search held-out details in `STATE.md` | Committed query text with answer details | **Applied** (round-8 follow-up) |
