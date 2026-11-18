"""Offline tests for the adversarial check of round 10 on acting and secrets (checker 1 of the verdict's section 5.2;
DESIGN.md section 17, "The check of acting and secrets"). Each test here failed before the fix it guards.

- The browser: a redirect from an allowed merchant page to another site (a denied one among them) never leaves the
  machine (browser_host.network_lock); a host is read the way the browser reads it (browser_guard.canon / host).
- Secrets typed into the chat in everyday shapes are refused before any model sees them (connectors.secret_said).
- The take-over view (/vm) belongs to the first browser that opens it (browser_vm, a cookie per view).
- The test page answers only requests addressed to it (channels/web.py, the Host check).
- A merchant button whose label for assistants differs from what it shows is never pressed (browser_guard.allowed).

Fakes only: a local http server on a free port of 127.0.0.1 (never 8765 or 8791) plays a merchant; a made-up name stands
for a denied site; Chromium resolves it to that server only in the test. No model call, no real site.
"""
import http.server
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round10_browser import WHY_NO_BROWSER, chromium_left  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

needs_browser = pytest.mark.skipif(WHY_NO_BROWSER is not None, reason=f"no browser can start here: {WHY_NO_BROWSER}")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 only, never through a proxy


# =====================================================================================================================
# 1. The browser never follows a redirect off the merchant's own hosts (a denied site above all)
# =====================================================================================================================
class _Sites:
    """Two local servers: the merchant (allowed) and 'elsewhere' (must never be reached). Elsewhere counts its hits."""

    def __init__(self):
        sites = self
        self.hits = []

        class Merchant(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/go/"):
                    self.send_response(302)
                    self.send_header("Location", sites.targets[self.path[4:]])
                    self.end_headers()
                    return
                body = b"<h1>Your account</h1><a href='/x'>Cancel membership</a>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        class Elsewhere(Merchant):
            def do_GET(self):
                sites.hits.append(self.headers.get("Host"))
                body = b"<h1>elsewhere</h1>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.m = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Merchant)
        self.e = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Elsewhere)
        self.e2 = http.server.ThreadingHTTPServer(("127.0.0.2", 0), Elsewhere)   # another address of this computer
        for s in (self.m, self.e, self.e2):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        ep = self.e.server_address[1]
        self.base = f"http://127.0.0.1:{self.m.server_address[1]}"
        self.targets = {"denied": f"http://www.denied-social.example:{ep}/feed",
                        "other": f"http://localhost:{ep}/other",
                        "ip": f"http://127.0.0.2:{self.e2.server_address[1]}/ip"}

    def close(self):
        for s in (self.m, self.e, self.e2):
            s.shutdown()
            s.server_close()


@pytest.fixture()
def sites(monkeypatch):
    from mvp import browser_guard as G
    for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "no_proxy",
              "NO_PROXY"):
        monkeypatch.delenv(k, raising=False)   # Chromium would hand a made-up name to this machine's proxy instead
    monkeypatch.setattr(G, "DENIED_SITES", G.DENIED_SITES + ("denied-social.example",))
    s = _Sites()
    yield s
    s.close()
    assert chromium_left() == []


def _session(rules):
    from mvp.browser_host import Session

    class S(Session):
        # the made-up denied site is this computer, for the test only: reaching it would be a hit on `elsewhere`
        extra_args = (f"--host-resolver-rules={rules}",)

        def _c_url(self):
            return self.page.url
    return S(("127.0.0.1",), headless=True)


@needs_browser
@pytest.mark.parametrize("where", ["denied", "other", "ip"])
def test_a_redirect_from_the_merchant_to_another_site_never_leaves_the_machine(sites, where):
    s = _session("MAP www.denied-social.example 127.0.0.1")
    try:
        s.call("goto", sites.base + "/")                      # the merchant's own page loads
        try:
            s.call("goto", f"{sites.base}/go/{where}")
        except Exception:  # noqa: BLE001 - the redirect's target fails in the browser: that is the point
            pass
        time.sleep(0.5)
        assert sites.hits == [], (where, sites.hits)
        assert "elsewhere" not in s.call("snapshot")["text"]
    finally:
        s.kill()


def test_the_network_lock_lets_only_the_routes_own_hosts_out_and_never_a_denied_site():
    from mvp.browser_host import BLACKHOLE, network_lock
    lock = network_lock(("WWW.Shop.Example.", "cdn.shop.example", "www.instagram.com", "m.facebook.com",
                         "bad host,*", ""))
    assert lock["server"] == BLACKHOLE
    assert lock["bypass"].split(",") == ["<-loopback>", "www.shop.example", "cdn.shop.example"]


@pytest.mark.parametrize("url", [
    "https://www.ＩＮＳＴＡＧＲＡＭ.com/", "https://www.instagram.com./", "https://%69nstagram.com/",
    "https://WWW.TikTok.COM:443/", "https://instagram.com\\@shop.example/", "https://ins\ttagram.com/",
    "https://accounts.google.com./signin", "https://m.youtube.com/feed"])
def test_a_denied_site_is_known_in_every_spelling_the_browser_accepts(url):
    from mvp import browser_guard as G
    assert G.denied(url), url


@pytest.mark.parametrize("host", ["ＩＮＳＴＡＧＲＡＭ.com", "instagram.com.", "Instagram.com:443", "%69nstagram.com"])
def test_a_route_file_naming_a_denied_site_in_another_spelling_is_refused(env, monkeypatch, host):
    from mvp import browser, config
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "lookalike")
    monkeypatch.setattr(config, "OPERATOR", H)
    e = browser.practice_entry(1)
    e = dict(e, key="lookalike", name="Lookalike", names=["lookalike"], browser=dict(
        e["browser"], domains=[host], start_url=f"https://{host}/account"))
    e.pop("practice")
    monkeypatch.setattr(browser, "EXTRA", {"lookalike": e})
    assert browser.why_not(env["bot"], env["bot"].store.person(H), "lookalike") == "denied"


def test_the_guard_reads_the_host_the_way_the_browser_does():
    from mvp import browser_guard as G
    assert G.host("https://shop.example\\@other.example/x") == "shop.example"
    assert G.host("https://SHOP.example./a?b=1") == "shop.example"
    assert G.canon("Shop.Example:8443") == "shop.example"
    assert G.host("") == "" and G.host("not a url") == ""
