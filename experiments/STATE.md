# State

## Round 8 (`BRIEF-8.md`) — in progress (started 8 Nov 2026)

- **Setup:** data rebuilt from the split zip into `data/all/`. `corpus/emb/oai512` (3-small, $0.08) and `oai3l_1024` (3-large, $0.52) re-embedded with the id order reconstructed (Instagram = round-1 store order, 20,202; YouTube = titled items in file order, 100,967; total 121,169 = the original count).
- **H0 does not reproduce bit-exactly:** 0 of 55 rankings identical 1,000 deep, but mean top-10 overlap with `r7/h0_r*` is 0.998–1.000 (9–11 of 55 searches differ somewhere in the top 10). Fresh embeddings of the same texts differ at float level. **Round-8 base = `runs/r8_base/h0r8_r{1,2,3}` (H0 on the rebuilt vectors).** The first evaluator scores old vs rebuilt H0 on dev to size the drift. C0 (`r4.2/c0x`) is likewise only approximately reproducible on the rebuilt 3-small store.
- **Budget:** Derrick: $16 OpenAI and $13 Gemini left. Ledger `data/all/ai_runs.jsonl` at start: OpenAI $2.882, Gemini $3.776. Caps: OpenAI $18.0 (env), Gemini **$16.0** (exported per command). Each round < $2.
- **Setup done:** `ig_known_dev` / `ig_known_test` built by an evaluator (150 / 150 synthetic half-remembered searches for saved/collected Instagram items, gemini-3.5-flash-lite, $0.08; `results/r8-ig-known-build.md`).
- **Phase A done** (`results/validation-audit.md`, $0.05): judges agree with each other at κ 0.66 but with Derrick at only κ 0.39–0.49 (slightly stricter, esp. on thin items). Median per-search SD of Δ 0.117 → detectable Δ at 80% power: 0.116 (10 searches), 0.075 (21), 0.050 (44), 0.017 (381). Most past near misses and single held-out verdicts were within noise; no round-4–7 pass survives Holm/BH. known_dev targets are clean in 62.5% of hand-checked pairs; use MRR / success@10 on the grade-2 target only (`mrr2`, `s10_2`); `known_test_clean` (216, session-disjoint) is the primary held-out YouTube set. PROTOCOL.md updated (pool always; MDE, Holm, grade-sensitivity, pooled share in every report; held-out hygiene). **A-005 Proposed** (dev = screen; confirm on large held-out sets; two judges; Derrick calibration sheet).
- **Phase B done** (`docs/research/2026-11-08-architecture-review.md`): the LLM rewrite is ~92% of cost and ~1.8 s of 2.0 s p50 and has never been tested on short keyword searches; ranked options: (1) code query planner with a no-rewrite keyword path, (2) deterministic creator index, (3) LLM refine of the top 20, (4) learned fusion, (5) MCP tool surface, (6) local sparse/late-interaction/quantization for desktop. **A-006 Proposed.**
- **Round 8.1 in flight:** experimenter building H0r8 on `known_dev` / `ig_known_dev`, and arms H5d (deterministic creator search), I (instant path, no rewrite), R (LLM-free shape router).
- **Round 8.1 verdict** (`results/r8.1-eval.md`, labels c4-r8.1): the vector rebuild moved H0 by −0.001 on dev. **R (route-r1) is adopted as cheaper-equivalent by the round-8 rule, marginally.** Cost $0.042 vs $0.128 / 1k and p50 0.37 vs 1.91 s; dev −0.005 [−0.018, +0.007], `known_dev` mrr2 −0.000, `ig_known_dev` +0.006. But the dev point clause fails on seed labels (−0.0095), and the saving comes only from short keyword searches. I fails non-inferiority (dev −0.076). **H5d fails the gain rule** (dev +0.008, within noise) and loses on `known_dev` mrr2 (−0.018 [−0.031, −0.007]), through misread platform calibration, not creator search. **Finalist by the rule: R** (H0r8 plus the instant path for short searches; rewrite-routed searches are identical to H0r8), pending the orchestrator's review of the flags.
- **Orchestrator decision after 8.1:** R accepted as the round-8 base (**B8.1 = `runs/r8.1/route_r*`**), with the evaluator's flags recorded (fragile dev point clause; saving depends on the search mix). Rounds without adoption: 0. Next, round 8.2: platform prior from the user's own library (replacing the misreading calibration), a pared-down package (guarded filters + creator profiles, no calibration / soft time / format), and an LLM refine of the top 20.
- **Round 8.2 verdict** (`results/r8.2-eval.md`, labels c4-r8.2, 46 new pooled grades): **P (prior-p1) is adopted by the round-8.2 rule, driven by `ig_known_dev` alone.** It gives mrr2 +0.031 [+0.003, +0.059], 54/12, at $0 extra (Holm p 0.048, so it passes the rule, not the family-wise test; s10_2 +0.044, Holm 0.014). It is non-inferior on dev (+0.001) and `known_dev` (−0.0042 [−0.0092, −0.0004], point clause by 0.0008). Flags: fragile (CI > 0 lost without the best search); the gain sits on a synthetic single-platform set; dev MRR −0.022, dev yt −0.014; wrong platform reads still cost −0.04 / −0.13. Its read favours the target's platform on 88% / 87% of searches vs 70% / 74% for round 7's text read, and on dev 71% vs 74%. **F (LLM refine of the top 20)** gains on dev, +0.040 [+0.006, +0.080] 18/9, all YouTube (+0.081). That passes the rule but not Holm (0.061), and it is below the MDE. F fails non-inferiority on `ig_known_dev` (−0.022 [−0.063, +0.017]) and costs +80% and +1.4 s p95: **not adopted**. **L (lean)** dev +0.011, within noise; not adopted.
- **Orchestrator decision after 8.2:** P accepted as the base (**B8.2 = `runs/r8.2/prior_r*`**) with the evaluator's flags (gain rests on `ig_known_dev`; tiny `known_dev` loss). Rounds without adoption: 0. Round 8.3: refine gated to YouTube-read rewrite searches; tighter creator-name match in P; te lists for Instagram items only.
- **Round 8.3 verdict** (`results/r8.3-eval.md`, labels c4-r8.3, 8 new pooled grades, 1 relevant): **two arms pass the round rule, each on one set.** **FY (refine gated to rewrite searches read as YouTube)** gives dev +0.032 [+0.005, +0.066] 12/2, all YouTube (+0.058); it is non-inferior on `known_dev` (+0.002) and `ig_known_dev` (+0.001; F's −0.022 loss is gone). It passes the rule, not the family-wise test (Holm 0.069), it is below the MDE (0.045), and CI > 0 is lost without the best 2 searches. It costs +28% per 1k typed searches and +1.2 s p95: **adopted by the rule, driven by dev alone**. **TI (te lists, Instagram items only)** gives `ig_known_dev` mrr2 +0.094 [+0.063, +0.128] 81/16 (Holm < 0.001). It is non-inferior on dev (+0.006 [−0.023, +0.039]) and `known_dev` (−0.004 [−0.009, −0.001], point clause by 0.0009). But that set is the preregistered biased one: searches sharing no word with the target's te summary gain only +0.031 (within noise, 26), and those whose shared words also appear in the caption or creator gain +0.078 (86). Dev ig +0.035 is within noise; dev yt −0.024 and `known_dev` −0.004 are small YouTube losses with CI < 0 (vs B8.1, `known_dev` is now −0.008): **adopted by the rule, driven by `ig_known_dev` alone**, with strong flags. FY and TI were not tested together. **PC (stricter creator match)** is essentially a no-op (0.000 / 0.000 / −0.001): not adopted.
- **Orchestrator decision after 8.3:** TI accepted as the base (**B8.3 = `runs/r8.3/ti_r*`**): its `ig_known_dev` gain survives Holm and the bias split (no-shared-word subset +0.031, within noise), but it costs YouTube searches a little (dev yt −0.024; `known_dev` −0.004). FY passes on dev only and is untested with TI. Rounds without adoption: 0. Round 8.4: (a) te lists gated by the platform prior (Instagram reads only), (b) TI + FY together.
- **Round 8.4 verdict** (`results/r8.4-eval.md`, labels c4-r8.4, 5 new pooled grades, 2 relevant): **TFY (TI + the refine gated to rewrite searches read as YouTube) is adopted by the round rule, driven by dev.** Dev +0.038 [+0.010, +0.071] 12/3 vs B8.3, mostly YouTube (+0.066); it passes the rule **and** the family-wise test (Holm 0.021), but is below the MDE (0.045), so within noise. CI > 0 survives dropping the best 2 searches, and 0–2% of the Δ rests on new grades (no-AI grades +0.040). It is non-inferior on `known_dev` (+0.001) and `ig_known_dev` (−0.004 [−0.022, +0.011], point clause by 0.0012). It costs +28% / 1k typed and +1.2 s p95, as FY did. **TG (te lists only when the prior reads Instagram) is not adopted:** dev −0.001, `known_dev` 0.000, and `ig_known_dev` −0.016 [−0.028, −0.006] 1/17 (NI fail). The gate keys on the wrong searches: TI's `known_dev` loss sits on the 45 YouTube searches P misreads as Instagram (−0.035), which TG keeps, while TG drops TI's gain on the 20 Instagram searches P misreads as YouTube (−0.113). **Cumulative vs H0r8 (rounds 8.1–8.4, TFY as B8.4):** dev +0.040 [−0.007, +0.091] 22/14 (ig +0.053, yt +0.027; within noise, MDE 0.072); `known_dev` mrr2 −0.008 [−0.025, +0.012]; `ig_known_dev` mrr2 +0.127 [+0.075, +0.181] (te-biased set). Cost $0.054–0.055 vs $0.128 / 1k (−58%), typed p50 0.46–0.47 vs 1.90 s (−75%), p95 3.4–3.5 vs 2.2 s (+1.2 s). For B8.3 (TI) vs H0r8: dev +0.002 (yt −0.038), `known_dev` −0.009, `ig_known_dev` +0.130. For B8.3 vs P: dev +0.006, `known_dev` −0.004, `ig_known_dev` +0.094.
- **Orchestrator decision after 8.4:** TFY accepted as the base (**B8.4 = `runs/r8.4/tfy_r*`**). Rounds without adoption: 0. Round 8.5: te-list weight scaled by the platform prior (fixes the misread-as-Instagram side TG missed); int8 and binary (+ float rescoring) quantization of the 3-large item vectors as cheaper-equivalent arms for desktop storage.
- **Round 8.5 verdict** (`results/r8.5-eval.md`, labels c4-r8.5, 9 new pooled grades, 2 relevant): **Q8 (int8 item vectors, no rescoring) is adopted as cheaper-equivalent on storage** (1,024 B / item: −50% vs the float16 file, −75% vs float32 RAM). Every non-inferiority clause passes with margin: dev −0.0012 [−0.004, +0.001], `known_dev` mrr2 +0.0008 [−0.000, +0.002], `ig_known_dev` +0.0032 [−0.000, +0.008]; the unrefined subsets are flat (+0.0002 / +0.0004 / +0.0008). Flags: as run, typed p50 is *worse* (0.59–0.60 vs 0.44–0.45 s), because numpy upcasts int8 (scan 48.8 vs 10.7 ms), so it needs an int8 kernel; s10_2 −0.005 / −0.007 sits at the clause line (within noise; the rule uses mrr2). **QB (binary top 400 + int8 rescoring) is not adopted:** dev −0.015 [−0.032, −0.003] 4/7 fails both NI clauses. The loss sits on refined searches whose top-20 set the candidate stage changed (unrefined 0.000); s10_2 also drops on the known sets (−0.006 / −0.013). **TS (te weight ramped on q_ig) is not adopted:** no gain anywhere (`known_dev` +0.002; on the 45 searches P misreads as Instagram +0.005 vs TI's −0.035 there). It fails the NI point clause on dev (−0.007; ig −0.016) and `ig_known_dev` (−0.0096; the 20 P misreads as YouTube lose −0.063, TG lost −0.113). The ramp mostly zeroes te on correct YouTube reads, not on the misreads (mean w 0.75 there). Holm (gain family = TS): 0.88 / 0.069 / 0.92. No verdict rests on new grades (≤ 0.2% share; seed and no-AI labels give the same calls). **Cumulative vs H0r8 with Q8 as B8.5:** dev +0.039 [−0.008, +0.090], `known_dev` −0.007, `ig_known_dev` +0.130; −58% cost; item vectors 4× smaller than in RAM.
- **Orchestrator decision after 8.5:** Q8 accepted as the base (**B8.5 = `runs/r8.5/q8_r*`**), with the flag that the desktop build needs an int8 dot kernel (numpy upcasts; local p50 +0.13 s as run). Rounds without adoption: 0. Round 8.6 targets `known_dev` (YouTube known-item, flat all round): a YouTube interaction prior (watch count / rewatch / like / playlist) and per-field keyword lists (title vs channel).
- **Round 8.6 verdict** (`results/r8.6-eval.md`, labels c4-r8.6, 23 new pooled grades, 9 relevant): **nothing adopted** (rounds without adoption: 1). **WP (capped YouTube interaction prior) is not adopted:** no gain on a valid set. Dev is −0.0049 [−0.016, +0.003]; the clean dev yt read is −0.0095 (within noise, MDE 0.030), all of it on refined searches (unrefined yt +0.0025). `ig_known_dev` is −0.0042 [−0.012, +0.001]. `known_dev` (confounded) is +0.0014 as run. Its gain sits on targets whose boost comes from the label-defining watch (+0.032), and searches with an unboosted target lose −0.014. Recomputing the target's boost with one fewer watch gives **−0.016 [−0.027, −0.006]** on the 335 unrefined searches. So an end-of-export interaction prior cannot be judged on `known_dev` without interaction timestamps, and it displaces unboosted targets. **FL (title-only + channel-only YouTube BM25) is not adopted:** no gain. It fails the NI point clause on dev (−0.0085 [−0.025, +0.006]) and `known_dev` (mrr2 −0.0114 [−0.025, +0.003]; s10_2 −0.015 [−0.031, −0.001]), under every label variant. The `known_dev` loss is on the unrefined instant path (−0.012) and on searches with a non-empty channel list (334 of 381: −0.016). The channel list fires almost everywhere, and Instagram items in `known_dev` top 10s rise from 0.061 to 0.073. `ig_known_dev` is +0.002. Holm (2 arms; FL alone on `known_dev`): no raw p below 0.36. No verdict rests on new grades (WP 0%, FL 2.2% share; seed, g1 → 0 and no-AI labels give the same calls). Both arms are $0 extra, +0.01 / +0.02–0.035 s local; round spend $0.038 (builder refine calls). **Cumulative vs H0r8 (B8.5 unchanged):** dev +0.039, `known_dev` −0.007, `ig_known_dev` +0.130 at −58% cost.
- **After 8.6:** rounds without adoption: **1**. Next (8.7): learned fusion from usage (review option 4) if an evaluator can build a search→watch training pool disjoint from `known_dev` / `known_test` (session-disjoint, no shared targets).
- **Round 8.7 verdict** (`results/r8.7-eval.md`, labels c4-r8.7, 7 new pooled grades, 3 relevant): **nothing adopted** (rounds without adoption: **2**; one more meets the stop rule). **CI (creator-level index, top 5 creators' items as an extra 0.5 RRF list on every typed search) is not adopted:** no gain (dev +0.0034 [−0.006, +0.012], within noise; 76% of it from the new grades), and it fails the NI point clause on both known-item sets: `known_dev` mrr2 **−0.0185 [−0.033, −0.006]** 49/65 and `ig_known_dev` **−0.0221 [−0.040, −0.005]** 11/39, on the deterministic instant path, in every repeat. It acts by displacement: targets whose creator has ≥ 2 items (so could be in the list) are flat (+0.003 / +0.001), and singleton-creator targets lose (−0.106 / −0.055); name-matched searches show no gain either (−0.005 on 109). **R2 (wider instant routing, 69% → 90% instant) is not adopted as cheaper-equivalent:** the ≥ 30% saving holds on all typed (−64% $ / 1k) and the known mixes (−69% / −77%), but **not on the dev mix (−29.4% $, −23% p50)**; and NI fails on dev (−0.0239 [−0.066, +0.009]) and `ig_known_dev` (mrr2 −0.0227 [−0.055, +0.006]; s10_2 −0.036), by both clauses. `known_dev` is non-inferior (−0.0039 [−0.012, +0.004]). Dev's loss sits on the 5 moved searches B8.5 refined (−0.28), while the 5 moved unrefined gain (+0.07); on `ig_known_dev` the rewrite itself pays (moved unrefined s10_2 −0.09). Holm (2 arms): no raw gain p below 0.23. No verdict rests on new grades (seed, g1 → 0 and no-AI labels give the same calls).
- **After 8.7:** two independent verifiers reproduced every number and agree with both verdicts. Rounds without adoption: **2** (one more stops the loop). Learned fusion is blocked (no disjoint search→watch pool; needs the raw My Activity search history or product click logs). Round 8.8: refine on the instant (fast) YouTube path, and a stronger refine model on the existing gate.
- **Round 8.8 verdict** (`results/r8.8-eval.md`, labels c4-r8.8, 6 new pooled grades, 4 relevant): **FM (gpt-5-mini instead of nano in the refine, same gate) is adopted by the gain rule** and passes Holm. `ig_known_dev` mrr2 **+0.0401 [+0.018, +0.065]** 12/0 (MDE 0.036, Holm p 0.002; s10_2 +0.022 [+0.004, +0.042]); dev +0.0003 [−0.004, +0.004] and `known_dev` +0.0037 [−0.004, +0.012] are non-inferior and within noise. Flags: the whole gain sits on the 17 `ig_known_dev` searches the prior misreads as YouTube (+0.354 there, where nano is about neutral vs the pre-refine order); without the best 2 searches it is +0.0285 (< 0.03, CI > 0); the synthetic set is lexically biased toward text-reading rerankers; on YouTube targets mini ≈ nano (dev refined +0.0006, `known_dev` refined +0.031, MDE 0.093). Cost: +$0.048 / 1k typed ($0.055 → $0.103, +88%; dev mix ×2); refined screen +0.2 s p50, first screen unchanged. **FK (nano refine also on the instant YouTube path) is not adopted:** no gain (`known_dev` mrr2 +0.0012 [−0.018, +0.021]; its 290 newly refined searches 56/53), and it fails the NI point clause on `ig_known_dev` (−0.0072 [−0.021, −0.000]; the 7 newly refined Instagram targets −0.153, 0/4), at +80% $ / 1k typed (×3.2 on `known_dev`). No verdict rests on new grades (≤ 0.7% share; seed, g1 → 0 and no-AI labels give the same calls). Rounds without adoption: **0 if the orchestrator accepts FM** (3, and the stop rule fires, if it declines). `ig_known_test` is the natural confirmation for FM.
- **After 8.8:** FM accepted as **B8.8** (gain on `ig_known_dev` only, +88% cost; see LOG). The loop ends here by orchestrator decision (agenda and evaluable review options exhausted; learned fusion blocked). Final held-out scoring: B8.8, H0r8, B8.5 on `known_test` (clean) and `ig_known_test`.

## Final held-out (round 7) (7 Nov 2026; `results/r7-final.md`)

- **`test2` scoring 3 of 3 and `yt_holdout` scoring 3 of 3. Both sets are now used up.** `test` has 2 left (contaminated for round-5 ideas: qs-v1, creator search, te lists).
- Frozen C0, H0 (= G4), H5 and **H5b (preregistered)**, scored once per set after pooling (test2 18 items, `yt_holdout` 58) and blind judging ($0). Labels c4-f7, backup `evalset.pre_final7.jsonl`; Derrick's marks and earlier grades untouched.
- **Levels:** test2 C0 0.448, H0 0.501, H5 0.519, **H5b 0.538**; `yt_holdout` C0 0.388, H0 0.445, **H5 0.470**, H5b 0.450.
- **vs C0 (21 searches pooled):** H5b **+0.075 [+0.026, +0.128], 15/4**; H5 **+0.076 [+0.022, +0.135], 15/4**; H0 **+0.055 [+0.013, +0.103], 15/4**. All lower bounds > 0 on 20/20 seeds, every repeat positive, and all hold without the creator-search cells.
  - test2: H5b +0.089 [+0.022, +0.174] 8/1 (seed +0.052, CI > 0); H5 +0.070 7/2; H0 +0.053 (= round 6's G4).
  - `yt_holdout`: H5 +0.081 8/2; H5b +0.061 7/3; **H0 +0.056 [+0.003, +0.119] 8/2** (seed +0.058, CI > 0): the first held-out YouTube confirmation of 3-large.
- **vs H0 (21):** H5b +0.020 [−0.008, +0.047] 12/5, H5 +0.021 [−0.006, +0.051] 10/6; half of each sits in creator-search cells. test2 alone H5b +0.036 [+0.007, +0.069] 6/1, but `yt_holdout` +0.005 6/4 (seed −0.015). **Not confirmed.**
- **te lists (H5b − H5):** test2 `both` +0.032, `yt_holdout` −0.020 (2/6; seed CI below 0); net −0.001, 7/7. The dev trade (help mixed / Instagram, hurt YouTube) is confirmed.
- **Parts on held-out (vs H0):** calibration helps when the router reads the platform right (+0.05 to +0.06) and hurts when it reads a YouTube search as Instagram (−0.064 H5, −0.083 H5b; 0 of 4 test2 `yt`, 2 of 9 `yt_holdout` typed); soft time loses in H5 on test2 (−0.048, 0/2); the guarded filter won once (+0.21); creator search 2 wins, 2 ties, 1 small loss.
- **Problems:** creator search depends on Python string hashing (9/30 test2 and 6/27 `yt_holdout` typed cells are one draw); test2's H0 vs C0 is round 6's number reused; no `ig`-scope held-out search; 76 new grades by one judge (≤ 8% of relevant top-10 items; no verdict changes with them set to 0).
- **Recommendation (for the founders):**
  1. **Adopt H0 (C0 + text-embedding-3-large 1,024 d) as the new processor.** Confirmed on dev (+0.022, 25/12) and on both held-out sets; +$0.011 per 1k searches, about +0.1 s.
  2. **Do not adopt H5b.**
  3. **Keep H5 as the package candidate, not adopted:** its gain over C0 is confirmed, its increment over H0 is not (+0.021 held-out, +0.006 dev), and it costs +$0.164 per 1k and +0.8 s unless qs-v1 is merged into the rewrite.
- **Next, to settle the rest:** make creator search deterministic; build H5-lite (H0 + confidence-gated calibration + guarded filters + creator search / H4 profiles, qs-v1 merged; no soft time, no format boost, no te lists); score H0 vs H5-lite (H5 as reference) on a **fresh Derrick set of about 40–45 searches**, about a third each `ig` / `yt` / `both`, with 6–8 creator recalls, 5+ time / behaviour searches and YouTube searches that do not name the platform. `test` could give H0 vs C0 one more check.

## Round 7 (`BRIEF-7.md`): cheap classifiers plus the combined package (evaluated 7 Nov 2026; `results/r7-eval.md`)

- **Adopted: nothing. Finalist stays C0** (dev 0.481 on c4-r7). No arm passes clause 1 against C0 or H0.
- **Levels:** C0 0.481, H0 (= G4, rebuilt) 0.504, H1 0.505, H2 0.504, H3 0.500, H4 0.507, **H5 0.510**, **H5b 0.516**.
- **Per scope:** the Instagram side gains robustly; the YouTube side does not.
  - vs C0: H5 ig **+0.057 [+0.012, +0.101]**, H5b ig **+0.087 [+0.034, +0.151]** (both 20/20 seeds, both > 0 without the best search).
  - yt: H5 −0.000, H5b −0.018. vs H0: H5 yt −0.014, H5b yt −0.032.
- **H5b vs C0 +0.034 [−0.012, +0.085], 24/15/5** (lower bound < 0 on 20/20 seeds). H5 vs C0 +0.028 [−0.012, +0.069], 24/14/6.
- **vs H0 every part is ≈ 0 overall:** H1 +0.002, H2 +0.000, H3 −0.003, H4 +0.004, H5 +0.006, H5b +0.012. The bulk of the package's gain over C0 is 3-large (+0.022).
- **Where parts fired (vs H0, dev cells):**
  - helped: H1's guarded filters (3 searches, +0.150 per cell; one yt behaviour search), router calibration when the platform read is right (+0.031 [+0.005, +0.062], 18 searches), H4 (1 search, +0.24), H2 tone (3 searches, +0.015);
  - hurt: H1 soft time (−0.032 per cell, 18 searches), calibration when the router reads the other app (**−0.071 [−0.155, −0.001]**, 7 searches; H5 −0.072, H5b −0.125), router-gated creator search (2 searches, −0.12);
  - nothing: H2 format (0.000).
- **Flagged weaknesses all show in the scores:**
  - dev yt searches are read yt 8 / both 7 / ig 5;
  - 20 of 26 soft-time cells come from guard-dropped windows (16 'new'), and they lose;
  - H5b raises Instagram items per yt top 10 from 1.61 to 2.27, so H5b vs H5 is yt −0.018 in every repeat and ig +0.030 in every repeat.
- **Labels:** c4-r7 = c4-t2b + 51 blind evaluator dev judgments (2/11/38) over 16 searches; backup `evalset.pre_r7.jsonl`. Unjudged@10 0.00. With this round's 1s set to 0, no verdict changes.
- **Cost / latency vs C0:**
  - H5 / H5b $0.294 per 1k as run (+$0.174; $0.062 / $0.051 per +0.01); about $0.131 if qs-v1 is merged into the rewrite call (estimate).
  - +0.8 to +1.0 s at p50 and p95, all from the separate qs-v1 call.
  - H1 / H3 cost as H0.
  - Judging $0. OpenAI $2.882 of $9.50; ledger $6.657.
- **Package for the last `test2` scoring: H5b** (better of H5 / H5b on dev, as preregistered), with **C0** and **H0** as references.
  - No run isolates a pared-down package. The clearly harmful parts (misread calibration, soft time) are inside both packages.
  - Risk: test2 is 4 `yt` + 6 `both` with no `ig` scope, so H5b's weakness is tested directly and its strength only through `both`. Expect a yt loss.
  - Fallback if the orchestrator prefers it: H5.
- **Remaining scorings:** `test2` 1 left, `test` 2 left, `yt_holdout` 1 left; none touched this round.
- **Next, if the loop continues:**
  - keep the guarded filters and 3-large;
  - gate calibration on router confidence, or drop it for yt reads;
  - drop soft time and the format boost;
  - keep te lists away from yt searches.

## Held-out test2 (round 6) (7 Nov 2026; `results/r6-test2.md`)

- **Scoring 2 of 3 on `test2`** (Derrick's 10 searches: 4 `yt`, 6 `both`). Frozen C0, G4 and G5 (`runs/final2/c0x_test2_r*`, `runs/final3/{g4,g5}_test2_r*`), scored once after pooling and blind judging.
- **Scores:** C0 0.448, **G4 0.501**, G5 0.480.
- **G4 vs C0: +0.053 [−0.001, +0.134], 7/2/1.**
  - yt +0.109 (3/1); both +0.015 (4/1).
  - Seed only (Derrick's labels): **+0.022, 7/2**, the same as the dev Δ.
  - Concentrated: one `yt` topic/structure search is +0.38, 72% of the net. Drop the best 1 / 3 searches → +0.017 / +0.003. The lower bound is < 0 on 20/20 seeds (−0.001 to 0.000). All 9 repeat pairings are positive.
  - Mechanism as on dev: fewer Instagram items in yt top 10s (0.50 → 0.33); Instagram items in `both` searches are fewer but more precise (3.22 @ 0.81 → 2.72 @ 0.96).
  - Holds when this round's 1s are set to 0 (+0.033, 5/3) and when its 2s are set to 1 (+0.033, 6/3).
  - **Verdict: CONFIRMED** in direction and wins; the size is not established. It misses clause 1 on test2 narrowly (lower bound −0.001).
- **G5 vs C0: +0.032 [−0.026, +0.085], 5/4/1.**
  - yt +0.053 (3/1); both +0.017 but 2/3. Seed only +0.009, 4/4.
  - Its sign flips under the grade-sensitivity variants (1s → 0: −0.017; 2s → 1: −0.006).
  - Its dev strength (ig side) does not reappear on the `both` searches.
  - **Verdict: NOT CONFIRMED.**
- **G5 vs G4: −0.021, 4/5/1** (seed only −0.014, 2/6), against −0.008 on dev. The mini rewrites add nothing on top of 3-large.
- **Labels:** c4-t2b = c4-r6 + 73 blind evaluator test2 judgments (20/31/22), 35 of them surfaced `unvetted_candidates`.
  - Derrick's gold and the earlier test2 grades are untouched. Backup `evalset.pre_test2b.jsonl`.
  - Seed unjudged@10 vs c4-r6: C0 0.00, G4 0.19, G5 0.30 → 0.00. Pre-pool Δ was G4 +0.003, G5 −0.073.
- **Remaining scorings: `test2` 1 left; `test` 2 left; `yt_holdout` 1 left.**
- **Spend:** $0 judging. OpenAI $2.623 of $9.50; ledger $6.399.
- **Finalist line:**
  - No adoption from this scoring alone; C0 stays the finalist unless the orchestrator decides otherwise.
  - G4 is the strongest held-out candidate so far, at +$0.011 per 1k searches. A Derrick spot-check of the pooled items on its best search would firm up its size.
  - Drop G5 and the rewrite-model line.

## Round 6: stronger rewrite models, larger embedding model (evaluated 7 Nov 2026; `results/r6-eval.md`)

- **Adopted: nothing. Finalist stays C0** (dev 0.482). No arm passes clause 1. Clause 2 does not apply, because every arm costs more.
- **Round-6 dev leader: G4** (text-embedding-3-large 1,024 d, C0's nano rewrites): 0.505.
  - vs C0 **+0.022 [−0.008, +0.051], 25/12/7**. The lower bound is < 0 on 20/20 seeds.
  - ig +0.031 (lower bound −0.003 to −0.001); yt +0.014 (a few searches, one good repeat); more-like-this +0.042; MRR +0.050.
  - It lets fewer Instagram items into YouTube searches (2.05 → 1.59 per top 10, more of them relevant).
  - Cost +$0.011 per 1k searches ($0.005 per +0.01), plus $0.52 once for the library; +0.1 s.
- **G5** (3-large + gpt-5.4-mini): +0.014, 23/15. **ig +0.038 [+0.008, +0.068], robust** (20/20 seeds, and still > 0 without the best search). yt −0.009. vs G4 −0.008, at 11× G4's cost.
- **The embedding model is what helps; the rewrite model is not.**
  - G5 vs G1 is +0.027 [+0.004, +0.049], robust.
  - G1 (mini) −0.012; G2 (gpt-5.5) +0.005 at $11.34 per 1k (≈ 95× C0) and +2.4 s p50; G3 (escalation, 55%) −0.012.
  - G3's hard rule picks searches where mini loses (−0.024), and leaves to nano the ones where gpt-5.5 would gain (+0.020).
- **Spread:** stronger rewrites cut per-search nDCG variation between repeats by about a third (SD 0.060 → 0.041 mini, 0.039 gpt-5.5; G5 0.034), but the aggregate spread does not fall. The extra stability brought no quality.
- **Labels:** c4-r6 = c4-t2 + 290 blind evaluator dev judgments (18/57/215) over 40 searches; backup `evalset.pre_r6.jsonl`. Unjudged@10 is 0.00.
  - Pooling moved G4 +0.009 → +0.022 and G5 −0.008 → +0.014.
  - With this round's 1s set to 0, no verdict changes.
- **Spend:** round 6 $2.385 OpenAI (builder), judging $0. OpenAI $2.578 of $9.50; ledger $6.354.
- **Remaining scorings:** `test2` 2 left, `test` 2 left, `yt_holdout` 1 left; none touched this round.
- **Candidates for one test2 scoring:**
  1. **C0** (finalist);
  2. **G4** (dev leader, near-zero cost);
  3. optional **G5**: its robust part is ig scope, which test2 lacks except via `both`.
  - G4 needs 3-large vectors of C0's test2 strings (≈ $0.001); G5 also needs mini parses (≈ $0.02). The orchestrator arranges both.
- **Next, if the loop continues:** a 3-large te / fusion arm (E1/F0 on 3-large vectors) is the natural test; drop the rewrite-model line.

## Held-out test2 (3 Nov 2026; `results/r5-test2.md`)

- **Scoring 1 of 3 on `test2`** (Derrick's 10 fresh searches: 4 `yt`, 6 `both`). Frozen C0, E1, F0, F2 (`runs/final2/*_test2_r*`), scored once after pooling and blind judging.
- **Scores:** C0 0.448, **E1 0.479**, F0 0.453, F2 0.457.
- **E1 vs C0: +0.030 [−0.015, +0.076], 6/3/1.**
  - both +0.054 [+0.008, +0.107], 5/0; yt −0.006, 1/3.
  - Intent was active on 1 of 30 cells, so this is te fusion.
  - Fragile: dropping the best 2 searches leaves +0.002, and the lower bound is < 0 on 20/20 seeds.
  - **Verdict: CONFIRMED (narrow), te-fusion part only.** The YouTube side and the intent step stay unconfirmed. It does not meet adoption clause 1.
- **F0 vs C0: +0.005 [−0.034, +0.051], 4/4/2.**
  - both +0.040, 4/0; **yt −0.049 [−0.095, −0.016], 0/4.**
  - Instagram crowding: 2.17 items per yt top 10 at 4% relevant (C0: 0.50).
  - **Verdict: NOT CONFIRMED.** Same pattern as dev, with a larger yt loss.
- **F2 vs C0: +0.008 [0.000, +0.022], 2/0/8.** Creator lookup fired on 3 searches (8 of 30 cells). On the other 22 cells F2 equals C0.
  - Creator searches: +0.027, 2/0.
  - The two wins name the creator; F2 moved the first gold-2 item up by 0–2 ranks.
  - On the one *described*-creator search every method scores 0, and F2 pushed the target creator further down the list.
  - **Verdict: NOT CONFIRMED.** p95 is 5.4–7.6 s.
- **Labels:** c4-t2 = c4-r5 + 159 blind evaluator test2 judgments (37/44/78), 59 of them surfaced `unvetted_candidates`.
  - Derrick's gold was untouched. Backup `evalset.pre_test2.jsonl`.
  - Seed unjudged@10 0.78–0.79 → 0.00.
  - Seed-only Δ: E1 +0.004, F0 +0.009, F2 +0.004. Pooling moved E1 most.
  - 32–36% of relevant top-10 items carry Derrick's grades.
- **Remaining scorings: `test2` 2 left; `test` 2 left; `yt_holdout` 1 left.**
- **Spend:** $0 judging. OpenAI $0.194 of $9.50; ledger $3.969.
- **Finalist line:**
  - C0 stays the finalist; no adoption.
  - E1's te fusion is confirmed again for Instagram and mixed-platform searches (test, test2), not for YouTube searches (`yt_holdout`, both `yt` subsets).
  - Next: fix the YouTube slot competition before a te arm can be adopted. Collect described-creator searches before more work on F2.

## Round 5 (`BRIEF-5.md`): understand the query in parts (evaluated 3 Nov 2026; `results/r5-eval.md`)

- **Adopted: nothing. Finalist stays C0** (dev 0.482). No arm passes clause 1; clause 2 is closed to all (te pass or extra LLM calls).
- **Round-5 dev leader: F0** (te lists for caption-type items only, coverage-fair fusion): 0.509.
  - vs C0 **+0.027 [−0.004, +0.062], 20/14/10**. Lower bound < 0 on 20/20 seeds; top 5 searches = 99% of the net gain.
  - **ig +0.067 [+0.020, +0.126], 15/3** (robust: lower bound > 0 on 20/20 seeds). This is the milestone's confirmed component again.
  - yt −0.014, 5/11. Within-YouTube ordering = C0 exactly. The loss is more Instagram items in YouTube searches: 3.02 per top 10 at 0.37 relevant (C0 2.05, D1 2.39). vs D1 −0.011.
- **F1** (typed-slot rewrite qs-v1): −0.007, 16/17. ig −0.032, 5/11; yt +0.019, 11/6 (topic/structure). Unstable over repeats (+0.014 / −0.011 / −0.023). No single slot explains it; it is the whole plan change. +0.7 s.
- **F2** (creator search): fired on **one** dev search (2 of 132 cells), +0.15 there. Not judgeable on dev.
- **F3** (facet boosts): −0.017, 6/7. One YouTube search where a stated count was read as format `list` gives −0.71; without it −0.001. Format boosts lose per active cell (−0.063).
- **F4** (checker): −0.000, 6/8; reorders the top 20 with no effect. p95 6.3 s (+3.8 s).
- **F5** (stack): +0.009 vs C0; **vs E1 −0.046 [−0.082, −0.010], 13/24/7**. The intent cells still win (+0.185 over 4 searches); F1 and F3 cost Instagram.
- **Where each slot fired (dev cells):**
  - format: F1 −0.011, F3 −0.063, F4 −0.005, all worse than where it did not fire;
  - tone: F1 +0.021, F3 +0.012, F4 +0.020, positive but only 3 vibe searches (a lead, not a finding);
  - creator lookup: 1 search.
- **Labels:** c4-r5 = c4-m1 + 279 blind evaluator dev judgments (14/55/210), backup `evalset.pre_r5.jsonl`. Unjudged@10 0.00. Pooling moved F1 from −0.030 to −0.007 and F5 from −0.013 to +0.009; no verdict changed. `test` 2 scorings left, `yt_holdout` 1 left, `test2` unused; none touched.
- **Spend:** round 5 $0.071 OpenAI (builder), judging $0. OpenAI total $0.174 of $9.50; ledger total $3.950.
- **Candidates for held-out scoring (test2 first; it is the only split clean for F0):**
  1. **C0** (finalist);
  2. **F0** (round-5 leader);
  3. optional **E1** (best dev overall, 0.538; tests the intent step if test2 has behaviour/time searches).
  - No candidate has `test2` runs yet. Fresh qr-v1 (+ qi-v3 for E1) are needed (≈ $0.01, orchestrator).
  - `test` is contaminated for round-5 ideas and for F0. Keep `yt_holdout`'s last scoring for the final.
- **Next, if the loop continues:**
  - stop Instagram te votes crowding YouTube searches under F0 (for example, te lists rerank only within the own lists' top N);
  - build a creator-lookup search set before judging F2;
  - try tone-only facets on vibe searches, with more vibe searches first.

## Round 4 (`BRIEF-4.md`): one library, two platforms, as a loop

**Loop stopped (3 Nov):** E1 was withdrawn after the held-out milestone. Counting 4.1–4.3 as three rounds without a confirmed win, the stop rule fired.
- **Finalist stays C0.**
- **Confirmed:** the te pass helps Instagram-side searches; coverage-fair fusion is needed.
- **Spend:** $3.88 of $15.
- **Write-up:** `docs/research/2026-11-03-combined-loop.md`.
- **Next free experiment:** te lists for Instagram plus untitled YouTube only.

### Milestone (held-out), 3 Nov 2026 (`results/r4-milestone.md`)

- **Verdict: NOT CONFIRMED.** E1's dev gain over C0 (+0.056) does not hold on held-out searches.
  - **`test`** (Derrick's 13 searches, scoring 1 of 3): E1 vs C0 **+0.030 [−0.005, +0.068], 7/5/1**. E1 0.510 vs C0 0.480. Dropping the best search leaves +0.018, and that search is the partial-credit-only `f01`.
  - **`yt_holdout`** (11 searches, scoring 2 of 3): **−0.024 [−0.077, +0.012], 3/6/2**. E1 0.364 vs C0 0.388.
  - **Both sets together** (24 searches): +0.005 [−0.027, +0.035], 10/11.
  - E3 vs C0: test +0.024 (6/6), `yt_holdout` −0.023 (3/5). E1 vs E3 cannot be told apart (+0.003 over 24 searches).
- **Per scope:**
  - **The Instagram side holds:** test `ig` +0.051 [+0.012, +0.100], 3/0/1; `both` +0.053, 3/2.
  - **The YouTube side fails:** test `yt` −0.021 (E3 −0.042 [−0.072, −0.013], 0/4); `yt_holdout` −0.024.
- **Why dev and held-out differ:**
  - Dev's `yt` gain was the intent step on behaviour and time searches. Held-out has no search where it acts: on test the guards dropped all 13 intents, and on `yt_holdout` only the behaviour search kept a filter, where all methods score 0. So held-out measures D1-style te fusion only.
  - That fusion moves top-10 slots to Instagram items. This helps `ig` and `both` searches, where those items are 80–87% relevant. It hurts YouTube searches, where they are 34–42% relevant against 53–81% for the YouTube items they replace.
  - E3's descriptive rule makes the YouTube crowding slightly worse.
  - **The intent step is untested on held-out.**
- **Labels:** c4-m1 = c4-r3 + 358 blind evaluator judgments, calibrated on Derrick's own marks first.
  - test 243 (37/103/103), including 38 `unvetted_candidates`; `yt_holdout` 115 (13/19/83), 100 of them Instagram items.
  - Derrick's gold grades were not touched. Backup `evalset.pre_milestone.jsonl`. Unjudged@10 is 0.00 everywhere.
  - Pooling changed no direction: seed-only Δ was +0.022 on test and −0.026 on `yt_holdout`.
  - Caveat: only about 26% of the relevant top-10 items on test carry Derrick's own grades.
- **Remaining scorings: `test` 2 left; `yt_holdout` 1 left.**
- **Spend:** milestone $0. Round 4 to date is **$3.879** (Gemini $3.776, OpenAI $0.103; the +$0.012 is the `test` runs).
- **Finalist line:**
  - E1 stays the dev finalist, but its held-out confirmation failed.
  - The confirmed piece is te fusion for Instagram-side searches. For YouTube searches, C0 is at least as good.
  - Next: fix te slot competition on YouTube searches (4.3 agenda item 2). Get held-out behaviour and time searches before claiming the intent step.
  - BRIEF-4's Finish write-up and the A-003/A-004 updates are still open (orchestrator).

### Round 4.3 (evaluated 3 Nov 2026; `results/r4.3-eval.md`)

- **Finalist: E1 (new; adopted under clause 1)**, D1's coverage-fair te fusion + qi-v3 intent with guards that only widen. Dev 0.538 [0.460, 0.618] under label round c4-r3 (ig 0.579, yt 0.497).
  - vs C0: **+0.056 [+0.010, +0.105], 30/8/6**; repeats +0.065 / +0.038 / +0.063.
  - ig +0.073 [+0.026, +0.131]; yt +0.038 [−0.036, +0.119].
  - **Robustness:** the lower bound is +0.009 to +0.012 over 20 seeds (20 of 20 above 0). It still passes without its best search. It fails once the 2 best are removed (one YouTube intent win, one Instagram te win).
  - **Caveat:** the decisive guard fix was designed from one dev search (the only search E1 changes vs D4 on dev). The held-out splits must confirm it.
- **Best rival: E3** (E2 + E1's guards): 0.532.
  - vs C0: +0.050 [+0.012, +0.095], 25/9/10; lower bound +0.011 to +0.012 over 20 seeds.
  - vs E1: −0.006 [−0.017, +0.009]. It needs te on only about 60% of items, but also needs a `platform_data.text_kind` contract field.
- **E2** (te only for non-descriptive items) passes clause 1 only marginally: +0.034 [+0.001, +0.071]. It is fragile, failing without its best search.
  - vs D1: −0.003, yt +0.000. Withholding te from descriptive titles frees top-10 slots that thin and Instagram items fill at lower precision. The round-3 YouTube te loss is slot competition, not te on titles in the top 10.
- **E4** (per-group BM25) fails: +0.050 [−0.001, +0.105], 22/18/4.
  - vs E3: ig +0.021, yt −0.021. Raw-score merging moves Instagram items into every search; within-platform ordering is unchanged.
- **Clause 2** applies to no arm: all need the te pass (about $0.18 per 1k items).
- **Labels:** c4-r3 = c4-r2 + 21 blind evaluator judgments (3/4/14), backup `evalset.pre_r4.3.jsonl`. Unjudged@10 is 0.00 for all runs. `yt_holdout`: 2 scorings left. `test`: 3 left. Both untouched.
- **Spend, round 4:** **$3.867** of $15, unchanged.
  - Gemini $3.776 ($1.72 left); OpenAI $0.092 ($9.41 left).
  - Round 4.3: $0 building, $0 judging.
- **Stop rule: rounds adopting nothing in a row = 0** (it was 2 before this round; E1 was adopted). The spend stop is far off. The loop may continue.
- **Recommended candidates for the final held-out scoring** (`yt_holdout` once, Derrick's `test` once):
  1. **E1**, the finalist;
  2. **C0**, the round-4.1 baseline (`c0x` = `c0`);
  3. **E3**, the best rival.
  - The runs cover dev + `yt_holdout` only. **No `test` runs exist yet.** E1, E3 and C0 must be run on the 13 `test` searches first (fresh qr-v1 + qi-v3, ≈ $0.05 OpenAI), arranged by the orchestrator.

**Agenda for round 4.4** (if the loop continues; $0 unless noted):

1. **Get `test` runs for E1, E3 and C0** (≈ $0.05), so the Finish step can happen at any time.
2. **Target the YouTube te loss as slot competition** (yt topic/task/structure −0.04 to −0.09 vs C0).
   - Let te lists only rerank within the own lists' top N, or cap their RRF weight when the own lists agree.
   - Expected yt +0.01 to +0.03, ig 0.
3. **Per-group BM25 with rank- or quantile-based merging** instead of raw scores (E4 fixed). Low expected value, because E4's within-platform projections did not improve.

Not recommended: more intent-guard tuning on dev (it has now been tuned on two dev searches), Gemini spend, or an LLM judge.

### Round 4.2 (evaluated 3 Nov 2026; `results/r4.2-eval.md`)

- **Finalist: C0 (unchanged)**, 0.483 [0.401, 0.565] on dev under label round c4-r2 (ig 0.506, yt 0.459). Nothing passed the adoption rule. **Best rival: D1** (two near misses, D1 and D4).
- **Labels:** c4-r2 = c4-r1 + 81 blind evaluator judgments (3/17/61) of every unjudged dev top-10 item from the 4.2 runs. Backup `evalset.pre_r4.2.jsonl`. `yt_holdout`: 2 scorings left. `test`: 3 left. Both untouched.
- **D1, coverage-fair fusion of the te lists:** 0.520.
  - vs C0: +0.037 [−0.002, +0.078], 29/8/7. The CI lower bound stays at −0.002 to −0.001 over 20 bootstrap seeds. Clause 2 fails on the te-pass cost.
  - ig +0.073 [+0.026, +0.131], 17/1/4; yt +0.001.
  - vs C1: +0.059 [+0.012, +0.110]; yt +0.107. The crowding is fixed.
  - The YouTube topic/task/structure te loss from round 3 remains (−0.05 to −0.09).
- **D4 = D1 + guarded intent:** 0.528.
  - vs C0: +0.045 [−0.001, +0.095], 29/9/6. A near miss for the same reasons.
  - vs D1: +0.008.
  - A guard flaw costs about 0.01. Dropping one flag of an ORed multi-flag `require` *narrows* the pool, which cost one Instagram search −0.45.
- **D3 (guarded qi-v3 on C0):** +0.004.
  - yt +0.025, 3/0/19. The guards removed every C3 loss.
  - ig −0.017, from the same flaw.
  - The watch-rule deviation (≥ 50% coverage instead of "any watch event") has no measurable effect.
- **D2 (te merged into thin items' own view):** +0.007 overall.
  - yt +0.025; yt-only projection +0.042 [+0.008, +0.087].
  - ig −0.010; ig-only projection −0.050. It gives up te on sufficient Instagram captions.
- **D1p (te ranks rescaled):** significantly worse than D1, −0.026 [−0.044, −0.008]. It overcorrects.
- **Spend, round 4 (ledger `data/all/ai_runs.jsonl`):** **$3.867** of $15.
  - Gemini $3.776 ($1.72 left of its cap); OpenAI $0.092 ($9.41 left).
  - Round 4.2: $0.016 building, $0 judging.
- **Stop rule: rounds adopting nothing in a row = 2.** One more round without an adoption ends the loop; then comes the Finish step: finalist, 4.1 baseline and best rival on `test` and `yt_holdout`.

**Agenda for round 4.3** (ranked by expected value per dollar; all $0 in API calls):

1. **D4′ = D1 + D3 with guards that only widen.**
   - If any flag of a multi-flag `require` fails its word check, drop the whole `require`.
   - Extend the share lexicon to sending (send / sent / DM'd).
   - Expected vs C0: +0.05 to +0.06; evaluator counterfactual +0.056 [+0.010, +0.105].
   - It is the arm most likely to clear clause 1. The fix was motivated by one dev search, so the finish splits are the real check.
2. **D1 with te eligibility limited to items whose own text is not a descriptive title** (caption-type or insufficient).
   - Set from an adapter field in `platform_data` (AGENTS rule 4).
   - It targets D1's YouTube topic/task/structure loss, while D2 shows te helps thin YouTube items.
   - Expected vs D1: yt +0.02 to +0.05, ig 0.
3. **Per-platform BM25 statistics** (idf and length normalisation per item group).
   - It targets C0's −0.025 Instagram ordering loss (ig-only projection).
   - Expected +0.00 to +0.02 on ig. Low expected value.

Not recommended: Gemini spend (YouTube te parity ≈ $10 against $1.72 left) or an LLM judge. Keep the OpenAI budget for the finish.

### Round 4.1 (evaluated 3 Nov 2026; `results/r4.1-eval.md`)

- **Finalist: C0**, the combined platform-blind baseline (A0/B3-without-enrichment recipe over all 136,908 items). It scores 0.483 [0.401, 0.565] on dev under label round c4-r1: ig 0.506, yt 0.459. Nothing passed the adoption rule.
- **Labels:** c4-r1 = +1,066 blind evaluator judgments of every unjudged dev top-10 item, cross-platform items included (77/242/747). Backup `evalset.pre_r4.1.jsonl`. `yt_holdout`: 2 scorings left. `test`: 3 left, both untouched.
- **Interference is small:**
  - ig −0.007 vs the Instagram-only control;
  - yt −0.017 vs the YouTube-only control;
  - MRR −0.04/−0.05.
  - The other platform fills 46% of the ig top 10 and 20% of the yt top 10, with 54% and 38% relevant.
  - Seed-only labels had badly overstated interference (−0.165 / −0.055), so pool every round.
- **C1 (te lists everywhere):** −0.022 overall.
  - ig +0.063 [−0.004, +0.143], a near miss.
  - yt −0.106. About −0.095 of that is Instagram items crowding YouTube searches: te coverage is 98% of Instagram items vs 6% of YouTube items.
  - The YouTube-internal te effect is about −0.03, as in round 3.
- **C2 (te only for insufficient items):** −0.181. Restricting the te *lists* to thin items gives them two RRF votes on every search. This is a design flaw, not a verdict on routing.
- **C3 (qi-v3 filters):** −0.013.
  - It helps behaviour and named-window searches.
  - It is cancelled by guessed calendar windows, topic-free ordering on vibe searches and spurious Instagram save/date filters.
  - `require watched` silently drops Instagram.
- **Spend, round 4 (ledger `data/all/ai_runs.jsonl`):** $3.852 of $15.
  - Gemini $3.776 of its $5.50 cap, $1.72 left;
  - OpenAI $0.076.
  - Round-4.1 judging cost $0. Rounds adopting nothing in a row: 1.

**Agenda for round 4.2** (ranked by expected value per dollar; all three reuse existing outputs):

1. **Coverage-fair fusion of the te lists** (free; expected +0.02 to +0.04 overall vs C0).
   - Let each item's RRF score count only the lists that *could* rank it: the mean over eligible lists, or own-text lists standing in for missing te lists.
   - This is platform-blind and comes from an item property, not the platform.
   - Projections say it keeps C1's ig gain (+0.05 to +0.08) and cuts the yt loss from −0.106 to about −0.03.
   - Pair it with a yt-side guard for topic/task searches if the loss stays.
2. **Item-level sufficiency routing (the cascade, rebuilt; free; expected +0.01 to +0.03 on top of 1).**
   - Put an insufficient item's te text into *its own* BM25 view and blend its te vector into its own dense vector, instead of adding separate lists for a subset.
   - Sufficient items stay text-only.
   - This tests the routing idea C2 could not.
3. **qi-v3 with code-side guards (≈ $0.03 for 3 repeats; expected +0.01 to +0.03, on yt behaviour/time searches only).**
   - Keep a date window only if the search contains a calendar word (a year, month or season). Keep a behaviour filter only if it contains a behaviour word.
   - Disable topic-free → behaviour-only ordering when the parse has topic phrases.
   - Treat `watched` as "watched OR an Instagram interaction" so it no longer acts as a hidden platform filter.

Not recommended yet:
- YouTube te coverage parity: more Gemini spend, with only $1.72 left, and round 3 found te hurts titled YouTube items.
- Per-platform BM25 normalisation: interference is only about −0.01 to −0.02.

## Round 3 (`BRIEF-3.md`, run as `RUN-3.md`): YouTube, done

- **YouTube base: A0** (B3 recipe on Takeout titles and channels, OpenAI 3-small 512d). Dev 0.463, test 0.437. Nothing passed the adoption rule. **YouTube test scorings: 1 of 3 used.**
- **Spend:** Gemini $6.76, OpenAI $0.47. Ledger: `data/yt/ai_runs.jsonl`.
- **A1, the text pass:** −0.046. It does not transfer from Instagram because titles are already descriptive.
- **A2, the Gemini video pass:** the gate beats random at equal spend by +0.018 (fails the rule). Its value is reach into untitled saved videos. No correct moment was found.
- **A3, the intent filters (qi-v2):** +0.05, with about +0.6 on behaviour and time searches. **Next: run filters only on A0**, without guessed era windows.
- **Literal vs intent:** 71% agreement on relevant-vs-not (κ 0.41).
- **Reference arm (API text):** no measurable overall cost; it helps moment and name searches. **Delete `data/yt/ref/` by 2026-11-29.**
- **Write-ups:** `docs/research/2026-10-31-youtube-round.md`, `results/r3-methods.md`, `results/r3-eval.md`, `research/youtube-api-terms.md`. A-004 updated.

## Round 2 (`BRIEF-2.md`) — done except Q4 (waiting for Derrick's grades)

- **Finalist unchanged: B3.** Labels: round t2 is current. **Test-split scorings: 3 of 3 used** (none left).
- **Spend in round 2:** OpenAI $0.096, Gemini $0.058 (**$0.15**, plan was < $3). Loop totals: OpenAI $0.189, Gemini $6.758.
- **Q1 (gap flags):** weak predictors of misses (AUC 0.60 vs caption richness 0.67). 52% of misses rank beyond 1,000; on-demand enrichment of the top 200 reaches ≤ 12%. Flags should choose the facet, not the item; gap rule "unknown OR empty". Media gate proposed (image for all; audio for music/how-to gaps; video for weight ≥ 0.8 reels). `results/r2-q1-gap-flags.md`.
- **Q2 (library-aware rewrite):** profile +0.006 (cheaper with caching); look-first +0.024 on dev but −0.038 on test, +0.007 over all 22 → withdrawn; gpt-5-mini no better. `results/2026-10-30-r11-q2-q3.md`, `results/2026-10-30-test-milestone-2.md`.
- **Q3 (speed):** only the instant path (no rewrite) meets p95 ≤ 0.5 s (0.17 s), at ~−0.07 nDCG@10; LLM rewrites are 2.1–3.1 s p95 with a ~0.9 s network floor; faster/shorter models and routing don't help; recommend two-stage search. `results/r2-q3-speed.md`, chart `results/r2-q3-speed-chart.html`.
- **Q4 (AI judge vs Derrick):** blind 60-line sheet at `data/eval_work/human_check/sheet.md` (key hidden in `key.json`); scorer `eval/human_check.py`. **Next:** put Derrick's 60 grades in `data/eval_work/human_check/derrick_grades.json` and have a fresh evaluator run `python experiments/eval/human_check.py`.
- **Q5 (YouTube):** `experiments/youtube/` (synthetic importer, API enricher, eval format with `moment`, PLAN.md; 34 tests). Needs from Derrick: Takeout (JSON), `YOUTUBE_API_KEY`, ~30 YouTube searches.
- **Amendments:** A-003 updated (two-stage search, background enrichment, gap-flag findings); A-004 Proposed (YouTube contract gaps).
- **Code notes:** look-first context ordering is hash-seed dependent for tied counts (sort ties to make it deterministic before reuse). gpt-4.1-nano is no longer served (404) though still listed.
- **Round-2 assumptions:**
  1. Q1 used the dev split only, so test labels stayed untouched until the last test scoring.
  2. Q2 and Q3 runs were judged together in one evaluator round (r11).
  3. Experiment 26 was adopted provisionally under clause 2 (cache-adjusted cost below B3; its first pass equals the instant screen) and then withdrawn when the last test scoring did not confirm it.
  4. Q4 excludes friends' items from the human sheet.
  5. Rule slip: the Q3 experimenter made three diagnostic API probes outside `lib/ai.py` (one billed, $0.00001, logged by hand).

---

# Round 1 (closed)

- **Phase:** 6 done — converged and handed over. Draft pull request into `main`: https://github.com/cookie-is-yummy/digester/pull/2 (squash-merge).
- **Finalist:** **B3** = real gpt-5-nano query rewrite (qr-v1) + bge-small dense (gate, PRF) + BM25 + RRF, **plus** tier-1 text enrichment of every non-friend item (gemini-3.1-flash-lite, prompt te-v1c, Batch) indexed as its own BM25 list and its own bge-small vector list, **plus** HyDE (the rewrite's 3 invented captions as one extra query vector). Code: `methods/stack.py --opt hyde=1` (with `e9_enrich_search.py`, `pipeline.py`).
- **Labels:** round t1 is current (r0 + 567 dev judgments over rounds r1–r10 + 88 test judgments in t1). Backups `data/evals/labels/evalset.pre_*.jsonl`.
- **Test-split scorings used: 2 of 3.** One left.
- **Budget (ledger `data/ai_runs.jsonl`, list-price estimates):** OpenAI **$0.09** of $18; Gemini **$6.70** of $18. Not reconciled with the billing pages (no access from the loop).

## Summary for the founders

**Top three findings**

1. **One cheap text pass per item, indexed separately, is the only clear win.** A Gemini Flash-Lite pass writes a summary, facet slots, unknown facets and likely searches for every item; searched as its own keyword field and vector, it adds **+0.059 [+0.016, +0.108]** dev nDCG@10 (13/3/0) for **$0.18 per 1,000 items** in Batch (~$3.7 for a 21k history). With HyDE the finalist reaches 0.570 vs 0.489 for the honest base on dev; on the 6 held-out test searches it is +0.023 [−0.010, +0.053] (recall@100 +0.060 [+0.007, +0.107]); over all 22 searches **+0.065 [+0.028, +0.103]**.
2. **The previous numbers were inflated twice.** The hand-simulated rewrite had seen the answers (real rewrite: 0.49 vs 0.58), and Muse's descriptions leak labels by *which* items they cover (presence alone: +0.16). Every result in this loop was scored by a fresh blind evaluator with pooled judging.
3. **Text has hit its ceiling; the rest needs media.** 17 other ideas — feedback, fusion tweaks, priors, creator expansion, rewrite variants, three embedder swaps, ColBERT, two LLM rerankers, a second enrichment prompt — gained under 0.02 or cost too much latency. Recall@100 stayed ~0.51–0.53 with every text method. Text enrichment misses 96% of audio, 60% of place and 50% of speech that Muse had.

**Recommendation:** adopt A-003 items 1, 2 and 4 (enrich every item with one text pass, index it separately, keep bge-small); add HyDE as a free option. Keep the LLM rerank only as an opt-in "precise" mode (+0.013–0.016, +3 s). Spend the next money on a permitted media route (A-002), starting with thumbnails/keyframes for shown/vibe/more-like-this and audio fingerprints for songs, indexed the same separate-field way.

**What the founders need to decide or provide**

- Accept / reject **A-003** (contract change: ItemCard gains facet slots, unknown facets and likely searches for every item; a second embedding row per item; the 18 Oct "on-demand only" decision changes). Both founders.
- Whether the user's **collection names** may go to the LLM (kept per user, out of the shared cache), or be dropped.
- **Media:** a decision on A-002, or media files for a sample; a `YOUTUBE_API_KEY` to test YouTube thumbnails.
- **More-like-this:** an LLM "what makes these alike" plan gained on every dev MLT search (+0.05–0.11) but not on the single test one; more MLT searches are needed to decide.
- **More searches:** 16 dev searches with 5 single-search kinds can't resolve gains under ~0.02; a second person's searches and more audio/place/vibe searches would.
- Check the **Gemma licence** if EmbeddingGemma (local, multilingual) is ever reconsidered.

## Done (in order)

- Phase 1: data unzipped; baseline reproduced exactly (dev 0.508, all 0.486); prices verified (`lib/ai_prices.json`, 30 Oct); key checks; Muse inventory and ceiling (`results/muse-*.md`).
- Phase 2: `results/benchmark-baseline.md`.
- Phase 3: `results/flaws-ranked.md`. Phase 4: five research notes in `research/`.
- Phase 5: experiments 1–24 (+9b), rounds r1–r10; every row in `LOG.md`.
- Phase 6: test milestone (`results/2026-10-30-test-milestone.md`), write-up `docs/research/2026-10-30-search-loop.md`, Proposed amendment A-003 in `docs/amendments.md`.

## If resuming

- Data needed: `data/` from the zips plus `data/enrich/` (te-v1c full-corpus enrichment, ~20k rows) and `data/runs/rewrites/` (cached rewrites). Without them, rebuild with `methods/enrich_batch.py` (~$2.9) and `methods/llm_rewrite.py` (~$0.002).
- Next experiments worth running only with new inputs: media description pass on permitted media; more MLT searches; a second user's eval set.

## Assumptions

1. **No `YOUTUBE_API_KEY`**, so no YouTube media experiments; YouTube/podcast/article fit is by design and cost estimate only.
2. **`gemini-2.5-flash-lite` is unavailable** to this key (404); the cheapest Gemini text model used is `gemini-3.1-flash-lite`.
3. **Gemini Embedding 2's model ID is `gemini-embedding-2`** ($0.20/M text standard, $0.10 batch). It doesn't accept `task_type`; text prefixes were used.
4. **The phase-1 "all 22" repro counts as test scoring #1 of 3.** The T1 milestone (score, pool/judge, re-score once, all finalists together) counts as #2.
5. **MU ceiling and Muse parser are evaluator-side code** (`eval/muse*.py`, `eval/reference_compare.py`); builders never ran or read them.
6. **One experimenter may run a small batch of independent one-variable experiments**, each preregistered as its own LOG row.
7. **Experiments run on all three cached rewrite sets** and report the mean paired Δ against the same-repeat base. In production the rewrite would be cached per query.
8. **Evaluators pooled and judged every round**, even when `unjudged10` was below 0.15, so methods surfacing new items were never penalised by missing labels.
9. **HyDE adopted under clause 2 ("no extra cost")** because its captions come from the rewrite call the base already makes; it adds ~0.1 s of local embedding. Not confirmed on test.
10. **Friends' posts** (`owner_relation == "mutual"`, 463 items) were never sent to any LLM; they stay rankable from their caption only.
11. **Collection names** (the user's own data) were sent with each item to the enrichment LLM; flagged as a product decision in A-003.
12. **Rule slips, recorded:** one Gemini diagnostic curl call bypassed `lib/ai.py` (~$0.00004, logged by hand); evaluator round 1 had read MU text before judging the r1 pool; one experimenter printed one item code to its console (not written anywhere); one experimenter's `grep` of LOG.md showed two dev-score rows (aggregate, dev only); two evaluator notes quoted five search texts next to grading conventions — redacted in the final commit, but still in earlier commits on this branch, so squash-merge.
