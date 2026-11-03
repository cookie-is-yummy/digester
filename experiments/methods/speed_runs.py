"""PROTOTYPE ONLY - Q3 (c) B3 runs on the faster rewrites (experiments 31-33), round 2.

For each repeat k: loads data/runs/rewrites/<prefix>_r<k>.json (written by speed_rewrite.py), runs B3
(stack.py Stack, hyde=1, te-v1c; imported, not edited) on the 16 dev searches in a warm process, and writes
data/runs/<out>_r<k>.json. Per typed search: total = that call's measured rewrite seconds (incl. retries) + the
measured search seconds. More-like-this searches have no rewrite (total = search).

usage: python experiments/methods/speed_runs.py --prefix qr-v1_gemini-3.1-flash-lite --out e31_qrv1_flashlite \
         --experiment 31
Prints aggregates only.
"""
import argparse
import json
import os
import time

import numpy as np

from speed_common import REWRITES, RUNS, dev_queries, load_b3, summary, timed_search, warm, write_run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--experiment", type=int, required=True)
    ap.add_argument("--repeats", nargs="+", type=int, default=[1, 2, 3])
    a = ap.parse_args()
    t0 = time.time()
    S, C = load_b3()
    qs = dev_queries()
    allrows = {"rewrite": [], "search_typed": [], "total_typed": [], "total_all": []}
    for k in a.repeats:
        P = json.load(open(os.path.join(REWRITES, f"{a.prefix}_r{k}.json")))
        RW = P["_meta"]
        warm(S, qs, lambda q: P[q["id"]])
        out, rw, st, tt, ta = {}, [], [], [], []
        for q in qs:
            fused, s = timed_search(S, q, None if q["examples"] else P[q["id"]])
            out[q["id"]] = fused[:1000]
            if q["examples"]:
                ta.append(s)
                continue
            r = RW["per_query"][q["id"]]["seconds"]
            rw.append(r)
            st.append(s)
            tt.append(r + s)
            ta.append(r + s)
        costs = [v["cost_usd"] for v in RW["per_query"].values()]
        meta = {"base": "B3 (stack.py hyde=1, te-v1c) on a Q3 speed rewrite", "experiment": a.experiment,
                "rewrite": f"{a.prefix}_r{k}.json",
                "model": RW["model"], "prompt_version": RW["prompt_version"],
                "reasoning_effort": RW.get("reasoning_effort"), "repeat": k,
                "cost_usd": round(sum(costs), 6), "rewrite_n": len(costs),
                "rewrite_cost_per_1k_searches_usd": round(1000 * float(np.mean(costs)), 4),
                "rewrite_p50_s": summary(rw)["p50_s"], "rewrite_p95_s": summary(rw)["p95_s"],
                "typed_query_p50_s": summary(st)["p50_s"], "typed_query_p95_s": summary(st)["p95_s"],
                "typed_total_p50_s": summary(tt)["p50_s"], "typed_total_p95_s": summary(tt)["p95_s"],
                "all16_total_p50_s": summary(ta)["p50_s"], "all16_total_p95_s": summary(ta)["p95_s"],
                "mean_in_tokens": RW.get("mean_in_tokens"), "mean_out_tokens": RW.get("mean_out_tokens")}
        method = f"stack_b2:hyde=1+{RW['prompt_version']}_{RW['model']}_r{k}+te-v1c"
        write_run(os.path.join(RUNS, f"{a.out}_r{k}.json"), method, C.emb_name, meta, out)
        allrows["rewrite"] += rw
        allrows["search_typed"] += st
        allrows["total_typed"] += tt
        allrows["total_all"] += ta
    agg = {k: summary(v) for k, v in allrows.items()}
    os.makedirs(os.path.join(RUNS, "speed"), exist_ok=True)
    json.dump({"prefix": a.prefix, "out": a.out, "experiment": a.experiment, "pooled": agg},
              open(os.path.join(RUNS, "speed", f"{a.out}_timing.json"), "w"), indent=1)
    print(json.dumps(agg))
    print(f"wall {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
