"""PROTOTYPE ONLY - the sign-up page for a small invited test on the Photon channel (channels/photon.py).

    python -m mvp.signup_web            # 127.0.0.1:8790, behind a tunnel of its own; the bot runs beside it

What a tester does: opens the invite link, gives a phone number, taps one button that opens Messages
with a short code already typed, sends it, and (now or later) drops an Instagram export on the page. The bot's own
consent and setup then run in the thread, unchanged.

How it is kept safe (each line has a test in tests/test_signup_web.py):
- Invite only. Every call carries the invite code (MVP_SIGNUP_INVITE, 16 characters or more), compared in constant
  time. The code rides in the link's fragment (#...), which browsers never send to a server or in a Referer.
- A small, fixed number of people (MVP_SIGNUP_MAX_PEOPLE, default 3). A full test says so and assigns nobody.
- The number must prove itself. Signing up shows a 6-digit code; the upload ticket is given only after the bot's own
  store holds a text with that code from that number, received after the sign-up. So a stranger who types someone
  else's number gets nothing of theirs, and cannot put a file into their library.
- A claim lives 30 minutes, in memory only. Its secret never leaves the browser that made it.
- Uploads: a ticket for one person, signed with a key of this computer (HMAC-SHA256, 24 hours); a size limit; a zip
  only; only an Instagram export (JSON) or a Google Takeout with YouTube is kept, anything else is deleted at once.
- Limits per address and for everyone, on sign-ups, checks and uploads.
- Nothing personal is logged. A sign-up answers the same for a new and a known number (only a full test differs).
- The page is one file with no outside requests; every answer carries a strict Content-Security-Policy and no-store.
- The server listens on 127.0.0.1 only: the tunnel is the one way in.

Settings (environment only): MVP_SIGNUP_INVITE, PHOTON_API_KEY and PHOTON_PROJECT_ID (photon_assign.py). Optional:
MVP_SIGNUP_MAX_PEOPLE, MVP_SIGNUP_UPLOAD_MB (default 99; a quick Cloudflare tunnel refuses bodies over 100 MB, so a real host is needed to go higher),
MVP_SIGNUP_LIBRARY (the empty library a new person starts on; default data/libraries/empty).
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from . import config
from .handler import norm_handle

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "signup_page.html")
CLAIM_SECONDS = 30 * 60
TICKET_SECONDS = 24 * 3600
MAX_JSON = 4096
NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '\-]){0,39}$")   # letters, spaces, ' and -, 40 at most
PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                               "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; "
                               "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class Refused(Exception):
    """An answer for the page: an HTTP status, a short code the page turns into words, nothing personal."""

    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def normalize_phone(raw, default_country="1"):
    """What a person types -> E.164, or None. Ten digits are read as a US or Canadian number."""
    s = re.sub(r"[\s().\-]", "", raw or "")
    if not re.fullmatch(r"\+?\d{7,15}", s):
        return None
    if s.startswith("+"):
        out = s
    elif len(s) == 10:
        out = f"+{default_country}{s}"
    elif len(s) == 11 and s.startswith(default_country):
        out = "+" + s
    else:
        return None
    return out if PHONE.match(out) else None


class Limiter:
    """At most `n` events per `seconds` for one key (real time)."""

    def __init__(self, n, seconds):
        self.n, self.seconds, self.hits, self.lock = n, seconds, {}, threading.Lock()

    def allow(self, key, now=None):
        now = time.time() if now is None else now
        with self.lock:
            hits = [t for t in self.hits.get(key, []) if now - t < self.seconds]
            if len(hits) >= self.n:
                self.hits[key] = hits
                return False
            self.hits[key] = hits + [now]
            if len(self.hits) > 5000:
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.seconds}
            return True


def load_key(home=None):
    """This computer's signing key for upload tickets: made once, kept beside the store, readable by the owner only."""
    path = os.path.join(home or config.HOME, "signup_key.txt")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as f:
        return bytes.fromhex(f.read().strip())


def make_ticket(key, handle, now=None):
    body = base64.urlsafe_b64encode(json.dumps({"h": handle, "t": int(time.time() if now is None else now)}).encode())
    return body.decode() + "." + hmac.new(key, body, hashlib.sha256).hexdigest()


def read_ticket(key, ticket, now=None):
    """The handle a ticket was made for, or None (not ours, changed, or older than a day)."""
    body, _, mac = (ticket or "").partition(".")
    if not body or not mac or not hmac.compare_digest(hmac.new(key, body.encode(), hashlib.sha256).hexdigest(), mac):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
        handle, made = data["h"], int(data["t"])
    except (ValueError, KeyError, TypeError):
        return None
    if not 0 <= (time.time() if now is None else now) - made <= TICKET_SECONDS:
        return None
    return handle if isinstance(handle, str) else None


class Signup:
    """The sign-up's own logic, apart from HTTP, so tests call it directly."""

    def __init__(self, store, invite, assign, key, people_path=None, library=None, max_people=3, classify=None,
                 save_upload=None, nudge=None, yt=None):
        if not invite or len(invite) < 16:
            raise RuntimeError("MVP_SIGNUP_INVITE is not set, or shorter than 16 characters")
        self.store, self.invite, self.assign, self.key = store, invite, assign, key
        self.people_path = people_path or config.PEOPLE
        self.library = os.path.abspath(library or os.path.join(config.REPO, "data", "libraries", "empty"))
        self.max_people = max_people
        self.classify, self.save_upload, self.nudge = classify, save_upload, nudge
        self.yt = yt   # yt_auth; None when YouTube is off on this bot
        self.claims = {}                 # claim id -> {secret, handle, code, at, since, bot}
        self.lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.per_ip = Limiter(10, 3600)
        self.everyone = Limiter(40, 3600)
        self.checks = Limiter(1200, 3600)     # one page asks every 2 seconds for up to 30 minutes
        self.uploads = Limiter(8, 3600)      # a few wrong files (HTML, the wrong zip) must not lock a person out
        self.chunks = Limiter(6000, 3600)    # pieces of a big file: many requests for one upload, so counted apart
        self.total_cap = int(os.environ.get("MVP_SIGNUP_UPLOAD_MAX_MB", "2048")) * 2 ** 20   # whole-file cap when chunked
        self.parts_dir = os.path.join(config.INBOX, ".uploads")
        ensure_empty_library(self.library)

    # ---------- the invite ----------
    def check_invite(self, got):
        if not isinstance(got, str) or not hmac.compare_digest(got.encode(), self.invite.encode()):
            raise Refused(403, "invite")

    # ---------- step 1: a name and a number ----------
    def start(self, invite, name, phone, timezone, ip="?", now=None):
        self.check_invite(invite)
        if not self.per_ip.allow(ip, now) or not self.everyone.allow("all", now):
            raise Refused(429, "slow_down")
        if name is None or name == "":                # the page asks only for a number; the bot never uses a name
            name = None
        else:
            if not isinstance(name, str) or re.search(r"[\x00-\x1f\x7f]", name):   # a control character is never tidied away
                raise Refused(400, "name")
            name = re.sub(r" +", " ", name.strip())
            if not NAME.match(name):
                raise Refused(400, "name")
        handle = normalize_phone(phone)
        if not handle:
            raise Refused(400, "phone")
        handle = norm_handle(handle)
        try:
            ZoneInfo(timezone)
        except Exception:  # noqa: BLE001 - an unknown or malformed zone: the bot's default, changed later by text
            timezone = "America/New_York"
        if handle in self.store.deleted_handles():
            raise Refused(409, "ask_founder")       # they asked for deletion: only a founder adds them back
        with self.file_lock:
            known = self.store.person(handle) is not None
            if not known and self._count_people() >= self.max_people:
                raise Refused(409, "full")
            try:
                got = self.assign(handle)
            except Exception as e:  # noqa: BLE001 - Photon said no, or could not be reached: the type only
                print(f"signup: no number assigned ({type(e).__name__})", file=sys.stderr)
                raise Refused(502, "try_later") from None
            bot = (got or {}).get("assignedPhoneNumber")
            if not bot:
                raise Refused(502, "try_later")
            if not known:
                self._add_person(handle, name, timezone)
        claim, secret = secrets.token_urlsafe(12), secrets.token_urlsafe(24)
        code = f"{secrets.randbelow(900000) + 100000}"
        with self.lock:
            self._drop_old(now)
            self.claims[claim] = {"secret": secret, "handle": handle, "code": code, "bot": bot,
                                  "at": time.time() if now is None else now, "since": self._last_inbound_id()}
        return {"claim": claim, "secret": secret, "code": code, "botNumber": bot}

    def _count_people(self):
        return len(self.store.q("SELECT handle FROM people"))

    def _last_inbound_id(self):
        r = self.store.one("SELECT MAX(id) AS m FROM inbound")
        return (r or {}).get("m") or 0

    def _add_person(self, handle, name, timezone):
        """Into people.json (so a restart of the bot keeps them) and into the store (so the running bot knows them at
        their first text, with no restart)."""
        people = {}
        if os.path.exists(self.people_path):
            with open(self.people_path, encoding="utf-8") as f:
                people = json.load(f)
        if handle not in people:
            people[handle] = {"name": name, "library": self.library, "timezone": timezone}
            tmp = self.people_path + ".tmp"
            os.makedirs(os.path.dirname(self.people_path), exist_ok=True)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(people, f, indent=1)
            os.replace(tmp, self.people_path)
        self.store.upsert_person(handle, name, self.library, timezone)

    def _drop_old(self, now=None):
        now = time.time() if now is None else now
        for k in [k for k, c in self.claims.items() if now - c["at"] > CLAIM_SECONDS]:
            del self.claims[k]

    # ---------- step 2: the number proves itself ----------
    def _claim(self, invite, claim, secret, now=None):
        self.check_invite(invite)
        with self.lock:
            self._drop_old(now)
            c = self.claims.get(claim if isinstance(claim, str) else "")
        if c is None or not isinstance(secret, str) or not hmac.compare_digest(secret.encode(), c["secret"].encode()):
            raise Refused(404, "claim")
        return c

    def status(self, invite, claim, secret, ip="?", now=None):
        if not self.checks.allow(ip, now):
            raise Refused(429, "slow_down")
        c = self._claim(invite, claim, secret, now)
        if not c.get("verified"):
            rows = self.store.q("SELECT text FROM inbound WHERE handle=? AND id>? ORDER BY id", (c["handle"], c["since"]))
            if any(re.search(rf"(?<!\d){c['code']}(?!\d)", r.get("text") or "") for r in rows):
                c["verified"] = True
        if not c.get("verified"):
            return {"verified": False}
        return {"verified": True, "ticket": make_ticket(self.key, c["handle"], now)}

    # ---------- step 3: an export ----------
    def _finish_saved(self, path):
        """A file is in the inbox: keep it if it is an export, delete it otherwise. Shared by both upload paths."""
        kind = None
        try:
            if zipfile.is_zipfile(path):
                kind, why = self.classify(path)
            else:
                why = "not_zip"
        except Exception:  # noqa: BLE001 - a broken archive is not an export
            why = "not_zip"
        if kind is None:
            try:
                os.remove(path)          # never kept: not in the inbox, not in .failed
            except OSError:
                pass
            raise Refused(415, "html" if why == "html" else "not_export")
        if self.nudge:
            self.nudge(path)
        return {"ok": True, "kind": kind}

    def _sweep_parts(self):
        """Drop half-finished uploads nobody came back to finish (older than 2 hours)."""
        cutoff = time.time() - 2 * 3600
        try:
            for n in os.listdir(self.parts_dir):
                f = os.path.join(self.parts_dir, n)
                try:
                    if os.path.getmtime(f) < cutoff:
                        os.remove(f)
                except OSError:
                    pass
        except OSError:
            pass

    def upload(self, invite, ticket, filename, stream, length, max_bytes, ip="?", now=None,
               upload_id=None, total=None, final=True):
        """One request is at most `max_bytes` (the tunnel's limit). A file larger than that arrives as many requests
        sharing one `upload_id`, appended into one file (bounded only by self.total_cap), then imported on the last."""
        self.check_invite(invite)
        handle = read_ticket(self.key, ticket, now)
        if handle is None or self.store.person(handle) is None:
            raise Refused(403, "ticket")
        if not isinstance(length, int) or length <= 0:
            raise Refused(411, "length")
        if length > max_bytes:
            raise Refused(413, "too_big")
        if upload_id is None:                                        # a small file: one request, as before
            if not self.uploads.allow(handle, now) or not self.per_ip.allow("up:" + ip, now):
                raise Refused(429, "slow_down")
            try:
                path = self.save_upload(handle, filename, stream, length)
            except ValueError:
                raise Refused(400, "cut_off") from None
            return self._finish_saved(path)
        # a big file, in pieces
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", upload_id or ""):
            raise Refused(400, "body")
        if not isinstance(total, int) or total <= 0 or total > self.total_cap:
            raise Refused(413, "too_big")
        os.makedirs(self.parts_dir, exist_ok=True)
        part = os.path.join(self.parts_dir, hashlib.sha256(f"{handle}|{upload_id}".encode()).hexdigest()[:24] + ".part")
        with self.file_lock:
            first = not os.path.exists(part)
            if first:
                self._sweep_parts()
                if not self.uploads.allow(handle, now) or not self.per_ip.allow("up:" + ip, now):
                    raise Refused(429, "slow_down")
            elif not self.chunks.allow("ch:" + ip, now):
                raise Refused(429, "slow_down")
            have = 0 if first else os.path.getsize(part)
            if have + length > total or have + length > self.total_cap:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise Refused(413, "too_big")
            left = length
            with open(part, "ab") as f:
                while left > 0:
                    buf = stream.read(min(1 << 20, left))
                    if not buf:
                        break
                    f.write(buf)
                    left -= len(buf)
            if left:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise Refused(400, "cut_off")
            if not final:
                return {"ok": True, "received": os.path.getsize(part)}
            size = os.path.getsize(part)
        if size != total:
            try:
                os.remove(part)
            except OSError:
                pass
            raise Refused(400, "cut_off")
        try:
            with open(part, "rb") as f:
                path = self.save_upload(handle, filename, f, size)
        finally:
            try:
                os.remove(part)
            except OSError:
                pass
        return self._finish_saved(path)


    # ---------- step 3 (optional): connect YouTube by Google's device code, confirmed on this page ----------
    def _ticket_handle(self, ticket, now):
        handle = read_ticket(self.key, ticket, now)
        if handle is None or self.store.person(handle) is None:
            raise Refused(403, "ticket")
        return handle

    def youtube_start(self, invite, ticket, ip="?", now=None):
        """Ask Google for a sign-in code for this (already phone-verified) person. {"code","url","minutes"} or
        {"connected": True}. yt_off when this bot has no Google client."""
        self.check_invite(invite)
        handle = self._ticket_handle(ticket, now)
        if not self.per_ip.allow("yts:" + ip, now):
            raise Refused(429, "slow_down")
        if self.yt is None or self.yt.client() is None:
            raise Refused(503, "yt_off")
        if self.yt.connected(self.store, handle):
            return {"connected": True}
        st = self.yt.waiting(self.store, handle, now)
        if st:
            return {"code": st["user_code"], "url": "https://www.google.com/device"}
        from .actions.youtube import YtError
        try:
            got = self.yt.start(self.store, handle, now)
        except YtError as e:
            raise Refused(503, "yt_off" if e.code in ("not_set_up", "no_key") else "yt_failed") from None
        return {"code": got["user_code"], "url": "https://www.google.com/device", "minutes": got["minutes"]}

    def youtube_status(self, invite, ticket, ip="?", now=None):
        """Has the person approved the code yet? Polls Google no faster than its interval. {"connected": bool,
        "waiting": bool, "error"?}."""
        self.check_invite(invite)
        handle = self._ticket_handle(ticket, now)
        if not self.checks.allow("ytp:" + ip, now):
            raise Refused(429, "slow_down")
        if self.yt is None:
            raise Refused(503, "yt_off")
        if self.yt.connected(self.store, handle):
            return {"connected": True}
        got = self.yt.poll(self.store, handle, now)   # force=False: at most one Google call per device interval
        if got == "connected" or self.yt.connected(self.store, handle):
            return {"connected": True}
        if got == "pending" or (got is None and self.yt.waiting(self.store, handle, now)):
            return {"connected": False, "waiting": True}
        if got in ("denied", "expired", "scope", "failed"):
            return {"connected": False, "waiting": False, "error": got}
        return {"connected": False, "waiting": False}   # no code open: the page offers to start again



def ensure_empty_library(lib):
    """The library a new person starts on: nothing in it, so every answer says so until their export is added."""
    corpus = os.path.join(lib, "corpus")
    if os.path.isfile(os.path.join(corpus, "items.jsonl")):
        return
    os.makedirs(corpus, exist_ok=True)
    for name in ("items.jsonl", "interactions.jsonl"):
        open(os.path.join(corpus, name), "a", encoding="utf-8").close()
    with open(os.path.join(lib, "library.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "Empty library (nothing imported yet)", "source": "none",
                   "counts": {"items": 0, "instagram": 0, "youtube": 0, "interactions": 0}, "warnings": []}, f)


def make_server(app, port=8790, max_upload=99 * 2 ** 20, page_path=PAGE):
    with open(page_path, encoding="utf-8") as f:
        page = f.read()

    class Handler(BaseHTTPRequestHandler):
        server_version, sys_version = "signup", ""

        def log_message(self, *a):  # no request lines: they would hold addresses
            pass

        def _ip(self):
            # the tunnel is the only caller (we listen on 127.0.0.1); it names the visitor's address in this header
            return (self.headers.get("CF-Connecting-IP") or self.client_address[0] or "?")[:64]

        def _send(self, status, body=b"", ctype="application/json", nonce=""):
            self.send_response(status)
            for k, v in HEADERS.items():
                self.send_header(k, v.replace("{nonce}", nonce))
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode())

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_JSON:
                raise Refused(400, "body")
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                raise Refused(400, "body") from None
            if not isinstance(data, dict):
                raise Refused(400, "body")
            return data

        def do_GET(self):
            if self.path.split("?", 1)[0] != "/":
                return self._send(404)
            nonce = secrets.token_urlsafe(16)
            self._send(200, page.replace("__NONCE__", nonce).replace("__MAX_MB__", str(max_upload // 2 ** 20)).encode(),
                       "text/html; charset=utf-8", nonce)

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            try:
                if path == "/api/start":
                    d = self._body()
                    out = app.start(d.get("invite"), d.get("name"), d.get("phone"), d.get("timezone") or "", self._ip())
                elif path == "/api/status":
                    d = self._body()
                    out = app.status(d.get("invite"), d.get("claim"), d.get("secret"), self._ip())
                elif path == "/api/youtube/start":
                    d = self._body()
                    out = app.youtube_start(d.get("invite"), d.get("ticket"), self._ip())
                elif path == "/api/youtube/status":
                    d = self._body()
                    out = app.youtube_status(d.get("invite"), d.get("ticket"), self._ip())
                elif path == "/api/upload":
                    try:
                        length = int(self.headers.get("Content-Length") or 0)
                    except ValueError:
                        length = 0
                    tot = self.headers.get("X-Total-Size")
                    out = app.upload(self.headers.get("X-Invite"), self.headers.get("X-Ticket"),
                                     self.headers.get("X-Filename") or "export.zip", self.rfile, length, max_upload,
                                     self._ip(), upload_id=self.headers.get("X-Upload-Id"),
                                     total=int(tot) if tot and tot.isdigit() else None,
                                     final=(self.headers.get("X-Chunk-Final") != "0"))
                else:
                    return self._send(404)
            except Refused as e:
                self.close_connection = True      # an upload we did not read must not be taken as the next request
                return self._json(e.status, {"error": e.code})
            except Exception as e:  # noqa: BLE001 - never a stack or a value on the wire
                print(f"signup: {type(e).__name__}", file=sys.stderr)
                self.close_connection = True
                return self._json(500, {"error": "try_later"})
            self._json(200, out)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The invited testers' sign-up page (Photon channel).")
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args(argv)
    from . import photon_assign, refresh, yt_auth
    from .store import Store
    store = Store(config.DB)
    app = Signup(store, os.environ.get("MVP_SIGNUP_INVITE", ""), photon_assign.assign, load_key(),
                 library=os.environ.get("MVP_SIGNUP_LIBRARY"),
                 max_people=int(os.environ.get("MVP_SIGNUP_MAX_PEOPLE", "3")),
                 classify=refresh.classify, save_upload=refresh.save_upload, yt=yt_auth)
    server = make_server(app, a.port, int(os.environ.get("MVP_SIGNUP_UPLOAD_MB", "99")) * 2 ** 20)
    print(f"Sign-up page on 127.0.0.1:{a.port}, at most {app.max_people} people, store {store.path}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
