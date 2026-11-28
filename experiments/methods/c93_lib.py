"""PROTOTYPE ONLY - round 9.3 Track 1 (items 5 and 7) shared code (LOG.md "Round 9.3 fixed parameters", rows
Y9.3-C1, Y9.3-C2).

Base Q8 (q8-v1, = runs/r9.1/q8ref_r{k}). Each arm changes one thing:
  C1  pv-v1: personal vocabulary expansion (code only). A per-user map built from the user's OWN library text only
      (titles / captions, hashtags, creator names and handles, collection / playlist names; friends' items
      excluded; no search logs, no eval texts) maps the user's words to the library's words. A search whose RAW
      words hit a map key gets at most PV_K mapped entries as extra BM25 terms at weight PV_W (both paths; own and
      te BM25 lists). The map is user data: it is written under data/ only (the private vault in the product).
  C2  rf-i1 alone: Q8's retrieval and gate unchanged; the gated refine reads round 9.1's cached qi-v1 frame and the
      generic 4-point rubric (c91t_lib.RefinerI) instead of rf-v1. Code lives in c93_search.py.
Method side only: never opens evals/labels/ or eval_work/; never reads a search timestamp. Prints aggregates only.
"""
import collections
import json
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c81_lib as R  # noqa: E402
from common import STOP  # noqa: E402
from corpus import DATA  # noqa: E402

C1_VERSION, C2_VERSION = "pv-v1", "c2-v1"
WORK = os.path.join(DATA, "r9.3")
MAP_PATH = os.path.join(WORK, "c1_vocab_map.json")  # user data: private vault, never in git

# ---------------- fixed parameters (LOG.md Y9.3-C1) ----------------
CAP_CHARS = 600          # caption cut, as the index's own text view
ACR_LEN = (2, 6)         # acronym token length; phrase has exactly len(acronym) tokens
JOIN_LEN = (5, 20)       # joined / clipped token length
JOIN_PART_MIN = 3        # each phrase part >= 3 characters
MIN_CO = 2               # items holding both the token and the phrase
MIN_CO_ACR2 = 5          # ... for 2-letter acronyms
MIN_DF_PHRASE = 3        # items holding the phrase
MIN_P_GIVEN_PHRASE = 0.25  # share of the phrase's items that also hold the token
MIN_LIFT = 10.0          # that share / the token's library rate
CRE_MIN_KEY = 5          # normalised handle / name length
COL_MIN_ITEMS, COL_K, COL_MIN_SHARE, COL_MIN_DF, COL_MIN_LIFT, COL_MAX_NAME_TOKENS = 5, 2, 0.2, 3, 5.0, 4
PV_K, PV_MAX_TOKENS, PV_W = 3, 8, 0.3
TYPE_ORDER = ("cre", "acr", "join", "col")

_TOK = re.compile(r"[a-z0-9]+")


def toks(s):
    return _TOK.findall((s or "").lower())


def _alpha(t):
    return t.isalpha()


def _segments(it):
    """Token lists that phrases may not cross: caption (cut), creator name, each collection / playlist name."""
    pd = it["platform_data"]
    segs = [toks((it.get("caption") or "")[:CAP_CHARS]), toks(pd.get("owner_name"))]
    segs += [toks(c) for c in sorted(pd.get("collections") or []) if c != L.WATCH_LATER]
    return [s for s in segs if s]


def _item_tokens(it, segs):
    pd = it["platform_data"]
    out = set()
    for s in segs:
        out.update(s)
    for h in pd.get("hashtags") or []:
        out.update(toks(h) if not _TOK.fullmatch(str(h).lower()) else [str(h).lower()])
    out.update(toks(pd.get("owner_handle")))
    return out


def _friend(it):
    return (it["platform_data"].get("owner_relation") or "") == "mutual"


def _acr_phrases(seg, acr_vocab):
    out = set()
    lo, hi = ACR_LEN
    for n in range(lo, hi + 1):
        for i in range(len(seg) - n + 1):
            w = seg[i:i + n]
            if not all(_alpha(x) and len(x) >= 2 for x in w):
                continue
            ini = "".join(x[0] for x in w)
            if ini not in acr_vocab or ini in w:
                continue
            if w[0] in STOP or w[-1] in STOP or sum(x not in STOP for x in w) < 2:
                continue
            out.add((ini, " ".join(w)))
    return out


def _join_phrases(seg, join_vocab):
    out = set()
    for i in range(len(seg) - 1):
        a, b = seg[i], seg[i + 1]
        if not (_alpha(a) and _alpha(b)) or a in STOP or b in STOP:
            continue
        if len(a) < JOIN_PART_MIN or len(b) < JOIN_PART_MIN:
            continue
        for k in range(2, len(a) + 1):
            s = a[:k] + b
            if s in join_vocab and s not in (a, b):
                out.add((s, f"{a} {b}"))
        if i + 2 < len(seg):
            c = seg[i + 2]
            if _alpha(c) and c not in STOP and len(c) >= JOIN_PART_MIN and a + b + c in join_vocab:
                out.add((a + b + c, f"{a} {b} {c}"))
    return out


def _accept(co, dfp, df, N):
    """{(token, phrase): stats} passing the fixed thresholds; best phrase per token and best token per phrase."""
    ok = {}
    for (t, p), n in co.items():
        if n < (MIN_CO_ACR2 if len(t) == 2 else MIN_CO) or dfp[p] < MIN_DF_PHRASE:
            continue
        pt = n / dfp[p]
        lift = pt / (df[t] / N)
        if pt >= MIN_P_GIVEN_PHRASE and lift >= MIN_LIFT:
            ok[(t, p)] = (n, dfp[p], round(pt, 4), round(lift, 2))
    best_t, best_p = {}, {}
    for (t, p), st in sorted(ok.items(), key=lambda x: (-x[1][0], -x[1][1], x[0])):
        best_t.setdefault(t, p)
        best_p.setdefault(p, t)
    return {(t, p): st for (t, p), st in ok.items() if best_t[t] == p and best_p[p] == t}


def build_map(items, df_other=None, common=None):
    """The per-user vocabulary map from the user's own library (friends' items excluded). Deterministic."""
    t0 = time.time()
    rows = []
    for it in items:
        if _friend(it):
            continue
        segs = _segments(it)
        rows.append((it, segs, _item_tokens(it, segs)))
    N = len(rows)
    df = collections.Counter()
    for _, _, ts in rows:
        df.update(ts)
    acr_vocab = {t for t, n in df.items() if ACR_LEN[0] <= len(t) <= ACR_LEN[1] and _alpha(t) and t not in STOP
                 and n >= MIN_CO}
    join_vocab = {t for t, n in df.items() if JOIN_LEN[0] <= len(t) <= JOIN_LEN[1] and _alpha(t) and t not in STOP
                  and n >= MIN_CO}
    co = {"acr": collections.Counter(), "join": collections.Counter()}
    dfp = {"acr": collections.Counter(), "join": collections.Counter()}
    for _, segs, ts in rows:
        got = {"acr": set(), "join": set()}
        for s in segs:
            got["acr"] |= _acr_phrases(s, acr_vocab)
            got["join"] |= _join_phrases(s, join_vocab)
        for kind in ("acr", "join"):
            for p in {p for _, p in got[kind]}:
                dfp[kind][p] += 1
            for t, p in got[kind]:
                if t in ts:
                    co[kind][(t, p)] += 1
    entries = []
    for kind in ("acr", "join"):
        for (t, p), st in sorted(_accept(co[kind], dfp[kind], df, N).items()):
            stats = {"co": st[0], "df_phrase": st[1], "df_token": df[t], "p_token_given_phrase": st[2],
                     "lift": st[3]}
            entries.append({"type": kind, "dir": "token_to_phrase", "key": [t], "value": p.split(), **stats})
            entries.append({"type": kind, "dir": "phrase_to_token", "key": p.split(), "value": [t], **stats})
    # cross-platform creator alias: an Instagram handle -> the same creator's YouTube channel name
    yt = collections.defaultdict(set)
    ig = {}
    for it, _, _ in rows:
        pd = it["platform_data"]
        n = (pd.get("owner_name") or "").strip()
        if not n:
            continue
        if it["platform"] == "youtube":
            yt[R.norm_key(n)].add(n)
        else:
            h = (pd.get("owner_handle") or "").strip().lstrip("@")
            if h:
                ig.setdefault((R.norm_key(h), R.norm_key(n)), (h, n))
    for (hk, nk) in sorted(ig):
        if len(hk) < CRE_MIN_KEY or len(nk) < CRE_MIN_KEY or hk == nk or hk.isdigit() or nk not in yt:
            continue
        name = sorted(yt[nk])[0]
        if common is not None and common(hk):
            continue
        entries.append({"type": "cre", "dir": "handle_to_channel", "key_norm": hk, "value": toks(name)[:6]})
    # collection / playlist name -> its items' most distinctive library terms
    members = collections.defaultdict(list)
    for it, _, ts in rows:
        for c in sorted(set(it["platform_data"].get("collections") or [])):
            if c != L.WATCH_LATER:
                members[c].append(ts)
    for c in sorted(members):
        m = members[c]
        name = toks(c)
        if len(m) < COL_MIN_ITEMS or not name or len(name) > COL_MAX_NAME_TOKENS:
            continue
        if not any(x not in STOP and len(x) >= 3 for x in name):
            continue
        din = collections.Counter()
        for ts in m:
            din.update(ts)
        need = max(COL_MIN_DF, int(np.ceil(COL_MIN_SHARE * len(m))))
        cand = []
        for t, n in din.items():
            if n < need or not _alpha(t) or len(t) < 3 or t in STOP or t in name:
                continue
            lift = (n / len(m)) / (df[t] / N)
            if lift >= COL_MIN_LIFT:
                cand.append((-lift, -n, t))
        cand.sort()
        vals = [t for _, _, t in cand[:COL_K]]
        if vals:
            entries.append({"type": "col", "dir": "name_to_terms", "key": name, "value": vals, "n_items": len(m)})
    meta = {"version": C1_VERSION, "items_used": N, "friend_items_excluded": len(items) - N,
            "build_s": round(time.time() - t0, 1),
            "params": {"cap_chars": CAP_CHARS, "acr_len": ACR_LEN, "join_len": JOIN_LEN, "join_part_min": JOIN_PART_MIN,
                       "min_co": MIN_CO, "min_co_acr2": MIN_CO_ACR2, "min_df_phrase": MIN_DF_PHRASE, "min_p_token_given_phrase": MIN_P_GIVEN_PHRASE, "min_lift": MIN_LIFT,
                       "cre_min_key": CRE_MIN_KEY, "col": [COL_MIN_ITEMS, COL_K, COL_MIN_SHARE, COL_MIN_DF,
                                                           COL_MIN_LIFT, COL_MAX_NAME_TOKENS],
                       "pv_k": PV_K, "pv_max_tokens": PV_MAX_TOKENS, "pv_w": PV_W},
            "sizes": dict(collections.Counter(f"{e['type']}:{e['dir']}" for e in entries))}
    return {"meta": meta, "entries": entries}


class VocabMap:
    def __init__(self, m):
        self.meta = m["meta"]
        self.entries = m["entries"]
        self.phrase = collections.defaultdict(list)  # first token -> [(key tuple, entry)]
        self.handle = {}
        for e in self.entries:
            if e["type"] == "cre":
                self.handle[e["key_norm"]] = e
            else:
                self.phrase[e["key"][0]].append((tuple(e["key"]), e))

    def match(self, query):
        """[(entry, span)] of every key in the raw search (phrase keys as consecutive tokens; handle keys as a
        normalised concatenation of 1-3 consecutive tokens)."""
        q = toks(query)
        out = []
        for i, t in enumerate(q):
            for key, e in self.phrase.get(t, []):
                if tuple(q[i:i + len(key)]) == key:
                    out.append((e, (i, i + len(key))))
            for j in range(i + 1, min(len(q), i + 3) + 1):
                k = R.norm_key("".join(q[i:j]))
                if k in self.handle:
                    out.append((self.handle[k], (i, j)))
        return out

    def expand(self, query, bq):
        """(extra BM25 string, info). At most PV_K entries (type order cre, acr, join, col; longer span first),
        tokens not already in the raw search or the BM25 string, at most PV_MAX_TOKENS tokens."""
        m = self.match(query)
        m.sort(key=lambda x: (TYPE_ORDER.index(x[0]["type"]), -(x[1][1] - x[1][0]), x[1][0],
                              " ".join(x[0]["value"])))
        have = set(toks(query)) | set(toks(bq))
        used, extra, types = [], [], []
        for e, _ in m:
            if len(used) >= PV_K:
                break
            add = [t for t in e["value"] if t not in have and t not in extra]
            if not add or len(extra) + len(add) > PV_MAX_TOKENS:
                continue
            used.append(e)
            extra += add
            types.append(f"{e['type']}:{e['dir']}")
        return " ".join(extra), {"fired": bool(extra), "n_matches": len(m), "n_entries": len(used), "types": types,
                                 "n_tokens": len(extra)}


def save_map(m):
    os.makedirs(WORK, exist_ok=True)
    json.dump(m, open(MAP_PATH, "w"), indent=0, ensure_ascii=False)


def load_map():
    return VocabMap(json.load(open(MAP_PATH, encoding="utf-8")))


def bm25_weighted(bm, bq, extra, keep, w=PV_W, depth=1000):
    """yt_lib.BM25.rank on score(bq) + w * score(extra) (c92_lib.bm25_weighted with the C1 weight)."""
    s = bm.scores(bq) if bq.strip() else np.zeros(len(bm.keys), np.float32)
    s = s + w * bm.scores(extra)
    s[s <= 0] = -np.inf
    order = np.argsort(-s)
    out = []
    for n in order:
        if not np.isfinite(s[n]):
            break
        k = bm.keys[n]
        if keep is None or keep(k):
            out.append(k)
            if len(out) >= depth:
                break
    return out


_ = F  # creator_key etc. available to callers
