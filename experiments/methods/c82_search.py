"""PROTOTYPE ONLY - round 8.2 run files (LOG.md "Round 8.2 fixed parameters", rows Y8.2-P, Y8.2-L, Y8.2-F).

Configs (one variable each vs B8.1 = R, route-r1 = runs/r8.1/route_r{k}):
  route   B8.1 from this runner: must equal runs/r8.1/route_r{k} exactly (reproduction gate; written to tmp/ only).
  prior   Y8.2-P: B8.1 + prior-p1 soft per-platform weight on every typed search (both paths).
  lean    Y8.2-L: B8.1 with lean-l1 (H4 creator search + H1 guarded filters) on rewrite-routed searches.
  refine  Y8.2-F: B8.1 + rf-v1 gpt-5-nano listwise refine of the top 20 on rewrite-routed searches (from the cache
          filled by the `refine` command).
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat covering all four splits).
More-like-this searches = H0 in every config.

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
(lean: max(qr-v1, qs-v1), parallel) + round 8.1's measured live 3-large query-embedding call (rewrite path: query +
phrases + HyDE captions; instant path: raw query) + (refine) the refine call's seconds, sequential. Aggregates only.

usage: python experiments/methods/c82_search.py refine [--reps 1,2,3] [--workers 4]   # paid gpt-5-nano calls, cached
       python experiments/methods/c82_search.py run --configs route,prior,lean,refine [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c82_search.py compare --a DIR --b DIR --configs ...
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
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.2")
TMP = os.path.join(DATA, "tmp", "r8.2_checks")
T81 = os.path.join(DATA, "r8.1")
BASE = os.path.join(DATA, "runs", "r8.1")
CONFIGS = ["route", "prior", "lean", "refine"]
SPLITS = S81.SPLITS


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 3) if xs else None


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
        if "prior" in cfgs:
            t2 = time.time()
            self.prior = P.PlatformPrior(S, H.Router())
            self.extra_build_s["prior"] = round(time.time() - t2, 1)
        if "lean" in cfgs:
            t2 = time.time()
            self.CR4d = R.Creators7d(S, F.te_meta_rows(), H.Facets7(), enriched=True)
            self.CR_elig = set(self.CR4d.of)
            self.extra_build_s["lean_creators"] = round(time.time() - t2, 1)
        if "refine" in cfgs:
            self.refiner = P.Refiner(S, F.te_meta_rows())
        self.build_s = time.time() - t0


def fused(env, q, parse, path):
    """B8.1's fused list for one typed search (before truncation): (order, scores)."""
    S = env.S
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = R.plan_instant(q) if path == "instant" else F.plan_c0(q, parse)
    own, _ = F.own_lists(S, texts, caps, bq, keep)
    return F.fair_fuse(own, [])


def search_one(env, cfg, q, parse, slots, rep):
    if q["examples"]:
        return env.S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r}
    if cfg == "lean" and path == "rewrite":
        order, li = P.lean_rewrite(env, q, parse, slots)
        return order, {**info, "lean": li}
    order, sc = fused(env, q, parse, path)
    if cfg == "prior":
        q_ig, pinfo = env.prior.read(q["query"], env.S.QV.get([q["query"]])[0], order)
        order, sc = env.prior.apply(order, sc, q_ig)
        info["prior"] = pinfo
    order = order[:1000]
    if cfg == "refine" and path == "rewrite":
        (order, rinfo), rr = env.refiner.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"]}
    return order, info


# ---------------- paid refine calls (cached) ----------------
def refine(reps, workers):
    qs, _ = S81.queries()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    rf = P.Refiner(S, F.te_meta_rows())
    jobs = []
    for rep in reps:
        base = json.load(open(os.path.join(BASE, f"route_r{rep}.json")))
        per = base["meta"]["per_search"]
        for q in qs:
            if q["examples"] or per[q["id"]]["path"] != "rewrite":
                continue
            jobs.append((rep, q, base["queries"][q["id"]]))
    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1], jobs))
    wall = time.time() - t0
    cost = sum(r["cost_usd"] for r in L.ledger()[n0:])
    print(f"refine: {len(jobs)} searches in {wall:.1f} s ({len(jobs) / max(wall, 1e-9):.2f} searches/s), "
          f"{len(L.ledger()) - n0} new calls, ${cost:.4f}; ok {sum(r['ok'] for r in res)}, "
          f"failed {sum(not r['ok'] for r in res)}", flush=True)


# ---------------- runs ----------------
def run_config(env, cfg, reps, outdir):
    qs, split_of = S81.queries()
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    t_inst = json.load(open(os.path.join(T81, "embed_timing_inst.json")))
    written = []
    for rep in reps:
        Pqr = S81.rewrites("qr-v1", rep)
        Pqs = S81.rewrites("qs-v1", rep)
        need = S81.strings(qs, Pqr, Pqs if cfg == "lean" else None)
        miss = [s for s in need if s not in S.QV.vec]
        assert not miss, f"{len(miss)} query strings not in the 3-large query store"
        t_h0 = json.load(open(os.path.join(T81, f"embed_timing_h0_r{rep}.json")))
        typed = [x for x in qs if not x["examples"]]
        for q in typed[:5]:  # warm-up (not timed, not written)
            search_one(env, cfg, q, Pqr[q["id"]], Pqs[q["id"]], rep)
        out, per = {}, {}
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        agg = collections.Counter()
        t_run = time.time()
        for q in qs:
            sp = split_of[q["id"]]
            parse = None if q["examples"] else Pqr[q["id"]]
            slots = None if q["examples"] else Pqs[q["id"]]
            t = time.time()
            order, info = search_one(env, cfg, q, parse, slots, rep)
            local = time.time() - t
            out[q["id"]] = order
            if q["examples"]:
                by[sp]["local_mlt"].append(local)
                continue
            path = info["route"]["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rs = Pqs["_meta"]["per_query"][q["id"]]
            rf_s = rf_c = 0.0
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e = t_h0[q["id"]]
                uses_qs = cfg == "lean"
                rw_s = max(rq["seconds"], rs["seconds"] if uses_qs else 0.0)
                rw_c = rq["cost_usd"] + (rs["cost_usd"] if uses_qs else 0.0)
                if uses_qs:
                    by[sp]["cost_qs"].append(rs["cost_usd"])
                if cfg == "refine":
                    rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                    by[sp]["refine_s"].append(rf_s)
                    by[sp]["refine_cost"].append(rf_c)
            d = by[sp]
            tot = local + rw_s + e["seconds"] + rf_s
            d["local"].append(local)
            d["total"].append(tot)
            d["cost"].append(rw_c + e["cost_usd"] + rf_c)
            d["cost_merged"].append(rq["cost_usd"] * (path == "rewrite") + e["cost_usd"] + rf_c)
            d["routed"].append(path == "instant")
            d[f"total_{path}_path"].append(tot)
            d[f"local_{path}_path"].append(local)
            agg[f"{sp}:{path}"] += 1
            if "prior" in info:
                pi = info["prior"]
                for k in ("q_ig", "e_t", "e_k", "e_c", "mult_ig", "mult_yt"):
                    d["prior_" + k].append(pi[k])
                agg[f"{sp}:prior_creator_fired"] += pi["n_creators"] > 0
            if "lean" in info:
                li = info["lean"]
                agg[f"{sp}:lean_creator_fired"] += "creator" in li
                agg[f"{sp}:lean_filter_active"] += li["intent"]["mode"] != "unchanged"
            if "refine" in info:
                ri = info["refine"]
                agg[f"{sp}:refine_ok"] += ri["ok"]
                agg[f"{sp}:refine_failed"] += not ri["ok"]
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
            row = {"n_typed": n, "routed_instant": int(sum(d["routed"])),
                   "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                   "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                   "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                   "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                   "local_rewrite_path_p50_s": pct(d["local_rewrite_path"], 50),
                   "local_rewrite_path_p95_s": pct(d["local_rewrite_path"], 95),
                   "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None}
            if cfg == "lean":
                row["cost_per_1k_if_qs_merged_usd"] = round(1000 * float(np.mean(d["cost_merged"])), 4)
            if cfg == "refine":
                row["refine_p50_s"], row["refine_p95_s"] = pct(d["refine_s"], 50), pct(d["refine_s"], 95)
                row["refine_cost_per_1k_refined_usd"] = round(1000 * float(np.mean(d["refine_cost"])), 4) \
                    if d["refine_cost"] else None
            if cfg == "prior":
                row["prior"] = {k[6:]: {f"p{p}": pct(v, p) for p in (5, 25, 50, 75, 95)}
                                for k, v in d.items() if k.startswith("prior_")}
            splits[sp] = row
        meta = {"config": cfg, "round": "8.2", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.1 = runs/r8.1/route_r{k} (route-r1)",
                "version": {"prior": P.PRIOR_VERSION, "lean": P.LEAN_VERSION, "refine": P.REFINE_VERSION}.get(cfg),
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"], "qs-v1": Pqs["_meta"]["sources"] if cfg == "lean"
                             else None},
                "refine_model": P.REFINE_MODEL if cfg == "refine" else None,
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "route_index_build_s": round(env.route_build_s, 1), "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used (lean: "
                                 "max(qr-v1, qs-v1)) + round 8.1's live 3-large embed call + refine call (refine)",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"route_r{rep}.json")))
        meta["diagnostics_vs_b81"] = top10_diag(out, ref, plat, split_of)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c82:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"total p50 {sa['total_p50_s']} / p95 {sa['total_p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}; "
              f"{json.dumps(meta['diagnostics_vs_b81'])}", flush=True)
        if cfg == "route":
            same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
            print(f"route r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.1/route (1,000 deep)",
                  flush=True)
    return written


def top10_diag(out, ref, plat, split_of):
    res = {}
    for sp in SPLITS:
        ks = [k for k in out if split_of[k] == sp]
        ovl = [len(set(out[k][:10]) & set(ref["queries"][k][:10])) / 10 for k in ks]
        diff = sum(out[k][:10] != ref["queries"][k][:10] for k in ks)
        own = {"known_dev": "youtube", "ig_known_dev": "instagram"}.get(sp)
        row = {"top10_differs": diff, "mean_top10_overlap": round(float(np.mean(ovl)), 3)}
        if own:
            row["other_platform_share_top10"] = round(float(np.mean(
                [sum(plat.get(c) != own for c in out[k][:10]) / max(len(out[k][:10]), 1) for k in ks])), 3)
        res[sp] = row
    return res


def compare(a, b, cfgs, reps):
    for cfg in cfgs:
        for rep in reps:
            pa, pb = os.path.join(a, f"{cfg}_r{rep}.json"), os.path.join(b, f"{cfg}_r{rep}.json")
            if not (os.path.exists(pa) and os.path.exists(pb)):
                print(f"{cfg} r{rep}: missing", flush=True)
                continue
            x, y = json.load(open(pa))["queries"], json.load(open(pb))["queries"]
            same = sum(x[k] == y.get(k) for k in x)
            print(f"{cfg} r{rep}: {same} of {len(x)} rankings identical (1,000 deep)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["refine", "run", "compare"])
    ap.add_argument("--configs", default="prior,lean,refine")
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
        return compare(a.a, a.b, cfgs, reps)
    t0 = time.time()
    env = Env(cfgs)
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; route {env.route_build_s:.1f} s; "
          f"extra {json.dumps(env.extra_build_s)})", flush=True)
    for cfg in cfgs:
        assert cfg in CONFIGS, cfg
        run_config(env, cfg, reps, TMP if cfg == "route" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
