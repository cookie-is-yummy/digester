"""Offline tests for the invited testers' sign-up page (signup_web.py, signup_page.html).

Everything here is made up: numbers, names, codes and zips. No network beyond 127.0.0.1, no Photon, no model.
"""
import io
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

INVITE = "made-up-invite-code-0123456789"
ANA, BEN, CAM, DEE = "+15550001", "+15550002", "+15550003", "+15550004"
BOT = "+15559999"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp import refresh, signup_web
    from mvp.channels.base import Inbound
    from mvp.store import Store
    store = Store(str(tmp_path / "home" / "t.sqlite"))
    assigned = []

    def assign(handle):
        assigned.append(handle)
        return {"assignedPhoneNumber": BOT, "optIn": {"state": "pending"}}
    app = signup_web.Signup(store, INVITE, assign, b"k" * 32, people_path=str(tmp_path / "home" / "people.json"),
                            library=str(tmp_path / "libs" / "empty"), max_people=3,
                            classify=refresh.classify, save_upload=refresh.save_upload)

    def text(handle, body, ref=None):
        return store.inbound_add("photon", Inbound(handle=handle, text=body, ref=ref))
    return {"app": app, "store": store, "assigned": assigned, "S": signup_web, "tmp": tmp_path, "text": text,
            "refresh": refresh}


def start(env, phone="(555) 000-1", name="Ana", **kw):
    return env["app"].start(INVITE, name, phone if phone.startswith("+") else "+1555000" + phone[-1], "America/Chicago",
                            **kw)


def refused(fn, *a, **kw):
    from_mod = sys.modules["mvp.signup_web"]
    with pytest.raises(from_mod.Refused) as e:
        fn(*a, **kw)
    return e.value.status, e.value.code


def ig_zip(html=False, junk=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if junk:
            z.writestr("holiday/photo.txt", "nothing")
        elif html:
            z.writestr("your_instagram_activity/saved/saved_posts.html", "<html></html>")
        else:
            z.writestr("your_instagram_activity/saved/saved_posts.json", json.dumps({"saved_saved_media": []}))
            z.writestr("connections/followers_and_following/following.json", json.dumps({"relationships_following": []}))
    return buf.getvalue()


# ---------- numbers ----------
@pytest.mark.parametrize("typed,want", [
    ("5550001234", "+15550001234"), ("(555) 000-1234", "+15550001234"), ("555.000.1234", "+15550001234"),
    ("1 555 000 1234", "+15550001234"), ("+1 555 000 1234", "+15550001234"), ("+44 7700 900123", "+447700900123"),
    ("555000", None), ("abc", None), ("", None), (None, None), ("+0 555 000 1234", None), ("55500012345678901", None),
    ("555-000-1234 ext 9", None), ("<script>5550001234", None),
])
def test_phone_numbers(env, typed, want):
    assert env["S"].normalize_phone(typed) == want


# ---------- the invite ----------
@pytest.mark.parametrize("bad", ["", None, "wrong", INVITE + "x", INVITE[:-1], 12345, ["x"]])
def test_every_call_needs_the_invite(env, bad):
    app = env["app"]
    assert refused(app.start, bad, "Ana", ANA, "UTC") == (403, "invite")
    assert refused(app.status, bad, "c", "s") == (403, "invite")
    assert refused(app.upload, bad, "t", "a.zip", io.BytesIO(b""), 1, 100) == (403, "invite")
    assert env["assigned"] == [] and env["store"].person(ANA) is None


@pytest.mark.parametrize("weak", ["", "short", "fifteen-chars-x"])
def test_a_weak_invite_is_refused_at_start(env, weak):
    with pytest.raises(RuntimeError, match="MVP_SIGNUP_INVITE"):
        env["S"].Signup(env["store"], weak, lambda h: {}, b"k" * 32, library=str(env["tmp"] / "l"))


# ---------- step 1 ----------
def test_start_adds_the_person_and_shows_a_code(env):
    out = env["app"].start(INVITE, "  Ana  ", "(555) 000-1234", "America/Chicago")
    assert set(out) == {"claim", "secret", "code", "botNumber"}
    assert re.fullmatch(r"\d{6}", out["code"]) and out["botNumber"] == BOT
    assert env["assigned"] == ["+15550001234"]
    p = env["store"].person("+15550001234")
    assert (p["name"], p["timezone"]) == ("Ana", "America/Chicago") and not p["consent_version"]
    people_path = env["app"].people_path
    with open(people_path) as f:
        assert json.load(f)["+15550001234"]["name"] == "Ana"
    assert stat.S_IMODE(os.stat(people_path).st_mode) == 0o600
    assert os.path.isfile(os.path.join(p["library"], "corpus", "items.jsonl"))


def test_the_bot_can_load_what_the_sign_up_wrote(env):
    env["app"].start(INVITE, "Ana", ANA, "America/Chicago")
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot

    class NoPool:
        max_resident = 1
    bot = Bot(ConsoleChannel(printer=None), store=env["store"], pool=NoPool())
    assert bot.load_people(env["app"].people_path) == 1


@pytest.mark.parametrize("name", [" ", "A" * 41, 7, ["Ana"], "Ana<script>", "Ana\nBen", "Ana\tBen", "Ana\x00", "1234", "Ana; DROP TABLE people", "{}"])
def test_bad_names_are_refused(env, name):
    assert refused(env["app"].start, INVITE, name, ANA, "UTC") == (400, "name")
    assert env["assigned"] == []


@pytest.mark.parametrize("name", [None, ""])
def test_a_number_alone_is_enough(env, name):
    assert env["app"].start(INVITE, name, ANA, "UTC")["code"]
    assert env["store"].person(ANA)["name"] is None


@pytest.mark.parametrize("name", ["Ana", "Mary Ann", "O'Neil", "Jean-Luc", "José", "Zoë", "李"])
def test_real_names_are_taken(env, name):
    assert env["app"].start(INVITE, name, ANA, "UTC")["code"]


@pytest.mark.parametrize("phone", ["", "555", "not a number", "+1555", None])
def test_bad_numbers_are_refused(env, phone):
    assert refused(env["app"].start, INVITE, "Ana", phone, "UTC") == (400, "phone")
    assert env["assigned"] == []


def test_an_unknown_time_zone_falls_back(env):
    for i, tz in enumerate(["Mars/Olympus", "", "../../etc/passwd", None]):
        handle = f"+1555000100{i}"
        env["app"].max_people = 10
        env["app"].start(INVITE, "Ana", handle, tz)
        assert env["store"].person(handle)["timezone"] == "America/New_York"


def test_the_test_is_full_after_the_limit(env):
    for i, h in enumerate([ANA, BEN, CAM]):
        env["app"].start(INVITE, "Ana", h, "UTC", ip=f"ip{i}")
    assert refused(env["app"].start, INVITE, "Dee", DEE, "UTC") == (409, "full")
    assert DEE not in env["assigned"] and env["store"].person(DEE) is None
    assert env["app"].start(INVITE, "Ana", ANA, "UTC")["code"]        # someone already in can come back


def test_a_deleted_person_is_not_added_back(env):
    env["store"].add_deletion({"handle": ANA})
    assert refused(env["app"].start, INVITE, "Ana", ANA, "UTC") == (409, "ask_founder")
    assert env["assigned"] == [] and env["store"].person(ANA) is None


def test_when_photon_says_no_nobody_is_added(env):
    def boom(handle):
        raise OSError("down")
    env["app"].assign = boom
    assert refused(env["app"].start, INVITE, "Ana", ANA, "UTC") == (502, "try_later")
    env["app"].assign = lambda h: {}
    assert refused(env["app"].start, INVITE, "Ana", ANA, "UTC") == (502, "try_later")
    assert env["store"].person(ANA) is None and not os.path.exists(env["app"].people_path)


def test_sign_ups_are_limited_per_address_and_for_everyone(env):
    env["app"].max_people = 1000
    for i in range(10):
        env["app"].start(INVITE, "Ana", f"+155500020{i:02d}", "UTC", ip="1.2.3.4")
    assert refused(env["app"].start, INVITE, "Ana", "+15550002099", "UTC", ip="1.2.3.4") == (429, "slow_down")
    for i in range(30):                                               # 10 above and 30 here: 40 in the hour
        env["app"].start(INVITE, "Ana", f"+155500021{i:02d}", "UTC", ip=f"9.9.9.{i}")
    assert refused(env["app"].start, INVITE, "Ana", "+15550002199", "UTC", ip="8.8.8.8") == (429, "slow_down")


# ---------- step 2 ----------
def test_not_verified_until_the_code_arrives_from_that_number(env):
    app, text = env["app"], env["text"]
    c = app.start(INVITE, "Ana", ANA, "UTC")
    assert app.status(INVITE, c["claim"], c["secret"]) == {"verified": False}
    text(ANA, "hi there", "m1")
    text(ANA, "my code is 000000", "m2")
    text(BEN, f"Hi digestr {c['code']}", "m3")                        # the right code from someone else's phone
    text(ANA, f"9{c['code']}", "m4")                                  # the digits inside a longer number
    assert app.status(INVITE, c["claim"], c["secret"]) == {"verified": False}
    text(ANA, f"Hi digestr {c['code']}", "m5")
    out = app.status(INVITE, c["claim"], c["secret"])
    assert out["verified"] is True
    assert env["S"].read_ticket(app.key, out["ticket"]) == ANA
    assert app.status(INVITE, c["claim"], c["secret"])["verified"] is True   # asked again: still yes


def test_a_text_from_before_the_sign_up_never_counts(env):
    app = env["app"]
    first = app.start(INVITE, "Ana", ANA, "UTC")
    env["text"](ANA, first["code"], "m1")
    second = app.start(INVITE, "Ana", ANA, "UTC")
    env["text"](ANA, "111111 222222 333333", "m2")
    if second["code"] != first["code"]:
        assert app.status(INVITE, second["claim"], second["secret"]) == {"verified": False}
    assert app.status(INVITE, first["claim"], first["secret"])["verified"] is True


def test_signing_up_with_someone_elses_number_gets_nothing_of_theirs(env):
    """Ben is a tester. A stranger with the invite types Ben's number. Ben keeps texting the bot as usual."""
    app, text = env["app"], env["text"]
    ben = app.start(INVITE, "Ben", BEN, "UTC")
    text(BEN, f"Hi digestr {ben['code']}", "m1")
    assert app.status(INVITE, ben["claim"], ben["secret"])["verified"] is True
    stranger = app.start(INVITE, "Mallory", BEN, "UTC", ip="6.6.6.6")
    for i, body in enumerate(["what did I save about Tokyo", "remind me at 9", f"Hi digestr {ben['code']}", "yes"]):
        text(BEN, body, f"n{i}")
    assert app.status(INVITE, stranger["claim"], stranger["secret"], ip="6.6.6.6") == {"verified": False}
    assert env["store"].person(BEN)["name"] == "Ben"                  # the stranger's name changed nothing
    assert refused(app.status, INVITE, ben["claim"], stranger["secret"]) == (404, "claim")   # nor does mixing claims


def test_a_claim_needs_its_own_secret_and_lasts_thirty_minutes(env):
    app = env["app"]
    c = app.start(INVITE, "Ana", ANA, "UTC", now=1000.0)
    for claim, secret in [(c["claim"], "nope"), ("nope", c["secret"]), (None, None), (c["claim"], None), (["x"], 5)]:
        assert refused(app.status, INVITE, claim, secret, now=1001.0) == (404, "claim")
    assert app.status(INVITE, c["claim"], c["secret"], now=1000.0 + 29 * 60) == {"verified": False}
    assert refused(app.status, INVITE, c["claim"], c["secret"], now=1000.0 + 31 * 60) == (404, "claim")


def test_codes_and_secrets_differ_each_time(env):
    env["app"].max_people = 1000
    got = [env["app"].start(INVITE, "Ana", f"+155500030{i:02d}", "UTC", ip=f"i{i}") for i in range(8)]
    assert len({g["secret"] for g in got}) == 8 and len({g["claim"] for g in got}) == 8
    assert len({g["code"] for g in got}) > 1


# ---------- tickets ----------
def test_tickets(env):
    S = env["S"]
    key = b"a" * 32
    t = S.make_ticket(key, ANA, now=5000)
    assert S.read_ticket(key, t, now=5000 + 3600) == ANA
    assert S.read_ticket(key, t, now=5000 + 25 * 3600) is None        # a day old
    assert S.read_ticket(key, t, now=4000) is None                    # from the future
    assert S.read_ticket(b"b" * 32, t, now=5001) is None              # another computer's key
    body, mac = t.split(".")
    assert S.read_ticket(key, S.make_ticket(key, BEN, now=5000).split(".")[0] + "." + mac, now=5001) is None
    for junk in ["", None, ".", "abc", "abc.def", body + ".", "." + mac]:
        assert S.read_ticket(key, junk, now=5001) is None


def test_the_signing_key_is_made_once_and_private(env):
    home = str(env["tmp"] / "keyhome")
    k1 = env["S"].load_key(home)
    assert len(k1) == 32 and env["S"].load_key(home) == k1
    assert stat.S_IMODE(os.stat(os.path.join(home, "signup_key.txt")).st_mode) == 0o600


# ---------- step 3 ----------
def verified(env, handle=ANA):
    c = env["app"].start(INVITE, "Ana", handle, "UTC")
    env["text"](handle, c["code"], "v-" + handle)
    return env["app"].status(INVITE, c["claim"], c["secret"])["ticket"]


def inbox_files(env, handle=ANA):
    d = env["refresh"].inbox_dir(handle)
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def test_a_real_export_lands_in_that_persons_inbox(env):
    ticket, data = verified(env), ig_zip()
    out = env["app"].upload(INVITE, ticket, "instagram-ana.zip", io.BytesIO(data), len(data), 10 ** 6)
    assert out == {"ok": True, "kind": "instagram"}
    assert inbox_files(env) == ["instagram-ana.zip"] and inbox_files(env, BEN) == []


def test_upload_needs_a_ticket_for_a_person_still_here(env):
    data = ig_zip()
    for ticket in ["", None, "abc.def", env["S"].make_ticket(b"x" * 32, ANA)]:
        assert refused(env["app"].upload, INVITE, ticket, "a.zip", io.BytesIO(data), len(data), 10 ** 6) == (403, "ticket")
    ticket = verified(env)
    env["store"].delete_person_data(ANA)                              # they asked for deletion after verifying
    assert refused(env["app"].upload, INVITE, ticket, "a.zip", io.BytesIO(data), len(data), 10 ** 6) == (403, "ticket")
    assert inbox_files(env) == []


@pytest.mark.parametrize("data,code", [(ig_zip(html=True), "html"), (ig_zip(junk=True), "not_export"),
                                       (b"not a zip at all", "not_export"), (b"PK\x03\x04broken", "not_export")])
def test_anything_that_is_not_an_export_is_deleted_at_once(env, data, code):
    ticket = verified(env)
    assert refused(env["app"].upload, INVITE, ticket, "x.zip", io.BytesIO(data), len(data), 10 ** 6) == (415, code)
    assert inbox_files(env) == []                                     # not kept, and no .failed copy


def test_upload_size_and_length(env):
    ticket, data = verified(env), ig_zip()
    assert refused(env["app"].upload, INVITE, ticket, "a.zip", io.BytesIO(data), len(data), len(data) - 1) == (413, "too_big")
    for length in [0, -5, None, "12"]:
        assert refused(env["app"].upload, INVITE, ticket, "a.zip", io.BytesIO(data), length, 10 ** 6) == (411, "length")
    assert refused(env["app"].upload, INVITE, ticket, "a.zip", io.BytesIO(data[:10]), len(data), 10 ** 6) == (400, "cut_off")
    assert inbox_files(env) == []


def test_a_file_name_cannot_leave_the_inbox(env):
    ticket, data = verified(env), ig_zip()
    env["app"].upload(INVITE, ticket, "../../../etc/cron.d/x.zip", io.BytesIO(data), len(data), 10 ** 6)
    env["app"].upload(INVITE, ticket, "..\\..\\evil.zip", io.BytesIO(data), len(data), 10 ** 6)
    assert inbox_files(env) == ["evil.zip", "x.zip"]
    assert not os.path.exists("/etc/cron.d/x.zip")


def test_uploads_are_limited_per_person(env):
    ticket, data = verified(env), ig_zip()
    for i in range(8):
        env["app"].upload(INVITE, ticket, f"a{i}.zip", io.BytesIO(data), len(data), 10 ** 6, ip=f"u{i}")
    assert refused(env["app"].upload, INVITE, ticket, "a9.zip", io.BytesIO(data), len(data), 10 ** 6) == (429, "slow_down")


def test_limiter(env):
    lim = env["S"].Limiter(2, 60)
    assert lim.allow("a", 0) and lim.allow("a", 1) and not lim.allow("a", 2)
    assert lim.allow("b", 2) and lim.allow("a", 61)


# ---------- the page and the wire ----------
@pytest.fixture()
def web(env):
    server = env["S"].make_server(env["app"], port=0, max_upload=10 ** 6)
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env["base"] = f"http://127.0.0.1:{server.server_address[1]}"
    env["server"] = server
    yield env
    server.shutdown()
    server.server_close()


def call(env, path, body=None, headers=None, raw=None, method=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(env["base"] + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                 headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_the_page_is_served_locked_down(web):
    status, headers, body = call(web, "/")
    html = body.decode()
    assert status == 200 and "__NONCE__" not in html and "__MAX_MB__" not in html
    nonce = re.search(r'<script nonce="([^"]+)">', html).group(1)
    csp = headers["Content-Security-Policy"]
    assert f"script-src 'nonce-{nonce}'" in csp and f"style-src 'nonce-{nonce}'" in csp
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp and "unsafe" not in csp
    assert headers["Cache-Control"] == "no-store" and headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer" and headers["X-Content-Type-Options"] == "nosniff"
    assert call(web, "/")[2].decode() != html                         # a new nonce every time
    assert web["server"].server_address[0] == "127.0.0.1"


def test_the_page_asks_nothing_of_other_sites(web):
    html = call(web, "/")[2].decode()
    links = set(re.findall(r'(?:src|href|action)="(https?://[^"]+)"', html))
    assert links == {"https://accountscenter.instagram.com/info_and_permissions/dyi/"}
    assert not re.search(r"<(script|link|img|iframe)[^>]+(src|href)=", html)   # no outside script, style, image or frame
    assert "location.hash" in html and "location.search" not in html  # the invite stays in the fragment
    assert 'on' + 'click="' not in html and "eval(" not in html and "innerHTML" not in html


def test_the_page_has_what_a_person_needs(web):
    html = call(web, "/")[2].decode()
    for must in ['autocomplete="tel"', 'for="phone"', 'aria-live="polite"', 'role="alert"',
                 "prefers-color-scheme: dark", "prefers-reduced-motion", 'name="viewport"', "delete my data",
                 "Leave Messages unticked", "JSON", '<html lang="en">']:
        assert must in html, must
    for label in re.findall(r'<label class="field" for="([^"]+)"', html):
        assert f'id="{label}"' in html


def test_other_paths_and_methods(web):
    assert call(web, "/admin")[0] == 404 and call(web, "/api/start", method="GET")[0] == 404
    assert call(web, "/.env")[0] == 404 and call(web, "/api/nope", {"a": 1})[0] == 404
    assert call(web, "/api/start", raw=b"not json")[0] == 400
    assert call(web, "/api/start", raw=b"[1,2]")[0] == 400
    assert call(web, "/api/start", raw=b"x" * 5000)[0] == 400


def test_the_whole_flow_over_http(web):
    status, _, body = call(web, "/api/start", {"invite": INVITE, "phone": "555 000 1234",
                                               "timezone": "America/Los_Angeles"})
    c = json.loads(body)
    assert status == 200 and c["botNumber"] == BOT
    q = {"invite": INVITE, "claim": c["claim"], "secret": c["secret"]}
    assert json.loads(call(web, "/api/status", q)[2]) == {"verified": False}
    web["text"]("+15550001234", f"Hi digestr {c['code']}", "m1")
    ticket = json.loads(call(web, "/api/status", q)[2])["ticket"]
    data = ig_zip()
    up = {"X-Invite": INVITE, "X-Ticket": ticket, "X-Filename": "export.zip", "Content-Type": "application/zip"}
    status, _, body = call(web, "/api/upload", raw=data, headers=up)
    assert (status, json.loads(body)) == (200, {"ok": True, "kind": "instagram"})
    assert inbox_files(web, "+15550001234") == ["export.zip"]


def test_errors_on_the_wire_say_little(web):
    status, headers, body = call(web, "/api/start", {"invite": "wrong", "name": "Ana", "phone": "5550001234"})
    assert status == 403 and json.loads(body) == {"error": "invite"} and headers["Cache-Control"] == "no-store"
    status, _, body = call(web, "/api/start", {"invite": INVITE, "name": "Ana", "phone": "abc"})
    assert status == 400 and json.loads(body) == {"error": "phone"}
    web["app"].assign = lambda h: (_ for _ in ()).throw(RuntimeError("secret detail +15550001234"))
    status, _, body = call(web, "/api/start", {"invite": INVITE, "name": "Ana", "phone": "5550001234"})
    assert status == 502 and b"secret detail" not in body and b"5550001234" not in body
    status, _, body = call(web, "/api/upload", raw=b"x", headers={"X-Invite": INVITE, "X-Ticket": "bad"})
    assert status == 403 and json.loads(body) == {"error": "ticket"}


def test_an_upload_over_the_limit_is_refused_by_its_size(web):
    c = json.loads(call(web, "/api/start", {"invite": INVITE, "name": "Ana", "phone": "5550001234"})[2])
    web["text"]("+15550001234", c["code"], "m1")
    ticket = json.loads(call(web, "/api/status", {"invite": INVITE, "claim": c["claim"], "secret": c["secret"]})[2])["ticket"]
    web["server"].shutdown()
    web["server"].server_close()
    small = web["S"].make_server(web["app"], port=0, max_upload=50)
    import threading
    threading.Thread(target=small.serve_forever, daemon=True).start()
    web["server"], web["base"] = small, f"http://127.0.0.1:{small.server_address[1]}"
    data = ig_zip()
    status, _, body = call(web, "/api/upload", raw=data, headers={"X-Invite": INVITE, "X-Ticket": ticket})
    assert status == 413 and json.loads(body) == {"error": "too_big"}
    assert inbox_files(web, "+15550001234") == []
