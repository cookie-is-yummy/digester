"""PROTOTYPE ONLY - round 5 run files (LOG.md Y5-F0 ... Y5-F5) over the combined index.

Configs (one variable each vs C0; F5 is the preregistered stack):
  f0   C0 + te lists (te rows rankable only for items whose own text is not a real title), coverage-fair fusion.
  f1   C0 with the qs-v1 typed-slot plan instead of qr-v1 (dense: topic phrases + HyDE; BM25: topic/format terms).
  f2   C0 + creator search on qs-v1 creator_lookup searches (profiles, 3-list creator ranking, pick-v1, creator list).
  f2n  f2 without the LLM pick (ablation, diagnostic only).
  f3   C0 + soft facet boosts from qs-v1 format / tone (F3 mapping table).
  f4   C0 + chk-v1 per-property checker on the top 20 (format / tone slots).
  f5   f0's lists + f1's plan + f2 + f3 + E1's guarded qi-v3 intent + f4.
  c0chk / d1chk  reproduction checks of r4.2 c0x / d1 (written to tmp/, not scored).
Searches: load_queries('dev') + load_queries('yt_holdout'), or --queries FILE. qr-v1 / qi-v3 / qs-v1 parses come from
runs/rewrites (or --rewrites-dir); repeat k uses repeat k of each. Every LLM call is cached (c5_rewrite.cached_chat).
Writes $DIGESTER_DATA/runs/r5/<cfg>_r<k>.json with lib/corpus.write_run; cost and latency in meta. Prints aggregates
only (no query text, no items).

usage: python experiments/methods/c5_search.py --configs f0,f1,f2,f2n,f3,f4,f5 [--reps 1,2,3]
       python experiments/methods/c5_search.py --stats      # slot fire counts per kind (aggregate)
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c5_rewrite as RW  # noqa: E402
from corpus import DATA, load_queries, write_run  # noqa: E402

CONFIGS = ["f0", "f1", "f2", "f2n", "f3", "f4", "f5", "c0chk", "d1chk"]
TE_F0 = {"f0", "f5"}
PLAN_F1 = {"f1", "f5"}
CREATOR = {"f2", "f2n", "f5"}
PICK = {"f2", "f5"}
FACET = {"f3", "f5"}
CHECK = {"f4", "f5"}
INTENT = {"f5"}
USES_QS = {"f1", "f2", "f2n", "f3", "f4", "f5"}
USES_QR = {"f0", "f2", "f2n", "f3", "f4", "c0chk", "d1chk"}
ALT = {"queries": None, "rewrites": None, "outdir": None, "suffix": "", "splits": None}


class Timer:
    """Wall time spent inside LLM calls (cached or live), so local time can be reported without them."""

    def __init__(self):
        self.s = 0.0

    def call(self, fn, *a, **k):
        t = time.time()
        out = fn(*a, **k)
        self.s += time.time() - t
        return out


def queries():
    if ALT["queries"]:
        return [json.loads(line) for line in open(ALT["queries"]) if line.strip()]
    return load_queries("dev") + load_queries("yt_holdout")


def rw(prefix, rep):
    d = ALT["rewrites"] or os.path.join(DATA, "runs", "rewrites")
    return json.load(open(os.path.join(d, f"{prefix}_gpt-5-nano_r{rep}.json")))


class Env:
    def __init__(self, items):
        t0 = time.time()
        self.S = L.Combined("all", items=items)
        self.E_all = L.EnrichIdx(L.te_sources(), set(self.S.pos))
        self.E_f0 = L.EnrichIdx(L.te_sources(), set(self.S.pos), F.te_active_f0(self.S))
        self.te_rows = F.te_meta_rows()
        t1 = time.time()
        self.CR = F.Creators(self.S, self.te_rows, self.E_all.ex_vec)
        self.creator_build_s = time.time() - t1
        self.CR_elig = set(self.CR.of)
        self.FA = F.Facets(self.S, self.te_rows)
        self.intent = None
        self.build_s = time.time() - t0

    def need_intent(self):
        if self.intent is None:
            import c4_intent
            c4_intent.prepare(self.S)
            self.intent = c4_intent
        return self.intent


def te_for(cfg, env):
    return env.E_f0 if cfg in TE_F0 else env.E_all if cfg == "d1chk" else None


def search_one(env, cfg, q, Pqr, Pqs, PI, T):
    S = env.S
    info, calls = {}, []
    E = te_for(cfg, env)
    if q["examples"]:
        S.E = [E] if E else []
        S.fusion = "fair" if E else "rrf"
        return S.mlt(q), info, calls
    keep = S.keep_fn(q.get("filters"))
    slots = Pqs[q["id"]] if Pqs else None
    qtexts, caps, bq = F.plan_f1(q, slots) if cfg in PLAN_F1 else F.plan_c0(q, Pqr[q["id"]])
    own, Qv = F.own_lists(S, qtexts, caps, bq, keep)
    groups = [([E.bm25(bq, keep), E.dense(Qv, keep)], E.codeset)] if E else []
    order, sc = F.fair_fuse(own, groups)
    if cfg in CREATOR and slots["creator_lookup"]["is"]:
        t = slots["topic"]
        desc = slots["creator_lookup"]["description"]
        ranking = env.CR.rank(S.QV, desc, t["phrases"], t["terms"] + t["expansions"], order)
        info["creator_lookup"] = True
        if cfg in PICK:
            ranking, pinfo, rec = T.call(env.CR.pick, ranking, desc, t["phrases"])
            info["pick"] = pinfo
            if rec:
                calls.append(("pick", rec))
        clist = env.CR.item_list(S, ranking, order, Qv, keep)
        info["creator_items_listed"] = len(clist)
        order, sc = F.fair_fuse(own, groups + [([clist], env.CR_elig)])
    if cfg in FACET:
        order, finfo = env.FA.boost(order, sc, slots)
        info["facets"] = finfo
    if cfg in INTENT:
        I = env.need_intent()
        raw_i = PI[q["id"]]["intent"]
        gi, dropped = I.guard_v43(raw_i, q["query"], PI[q["id"]].get("kind"))
        order, iinfo = I.apply(S, order, gi, unknown_watch=True, widen_only=True)
        iinfo.update({"raw_intent": I.describe(raw_i), "dropped_by_guard": dropped})
        info["intent"] = iinfo
    if cfg in CHECK:
        order, cinfo, rec = T.call(F.check_top, S, order, slots, env.te_rows)
        info["check"] = cinfo
        if rec:
            calls.append(("check", rec))
    return order, info, calls


def precache_vectors(env, qs, Pqr, Pqs):
    texts = []
    for q in qs:
        if q["examples"]:
            continue
        p = Pqr[q["id"]]
        texts += [q["query"]] + p["phrases"] + (p.get("hypothetical_captions") or [])
        if Pqs:
            s = Pqs[q["id"]]
            texts += s["topic"]["phrases"] + (s.get("hypothetical_captions") or [])
            if s["creator_lookup"]["description"]:
                texts.append(s["creator_lookup"]["description"])
    env.S.QV.get([t for t in texts if t])


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 3) if xs else None


def run_config(env, cfg, reps):
    qs = queries()
    written = []
    for rep in reps:
        Pqr = rw("qr-v1", rep)
        Pqs = rw("qs-v1", rep) if cfg in USES_QS else None
        PI = rw("qi-v3", rep) if cfg in INTENT else None
        precache_vectors(env, qs, Pqr, Pqs or rw("qs-v1", rep))
        spent0 = L.ledger()
        out, per = {}, {}
        lat_local, lat_total, lat_all = [], [], []
        agg = collections.Counter()
        cost = collections.Counter()
        for q in qs:
            T = Timer()
            t = time.time()
            order, info, calls = search_one(env, cfg, q, Pqr, Pqs, PI, T)
            local = time.time() - t - T.s
            out[q["id"]] = order[:1000]
            lat_all.append(local)
            if q["examples"]:
                continue
            qid = q["id"]
            rq = Pqr["_meta"]["per_query"][qid] if cfg in USES_QR else None
            rs = Pqs["_meta"]["per_query"][qid] if Pqs else None
            ri = PI["_meta"]["per_query"][qid] if PI else None
            pre = max([r["seconds"] for r in (rq, rs, ri) if r] or [0.0])  # parallel query-plan calls
            post = sum(rec["seconds"] for _, rec in calls)  # sequential, after the first search
            lat_local.append(local)
            lat_total.append(local + pre + post)
            for name, r in (("qr-v1", rq), ("qs-v1", rs), ("qi-v3", ri)):
                if r:
                    cost[name] += r["cost_usd"]
            for name, rec in calls:
                cost[name] += rec["cost_usd"]
                agg[f"{name}_calls"] += 1
                agg[f"{name}_calls_new"] += not rec["cached"]
            agg["creator_lookup"] += bool(info.get("creator_lookup"))
            agg["picks_made"] += bool((info.get("pick") or {}).get("picks"))
            agg["facet_active"] += bool((info.get("facets") or {}).get("active"))
            agg["checked"] += bool((info.get("check") or {}).get("checked"))
            agg["intent_active"] += (info.get("intent") or {}).get("mode", "unchanged") != "unchanged"
            per[qid] = {**info, "latency_total_s": round(lat_total[-1], 3), "latency_local_s": round(local, 4),
                        "llm_calls": [n for n, _ in calls]}
        n_typed = len(lat_total)
        new_spend = sum(r["cost_usd"] for r in L.ledger()[len(spent0):])
        meta = {"config": cfg, "round": "5", "repeat": rep, "splits": ALT["splits"] or ["dev", "yt_holdout"],
                "n_searches": len(qs), "n_typed": n_typed,
                "plan": "qs-v1 (c5_rewrite)" if cfg in PLAN_F1 else "qr-v1",
                "rewrites": {"qr-v1": f"qr-v1_gpt-5-nano_r{rep}" if cfg in USES_QR else None,
                             "qs-v1": f"qs-v1_gpt-5-nano_r{rep}" if cfg in USES_QS else None,
                             "qi-v3": f"qi-v3_gpt-5-nano_r{rep}" if cfg in INTENT else None},
                "embedding": "text-embedding-3-small@512", "hyde_alpha": L.HYDE_ALPHA,
                "te": None if not te_for(cfg, env) else
                {"rule": "rankable only if own text is not a real title (F0)" if cfg in TE_F0 else "all rows (D1)",
                 "rankable": len(te_for(cfg, env).codes)},
                "fusion": "coverage-fair RRF k=60" if (te_for(cfg, env) or cfg in CREATOR) else "RRF k=60",
                "components": {"creator": cfg in CREATOR, "pick": cfg in PICK, "facets": cfg in FACET,
                               "check": cfg in CHECK, "intent_e1": cfg in INTENT},
                "counts": dict(agg),
                "index_build_s": round(env.build_s, 1), "creator_profiles_build_s": round(env.creator_build_s, 1),
                "n_creators": len(env.CR.keys),
                "query_local_p50_s": pct(lat_all, 50), "query_local_p95_s": pct(lat_all, 95),
                "typed_local_p50_s": pct(lat_local, 50), "typed_local_p95_s": pct(lat_local, 95),
                "typed_total_p50_s": pct(lat_total, 50), "typed_total_p95_s": pct(lat_total, 95),
                "latency_model": "local search + max(query-plan calls, run in parallel) + pick + checker "
                                 "(sequential); LLM seconds are the original (uncached) call times",
                "cost_usd_by_call": {k: round(v, 6) for k, v in cost.items()},
                "cost_usd": round(sum(cost.values()), 6),
                "cost_per_1k_searches_usd": round(1000 * sum(cost.values()) / max(n_typed, 1), 4),
                "new_spend_this_run_usd": round(new_spend, 6),
                "per_search": per}
        if ALT["queries"]:
            meta["queries_file"] = os.path.basename(ALT["queries"])
            meta["rewrites_dir"] = ALT["rewrites"]
        outdir = ALT["outdir"] or (os.path.join(DATA, "tmp", "r5_checks") if cfg.endswith("chk")
                                   else os.path.join(DATA, "runs", "r5"))
        path = write_run(os.path.join(outdir, f"{cfg}{ALT['suffix']}_r{rep}.json"), f"c5:{cfg}", L.CodeIds("oai512"),
                         out, meta)
        written.append(path)
        print(f"wrote {os.path.basename(path)}: {len(out)} searches; local p50 {meta['typed_local_p50_s']} s; "
              f"total p50 {meta['typed_total_p50_s']} / p95 {meta['typed_total_p95_s']} s; "
              f"cost/1k ${meta['cost_per_1k_searches_usd']}; new spend ${new_spend:.4f}; {json.dumps(dict(agg))}",
              flush=True)
    return written


def stats():
    """Slot fire counts per search kind over the 3 qs-v1 repeats (aggregates only)."""
    qs = {q["id"]: q for q in queries() if not q["examples"]}
    tab = collections.defaultdict(collections.Counter)
    n = collections.Counter()
    for rep in (1, 2, 3):
        P = rw("qs-v1", rep)
        for qid, q in qs.items():
            p = P[qid]
            f = RW.slots_fired(p)
            raw = p["unguarded"]
            f["format_unguarded"] = raw["format"]["value"] is not None
            f["tone_unguarded"] = bool(raw["tone"]["values"])
            for k in q["kinds"]:
                n[k] += 1
                for s, v in f.items():
                    tab[k][s] += int(v)
            n["ALL"] += 1
            for s, v in f.items():
                tab["ALL"][s] += int(v)
    cols = ["topic", "topic_expansions", "format_unguarded", "format", "tone_unguarded", "tone", "creator_lookup",
            "request_words", "behaviour_time"]
    print("kind (search x repeat cells) | " + " | ".join(cols))
    for k in sorted(n, key=lambda x: (x != "ALL", -n[x])):
        print(f"{k} ({n[k]}) | " + " | ".join(str(tab[k][c]) for c in cols))
    vals = collections.Counter()
    for rep in (1, 2, 3):
        P = rw("qs-v1", rep)
        for qid in qs:
            vals["format:" + str(P[qid]["format"]["value"])] += 1
            for v in P[qid]["tone"]["values"]:
                vals["tone:" + v] += 1
    print(json.dumps(dict(sorted(vals.items()))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--queries", default=None)
    ap.add_argument("--rewrites-dir", default=None)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--splits", default=None)
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    ALT.update({"queries": a.queries, "rewrites": a.rewrites_dir, "outdir": a.outdir, "suffix": a.suffix,
                "splits": a.splits.split(",") if a.splits else None})
    if a.stats:
        stats()
        return
    t0 = time.time()
    env = Env(L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    print(f"index + te + creators built in {env.build_s:.1f} s (creators {env.creator_build_s:.1f} s, "
          f"{len(env.CR.keys)} creators, te rankable all {len(env.E_all.codes)} / f0 {len(env.E_f0.codes)})",
          flush=True)
    reps = [int(x) for x in a.reps.split(",")]
    for cfg in a.configs.split(","):
        assert cfg in CONFIGS, cfg
        run_config(env, cfg, reps)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
