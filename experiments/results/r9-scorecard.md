# Round 9, Phase B: per-facet scorecard (what "good enough" means, and where Q8 is now)

Written 9 Nov 2026 by the round-9 evaluator, which built none of the methods scored here. Aggregates only: no query texts, captions, item codes or per-search scores. Numbers are in `r9-scorecard.json`; per-search values are in `data/all/eval_work/r9.B/` (gitignored). Script: `experiments/eval/scorecard_r9.py` (no paid calls).

> **The targets below are proposals for the founders.** They have not been accepted. Arms must not be tuned against them, and they do not replace the adoption rule in `BRIEF.md`. They are here so that "is this good enough?" has a number the founders can accept, change or reject.

## Bottom line

1. **Known-item search is the clear gap.** When the person wants one item they remember, Q8 puts it on the first screen (top 10) for 42% of Derrick's real Instagram known-item searches [13%, 71%] and 45% of `known_dev` [40%, 49%]. The proposed target is 80%. Both CIs end below it, so the target is clearly missed. This is also what pulls the overall Gate 1 number down on real Instagram searches (70%).
2. **"Anything like it" searches pass on AI grades.** At least one good or exact item is in the top 5 for 86% of real Instagram topic searches, 92% of facet_dev and 83% of dev. That clears the proposed 80%, but none of these numbers is anchored on Derrick. Counting his own grades only, the floor is 17% / 0% / 7%. The truth lies between the two, and only his own grades on Q8's top 5 can narrow it (see "What it would take to check").
3. **Looks, sound and "examples of" cannot be scored by text-only judges.** The judges see the same captions and titles that the search uses. They grade looks searches 83–93% "good in top 5", yet Derrick's own target is on the first screen for 22% (ig_real) and 0% (facet_dev) of them. For these facets, the AI number measures topical match, not the facet.
4. **Named creator and time are below target even though our data already holds the answer.** A named creator gets the target on the first screen 42% of the time (`known_dev`, 46 searches; target 90%). Time and behaviour searches show a good item in the top 5 53% of the time (dev, 10 searches; target 80%). Phase A classes both as information that is present but not used.
5. **Most per-facet cells are too small to check a target.** The MDE for a paired change is 0.10–0.60 on cells of 3–24 searches. Only `known_dev` as a whole (MDE 0.036) and its named-creator and topic cells (0.13 and 0.09) can detect a change smaller than 0.15.

## The scorecard

**User-terms metrics.**

| Search wants | Metric | Plain words |
| --- | --- | --- |
| **exact** (this one item) | `hit10` | the target is on the first screen (top 10) |
| | `hit5` | the target is in the top 5 (Gate 1 wording) |
| **like** (anything like it) | `good5` | at least one good-or-exact item in the top 5 (grade ≥ 2 of 4, or 2 of 3 on old dev labels) |
| either | **worked** | `hit10` on exact searches, `good5` on like searches: "the search worked on the first screen" |
| either | **Gate 1** | `hit5` on exact searches, `good5` on like searches: `docs/08` / `docs/09` M3, "right item in top 5" |

**Cell format.** Q8 value [95% CI], n searches, MDE. The MDE is the smallest paired Q8-vs-arm change that cell could detect at 80% power, using the sd of Q8 − H0r8 on the same cell. "–" means fewer than 3 searches (suppressed), or that the metric does not apply.

**Facet tags.**
- facet_dev uses Derrick's own `based_on` ticks.
- dev, the `known_dev` 100-search sample and `ig_real` (kept evaluator-side) use the Phase A tagger `r9c-v2`.
- `known_dev` facet cells are therefore from the 100-search sample, and its "all" row from all 381.

| # | Facet | Metric | **Proposed target (founders)** | ig_real (real IG, Derrick's searches) | facet_dev (Derrick's sheet) | dev | known_dev (YT, auto labels) | Reading |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **All searches** | Gate 1 | **≥ 80%** (existing Gate 1: 16 of 20) | 0.70 [0.56, 0.85] n31 · 0.14 | 0.79 [0.60, 0.96] n16 · 0.27 | 0.82 [0.69, 0.92] n38 · 0.17 | 0.37 [0.33, 0.42] n381 · 0.033 | Below on real IG and `known_dev`. The shortfall comes from known-item searches |
| 2 | **Known item** (exact) | hit10 | **≥ 80%** | **0.42** [0.13, 0.71] n8 · 0.58 | 0.22 [0, 0.67] n3 · – | 0.67 n3 · – | **0.45** [0.40, 0.49] n381 · 0.036; clean labels ≈ 0.58 [0.47, 0.69]† | **Missed.** CI upper bounds are below 80% |
| 3 | **Topic / like it** | good5 | **≥ 80%** on Derrick's grades (≥ 90% on AI grades as a screen) | 0.86 [0.71, 0.97] n23 · 0.11; floor 0.17 | 0.92 [0.77, 1.00] n13 · 0.29; floor 0.00 | 0.83 [0.71, 0.93] n35 · 0.18; floor 0.07 | – | Met on AI grades; not anchored |
| 4 | **Creator, named** | worked | **≥ 90%** (handle 98%, channel 87%) | – (n1) | 0.56 n3 · – | – (n1) | **0.42** [0.28, 0.57] n46 · 0.13 (top 5: 0.26) | **Missed.** Present but not used |
| 5 | Creator, described | worked | ≥ 60% interim (no creator-profile text yet) | – | – (n2) | – (n2) | – | Not measurable (n ≤ 2) |
| 6 | **Type / format** | worked | **≥ 80%** (format in 87–97% of targets' text) | 0.84 [0.67, 1.00] n17 · 0.18 | 0.79 [0.55, 1.00] n11 · 0.36 | 0.83 [0.69, 0.94] n24 · 0.23 | 0.75 [0.38, 1.00] n8 · 0.41 | About at target on AI grades; not anchored |
| 7 | **Looks** | good5, Derrick-graded | **≥ 60% interim without media; 80% once a media route exists** | AI 0.93 n10; Derrick's target on first screen 0.22 [0, 0.56] n9 | AI 0.71 n7; target 0.00 n6 | AI 1.00 n3 | 0.25 n4 · 0.52 | **Unknown.** Text judges cannot see the look |
| 8 | Sound | good5, Derrick-graded | ≥ 50% interim without media | – (n2) | – (n1) | 0.67 n3 · – | 0.00 n3 · – | Not measurable |
| 9 | Said | – | **No target until founders decide** the rule-8 "what is said" summary | – | – | – (n1) | – (n2) | Not measurable; almost never searched |
| 10 | Tone / vibe | worked | ≥ 80% (te `vibe` 85% IG; 5% YT) | – (n2) | – (n0 ticks) | 0.67 n3 · – | 0.50 n4 · – | Not measurable |
| 11 | **Examples of a quality** | good5, Derrick-graded | **≥ 70%** | AI 0.75 [0.50, 1.00] n8 · 0.27; target 0.00 n6 | AI 0.83 n6 · 0.58; target 0.00 n6 | AI 0.58 n4 · 0.98 | – | Unknown. The AI grade is the only reading, and Derrick's targets are never on the first screen |
| 12 | **When / behaviour** | good5 | **≥ 80%** (dates 100%, watch counts 94%) | – (n1) | – | **0.53** [0.23, 0.80] n10 · 0.44 | – (n2) | Probably missed. Present but not used |
| 13 | Platform named | worked | ≥ 90%, and no wrong-platform item on the first screen | – | – | 0.83 [0.50, 1.00] n6 · 0.19 | – | Too small |

† `known_dev` targets are the next video watched. Phase A flags 23 of the 100 sampled searches as "doubtful auto-label": the target shares no word with the search. Leaving those out gives 0.58. That is an upper reading, because the flag only fires on failures. The true clean rate lies between 0.45 and 0.58, still well below 80%.

**H0r8 for comparison** (same cells):
- known-item hit10: ig_real 0.29, `known_dev` 0.45;
- Gate 1: ig_real 0.67, dev 0.76, facet_dev 0.77;
- named creator 0.41; when 0.63.

Q8 does not move any per-facet cell by more than its MDE.

## Why these targets (anchors)

- **Gate 1 is already the founders' number.** `docs/08-evals-and-quality.md` and `docs/09-roadmap-and-ownership.md` (M3) define it: "right item in top 5 for ≥ 16 of 20 real queries" (80%). Rows 1–3 restate it in per-facet terms. They do not invent a new bar.
  - Known item uses the first screen (top 10), as BRIEF-9 suggests, and Gate 1's top 5 is reported beside it.
  - On top 5, Q8 known-item is 0.25 on ig_real and 0.37 on `known_dev`.
- **Facets where the information is in our text get the full 80%, or more.** These are named creator, type, tone, when and platform. Phase A found the needed information in the target's text for:
  - type: 87–97%;
  - named creator: handle 98%, channel 87%;
  - when: 100%, by rule.
  - A miss there is a query-understanding or routing fault, not a data limit. Named creator gets 90%, because it is a lookup.
- **Facets where the information is mostly missing get an interim bar** until a media route exists. These are looks, sound and examples.
  - For looks searches, our text shows the look in only 18% of targets (32% counting hints).
  - Asking for 80% there would ask the text path for what it cannot hold. 60% / 50% / 70% are judgement calls between today's Derrick floor and Gate 1. The founders should set them.
- **Said has no target.** Transcripts and audio are never stored (rule 8). A "what is said" summary is a founders' decision (BRIEF-9 Track 2). Real searches almost never ask for it (0–3% of searches).
- **Derrick's calibration (72 items) anchors how far an AI "good" can be trusted.**
  - P(Derrick says "clearly what I want" | AI grade):
    - round-8 judge (3-point): 0.04 / 0.29 / 0.63 for grades 0 / 1 / 2, n 24 each;
    - two-judge lower grade (4-point): 0.12 / 0.31 / 0.60 / 0.40 for grades 0 / 1 / 2 / 3, n 17 / 35 / 10 / 10.
  - Item-level "good" rates are similar: Derrick 32%, two-judge good-or-exact 28%. Only 50–63% of AI "good" items are Derrick-good.
  - That is why row 3 asks for ≥ 90% on AI grades as a screen, and the 80% bar is checked on Derrick's own grades.
- **Anchored first-screen share** (linear, no independence assumption). Each item counts as Derrick graded it, or at P(Derrick 2 | AI grade). It gives about 4 in 10 good items on Q8's first screen: ig_real 0.39 [0.25, 0.53], facet_dev 0.40 [0.26, 0.55], dev 0.32 [0.21, 0.43].
  - H0r8 is 0.37 / 0.39 / 0.30.
  - It is descriptive. Calibration items are dev pooled items, so carrying the rates over to other sets is an assumption.

## What it would take to check a target

**Real searches.** A target can only be checked on searches Derrick (or another real user) wrote, with his grades. Searches needed for 80% power, one-sided α 0.025:

| Question | Now | Target | Searches needed |
| --- | --- | --- | --- |
| Is known-item below 80%? | 0.42 | 0.80 | about 10. Already shown: ig_real + facet_dev exact = 11, and both CIs end below 0.80 |
| Does Gate 1 on real IG reach 80%? | 0.70 | 0.80 | about 140 |
| Do like searches really clear 80%? | 0.86 (AI) | 0.80 | about 380 to prove "≥ 80%". About 20–30 to tell whether it is clearly below 80% on Derrick's grades |
| A per-facet cell at MDE ≤ 0.10 | | | about 30–200 per facet (binary metrics: sd_d 0.2–0.5) |

**Cheapest anchor: Derrick grades Q8's top 5 on 20 real "like" searches.** That is 100 items, about 15 minutes.
- Use the `ig_real` topic and facet_test like searches. These are evaluator-side, so their hidden texts never reach builders.
- That is the Gate 1 check as the docs define it.
- It replaces the AI-graded good5 for the facets text judges cannot see: looks, examples and sound.

**Known-item.** About 25 more real known-item searches (Instagram and YouTube; about 35 in all) would give a CI of about ±0.16 on hit10. That is enough to track progress from 0.4 toward 0.8.

## Method notes and caveats

**Runs.** Q8 and H0r8, 3 repeats each:
- dev and `known_dev`: `runs/r8.5/q8`, `runs/r8.1/h0r8`;
- ig_real and facet_dev: `runs/r9/*_{ig_real,facet_dev}`.

**Sets.**
- **ig_real:** this re-reads scoring 1 (Phase 0), with the same runs and labels. No new scoring was used; `ig_real` still has 2 of 3 left. Slices: known_item 8 → exact; topic 22 + meta 1 → like.
- **facet_dev:** `specificity` from Derrick's `want` (3 exact, 13 like).
- **dev:** the 3 single-answer searches of `BRIEF.md` count as exact; the 6 more-like-this searches are left out of the scorecard.
- **facet_test:** not scored. It still has 3 of 3 scorings left.

**facet_dev was pooled and judged in this phase.** Before, its "like" searches could only be scored on the one target: `unjudged10` was 0.99.
- 364 items: every unjudged in-library top-10 item of H0r8, Q8 and FM, all repeats. They went through the two judges (rubric j9-v1, lower-grade rule), as in Phase 0.
- Judges' agreement is lower here than on `ig_real`:
  - 4-point exact 61%, κ 0.46 (linear 0.63);
  - κ relevant vs not 0.53 (Instagram items 0.43, YouTube 0.52).
- Merged as round `r9.B` into `evalset.jsonl`. The backup is `evalset.pre_r9.B.jsonl`, and the judgments log was backed up under `eval_work/r9.B/`.
- No existing grade was overwritten. `facet_real.jsonl` stays Derrick-only.
- **For the loop's evaluators:** facet_dev now has pooled grades for H0r8, Q8 and FM. Pool new arms as usual.

**Statistics.**
- CIs: 95% bootstrap over searches.
- MDE: (t.975 + t.80) · sd_d / √n, with sd_d from Q8 − H0r8 per search (mean over repeats).
- Binary metrics have large sd_d (0.2–0.5 per search), so their MDEs are much larger than nDCG's.

**Facet cells overlap.** A search counts in every facet it needs. "Topic" is near-universal, so the topic row is close to the "all" row.

**The "worked" metric mixes two definitions,** hit10 for exact and good5 for like. Rows 4, 6 and 13 hold both kinds of search. The JSON gives each part separately.

**JSON-only reading:** `good5_indep` = 1 − Π(1 − p_i) over the top 5.
- It assumes independent judge errors within a search. Correlated errors make the truth lower, so read it as an upper reading.
- It is 0.82–0.92 on the like sets.

## Budget and hygiene

**Spend:**
- Phase B: $0.176 for judging the facet_dev pool (gpt-5.4-mini $0.119, gemini-3-flash-preview $0.057, 51 calls each).
- Ledger: OpenAI $5.207 of $9.70, Gemini $4.033 of $6.88.
- Round 9 so far: $0.63 (setup $0.061, Phase 0 $0.241, Phase A $0.157, Phase B $0.176).

**Hygiene:**
- No query text, caption, item code or per-search score is in this file or the JSON.
- The `ig_real` facet tags stay evaluator-side.
- No held-out set was scored.
