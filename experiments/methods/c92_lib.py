"""PROTOTYPE ONLY - round 9.2 Track 1 (per-facet routing) shared code (LOG.md "Round 9.2 fixed parameters", rows
Y9.2-B1, Y9.2-B2, Y9.2-B3).

Base Q8 (q8-v1, = runs/r9.1/q8ref_r{k}). Each arm changes one thing:
  B1  b1-v1: named-creator lookup (code only). A literal library creator name / handle in the RAW search adds one
      list of that creator's items (ordered by the search's own dense score) at RRF weight 1.0.
  B2  b2-v1: soft time window from explicit time words (code only). In-window items' fused scores x 1.15.
  B3  b3-v1: additive intent frame. Q8's qr-v1 plan kept; the cached qi-v1 frame adds item_language as one dense
      phrase and its subject words as BM25 terms at weight 0.5 (rewrite path only).
Rule 6: the frame is an LLM-filled, schema-validated form (round 9.1's qi-v1); code builds every search string.
Method side only: never opens evals/labels/ or eval_work/; never reads a search timestamp. Prints aggregates only.
"""
import bisect
import collections
import datetime
import hashlib
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c7_lib as H  # noqa: E402
import c81_lib as R  # noqa: E402
import c91t_lib as A  # noqa: E402
from common import STOP  # noqa: E402
from corpus import DATA  # noqa: E402

B1_VERSION, B2_VERSION, B3_VERSION = "b1-v1", "b2-v1", "b3-v1"
CACHE_DIR = os.path.join(DATA, "cache", "r9.2")

# ---------------- B1: named-creator lookup ----------------
B1_MIN_KEY, B1_MAX_NGRAM, B1_DF_COMMON, B1_MAX_CREATORS, B1_W = 5, 4, 50, 3, 1.0
_BMTOK = re.compile(r"(?u)\b\w\w+\b")  # the BM25 tokeniser (yt_lib.BM25)


class CreatorNames:
    """{name key: sorted creator keys}; member rows; the common-word table. Deterministic (sorted iteration)."""

    def __init__(self, S):
        members = collections.defaultdict(list)
        friend = set()
        names = collections.defaultdict(set)  # creator key -> its name keys
        for it, c in zip(S.items, S.codes):  # corpus file order
            k = F.creator_key(it)
            if not k:
                continue
            members[k].append(c)
            pd = it["platform_data"]
            if (pd.get("owner_relation") or "") == "mutual":
                friend.add(k)
            for s in (pd.get("owner_handle"), pd.get("owner_name")):
                n = R.norm_key(str(s or "").strip().lstrip("@"))
                if len(n) >= B1_MIN_KEY and not n.isdigit():
                    names[k].add(n)
        self.table = collections.defaultdict(set)
        for k in sorted(names):
            if k in friend:
                continue
            for n in sorted(names[k]):
                self.table[n].add(k)
        self.table = {n: sorted(ks) for n, ks in sorted(self.table.items())}
        self.n_items = {k: len(m) for k, m in members.items()}
        self.member_rows = {k: sorted(S.row_of[c] for c in members[k] if c in S.row_of) for k in sorted(members)}
        self.n_friend_excluded = len(friend)
        # common words: in STOP, < 3 chars, or in the text of >= 50 items whose own creator's name keys lack it
        item_keys = {}
        for it, c in zip(S.items, S.codes):
            k = F.creator_key(it)
            item_keys[c] = " ".join(sorted(names.get(k, ()))) if k else ""
        other = collections.Counter()
        for c in sorted(S.text):
            own = item_keys.get(c, "")
            for t in sorted(set(R.TOK.findall(S.text[c].lower()))):
                if t not in own:
                    other[t] += 1
        self.df_other = other

    def common(self, t):
        return t in STOP or len(t) < 3 or self.df_other.get(t, 0) >= B1_DF_COMMON

    def match(self, query):
        """[(name key, [creator keys], n-gram span)] accepted, longest key first, non-overlapping."""
        toks = R.TOK.findall(" ".join((query or "").lower().split()))
        cands = []
        for i in range(len(toks)):
            for j in range(i + 1, min(len(toks), i + B1_MAX_NGRAM) + 1):
                key = R.norm_key("".join(toks[i:j]))
                if key in self.table and not all(self.common(t) for t in toks[i:j]):
                    cands.append((-len(key), i, j, key))
        cands.sort()
        used, out = set(), []
        for _, i, j, key in cands:
            if used & set(range(i, j)):
                continue
            used |= set(range(i, j))
            out.append((key, self.table[key], (i, j)))
        return out

    def creators(self, query):
        m = self.match(query)
        ck = {}
        for key, ks, _ in m:
            for k in ks:
                ck[k] = max(ck.get(k, 0), len(key))
        ranked = sorted(ck, key=lambda k: (-ck[k], -self.n_items.get(k, 0), k))[:B1_MAX_CREATORS]
        return ranked, m

    def item_list(self, S, creators, s, keep):
        rows = sorted({r for k in creators for r in self.member_rows.get(k, [])})
        rows = [r for r in rows if S.gate[r] and (keep is None or keep(S.vcodes[r]))]
        if not rows:
            return []
        ra = np.array(rows, np.int64)
        o = np.argsort(-s[ra], kind="stable")  # ties -> lower vector row
        return [S.vcodes[ra[n]] for n in o[:F.DEPTH]]


def add_list(order, sc, lst, w):
    """F(i) + w / (60 + r + 1) for the list's items; insertion order the fused order's, then new items."""
    if not lst:
        return order, sc
    out = dict(sc)
    for r, c in enumerate(lst[:F.DEPTH]):
        out[c] = out.get(c, 0.0) + w / (F.K_RRF + r + 1)
    return [c for c, _ in sorted(out.items(), key=lambda x: -x[1])], out


# ---------------- B2: soft time window ----------------
B2_MULT, B2_RECENT_DAYS, B2_OLD_DAYS = 1.15, 90, 730
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]
_MON = {m: n + 1 for n, m in enumerate(_MONTHS)} | {"sept": 9}
_MRX = "|".join(sorted(_MON, key=len, reverse=True))
_NUMW = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "few": 3, "a few": 3, "couple": 2, "a couple": 2, "couple of": 2, "a couple of": 2}
_UNIT = {"day": 1, "week": 7, "month": 30, "year": 365}
_N = r"(\d{1,2}|a couple of|a couple|couple of|couple|a few|few|an|a|one|two|three|four|five|six|seven|eight|nine|ten)"
_YEAR = r"(?<![\d#])(20[01]\d|202[0-6])(?!\d)"
RX_MONTH_YEAR = re.compile(rf"\b({_MRX})\s+(?:of\s+)?{_YEAR}")
RX_DECADE = re.compile(r"(?<![\d#])(20[012]0)'?s\b")
RX_YEAR = re.compile(_YEAR)
RX_MONTH_CTX = re.compile(rf"\b(in|during|last|this|since|from|early|late|mid|around)\s+({_MRX})\b")
RX_AGO = re.compile(rf"\b{_N}\s+(day|week|month|year)s?\s+ago\b")
RX_LASTN = re.compile(rf"\b(?:last|past)\s+{_N}\s+(day|week|month|year)s?\b")
RX_REL = re.compile(r"\b(last year|this year|last month|this month|last week|past week|this week|yesterday|today|"
                    r"tonight)\b")
RX_NEW = re.compile(r"\b(recently|recent|lately|the other day|these days)\b|\bjust (saw|watched|saved|liked|found)\b")


def _date(s):
    return datetime.date.fromisoformat(s)


def _iso(d):
    return d.isoformat()


def _month_range(y, m):
    lo = datetime.date(y, m, 1)
    hi = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
    return lo, hi


def parse_time(query, ref):
    """[(kind, window)] from explicit / vague time words; window = ("range", lo, hi) ISO strings or ("moy", m)."""
    q = " ".join((query or "").lower().split())
    out = []
    used = []

    def take(m):
        used.append(m.span())

    def free(m):
        a, b = m.span()
        return not any(a < y and x < b for x, y in used)

    for m in RX_MONTH_YEAR.finditer(q):
        lo, hi = _month_range(int(m.group(2)), _MON[m.group(1)])
        out.append(("month_year", ("range", _iso(lo), _iso(hi))))
        take(m)
    for m in RX_DECADE.finditer(q):
        if free(m):
            y = int(m.group(1))
            out.append(("decade", ("range", f"{y}-01-01", f"{y + 9}-12-31")))
            take(m)
    for m in RX_YEAR.finditer(q):
        if free(m):
            y = int(m.group(1))
            out.append(("year", ("range", f"{y}-01-01", f"{y}-12-31")))
            take(m)
    for m in RX_MONTH_CTX.finditer(q):
        if not free(m):
            continue
        w, mo = m.group(1), _MON[m.group(2)]
        if w == "last":
            y = ref.year if mo < ref.month else ref.year - 1
            lo, hi = _month_range(y, mo)
            out.append(("month_last", ("range", _iso(lo), _iso(hi))))
        elif w == "this":
            lo, hi = _month_range(ref.year, mo)
            out.append(("month_this", ("range", _iso(lo), _iso(min(hi, ref)))))
        else:
            out.append(("month_any_year", ("moy", mo)))
        take(m)
    for m in RX_AGO.finditer(q):
        if not free(m):
            continue
        u = _UNIT[m.group(2)]
        nw = m.group(1)
        if nw in ("few", "a few", "couple", "a couple", "couple of", "a couple of"):
            lo_n, hi_n = 4, 1
        else:
            n = int(nw) if nw.isdigit() else _NUMW[nw]
            lo_n, hi_n = n + 1, max(n - 1, 0)
        out.append(("ago", ("range", _iso(ref - datetime.timedelta(days=lo_n * u)),
                            _iso(ref - datetime.timedelta(days=hi_n * u)))))
        take(m)
    for m in RX_LASTN.finditer(q):
        if not free(m):
            continue
        nw = m.group(1)
        n = int(nw) if nw.isdigit() else _NUMW[nw]
        out.append(("last_n", ("range", _iso(ref - datetime.timedelta(days=n * _UNIT[m.group(2)])), _iso(ref))))
        take(m)
    for m in RX_REL.finditer(q):
        if not free(m):
            continue
        w = m.group(1)
        if w == "last year":
            win = ("range", f"{ref.year - 1}-01-01", f"{ref.year - 1}-12-31")
        elif w == "this year":
            win = ("range", f"{ref.year}-01-01", _iso(ref))
        elif w == "last month":
            y, mo = (ref.year, ref.month - 1) if ref.month > 1 else (ref.year - 1, 12)
            lo, hi = _month_range(y, mo)
            win = ("range", _iso(lo), _iso(hi))
        elif w == "this month":
            win = ("range", _iso(datetime.date(ref.year, ref.month, 1)), _iso(ref))
        elif w in ("last week", "past week"):
            win = ("range", _iso(ref - datetime.timedelta(days=14)), _iso(ref))
        elif w == "this week":
            win = ("range", _iso(ref - datetime.timedelta(days=7)), _iso(ref))
        else:
            win = ("range", _iso(ref - datetime.timedelta(days=3)), _iso(ref))
        out.append(("relative", win))
        take(m)
    if out:
        return out
    new, old = bool(RX_NEW.search(q)), bool(H.OLD_RX.search(q))
    if new and not old:
        return [("vague_new", ("range", _iso(ref - datetime.timedelta(days=B2_RECENT_DAYS)), _iso(ref)))]
    if old and not new:
        return [("vague_old", ("range", "0000-01-01", _iso(ref - datetime.timedelta(days=B2_OLD_DAYS))))]
    return []


class ItemDates:
    """Sorted ISO dates per item code: first_seen_at + every interaction `at` (no search timestamps)."""

    def __init__(self, S):
        d = collections.defaultdict(set)
        for it, c in zip(S.items, S.codes):
            a = (it.get("first_seen_at") or "")[:10]
            if len(a) == 10:
                d[c].add(a)
        code_of_id = {it["id"]: c for it, c in zip(S.items, S.codes)}
        for line in open(os.path.join(DATA, "corpus", "interactions.jsonl")):
            r = json.loads(line)
            c = code_of_id.get(r["item_id"])
            a = (r.get("at") or "")[:10]
            if c is not None and len(a) == 10:
                d[c].add(a)
        self.dates = {c: sorted(v) for c, v in d.items()}
        self.ref = _date(max(v[-1] for v in self.dates.values()))
        self.n_dated = len(self.dates)

    def in_window(self, c, wins):
        ds = self.dates.get(c)
        if not ds:
            return False
        for w in wins:
            if w[0] == "moy":
                mm = f"{w[1]:02d}"
                if any(x[5:7] == mm for x in ds):
                    return True
            else:
                i = bisect.bisect_left(ds, w[1])
                if i < len(ds) and ds[i] <= w[2]:
                    return True
        return False


def time_boost(order, sc, dates, wins):
    """In-window items x B2_MULT; stable re-sort (ties keep fused order). Returns (order, sc, n boosted)."""
    new, n = {}, 0
    for c in order:
        if dates.in_window(c, wins):
            new[c] = sc[c] * B2_MULT
            n += 1
        else:
            new[c] = sc[c]
    return sorted(order, key=lambda c: -new[c]), new, n


# ---------------- B3: additive frame (round 9.1 qi-v1 frames; new ones only where none is cached) ----------------
B3_BM_W = 0.5


class Frames:
    def __init__(self):
        self.r91 = {}
        p = os.path.join(A.CACHE_DIR, f"{A.FRAME_VERSION}.jsonl")
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            self.r91.setdefault(r["key"], r)
        self.own = {}
        self.own_path = os.path.join(CACHE_DIR, f"{A.FRAME_VERSION}.jsonl")
        if os.path.exists(self.own_path):
            for line in open(self.own_path, encoding="utf-8"):
                r = json.loads(line)
                self.own.setdefault(r["key"], r)

    @staticmethod
    def key(query, rep):
        body = {"model": A.FRAME_MODEL, "msgs": A.frame_messages(query), "rf": A.FRAME_FORMAT,
                "reasoning": A.FRAME_REASONING, "max": A.FRAME_MAX_TOKENS, "salt": str(rep)}
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def get(self, query, rep, allow_call=False):
        """(frame or None, rec or None, source)."""
        k = self.key(query, rep)
        rec, src = self.r91.get(k), "r9.1-t1"
        if rec is None:
            rec, src = self.own.get(k), "r9.2"
        if rec is None:
            if not allow_call:
                return None, None, "missing"
            G.CACHE = CACHE_DIR
            G._MEM.pop(A.FRAME_VERSION, None)
            rec = G.cached_chat(A.frame_messages(query), A.FRAME_FORMAT, A.FRAME_VERSION, "c92_frame", A.FRAME_MODEL,
                                A.FRAME_REASONING, A.FRAME_MAX_TOKENS, salt=rep)
            assert rec["key"] == k
            self.own[k] = rec
            src = "r9.2-new"
        fr, ok = A.validate_frame(rec["out"])
        return (fr if ok else None), rec, src


def b3_additions(fr, texts, bq):
    """(extra dense phrase or None, extra BM25 terms string) from a validated frame, code only."""
    il = fr["item_language"]
    low = {t.lower() for t in texts}
    extra_dense = il if il and il.lower() not in low else None
    have = set(_BMTOK.findall(bq.lower()))
    extra = []
    for t in _BMTOK.findall((fr["subject"]["text"] or "").lower()):
        if t not in STOP and t not in have and t not in extra:
            extra.append(t)
    return extra_dense, " ".join(extra)


def bm25_weighted(bm, bq, extra, keep, depth=1000):
    """yt_lib.BM25.rank on score(bq) + B3_BM_W * score(extra) (same tie handling)."""
    s = bm.scores(bq) if bq.strip() else np.zeros(len(bm.keys), np.float32)
    s = s + B3_BM_W * bm.scores(extra)
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
