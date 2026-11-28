"""PROTOTYPE ONLY - YouTube Data API v3 enricher (tier 0) for the search experiments.

For every item from takeout_import.py, calls `videos.list` (part=snippet,contentDetails,topicDetails) in batches of
50 IDs. One call costs 1 quota unit whatever the number of IDs or parts; the default project quota is 10,000
units/day (https://developers.google.com/youtube/v3/determine_quota_cost). So 20,000 videos = 400 calls = 400 units,
4% of one day's quota, and the same again every 30 days to refresh (see quota_estimate()).

Output, one row per video (enrich.jsonl), shaped like the contract's `enrichments` row (provider youtube_api, tier 0):
  code, ok, status (ok | unavailable), provider, tier, title, caption (= description), hashtags (= API tags),
  creator {name, id, url}, thumbnail_url (best returned), thumbnails {size: url} as returned, duration_s,
  posted_at, chapters [{start_s, title}], topic_categories, category_id, default_audio_language, live,
  cost_usd (0), fetched_at, refresh_by (fetched_at + 30 days: Developer Policies III.E.4.c)
  `title`, `topic_categories`, `category_id`, `default_audio_language`, `live` are NOT in the enrichments contract
  yet: see PLAN.md (a Proposed amendment is needed before product code uses them).
plus text.json = {video_id: tier-0 search text}, the same shape as data/enrich/text_*.json, so it plugs into
lib/corpus.py Corpus(extra_text=...) unchanged. Raw API responses are kept under raw/ with refresh_by (raw layer).

Terms (https://developers.google.com/youtube/terms/developer-policies): API Data must be refreshed or deleted after
30 days (III.E.4.c) and deleted within 7 days of a user's request (III.E.4.g); III.E.4.h forbids using API Data "to
create new or derived data or metrics", so embeddings of API text are an open legal question (docs/07 open check):
experiments only, re-derived on every refresh. No audio/video is downloaded (III.E.1). Thumbnails are used by URL.

Key: YOUTUBE_API_KEY from the environment, sent as the X-Goog-Api-Key header (never in the URL, never printed).
Without a key the live call is skipped; --response FILE parses a saved (or synthetic) videos.list response instead.
Descriptions, titles and tags are third-party text: data, never instructions. Logs carry counts only.

usage:
  python experiments/youtube/api_enrich.py --items $DIGESTER_DATA/youtube/corpus/items.jsonl \
      [--out $DIGESTER_DATA/youtube/enrich] [--response fixtures/videos_list_response.json] [--quota 20000]
"""
import argparse
import json
import math
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://www.googleapis.com/youtube/v3/videos"
PARTS = "snippet,contentDetails,topicDetails"
BATCH = 50
DAILY_QUOTA = 10_000
REFRESH_DAYS = 30
THUMB_ORDER = ["maxres", "standard", "high", "medium", "default"]

# ---------------- parsing ----------------
_DUR = re.compile(r"^P(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$")


def parse_duration(s):
    """ISO 8601 duration as the API returns it ('PT15M33S', 'PT1H2M3S', 'P1DT2H', 'P0D' for live) -> seconds or None."""
    if not s:
        return None
    m = _DUR.match(s.strip())
    if not m or s.strip() in ("P", "PT"):
        return None
    g = {k: float(v) if v else 0.0 for k, v in m.groupdict().items()}
    return int(round(g["w"] * 604800 + g["d"] * 86400 + g["h"] * 3600 + g["m"] * 60 + g["s"]))


_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})"
_LEAD = re.compile(r"^\s*[\[(]?" + _TS + r"[\])]?\s*(?:[-–—:|.)]\s*)?(.+?)\s*$")
_TRAIL = re.compile(r"^\s*(.+?)\s*(?:[-–—:|]\s*)?[\[(]?" + _TS + r"[\])]?\s*$")


def _secs(h, m, s):
    return int(h or 0) * 3600 + int(m) * 60 + int(s)


def parse_chapters(description, duration_s=None):
    """Chapters from description lines like '0:00 Intro', '00:00 - Intro', '1:02:03 Part 3', 'Intro 0:00'.

    Applies YouTube's own rules (https://support.google.com/youtube/answer/9884579): the first timestamp is 0:00,
    at least three timestamps in ascending order, each chapter at least 10 s. If they fail, returns [] (YouTube
    would show no chapters either). Timestamps past the duration are dropped when the duration is known.
    """
    lead, trail = [], []
    for line in (description or "").splitlines():
        m = _LEAD.match(line)
        if m:
            lead.append((_secs(m.group(1), m.group(2), m.group(3)), m.group(4)))
            continue
        m = _TRAIL.match(line)
        if m:
            trail.append((_secs(m.group(2), m.group(3), m.group(4)), m.group(1)))
    # leading timestamps ('0:00 Intro') are the usual form; 'Intro 0:00' is tried only if they don't validate
    return _valid_chapters(lead, duration_s) or _valid_chapters(trail, duration_s)


def _valid_chapters(pairs, duration_s):
    out = []
    for t, title in pairs:
        title = title.strip(" -–—:|")
        if title and not re.fullmatch(_TS, title):
            out.append({"start_s": t, "title": title[:100]})
    if duration_s:
        out = [c for c in out if c["start_s"] < duration_s]
    if len(out) < 3 or out[0]["start_s"] != 0:
        return []
    for a, b in zip(out, out[1:]):
        if b["start_s"] - a["start_s"] < 10:
            return []
    if duration_s and duration_s - out[-1]["start_s"] < 10:
        return []
    return out


def best_thumbnail(thumbs):
    for k in THUMB_ORDER:
        if (thumbs or {}).get(k, {}).get("url"):
            return thumbs[k]["url"]
    for v in (thumbs or {}).values():  # fhd/qhd/uhd or anything new
        if v.get("url"):
            return v["url"]
    return None


def topic_names(urls):
    """'https://en.wikipedia.org/wiki/Food' -> 'Food' (topicCategories are Wikipedia URLs)."""
    return [urllib.parse.unquote(u.rsplit("/", 1)[-1]).replace("_", " ") for u in urls or []]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_video(v, fetched_at):
    sn, cd, td = v.get("snippet") or {}, v.get("contentDetails") or {}, v.get("topicDetails") or {}
    dur = parse_duration(cd.get("duration"))
    if dur == 0 and (sn.get("liveBroadcastContent") or "none") != "none":
        dur = None  # live/upcoming streams report P0D: no duration yet
    desc = sn.get("description") or ""
    cid = sn.get("channelId")
    refresh = (datetime.fromisoformat(fetched_at) + timedelta(days=REFRESH_DAYS)).isoformat(timespec="seconds")
    return {
        "code": v["id"], "ok": True, "status": "ok", "provider": "youtube_api", "tier": 0,
        "title": sn.get("title") or "",
        "caption": desc,
        "hashtags": list(sn.get("tags") or []),
        "creator": {"name": sn.get("channelTitle"), "id": cid,
                    "url": f"https://www.youtube.com/channel/{cid}" if cid else None},
        "thumbnail_url": best_thumbnail(sn.get("thumbnails")),
        "thumbnails": {k: t.get("url") for k, t in (sn.get("thumbnails") or {}).items() if t.get("url")},
        "duration_s": dur,
        "posted_at": sn.get("publishedAt"),
        "chapters": parse_chapters(desc, dur),
        "topic_categories": topic_names(td.get("topicCategories")),
        "category_id": sn.get("categoryId"),
        "default_audio_language": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage"),
        "live": sn.get("liveBroadcastContent") or "none",
        "cost_usd": 0.0, "fetched_at": fetched_at, "refresh_by": refresh,
    }


def parse_response(resp, requested_ids, fetched_at=None):
    """videos.list response -> {video_id: row}. IDs asked for but not returned = deleted/private/unavailable."""
    fetched_at = fetched_at or now_iso()
    rows = {v["id"]: parse_video(v, fetched_at) for v in resp.get("items") or [] if v.get("id")}
    refresh = (datetime.fromisoformat(fetched_at) + timedelta(days=REFRESH_DAYS)).isoformat(timespec="seconds")
    for vid in requested_ids:
        if vid not in rows:
            rows[vid] = {"code": vid, "ok": False, "status": "unavailable", "provider": "youtube_api", "tier": 0,
                         "cost_usd": 0.0, "fetched_at": fetched_at, "refresh_by": refresh}
    return rows


def platform_data_patch(row):
    """The contract's platform_data.youtube fields this row fills (channel_id, channel_title, duration_s, chapters)."""
    if not row.get("ok"):
        return {}
    p = {"channel_id": row["creator"]["id"], "channel_title": row["creator"]["name"],
         "duration_s": row["duration_s"], "chapters": row["chapters"]}
    return {k: v for k, v in p.items() if v not in (None, [])}


_URL = re.compile(r"https?://\S+")


def clean_description(desc, chapters):
    """Description without URLs and without the chapter lines (their titles are added separately)."""
    lines = []
    for line in (desc or "").splitlines():
        if chapters and (_LEAD.match(line) or _TRAIL.match(line)):
            continue
        line = _URL.sub(" ", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines)


def tier0_text(item, row=None):
    """Tier-0 search text: title + channel + tags + chapter titles + description (600 chars) + topics.

    Mirrors lib/corpus.py's 'full' view (caption[:600] + hashtags + creator) so BM25/dense legs treat both platforms
    alike. Takeout-only items (no row) fall back to the Takeout title and channel.
    """
    pd = item.get("platform_data") or {}
    title = (row or {}).get("title") or item.get("caption") or ""
    channel = ((row or {}).get("creator") or {}).get("name") or pd.get("channel_title") or ""
    parts = [title, f"by {channel}" if channel else ""]
    if row and row.get("ok"):
        parts.append(" ".join("#" + t.replace(" ", "") for t in row["hashtags"][:15]))
        parts.append(" ".join(t for t in row["hashtags"][:15]))
        if row["chapters"]:
            parts.append("chapters: " + " · ".join(c["title"] for c in row["chapters"]))
        parts.append(clean_description(row["caption"], row["chapters"])[:600])
        if row["topic_categories"]:
            parts.append("topics: " + ", ".join(row["topic_categories"]))
    return " ".join(" ".join(p for p in parts if p).split())


def quota_estimate(n_videos, daily=DAILY_QUOTA, batch=BATCH):
    calls = math.ceil(n_videos / batch)
    return {"videos": n_videos, "calls": calls, "units": calls, "share_of_daily_quota": round(calls / daily, 4),
            "days_at_default_quota": math.ceil(calls / daily) if calls else 0,
            "refresh_units_per_30_days": calls,
            "users_backfilled_per_day_at_default_quota": daily // calls if calls else None}


# ---------------- live call ----------------
def _ssl_ctx():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca and os.path.exists(ca) else ssl.create_default_context()


def fetch_batch(ids, key, timeout=30):
    q = urllib.parse.urlencode({"part": PARTS, "id": ",".join(ids)})
    req = urllib.request.Request(f"{API}?{q}", headers={"X-Goog-Api-Key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_all(ids, key, raw_dir=None, sleep_s=0.1):
    rows, units = {}, 0
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        fetched_at = now_iso()
        try:
            resp = fetch_batch(chunk, key)
        except urllib.error.HTTPError as e:  # never print e.url or headers: they could carry the key
            reason = ""
            try:
                reason = json.loads(e.read().decode())["error"]["errors"][0]["reason"]
            except (ValueError, KeyError, IndexError, TypeError):
                pass  # no structured reason in the body
            print(f"videos.list batch {i // BATCH}: HTTP {e.code} {reason}; stopping", file=sys.stderr)
            break
        units += 1
        if raw_dir:
            os.makedirs(raw_dir, exist_ok=True)
            refresh = (datetime.fromisoformat(fetched_at) + timedelta(days=REFRESH_DAYS)).isoformat()
            json.dump({"source": "youtube_api", "kind": "videos_list", "received_at": fetched_at,
                       "refresh_by": refresh, "requested_ids": chunk, "payload": resp},
                      open(os.path.join(raw_dir, f"videos_list_{i // BATCH:05d}.json"), "w"))
        rows.update(parse_response(resp, chunk, fetched_at))
        time.sleep(sleep_s)
    return rows, units


# ---------------- main ----------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", help="items.jsonl from takeout_import.py")
    ap.add_argument("--out", help="output folder (default $DIGESTER_DATA/youtube/enrich)")
    ap.add_argument("--response", help="parse this saved videos.list response instead of calling the API")
    ap.add_argument("--quota", type=int, help="print the quota estimate for N videos and exit")
    a = ap.parse_args(argv)
    if a.quota is not None:
        print(json.dumps(quota_estimate(a.quota)))
        return
    if not a.items:
        ap.error("--items is required")
    data = os.environ.get("DIGESTER_DATA", os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"))
    out = a.out or os.path.join(data, "youtube", "enrich")
    items = [json.loads(l) for l in open(a.items, encoding="utf-8")]
    ids = sorted({it["platform_data"]["video_id"] for it in items})
    t0 = time.time()
    units = 0
    if a.response:
        rows = parse_response(json.load(open(a.response, encoding="utf-8")), ids)
        mode = "offline response"
    elif os.environ.get("YOUTUBE_API_KEY"):
        rows, units = fetch_all(ids, os.environ["YOUTUBE_API_KEY"], raw_dir=os.path.join(out, "raw"))
        mode = "live"
    else:
        print("YOUTUBE_API_KEY not set: skipping the live videos.list call; writing Takeout-only tier-0 text",
              file=sys.stderr)
        rows, mode = {}, "takeout only"
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "enrich.jsonl"), "w", encoding="utf-8") as f:
        for vid in sorted(rows):
            f.write(json.dumps(rows[vid], ensure_ascii=False) + "\n")
    text = {it["platform_data"]["video_id"]: tier0_text(it, rows.get(it["platform_data"]["video_id"]))
            for it in items}
    json.dump(text, open(os.path.join(out, "text.json"), "w"), ensure_ascii=False)
    wall = time.time() - t0
    stats = {"mode": mode, "videos": len(ids), "rows": len(rows),
             "ok": sum(1 for r in rows.values() if r.get("ok")),
             "unavailable": sum(1 for r in rows.values() if not r.get("ok")),
             "with_chapters": sum(1 for r in rows.values() if r.get("chapters")),
             "quota_units_used": units, "quota_estimate": quota_estimate(len(ids)),
             "wall_s": round(wall, 3), "items_per_s": round(len(ids) / wall, 1) if wall else None}
    json.dump(stats, open(os.path.join(out, "enrich_stats.json"), "w"), indent=1)
    print(json.dumps(stats), file=sys.stderr)
    return stats


if __name__ == "__main__":
    main()
