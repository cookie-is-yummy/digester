"""PROTOTYPE ONLY - iMessage (and SMS for Android) through Sendblue (BRIEF-10 section 6, testers).

Receiving: a small HTTPS-behind-a-tunnel web server takes Sendblue's 'receive' webhook. Sendblue sends the configured
secret in the `sb-signing-secret` header (docs.sendblue.com/security); it is compared in constant time, and anything
without it gets 401. Outbound echoes are ignored; message_handle dedupes retries. Sending: POST /api/send-message with
`sb-api-key-id` / `sb-api-secret-key` headers; the response's message_handle is the channel reference.
Keys come from the environment only: SENDBLUE_API_KEY_ID, SENDBLUE_API_SECRET_KEY, SENDBLUE_FROM_NUMBER,
SENDBLUE_WEBHOOK_SECRET. They are never printed or logged.
Reactions: Sendblue does not document how an inbound reaction arrives. Texts like 'Liked "…"' (how reactions reach
SMS phones) are handled as feedback by the bot core; a payload with is_reaction true is ignored here until a real one
is recorded.
"""
import hmac
import json
import os
import queue
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .base import Channel, Inbound, SendUncertain

API = "https://api.sendblue.com/api/send-message"
WEBHOOK_PATH = "/sendblue/receive"


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"{name} is not set")
    return v


def parse_receive(payload):
    """A Sendblue receive payload -> Inbound, or None for outbound echoes, groups and empty messages."""
    if payload.get("is_outbound") or payload.get("group_id") or payload.get("is_reaction"):
        return None
    handle = payload.get("number") or payload.get("from_number")
    text = (payload.get("content") or "").strip()
    if not handle or not text:
        return None
    return Inbound(handle=handle, text=text, ref=payload.get("message_handle"))


class SendblueChannel(Channel):
    name = "sendblue"

    def __init__(self, port=8787, poster=None):
        self.inbox = queue.Queue()
        self.seen = OrderedDict()
        self.secret = _env("SENDBLUE_WEBHOOK_SECRET")
        self.poster = poster or self._post
        channel = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # no request lines in logs (they can carry numbers)
                pass

            def do_POST(self):
                if self.path != WEBHOOK_PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                got = self.headers.get("sb-signing-secret", "")
                if not hmac.compare_digest(got.encode(), channel.secret.encode()):
                    self.send_response(401)
                    self.end_headers()
                    return
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    payload = json.loads(self.rfile.read(min(n, 1_000_000)) or b"{}")
                except ValueError:
                    self.send_response(400)
                    self.end_headers()
                    return
                channel.accept(payload)
                self.send_response(200)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def accept(self, payload):
        msg = parse_receive(payload)
        if msg is None:
            return
        if msg.ref:  # a quick in-memory check; the store's inbound table is what dedupes across restarts
            if msg.ref in self.seen:
                return
            self.seen[msg.ref] = True
            while len(self.seen) > 5000:
                self.seen.popitem(last=False)
        self.inbox.put(msg)

    def receive(self):
        out = []
        while not self.inbox.empty():
            out.append(self.inbox.get())
        return out

    def _post(self, body):
        req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
            "sb-api-key-id": _env("SENDBLUE_API_KEY_ID"), "sb-api-secret-key": _env("SENDBLUE_API_SECRET_KEY"),
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or b"{}")
        except TimeoutError as e:  # the request may have reached Sendblue
            raise SendUncertain("timeout") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise SendUncertain("timeout") from e
            raise

    def send(self, handle, text):
        r = self.poster({"number": handle, "content": text[:18000], "from_number": _env("SENDBLUE_FROM_NUMBER")})
        return r.get("message_handle")

    def close(self):
        self.server.shutdown()
