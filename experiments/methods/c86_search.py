"""PROTOTYPE ONLY - round 8.6 run files (LOG.md "Round 8.6 fixed parameters", rows Y8.6-WP, Y8.6-FL).

Configs (one variable each vs B8.5 = Q8, q8-v1 = runs/r8.5/q8_r{k}); every config runs on the int8 item store:
  q8   B8.5 from this runner: must equal runs/r8.5/q8_r{k} exactly (reproduction gate; written to tmp/ only).
  wp   Y8.6-WP: YouTube interaction prior in fused-rank places (cap 5), after P's multiplier, before the refine.
  fl   Y8.6-FL: YouTube items' shared-BM25 term -> title-only (1.0) + channel-only (0.5) BM25 RRF terms.
q_ig is read from the B8.5 own-list fusion in every config, so the multiplier and the refine gate equal B8.5's.
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat).

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
+ max(round 8.1's live 3-large call, round 8.3's live 3-small te call) (parallel) + the refine call's seconds.

usage: python experiments/methods/c86_search.py refine --configs wp,fl [--reps 1,2,3] [--workers 4]  # paid if uncached
       python experiments/methods/c86_search.py run --configs q8,wp,fl [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c86_search.py compare --a DIR --b DIR --configs ...
"""
import argparse
import collections
import concurrent.futures as cf
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c4_intent as I  # noqa: E402
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c7_lib as H  # noqa: E402
import c81_lib as R  # noqa: E402
import c81_search as S81  # noqa: E402
import c82_lib as P  # noqa: E402
import c82_search as S82  # noqa: E402
import c83_lib as Q  # noqa: E402
import c85_lib as X  # noqa: E402
import c86_lib as W  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.6")
TMP = os.path.join(DATA, "tmp", "r8.6_checks")
T81 = os.path.join(DATA, "r8.1")
T83 = os.path.join(DATA, "r8.3")
BASE = os.path.join(DATA, "runs", "r8.5")
CONFIGS = ["q8", "wp", "fl"]
SPLITS = S81.SPLITS
VERSION = {"q8": X.Q8_VERSION, "wp": W.WP_VERSION, "fl": W.FL_VERSION}
pct = S82.pct


class Env:
    def __init__(self):
        t0 = time.time()
        items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.S = L.Combined("all", items=items)
        G.swap_to_3l(self.S)
        S = self.S
        t1 = time.time()
        S.V = X.QMat(S.V)
        self.quant_s = round(time.time() - t1, 1)
        self.h0_build_s = time.time() - t0
        I.prepare(S)
        t1 = time.time()
        self.router_shape = R.ShapeRouter(S)
        self.route_build_s = time.time() - t1
        self.extra_build_s = {}
        t2 = time.time()
        self.prior = P.PlatformPrior(S, H.Router())
        self.extra_build_s["prior"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.te = Q.TeIG(S)
        self.extra_build_s["te_ig"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.wp = W.WP(S)
        self.extra_build_s["wp"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.fl = W.FL(S)
        self.extra_build_s["fl"] = round(time.time() - t2, 1)
        self.refiner = W.Refiner86(S, F.te_meta_rows())
        self.build_s = time.time() - t0


def plan(q, parse, path):
    return R.plan_instant(q) if path == "instant" else F.plan_c0(q, parse)


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """Returns (order, info). With stop_before_refine, returns the pre-refine order and whether the gate fires."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = plan(q, parse, path)
    own, _ = F.own_lists(S, texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)  # B8.5 own-list fusion
    info["prior"] = pinfo
    group = env.te.group(texts, caps, bq, keep)
    if cfg == "fl":
        order, sc, finfo = env.fl.fuse(own[0], own[1], bq, keep, group)
        info["fl"] = finfo
    else:
        order, sc = F.fair_fuse(own, [group])
    info["te_used"] = True
    order, sc = env.prior.apply(order, sc, q_ig)
    if cfg == "wp":
        order, n20 = env.wp.apply(order)
        info["wp"] = {"boosted_in_top20_before": n20}
    order = order[:1000]
    gate = path == "rewrite" and q_ig < W.REFINE_Q_IG_MAX
    if stop_before_refine:
        return order, {"gate": gate}
    if gate:
        (order, rinfo), rr = env.refiner.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "cache": env.refiner.source.get(rr["key"])}
    return order, info


# ---------------- refine calls (cached; paid only where no earlier cache has the exact inputs) ----------------
def refine(cfgs, reps, workers):
    qs, _ = S81.queries()
    env = Env()
    rf = env.refiner
    orig = ai.openai_chat_json

    def tagged(*a, **k):  # this round's ledger purpose; prompt, model and schema are rf-v1's
        k["purpose"] = "c86_refine"
        return orig(*a, **k)
    ai.openai_chat_json = tagged
    jobs, src = [], collections.Counter()
    t0 = time.time()
    for cfg in cfgs:
        for rep in reps:
            Pqr = S81.rewrites("qr-v1", rep)
            for q in qs:
                if q["examples"]:
                    continue
                order, g = search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                key = P.cache_key(rep, q["id"], rf.split_top(order)[2])
                src[(cfg, rf.source.get(key, "new"))] += 1
                if key not in rf.cache:
                    jobs.append((rep, q, order))
    uniq = {}
    for rep, q, order in jobs:
        uniq.setdefault(P.cache_key(rep, q["id"], rf.split_top(order)[2]), (rep, q, order))
    print(f"refine: gated searches by (config, source) {dict(src)}; {len(uniq)} distinct new inputs "
          f"(pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
                          list(uniq.values())))
    wall = time.time() - t0
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c86_refine"]
    print(f"refine: {len(uniq)} calls in {wall:.1f} s ({len(uniq) / max(wall, 1e-9):.2f}/s), {len(new)} ledger rows, "
          f"${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, "
          f"failed {sum(not r['ok'] for r in res)}", flush=True)


# ---------------- runs ----------------
def run_config(env, cfg, reps, outdir):
    qs, split_of = S81.queries()
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    t_inst = json.load(open(os.path.join(T81, "embed_timing_inst.json")))
    te_inst = json.load(open(os.path.join(T83, "embed_timing_te_inst.json")))
    written = []
    for rep in reps:
        Pqr = S81.rewrites("qr-v1", rep)
        need = S81.strings(qs, Pqr, None)
        miss = [s for s in need if s not in S.QV.vec]
        assert not miss, f"{len(miss)} query strings not in the 3-large query store"
        t_h0 = json.load(open(os.path.join(T81, f"embed_timing_h0_r{rep}.json")))
        te_rw = json.load(open(os.path.join(T83, f"embed_timing_te_r{rep}.json")))
        typed = [x for x in qs if not x["examples"]]
        for q in typed[:5]:  # warm-up (not timed, not written)
            search_one(env, cfg, q, Pqr[q["id"]], rep)
        out, per = {}, {}
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        agg = collections.Counter()
        t_run = time.time()
        for q in qs:
            sp = split_of[q["id"]]
            parse = None if q["examples"] else Pqr[q["id"]]
            t = time.time()
            order, info = search_one(env, cfg, q, parse, rep)
            local = time.time() - t
            out[q["id"]] = order
            if q["examples"]:
                continue
            d = by[sp]
            path = info["route"]["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rf_s = rf_c = 0.0
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
            es = (te_inst if path == "instant" else te_rw)[q["id"]]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]  # parallel, every search
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refine_cost"].append(rf_c)
            tot = local + rw_s + e_s + rf_s
            d["local"].append(local)
            d["total"].append(tot)
            d["cost"].append(rw_c + e_c + rf_c)
            d[f"total_{path}_path"].append(tot)
            d[f"local_{path}_path"].append(local)
            d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
            agg[f"{sp}:{path}"] += 1
            if "wp" in info:
                d["wp_boosted_top20"].append(info["wp"]["boosted_in_top20_before"])
                d["wp_boosted_top10_final"].append(sum(c in env.wp.m for c in order[:10]))
                agg[f"{sp}:wp_any_boosted_top20"] += info["wp"]["boosted_in_top20_before"] > 0
            if "fl" in info:
                d["fl_title_len"].append(info["fl"]["title_len"])
                d["fl_channel_len"].append(info["fl"]["channel_len"])
                agg[f"{sp}:fl_channel_nonempty"] += info["fl"]["channel_len"] > 0
            if "refine" in info:
                ri = info["refine"]
                agg[f"{sp}:refine_ok"] += ri["ok"]
                agg[f"{sp}:refine_failed"] += not ri["ok"]
                agg[f"{sp}:refine_cache_{ri['cache']}"] += 1
                for k in ("n_sent", "n_friends_kept", "n_invalid", "n_dup", "n_missing", "moved"):
                    agg[f"{sp}:refine_{k}"] += ri[k]
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4), "latency_total_s": round(tot, 3)}
        wall = time.time() - t_run
        allv = collections.defaultdict(list)
        for sp in SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        splits = {}
        for sp, d in [(s, by[s]) for s in SPLITS] + [("all_typed", allv)]:
            n = len(d["local"])
            row = {"n_typed": n,
                   "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                   "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                   "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                   "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                   "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                   "yt_share_top10_mean": round(float(np.mean(d["yt_share_top10"])), 4) if n else None,
                   "refined": len(d["refine_s"]),
                   "refine_p50_s": pct(d["refine_s"], 50), "refine_p95_s": pct(d["refine_s"], 95)}
            for k in [k for k in d if k.startswith("wp_") or k.startswith("fl_")]:
                row[k] = {"mean": round(float(np.mean(d[k])), 3), "p50": pct(d[k], 50), "p95": pct(d[k], 95)}
            splits[sp] = row
        meta = {"config": cfg, "round": "8.6", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.5 = runs/r8.5/q8_r{k} (q8-v1: TFY with int8 item vectors)",
                "version": VERSION[cfg], "vector_mode": "int8",
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]},
                "wp": {"cap_places": W.WP_CAP, "w_rewatch": W.WP_W_REWATCH, "w_like": W.WP_W_LIKE,
                       "w_playlist": W.WP_W_PLAYLIST, "rewatch_sat": W.WP_REWATCH_SAT,
                       "youtube_items_boosted": len(env.wp.m)} if cfg == "wp" else None,
                "fl": {"w_title": W.FL_W_TITLE, "w_channel": W.FL_W_CHANNEL, "n_o": W.FL_N_O,
                       "title_docs": env.fl.n_title, "channel_docs": env.fl.n_chan} if cfg == "fl" else None,
                "refine_model": P.REFINE_MODEL, "refine_gate": f"rewrite-routed and q_ig < {W.REFINE_Q_IG_MAX}",
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "quantise_s": env.quant_s, "route_index_build_s": round(env.route_build_s, 1),
                "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used + max(round "
                                 "8.1's live 3-large call, round 8.3's live 3-small te call) + refine call",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"q8_r{rep}.json")))
        meta["diagnostics_vs_b85"] = S82.top10_diag(out, ref, plat, split_of)
        mlt = [k for k in out if not per.get(k)]
        meta["mlt_identical_to_b85"] = sum(out[k] == ref["queries"][k] for k in mlt)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c86:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"total p50 {sa['total_p50_s']} / p95 {sa['total_p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}",
              flush=True)
        same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
        print(f"{cfg} r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.5/q8 (1,000 deep); "
              f"more-like-this identical {meta['mlt_identical_to_b85']} / {len(mlt)}", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["refine", "run", "compare"])
    ap.add_argument("--configs", default="wp,fl")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    for cfg in cfgs:
        assert cfg in CONFIGS, cfg
    if a.cmd == "refine":
        return refine(cfgs, reps, a.workers)
    if a.cmd == "compare":
        return S82.compare(a.a, a.b, cfgs, reps)
    t0 = time.time()
    env = Env()
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; route {env.route_build_s:.1f} s; "
          f"extra {json.dumps(env.extra_build_s)}; quantise {env.quant_s} s)", flush=True)
    for cfg in cfgs:
        run_config(env, cfg, reps, TMP if cfg == "q8" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
