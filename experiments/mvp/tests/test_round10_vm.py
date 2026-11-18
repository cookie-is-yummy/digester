"""Offline tests for round 10, slice V5 (DESIGN.md section 17.V; the addendum's section 1; amendment A-016, Proposed):
the "virtual machine": a headless browser inside the bot's machine (browser_vm.VmHost) that the person watches and
takes over on the test page (/vm). The practice merchant "Streamly" (tests/fakes/fake_merchant.py) is served by routing,
no port; the test page listens on a free port of 127.0.0.1 chosen by the system (never 8765 or 8791). A fake person
clicks and types through the view's endpoints. No model call anywhere.

Where no browser can start, the tests that need one are skipped, and pytest counts them.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round10_browser import WHY_NO_BROWSER, chromium_left  # noqa: E402
from mvp.tests.test_slice2 import H  # noqa: E402

UTC = timezone.utc
needs_browser = pytest.mark.skipif(WHY_NO_BROWSER is not None, reason=f"no browser can start here: {WHY_NO_BROWSER}")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 only, never through a proxy
EMAIL, PASSWORD = "person@example.com", "Not-A-Real-Pass-42"


def vm_host():
    """VmHost whose sessions can also tell the test where a field is and what it holds (the fake person's eyes)."""
    from mvp.browser_vm import VmHost, VmSession

    class TestSession(VmSession):
        def _c_box(self, selector):
            b = self.page.locator(selector).bounding_box()
            return [b["x"] + b["width"] / 2, b["y"] + b["height"] / 2]

        def _c_url(self):
            return self.page.url

        def _c_signed_in(self):
            return (self.page.locator("input[type=password]").count() == 0
                    and self.page.locator("text=Cancel membership").count() == 1)

        def _c_count_final(self):
            return self.page.url.endswith("/done")

    class TestHost(VmHost):
        session_class = TestSession

    return TestHost()


@pytest.fixture()
def vm(env, monkeypatch):
    """The env bot on the test page (a WebChannel on a free port), MVP_BROWSER=vm with the practice merchant
    (MVP_BROWSER_DEMO=1: flow 5, a sign-in first), the env person as the operator."""
    from mvp import browser, config
    from mvp.channels.web import WebChannel
    env["clock"][0] = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)
    bot = env["bot"]
    bot.max_per_minute = None
    ch = WebChannel(port=0, serve=True)
    ch.attach(bot)
    bot.channel = ch
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    monkeypatch.delenv("MVP_BROWSER_MERCHANTS", raising=False)
    monkeypatch.delenv("MVP_BROWSER_FOR", raising=False)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setattr(browser, "make_host", lambda m: vm_host())
    env["web"] = ch
    yield env
    browser.close_all(bot)
    ch.close()
    assert chromium_left() == []


def said(e):
    return [m["text"] for m in e["web"].threads.get(H, []) if m["dir"] == "out"]


def msg(e, text):
    e["bot"].on_message(H, text)
    return said(e)[-1]


def walked(e):
    from mvp import browser
    assert browser.wait(e["bot"], H, timeout=60)
    return said(e)[-1]


def run(e):
    from mvp import browser
    return browser._sessions(e["bot"])["runs"].get(H)


def http(e, method, path, body=None):
    url = e["web"].base_url + path
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with OPENER.open(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read()


def link_key(text):
    m = re.search(r"/vm\?k=([\w-]+)", text)
    return m.group(1) if m else None


def person_does(e, key, *events):
    for ev in events:
        code, _, body = http(e, "POST", f"/api/vm/input?k={key}", ev)
        assert code == 204 and body == b""


def wait_until(fn, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(0.1)
    return False


def open_to_sign_in(e):
    assert "in a browser on my side that you can watch" in msg(e, "cancel my streamly")
    perm = msg(e, "do it for me")
    assert "in a browser on my side that you can watch" in perm and perm.endswith("Reply \"allow streamly\" to go "
                                                                                  "ahead.")
    opening = msg(e, "allow streamly")
    key = link_key(opening)
    assert key and opening.startswith("Opening Streamly in a browser on my side. Watch it here: "
                                      f"{e['web'].base_url}/vm?k={key} .")
    return key


def sign_in_through_the_view(e, key):
    s = run(e)["session"]
    for selector, text in (("input[type=email]", EMAIL), ("input[type=password]", PASSWORD)):
        x, y = s.call("box", selector)
        person_does(e, key, {"type": "click", "x": x, "y": y})
        for i in range(0, len(text), 5):
            person_does(e, key, {"type": "text", "text": text[i:i + 5]})
    x, y = s.call("box", "button")
    person_does(e, key, {"type": "click", "x": x, "y": y})
    assert wait_until(lambda: s.call("signed_in"))


@needs_browser
def test_the_practice_cancel_end_to_end_with_the_sign_in_through_the_view(vm, tmp_path, caplog):
    from mvp import browser_vm
    t0 = time.monotonic()
    key = open_to_sign_in(vm)
    assert said(vm)[0].endswith("Streamly is a practice site made up for trying this: no real account, no real money.")
    code, headers, page = http(vm, "GET", f"/vm?k={key}")
    assert code == 200 and b"Take over" in page and headers.get("Referrer-Policy") == "no-referrer"
    assert http(vm, "GET", "/vm?k=wrong")[0] == 404
    assert wait_until(lambda: http(vm, "GET", f"/api/vm/frame?k={key}&after=0")[0] == 200)
    code, headers, jpeg = http(vm, "GET", f"/api/vm/frame?k={key}&after=0")
    assert jpeg[:2] == b"\xff\xd8" and headers["X-Held"] == "person"   # the person holds it while signing in
    sign_in_through_the_view(vm, key)
    person_does(vm, key, {"type": "handback"})   # "I'm done" on the view acts as "I'm in"
    assert wait_until(lambda: said(vm)[-1].startswith("This is the last step."), 30)
    assert said(vm)[-2] == "Thanks. Going to the cancel page."
    assert msg(vm, "yes cancel streamly").startswith("Streamly's page now says: \"Your membership has been cancelled.")
    seconds = time.monotonic() - t0
    assert run(vm) is None and browser_vm.open_views() == 0
    assert http(vm, "GET", f"/api/vm/frame?k={key}&after=0")[0] == 410   # the key died with the run
    # what the person typed is in no store row, file, log line or reply; no picture was written
    from mvp.tests.test_round10_browser import _all_kept_text
    kept = _all_kept_text(vm, tmp_path) + "\n".join(r.getMessage() for r in caplog.records) + "\n".join(said(vm))
    assert EMAIL not in kept and PASSWORD not in kept and "Not-A-Real" not in kept
    assert not [f for _, _, fs in os.walk(tmp_path) for f in fs if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    row = vm["bot"].store.browser_runs_of(H)[0]
    assert (row["host"], row["status"]) == ("vm", "page_says_cancelled")
    assert seconds < 60


@needs_browser
def test_the_bot_presses_nothing_while_the_person_holds_the_view(vm):
    key = open_to_sign_in(vm)
    sign_in_through_the_view(vm, key)
    msg(vm, "I'm in")
    assert walked(vm).startswith("This is the last step.")
    person_does(vm, key, {"type": "take"})
    s = run(vm)["session"]
    assert wait_until(lambda: s.takeover)
    out = msg(vm, "yes cancel streamly")
    assert out == "You have the browser right now, so I didn't press it. Say \"I'm in\" first, then \"yes cancel " \
                  "streamly\"."
    assert not s.call("count_final")
    assert http(vm, "GET", f"/api/vm/frame?k={key}&after=0")[1]["X-Held"] == "person"


@needs_browser
def test_clicks_and_keys_are_not_forwarded_while_the_bot_holds_the_browser(vm):
    key = open_to_sign_in(vm)
    sign_in_through_the_view(vm, key)
    msg(vm, "I'm in")
    walked(vm)
    s = run(vm)["session"]
    assert not s.takeover
    before = s.call("url")
    x, y = s.call("box", "button:has-text('Go back')")
    person_does(vm, key, {"type": "click", "x": x, "y": y}, {"type": "key", "key": "Enter"})
    time.sleep(0.5)
    assert s.call("url") == before


@needs_browser
def test_stop_on_the_view_closes_everything(vm):
    key = open_to_sign_in(vm)
    person_does(vm, key, {"type": "stop"})
    assert wait_until(lambda: said(vm)[-1] == "Stopped. I closed the browser. Nothing else was pressed.")
    assert run(vm) is None and chromium_left() == []
    assert http(vm, "GET", f"/api/vm/frame?k={key}&after=0")[0] == 410


@needs_browser
def test_bad_input_is_dropped_silently(vm):
    key = open_to_sign_in(vm)
    for body in (b"not json", b"[1,2]", json.dumps({"type": "text", "text": 5}).encode(),
                 json.dumps({"type": "key", "key": "F12"}).encode(), json.dumps({"type": "click", "x": "a"}).encode()):
        code, _, out = http(vm, "POST", f"/api/vm/input?k={key}", body)
        assert code == 204 and out == b""
    assert http(vm, "POST", f"/api/vm/input?k={key}", b"x" * 5000)[0] == 413
    assert http(vm, "POST", "/api/vm/input?k=nope", {"type": "text", "text": "abc"})[0] == 403
    assert run(vm)["session"].alive


@needs_browser
def test_memory_and_time_for_one_run(vm):
    """Counts for the report: the Chromium processes' resident memory while the page is open, and the time from the
    offer to the last step."""
    t0 = time.monotonic()
    key = open_to_sign_in(vm)
    sign_in_through_the_view(vm, key)
    msg(vm, "I'm in")
    walked(vm)
    seconds = time.monotonic() - t0
    rss = 0
    for pid in run(vm)["session"].pids:
        try:
            with open(f"/proc/{pid}/status") as f:
                rss += next(int(x.split()[1]) for x in f if x.startswith("VmRSS:"))
        except (OSError, StopIteration):
            pass
    print(f"VM run: {len(run(vm)['session'].pids)} processes, {rss // 1024} MB resident, {seconds:.1f} s to the "
          f"last step")
    assert 0 < rss // 1024 < 2000 and seconds < 60


# ---------- who sees it ----------
def test_a_tester_never_sees_it_unless_the_setting_opens_it_to_everyone(env, monkeypatch):
    from mvp import browser, config
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    person = env["bot"].store.person(H)
    assert browser.why_not(env["bot"], person, "streamly") == "person"
    monkeypatch.setenv("MVP_BROWSER_FOR", "all")
    assert browser.why_not(env["bot"], person, "streamly") == "channel"   # the env bot is not on the test page
    monkeypatch.setenv("MVP_BROWSER", "operator")   # "all" opens only the vm, never the window on this computer
    assert browser.why_not(env["bot"], person, "streamly") == "person"


def test_off_the_test_page_it_says_so(env, monkeypatch):
    from mvp import config
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    monkeypatch.setattr(config, "OPERATOR", H)
    env["clock"][0] = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)
    env["bot"].on_message(H, "cancel my streamly")
    out = env["ch"].outbox[-1][2]
    assert out.startswith("I can only do that from the test page for now.\n")
    assert env["bot"].store.get_state(f"browserrun:{H}") is None


def test_the_practice_merchant_exists_only_with_the_demo_and_the_browser_on(env, monkeypatch):
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    monkeypatch.delenv("MVP_BROWSER", raising=False)
    assert browser.practice_routes() is None and "streamly" not in browser.merchants()
    monkeypatch.setenv("MVP_BROWSER", "vm")
    assert "streamly" in browser.merchants()
    assert any(m["key"] == "streamly" for m in browser.practice_routes()["merchants"])


def test_denied_sites_with_the_vm_on(env, monkeypatch):
    from mvp import browser, config
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "youtube_premium")
    monkeypatch.setattr(config, "OPERATOR", H)
    assert browser.why_not(env["bot"], env["bot"].store.person(H), "youtube_premium") == "denied"


def test_the_view_has_no_route_without_a_key_and_the_page_token_is_not_needed(env):
    """The view's endpoints take the run's own key; a wrong or missing key gets nothing (and the page's token does
    not open them)."""
    from mvp.channels.web import WebChannel
    ch = WebChannel(port=0, serve=True)
    try:
        for path in ("/vm", "/vm?k=", "/api/vm/frame?k=abc"):
            req = urllib.request.Request(ch.base_url + path, headers={"X-Test-Token": ch.token})
            try:
                code = OPENER.open(req, timeout=5).status
            except urllib.error.HTTPError as err:
                code = err.code
            assert code in (404, 410), path
    finally:
        ch.close()
