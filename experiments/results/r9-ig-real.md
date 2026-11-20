# Round 9, Phase 0: the first real Instagram check (`ig_real`, scoring 1 of 3)

Written 9 Nov 2026 by the round-9 evaluator, which built none of the methods scored here. This file holds aggregates only. Per-search numbers, the sheet and the grades are under `data/all/eval_work/r9.0/` (gitignored). Numbers are in `r9-ig-real.json`.

## Headline

**Q8's Instagram gain does not clearly hold on real searches.**

- **Topic searches (22).** Q8 − H0r8 is **+0.039** nDCG@10 [−0.013, +0.090], 13/8/1. That is within noise: the MDE is 0.080 and Holm p is 0.17. The direction is positive, and the gain clears the family-wise test only under the lenient higher-grade rule.
- **Known-item searches (8).** Q8 − H0r8 is **−0.025** mrr2 [−0.244, +0.132], 4/2/2. With an MDE of 0.34, this slice can tell us nothing either way.
- **Compared with `ig_known_test` (+0.110 mrr2):**
  - The rank of Derrick's own target, over all 31 searches, moves **+0.010** mrr2 [−0.049, +0.058] for Q8 − H0r8.
  - The upper end of that CI is about half of +0.110, so a synthetic-sized gain on target rank is unlikely on real searches. Caveat: on topic searches the target is one good answer among several.
- **Real searches are much harder than the synthetic set.**
  - Known-item mrr2 is 0.12–0.15 here, against 0.37–0.48 on `ig_known_test`.
  - The target is on the first screen (top 10) in 29% (H0r8) to 42% (Q8) of known-item searches.
- **FM − Q8 rests on one search.** On `ig_real` the refine fires for 2 of 31 searches, and FM differs from Q8 on 1 of 22 topic searches. FM − H0r8 (+0.054, Holm 0.046) is therefore Q8's within-noise gain plus that one search.
- **The rest of the round builds on Q8 either way**, as BRIEF-9 says.

## Set and method

**Methods.** H0r8, Q8 and FM, 3 repeats each, are in `runs/r9/*_ig_real_r{1,2,3}.json`. The runner is `eval/final8_heldout.py --splits ig_real`.

**`ig_real`.** 31 searches, all with scope `ig`. Each has Derrick's target at grade 3 (one search has two targets) and an intent line.

| Slice | n | How it is scored |
| --- | --- | --- |
| known_item | 8 | mrr2 / s10_2 on the target only; no pooling |
| topic | 22 | target = 3; every unjudged in-library top-10 item of all three methods (all repeats) pooled and graded by two judges |
| meta | 1 | as topic; descriptive only |

**Pooling and judging.**
- **Pool:** 459 items over 23 searches; `unjudged10` after pooling is 0.00 for every method.
- **Judges:** `eval/judges9.py`, rubric j9-v1 (4-point, instance-vs-about, MEANING line shown). A is gpt-5.4-mini; B is gemini-3-flash-preview.
- **Combination rule**, as fixed at setup: if the judges agree, that grade; if they disagree, the lower one. The higher one is the sensitivity check.
- **Merge:** round `r9.0`, judge name "r9.0 two-judge lower-grade (A gpt-5.4-mini + B gemini-3-flash-preview)". Both judges' grades are written to `judgments_log.jsonl`.
  - `evalset.jsonl` was backed up first as `evalset.pre_r9.0b.jsonl`; `pre_r9.0` is the setup backup and was not overwritten.
  - No existing grade was overwritten. `labels/ig_real.jsonl` stays Derrick-only.

**Scoring.**
- **Gains:** nDCG@10 uses gains 0/1/2/3 (`lin4`, primary) and the collapsed 3-point version (`col3`: 3, 2 → 2, then the old 2^g − 1 gains).
- **Scorer change:** `score_c4.py` gained `--gains exp2|lin4|col3`. The default (`exp2`) gives output identical to before on `r8.5/q8` dev.
- **Slices:** `eval/score_r9_igreal.py` does the slices, sensitivities and stats.
- **Stats:** paired Δ is the per-search mean over the 3 repeats. The CI is a 95% bootstrap; W/L/T uses |d| > 0.005. MDE = (t.975 + t.80) · sd_d / √n. p comes from a one-sided paired t-test. Holm runs over the 3 comparisons per slice and metric, with α = 0.025.

## Results

### Known-item slice (8 searches): target only

| | mrr2 | s10_2 |
| --- | --- | --- |
| H0r8 | 0.148 [0.024, 0.349] | 0.292 [0.083, 0.542] |
| Q8 | 0.123 [0.045, 0.208] | 0.417 [0.125, 0.708] |
| FM | 0.123 | 0.417 |

| Comparison | Δ mrr2 | W/L/T | sd_d | MDE | Holm p | Δ s10_2 | Holm p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q8 − H0r8 | −0.025 [−0.244, +0.132] | 4/2/2 | 0.296 | 0.34 | 1.00 | +0.125 [−0.208, +0.417] | 0.76 |
| FM − H0r8 | −0.025 (same) | 4/2/2 | 0.296 | 0.34 | 1.00 | +0.125 | 0.76 |
| FM − Q8 | 0.000 | 0/0/8 | 0 | — | 1.00 | 0.000 | 1.00 |

- All three are **within noise**.
- Any-grade mrr / success10 are identical to mrr2 / s10_2, because the only labels here are the targets.

### Topic slice (22 searches): pooled, two judges, lower-grade rule

| | nDCG@10 lin4 | nDCG@10 col3 | good or exact in top 5 | exact in top 5 | good+ share of top 10 |
| --- | --- | --- | --- | --- | --- |
| H0r8 | 0.678 [0.613, 0.740] | 0.696 | 0.894 | 0.727 | 0.508 |
| Q8 | 0.717 [0.630, 0.786] | 0.730 | 0.894 | 0.833 | 0.558 |
| FM | 0.732 [0.657, 0.792] | 0.748 | 0.924 | 0.864 | 0.568 |

| Comparison (lin4) | Δ | W/L/T | sd_d | MDE | p | Holm p | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q8 − H0r8 | **+0.039 [−0.013, +0.090]** | 13/8/1 | 0.128 | 0.080 | 0.085 | 0.17 | within noise |
| FM − H0r8 | +0.054 [+0.008, +0.099] | 14/7/1 | 0.110 | 0.069 | 0.015 | 0.046 | below MDE; fails Holm at 0.025 |
| FM − Q8 | +0.016 [0.000, +0.047] | 1/0/21 | 0.073 | 0.046 | 0.16 | 0.17 | one search |

| Comparison (col3) | Δ | W/L/T | MDE | Holm p |
| --- | --- | --- | --- | --- |
| Q8 − H0r8 | +0.035 [−0.021, +0.090] | 14/8/0 | 0.086 | 0.25 |
| FM − H0r8 | +0.052 [+0.005, +0.099] | 15/7/0 | 0.071 | 0.063 |
| FM − Q8 | +0.017 [0.000, +0.052] | 1/0/21 | 0.051 | 0.25 |

- "Exact in top 5" is the metric that moves most: Q8 − H0r8 +0.106 [0.000, +0.242], 4/1/17, Holm 0.11.
- "Good or exact in top 5" does not move for Q8 (0.894 for both).

**Meta slice (1 search), descriptive:** nDCG@10 lin4 is 0.493 / 0.497 / 0.497 for H0r8 / Q8 / FM. None of the three has a good or exact item in its top 5.

**Topic + meta (23):** Q8 − H0r8 +0.037 [−0.015, +0.086], 13/8/2, MDE 0.077, Holm 0.17. FM − H0r8 +0.052 [+0.008, +0.095], Holm 0.045.

### Grade sensitivity (topic slice, lin4; col3 in the JSON)

| Labels | H0r8 | Q8 | Q8 − H0r8 | Holm p | FM − H0r8 | Holm p |
| --- | --- | --- | --- | --- | --- | --- |
| Lower rule (primary) | 0.678 | 0.717 | +0.039 [−0.013, +0.090] | 0.17 | +0.054 | 0.046 |
| Higher rule | 0.730 | 0.787 | **+0.056 [+0.014, +0.101]**, 14/7/1, MDE 0.066 | **0.021** | +0.069 | 0.008 |
| This round's grade 1 → 0 | 0.552 | 0.605 | +0.053 [−0.006, +0.112], 13/9/0, MDE 0.093 | 0.11 | +0.070 | 0.024 |
| Seed only (Derrick's target) | 0.071 | 0.110 | +0.038 [−0.019, +0.102], 5/2/15, MDE 0.094 | 0.35 | +0.038 | 0.35 |

- **Where the relevant items come from:** 96.8% of the relevant top-10 items (all three methods, topic + meta) rest on this round's AI grades.
- **Pooled share:** the Δ before pooling (seed only, +0.038) and after (+0.039) are the same size. Pooling does not create the gain; it turns ties into wins and losses (5/2/15 → 13/8/1) and narrows the CI only a little.
- **Direction across rules:** the per-search sign of Q8 − H0r8 is the same under the lower and higher rule for 83% of topic + meta searches.
- **Reading:** on every label variant the gain is positive, at +0.04 to +0.06. It clears the family-wise test only under the lenient rule. On Derrick's own targets it is within noise.

### Groups worth noting (descriptive, n ≥ 3)

- **Caption revealed** before the search was written (6: 3 known-item, 3 topic). Target mrr2 is H0r8 0.218 vs Q8 0.119 (Δ −0.099).
- **Not revealed** (25). Target mrr2 is H0r8 0.034 vs Q8 0.069 (Δ +0.035).
- Searches written with the caption in view favour the lexical baseline. This is the reverse of the te-text bias that `ig_known_test` was suspected of. Too small for inference.

### Cost and latency (from run meta, `ig_real`)

| | $/1k searches | p50 total | p95 total | Paths | YouTube share of top 10 |
| --- | --- | --- | --- | --- | --- |
| H0r8 | 0.131 | 2.25 s | 2.72 s | 31 rewrite | 0.42 |
| Q8 | 0.101 | 2.43 s | 3.91 s | 9 instant / 22 rewrite / 2 refined | 0.21 |
| FM | 0.125 | 2.37 s | 3.54 s | same as Q8 | 0.20 |

- **Cost:** Q8 saves 23% per 1,000 searches here. The −61% was measured on the YouTube-heavy `known_dev`; real Instagram searches are longer, so fewer go instant.
- **Wrong platform:** Q8 halves the share of YouTube items in the top 10 of these Instagram searches.

## Judge disagreement (459 pooled items)

| | Value |
| --- | --- |
| Disagree on 4 points | **28.3%** (one step 25.7%, two steps 2.6%, three steps 0) |
| Disagree on collapsed 3 points | 21.4% |
| Disagree on relevant (≥ 1) vs not | 6.8% |
| Disagree on good-or-better (≥ 2) vs not | 15.0% |
| κ 4-point / linear | 0.61 / 0.74 |
| κ relevant vs not | 0.74 (Instagram items 0.74, YouTube items 0.74) |
| Mean grade A / B | 1.67 / 1.65 |
| Lower-rule grade mix (0 / 1 / 2 / 3) | 86 / 171 / 87 / 115 |
| Per-search 4-point disagreement | median 25%, range 12–55% |

The judges agree with each other better here than on the calibration items (κ 4-point 0.61 vs 0.57). Both are more lenient than Derrick on calibration (setup: mean 1.15 / 1.21 vs his 1.01), and the lower-grade rule only partly corrects for that. That is why the absolute topic numbers (nDCG ≈ 0.7, good-or-exact in top 5 ≈ 90%) are probably optimistic. Use the seed-only row and Derrick-anchored targets for the scorecard (Phase B).

## Budget and hygiene

- **Spend:** $0.241 for judging (gpt-5.4-mini $0.161, gemini-3-flash-preview $0.080, 68 calls each). The ledger now stands at OpenAI $4.931 of $9.70 and Gemini $3.976 of $6.88. That leaves about $0.26 of the brief's "Phase 0 + Phase A tagging < $0.5".
- **Scorings:** `ig_real` has used 1 of its 3 scorings; 2 are left.
- **Hygiene:** no query text, caption, item code or per-search score is in this file or the JSON. Per-search diagnoses were not written anywhere builders read.

## Verifier note (orchestrator, from the read-only verifier)

- Every number reproduces and the conclusions follow from the CIs and MDEs.
- **Judge B on Instagram:** on Derrick's calibration items, judge B (gemini-3-flash-preview) has κ 0.34 on Instagram relevant-vs-not, below BRIEF-9's 0.40 bar; the setup applied the bar to the overall κ (0.45). `ig_real` is all Instagram, so read its pooled grades through the lower-grade combination and the Derrick-targets-only sensitivity (+0.038, Holm 0.35).
- **Held-out contamination:** one `ig_real` search text (a 3-word meta search) appears verbatim in `BRIEF-9.md` as Derrick's own example, so it is not held out for Track 1. Later `ig_real` scorings report results with and without it.
- **Framing:** the comparison with `ig_known_test` (+0.110) uses absolute changes on very different baselines (target mrr2 ≈ 0.07 here vs 0.37–0.48 there); "a gain that size is unlikely" is somewhat overstated.
- Minor: H0r8's YouTube top-10 share is 0.40 as a 3-repeat mean (0.42 was repeat 1).
