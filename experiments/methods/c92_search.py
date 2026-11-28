"""PROTOTYPE ONLY - round 9.2 Track 1 (per-facet routing) run files (LOG.md "Round 9.2 fixed parameters", rows
Y9.2-B1, Y9.2-B2, Y9.2-B3).

Configs (one variable each vs Q8 = runs/r9.1/q8ref_r{k}):
  q8   Q8 through this runner: must equal runs/r9.1/q8ref_r{k} in every ranking 1,000 deep (tmp/ only).
  b1   Y9.2-B1 named-creator lookup list (code only).
  b2   Y9.2-B2 soft time window from explicit time words (code only).
  b3   Y9.2-B3 additive qi-v1 frame (item_language dense phrase + subject BM25 terms at 0.5) on the rewrite path.
Searches: dev + yt_holdout + known_dev + ig_known_dev + facet_dev (602). facet_dev inputs are read only from
runs/rewrites/facet_dev/. Never opens evals/labels/ or eval_work/; never reads a search timestamp.

usage: python experiments/methods/c92_search.py frames  [--reps 1,2,3]          # paid only for uncached frames
       python experiments/methods/c92_search.py vectors [--reps 1,2,3]          # paid only for new strings
       python experiments/methods/c92_search.py refine --configs b1,b2,b3 [--reps 1,2,3] [--workers 4]
       python experiments/methods/c92_search.py run --configs q8,b1,b2,b3 [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c92_search.py compare --a DIR --b DIR --configs b1,b2,b3
       python experiments/methods/c92_search.py report
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
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c87_lib as C  # noqa: E402
import c88_lib as K  # noqa: E402
import c88_search as S88  # noqa: E402
import c91m_search as M  # noqa: E402
import c91t_search as T  # noqa: E402
import c92_lib as Z  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r9.2")
TMP = os.path.join(DATA, "tmp", "r9.2_checks")
WORK = os.path.join(DATA, "r9.2")
BASE = os.path.join(DATA, "runs", "r9.1", "q8ref_r{rep}.json")
SPLITS = M.SPLITS
CONFIGS = ["q8", "b1", "b2", "b3"]
VERSION = {"q8": "q8-v1", "b1": Z.B1_VERSION, "b2": Z.B2_VERSION, "b3": Z.B3_VERSION}
RF_CACHE = os.path.join(Z.CACHE_DIR, "rf-v1.jsonl")
pct = M.pct


def make_env():
    t0 = time.time()
    env = M.make_env(media=False)
    S = env.S
    r91 = os.path.join(DATA, "r9.1-t1")
    S.QV = T.ArmQV(S.QV.vec, [os.path.join(r91, "qvec_3l")], os.path.join(WORK, "qvec_3l"),
                   lambda m: G.embed_3l(m, "c92_query_vectors_3l", batch=500, workers=1))
    env.te.QVs = T.ArmQV(env.te.QVs.vec, [os.path.join(r91, "qvec_te")], os.path.join(WORK, "qvec_te"),
                         lambda m: normalize(Y.embed_texts(m, "c92_te_query_vectors", batch=500, workers=1)))
    rf = env.refiners[K.NANO]
    for path, tag in ((os.path.join(A_CACHE(), "rf-v1.jsonl"), "r9.1-t1"), (RF_CACHE, "r9.2")):
        if os.path.exists(path):
            for line in open(path):
                r = json.loads(line)
                if r["key"] not in rf.cache:
                    rf.cache[r["key"]] = r
                    rf.source[r["key"]] = tag
    rf.out_path, rf.tag, rf.purpose = RF_CACHE, "r9.2", "c92_refine"
    t1 = time.time()
    env.names = Z.CreatorNames(S)
    env.dates = Z.ItemDates(S)
    env.frames = Z.Frames()
    env.z_build_s = round(time.time() - t1, 1)
    env.build_s = time.time() - t0
    return env


def A_CACHE():
    return os.path.join(DATA, "cache", "r9.1-t1")


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """c91m_search.search_one (q8) with one arm hook."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r, "path": path}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = S88.plan(q, parse, path)
    extra_bm = ""
    if cfg == "b3" and path == "rewrite":
        fr, rec, src = env.frames.get(q["query"], rep)
        fi = {"valid": fr is not None, "source": src, "seconds": rec["seconds"] if rec else 0.0,
              "cost_usd": rec["cost_usd"] if rec else 0.0, "dense_added": False, "bm_terms": 0}
        if fr is not None:
            ed, extra_bm = Z.b3_additions(fr, texts, bq)
            if ed:
                texts = texts + [ed]
            fi["dense_added"], fi["bm_terms"] = bool(ed), len(extra_bm.split())
            fi["kind"], fi["has_subject"] = fr["deliverable"]["kind"], bool(fr["subject"]["text"])
        fi["used"] = fi["dense_added"] or fi["bm_terms"] > 0
        info["frame"] = fi
    own, Qv, s = C.own_lists_s(S, texts, caps, bq, keep)
    if extra_bm:
        own[1] = Z.bm25_weighted(S.bm, bq, extra_bm, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)
    info["prior"] = pinfo
    group = env.te.group(texts, caps, bq, keep)
    if extra_bm:
        E = env.te.E
        group = ([Z.bm25_weighted(E.bm, bq, extra_bm, keep) if E.bm else [], group[0][1]], group[1])
    order, sc = F.fair_fuse(own, [group])
    info["te_used"] = True
    if cfg == "b1":
        creators, m = env.names.creators(q["query"])
        lst = env.names.item_list(S, creators, s, keep)
        info["b1"] = {"fired": bool(lst), "n_matches": len(m), "n_creators": len(creators), "list_len": len(lst),
                      "max_ngram_tokens": max((j - i for _, _, (i, j) in m), default=0)}
        order, sc = Z.add_list(order, sc, lst, Z.B1_W)
    if cfg == "b2":
        wins = Z.parse_time(q["query"], env.dates.ref)
        nb = 0
        if wins:
            order, sc, nb = Z.time_boost(order, sc, env.dates, [w for _, w in wins])
        info["b2"] = {"fired": bool(wins), "kinds": sorted({k for k, _ in wins}), "n_boosted": nb,
                      "share_boosted": round(nb / max(len(order), 1), 4)}
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    g = K.gate("q8", path, q_ig)
    if stop_before_refine:
        return order, {"gate": g, "path": path}
    if g:
        rf = env.refiners[K.NANO]
        (order, rinfo), rr = rf.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "in_tokens": rr.get("in_tokens", 0), "out_tokens": rr.get("out_tokens", 0),
                          "cache": rf.source.get(rr["key"]), "model": K.NANO}
    return order, info


# ---------------- paid steps ----------------
def frames(reps, workers):
    env = make_env()
    qs, split_of = M.queries()
    todo = [q for q in qs if not q["examples"] and env.router_shape.route(q["query"])["path"] == "rewrite"]
    for rep in reps:
        miss = [q for q in todo if env.frames.get(q["query"], rep)[2] == "missing"]
        n0 = len(L.ledger())
        t0 = time.time()
        with cf.ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(lambda q: env.frames.get(q["query"], rep, allow_call=True), miss))
        wall = time.time() - t0
        new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c92_frame"]
        print(f"frames r{rep}: {len(todo)} rewrite-routed, {len(miss)} uncached "
              f"({dict(collections.Counter(split_of[q['id']] for q in miss))}); {len(new)} calls in {wall:.1f} s "
              f"({len(miss) / max(wall, 1e-9):.2f} items/s), ${sum(r['cost_usd'] for r in new):.4f}; valid "
              f"{sum(fr is not None for fr, _, _ in res)}", flush=True)
    print(f"openai ledger ${ai.spent('openai'):.4f}")


def vectors(reps):
    env = make_env()
    qs, _ = M.queries()
    s3, ste = [], []
    for rep in reps:
        P = M.rewrites(rep)
        for q in qs:
            if q["examples"] or env.router_shape.route(q["query"])["path"] != "rewrite":
                continue
            fr, _, _ = env.frames.get(q["query"], rep)
            if fr is None:
                continue
            texts, _, bq = S88.plan(q, P[q["id"]], "rewrite")
            ed, _ = Z.b3_additions(fr, texts, bq)
            if ed:
                s3.append(ed)
                ste.append(ed)
    m3 = len({x for x in s3 if x not in env.S.QV.vec})
    mte = len({x for x in ste if x not in env.te.QVs.vec})
    n0 = len(L.ledger())
    t0 = time.time()
    env.S.QV.get(s3, allow_embed=True)
    env.te.QVs.get(ste, allow_embed=True)
    wall = time.time() - t0
    print(f"vectors: 3-large {m3} new of {len(set(s3))}, 3-small {mte} new of {len(set(ste))}; {wall:.1f} s "
          f"({(m3 + mte) / max(wall, 1e-9):.1f} items/s), ${sum(r['cost_usd'] for r in L.ledger()[n0:]):.5f}",
          flush=True)


def refine(cfgs, reps, workers):
    qs, _ = M.queries()
    env = make_env()
    rf = env.refiners[K.NANO]
    jobs, src = {}, collections.Counter()
    t0 = time.time()
    for cfg in cfgs:
        for rep in reps:
            P = M.rewrites(rep)
            for q in qs:
                if q["examples"]:
                    continue
                order, g = search_one(env, cfg, q, P[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                key = rf.key(rep, q["id"], order)
                src[(cfg, rf.source.get(key, "new"))] += 1
                if key not in rf.cache:
                    jobs.setdefault(key, (rep, q, order))
    print(f"refine: gated by (config, source) {dict(sorted(src.items()))}; {len(jobs)} new inputs "
          f"(pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    if not jobs:
        return
    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
                          [jobs[k] for k in sorted(jobs)]))
    wall = time.time() - t0
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == rf.purpose]
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
        t_h0, te_rw = M.timing(f"embed_timing_h0_r{rep}.json"), M.timing(f"embed_timing_te_r{rep}.json")
        typed = [x for x in qs if not x["examples"]]
        for q in typed[:5]:  # warm-up (not timed, not written)
            search_one(env, cfg, q, P[q["id"]], rep)
        out, per = {}, {}
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        agg = collections.Counter()
        t_run = time.time()
        for q in qs:
            sp = split_of[q["id"]]
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
            fr_s = fr_c = 0.0
            if "frame" in info:
                fr_s, fr_c = info["frame"]["seconds"], info["frame"]["cost_usd"]
                agg[f"{sp}:frame_{info['frame']['source']}"] += 1
                agg[f"{sp}:frame_used"] += info["frame"]["used"]
                agg[f"{sp}:frame_dense_added"] += info["frame"]["dense_added"]
                agg[f"{sp}:frame_bm_terms_any"] += info["frame"]["bm_terms"] > 0
            first = local + max(rw_s, fr_s) + e_s
            rf_s = rf_c = 0.0
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refined_screen"].append(first + rf_s)
                agg[f"{sp}:refine_cache_{info['refine']['cache']}"] += 1
            for arm in ("b1", "b2"):
                if arm in info:
                    agg[f"{sp}:{arm}_fired"] += info[arm]["fired"]
                    agg[f"{sp}:{arm}_fired_{path}"] += info[arm]["fired"]
            if "b2" in info:
                for k in info["b2"]["kinds"]:
                    agg[f"{sp}:b2_kind_{k}"] += 1
            d["local"].append(local)
            d["first_screen"].append(first)
            d[f"first_screen_{path}"].append(first)
            d["total"].append(first + rf_s)
            d["cost"].append(rw_c + fr_c + e_c + rf_c)
            agg[f"{sp}:{path}"] += 1
            per[q["id"]] = {k: v for k, v in info.items() if k != "route"} | {
                "latency_local_s": round(local, 4), "latency_first_screen_s": round(first, 3),
                "latency_total_s": round(first + rf_s, 3), "cost_usd": round(rw_c + fr_c + e_c + rf_c, 8)}
        wall = time.time() - t_run
        allv = collections.defaultdict(list)
        for sp in SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        rows = {}
        for sp, d in [(s, by[s]) for s in SPLITS] + [("all_typed", allv)]:
            n = len(d["local"])
            rows[sp] = {"n_typed": n, "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                        "first_screen": _lat(d, "first_screen"), "first_screen_rewrite": _lat(d, "first_screen_rewrite"),
                        "refined_screen": _lat(d, "refined_screen"), "total_p50_s": pct(d["total"], 50),
                        "total_p95_s": pct(d["total"], 95),
                        "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                        "refined": len(d["refine_s"])}
        ref = json.load(open(BASE.format(rep=rep)))["queries"]
        same = {sp: sum(out[k] == ref[k] for k in out if split_of[k] == sp) for sp in SPLITS}
        top10 = {sp: sum(out[k][:10] != ref[k][:10] for k in out if split_of[k] == sp) for sp in SPLITS}
        meta = {"config": cfg, "round": "9.2 (Track 1 per-facet routing)", "repeat": rep, "splits": SPLITS,
                "n_searches": len(qs), "base": "Q8 (q8-v1) = runs/r9.1/q8ref_r{k}", "version": VERSION[cfg],
                "vector_mode": "int8", "rewrites": {"qr-v1": P["_meta"]["sources"]}, "refine_model": K.NANO,
                "refine_gate": f"rewrite-routed and q_ig < {K.REFINE_Q_IG_MAX}",
                "params": {"b1": {"min_key": Z.B1_MIN_KEY, "max_ngram": Z.B1_MAX_NGRAM, "df_common": Z.B1_DF_COMMON,
                                  "max_creators": Z.B1_MAX_CREATORS, "weight": Z.B1_W,
                                  "name_keys": len(env.names.table)},
                           "b2": {"mult": Z.B2_MULT, "recent_days": Z.B2_RECENT_DAYS, "old_days": Z.B2_OLD_DAYS,
                                  "ref_date": env.dates.ref.isoformat(), "dated_items": env.dates.n_dated},
                           "b3": {"frame": "qi-v1 (round 9.1 cache; new only where uncached)",
                                  "bm_weight": Z.B3_BM_W}}.get(cfg),
                "embedding": "text-embedding-3-large@1024", "route_version": "route-r1",
                "counts": dict(sorted(agg.items())), "per_split": rows, "identical_to_q8_base_by_split": same,
                "top10_changed_vs_q8_by_split": top10, "index_build_s": round(env.build_s, 1),
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + max(qr-v1 call's original seconds, b3 frame call's original seconds) "
                                 "where used + max(3-large, 3-small te embedding call) + refine call",
                "per_search": per}
        p = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c92:{cfg}", L.CodeIds(meta["embedding"]), out,
                      meta)
        sa = rows["all_typed"]
        print(f"wrote {os.path.relpath(p, DATA)}: {len(qs)} searches in {wall:.1f} s ({len(qs) / max(wall, 1e-9):.1f} "
              f"items/s); first p50 {sa['first_screen']['p50_s']} p95 {sa['first_screen']['p95_s']}; $/1k "
              f"{sa['cost_per_1k_searches_usd']}; identical to Q8 {same}; top-10 changed {top10}", flush=True)


def compare(a, b, cfgs, reps):
    for cfg in cfgs:
        for rep in reps:
            x = json.load(open(os.path.join(a, f"{cfg}_r{rep}.json")))["queries"]
            y = json.load(open(os.path.join(b, f"{cfg}_r{rep}.json")))["queries"]
            print(f"{cfg} r{rep}: {sum(x[k] == y.get(k) for k in x)} of {len(x)} rankings identical", flush=True)


def report(reps=(1, 2, 3)):
    """Firing / top-10 change counts per split, facet and trap (method-side tags), mean per repeat; cost, latency."""
    ft = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    tt = json.load(open(os.path.join(DATA, "evals", "trap_tags.json")))["tags"]
    _, split_of = M.queries()
    res = {}
    for cfg in ("b1", "b2", "b3"):
        cnt = collections.Counter()
        lat = collections.defaultdict(list)
        for rep in reps:
            run = json.load(open(os.path.join(OUT, f"{cfg}_r{rep}.json")))
            base = json.load(open(BASE.format(rep=rep)))["queries"]
            for k in ("all_typed", "dev", "known_dev", "ig_known_dev", "facet_dev", "yt_holdout"):
                lat[k].append(run["meta"]["per_split"][k])
            for qid, ps in run["meta"]["per_search"].items():
                sp = split_of[qid]
                on = bool(ps.get(cfg, {}).get("fired")) if cfg != "b3" else bool(ps.get("frame", {}).get("used"))
                ch = run["queries"][qid][:10] != base[qid][:10]
                groups = [f"split:{sp}", f"path:{ps['path']}@{sp}"]
                if qid in ft:
                    groups += [f"facet:{f}@{sp}" for f in ft[qid]["facets"]]
                if qid in tt:
                    groups += [f"trap:{t}@{sp}" for t in tt[qid]] or [f"trap:none@{sp}"]
                if cfg == "b2" and on:
                    groups += [f"b2kind:{k}@{sp}" for k in ps["b2"]["kinds"]]
                for g in groups:
                    cnt[(g, "n")] += 1
                    cnt[(g, "on")] += on
                    cnt[(g, "top10_changed")] += ch
        rows = {g: {m: round(cnt[(g, m)] / len(reps), 2) for m in ("n", "on", "top10_changed")}
                for g in sorted({g for g, _ in cnt})}
        cost = {k: {"cost_per_1k": round(float(np.mean([r["cost_per_1k_searches_usd"] for r in v])), 4),
                    "first_p50": round(float(np.mean([r["first_screen"]["p50_s"] for r in v])), 3),
                    "first_p95": round(float(np.mean([r["first_screen"]["p95_s"] for r in v])), 3),
                    "rewrite_first_p50": round(float(np.mean([r["first_screen_rewrite"]["p50_s"] or 0 for r in v])), 3),
                    "rewrite_first_p95": round(float(np.mean([r["first_screen_rewrite"]["p95_s"] or 0 for r in v])), 3),
                    "refined_p50": round(float(np.mean([r["refined_screen"]["p50_s"] or 0 for r in v])), 3),
                    "refined_p95": round(float(np.mean([r["refined_screen"]["p95_s"] or 0 for r in v])), 3),
                    "local_p50": round(float(np.mean([r["local_p50_s"] for r in v])), 3),
                    "refined_n": round(float(np.mean([r["refined"] for r in v])), 1)} for k, v in lat.items()}
        res[cfg] = {"counts": rows, "cost_latency": cost}
    os.makedirs(WORK, exist_ok=True)
    p = os.path.join(WORK, "report_counts.json")
    json.dump(res, open(p, "w"), indent=1)
    for cfg, r in res.items():
        print(f"== {cfg} (mean per repeat: n / on / top10 changed vs Q8)")
        for k, v in r["counts"].items():
            print(f"  {k:42s} {v['n']:7.2f} {v['on']:7.2f} {v['top10_changed']:7.2f}")
        for k, v in r["cost_latency"].items():
            print(f"  cost/lat {k:14s} {v}")
    print(f"wrote {os.path.relpath(p, DATA)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["frames", "vectors", "refine", "run", "compare", "report"])
    ap.add_argument("--configs", default="b1,b2,b3")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    assert all(c in CONFIGS for c in cfgs), cfgs
    if a.cmd == "frames":
        return frames(reps, a.workers)
    if a.cmd == "vectors":
        return vectors(reps)
    if a.cmd == "refine":
        return refine(cfgs, reps, a.workers)
    if a.cmd == "compare":
        return compare(a.a, a.b, cfgs, reps)
    if a.cmd == "report":
        return report(tuple(reps))
    t0 = time.time()
    env = make_env()
    print(f"index built in {env.build_s:.1f} s (b1/b2/b3 tables {env.z_build_s} s; name keys {len(env.names.table)}, "
          f"friend creators excluded {env.names.n_friend_excluded}; dated items {env.dates.n_dated}, ref "
          f"{env.dates.ref})", flush=True)
    for cfg in cfgs:
        run_config(env, cfg, reps, TMP if cfg == "q8" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
