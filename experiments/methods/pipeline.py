"""PROTOTYPE ONLY - the honest-base search (baseline.py hybrid_prf + real LLM rewrite) as one function with
explicit options, so free one-variable experiments can be switched on from the command line.

Default options reproduce `baseline.py --variant hybrid_prf --parses <rewrite file>` exactly
(verified against data/runs/e1_rewrite_r{1,2,3}.json).

Typed searches: phrases = [query] + rewrite phrases -> dense (max over phrases, info-ok items only,
+ Rocchio PRF from top 5) ; BM25 over 'full' with [query] + rewrite keywords ; RRF (k=60).
More-like-this (searches with `examples`): centroid dense + BM25 on the examples' text -> RRF (as the base).

Options (--opt name=value; defaults reproduce the base):
  prf=dense|fused|none      feedback set for Rocchio: dense top 5 (base), top 5 info-ok of the first-pass fused list
  dense_fusion=max|rrf      combine phrase vectors by max score (base) or by RRF of per-phrase rankings
  rm3=0|1                   BM25 feedback from the fused top `rm3_docs`: `rm3_terms` unigram terms at `rm3_weight`
  hyde=0|1                  extra dense vector normalize((1-hyde_alpha)*q + hyde_alpha*mean(caption vectors))
  prior=0.0                 final score = RRF + prior * max(0, importance - prior_floor)
  creator=0|1               third RRF list (weight creator_weight): same-creator items of the fused top creator_seeds
  union_phrases=6, union_keywords=12   caps when several --parses files are given (round-robin union)
  mlt_coll=0|1              more-like-this only: third RRF list of items sharing a collection with the examples
                            (by cosine to the example centroid; items without a vector after, corpus order)
  mlt_plan=<file>           more-like-this only: a plan file {qid: {phrases, keywords}} (methods/mlt_plan.py); the
                            typed pipeline runs on it (query = phrase 1) and its fused list joins RRF as a third list

usage: python experiments/methods/pipeline.py --parses data/runs/rewrites/qr-v1_gpt-5-nano_r1.json \
         [--parses more.json ...] [--opt hyde=1 ...] --out data/runs/x.json [--split dev]
Prints aggregate timing only (no query text, no items).
"""
import argparse
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from common import STOP  # noqa: E402
from corpus import DATA, Corpus, code_of, load_queries, rank, rrf  # noqa: E402

DEFAULTS = {
    "prf": "dense", "prf_k": 5, "dense_fusion": "max", "rrf_k": 60,
    "rm3": 0, "rm3_docs": 10, "rm3_terms": 10, "rm3_weight": 0.5,
    "hyde": 0, "hyde_alpha": 0.7,
    "prior": 0.0, "prior_floor": 0.3,
    "creator": 0, "creator_seeds": 10, "creator_min": 2, "creator_max": 30, "creator_weight": 0.5,
    "union_phrases": 6, "union_keywords": 12,
    "mlt_coll": 0, "mlt_plan": "",
}


def parse_opts(pairs):
    o = dict(DEFAULTS)
    for p in pairs or []:
        k, v = p.split("=", 1)
        if k not in DEFAULTS:
            raise SystemExit(f"unknown option {k}")
        d = DEFAULTS[k]
        o[k] = type(d)(float(v)) if isinstance(d, int) and not isinstance(d, bool) else (float(v) if isinstance(d, float) else v)
    return o


def rrf_scores(lists, weights=None, k=60, depth=1000):
    """Weighted RRF over lists of hashable keys; dict insertion order = corpus.rrf's (same tie order)."""
    sc = {}
    for j, r in enumerate(lists):
        w = 1.0 if weights is None else weights[j]
        for i, n in enumerate(r[:depth]):
            sc[n] = sc.get(n, 0.0) + w / (k + i + 1)
    return sc


def order(sc):
    return [n for n, _ in sorted(sc.items(), key=lambda x: -x[1])]


def union_parse(parses, n_phr, n_kw):
    """Round-robin union of several rewrite parses for one query."""
    def rr(lists, cap, key):
        out, seen = [], set()
        for i in range(max(len(x) for x in lists)):
            for x in lists:
                if i < len(x) and key(x[i]) not in seen and len(out) < cap:
                    seen.add(key(x[i]))
                    out.append(x[i])
        return out
    return {"phrases": rr([p["phrases"] for p in parses], n_phr, lambda s: " ".join(s.lower().split())),
            "keywords": rr([p["keywords"] for p in parses], n_kw, lambda s: s.lower().strip())}


class Search:
    def __init__(self, C, opts):
        self.C, self.o = C, opts
        self.ok = C.info == "ok"
        self._df = None
        self._creators = None

    # ----- BM25 with weighted query terms -----
    def idf(self):
        if self._df is None:
            cv, W = self.C.bm25_index("full")
            df = np.diff(W.tocsc().indptr)
            N = W.shape[0]
            self._idf = np.log(1 + (N - df + 0.5) / (df + 0.5))
            self._df = df
            self._vocab_inv = {i: t for t, i in cv.vocabulary_.items()}
        return self._idf

    def rm3_terms(self, query_str, docs):
        C = self.C
        cv, W = C.bm25_index("full")
        idf = self.idf()
        own = set(re.findall(r"(?u)\b\w\w+\b", query_str.lower()))
        X = cv.transform([C.text(n, "full").lower() for n in docs]).tocsr()
        acc = {}
        for r in range(X.shape[0]):
            cols, vals = X[r].indices, X[r].data
            uni = [(c, v) for c, v in zip(cols, vals) if " " not in self._vocab_inv[c]]
            L = sum(v for _, v in uni) or 1
            for c, v in uni:
                acc[c] = acc.get(c, 0.0) + v / L * idf[c]
        out = []
        for c, _ in sorted(acc.items(), key=lambda x: -x[1]):
            t = self._vocab_inv[c]
            if t in STOP or t in own or t.isdigit():
                continue
            out.append(c)
            if len(out) == self.o["rm3_terms"]:
                break
        return out

    def bm25_weighted(self, query_str, extra_cols, w):
        cv, W = self.C.bm25_index("full")
        q = cv.transform([query_str.lower()])
        q.data[:] = 1
        q = q.toarray().ravel().astype(np.float32)
        for c in extra_cols:
            if q[c] == 0:
                q[c] = w
        return np.asarray(W @ q).ravel()

    # ----- creators -----
    def creators(self):
        if self._creators is None:
            C = self.C
            by = {}
            for k, it in C.items.items():
                h = (it["platform_data"].get("owner_handle") or "").strip().lower()
                if h:
                    by.setdefault(h, []).append(k)
            self._creators = by
        return self._creators

    def item_ok_for(self, it, filters):
        if filters.get("before") and not ((it.get("first_seen_at") or "9999") < filters["before"]):
            return False
        if filters.get("kinds") and not (set(it["interaction_kinds"]) & set(filters["kinds"])):
            return False
        return True

    # ----- one search -> list of content codes -----
    def run(self, q, parse):
        C, o = self.C, self.o
        m = C.mask(q["filters"])
        if q["examples"]:
            ex = [C.by_code[c] for c in q["examples"] if c in C.by_code]
            cen = C.V[ex].mean(0)
            cen /= np.linalg.norm(cen)
            d = rank(C.V @ cen, m & self.ok, ex)
            b = rank(C.bm25(" ".join(C.text(n, "full") for n in ex), "full"), m, ex)
            if not (o["mlt_coll"] or o["mlt_plan"]):
                return [C.code[n] for n in rrf(d, b)]
            lists = [[C.code[n] for n in d], [C.code[n] for n in b]]
            if o["mlt_coll"]:
                lists.append(self.same_collection(q, ex, cen, m))
            if o["mlt_plan"]:
                plan = self._plans().get(q["id"])
                if plan and plan.get("phrases"):
                    exc = set(q["examples"])
                    q2 = {"id": q["id"], "query": plan["phrases"][0], "filters": q["filters"], "examples": []}
                    p2 = {"phrases": plan["phrases"][1:], "keywords": plan.get("keywords") or []}
                    lists.append([c for c in self.run(q2, p2) if c not in exc])
            return order(rrf_scores(lists, k=o["rrf_k"]))
        mo = m & self.ok
        phrases = [q["query"]] + parse["phrases"]
        Qv = C.qvecs(phrases)
        if o["hyde"]:
            caps = parse.get("hypothetical_captions") or []
            if caps:
                from sklearn.preprocessing import normalize
                H = normalize(np.array(list(C.model().embed(caps)), dtype=np.float32))
                a = o["hyde_alpha"]
                v = (1 - a) * Qv[0] + a * H.mean(0)
                Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
        bq = " ".join([q["query"]] + parse["keywords"])
        b = rank(C.bm25(bq, "full"), m)
        S = C.V @ Qv.T  # rows x phrases
        k = o["rrf_k"]

        def dense_list(extra_vec=None):
            if o["dense_fusion"] == "max":
                s = S.max(axis=1)
                if extra_vec is not None:
                    s = np.maximum(s, C.V @ extra_vec)
                return rank(s, mo)
            lists = [rank(S[:, j], mo) for j in range(S.shape[1])]
            if extra_vec is not None:
                lists.append(rank(C.V @ extra_vec, mo))
            return rrf(*lists, k=k)

        if o["prf"] == "none":
            d = dense_list()
        else:
            if o["prf"] == "dense" and o["dense_fusion"] == "max":
                s0 = S.max(axis=1)
                top = np.argsort(-np.where(mo, s0, -9))[:o["prf_k"]]
            elif o["prf"] == "dense":
                top = np.array(dense_list()[:o["prf_k"]])
            elif o["prf"] == "fused":
                f0 = rrf(dense_list(), b, k=k)
                top = np.array([n for n in f0 if self.ok[n]][:o["prf_k"]])
            else:
                raise SystemExit("prf must be dense|fused|none")
            q2 = Qv.mean(0) + C.V[top].mean(0)
            q2 /= np.linalg.norm(q2)
            d = dense_list(q2)

        fused = order(rrf_scores([d, b], k=k))
        if o["rm3"]:
            docs = fused[:o["rm3_docs"]]
            cols = self.rm3_terms(bq, docs)
            b = rank(self.bm25_weighted(bq, cols, o["rm3_weight"]), m)
            fused = order(rrf_scores([d, b], k=k))

        # from here on, work in content codes (creator expansion can add items that have no vector)
        lists = [[C.code[n] for n in d], [C.code[n] for n in b]]
        weights = [1.0, 1.0]
        if o["creator"]:
            seeds = [C.code[n] for n in fused[:o["creator_seeds"]]]
            seedset = set(seeds)
            pos = {C.code[n]: i for i, n in enumerate(fused)}
            cre = self.creators()
            exp, seen = [], set()
            for sc in seeds:
                it = C.items[C.ids[C.by_code[sc]]]
                h = (it["platform_data"].get("owner_handle") or "").strip().lower()
                group = cre.get(h, [])
                if not h or not (o["creator_min"] <= len(group) <= o["creator_max"]):
                    continue
                cand = []
                for j, iid in enumerate(group):
                    ci = code_of(C.items[iid])
                    if ci in seedset or ci in seen or not self.item_ok_for(C.items[iid], q["filters"]):
                        continue
                    cand.append((pos.get(ci, 10 ** 9), j, ci))
                for _, _, ci in sorted(cand):
                    seen.add(ci)
                    exp.append(ci)
            lists.append(exp)
            weights.append(o["creator_weight"])
        sc = rrf_scores(lists, weights, k=k)
        if o["prior"]:
            byc = self._imp_by_code()
            for c in sc:
                sc[c] += o["prior"] * max(0.0, byc.get(c, 0.0) - o["prior_floor"])
        return order(sc)

    def same_collection(self, q, ex, cen, m):
        """Items sharing >=1 collection with the examples (examples excluded, filters applied, no info gate):
        those with a vector by cosine to `cen`, then those without a vector in corpus (items.jsonl) order."""
        C = self.C
        excodes = set(q["examples"])
        cols = set()
        for iid in C.items:
            it = C.items[iid]
            if code_of(it) in excodes:
                cols |= set(it["platform_data"].get("collections") or [])
        if not cols:
            return []
        with_v, without_v = [], []
        for iid, it in C.items.items():
            c = code_of(it)
            if c in excodes or not (cols & set(it["platform_data"].get("collections") or [])):
                continue
            n = C.by_code.get(c)
            if n is None:
                if self.item_ok_for(it, q["filters"]):
                    without_v.append(c)
            elif m[n]:
                with_v.append((-float(C.V[n] @ cen), len(with_v), c))
        return [c for _, _, c in sorted(with_v)] + without_v

    def _plans(self):
        if not hasattr(self, "_plan_cache"):
            P = json.load(open(self.o["mlt_plan"]))
            self._plan_cache = {k: v for k, v in P.items() if not k.startswith("_")}
        return self._plan_cache

    def _imp_by_code(self):
        if not hasattr(self, "_imp"):
            self._imp = {code_of(it): float(it.get("importance") or 0.0) for it in self.C.items.values()}
        return self._imp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emb", default="bge_full")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--parses", action="append", required=True, help="rewrite file; repeat for a union")
    ap.add_argument("--opt", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    o = parse_opts(a.opt)
    t0 = time.time()
    C = Corpus(a.emb)
    Ps = [json.load(open(p)) for p in a.parses]
    S = Search(C, o)
    out, lat = {}, []
    qs = load_queries(a.split)
    for q in qs:
        t = time.time()
        if q["examples"]:
            parse = None
        elif len(Ps) == 1:
            parse = Ps[0][q["id"]]
        else:
            parse = union_parse([P[q["id"]] for P in Ps], o["union_phrases"], o["union_keywords"])
        out[q["id"]] = S.run(q, parse)[:1000]
        lat.append(time.time() - t)
    wall = time.time() - t0
    changed = {k: v for k, v in o.items() if v != DEFAULTS[k]}
    meta = {"wall_s": round(wall, 1), "query_p50_s": round(float(np.median(lat)), 3), "options": o,
            "options_changed": changed, "rewrite": [os.path.basename(p) for p in a.parses]}
    # rewrite cost/latency for the typed queries in this run (parallel calls when several files: latency = slowest)
    RWs = [P.get("_meta", {}) for P in Ps]
    if all(RWs):
        typed = [q["id"] for q in qs if not q["examples"]]
        per = [[RW["per_query"][k] for RW in RWs] for k in typed if all(k in RW.get("per_query", {}) for RW in RWs)]
        meta.update({"cost_usd": round(sum(v["cost_usd"] for row in per for v in row), 6), "rewrite_n": len(per),
                     "rewrite_calls_per_query": len(Ps),
                     "rewrite_p50_s": round(float(np.median([max(v["seconds"] for v in row) for row in per])), 3),
                     "prompt_version": RWs[0].get("prompt_version"), "model": RWs[0].get("model"),
                     "reasoning_effort": RWs[0].get("reasoning_effort")})
        meta["query_plus_rewrite_p50_s"] = round(meta["query_p50_s"] + meta["rewrite_p50_s"], 3)
    else:
        meta["cost_usd"] = 0
    if o["mlt_coll"] or o["mlt_plan"]:
        mlt_lat = [s for q, s in zip(qs, lat) if q["examples"]]
        meta["mlt_query_p50_s"] = round(float(np.median(mlt_lat)), 3) if mlt_lat else None
    if o["mlt_plan"]:
        PM = json.load(open(o["mlt_plan"])).get("_meta", {})
        pq = [PM.get("per_query", {}).get(q["id"]) for q in qs if q["examples"]]
        pq = [v for v in pq if v]
        meta.update({"mlt_plan_n": len(pq), "mlt_plan_cost_usd": round(sum(v["cost_usd"] for v in pq), 6),
                     "mlt_plan_p50_s": round(float(np.median([v["seconds"] for v in pq])), 3) if pq else None,
                     "mlt_plan_model": PM.get("model"), "mlt_plan_prompt_version": PM.get("prompt_version")})
        meta["cost_usd"] = round(meta["cost_usd"] + meta["mlt_plan_cost_usd"], 6)
    tag =",".join(f"{k}={v}" for k, v in sorted(changed.items())) or "default"
    method = a.name or f"pipeline:{tag}+{RWs[0].get('prompt_version')}_{RWs[0].get('model')}x{len(Ps)}"
    run = {"method": method, "embedding": C.emb_name, "meta": meta, "queries": out}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(run, open(a.out, "w"))
    print(f"wrote {a.out}: {len(out)} queries, {len(out) / wall:.2f} queries/s, wall {wall:.1f} s, "
          f"query p50 {meta['query_p50_s']} s")


if __name__ == "__main__":
    main()
