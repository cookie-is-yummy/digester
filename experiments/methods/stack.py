"""PROTOTYPE ONLY - base B2 (experiment 9b's main arm) as one function with one-variable options on top.

B2 = honest base + enrichment lists (e9_enrich_search.py, arms=both, full index te-v1c_gemini-3.1-flash-lite):
  typed: phrases = [query] + rewrite phrases -> bge-small caption dense (max over phrases, info-ok items, Rocchio
         PRF top 5) ; BM25 'full' (query + rewrite keywords) ; enrichment BM25 (same BM25 query) ; enrichment
         dense (max over the phrase vectors, no PRF, no gate) -> RRF k=60 in content-code space.
  more-like-this: caption centroid dense (info-ok) ; BM25 on the examples' 'full' text ; enrichment BM25 on the
         examples' enrichment text ; centroid of the examples' enrichment vectors -> RRF.
With every option off this reproduces data/runs/e9b_full_r{k}.json exactly (checked with --verify).

Options (--opt name=value; one experiment = one option):
  hyde=0|1, hyde_alpha=0.7   exp 20: extra query vector normalize((1-a)*q + a*mean(caption vectors)), q = raw-query
                             vector, captions = the rewrite's cached hypothetical_captions (bge plain `embed`); it
                             joins the phrase set of BOTH dense lists (caption: max + PRF mean; enrichment: max)
  gate_kind=0|1              exp 19: items failing the caption information gate join the caption dense leg (typed
                             dense + its PRF feedback set, and the MLT centroid dense) when their enrichment `kind`
                             is known (not '', 'unknown', 'other'; last ok enrichment row per item)
  mlt_plan=<file>            exp 18: MLT only; plan {qid: {phrases, keywords}} -> the B2 typed pipeline runs on it
                             (query = phrase 1, phrases 2.., keywords; examples excluded) and its fused list joins
                             the B2 MLT lists as one more RRF list
  The rewrite set (exp 17: qr-v2) is chosen with --parses.
  The enrichment index (exp 23: te-v2bh hybrid) is chosen with --enrich (default te-v1c, i.e. B2/B3).

usage: python experiments/methods/stack.py --parses data/runs/rewrites/qr-v1_gpt-5-nano_r1.json \
         [--opt hyde=1] --out data/runs/x.json [--verify data/runs/e9b_full_r1.json]
Prints aggregate timing only (no query text, no items).
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
from corpus import DATA, Corpus, code_of, load_queries, rank, rrf  # noqa: E402
from e9_enrich_search import EnrichIndex  # noqa: E402

ENRICH = "te-v1c_gemini-3.1-flash-lite"
DEFAULTS = {"hyde": 0, "hyde_alpha": 0.7, "gate_kind": 0, "mlt_plan": ""}


def parse_opts(pairs):
    o = dict(DEFAULTS)
    for p in pairs or []:
        k, v = p.split("=", 1)
        if k not in DEFAULTS:
            raise SystemExit(f"unknown option {k}")
        d = DEFAULTS[k]
        o[k] = int(float(v)) if isinstance(d, int) else (float(v) if isinstance(d, float) else v)
    return o


def enrich_kinds(enrich, codes):
    """Last ok enrichment row's kind per code (same row choice as e9_enrich_search.build)."""
    kinds = {}
    for line in open(os.path.join(DATA, "enrich", f"{enrich}.jsonl")):
        r = json.loads(line)
        if r["ok"]:
            kinds[r["code"]] = r.get("kind") or ""
    return {c: kinds.get(c, "") for c in codes}


class Stack:
    def __init__(self, C, E, opts):
        self.C, self.E, self.o = C, E, opts
        self.ok = C.info == "ok"
        self.n_gate_added = 0
        if opts["gate_kind"]:
            kinds = enrich_kinds(ENRICH, set(E.codes))
            known = np.array([kinds.get(c, "") not in ("", "unknown", "other") for c in C.code])
            self.n_gate_added = int((known & ~self.ok).sum())
            self.ok = self.ok | known
        self._plan = None

    def typed(self, q, parse):
        C, E, o = self.C, self.E, self.o
        m = C.mask(q["filters"])
        mo = m & self.ok
        Qv = C.qvecs([q["query"]] + parse["phrases"])
        if o["hyde"]:
            caps = parse.get("hypothetical_captions") or []
            if caps:
                H = normalize(np.array(list(C.model().embed(caps)), dtype=np.float32))
                a = o["hyde_alpha"]
                v = (1 - a) * Qv[0] + a * H.mean(0)
                Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
        s = (C.V @ Qv.T).max(axis=1)
        top = np.argsort(-np.where(mo, s, -9))[:5]
        q2 = Qv.mean(0) + C.V[top].mean(0)
        q2 /= np.linalg.norm(q2)
        s = np.maximum(s, C.V @ q2)
        bq = " ".join([q["query"]] + parse["keywords"])
        em = E.mask(q["filters"])
        lists = [[C.code[n] for n in rank(s, mo)],
                 [C.code[n] for n in rank(C.bm25(bq, "full"), m)],
                 E.bm25(bq, em),
                 E.dense(Qv, em)]
        return rrf(*lists)

    def mlt(self, q):
        C, E, o = self.C, self.E, self.o
        m = C.mask(q["filters"])
        ex = [C.by_code[c] for c in q["examples"] if c in C.by_code]
        cen = C.V[ex].mean(0)
        cen /= np.linalg.norm(cen)
        lists = [[C.code[n] for n in rank(C.V @ cen, m & self.ok, ex)],
                 [C.code[n] for n in rank(C.bm25(" ".join(C.text(n, "full") for n in ex), "full"), m, ex)]]
        em = E.mask(q["filters"])
        exe = [c for c in q["examples"] if c in E.pos]
        if exe:
            lists.append(E.bm25(" ".join(E.text[c] for c in exe), em, exe))
            ce = E.V[[E.pos[c] for c in exe]].mean(0, keepdims=True)
            lists.append(E.dense(normalize(ce), em, exe))
        if o["mlt_plan"]:
            plan = self.plans().get(q["id"])
            if plan and plan.get("phrases"):
                exc = set(q["examples"])
                q2 = {"id": q["id"], "query": plan["phrases"][0], "filters": q["filters"], "examples": []}
                p2 = {"phrases": plan["phrases"][1:], "keywords": plan.get("keywords") or []}
                lists.append([c for c in self.typed(q2, p2) if c not in exc])
        return rrf(*lists)

    def plans(self):
        if self._plan is None:
            P = json.load(open(self.o["mlt_plan"]))
            self._plan = {k: v for k, v in P.items() if not k.startswith("_")}
        return self._plan

    def run(self, q, parse):
        return self.mlt(q) if q["examples"] else self.typed(q, parse)


def main():
    global ENRICH
    ap = argparse.ArgumentParser()
    ap.add_argument("--parses", required=True)
    ap.add_argument("--opt", action="append", default=[])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--enrich", default=ENRICH, help="enrichment index name (text_<name>.json, emb_<name>/)")
    ap.add_argument("--out")
    ap.add_argument("--verify", help="run file to compare with (all rankings identical, 1000 deep)")
    a = ap.parse_args()
    ENRICH = a.enrich
    o = parse_opts(a.opt)
    t0 = time.time()
    C = Corpus("bge_full")
    by_code = {code_of(it): it for it in C.items.values()}
    E = EnrichIndex(ENRICH, by_code)
    S = Stack(C, E, o)
    P = json.load(open(a.parses))
    RW = P.get("_meta", {})
    qs = load_queries(a.split)
    out, lat, n_extra = {}, [], []
    for q in qs:
        t = time.time()
        fused = S.run(q, None if q["examples"] else P[q["id"]])
        out[q["id"]] = fused[:1000]
        n_extra.append(sum(1 for c in fused[:100] if c not in C.by_code))
        lat.append(time.time() - t)
    wall = time.time() - t0

    if a.verify:
        ref = json.load(open(a.verify))["queries"]
        same = sum(1 for k in out if out[k] == ref.get(k))
        print(f"verify vs {os.path.basename(a.verify)}: {same}/{len(out)} rankings identical (1000 deep)")

    changed = {k: v for k, v in o.items() if v != DEFAULTS[k]}
    typed_lat = [s for q, s in zip(qs, lat) if not q["examples"]]
    mlt_lat = [s for q, s in zip(qs, lat) if q["examples"]]
    meta = {"base": "B2 = e9b_full (honest base + enrichment BM25 + enrichment dense, full index)",
            "wall_s": round(wall, 1), "query_p50_s": round(float(np.median(lat)), 3),
            "typed_query_p50_s": round(float(np.median(typed_lat)), 3) if typed_lat else None,
            "mlt_query_p50_s": round(float(np.median(mlt_lat)), 3) if mlt_lat else None,
            "options": o, "options_changed": changed, "rewrite": os.path.basename(a.parses), "enrich": ENRICH,
            "enriched_items": len(E.codes), "no_caption_vector_items_in_top100_mean": round(float(np.mean(n_extra)), 2),
            "prompt_version": RW.get("prompt_version"), "model": RW.get("model"),
            "reasoning_effort": RW.get("reasoning_effort")}
    pq = [RW["per_query"][q["id"]] for q in qs if not q["examples"] and q["id"] in RW.get("per_query", {})]
    meta.update({"cost_usd": round(sum(v["cost_usd"] for v in pq), 6), "rewrite_n": len(pq),
                 "rewrite_cost_per_1k_searches_usd": round(1000 * float(np.mean([v["cost_usd"] for v in pq])), 4)
                 if pq else None,
                 "rewrite_p50_s": round(float(np.median([v["seconds"] for v in pq])), 3) if pq else None})
    if meta["rewrite_p50_s"] is not None:
        meta["typed_query_plus_rewrite_p50_s"] = round(meta["typed_query_p50_s"] + meta["rewrite_p50_s"], 3)
    if o["gate_kind"]:
        meta["gate_items_added"] = S.n_gate_added
    if o["mlt_plan"]:
        PM = json.load(open(o["mlt_plan"])).get("_meta", {})
        pp = [PM.get("per_query", {}).get(q["id"]) for q in qs if q["examples"]]
        pp = [v for v in pp if v]
        meta.update({"mlt_plan_n": len(pp), "mlt_plan_cost_usd": round(sum(v["cost_usd"] for v in pp), 6),
                     "mlt_plan_cost_per_1k_mlt_searches_usd": round(1000 * float(np.mean([v["cost_usd"] for v in pp])), 4)
                     if pp else None,
                     "mlt_plan_p50_s": round(float(np.median([v["seconds"] for v in pp])), 3) if pp else None,
                     "mlt_plan_model": PM.get("model"), "mlt_plan_prompt_version": PM.get("prompt_version")})
        meta["cost_usd"] = round(meta["cost_usd"] + meta["mlt_plan_cost_usd"], 6)
    tag = ",".join(f"{k}={os.path.basename(str(v))}" for k, v in sorted(changed.items())) or "default"
    method = f"stack_b2:{tag}+{RW.get('prompt_version')}_{RW.get('model')}_r{RW.get('repeat')}+{ENRICH}"
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump({"method": method, "embedding": C.emb_name, "meta": meta, "queries": out}, open(a.out, "w"))
    print(f"wrote {a.out}: {len(out)} queries, {len(out) / wall:.2f} queries/s, wall {wall:.1f} s, "
          f"query p50 {meta['query_p50_s']} s (typed {meta['typed_query_p50_s']}, mlt {meta['mlt_query_p50_s']})")


if __name__ == "__main__":
    main()
