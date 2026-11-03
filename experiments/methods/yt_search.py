"""PROTOTYPE ONLY - round 3 (YouTube) search runs: B3 recipe ported to YouTube, plus enrichment lists and intent.

B3 (round-1 finalist) per typed search:
  phrases = [query] + rewrite phrases (+ HyDE vector: normalize(0.3*q + 0.7*mean(hypothetical captions)))
  -> dense over the view's vectors (max over phrase vectors; Rocchio PRF from the top 5)
  -> BM25 over the view text (query + rewrite keywords)
  -> per enrichment index: BM25 over its text (same BM25 query) + dense (max over the same phrase vectors)
  -> RRF k=60 in content-code space (items without a view vector are rankable through enrichment lists).
More-like-this: centroid of the examples' view vectors (outside-library examples: their given title, embedded) ;
  BM25 on the examples' text ; per enrichment index BM25 on the examples' enrichment text + centroid of their
  enrichment vectors. Examples are excluded from results.
YouTube port differences (recorded in results/r3-methods.md): OpenAI text-embedding-3-small 512 d instead of
bge-small; the Instagram caption information gate is not used (titles are short; every titled item is in the
dense leg); query vectors and HyDE vectors are cached (corpus/emb/oai512_queries).

Configs (--config):
  a0        allowed view, no enrichment lists
  a1        a0 + te-v1c allowed (tier-1 text pass over gated items)
  a2_gated  a1 + tv-v1 video pass, gated arm (+ more-like-this example videos)
  a2_random a1 + tv-v1 video pass, random arm (+ the same example videos)
  ref_r0    RESEARCH ONLY: API view, no enrichment lists
  ref_r1    RESEARCH ONLY: ref_r0 + te-v1c over API text (same gate)
  --intent full|filters  A3 on top of a config: the qi-v1 intent (yt_intent.apply) re-filters/re-orders the fused
           list using the user's interactions and durations. full = qi-v1's own text plan + intent; filters =
           qr-v1 text plan (same as the base) + qi-v1 intent, so only the intent differs from the base run.
Writes data/yt/runs/<name>_r<k>.json with lib/corpus.py's run format (+ "moments" for moment searches when a
video index is present). Prints aggregate timing only.
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
import yt_intent as I
import yt_lib as Y
from corpus import DATA, rrf

TE_A = "te-v1c_allowed_gemini-3.1-flash-lite"
TE_R = "ref_te-v1c_api_gemini-3.1-flash-lite"
TV = "tv-v1_gemini-3.1-flash-lite"
CONFIGS = {"a0": ("allowed", []), "a1": ("allowed", [TE_A]), "a2_gated": ("allowed", [TE_A, TV + ":gated"]),
           "a2_random": ("allowed", [TE_A, TV + ":random"]), "ref_r0": ("api", []), "ref_r1": ("api", [TE_R])}
HYDE_ALPHA = 0.7
RUNS = os.path.join(DATA, "runs")


def ledger():
    p = os.path.join(DATA, "ai_runs.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


class EnrichIdx:
    """One enrichment index (text_<name>.json + emb_<name>/), optionally restricted to a code subset (video arm).
    `ex_text/ex_vec` also hold query-side example rows outside the subset (e.g. outside-library examples)."""

    def __init__(self, name, subset=None, example_fallback=None):
        self.name = name
        text = json.load(open(os.path.join(DATA, "enrich", f"text_{name}.json")))
        ids, V = Y.load_store(f"emb_{name}")
        keep = [k for k, c in enumerate(ids) if subset is None or c in subset]
        self.codes = [ids[k] for k in keep]
        self.V = V[keep]
        self.text = {c: text[c] for c in self.codes}
        self.bm = Y.BM25(self.text)
        self.ex_text = dict(self.text)
        self.ex_vec = {c: self.V[k] for k, c in enumerate(self.codes)}
        if example_fallback:  # (name) of another index whose rows may serve as query-side example rows
            t2 = json.load(open(os.path.join(DATA, "enrich", f"text_{example_fallback}.json")))
            i2, V2 = Y.load_store(f"emb_{example_fallback}")
            for k, c in enumerate(i2):
                if c not in self.ex_text and c in OUTSIDE:
                    self.ex_text[c], self.ex_vec[c] = t2[c], V2[k]

    def bm25(self, q, keep, exclude=()):
        return self.bm.rank(q, exclude=exclude, keep=keep)

    def dense(self, Qv, keep, exclude=()):
        s = (self.V @ Qv.T).max(axis=1)
        order = np.argsort(-s)
        ex = set(exclude)
        return [self.codes[n] for n in order if self.codes[n] not in ex and keep(self.codes[n])][:1000]


OUTSIDE = Y.outside_examples()


class Searcher:
    def __init__(self, cfg):
        view, enr = CONFIGS[cfg]
        self.D = D = Y.YT()
        self.view = view
        api = Y.load_api_rows() if view == "api" else None
        store = "oai512_allowed" if view == "allowed" else "ref_oai512_api"
        ids, self.V = Y.load_store(store)
        self.vpos = np.array([D.id_pos[i] for i in ids])  # vector row -> item position
        self.vcodes = [D.codes[n] for n in self.vpos]
        self.row_of = {c: k for k, c in enumerate(self.vcodes)}
        ext_ids, ext_V = Y.load_store("oai512_allowed_ext")
        self.ext_vec = {c: ext_V[k] for k, c in enumerate(ext_ids)}
        self.text = {}
        for n in range(len(D.items)):
            t = D.api_text(n, api.get(D.codes[n])) if api is not None else D.allowed_text(n)
            if t:
                self.text[D.codes[n]] = t
        self.bm = Y.BM25(self.text)
        self.E = []
        arms = None
        for e in enr:
            if ":" in e:
                name, arm = e.split(":")
                if arms is None:
                    arms = json.load(open(os.path.join(DATA, "video", "arms.json")))
                sub = set(arms[arm]) | set(arms["examples"])
                self.E.append(EnrichIdx(name, sub))
            else:
                self.E.append(EnrichIdx(e, example_fallback=TE_A if e == TE_R else None))
        self.QV = Y.QueryVecs()
        self.segs = None
        if any(e.name == TV for e in self.E):
            self.tv_idx = [e for e in self.E if e.name == TV][0]
            self._load_segments()

    # ---------- filters (method-side query filters; all empty in this eval) ----------
    def keep_fn(self, filters):
        if not filters:
            return lambda c: True
        D = self.D

        def keep(c):
            n = D.pos.get(c)
            if n is None:
                return False
            if filters.get("before") and not D.first[n] < filters["before"]:
                return False
            if filters.get("kinds") and not set(D.items[n]["interaction_kinds"]) & set(filters["kinds"]):
                return False
            return True
        return keep

    def typed(self, q, parse):
        keep = self.keep_fn(q.get("filters"))
        Qv = self.QV.get([q["query"]] + parse["phrases"])
        caps = parse.get("hypothetical_captions") or []
        if caps:
            H = self.QV.get(caps)
            v = (1 - HYDE_ALPHA) * Qv[0] + HYDE_ALPHA * H.mean(0)
            Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
        s = (self.V @ Qv.T).max(axis=1)
        top = np.argsort(-s)[:5]
        q2 = Qv.mean(0) + self.V[top].mean(0)
        q2 /= np.linalg.norm(q2)
        s = np.maximum(s, self.V @ q2)
        order = np.argsort(-s)
        dense = [self.vcodes[n] for n in order[:3000] if keep(self.vcodes[n])][:1000]
        bq = " ".join([q["query"]] + parse["keywords"])
        lists = [dense, self.bm.rank(bq, keep=keep)]
        for E in self.E:
            lists += [E.bm25(bq, keep), E.dense(Qv, keep)]
        return rrf(*lists), Qv, bq

    def mlt(self, q):
        keep = self.keep_fn(q.get("filters"))
        ex = q["examples"]
        vecs = [self.V[self.row_of[c]] for c in ex if c in self.row_of] + \
               [self.ext_vec[c] for c in ex if c not in self.row_of and c in self.ext_vec]
        lists = []
        if vecs:
            cen = np.mean(vecs, 0)
            cen /= np.linalg.norm(cen)
            order = np.argsort(-(self.V @ cen))
            lists.append([self.vcodes[n] for n in order[:3000] if self.vcodes[n] not in ex and keep(self.vcodes[n])][:1000])
        etext = " ".join(self.text.get(c) or OUTSIDE.get(c, "") for c in ex)
        lists.append(self.bm.rank(etext, exclude=ex, keep=keep))
        for E in self.E:
            exe = [c for c in ex if c in E.ex_text]
            if exe:
                lists.append(E.bm25(" ".join(E.ex_text[c] for c in exe), keep, ex))
                ce = normalize(np.mean([E.ex_vec[c] for c in exe], 0, keepdims=True))
                lists.append(E.dense(ce, keep, ex))
        return rrf(*lists)

    # ---------- moments (video index only) ----------
    def _load_segments(self):
        rows = {}
        for l in open(os.path.join(DATA, "video", f"{TV}.jsonl")):
            r = json.loads(l)
            if r.get("ok") and r["code"] in self.tv_idx.text:
                rows[r["code"]] = r
        self.segs = [(c, s["start_s"], s["end_s"], s["summary"]) for c, r in rows.items() for s in r["segments"]]
        texts = [s[3] for s in self.segs]
        ids, V = Y.load_store("emb_tvseg")
        have = dict(zip(ids, V)) if ids else {}
        miss = sorted({t for t in texts if t not in have})
        if miss:
            Vm = normalize(Y.embed_texts(miss, "yt_embed_tv_segments", batch=500))
            have.update(zip(miss, Vm))
            Y.save_store("emb_tvseg", list(have), np.array(list(have.values())))
        self.segV = np.array([have[t] for t in texts], dtype=np.float32) if texts else np.zeros((0, Y.EMB_DIM))
        self.segbm = Y.BM25({k: t for k, t in enumerate(texts)})

    def moments(self, fused, Qv, bq, depth=20):
        if not self.segs:
            return []
        vr = {c: k for k, c in enumerate(fused[:100])}
        cand = [k for k, s in enumerate(self.segs) if s[0] in vr]
        if not cand:
            return []
        ds = (self.segV[cand] @ Qv.T).max(axis=1)
        bs = self.segbm.scores(bq)[cand]
        r_d = [cand[i] for i in np.argsort(-ds)]
        r_b = [cand[i] for i in np.argsort(-bs) if bs[i] > 0]
        r_v = sorted(cand, key=lambda k: (vr[self.segs[k][0]], self.segs[k][1]))
        out = rrf(r_d, r_b, r_v)[:depth]
        return [{"code": self.segs[k][0], "start_s": int(self.segs[k][1]), "end_s": int(self.segs[k][2])} for k in out]


def load_parses(prefix, rep):
    return json.load(open(os.path.join(RUNS, "rewrites", f"{prefix}_gpt-5-nano_r{rep}.json")))


def run(cfg, reps, intent=None, name=None, iv="qi-v1"):
    t0 = time.time()
    S = Searcher(cfg)
    build_s = time.time() - t0
    qs = Y.load_queries()
    L = ledger()
    costs = {}
    for r in L:
        costs[r["purpose"]] = costs.get(r["purpose"], 0) + r["cost_usd"]
    written = []
    for rep in reps:
        P = load_parses("qr-v1", rep)
        PI = load_parses(iv, rep) if intent else None
        RW = (PI if intent == "full" else P)["_meta"]
        out, moments, lat, intents = {}, {}, [], {}
        for q in qs:
            t = time.time()
            if q["examples"]:
                fused = S.mlt(q)
            else:
                parse = PI[q["id"]] if intent == "full" else P[q["id"]]
                fused, Qv, bq = S.typed(q, parse)
                if intent:
                    fused, info = I.apply(S.D, fused, PI[q["id"]]["intent"])
                    intents[q["id"]] = info
                if "moment" in q["kinds"] and S.segs:
                    moments[q["id"]] = S.moments(fused, Qv, bq)
            out[q["id"]] = fused[:1000]
            lat.append(time.time() - t)
        typed = [q["id"] for q in qs if not q["examples"]]
        pq = [RW["per_query"][k] for k in typed if k in RW["per_query"]]
        cost_extra = {}
        if intent == "filters":  # the base qr-v1 call + the qi-v1 call (in production one qi-v1 call would do)
            pq2 = [PI["_meta"]["per_query"][k] for k in typed]
            cost_extra["intent_call_cost_usd"] = round(sum(v["cost_usd"] for v in pq2), 6)
        meta = {"config": cfg, "view": S.view, "intent": intent, "rewrite": f"{RW['prompt_version']}_{RW['model']}_r{rep}",
                "hyde_alpha": HYDE_ALPHA, "embedding": f"{Y.EMB_MODEL}@{Y.EMB_DIM}",
                "enrichment_indexes": {E.name + (":" + cfg.split("_")[1] if E.name == TV else ""): len(E.codes)
                                       for E in S.E},
                "items_with_view_vector": len(S.vcodes), "items_with_view_text": len(S.text),
                "index_build_s": round(build_s, 1), "query_p50_s": round(float(np.median(lat)), 3),
                "query_p95_s": round(float(np.percentile(lat, 95)), 3),
                "rewrite_cost_usd": round(sum(v["cost_usd"] for v in pq), 6),
                "rewrite_cost_per_1k_searches_usd": round(1000 * float(np.mean([v["cost_usd"] for v in pq])), 4),
                "rewrite_p50_s": round(float(np.median([v["seconds"] for v in pq])), 3), **cost_extra,
                "offline_cost_usd_by_purpose": {k: round(v, 4) for k, v in costs.items()}}
        meta["typed_query_plus_rewrite_p50_s"] = round(meta["query_p50_s"] + meta["rewrite_p50_s"], 3)
        if intents:
            meta["intent_per_search"] = intents
        if cfg.startswith("ref_"):
            meta["research_only"] = "uses YouTube API Data (description, tags, chapters); never adopt"
        tag = "a3" if iv == "qi-v1" else "a3v2"
        nm = name or (cfg if not intent else f"{tag}_{'intent' if intent == 'full' else 'filtersonly'}_on_{cfg}")
        method = f"yt_b3:{nm}+{meta['rewrite']}+hyde"
        run_d = {"method": method, "embedding": f"oai512_{S.view}", "meta": meta, "queries": out}
        if moments:
            run_d["moments"] = moments
        path = os.path.join(RUNS, f"{nm}_r{rep}.json")
        os.makedirs(RUNS, exist_ok=True)
        json.dump(run_d, open(path, "w"))
        written.append(path)
        print(f"wrote {os.path.basename(path)}: {len(out)} searches, p50 {meta['query_p50_s']} s, "
              f"moments {len(moments)}", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, choices=list(CONFIGS))
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--intent", choices=["full", "filters"])
    ap.add_argument("--intent-version", default="qi-v1", choices=["qi-v1", "qi-v2"])
    a = ap.parse_args()
    run(a.config, [int(x) for x in a.reps.split(",")], a.intent, iv=a.intent_version)


if __name__ == "__main__":
    main()
