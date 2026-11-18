"""PROTOTYPE ONLY - the one seam between the bot and a browser (round 10, slice V2; DESIGN.md section 17.V; amendment
A-016, Proposed).

    host = LocalHost()                       # a headed Chromium on the machine that runs the bot (the operator's Mac)
    s = host.start(domains=("www.netflix.com",))
    s.call("goto", url); s.call("snapshot"); s.call("press", name, tag, "click", None, final_names)
    s.kill()                                 # from any thread: every Chromium process of this run ends

`Session` runs Playwright's sync API on its own worker thread (Playwright objects stay on one thread); other threads
talk to it through a queue. A fresh browser and context per run, thrown away at the end: no storage state, no cookie,
no profile and no picture is ever written (critic D-4). Every request to a host outside the route's domains is aborted
at the network level. The user agent says it is an agent (`Agent/ScrollDigest`) and `navigator.webdriver` stays true:
no captcha solving, no stealth, no proxy anywhere.

`browser_vm.VmHost` (V5) is the second implementation: headless, in the bot's own machine, with a live picture the
person can watch and take over on the test page.
"""
import base64
import os
import queue
import signal
import sys
import threading
import time

from . import browser_guard as G

AGENT_TAG = "Agent/ScrollDigest"   # the bot says what it is; nothing about automation is hidden
MAX_PRESSES = 12
MAX_SECONDS = 180                  # the bot's own time on the pages (a person's sign-in time is not counted)
LAUNCH_SECONDS = 30


class HostError(RuntimeError):
    """The browser could not start or was closed. Carries a short code only (never page text or typed text)."""


def has_screen():
    """True where a headed window can be shown: macOS and Windows always; Linux with a display."""
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def chromium_processes():
    """PIDs of the Chromium processes started under this process (Linux /proc; elsewhere an empty list). For the
    kill check and the tests: a run must leave none behind."""
    if not os.path.isdir("/proc"):
        return []
    me, kids = os.getpid(), {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat", "rb") as f:
                st = f.read().decode("utf-8", "replace")
            name = st[st.index("(") + 1:st.rindex(")")]
            parts = st[st.rindex(")") + 2:].split()
            if parts[0] == "Z":   # a zombie: already dead, only waiting to be reaped
                continue
            kids[int(d)] = (int(parts[1]), name)
        except (OSError, ValueError, IndexError):
            continue
    out = []
    for pid, (ppid, name) in kids.items():
        low = name.lower()
        if not ("chrom" in low or "headless" in low):
            continue
        p, seen = ppid, 0
        while p and p in kids and p != me and seen < 50:
            p, seen = kids[p][0], seen + 1
        if p == me:
            out.append(pid)
    return sorted(out)


def chromium_path():
    """MVP_CHROMIUM when set (a path to a Chromium or Chrome binary), else Playwright's own browser."""
    p = (os.environ.get("MVP_CHROMIUM") or "").strip()
    return p or None


class Session:
    """One run's browser. All Playwright calls happen on self.thread; other threads use call() and post()."""

    screencast = False

    def __init__(self, domains, headless=False, install=None, asset_hosts=(), viewport=(1024, 700),
                 max_presses=MAX_PRESSES, max_seconds=MAX_SECONDS, on_end=None):
        self.domains = tuple(d.lower() for d in domains)
        self.asset_hosts = tuple(h.lower() for h in asset_hosts or ())
        self.headless, self.install, self.viewport = headless, install, viewport
        self.max_presses, self.max_seconds = max_presses, max_seconds
        self.on_end = on_end
        self.q = queue.Queue()
        self.killed = threading.Event()
        self.ended = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.presses = 0
        self.refusals = 0
        self.aborted = 0                 # requests to other hosts, aborted (a count)
        self.aborted_hosts = {}          # host -> count (hosts only, never a path or a query)
        self.bot_seconds = 0.0           # the bot's own time on the pages
        self.takeover = False            # the person holds the browser: the bot presses nothing
        self.flags = 0                   # pages that carried words aimed at an assistant or hidden text
        self.frame, self.frame_no = None, 0
        self.frame_lock = threading.Condition()
        self.user_agent = ""
        self.pids = []
        self._before = set(chromium_processes())
        self.thread = threading.Thread(target=self._run, daemon=True, name="browser-session")
        self.thread.start()
        if not self.ready.wait(LAUNCH_SECONDS) or self.error:
            self.kill()
            raise HostError(self.error or "start_timeout")

    # ---------- from any thread ----------
    def call(self, *cmd, timeout=30):
        if self.killed.is_set() or self.ended.is_set():
            raise HostError("closed")
        r = queue.Queue(maxsize=1)
        self.q.put((cmd, r))
        try:
            ok, val = r.get(timeout=timeout)
        except queue.Empty:
            raise HostError("timeout") from None
        if not ok:
            raise HostError(val)
        return val

    def post(self, *cmd):
        """Fire and forget (the person's clicks and keys on the take-over view): no reply, nothing kept."""
        if not (self.killed.is_set() or self.ended.is_set()):
            self.q.put((cmd, None))

    def kill(self, wait=15):
        """Stops the run at once and ends every Chromium process it started, from any thread."""
        self.killed.set()
        self.q.put((("close",), None))
        if threading.current_thread() is not self.thread:
            self.thread.join(wait)
        for pid in self.pids:   # a process that outlived the close (never expected): ended here
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    @property
    def alive(self):
        return not (self.killed.is_set() or self.ended.is_set())

    def latest_frame(self, after, wait=2.0):
        """(number, jpeg bytes) of the newest picture, waiting up to `wait` seconds for one newer than `after`. Only
        the newest is held, in memory; none is ever written."""
        with self.frame_lock:
            if self.frame_no <= after and self.alive:
                self.frame_lock.wait(wait)
            return self.frame_no, self.frame

    # ---------- the worker thread ----------
    def _guard(self, route):
        req = route.request
        url = req.url
        if url.startswith(("data:", "blob:")):
            return route.continue_()
        h = G.host(url)
        ok = h in self.domains and not G.denied(h)
        if not ok and h in self.asset_hosts and req.resource_type != "document" and not G.denied(h):
            ok = True
        if ok:
            return route.continue_()
        self.aborted += 1
        self.aborted_hosts[h] = self.aborted_hosts.get(h, 0) + 1
        return route.abort()

    def _open(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        args = ["--disable-features=AutofillServerCommunication", "--password-store=basic", "--no-first-run"]
        self.browser = self.pw.chromium.launch(headless=self.headless, executable_path=chromium_path(), args=args)
        probe = self.browser.new_context()
        try:
            base = probe.new_page().evaluate("navigator.userAgent")
        finally:
            probe.close()
        self.user_agent = f"{base} {AGENT_TAG}"
        self.ctx = self.browser.new_context(user_agent=self.user_agent, accept_downloads=False,
                                            viewport={"width": self.viewport[0], "height": self.viewport[1]})
        if self.install is not None:
            self.install(self.ctx)          # the practice merchant (served by routing: no socket, no port)
        else:
            self.ctx.route("**/*", self._guard)
        self.page = self.ctx.new_page()
        self.ctx.on("page", lambda p: p.close())   # one tab: every page opened after this one (a pop-up) is closed
        self.pids = [p for p in chromium_processes() if p not in self._before]
        self._acks = []
        if self.screencast:
            self.cdp = self.ctx.new_cdp_session(self.page)
            self.cdp.on("Page.screencastFrame", self._on_frame)
            self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": self.viewport[0],
                                                   "maxHeight": self.viewport[1], "everyNthFrame": 1})

    def _on_frame(self, p):
        data = base64.b64decode(p["data"])
        with self.frame_lock:
            self.frame, self.frame_no = data, self.frame_no + 1
            self.frame_lock.notify_all()
        self._acks.append(p["sessionId"])

    def _close(self):
        for step in (lambda: self.ctx.close(), lambda: self.browser.close(), lambda: self.pw.stop()):
            try:
                step()
            except Exception:  # noqa: BLE001 - closing goes on whatever failed before it
                pass
        with self.frame_lock:
            self.frame = None
            self.frame_lock.notify_all()

    def _run(self):
        try:
            self._open()
        except Exception as e:  # noqa: BLE001
            self.error = "start_failed:" + type(e).__name__
            try:
                self._close()
            finally:
                self.ended.set()
                self.ready.set()
            return
        self.ready.set()
        try:
            while True:
                while self._acks:
                    try:
                        self.cdp.send("Page.screencastFrameAck", {"sessionId": self._acks.pop(0)})
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    cmd, r = self.q.get(timeout=0.02 if self.screencast else 0.2)
                except queue.Empty:
                    if self.screencast:
                        try:
                            self.page.wait_for_timeout(15)   # lets Playwright deliver the screencast's events
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                if cmd[0] == "close" or self.killed.is_set():
                    if r:
                        r.put((False, "closed"))
                    break
                try:
                    val = getattr(self, "_c_" + cmd[0])(*cmd[1:])
                    if r:
                        r.put((True, val))
                except Exception as e:  # noqa: BLE001 - the error is a class name only: never typed text
                    if r:
                        r.put((False, "error:" + type(e).__name__))
        finally:
            self._close()
            while True:
                try:
                    _, r = self.q.get_nowait()
                except queue.Empty:
                    break
                if r:
                    r.put((False, "closed"))
            self.ended.set()
            if self.on_end:
                try:
                    self.on_end(self)
                except Exception:  # noqa: BLE001
                    pass

    # ---------- commands (worker thread) ----------
    def _c_goto(self, url):
        h = G.host(url)
        if h not in self.domains or G.denied(h):
            raise ValueError("host")
        t0 = time.monotonic()
        self.page.goto(url, wait_until="domcontentloaded")
        self.bot_seconds += time.monotonic() - t0
        return True

    def _c_snapshot(self):
        snap = self.page.evaluate(G.SNAPSHOT_JS)
        if G.flagged(snap):
            self.flags += 1
        return snap

    def _c_press(self, name, tag, action, yes_hash, final_names):
        """The one way the bot presses: on a fresh snapshot, exactly one element with this name and tag; code's
        `allowed()` must pass; a press on the last step needs the hash the person said yes to. Returns
        {"did": name} or {"refused": reason, "hash": ...}."""
        if self.takeover:
            return {"refused": "the person has the browser"}
        if self.presses >= self.max_presses or self.bot_seconds > self.max_seconds:
            return {"refused": "limit"}
        t0 = time.monotonic()
        snap = self._c_snapshot()
        st = G.page_state(snap, self.domains, final_names)
        if st in G.WALLS:
            return {"refused": "wall:" + st}
        hits = [e for e in snap["elements"] if e["name"] == name and e["tag"] == tag]
        if len(hits) != 1:
            return {"refused": "not one element"}
        el = hits[0]
        ok, why = G.allowed(el, action, self.domains, snap, final_names)
        if not ok:
            self.refusals += 1
            return {"refused": why}
        if action == "confirmed_click":
            now_hash = G.el_hash(snap, el)
            if not yes_hash or now_hash != yes_hash:
                return {"refused": "page_changed", "hash": now_hash}
        sel = f'[data-sd-id="{el["id"]}"]'
        if el["tag"] == "input" and el["type"] == "radio":
            self.page.check(sel, timeout=5000)
        else:
            self.page.click(sel, timeout=5000)
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: BLE001 - a page that does not navigate is fine
            pass
        self.presses += 1
        self.bot_seconds += time.monotonic() - t0
        return {"did": name}

    def _c_takeover(self, on):
        self.takeover = bool(on)
        return True

    def _c_identity(self):
        return self.page.evaluate("({ua: navigator.userAgent, webdriver: navigator.webdriver})")

    # the person's input on the take-over view (only while they hold it); nothing here is logged, kept or returned
    def _c_view_click(self, x, y):
        if self.takeover:
            self.page.mouse.click(float(x), float(y))

    def _c_view_text(self, s):
        if self.takeover:
            self.page.keyboard.insert_text(s)

    def _c_view_key(self, k):
        if self.takeover and k in ("Enter", "Backspace", "Tab", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
                                   "Escape", "Delete", "Home", "End"):
            self.page.keyboard.press(k)

    def _c_view_scroll(self, dy):
        if self.takeover:
            self.page.mouse.wheel(0, max(-2000, min(2000, int(dy))))


class Host:
    """The seam: start(domains, ...) -> Session; available() -> (ok, reason code)."""
    kind = "none"
    session_class = Session

    def available(self):
        return False, "no_host"

    def start(self, domains, install=None, asset_hosts=(), on_end=None):
        raise HostError("no_host")


class LocalHost(Host):
    """A headed Chromium on the machine that runs the bot: the person signs in there, in the window, themselves.
    No screen (a container, an SSH session): not available. `headless` and `screen` are for tests only."""
    kind = "local"

    def __init__(self, headless=False, screen=None):
        self.headless = headless
        self.screen = screen

    def available(self):
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False, "no_playwright"
        screen = self.screen() if callable(self.screen) else has_screen()
        if not screen and not self.headless:
            return False, "no_screen"
        return True, "ok"

    def start(self, domains, install=None, asset_hosts=(), on_end=None):
        return self.session_class(domains, headless=self.headless, install=install, asset_hosts=asset_hosts,
                                  on_end=on_end)
