# Round 9 · final held-out scoring

*9 Nov 2026 · fresh evaluator (built nothing) · aggregates only. **`facet_test` scoring 1 of 3** (H0r8, Q8 and FM together, once). The per-facet and per-trap breakdowns of `known_test_clean`, `ig_known_test` and `ig_real` re-read the runs already scored (r8-final, r9-ig-real) and use **no new scoring**: the methods and run files are unchanged. Numbers: `r9-final.json`. Per-search detail, sheet, grades and the evaluator-side tags are in `data/all/eval_work/r9.F/` (gitignored). Script: `experiments/eval/final9.py`.*

**Finalist:** Q8 (B8.5). The round-9 loop adopted nothing in 9.1–9.3, so BRIEF-9's stop rule fired and the finalist stays Q8. FM is Q8 with the gpt-5-mini refine.

## Headline

- **facet_test confirms the direction of Q8's real-search gain, and nothing more.** On the 12 "anything like it" searches, Q8 − H0r8 is **+0.047 nDCG@10 lin4 [−0.008, +0.102]**, 8/4/0, MDE 0.091, Holm p 0.21. That is within noise. It is positive in all three repeats (+0.086 / +0.037 / +0.018) and on every label variant except Derrick's own targets.
- **The gain rests entirely on AI pooled grades.** 99% of the relevant top-10 items rest on this step's two-judge grades. On Derrick's targets alone, Q8 − H0r8 is −0.024 [−0.072, 0.000], 0/1/11 (one search). Before pooling the Δ was −0.024; after pooling it is +0.047.
- **Known-item search is still the gap.** On the 3 exact facet_test searches, no method puts the target in the top 10 (hit10 0.00 for all three; target MRR ≈ 0.03). Across all 11 real exact searches (ig_real + facet_test), Q8 has the target on the first screen 30% of the time [9%, 58%]. The proposed target is 80%.
- **FM adds nothing measurable on facet_test.** FM − Q8 is +0.000 [−0.041, +0.038], 2/1/9, MDE 0.062. The refine fired on 4 of 15 searches. FM costs +90% per 1,000 searches here ($0.200 vs $0.105).
- **Real "like" searches, both sets together (35; descriptive, post hoc pooling).** Q8 − H0r8 is **+0.041 [+0.001, +0.078]**, 21/12, MDE 0.057, Holm 0.047. It is within noise and does not pass α 0.025, but this is the first real-search reading with a CI above 0. FM − H0r8 is +0.051 [+0.012, +0.087] (Holm 0.017). FM − Q8 is +0.010, within noise.
- **Per facet and per trap, no cell on a real-search set moves by more than its MDE.** Only the synthetic `ig_known_test` has cells past their MDE: all 150, and looks (52: +0.130 [+0.059, +0.197], MDE 0.102). `known_test_clean` is flat in every cell.
- **The search quoted in BRIEF-9 changes nothing.** `ig_real` without it: topic + meta +0.039 (22) vs +0.037 with it (23); all 31 nDCG +0.034 vs +0.033.
- **The judges are lenient on facet_test, and blind on Instagram relevance.** Mean grade is 2.0 of 3 for both judges. good-or-exact in the top 5 is 1.00 for H0r8 and Q8, so `good5` is at its ceiling and cannot discriminate here. On Instagram items, κ for relevant vs not is −0.01 (almost every item graded ≥ 1 by at least one judge; 4-point exact agreement 49%).

## 0. Checks before scoring

- **Run files** (`runs/r9/{h0r8,q8,fm}_facet_test_r{1,2,3}.json`): all 9 hold the 15 searches, 1,000 deep, with no duplicate ids.
  - H0r8's repeats differ from each other (independent rewrite draws).
  - FM differs from Q8 on 4 searches per repeat, only by reordering the same top 20 (0 searches differ below rank 20 or in top-20 membership).
  - Refine: 4 ok, 0 failed, 0 invalid per repeat. Paths: 6 instant, 9 rewrite.
- **Cost and latency in the run meta match the runner's report** (table in section 1).
- **Hygiene.** No facet_test text sits in any method-side cache or run outside `runs/rewrites/facet_test/` (652 files checked). One 2-word facet_test text occurs once inside item-side YouTube enrichment text: a coincidence in third-party item text, not a query cache.
- **Label integrity.** `evalset.jsonl` was backed up as `labels/evalset.pre_r9.F.jsonl` and `judgments_log.jsonl` as `eval_work/r9.F/judgments_log.pre_r9.F.jsonl`. The merge added 259 rows on 12 searches and skipped 0. No existing grade was changed or removed, Derrick's included. `facet_real.jsonl` stays Derrick-only.

## 1. facet_test (15 hidden searches from Derrick's sheet; 9 IG, 6 YT; scoring 1 of 3)

**How it is scored.**
- `want = exact` (3 searches): target only, target MRR (= mrr2; grade 3 counts as ≥ 2) and hit10 (= s10_2). No pooling.
- `want = like` (12 searches): target = 3. Every unjudged in-library top-10 item of all three methods, all repeats, was pooled: **259 items**. Both judges graded every item (`judges9.py`, rubric j9-v1; A = gpt-5.4-mini, B = gemini-3-flash-preview). The lower grade is primary; the higher grade is the sensitivity.
- Merged as round **r9.F**, judge name "r9.F two-judge lower-grade (A gpt-5.4-mini + B gemini-3-flash-preview)". `unjudged10` is 0.00 for every method afterwards.
- nDCG@10 with gains 0/1/2/3 (`lin4`, primary) and the collapsed 3-point version (`col3`).
- **Stats:** paired Δ is the per-search mean over the 3 repeats. CI is a 95% paired bootstrap; W/L/T at |d| > 0.005. MDE = (t.975 + t.80) · sd_d / √n. p is a one-sided paired t-test. Holm runs over the 3 comparisons per slice and metric (α 0.025).

### Like searches (12): pooled, two judges, lower grade

| | nDCG@10 lin4 | col3 | good or exact in top 5 | exact in top 5 | P@10 | good+ share of top 10 |
| --- | --- | --- | --- | --- | --- | --- |
| H0r8 | 0.721 [0.659, 0.787] | 0.771 | 1.000 | 0.861 | 0.908 | 0.636 |
| Q8 | 0.768 [0.692, 0.842] | 0.819 | 1.000 | 0.861 | 0.931 | 0.689 |
| FM | 0.768 [0.681, 0.849] | 0.822 | 0.972 | 0.833 | 0.964 | 0.683 |

| Comparison (lin4) | Δ [CI] | W/L/T | sd_d | MDE | p | Holm p | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q8 − H0r8 | **+0.047 [−0.008, +0.102]** | 8/4/0 | 0.102 | 0.091 | 0.069 | 0.21 | within noise |
| FM − H0r8 | +0.048 [−0.020, +0.116] | 7/5/0 | 0.124 | 0.110 | 0.106 | 0.21 | within noise |
| FM − Q8 | +0.000 [−0.041, +0.038] | 2/1/9 | 0.069 | 0.062 | 0.49 | 0.49 | within noise |

- **col3** gives the same reading: Q8 − H0r8 +0.048 [−0.013, +0.103] (Holm 0.22); FM − Q8 +0.003.
- **Per repeat (lin4):** Q8 − H0r8 +0.086 / +0.037 / +0.018; FM − Q8 −0.040 / +0.021 / +0.020.
- **By platform (descriptive):** Instagram (8) Q8 − H0r8 +0.012, 4/4, MDE 0.115. YouTube (4) +0.118 [+0.067, +0.183], 4/0, MDE 0.148. The facet_test gain comes from its YouTube like searches. On `ig_real` (all Instagram) the topic gain was +0.039.
- **All 15 searches (lin4, exact searches target-only):** Q8 − H0r8 +0.038 [−0.007, +0.082], 8/4/3, MDE 0.072, Holm 0.21.

### Exact searches (3): target only

| | target MRR | hit10 |
| --- | --- | --- |
| H0r8 | 0.028 | 0.00 |
| Q8 | 0.030 | 0.00 |
| FM | 0.030 | 0.00 |

Q8 − H0r8 is +0.002 [−0.043, +0.050], 1/1/1, MDE 0.145. Three searches cannot show a difference. No method finds any of the three targets on the first screen.

### Grade sensitivity and pooled share (like slice)

| Labels | H0r8 | Q8 | Q8 − H0r8 | Holm p | FM − Q8 |
| --- | --- | --- | --- | --- | --- |
| Lower rule (primary) | 0.721 | 0.768 | +0.047 [−0.008, +0.102], MDE 0.091 | 0.21 | +0.000 |
| Higher rule | 0.824 | 0.868 | +0.044 [+0.001, +0.087], 8/4, MDE 0.072 | 0.13 | +0.002 |
| Higher rule, col3 | 0.862 | 0.911 | +0.049 [+0.013, +0.086], 8/1/3, MDE 0.061 | 0.045 | +0.003 |
| This step's grade 1 → 0 | 0.631 | 0.696 | +0.065 [−0.022, +0.149], MDE 0.140 | 0.27 | −0.014 |
| **Seed only (Derrick's target)** | 0.083 | 0.059 | **−0.024 [−0.072, 0.000], 0/1/11**, MDE 0.074 | 1.00 | 0.000 |

- **Where the relevant items come from:** 99.1% of relevant top-10 items (all methods, like slice) rest on this step's AI grades.
- **Pooled share:** the Δ before pooling (seed) is −0.024; after pooling it is +0.047. All of the reported gain comes from the newly pooled grades. On Derrick's own targets, Q8 ranks one target lower than H0r8 does and ties on the other 11. Target MRR on like searches: H0r8 0.086, Q8 0.053.
- **Direction across rules:** the per-search sign of Q8 − H0r8 is the same under the lower and higher rule for 83% of like searches.
- **Reading:** positive on every AI-label variant (+0.044 to +0.065), never past Holm at 0.025, and slightly negative on Derrick's targets. Same pattern as `ig_real` scoring 1.

### Judge disagreement (259 pooled items)

| | Value |
| --- | --- |
| Disagree on 4 points | 43.6% (one step 39.8%, two steps 3.9%) |
| Disagree on relevant (≥ 1) vs not | 7.3% |
| Disagree on good-or-better (≥ 2) vs not | 15.1% |
| κ 4-point / linear | 0.36 / 0.57 |
| κ relevant vs not | 0.54 [0.34, 0.72]; Instagram items **−0.01**, YouTube items 0.57 |
| Mean grade A / B | 2.02 / 2.04 |
| Lower-rule grade mix (0 / 1 / 2 / 3) | 32 / 73 / 71 / 83 (higher rule: 13 / 53 / 45 / 148) |

- **Instagram κ near 0 is mostly prevalence, not chaos.** Few Instagram items get a 0 from either judge, so relevant vs not carries almost no signal there. 4-point agreement on Instagram items is 49% (YouTube 65%).
- **Leniency:** both judges' mean (2.0) is far above Derrick's calibration mean (1.01 on the 3-point scale; setup κ). Absolute facet_test levels (nDCG ≈ 0.77, good5 = 1.00) are optimistic. Use Derrick's targets and the scorecard's anchored readings for "good enough".

### Cost and latency (run meta, facet_test, 3 repeats)

| | $ / 1k searches | total p50 | total p95 | Paths |
| --- | --- | --- | --- | --- |
| H0r8 | 0.131 | 3.3–3.5 s | 3.4–4.0 s | 15 rewrite |
| Q8 | 0.105 (−20%) | 3.2 s | 5.2–5.9 s | 6 instant / 9 rewrite / 4 refined |
| FM | 0.200 (+90% vs Q8) | 3.2–3.3 s | 5.7–5.8 s | same as Q8 |

## 2. Real searches together (descriptive; not a new scoring)

`ig_real` scoring 1 and `facet_test` scoring 1 read together: same methods, same labels rules (two judges, lower grade). The grouping was chosen after both were scored, so it is descriptive.

| Group | n | H0r8 | Q8 | FM | Q8 − H0r8 | FM − H0r8 | FM − Q8 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Like searches, nDCG@10 lin4 | 35 | 0.687 | 0.728 | 0.738 | **+0.041 [+0.001, +0.078]**, 21/12, MDE 0.057, Holm 0.047 | +0.051 [+0.012, +0.087], MDE 0.055, Holm 0.017 | +0.010 [−0.010, +0.036], 3/1, MDE 0.034 |
| Like searches, good5 | 35 | 0.905 | 0.905 | 0.914 | 0.000, 2/1 | +0.010 | +0.010 |
| Exact searches, target hit10 | 11 | 0.21 | 0.30 [0.09, 0.58] | 0.30 | +0.091, 3/2, MDE 0.40 | same | 0 |
| Exact searches, target hit5 | 11 | 0.09 | 0.18 | 0.18 | +0.091, 3/1, MDE 0.35 | same | 0 |
| All 46, target MRR | 46 | 0.071 | 0.069 | 0.069 | −0.002 [−0.044, +0.034], 11/7, MDE 0.061 | same | 0 |

- On Derrick's real searches, Q8 orders the first screen better by AI grades, within noise, and does not move his own targets.
- FM − H0r8 passes Holm on the pooled like group only. FM − Q8 does not.

## 3. Per facet and per trap (Q8 − H0r8 and FM − Q8, MDE per cell)

**Tags.** Evaluator-side only (`eval_work/r9.F/heldout_tags_EVALUATOR_ONLY.json`).
- `known_test_clean` and `ig_known_test` were tagged in this step with the Phase A tagger r9c-v2 (366 searches; rules for every facet but creator, gpt-5.4-nano for creator, examples-of and shorthand).
- `ig_real` uses the Phase A evaluator-side tags. `facet_test` facets are Derrick's own `based_on` ticks; its traps come from the tagger.
- Cells with fewer than 3 searches are suppressed. A search counts in every facet and trap it carries. "none" = no trap.
- Format: Δ [CI], W/L, MDE. **No cell below is past its MDE unless bold.**

### known_test_clean (216 YouTube known-item, mrr2; scoring 1 re-read)

All: Q8 0.301; Q8 − H0r8 +0.003 [−0.026, +0.031], 56/45, MDE 0.041; FM − Q8 +0.008 [−0.001, +0.018], 7/3, MDE 0.014.

| Cell | n | Q8 mrr2 | Q8 − H0r8 | FM − Q8 |
| --- | --- | --- | --- | --- |
| creator, named | 94 | 0.264 | +0.028 [−0.009, +0.068], 22/20, 0.054 | +0.004, 1/1, 0.016 |
| topic | 192 | 0.320 | −0.008 [−0.038, +0.021], 47/41, 0.042 | +0.009 [0.000, +0.019], 7/3, 0.015 |
| type | 17 | 0.381 | +0.026, 4/5, 0.19 | +0.011, 1/0, 0.032 |
| sound | 8 | 0.426 | +0.043, 3/2, 0.095 | 0 |
| examples | 6 | 0.481 | +0.021, 3/2, 0.23 | +0.102, 1/0, 0.36 |
| looks | 5 | 0.102 | −0.188, 0/2, 0.61 | 0 |
| when | 3 | 0.643 | −0.089, 1/2, 2.5 | +0.006 |
| trap: shorthand | 40 | 0.299 | +0.025 [−0.057, +0.112], 12/5, 0.12 | +0.001 |
| trap: examples-of | 17 | 0.383 | +0.001, 6/4, 0.10 | +0.017, 1/2, 0.12 |
| trap: format word as topic | 15 | 0.366 | +0.018, 3/5, 0.22 | +0.012, 1/0, 0.037 |
| trap: wrapper / negation | 3 / 3 | 0.41 / 0.75 | −0.018 / 0.000 | +0.204 (1 search) / 0 |
| no trap | 146 | 0.275 | −0.004, 36/32, 0.045 | +0.008, 4/1, 0.015 |

s10_2 cells are in the JSON; the largest is examples-of +0.098 [0.000, +0.216], 3/0, MDE 0.17. Suppressed: described creator (2), said (1), count (1).

### ig_known_test (150 synthetic Instagram known-item, mrr2; scoring 1 re-read)

All: Q8 0.479; **Q8 − H0r8 +0.110 [+0.057, +0.162], 93/25, MDE 0.078**; FM − Q8 +0.025 [+0.006, +0.049], 8/1, MDE 0.031.

| Cell | n | Q8 mrr2 | Q8 − H0r8 | FM − Q8 |
| --- | --- | --- | --- | --- |
| topic (= all) | 150 | 0.479 | **+0.110**, 93/25, 0.078 | +0.025, 8/1, 0.031 |
| type | 76 | 0.400 | +0.071 [+0.012, +0.134], 50/11, 0.092 | +0.041 [+0.005, +0.084], 5/1, 0.057 |
| looks | 52 | 0.517 | **+0.130 [+0.059, +0.197], 35/6, 0.102** | +0.002, 1/0, 0.007 |
| creator, named | 12 | 0.743 | +0.126, 6/2, 0.45 | 0 |
| creator, described | 12 | 0.461 | +0.248 [+0.060, +0.453], 8/2, 0.33 | 0 |
| tone | 21 | 0.527 | +0.139, 12/7, 0.34 | +0.087, 3/0, 0.17 |
| examples | 21 | 0.319 | +0.088 [−0.001, +0.184], 13/4, 0.15 | 0 |
| sound | 11 | 0.339 | −0.008, 6/3, 0.33 | 0 |
| platform | 9 | 0.394 | +0.241, 7/2, 0.53 | +0.002 |
| said / when | 5 / 4 | 0.68 / 0.56 | +0.287 / +0.250 (MDE 0.39 / 0.61) | 0 / +0.031 |
| trap: format word as topic | 62 | 0.440 | +0.092 [+0.024, +0.157], 41/7, 0.094 | +0.022, 3/1, 0.044 |
| trap: wrapper | 28 | 0.348 | +0.136 [−0.005, +0.274], 21/5, 0.21 | +0.061, 3/0, 0.12 |
| trap: examples-of | 27 | 0.418 | +0.074, 19/5, 0.20 | 0 |
| trap: described creator | 12 | 0.461 | +0.248, 8/2, 0.33 | 0 |
| trap: shorthand | 5 | 0.566 | +0.263, 3/0, 0.58 | 0 |
| no trap | 49 | 0.554 | +0.089, 24/10, 0.14 | +0.015, 2/0, 0.036 |

FM's increment sits on type searches (+0.041) and the wrapper trap, within noise in every cell. Suppressed: negation (2).

### ig_real (31 real Instagram searches; scoring 1 re-read), with and without the BRIEF-9 search

Metric: nDCG@10 lin4 on the merged labels (known-item searches carry their target only), and target MRR. The search quoted verbatim in BRIEF-9 is the one meta search (found evaluator-side by text match; it carries the examples and examples-of tags).

| Group | With it: n, Q8 − H0r8 | Without it: n, Q8 − H0r8 | FM − Q8 (with / without) |
| --- | --- | --- | --- |
| All, nDCG lin4 | 31: +0.033 [−0.035, +0.099], 16/10, MDE 0.102 | 30: +0.034 [−0.042, +0.101], MDE 0.106 | +0.011 / +0.011 |
| Topic + meta, nDCG lin4 | 23: +0.037 [−0.013, +0.085], MDE 0.077, Holm 0.17 | 22: +0.039 [−0.013, +0.090], MDE 0.080, Holm 0.17 | +0.015 / +0.016 |
| All, target MRR | 31: +0.009 [−0.049, +0.058], MDE 0.083 | 30: +0.010, MDE 0.086 | 0 / 0 |
| type | 17: +0.042 [−0.020, +0.107], 9/6, MDE 0.099 | same | +0.020 |
| looks | 10: +0.055 [−0.015, +0.145], 5/4, MDE 0.137 | same | 0 |
| examples | 8: +0.065 [−0.017, +0.164], 4/2, MDE 0.167 | 7: +0.073, MDE 0.196 | 0 |
| trap: format word as topic | 16: +0.045, 9/6, MDE 0.106 (target MRR +0.042 [−0.002, +0.089], 6/1) | same | +0.021 |
| trap: examples-of | 6: +0.074, 2/1, MDE 0.22 | 5: +0.088, MDE 0.28 | 0 |
| trap: wrapper | 3: −0.210, 1/1, MDE 1.1 | same | 0 |
| no trap | 9: +0.097 [+0.006, +0.189], 6/1, MDE 0.163 | same | 0 |

Suppressed (n ≤ 2): creator, sound, tone, when, platform, shorthand. Excluding the quoted search moves no number by more than 0.015.

### facet_test (15; Derrick's ticks)

All, nDCG lin4: Q8 − H0r8 +0.038 [−0.007, +0.082], 8/4, MDE 0.072; FM − Q8 +0.000, 2/1, MDE 0.048. Target MRR: Q8 − H0r8 −0.025 [−0.080, +0.007], 1/2.

| Cell | n | Q8 nDCG lin4 | Q8 − H0r8 | FM − Q8 |
| --- | --- | --- | --- | --- |
| type | 13 | 0.636 | +0.034 [−0.015, +0.085], 7/4, 0.082 | +0.000, 2/1, 0.056 |
| topic | 12 | 0.640 | +0.043 [−0.013, +0.097], 7/3, 0.090 | +0.000, 2/1, 0.062 |
| looks | 6 | 0.818 | +0.048, 4/2, 0.12 | 0 |
| examples | 5 | 0.744 | +0.026, 3/2, 0.20 | 0 |
| creator | 3 | 0.543 | +0.056, 2/0, 0.19 | +0.046, 1/0 |
| trap: format word as topic | 7 | 0.773 | +0.026, 4/3, 0.15 | +0.007 |
| trap: examples-of / wrapper | 4 / 3 | 0.56 / 0.45 | +0.085 / +0.008 | +0.011 / +0.046 |
| no trap | 4 | 0.403 | +0.051, 2/0, 0.13 | −0.045, 0/1 |

On looks and examples facet_test searches, Derrick's own target is never on any method's first screen (target MRR ≈ 0 for all three).

## 4. Flags

1. **The test-split verdict on Q8 is "direction confirmed, size not".** Three real-search readings agree in sign (ig_real topic +0.039, facet_test like +0.047, both together +0.041) and all rest on AI pooled grades. None passes Holm at 0.025. Derrick's own targets show no gain on either set.
2. **FM is not supported on real searches.** FM − Q8 is +0.016 (ig_real topic, one search) and +0.000 (facet_test like). Its held-out support is synthetic only (`ig_known_test` +0.025) plus a within-noise YouTube +0.008. At +90% cost here, the case for FM over Q8 is weak.
3. **Judge reliability on Instagram is the binding limit.** Relevant-vs-not κ on Instagram items is −0.01 here and 0.34 for judge B on calibration. Instagram pooled grades mostly sort items into 1 / 2 / 3 rather than 0 / not 0. Derrick grading Q8's top 5 on the 20 real like searches (100 items) remains the cheapest anchor (scorecard).
4. **Logging gap (runner, rankings unaffected).** The facet_test rewrite calls are logged under the purpose `c6_query_rewrite`, not `r9_facet_test_*`, although the runner's docstring says purposes carry the split. Ledger totals are right; per-split cost attribution from the ledger is not.
5. **Facet coverage on held-out real searches is thin.** facet_test has no said or when search and one sound, one tone. Those facets are measured only on synthetic or auto-labelled sets.
6. **Scorings left:** `facet_test` 2 of 3; `ig_real` 2 of 3; `known_test_clean` 2; `ig_known_test` 2. BRIEF-9's final list also names `ig_real`, `known_test_clean` and `ig_known_test` scoring 2. Per the orchestrator's LOG note (same methods, same run files), those were re-read as breakdowns and no scoring was spent. The LOG row for this step was not filled in here.

## Budget and hygiene

- **Spend:** $0.200 in this step, all through `lib/ai.py`.
  - Judging: gpt-5.4-mini $0.080 and gemini-3-flash-preview $0.041 (36 calls each).
  - Held-out tagging: gpt-5.4-nano $0.079 (366 calls, purpose `r9_audit_tag`).
  - Runner (before this step): $0.013.
  - Ledger now: OpenAI $5.685 of $9.70, Gemini $5.406 of $6.88.
- **Hygiene:**
  - No query text, caption, title, item code, search id or per-search score is in this file or the JSON (checked by script against all hidden texts, the pooled codes and every split id).
  - Hidden texts were read only evaluator-side. Tags of held-out searches are only under `eval_work/r9.F/`.
  - No per-search diagnosis was written anywhere builders read.
