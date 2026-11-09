"""PROTOTYPE ONLY - search demo: turn uploaded exports into a new library folder (stdlib only).

  Instagram: ig_import.import_export (zip read in place).
  YouTube:   experiments/youtube/takeout_import.build on the YouTube / My Activity files of one or more Takeout
             zips, extracted to a temporary folder inside the libraries folder and deleted afterwards; its rows are
             mapped to the corpus shape of data/all (platform_data.owner_name = channel, collections = playlist
             names, owner_relation from subscriptions). Search history is not kept.
The new library then needs Prepare (vectors, optional te pass) before it can be searched.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "youtube"))
import ig_import  # noqa: E402
import library as LIB  # noqa: E402
import takeout_import as T  # noqa: E402

YT_KEEP = re.compile(r"(^|/)(history/watch-history\.(json|html)|playlists/[^/]+\.csv|subscriptions/[^/]+\.csv"
                     r"|my activity/youtube/myactivity\.(json|html))$", re.IGNORECASE)


def _safe_members(z):
    for n in z.namelist():
        norm = n.replace("\\", "/")
        if n.endswith("/") or norm.startswith("/") or ".." in norm.split("/"):
            continue
        if YT_KEEP.search(norm):
            yield n, norm


def import_takeout(paths, workdir):
    """-> (items, interactions, stats) in the corpus shape. Only watch history, playlists, subscriptions and the
    My Activity YouTube file are extracted (to a temporary folder that is removed before returning)."""
    tmp = tempfile.mkdtemp(prefix="takeout_", dir=workdir)
    try:
        n = 0
        for p in paths:
            with zipfile.ZipFile(p) as z:
                for name, norm in _safe_members(z):
                    dest = os.path.join(tmp, *norm.split("/"))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(name) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    n += 1
        if not n:
            raise ValueError("No YouTube history, playlists or subscriptions found in the Takeout zip(s).")
        try:
            items, inter, _searches, _subs, stats = T.build(tmp)
        except SystemExit as e:
            raise ValueError(str(e)) from None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    by = {}
    for r in inter:
        by.setdefault(r["item_id"], []).append(r)
    out = [to_corpus(it, by.get(it["id"], [])) for it in items]
    keep = {k: v for k, v in stats.items() if isinstance(v, (int, float)) or v is None}
    keep.pop("searches", None)
    return out, inter, keep


def to_corpus(it, rows):
    pd0 = it.get("platform_data") or {}
    cols = sorted({r["collection_name"] for r in rows if r["kind"] == "playlist" and r.get("collection_name")})
    return {"id": it["id"], "platform": "youtube", "source_url": it["source_url"], "dedup_key": it["dedup_key"],
            "first_seen_at": it.get("first_seen_at"), "caption": it.get("caption") or "",
            "platform_data": {"video_id": pd0.get("video_id"), "media_kind": "video", "owner_handle": "",
                              "owner_name": pd0.get("channel_title") or "", "hashtags": [], "collections": cols,
                              "owner_relation": it.get("creator_relation") or "none",
                              "watch_count": pd0.get("watch_count", 0), "duration_s": None, "available": None},
            "interaction_kinds": it["interaction_kinds"], "importance": it["importance"],
            "processing_depth": it["processing_depth"]}


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "library"


def create_library(root, name, ig_zips=(), yt_zips=(), own_names=(), router_from=()):
    """Write <root>/<slug>/ with items, interactions, empty te files, the router and library.json."""
    if not ig_zips and not yt_zips:
        raise ValueError("Add at least one Instagram export or Google Takeout zip.")
    base = slug(name)
    lib, k = os.path.join(root, base), 2
    while os.path.exists(lib):
        lib, k = os.path.join(root, f"{base}-{k}"), k + 1
    t0 = time.time()
    items, inter, stats, warnings = [], [], {}, []
    if ig_zips:
        a, b, s = ig_import.import_export(list(ig_zips), own_names)
        items += a
        inter += b
        stats["instagram"] = s
        if s.get("warning"):
            warnings.append(s["warning"])
    if yt_zips:
        os.makedirs(root, exist_ok=True)
        a, b, s = import_takeout(list(yt_zips), root)
        ids = {it["id"] for it in items}
        if any(it["id"] in ids for it in a):
            raise ValueError("Item id clash between the Instagram and YouTube imports.")
        items += a
        inter += b
        stats["youtube"] = s
    if not items:
        raise ValueError("The exports held no items.")
    os.makedirs(os.path.join(lib, "corpus"), exist_ok=True)
    for fname, rows in (("items.jsonl", items), ("interactions.jsonl", inter)):
        with open(os.path.join(lib, "corpus", fname), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    LIB.ensure_empty_te_files(lib)
    for src in router_from:
        rp = os.path.join(src, "r7", "router.npz")
        if os.path.isfile(rp):
            os.makedirs(os.path.join(lib, "r7"), exist_ok=True)
            shutil.copyfile(rp, os.path.join(lib, "r7", "router.npz"))
            break
    else:
        warnings.append("No platform router found to copy (r7/router.npz from the preloaded library); "
                        "Q8 and FM need it.")
    plat = [it["platform"] for it in items]
    LIB.write_json(os.path.join(lib, "library.json"), {
        "name": name or base, "source": "uploaded exports", "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": {"items": len(items), "instagram": plat.count("instagram"), "youtube": plat.count("youtube"),
                   "interactions": len(inter)},
        "import_stats": stats, "warnings": warnings, "import_s": round(time.time() - t0, 1)})
    return lib
