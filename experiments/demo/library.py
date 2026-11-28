"""PROTOTYPE ONLY - search demo: what a "library" folder is (stdlib only, shared by app, engine, make_pack, tests).

A library is a folder with the same layout as data/all, holding only what the round-8 processor (Q8) reads:

  library.json                                        manifest (name, source, counts; no personal text)
  corpus/items.jsonl, corpus/interactions.jsonl       items and interactions (friends' posts removed)
  corpus/emb/oai3l_1024_q8/{ids.json,q8.npy,scale.npy} 3-large 1,024 d item vectors as per-dimension int8 (q8-v1)
  corpus/emb/emb_te-v1c_ig_gemini-3.1-flash-lite/     3-small vectors of the Instagram te-v1c texts
  enrich/te-v1c_ig_gemini-3.1-flash-lite.jsonl        Instagram te-v1c rows; enrich/text_<same>.json their texts
  yt_enrich/te-v1c_allowed_gemini-3.1-flash-lite.jsonl YouTube te summaries (only read by the refine's candidate
                                                      lines); yt_enrich/text_<same>.json is {} (Q8 ranks no YouTube te)
  r7/router.npz                                       the round-7 platform head the prior reads (query vector only)
Written while the demo runs (all local): ai_runs.jsonl (cost ledger), cache/ (rewrite and refine responses),
corpus/emb/oai3l_1024_queries and c4_queries (vectors of the searches typed), prepare_status.json.
"""
import json
import os

TE_IG = "te-v1c_ig_gemini-3.1-flash-lite"
TE_YT = "te-v1c_allowed_gemini-3.1-flash-lite"
Q8_STORE = "oai3l_1024_q8"
FRIEND_RELATIONS = {"friend", "mutual"}  # the exports mark friends as mutual follows (owner_relation "mutual")
UPLOADS = "_uploads"


def p(lib, *parts):
    return os.path.join(lib, *parts)


def is_library(d):
    return os.path.isfile(p(d, "corpus", "items.jsonl"))


def roots_and_libraries(path):
    """--library may name one library or a folder of libraries. Returns (root for new uploads, [library dirs])."""
    path = os.path.abspath(path)
    root = os.path.dirname(path) if is_library(path) else path
    libs = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            d = os.path.join(root, name)
            if not name.startswith((".", "_")) and os.path.isdir(d) and is_library(d):
                libs.append(d)
    if is_library(path) and path not in libs:
        libs.insert(0, path)
    return root, libs


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def status(lib):
    """ready | needs_prepare | preparing | prepare_failed, plus what is present (no text)."""
    man = read_json(p(lib, "library.json"), {}) or {}
    has_vec = os.path.isfile(p(lib, "corpus", "emb", Q8_STORE, "q8.npy")) or \
        os.path.isfile(p(lib, "corpus", "emb", "oai3l_1024", "emb.npy"))
    has_te = os.path.isfile(p(lib, "corpus", "emb", f"emb_{TE_IG}", "ids.json"))
    has_router = os.path.isfile(p(lib, "r7", "router.npz"))
    job = read_json(p(lib, "prepare_status.json"), {}) or {}
    if job.get("state") == "running":
        st = "preparing"
    elif has_vec and has_router:
        st = "ready"
    elif job.get("state") == "error":
        st = "prepare_failed"
    else:
        st = "needs_prepare"
    return {"name": man.get("name") or os.path.basename(lib), "path": lib, "state": st, "has_vectors": has_vec,
            "has_te": has_te, "te_skipped": bool(man.get("te_skipped")), "has_router": has_router,
            "counts": man.get("counts") or {}, "source": man.get("source"), "job": job}


def ensure_empty_te_files(lib):
    """te_meta_rows / EnrichIdx open both te files; a library without one gets an empty file (no rows)."""
    for d, name in (("enrich", TE_IG), ("yt_enrich", TE_YT)):
        os.makedirs(p(lib, d), exist_ok=True)
        if not os.path.exists(p(lib, d, f"{name}.jsonl")):
            open(p(lib, d, f"{name}.jsonl"), "w").close()
        if not os.path.exists(p(lib, d, f"text_{name}.json")):
            with open(p(lib, d, f"text_{name}.json"), "w") as f:
                f.write("{}")


def is_friend(item):
    return (item.get("platform_data") or {}).get("owner_relation") in FRIEND_RELATIONS
