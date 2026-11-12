"""PROTOTYPE ONLY - a local chat page for testing without a phone (BRIEF-10 section 9, DESIGN.md section 7).

    python -m mvp.bot --channel web      then open http://127.0.0.1:8765

The page is a message thread with the bot: type as any person in people.json, tap 👍 or 👎 on a reply (a tapback),
and move the bot's clock forward to make a timed or repeating rule fire now instead of waiting for Friday. It runs the
same handler, executor and scheduler as the iMessage channels; only the transport differs. Nothing is sent to a phone.

It keeps its own store (MVP_HOME/webtest.sqlite), so moving the clock never touches rules that real testers have.
Beside the thread: the person's rules, their To-dos (open and done, by list), their Outbox (emails and calendar files
that were written; click one to read it), and an upload box that puts an export file in the person's inbox (refresh.py)
with their last imports. "Start over" clears the rules, thread, to-dos and outbox for that person.
The server listens on this machine only, and every call needs a token that is built into the page when it is served,
so another site open in the browser cannot drive the bot or read the thread.
"""
import hmac
import itertools
import json
import os
import queue
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from .base import Channel, Inbound

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_page.html")
IG_POST = re.compile(r"^https://www\.instagram\.com/(p|reel|tv)/([A-Za-z0-9_-]+)/")


def instagram_permalink(url):
    """The post's plain permalink for Instagram's embed ('https://www.instagram.com/reel/CODE/'), or None."""
    m = IG_POST.match(url or "")
    return f"https://www.instagram.com/{'reel' if m.group(1) == 'reel' else 'p'}/{m.group(2)}/" if m else None
MAX_BODY = 20_000


def _local(dt, tzname, with_day=True):
    t = dt.astimezone(ZoneInfo(tzname))
    clock = t.strftime("%-I:%M %p").lower()
    return f"{t.strftime('%a %-d %b')}, {clock}" if with_day else clock


class WebChannel(Channel):
    name = "web"
    link_previews = True   # a link part is drawn as a card (YouTube thumbnail or a plain Instagram card)
    outbox_place = "in the Outbox panel"   # where an email that was not sent is, in the bot's reply
    poll_seconds = 0.2
    join_seconds = 1.2

    def __init__(self, port=8765, host="127.0.0.1", serve=True):
        self.inbox = queue.Queue()        # ("msg", Inbound) or ("control", dict), handled on the bot's own thread
        self.lock = threading.Lock()
        self.threads = {}                 # handle -> [{"id","ref","dir","text","at","reaction"}]
        self.busy = {}                    # handle -> messages received but not yet handled
        self.offset = timedelta(0)        # how far the test clock is ahead of the real one
        self.ready = False                # set by the bot once the search engines are loaded
        self.problem = None               # a start-up problem to show on the page
        self.bot = None
        self.token = secrets.token_urlsafe(18)
        self._ids = itertools.count(1)
        self._tick = False
        self.server = None
        if serve:
            self.server = ThreadingHTTPServer((host, port), self._handler())
            self.port = self.server.server_address[1]
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

    # ---------- the bot's side ----------
    def attach(self, bot):
        self.bot = bot

    def clock(self):
        return datetime.now(timezone.utc) + self.offset

    def receive(self):
        out = []
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == "msg":
                out.append(payload)
            else:
                self._control(payload)
        return out

    def done(self, msg):
        with self.lock:
            self.busy[msg.handle] = max(0, self.busy.get(msg.handle, 0) - 1)

    def wants_tick(self):
        t, self._tick = self._tick, False
        return t

    def send(self, handle, text, link=None):
        n = next(self._ids)
        ref = f"web-{n}"
        with self.lock:
            self.threads.setdefault(handle, []).append(
                {"id": n, "ref": ref, "dir": "out", "text": text, "at": self.clock().isoformat(), "reaction": None,
                 "link": link})
        return ref

    def send_link(self, handle, part):
        """A link part becomes a card on the page. Only the URL, our own title and a YouTube video ID are kept: the page
        loads YouTube's thumbnail and player, or Instagram's embed, in the viewer's browser. This server never fetches
        Instagram or YouTube media."""
        url = str(part.get("url") or "")
        if not re.match(r"^https?://", url, re.I):   # only web links become cards (never javascript: or data:)
            return self.send(handle, url)
        vid = part.get("video_id") if part.get("platform") == "youtube" else None
        if vid and not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", str(vid)):
            vid = None
        card = {"url": url, "title": str(part.get("title") or "")[:200], "platform": part.get("platform"),
                "video_id": vid, "permalink": instagram_permalink(url) if part.get("platform") == "instagram" else None,
                "outside": bool(part.get("outside"))}   # an outside pick: the card says it is not from their saves
        return self.send(handle, url, link=card)

    def close(self):
        if self.server:
            self.server.shutdown()

    # ---------- the page's side ----------
    def post_message(self, handle, text):
        text = (text or "").strip()[:2000]
        if not text:
            return
        n = next(self._ids)
        with self.lock:
            self.threads.setdefault(handle, []).append(
                {"id": n, "ref": f"web-{n}", "dir": "in", "text": text, "at": self.clock().isoformat(), "reaction": None})
            self.busy[handle] = self.busy.get(handle, 0) + 1
        self.inbox.put(("msg", Inbound(handle=handle, text=text, ref=f"web-{n}")))

    def post_tapback(self, handle, ref, kind):
        if kind not in ("up", "down"):
            return
        with self.lock:
            for m in self.threads.get(handle, []):
                if m["ref"] == ref and m["dir"] == "out":
                    m["reaction"] = kind
                    break
            else:
                return
            self.busy[handle] = self.busy.get(handle, 0) + 1
        self.inbox.put(("msg", Inbound(handle=handle, tapback=kind, tapback_ref=ref)))

    def post_control(self, payload):
        self.inbox.put(("control", payload))

    def _control(self, c):
        """Clock moves and 'start over', run on the bot's thread so they never race a run in progress."""
        bot = self.bot
        op = c.get("op")
        if op == "add_minutes":
            self.offset += timedelta(minutes=max(0, min(int(c.get("minutes") or 0), 60 * 24 * 60)))
        elif op == "to_next" and bot:
            now = self.clock()
            nxt = [datetime.fromisoformat(r["next_run_at"]) for r in bot.store.rules(c.get("handle"), statuses=("active",))
                   if r.get("next_run_at")]
            nxt = [t for t in nxt if t > now]
            if nxt:
                self.offset += (min(nxt) - now) + timedelta(seconds=1)
        elif op == "start_over" and bot:
            handle = c.get("handle")
            with bot.lock_for(handle):  # not in the middle of an answer to this person
                person = bot.store.person(handle)
                agreed = bool(person and person["consent_version"]) and not c.get("with_welcome")
                bot.store.delete_person_data(handle)
                bot.load_people()
                if agreed and bot.store.person(handle):
                    from ..core import CONSENT_VERSION
                    bot.store.set_consent(handle, CONSENT_VERSION)
                with self.lock:
                    self.threads[handle] = []
                    self.busy[handle] = 0
                self.offset = timedelta(0)
        self._tick = True

    def state(self, handle):
        bot = self.bot
        people = bot.store.q("SELECT handle, name, timezone, consent_version FROM people ORDER BY handle") if bot else []
        if not people:
            return {"people": [], "ready": self.ready}
        me = next((p for p in people if p["handle"] == handle), people[0])
        tz = me["timezone"]
        now = self.clock()
        rules = []
        from ..schedule import describe
        from ..schema import RuleSpec
        for i, r in enumerate(bot.store.rules(me["handle"]), 1):
            spec = RuleSpec.model_validate(r["spec"])
            nxt = datetime.fromisoformat(r["next_run_at"]) if r.get("next_run_at") else None
            rules.append({"number": i, "goal": spec.content.goal, "when": describe(spec.when), "status": r["status"],
                          # random moments are never shown in advance (DESIGN.md section 1)
                          "next": _local(nxt, tz) if nxt and r["status"] == "active" and spec.when.type != "random"
                          else None})
        with self.lock:
            msgs = [dict(m, time=_local(datetime.fromisoformat(m["at"]), tz)) for m in self.threads.get(me["handle"], [])]
            busy = self.busy.get(me["handle"], 0) > 0
        todos = self.todos_panel(me["handle"], tz)
        outbox = [{"id": o["id"], "kind": o["kind"], "subject": o["subject"], "via": o["via"],
                   "time": _local(datetime.fromisoformat(o["at"]), tz)} for o in bot.store.outbox(me["handle"])]
        imports = [{"status": r["status"], "time": _local(datetime.fromisoformat(r["at"]), tz),
                    "new": sum(json.loads(r["new_counts"] or "{}").values())}
                   for r in bot.store.q("SELECT status, at, new_counts FROM imports WHERE handle=? ORDER BY id DESC "
                                        "LIMIT 3", (me["handle"],))]
        importing = me["handle"] in getattr(bot.refresher, "busy", ())
        return {"people": [{"handle": p["handle"], "name": p["name"] or p["handle"]} for p in people],
                "me": me["handle"], "agreed": bool(me["consent_version"]), "ready": self.ready, "busy": busy,
                "problem": self.problem,
                "now": _local(now, tz), "timezone": tz, "ahead_minutes": int(self.offset.total_seconds() // 60),
                "messages": msgs, "rules": rules, "todos": todos, "outbox": outbox, "imports": imports,
                "importing": importing}

    def upload(self, handle, filename, stream, length):
        """The upload box: an export file goes to the person's inbox (refresh.py), and the inbox is looked at next."""
        from .. import config
        from ..refresh import inbox_name, save_upload, shared_inboxes
        bot = self.bot
        if not bot or not bot.store.person(handle):
            raise ValueError("unknown person")
        if inbox_name(handle) in shared_inboxes(bot.store):
            raise ValueError("this person's inbox folder has the same name as another person's")
        if length <= 0 or length > config.UPLOAD_MAX_MB * 1024 * 1024:
            raise ValueError("too large")
        path = save_upload(handle, filename, stream, length)
        bot.refresher.nudge(path)
        self._tick = True
        return os.path.basename(path)

    def todos_panel(self, handle, tz):
        """The person's lists: open to-dos numbered as the bot numbers them, then the last few done, by list."""
        bot = self.bot
        now = self.clock()
        lists = {}
        numbers = {t["id"]: i for i, t in enumerate(bot.store.todos(handle), 1)}
        for t in bot.store.all_todos(handle):
            name = t.get("list") or "todo"
            box = lists.setdefault(name, {"list": name, "open": [], "done": []})
            row = {"text": t["text"], "url": t["url"] if re.match(r"^https?://", t["url"] or "", re.I) else None}
            if t["done_at"]:
                box["done"].append(dict(row, at=t["done_at"]))
            else:
                due = datetime.fromisoformat(t["due_at"]) if t.get("due_at") else None
                box["open"].append(dict(row, number=numbers.get(t["id"]), due=_local(due, tz) if due else None,
                                        overdue=bool(due and due < now)))
        for box in lists.values():
            box["done"] = sorted(box["done"], key=lambda r: r["at"], reverse=True)[:5]
            for r in box["done"]:
                r.pop("at", None)
        return sorted(lists.values(), key=lambda b: (b["list"] != "todo", b["list"]))

    def outbox_item(self, handle, item_id):
        """One email or calendar file of this person's outbox, to read on the page: its plain text, its HTML (shown
        in a sandboxed frame), and the names of its attachments. Only files inside MVP_HOME/outbox are read."""
        from email import policy
        from email.parser import BytesParser
        from .. import config
        bot = self.bot
        row = bot.store.one("SELECT * FROM outbox WHERE id=? AND handle=?", (item_id, handle))
        if not row:
            return None
        if not row["path"]:   # a code email that went out by SMTP: listed, not kept
            return {"id": row["id"], "kind": row["kind"], "subject": row["subject"], "via": row["via"],
                    "text": "This email was sent. Its code is not kept here.", "html": None, "attachments": []}
        root = os.path.realpath(config.OUTBOX)
        path = os.path.realpath(row["path"])
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            return None
        out = {"id": row["id"], "kind": row["kind"], "subject": row["subject"], "via": row["via"],
               "text": "", "html": None, "attachments": []}
        with open(path, "rb") as f:
            raw = f.read()
        if row["kind"] == "email":
            m = BytesParser(policy=policy.default).parsebytes(raw)
            out["to"] = str(m["To"] or "")
            plain, html = m.get_body(("plain",)), m.get_body(("html",))
            out["text"] = plain.get_content() if plain else ""
            out["html"] = html.get_content() if html else None
            out["attachments"] = [a.get_filename() or "file" for a in m.iter_attachments()]
        else:
            out["text"] = raw.decode("utf-8", "replace")
        return out

    def _handler(self):
        ch = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # messages hold personal text: nothing is logged
                pass

            def _json(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _ok(self):
                return hmac.compare_digest(self.headers.get("X-Test-Token") or "", ch.token)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                if path in ("/", "/index.html"):
                    with open(PAGE, encoding="utf-8") as f:
                        body = f.read().replace("__TOKEN__", ch.token).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path == "/api/state":
                    if not self._ok():
                        return self._json(403, {"error": "token"})
                    from urllib.parse import parse_qs
                    handle = (parse_qs(query).get("as") or [None])[0]
                    return self._json(200, ch.state(handle))
                if path == "/api/outbox":
                    if not self._ok():
                        return self._json(403, {"error": "token"})
                    from urllib.parse import parse_qs
                    q = parse_qs(query)
                    try:
                        item_id = int((q.get("id") or ["0"])[0])
                    except ValueError:
                        return self._json(400, {"error": "id"})
                    got = ch.outbox_item((q.get("as") or [None])[0], item_id)
                    return self._json(200, got) if got else self._json(404, {"error": "not found"})
                self._json(404, {"error": "not found"})

            def do_POST(self):
                if not self._ok():
                    return self._json(403, {"error": "token"})
                if self.path.startswith("/api/upload"):   # a raw file body, streamed to the inbox
                    from urllib.parse import parse_qs
                    q = parse_qs(self.path.partition("?")[2])
                    try:
                        name = ch.upload((q.get("as") or [None])[0], (q.get("name") or ["export.zip"])[0], self.rfile,
                                         int(self.headers.get("Content-Length") or 0))
                    except ValueError as e:
                        return self._json(400, {"error": str(e)})
                    return self._json(200, {"ok": True, "name": name})
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._json(413, {"error": "too long"})
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json(400, {"error": "json"})
                if self.path == "/api/send":
                    ch.post_message(body.get("handle"), body.get("text"))
                elif self.path == "/api/tapback":
                    ch.post_tapback(body.get("handle"), body.get("ref"), body.get("kind"))
                elif self.path == "/api/control":
                    ch.post_control(body)
                else:
                    return self._json(404, {"error": "not found"})
                self._json(200, {"ok": True})

        return Handler
