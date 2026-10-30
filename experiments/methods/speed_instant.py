"""PROTOTYPE ONLY - Q3 (a) instant path and (b) two-stage screen, round 2 (experiment 30).

(a) Instant path = B3 with no rewrite: raw query as the only phrase, no keywords, no HyDE vector
    (speed_common.EMPTY). Deterministic: one run file data/runs/e30_instant.json.
(b) Two-stage = instant screen, then the refined B3 list. No new ranking. This script times, in the same
    warm process and interleaved per search, the instant search and the B3 search (stack.py hyde=1 on the cached
    qr-v1 gpt-5-nano r{k} rewrite; cycle k uses repeat k), and checks that the B3 search reproduces
    e20_hyde_b2_r{k}. It reports the label-free overlap: of the refined (B3 r{k}) top 10, how many were already in
    the instant top 10, mean over searches, per repeat.
Rewrite latency for "time to refined" is added later by speed_report.py from the rewrite files' measured calls.

usage: python experiments/methods/speed_instant.py [--cycles 3]
Writes data/runs/e30_instant.json and data/runs/speed/instant_timing.json. Prints aggregates only.
"""
import argparse
import json
import os
import time

import numpy as np

from speed_common import EMPTY, REWRITES, RUNS, dev_queries, load_b3, load_run, summary, timed_search, warm, \
    write_run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    S, C = load_b3()
    qs = dev_queries()
    typed = [q["id"] for q in qs if not q["examples"]]
    P = {k: json.load(open(os.path.join(REWRITES, f"qr-v1_gpt-5-nano_r{k}.json"))) for k in (1, 2, 3)}
    warm(S, qs)
    warm(S, qs, lambda q: P[1][q["id"]])

    # deterministic instant run
    out = {}
    for q in qs:
        fused, _ = timed_search(S, q, EMPTY)
        out[q["id"]] = fused[:1000]

    # interleaved timing: instant vs B3 search-only, all 16 dev searches per cycle
    lat_i, lat_b, lat_i_typed, lat_b_typed, same = [], [], [], [], {1: 0, 2: 0, 3: 0}
    ref = {k: load_run(os.path.join(RUNS, f"e20_hyde_b2_r{k}.json")) for k in (1, 2, 3)}
    for c in range(a.cycles):
        k = c % 3 + 1
        for q in qs:
            fi, si = timed_search(S, q, EMPTY)
            fb, sb = timed_search(S, q, None if q["examples"] else P[k][q["id"]])
            lat_i.append(si)
            lat_b.append(sb)
            if not q["examples"]:
                lat_i_typed.append(si)
                lat_b_typed.append(sb)
            if c < 3:
                same[k] += int(fb[:1000] == ref[k][q["id"]])
            assert fi[:1000] == out[q["id"]], "instant path is not deterministic"

    # label-free overlap: refined top 10 already in the instant top 10
    overlap = {}
    for k in (1, 2, 3):
        o_all = [len(set(ref[k][q["id"]][:10]) & set(out[q["id"]][:10])) for q in qs]
        o_typed = [len(set(ref[k][i][:10]) & set(out[i][:10])) for i in typed]
        first_same = [ref[k][i][0] == out[i][0] for i in typed]
        overlap[f"r{k}"] = {"mean_overlap10_all16": round(float(np.mean(o_all)), 2),
                            "mean_overlap10_typed": round(float(np.mean(o_typed)), 2),
                            "min_overlap10_typed": int(min(o_typed)), "max_overlap10_typed": int(max(o_typed)),
                            "typed_searches_top1_unchanged": int(sum(first_same)), "n_typed": len(typed)}
    wall = time.time() - t0
    timing = {"cycles": a.cycles, "calls": len(lat_i), "load_avg_1min_end": round(os.getloadavg()[0], 2),
              "instant_search": summary(lat_i), "instant_search_typed": summary(lat_i_typed),
              "b3_search_only": summary(lat_b), "b3_search_only_typed": summary(lat_b_typed),
              "b3_reproduces_e20": {f"r{k}": f"{v}/{len(qs)}" for k, v in same.items()},
              "overlap_refined_vs_instant": overlap, "wall_s": round(wall, 1)}
    meta = {"base": "B3 (stack.py hyde=1, te-v1c) with no rewrite: raw query only, no keywords, no HyDE",
            "rewrite": "none", "cost_usd": 0.0, "rewrite_p50_s": 0.0,
            "query_p50_s": timing["instant_search"]["p50_s"], "query_p95_s": timing["instant_search"]["p95_s"],
            "typed_query_p50_s": timing["instant_search_typed"]["p50_s"],
            "typed_query_p95_s": timing["instant_search_typed"]["p95_s"], "timed_calls": len(lat_i),
            "experiment": 30}
    write_run(os.path.join(RUNS, "e30_instant.json"), "stack_b2:hyde=1+norewrite+te-v1c", C.emb_name, meta, out)
    os.makedirs(os.path.join(RUNS, "speed"), exist_ok=True)
    json.dump(timing, open(os.path.join(RUNS, "speed", "instant_timing.json"), "w"), indent=1)
    print(json.dumps(timing, indent=1))
    print(f"items processed {len(lat_i) * 2} searches, {len(lat_i) * 2 / wall:.2f} searches/s, wall {wall:.1f} s")


if __name__ == "__main__":
    main()
