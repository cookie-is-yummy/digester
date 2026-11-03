"""PROTOTYPE ONLY - round 4.1: one combined Instagram + YouTube index for platform-blind search.

Method side only: reads $DIGESTER_DATA/corpus, evals/queries.jsonl, evals/split.json, enrich/, yt_enrich/ and the
reused round-3 YouTube vector stores. Never opens evals/labels/.

What each item contributes (fixed per item by its platform's adapter rule, never by the search):
  view text : Instagram = round 1's `full` view (caption[:600], hashtags, "by @handle name", word-split hashtags and
              handle; lib/corpus.Corpus.text); YouTube = round 3's allowed view (Takeout title, "by <channel>",
              named playlists; yt_lib.YT.allowed_text).
  vector    : corpus/emb/oai512 (text-embedding-3-small, 512 d) of that view; items with no text have none.
  dense gate: Instagram = round-1 info class "ok" (B3); YouTube = has a Takeout title (A0: no caption gate).
The search code below never asks which platform a search targets. `platform` is used only to restrict an index to
one platform for the single-platform control runs (c0ig / c0yt) and by the intent step when a user names it.

Enrichment indexes (te-v1c): one combined index of Instagram rows (Y4.1-TE) and YouTube's round-3 allowed rows.
`active` restricts which items' rows are rankable (C2, information sufficiency); query-side example rows are kept.
"""
import json
import os
import re
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import yt_lib as Y
from common import GENERIC, STOP, info_class, letters, strip_tags
from corpus import DATA, fix_ws, rrf

EMB = os.path.join(DATA, "corpus", "emb")
HYDE_ALPHA = 0.7
TE_IG = "te-v1c_ig_gemini-3.1-flash-lite"
TE_YT = "te-v1c_allowed_gemini-3.1-flash-lite"
WATCH_LATER = "Watch later"


def code_of(it):
    return it["dedup_key"].split(":", 1)[1]


def jl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------- per-item text views (adapter side) ----------------
_SPLIT = {}


def _ninja(s):
    if s not in _SPLIT:
        import wordninja
        _SPLIT[s] = " ".join(wordninja.split(s))
    return _SPLIT[s]


def ig_full_text(it):
    """Exactly lib/corpus.Corpus.text(n, 'full') without extra_text."""
    pd = it["platform_data"]
    cap = it.get("caption") or ""
    tags = pd.get("hashtags") or []
    parts = [cap[:600], " ".join("#" + t for t in tags[:15]),
             f"by @{pd.get('owner_handle') or ''} {pd.get('owner_name') or ''}",
             " ".join(_ninja(t) for t in tags[:15]), _ninja(pd.get("owner_handle") or "")]
    return fix_ws(" ".join(parts))


def yt_allowed_text(it):
    """Exactly yt_lib.YT.allowed_text."""
    pd = it["platform_data"]
    title = (it.get("caption") or "").strip()
    ch = (pd.get("owner_name") or "").strip()
    pls = sorted({p for p in (pd.get("collections") or []) if p != WATCH_LATER})
    parts = [title]
    if ch:
        parts.append(f"by {ch}")
    if pls:
        parts.append("playlists: " + ", ".join(pls))
    return fix_ws(" ".join(p for p in parts if p))


def view_text(it):
    return ig_full_text(it) if it["platform"] == "instagram" else yt_allowed_text(it)


def gate_ok(it):
    if it["platform"] == "instagram":
        return info_class(it) == "ok"
    return bool((it.get("caption") or "").strip())


# ---------------- information sufficiency (C2, preregistered in LOG.md Y4.1-C2) ----------------
_W = re.compile(r"[^\W\d_]{3,}")
MIN_CONTENT_WORDS = 4


def content_words(it):
    toks = {t for t in _W.findall(strip_tags(it.get("caption") or "").lower()) if t not in STOP}
    tags = {h.lower() for h in (it["platform_data"].get("hashtags") or [])}
    topical = {t for t in tags if t not in GENERIC and letters(t)[0] >= 3 and t not in toks}
    return len(toks) + len(topical)


def insufficient(it):
    """(1) no own text, (2) round-1 info class non_english, or (3) fewer than 4 content words."""
    if info_class(it) == "non_english":
        return True
    return content_words(it) < MIN_CONTENT_WORDS  # (1) is the 0-word case of (3)


def insufficient_reason(it):
    text = strip_tags(it.get("caption") or "").strip()
    n = content_words(it)
    if not text and n == 0:
        return "no_text"
    if info_class(it) == "non_english":
        return "non_english"
    if n < MIN_CONTENT_WORDS:
        return "few_words"
    return None


# ---------------- vector stores ----------------
def load_store(path):
    if not os.path.exists(os.path.join(path, "ids.json")):
        return [], np.zeros((0, Y.EMB_DIM), np.float32)
    return json.load(open(os.path.join(path, "ids.json"))), normalize(np.load(os.path.join(path, "emb.npy")).astype(np.float32))


def save_store(path, ids, V):
    os.makedirs(path, exist_ok=True)
    json.dump(ids, open(os.path.join(path, "ids.json"), "w"))
    np.save(os.path.join(path, "emb.npy"), V.astype(np.float16))


class QueryVecs:
    """Cached query / HyDE / outside-example vectors (corpus/emb/c4_queries). Missing strings are embedded."""

    def __init__(self, name="c4_queries"):
        self.path = os.path.join(EMB, name)
        ids, V = load_store(self.path)
        self.vec = {s: V[k] for k, s in enumerate(ids)}

    def get(self, texts):
        miss = sorted({t for t in texts if t not in self.vec})
        if miss:
            V = normalize(Y.embed_texts(miss, "c4_query_vectors", batch=500, workers=1))
            self.vec.update(zip(miss, V))
            ids = list(self.vec)
            save_store(self.path, ids, np.array([self.vec[s] for s in ids]))
        return np.array([self.vec[t] for t in texts], dtype=np.float32)


# ---------------- enrichment index ----------------
class EnrichIdx:
    """te-v1c rows as their own BM25 list and dense list. `codes` = rankable rows (corpus items in the subset, and
    in `active` if given); ex_text / ex_vec = every row, for more-like-this examples (incl. outside-library ones)."""

    def __init__(self, sources, corpus_codes, active=None):
        text, vec = {}, {}
        for tpath, epath in sources:
            t = json.load(open(tpath))
            ids, V = load_store(epath)
            for k, c in enumerate(ids):
                if c in t:
                    text[c], vec[c] = t[c], V[k]
        self.ex_text, self.ex_vec = text, vec
        self.codes = [c for c in text if c in corpus_codes and (active is None or c in active)]
        self.V = np.array([vec[c] for c in self.codes], dtype=np.float32).reshape(-1, Y.EMB_DIM)
        self.bm = Y.BM25({c: text[c] for c in self.codes}) if self.codes else None

    def bm25(self, q, keep, exclude=()):
        return self.bm.rank(q, exclude=exclude, keep=keep) if self.bm else []

    def dense(self, Qv, keep, exclude=()):
        if not self.codes:
            return []
        s = (self.V @ Qv.T).max(axis=1)
        ex = set(exclude)
        out = []
        for n in np.argsort(-s):
            c = self.codes[n]
            if c not in ex and (keep is None or keep(c)):
                out.append(c)
                if len(out) >= 1000:
                    break
        return out


def te_sources():
    return [(os.path.join(DATA, "enrich", f"text_{TE_IG}.json"), os.path.join(EMB, f"emb_{TE_IG}")),
            (os.path.join(DATA, "yt_enrich", f"text_{TE_YT}.json"), os.path.join(EMB, f"emb_yt_{TE_YT}"))]


# ---------------- the combined index ----------------
class Combined:
    def __init__(self, platform="all", enrich=None, route=False, items=None):
        """platform: all | instagram | youtube (control runs). enrich: None or 'te' (combined te-v1c index).
        route: C2, te rows rankable only for items whose own text is insufficient."""
        t0 = time.time()
        allitems = items if items is not None else jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.items = [it for it in allitems if platform == "all" or it["platform"] == platform]
        self.platform = platform
        self.codes = [code_of(it) for it in self.items]
        self.pos = {c: n for n, c in enumerate(self.codes)}
        self.id_pos = {it["id"]: n for n, it in enumerate(self.items)}
        self.first = np.array([it.get("first_seen_at") or "9999" for it in self.items])
        self.kinds = [set(it["interaction_kinds"]) for it in self.items]
        texts = {}
        for it, c in zip(self.items, self.codes):
            t = view_text(it)
            if t:
                texts[c] = t
        self.text = texts
        self.bm = Y.BM25(texts)
        ids, V = load_store(os.path.join(EMB, "oai512"))
        keep = [k for k, i in enumerate(ids) if i in self.id_pos]
        self.V = V[keep]
        self.vpos = np.array([self.id_pos[ids[k]] for k in keep])
        self.vcodes = [self.codes[n] for n in self.vpos]
        self.row_of = {c: k for k, c in enumerate(self.vcodes)}
        self.gate = np.array([gate_ok(self.items[n]) for n in self.vpos])
        self.QV = QueryVecs()
        self.outside = Y.outside_examples() if platform != "instagram" else {}
        self.ext_vec = {}
        if self.outside:
            oc = list(self.outside)
            self.ext_vec = dict(zip(oc, self.QV.get([self.outside[c] for c in oc])))
        self.E = []
        self.n_active = None
        if enrich == "te":
            active = None
            if route:
                active = {c for it, c in zip(self.items, self.codes) if insufficient(it)}
            self.E.append(EnrichIdx(te_sources(), set(self.pos), active))
        self.build_s = time.time() - t0

    def counts(self):
        plat = [it["platform"] for it in self.items]
        out = {"items": len(self.items), "items_by_platform": {p: plat.count(p) for p in sorted(set(plat))},
               "items_with_vector": len(self.vcodes), "items_dense_gated_in": int(self.gate.sum()),
               "items_with_view_text": len(self.text)}
        for E in self.E:
            byp = {}
            for c in E.codes:
                p = self.items[self.pos[c]]["platform"]
                byp[p] = byp.get(p, 0) + 1
            out["te_rows_rankable"] = len(E.codes)
            out["te_rows_rankable_by_platform"] = byp
        return out

    def keep_fn(self, filters):
        if not filters:
            return None
        ok = np.ones(len(self.items), bool)
        if filters.get("before"):
            ok &= self.first < filters["before"]
        if filters.get("kinds"):
            want = set(filters["kinds"])
            ok &= np.array([bool(k & want) for k in self.kinds])
        pos = self.pos
        return lambda c: c in pos and bool(ok[pos[c]])

    def _dense_rank(self, s, keep, exclude=(), gate=True):
        ex = set(exclude)
        out = []
        for n in np.argsort(-s):
            if gate and not self.gate[n]:
                continue
            c = self.vcodes[n]
            if c in ex or (keep is not None and not keep(c)):
                continue
            out.append(c)
            if len(out) >= 1000:
                break
        return out

    def typed(self, q, parse):
        keep = self.keep_fn(q.get("filters"))
        Qv = self.QV.get([q["query"]] + parse["phrases"])
        caps = parse.get("hypothetical_captions") or []
        if caps:
            H = self.QV.get(caps)
            v = (1 - HYDE_ALPHA) * Qv[0] + HYDE_ALPHA * H.mean(0)
            Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
        s = (self.V @ Qv.T).max(axis=1)
        sg = np.where(self.gate, s, -9.0)
        if keep is not None:
            sg = np.where(np.array([keep(c) for c in self.vcodes]), sg, -9.0)
        top = np.argsort(-sg)[:5]
        q2 = Qv.mean(0) + self.V[top].mean(0)
        q2 /= np.linalg.norm(q2)
        s = np.maximum(s, self.V @ q2)
        bq = " ".join([q["query"]] + parse["keywords"])
        lists = [self._dense_rank(s, keep), self.bm.rank(bq, keep=keep)]
        for E in self.E:
            lists += [E.bm25(bq, keep), E.dense(Qv, keep)]
        return rrf(*lists)

    def mlt(self, q):
        keep = self.keep_fn(q.get("filters"))
        ex = q["examples"]
        vecs = [self.V[self.row_of[c]] for c in ex if c in self.row_of] + \
               [self.ext_vec[c] for c in ex if c not in self.row_of and c in self.ext_vec]
        lists = []
        if vecs:
            cen = np.mean(vecs, 0)
            cen /= np.linalg.norm(cen)
            lists.append(self._dense_rank(self.V @ cen, keep, ex))
        etext = " ".join(self.text.get(c) or self.outside.get(c, "") for c in ex)
        lists.append(self.bm.rank(etext, exclude=ex, keep=keep))
        for E in self.E:
            exe = [c for c in ex if c in E.ex_text]
            if exe:
                lists.append(E.bm25(" ".join(E.ex_text[c] for c in exe), keep, ex))
                ce = normalize(np.mean([E.ex_vec[c] for c in exe], 0, keepdims=True))
                lists.append(E.dense(ce, keep, ex))
        return rrf(*lists)

    def search(self, q, parse):
        return self.mlt(q) if q["examples"] else self.typed(q, parse)


class CodeIds:
    """Shim for lib/corpus.write_run: rankings are already content codes."""

    def __init__(self, emb_name):
        self.emb_name = emb_name
        self.code = self

    def __getitem__(self, c):
        return c


def ledger():
    p = os.path.join(DATA, "ai_runs.jsonl")
    return jl(p) if os.path.exists(p) else []


def load_parses(prefix, rep):
    return json.load(open(os.path.join(DATA, "runs", "rewrites", f"{prefix}_gpt-5-nano_r{rep}.json")))
