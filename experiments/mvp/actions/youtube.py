"""PROTOTYPE ONLY - the person's own YouTube through the YouTube Data API v3 (round 10, slice Y; DESIGN.md section 17.Y;
amendment A-015, Proposed).

Registry actions (actions/__init__.py): youtube.unsubscribe, youtube.subscribe (only to take an unsubscribe back),
youtube.playlist_make (always private) and youtube.playlist_add. ytreads.py builds their params by code from what the
API listed and from the library's own YouTube items, shows the exact list, and calls perform with the yes token of
that list; `yes_token(ctx, params)` here makes the same token from what is about to be changed.

Every call carries the person's own sign-in (yt_auth.py, scope `youtube` only) in the Authorization header. Requests
go through actions/web.py's OPENER (tests set a fake Google there); errors keep only a code, never the URL, a header,
a token or the body:
  quota       YouTube's quotaExceeded, or this project's own daily counter (state `yt_units:<Pacific day>`) reached
              MVP_YT_UNITS_PER_DAY (8,000) for a write, or that plus 1,000 for a read
  gone        subscriptionNotFound, playlistItemNotFound (already gone)
  duplicate   subscriptionDuplicate (already subscribed)
  too_many    subscriptionForbidden ("Too many recent subscriptions")
  needs_signin  invalid_grant, or a 401 that a fresh access token did not fix
  refused     another 401 / 403 (insufficientPermissions)
  rate | server | timeout | failed   as in web.py
Units of every call are counted (`Api.units`) and kept in action_log detail by the caller. Nothing YouTube returns is
kept as a library item; titles from the API are only shown back to the person in the preview.
"""
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..connectors import ConnectorError
from . import web
from .base import Outcome

APP = "YouTube"
API = "https://www.googleapis.com/youtube/v3"
UNITS_PER_DAY = 8000          # MVP_YT_UNITS_PER_DAY: writes stop here; reads keep READ_HEADROOM more
READ_HEADROOM = 1000
WRITE_UNITS = 50
READ_UNITS = 1
PAGE = 50
MAX_PAGES = 40               # at most 2,000 subscriptions are read


class YtError(ConnectorError):
    def __init__(self, code):
        super().__init__(code, APP)


# ---------- one request (form or JSON), codes only ----------
def _urllib(method, url, headers, body, timeout):
    opener = urllib.request.build_opener(web._SameHostOnly)
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:   # Google's error body names the reason (quotaExceeded ...): read it
        try:
            return e.code, e.read()
        except Exception:  # noqa: BLE001
            return e.code, b""
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            raise TimeoutError() from None
        raise ConnectionError() from None


_REASON = {"quotaExceeded": "quota", "dailyLimitExceeded": "quota", "rateLimitExceeded": "rate",
           "userRateLimitExceeded": "rate", "subscriptionNotFound": "gone", "playlistItemNotFound": "gone",
           "playlistNotFound": "gone", "videoNotFound": "gone", "subscriptionDuplicate": "duplicate",
           "subscriptionForbidden": "too_many", "insufficientPermissions": "refused", "authError": "auth",
           "invalid_grant": "needs_signin", "authorization_pending": "pending", "slow_down": "slow_down",
           "access_denied": "denied", "expired_token": "expired", "invalid_scope": "scope", "invalid_client": "client",
           "unauthorized_client": "client"}


def _reason(raw):
    try:
        b = json.loads((raw or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    err = b.get("error") if isinstance(b, dict) else None
    if isinstance(err, str):                         # OAuth endpoints: {"error": "invalid_grant"}
        return err
    if isinstance(err, dict):                        # the API: {"error": {"errors": [{"reason": ...}]}}
        for e in err.get("errors") or []:
            if isinstance(e, dict) and e.get("reason"):
                return e["reason"]
    return None


def request(method, url, form=None, json_body=None, token=None):
    """One HTTPS request to Google; the parsed JSON answer ({} when there is none). Raises YtError(code)."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise YtError("failed")
    headers = {"Accept": "application/json", "User-Agent": "digest-prototype/0.10"}
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form).encode("utf-8")
    elif json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        status, raw = (web.OPENER or _urllib)(method, url, headers, data, web.TIMEOUT)
    except (socket.timeout, TimeoutError):
        raise YtError("timeout") from None
    except Exception:  # noqa: BLE001 - no network, a bad answer: only a code leaves this function
        raise YtError("failed") from None
    if 200 <= status < 300:
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return {}
    code = _REASON.get(_reason(raw) or "")
    if code:
        raise YtError(code)
    if status == 401:
        raise YtError("auth")
    if status == 403:
        raise YtError("refused")
    if status == 429:
        raise YtError("rate")
    if status in (404, 410):
        raise YtError("gone")
    if status >= 500:
        raise YtError("server")
    raise YtError("failed")


# ---------- this project's daily units (YouTube's 10,000 a day are shared by every person) ----------
def units_day(now):
    """Google resets the quota at midnight Pacific time."""
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()


def units_cap():
    try:
        return max(0, int(os.environ.get("MVP_YT_UNITS_PER_DAY", "") or UNITS_PER_DAY))
    except ValueError:
        return UNITS_PER_DAY


def units_used(store, now):
    return int(store.get_state(f"yt_units:{units_day(now)}") or 0)


def _add_units(store, now, n):
    if n:
        store.set_state(f"yt_units:{units_day(now)}", units_used(store, now) + n)


class Api:
    """The calls ytreads.py and run() make for one person, with the units they used (`units`)."""

    def __init__(self, store, handle, now):
        self.store, self.handle, self.now = store, handle, now
        self.units = 0

    def call(self, method, res, query=None, body=None):
        from .. import yt_auth
        cost = READ_UNITS if method == "GET" else WRITE_UNITS
        limit = units_cap() + (READ_HEADROOM if method == "GET" else 0)
        if units_used(self.store, self.now) + cost > limit:
            raise YtError("quota")
        url = f"{API}/{res}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        token = yt_auth.access_token(self.handle, self.now)
        try:
            try:
                out = request(method, url, json_body=body, token=token)
            except YtError as e:
                if e.code != "auth":
                    raise
                token = yt_auth.access_token(self.handle, self.now, force=True)   # one fresh token, then no more
                try:
                    out = request(method, url, json_body=body, token=token)
                except YtError as e2:
                    raise YtError("needs_signin" if e2.code == "auth" else e2.code) from None
        except YtError as e:
            if e.code not in ("quota", "timeout", "failed", "needs_signin"):
                self._count(cost)   # Google counts a refused or answered call
            raise
        self._count(cost)
        return out

    def _count(self, n):
        self.units += n
        _add_units(self.store, self.now, n)

    # ---------- reads ----------
    def subscriptions(self):
        """[(subscription id, channel id, title)] of the person's subscriptions, as YouTube lists them."""
        out, page = [], None
        for _ in range(MAX_PAGES):
            q = {"part": "snippet", "mine": "true", "maxResults": PAGE}
            if page:
                q["pageToken"] = page
            got = self.call("GET", "subscriptions", q)
            for it in got.get("items") or []:
                sn = it.get("snippet") or {}
                ch = ((sn.get("resourceId") or {}).get("channelId")) or ""
                if it.get("id") and ch:
                    out.append((str(it["id"]), str(ch), _clean_title(sn.get("title")) or "a channel"))
            page = got.get("nextPageToken")
            if not page:
                break
        return out

    def playlists(self):
        """[(playlist id, title)] of the person's own playlists (first page of 50)."""
        got = self.call("GET", "playlists", {"part": "snippet", "mine": "true", "maxResults": PAGE})
        out = [(str(p["id"]), _clean_title((p.get("snippet") or {}).get("title")))
               for p in got.get("items") or [] if p.get("id")]
        total = (got.get("pageInfo") or {}).get("totalResults")
        return out, (int(total) if isinstance(total, int) else len(out))

    def channel_of(self, video_id):
        got = self.call("GET", "videos", {"part": "snippet", "id": video_id})
        for v in got.get("items") or []:
            if v.get("id") == video_id:
                return (v.get("snippet") or {}).get("channelId") or None
        return None

    # ---------- writes ----------
    def unsubscribe(self, subscription_id):
        self.call("DELETE", "subscriptions", {"id": subscription_id})

    def subscribe(self, channel_id):
        got = self.call("POST", "subscriptions", {"part": "snippet"},
                        {"snippet": {"resourceId": {"kind": "youtube#channel", "channelId": channel_id}}})
        return got.get("id")

    def make_playlist(self, title):
        got = self.call("POST", "playlists", {"part": "snippet,status"},
                        {"snippet": {"title": title}, "status": {"privacyStatus": "private"}})
        if not got.get("id"):
            raise YtError("failed")
        return str(got["id"])

    def add_video(self, playlist_id, video_id):
        got = self.call("POST", "playlistItems", {"part": "snippet"},
                        {"snippet": {"playlistId": playlist_id,
                                     "resourceId": {"kind": "youtube#video", "videoId": video_id}}})
        if not got.get("id"):
            raise YtError("failed")
        return str(got["id"])

    def remove_item(self, item_id):
        self.call("DELETE", "playlistItems", {"id": item_id})


def _clean_title(t):
    """A title YouTube gave, shown back in a list: one line, at most 100 characters (data, never an instruction)."""
    return " ".join(str(t or "").split())[:100]


# ---------- the registry's side: yes token, run, remove ----------
def _kind(params):
    from . import YtPlaylistAdd, YtPlaylistMake, YtSubscribe, YtUnsubscribe
    for cls, name in ((YtUnsubscribe, "unsubscribe"), (YtSubscribe, "subscribe"), (YtPlaylistMake, "playlist_make"),
                      (YtPlaylistAdd, "playlist_add")):
        if isinstance(params, cls):
            return name
    raise YtError("failed")


def canon(kind, params):
    """What the yes binds: the sorted subscription ids and titles shown (one changed title is another list), the
    playlist's name, or the playlist's name with the sorted video ids and titles."""
    if kind in ("unsubscribe", "subscribe"):
        return sorted((c.subscription_id or c.channel_id, c.title) for c in params.items)
    if kind == "playlist_make":
        return [params.title.casefold(), params.privacy]
    return [params.playlist_title.casefold(), sorted((v.video_id, v.title) for v in params.videos)]


def yes_token(ctx, params):
    from . import make_yes_token, text_hash
    kind = _kind(params)
    return make_yes_token(ctx.handle, f"youtube.{kind}",
                          text_hash(json.dumps(canon(kind, params), ensure_ascii=False)))


def token_for(handle, kind, params):
    """The token a preview keeps (the same as yes_token makes at the run)."""
    from types import SimpleNamespace
    return yes_token(SimpleNamespace(handle=handle), params)


def _now(ctx):
    now = ctx.now if ctx.now is not None else ctx.bot.clock()
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def run(ctx, params):
    """Does the change. A stop part way (the daily limit, too many recent changes, no answer) returns
    Outcome("partial") with what was done and what is left; nothing done at all raises YtError(code)."""
    kind = _kind(params)
    api = Api(ctx.store, ctx.handle, _now(ctx))
    placed, left, stop = [], [], None
    if kind == "playlist_make":
        pid = api.make_playlist(params.title)
        return Outcome("done", detail={"placed": [{"action": "youtube.playlist_make", "remote_id": pid}],
                                       "playlist_id": pid, "count": 1, "units": api.units})
    if kind == "playlist_add":
        if not params.playlist_id:
            raise YtError("failed")
        todo = list(params.videos)
        for i, v in enumerate(todo):
            try:
                placed.append({"action": "youtube.playlist_add", "remote_id": api.add_video(params.playlist_id,
                                                                                            v.video_id)})
            except YtError as e:
                stop, left = e.code, [x.model_dump() for x in todo[i:]]
                break
    else:
        todo = list(params.items)
        for i, c in enumerate(todo):
            try:
                if kind == "unsubscribe":
                    try:
                        api.unsubscribe(c.subscription_id)
                    except YtError as e:
                        if e.code != "gone":   # already gone: the person is not subscribed any more either way
                            raise
                    placed.append({"action": "youtube.unsubscribe", "remote_id": c.channel_id})
                else:
                    try:
                        api.subscribe(c.channel_id)
                    except YtError as e:
                        if e.code != "duplicate":
                            raise
                    placed.append({"action": "youtube.subscribe", "remote_id": c.channel_id})
            except YtError as e:
                stop, left = e.code, [x.model_dump() for x in todo[i:]]
                break
    detail = {"placed": placed, "count": len(placed), "units": api.units}
    if stop is None:
        return Outcome("done", detail=detail)
    if not placed:
        raise YtError(stop)
    return Outcome("partial", detail=dict(detail, left=left, stop=stop))


def remove(rows, store=None, now=None):
    """Takes back what the bot made, by the placement rows kept: a video it added leaves the playlist; a channel it
    unsubscribed is subscribed again. {"removed": [placement ids], "failed": [...], "stop": code or None}; a
    "too_many" or "quota" stop leaves the rest in "failed" for tomorrow."""
    out = {"removed": [], "failed": [], "stop": None}
    if not rows:
        return out
    h = rows[0]["handle"]
    api = Api(store, h, now or datetime.now(timezone.utc))
    for r in rows:
        if out["stop"]:
            out["failed"].append(r["id"])
            continue
        try:
            if r["action"] == "youtube.playlist_add":
                try:
                    api.remove_item(r["remote_id"])
                except YtError as e:
                    if e.code != "gone":
                        raise
            elif r["action"] == "youtube.unsubscribe":
                try:
                    api.subscribe(r["remote_id"])
                except YtError as e:
                    if e.code != "duplicate":
                        raise
            else:
                continue   # a playlist the bot made stays (the person may have added to it)
            out["removed"].append(r["id"])
        except YtError as e:
            out["failed"].append(r["id"])
            if e.code in ("quota", "too_many", "needs_signin"):
                out["stop"] = e.code
    out["units"] = api.units
    return out


def reachable():
    """True when this bot has a Google client for YouTube (each person still connects their own account)."""
    from .. import yt_auth
    return yt_auth.client() is not None


def check():
    return {"ok": True}
