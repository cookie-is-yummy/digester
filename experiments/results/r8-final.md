# Round 8 · final held-out scoring

*9 Nov 2026 · fresh evaluator (built nothing) · aggregates only. **`known_test` scoring 1 of 3 and `ig_known_test` scoring 1 of 3.** Each set was scored once, with all three methods together. Known-item sets, so nothing was pooled or judged, and labels are unchanged (no backup needed). No paid calls. Machine-readable numbers: `r8-final.json`. Per-search detail is in `data/all/eval_work/final8/` (gitignored).*

**Methods** (frozen run files `runs/final8/{h0r8,q8,fm}_{known_test,ig_known_test}_r{1,2,3}.json`, produced by `experiments/eval/final8_heldout.py`):
- **H0r8** is the round-8 base: H0 on the rebuilt vectors, always rewritten.
- **B8.5 = Q8** is the round-8.1–8.5 package: route-r1 instant path, prior-p1, TI te lists, the nano refine gated to YouTube-read rewrite searches, and int8 item vectors.
- **B8.8 = FM** is Q8 with gpt-5-mini in the refine (the finalist).

**Conventions** (as in rounds 8.5–8.8):
- Δ is the mean over 3 paired repeats per search. CI is a 95% paired bootstrap. W/L/T is counted at ±0.005.
- MDE = (t₀.₉₇₅ + t₀.₈) · sd_d / √n.
- p is a one-sided paired t-test for a gain. Holm runs over the **3 comparisons per set** (FM − H0r8, FM − Q8, Q8 − H0r8), separately for each metric.
- Level cells read: mean over repeats (repeat range) [95% CI of the per-search repeat mean].
- PROTOCOL 6f: the primary metrics are `mrr2` and `s10_2` on the grade-2 target. `known_test_clean` (216, session-disjoint) is the primary YouTube set; full `known_test` (381) is secondary.
  - On `ig_known_test`, every search has exactly one relevant item, so mrr = mrr2 and success@10 = s10_2.
- Gain rule as practised in round 8: Δ ≥ 0.03 with CI > 0 (or ≥ 0.02 with W > L at no extra cost). Non-inferiority (NI): point ≥ −0.005 and CI lower bound ≥ −0.03.

## 0. Checks before scoring

- **Never scored before.** Every round-8 evaluator report states that `known_test` and `ig_known_test` were not scored. Builders' LOG blocks state that no rewrite, vector or run was made for them. The audit found no `known_test` / `ig_known_test` texts in method-side caches.
- **Run integrity.**
  - All 18 files hold the full sets (381 / 150), 1,000 deep.
  - The three repeats differ from each other (independent rewrite draws).
  - The refine pass was clean: 0 failed and 0 invalid. Q8 has 3–8 duplicate / missing ids per repeat, which keep their fused order; FM has 0.
  - FM and Q8 differ only on refined searches, and only by reordering the same top-20 set (0 rankings differ below rank 20 or in top-20 membership). This also holds for the FM repeat 3 that was re-run from cache.
  - Refined searches per repeat: `known_test` 43 / 42 / 42, `ig_known_test` 19 / 20 / 19 (22 refined in at least one repeat; the r8.8 evaluator expected 15–20).
- **My scorer matches `score_c4.py`.** I re-ran it on `known_test_clean` and `ig_known_test`, and every level agrees to 3 decimals.
- **My te-bias split reproduces r8.3's.** On `ig_known_dev` it gives the same group sizes (124 / 26 shares / no te word; 64 / 86 te-only / no te-only word).
- **Problem found: the logged cost of repeat 3 is inflated (measurement bug, rankings unaffected).**
  - In `final8_heldout._timed`, the cost of a timing call is the *last ledger row written since the call started*.
  - The 3-large timing pass (ledger 23:39–23:58) ran concurrently with the held-out refine passes (23:55–23:58). So 24 of the 531 repeat-3 timing entries recorded a concurrent nano / mini refine row, up to 50× an embedding's cost. Their costs match `final8_refine_mini` / `final8_refine` ledger rows.
  - The repeat-3 cost per 1k is inflated by about $0.05 for H0r8, $0.03 for Q8 and $0.03 for FM on `ig_known_test`, and by $0.009 for H0r8 on `known_test`.
  - The runner report's means of repeats ($0.146 / $0.112 / $0.163 on `ig_known_test`; $0.130 for H0r8 on `known_test`) are therefore overstated by $0.002–0.016. Corrected figures are in section 5: each inflated entry is replaced by that repeat's median timing cost, and all three repeats then agree within $0.005.
  - Latency is unaffected: the seconds are each call's own.
  - Fix for future runners: take the cost from the ledger row with the call's own purpose, or don't overlap timing and paid passes.

## 1. `known_test_clean` (216 session-disjoint YouTube known-item searches; primary)

| Method | mrr2 | s10_2 | mrr | success@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- |
| H0r8 | 0.299 (0.295–0.303) [0.247, 0.352] | 0.448 (0.431–0.468) [0.383, 0.512] | 0.310 (0.307–0.314) [0.259, 0.364] | 0.463 (0.449–0.481) [0.398, 0.528] | 0.293 (0.288–0.301) [0.247, 0.342] |
| B8.5 (Q8) | 0.301 (0.297–0.306) [0.250, 0.354] | 0.452 (0.449–0.454) [0.386, 0.515] | 0.319 (0.314–0.323) [0.267, 0.374] | 0.471 (0.468–0.472) [0.406, 0.532] | 0.295 (0.293–0.297) [0.248, 0.343] |
| B8.8 (FM) | 0.309 (0.309–0.310) [0.256, 0.363] | 0.451 (0.449–0.454) [0.386, 0.515] | 0.326 (0.326–0.327) [0.274, 0.381] | 0.469 (0.468–0.472) [0.404, 0.534] | 0.300 (0.300–0.301) [0.252, 0.349] |

| Comparison | mrr2 Δ [CI] | W/L/T | per repeat | sd_d | MDE | p | Holm p | s10_2 Δ [CI] | W/L/T | MDE | Holm p | mrr Δ | success@10 Δ | nDCG@10 Δ [CI] |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FM − H0r8 | **+0.0104** [-0.019, +0.040] | 56/42/118 | +0.013 / +0.012 / +0.006 | 0.210 | 0.040 | 0.233 | 0.466 | +0.0031 [-0.034, +0.040] | 15/15/186 | 0.051 | 1 | +0.0159 | +0.0062 | +0.0068 [-0.016, +0.031] |
| FM − Q8 | **+0.0078** [-0.001, +0.018] | 7/3/206 | +0.008 / +0.012 / +0.004 | 0.071 | 0.013 | 0.053 | 0.159 | -0.0015 [-0.009, +0.005] | 1/1/214 | 0.010 | 1 | +0.0070 | -0.0015 | +0.0051 [-0.001, +0.012] |
| Q8 − H0r8 | **+0.0026** [-0.026, +0.031] | 56/45/115 | +0.006 / -0.000 / +0.002 | 0.212 | 0.041 | 0.428 | 0.466 | +0.0046 [-0.032, +0.042] | 15/15/186 | 0.052 | 1 | +0.0089 | +0.0077 | +0.0017 [-0.022, +0.026] |

- **No comparison passes Holm.** All three are within noise: FM − H0r8 has MDE 0.040, and FM − Q8 (+0.0078, MDE 0.013) is the closest, at raw p 0.053.
- **Non-inferiority holds** on mrr2 for every comparison (lowest CI bound: Q8 − H0r8, −0.026). On s10_2, Q8 − H0r8 and FM − H0r8 have CI lower bounds of −0.032 / −0.034, just past the −0.03 line, while their points are +0.005 / +0.003.

**Subsets** (mrr2 Δ [CI], W/L; MDE). The refined and rewrite subsets are by Q8's run meta; "prior reads yt / ig" is q_ig < 0.5 / ≥ 0.5.

| Subset | n | Q8 mrr2 | FM − H0r8 | FM − Q8 | Q8 − H0r8 |
| --- | --- | --- | --- | --- | --- |
| refined_in_q8 | 23 | 0.587 | +0.035 [-0.066, +0.132], 6/3; 0.149 | +0.073 [-0.003, +0.163], 7/3; 0.128 | -0.038 [-0.143, +0.068], 6/6; 0.156 |
| unrefined | 193 | 0.267 | +0.007 [-0.022, +0.036], 50/39; 0.042 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.007 [-0.022, +0.036], 50/39; 0.042 |
| instant | 189 | 0.267 | +0.010 [-0.020, +0.039], 50/36; 0.042 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.010 [-0.020, +0.039], 50/36; 0.042 |
| rewrite | 27 | 0.538 | +0.016 [-0.068, +0.105], 6/6; 0.132 | +0.062 [-0.004, +0.136], 7/3; 0.109 | -0.046 [-0.135, +0.043], 6/9; 0.135 |
| prior_reads_yt | 189 | 0.312 | +0.018 [-0.009, +0.047], 52/35; 0.040 | +0.009 [-0.001, +0.020], 7/3; 0.015 | +0.009 [-0.018, +0.039], 52/38; 0.041 |
| prior_reads_ig | 27 | 0.225 | -0.046 [-0.154, +0.062], 4/7; 0.162 | +0.000 [+0.000, +0.000], 0/0; 0.000 | -0.046 [-0.154, +0.062], 4/7; 0.162 |

## 2. `known_test` (381, full; secondary)

| Method | mrr2 | s10_2 | mrr | success@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- |
| H0r8 | 0.254 (0.252–0.258) [0.219, 0.291] | 0.410 (0.404–0.417) [0.362, 0.458] | 0.271 (0.269–0.275) [0.235, 0.309] | 0.432 (0.425–0.438) [0.384, 0.481] | 0.251 (0.251–0.252) [0.218, 0.285] |
| B8.5 (Q8) | 0.270 (0.266–0.274) [0.232, 0.308] | 0.426 (0.425–0.428) [0.374, 0.478] | 0.290 (0.286–0.294) [0.252, 0.330] | 0.450 (0.449–0.451) [0.399, 0.501] | 0.263 (0.261–0.265) [0.229, 0.299] |
| B8.8 (FM) | 0.278 (0.276–0.280) [0.240, 0.318] | 0.427 (0.425–0.428) [0.375, 0.479] | 0.298 (0.296–0.300) [0.259, 0.339] | 0.451 (0.449–0.451) [0.400, 0.502] | 0.269 (0.268–0.271) [0.234, 0.305] |

| Comparison | mrr2 Δ [CI] | W/L/T | per repeat | sd_d | MDE | p | Holm p | s10_2 Δ [CI] | W/L/T | MDE | Holm p | mrr Δ | success@10 Δ | nDCG@10 Δ [CI] |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FM − H0r8 | **+0.0243** [+0.005, +0.044] | 104/65/212 | +0.029 / +0.018 / +0.026 | 0.194 | 0.028 | 0.0074 | 0.0222 | +0.0166 [-0.010, +0.042] | 31/23/327 | 0.037 | 0.315 | +0.0268 | +0.0184 | +0.0178 [+0.002, +0.034] |
| FM − Q8 | **+0.0087** [+0.002, +0.017] | 15/5/361 | +0.011 / +0.011 / +0.004 | 0.072 | 0.010 | 0.00942 | 0.0222 | +0.0009 [-0.004, +0.006] | 4/2/375 | 0.007 | 0.37 | +0.0083 | +0.0009 | +0.0062 [+0.001, +0.012] |
| Q8 − H0r8 | **+0.0156** [-0.004, +0.036] | 101/71/209 | +0.017 / +0.008 / +0.022 | 0.196 | 0.028 | 0.0599 | 0.0599 | +0.0157 [-0.011, +0.041] | 29/23/329 | 0.037 | 0.315 | +0.0186 | +0.0175 | +0.0116 [-0.005, +0.028] |

- **On the full set, FM − H0r8 (+0.024, Holm 0.022) and FM − Q8 (+0.0087, Holm 0.022) pass Holm on mrr2.** Q8 − H0r8 is +0.016 (Holm 0.060). None of these passes on s10_2.
- **The gap between the full and clean sets comes from the 165 non-clean searches:** Q8 − H0r8 +0.033 [+0.007, +0.061] (45/26), FM − H0r8 +0.043 [+0.018, +0.070] (48/23), FM − Q8 +0.010 [−0.000, +0.021].
  - These searches are session-correlated with `known_dev` and partly share its targets.
  - Read the full-set significance as leak-tilted. The primary clean set does not reproduce it.

| Subset | n | Q8 mrr2 | FM − H0r8 | FM − Q8 | Q8 − H0r8 |
| --- | --- | --- | --- | --- | --- |
| refined_in_q8 | 43 | 0.447 | +0.059 [-0.010, +0.124], 13/5; 0.101 | +0.077 [+0.020, +0.138], 15/5; 0.089 | -0.018 [-0.094, +0.051], 10/11; 0.106 |
| unrefined | 338 | 0.247 | +0.020 [+0.002, +0.041], 91/60; 0.029 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.020 [+0.002, +0.041], 91/60; 0.029 |
| instant | 328 | 0.243 | +0.022 [+0.001, +0.042], 91/57; 0.030 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.022 [+0.001, +0.042], 91/57; 0.030 |
| rewrite | 53 | 0.436 | +0.040 [-0.016, +0.100], 13/8; 0.084 | +0.062 [+0.018, +0.113], 15/5; 0.073 | -0.022 [-0.082, +0.037], 10/14; 0.087 |
| prior_reads_yt | 335 | 0.271 | +0.031 [+0.011, +0.051], 97/56; 0.029 | +0.010 [+0.002, +0.019], 15/5; 0.012 | +0.021 [+0.001, +0.041], 94/62; 0.029 |
| prior_reads_ig | 46 | 0.259 | -0.022 [-0.094, +0.042], 7/9; 0.097 | +0.000 [+0.000, +0.000], 0/0; 0.000 | -0.022 [-0.094, +0.042], 7/9; 0.097 |

## 3. `ig_known_test` (150 synthetic Instagram known-item searches)

| Method | mrr2 | s10_2 | mrr | success@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- |
| H0r8 | 0.369 (0.368–0.372) [0.311, 0.427] | 0.602 (0.573–0.633) [0.531, 0.671] | 0.369 (0.368–0.372) [0.311, 0.427] | 0.602 (0.573–0.633) [0.531, 0.671] | 0.415 (0.406–0.425) [0.354, 0.474] |
| B8.5 (Q8) | 0.479 (0.473–0.489) [0.413, 0.545] | 0.693 (0.687–0.700) [0.627, 0.760] | 0.479 (0.473–0.489) [0.413, 0.545] | 0.693 (0.687–0.700) [0.627, 0.760] | 0.521 (0.514–0.528) [0.454, 0.585] |
| B8.8 (FM) | 0.505 (0.493–0.519) [0.438, 0.570] | 0.713 (0.707–0.727) [0.642, 0.782] | 0.505 (0.493–0.519) [0.438, 0.570] | 0.713 (0.707–0.727) [0.642, 0.782] | 0.546 (0.535–0.560) [0.480, 0.611] |

| Comparison | mrr2 Δ [CI] | W/L/T | per repeat | sd_d | MDE | p | Holm p | s10_2 Δ [CI] | W/L/T | MDE | Holm p | mrr Δ | success@10 Δ | nDCG@10 Δ [CI] |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FM − H0r8 | **+0.1354** [+0.084, +0.186] | 93/23/34 | +0.124 / +0.147 / +0.135 | 0.330 | 0.076 | 0 | 0 | +0.1111 [+0.056, +0.169] | 32/10/108 | 0.084 | 0.00042 | +0.1354 | +0.1111 | +0.1314 [+0.082, +0.179] |
| FM − Q8 | **+0.0255** [+0.006, +0.049] | 8/1/141 | +0.020 / +0.029 / +0.028 | 0.134 | 0.031 | 0.0106 | 0.0106 | +0.0200 [+0.004, +0.038] | 6/0/144 | 0.024 | 0.00981 | +0.0255 | +0.0200 | +0.0255 [+0.007, +0.047] |
| Q8 − H0r8 | **+0.1098** [+0.057, +0.162] | 93/25/32 | +0.105 / +0.118 / +0.107 | 0.337 | 0.078 | 5e-05 | 0.0001 | +0.0911 [+0.033, +0.149] | 31/13/106 | 0.084 | 0.00274 | +0.1098 | +0.0911 | +0.1059 [+0.058, +0.154] |

- **Q8 − H0r8 and FM − H0r8 are large and pass Holm** on mrr2, s10_2 and nDCG@10. Every repeat is positive.
- **FM − Q8 is +0.0255 [+0.006, +0.049], 8/1/141, Holm 0.011** (s10_2 +0.020 [+0.004, +0.038], 6/0, Holm 0.010).
  - It passes the family-wise test, but it is **below the gain-rule threshold (0.03) and below its MDE (0.031)**. Under the round-8 rule it would not be adopted on this set alone: clause 2 does not apply, because FM costs more.
  - All three repeats are positive (+0.020 / +0.029 / +0.028).

**Subsets** (mrr2 Δ [CI], W/L; MDE). "te word" groups follow r8.3's bias check: the search's content words against the generator's te summary, caption and creator fields.

| Subset | n | Q8 mrr2 | FM − H0r8 | FM − Q8 | Q8 − H0r8 |
| --- | --- | --- | --- | --- | --- |
| refined_in_q8 | 22 | 0.298 | +0.203 [+0.075, +0.347], 15/3; 0.208 | +0.174 [+0.051, +0.315], 8/1; 0.199 | +0.029 [-0.121, +0.188], 15/5; 0.233 |
| unrefined | 128 | 0.510 | +0.124 [+0.070, +0.181], 78/20; 0.082 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.124 [+0.070, +0.181], 78/20; 0.082 |
| instant | 50 | 0.449 | +0.002 [-0.096, +0.090], 22/14; 0.137 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.002 [-0.096, +0.090], 22/14; 0.137 |
| rewrite | 100 | 0.494 | +0.202 [+0.142, +0.262], 71/9; 0.087 | +0.038 [+0.010, +0.072], 8/1; 0.046 | +0.164 [+0.100, +0.226], 71/11; 0.092 |
| prior_reads_yt | 36 | 0.193 | -0.025 [-0.158, +0.108], 16/13; 0.200 | +0.103 [+0.025, +0.196], 7/1; 0.125 | -0.128 [-0.255, +0.000], 16/15; 0.188 |
| prior_reads_ig | 114 | 0.570 | +0.186 [+0.138, +0.237], 77/10; 0.075 | +0.001 [+0.000, +0.003], 1/0; 0.003 | +0.185 [+0.137, +0.236], 77/10; 0.074 |
| shares_te_word | 128 | 0.528 | +0.150 [+0.093, +0.209], 82/18; 0.086 | +0.030 [+0.008, +0.058], 8/1; 0.036 | +0.120 [+0.061, +0.181], 82/20; 0.088 |
| no_te_word | 22 | 0.195 | +0.049 [-0.033, +0.157], 11/5; 0.145 | +0.000 [+0.000, +0.000], 0/0; 0.000 | +0.049 [-0.033, +0.157], 11/5; 0.145 |
| te_only_word | 64 | 0.606 | +0.182 [+0.106, +0.266], 39/8; 0.120 | +0.043 [+0.009, +0.090], 5/1; 0.060 | +0.139 [+0.053, +0.227], 39/10; 0.131 |
| no_te_only_word | 86 | 0.385 | +0.100 [+0.030, +0.172], 54/15; 0.099 | +0.012 [+0.000, +0.035], 3/0; 0.030 | +0.088 [+0.023, +0.152], 54/15; 0.095 |

- **FM's increment sits where it did on dev: on searches the prior reads as YouTube** (36: +0.103 [+0.025, +0.196], 7/1). Those are the searches where Q8 loses to H0r8 (−0.128 [−0.255, 0.000]). The prior misreads 24% of `ig_known_test` searches as YouTube, against 14% (21) on `ig_known_dev`.
- **The package's Instagram gain comes from the rewrite path.** Rewrite-routed searches gain +0.164 [+0.100, +0.226] (100). The instant-routed ones gain +0.002 (50), but s10_2 there is −0.060.

## 4. Dev side for comparison (same scorer, current labels c4-r8.8)

These are `runs/r8.1/h0r8`, `runs/r8.5/q8` and `runs/r8.8/fm` scored on the dev known-item sets, with the same three comparisons as above. The dev nDCG@10 set (44) has no held-out counterpart in this scoring, so its round-8 claims (cumulative +0.039 vs H0r8; FM +0.0003 vs Q8) are **not tested here**.

known_dev (381): levels mrr2 H0r8 0.289, B8.5 (Q8) 0.282, B8.8 (FM) 0.286; s10_2 H0r8 0.451, B8.5 (Q8) 0.446, B8.8 (FM) 0.449

| Comparison | mrr2 Δ [CI] | W/L/T | MDE | Holm p | s10_2 Δ [CI] |
| --- | --- | --- | --- | --- | --- |
| FM − H0r8 | -0.0031 [-0.020, +0.017] | 88/88/205 | 0.026 | 1 | -0.0026 [-0.027, +0.023] |
| FM − Q8 | +0.0037 [-0.004, +0.012] | 10/7/364 | 0.011 | 0.522 | +0.0026 [-0.001, +0.008] |
| Q8 − H0r8 | -0.0068 [-0.024, +0.012] | 90/87/204 | 0.026 | 1 | -0.0052 [-0.030, +0.020] |

ig_known_dev (150): levels mrr2 H0r8 0.425, B8.5 (Q8) 0.555, B8.8 (FM) 0.595; s10_2 H0r8 0.633, B8.5 (Q8) 0.809, B8.8 (FM) 0.831

| Comparison | mrr2 Δ [CI] | W/L/T | MDE | Holm p | s10_2 Δ [CI] |
| --- | --- | --- | --- | --- | --- |
| FM − H0r8 | +0.1698 [+0.121, +0.220] | 100/14/36 | 0.071 | 0 | +0.1978 [+0.138, +0.262] |
| FM − Q8 | +0.0401 [+0.018, +0.065] | 12/0/138 | 0.036 | 0.00097 | +0.0222 [+0.004, +0.042] |
| Q8 − H0r8 | +0.1297 [+0.080, +0.184] | 95/20/35 | 0.074 | 0 | +0.1756 [+0.111, +0.244] |
- prior_reads_yt (21): FM − H0r8 +0.229 [+0.074, +0.403], 14/2; FM − Q8 +0.267 [+0.135, +0.411], 10/0; Q8 − H0r8 -0.038 [-0.213, +0.131], 9/8
- shares_te_word (124): FM − H0r8 +0.178 [+0.129, +0.231], 83/11; FM − Q8 +0.025 [+0.007, +0.048], 7/0; Q8 − H0r8 +0.153 [+0.099, +0.209], 80/16
- no_te_word (26): FM − H0r8 +0.129 [-0.008, +0.276], 17/3; FM − Q8 +0.112 [+0.026, +0.219], 5/0; Q8 − H0r8 +0.017 [-0.109, +0.137], 15/4
- te_only_word (64): FM − H0r8 +0.148 [+0.086, +0.209], 41/5; FM − Q8 +0.009 [+0.000, +0.029], 1/0; Q8 − H0r8 +0.139 [+0.072, +0.204], 41/6
- no_te_only_word (86): FM − H0r8 +0.186 [+0.113, +0.259], 59/9; FM − Q8 +0.063 [+0.028, +0.105], 11/0; Q8 − H0r8 +0.123 [+0.049, +0.197], 54/14

## 5. Cost and latency (run meta; mean of 3 repeats, with range)

| Set · method | $ / 1k typed, logged | $ / 1k, corrected (sec. 0) | Total p50 / p95 | First screen p50 / p95 | Refined screen p50 / p95 (n refined) | Instant share |
| --- | --- | --- | --- | --- | --- | --- |
| `known_test` · H0r8 | 0.1297 (0.126–0.136) | **0.1279** | 1.97 / 2.25 s | (= total) | — | 0 |
| `known_test` · Q8 | 0.0287 | **0.0287** (−78%) | 0.58 / 3.53 s | 0.58 / 2.21 s | 3.50 / 3.84 s (42.3) | 0.86 |
| `known_test` · FM | 0.0674 | **0.0674** (−47%; +135% vs Q8) | 0.58 / 3.80 s | 0.58 / 2.19 s | 3.77 / 4.41 s (42.3) | 0.86 |
| `ig_known_test` · H0r8 | 0.1462 (0.130–0.178) | **0.1304** | 1.98 / 2.30 s | (= total) | — | 0 |
| `ig_known_test` · Q8 | 0.1117 (0.102–0.131) | **0.1019** (−22%) | 2.10 / 3.55 s | 2.05 / 2.47 s | 3.50 / 3.82 s (19.3) | 0.33 |
| `ig_known_test` · FM | 0.1632 (0.152–0.182) | **0.1534** (+18%; +51% vs Q8) | 2.10 / 3.82 s | 2.06 / 2.48 s | 3.78 / 4.34 s (19.3) | 0.33 |

- **Both splits together** (531 typed, repeat 1, which has no inflated entries): H0r8 $0.127, Q8 $0.049 (−61%) and FM $0.092 (−28% vs H0r8, +86% vs Q8).
  - On dev all-typed, round 8 reported $0.128 / $0.055 / $0.103.
- **Refine call seconds** (p50 / p95): nano 1.30–1.34 / 1.59–1.62 s; mini 1.61–1.62 / 2.13 s.
- **First screen.** Q8 and FM are 71% faster than H0r8 at p50 on `known_test`, and about +0.07 s slower on `ig_known_test`, where 67% of searches are rewrite-routed and the te call is added.
  - The refined screen arrives about 3.5 s (Q8) / 3.8 s (FM) after the search.
  - Total p95 is +1.3 s (Q8) / +1.5 s (FM) over H0r8.

## 6. Round-8 claims against the held-out sets

| Claim (dev side) | Held-out | Verdict |
| --- | --- | --- |
| **Package (Q8) gains on Instagram known items:** `ig_known_dev` mrr2 +0.130 [+0.080, +0.184] vs H0r8 (P 8.2, TI 8.3, carried to 8.5) | `ig_known_test` **+0.110 [+0.057, +0.162]**, 93/25, Holm 1e-4; s10_2 +0.091 (dev +0.176) | **Confirmed in direction and significance; about 85% of the dev size** on mrr2, about half on s10_2 |
| **The package costs YouTube known items a little:** `known_dev` mrr2 −0.007 (TI −0.004, CI < 0) | `known_test_clean` +0.003 [−0.026, +0.031]; full +0.016 [−0.004, +0.036] | **Loss not reproduced.** Non-inferior on mrr2 (clean); a flat-to-small gain, within noise |
| **The instant path (R) is non-inferior on short YouTube searches** | clean instant-routed (189): +0.010 [−0.020, +0.039]; full (328): +0.022 [+0.001, +0.042] | **Confirmed** (no loss) |
| **FM gains over Q8 on Instagram:** `ig_known_dev` +0.040 [+0.018, +0.065], 12/0, Holm 0.002 | `ig_known_test` **+0.0255 [+0.006, +0.049]**, 8/1, Holm 0.011 | **Direction and family-wise significance confirmed; the size is not.** About 64% of the dev size, below the 0.03 gain threshold and the MDE (0.031) |
| **FM's gain sits on searches the prior misreads as YouTube** (dev 17 refined: +0.354) | prior-reads-yt (36): +0.103 [+0.025, +0.196], 7/1; refined (22): +0.174 | **Confirmed** (same mechanism, smaller) |
| **Mini ≈ nano on YouTube targets** (`known_dev` +0.0037; refined 46: +0.031 within noise) | clean +0.0078 [−0.001, +0.018] (refined 23: +0.073 [−0.003, +0.163]); full +0.0087 [+0.002, +0.017], Holm 0.022 (refined 43: +0.077 [+0.020, +0.138]) | **Not confirmed as "no gain".** Held-out shows a small YouTube gain on refined searches; it is not significant on the primary clean set |
| **Cumulative FM vs H0r8:** `ig_known_dev` +0.170, `known_dev` −0.003 | `ig_known_test` +0.135 [+0.084, +0.186]; clean +0.010 [−0.019, +0.040]; full +0.024 (Holm 0.022, leak-tilted) | **Instagram confirmed (≈ 80%); YouTube flat** (no loss) |
| **Cost −58% (Q8) at equal or better quality** | Q8 −61% on all held-out typed, but mix-dependent: −78% on `known_test`, −22% on `ig_known_test`. FM −28% vs H0r8, +86% vs Q8 | **Confirmed on the mix of typed searches; the saving shrinks on rewrite-heavy mixes** |
| **Round-8 adoption practice** (adopt on one primary set, NI on the others; P / TI / FM adopted on `ig_known_dev` alone) | Every `ig_known_dev`-driven gain replicates in direction on `ig_known_test`, at 64–85% of the dev size; no YouTube-side loss appears | **Supported in direction.** Sizes shrink (regression to the mean), and the confirming set shares the dev set's generator bias (next section) |

### The `ig_known` te-bias question

`ig_known_test` was made by the same generator from the same inputs (caption, creator, te summary) as `ig_known_dev`. A held-out confirmation therefore shows that the gains generalise to **new searches of the same synthetic kind**. It cannot show that the gains carry over to real people's Instagram searches.

The split by shared words looks as it did on dev:

| Group (`ig_known_test`) | n | Q8 − H0r8 mrr2 | dev (`ig_known_dev`) | FM − Q8 mrr2 | dev |
| --- | --- | --- | --- | --- | --- |
| shares ≥ 1 word with the te summary | 128 | +0.120 [+0.061, +0.181] | +0.153 (124) | +0.030 [+0.008, +0.058], 8/1 | +0.025 |
| shares **no** te-summary word | 22 | +0.049 [−0.033, +0.157] (MDE 0.145) | +0.017 (26) | 0.000 (none refined) | +0.112 (5/0) |
| has a te-only word (not in caption / creator) | 64 | +0.139 [+0.053, +0.227] | +0.139 (64) | +0.043 [+0.009, +0.090], 5/1 | +0.009 |
| no te-only word | 86 | +0.088 [+0.023, +0.152] | +0.123 (86) | +0.012 [0.000, +0.035], 3/0 | +0.063 |

- **The package's gain survives the bias-robust reading.** On searches with no te-only word it is +0.088, CI > 0, about 80% of the full-set gain. That is at the top of r8.3's unbiased estimate for TI (+0.03 to +0.08).
  - The no-shared-word subset is small and within noise both times (+0.049 held-out, +0.017 dev).
- **FM's held-out increment leans on te-word-sharing searches** (te-only +0.043 vs no-te-only +0.012), which is the opposite of dev (+0.009 vs +0.063). The rf-v1 prompt carries the te summary hint, so a text-reading reranker profits from the same lexical overlap.
  - With 8/1 searches this is indicative only, but it gives no reason to read FM's Instagram gain as bias-free.
- **To settle it:** real Instagram known-item searches written by a person who did not see the te summary (for example a Derrick set of 30–40), not another synthetic split.

## 7. Grade sensitivity, pooled share, and what is not covered

- **Grades and pooling (PROTOCOL 6c/6d) do not apply.** Known-item sets are not pooled, no new grades exist, and the labels are unchanged. mrr2 / s10_2 already set grade-1 items to 0, and the any-grade mrr / success@10 tell the same story on `known_test`.
- **Not covered:** the dev nDCG@10 claims (FY / TFY +0.038 on graded topic searches; cumulative dev +0.039). No graded topic held-out set was scored: `test` has 2 scorings left but is contaminated for round-5 ideas, and `test2` is used up.
- **Remaining scorings:** `known_test` 2, `ig_known_test` 2. This report and the JSON hold aggregates and groups of ≥ 3 searches only. No per-search diagnosis was written anywhere builders read.
- **No LOG row exists** for this final scoring (unlike Y7-F in round 7), so step 7 had nothing to fill. The orchestrator may want to add one.

## 8. Summary for the orchestrator

1. **On real YouTube known items (`known_test_clean`), the three methods are indistinguishable:** H0r8 0.299, Q8 0.301, FM 0.309 mrr2. No comparison passes Holm, and none loses. The round's small dev-side YouTube loss does not replicate.
2. **On synthetic Instagram known items, the package's large gain replicates** (+0.110, Holm 1e-4), and **FM's increment replicates in direction, at a smaller size** (+0.026, Holm 0.011, below the 0.03 bar and the MDE). Both sit on a set that shares the dev set's generator bias.
3. **The cost picture holds.** Q8 is −61% vs H0r8 on held-out typed searches. FM gives back about half of that saving (+86% vs Q8) for +0.026 on synthetic Instagram and +0.008 on YouTube (Holm-significant on the full set only). The logged repeat-3 costs are inflated by a timing / ledger race; use the corrected column.
4. **My recommendation:** the held-out evidence supports **Q8 (B8.5) as the round-8 result without reservation**. It also supports **FM as a defensible but marginal upgrade**: its quality increment is real in direction on both sets, but small, and it costs +$0.043 / 1k typed. If cost matters, Q8 is the better value. If FM is kept, confirm it on real Instagram searches.

## Verifier note (orchestrator, from two independent read-only verifiers)

Both verifiers reproduced every level, Δ, CI, MDE and Holm value within 0.002 and found held-out hygiene intact (no test-only query text in dev caches; no query texts, item codes or captions in `experiments/` or `docs/`). Corrections and qualifications:

- **Cost-logging race:** 40 repeat-3 3-large timing entries (24 `known_test`, 16 `ig_known_test`) took a refine call's cost, not 24; a few 3-small te timing entries in repeats 1–3 were hit too (≤ $0.002 per 1k). Corrected H0r8 `known_test` cost is **$0.127** per 1k (not $0.128). Rankings and latency are unaffected. `final8_heldout._timed` now takes the cost from the call's own ledger row.
- **Instant path on YouTube:** non-inferior on `mrr2`; on the primary `known_test_clean`, `s10_2` for the instant-routed searches is 0.000 [−0.042, +0.042], so non-inferiority is **not shown** on `s10_2` there (too wide).
- **"Dev YouTube loss not confirmed"** should read **untestable at this size**: the dev effect (−0.007) is far below the held-out MDE (0.041 clean, 0.028 full).
- **"mini no better than nano on YouTube: not confirmed"** is better read as **inconclusive, leaning small gain** (clean +0.008 [−0.001, +0.018], Holm 0.16).
- **Q8 is confirmed as the round-8 result, with reservations** (te bias shared by `ig_known_test`; `s10_2` non-inferiority on the clean YouTube set not shown), not "without reservation".
- Cosmetic: two p-value cells print 0 (true values ≈ 1e-6); the dev FM − Q8 Holm on `ig_known_dev` is 0.001 in the 3-comparison family.
