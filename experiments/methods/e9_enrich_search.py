"""PROTOTYPE ONLY - experiment 9: honest base + tier-1 enrichment as separate RRF lists.

Base (reproduced exactly when --arms none; checked against data/runs/e1_rewrite_r{1,2,3}.json):
  real LLM rewrite (qr-v1, cached) -> bge-small dense over info-ok items (max over phrases, Rocchio PRF top 5)
  + BM25 over the 'full' text view -> RRF (k=60). More-like-this: example centroid + BM25 on example text.
Extra lists (each its own index, fused into the same RRF in content-code space):
  ebm25  : BM25 over the enrichment text only (summary, kind, facets, likely searches; separate index,
           same tokenisation and k1/b as the base BM25). Only items with a positive score are listed.
  edense : bge-small over the enrichment text only; max over the base's query phrases (no PRF, no gate).
  More-like-this: BM25 over the examples' enrichment text and the centroid of their enrichment vectors.
Items with enrichment but no caption vector (no-text items) are rankable through these lists.

Build step (once per enrichment file): python e9_enrich_search.py --build --enrich te-v1_gpt-5-nano
  -> $DIGESTER_DATA/enrich/text_<enrich>.json {code: text}  and  enrich/emb_<enrich>/ (ids.json, emb.npy f16)
Run:  python e9_enrich_search.py --enrich te-v1_gpt-5-nano --arms both|bm25|dense|none --rep 1 --out runs/x.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
from corpus import DATA, Corpus, code_of, fix_ws, load_queries, rank, rrf  # noqa: E402
from enrich_items import FILLER  # noqa: E402

FIELDS = ["topics", "shown", "said", "place", "people", "vibe", "use", "queries"]


def enrich_text(r):
    kind = r.get("kind") or ""
    parts = [r.get("summary") or ""]
    if kind not in ("", "unknown", "other"):
        parts.append(kind.replace("_", " "))
    for f in FIELDS:  # re-apply the filler filter (rows validated before it existed)
        parts.append(" · ".join(x for x in (r.get(f) or []) if not FILLER.search(x)))
    return fix_ws(" · ".join(p for p in parts if p))


def build(enrich, restrict_sample=True):
    t0 = time.time()
    rows = [json.loads(l) for l in open(os.path.join(DATA, "enrich", f"{enrich}.jsonl"))]
    rows = {r["code"]: r for r in rows if r["ok"]}  # last ok row wins
    if restrict_sample:
        import enrich_items
        items = enrich_items.load_items()
        keep = set(enrich_items.select("sample", items)[0])
        rows = {c: r for c, r in rows.items() if c in keep}
    texts = {c: enrich_text(r) for c, r in sorted(rows.items())}
    json.dump(texts, open(os.path.join(DATA, "enrich", f"text_{enrich}.json"), "w"))
    items = {code_of(json.loads(l)): json.loads(l)["id"]
             for l in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8")}
    codes = list(texts)
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=4)
    t1 = time.time()
    V = np.array(list(model.embed([texts[c] for c in codes], batch_size=64)), dtype=np.float32)
    d = os.path.join(DATA, "enrich", f"emb_{enrich}")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "emb.npy"), V.astype(np.float16))
    json.dump([items[c] for c in codes], open(os.path.join(d, "ids.json"), "w"))
    el = time.time() - t1
    print(f"built {len(codes)} enrichment texts (mean {np.mean([len(t) for t in texts.values()]):.0f} chars); "
          f"embedded {len(codes)} items, {len(codes) / el:.1f} items/s, embed {el:.1f}s, wall {time.time() - t0:.1f}s")


class EnrichIndex:
    def __init__(self, enrich, items_by_code):
        self.text = json.load(open(os.path.join(DATA, "enrich", f"text_{enrich}.json")))
        d = os.path.join(DATA, "enrich", f"emb_{enrich}")
        ids = json.load(open(os.path.join(d, "ids.json")))
        code_by_id = {it["id"]: c for c, it in items_by_code.items()}
        self.codes = [code_by_id[i] for i in ids]
        assert set(self.codes) == set(self.text)
        self.pos = {c: n for n, c in enumerate(self.codes)}
        self.V = normalize(np.load(os.path.join(d, "emb.npy")).astype(np.float32))
        docs = [self.text[c].lower() for c in self.codes]
        cv = CountVectorizer(token_pattern=r"(?u)\b\w\w+\b", ngram_range=(1, 2), min_df=1)
        tf = cv.fit_transform(docs).tocsc().astype(np.float32)
        N = tf.shape[0]
        df = np.diff(tf.indptr)
        idf = np.log(1 + (N - df + 0.5) / (df + 0.5)).astype(np.float32)
        dl = np.asarray(tf.sum(axis=1)).ravel()
        k1, b = 1.2, 0.75
        tf = tf.tocoo()
        w = tf.data * (k1 + 1) / (tf.data + k1 * (1 - b + b * dl[tf.row] / dl.mean())) * idf[tf.col]
        self.cv, self.W = cv, sparse.csr_matrix((w, (tf.row, tf.col)), shape=tf.shape)
        first = [items_by_code[c].get("first_seen_at") or "9999" for c in self.codes]
        self.first = np.array(first)
        self.kinds = [set(items_by_code[c]["interaction_kinds"]) for c in self.codes]

    def mask(self, filters):  # same semantics as Corpus.mask
        m = np.ones(len(self.codes), bool)
        if filters.get("before"):
            m &= self.first < filters["before"]
        if filters.get("kinds"):
            want = set(filters["kinds"])
            m &= np.array([bool(k & want) for k in self.kinds])
        return m

    def bm25(self, query, m, exclude=()):
        q = self.cv.transform([query.lower()])
        q.data[:] = 1
        s = np.asarray((self.W @ q.T).todense()).ravel()
        s[~m] = -np.inf
        s[s <= 0] = -np.inf
        return [self.codes[n] for n in rank(s, None, [self.pos[c] for c in exclude if c in self.pos])][:1000]

    def dense(self, Qv, m, exclude=()):
        s = (self.V @ Qv.T).max(axis=1)
        return [self.codes[n] for n in rank(s, m, [self.pos[c] for c in exclude if c in self.pos])][:1000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", default="te-v1_gpt-5-nano")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--arms", default="both", choices=["both", "bm25", "dense", "none"])
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.build:
        build(a.enrich)
        return

    t0 = time.time()
    C = Corpus("bge_full")
    by_code = {code_of(it): it for it in C.items.values()}
    ok = C.info == "ok"
    parses = os.path.join(DATA, "runs", "rewrites", f"qr-v1_gpt-5-nano_r{a.rep}.json")
    P = json.load(open(parses))
    RW = P.get("_meta", {})
    E = EnrichIndex(a.enrich, by_code) if a.arms != "none" else None
    use_b, use_d = a.arms in ("both", "bm25"), a.arms in ("both", "dense")

    def dense(phrases, m):
        Qv = C.qvecs(phrases)
        s = (C.V @ Qv.T).max(axis=1)
        top = np.argsort(-np.where(m, s, -9))[:5]
        q2 = Qv.mean(0) + C.V[top].mean(0)
        q2 /= np.linalg.norm(q2)
        return np.maximum(s, C.V @ q2), Qv

    out, lat, n_extra = {}, [], []
    for q in load_queries(a.split):
        t = time.time()
        m = C.mask(q["filters"])
        lists = []
        if q["examples"]:
            ex = [C.by_code[c] for c in q["examples"] if c in C.by_code]
            cen = C.V[ex].mean(0)
            cen /= np.linalg.norm(cen)
            lists.append([C.code[n] for n in rank(C.V @ cen, m & ok, ex)])
            lists.append([C.code[n] for n in rank(C.bm25(" ".join(C.text(n, "full") for n in ex), "full"), m, ex)])
            if E is not None:
                em = E.mask(q["filters"])
                exe = [c for c in q["examples"] if c in E.pos]
                if exe and use_b:
                    lists.append(E.bm25(" ".join(E.text[c] for c in exe), em, exe))
                if exe and use_d:
                    ce = E.V[[E.pos[c] for c in exe]].mean(0, keepdims=True)
                    lists.append(E.dense(normalize(ce), em, exe))
        else:
            p = P[q["id"]]
            phrases = [q["query"]] + p["phrases"]
            s, Qv = dense(phrases, m & ok)
            lists.append([C.code[n] for n in rank(s, m & ok)])
            bq = " ".join([q["query"]] + p["keywords"])
            lists.append([C.code[n] for n in rank(C.bm25(bq, "full"), m)])
            if E is not None:
                em = E.mask(q["filters"])
                if use_b:
                    lists.append(E.bm25(bq, em))
                if use_d:
                    lists.append(E.dense(Qv, em))
        fused = rrf(*lists)
        out[q["id"]] = fused[:1000]
        if E is not None:
            n_extra.append(sum(1 for c in fused[:100] if c not in C.by_code))
        lat.append(time.time() - t)

    meta = {"wall_s": round(time.time() - t0, 1), "query_p50_s": round(float(np.median(lat)), 3),
            "rewrite": os.path.basename(parses), "arms": a.arms, "enrich": a.enrich if E else None,
            "prompt_version": RW.get("prompt_version"), "model": RW.get("model"),
            "reasoning_effort": RW.get("reasoning_effort")}
    pq = [RW["per_query"][k] for k in out if k in RW.get("per_query", {})]
    meta.update({"cost_usd": round(sum(v["cost_usd"] for v in pq), 6), "rewrite_n": len(pq),
                 "rewrite_p50_s": round(float(np.median([v["seconds"] for v in pq])), 3) if pq else None})
    if E is not None:
        rows = [json.loads(l) for l in open(os.path.join(DATA, "enrich", f"{a.enrich}.jsonl"))]
        rows = [r for r in rows if r["code"] in E.pos]
        meta.update({"enriched_items": len(E.codes),
                     "enrich_cost_usd_items": round(sum(r.get("cost_usd", 0) for r in rows), 4),
                     "enrich_cost_per_1k_items_usd": round(1000 * float(np.mean([r.get("cost_usd", 0) for r in rows])), 4),
                     "no_caption_vector_items_in_top100_mean": round(float(np.mean(n_extra)), 2),
                     "provisional": "enrichment covers the label-independent sample only (base top-200 per dev "
                                    "query x3 rewrites + 2,000 random + MLT examples), not the full corpus"})
    method = f"e9_enrich:{a.arms}+qr-v1_gpt-5-nano_r{a.rep}" + (f"+{a.enrich}" if E else "")
    run = {"method": method, "embedding": C.emb_name, "meta": meta, "queries": out}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(run, open(a.out, "w"))
    print("wrote", a.out, f"wall {meta['wall_s']}s, p50 {meta['query_p50_s']}s")


if __name__ == "__main__":
    main()
