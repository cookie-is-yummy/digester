"""PROTOTYPE ONLY - round 8.8 run files (LOG.md "Round 8.8 fixed parameters", rows Y8.8-FK, Y8.8-FM).

Configs (one variable each vs B8.5 = Q8, q8-v1 = runs/r8.5/q8_r{k}); every config runs on the int8 item store:
  q8   B8.5 from this runner: must equal runs/r8.5/q8_r{k} exactly (reproduction gate; written to tmp/ only).
  fk   Y8.8-FK: rf-v1 (gpt-5-nano) also on instant-routed typed searches with q_ig < 0.5.
  fm   Y8.8-FM: gpt-5-mini (minimal reasoning) instead of gpt-5-nano in the refine, B8.5's gate.
Pre-refine orders equal B8.5's in every config (the first screen of the two-stage flow is unchanged).
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat).

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
+ max(round 8.1's live 3-large call, round 8.3's live 3-small te call) (parallel) + the refine call's live seconds.
First screen = all but the refine; refined screen = first screen + refine seconds (refined searches only).

usage: python experiments/methods/c88_search.py refine --configs fk,fm [--reps 1,2,3] [--workers 4]  # paid if new
       python experiments/methods/c88_search.py run --configs q8,fk,fm [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c88_search.py compare --a DIR --b DIR --configs ...
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
import c87_lib as C  # noqa: E402
import c88_lib as K  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.8")
TMP = os.path.join(DATA, "tmp", "r8.8_checks")
T81 = os.path.join(DATA, "r8.1")
T83 = os.path.join(DATA, "r8.3")
BASE = os.path.join(DATA, "runs", "r8.5")
CONFIGS = ["q8", "fk", "fm"]
SPLITS = S81.SPLITS
VERSION = {"q8": X.Q8_VERSION, "fk": K.FK_VERSION, "fm": K.FM_VERSION}
MODEL = {"q8": K.NANO, "fk": K.NANO, "fm": K.MINI}
PURPOSE = {"q8": "c88_refine", "fk": "c88_refine", "fm": "c88_refine_mini"}
pct = S82.pct


class Env:
    def __init__(self, S=None):
        """S: optional prebuilt index whose S.V is already the int8 store (the demo app loads a stored int8 matrix);
        None = the original build (float 3-large store quantised here)."""
        t0 = time.time()
        if S is None:
            items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
            self.S = L.Combined("all", items=items)
            G.swap_to_3l(self.S)
            S = self.S
            t1 = time.time()
            S.V = X.QMat(S.V)
            self.quant_s = round(time.time() - t1, 1)
        else:
            self.S = S
            self.quant_s = 0.0
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
        te_rows = F.te_meta_rows()
        self.refiners = {m: K.Refiner88(S, te_rows, model=m, purpose=p)
                         for m, p in ((K.NANO, "c88_refine"), (K.MINI, "c88_refine_mini"))}
        self.build_s = time.time() - t0


def plan(q, parse, path):
    return R.plan_instant(q) if path == "instant" else F.plan_c0(q, parse)


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """Returns (order, info). With stop_before_refine, returns the pre-refine order and the gate."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = plan(q, parse, path)
    own, _, _ = C.own_lists_s(S, texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)  # B8.5 own-list fusion
    info["prior"] = pinfo
    group = env.te.group(texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [group])
    info["te_used"] = True
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    g = K.gate(cfg, path, q_ig)
    if stop_before_refine:
        return order, {"gate": g, "path": path}
    if g:
        rf = env.refiners[MODEL[cfg]]
        (order, rinfo), rr = rf.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "in_tokens": rr.get("in_tokens", 0), "out_tokens": rr.get("out_tokens", 0),
                          "cache": rf.source.get(rr["key"]), "model": MODEL[cfg]}
    return order, info


# ---------------- refine calls (cached; paid only where no earlier cache has the exact inputs) ----------------
def refine(cfgs, reps, workers):
    qs, _ = S81.queries()
    env = Env()
    jobs, src = collections.defaultdict(dict), collections.Counter()
    t0 = time.time()
    for cfg in cfgs:
        rf = env.refiners[MODEL[cfg]]
        for rep in reps:
            Pqr = S81.rewrites("qr-v1", rep)
            for q in qs:
                if q["examples"]:
                    continue
                order, g = search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                key = rf.key(rep, q["id"], order)
                src[(cfg, g["path"], rf.source.get(key, "new"))] += 1
                if key not in rf.cache:
                    jobs[MODEL[cfg]].setdefault(key, (rep, q, order))
    print(f"refine: gated searches by (config, path, source) {dict(src)}; distinct new inputs "
          f"{ {m: len(v) for m, v in jobs.items()} } (pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    for model, uniq in jobs.items():
        rf = env.refiners[model]
        n0 = len(L.ledger())
        t0 = time.time()
        with cf.ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
                              list(uniq.values())))
        wall = time.time() - t0
        new = [r for r in L.ledger()[n0:] if r.get("purpose") == rf.purpose]
        print(f"refine {model}: {len(uniq)} calls in {wall:.1f} s ({len(uniq) / max(wall, 1e-9):.2f} items/s), "
              f"{len(new)} ledger rows, ${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, "
              f"failed {sum(not r['ok'] for r in res)}; call seconds p50 {pct([r['seconds'] for r in res], 50)} "
              f"p95 {pct([r['seconds'] for r in res], 95)}", flush=True)


# ---------------- runs ----------------
def _lat(d, k):
    return {"p50_s": pct(d[k], 50), "p95_s": pct(d[k], 95), "n": len(d[k])}


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
            first = local + rw_s + e_s
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refine_cost"].append(rf_c)
                d[f"refine_s_{path}"].append(rf_s)
                d["refined_screen"].append(first + rf_s)
                d[f"refined_screen_{path}"].append(first + rf_s)
            tot = first + rf_s
            d["local"].append(local)
            d["first_screen"].append(first)
            d[f"first_screen_{path}"].append(first)
            d["total"].append(tot)
            d["cost"].append(rw_c + e_c + rf_c)
            d[f"total_{path}_path"].append(tot)
            d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
            agg[f"{sp}:{path}"] += 1
            if "refine" in info:
                ri = info["refine"]
                agg[f"{sp}:refined_{path}"] += 1
                agg[f"{sp}:refine_ok"] += ri["ok"]
                agg[f"{sp}:refine_failed"] += not ri["ok"]
                agg[f"{sp}:refine_cache_{ri['cache']}"] += 1
                for k in ("n_sent", "n_friends_kept", "n_invalid", "n_dup", "n_missing", "moved"):
                    agg[f"{sp}:refine_{k}"] += ri[k]
                agg[f"{sp}:refine_moved_any"] += ri["moved"] > 0
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4),
                            "latency_first_screen_s": round(first, 3), "latency_total_s": round(tot, 3)}
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
                   "total_instant_path_p95_s": pct(d["total_instant_path"], 95),
                   "first_screen": _lat(d, "first_screen"),
                   "first_screen_instant": _lat(d, "first_screen_instant"),
                   "first_screen_rewrite": _lat(d, "first_screen_rewrite"),
                   "refined_screen": _lat(d, "refined_screen"),
                   "refined_screen_instant": _lat(d, "refined_screen_instant"),
                   "refined_screen_rewrite": _lat(d, "refined_screen_rewrite"),
                   "instant_share": round(len(d["total_instant_path"]) / n, 4) if n else None,
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                   "refine_cost_per_1k_refined_usd": round(1000 * float(np.mean(d["refine_cost"])), 4)
                   if d["refine_cost"] else None,
                   "yt_share_top10_mean": round(float(np.mean(d["yt_share_top10"])), 4) if n else None,
                   "refined": len(d["refine_s"]), "refined_share": round(len(d["refine_s"]) / n, 4) if n else None,
                   "refine_p50_s": pct(d["refine_s"], 50), "refine_p95_s": pct(d["refine_s"], 95),
                   "refine_instant": _lat(d, "refine_s_instant"), "refine_rewrite": _lat(d, "refine_s_rewrite")}
            splits[sp] = row
        meta = {"config": cfg, "round": "8.8", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.5 = runs/r8.5/q8_r{k} (q8-v1: TFY with int8 item vectors)",
                "version": VERSION[cfg], "vector_mode": "int8",
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]},
                "refine_model": MODEL[cfg], "refine_prompt": P.REFINE_VERSION, "refine_reasoning_effort": "minimal",
                "refine_gate": (f"q_ig < {K.REFINE_Q_IG_MAX} (rewrite- or instant-routed)" if cfg == "fk"
                                else f"rewrite-routed and q_ig < {K.REFINE_Q_IG_MAX}"),
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "quantise_s": env.quant_s, "route_index_build_s": round(env.route_build_s, 1),
                "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used + max(round "
                                 "8.1's live 3-large call, the live 3-small te call) + refine call; first screen = "
                                 "all but the refine, refined screen = first screen + refine (refined searches)",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"q8_r{rep}.json")))
        meta["diagnostics_vs_b85"] = S82.top10_diag(out, ref, plat, split_of)
        mlt = [k for k in out if not per.get(k)]
        meta["mlt_identical_to_b85"] = sum(out[k] == ref["queries"][k] for k in mlt)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c88:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f} items/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"first p50 {sa['first_screen']['p50_s']} / p95 {sa['first_screen']['p95_s']}; refined screen p50 "
              f"{sa['refined_screen']['p50_s']} / p95 {sa['refined_screen']['p95_s']} (n {sa['refined']}); "
              f"$/1k {sa['cost_per_1k_searches_usd']}", flush=True)
        same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
        print(f"{cfg} r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.5/q8 (1,000 deep); "
              f"more-like-this identical {meta['mlt_identical_to_b85']} / {len(mlt)}", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["refine", "run", "compare"])
    ap.add_argument("--configs", default="fk,fm")
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
