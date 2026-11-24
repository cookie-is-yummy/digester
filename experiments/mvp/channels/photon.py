"""PROTOTYPE ONLY - iMessage through Photon's hosted API (BRIEF-10 section 6, the first outside testers).

This is Photon's Beta API ("Photon 2.0", api.photon.codes/v1), which Photon calls a preview. Shapes below were read
from api.photon.codes/openapi.json on 21 Nov 2026. One real text has come in and one reply has been accepted by Photon
(21 Nov, a founder's own phone, through a test listener, not the bot); tests/photon_message_received.json is that
delivery with everything personal replaced.

Receiving: a small web server behind a tunnel takes Photon's webhook. Each delivery is signed the Standard Webhooks
way: HMAC-SHA256 over "<webhook-id>.<webhook-timestamp>.<raw body>" with the Base64-decoded part of the destination's
"whsec_..." secret, sent as "v1,<base64>" in `webhook-signature`. A delivery more than five minutes off the clock, or
with no matching signature, gets 401. Only a `message.received` event that is a text, from a human, in a direct
conversation of this project is read; everything else is answered 204 and dropped, because any other answer makes
Photon retry or stop the destination.

Sending: Photon has no "to" number. A reply names the conversation (`spaceId`) and the bot's own user in it
(`senderId`), both taken from the person's last message and kept in the store under `photonroute:<handle>`. So nobody
can be sent anything before they text, which is also Photon's rule for a shared line. POST /v1/projects/{id}/messages
answers 202 with the message's `id`: accepted, not delivered.

Not here: tapbacks (the Beta API has none; the person types "yes"), the contact card (an attachment upload nobody has
tried), group chats (not allowed on a shared line), and anything that is not text.

Settings come from the environment only and are never printed or logged: PHOTON_API_KEY (a project key, `pho_sk_...`,
with project:read and project:write; platforms:write too for photon_assign.py), PHOTON_PROJECT_ID (`pho_prj_...`),
PHOTON_WEBHOOK_SECRET (the destination's `whsec_...`). Optional: PHOTON_API_URL, and PHOTON_PLATFORMS (default
"imessage"; add "sms" only knowing that Photon charges per SMS part).
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .base import Channel, Inbound, SendUncertain

WEBHOOK_PATH = "/photon/webhook"
ROUTE = "photonroute:{h}"      # state key; ends with ":<handle>", so Store.delete_person_data removes it
TOLERANCE = 300                # seconds either side of now (Photon's own rule)
MAX_BODY = 1_000_000
MAX_TEXT = 18_000              # the Sendblue channel's cut; Photon publishes no limit for iMessage text
TIMEOUT = 30
USER_AGENT = "digest-bot-mvp/1"


class PhotonError(RuntimeError):
    """Photon answered with an HTTP error. The message holds the status and Photon's short title, never the body's
    detail (it can carry a number)."""

    def __init__(self, status, title="", retry_after=None):
        self.status, self.title, self.retry_after = status, title, retry_after
        super().__init__(f"Photon answered {status}" + (f": {title}" if title else "")
                         + (f" (retry after {retry_after} s)" if retry_after else ""))


class PhotonNoRoute(RuntimeError):
    """This person has not texted the bot through Photon, so there is no conversation to send into."""


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"{name} is not set")
    return v


def api_url():
    return os.environ.get("PHOTON_API_URL", "https://api.photon.codes").rstrip("/")


def _key(secret):
    """The signing key inside a 'whsec_<base64>' secret."""
    try:
        return base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except (binascii.Error, ValueError) as e:
        raise RuntimeError("PHOTON_WEBHOOK_SECRET is not a webhook signing secret (whsec_...)") from e


def verify(secret, headers, raw, now=None):
    """True when one of the delivery's signatures is ours and its timestamp is within five minutes of now."""
    wid, ts, sigs = headers.get("webhook-id"), headers.get("webhook-timestamp"), headers.get("webhook-signature")
    if not wid or not ts or not sigs:
        return False
    try:
        stamp = int(ts)
    except ValueError:
        return False
    if abs((time.time() if now is None else now) - stamp) > TOLERANCE:
        return False
    want = hmac.new(_key(secret), f"{wid}.{ts}.".encode() + raw, hashlib.sha256).digest()
    for part in sigs.split():
        version, _, value = part.partition(",")
        if version != "v1":
            continue
        try:
            got = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            continue
        if hmac.compare_digest(got, want):
            return True
    return False


def _bot_id(obj, sender_id):
    """The bot's user in this conversation: who received the message, or the one other participant."""
    for field in ("receivedBy", "addressedTo"):
        who = obj.get(field)
        if isinstance(who, dict) and who.get("id"):
            return who["id"]
    others = [p for p in (obj.get("space") or {}).get("participantIds") or [] if p != sender_id]
    return others[0] if len(others) == 1 else None


def parse_event(event, project_id, platforms=("imessage",)):
    """A Photon webhook event -> (Inbound, route) or None. route is {"spaceId", "senderId"} for the reply, or None
    when the event does not say who the bot is in that conversation."""
    if not isinstance(event, dict) or event.get("type") != "message.received":
        return None
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return None
    if (data.get("projectId") or obj.get("projectId")) != project_id:
        return None
    if obj.get("platform") not in platforms or obj.get("status") != "received":
        return None
    space, sender, content = obj.get("space"), obj.get("sentBy"), obj.get("content")
    if not (isinstance(space, dict) and isinstance(sender, dict) and isinstance(content, dict)):
        return None
    if space.get("kind") != "direct" or sender.get("kind") != "human" or content.get("type") != "text":
        return None
    handle, text = sender.get("handle"), (content.get("text") or "").strip()
    if not handle or not text or not space.get("id"):
        return None
    bot = _bot_id(obj, sender.get("id"))
    route = {"spaceId": space["id"], "senderId": bot} if bot else None
    return Inbound(handle=handle, text=text, ref=obj.get("id")), route


def call(method, path, body=None, idem=None):
    """One call to Photon's API with the project key. A timeout on the way is SendUncertain (the call may have
    arrived); an HTTP error is PhotonError."""
    # Photon's edge answers 403 "Error 1010" to urllib's default User-Agent (found on the first live call, 21 Nov)
    headers = {"Authorization": f"Bearer {_env('PHOTON_API_KEY')}", "Accept": "application/json",
               "User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idem:
        headers["Idempotency-Key"] = idem
    req = urllib.request.Request(api_url() + path, data=None if body is None else json.dumps(body).encode(),
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        title = ""
        try:
            problem = json.loads(e.read() or b"{}")
            title = str(problem.get("title") or "")[:120] if isinstance(problem, dict) else ""
        except (ValueError, OSError):
            pass
        raise PhotonError(e.code, title, e.headers.get("Retry-After") if e.headers else None) from None
    except TimeoutError as e:
        raise SendUncertain("timeout") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise SendUncertain("timeout") from e
        raise


class PhotonChannel(Channel):
    name = "photon"
    link_previews = True   # one link per message, nothing else in it (iMessage shows it as a card)

    def __init__(self, store, port=8788, caller=None):
        self.store = store
        self.inbox = queue.Queue()
        self.deliveries = OrderedDict()   # webhook-id of each delivery taken (Photon may send one twice)
        self.messages = OrderedDict()     # message ids taken; the store's inbound table dedupes across restarts
        self.lock = threading.Lock()
        self.secret = _env("PHOTON_WEBHOOK_SECRET")
        _key(self.secret)                 # stop at start, not at the first delivery, when it is not a secret
        self.project = _env("PHOTON_PROJECT_ID")
        if caller is None:
            _env("PHOTON_API_KEY")
        self.caller = caller or call
        self.platforms = tuple(p.strip() for p in os.environ.get("PHOTON_PLATFORMS", "imessage").split(",") if p.strip())
        channel = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # no request lines in logs
                pass

            def _answer(self, status):
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                if self.path != WEBHOOK_PATH:
                    return self._answer(404)
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._answer(413)
                raw = self.rfile.read(n)
                if not verify(channel.secret, self.headers, raw):
                    return self._answer(401)
                wid = self.headers.get("webhook-id")
                if channel._seen(channel.deliveries, wid, mark=False):
                    return self._answer(204)
                try:
                    event = json.loads(raw or b"{}")
                except ValueError:
                    return self._answer(400)
                try:
                    channel.accept(event)
                except Exception:  # noqa: BLE001 - it could not be kept: 503 makes Photon send it again
                    return self._answer(503)
                channel._seen(channel.deliveries, wid)
                self._answer(204)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _seen(self, table, key, mark=True):
        """Whether this id was taken before; with mark, it is taken now."""
        if not key:
            return False
        with self.lock:
            if key in table:
                return True
            if mark:
                table[key] = True
                while len(table) > 5000:
                    table.popitem(last=False)
            return False

    def accept(self, event):
        parsed = parse_event(event, self.project, self.platforms)
        if parsed is None:
            return
        msg, route = parsed
        if route and self.store.get_state(ROUTE.format(h=msg.handle)) != route:
            self.store.set_state(ROUTE.format(h=msg.handle), route)   # before the message is queued: a reply needs it
        if self._seen(self.messages, msg.ref):
            return
        self.inbox.put(msg)

    def receive(self):
        out = []
        while not self.inbox.empty():
            out.append(self.inbox.get())
        return out

    def send(self, handle, text):
        text = (text or "").strip()
        if not text:
            return None
        route = self.store.get_state(ROUTE.format(h=handle))
        if not route:
            raise PhotonNoRoute("this person has not texted the bot through Photon yet, so there is no conversation "
                                "to send into (they text their assigned number first)")
        body = {"spaceId": route["spaceId"], "senderId": route["senderId"],
                "content": {"type": "text", "format": "plain", "text": text[:MAX_TEXT]}}
        r = self.caller("POST", f"/v1/projects/{self.project}/messages", body, idem=uuid.uuid4().hex)
        return (r or {}).get("id")

    def close(self):
        self.server.shutdown()
        self.server.server_close()
