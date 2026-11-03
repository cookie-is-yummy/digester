# Experiments

**PROTOTYPE code.** This is where search and enrichment ideas are tested on real data before they become product code. Nothing here is imported by `scrolldigest/`. The working brief for the autonomous loop is [BRIEF.md](BRIEF.md); results go in [LOG.md](LOG.md).

## Layout

```
experiments/
  BRIEF.md        the loop: goals, roles, rules, phases
  LOG.md          one row per experiment (hypothesis, cost, result); negative results stay
  STATE.md        where the loop is and what's next, so a fresh session can resume
  lib/            method-side helpers: corpus.py (data, BM25, dense, rank fusion, run files),
                  ai.py (every paid AI call: env keys, ledger, hard budget), ai_prices.json
  methods/        one script per method; each writes a run file and never reads labels
  eval/           EVALUATOR ONLY: score_run.py (metrics, CIs, paired deltas), judge.py (blind judging)
  results/        aggregate scores only (JSON + short notes), no per-item data
  research/       literature notes per flaw
  archive/        earlier scripts kept for reference (old paths; don't run as-is)
```

## Data (never committed)

Real data lives in `data/` at the repo root (gitignored) or wherever `$DIGESTER_DATA` points:

```
data/
  corpus/items.jsonl            21,293 Instagram items from one founder's export (+ DM shares)
  corpus/interactions.jsonl     25,737 interactions (save, like, collection, share_self, share_friend)
  corpus/emb/bge_full/          bge-small-en-v1.5 384d (float16) of the 'full' text view, 20,202 items with any text
  corpus/emb/openai3s_512/      text-embedding-3-small at 512d (float16), same items
  evals/queries.jsonl           22 searches, method side: id, query, kinds, examples, filters. No answers
  evals/query_parses.json       hand-simulated AI rewrites (phrases, keywords) for the 18 typed searches
  evals/split.json              dev (16) / test (6)
  evals/qcache/                 query vectors for API embeddings
  evals/labels/                 EVALUATOR ONLY:
                                  evalset.jsonl (graded answers, hard negatives, judged_not_relevant)
                                  muse_reports/ (where the answers came from)
                                  judgments_log.jsonl
  ai_runs.jsonl                 cost ledger written by lib/ai.py
```

## Run

```bash
uv venv && uv pip install numpy scipy scikit-learn fastembed wordninja
export DIGESTER_DATA=$PWD/data
python experiments/methods/baseline.py --emb bge_full --variant hybrid_prf --out data/runs/baseline.json
python experiments/eval/score_run.py data/runs/baseline.json --split dev          # evaluator
```

Run files are stored as content codes. Keep them in `data/runs/`, because ranked lists of a real person's items are personal data. Commit only the aggregate report.
