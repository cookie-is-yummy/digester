"""PROTOTYPE ONLY - round 8.1 shared code (LOG.md "Round 8.1 fixed parameters", rows Y8.1-H5d, Y8.1-I, Y8.1-R).

  Creators7d   H5d: round 7's Creators7 (H4 profiles: channel-type / era words, affinity / era priors) made
               deterministic. Round 7 built each creator's profile text from Counter.most_common() over terms that
               were inserted by iterating Python sets of strings, so ties at the top-k cut (which terms made the
               profile, in which order) followed PYTHONHASHSEED. Here every set is iterated sorted, every top-k is
               (-count, term), and every ranking tie is broken by the creator key (stable argsort, key tie-breaks in
               the creator RRF and the prior re-sort). Nothing else changes.
  plan_instant Y8.1-I: no LLM rewrite. Dense texts = [raw query], no HyDE captions, BM25 = raw query (H0's PRF, gate,
               depth and RRF unchanged).
  ShapeRouter  Y8.1-R: LLM-free rule from query shape and the user's own index (creator handles / names, own view
               text). Fixed in LOG.md before any run; never reads labels, timestamps or eval outcomes.
Method side only: never opens evals/labels/. Never prints query or item text.
"""
import collections
import os
import re
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_intent as I  # noqa: E402
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c7_lib as H  # noqa: E402
import yt_lib as Y  # noqa: E402
from common import GENERIC, STOP, strip_tags  # noqa: E402
from corpus import fix_ws  # noqa: E402

ROUTE_VERSION = "route-r1"


# ---------------- deterministic helpers ----------------
def top_terms(counter, n):
    """Top n terms by count, ties broken by the term (no dependence on insertion / hash order)."""
    return [t for t, _ in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:n]]


def rrf_det(*lists, k=60, depth=1000):
    sc = {}
    for lst in lists:
        for r, c in enumerate(lst[:depth]):
            sc[c] = sc.get(c, 0.0) + 1.0 / (k + r + 1)
    return sorted(sc, key=lambda c: (-sc[c], c)), sc


class Creators7d(H.Creators7):
    """H.Creators7 with deterministic profile text and tie-sorted rankings (see module docstring)."""

    def __init__(self, S, te_rows, facets=None, enriched=False):  # noqa: C901 - mirrors Creators7.__init__
        t0 = time.time()
        self.enriched = enriched
        self.of = {}
        members = collections.defaultdict(list)
        names, handles = {}, {}
        for it, c in zip(S.items, S.codes):  # item order is the corpus file order (deterministic)
            k = F.creator_key(it)
            if not k:
                continue
            self.of[c] = k
            members[k].append(c)
            pd = it["platform_data"]
            names.setdefault(k, F._clean(pd.get("owner_name")))
            handles.setdefault(k, F._clean(pd.get("owner_handle")).lstrip("@"))
        self.keys = sorted(members)
        self.idx = {k: n for n, k in enumerate(self.keys)}
        self.members = dict(members)
        dim = S.V.shape[1]
        P = np.zeros((len(self.keys), dim), np.float32)
        nv = np.zeros(len(self.keys))
        for c, k in self.of.items():
            r = S.row_of.get(c)
            if r is not None:
                P[self.idx[k]] += S.V[r]
                nv[self.idx[k]] += 1
        self.hasvec = nv > 0
        P[self.hasvec] = normalize(P[self.hasvec])
        self.P = P
        n_inter = np.zeros(len(self.keys))
        last = [""] * len(self.keys)
        first = ["9999"] * len(self.keys)
        if enriched:
            for c, k in self.of.items():
                n = S.pos[c]
                j = self.idx[k]
                n_inter[j] += len(S.inter[n])
                for _, a in S.inter[n]:
                    if a:
                        last[j] = max(last[j], a)
                        first[j] = min(first[j], a)
            self.aff = H.pct_rank(np.log1p(n_inter))
            self.has_date = np.array([bool(x) for x in last])
            self.last_pct = np.zeros(len(self.keys))
            la = np.array(last)[self.has_date]
            self.last_pct[self.has_date] = H.pct_rank(np.unique(la, return_inverse=True)[1])
        texts = {}
        self.n_typed, self.n_era = 0, 0
        pos = S.pos
        for k in self.keys:
            tops, kinds, vibes, tags, words = (collections.Counter() for _ in range(5))
            for c in self.members[k]:
                it = S.items[pos[c]]
                r = te_rows.get(c)
                if r:
                    tops.update(sorted(set(r["topics"])))
                    if r["kind"] and r["kind"] not in ("unknown", "other"):
                        kinds[r["kind"]] += 1
                    vibes.update(sorted(set(r["vibe"])))
                for h in sorted({x.lower() for x in it["platform_data"].get("hashtags") or []}):
                    if h not in GENERIC and len(h) >= 3:
                        tags[h] += 1
                words.update(sorted({t for t in H._W.findall(strip_tags(it.get("caption") or "").lower())
                                     if t not in STOP}))
            h = handles.get(k, "")
            parts = [names.get(k, ""), h, L._ninja(h) if h else "", " ".join(top_terms(tops, 15)),
                     " ".join(top_terms(kinds, 3)).replace("_", " "), " ".join(top_terms(vibes, 5)),
                     " ".join(top_terms(tags, 10)), " ".join(top_terms(words, 20))]
            if enriched:
                extra = self._channel_words(k, facets)
                j = self.idx[k]
                if extra:
                    self.n_typed += 1
                if last[j]:
                    y0, y1 = int(first[j][:4]), int(last[j][:4])
                    extra += " " + " ".join(str(y) for y in range(y0, y1 + 1))
                    self.n_era += 1
                parts.append(extra)
            texts[k] = fix_ws(" ".join(parts))
        self.names, self.handles = names, handles
        self.texts = texts
        self.bm = Y.BM25(texts)
        self.build_s = time.time() - t0

    def _channel_words(self, k, facets):
        rows = [facets.row[c] for c in self.members[k] if c in facets.row]
        if not rows:
            return ""
        am = facets.Pf[rows].argmax(1)
        cnt = collections.Counter(am.tolist())
        top, n = min(cnt.items(), key=lambda x: (-x[1], x[0]))  # majority class, ties -> lower class index
        out = []
        if H.FORMAT_CLASSES[top] != "other" and n / len(rows) >= 0.4:
            out.append(H.FORMAT_WORDS[H.FORMAT_CLASSES[top]])
        mt = facets.Pt[rows].mean(0)
        out += [H.TONE_WORDS[c] for j, c in enumerate(H.TONE_CLASSES) if mt[j] >= 0.4]
        return " ".join(out)

    def _bm_rank(self, query, depth):
        s = self.bm.scores(query)
        s[s <= 0] = -np.inf
        order = np.lexsort((np.arange(len(s)), -s))  # score desc, ties by key order (keys are sorted)
        return [self.bm.keys[n] for n in order[:depth] if np.isfinite(s[n])]

    def rank(self, QV, dense_texts, bm_query, item_order, direction=None):
        lists = []
        texts = [t for t in dense_texts if t]
        if texts:
            Qv = QV.get(texts)
            s = (self.P @ Qv.T).max(axis=1)
            s[~self.hasvec] = -np.inf
            order = np.argsort(-s, kind="stable")[:F.DEPTH]  # ties -> creator key order
            lists.append([self.keys[n] for n in order if np.isfinite(s[n])])
        lists.append(self._bm_rank(bm_query, F.DEPTH) if bm_query.strip() else [])
        best, seen = [], set()
        for c in item_order[:F.DEPTH]:
            k = self.of.get(c)
            if k and k not in seen:
                seen.add(k)
                best.append(k)
        lists.append(best)
        lists = [x for x in lists if x]
        base, sc = rrf_det(*lists, k=F.K_RRF, depth=F.DEPTH)
        if not self.enriched:
            return base
        out = {}
        for k in base:
            j = self.idx[k]
            e = 0.0
            if direction and self.has_date[j]:
                e = (1 - self.last_pct[j]) if direction == "old" else self.last_pct[j]
            out[k] = sc[k] * (1 + 0.3 * self.aff[j]) * (1 + 0.3 * e)
        return sorted(base, key=lambda k: (-out[k], k))


# ---------------- Y8.1-I: instant plan ----------------
def plan_instant(q):
    """(dense texts, HyDE captions, BM25 query) with no rewrite: the raw query only."""
    return [q["query"]], [], q["query"]


# ---------------- Y8.1-R: LLM-free shape router (route-r1, fixed in LOG.md) ----------------
TOK = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
QWORDS = {"how", "what", "whats", "what's", "why", "where", "when", "who", "whos", "who's", "which", "whose"}
DESC = {"about", "something", "someone", "somebody", "stuff", "thing", "things", "whatever", "whoever", "remember",
        "forgot", "forget", "maybe", "kinda", "sorta", "guy", "girl", "dude", "lady", "person"}
PRON = {"i", "i'm", "im", "i've", "ive", "i'd", "me", "my", "myself", "we", "our"}
MAX_SHORT, MAX_MATCH, MIN_NAME_CHARS, MIN_CREATOR_ITEMS = 4, 8, 5, 2
_NORM = re.compile(r"[^a-z0-9]+")


def norm_key(s):
    return _NORM.sub("", (s or "").lower())


_URL = re.compile(r"https?://\S+")


def norm_phrase(s):
    return " ".join(TOK.findall(_URL.sub(" ", (s or "").lower())))


def markers(query):
    """Description / question / request / behaviour / time markers (fixed lexicons; most reused from earlier rounds)."""
    q = query or ""
    low = " ".join(q.lower().split())
    toks = TOK.findall(low)
    m = []
    if "?" in q:
        m.append("qmark")
    if any(t in QWORDS for t in toks):
        m.append("question_word")
    if any(t in DESC for t in toks):
        m.append("description_word")
    if any(t in PRON for t in toks):
        m.append("first_person")
    if any(r.search(low) for r in G.H2):
        m.append("vague_reference")  # round 6 G3 lexicon
    if any(r.search(low) for r in G.H3):
        m.append("request")  # round 6 G3 lexicon
    if any(rx.search(q) for rx in I.FLAG_RX_V43.values()):
        m.append("behaviour")  # E1 lexicon: liked / saved / shared / sent / watched
    if I.TIME_RX.search(q) or I.ORDER_TIME_RX.search(q) or H.OLD_RX.search(q) or H.NEW_RX.search(q):
        m.append("time")  # E1 calendar words, ordering words, round 7 soft-time lexicon
    return toks, m


class ShapeRouter:
    """route-r1: instant path iff the query has no marker AND (<= 4 tokens OR (<= 8 tokens AND it names a creator
    in the user's library or repeats a phrase of the user's own item text verbatim)). Else the H0 rewrite path."""

    def __init__(self, S):
        t0 = time.time()
        cnt = collections.Counter()
        for it in S.items:
            k = F.creator_key(it)
            if k:
                cnt[k] += 1
        keys = set()
        for it in S.items:
            k = F.creator_key(it)
            if not k or cnt[k] < MIN_CREATOR_ITEMS:
                continue
            pd = it["platform_data"]
            for s in (pd.get("owner_handle"), pd.get("owner_name")):
                n = norm_key(str(s or "").lstrip("@"))
                if len(n) >= MIN_NAME_CHARS:
                    keys.add(n)
        self.creator_keys = keys
        self.blob = "\n".join(" " + norm_phrase(t) + " " for t in S.text.values())  # phrases cannot span a newline
        self.build_s = time.time() - t0

    def creator_match(self, toks):
        for i in range(len(toks)):
            for j in range(i + 1, min(len(toks), i + 4) + 1):
                if norm_key("".join(toks[i:j])) in self.creator_keys:
                    return True
        return False

    def phrase_match(self, toks):
        if len(toks) < 2:
            return False
        p = " " + " ".join(toks) + " "
        return p in self.blob

    def route(self, query):
        toks, m = markers(query)
        n = len(toks)
        info = {"version": ROUTE_VERSION, "n_tokens": n, "markers": m, "creator_match": False, "phrase_match": False}
        if not n or m:
            info["path"] = "rewrite"
            return info
        if n <= MAX_SHORT:
            info["path"], info["reason"] = "instant", "short"
            return info
        if n <= MAX_MATCH:
            info["creator_match"] = self.creator_match(toks)
            if not info["creator_match"]:
                info["phrase_match"] = self.phrase_match(toks)
            if info["creator_match"] or info["phrase_match"]:
                info["path"], info["reason"] = "instant", "creator" if info["creator_match"] else "phrase"
                return info
        info["path"] = "rewrite"
        return info
