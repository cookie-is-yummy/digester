"""PROTOTYPE ONLY - round 8.3 run files (LOG.md "Round 8.3 fixed parameters", rows Y8.3-FY, Y8.3-PC, Y8.3-TI).

Configs (one variable each vs B8.2 = P, prior-p1 = runs/r8.2/prior_r{k}):
  prior  B8.2 from this runner: must equal runs/r8.2/prior_r{k} exactly (reproduction gate; written to tmp/ only).
  fy     Y8.3-FY: P + rf-v1 refine of P's top 20 on rewrite-routed typed searches with P's q_ig < 0.5.
  pc     Y8.3-PC: P with pc-v1's strict creator-name match in the prior's creator term.
  ti     Y8.3-TI: P + te-v1c lists (te BM25 + te dense, 3-small) with only Instagram items rankable, coverage-fair
         fusion, every typed search; P's platform read taken from the own-list fusion as in P.
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat). More-like-this = H0 everywhere.

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
+ the live query-embedding call(s): round 8.1's measured 3-large call; for ti max(3-large, 3-small) (parallel calls,
3-small measured live by `timing`) + (fy) the refine call's seconds, sequential. Aggregates only.

usage: python experiments/methods/c83_search.py prefetch            # 3-small vectors of te query strings (ti)
       python experiments/methods/c83_search.py timing [--reps 1,2,3]  # live 3-small call per typed search (ti)
       python experiments/methods/c83_search.py refine [--reps 1,2,3] [--workers 4]   # fy; paid only if uncached
       python experiments/methods/c83_search.py run --configs prior,fy,pc,ti [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c83_search.py compare --a DIR --b DIR --configs ...
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
import yt_lib as Y  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.3")
TMP = os.path.join(DATA, "tmp", "r8.3_checks")
WORK = os.path.join(DATA, "r8.3")
T81 = os.path.join(DATA, "r8.1")
BASE = os.path.join(DATA, "runs", "r8.2")
CONFIGS = ["prior", "fy", "pc", "ti"]
SPLITS = S81.SPLITS
VERSION = {"prior": P.PRIOR_VERSION, "fy": Q.FY_VERSION, "pc": Q.PC_VERSION, "ti": Q.TI_VERSION}
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
        router = H.Router()
        self.prior = P.PlatformPrior(S, router)
        self.extra_build_s["prior"] = round(time.time() - t2, 1)
        if "pc" in cfgs:
            t2 = time.time()
            self.prior_pc = Q.StrictPrior(S, router)
            self.extra_build_s["prior_pc"] = round(time.time() - t2, 1)
        if "fy" in cfgs:
            self.refiner = Q.Refiner83(S, F.te_meta_rows())
        if "ti" in cfgs:
            t2 = time.time()
            self.te = Q.TeIG(S)
            self.extra_build_s["te_ig"] = round(time.time() - t2, 1)
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
    prior = env.prior_pc if cfg == "pc" else env.prior
    q_ig, pinfo = prior.read(q["query"], S.QV.get([q["query"]])[0], order)  # read from the own-list fusion
    info["prior"] = pinfo
    if cfg == "ti":
        order, sc = F.fair_fuse(own, [env.te.group(texts, caps, bq, keep)])
        info["ti"] = {"te_in_top10": sum(c in env.te.E.codeset for c in order[:10])}
    order, sc = prior.apply(order, sc, q_ig)
    order = order[:1000]
    if cfg == "fy" and path == "rewrite" and q_ig < Q.FY_Q_IG_MAX:
        (order, rinfo), rr = env.refiner.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "cache": env.refiner.source.get(rr["key"])}
    return order, info


# ---------------- ti: 3-small te query vectors and live timing ----------------
def te_strings(q, parse, path):
    texts, caps, _ = plan(q, parse, path)
    return texts + caps


def te_jobs(reps):
    """[(rep or 0 for the instant path, search, strings)]: one 3-small call per instant search, one per rewrite
    search and repeat (the same strings as the 3-large call)."""
    qs, _ = S81.queries()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    router = R.ShapeRouter(S)
    jobs = []
    typed = [q for q in qs if not q["examples"]]
    paths = {q["id"]: router.route(q["query"])["path"] for q in typed}
    for q in typed:
        if paths[q["id"]] == "instant":
            jobs.append((0, q, te_strings(q, None, "instant")))
    for rep in reps:
        Pqr = S81.rewrites("qr-v1", rep)
        for q in typed:
            if paths[q["id"]] == "rewrite":
                jobs.append((rep, q, te_strings(q, Pqr[q["id"]], "rewrite")))
    return jobs


def prefetch(reps):
    jobs = te_jobs(reps)
    qv = L.QueryVecs(Q.TE_QV_STORE)
    need = sorted({s for _, _, ss in jobs for s in ss})
    miss = [s for s in need if s not in qv.vec]
    print(f"te query strings: {len(need)} needed, {len(miss)} missing from {Q.TE_QV_STORE}", flush=True)
    if miss:
        n0 = len(L.ledger())
        t0 = time.time()
        from sklearn.preprocessing import normalize
        V = normalize(Y.embed_texts(miss, "c83_te_query_vectors", batch=500, workers=1))
        qv.vec.update(zip(miss, V))
        ids = list(qv.vec)
        L.save_store(qv.path, ids, np.array([qv.vec[s] for s in ids]))
        wall = time.time() - t0
        cost = sum(r["cost_usd"] for r in L.ledger()[n0:])
        print(f"prefetch: {len(miss)} strings in {wall:.1f} s ({len(miss) / max(wall, 1e-9):.0f}/s), ${cost:.5f}",
              flush=True)


def _timed_embed_small(texts):
    n0 = len(L.ledger())
    for att in range(6):
        try:
            t = time.time()
            ai.openai_embed(texts, model=Y.EMB_MODEL, dimensions=Y.EMB_DIM, purpose="c83_te_embed_timing")
            sec = time.time() - t
            return {"seconds": round(sec, 3), "cost_usd": L.ledger()[n0:][-1]["cost_usd"], "attempts": att + 1}
        except Exception as e:  # noqa: BLE001 - transient network errors: retry, keep only the successful call's time
            if "budget stop" in str(e) or att == 5:
                raise
            time.sleep(2 * (att + 1))


def timing(reps):
    os.makedirs(WORK, exist_ok=True)
    jobs = te_jobs(reps)
    out = collections.defaultdict(dict)
    for name in ["inst"] + [f"r{k}" for k in reps]:
        p = os.path.join(WORK, f"embed_timing_te_{name}.json")
        if os.path.exists(p):
            out[name] = json.load(open(p))
    t0 = time.time()
    n = 0
    for rep, q, ss in jobs:
        name = "inst" if rep == 0 else f"r{rep}"
        if q["id"] in out[name]:
            continue
        out[name][q["id"]] = _timed_embed_small(ss)
        n += 1
    for name, d in out.items():
        H.jdump(d, os.path.join(WORK, f"embed_timing_te_{name}.json"))
    wall = time.time() - t0
    print(f"timing: {n} live 3-small calls in {wall:.1f} s ({n / max(wall, 1e-9):.2f} items/s)", flush=True)


# ---------------- fy: refine calls (cached; paid only where round 8.2's cache lacks the exact inputs) ----------------
def refine(reps, workers):
    qs, _ = S81.queries()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    rf = Q.Refiner83(S, F.te_meta_rows())
    orig = ai.openai_chat_json

    def tagged(*a, **k):  # this round's ledger purpose; prompt, model and schema are rf-v1's
        k["purpose"] = "c83_refine"
        return orig(*a, **k)
    ai.openai_chat_json = tagged
    jobs = []
    for rep in reps:
        base = json.load(open(os.path.join(BASE, f"prior_r{rep}.json")))
        per = base["meta"]["per_search"]
        for q in qs:
            if q["examples"] or per[q["id"]]["path"] != "rewrite":
                continue
            if per[q["id"]]["prior"]["q_ig"] >= Q.FY_Q_IG_MAX + 1e-4:  # rounded in the file; superset of the gate
                continue
            jobs.append((rep, q, base["queries"][q["id"]]))
    hits = sum(P.cache_key(r, q["id"], rf.split_top(o)[2]) in rf.cache for r, q, o in jobs)
    print(f"refine: {len(jobs)} gated searches over {len(reps)} repeats; {hits} already cached", flush=True)
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
    te_t = {}
    if cfg == "ti":
        te_t["inst"] = json.load(open(os.path.join(WORK, "embed_timing_te_inst.json")))
    written = []
    for rep in reps:
        Pqr = S81.rewrites("qr-v1", rep)
        need = S81.strings(qs, Pqr, None)
        miss = [s for s in need if s not in S.QV.vec]
        assert not miss, f"{len(miss)} query strings not in the 3-large query store"
        t_h0 = json.load(open(os.path.join(T81, f"embed_timing_h0_r{rep}.json")))
        if cfg == "ti":
            te_t["rw"] = json.load(open(os.path.join(WORK, f"embed_timing_te_r{rep}.json")))
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
            e_s, e_c = e["seconds"], e["cost_usd"]
            if cfg == "ti":
                es = te_t["inst" if path == "instant" else "rw"][q["id"]]
                e_s, e_c = max(e_s, es["seconds"]), e_c + es["cost_usd"]
                by[sp]["te_embed_s"].append(es["seconds"])
                by[sp]["te_in_top10"].append(info["ti"]["te_in_top10"])
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                by[sp]["refine_s"].append(rf_s)
                by[sp]["refine_cost"].append(rf_c)
            d = by[sp]
            tot = local + rw_s + e_s + rf_s
            d["local"].append(local)
            d["total"].append(tot)
            d["cost"].append(rw_c + e_c + rf_c)
            d["routed"].append(path == "instant")
            d[f"total_{path}_path"].append(tot)
            d[f"local_{path}_path"].append(local)
            agg[f"{sp}:{path}"] += 1
            pi = info["prior"]
            for k in ("q_ig", "e_t", "e_k", "e_c", "mult_ig", "mult_yt"):
                d["prior_" + k].append(pi[k])
            agg[f"{sp}:prior_creator_fired"] += pi["n_creators"] > 0
            if path == "rewrite":
                agg[f"{sp}:rewrite_read_yt"] += pi["q_ig"] < Q.FY_Q_IG_MAX
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
            row = {"n_typed": n, "routed_instant": int(sum(d["routed"])),
                   "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                   "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                   "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                   "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                   "local_rewrite_path_p50_s": pct(d["local_rewrite_path"], 50),
                   "local_rewrite_path_p95_s": pct(d["local_rewrite_path"], 95),
                   "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                   "prior": {k[6:]: {f"p{p}": pct(v, p) for p in (5, 25, 50, 75, 95)}
                             for k, v in d.items() if k.startswith("prior_")}}
            if cfg == "fy":
                row["refined"] = len(d["refine_s"])
                row["refine_p50_s"], row["refine_p95_s"] = pct(d["refine_s"], 50), pct(d["refine_s"], 95)
                row["refine_cost_per_1k_refined_usd"] = round(1000 * float(np.mean(d["refine_cost"])), 4) \
                    if d["refine_cost"] else None
            if cfg == "ti":
                row["te_embed_p50_s"], row["te_embed_p95_s"] = pct(d["te_embed_s"], 50), pct(d["te_embed_s"], 95)
                row["te_items_in_top10_mean"] = round(float(np.mean(d["te_in_top10"])), 3) if n else None
            splits[sp] = row
        meta = {"config": cfg, "round": "8.3", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.2 = runs/r8.2/prior_r{k} (prior-p1 on route-r1)", "version": VERSION[cfg],
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]},
                "refine_model": P.REFINE_MODEL if cfg == "fy" else None,
                "refine_gate": f"rewrite-routed and q_ig < {Q.FY_Q_IG_MAX}" if cfg == "fy" else None,
                "pc_keys": env.prior_pc.n_keys if cfg == "pc" else None,
                "te": {"rows": "te-v1c Instagram rows only", "rankable": env.te.n_rankable,
                       "equals_f0_rankable_set": env.te.same_as_f0, "f0_rankable": env.te.n_f0,
                       "dense_query_vectors": f"{Y.EMB_MODEL}@{Y.EMB_DIM}",
                       "fusion": "coverage-fair (c5_lib.fair_fuse)"} if cfg == "ti" else None,
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "route_index_build_s": round(env.route_build_s, 1), "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used + round 8.1's "
                                 "live 3-large embed call (ti: max with the live 3-small te call) + refine call (fy)",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"prior_r{rep}.json")))
        meta["diagnostics_vs_b82"] = S82.top10_diag(out, ref, plat, split_of)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c83:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"total p50 {sa['total_p50_s']} / p95 {sa['total_p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}; "
              f"{json.dumps(meta['diagnostics_vs_b82'])}", flush=True)
        same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
        print(f"{cfg} r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.2/prior (1,000 deep)",
              flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prefetch", "timing", "refine", "run", "compare"])
    ap.add_argument("--configs", default="fy,pc,ti")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    if a.cmd == "prefetch":
        return prefetch(reps)
    if a.cmd == "timing":
        return timing(reps)
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
        run_config(env, cfg, reps, TMP if cfg == "prior" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
