"""A fake Google for the YouTube connector, in process (round 10, slice K; port of the social research prototype):
the OAuth device flow and a YouTube Data API v3 subset with its quota costs and error shapes. Made-up data; no port.

It is an opener for actions/web.py (`OPENER(method, url, headers, body_bytes, timeout) -> (status, body_bytes)`):

    from mvp.tests.fakes.fake_google import FakeGoogle
    g = FakeGoogle()
    monkeypatch.setattr(web, "OPENER", g)        # every https call to Google's hosts lands here; any other host fails
    g.add_channels(["UCaaa", "UCbbb"])           # subscriptions of the signed-in person
    g.add_video("vid00000001", "UCaaa")          # videos.list knows it (snippet.channelId)
    g.approve()                                  # the person typed the code at google.com/device (else: pending)

Endpoints (shapes from the pages read on 17 Nov 2026):
  POST https://oauth2.googleapis.com/device/code   form: client_id, scope. A scope other than youtube / youtube.readonly
                                                   (force-ssl, gmail ...) answers 400 invalid_scope
  POST https://oauth2.googleapis.com/token         device_code grant: 428 authorization_pending | 403 access_denied |
                                                   400 slow_down (knob) | 400 expired_token | 200 tokens;
                                                   refresh_token grant: 200, or 400 invalid_grant after withdraw()
  POST https://oauth2.googleapis.com/revoke        form: token
  https://www.googleapis.com/youtube/v3/  GET subscriptions?mine=true (paged by maxResults / pageToken),
      DELETE subscriptions?id=, POST subscriptions, GET playlists?mine=true, POST playlists, POST playlistItems,
      DELETE playlistItems?id=, GET videos?id= (snippet.channelId), GET channels?mine=true
Errors keep Google's body: {"error": {"code", "message", "errors": [{"reason"}]}}; 401 authError on a bad token, 403
insufficientPermissions for a write with a read-only scope, 403 quotaExceeded when the units run out, 404
subscriptionNotFound / playlistItemNotFound, 400 subscriptionDuplicate, and 400 subscriptionForbidden ("Too many
recent subscriptions") after `recent_sub_limit` inserts.

Knobs: quota (units left today; COST per call), recent_sub_limit, slow_down (True: the next poll answers slow_down),
deny(), expire_device(), withdraw() (every token dies: refresh answers invalid_grant). Read back: calls
[(method, resource)], units_used, subs, playlists, revoked.
"""
import json
import urllib.parse

COST = {("GET", "subscriptions"): 1, ("POST", "subscriptions"): 50, ("DELETE", "subscriptions"): 50,
        ("GET", "playlists"): 1, ("POST", "playlists"): 50, ("POST", "playlistItems"): 50,
        ("DELETE", "playlistItems"): 50, ("GET", "videos"): 1, ("GET", "playlistItems"): 1, ("GET", "channels"): 1}
AUTH_HOST = "oauth2.googleapis.com"
API_HOST = "www.googleapis.com"
SCOPE_RW = "https://www.googleapis.com/auth/youtube"
SCOPE_RO = "https://www.googleapis.com/auth/youtube.readonly"


def _j(status, obj=None):
    return status, (json.dumps(obj).encode() if obj is not None else b"")


def _err(status, reason, msg=None):
    return _j(status, {"error": {"code": status, "message": msg or reason,
                                 "errors": [{"reason": reason, "message": msg or reason}]}})


class FakeGoogle:
    def __init__(self, quota=10_000, recent_sub_limit=None):
        self.quota = quota
        self.units_used = 0
        self.recent_sub_limit = recent_sub_limit
        self.inserts = 0
        self.slow_down = False
        self.device = {}          # device_code -> {"user_code", "state": pending|approved|denied|expired, "scopes"}
        self.tokens = {}          # access token -> scopes
        self.refresh = {}         # refresh token -> scopes
        self.revoked = []
        self.subs = {}            # subscription id -> channel id
        self.channels = {}        # channel id -> title
        self.videos = {}          # video id -> channel id
        self.playlists = {}       # playlist id -> {"title", "privacy", "items": {item id: video id}}
        self.calls = []
        self._n = 0

    def _id(self, p):
        self._n += 1
        return f"{p}{self._n:04d}"

    # ---------- test setup ----------
    def add_channels(self, ids, titles=None):
        for i, ch in enumerate(ids):
            self.channels[ch] = (titles or {}).get(ch) or f"Made-up channel {i + 1}"
            self.subs[self._id("sub")] = ch

    def add_video(self, video_id, channel_id):
        self.videos[video_id] = channel_id
        self.channels.setdefault(channel_id, f"Made-up channel {channel_id[-3:]}")

    def approve(self, user_code=None):
        for d in self.device.values():
            if d["state"] == "pending" and (user_code is None or d["user_code"] == user_code):
                d["state"] = "approved"

    def deny(self):
        for d in self.device.values():
            if d["state"] == "pending":
                d["state"] = "denied"

    def expire_device(self):
        for d in self.device.values():
            d["state"] = "expired"

    def withdraw(self):
        self.tokens.clear()
        self.refresh.clear()

    # ---------- the opener ----------
    def __call__(self, method, url, headers, body, timeout):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" or u.hostname not in (AUTH_HOST, API_HOST):
            raise ConnectionError("fake_google: not a Google host")
        q = dict(urllib.parse.parse_qsl(u.query))
        form = self._body(headers or {}, body)
        if u.hostname == AUTH_HOST:
            return self._auth(u.path, form)
        if not u.path.startswith("/youtube/v3/"):
            return _err(404, "notFound")
        tok = ((headers or {}).get("Authorization") or "").removeprefix("Bearer ")
        return self._api(method, u.path.removeprefix("/youtube/v3/"), q, form, self.tokens.get(tok))

    @staticmethod
    def _body(headers, body):
        if not body:
            return {}
        ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "")
        raw = body.decode("utf-8") if isinstance(body, bytes) else str(body)
        if ctype.startswith("application/json"):
            return json.loads(raw or "{}")
        return dict(urllib.parse.parse_qsl(raw))

    def _auth(self, path, f):
        if path == "/device/code":
            scopes = (f.get("scope") or "").split()
            if not scopes or any(s not in (SCOPE_RW, SCOPE_RO) for s in scopes):
                return _j(400, {"error": "invalid_scope"})
            dc = self._id("dc-")
            self.device[dc] = {"user_code": f"ABCD-{self._n:04d}", "state": "pending", "scopes": scopes, "polls": 0}
            return _j(200, {"device_code": dc, "user_code": self.device[dc]["user_code"],
                            "verification_url": "https://www.google.com/device", "expires_in": 1800, "interval": 5})
        if path == "/token":
            if f.get("grant_type") == "refresh_token":
                sc = self.refresh.get(f.get("refresh_token"))
                if sc is None:
                    return _j(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
                at = self._id("at-")
                self.tokens[at] = sc
                return _j(200, {"access_token": at, "expires_in": 3599, "token_type": "Bearer", "scope": " ".join(sc)})
            d = self.device.get(f.get("device_code"))
            if d is None or d["state"] == "expired":
                return _j(400, {"error": "expired_token"})
            d["polls"] += 1
            if self.slow_down:
                self.slow_down = False
                return _j(400, {"error": "slow_down"})
            if d["state"] == "pending":
                return _j(428, {"error": "authorization_pending"})
            if d["state"] == "denied":
                return _j(403, {"error": "access_denied"})
            d["state"] = "expired"   # a device code gives tokens once
            at, rt = self._id("at-"), self._id("rt-")
            self.tokens[at] = d["scopes"]
            self.refresh[rt] = d["scopes"]
            return _j(200, {"access_token": at, "refresh_token": rt, "expires_in": 3599,
                            "scope": " ".join(d["scopes"]), "token_type": "Bearer"})
        if path == "/revoke":
            t = f.get("token")
            self.revoked.append(bool(t))
            self.tokens.pop(t, None)
            self.refresh.pop(t, None)
            return _j(200, {})
        return _j(404, {"error": "not_found"})

    def _api(self, method, res, q, body, scopes):
        if scopes is None:
            return _err(401, "authError", "Invalid Credentials")
        if method != "GET" and SCOPE_RW not in scopes:
            return _err(403, "insufficientPermissions")
        cost = COST.get((method, res), 1)
        if self.quota - self.units_used < cost:
            return _err(403, "quotaExceeded", "The request cannot be completed because you have exceeded your "
                        "quota.")
        self.units_used += cost
        self.calls.append((method, res))
        if res == "subscriptions" and method == "GET":
            items = [{"id": sid, "snippet": {"title": self.channels.get(ch, ch), "resourceId": {
                "kind": "youtube#channel", "channelId": ch}}} for sid, ch in self.subs.items()]
            start = int(q.get("pageToken") or 0)
            page = items[start:start + int(q.get("maxResults", 5))]
            out = {"items": page, "pageInfo": {"totalResults": len(items)}}
            if start + len(page) < len(items):
                out["nextPageToken"] = str(start + len(page))
            return _j(200, out)
        if res == "subscriptions" and method == "DELETE":
            if self.subs.pop(q.get("id"), None) is None:
                return _err(404, "subscriptionNotFound")
            return _j(204)
        if res == "subscriptions" and method == "POST":
            ch = body["snippet"]["resourceId"]["channelId"]
            if ch in self.subs.values():
                return _err(400, "subscriptionDuplicate")
            if self.recent_sub_limit is not None and self.inserts >= self.recent_sub_limit:
                return _err(400, "subscriptionForbidden", "Too many recent subscriptions. Please try again in a few "
                            "hours.")
            self.inserts += 1
            sid = self._id("sub")
            self.subs[sid] = ch
            return _j(200, {"id": sid, "snippet": body["snippet"]})
        if res == "playlists" and method == "GET":
            return _j(200, {"items": [{"id": pid, "snippet": {"title": p["title"]}, "status": {
                "privacyStatus": p["privacy"]}} for pid, p in self.playlists.items()]})
        if res == "playlists" and method == "POST":
            pid = self._id("PL")
            self.playlists[pid] = {"title": body["snippet"]["title"], "items": {},
                                   "privacy": (body.get("status") or {}).get("privacyStatus", "public")}
            return _j(200, {"id": pid, "snippet": body["snippet"], "status": body.get("status") or {}})
        if res == "playlistItems" and method == "POST":
            pid = body["snippet"]["playlistId"]
            if pid not in self.playlists:
                return _err(404, "playlistNotFound")
            iid = self._id("PLI")
            self.playlists[pid]["items"][iid] = body["snippet"]["resourceId"]["videoId"]
            return _j(200, {"id": iid, "snippet": body["snippet"]})
        if res == "playlistItems" and method == "DELETE":
            for p in self.playlists.values():
                if p["items"].pop(q.get("id"), None) is not None:
                    return _j(204)
            return _err(404, "playlistItemNotFound")
        if res == "videos" and method == "GET":
            ids = [v for v in (q.get("id") or "").split(",") if v]
            return _j(200, {"items": [{"id": v, "snippet": {"channelId": self.videos[v], "title": f"Video {v[-4:]}",
                                                           "channelTitle": self.channels.get(self.videos[v], "")}}
                                      for v in ids if v in self.videos]})
        if res == "channels" and method == "GET":
            return _j(200, {"items": [{"id": "UCme", "snippet": {"title": "Me"},
                                       "statistics": {"subscriberCount": "0"}}]})
        return _err(404, "notFound")
