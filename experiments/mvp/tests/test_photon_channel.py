"""Offline tests for the Photon channel (channels/photon.py) and the tester sign-up command (photon_assign.py).

Every payload here is made up from Photon's published API description (api.photon.codes/openapi.json, read 21 Nov
2026): no real number, no real message, no network. The first real webhook body must replace the made-up event below
as a sanitised fixture before the channel is trusted (README, "Photon").
"""
import base64
import hashlib
import hmac
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

KEY = b"made-up-signing-key-0123456789ab"
SECRET = "whsec_" + base64.b64encode(KEY).decode()
PROJECT = "pho_prj_madeup"
PERSON = "+15550001"
BOT = "+15559999"


def sign(wid, ts, raw, key=KEY):
    """Standard Webhooks, written here independently of the code under test."""
    mac = hmac.new(key, f"{wid}.{ts}.".encode() + raw, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def event(text="hi", mid="msg_1", kind="direct", sender_kind="human", platform="imessage", etype="message.received",
          content=None, project=PROJECT, received_by=True, handle=PERSON):
    obj = {
        "id": mid, "projectId": project, "platform": platform, "status": "received",
        "space": {"id": "spc_1", "projectId": project, "platform": platform, "kind": kind,
                  "participantIds": ["usr_person", "usr_bot"], "details": {}, "metadata": {}},
        "sentBy": {"id": "usr_person", "projectId": project, "platform": platform, "handle": handle,
                   "kind": sender_kind, "details": {}, "metadata": {}},
        "content": content if content is not None else {"type": "text", "format": "plain", "text": text},
        "metadata": {}, "createdAt": "2026-11-21T10:00:00Z", "updatedAt": "2026-11-21T10:00:00Z",
        "timestamps": {"receivedAt": "2026-11-21T10:00:00Z"},
    }
    if received_by:
        obj["receivedBy"] = {"id": "usr_bot", "projectId": project, "platform": platform, "handle": BOT,
                             "kind": "agent", "details": {}, "metadata": {}}
    return {"id": "evt_" + mid, "type": etype, "apiVersion": "2026-07-01", "source": f"{platform}.photon",
            "timestamp": "2026-11-21T10:00:01Z", "data": {"projectId": project, "object": obj}}


class FakeStore:
    def __init__(self):
        self.state = {}
        self.fail = False

    def get_state(self, key, default=None):
        return self.state.get(key, default)

    def set_state(self, key, value):
        if self.fail:
            raise OSError("disk full")
        self.state[key] = value


@pytest.fixture()
def photon(monkeypatch):
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    monkeypatch.setenv("PHOTON_API_KEY", "pho_sk_madeup")
    monkeypatch.setenv("PHOTON_PROJECT_ID", PROJECT)
    monkeypatch.setenv("PHOTON_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("PHOTON_API_URL", raising=False)
    monkeypatch.delenv("PHOTON_PLATFORMS", raising=False)
    from mvp.channels import photon as P
    return P


@pytest.fixture()
def channel(photon):
    calls = []

    def caller(method, path, body=None, idem=None):
        calls.append({"method": method, "path": path, "body": body, "idem": idem})
        return {"id": f"out_{len(calls)}", "status": "accepted"}
    ch = photon.PhotonChannel(FakeStore(), port=0, caller=caller)
    ch.calls = calls
    yield ch
    ch.close()


# ---------- the signature ----------
def test_signature_valid(photon):
    raw, ts = b'{"a":1}', int(time.time())
    headers = {"webhook-id": "w1", "webhook-timestamp": str(ts), "webhook-signature": sign("w1", ts, raw)}
    assert photon.verify(SECRET, headers, raw) is True


def test_signature_wrong_key_body_or_id(photon):
    raw, ts = b'{"a":1}', int(time.time())
    good = sign("w1", ts, raw)
    h = {"webhook-id": "w1", "webhook-timestamp": str(ts)}
    assert not photon.verify(SECRET, {**h, "webhook-signature": sign("w1", ts, raw, key=b"another-key")}, raw)
    assert not photon.verify(SECRET, {**h, "webhook-signature": good}, b'{"a":2}')            # body changed
    assert not photon.verify(SECRET, {**h, "webhook-id": "w2", "webhook-signature": good}, raw)  # another id
    assert not photon.verify(SECRET, {**h, "webhook-signature": "v1,not-base64!!"}, raw)
    assert not photon.verify(SECRET, {**h, "webhook-signature": good.replace("v1,", "v2,")}, raw)


@pytest.mark.parametrize("shift", [-301, 301, -86400])
def test_signature_stale_or_future(photon, shift):
    raw, ts = b"{}", int(time.time()) + shift
    headers = {"webhook-id": "w1", "webhook-timestamp": str(ts), "webhook-signature": sign("w1", ts, raw)}
    assert photon.verify(SECRET, headers, raw) is False


def test_signature_inside_five_minutes(photon):
    raw, ts = b"{}", int(time.time()) - 290
    headers = {"webhook-id": "w1", "webhook-timestamp": str(ts), "webhook-signature": sign("w1", ts, raw)}
    assert photon.verify(SECRET, headers, raw) is True


def test_signature_missing_or_bad_headers(photon):
    raw, ts = b"{}", int(time.time())
    full = {"webhook-id": "w1", "webhook-timestamp": str(ts), "webhook-signature": sign("w1", ts, raw)}
    for gone in full:
        assert photon.verify(SECRET, {k: v for k, v in full.items() if k != gone}, raw) is False
    assert photon.verify(SECRET, {**full, "webhook-timestamp": "yesterday"}, raw) is False


def test_signature_during_a_secret_rotation(photon):
    """Photon sends the old and the new signature, separated by a space, while a secret is rotated."""
    raw, ts = b"{}", int(time.time())
    both = sign("w1", ts, raw, key=b"the-other-secret") + " " + sign("w1", ts, raw)
    assert photon.verify(SECRET, {"webhook-id": "w1", "webhook-timestamp": str(ts), "webhook-signature": both}, raw)


def test_secret_must_be_a_webhook_secret(photon, monkeypatch):
    monkeypatch.setenv("PHOTON_WEBHOOK_SECRET", "whsec_%%%not base64%%%")
    with pytest.raises(RuntimeError, match="PHOTON_WEBHOOK_SECRET"):
        photon.PhotonChannel(FakeStore(), port=0, caller=lambda *a, **k: {})


@pytest.mark.parametrize("name", ["PHOTON_API_KEY", "PHOTON_PROJECT_ID", "PHOTON_WEBHOOK_SECRET"])
def test_every_setting_is_needed_at_start(photon, monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(RuntimeError, match=name):
        photon.PhotonChannel(FakeStore(), port=0)


# ---------- reading an event ----------
def test_a_direct_text_is_taken(photon):
    msg, route = photon.parse_event(event("what did I save about Tokyo"), PROJECT)
    assert (msg.handle, msg.text, msg.ref) == (PERSON, "what did I save about Tokyo", "msg_1")
    assert msg.tapback is None
    assert route == {"spaceId": "spc_1", "senderId": "usr_bot"}


def test_the_first_real_event_is_read(photon):
    """photon_message_received.json is the first real delivery (21 Nov 2026) with every id, both numbers, the text
    and the times replaced. Its shape is Photon's; nothing in it is a person's."""
    with open(os.path.join(HERE, "photon_message_received.json")) as f:
        ev = json.load(f)
    obj = ev["data"]["object"]
    msg, route = photon.parse_event(ev, ev["data"]["projectId"])
    assert (msg.handle, msg.text, msg.ref) == ("+15550001", "hi", obj["id"])
    assert route == {"spaceId": obj["space"]["id"], "senderId": obj["receivedBy"]["id"]}
    assert obj["receivedBy"]["id"] in obj["space"]["participantIds"]   # what the fallback relies on


def test_the_bot_id_comes_from_the_space_when_received_by_is_absent(photon):
    msg, route = photon.parse_event(event(received_by=False), PROJECT)
    assert msg.text == "hi" and route == {"spaceId": "spc_1", "senderId": "usr_bot"}


@pytest.mark.parametrize("ev", [
    event(kind="group"),                                              # shared lines are direct only
    event(sender_kind="agent"),                                       # the bot's own message
    event(etype="message.delivered"),
    event(etype="space.typing.updated"),
    event(text="   "),
    event(content={"type": "attachment", "attachmentId": "pho_att_x"}),
    event(content={"type": "message.read"}),
    event(project="pho_prj_someone_else"),
    event(platform="sms"),                                            # iMessage only unless PHOTON_PLATFORMS says more
    event(handle=""),
    {}, {"type": "message.received"}, {"type": "message.received", "data": {"object": "text"}},
])
def test_everything_else_is_ignored(photon, ev):
    assert photon.parse_event(ev, PROJECT) is None


def test_sms_is_taken_when_switched_on(photon):
    msg, _ = photon.parse_event(event(platform="sms"), PROJECT, platforms=("imessage", "sms"))
    assert msg.handle == PERSON


# ---------- the webhook ----------
def post(ch, photon, ev, wid="w1", ts=None, key=KEY, path=None, raw=None):
    raw = json.dumps(ev).encode() if raw is None else raw
    ts = int(time.time()) if ts is None else ts
    port = ch.server.server_address[1]
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path or photon.WEBHOOK_PATH}", data=raw, method="POST",
        headers={"webhook-id": wid, "webhook-timestamp": str(ts), "webhook-signature": sign(wid, ts, raw, key=key),
                 "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


def test_webhook_takes_a_signed_message_once(channel, photon):
    assert post(channel, photon, event("hi")) == 204
    assert post(channel, photon, event("hi")) == 204                 # Photon's retry of the same delivery
    got = channel.receive()
    assert [(m.handle, m.text, m.ref) for m in got] == [(PERSON, "hi", "msg_1")]
    assert channel.receive() == []
    assert channel.store.state[f"photonroute:{PERSON}"] == {"spaceId": "spc_1", "senderId": "usr_bot"}


def test_webhook_same_message_under_a_new_delivery_id(channel, photon):
    assert post(channel, photon, event("hi"), wid="w1") == 204
    assert post(channel, photon, event("hi"), wid="w2") == 204
    assert len(channel.receive()) == 1


def test_webhook_refuses_a_wrong_signature(channel, photon):
    assert post(channel, photon, event("hi"), key=b"someone-else") == 401
    assert post(channel, photon, event("hi"), ts=int(time.time()) - 3600) == 401
    assert channel.receive() == [] and channel.store.state == {}


def test_webhook_other_paths_and_bad_bodies(channel, photon):
    assert post(channel, photon, event("hi"), path="/sendblue/receive") == 404
    assert post(channel, photon, None, raw=b"not json") == 400
    assert post(channel, photon, None, raw=b"[1, 2]", wid="w3") == 204   # signed, but nothing we read
    assert channel.receive() == []


def test_webhook_ignored_events_answer_2xx(channel, photon):
    """Anything but 2xx makes Photon retry or disable the destination, so an event we do not read is still a success."""
    assert post(channel, photon, event(etype="message.delivered")) == 204
    assert post(channel, photon, event(kind="group"), wid="w2") == 204
    assert channel.receive() == []


def test_webhook_says_503_when_the_route_cannot_be_saved(channel, photon):
    channel.store.fail = True
    assert post(channel, photon, event("hi")) == 503                 # Photon retries
    assert channel.receive() == []
    channel.store.fail = False
    assert post(channel, photon, event("hi")) == 204                 # the retry, same delivery id
    assert [m.text for m in channel.receive()] == ["hi"]


def test_route_key_ends_with_the_handle(photon):
    """Store.delete_person_data removes every state key that ends with ':<handle>': the route must be one of them."""
    assert photon.ROUTE.format(h=PERSON).endswith(":" + PERSON)


def test_delete_my_data_removes_the_route(photon, monkeypatch, tmp_path):
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.channels.photon import ROUTE
    from mvp.store import Store
    store = Store(str(tmp_path / "t.sqlite"))
    store.set_state(ROUTE.format(h=PERSON), {"spaceId": "spc_1", "senderId": "usr_bot"})
    store.set_state(ROUTE.format(h="+15550002"), {"spaceId": "spc_2", "senderId": "usr_bot"})
    store.delete_person_data(PERSON)
    assert store.get_state(ROUTE.format(h=PERSON)) is None
    assert store.get_state(ROUTE.format(h="+15550002")) is not None


# ---------- sending ----------
def test_send_goes_to_the_saved_conversation(channel, photon):
    channel.accept(event("hi"))
    ref = channel.send(PERSON, "Here is what you saved.")
    assert ref == "out_1"
    call = channel.calls[0]
    assert (call["method"], call["path"]) == ("POST", f"/v1/projects/{PROJECT}/messages")
    assert call["body"] == {"spaceId": "spc_1", "senderId": "usr_bot",
                            "content": {"type": "text", "format": "plain", "text": "Here is what you saved."}}
    assert call["idem"]


def test_each_send_has_its_own_idempotency_key(channel):
    channel.accept(event("hi"))
    channel.send(PERSON, "one")
    channel.send(PERSON, "one")
    assert channel.calls[0]["idem"] != channel.calls[1]["idem"]


def test_send_to_someone_who_never_texted_is_refused(channel, photon):
    with pytest.raises(photon.PhotonNoRoute) as e:
        channel.send("+15557777", "hello")
    assert channel.calls == []
    assert "+15557777" not in str(e.value)                            # numbers stay out of error text and logs


def test_send_uses_the_latest_conversation(channel):
    channel.accept(event("hi"))
    ev = event("again", mid="msg_2")
    ev["data"]["object"]["space"]["id"] = "spc_2"
    channel.accept(ev)
    channel.send(PERSON, "ok")
    assert channel.calls[0]["body"]["spaceId"] == "spc_2"


def test_a_message_with_no_route_keeps_the_old_one(channel):
    channel.accept(event("hi"))
    ev = event("again", mid="msg_2", received_by=False)
    ev["data"]["object"]["space"]["participantIds"] = []
    channel.accept(ev)
    assert [m.text for m in channel.receive()] == ["hi", "again"]
    assert channel.store.state[f"photonroute:{PERSON}"] == {"spaceId": "spc_1", "senderId": "usr_bot"}


def test_send_empty_text_sends_nothing(channel):
    channel.accept(event("hi"))
    assert channel.send(PERSON, "  ") is None and channel.calls == []


def test_send_long_text_is_cut(channel, photon):
    channel.accept(event("hi"))
    channel.send(PERSON, "x" * (photon.MAX_TEXT + 500))
    assert len(channel.calls[0]["body"]["content"]["text"]) == photon.MAX_TEXT


def test_a_link_is_sent_alone(channel):
    channel.accept(event("hi"))
    assert channel.link_previews is True
    channel.send_link(PERSON, {"url": "https://www.youtube.com/watch?v=madeup"})
    assert channel.calls[0]["body"]["content"]["text"] == "https://www.youtube.com/watch?v=madeup"
    assert channel.send_contact_card(PERSON) is None


# ---------- the HTTP call ----------
def test_call_sets_the_key_and_the_idempotency_header(photon, monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, timeout=None):
        seen.update(url=req.full_url, method=req.get_method(), headers={k.lower(): v for k, v in req.header_items()},
                    body=json.loads(req.data), timeout=timeout)
        return Resp(b'{"id": "out_9"}')
    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    assert photon.call("POST", "/v1/projects/p/messages", {"a": 1}, idem="k1") == {"id": "out_9"}
    assert seen["url"] == "https://api.photon.codes/v1/projects/p/messages" and seen["method"] == "POST"
    assert seen["headers"]["authorization"] == "Bearer pho_sk_madeup"
    assert seen["headers"]["user-agent"] == photon.USER_AGENT        # the default one is refused (403, Error 1010)
    assert "urllib" not in seen["headers"]["user-agent"].lower()
    assert seen["headers"]["idempotency-key"] == "k1" and seen["body"] == {"a": 1} and seen["timeout"]


@pytest.mark.parametrize("exc", [TimeoutError("slow"), urllib.error.URLError(TimeoutError("slow"))])
def test_a_timeout_is_uncertain_never_retried(photon, monkeypatch, exc):
    def boom(req, timeout=None):
        raise exc
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(photon.SendUncertain):
        photon.call("POST", "/v1/projects/p/messages", {"a": 1}, idem="k1")


def test_an_http_error_names_the_status_not_the_body(photon, monkeypatch):
    def boom(req, timeout=None):
        body = json.dumps({"title": "Too many requests", "detail": f"handle {PERSON} is limited"}).encode()
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "30"}, io.BytesIO(body))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(photon.PhotonError) as e:
        photon.call("POST", "/v1/projects/p/messages", {"a": 1}, idem="k1")
    assert e.value.status == 429 and e.value.retry_after == "30"
    assert "429" in str(e.value) and "Too many requests" in str(e.value)
    assert PERSON not in str(e.value) and "pho_sk_madeup" not in str(e.value)


def test_a_refused_connection_is_a_plain_failure(photon, monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError("no"))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(urllib.error.URLError):
        photon.call("GET", "/v1/projects/p/messages")


# ---------- signing a tester up ----------
def test_assign_asks_photon_for_a_number(photon):
    from mvp import photon_assign
    calls = []

    def caller(method, path, body=None, idem=None):
        calls.append((method, path, body, idem))
        return {"assignmentId": "asg_1", "assignedPhoneNumber": BOT, "handle": PERSON, "optIn": {"state": "pending"}}
    got = photon_assign.assign(PERSON, caller=caller)
    assert got["assignedPhoneNumber"] == BOT
    method, path, body, idem = calls[0]
    assert (method, path, body) == ("POST", f"/v1/projects/{PROJECT}/platforms/imessage/assignments", {"handle": PERSON})
    photon_assign.assign(PERSON, caller=caller)
    assert idem and calls[1][3] == idem                               # asking twice for one person is one assignment
    photon_assign.assign("+15550002", caller=caller)
    assert calls[2][3] != idem


@pytest.mark.parametrize("bad", ["5550001", "+1 555 0001", "not a number", ""])
def test_assign_wants_a_full_number_or_an_email(photon, bad):
    from mvp import photon_assign
    with pytest.raises(SystemExit):
        photon_assign.assign(bad, caller=lambda *a, **k: pytest.fail("no call for a bad handle"))


def test_assign_command_prints_the_number_to_text(photon, capsys):
    from mvp import photon_assign
    photon_assign.main([PERSON], caller=lambda *a, **k: {"assignedPhoneNumber": BOT, "optIn": {"state": "pending"}})
    out = capsys.readouterr().out
    assert BOT in out and "text" in out.lower()


def test_assign_command_lists(photon, capsys):
    from mvp import photon_assign

    def caller(method, path, body=None, idem=None):
        assert (method, path) == ("GET", f"/v1/projects/{PROJECT}/platforms/imessage/assignments")
        return {"assignments": [{"handle": PERSON, "assignedPhoneNumber": BOT, "optIn": {"state": "received"}}]}
    photon_assign.main(["--list"], caller=caller)
    out = capsys.readouterr().out
    assert PERSON in out and BOT in out and "received" in out


# ---------- starting the bot ----------
def test_the_bot_can_start_on_photon(photon, monkeypatch, tmp_path):
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp import bot
    from mvp.channels.photon import PhotonChannel
    ch = bot.make_channel("photon", FakeStore(), 0)
    try:
        assert isinstance(ch, PhotonChannel) and ch.name == "photon"
    finally:
        ch.close()
