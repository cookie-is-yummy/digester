"""PROTOTYPE ONLY - round 8.4 run files (LOG.md "Round 8.4 fixed parameters", rows Y8.4-TG, Y8.4-TFY).

Configs (one variable each vs B8.3 = TI, ti-v1 = runs/r8.3/ti_r{k}):
  ti   B8.3 from this runner: must equal runs/r8.3/ti_r{k} exactly (reproduction gate; written to tmp/ only).
  tg   Y8.4-TG: TI's te lists only when P's q_ig >= 0.5 (unrounded); otherwise exactly P (no te lists).
  tfy  Y8.4-TFY: TI + rf-v1 refine of TI's top 20 on rewrite-routed typed searches with q_ig < 0.5.
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat). More-like-this = H0 everywhere.

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
+ max(round 8.1's live 3-large call, round 8.3's live 3-small te call) (parallel) + (tfy) the refine call's seconds,
sequential. tg also reports a secondary model: the 3-small call only after a q_ig >= 0.5 read, sequential.
No new embedding or timing calls: the te query vectors (c4_queries) and the 3-small timings exist from round 8.3.

usage: python experiments/methods/c84_search.py refine [--reps 1,2,3] [--workers 4]   # tfy; paid only if uncached
       python experiments/methods/c84_search.py run --configs ti,tg,tfy [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c84_search.py compare --a DIR --b DIR --configs ...
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
import c84_lib as Z  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.4")
TMP = os.path.join(DATA, "tmp", "r8.4_checks")
T81 = os.path.join(DATA, "r8.1")
T83 = os.path.join(DATA, "r8.3")
BASE = os.path.join(DATA, "runs", "r8.3")
BASE_P = os.path.join(DATA, "runs", "r8.2")
CONFIGS = ["ti", "tg", "tfy"]
SPLITS = S81.SPLITS
VERSION = {"ti": Q.TI_VERSION, "tg": Z.TG_VERSION, "tfy": Z.TFY_VERSION}
pct = S82.pct


class Env:
    def __init__(self, cfgs):
        t0 = time.time()
        items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.S = L.Combined("all", items=items)
        G.swap_to_3l(self.S)
        self.h0_build_s = time.time() - t0
        S = self.S
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
        if "tfy" in cfgs:
            self.refiner = Z.Refiner84(S, F.te_meta_rows())
        self.build_s = time.time() - t0


def plan(q, parse, path):
    return R.plan_instant(q) if path == "instant" else F.plan_c0(q, parse)


def search_one(env, cfg, q, parse, rep):
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
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)  # read from the own-list fusion
    info["prior"] = pinfo
    use_te = cfg in ("ti", "tfy") or (cfg == "tg" and q_ig >= Z.TG_Q_IG_MIN)
    info["te_used"] = use_te
    if use_te:
        order, sc = F.fair_fuse(own, [env.te.group(texts, caps, bq, keep)])
        info["ti"] = {"te_in_top10": sum(c in env.te.E.codeset for c in order[:10])}
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    if cfg == "tfy" and path == "rewrite" and q_ig < Z.TFY_Q_IG_MAX:
        (order, rinfo), rr = env.refiner.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "cache": env.refiner.source.get(rr["key"])}
    return order, info


# ---------------- tfy: refine calls (cached; paid only where no earlier cache has the exact inputs) -------------
def refine(reps, workers):
    qs, _ = S81.queries()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    rf = Z.Refiner84(S, F.te_meta_rows())
    orig = ai.openai_chat_json

    def tagged(*a, **k):  # this round's ledger purpose; prompt, model and schema are rf-v1's
        k["purpose"] = "c84_refine"
        return orig(*a, **k)
    ai.openai_chat_json = tagged
    jobs = []
    for rep in reps:
        base = json.load(open(os.path.join(BASE, f"ti_r{rep}.json")))  # TI's top 20 = the refine's input
        per = base["meta"]["per_search"]
        for q in qs:
            if q["examples"] or per[q["id"]]["path"] != "rewrite":
                continue
            if per[q["id"]]["prior"]["q_ig"] >= Z.TFY_Q_IG_MAX + 1e-4:  # rounded in the file; superset of the gate
                continue
            jobs.append((rep, q, base["queries"][q["id"]]))
    hits = collections.Counter(rf.source.get(P.cache_key(r, q["id"], rf.split_top(o)[2])) for r, q, o in jobs)
    print(f"refine: {len(jobs)} gated searches over {len(reps)} repeats; cached by source {dict(hits)}", flush=True)
    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1], jobs))
    wall = time.time() - t0
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c84_refine"]
    print(f"refine: {len(jobs)} searches in {wall:.1f} s ({len(jobs) / max(wall, 1e-9):.2f} searches/s), "
          f"{len(new)} new calls, ${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, "
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
            path = info["route"]["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rf_s = rf_c = 0.0
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
            es = (te_inst if path == "instant" else te_rw)[q["id"]]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]  # parallel, every search
            seq_s = e["seconds"] + (es["seconds"] if info["te_used"] else 0.0)  # secondary (tg): call after read
            seq_c = e["cost_usd"] + (es["cost_usd"] if info["te_used"] else 0.0)
            d = by[sp]
            d["te_embed_s"].append(es["seconds"])
            d["te_used"].append(info["te_used"])
            if info["te_used"]:
                d["te_in_top10"].append(info["ti"]["te_in_top10"])
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refine_cost"].append(rf_c)
            tot = local + rw_s + e_s + rf_s
            d["local"].append(local)
            d["total"].append(tot)
            d["cost"].append(rw_c + e_c + rf_c)
            d["total_seq"].append(local + rw_s + seq_s + rf_s)
            d["cost_seq"].append(rw_c + seq_c + rf_c)
            d["routed"].append(path == "instant")
            d[f"total_{path}_path"].append(tot)
            d[f"local_{path}_path"].append(local)
            agg[f"{sp}:{path}"] += 1
            agg[f"{sp}:te_used"] += info["te_used"]
            agg[f"{sp}:{path}:te_used"] += info["te_used"]
            pi = info["prior"]
            for k in ("q_ig", "e_t", "e_k", "e_c", "mult_ig", "mult_yt"):
                d["prior_" + k].append(pi[k])
            agg[f"{sp}:prior_creator_fired"] += pi["n_creators"] > 0
            if path == "rewrite":
                agg[f"{sp}:rewrite_read_yt"] += pi["q_ig"] < Z.TFY_Q_IG_MAX
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
            row = {"n_typed": n, "routed_instant": int(sum(d["routed"])), "te_used": int(sum(d["te_used"])),
                   "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                   "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                   "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                   "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                   "local_rewrite_path_p50_s": pct(d["local_rewrite_path"], 50),
                   "local_rewrite_path_p95_s": pct(d["local_rewrite_path"], 95),
                   "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                   "te_embed_p50_s": pct(d["te_embed_s"], 50), "te_embed_p95_s": pct(d["te_embed_s"], 95),
                   "te_items_in_top10_mean_when_used": round(float(np.mean(d["te_in_top10"])), 3)
                   if d["te_in_top10"] else None,
                   "prior": {k[6:]: {f"p{p}": pct(v, p) for p in (5, 25, 50, 75, 95)}
                             for k, v in d.items() if k.startswith("prior_")}}
            if cfg == "tg":
                row["secondary_sequential"] = {
                    "total_p50_s": pct(d["total_seq"], 50), "total_p95_s": pct(d["total_seq"], 95),
                    "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost_seq"])), 4) if n else None}
            if cfg == "tfy":
                row["refined"] = len(d["refine_s"])
                row["refine_p50_s"], row["refine_p95_s"] = pct(d["refine_s"], 50), pct(d["refine_s"], 95)
                row["refine_cost_per_1k_refined_usd"] = round(1000 * float(np.mean(d["refine_cost"])), 4) \
                    if d["refine_cost"] else None
            splits[sp] = row
        meta = {"config": cfg, "round": "8.4", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.3 = runs/r8.3/ti_r{k} (ti-v1 on prior-p1, route-r1)", "version": VERSION[cfg],
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]},
                "te_gate": f"te lists iff q_ig >= {Z.TG_Q_IG_MIN}, else P" if cfg == "tg" else
                ("te lists on every typed search (TI)"),
                "refine_model": P.REFINE_MODEL if cfg == "tfy" else None,
                "refine_gate": f"rewrite-routed and q_ig < {Z.TFY_Q_IG_MAX}" if cfg == "tfy" else None,
                "te": {"rows": "te-v1c Instagram rows only", "rankable": env.te.n_rankable,
                       "equals_f0_rankable_set": env.te.same_as_f0, "f0_rankable": env.te.n_f0,
                       "dense_query_vectors": f"{Y.EMB_MODEL}@{Y.EMB_DIM}",
                       "fusion": "coverage-fair (c5_lib.fair_fuse)"},
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "route_index_build_s": round(env.route_build_s, 1), "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used + max(round "
                                 "8.1's live 3-large call, round 8.3's live 3-small te call) + refine call (tfy)",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"ti_r{rep}.json")))
        refp = json.load(open(os.path.join(BASE_P, f"prior_r{rep}.json")))
        meta["diagnostics_vs_b83"] = S82.top10_diag(out, ref, plat, split_of)
        meta["diagnostics_vs_b82"] = S82.top10_diag(out, refp, plat, split_of)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c84:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"total p50 {sa['total_p50_s']} / p95 {sa['total_p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}",
              flush=True)
        same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
        same_p = sum(out[k] == refp["queries"][k] for k in refp["queries"])
        print(f"{cfg} r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.3/ti, {same_p} to r8.2/prior "
              f"(1,000 deep)", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["refine", "run", "compare"])
    ap.add_argument("--configs", default="tg,tfy")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    if a.cmd == "refine":
        return refine(reps, a.workers)
    if a.cmd == "compare":
        return S82.compare(a.a, a.b, cfgs, reps)
    t0 = time.time()
    env = Env(cfgs)
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; route {env.route_build_s:.1f} s; "
          f"extra {json.dumps(env.extra_build_s)})", flush=True)
    for cfg in cfgs:
        assert cfg in CONFIGS, cfg
        run_config(env, cfg, reps, TMP if cfg == "ti" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
