# Evaluator protocol (one round)

The evaluator is a fresh agent each round that did not build what it scores. It is the only role that opens `data/all/evals/labels/`.

Setup: `cd /home/user/digester && source .venv/bin/activate && export DIGESTER_DATA=$PWD/data/all`. The scorer is `experiments/eval/score_c4.py` (three repeats per run, `--rundir DIR --runs STEM ... --cmp RUN:BASE`). *(Changed in round 8, see audit: the old setup line pointed at the round-1 Instagram root `data/` and `score_run.py`.)*

## Steps

1. **Score** every run in the round against the current labels, each with `--cmp` against its stated base:
   `python experiments/eval/score_c4.py --rundir data/all/runs/rN --split dev --runs X BASE --cmp X:BASE --out data/all/eval_work/rN/X.json --detail data/all/eval_work/rN/X_detail.json`
   - The split must be one named in `evals/split.json`, or `known_test_clean`. The scorer now refuses unknown names. *(Changed in round 8, see audit: before, an unknown name such as `known_dev` silently scored every search in the run.)*
2. **Pool** every unjudged in-library top-10 item of every run in the round: run once more with `--pool data/all/eval_work/pool_rN.json`, one pool file for the round. Do not skip pooling when `unjudged10` is low. *(Changed in round 8, see audit: the old trigger was `unjudged10` > 0.15. Arms gain about +0.07 nDCG@10 per unit of extra unjudged share once pooled, so a small leftover still tilts comparisons.)*
   - **Known-item sets** (`known_*`, `ig_known_*`) are not pooled. Only the target is known.
3. **Judge blind:** `python experiments/eval/judge.py sheet ...`. Grade every line from the sheet content only: 2 = clearly what the search wants, 1 = borderline, 0 = not relevant.
   - Never look up which run surfaced an item.
   - The sheet must show the search's `intent` (the person's clarification) when it has one. For more-like-this lines, show the example item text. *(Changed in round 8, see audit: the round-8 re-judging sheet did this; `judge.py` showed only the query text.)*
   - Do **not** read the Muse export or Muse reports before judging.
   - Grades go to `data/all/eval_work/grades_rN.json` as a JSON list in sheet order.
   - **Measured judge quality (round 8 audit):**
     - Two fresh Claude judges agree with each other at κ 0.66 (relevant vs not; 75% exact) and with the original grades at κ 0.54–0.66.
     - They agree with Derrick at only κ 0.39–0.43 (60–62% exact). They are slightly stricter than he is, most of all on items with little text.
     - Read single-judge pooled grades as noisy. That is why steps 6c and 6d below are required.
4. **Back up, then merge:** copy `labels/evalset.jsonl` to `labels/evalset.pre_rN.jsonl`, then `python experiments/eval/judge.py merge data/all/eval_work/sheet_rN.txt data/all/eval_work/grades_rN.json --judge "claude-evaluator-rN"`.
   - Never overwrite Derrick's grades (`relevant` / `judged_nonrelevant` rows from his vetting).
5. **Re-score** every run in the round *and* the current finalists (named in the task) on the new labels.
6. **Report** to `experiments/results/<round>-eval.md` (+ `.json`). Include:
   - per run: nDCG@10 with CI, Δ vs base with paired CI and W/L/T, P@10, MRR, R@100, success@5, unjudged10;
   - per-kind nDCG@10 and R@100;
   - the mean over the three single-answer searches as one group;
   - cost and latency from the run's `meta`;
   - the adoption verdict by the rule in `BRIEF.md`.

   *(Changed in round 8, see audit:)* every report also gives:
   a. **Power.** For each comparison: n, the SD of the per-search Δ (`sd_d`), and the minimum detectable Δ at 80% power, MDE ≈ 2.8 · sd_d / √n (use t quantiles below 30 searches).
      - Call a result with |Δ| below its MDE **"within noise"**, not a "near miss".
      - Typical `sd_d` is 0.07–0.17 for nDCG@10. That gives an MDE of 0.12 on 10 searches, 0.075 on 21, 0.05 on 44, 0.027 on 150 and 0.017 on 381 at the median `sd_d` (0.117).
   b. **Arms in the round.** Count the arms compared with the base this round. Give Holm-adjusted p-values (one-sided paired test, α = 0.025) next to the CI. If the rule passes and Holm fails, label the verdict "passes the rule, not the family-wise test".
   c. **Grade sensitivity, required:**
      - this round's grade-1 items set to 0;
      - seed-only (Derrick's labels only), on any set that has his grades;
      - the share of the relevant top-10 items that rest on this round's grades.
   d. **Pooled share.** The Δ before pooling (seed) and after. State how much of the reported Δ comes from newly pooled grades.
   e. **R@100 and nDCG@20 are descriptive only.** Ranks 21–100 are 65–82% unjudged, and R@100 could move by up to about 0.10–0.25 if they were judged. Don't base a verdict on them.
   f. **Known-item sets** (`known_dev`, `known_test`, `ig_known_*`):
      - the main metrics are `mrr2` and `s10_2`: MRR and success@10 of the **grade-2 target only**;
      - any-grade `mrr` / `success10` are secondary;
      - grade-1 "later" videos are mostly autoplay or unrelated: 75% share no word with the search, and 21% start exactly when the previous video ends;
      - score `known_test` on the session-disjoint subset `known_test_clean` (216 of 381 searches) as primary, and on the full set as secondary.
      - *(changed in round 8, see audit)*
7. **Fill in the LOG row(s):** replace the `(evaluator)` cells of the experiment's row in `experiments/LOG.md` in place (a small Python string replace on that row only; others may be appending rows concurrently).

## Held-out hygiene (changed in round 8, see audit)

- Held-out query texts (`test`, `test2`, `known_test`, `ig_known_test`) must not sit in method-side caches before their scoring. Round 8 found `test` / `test2` texts in method-side caches: `corpus/emb/*_queries/ids.json` and `runs/rewrites/test*`.
  - The orchestrator makes held-out rewrites and embeddings in a separate step, right before the scoring, and writes them under `runs/rewrites/<split>/`.
  - Builders do not read those folders.
- Don't write per-search diagnoses of held-out failures into files builders read (`STATE.md`, briefs, `docs/research/`) while the set still has scorings left. Write per-scope or per-kind aggregates instead. A set whose failures were diagnosed per search counts as **used** for any method designed after that diagnosis.
- Known-item splits must be **session-disjoint**: no search within 30 minutes of a search in the other split, no shared watched video, no near-duplicate wording (word Jaccard ≥ 0.5). The round-8 `known_dev` / `known_test` split was random. 24% of `known_test` targets are relevant items in `known_dev`, and 91 test searches sit within 5 minutes of a dev search.

## What may be written where

- `experiments/results/`: aggregates only.
  - No captions, item IDs/codes, MU text, per-item labels, or per-query scores next to query texts.
  - Per-kind averages and groups of ≥ 3 searches are fine.
- `data/all/eval_work/rN/`: per-query detail, sheets, grades (gitignored).
- The test splits are scored only when the orchestrator says so (max 3 times each in the whole loop).
- Return to the orchestrator: aggregate numbers only.
