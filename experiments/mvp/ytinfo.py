"""PROTOTYPE ONLY - a YouTube video's length and description from the official videos.list endpoint (DESIGN.md section
11, "Answers"). Library YouTube items hold only a title; "under 10 minutes" or "ends with a finished model" needs more.

For the candidates shown to the composer only: one call per 50 videos (1 quota unit each), key from YOUTUBE_API_KEY sent
in the X-Goog-Api-Key header (never in the URL, never printed or logged). Rows are kept at most 30 days in the store's
youtube_cache table (Developer Policies III.E.4), and details derived from a description expire with it. A video the
API does not return (private, deleted) is recorded as unavailable for the same period, so it is not asked for again.
Without a key, or on any error, what is cached is used and the bot works as before. The description is third-party
text: data, never instructions. Our server never fetches YouTube media.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config

sys.path.insert(0, os.path.join(config.EXP, "youtube"))
from api_enrich import _ssl_ctx, parse_duration  # noqa: E402

API = "https://www.googleapis.com/youtube/v3/videos"
BATCH = 50


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def fetch_batch(ids, key, timeout=None):
    """One videos.list call (snippet and contentDetails). Raises on any error; the error never carries the key."""
    q = urllib.parse.urlencode({"part": "snippet,contentDetails", "id": ",".join(ids), "maxResults": BATCH})
    req = urllib.request.Request(f"{API}?{q}", headers={"X-Goog-Api-Key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or config.YOUTUBE_TIMEOUT, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode("utf-8"))


def parse(resp, ids):
    """videos.list response -> {video_id: (ok, duration_s, description)}; ids not returned are unavailable."""
    out = {}
    for v in resp.get("items") or []:
        vid = v.get("id")
        if not vid:
            continue
        sn, cd = v.get("snippet") or {}, v.get("contentDetails") or {}
        dur = parse_duration(cd.get("duration"))
        if not dur:
            dur = None   # live and upcoming streams report P0D
        out[vid] = (1, dur, (sn.get("description") or "")[:5000])
    for vid in ids:
        out.setdefault(vid, (0, None, ""))
    return out


class YouTubeInfo:
    """details(items, now) -> {item_id: {"duration_s", "description"}} for the YouTube items among `items`."""

    def __init__(self, store, fetch=None, key_env=None):
        self.store = store
        self.fetch = fetch          # None: this module's fetch_batch
        self.key_env = key_env or config.YOUTUBE_KEY_ENV
        self.calls = 0      # API calls made by this object (each is one quota unit)
        self.errors = 0

    def details(self, items, now=None):
        now = now or datetime.now(timezone.utc)
        since = _iso(now - timedelta(days=config.YOUTUBE_KEEP_DAYS))
        self.store.purge_youtube(since)
        want = {it.video_id: it for it in items if it.platform == "youtube" and it.video_id}
        if not want:
            return {}
        marks = ",".join("?" * len(want))
        rows = {r["video_id"]: r for r in self.store.q(
            f"SELECT * FROM youtube_cache WHERE video_id IN ({marks}) AND fetched_at>=?", (*want, since))}
        missing = [v for v in want if v not in rows]
        key = os.environ.get(self.key_env)
        if missing and key:
            for i in range(0, len(missing), BATCH):
                chunk = missing[i:i + BATCH]
                try:
                    got = parse((self.fetch or fetch_batch)(chunk, key), chunk)
                    self.calls += 1
                except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                    self.errors += 1   # the type only; the request URL and headers are never logged
                    break
                at = _iso(now)
                for vid, (ok, dur, desc) in got.items():
                    self.store.x("INSERT OR REPLACE INTO youtube_cache(video_id,ok,duration_s,description,fetched_at) "
                                 "VALUES(?,?,?,?,?)", (vid, ok, dur, desc, at))
                    rows[vid] = {"video_id": vid, "ok": ok, "duration_s": dur, "description": desc, "fetched_at": at}
        out = {}
        for vid, it in want.items():
            r = rows.get(vid)
            if r and r["ok"]:
                out[it.id] = {"duration_s": r["duration_s"], "description": r["description"] or "",
                              "fetched_at": r["fetched_at"]}
        return out


def minutes_text(seconds):
    """'12 minutes', '1 hour 5 minutes', 'under a minute': a video's length in words, computed by code."""
    if not seconds:
        return None
    m = int(round(seconds / 60))
    if m < 1:
        return "under a minute"
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''}"
    h, m = divmod(m, 60)
    return f"{h} hour{'s' if h != 1 else ''}" + (f" {m} minute{'s' if m != 1 else ''}" if m else "")
