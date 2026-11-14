"""PROTOTYPE ONLY - round 6 rewrites: qr-v1, prompt unchanged, on a stronger model (LOG.md Y6-G1, Y6-G2).

  pilot  token / cost / latency pilot on 4 invented searches (fixed in LOG.md; not eval searches, outputs unused),
         for G2's model rule and to confirm each model's reasoning setting works with qr-v1's strict schema.
  run    3 independent repeats over the typed dev + yt_holdout searches (cache salt = repeat), written to
         $DIGESTER_DATA/runs/rewrites/qr-v1_<model>_r<k>.json in llm_rewrite.py's shape (+ per-query cost, seconds,
         tokens). Every call is cached (c6_lib.cached_chat).
Prints aggregates only (no query text).

usage: python experiments/methods/c6_rewrite.py pilot --models gpt-5.4-mini,gpt-5.5
       python experiments/methods/c6_rewrite.py run --model gpt-5.4-mini [--repeats 1,2,3]
           [--queries FILE --outdir DIR --splits NAME]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c6_lib as G  # noqa: E402
from corpus import DATA, load_queries  # noqa: E402

RW_DIR = os.path.join(DATA, "runs", "rewrites")
PILOT = ["lofi beats for studying late at night", "that guy who builds tiny houses out of shipping containers",
         "should I learn piano or guitar next", "how to knit a sweater as a beginner"]


# Alternative query file (e.g. frozen held-out searches): set from the CLI; defaults keep the dev + yt_holdout runs.
ALT = {"queries": None, "outdir": None, "splits": None}


def typed_queries():
    if ALT["queries"]:
        with open(ALT["queries"]) as f:
            qs = [json.loads(line) for line in f if line.strip()]
    else:
        qs = load_queries("dev") + load_queries("yt_holdout")
    return [q for q in qs if not q["examples"]]


def pilot(models):
    for m in models:
        rows = []
        for q in PILOT:
            p, rec = G.rewrite_one(q, m, "pilot", purpose="c6_rewrite_pilot")
            rows.append({**{k: rec[k] for k in ("cost_usd", "seconds", "in_tokens", "out_tokens", "reasoning_tokens",
                                                "cached_tokens", "cached")},
                         "n_phrases": len(p["phrases"]), "n_keywords": len(p["keywords"]),
                         "n_captions": len(p["hypothetical_captions"])})
        mean_cost = float(np.mean([r["cost_usd"] for r in rows]))
        out = {"model": m, "reasoning": G.REASONING[m], "n": len(rows), "mean_cost_usd": round(mean_cost, 6),
               "projected_141_calls_usd": round(141 * mean_cost * 1.15, 4),
               "mean_in": float(np.mean([r["in_tokens"] for r in rows])),
               "mean_out": float(np.mean([r["out_tokens"] for r in rows])),
               "mean_reasoning": float(np.mean([r["reasoning_tokens"] for r in rows])),
               "seconds": [r["seconds"] for r in rows], "all_valid": all(r["n_captions"] == 3 for r in rows)}
        print(json.dumps(out), flush=True)
    print(f"openai ledger total ${ai.spent('openai'):.4f}")


def run(model, reps):
    qs = typed_queries()
    for k in reps:
        t0 = time.time()
        parses, per_q, new = {}, {}, 0
        for q in qs:
            p, rec = G.rewrite_one(q["query"], model, k)
            parses[q["id"]] = p
            new += not rec["cached"]
            per_q[q["id"]] = {"seconds": rec["seconds"], "cost_usd": rec["cost_usd"], "in_tokens": rec["in_tokens"],
                              "out_tokens": rec["out_tokens"], "reasoning_tokens": rec["reasoning_tokens"],
                              "cached_tokens": rec.get("cached_tokens", 0)}
        wall = time.time() - t0
        secs = [v["seconds"] for v in per_q.values()]
        meta = {"model": model, "prompt_version": G.PROMPT_VERSION, "reasoning_effort": G.REASONING[model],
                "max_completion_tokens": G.MAX_TOKENS[model], "repeat": k, "n": len(parses),
                "cost_usd": sum(v["cost_usd"] for v in per_q.values()),
                "rewrite_p50_s": round(float(np.median(secs)), 3),
                "rewrite_p95_s": round(float(np.percentile(secs, 95)), 3), "wall_s": round(wall, 1),
                "new_calls": new, "splits": ALT["splits"] or ["dev", "yt_holdout"], "per_query": per_q}
        if ALT["queries"]:
            meta["queries_file"] = os.path.basename(ALT["queries"])
        out = {"_note": f"qr-v1 rewrite (prompt unchanged) on {model}, reasoning {G.REASONING[model]}, run r{k}. "
                        "Written by experiments/methods/c6_rewrite.py (round 6).", "_meta": meta, **parses}
        os.makedirs(ALT["outdir"] or RW_DIR, exist_ok=True)
        path = os.path.join(ALT["outdir"] or RW_DIR, f"{G.PROMPT_VERSION}_{model}_r{k}.json")
        json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
        print(f"wrote {os.path.basename(path)}: {len(parses)} searches, {new} new calls, wall {wall:.1f} s "
              f"({len(parses) / max(wall, 1e-9):.2f} items/s), cost ${meta['cost_usd']:.4f}, p50 {meta['rewrite_p50_s']} s, "
              f"p95 {meta['rewrite_p95_s']} s, mean out {np.mean([v['out_tokens'] for v in per_q.values()]):.0f}, "
              f"mean reasoning {np.mean([v['reasoning_tokens'] for v in per_q.values()]):.0f}", flush=True)
    print(f"openai ledger total ${ai.spent('openai'):.4f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pilot")
    p.add_argument("--models", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--repeats", default="1,2,3")
    r.add_argument("--queries", default=None, help="alternative query file (same format as evals/queries.jsonl)")
    r.add_argument("--outdir", default=None, help="rewrite file dir (default runs/rewrites)")
    r.add_argument("--splits", default=None, help="comma list recorded in meta.splits")
    a = ap.parse_args()
    if a.cmd == "run":
        ALT.update({"queries": a.queries, "outdir": a.outdir, "splits": a.splits.split(",") if a.splits else None})
    if a.cmd == "pilot":
        pilot(a.models.split(","))
    else:
        run(a.model, [int(x) for x in a.repeats.split(",")])


if __name__ == "__main__":
    main()
