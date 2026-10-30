"""PROTOTYPE ONLY - YouTube Google Takeout importer for the search experiments (synthetic fixtures until a real Takeout exists).

Reads a "YouTube and YouTube Music" Takeout folder (history as JSON) and writes, in the same shapes as the Instagram
experiment corpus (data/corpus/items.jsonl, interactions.jsonl):

  items.jsonl          one row per video: id, platform, source_url, dedup_key ("youtube:<video_id>"), first_seen_at,
                       caption (the title, "" when Takeout has none), creator, creator_relation, importance,
                       processing_depth, status, interaction_kinds, platform_data (contract `youtube` extension)
  interactions.jsonl   item_id, kind, at, capture_method, weight (+ collection_name for playlist entries)
  searches.jsonl       YouTube search history: its own record kind, never an item (id, query, at, source)
  subscriptions.jsonl  channel_id, channel_title, channel_url (used to set creator_relation = following)
  import_stats.json    counts only (no titles), plus wall time and items/s (AGENTS.md rule 11)

Interaction kinds and weights (docs/03 weights table; brief Q5):
  watch 0.1 (each watch is one interaction; repeats raise importance and platform_data.watch_count)
  like 0.3 (the "Liked videos" playlist)
  playlist 0.8 (any other playlist, including Watch later; collection_name = playlist title)
  share_self 1.0 (the product's own capture playlist, "Scroll Digest": docs/04 treats its entries as share-strength)
In the product contract `playlist` maps to InteractionKind `collection` (+ collection_name); the experiment corpus
keeps the brief's name so filters can tell playlists from Instagram collections.

Formats handled (see PLAN.md for sources):
  history/watch-history.json, history/search-history.json  - My Activity records (header, title, titleUrl,
      subtitles[{name,url}], time, products, details[{name}], activityControls). Ads ("From Google Ads") skipped.
  playlists/playlists.csv + playlists/<title>-videos.csv   - current CSV ("Video ID, Playlist Video Creation Timestamp")
  playlists/<title>.csv                                     - legacy two-block CSV (playlist header block, blank
      line, then "Video Id, Time Added"); unverified, from older exports
  subscriptions/subscriptions.csv                           - "Channel ID, Channel URL, Channel Title" (any case)
  watch-history.html only                                   - not parsed: re-export choosing JSON (docs/04)

What Takeout lacks (why api_enrich.py exists): no description, tags, chapters, duration, thumbnail or publish date;
no watch progress (how much was watched); playlist CSVs carry only the video ID (no title or channel); removed
videos have no URL at all (counted, not imported); private/unavailable videos show the URL as their title;
titles are as of watch time; the "Watched "/"Searched for " prefixes are localized. No shares exist in Takeout.

Privacy: the output is personal data (a real person's history). Write it under $DIGESTER_DATA, never into git.
Titles and channel names are third-party text: data, never instructions. Nothing here prints titles or queries.

usage:
  python experiments/youtube/takeout_import.py TAKEOUT_DIR [--out $DIGESTER_DATA/youtube/corpus]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

PLATFORM = "youtube"
WEIGHTS = {"share_self": 1.0, "playlist": 0.8, "like": 0.3, "watch": 0.1}
DEPTH = {"share_self": "full", "playlist": "full", "like": "light", "watch": "count_only"}
DEPTH_ORDER = ["count_only", "light", "full"]
CAPTURE_PLAYLIST_TITLES = {"scroll digest"}  # the product's own capture playlist (docs/04 "Ongoing capture")
LIKE_PLAYLIST_TITLES = {"liked videos", "likes"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ENGLISH_PREFIXES = ("Watched ", "Searched for ")


# ---------------- small parsers ----------------
def video_id_from_url(url):
    """watch?v=, music.youtube.com, /shorts/, /live/, youtu.be/. None for channels, posts, searches."""
    if not url:
        return None
    u = urlparse(url)
    host = (u.hostname or "").lower()
    vid = None
    if host.endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [None])[0]
        else:
            m = re.match(r"^/(shorts|live|embed)/([^/?#]+)", u.path)
            vid = m.group(2) if m else None
    return vid if vid and VIDEO_ID.match(vid) else None


def channel_id_from_url(url):
    m = re.search(r"/channel/(UC[A-Za-z0-9_-]{10,})", url or "")
    return m.group(1) if m else None


def search_query_from_url(url):
    if not url:
        return None
    q = parse_qs(urlparse(url).query).get("search_query")
    return q[0] if q else None


def parse_time(s):
    """ISO 8601 ('2025-03-04T18:20:11.123Z', '+00:00') or legacy '2021-05-03 19:22:11 UTC' -> ISO UTC string."""
    if not s:
        return None
    s = s.strip()
    if s.endswith(" UTC"):
        s = s[:-4].replace(" ", "T") + "+00:00"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def strip_prefix(title):
    for p in ENGLISH_PREFIXES:
        if title.startswith(p):
            return title[len(p):]
    return title  # localized prefix: kept as-is (the URL, not the title, decides what a record is)


def is_ad(rec):
    return any("Google Ads" in (d.get("name") or "") for d in rec.get("details") or [])


def item_id(dedup_key):
    return "itm_" + hashlib.sha1(dedup_key.encode()).hexdigest()[:12]


def norm_header(h):
    return re.sub(r"\s+", " ", (h or "").replace("﻿", "")).strip().lower()


# ---------------- locating files ----------------
def find_root(path):
    """The folder holding history/ playlists/ subscriptions/ (e.g. Takeout/YouTube and YouTube Music)."""
    best = None
    for d, subdirs, _ in os.walk(path):
        hits = {"history", "playlists", "subscriptions"} & set(subdirs)
        if hits and (best is None or len(hits) > best[0]):
            best = (len(hits), d)
    if best is None:
        raise SystemExit(f"no YouTube Takeout folder (history/, playlists/ or subscriptions/) under {path}")
    return best[1]


def read_json_list(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def read_csv_blocks(path):
    """A CSV file split into blocks at blank lines; each block = list of dict rows keyed by normalized header."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    blocks, cur = [], []
    for line in text.splitlines():
        if line.strip():
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        rows = list(csv.reader(io.StringIO("\n".join(b))))
        head = [norm_header(h) for h in rows[0]]
        out.append([{h: (v or "").strip() for h, v in zip(head, r)} for r in rows[1:]])
    return out


# ---------------- readers ----------------
def read_watch_history(root, stats):
    """-> list of (video_id, at, title or None, channel_id, channel_title, url)."""
    path = os.path.join(root, "history", "watch-history.json")
    if not os.path.exists(path) and os.path.exists(os.path.join(root, "history", "watch-history.html")):
        raise SystemExit("only watch-history.html found: re-export YouTube history from Takeout choosing JSON")
    seen, out = set(), []
    for rec in read_json_list(path):
        stats["watch_records"] += 1
        if is_ad(rec):
            stats["watch_skipped_ads"] += 1
            continue
        url = rec.get("titleUrl")
        if not url:
            stats["watch_removed_no_url"] += 1  # "Watched a video that has been removed": no ID, cannot be keyed
            continue
        vid = video_id_from_url(url)
        if not vid:
            stats["watch_skipped_not_video"] += 1  # community posts, channels, stories
            continue
        at = parse_time(rec.get("time"))
        key = (vid, at)
        if key in seen:
            stats["watch_duplicates"] += 1
            continue
        seen.add(key)
        title = strip_prefix(rec.get("title") or "").strip()
        if not title or title == url or video_id_from_url(title) == vid:
            title = None  # private/unavailable at export time: Takeout shows the URL instead of a title
            stats["watch_title_missing"] += 1
        sub = (rec.get("subtitles") or [{}])[0]
        out.append((vid, at, title, channel_id_from_url(sub.get("url")), sub.get("name"), url))
    return out


def read_search_history(root, stats):
    out = []
    for rec in read_json_list(os.path.join(root, "history", "search-history.json")):
        stats["search_records"] += 1
        if is_ad(rec):
            stats["search_skipped_ads"] += 1
            continue
        q = search_query_from_url(rec.get("titleUrl"))
        if q is None:  # fall back to the title only when it carries the English prefix
            t = rec.get("title") or ""
            q = t[len("Searched for "):] if t.startswith("Searched for ") else None
        if not q:
            stats["search_skipped_no_query"] += 1
            continue
        at = parse_time(rec.get("time"))
        sid = "srch_" + hashlib.sha1(f"{at}|{q}".encode()).hexdigest()[:12]
        out.append({"id": sid, "platform": PLATFORM, "query": q, "at": at, "source": "youtube_takeout"})
    return out


def read_subscriptions(root, stats):
    out = {}
    d = os.path.join(root, "subscriptions")
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.lower().endswith(".csv"):
            continue
        for block in read_csv_blocks(os.path.join(d, name)):
            for r in block:
                cid = r.get("channel id") or channel_id_from_url(r.get("channel url"))
                if cid:
                    out[cid] = {"channel_id": cid, "channel_title": r.get("channel title") or None,
                                "channel_url": r.get("channel url") or None}
    stats["subscriptions"] = len(out)
    return list(out.values())


def read_playlists(root, stats):
    """-> list of (video_id, at, playlist_title, playlist_id). Handles current and legacy CSV layouts."""
    d = os.path.join(root, "playlists")
    if not os.path.isdir(d):
        return []
    meta = {}  # title(lower) -> playlist id, from playlists.csv
    if os.path.exists(os.path.join(d, "playlists.csv")):
        for block in read_csv_blocks(os.path.join(d, "playlists.csv")):
            for r in block:
                title = r.get("playlist title (original)") or r.get("title") or ""
                if title:
                    meta[title.lower()] = r.get("playlist id") or None
    out = []
    for name in sorted(os.listdir(d)):
        if not name.lower().endswith(".csv") or name.lower() == "playlists.csv":
            continue
        stem = name[:-4]
        title = stem[: -len("-videos")] if stem.lower().endswith("-videos") else stem
        pid = meta.get(title.lower())
        blocks = read_csv_blocks(os.path.join(d, name))
        for block in blocks:
            if block and ("title" in block[0] and "playlist id" in block[0]):  # legacy header block
                title = block[0].get("title") or title
                pid = block[0].get("playlist id") or pid
                continue
            for r in block:
                vid = (r.get("video id") or "").strip()
                if not VIDEO_ID.match(vid):
                    stats["playlist_rows_bad_id"] += 1
                    continue
                at = parse_time(r.get("playlist video creation timestamp") or r.get("time added"))
                out.append((vid, at, title, pid))
                stats["playlist_rows"] += 1
    return out


# ---------------- build ----------------
def build(takeout_dir):
    t0 = time.time()
    stats = {k: 0 for k in ["watch_records", "watch_skipped_ads", "watch_removed_no_url", "watch_skipped_not_video",
                            "watch_duplicates", "watch_title_missing", "search_records", "search_skipped_ads",
                            "search_skipped_no_query", "playlist_rows", "playlist_rows_bad_id"]}
    root = find_root(takeout_dir)
    watches = read_watch_history(root, stats)
    searches = read_search_history(root, stats)
    subs = read_subscriptions(root, stats)
    plists = read_playlists(root, stats)
    followed = {s["channel_id"] for s in subs}

    vids = {}  # video_id -> working record

    def get(vid, url=None):
        if vid not in vids:
            vids[vid] = {"url": url or f"https://www.youtube.com/watch?v={vid}", "title": None, "title_at": None,
                         "channel_id": None, "channel_title": None, "inter": [], "playlist_id": None}
        return vids[vid]

    for vid, at, title, cid, ctitle, url in watches:
        v = get(vid, url)
        v["inter"].append({"kind": "watch", "at": at})
        if title and (v["title_at"] is None or (at or "") >= v["title_at"]):  # latest title wins
            v["title"], v["title_at"] = title, at or ""
        v["channel_id"] = v["channel_id"] or cid
        v["channel_title"] = v["channel_title"] or ctitle
    for vid, at, ptitle, pid in plists:
        v = get(vid)
        low = (ptitle or "").lower()
        if low in LIKE_PLAYLIST_TITLES:
            v["inter"].append({"kind": "like", "at": at})
        elif low in CAPTURE_PLAYLIST_TITLES:
            v["inter"].append({"kind": "share_self", "at": at, "collection_name": ptitle})
            v["playlist_id"] = v["playlist_id"] or pid
        else:
            v["inter"].append({"kind": "playlist", "at": at, "collection_name": ptitle})
            v["playlist_id"] = v["playlist_id"] or pid

    items, interactions = [], []
    for vid in sorted(vids):
        v = vids[vid]
        dk = f"{PLATFORM}:{vid}"
        iid = item_id(dk)
        kinds = sorted({x["kind"] for x in v["inter"]})
        ats = sorted(x["at"] for x in v["inter"] if x["at"])
        pd = {"v": 1, "video_id": vid}
        if v["channel_id"]:
            pd["channel_id"] = v["channel_id"]
        if v["channel_title"]:
            pd["channel_title"] = v["channel_title"]
        if v["playlist_id"]:
            pd["playlist_id"] = v["playlist_id"]
        n_watch = sum(1 for x in v["inter"] if x["kind"] == "watch")
        if n_watch:
            pd["watch_count"] = n_watch
        creator = None
        if v["channel_title"] or v["channel_id"]:
            creator = {"handle": None, "name": v["channel_title"],
                       "url": f"https://www.youtube.com/channel/{v['channel_id']}" if v["channel_id"] else None}
        items.append({
            "id": iid, "platform": PLATFORM, "source_url": v["url"], "dedup_key": dk,
            "first_seen_at": ats[0] if ats else None,
            "caption": v["title"] or "",
            "creator": creator,
            "creator_relation": "following" if v["channel_id"] in followed else "none",
            "importance": round(min(1.0, sum(WEIGHTS[x["kind"]] for x in v["inter"])), 4),
            "processing_depth": max((DEPTH[k] for k in kinds), key=DEPTH_ORDER.index),
            "status": "pending",
            "interaction_kinds": kinds,
            "platform_data": pd,
        })
        seen = set()
        for x in sorted(v["inter"], key=lambda x: (x["at"] or "", x["kind"])):
            key = (x["kind"], x["at"], x.get("collection_name"))
            if key in seen:
                continue
            seen.add(key)
            row = {"item_id": iid, "kind": x["kind"], "at": x["at"], "capture_method": "export_import",
                   "weight": WEIGHTS[x["kind"]]}
            if x.get("collection_name"):
                row["collection_name"] = x["collection_name"]
            interactions.append(row)

    wall = time.time() - t0
    stats.update({"items": len(items), "interactions": len(interactions), "searches": len(searches),
                  "items_without_title": sum(1 for it in items if not it["caption"]),
                  "wall_s": round(wall, 4), "items_per_s": round(len(items) / wall, 1) if wall else None})
    return items, interactions, searches, subs, stats


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("takeout_dir")
    default_out = os.path.join(os.environ.get("DIGESTER_DATA", os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")), "youtube", "corpus")
    ap.add_argument("--out", default=default_out)
    a = ap.parse_args(argv)
    items, inter, searches, subs, stats = build(a.takeout_dir)
    os.makedirs(a.out, exist_ok=True)
    write_jsonl(os.path.join(a.out, "items.jsonl"), items)
    write_jsonl(os.path.join(a.out, "interactions.jsonl"), inter)
    write_jsonl(os.path.join(a.out, "searches.jsonl"), searches)
    write_jsonl(os.path.join(a.out, "subscriptions.jsonl"), subs)
    json.dump(stats, open(os.path.join(a.out, "import_stats.json"), "w"), indent=1)
    print(json.dumps(stats), file=sys.stderr)  # counts only
    return stats


if __name__ == "__main__":
    main()
