"""PROTOTYPE ONLY - Q3 speed aggregates (round 2): timings, costs, two-stage and cache estimates in one summary.

Reads only method-side outputs of this round: rewrite files' per-call seconds and costs and data/runs/speed/*.json.
No labels, no scores. Writes data/runs/speed/summary.json and the chart template
experiments/results/r2-q3-speed-p95.json ({arm: {ndcg10: null, p95_s}}) for the evaluator to fill.

Latency (typed searches; more-like-this searches never call the rewrite):
  total = rewrite call (incl. retries) + B3 search.
  - exp 31-33: paired per search (speed_runs.py timed the search right after loading that rewrite).
  - B3 and the two-stage refined screen: convolution of every gpt-5-nano rewrite call with every warm B3 typed
    search time from speed_instant.py (78 samples); assumes the two are independent.
  - exp 34: paired per search (speed_route.py).
Cache estimate (e): a hit costs the instant search (lookup < 1 ms); a miss costs rewrite + B3 search. Mixture
p50/p95 for assumed hit rates, from the same samples.

usage: python experiments/methods/speed_report.py
"""
import json
import os

import numpy as np

from speed_common import REWRITES, RUNS, dev_queries

SPEED = os.path.join(RUNS, "speed")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REWRITE_SETS = {
    "B3 gpt-5-nano qr-v1, round-1 calls": "qr-v1_gpt-5-nano",
    "B3 gpt-5-nano qr-v1, fresh calls": "qr-v1_gpt-5-nano_t",
    "31 gemini-3.1-flash-lite qr-v1": "qr-v1_gemini-3.1-flash-lite",
    "32 gpt-5.4-nano qr-v1": "qr-v1_gpt-5.4-nano",
    "33 gemini-3.1-flash-lite qr-s1": "qr-s1_gemini-3.1-flash-lite",
    "flash-lite qr-v1, interleaved with 33": "qr-v1_gemini-3.1-flash-lite_t",
}


def rewrite_set(prefix):
    """Per-call rows of the 3 repeats, dev typed searches only (round-1 files also hold test searches)."""
    dev_typed = {x["id"] for x in dev_queries() if not x["examples"]}
    rows = []
    for k in (1, 2, 3):
        pqd = json.load(open(os.path.join(REWRITES, f"{prefix}_r{k}.json")))["_meta"]["per_query"]
        rows += [v for i, v in pqd.items() if i in dev_typed]
    s = np.array([r["seconds"] for r in rows])
    return s, {"calls": len(rows), "p50_s": pq(s, 50), "p95_s": pq(s, 95), "max_s": round(float(s.max()), 3),
               "cost_per_1k_typed_searches_usd": round(1000 * float(np.mean([r["cost_usd"] for r in rows])), 4),
               "mean_in_tokens": round(float(np.mean([r.get("in_tokens", 0) for r in rows])), 1),
               "mean_out_tokens": round(float(np.mean([r.get("out_tokens", 0) for r in rows])), 1),
               "mean_cached_tokens": round(float(np.mean([r.get("cached_tokens", 0) or 0 for r in rows])), 1),
               "retries": int(sum(r.get("attempts", 1) - 1 for r in rows))}


def pq(x, p):
    return round(float(np.percentile(x, p)), 3)


def dist(x):
    return {"n": int(len(x)), "p50_s": pq(x, 50), "p95_s": pq(x, 95)}


def conv(a, b):
    return (np.asarray(a)[:, None] + np.asarray(b)[None, :]).ravel()


def mix_quantiles(hit, miss, h):
    smp = np.concatenate([hit, miss])
    w = np.concatenate([np.full(len(hit), h / len(hit)), np.full(len(miss), (1 - h) / len(miss))])
    o = np.argsort(smp)
    c = np.cumsum(w[o])
    return {p: round(float(smp[o][np.searchsorted(c, p / 100.0)]), 3) for p in (50, 95)}


def main():
    inst = json.load(open(os.path.join(SPEED, "instant_timing.json")))
    route = json.load(open(os.path.join(SPEED, "route.json")))
    pings = {lab: json.load(open(os.path.join(SPEED, f"pings_{lab}.json")))["pings"] for lab in ("c12", "c3")}
    pilot = json.load(open(os.path.join(SPEED, "pilot_c2.json")))["models"]
    inst_s = np.array(inst["samples_typed_s"]["instant"])
    b3_s = np.array(inst["samples_typed_s"]["b3_search"])

    rw, secs = {}, {}
    for label, prefix in REWRITE_SETS.items():
        secs[label], rw[label] = rewrite_set(prefix)
    b3_rec = conv(secs["B3 gpt-5-nano qr-v1, round-1 calls"], b3_s)
    b3_fr = conv(secs["B3 gpt-5-nano qr-v1, fresh calls"], b3_s)
    paired = {e: json.load(open(os.path.join(SPEED, f"{f}_timing.json")))["pooled"]
              for e, f in (("31", "e31_qrv1_flashlite"), ("32", "e32_qrv1_gpt-5.4-nano"), ("33", "e33_qrs1"))}
    n_typed = sum(1 for x in dev_queries() if not x["examples"])
    routed = sum(1 for d in route["decisions"].values() if d["routed"])
    cost_b3 = rw["B3 gpt-5-nano qr-v1, round-1 calls"]["cost_per_1k_typed_searches_usd"]

    cache = {}
    for h in (0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 0.95, 0.97):
        m = mix_quantiles(inst_s, b3_fr, h)
        cache[f"{h:.2f}"] = {"p50_s": m[50], "p95_s": m[95],
                             "rewrite_cost_per_1k_typed_usd": round((1 - h) * cost_b3, 4)}

    out = {
        "search_only_warm": {"instant_typed": dist(inst_s), "b3_typed": dist(b3_s),
                             "instant_all16": inst["instant_search"], "b3_all16": inst["b3_search_only"],
                             "load_avg_1min_end": inst["load_avg_1min_end"]},
        "rewrites": rw,
        "totals_typed": {
            "B3 (round-1 calls, convolved)": dist(b3_rec),
            "B3 (fresh calls, convolved)": dist(b3_fr),
            "30 instant": dist(inst_s),
            **{f"{e} (paired)": {"n": v["total_typed"]["n"], "p50_s": v["total_typed"]["p50_s"],
                                 "p95_s": v["total_typed"]["p95_s"]} for e, v in paired.items()},
            "34 routing (fresh calls, paired)": {k: route["mix_typed_fresh_rewrite"][k] for k in ("n", "p50_s", "p95_s")},
            "34 routing (round-1 calls, paired)": {k: route["mix_typed_recorded_rewrite"][k]
                                                   for k in ("n", "p50_s", "p95_s")},
        },
        "two_stage": {"first_screen": dist(inst_s), "refined_fresh": dist(b3_fr), "refined_round1": dist(b3_rec),
                      "overlap": inst["overlap_refined_vs_instant"]},
        "routing": {"routed_typed": f"{routed}/{n_typed}", "by_kind": route["routed_by_kind"],
                    "entities": route["entities"], "rule_check_ms": route["rule_check_ms"],
                    "rewrite_cost_per_1k_typed_usd": round((1 - routed / n_typed) * cost_b3, 4)},
        "cache_estimate_by_hit_rate": cache,
        "pings": {lab: {m: v["latency"] for m, v in p.items()} for lab, p in pings.items()},
        "pilot_c2": {m: {"latency": v["latency"], "valid": v["valid"], "mean_out_tokens": v["mean_out_tokens"],
                         "cost_usd": v["cost_usd"]} for m, v in pilot.items()},
    }
    json.dump(out, open(os.path.join(SPEED, "summary.json"), "w"), indent=1)
    tt = out["totals_typed"]
    tmpl = {"_note": "Q3 chart input (round 2). p95_s = measured p95 per typed search in seconds, rewrite included "
                     "where the arm has one. ndcg10 is filled by the evaluator (dev, mean of repeats). Render: "
                     "python experiments/methods/speed_chart.py <this file>",
            "B3": {"ndcg10": None, "p95_s": tt["B3 (fresh calls, convolved)"]["p95_s"], "note": "gpt-5-nano qr-v1"},
            "30 instant": {"ndcg10": None, "p95_s": tt["30 instant"]["p95_s"], "note": "no rewrite, no HyDE"},
            "31 flash-lite qr-v1": {"ndcg10": None, "p95_s": tt["31 (paired)"]["p95_s"]},
            "32 gpt-5.4-nano qr-v1": {"ndcg10": None, "p95_s": tt["32 (paired)"]["p95_s"]},
            "33 flash-lite qr-s1": {"ndcg10": None, "p95_s": tt["33 (paired)"]["p95_s"]},
            "34 routing": {"ndcg10": None, "p95_s": tt["34 routing (fresh calls, paired)"]["p95_s"],
                           "note": f"{routed}/{n_typed} typed searches skip the rewrite"}}
    json.dump(tmpl, open(os.path.join(REPO, "experiments", "results", "r2-q3-speed-p95.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
