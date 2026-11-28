"""PROTOTYPE ONLY - round 7 shared code (LOG.md "Round 7 fixed parameters", rows Y7-H0 ... Y7-H6).

  Facets       H2: format (8 classes, multinomial LR) and tone (9 binary LR) classifiers over 3-large item vectors,
               trained only on te-v1c kind / vibe; 80 / 20 hash split; per-item probabilities for every item.
  Router       H3: type (5) and platform (3) heads over the query's 3-large vector, trained only on syn-v1 searches.
  calibrate    H3: platform-share calibration, score * exp(0.5 * (q_g - 0.5)).
  Creators7    H3 / H4: creator profiles on 3-large own vectors (no te vectors, no LLM pick); H4 adds channel-type and
               era words to the profile text and affinity / era priors to the creator ranking.
  time_dir     H1: soft time direction (lexicon, or a window the E1 guard dropped).
  boost_top    H1 / H2: centred additive boosts on the top 300.
  qr_intent    H1: qr-v1 filters -> a qi-v3-shaped intent for c4_intent.guard_v43 / apply.
Method side only: never opens evals/labels/. Never prints query or item text.
"""
import collections
import datetime
import hashlib
import json
import os
import re
import sys
import time

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_intent as I  # noqa: E402
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import yt_lib as Y  # noqa: E402
from common import GENERIC, STOP, strip_tags  # noqa: E402
from corpus import DATA, fix_ws, rrf  # noqa: E402

R7 = os.path.join(DATA, "r7")
TODAY = "2026-10-30"
BOOST = 0.008
BOOST_DEPTH = 300
CAL_BETA = 0.5
C_GRID = (0.25, 1.0, 4.0)

FORMAT_CLASSES = ["howto", "review", "explainer", "vlog", "comedy", "music", "motivation", "other"]
KIND_TO_FORMAT = {"tutorial": "howto", "tips": "howto", "recipe": "howto", "art_process": "howto",
                  "review": "review", "product_ad": "review", "news_info": "explainer", "vlog": "vlog",
                  "travel": "vlog", "meme_joke": "comedy", "skit": "comedy", "music_dance": "music",
                  "motivation": "motivation", "other": "other", "pets_animals": "other"}
TONE_CLASSES = list(F.TONE_MAP)  # funny, cute_wholesome, serious, motivational, calm, intense, nostalgic, ...
SLOT_FORMAT = {"tutorial": "howto", "recipe": "howto", "review": "review", "explainer": "explainer", "vlog": "vlog",
               "skit_meme": "comedy", "music_performance": "music"}
ROUTER_TYPES = ["topic", "creator", "behaviour_time", "format", "vibe"]
ROUTER_PLATFORMS = ["ig", "yt", "both"]


def jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


# ---------------- 3-large item vectors (same ids and order as oai512) ----------------
def item_vectors_3l():
    d = os.path.join(L.EMB, G.STORE_3L)
    ids = json.load(open(os.path.join(d, "ids.json")))
    V = normalize(np.load(os.path.join(d, "emb.npy")).astype(np.float32))
    return ids, V


# ---------------- metrics ----------------
def ece(conf, correct, bins=10):
    conf, correct = np.asarray(conf, float), np.asarray(correct, float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return round(float(e), 4)


def held_out(code):
    """20% held out: the last two hex digits of sha256('r7|' + code) < 51 (51/256 = 19.9%)."""
    return int(hashlib.sha256(f"r7|{code}".encode()).hexdigest()[-2:], 16) < 51


def pick_c(X, y, multi, scorer, seed=7):
    """C from C_GRID by 5-fold CV on the training rows only."""
    skf = StratifiedKFold(5, shuffle=True, random_state=seed)
    best, res = None, {}
    for C in C_GRID:
        sc = []
        for tr, va in skf.split(X, y):
            m = LogisticRegression(C=C, max_iter=2000)
            m.fit(X[tr], y[tr])
            sc.append(scorer(y[va], m.predict(X[va])))
        res[C] = round(float(np.mean(sc)), 4)
        if best is None or res[C] > res[best]:
            best = C
    return best, res


def macro_f1(y, p):
    return f1_score(y, p, average="macro")


def bin_f1(y, p):
    return f1_score(y, p, zero_division=0)


# ---------------- H2: facet classifiers ----------------
def te_label_rows():
    """{code: (platform, te kind, set of te vibes)} for te-v1c ok rows (both platforms)."""
    out = {}
    for plat, p in (("instagram", os.path.join(DATA, "enrich", f"{L.TE_IG}.jsonl")),
                    ("youtube", os.path.join(DATA, "yt_enrich", f"{L.TE_YT}.jsonl"))):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if r.get("ok"):
                out[r["code"]] = (plat, (r.get("kind") or "").strip().lower(),
                                  {str(v).strip().lower() for v in r.get("vibe") or []})
    return out


def tone_positive(kind, vibes, cls):
    K, V, _ = F.TONE_MAP[cls]
    return kind in K or bool(vibes & V)


def train_facets(items, log=print):
    """Fits the format and tone facets on the training 80%, reports held-out quality, predicts every item.
    Writes r7/facets_quality.json and r7/facet_probs.npz (codes, P_format, P_tone). Returns the quality dict."""
    t0 = time.time()
    ids, V = item_vectors_3l()
    code_of_id = {it["id"]: L.code_of(it) for it in items}
    row = {code_of_id[i]: k for k, i in enumerate(ids) if i in code_of_id}
    te = te_label_rows()
    codes = [c for c in sorted(te) if c in row]
    X = V[[row[c] for c in codes]]
    plat = np.array([te[c][0] for c in codes])
    ho = np.array([held_out(c) for c in codes])
    q = {"n_te_rows_with_vector": len(codes), "held_out_share": round(float(ho.mean()), 4),
         "by_platform": {p: int((plat == p).sum()) for p in sorted(set(plat))}}
    # format
    fy = np.array([KIND_TO_FORMAT.get(te[c][1], "") for c in codes])
    fm = fy != ""
    tr, te_m = fm & ~ho, fm & ho
    C, cv = pick_c(X[tr], fy[tr], True, macro_f1)
    fmod = LogisticRegression(C=C, max_iter=2000).fit(X[tr], fy[tr])
    classes = list(fmod.classes_)
    P = fmod.predict_proba(X[te_m])
    pred = np.array(classes)[P.argmax(1)]
    yt = fy[te_m]
    fq = {"classes": FORMAT_CLASSES, "train_rows": int(tr.sum()), "held_out_rows": int(te_m.sum()), "C": C,
          "cv_macro_f1": cv, "accuracy": round(float((pred == yt).mean()), 4),
          "macro_f1": round(float(f1_score(yt, pred, average="macro")), 4),
          "majority_class_accuracy": round(float(max(collections.Counter(yt).values()) / len(yt)), 4),
          "ece_top_label": ece(P.max(1), pred == yt),
          "per_class_f1": {c: round(float(f1_score(yt == c, pred == c, zero_division=0)), 4) for c in classes},
          "held_out_class_share": {c: round(float((yt == c).mean()), 4) for c in classes}, "per_platform": {}}
    for p in sorted(set(plat)):
        m = plat[te_m] == p
        fq["per_platform"][p] = {"n": int(m.sum()), "accuracy": round(float((pred[m] == yt[m]).mean()), 4),
                                 "macro_f1": round(float(f1_score(yt[m], pred[m], average="macro")), 4)}
    q["format"] = fq
    log(f"format facet: C={C} acc {fq['accuracy']} macro-F1 {fq['macro_f1']} ({time.time() - t0:.0f} s)")
    # tone
    tm = np.array([bool(te[c][2]) for c in codes])
    tr_t, te_t = tm & ~ho, tm & ho
    Y_ = np.array([[tone_positive(te[c][1], te[c][2], k) for k in TONE_CLASSES] for c in codes])

    def mean_f1_all(C):
        skf = StratifiedKFold(5, shuffle=True, random_state=7)
        idx = np.flatnonzero(tr_t)
        sc = []
        for j in range(len(TONE_CLASSES)):
            y = Y_[idx, j]
            for a, b in skf.split(X[idx], y):
                m = LogisticRegression(C=C, max_iter=2000).fit(X[idx][a], y[a])
                sc.append(f1_score(y[b], m.predict(X[idx][b]), zero_division=0))
        return float(np.mean(sc))

    cvt = {C: round(mean_f1_all(C), 4) for C in C_GRID}
    Ct = max(cvt, key=cvt.get)
    tmods = [LogisticRegression(C=Ct, max_iter=2000).fit(X[tr_t], Y_[tr_t, j]) for j in range(len(TONE_CLASSES))]
    tq = {"classes": TONE_CLASSES, "train_rows": int(tr_t.sum()), "held_out_rows": int(te_t.sum()), "C": Ct,
          "cv_mean_f1": cvt, "per_class": {}}
    f1s, accs = [], []
    for j, k in enumerate(TONE_CLASSES):
        y = Y_[te_t, j]
        p = tmods[j].predict_proba(X[te_t])[:, 1]
        yh = p >= 0.5
        d = {"positive_share": round(float(y.mean()), 4), "accuracy": round(float((yh == y).mean()), 4),
             "f1": round(float(f1_score(y, yh, zero_division=0)), 4),
             "auc": round(float(roc_auc_score(y, p)), 4) if 0 < y.mean() < 1 else None,
             "brier": round(float(np.mean((p - y) ** 2)), 4), "ece": ece(p, y)}
        tq["per_class"][k] = d
        f1s.append(d["f1"])
        accs.append(d["accuracy"])
    tq["macro_f1"] = round(float(np.mean(f1s)), 4)
    tq["mean_accuracy"] = round(float(np.mean(accs)), 4)
    tq["per_platform_macro_f1"] = {}
    for p_ in sorted(set(plat)):
        m = plat[te_t] == p_
        tq["per_platform_macro_f1"][p_] = round(float(np.mean(
            [f1_score(Y_[te_t][m, j], tmods[j].predict_proba(X[te_t][m])[:, 1] >= 0.5, zero_division=0)
             for j in range(len(TONE_CLASSES))])), 4)
    q["tone"] = tq
    log(f"tone facet: C={Ct} macro-F1 {tq['macro_f1']} mean acc {tq['mean_accuracy']} ({time.time() - t0:.0f} s)")
    # predict every item with a vector
    all_codes = [code_of_id[i] for i in ids if i in code_of_id]
    Xa = V[[k for k, i in enumerate(ids) if i in code_of_id]]
    Pf = fmod.predict_proba(Xa)
    order = [classes.index(c) for c in FORMAT_CLASSES]
    Pf = Pf[:, order].astype(np.float32)
    Pt = np.stack([m.predict_proba(Xa)[:, 1] for m in tmods], 1).astype(np.float32)
    os.makedirs(R7, exist_ok=True)
    np.savez_compressed(os.path.join(R7, "facet_probs.npz"), codes=np.array(all_codes), P_format=Pf, P_tone=Pt)
    q["predicted_items"] = len(all_codes)
    q["predicted_format_share_by_platform"] = {}
    plat_of = {L.code_of(it): it["platform"] for it in items}
    pa = np.array([plat_of[c] for c in all_codes])
    for p_ in sorted(set(pa)):
        am = Pf[pa == p_].argmax(1)
        q["predicted_format_share_by_platform"][p_] = {c: round(float((am == n).mean()), 4)
                                                       for n, c in enumerate(FORMAT_CLASSES)}
        q.setdefault("predicted_tone_mean_by_platform", {})[p_] = {
            c: round(float(Pt[pa == p_, n].mean()), 4) for n, c in enumerate(TONE_CLASSES)}
    q["train_and_predict_s"] = round(time.time() - t0, 1)
    jdump(q, os.path.join(R7, "facets_quality.json"))
    return q


class Facets7:
    """Per-item facet probabilities (from facet_probs.npz)."""

    def __init__(self):
        z = np.load(os.path.join(R7, "facet_probs.npz"))
        self.row = {c: k for k, c in enumerate(z["codes"].tolist())}
        self.Pf, self.Pt = z["P_format"], z["P_tone"]

    def score(self, codes, facet):
        """facet = ('format', class) or ('tone', [classes]); returns array with nan for items without a vector."""
        out = np.full(len(codes), np.nan, np.float32)
        kind, val = facet
        for n, c in enumerate(codes):
            r = self.row.get(c)
            if r is None:
                continue
            if kind == "format":
                out[n] = self.Pf[r, FORMAT_CLASSES.index(val)]
            else:
                out[n] = max(self.Pt[r, TONE_CLASSES.index(v)] for v in val)
        return out


def active_facets(slots):
    """H2 mapping: guarded qs-v1 slots -> [('format', class)] + [('tone', [classes])]."""
    out = []
    fv = slots["format"]["value"]
    if fv in SLOT_FORMAT:
        out.append(("format", SLOT_FORMAT[fv]))
    tv = [v for v in slots["tone"]["values"] if v in TONE_CLASSES]
    if tv:
        out.append(("tone", tv))
    return out


# ---------------- boosts on the top 300 ----------------
def centred(x):
    """x with nan for missing; returns x - mean(non-missing) with missing -> 0."""
    m = ~np.isnan(x)
    out = np.zeros(len(x), np.float32)
    if m.any():
        out[m] = x[m] - x[m].mean()
    return out


def boost_top(order, scores, add):
    """add: array over order[:BOOST_DEPTH] of additive terms (already scaled). Stable re-sort of the head."""
    head = order[:BOOST_DEPTH]
    new = {c: scores[c] + float(a) for c, a in zip(head, add)}
    head2 = sorted(head, key=lambda c: -new[c])
    sc2 = dict(scores)
    sc2.update(new)
    return head2 + order[BOOST_DEPTH:], sc2


# ---------------- H1: qr-v1 filters -> intent; soft time ----------------
INTER_FLAG = {"save": "saved", "collection": "saved", "like": "liked", "share_self": "shared",
              "share_friend": "shared"}


def qr_intent(parse):
    f = parse.get("filters") or {}
    i = dict(I.NONE)
    i["after"], i["before"] = f.get("after"), f.get("before")
    i["require"] = sorted({INTER_FLAG[x] for x in f.get("interactions") or [] if x in INTER_FLAG})
    return i


OLD_RX = re.compile(
    r"\b(a )?long time ago\b|\bwhile (ago|back)\b|\bages ago\b|\bway back\b|\bback in the days?\b|\bback then\b"
    r"|\byears ago\b|\bold (videos?|vids?|reels?|posts?|stuff|clips?|ones?)\b|\b(oldest|earliest)\b|\bthrowback\b"
    r"|\bused to (watch|like|love|save)\b|\bwhen i was (a kid|younger|little|in (high|middle|elementary|primary) "
    r"school)\b|\bchildhood\b|\bforever ago\b|\bfirst (saw|watched|saved|found)\b", re.IGNORECASE)
NEW_RX = re.compile(
    r"\b(recently|recent|lately)\b|\bthe other day\b|\bjust (saw|watched|saved|liked|found)\b|\b(newest|latest)\b"
    r"|\bnew (videos?|vids?|reels?|posts?|ones?)\b|\bthese days\b|\bnowadays\b", re.IGNORECASE)


def lexicon_dir(query):
    o, n = bool(OLD_RX.search(query or "")), bool(NEW_RX.search(query or ""))
    return "old" if o and not n else "new" if n and not o else None


def _d(s):
    return datetime.date.fromisoformat(s)


def time_dir(query, raw_intent, guarded):
    """(direction, source). A soft direction only when the guarded intent keeps no window."""
    if guarded["after"] or guarded["before"]:
        return None, "window_kept"
    d = lexicon_dir(query)
    if d:
        return d, "lexicon"
    if raw_intent["after"] or raw_intent["before"]:
        lo = _d(raw_intent["after"] or "2015-01-01")
        hi = _d(raw_intent["before"] or TODAY)
        mid = lo + (hi - lo) / 2
        today = _d(TODAY)
        if mid < today - datetime.timedelta(days=365):
            return "old", "dropped_window"
        if mid >= today - datetime.timedelta(days=120):
            return "new", "dropped_window"
    return None, None


class TimePct:
    """Percentile of each item's first / last dated interaction among items with one (needs c4_intent.prepare)."""

    def __init__(self, S):
        first = np.array([x if x and x != "9999" else "" for x in S.firsti])
        last = np.array(S.last)
        self.first = self._pct(first)
        self.last = self._pct(last)

    @staticmethod
    def _pct(a):
        out = np.full(len(a), np.nan, np.float32)
        m = a != ""
        if m.any():
            vals = a[m]
            order = np.argsort(vals, kind="stable")
            r = np.empty(len(vals))
            r[order] = np.arange(len(vals))
            # ties get the mean rank
            _, inv = np.unique(vals, return_inverse=True)
            sums = np.bincount(inv, r)
            cnt = np.bincount(inv)
            out[m] = (sums / cnt)[inv] / max(len(vals) - 1, 1)
        return out

    def u(self, S, codes, direction):
        idx = [S.pos[c] for c in codes]
        if direction == "old":
            return 1.0 - self.first[idx]
        return self.last[idx]


# ---------------- H3: router ----------------
class Router:
    def __init__(self):
        z = np.load(os.path.join(R7, "router.npz"))
        self.Wt, self.bt, self.Wp, self.bp = z["Wt"], z["bt"], z["Wp"], z["bp"]

    @staticmethod
    def _soft(x):
        x = x - x.max()
        e = np.exp(x)
        return e / e.sum()

    def predict(self, v):
        pt = self._soft(self.Wt @ v + self.bt)
        pp = self._soft(self.Wp @ v + self.bp)
        return {"type": ROUTER_TYPES[int(pt.argmax())], "p_type": {k: round(float(x), 4) for k, x in zip(ROUTER_TYPES, pt)},
                "p_platform": {k: round(float(x), 4) for k, x in zip(ROUTER_PLATFORMS, pp)}}


def train_router(log=print):
    """Embeds syn-v1 searches (3-large, cached store r7_synth_3l), fits both heads on the training 80%, reports the
    held-out 20%, writes r7/router.npz and r7/router_quality.json."""
    rows = [json.loads(line) for line in open(os.path.join(R7, "synth_searches.jsonl"), encoding="utf-8")]
    qv = G.QueryVecs3L("r7_synth_3l")
    X = qv.get([r["text"] for r in rows])
    cells = np.array([r["cell"] for r in rows])
    yt_ = np.array([r["type"] for r in rows])
    yp = np.array([r["platform"] for r in rows])
    rng = np.random.RandomState(7)
    ho = np.zeros(len(rows), bool)
    for c in sorted(set(cells)):
        idx = np.flatnonzero(cells == c)
        rng.shuffle(idx)
        ho[idx[:int(round(0.2 * len(idx)))]] = True
    q = {"n_searches": len(rows), "held_out": int(ho.sum()), "train": int((~ho).sum())}
    heads = {}
    for name, y, classes in (("type", yt_, ROUTER_TYPES), ("platform", yp, ROUTER_PLATFORMS)):
        C, cv = pick_c(X[~ho], y[~ho], True, macro_f1)
        m = LogisticRegression(C=C, max_iter=3000).fit(X[~ho], y[~ho])
        order = [list(m.classes_).index(k) for k in classes]
        W, b = m.coef_[order], m.intercept_[order]
        P = m.predict_proba(X[ho])[:, order]
        pred = np.array(classes)[P.argmax(1)]
        yh = y[ho]
        conf = {a: {b_: int(((yh == a) & (pred == b_)).sum()) for b_ in classes} for a in classes}
        q[name] = {"C": C, "cv_macro_f1": cv, "accuracy": round(float((pred == yh).mean()), 4),
                   "macro_f1": round(float(f1_score(yh, pred, average="macro")), 4),
                   "ece_top_label": ece(P.max(1), pred == yh), "confusion_rows_true_cols_pred": conf,
                   "per_class_f1": {k: round(float(f1_score(yh == k, pred == k, zero_division=0)), 4) for k in classes}}
        heads[name] = (W, b)
        log(f"router {name}: C={C} held-out acc {q[name]['accuracy']} macro-F1 {q[name]['macro_f1']}")
    # platform calibration quantity q_g on held-out: mean q of the true platform, ig/yt cells only
    Wp, bp = heads["platform"]
    Pp = np.array([Router._soft(Wp @ x + bp) for x in X[ho]])
    qig = Pp[:, 0] + Pp[:, 2] / 2
    q["platform"]["mean_q_true_group"] = {
        "ig": round(float(qig[yp[ho] == "ig"].mean()), 4), "yt": round(float((1 - qig)[yp[ho] == "yt"].mean()), 4),
        "both_mean_abs_q_minus_half": round(float(np.abs(qig[yp[ho] == "both"] - 0.5).mean()), 4)}
    np.savez(os.path.join(R7, "router.npz"), Wt=heads["type"][0], bt=heads["type"][1], Wp=heads["platform"][0],
             bp=heads["platform"][1])
    jdump(q, os.path.join(R7, "router_quality.json"))
    return q


def calibrate(order, scores, group, p_platform):
    """H3: score' = score * exp(beta * (q_g - 0.5)); q_ig = p_ig + p_both / 2, q_yt = p_yt + p_both / 2.
    group: {code: 'ig' | 'yt'} built once from the items' source attribute."""
    q = {"ig": p_platform["ig"] + p_platform["both"] / 2, "yt": p_platform["yt"] + p_platform["both"] / 2}
    mult = {g: float(np.exp(CAL_BETA * (v - 0.5))) for g, v in q.items()}
    sc = {c: scores[c] * mult.get(group.get(c), 1.0) for c in order}
    new = sorted(order, key=lambda c: -sc[c])
    return new, sc, {"q_ig": round(q["ig"], 4), "mult_ig": round(mult["ig"], 4), "mult_yt": round(mult["yt"], 4)}


# ---------------- H3 / H4: creators on 3-large vectors ----------------
FORMAT_WORDS = {"howto": "tutorial tutorials how to guide tips lessons", "review": "review reviews reviewer unboxing",
                "explainer": "explainer explained news analysis documentary",
                "vlog": "vlog vlogs vlogger daily life travel", "comedy": "funny comedy skits sketches memes",
                "music": "music songs covers dance", "motivation": "motivation motivational mindset"}
TONE_WORDS = {"funny": "funny comedy humor", "cute_wholesome": "cute wholesome", "serious": "serious",
              "motivational": "motivational inspiring", "calm": "calm relaxing chill", "intense": "intense epic",
              "nostalgic": "nostalgic retro", "emotional": "emotional sad", "informative": "informative educational"}
_W = re.compile(r"[^\W\d_]{3,}")


def pct_rank(vals):
    vals = np.asarray(vals, float)
    order = np.argsort(vals, kind="stable")
    r = np.empty(len(vals))
    r[order] = np.arange(len(vals))
    _, inv = np.unique(vals, return_inverse=True)
    r = (np.bincount(inv, r) / np.bincount(inv))[inv]
    return r / max(len(vals) - 1, 1)


class Creators7:
    """F2's creator machinery on 3-large own vectors. enriched=True adds H4's channel-type / era words and priors."""

    def __init__(self, S, te_rows, facets=None, enriched=False):
        t0 = time.time()
        self.enriched = enriched
        self.of = {}
        members = collections.defaultdict(list)
        names, handles = {}, {}
        for it, c in zip(S.items, S.codes):
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
        # interactions per creator (H4)
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
            self.aff = pct_rank(np.log1p(n_inter))
            self.has_date = np.array([bool(x) for x in last])
            self.last_pct = np.zeros(len(self.keys))
            la = np.array(last)[self.has_date]
            self.last_pct[self.has_date] = pct_rank(np.unique(la, return_inverse=True)[1])
        texts = {}
        self.n_typed, self.n_era = 0, 0
        pos = S.pos
        for k in self.keys:
            tops, kinds, vibes, tags, words = (collections.Counter() for _ in range(5))
            for c in self.members[k]:
                it = S.items[pos[c]]
                r = te_rows.get(c)
                if r:
                    tops.update(set(r["topics"]))
                    if r["kind"] and r["kind"] not in ("unknown", "other"):
                        kinds[r["kind"]] += 1
                    vibes.update(set(r["vibe"]))
                for h in {x.lower() for x in it["platform_data"].get("hashtags") or []}:
                    if h not in GENERIC and len(h) >= 3:
                        tags[h] += 1
                words.update({t for t in _W.findall(strip_tags(it.get("caption") or "").lower()) if t not in STOP})
            h = handles.get(k, "")
            parts = [names.get(k, ""), h, L._ninja(h) if h else "", " ".join(x for x, _ in tops.most_common(15)),
                     " ".join(x for x, _ in kinds.most_common(3)).replace("_", " "),
                     " ".join(x for x, _ in vibes.most_common(5)), " ".join(x for x, _ in tags.most_common(10)),
                     " ".join(x for x, _ in words.most_common(20))]
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
        self.names = names
        self.bm = Y.BM25(texts)
        self.build_s = time.time() - t0

    def _channel_words(self, k, facets):
        rows = [facets.row[c] for c in self.members[k] if c in facets.row]
        if not rows:
            return ""
        am = facets.Pf[rows].argmax(1)
        cnt = collections.Counter(am.tolist())
        top, n = cnt.most_common(1)[0]
        out = []
        if FORMAT_CLASSES[top] != "other" and n / len(rows) >= 0.4:
            out.append(FORMAT_WORDS[FORMAT_CLASSES[top]])
        mt = facets.Pt[rows].mean(0)
        out += [TONE_WORDS[c] for j, c in enumerate(TONE_CLASSES) if mt[j] >= 0.4]
        return " ".join(out)

    def rank(self, QV, dense_texts, bm_query, item_order, direction=None):
        lists = []
        texts = [t for t in dense_texts if t]
        if texts:
            Qv = QV.get(texts)
            s = (self.P @ Qv.T).max(axis=1)
            s[~self.hasvec] = -np.inf
            order = np.argsort(-s)[:F.DEPTH]
            lists.append([self.keys[n] for n in order if np.isfinite(s[n])])
        lists.append(self.bm.rank(bm_query, depth=F.DEPTH) if bm_query.strip() else [])
        best, seen = [], set()
        for c in item_order[:F.DEPTH]:
            k = self.of.get(c)
            if k and k not in seen:
                seen.add(k)
                best.append(k)
        lists.append(best)
        lists = [x for x in lists if x]
        if not self.enriched:
            return rrf(*lists)
        sc = F._rrf_scores(lists)
        base = rrf(*lists)
        out = {}
        for k in base:
            j = self.idx[k]
            e = 0.0
            if direction and self.has_date[j]:
                e = (1 - self.last_pct[j]) if direction == "old" else self.last_pct[j]
            out[k] = sc[k] * (1 + 0.3 * self.aff[j]) * (1 + 0.3 * e)
        return sorted(base, key=lambda k: -out[k])

    def item_list(self, S, ranking, item_order, Qv, keep, per=5, top=200):
        return F.Creators.item_list(self, S, ranking, item_order, Qv, keep, per, top)
