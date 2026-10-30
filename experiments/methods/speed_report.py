"""PROTOTYPE ONLY - Q3 speed aggregates (round 2): one summary of timings, costs, two-stage and cache estimates.

Reads only method-side outputs of this round (rewrite files' per-call seconds and costs, data/runs/speed/*.json).
No labels, no scores. Writes data/runs/speed/summary.json and the chart template
experiments/results/r2-q3-speed-p95.json ({arm: {ndcg10: null, p95_s}}) for the evaluator to fill.

Latency definitions (typed searches; more-like-this searches never call the rewrite):
  total = rewrite call (incl. retries) + B3 search. Where a rewrite and a search were not timed as a pair, the total
  distribution is the convolution (every rewrite call x every warm search time) - it assumes independence.
Cache estimate (e): a hit costs the instant search (lookup itself is < 1 ms); a miss costs rewrite + B3 search.
  Mixture p50/p95 for assumed hit rates.

usage: python experiments/methods/speed_report.py
"""
import json
import os

import numpy as np

from speed_common import REWRITES, RUNS, dev_queries

SPEED = os.path.join(RUNS, "speed")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rw(prefix):
    secs, costs, tin, tout = [], [], [], []
    for k in (1, 2, 3):
        m = json.load(open(os.path.join(REWRITES, f"{prefix}_r{k}.json")))["_meta"]
        for v in m["per_query"].values():
            secs.append(v["seconds"])
            costs.append(v["cost_usd"])
            tin.append(v.get("in_tokens", 0))
            tout.append(v.get("out_tokens", 0))
    return np.array(secs), np.array(costs), float(np.mean(tin)), float(np.mean(tout))


def q(x, p):
    return round(float(np.percentile(x, p)), 3)


def conv(a, b):
    return (np.asarray(a)[:, None] + np.asarray(b)[None, :]).ravel()


def wquant(samples, weights, p):
    o = np.argsort(samples)
    s, w = np.asarray(samples)[o], np.asarray(weights)[o]
    c = np.cumsum(w) / w.sum()
    return round(float(s[np.searchsorted(c, p / 100.0)]), 3)


def main():
    inst = json.load(open(os.path.join(SPEED, "instant_timing.json")))
    route = json.load(open(os.path.join(SPEED, "route.json")))
    pings = {lab: json.load(open(os.path.join(SPEED, f"pings_{lab}.json")))["pings"] for lab in ("c12", "c3")}
    pilot = json.load(open(os.path.join(SPEED, "pilot_c2.json")))["models"]
    # warm search-only samples from the interleaved timing run (typed searches)
    # (instant_timing.json keeps summaries only; re-derive samples from its summary is impossible, so use the
    #  per-arm timing files for B3 search samples and the instant summary for the first screen)
    arms = {}
    ref_search = []
    for name, f in [("31", "e31_qrv1_flashlite"), ("32", "e32_qrv1_gpt-5.4-nano"), ("33", "e33_qrs1")]:
        t = json.load(open(os.path.join(SPEED, f"{f}_timing.json")))["pooled"]
        arms[name] = t
    rewrites = {
        "B3 qr-v1 gpt-5-nano (round-1 recorded calls)": "qr-v1_gpt-5-nano",
        "B3 qr-v1 gpt-5-nano (fresh, this session)": "qr-v1_gpt-5-nano_t",
        "31 qr-v1 gemini-3.1-flash-lite": "qr-v1_gemini-3.1-flash-lite",
        "32 qr-v1 gpt-5.4-nano": "qr-v1_gpt-5.4-nano",
        "33 qr-s1 gemini-3.1-flash-lite": "qr-s1_gemini-3.1-flash-lite",
        "ref qr-v1 gemini-3.1-flash-lite (interleaved with 33)": "qr-v1_gemini-3.1-flash-lite_t",
    }
    rew = {}
    for label, prefix in rewrites.items():
        s, c, tin, tout = rw(prefix)
        rew[label] = {"n_calls": len(s), "rewrite_p50_s": q(s, 50), "rewrite_p95_s": q(s, 95),
                      "rewrite_max_s": round(float(s.max()), 3),
                      "cost_per_1k_typed_searches_usd": round(1000 * float(c.mean()), 4),
                      "mean_in_tokens": round(tin, 1), "mean_out_tokens": round(tout, 1), "_secs": s}
    # B3 search-only distribution: use the typed search samples behind exp 31-33 (same B3 code, same box) via
    # their pooled summaries is not enough for a convolution, so approximate the B3 search as the instant-timing
    # run's B3 typed summary: normal-free approach = use exp 31's per-run search p50/p95 is coarse. Instead we take
    # the paired totals where we have them (31-33 from speed_runs, B3 fresh/recorded from speed_route) and use
    # convolution only for the cache mixture, with search time fixed at the measured B3 typed p50 + spread.
    b3_search = inst["b3_search_only_typed"]
    inst_typed = inst["instant_search_typed"]
    totals = {
        "B3 (round-1 recorded rewrite)": route["b3_all16_recorded_rewrite"],
        "B3 (fresh gpt-5-nano rewrite)": route["b3_all16_fresh_rewrite"],
    }
    # typed-only B3 totals: rewrite calls + B3 search, approximated by convolution with a 3-point search sample
    # (p50, mean, p95 of the warm B3 typed search) so the shape is dominated by the rewrite distribution.
    srch = np.array([b3_search["p50_s"], b3_search["mean_s"], b3_search["p95_s"]])
    inst_s = np.array([inst_typed["p50_s"], inst_typed["mean_s"], inst_typed["p95_s"]])
    b3_typed = {}
    for label in ("B3 qr-v1 gpt-5-nano (round-1 recorded calls)", "B3 qr-v1 gpt-5-nano (fresh, this session)"):
        tot = conv(rew[label]["_secs"], srch)
        b3_typed[label] = {"total_p50_s": q(tot, 50), "total_p95_s": q(tot, 95)}
    # cache mixture (e): hits = instant search, misses = fresh gpt-5-nano rewrite + B3 search
    miss = conv(rew["B3 qr-v1 gpt-5-nano (fresh, this session)"]["_secs"], srch)
    hit = inst_s
    cache = {}
    for h in (0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 0.95, 0.97):
        smp = np.concatenate([hit, miss])
        w = np.concatenate([np.full(len(hit), h / len(hit)), np.full(len(miss), (1 - h) / len(miss))])
        cache[f"hit_{h:.2f}"] = {"p50_s": wquant(smp, w, 50), "p95_s": wquant(smp, w, 95),
                                 "rewrite_cost_per_1k_typed_usd": round(
                                     (1 - h) * rew["B3 qr-v1 gpt-5-nano (fresh, this session)"][
                                         "cost_per_1k_typed_searches_usd"], 4)}
    n_typed = sum(1 for x in dev_queries() if not x["examples"])
    routed = sum(1 for d in route["decisions"].values() if d["routed"])
    out = {
        "search_only": {"instant_all16": inst["instant_search"], "instant_typed": inst_typed,
                        "b3_all16": inst["b3_search_only"], "b3_typed": b3_search, "calls_each": inst["calls"]},
        "two_stage": {"first_screen_typed": inst_typed,
                      "refined_typed_round1_rewrite": b3_typed["B3 qr-v1 gpt-5-nano (round-1 recorded calls)"],
                      "refined_typed_fresh_rewrite": b3_typed["B3 qr-v1 gpt-5-nano (fresh, this session)"],
                      "overlap": inst["overlap_refined_vs_instant"]},
        "rewrites": {k: {kk: vv for kk, vv in v.items() if kk != "_secs"} for k, v in rewrites_out(rew).items()},
        "arms_paired_totals": arms,
        "b3_paired_totals_all16": totals,
        "routing": {"routed_typed": f"{routed}/{n_typed}", "by_kind": route["routed_by_kind"],
                    "entities": route["entities"], "rule_check_ms": route["rule_check_ms"],
                    "mix_typed_fresh": route["mix_typed_fresh_rewrite"],
                    "mix_typed_recorded": route["mix_typed_recorded_rewrite"],
                    "mix_all16_fresh": route["mix_all16_fresh_rewrite"],
                    "rewrite_cost_per_1k_typed_usd": round((1 - routed / n_typed) * rew[
                        "B3 qr-v1 gpt-5-nano (round-1 recorded calls)"]["cost_per_1k_typed_searches_usd"], 4)},
        "cache_estimate": cache,
        "pings": {lab: {m: v["latency"] for m, v in p.items()} for lab, p in pings.items()},
        "pilot_c2": {m: {"latency": v["latency"], "valid": v["valid"], "mean_out_tokens": v["mean_out_tokens"]}
                     for m, v in pilot.items()},
    }
    json.dump(out, open(os.path.join(SPEED, "summary.json"), "w"), indent=1)
    tmpl = {"_note": "Q3 chart input template (round 2). p95_s = measured p95 per typed search in seconds, rewrite "
                     "included where the arm has one; ndcg10 to be filled by the evaluator (dev, mean of repeats). "
                     "Render with: python experiments/methods/speed_chart.py <this file>",
            "B3": {"ndcg10": None, "p95_s": b3_typed["B3 qr-v1 gpt-5-nano (fresh, this session)"]["total_p95_s"],
                   "note": "qr-v1 gpt-5-nano + search"},
            "30 instant": {"ndcg10": None, "p95_s": inst_typed["p95_s"], "note": "no rewrite, no HyDE"},
            "31 flash-lite qr-v1": {"ndcg10": None, "p95_s": arms["31"]["total_typed"]["p95_s"]},
            "32 gpt-5.4-nano qr-v1": {"ndcg10": None, "p95_s": arms["32"]["total_typed"]["p95_s"]},
            "33 flash-lite qr-s1": {"ndcg10": None, "p95_s": arms["33"]["total_typed"]["p95_s"]},
            "34 routing": {"ndcg10": None, "p95_s": route["mix_typed_fresh_rewrite"]["p95_s"],
                           "note": f"{routed}/{n_typed} typed searches routed to instant"}}
    json.dump(tmpl, open(os.path.join(REPO, "experiments", "results", "r2-q3-speed-p95.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


def rewrites_out(rew):
    return rew


if __name__ == "__main__":
    main()
