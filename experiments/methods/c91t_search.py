"""PROTOTYPE ONLY - round 9.1 Track 1 run files (LOG.md "Round 9.1 fixed parameters (Track 1, rows Y9.1-A1, Y9.1-A2).

Configs (one variable each vs Q8 = B8.5):
  q8   Q8 through this runner's pipeline: must equal runs/r8.5/q8_r{k} (dev, known_dev, ig_known_dev) and
       runs/r9/q8_facet_dev_r{k} (facet_dev) in every ranking 1,000 deep (written to tmp/ only; the evaluator's
       base files are those two).
  a1   Y9.1-A1: qi-v1 intent frame instead of qr-v1 on rewrite-routed searches + rf-i1 intent-aware refine.
  a2   Y9.1-A2: ri-v1 intent-word detector sends instant-routed searches with intent words to Q8's rewrite path.
Searches: dev + known_dev + ig_known_dev + facet_dev (591). facet_dev inputs are read from runs/rewrites/facet_dev/
(read only). New query vectors go to r9.1-t1/qvec_3l and r9.1-t1/qvec_te only; caches under cache/r9.1-t1/.

usage: python experiments/methods/c91t_search.py frames [--reps 1,2,3] [--workers 4]     # paid (A1 frames)
       python experiments/methods/c91t_search.py vectors [--reps 1,2,3]                  # paid (new strings)
       python experiments/methods/c91t_search.py refine [--reps 1,2,3] [--workers 4]     # paid (A1, A2 refines)
       python experiments/methods/c91t_search.py timing [--reps 1,2,3]                   # paid (A2 te timing)
       python experiments/methods/c91t_search.py run --configs q8,a1,a2 [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c91t_search.py compare --a DIR --b DIR --configs q8,a1,a2
       python experiments/methods/c91t_search.py report [--outdir DIR]
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
import c81_search as S81  # noqa: E402
import c87_lib as C  # noqa: E402
import c88_lib as K  # noqa: E402
import c88_search as S88  # noqa: E402
import c91t_lib as A  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, load_queries, write_run  # noqa: E402

SPLITS = ["dev", "known_dev", "ig_known_dev", "facet_dev"]
OUT = os.path.join(DATA, "runs", "r9.1")
WORK = os.path.join(DATA, "r9.1-t1")
FD = os.path.join(DATA, "runs", "rewrites", "facet_dev")
BASE = {"r8.5": os.path.join(DATA, "runs", "r8.5", "q8_r{rep}.json"),
        "facet_dev": os.path.join(DATA, "runs", "r9", "q8_facet_dev_r{rep}.json")}
CONFIGS = ["q8", "a1", "a2"]
VERSION = {"q8": "q8-v1", "a1": A.A1_VERSION, "a2": A.A2_VERSION}
pct = S81.pct


def queries():
    out, split_of = [], {}
    for s in SPLITS:
        for q in load_queries(s):
            out.append(q)
            split_of[q["id"]] = s
    return out, split_of


def rewrites(rep):
    S81.RUN_SPLITS[:] = ["dev", "yt_holdout", "known_dev", "ig_known_dev"]
    a = S81.rewrites("qr-v1", rep)
    b = json.load(open(os.path.join(FD, f"qr-v1_gpt-5-nano_r{rep}.json")))
    ks = [k for k in b if not k.startswith("_")]
    assert not set(ks) & set(a)
    out = {k: v for k, v in a.items() if not k.startswith("_")}
    out.update({k: b[k] for k in ks})
    out["_meta"] = {"per_query": {**a["_meta"]["per_query"], **b["_meta"]["per_query"]},
                    "sources": a["_meta"]["sources"] + [os.path.relpath(os.path.join(FD, f"qr-v1_gpt-5-nano_r{rep}.json"),
                                                                        DATA)]}
    return out


class ArmQV:
    """Query vectors: dev store (wins on overlap), then read-only facet_dev store, then this round's own store.
    get() never embeds unless allow_embed (prefetch only); new vectors are saved to the own store (float16)."""

    def __init__(self, base_vec, ro_paths, own_path, embed):
        self.vec = dict(base_vec)
        for p in ro_paths + [own_path]:
            if os.path.exists(os.path.join(p, "ids.json")):
                ids, V = L.load_store(p)
                for k, s in enumerate(ids):
                    if s not in self.vec:
                        self.vec[s] = V[k]
        self.own_path, self.embed = own_path, embed
        self.own_ids = json.load(open(os.path.join(own_path, "ids.json"))) \
            if os.path.exists(os.path.join(own_path, "ids.json")) else []

    def get(self, texts, allow_embed=False):
        miss = sorted({t for t in texts if t not in self.vec})
        if miss:
            assert allow_embed, f"{len(miss)} query strings not prefetched"
            V = self.embed(miss)
            self.vec.update(zip(miss, V))
            self.own_ids += miss
            L.save_store(self.own_path, self.own_ids, np.array([self.vec[s] for s in self.own_ids]))
        return np.array([self.vec[t] for t in texts], dtype=np.float32)


def _merge_json(*paths):
    out = {}
    for p in paths:
        if os.path.exists(p):
            out.update(json.load(open(p)))
    return out


class Env:
    def __init__(self):
        t0 = time.time()
        self.E = S88.Env()
        S = self.E.S
        S.QV = ArmQV(S.QV.vec, [os.path.join(FD, "qvec_3l")], os.path.join(WORK, "qvec_3l"),
                     lambda m: G.embed_3l(m, "c91t_query_vectors_3l", batch=500, workers=1))
        self.E.te.QVs = ArmQV(self.E.te.QVs.vec, [os.path.join(FD, "qvec_te")], os.path.join(WORK, "qvec_te"),
                              lambda m: normalize(Y.embed_texts(m, "c91t_te_query_vectors", batch=500, workers=1)))
        te_rows = F.te_meta_rows()
        rf = K.Refiner88(S, te_rows, model=K.NANO, purpose="c91t_refine")
        for path, tag in ((os.path.join(FD, "refine", "rf-v1.jsonl"), "r9-facet_dev"),
                          (os.path.join(A.CACHE_DIR, "rf-v1.jsonl"), "r9.1-t1")):
            if os.path.exists(path):
                for line in open(path):
                    r = json.loads(line)
                    if r["key"] not in rf.cache:
                        rf.cache[r["key"]] = r
                        rf.source[r["key"]] = tag
        rf.out_path, rf.tag = os.path.join(A.CACHE_DIR, "rf-v1.jsonl"), "r9.1-t1"
        self.rf = rf
        self.rfi = A.RefinerI(S, te_rows)
        self.S = S
        self.build_s = time.time() - t0


# ---------------- the pipeline (Q8's search_one, with the path and plan as inputs) ----------------
def route(env, cfg, q):
    r = env.E.router_shape.route(q["query"])
    path = r["path"]
    fired = []
    if cfg == "a2" and path == "instant":
        fired = A.intent_words(q["query"])
        if fired:
            path = "rewrite"
    return path, r, fired


def plan_for(env, cfg, q, parse, path, rep, frames_only_cache=True):
    """(texts, caps, bq, frame or None, frame record or None)."""
    if path == "instant":
        t, c, b = S88.plan(q, parse, "instant")
        return t, c, b, None, None
    if cfg == "a1":
        fr, rec = (A.frame_cached if frames_only_cache else A.frame_one)(q["query"], rep)
        if fr is not None:
            t, c, b = A.plan_frame(fr)
            return t, c, b, fr, rec
        t, c, b = F.plan_c0(q, parse)
        return t, c, b, None, rec
    t, c, b = F.plan_c0(q, parse)
    return t, c, b, None, None


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    path, r, fired = route(env, cfg, q)
    info = {"route": r, "path": path, "intent_words": fired}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq, fr, frec = plan_for(env, cfg, q, parse, path, rep)
    if cfg == "a1" and path == "rewrite":
        info["frame"] = {"used": fr is not None, "kind": fr["deliverable"]["kind"] if fr else None,
                         "specificity": fr["specificity"]["value"] if fr else None,
                         "qualities": sorted(k for k, v in fr["qualities"].items() if v["text"]) if fr else [],
                         "creator": (("named" if fr["creator"]["named"] else "described")
                                     if fr and (fr["creator"]["named"] or fr["creator"]["described"]) else None),
                         "time": bool(fr and fr["time"]["text"]), "n_drop": len(fr["drop"]) if fr else 0,
                         "seconds": frec["seconds"], "cost_usd": frec["cost_usd"]}
    own, _, _ = C.own_lists_s(S, texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.E.prior.read(q["query"], S.QV.get([q["query"]])[0], order)
    info["prior"] = pinfo
    group = env.E.te.group(texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [group])
    info["te_used"] = True
    order, sc = env.E.prior.apply(order, sc, q_ig)
    order = order[:1000]
    g = path == "rewrite" and q_ig < K.REFINE_Q_IG_MAX
    if stop_before_refine:
        return order, {"gate": g, "path": path, "frame": fr}
    if g:
        if fr is not None:
            (order, rinfo), rr = env.rfi.get_i(rep, q["id"], q["query"], order, fr)
            src, ver = env.rfi.source.get(rr["key"]), A.REFINE_I_VERSION
        else:
            (order, rinfo), rr = env.rf.get(rep, q["id"], q["query"], order)
            src, ver = env.rf.source.get(rr["key"]), "rf-v1"
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "cache": src, "prompt": ver}
    return order, info


# ---------------- paid steps ----------------
def typed_routes(env, cfg):
    qs, split_of = queries()
    out = []
    for q in qs:
        if q["examples"]:
            continue
        path, _, fired = route(env, cfg, q)
        out.append((q, path, fired))
    return out


def frames(reps, workers):
    env = Env()
    todo = [q for q, path, _ in typed_routes(env, "a1") if path == "rewrite"]
    for rep in reps:
        n0 = len(L.ledger())
        t0 = time.time()
        with cf.ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(lambda q: A.frame_one(q["query"], rep), todo))
        wall = time.time() - t0
        new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c91t_frame"]
        ok = sum(fr is not None for fr, _ in res)
        print(f"frames r{rep}: {len(todo)} rewrite-routed searches, {len(new)} new calls in {wall:.1f} s "
              f"({len(todo) / max(wall, 1e-9):.2f} items/s), ${sum(r['cost_usd'] for r in new):.4f}; valid {ok}, "
              f"fallback {len(todo) - ok}; call s p50 {pct([r['seconds'] for _, r in res], 50)} "
              f"p95 {pct([r['seconds'] for _, r in res], 95)}", flush=True)
    print(f"openai ledger ${ai.spent('openai'):.4f}")


def vectors(reps):
    env = Env()
    s3, ste = [], []
    for rep in reps:
        Pqr = rewrites(rep)
        for cfg in ("a1", "a2"):
            for q, path, fired in typed_routes(env, cfg):
                if cfg == "a2" and not fired:
                    continue
                if cfg == "a1" and path != "rewrite":
                    continue
                t, c, b, _, _ = plan_for(env, cfg, q, Pqr[q["id"]], path, rep)
                s3 += [q["query"]] + t + c
                ste += t + c
    n0 = len(L.ledger())
    t0 = time.time()
    m3 = len({s for s in s3 if s not in env.S.QV.vec})
    mte = len({s for s in ste if s not in env.E.te.QVs.vec})
    env.S.QV.get(s3, allow_embed=True)
    env.E.te.QVs.get(ste, allow_embed=True)
    wall = time.time() - t0
    cost = sum(r["cost_usd"] for r in L.ledger()[n0:])
    print(f"vectors: 3-large {m3} new of {len(set(s3))}, 3-small te {mte} new of {len(set(ste))}; {wall:.1f} s "
          f"({(m3 + mte) / max(wall, 1e-9):.1f} items/s), ${cost:.5f}", flush=True)


def refine(reps, workers):
    env = Env()
    qs, _ = queries()
    jobs_i, jobs_v = {}, {}
    src = collections.Counter()
    t0 = time.time()
    for rep in reps:
        Pqr = rewrites(rep)
        for cfg in ("a1", "a2"):
            for q in qs:
                if q["examples"]:
                    continue
                order, g = search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                if g["frame"] is not None:
                    key = env.rfi.key_i(rep, q["id"], order, g["frame"])
                    src[(cfg, "rf-i1", env.rfi.source.get(key, "new"))] += 1
                    if key not in env.rfi.cache:
                        jobs_i.setdefault(key, (rep, q, order, g["frame"]))
                else:
                    key = env.rf.key(rep, q["id"], order)
                    src[(cfg, "rf-v1", env.rf.source.get(key, "new"))] += 1
                    if key not in env.rf.cache:
                        jobs_v.setdefault(key, (rep, q, order))
    print(f"refine: gated by (config, prompt, source) {dict(sorted(src.items()))}; new rf-i1 {len(jobs_i)}, "
          f"rf-v1 {len(jobs_v)} (pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    for name, jobs, fn, purpose in (
            ("rf-i1", jobs_i, lambda j: env.rfi.get_i(j[0], j[1]["id"], j[1]["query"], j[2], j[3], allow_call=True)[1],
             "c91t_refine_intent"),
            ("rf-v1", jobs_v, lambda j: env.rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
             "c91t_refine")):
        if not jobs:
            continue
        n0 = len(L.ledger())
        t1 = time.time()
        with cf.ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(fn, [jobs[k] for k in sorted(jobs)]))
        wall = time.time() - t1
        new = [r for r in L.ledger()[n0:] if r.get("purpose") == purpose]
        print(f"refine {name}: {len(jobs)} calls in {wall:.1f} s ({len(jobs) / max(wall, 1e-9):.2f} items/s), "
              f"${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, failed "
              f"{sum(not r['ok'] for r in res)}; call s p50 {pct([r['seconds'] for r in res], 50)} "
              f"p95 {pct([r['seconds'] for r in res], 95)}", flush=True)
    print(f"openai ledger ${ai.spent('openai'):.4f}")


def _timed_small(texts):
    n0 = len(L.ledger())
    for att in range(6):
        try:
            t = time.time()
            ai.openai_embed(texts, model=Y.EMB_MODEL, dimensions=Y.EMB_DIM, purpose="c91t_te_timing")
            return {"seconds": round(time.time() - t, 3), "cost_usd": L.ledger()[n0:][-1]["cost_usd"],
                    "attempts": att + 1}
        except Exception as e:  # noqa: BLE001 - transient network errors: retry, keep the successful call's time
            if "budget stop" in str(e) or att == 5:
                raise
            time.sleep(2 * (att + 1))


def timing(reps):
    """One live 3-small call per A2-fired search and repeat (its qr-v1 dense + HyDE strings), sequential."""
    env = Env()
    os.makedirs(os.path.join(WORK, "timing"), exist_ok=True)
    fired = [q for q, _, f in typed_routes(env, "a2") if f]
    for rep in reps:
        p = os.path.join(WORK, "timing", f"te_a2_r{rep}.json")
        have = json.load(open(p)) if os.path.exists(p) else {}
        Pqr = rewrites(rep)
        t0 = time.time()
        for q in fired:
            if q["id"] in have:
                continue
            t, c, _ = F.plan_c0(q, Pqr[q["id"]])
            have[q["id"]] = _timed_small(t + c)
        json.dump(have, open(p, "w"))
        wall = time.time() - t0
        print(f"timing r{rep}: {len(fired)} fired searches, {wall:.1f} s; te s p50 "
              f"{pct([v['seconds'] for v in have.values()], 50)} p95 {pct([v['seconds'] for v in have.values()], 95)}",
              flush=True)


# ---------------- runs ----------------
def _lat(d, k):
    return {"p50_s": pct(d[k], 50), "p95_s": pct(d[k], 95), "n": len(d[k])}


def run_config(env, cfg, reps, outdir):
    qs, split_of = queries()
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    t_inst = _merge_json(os.path.join(S88.T81, "embed_timing_inst.json"), os.path.join(FD, "timing",
                                                                                         "embed_timing_inst.json"))
    te_inst = _merge_json(os.path.join(S88.T83, "embed_timing_te_inst.json"),
                          os.path.join(FD, "timing", "embed_timing_te_inst.json"))
    written = []
    for rep in reps:
        Pqr = rewrites(rep)
        t_h0 = _merge_json(os.path.join(S88.T81, f"embed_timing_h0_r{rep}.json"),
                           os.path.join(FD, "timing", f"embed_timing_h0_r{rep}.json"))
        te_rw = _merge_json(os.path.join(S88.T83, f"embed_timing_te_r{rep}.json"),
                            os.path.join(FD, "timing", f"embed_timing_te_r{rep}.json"))
        te_a2 = _merge_json(os.path.join(WORK, "timing", f"te_a2_r{rep}.json"))
        typed = [x for x in qs if not x["examples"]]
        for q in typed[:5]:
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
            path = info["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            if path == "instant":
                e, es, rw_s, rw_c = t_inst[q["id"]], te_inst[q["id"]], 0.0, 0.0
            else:
                e = t_h0[q["id"]]
                es = te_a2[q["id"]] if info["intent_words"] else te_rw[q["id"]]
                if "frame" in info and info["frame"]["used"]:
                    rw_s, rw_c = info["frame"]["seconds"], info["frame"]["cost_usd"]
                    agg[f"{sp}:frame_used"] += 1
                    agg[f"{sp}:frame_kind_{info['frame']['kind']}"] += 1
                    agg[f"{sp}:frame_spec_{info['frame']['specificity']}"] += 1
                    for k in info["frame"]["qualities"]:
                        agg[f"{sp}:frame_quality_{k}"] += 1
                    if info["frame"]["creator"]:
                        agg[f"{sp}:frame_creator_{info['frame']['creator']}"] += 1
                    agg[f"{sp}:frame_time"] += info["frame"]["time"]
                    agg[f"{sp}:frame_any_drop"] += info["frame"]["n_drop"] > 0
                else:
                    if "frame" in info:
                        agg[f"{sp}:frame_fallback"] += 1
                    rw_s, rw_c = rq["seconds"], rq["cost_usd"]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]
            first = local + rw_s + e_s
            rf_s = rf_c = 0.0
            if "refine" in info:
                ri = info["refine"]
                rf_s, rf_c = ri["seconds"], ri["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refined_screen"].append(first + rf_s)
                agg[f"{sp}:refined_{ri['prompt']}"] += 1
                agg[f"{sp}:refine_ok"] += ri["ok"]
                agg[f"{sp}:refine_failed"] += not ri["ok"]
                agg[f"{sp}:refine_cache_{ri['cache']}"] += 1
                agg[f"{sp}:refine_moved_any"] += ri["moved"] > 0
            d["local"].append(local)
            d["first_screen"].append(first)
            d[f"first_screen_{path}"].append(first)
            d["total"].append(first + rf_s)
            d["cost"].append(rw_c + e_c + rf_c)
            d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
            agg[f"{sp}:{path}"] += 1
            if info["intent_words"]:
                agg[f"{sp}:intent_fired"] += 1
                for k in info["intent_words"]:
                    agg[f"{sp}:intent_{k}"] += 1
            per[q["id"]] = {k: v for k, v in info.items() if k != "route"} | {
                "route_r1": info["route"]["path"], "latency_local_s": round(local, 4),
                "latency_first_screen_s": round(first, 3), "latency_total_s": round(first + rf_s, 3),
                "cost_usd": round(rw_c + e_c + rf_c, 8)}
        wall = time.time() - t_run
        allv = collections.defaultdict(list)
        for sp in SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        splits = {}
        for sp, d in [(s, by[s]) for s in SPLITS] + [("all_typed", allv)]:
            n = len(d["local"])
            splits[sp] = {"n_typed": n, "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                          "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                          "first_screen": _lat(d, "first_screen"),
                          "first_screen_instant": _lat(d, "first_screen_instant"),
                          "first_screen_rewrite": _lat(d, "first_screen_rewrite"),
                          "refined_screen": _lat(d, "refined_screen"),
                          "instant_share": round(len(d["first_screen_instant"]) / n, 4) if n else None,
                          "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                          "refined": len(d["refine_s"]), "refine_p50_s": pct(d["refine_s"], 50),
                          "refine_p95_s": pct(d["refine_s"], 95),
                          "yt_share_top10_mean": round(float(np.mean(d["yt_share_top10"])), 4) if n else None}
        meta = {"config": cfg, "round": "9.1", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "Q8 = B8.5 (runs/r8.5/q8_r{k}; facet_dev runs/r9/q8_facet_dev_r{k})",
                "version": VERSION[cfg], "vector_mode": "int8", "route_version": "route-r1",
                "frame": {"prompt": A.FRAME_VERSION, "model": A.FRAME_MODEL, "reasoning": A.FRAME_REASONING}
                if cfg == "a1" else None,
                "refine_prompt": "rf-i1 (frame) / rf-v1 (fallback)" if cfg == "a1" else "rf-v1",
                "intent_router": A.ROUTE_I_VERSION if cfg == "a2" else None,
                "refine_gate": "path == rewrite and q_ig < 0.5", "embedding": "text-embedding-3-large@1024",
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]}, "counts": dict(sorted(agg.items())),
                "per_split": splits, "index_build_s": round(env.build_s, 1), "run_wall_s": round(wall, 1),
                "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite / frame call's original uncached seconds where used + "
                                 "max(3-large, 3-small te embedding call) + refine call; A1 uses Q8's rewrite-path "
                                 "embedding timing of the same search and repeat; A2-fired use H0 3-large timing + "
                                 "a live 3-small timing (r9.1-t1/timing)",
                "per_search": per}
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c91t:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        # reference check against the base files
        ref = json.load(open(BASE["r8.5"].format(rep=rep)))["queries"]
        ref.update(json.load(open(BASE["facet_dev"].format(rep=rep)))["queries"])
        same = {sp: sum(out[k] == ref[k] for k in out if split_of[k] == sp) for sp in SPLITS}
        tot = {sp: sum(1 for k in out if split_of[k] == sp) for sp in SPLITS}
        top10 = {sp: sum(out[k][:10] != ref[k][:10] for k in out if split_of[k] == sp) for sp in SPLITS}
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f} items/s); first p50 {sa['first_screen']['p50_s']} / p95 "
              f"{sa['first_screen']['p95_s']}; refined p50 {sa['refined_screen']['p50_s']} / p95 "
              f"{sa['refined_screen']['p95_s']} (n {sa['refined']}); $/1k {sa['cost_per_1k_searches_usd']}", flush=True)
        print(f"  {cfg} r{rep} identical to Q8 base (1,000 deep): " +
              ", ".join(f"{sp} {same[sp]}/{tot[sp]}" for sp in SPLITS) + "; top-10 changed: " +
              ", ".join(f"{sp} {top10[sp]}" for sp in SPLITS), flush=True)
    return written


def compare(a, b, cfgs, reps):
    for cfg in cfgs:
        for rep in reps:
            ra = json.load(open(os.path.join(a, f"{cfg}_r{rep}.json")))["queries"]
            rb = json.load(open(os.path.join(b, f"{cfg}_r{rep}.json")))["queries"]
            same = sum(ra[k] == rb.get(k) for k in ra)
            print(f"{cfg} r{rep}: {same} / {len(ra)} rankings identical", flush=True)


def report(outdir, reps=(1, 2, 3)):
    """Per-facet / per-trap use counts and top-10 changes vs Q8 (method-side tags only); aggregates."""
    ft = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    tt = json.load(open(os.path.join(DATA, "evals", "trap_tags.json")))["tags"]
    _, split_of = queries()
    res = {}
    for cfg in ("a1", "a2"):
        cnt = collections.Counter()
        for rep in reps:
            run = json.load(open(os.path.join(outdir, f"{cfg}_r{rep}.json")))
            base = json.load(open(BASE["r8.5"].format(rep=rep)))["queries"]
            base.update(json.load(open(BASE["facet_dev"].format(rep=rep)))["queries"])
            for qid, ps in run["meta"]["per_search"].items():
                sp = split_of[qid]
                on = bool(ps.get("intent_words")) if cfg == "a2" else bool(ps.get("frame", {}).get("used"))
                ch = run["queries"][qid][:10] != base[qid][:10]
                groups = [("split", sp)]
                if qid in ft:
                    groups += [("facet", f) for f in ft[qid]["facets"]] + [("spec", ft[qid]["specificity"])]
                    groups.append(("tagged", sp))
                if qid in tt:
                    groups += [("trap", t) for t in tt[qid]] + [("trap_tagged", sp)]
                    if not tt[qid]:
                        groups.append(("trap", "none"))
                for g in groups:
                    key = f"{g[0]}:{g[1]}" if g[0] not in ("facet", "spec", "trap") else f"{g[0]}:{g[1]}@{sp}"
                    cnt[(key, "n")] += 1
                    cnt[(key, "on")] += on
                    cnt[(key, "top10_changed")] += ch
        res[cfg] = {k: {m: round(cnt[(k, m)] / len(reps), 2) for m in ("n", "on", "top10_changed")}
                    for k in sorted({k for k, _ in cnt})}
    p = os.path.join(WORK, "report_counts.json")
    os.makedirs(WORK, exist_ok=True)
    json.dump(res, open(p, "w"), indent=1)
    for cfg, rows in res.items():
        print(f"== {cfg} (mean per repeat: n / on / top10 changed vs Q8)")
        for k, v in rows.items():
            print(f"  {k:40s} {v['n']:7.2f} {v['on']:7.2f} {v['top10_changed']:7.2f}")
    print(f"wrote {os.path.relpath(p, DATA)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["frames", "vectors", "refine", "timing", "run", "compare", "report"])
    ap.add_argument("--configs", default="q8,a1,a2")
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
    if a.cmd == "frames":
        return frames(reps, a.workers)
    if a.cmd == "vectors":
        return vectors(reps)
    if a.cmd == "refine":
        return refine(reps, a.workers)
    if a.cmd == "timing":
        return timing(reps)
    if a.cmd == "compare":
        return compare(a.a, a.b, cfgs, reps)
    if a.cmd == "report":
        return report(a.outdir, tuple(reps))
    t0 = time.time()
    env = Env()
    print(f"index built in {env.build_s:.1f} s", flush=True)
    for cfg in cfgs:  # q8 (the reproduction check) never goes to runs/r9.1/
        run_config(env, cfg, reps, os.path.join(DATA, "tmp", "r9.1-t1_checks") if cfg == "q8" and a.outdir == OUT
                   else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
