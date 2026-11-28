"""PROTOTYPE ONLY - round 12, D (DESIGN.md section 19.D): the official length of every YouTube video the person watched.

An export says only that a video was opened, and when: never how long it ran or how long it was watched. The length
of a video is public metadata the YouTube Data API returns (videos.list, contentDetails.duration; docs/04-intake.md,
the data contract's `duration_s`). This enricher asks for it, 50 ids a call (1 quota unit a call), with the key from
YOUTUBE_API_KEY sent in the X-Goog-Api-Key header (never in a URL, never printed or logged), and writes a derived,
versioned file:

    <derived>/lengths-v1/lengths.jsonl   one row per video id: {video_id, length_s (None: no answer), published,
                                          fetched_at, refresh_by, version}
    <derived>/lengths-v1/runs.jsonl      one row per run: items asked, answered, missing, calls, quota units, wall
                                          time, items per second

<derived> is MVP_DERIVED_HOME, else data/mvp/derived (gitignored). The file is keyed by video id only: public content,
no person in it (docs/07, the shared enrichment cache). A video the API does not return (deleted, private) has no
length and is counted. Rows are kept 30 days (Developer Policies III.E.4, docs/04-intake.md `refresh_by`): a row past
its refresh_by is asked again on the next run and is not used until then. Resumable: each batch is appended as it
comes back, so a run cut off goes on where it stopped. Nothing is ever fetched but videos.list (no page, no media,
no transcript).

A Short is decided by code (`is_short`) from the length and the title's own marks; DESIGN 19.D says how the rule was
chosen from the data (the candidates and how many of the founder's watches each one calls Short).
"""
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config

VERSION = "lengths-v1"
BATCH = 50
MAX_UNITS = 6000           # the round's ceiling for one run (the daily quota is 10,000)
KEEP_DAYS = 30
API = "https://www.googleapis.com/youtube/v3/videos"
FIELDS = "items(id,contentDetails/duration,snippet/publishedAt)"
_LOCK = threading.Lock()
_CACHE = {}


def derived_home():
    return os.path.abspath(os.environ.get("MVP_DERIVED_HOME") or os.path.join(config.REPO, "data", "mvp", "derived"))


def folder():
    return os.path.join(derived_home(), VERSION)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def fetch_batch(ids, key, timeout=20):
    """One videos.list call (contentDetails.duration and snippet.publishedAt only). Raises on any error; the error
    never carries the key."""
    sys.path.insert(0, os.path.join(config.EXP, "youtube"))
    from api_enrich import _ssl_ctx
    q = urllib.parse.urlencode({"part": "contentDetails,snippet", "id": ",".join(ids), "maxResults": BATCH,
                                "fields": FIELDS})
    req = urllib.request.Request(f"{API}?{q}", headers={"X-Goog-Api-Key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode("utf-8"))


def parse(resp, ids):
    """videos.list response -> {video_id: (length_s or None, published date 'YYYY-MM-DD' or None)} for every id asked;
    an id not returned has (None, None). A live stream's P0D is no length."""
    sys.path.insert(0, os.path.join(config.EXP, "youtube"))
    from api_enrich import parse_duration
    if not isinstance(resp, dict) or not isinstance(resp.get("items") or [], list):
        raise ValueError("unexpected videos.list response")
    want = set(ids)
    out = {}
    for v in resp.get("items") or []:
        vid = v.get("id") if isinstance(v, dict) else None
        if vid not in want:
            continue
        dur = parse_duration(((v.get("contentDetails") or {}).get("duration")) or "") or None
        pub = (v.get("snippet") or {}).get("publishedAt")
        pub = pub[:10] if isinstance(pub, str) and re.match(r"\d{4}-\d\d-\d\d", pub) else None
        out[vid] = (dur, pub)
    for vid in ids:
        out.setdefault(vid, (None, None))
    return out


def watched_video_ids(lib):
    """The YouTube video ids the person watched (a watch or view event), in the order of the library's items."""
    corpus = os.path.join(lib, "corpus")
    vid_of = {}
    with open(os.path.join(corpus, "items.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("platform") == "youtube":
                v = (r.get("platform_data") or {}).get("video_id")
                if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", v):
                    vid_of[r["id"]] = v
    seen, out = set(), []
    with open(os.path.join(corpus, "interactions.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            v = vid_of.get(r.get("item_id"))
            if v and r.get("kind") in ("watch", "view") and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def _read_rows(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("video_id") and r.get("version") == VERSION:
                rows[r["video_id"]] = r     # the latest row of an id wins (a refresh appends)
    return rows


def run(lib, key=None, fetch=None, max_units=MAX_UNITS, now=None, log=print):
    """Ask for the length of every watched video with no fresh row; append each batch. Returns the run's numbers."""
    from .settings import secret
    key = key or secret(config.YOUTUBE_KEY_ENV)
    if not key and fetch is None:
        raise RuntimeError("no YouTube key in the environment")
    now = now or datetime.now(timezone.utc)
    os.makedirs(folder(), exist_ok=True)
    path = os.path.join(folder(), "lengths.jsonl")
    have = _read_rows(path)
    fresh = {v for v, r in have.items() if str(r.get("refresh_by") or "") > _iso(now)}
    want = [v for v in watched_video_ids(lib) if v not in fresh]
    t0 = time.monotonic()
    calls = got = missing = errors = 0
    with open(path, "a", encoding="utf-8") as out:
        for i in range(0, len(want), BATCH):
            if calls >= max_units:
                break
            chunk = want[i:i + BATCH]
            try:
                parsed = parse((fetch or fetch_batch)(chunk, key), chunk)
            except Exception as e:  # noqa: BLE001 - the type only; the URL and headers are never logged
                errors += 1
                log(f"batch {i // BATCH}: {type(e).__name__}")
                if errors >= 5:
                    break
                time.sleep(min(2 * errors, 10))
                continue
            calls += 1
            at = datetime.now(timezone.utc) if fetch is None else now
            for vid in chunk:
                length, pub = parsed[vid]
                got += length is not None
                missing += length is None
                out.write(json.dumps({"video_id": vid, "length_s": length, "published": pub, "fetched_at": _iso(at),
                                      "refresh_by": _iso(at + timedelta(days=KEEP_DAYS)), "version": VERSION}) + "\n")
            out.flush()
            if calls % 100 == 0:
                el = time.monotonic() - t0
                log(f"{calls} calls, {got + missing} items, {(got + missing) / max(el, 1e-6):.0f} items/s")
    wall = round(time.monotonic() - t0, 2)
    n = got + missing
    stats = {"version": VERSION, "at": _iso(now), "asked": len(want), "processed": n, "with_length": got,
             "no_answer": missing, "calls": calls, "quota_units": calls, "errors": errors, "wall_s": wall,
             "items_per_s": round(n / wall, 1) if wall else None, "already_fresh": len(fresh)}
    with open(os.path.join(folder(), "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(stats) + "\n")
    log(json.dumps(stats))
    with _LOCK:
        _CACHE.clear()
    return stats


def load(now=None):
    """{video_id: (length_s or None, published or None)} of the rows still inside their 30 days. Cached by the file's
    stamp."""
    path = os.path.join(folder(), "lengths.jsonl")
    try:
        st = os.stat(path)
    except OSError:
        return {}
    now_s = _iso(now or datetime.now(timezone.utc))
    key = (path, st.st_mtime_ns, st.st_size, now_s[:13])
    with _LOCK:
        if _CACHE.get("key") == key:
            return _CACHE["rows"]
    rows = {v: (r.get("length_s"), r.get("published")) for v, r in _read_rows(path).items()
            if str(r.get("refresh_by") or "") > now_s}
    with _LOCK:
        _CACHE.clear()
        _CACHE.update(key=key, rows=rows)
    return rows


# ---------------------------------------------------------------- Shorts
# The title's own marks: "#shorts" and its usual spellings. A mark alone does not make a long video a Short.
SHORT_MARK = re.compile(r"#\s?(?:yt|youtube)?shorts?\b|\byoutube\s+shorts\b|\(shorts?\)|\[shorts?\]|\|\s*shorts\s*$",
                        re.I)
SHORT_MAX = 61             # seconds: always a Short at or under this (the API gives many 60-second Shorts as 61)
SHORT_LONG_MAX = 180       # seconds: since 15 Oct 2024 a Short may run to 3 minutes
LONG_SHORTS_FROM = "2024-10-15"


def is_short(length_s, title, published=None):
    """True: a Short; False: a long video; None: unknown (no length). The rule, chosen from the founder's own
    lengths (DESIGN 19.D): at most 61 seconds; or at most 180 seconds for a video published on or after 15 October
    2024 (the lengths of those videos fall off a cliff at 180 seconds, the older ones' do not); or, with no date
    known, at most 180 seconds with the title's own Shorts mark."""
    if not length_s:
        return None
    if length_s <= SHORT_MAX:
        return True
    if length_s <= SHORT_LONG_MAX:
        if published:
            return published >= LONG_SHORTS_FROM
        return bool(SHORT_MARK.search(title or ""))
    return False


def length_of(item, rows=None):
    """(length_s or None, is_short or None) of a libview Item: this enricher's row first, the corpus's own duration_s
    second (an earlier import of the same API field)."""
    if getattr(item, "platform", None) != "youtube":
        return None, None
    rows = load() if rows is None else rows
    r = rows.get(item.video_id or "")
    length, pub = (r if r else (None, None))
    if length is None and r is None:
        length = item.duration_s or None
    return length, is_short(length, item.caption, pub)


if __name__ == "__main__":   # python3 -m mvp.lengths <library>
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("--max-units", type=int, default=MAX_UNITS)
    a = ap.parse_args()
    run(os.path.abspath(a.library), max_units=a.max_units)
