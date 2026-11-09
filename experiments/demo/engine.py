"""PROTOTYPE ONLY - search demo engine: the round-8 processors for ONE library, one search at a time.

The ranking is the round-8 code itself, not a copy of it:
  Q8  (B8.5, q8-v1)   c88_search.search_one(env, "q8", ...) on c88_search.Env (route-r1, prior-p1, Instagram te lists,
                      gpt-5-nano rf-v1 refine on rewrite searches read as YouTube, int8 3-large item vectors)
  FM  (B8.8, rfm-v1)  c88_search.search_one(env, "fm", ...): Q8 with the gpt-5-mini refine
  H0  (H0r8)          c7_search.search_one(env, "h0", ...): qr-v1 rewrite on every search, dense + BM25 RRF, no te,
                      no prior, no refine. Here it reads the same int8 item store as Q8 (the round-8 H0r8 runs read
                      float vectors), so its rankings can differ slightly from runs/r8.1/h0r8.
This module only adds what a live, single-search app needs around that code: it routes first so the rewrite is paid
for only when the planner asks for it, embeds the missing query strings (through lib/ai.py, ledger in the library),
lets the refine call the API when its response is not cached, records the ledger rows each search writes (its cost),
times each stage, and degrades to a clearly labelled keyword-only search when there is no key.

Every module of the round-8 code reads $DIGESTER_DATA when it is imported, so one process serves one library:
`python engine.py serve LIB` speaks JSON lines (stdin requests, stdout replies); `prepare LIB` builds a new library's
vectors (and optionally its Instagram te pass); `estimate LIB` prints the cost and time estimate for prepare.
Privacy: friends' posts never appear in results; nothing here prints or logs query or item text, or any key.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import threading
import time
import traceback
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import library as LIB  # noqa: E402

PROCESSORS = {
    "q8": {"label": "Q8", "title": "Q8 (recommended)", "refine_model": "gpt-5-nano"},
    "h0": {"label": "H0", "title": "H0: always rewrite, no te", "refine_model": None},
    "fm": {"label": "FM", "title": "Q8 + mini refine (FM)", "refine_model": "gpt-5-mini"},
}
REWRITE_SALT = 1  # qr-v1 cache salt (round 8 used the repeat number; the demo uses repeat 1 for every search)
LIVE_REP = "live"  # refine cache key "repeat" for live searches
EMB3L = ("text-embedding-3-large", 1024)
EMB3S = ("text-embedding-3-small", 512)
M = {}  # round-8 modules, imported after DIGESTER_DATA is set


def configure(lib):
    """Point the round-8 code at one library (must run before its modules are imported)."""
    lib = os.path.abspath(lib)
    if M:
        assert os.environ.get("DIGESTER_DATA") == lib, "one library per process"
        return lib
    os.environ["DIGESTER_DATA"] = lib
    sys.path.insert(0, os.path.join(EXP, "lib"))
    sys.path.insert(0, os.path.join(EXP, "methods"))
    import ai
    import c4_lib
    import c5_lib
    import c6_lib
    import c7_search
    import c82_lib
    import c85_lib
    import c88_search
    import enrich_batch
    import enrich_items
    import yt_lib
    from e9_enrich_search import enrich_text
    M.update(ai=ai, L=c4_lib, F=c5_lib, G=c6_lib, C7=c7_search, P=c82_lib, X=c85_lib, S88=c88_search,
             EB=enrich_batch, E=enrich_items, Y=yt_lib, enrich_text=enrich_text)
    return lib


def has_key(provider):
    return bool(os.environ.get("OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"))


# ---------------- loading a library ----------------
def qmat_from_parts(q, s):
    """A c85_lib.QMat from a stored int8 matrix and its per-dimension scales (QMat(V) computes the same two arrays)."""
    import numpy as np
    m = M["X"].QMat.__new__(M["X"].QMat)
    m.q = np.ascontiguousarray(q, dtype=np.int8)
    m.s = np.asarray(s, dtype=np.float32)
    m.shape = m.q.shape
    m.dtype = np.dtype(np.float32)
    return m


def load_q8_store(lib):
    import numpy as np
    d = LIB.p(lib, "corpus", "emb", LIB.Q8_STORE)
    with open(os.path.join(d, "ids.json")) as f:
        ids = json.load(f)
    return ids, np.load(os.path.join(d, "q8.npy")), np.load(os.path.join(d, "scale.npy"))


def save_q8_store(lib, ids, q, s):
    import numpy as np
    d = LIB.p(lib, "corpus", "emb", LIB.Q8_STORE)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "ids.json"), "w") as f:
        json.dump(ids, f)
    np.save(os.path.join(d, "q8.npy"), np.ascontiguousarray(q, dtype=np.int8))
    np.save(os.path.join(d, "scale.npy"), np.asarray(s, dtype=np.float32))


def load_env(lib):
    """c88_search.Env for this library. A demo library holds the int8 store (q8-v1); a research data root (data/all)
    holds the float 3-large store, which c88_search.Env quantises itself (used by the parity check)."""
    import numpy as np
    L, G, S88 = M["L"], M["G"], M["S88"]
    if not os.path.exists(LIB.p(lib, "corpus", "emb", LIB.Q8_STORE, "q8.npy")):
        return S88.Env()
    LIB.ensure_empty_te_files(lib)
    items = L.jl(LIB.p(lib, "corpus", "items.jsonl"))
    ids, q, s = load_q8_store(lib)
    S = L.Combined("all", items=items, vectors=(ids, np.zeros((len(ids), 0), np.float32)))
    keep = [k for k, i in enumerate(ids) if i in S.id_pos]
    assert len(keep) == len(S.vcodes)
    S.V = qmat_from_parts(q[keep], s)  # what swap_to_3l + QMat produce, read from disk
    S.QV = G.QueryVecs3L()
    S.emb_name = f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}"
    return S88.Env(S=S)


class FixedPrior:
    """prior-p1 needs both platforms in the library (its split enters a logit). With one platform the prior has
    nothing to weigh: q_ig is fixed at that platform and apply() is a uniform multiplier (order unchanged)."""

    def __init__(self, prior):
        self.inner = prior
        self.q = 1.0 if prior.pi >= 1.0 else 0.0

    def read(self, query, qvec, order):
        return self.q, {"version": "fixed (single-platform library)", "q_ig": self.q, "fixed": True,
                        "e_t": None, "e_k": None, "e_c": None, "n_creators": 0, "mult_ig": 1.0, "mult_yt": 1.0}

    def apply(self, order, sc, q_ig):
        return self.inner.apply(order, sc, q_ig)


class RefinerProxy:
    """Wraps a c88_lib.Refiner88 so c88_search.search_one can run unchanged: a cached response is used as-is; a
    missing one is fetched live when a key is set (allow_call=True), else the order is left as it is (= no refine)."""

    def __init__(self, rf, eng):
        self._rf, self._eng = rf, eng

    def __getattr__(self, k):
        return getattr(self._rf, k)

    def get(self, rep, qid, query, order, allow_call=False):
        rf, ctx = self._rf, self._eng.ctx
        t = time.time()
        top, friend, send = rf.split_top(order)
        key = rf.key(rep, qid, order)
        ctx["refine"] = {"model": rf.model, "cached": key in rf.cache, "live": False, "skipped": None}
        try:
            if key in rf.cache:
                return rf.get(rep, qid, query, order)
            if not ctx["allow_calls"]:
                raise LookupError("refine response not cached")
            if not has_key("openai"):
                ctx["refine"]["skipped"] = "no OpenAI key"
                raise LookupError("no key")
            ctx["refine"]["live"] = True
            res = rf.get(rep, qid, query, order, allow_call=True)
            if not res[1].get("ok"):
                rf.cache.pop(key, None)  # a failed call is not reused in this session
                ctx["refine"]["skipped"] = "refine call failed"
            return res
        except Exception as e:  # noqa: BLE001 - no key / network / budget: the first-stage order stands
            if not ctx["refine"]["skipped"]:
                ctx["refine"]["skipped"] = _short_error(e)
            r = {"key": key, "ok": False, "seconds": 0.0, "cost_usd": 0.0, "tries": 0, "in_tokens": 0,
                 "out_tokens": 0}
            return rf.reorder(order, top, friend, send, r), r
        finally:
            ctx["refine_wall_s"] = time.time() - t


def _short_error(e):
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}" + (" (key rejected)" if e.code in (401, 403) else "")
    if isinstance(e, urllib.error.URLError):
        return "network error"
    s = str(e)
    if "budget stop" in s:
        return "budget cap reached (see README: DIGESTER_OPENAI_BUDGET_USD)"
    if isinstance(e, KeyError) and "API_KEY" in s:
        return "no API key"
    return type(e).__name__


class Engine:
    def __init__(self, lib):
        self.lib = configure(lib)
        t0 = time.time()
        ai = M["ai"]
        self.lock = threading.Lock()
        self.ctx = {"rows": [], "allow_calls": True}
        orig = ai._log

        def _log(row):  # every ledger row a search writes is also kept for that search's cost line
            orig(row)
            with self.lock:
                self.ctx["rows"].append({k: row.get(k) for k in ("provider", "model", "purpose", "n", "in_tokens",
                                                                  "out_tokens", "cost_usd", "seconds")})
        ai._log = _log
        self.env = load_env(self.lib)
        env, S = self.env, self.env.S
        self.single_platform = env.prior.pi in (0.0, 1.0)
        if self.single_platform:
            env.prior = FixedPrior(env.prior)
        self.te_available = bool(env.te.E.codes)
        if not self.te_available:  # no te rows: the te lists are empty, so their 3-small query vectors are not needed
            import numpy as np
            env.te.small_qv = lambda texts, caps: np.zeros((len(texts) + (1 if caps else 0), EMB3S[1]), np.float32)
        for m, rf in list(env.refiners.items()):
            for k in [k for k, r in rf.cache.items() if not r.get("ok")]:
                rf.cache.pop(k)
            env.refiners[m] = RefinerProxy(rf, self)
        self.summary = env.refiners[M["S88"].K.NANO]._rf.summary
        self.load_s = time.time() - t0
        plat = [it["platform"] for it in S.items]
        self.counts = {"items": len(S.items), "instagram": plat.count("instagram"), "youtube": plat.count("youtube"),
                       "with_vectors": len(S.vcodes), "te_rows": len(env.te.E.codes),
                       "friends_in_index": sum(LIB.is_friend(it) for it in S.items)}

    def info(self):
        return {"counts": self.counts, "load_s": round(self.load_s, 1), "te_available": self.te_available,
                "single_platform": self.single_platform,
                "keys": {"openai": has_key("openai"), "gemini": has_key("gemini")}}

    # ---------------- one search ----------------
    def search(self, query, processors, parity=None):
        if parity is None:
            query = " ".join(str(query or "").split())[:300]
        return {p: self._one(query, p, parity) for p in processors}

    def _rewrite(self, query, ctx, why):
        """qr-v1 (gpt-5-nano, c6_lib.rewrite_one) from the library's cache, else live when a key is set."""
        G = M["G"]
        t = time.time()
        try:
            parse, rec = G.rewrite_one(query, "gpt-5-nano", REWRITE_SALT, purpose="demo_query_rewrite")
            why["rewrite"] = {"used": True, "phrases": parse["phrases"], "keywords": parse["keywords"],
                              "captions": parse["hypothetical_captions"], "cached": bool(rec.get("cached")),
                              "call_seconds": rec.get("seconds")}
            ctx["lat"]["rewrite_s"] = time.time() - t
            return parse
        except Exception as e:  # noqa: BLE001
            why["rewrite"] = {"used": False, "skipped": "no OpenAI key" if not has_key("openai") else _short_error(e)}
            why["notes"].append("The rewrite was skipped (" + why["rewrite"]["skipped"] + "), so this search used "
                                "the raw query only.")
            return {"phrases": [], "keywords": [], "hypothetical_captions": []}  # plan_c0 = the raw query alone

    def _embed(self, store, strings, model, dim, purpose):
        """Embed strings missing from a query-vector store (the same call and normalisation as the round-8 stores'
        get(); one retry only, so a bad key fails fast) and save the store."""
        import numpy as np
        from sklearn.preprocessing import normalize
        ai, L = M["ai"], M["L"]
        miss = sorted({s for s in strings if s not in store.vec})
        if not miss:
            return 0
        for att in range(2):
            try:
                V = ai.openai_embed([s[:6000] or " " for s in miss], model=model, dimensions=dim, purpose=purpose)
                break
            except urllib.error.HTTPError as e:
                if att or e.code not in (429, 500, 502, 503):
                    raise
                time.sleep(2)
        V = normalize(np.array(V, dtype=np.float32))
        with self.lock:
            store.vec.update(zip(miss, V))
            ids = list(store.vec)
            L.save_store(store.path, ids, np.array([store.vec[s] for s in ids]))
        return len(miss)

    def _one(self, query, proc, parity=None):
        env, S = self.env, self.env.S
        F, C7, S88 = M["F"], M["C7"], M["S88"]
        ctx = {"rows": [], "allow_calls": parity is None, "lat": {}, "refine": None, "refine_wall_s": 0.0}
        self.ctx = ctx
        why = {"processor": PROCESSORS[proc]["title"], "notes": [], "mode": "normal"}
        qid = parity["qid"] if parity else "live_" + hashlib.sha1(query.encode()).hexdigest()[:12]
        rep = parity["rep"] if parity else LIVE_REP
        q = {"id": qid, "query": query, "examples": [], "filters": (parity or {}).get("filters")}
        t_all = time.time()
        t = time.time()
        route = env.router_shape.route(query)
        ctx["lat"]["route_s"] = time.time() - t
        path = "rewrite" if proc == "h0" else route["path"]
        why["route"] = {"path": route["path"], "reason": route.get("reason"), "markers": route["markers"],
                        "n_tokens": route["n_tokens"]}
        why["path"] = path
        parse = None
        if path == "rewrite":
            parse = parity["parse"] if parity else self._rewrite(query, ctx, why)
            if parity:
                why["rewrite"] = {"used": True, "phrases": parse["phrases"], "keywords": parse["keywords"],
                                  "captions": parse["hypothetical_captions"], "cached": True}
        else:
            why["rewrite"] = {"used": False, "skipped": "instant path (no rewrite needed)"}
        texts, caps, bq = (F.plan_c0(q, parse) if proc == "h0" else S88.plan(q, parse, path))
        need3l = [query] + texts + caps
        need_te = (texts + caps) if (proc != "h0" and self.te_available) else []
        miss3l = [s for s in need3l if s not in S.QV.vec]
        miss_te = env.te.missing(need_te) if need_te else []
        fallback = None
        if miss3l or miss_te:
            if parity:
                raise KeyError("parity mode: query vectors must be cached")
            if not has_key("openai"):
                fallback = "no OpenAI key, and this search's vectors are not cached"
            else:
                t = time.time()
                try:
                    with cf.ThreadPoolExecutor(2) as ex:  # 3-large and 3-small in parallel, as round 8 timed them
                        a = ex.submit(self._embed, S.QV, miss3l, *EMB3L, "demo_query_vectors_3l")
                        b = ex.submit(self._embed, env.te.QVs, miss_te, *EMB3S, "demo_te_query_vectors")
                        a.result()
                        b.result()
                except Exception as e:  # noqa: BLE001
                    fallback = "query embedding failed: " + _short_error(e)
                ctx["lat"]["embed_s"] = time.time() - t
        else:
            ctx["lat"]["embed_s"] = 0.0
            why["embed_cached"] = True
        t = time.time()
        if fallback:
            order = self._keyword_fallback(proc, query)
            why["mode"] = "keyword_fallback"
            why["notes"].append(f"Keyword-only fallback ({fallback}): BM25 over item text"
                                + (" and Instagram te text" if proc != "h0" and self.te_available else "")
                                + ". This is not the real processor; set an OpenAI key for it.")
            info = {}
        elif proc == "h0":
            order, info = C7.search_one(env, "h0", q, parse, None)
            order = order[:1000]
        else:
            order, info = S88.search_one(env, proc, q, parse, rep)
        local = time.time() - t - ctx["refine_wall_s"]
        ctx["lat"]["local_s"] = local
        if info.get("prior"):
            pi = info["prior"]
            why["prior"] = {**pi, "reads": ("Instagram" if pi["q_ig"] >= 0.5 else "YouTube")}
        if proc != "h0":
            why["te"] = {"available": self.te_available, "used": bool(info.get("te_used")) and self.te_available,
                         "in_top10": sum(c in env.te.E.codeset for c in order[:10])}
            if not self.te_available:
                why["notes"].append("This library has no te pass, so Instagram search is weaker.")
        gated = "refine" in info
        r = ctx["refine"] or {}
        why["refine"] = {"gated": gated, "model": PROCESSORS[proc]["refine_model"],
                         "gate": "rewrite-path search read as YouTube (q_ig < 0.5)" if proc != "h0" else None}
        if gated:
            ri = info["refine"]
            why["refine"].update({"ran": bool(ri["ok"]), "moved": ri["moved"], "sent": ri["n_sent"],
                                  "cached": r.get("cached"), "skipped": r.get("skipped"),
                                  "call_seconds": ri["seconds"]})
            ctx["lat"]["refine_s"] = ctx["refine_wall_s"]
            if r.get("skipped"):
                why["notes"].append(f"The refine was skipped ({r['skipped']}); showing the first-stage order.")
        lat = ctx["lat"]
        first = sum(lat.get(k) or 0.0 for k in ("route_s", "rewrite_s", "embed_s", "local_s"))
        lat["first_screen_s"] = first
        lat["total_s"] = first + (lat.get("refine_s") or 0.0)
        lat["wall_s"] = time.time() - t_all
        why["latency"] = {k: round(v, 3) for k, v in lat.items() if v is not None}
        rows = list(ctx["rows"])
        why["cost"] = {"usd": sum(x.get("cost_usd") or 0.0 for x in rows), "calls": rows}
        results, hidden = [], 0
        for c in order:
            it = S.items[S.pos[c]]
            if LIB.is_friend(it):
                hidden += 1
                continue
            results.append(self.row(c, it, len(results) + 1))
            if len(results) >= 20:
                break
        if hidden:
            why["notes"].append(f"{hidden} friends' posts were left out of the list.")
        out = {"processor": proc, "results": results, "why": why}
        if parity:
            out["order"] = order[:1000]
        return out

    def _keyword_fallback(self, proc, query):
        env, S, F = self.env, self.env.S, M["F"]
        own = [S.bm.rank(query)]
        te = env.te.E.bm25(query, None) if proc != "h0" and self.te_available else []
        groups = [([te], env.te.E.codeset)] if te else []  # an empty te list would only scale non-te items up
        return F.fair_fuse(own, groups)[0][:1000]

    def row(self, c, it, rank):
        pd = it.get("platform_data") or {}
        kinds = set(it.get("interaction_kinds") or [])
        how = []
        cols = [x for x in pd.get("collections") or [] if x]
        if it["platform"] == "instagram":
            if "save" in kinds or "collection" in kinds:
                how.append("saved" + (" to " + ", ".join(cols[:3]) if cols else ""))
        else:
            pls = [x for x in cols if x != "Watch later"]
            if "Watch later" in cols:
                how.append("watch later")
            if pls:
                how.append("playlist: " + ", ".join(pls[:3]))
        if "like" in kinds:
            how.append("liked")
        if "share_self" in kinds:
            how.append("sent to yourself")
        if "share_friend" in kinds:
            how.append("sent to someone")
        wc = pd.get("watch_count") or 0
        if wc:
            how.append(f"watched {wc}×" if wc > 1 else "watched once")
        elif "watch" in kinds:
            how.append("watched")
        if "view" in kinds and not wc:
            how.append("viewed")
        handle = (pd.get("owner_handle") or "").strip().lstrip("@")
        name = (pd.get("owner_name") or "").strip()
        if it["platform"] == "instagram":
            creator = ("@" + handle if handle else "") + (f" · {name}" if name and name != handle else "")
        else:
            creator = name or handle
        text = " ".join((it.get("caption") or "").split())
        return {"rank": rank, "platform": it["platform"], "creator": creator.strip(" ·") or None,
                "text": text[:260] + ("…" if len(text) > 260 else ""), "summary": (self.summary.get(c) or "")[:200],
                "date": (it.get("first_seen_at") or "")[:10] or None, "how": how, "url": it.get("source_url"),
                "media": pd.get("media_kind")}


# ---------------- prepare (a new library's vectors and te pass) ----------------
TE_MODEL = "gemini-3.1-flash-lite"
TE_OUT_TOKENS = 160  # c4_ig_enrich.py's per-item output estimate
CHUNK = 2000


def _item_texts(items):
    L = M["L"]
    ids, texts = [], []
    for it in items:
        t = L.view_text(it)
        if t:
            ids.append(it["id"])
            texts.append(t)
    return ids, texts


def _te_items(items):
    return [it for it in items if it["platform"] == "instagram" and not LIB.is_friend(it)]


def estimate(lib):
    configure(lib)
    L, E, EB, ai = M["L"], M["E"], M["EB"], M["ai"]
    items = L.jl(LIB.p(lib, "corpus", "items.jsonl"))
    ids, texts = _item_texts(items)
    tok = sum(min(len(t), 6000) for t in texts) / 4.0
    p3 = ai.prices()[EMB3L[0]]["input_per_m"]
    ig = _te_items(items)
    done = _te_done(lib)
    todo = [it for it in ig if L.code_of(it) not in done]
    pr = ai.prices()[TE_MODEL]
    te_in = sum(len(EB.SYSTEM) + len(E.block(it)) for it in todo) / 4.0
    te_cost = te_in / 1e6 * pr["input_per_m"] + len(todo) * TE_OUT_TOKENS / 1e6 * pr["output_per_m"]
    te_small = len(todo) * 80 / 1e6 * ai.prices()[EMB3S[0]]["input_per_m"]  # ~80 tokens per te text
    return {"items": len(items), "items_with_text": len(texts),
            "embed": {"model": f"{EMB3L[0]} @ {EMB3L[1]} d, stored int8", "tokens_est": int(tok),
                      "cost_usd": round(tok / 1e6 * p3, 4), "minutes_est": round(len(texts) / 400 / 60 + 0.2, 1)},
            "te": {"model": TE_MODEL + " (synchronous, te-v1c prompt)", "instagram_items": len(ig),
                   "already_done": len(ig) - len(todo), "to_do": len(todo),
                   "cost_usd": round(te_cost + te_small, 4),
                   "minutes_est_at_6": round(len(todo) * 2.0 / 6 / 60 + 0.2, 1)},
            "spent_in_this_library": {"openai": round(ai.spent("openai"), 4), "gemini": round(ai.spent("gemini"), 4)},
            "budget_caps": {"openai": ai.budget("openai"), "gemini": ai.budget("gemini")}}


def _te_done(lib):
    path = LIB.p(lib, "enrich", f"{LIB.TE_IG}.jsonl")
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    if r.get("ok"):
                        done.add(r["code"])
    return done


class Status:
    def __init__(self, lib):
        self.path = LIB.p(lib, "prepare_status.json")
        self.d = {"state": "running", "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": "starting",
                  "done": 0, "total": 0, "cost_usd": 0.0, "message": ""}
        self.t0 = time.time()
        self.spent0 = M["ai"].spent()
        self.write()

    def write(self, **kw):
        self.d.update(kw)
        self.d["cost_usd"] = round(M["ai"].spent() - self.spent0, 4)
        self.d["elapsed_s"] = round(time.time() - self.t0, 1)
        LIB.write_json(self.path, self.d)


def prepare(lib, te=True, te_cap=1.0, workers=6):
    import numpy as np
    from sklearn.preprocessing import normalize
    lib = configure(lib)
    st = Status(lib)
    ai, L, G, X, Y, E, EB = M["ai"], M["L"], M["G"], M["X"], M["Y"], M["E"], M["EB"]
    man = LIB.read_json(LIB.p(lib, "library.json"), {}) or {}
    try:
        LIB.ensure_empty_te_files(lib)
        if not os.path.exists(LIB.p(lib, "r7", "router.npz")):
            raise RuntimeError("router.npz missing (copy r7/router.npz from the preloaded library)")
        if not has_key("openai"):
            raise RuntimeError("OPENAI_API_KEY is not set")
        items = L.jl(LIB.p(lib, "corpus", "items.jsonl"))
        ids, texts = _item_texts(items)
        st.write(step="checking the OpenAI key", total=len(texts))
        ai.openai_embed(["ok"], model=EMB3L[0], dimensions=EMB3L[1], purpose="demo_key_check")
        parts = LIB.p(lib, "corpus", "emb", LIB.Q8_STORE, "parts")
        os.makedirs(parts, exist_ok=True)
        t0 = time.time()
        chunks = []
        for i in range(0, len(texts), CHUNK):
            ch = texts[i:i + CHUNK]
            h = hashlib.sha1("\n".join(ch).encode()).hexdigest()[:12]
            fp = os.path.join(parts, f"{i:08d}_{h}.npy")
            if os.path.exists(fp):
                V = np.load(fp)
            else:
                V = G.embed_3l(ch, "demo_item_vectors_3l", batch=500, workers=2).astype(np.float16)
                np.save(fp, V)
            chunks.append(V)
            st.write(step="embedding items (3-large)", done=min(i + CHUNK, len(texts)), total=len(texts))
        V16 = np.vstack(chunks) if chunks else np.zeros((0, EMB3L[1]), np.float16)
        Vf = normalize(V16.astype(np.float32))  # = load_store of a float16 store, as round 8 read it
        Qm = X.QMat(Vf) if len(Vf) else None
        el = time.time() - t0
        print(f"prepare: embedded {len(texts)} items in {el:.1f} s ({len(texts) / max(el, 1e-9):.0f} items/s)",
              file=sys.stderr, flush=True)
        if Qm is None:
            raise RuntimeError("no item has any text to embed")
        save_q8_store(lib, ids, Qm.q, Qm.s)
        for f in os.listdir(parts):
            os.remove(os.path.join(parts, f))
        os.rmdir(parts)
        te_summary = {"skipped": not te}
        if te:
            te_summary = _te_pass(lib, items, te_cap, workers, st)
        man.update({"prepared": time.strftime("%Y-%m-%dT%H:%M:%S"), "processor_version": "q8-v1",
                    "embedding_model": f"{EMB3L[0]}@{EMB3L[1]} int8", "te_skipped": not te,
                    "te": te_summary})
        LIB.write_json(LIB.p(lib, "library.json"), man)
        st.write(state="done", step="done", message="Library ready.")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        st.write(state="error", message=_short_error(e) if not isinstance(e, RuntimeError) else str(e))
        raise SystemExit(1)


def _te_pass(lib, items, cap, workers, st):
    """te-v1c on the library's Instagram items (friends never sent), synchronous gemini-3.1-flash-lite calls through
    lib/ai.py: enrich_batch.request_for + enrich_items.validate exactly as c4_ig_enrich.py --retry-failed does, then
    the te texts (e9_enrich_search.enrich_text) and their 3-small vectors (as c4_embed_te.py)."""
    ai, L, E, EB, Y = M["ai"], M["L"], M["E"], M["EB"], M["Y"]
    out = LIB.p(lib, "enrich", f"{LIB.TE_IG}.jsonl")
    ig = _te_items(items)
    by_code = {L.code_of(it): it for it in ig}
    codes, _ = E.select("all", ig)
    done = _te_done(lib)
    todo = [c for c in codes if c not in done]
    pr = ai.prices()[TE_MODEL]
    lock = threading.Lock()
    spent = [0.0]
    n_ok = [0]
    if todo and not has_key("gemini"):
        raise RuntimeError("GEMINI_API_KEY is not set (or choose 'skip te')")

    def one(c):
        req = EB.request_for(by_code[c])
        gc = {k: v for k, v in req["generationConfig"].items() if k not in ("responseMimeType", "maxOutputTokens")}
        for att in range(4):
            try:
                o, u = ai.gemini_json(TE_MODEL, req["system_instruction"]["parts"][0]["text"],
                                      [req["contents"][0]["parts"][0]["text"]], max_tokens=EB.MAX_OUT,
                                      purpose="demo_te_ig", prompt_version=EB.PV, generation_config=gc)
                f, ok, dropped = E.validate(o)
                err = None if ok else "invalid"
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) or (e.code < 500 and e.code != 429) or att == 3:
                    raise
                time.sleep(2 * 2 ** att)
            except (ValueError, KeyError, IndexError) as e:  # bad JSON / no candidate: recorded as a failed row
                f, ok, dropped, err, u = {}, False, 0, type(e).__name__, {}
                break
        tin = u.get("promptTokenCount", 0)
        tout = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
        cost = tin / 1e6 * pr["input_per_m"] + tout / 1e6 * pr["output_per_m"]
        row = {"code": c, "ok": ok, **f, "dropped": dropped, "err": err, "in_tokens": tin, "out_tokens": tout,
               "cost_usd": cost, "prompt_version": EB.PV, "model": TE_MODEL,
               "input_hash": hashlib.sha256(E.block(by_code[c]).encode()).hexdigest()[:16]}
        with lock:
            with open(out, "a", encoding="utf-8") as fo:
                fo.write(json.dumps(row, ensure_ascii=False) + "\n")
            spent[0] += cost
            n_ok[0] += ok
        return cost

    t0 = time.time()
    stopped = False
    per = 0.0004  # worst-ish cost per item until measured
    i = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        while i < len(todo):
            if spent[0] + per * workers * 4 > cap:
                stopped = True
                break
            batch = todo[i:i + workers * 4]
            list(ex.map(one, batch))
            i += len(batch)
            per = max(per * 0.5, spent[0] / max(i, 1))
            st.write(step="te pass (Instagram, gemini-3.1-flash-lite)", done=len(done) + i, total=len(codes),
                     message=f"te spend ${spent[0]:.3f} of the ${cap:.2f} cap")
    el = time.time() - t0
    print(f"te: {i} items in {el:.1f} s ({i / max(el, 1e-9):.2f} items/s), ok {n_ok[0]}, ${spent[0]:.4f}",
          file=sys.stderr, flush=True)
    rows = {}
    for r in L.jl(out):
        if r.get("ok"):
            rows[r["code"]] = r  # last ok row per item wins (c4_embed_te.py)
    texts = {c: M["enrich_text"](r) for c, r in sorted(rows.items())}
    with open(LIB.p(lib, "enrich", f"text_{LIB.TE_IG}.json"), "w", encoding="utf-8") as f:
        json.dump(texts, f)
    tc = list(texts)
    st.write(step="embedding te texts (3-small)", done=0, total=len(tc))
    if tc:
        V = Y.embed_texts([texts[c] for c in tc], "demo_te_item_vectors", batch=500, workers=2)
        L.save_store(LIB.p(lib, "corpus", "emb", f"emb_{LIB.TE_IG}"), tc, V)
    return {"skipped": False, "items_ok": len(tc), "items_total": len(codes), "stopped_at_cap": stopped,
            "te_cost_usd": round(spent[0], 4)}


# ---------------- worker protocol ----------------
def serve(lib):
    proto = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)  # anything else printed goes to stderr (the round-8 code prints counts only)
    sys.stdout = sys.stderr

    def send(obj):
        proto.write(json.dumps(obj, ensure_ascii=False) + "\n")
        proto.flush()

    send({"event": "loading"})
    try:
        eng = Engine(lib)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        send({"event": "error", "message": f"could not load the library: {type(e).__name__}"})
        return
    send({"event": "ready", "info": eng.info()})
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        rid, cmd = msg.get("id"), msg.get("cmd")
        try:
            if cmd == "keys":
                for prov, var in (("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")):
                    if prov in msg:
                        if msg[prov]:
                            os.environ[var] = msg[prov]
                        else:
                            os.environ.pop(var, None)
                send({"id": rid, "ok": True, "info": eng.info()})
            elif cmd == "info":
                send({"id": rid, "ok": True, "info": eng.info()})
            elif cmd == "search":
                procs = [p for p in msg.get("processors") or ["q8"] if p in PROCESSORS][:2] or ["q8"]
                send({"id": rid, "ok": True, "result": eng.search(msg.get("query", ""), procs)})
            elif cmd == "quit":
                send({"id": rid, "ok": True})
                break
            else:
                send({"id": rid, "ok": False, "error": "unknown command"})
        except Exception as e:  # noqa: BLE001 - never crash the worker on one bad search
            traceback.print_exc(file=sys.stderr)
            send({"id": rid, "ok": False, "error": _short_error(e)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["serve", "prepare", "estimate"])
    ap.add_argument("library")
    ap.add_argument("--te", type=int, default=1)
    ap.add_argument("--te-cap", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(os.path.abspath(a.library))
    elif a.cmd == "estimate":
        proto = os.fdopen(os.dup(1), "w", encoding="utf-8")
        os.dup2(2, 1)
        proto.write(json.dumps(estimate(os.path.abspath(a.library))) + "\n")
        proto.flush()
    else:
        prepare(os.path.abspath(a.library), te=bool(a.te), te_cap=a.te_cap, workers=a.workers)


if __name__ == "__main__":
    main()
