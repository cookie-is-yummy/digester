"""PROTOTYPE ONLY - Instagram data export (JSON format) -> demo library items and interactions.

A port of the phase-0 prototype scripts, reading straight from the export zip(s) (nothing is extracted, media
files are never opened):
  importer.py       saved / liked posts, videos watched, posts viewed, saved collections -> items + interactions
  shares_adapter.py DM shares, as shared-post objects only: share_self (a thread of only the user's own accounts,
                    weight 1.0), share_friend (a share the user sent to anyone else, 0.6); received shares are
                    counted, not added. Only thread participants, sender name, timestamp and the share object
                    (link, share_text = the post's caption, original_content_owner) are read. Message text is
                    never read, kept or stored; recipients are not stored.
  social_graph.py   platform_data.owner_relation = mutual (a mutual follow: a likely friend) | following | none
Output rows have the shape of data/all/corpus/items.jsonl and interactions.jsonl. Friends' posts (mutual follows)
are then dropped with their interactions, so they never enter the library; only their count is kept.
Captions are third-party text: data, never instructions.
"""
import collections
import datetime as dt
import hashlib
import json
import posixpath
import re
import zipfile

SOURCES = [  # (path suffix, interaction kind, weight) - importer.py
    ("saved/saved_posts.json", "save", 0.8),
    ("likes/liked_posts.json", "like", 0.3),
    ("ads_and_topics/videos_watched.json", "watch", 0.1),
    ("ads_and_topics/posts_viewed.json", "view", 0.1),
]
COLLECTIONS = "saved/saved_collections.json"
FOLLOWERS = re.compile(r"(^|/)followers_and_following/followers(_\d+)?\.json$")
FOLLOWING = re.compile(r"(^|/)followers_and_following/following\.json$")
DM_FILE = re.compile(r"(^|/)messages/inbox/[^/]+/message_\d+\.json$")
DEPTH = {"share_self": "full", "share_friend": "full", "save": "full", "collection": "full",
         "like": "light", "watch": "count_only", "view": "count_only"}
RANK = {"full": 3, "light": 2, "count_only": 1}
SHARE_WEIGHT = {"share_self": 1.0, "share_friend": 0.6}


def fix(s):
    """Instagram exports UTF-8 text mis-decoded as latin-1."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def content_id(url):
    m = re.search(r"instagram\.com/(?:[^/]+/)?(reel|reels|p|tv)/([^/?#]+)", url or "")
    return ("reel" if m.group(1).startswith("reel") else m.group(1), m.group(2)) if m else (None, None)


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat() if ts else None


def item_id(key):
    return "itm_" + hashlib.sha1(key.encode()).hexdigest()[:12]


class Export:
    """Read-only view over one or more export zips (Instagram may split an export into parts)."""

    def __init__(self, paths):
        self.zips = [zipfile.ZipFile(p) for p in paths]
        self.names = []
        for z in self.zips:
            for n in z.namelist():
                if not n.endswith("/"):
                    self.names.append((posixpath.normpath(n), z, n))

    def find(self, suffix):
        for norm, z, n in self.names:
            if norm == suffix or norm.endswith("/" + suffix):
                return z, n
        return None

    def matching(self, rx):
        return [(z, n) for norm, z, n in self.names if rx.search(norm)]

    def load(self, zn):
        z, n = zn
        with z.open(n) as f:
            return json.load(f)

    def close(self):
        for z in self.zips:
            z.close()


def entries(data):
    return list(data.values())[0] if isinstance(data, dict) and data else (data or [])


def parse_entry(e):
    """importer.py's label_values reader, plus the older title / string_map_data layout (owner + link + time)."""
    row = {"ts": e.get("timestamp"), "caption": "", "hashtags": [], "owner": {}, "url": None}
    if "label_values" in e:
        for lv in e.get("label_values", []):
            label, title = lv.get("label"), lv.get("title")
            if label == "URL":
                row["url"] = lv.get("value") or lv.get("href")
            elif label == "Caption":
                row["caption"] = fix(lv.get("value", ""))
            elif title == "Hashtags":
                row["hashtags"] = [fix(kv.get("value")) for b in lv.get("dict", [])
                                   for kv in b.get("dict", []) if kv.get("value")]
            elif title == "Owner":
                for b in lv.get("dict", []):
                    for kv in b.get("dict", []):
                        if kv.get("label") in ("Username", "Name", "URL") and kv.get("value"):
                            row["owner"][kv["label"].lower()] = fix(kv["value"])
        return row
    if e.get("title"):
        row["owner"]["username"] = fix(e["title"])
    vals = list((e.get("string_map_data") or {}).values()) + list(e.get("string_list_data") or [])
    for v in vals:
        if isinstance(v, dict):
            row["url"] = row["url"] or v.get("href")
            row["ts"] = row["ts"] or v.get("timestamp")
    return row


def collection_groups(data):
    """[(name, [urls])] from saved_collections.json (label_values layout, or the older title / string_map_data one)."""
    out = []
    for c in entries(data):
        if "label_values" in c:
            name, urls = None, []
            for lv in c.get("label_values", []):
                if lv.get("label") == "Name":
                    name = fix(lv.get("value"))
                if lv.get("title") == "Media":
                    for b in lv.get("dict", []):
                        for kv in b.get("dict", []):
                            if kv.get("label") == "URL":
                                urls.append(kv.get("value"))
            out.append((name, urls))
        else:
            smd = c.get("string_map_data") or {}
            if c.get("title") == "Collection":
                out.append((fix((smd.get("Name") or {}).get("value")), []))
            elif out:
                href = (smd.get("Name") or {}).get("href")
                if href:
                    out[-1][1].append(href)
    return out


def handles(data):
    """social_graph.py: every username / name / profile-link handle in a followers / following file."""
    out = set()
    for e in entries(data):
        if e.get("title"):
            out.add(e["title"].lower())
        for s in e.get("string_list_data", []):
            if s.get("value"):
                out.add(s["value"].lower())
            href = s.get("href") or ""
            if "instagram.com/" in href:
                out.add(href.rstrip("/").split("/")[-1].lower())
        for lv in e.get("label_values", []):
            v = lv.get("value")
            if lv.get("label") in ("Username", "Name") and v:
                out.add(v.lower())
    return out


def import_export(paths, own_names=()):
    """-> (items, interactions, stats). stats holds counts only (no captions, names or message data)."""
    ex = Export(paths)
    try:
        return _import(ex, own_names)
    finally:
        ex.close()


def _import(ex, own_names):
    items, interactions = {}, []
    counts = collections.Counter()
    found = [suf for suf, _, _ in SOURCES if ex.find(suf)]
    if not found and not ex.find(COLLECTIONS):
        html = any(norm.endswith(("saved_posts.html", "liked_posts.html")) for norm, _, _ in ex.names)
        raise ValueError("This export is in HTML format: request the Instagram export again in JSON format."
                         if html else "No saved or liked posts found: is this an Instagram data export (JSON)?")
    for suf, kind, weight in SOURCES:
        zn = ex.find(suf)
        if not zn:
            continue
        for e in entries(ex.load(zn)):
            r = parse_entry(e)
            kind_ig, cid = content_id(r.get("url"))
            if not cid:
                counts["skipped_no_url"] += 1
                continue
            key = f"instagram:{cid}"
            item = items.get(key)
            if item is None:
                item = {"id": item_id(key), "platform": "instagram", "source_url": r["url"], "dedup_key": key,
                        "first_seen_at": iso(r["ts"]), "caption": r["caption"],
                        "platform_data": {"media_kind": "reel" if kind_ig == "reel" else "post",
                                          "owner_handle": r["owner"].get("username"),
                                          "owner_name": r["owner"].get("name"),
                                          "hashtags": r["hashtags"], "collections": []}}
                items[key] = item
            else:
                if r["caption"] and not item["caption"]:
                    item["caption"] = r["caption"]
                if r["ts"] and iso(r["ts"]) < (item["first_seen_at"] or "9999"):
                    item["first_seen_at"] = iso(r["ts"])
            interactions.append({"item_id": item["id"], "kind": kind, "at": iso(r["ts"]),
                                 "capture_method": "export_import", "weight": weight})
            counts[kind] += 1
    zn = ex.find(COLLECTIONS)
    for name, urls in collection_groups(ex.load(zn)) if zn else []:
        for u in urls:
            kind_ig, cid = content_id(u)
            if not cid:
                continue
            key = f"instagram:{cid}"
            item = items.get(key)
            if item is None:  # in a collection but not in the saved_posts list
                item = {"id": item_id(key), "platform": "instagram", "source_url": u, "dedup_key": key,
                        "first_seen_at": None, "caption": "",
                        "platform_data": {"media_kind": "reel" if kind_ig == "reel" else "post",
                                          "owner_handle": None, "owner_name": None, "hashtags": [],
                                          "collections": []}}
                items[key] = item
                counts["collection_only_items"] += 1
            if name not in item["platform_data"]["collections"]:
                item["platform_data"]["collections"].append(name)
                interactions.append({"item_id": item["id"], "kind": "collection", "at": None,
                                     "capture_method": "export_import", "weight": 0.8, "collection_name": name})
                counts["collection"] += 1
    _shares(ex, items, interactions, counts, own_names)
    by_item = collections.defaultdict(list)
    for it in interactions:
        by_item[it["item_id"]].append(it)
    for item in items.values():
        its = by_item[item["id"]]
        item["importance"] = round(min(1.0, sum(i["weight"] for i in its)), 3)
        item["processing_depth"] = max((DEPTH[i["kind"]] for i in its), key=RANK.get)
        item["interaction_kinds"] = sorted({i["kind"] for i in its})
    # social graph -> owner_relation; then friends' posts leave the library
    fz, gz = ex.matching(FOLLOWERS), ex.matching(FOLLOWING)
    followers = set().union(*[handles(ex.load(x)) for x in fz]) if fz else set()
    following = set().union(*[handles(ex.load(x)) for x in gz]) if gz else set()
    mutual = followers & following
    for item in items.values():
        h = (item["platform_data"].get("owner_handle") or "").lower()
        item["platform_data"]["owner_relation"] = "mutual" if h in mutual else "following" if h in following \
            else "none"
    friends = {it["id"] for it in items.values() if it["platform_data"]["owner_relation"] == "mutual"}
    out_items = [it for it in items.values() if it["id"] not in friends]
    out_inter = [r for r in interactions if r["item_id"] not in friends]
    stats = {"items": len(out_items), "interactions": len(out_inter), "friends_posts_removed": len(friends),
             "followers_file": bool(fz), "following_file": bool(gz), **dict(counts)}
    if not (fz and gz):
        stats["warning"] = ("No followers / following lists in this export, so friends' posts could not be "
                            "detected and removed.")
    return out_items, out_inter, stats


def _shares(ex, items, interactions, counts, own_names):
    """shares_adapter.py over the export's DM threads, reading the share objects only."""
    threads = collections.defaultdict(lambda: {"parts": set(), "shares": []})
    senders = collections.Counter()
    for zn in ex.matching(DM_FILE):
        d = ex.load(zn)
        t = threads[d.get("thread_path") or posixpath.dirname(zn[1])]
        t["parts"] |= {fix(p.get("name")) for p in d.get("participants") or []}
        for m in d.get("messages") or []:
            sender = fix(m.get("sender_name"))
            senders[sender] += 1
            s = m.get("share")
            if isinstance(s, dict) and s.get("link"):
                t["shares"].append((sender, m.get("timestamp_ms"), s.get("link"), fix(s.get("share_text") or ""),
                                    fix(s.get("original_content_owner"))))
        del d  # nothing else from the message file is kept
    if not senders:
        return
    owner = senders.most_common(1)[0][0]
    own = {fix(n) for n in own_names if n} | {owner}
    for t in threads.values():
        is_self = t["parts"] <= own
        for sender, ts_ms, link, text, orig_owner in t["shares"]:
            if is_self:
                kind = "share_self"
            elif sender == owner:
                kind = "share_friend"
            else:
                counts["received_not_added"] += 1
                continue
            kind_ig, cid = content_id(link)
            if not cid:
                counts["skipped_non_post_link"] += 1
                continue
            key = f"instagram:{cid}"
            at = dt.datetime.fromtimestamp((ts_ms or 0) / 1000, dt.timezone.utc).isoformat()
            item = items.get(key)
            if item is None:
                item = {"id": item_id(key), "platform": "instagram", "source_url": link, "dedup_key": key,
                        "first_seen_at": at, "caption": text,
                        "platform_data": {"media_kind": "reel" if kind_ig == "reel" else "post",
                                          "owner_handle": orig_owner, "owner_name": None,
                                          "hashtags": re.findall(r"#(\w+)", text), "collections": []}}
                items[key] = item
                counts["share_new_items"] += 1
            else:
                if text and not (item["caption"] or "").strip():
                    item["caption"] = text
                    item["platform_data"]["hashtags"] = item["platform_data"]["hashtags"] or \
                        re.findall(r"#(\w+)", text)
                if not item["platform_data"].get("owner_handle") and orig_owner:
                    item["platform_data"]["owner_handle"] = orig_owner
                if at < (item["first_seen_at"] or "9999"):
                    item["first_seen_at"] = at
            interactions.append({"item_id": item["id"], "kind": kind, "at": at, "capture_method": "dm_share",
                                 "weight": SHARE_WEIGHT[kind], "sent_by_owner_account": sender == owner})
            counts[kind] += 1
