# Evaluator protocol (one round)

The evaluator is a fresh agent each round that did not build what it scores. It is the only role that opens `data/evals/labels/`.

Setup: `cd /home/user/digester && source .venv/bin/activate && export DIGESTER_DATA=$PWD/data`.

## Steps

1. **Score** every run in the round on **dev** against the current labels, each with `--vs` its stated base:
   `python experiments/eval/score_run.py data/runs/X.json --split dev --vs data/runs/BASE.json --json data/eval_work/rN/X.json`
2. **Pool** if any run has `unjudged10` > 0.15: run each such run once more with `--pool data/eval_work/pool_rN.json` (one pool file for the round).
3. **Judge blind:** `python experiments/eval/judge.py sheet data/eval_work/pool_rN.json data/eval_work/sheet_rN.txt`. Read the sheet and grade every line from the sheet content only: 2 = clearly what the search wants, 1 = borderline, 0 = not relevant. Never look up which run surfaced an item. For more-like-this lines (no query text), judge against the example item(s) in `data/evals/queries.jsonl` (look them up in `data/corpus/items.jsonl`). Do **not** read the Muse export or Muse reports before judging. Grades go to `data/eval_work/grades_rN.json` as a JSON list in sheet order.
4. **Back up, then merge:** copy `data/evals/labels/evalset.jsonl` to `data/evals/labels/evalset.pre_rN.jsonl`, then `python experiments/eval/judge.py merge data/eval_work/sheet_rN.txt data/eval_work/grades_rN.json --judge "claude-evaluator-rN"`.
5. **Re-score** every run in the round *and* the current finalists (named in the task) on the new labels.
6. **Report** to `experiments/results/<date>-<round or experiment>.md` (+ `.json`): per run nDCG@10 with CI, Δ vs base with paired CI and W/L/T, P@10, MRR, R@100, success@5, unjudged10, per-kind nDCG@10 and R@100, the mean over the three single-answer searches as one group, cost and latency from the run's `meta`, and the adoption verdict by the rule in `BRIEF.md`:
   adopt if Δ ≥ 0.03 with the paired 95% CI above 0, or Δ ≥ 0.02 with more wins than losses and no extra cost.
7. **Fill in the LOG row(s):** replace the `(evaluator)` cells of the experiment's row in `experiments/LOG.md` in place (a small Python string replace on that row only; others may be appending rows concurrently).

## What may be written where

- `experiments/results/`: aggregates only. No captions, item IDs/codes, MU text, per-item labels, or per-query scores next to query texts. Per-kind averages and groups of ≥ 3 searches are fine.
- `data/eval_work/rN/`: per-query detail, sheets, grades (gitignored).
- The test split is scored only when the orchestrator says so (max 3 times in the whole loop).
- Return to the orchestrator: aggregate numbers only.
