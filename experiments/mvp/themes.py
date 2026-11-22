"""PROTOTYPE ONLY - round 12, D (DESIGN.md section 19.D): every watched item gets a theme, by code, from the library's
own item vectors; theme names come from one model call per field (a top cluster) on a sample of its titles.

Ported from docs/05-processor.md, stage 3 (the prototype's themes), with the changes a watch history of 100,000 videos
needs:
- The items: everything the person watched (watch or view events; friends' posts are not in the view). Their stored
  vectors (the ones the engine ranks with, history._vector_store: text-embedding-3-large at 1024, a demo library's
  int8 store or a research root's float16 store) are centred (the mean taken out), L2-normalised, cut to PCA_DIM
  dimensions by PCA, and normalised again ("centring was the key fix", docs/05).
- Two levels. Fields (broad: "Gaming"): one Ward tree on a fixed sample of SAMPLE items, k chosen at the biggest gap
  in the merge heights within FIELDS_K, every item then given to the nearest field centroid and a few rounds of
  spherical k-means over all of them (a Ward tree over 100,000 items does not fit in memory). Themes (narrow:
  "Minecraft builds") inside each field the same way, in the field's own centred PCA space (THEMES_K), with
  sub-groups under FOLD_MIN items folded into the nearest one.
- Names: one model call per field (prompt theme_name_v1), which names the field and each of its themes from a
  sample of their titles (the nearest NAME_NEAR to the centroid and NAME_RANDOM others) and the words code finds
  typical of each (share x log1p(lift), docs/05 step 6). Never a call per item. Titles are DATA in the prompt. A name
  the code finds sensitive (profile.sensitive on the name and its words) or the model marks sensitive is dropped:
  its items fall under no theme. A reply that fails the checks gets the code's own typical words as its name.
- Kept, versioned, rebuildable (AGENTS.md rule 2 and 10): <derived>/themes-v1/<library key>/build.json (the
  version, the embedding store, the parameters, the names, the counts) and space.npz (the transforms, the centroids,
  each vector-store row's field and theme), and themes.jsonl (the same rows with the version and the embedding model in
  each). Rebuilt only by `python3 -m mvp.themes build <library>` (a new version
  or a library that changed by more than REBUILD_SHARE); an item added later is given the nearest theme by code when
  the build is loaded, with the build's frozen transforms. Never built while a person waits.
"""
import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone

from . import config

VERSION = "themes-v2"            # v2: names by theme_name_v2 (a fixed category for each); v1 kept beside it
PROMPT_VERSION = "theme_name_v2"  # v1: names and words only ("gaming" then mapped to a third of the gaming themes)
CATEGORIES = ("gaming", "art and design", "music", "comedy", "film and tv", "sports", "fitness", "food and cooking",
              "travel", "science", "technology", "math", "education", "history", "nature and animals",
              "family and kids", "fashion and beauty", "vehicles", "diy and making", "internet culture", "news", "money",
              "health", "relationships", "politics", "religion", "other")
SENSITIVE_CATEGORIES = {"money", "health", "relationships", "politics", "religion"}
# the words a person uses for a category (a topic word that is one of these maps to the category's themes)
CATEGORY_WORDS = {"gaming": ("gaming", "games", "video games", "videogames", "gamer", "gameplay", "game"),
                  "art and design": ("art", "arts", "drawing", "painting", "design", "artwork"),
                  "music": ("music", "songs"), "comedy": ("comedy", "funny", "humor", "humour"),
                  "film and tv": ("movies", "films", "film", "tv", "shows", "series"),
                  "sports": ("sports", "sport"), "fitness": ("fitness", "workouts", "gym", "exercise"),
                  "food and cooking": ("food", "cooking", "recipes"), "travel": ("travel",),
                  "science": ("science",), "technology": ("tech", "technology"), "math": ("math", "maths",
                                                                                         "mathematics"),
                  "education": ("education", "learning", "studying"), "history": ("history",),
                  "nature and animals": ("nature", "animals", "pets"), "fashion and beauty": ("fashion", "beauty"),
                  "vehicles": ("cars", "vehicles"), "diy and making": ("diy", "making", "crafts"),
                  "internet culture": ("memes", "internet culture"), "news": ("news",)}
PCA_DIM, SUB_DIM = 24, 16
SAMPLE, SUB_SAMPLE = 6000, 2500
FIELDS_K, THEMES_K = (10, 20), (2, 7)
SUB_MIN = 80          # a field with fewer items is one theme
FOLD_MIN = 15         # sub-groups smaller than this (or 4% of the field) are folded into the nearest one
KMEANS_ROUNDS = 4
NAME_NEAR, NAME_RANDOM = 14, 10
REBUILD_SHARE = 0.25
SEED = 12
_LOCK = threading.Lock()
_LOADED = {}

STOPWORDS = set("""a an the and or but of to in on for with from by at as is are was were be been it its this that
these those i me my you your we our he she they them his her their what how why when where who which vs v ft feat
official video videos full hd 4k part ep episode new best top most more my first last day week year 2015 2016 2017
2018 2019 2020 2021 2022 2023 2024 2025 2026 shorts short reel reels live stream clip clips trailer just get got can
will do does did not no yes so if all any some one two three into out up down over about after before only also
watch watching like here there now then than very really much many make made makes making every each ever still
amp quot com www http https youtube instagram tiktok""".split())


def derived_home():
    return os.path.abspath(os.environ.get("MVP_DERIVED_HOME") or os.path.join(config.REPO, "data", "mvp", "derived"))


def lib_key(lib):
    return hashlib.sha1(os.path.abspath(lib).encode()).hexdigest()[:12]


def folder(lib):
    return os.path.join(derived_home(), VERSION, lib_key(lib))


def store_name(lib):
    """The name of the vector store history._vector_store reads (the embedding model of every row here)."""
    for name, f in (("oai3l_1024_q8", "q8.npy"), ("oai3l_1024", "emb.npy")):
        if os.path.exists(os.path.join(lib, "corpus", "emb", name, f)):
            return name
    return None


EMBEDDING_MODEL = {"oai3l_1024_q8": "text-embedding-3-large@1024 (int8)", "oai3l_1024": "text-embedding-3-large@1024"}


# ================================================================ maths (numpy only, plus scipy's Ward tree)
def _unit(m):
    import numpy as np
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def _rows(vs, ids):
    import numpy as np
    pos, mat, scale = vs
    rows = [pos[i] for i in ids]
    m = np.asarray(mat[rows], dtype=np.float32) if rows else np.zeros((0, mat.shape[1]), np.float32)
    if scale is not None:
        m = m * scale
    return _unit(m)


def _space(x, dim, rng):
    """(mean, components) of a centred PCA of x (rows already unit length), fitted on at most 20,000 rows."""
    import numpy as np
    mean = x.mean(0)
    s = x if len(x) <= 20000 else x[rng.choice(len(x), 20000, replace=False)]
    c = _unit(s - mean)
    dim = max(1, min(dim, c.shape[0] - 1, c.shape[1]))
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    return mean.astype(np.float32), vt[:dim].astype(np.float32)


def _project(x, mean, comps):
    return _unit(_unit(x - mean) @ comps.T)


def _ward_k(z, kr, rng, sample):
    """Labels of a sample of z cut from one Ward tree at the k within kr with the best silhouette (cosine), and the
    sample rows. (docs/05 chose k at the biggest gap in the merge heights; on the made-up library of
    tests/r12_library.py that rule cut at 3 and put four true themes into one; the silhouette kept them apart, and on
    the founder's library it chose a k inside the same range: DESIGN 19.D.)"""
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage
    from sklearn.metrics import silhouette_score
    idx = np.arange(len(z)) if len(z) <= sample else np.sort(rng.choice(len(z), sample, replace=False))
    zs = z[idx].astype(np.float64)
    lk = linkage(zs, method="ward")
    lo, hi = kr
    hi = min(hi, len(idx) - 1)
    best, bk, blab = -2.0, None, None
    for k in range(lo, hi + 1):
        lab = fcluster(lk, k, criterion="maxclust") - 1
        if len(set(lab.tolist())) < 2:
            continue
        sc = silhouette_score(zs, lab, metric="cosine")
        if sc > best + 1e-9:
            best, bk, blab = sc, int(lab.max()) + 1, lab
    if blab is None:
        blab = np.zeros(len(idx), dtype=np.int64)
        bk = 1
    return idx, blab, bk


def fields_k(n):
    """The range of the number of fields for n items: FIELDS_K for a large library (10 to 20 from 4,000 items), fewer
    for a small one (3 to 6 for 500)."""
    lo = max(3, min(FIELDS_K[0], n // 500))
    hi = max(lo + 3, min(FIELDS_K[1], n // 200))
    return lo, hi


def _kmeans(z, cent, rounds):
    import numpy as np
    lab = np.argmax(z @ cent.T, 1)
    for _ in range(rounds):
        new = np.stack([z[lab == j].mean(0) if (lab == j).any() else cent[j] for j in range(len(cent))])
        cent = _unit(new)
        lab = np.argmax(z @ cent.T, 1)
    return lab, cent


def _clusters(z, kr, rng, sample, fold_min):
    """(labels over all of z, centroids) for one level."""
    import numpy as np
    idx, lab, k = _ward_k(z, kr, rng, sample)
    cent = _unit(np.stack([z[idx[lab == j]].mean(0) for j in range(k)]))
    lab, cent = _kmeans(z, cent, KMEANS_ROUNDS)
    # fold the small ones into their nearest neighbour, then recompute
    while True:
        sizes = np.bincount(lab, minlength=len(cent))
        small = [j for j in range(len(cent)) if sizes[j] < fold_min]
        if not small or len(cent) - len(small) < 1:
            break
        keep = [j for j in range(len(cent)) if j not in small]
        cent = cent[keep]
        lab, cent = _kmeans(z, cent, 2)
    return lab, cent


# ================================================================ words typical of a group (docs/05 step 6)
_TOK = re.compile(r"[a-z][a-z0-9'+-]{2,}")


def _tokens(text):
    return {w.strip("'-") for w in _TOK.findall((text or "").lower()) if w.strip("'-") not in STOPWORDS}


def typical_words(texts_in, df_all, n_all, k=6):
    """Words by share-of-items x log1p(lift) within a group (docs/05, stage 3, step 6)."""
    import math
    c = Counter()
    for t in texts_in:
        c.update(_tokens(t))
    n = max(1, len(texts_in))
    out = []
    for w, f in c.items():
        if f < max(2, 0.02 * n):
            continue
        share = f / n
        lift = share / max(df_all.get(w, 0) / max(n_all, 1), 1e-9)
        out.append((share * math.log1p(lift), w))
    out.sort(reverse=True)
    return [w for _, w in out[:k]]


# ================================================================ names (one call per field)
NAME_WORDS_MAX = 5


def _check_name(name, top_channels):
    """The model's name, cleaned, or None when it fails the checks."""
    if not isinstance(name, str):
        return None
    s = " ".join(name.replace('"', "").replace("#", "").split()).strip(" .,:;-")
    if not s or len(s) > 40 or len(s.split()) > NAME_WORDS_MAX or "@" in s or "http" in s.lower():
        return None
    if s.lower() in {"videos", "clips", "shorts", "misc", "miscellaneous", "various", "other", "mixed"}:
        return None
    low = re.sub(r"\W+", "", s.lower())
    if any(low == re.sub(r"\W+", "", (c or "").lower()) for c in top_channels if c):
        return None   # a channel is not a theme
    return s[:1].upper() + s[1:]


def _check_words(words):
    out = []
    for w in words if isinstance(words, list) else []:
        if isinstance(w, str):
            w = " ".join(w.lower().replace("#", "").split())
            if 2 <= len(w) <= 30 and len(w.split()) <= 3 and "@" not in w and "http" not in w and w not in out:
                out.append(w)
    return out[:6]


def _fallback_name(words):
    return " ".join(words[:2]).capitalize() if words else None


def name_field(field_sample, groups, person=None, chat=None):
    """One model call: {"field": {...}, "groups": [{...}]} with names checked by code. `field_sample`: (titles,
    typical words, top channels); `groups`: the same for each theme inside it."""
    from . import llm
    from . import profile as P
    system = open(os.path.join(config.HERE, "prompts", f"{PROMPT_VERSION}.md"), encoding="utf-8").read()

    def block(label, titles, words):
        t = "\n".join("- " + " ".join((x or "").split())[:110] for x in titles)
        return f"{label}\nTypical words (code): {', '.join(words) or '(none)'}\n<titles>\n{t}\n</titles>"
    parts = [block("FIELD", field_sample[0], field_sample[1])]
    for n, (titles, words, _ch) in enumerate(groups, 1):
        parts.append(block(f"SUB-GROUP {n}", titles, words))
    user = "\n\n".join(parts)
    got, cost, err = None, 0.0, None
    try:
        got, cost = (chat or llm.chat_json)(system, user, purpose="mvp_theme_name", prompt_version=PROMPT_VERSION,
                                            person=person, max_tokens=900, temperature=0, seed=7)
    except Exception as e:  # noqa: BLE001 - the code's own words name it then
        err = type(e).__name__
    got = got if isinstance(got, dict) else {}

    def one(raw, sample):
        raw = raw if isinstance(raw, dict) else {}
        name = _check_name(raw.get("name"), sample[2])
        words = _check_words(raw.get("words"))
        cat = raw.get("category") if raw.get("category") in CATEGORIES else None
        source = "model"
        if name is None:
            name, source = _fallback_name(sample[1]), "code"
        sens = bool(raw.get("sensitive")) or cat in SENSITIVE_CATEGORIES or \
            P.sensitive(name, " ".join(words), " ".join(sample[1]))
        return {"name": None if sens else name, "words": [] if sens else words, "sensitive": sens,
                "category": None if sens else cat, "mixed": bool(raw.get("mixed")), "name_source": source}
    f = one(got.get("field"), field_sample)
    gl = got.get("groups") if isinstance(got.get("groups"), list) else []
    gs = [one(gl[k] if k < len(gl) else None, groups[k]) for k in range(len(groups))]
    # siblings with the same name stay apart here and are counted as one theme by name (facts.ItemFacts)
    return {"field": f, "groups": gs, "cost_usd": cost, "error": err}


# ================================================================ the build
def _watched_ids(view, lib):
    """The view's items with a watch or view event, in a fixed order."""
    path = os.path.join(lib, "corpus", "interactions.jsonl")
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") in ("watch", "view") and r.get("item_id") in view.items:
                seen.add(r["item_id"])
    return sorted(seen)


def build(lib, view=None, person=None, chat=None, log=print, now=None):
    """Clusters, names and writes the build. Returns build.json's content."""
    import numpy as np
    from .history import _vector_store
    from .libview import LibraryView
    t0 = time.monotonic()
    lib = os.path.abspath(lib)
    view = view or LibraryView(lib)
    vs = _vector_store(lib)
    if vs is None:
        raise RuntimeError("this library has no item vectors")
    pos = vs[0]
    ids = [i for i in _watched_ids(view, lib) if i in pos]
    if len(ids) < 30:
        raise RuntimeError("too few watched items with vectors to find themes")
    rng = np.random.default_rng(SEED)
    x = _rows(vs, ids)
    mean, comps = _space(x, PCA_DIM, rng)
    z = _project(x, mean, comps)
    flab, fcent = _clusters(z, fields_k(len(ids)), rng, SAMPLE, max(FOLD_MIN, int(0.005 * len(ids))))
    log(f"fields: {len(fcent)} over {len(ids)} items ({time.monotonic() - t0:.1f} s)")
    texts = [view.items[i].caption or "" for i in ids]
    df_all = Counter()
    for t in texts:
        df_all.update(_tokens(t))
    fields, themes, subspaces = [], [], []
    tlab = np.full(len(ids), -1, dtype=np.int32)
    cost = 0.0
    calls = 0
    for fj in range(len(fcent)):
        members = np.where(flab == fj)[0]
        if len(members) >= SUB_MIN:
            xf = x[members]
            m2, c2 = _space(xf, SUB_DIM, rng)
            zf = _project(xf, m2, c2)
            slab, scent = _clusters(zf, THEMES_K, rng, SUB_SAMPLE, max(FOLD_MIN, int(0.04 * len(members))))
        else:
            m2 = c2 = None
            zf = None
            slab, scent = np.zeros(len(members), dtype=np.int64), None
        subspaces.append((m2, c2, scent))
        groups = []
        first_theme = len(themes)
        for sj in range(int(slab.max()) + 1 if len(slab) else 0):
            sm = members[slab == sj]
            if not len(sm):
                continue
            tlab[sm] = len(themes)
            themes.append({"id": len(themes), "field": fj, "sub": sj, "n": int(len(sm))})
            groups.append((_sample(view, ids, sm, zf[slab == sj] if zf is not None else z[sm],
                                   scent[sj] if scent is not None else fcent[fj], rng),
                           typical_words([texts[k] for k in sm], df_all, len(ids)),
                           [c for c, _ in Counter(view.items[ids[k]].creator for k in sm).most_common(5)]))
        fs = (_sample(view, ids, members, z[members], fcent[fj], rng),
              typical_words([texts[k] for k in members], df_all, len(ids)),
              [c for c, _ in Counter(view.items[ids[k]].creator for k in members).most_common(5)])
        named = name_field(fs, groups, person=person, chat=chat)
        calls += 1
        cost += named.get("cost_usd") or 0.0
        # a sensitive group keeps no words of its own in the build (its typical words would say what it is)
        fields.append(dict(named["field"], id=fj, n=int(len(members)),
                           typical=[] if named["field"]["sensitive"] else fs[1], themes=list(
            range(first_theme, len(themes))), error=named.get("error")))
        for k, g in enumerate(named["groups"]):
            themes[first_theme + k].update(g, typical=[] if g["sensitive"] else groups[k][1])
        log(f"field {fj + 1}/{len(fcent)}: {len(groups)} themes")
    wall = round(time.monotonic() - t0, 2)
    out_dir = folder(lib)
    os.makedirs(out_dir, exist_ok=True)
    # every vector-store row gets a field and a theme (watched rows as clustered; the others by nearest centroid)
    all_ids = sorted(pos, key=lambda i: pos[i])
    frow, trow = _assign_rows(vs, all_ids, mean, comps, fcent, subspaces, themes)
    where = {i: k for k, i in enumerate(all_ids)}
    for k, i in enumerate(ids):
        frow[where[i]] = flab[k]
        trow[where[i]] = tlab[k]
    np.savez_compressed(os.path.join(out_dir, "space.npz"), mean=mean, comps=comps, fcent=fcent,
                        ids=np.array(all_ids), field=frow, theme=trow,
                        **{f"sub_mean_{j}": s[0] for j, s in enumerate(subspaces) if s[0] is not None},
                        **{f"sub_comps_{j}": s[1] for j, s in enumerate(subspaces) if s[1] is not None},
                        **{f"sub_cent_{j}": s[2] for j, s in enumerate(subspaces) if s[2] is not None})
    meta = {"version": VERSION, "prompt_version": PROMPT_VERSION, "model": config.MODEL,
            "embedding_store": store_name(lib), "embedding_model": EMBEDDING_MODEL.get(store_name(lib)),
            "library_key": lib_key(lib), "built_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
            "items_clustered": len(ids), "rows_assigned": len(all_ids),
            "params": {"pca_dim": PCA_DIM, "sub_dim": SUB_DIM, "sample": SAMPLE, "fields_k": FIELDS_K,
                       "themes_k": THEMES_K, "sub_min": SUB_MIN, "fold_min": FOLD_MIN, "seed": SEED},
            "name_calls": calls, "name_cost_usd": round(cost, 6), "wall_s": wall,
            "items_per_s": round(len(ids) / wall, 1) if wall else None, "fields": fields, "themes": themes}
    with open(os.path.join(out_dir, "build.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    log(json.dumps({k: meta[k] for k in ("items_clustered", "rows_assigned", "name_calls", "name_cost_usd", "wall_s",
                                         "items_per_s")}))
    with _LOCK:
        _LOADED.clear()
    write_rows(lib)
    return meta


def write_rows(lib):
    """themes.jsonl beside the build: one row per vector-store row with its field, theme, shown name, the version and
    the embedding model (AGENTS.md rule 10: every derived row says what made it). space.npz is the fast copy."""
    import numpy as np
    d = folder(lib)
    meta = json.load(open(os.path.join(d, "build.json"), encoding="utf-8"))
    z = np.load(os.path.join(d, "space.npz"))
    names = {t["id"]: (None if t.get("sensitive") else t.get("name")) for t in meta["themes"]}
    tmp = os.path.join(d, "themes.jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for i, fj, tj in zip(z["ids"].tolist(), z["field"].tolist(), z["theme"].tolist()):
            f.write(json.dumps({"item_id": str(i), "field": int(fj), "theme": int(tj), "name": names.get(int(tj)),
                                "version": meta["version"], "embedding_model": meta["embedding_model"]}) + "\n")
    os.replace(tmp, os.path.join(d, "themes.jsonl"))


def _sample(view, ids, members, zm, cent, rng):
    """Titles for naming: the nearest NAME_NEAR to the centroid and NAME_RANDOM others."""
    import numpy as np
    s = zm @ cent
    near = list(np.argsort(-s)[:NAME_NEAR])
    rest = [k for k in range(len(members)) if k not in set(near)]
    if rest:
        near += list(rng.choice(rest, min(NAME_RANDOM, len(rest)), replace=False))
    out = []
    for k in near:
        t = view.items[ids[members[k]]].caption or ""
        if t and t not in out:
            out.append(t)
    return out


def _assign_rows(vs, all_ids, mean, comps, fcent, subspaces, themes, chunk=20000):
    """(field, theme) of each vector-store row by the frozen transforms: the nearest field centroid, then inside that
    field the nearest theme centroid."""
    import numpy as np
    tid = {(t["field"], t["sub"]): t["id"] for t in themes}
    frow = np.full(len(all_ids), -1, dtype=np.int32)
    trow = np.full(len(all_ids), -1, dtype=np.int32)
    for a in range(0, len(all_ids), chunk):
        part = all_ids[a:a + chunk]
        x = _rows(vs, part)
        f = np.argmax(_project(x, mean, comps) @ fcent.T, 1)
        frow[a:a + len(part)] = f
        for fj in np.unique(f):
            sel = np.where(f == fj)[0]
            m2, c2, scent = subspaces[fj]
            if scent is None:
                sub = np.zeros(len(sel), dtype=np.int64)
            else:
                sub = np.argmax(_project(x[sel], m2, c2) @ scent.T, 1)
            trow[a + sel] = [tid.get((int(fj), int(s)), -1) for s in sub]
    return frow, trow


# ================================================================ loading and using a build
class Themes:
    """A loaded build: theme_of(item_id) -> theme dict or None (sensitive or none), field_of(item_id)."""

    def __init__(self, meta, ids, field, theme):
        self.meta = meta
        self.fields = {f["id"]: f for f in meta["fields"]}
        self.themes = {t["id"]: t for t in meta["themes"]}
        self.row = {i: k for k, i in enumerate(ids)}
        self.field = field
        self.theme = theme

    def theme_id(self, iid):
        k = self.row.get(iid)
        return None if k is None or self.theme[k] < 0 else int(self.theme[k])

    def field_id(self, iid):
        k = self.row.get(iid)
        return None if k is None or self.field[k] < 0 else int(self.field[k])

    def shown(self, tid):
        """The theme's name to show, or None (sensitive, or no name)."""
        t = self.themes.get(tid)
        if not t or t.get("sensitive") or not t.get("name"):
            return None
        # a field named sensitive hides its own name only: a theme inside it is judged on its own words
        return t["name"]

    def field_name(self, fid):
        f = self.fields.get(fid) or {}
        return None if f.get("sensitive") or not f.get("name") else f["name"]


def load(lib):
    """The library's build (with every item added since given its nearest theme by code), or None."""
    import numpy as np
    from .history import _vector_store
    lib = os.path.abspath(lib)
    d = folder(lib)
    bp, sp = os.path.join(d, "build.json"), os.path.join(d, "space.npz")
    try:
        stamp = (os.stat(bp).st_mtime_ns, os.stat(sp).st_mtime_ns)
    except OSError:
        return None
    vs = _vector_store(lib)
    vstamp = None if vs is None else (len(vs[0]),)
    key = (lib, stamp, vstamp)
    with _LOCK:
        if _LOADED.get(lib, (None,))[0] == key:
            return _LOADED[lib][1]
    with open(bp, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("version") != VERSION:
        return None
    z = np.load(sp)
    ids = [str(i) for i in z["ids"]]
    field, theme = z["field"].copy(), z["theme"].copy()
    if vs is not None:
        have = set(ids)
        new = [i for i in vs[0] if i not in have]
        if new:
            subspaces = []
            for j in range(len(z["fcent"])):
                subspaces.append((z[f"sub_mean_{j}"] if f"sub_mean_{j}" in z else None,
                                  z[f"sub_comps_{j}"] if f"sub_comps_{j}" in z else None,
                                  z[f"sub_cent_{j}"] if f"sub_cent_{j}" in z else None))
            fr, tr = _assign_rows(vs, new, z["mean"], z["comps"], z["fcent"], subspaces, meta["themes"])
            ids = ids + new
            field = np.concatenate([field, fr])
            theme = np.concatenate([theme, tr])
    th = Themes(meta, ids, field, theme)
    with _LOCK:
        _LOADED[lib] = (key, th)
    return th


# ================================================================ a topic the person names -> themes, by code
WORD_RATE = 0.5      # a theme whose own titles hold the topic's words this often is that topic
RARE_IN_TITLES = 30  # fewer titles than this hold the words: the themes' words are the best evidence there is


def for_topic(view, rec, phrase, th=None, hits=None):
    """[theme ids] a topic ("math", "gaming", "minecraft") stands for, by code:
    - a broad topic: the themes of the category it names (CATEGORY_WORDS: "games" is gaming, "drawing" is art and
      design), and the themes whose name holds its words;
    - the themes whose first two words (the model lists them broad first) hold it, or whose words hold it while at
      least WORD_RATE of the theme's own titles do too (or the words are rare in titles: RARE_IN_TITLES);
    - else where the items that hold the words AND fit them (history.topic_fit) fall: each theme with at least 20% of
      them (and 3 or more), when the words are rare in titles or that theme's titles hold them at least half as
      often as WORD_RATE.
    [] when none says. A field's own words are not used ("blender" was the fourth word of a field of art, DIY and
    animation). `hits`: the ids of the record's items whose text holds the words, when the caller has them."""
    from .history import holds, topic_fit
    th = th or load(view.lib)
    if th is None or not phrase:
        return []
    p = " ".join(phrase.strip().lower().split())
    cats = {c for c, ws in CATEGORY_WORDS.items() if p in ws or p == c}
    if hits is None:
        hits = {i for i in rec.events if view.items.get(i) is not None and holds(view.items[i].caption or "", p)}
    size, held = Counter(), Counter()
    for i in rec.events:
        t = th.theme_id(i)
        if t is not None:
            size[t] += 1
            if i in hits:
                held[t] += 1
    rare = len(hits) < RARE_IN_TITLES
    out = []
    for tid, t in th.themes.items():
        if th.shown(tid) is None:
            continue
        cat = t.get("category") or (th.fields.get(t["field"]) or {}).get("category")
        words = list(t.get("words") or [])
        rate = held[tid] / size[tid] if size[tid] else 0.0
        if cat in cats or holds(t.get("name") or "", p) or any(holds(w, p) for w in words[:2]) or \
                (any(holds(w, p) for w in words) and (rate >= WORD_RATE or rare)):
            out.append(tid)
    if out:
        return sorted(out)
    fit = topic_fit(view, rec, phrase)
    if fit is None:
        return []
    scores, cut = fit
    c = Counter(th.theme_id(i) for i, s in scores.items() if s >= cut)
    c.pop(None, None)
    total = sum(c.values())
    # a word many titles hold is its own topic (those titles); a theme is it only when its titles hold it often
    return sorted(t for t, n in c.items() if n >= 3 and n >= 0.2 * total and th.shown(t) is not None
                  and (rare or (size[t] and held[t] / size[t] >= WORD_RATE / 2)))


if __name__ == "__main__":   # python3 -m mvp.themes build <library>
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "rows"])
    ap.add_argument("library")
    a = ap.parse_args()
    if a.cmd == "rows":   # write themes.jsonl again from an existing build (no model call)
        write_rows(os.path.abspath(a.library))
    else:
        build(a.library)
