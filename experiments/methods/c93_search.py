"""PROTOTYPE ONLY - round 9.3 Track 1 (items 5 and 7) run files (LOG.md "Round 9.3 fixed parameters", rows Y9.3-C1,
Y9.3-C2).

Configs (one variable each vs Q8 = runs/r9.1/q8ref_r{k}):
  q8   Q8 through this runner: must equal runs/r9.1/q8ref_r{k} in every ranking 1,000 deep (tmp/ only).
  c1   Y9.3-C1 personal vocabulary expansion (pv-v1, code only; map from the user's own library).
  c2   Y9.3-C2 intent-aware refine alone (rf-i1 with round 9.1's cached qi-v1 frame; Q8 retrieval and gate).
Searches: dev + yt_holdout + known_dev + ig_known_dev + facet_dev (602). yt_holdout is NOT run for c1 / c2: its
rankings are copied from Q8 unchanged (no rewrite, embedding or LLM call for it). facet_dev inputs are read only
from runs/rewrites/facet_dev/. Never opens evals/labels/ or eval_work/; never reads a search timestamp.

usage: python experiments/methods/c93_search.py vmap                                # build / check the C1 map
       python experiments/methods/c93_search.py refine --configs c1,c2 [--reps 1,2,3] [--workers 4]  # paid if new
       python experiments/methods/c93_search.py run --configs q8,c1,c2 [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c93_search.py compare --a DIR --b DIR --configs c1,c2
       python experiments/methods/c93_search.py report
Prints aggregates only (no query or item text).
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
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c87_lib as C  # noqa: E402
import c88_lib as K  # noqa: E402
import c88_search as S88  # noqa: E402
import c91m_search as M  # noqa: E402
import c91t_lib as A  # noqa: E402
import c92_search as Z2  # noqa: E402
import c93_lib as V  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r9.3")
TMP = os.path.join(DATA, "tmp", "r9.3_checks")
WORK = V.WORK
CACHE_DIR = os.path.join(DATA, "cache", "r9.3")
BASE = os.path.join(DATA, "runs", "r9.1", "q8ref_r{rep}.json")
SPLITS = M.SPLITS
RUN_SPLITS = [s for s in SPLITS if s != "yt_holdout"]
CONFIGS = ["q8", "c1", "c2"]
VERSION = {"q8": "q8-v1", "c1": V.C1_VERSION, "c2": V.C2_VERSION}
pct = M.pct


def make_env():
    t0 = time.time()
    env = Z2.make_env()  # Q8 pipeline (c91m) + round 9.1 / 9.2 query-vector stores and refine caches, qi-v1 frames
    S = env.S
    rf = env.refiners[K.NANO]
    rv1 = os.path.join(CACHE_DIR, "rf-v1.jsonl")
    if os.path.exists(rv1):
        for line in open(rv1):
            r = json.loads(line)
            if r["key"] not in rf.cache:
                rf.cache[r["key"]] = r
                rf.source[r["key"]] = "r9.3"
    rf.out_path, rf.tag, rf.purpose = rv1, "r9.3", "c93_refine"
    rfi = A.RefinerI(S, F.te_meta_rows())  # loads round 9.1's rf-i1 cache (A1's inputs)
    ri1 = os.path.join(CACHE_DIR, f"{A.REFINE_I_VERSION}.jsonl")
    if os.path.exists(ri1):
        for line in open(ri1):
            r = json.loads(line)
            if r["key"] not in rfi.cache:
                rfi.cache[r["key"]] = r
                rfi.source[r["key"]] = "r9.3"
    rfi.out_path, rfi.tag, rfi.purpose = ri1, "r9.3", "c93_refine_intent"
    env.rfi = rfi
    t1 = time.time()
    m = V.build_map(S.items, common=env.names.common)
    if os.path.exists(V.MAP_PATH):
        old = json.load(open(V.MAP_PATH, encoding="utf-8"))
        assert old["entries"] == json.loads(json.dumps(m["entries"])), "C1 map differs from the stored map"
        m["meta"]["build_s"] = old["meta"]["build_s"]
    else:
        V.save_map(m)
    env.vmap = V.VocabMap(json.loads(json.dumps(m)))
    env.vmap_build_s = round(time.time() - t1, 1)
    env.build_s = time.time() - t0
    return env


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """c92_search.search_one (q8) with one arm hook."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r, "path": path}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = S88.plan(q, parse, path)
    extra = ""
    if cfg == "c1":
        extra, info["c1"] = env.vmap.expand(q["query"], bq)
    own, Qv, s = C.own_lists_s(S, texts, caps, bq, keep)
    if extra:
        own[1] = V.bm25_weighted(S.bm, bq, extra, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)
    info["prior"] = pinfo
    group = env.te.group(texts, caps, bq, keep)
    if extra:
        E = env.te.E
        group = ([V.bm25_weighted(E.bm, bq, extra, keep) if E.bm else [], group[0][1]], group[1])
    order, sc = F.fair_fuse(own, [group])
    info["te_used"] = True
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    g = K.gate("q8", path, q_ig)
    fr, frec = None, None
    if g and cfg == "c2":
        fr, frec, fsrc = env.frames.get(q["query"], rep)
        info["frame"] = {"valid": fr is not None, "source": fsrc, "seconds": frec["seconds"] if frec else 0.0,
                         "cost_usd": frec["cost_usd"] if frec else 0.0,
                         "kind": fr["deliverable"]["kind"] if fr else None}
    if stop_before_refine:
        return order, {"gate": g, "path": path, "frame": fr}
    if g:
        if fr is not None:
            rfi = env.rfi
            (order, rinfo), rr = rfi.get_i(rep, q["id"], q["query"], order, fr)
            prompt, cache = A.REFINE_I_VERSION, rfi.source.get(rr["key"])
        else:
            rf = env.refiners[K.NANO]
            (order, rinfo), rr = rf.get(rep, q["id"], q["query"], order)
            prompt, cache = "rf-v1", rf.source.get(rr["key"])
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "in_tokens": rr.get("in_tokens", 0), "out_tokens": rr.get("out_tokens", 0),
                          "cache": cache, "model": K.NANO, "prompt": prompt, "ok": rr.get("ok", True)}
    return order, info


# ---------------- paid step: refine calls for inputs no cache holds ----------------
def refine(cfgs, reps, workers):
    qs, split_of = M.queries()
    env = make_env()
    rf, rfi = env.refiners[K.NANO], env.rfi
    jobs, src = {}, collections.Counter()
    t0 = time.time()
    for cfg in cfgs:
        for rep in reps:
            P = M.rewrites(rep)
            for q in qs:
                if q["examples"] or split_of[q["id"]] == "yt_holdout":
                    continue
                order, g = search_one(env, cfg, q, P[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                if g["frame"] is not None:
                    key = rfi.key_i(rep, q["id"], order, g["frame"])
                    src[(cfg, "rf-i1", rfi.source.get(key, "new"))] += 1
                    if key not in rfi.cache:
                        jobs.setdefault(("i", key), (rep, q, order, g["frame"]))
                else:
                    key = rf.key(rep, q["id"], order)
                    src[(cfg, "rf-v1", rf.source.get(key, "new"))] += 1
                    if key not in rf.cache:
                        jobs.setdefault(("v", key), (rep, q, order, None))
    print(f"refine: gated by (config, prompt, source) {dict(sorted(src.items()))}; {len(jobs)} new inputs "
          f"(pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    if not jobs:
        return

    def one(j):
        rep, q, order, fr = j
        if fr is not None:
            return rfi.get_i(rep, q["id"], q["query"], order, fr, allow_call=True)[1]
        return rf.get(rep, q["id"], q["query"], order, allow_call=True)[1]

    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, [jobs[k] for k in sorted(jobs)]))
    wall = time.time() - t0
    new = [r for r in L.ledger()[n0:] if r.get("purpose") in (rf.purpose, rfi.purpose)]
    print(f"refine: {len(jobs)} calls in {wall:.1f} s ({len(jobs) / max(wall, 1e-9):.2f} items/s), {len(new)} ledger "
          f"rows, ${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, failed "
          f"{sum(not r['ok'] for r in res)}", flush=True)
    print(f"openai ledger ${ai.spent('openai'):.4f}")


# ---------------- runs ----------------
def _lat(d, k):
    return {"p50_s": pct(d[k], 50), "p95_s": pct(d[k], 95), "n": len(d[k])}


def run_config(env, cfg, reps, outdir):
    qs, split_of = M.queries()
    t_inst, te_inst = M.timing("embed_timing_inst.json"), M.timing("embed_timing_te_inst.json")
    for rep in reps:
        P = M.rewrites(rep)
        base_run = json.load(open(BASE.format(rep=rep)))
        base = base_run["queries"]
        t_h0, te_rw = M.timing(f"embed_timing_h0_r{rep}.json"), M.timing(f"embed_timing_te_r{rep}.json")
        typed = [x for x in qs if not x["examples"] and split_of[x["id"]] != "yt_holdout"]
        for q in typed[:5]:  # warm-up (not timed, not written)
            search_one(env, cfg, q, P[q["id"]], rep)
        out, per = {}, {}
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        agg = collections.Counter()
        n_run = 0
        t_run = time.time()
        for q in qs:
            sp = split_of[q["id"]]
            if sp == "yt_holdout" and cfg != "q8":
                out[q["id"]] = list(base[q["id"]])
                per[q["id"]] = {"copied_from_q8": True}
                continue
            n_run += 1
            parse = None if q["examples"] else P[q["id"]]
            t = time.time()
            order, info = search_one(env, cfg, q, parse, rep)
            local = time.time() - t
            out[q["id"]] = order
            if q["examples"]:
                continue
            d = by[sp]
            path = info["path"]
            rq = P["_meta"]["per_query"][q["id"]]
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
            es = (te_inst if path == "instant" else te_rw)[q["id"]]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]
            first = local + rw_s + e_s
            cost = rw_c + e_c
            rf_s = rf_c = fr_s = fr_c = 0.0
            if "frame" in info:
                fr_s, fr_c = info["frame"]["seconds"], info["frame"]["cost_usd"]
                agg[f"{sp}:frame_{info['frame']['source']}"] += 1
                agg[f"{sp}:frame_valid"] += info["frame"]["valid"]
                if info["frame"]["kind"]:
                    agg[f"{sp}:frame_kind_{info['frame']['kind']}"] += 1
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refined_screen"].append(first + fr_s + rf_s)  # C2 primary: frame call after the first screen
                agg[f"{sp}:refine_{info['refine']['prompt']}_cache_{info['refine']['cache']}"] += 1
                agg[f"{sp}:refine_failed"] += not info["refine"]["ok"]
            if "c1" in info:
                agg[f"{sp}:c1_fired"] += info["c1"]["fired"]
                agg[f"{sp}:c1_fired_{path}"] += info["c1"]["fired"]
                agg[f"{sp}:c1_matched_any"] += info["c1"]["n_matches"] > 0
                for ty in info["c1"]["types"]:
                    agg[f"{sp}:c1_type_{ty}"] += 1
            cost_main = cost + rf_c + fr_c  # C2 primary (frame only on refined searches)
            # C2 alternative: frame on every rewrite-routed search, in parallel with qr-v1
            alt_first = local + max(rw_s, fr_s) + e_s if cfg == "c2" and path == "rewrite" else first
            d["local"].append(local)
            d["first_screen"].append(first)
            d[f"first_screen_{path}"].append(first)
            d["total"].append(first + fr_s + rf_s)
            d["cost"].append(cost_main)
            per[q["id"]] = {k: v for k, v in info.items() if k != "route"} | {
                "latency_local_s": round(local, 4), "latency_first_screen_s": round(first, 3),
                "latency_total_s": round(first + fr_s + rf_s, 3), "cost_usd": round(cost_main, 8)}
            if cfg == "c2" and path == "rewrite":
                d["alt_first_screen_rewrite"].append(alt_first)
                if "refine" in info:
                    d["alt_refined_screen"].append(alt_first + rf_s)
            agg[f"{sp}:{path}"] += 1
        wall = time.time() - t_run
        allv = collections.defaultdict(list)
        for sp in RUN_SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        rows = {}
        splits_here = SPLITS if cfg == "q8" else RUN_SPLITS
        for sp, d in [(s, by[s]) for s in splits_here] + [("all_typed", allv)]:
            n = len(d["local"])
            rows[sp] = {"n_typed": n, "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                        "first_screen": _lat(d, "first_screen"), "first_screen_rewrite": _lat(d, "first_screen_rewrite"),
                        "refined_screen": _lat(d, "refined_screen"), "total_p50_s": pct(d["total"], 50),
                        "total_p95_s": pct(d["total"], 95),
                        "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                        "refined": len(d["refine_s"])}
        ref = base
        same = {sp: sum(out[k] == ref[k] for k in out if split_of[k] == sp) for sp in SPLITS}
        top10 = {sp: sum(out[k][:10] != ref[k][:10] for k in out if split_of[k] == sp) for sp in SPLITS}
        meta = {"config": cfg, "round": "9.3 (Track 1 items 5 and 7)", "repeat": rep, "splits": SPLITS,
                "n_searches": len(qs), "base": "Q8 (q8-v1) = runs/r9.1/q8ref_r{k}", "version": VERSION[cfg],
                "yt_holdout": "run (reproduction)" if cfg == "q8" else "copied from Q8 unchanged (not run)",
                "vector_mode": "int8", "rewrites": {"qr-v1": P["_meta"]["sources"]}, "refine_model": K.NANO,
                "refine_gate": f"rewrite-routed and q_ig < {K.REFINE_Q_IG_MAX}",
                "params": {"c1": {"map": os.path.relpath(V.MAP_PATH, DATA), "map_sizes": env.vmap.meta["sizes"],
                                  **env.vmap.meta["params"]},
                           "c2": {"refine_prompt": A.REFINE_I_VERSION, "frame": "qi-v1 (cached; rounds 9.1 / 9.2)",
                                  "fallback": "rf-v1 where no valid cached frame"}}.get(cfg),
                "embedding": "text-embedding-3-large@1024", "route_version": "route-r1",
                "counts": dict(sorted(agg.items())), "per_split": rows, "identical_to_q8_base_by_split": same,
                "top10_changed_vs_q8_by_split": top10, "index_build_s": round(env.build_s, 1),
                "vmap_build_s": env.vmap_build_s, "run_wall_s": round(wall, 1),
                "searches_per_s": round(n_run / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + qr-v1 call's original seconds where used + max(3-large, 3-small te "
                                 "embedding call) + [c2: cached qi-v1 frame call's original seconds, refined searches "
                                 "only] + refine call",
                "per_search": per}
        if cfg == "c2":
            meta["c2_alt_frame_parallel"] = {
                "model": "frame on every rewrite-routed search in parallel with qr-v1",
                "first_screen_rewrite": _lat(allv, "alt_first_screen_rewrite"),
                "refined_screen": _lat(allv, "alt_refined_screen")}
        p = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c93:{cfg}", L.CodeIds(meta["embedding"]), out,
                      meta)
        sa = rows["all_typed"]
        print(f"wrote {os.path.relpath(p, DATA)}: {n_run} searches run in {wall:.1f} s "
              f"({n_run / max(wall, 1e-9):.1f} items/s); first p50 {sa['first_screen']['p50_s']} p95 "
              f"{sa['first_screen']['p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}; identical to Q8 {same}; "
              f"top-10 changed {top10}", flush=True)


def compare(a, b, cfgs, reps):
    for cfg in cfgs:
        for rep in reps:
            x = json.load(open(os.path.join(a, f"{cfg}_r{rep}.json")))["queries"]
            y = json.load(open(os.path.join(b, f"{cfg}_r{rep}.json")))["queries"]
            print(f"{cfg} r{rep}: {sum(x[k] == y.get(k) for k in x)} of {len(x)} rankings identical", flush=True)


def report(reps=(1, 2, 3)):
    """Firing / top-10 change counts per split, path, facet and trap (method-side tags), mean per repeat; cost and
    latency for Q8 (tmp reproduction), C1 and C2 over the four run sets (yt_holdout excluded)."""
    ft = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    tt = json.load(open(os.path.join(DATA, "evals", "trap_tags.json")))["tags"]
    _, split_of = M.queries()
    res = {}
    for cfg in ("q8", "c1", "c2"):
        d = TMP if cfg == "q8" else OUT
        cnt = collections.Counter()
        lat = collections.defaultdict(list)
        alt = []
        for rep in reps:
            run = json.load(open(os.path.join(d, f"{cfg}_r{rep}.json")))
            base = json.load(open(BASE.format(rep=rep)))["queries"]
            if cfg == "c2":
                alt.append(run["meta"]["c2_alt_frame_parallel"])
            if cfg == "q8":
                # Q8 cost / latency over the same four sets as the arms
                ps = run["meta"]["per_search"]
                pool = collections.defaultdict(list)
                for qid, x in ps.items():
                    if split_of[qid] == "yt_holdout" or "latency_first_screen_s" not in x:
                        continue
                    pool["first"].append(x["latency_first_screen_s"])
                    pool["cost"].append(x["cost_usd"])
                    if x["path"] == "rewrite":
                        pool["rw"].append(x["latency_first_screen_s"])
                    if "refine" in x:
                        pool["ref"].append(x["latency_total_s"])
                    pool["local"].append(x["latency_local_s"])
                lat["all_typed"].append({"cost_per_1k_searches_usd": 1000 * float(np.mean(pool["cost"])),
                                         "first_screen": {"p50_s": pct(pool["first"], 50),
                                                          "p95_s": pct(pool["first"], 95)},
                                         "first_screen_rewrite": {"p50_s": pct(pool["rw"], 50),
                                                                  "p95_s": pct(pool["rw"], 95)},
                                         "refined_screen": {"p50_s": pct(pool["ref"], 50), "p95_s": pct(pool["ref"], 95)},
                                         "local_p50_s": pct(pool["local"], 50), "refined": len(pool["ref"])})
                for k in RUN_SPLITS:
                    lat[k].append(run["meta"]["per_split"][k])
                continue
            for k in ["all_typed"] + RUN_SPLITS:
                lat[k].append(run["meta"]["per_split"][k])
            for qid, ps in run["meta"]["per_search"].items():
                sp = split_of[qid]
                if sp == "yt_holdout":
                    continue
                if cfg == "c1":
                    on = bool(ps.get("c1", {}).get("fired"))
                else:
                    on = "refine" in ps and ps["refine"].get("prompt") == A.REFINE_I_VERSION
                ch = run["queries"][qid][:10] != base[qid][:10]
                groups = [f"split:{sp}", f"path:{ps.get('path', 'mlt')}@{sp}"]
                if qid in ft:
                    groups += [f"facet:{f}@{sp}" for f in ft[qid]["facets"]]
                if qid in tt:
                    groups += [f"trap:{t}@{sp}" for t in tt[qid]] or [f"trap:none@{sp}"]
                if cfg == "c1" and on:
                    groups += [f"c1type:{t}@{sp}" for t in sorted(set(ps["c1"]["types"]))]
                    groups += [f"c1entries:{ps['c1']['n_entries']}@{sp}"]
                for g in groups:
                    cnt[(g, "n")] += 1
                    cnt[(g, "on")] += on
                    cnt[(g, "top10_changed")] += ch
        rows = {g: {m: round(cnt[(g, m)] / len(reps), 2) for m in ("n", "on", "top10_changed")}
                for g in sorted({g for g, _ in cnt})}

        def mean(v, *ks):
            xs = []
            for r in v:
                x = r
                for k in ks:
                    x = x.get(k) if isinstance(x, dict) else None
                xs.append(x or 0)
            return round(float(np.mean(xs)), 4)

        cost = {k: {"cost_per_1k": mean(v, "cost_per_1k_searches_usd"),
                    "first_p50": mean(v, "first_screen", "p50_s"), "first_p95": mean(v, "first_screen", "p95_s"),
                    "rewrite_first_p50": mean(v, "first_screen_rewrite", "p50_s"),
                    "rewrite_first_p95": mean(v, "first_screen_rewrite", "p95_s"),
                    "refined_p50": mean(v, "refined_screen", "p50_s"), "refined_p95": mean(v, "refined_screen", "p95_s"),
                    "local_p50": mean(v, "local_p50_s"), "refined_n": mean(v, "refined")} for k, v in lat.items()}
        res[cfg] = {"counts": rows, "cost_latency": cost}
        if alt:
            res[cfg]["alt_frame_parallel"] = {
                "rewrite_first_p50": round(float(np.mean([a["first_screen_rewrite"]["p50_s"] for a in alt])), 3),
                "rewrite_first_p95": round(float(np.mean([a["first_screen_rewrite"]["p95_s"] for a in alt])), 3),
                "refined_p50": round(float(np.mean([a["refined_screen"]["p50_s"] for a in alt])), 3),
                "refined_p95": round(float(np.mean([a["refined_screen"]["p95_s"] for a in alt])), 3)}
    os.makedirs(WORK, exist_ok=True)
    p = os.path.join(WORK, "report_counts.json")
    json.dump(res, open(p, "w"), indent=1)
    for cfg, r in res.items():
        print(f"== {cfg} (mean per repeat: n / on / top10 changed vs Q8)")
        for k, v in r["counts"].items():
            print(f"  {k:42s} {v['n']:7.2f} {v['on']:7.2f} {v['top10_changed']:7.2f}")
        for k, v in r["cost_latency"].items():
            print(f"  cost/lat {k:14s} {v}")
        if "alt_frame_parallel" in r:
            print(f"  alt frame-parallel {r['alt_frame_parallel']}")
    print(f"wrote {os.path.relpath(p, DATA)}")


def vmap():
    env = make_env()
    m = env.vmap.meta
    print(f"C1 map: {sum(m['sizes'].values())} entries {m['sizes']}; items used {m['items_used']}, friend items "
          f"excluded {m['friend_items_excluded']}; build {m['build_s']} s ({m['items_used'] / max(m['build_s'], 1e-9):.0f}"
          f" items/s); stored at {os.path.relpath(V.MAP_PATH, DATA)}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["vmap", "refine", "run", "compare", "report"])
    ap.add_argument("--configs", default="c1,c2")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    assert all(c in CONFIGS for c in cfgs), cfgs
    if a.cmd == "vmap":
        return vmap()
    if a.cmd == "refine":
        return refine(cfgs, reps, a.workers)
    if a.cmd == "compare":
        return compare(a.a, a.b, cfgs, reps)
    if a.cmd == "report":
        return report(tuple(reps))
    t0 = time.time()
    env = make_env()
    print(f"index built in {env.build_s:.1f} s (C1 map {env.vmap_build_s} s, {sum(env.vmap.meta['sizes'].values())} "
          f"entries)", flush=True)
    for cfg in cfgs:
        run_config(env, cfg, reps, TMP if cfg == "q8" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
