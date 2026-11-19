"""PROTOTYPE ONLY - the browser that cancels for the person (round 10, slice V3 and V4; DESIGN.md section 17.V; amendment
A-016, Proposed). Off unless MVP_BROWSER is set; never from a rule or a model form; no model in the loop.

    MVP_BROWSER=operator     a headed browser window on the computer that runs the bot (browser_host.LocalHost)
    MVP_BROWSER=vm           a browser inside the bot's machine that the person watches and takes over on the test
                             page at /vm (browser_vm.VmHost, addendum V5)
    MVP_BROWSER_MERCHANTS    the merchants it may open, by key ("netflix,spotify"); none by default
    MVP_BROWSER_FOR=all      (vm only) testers too; by default only the operator
    MVP_BROWSER_DEMO=1       the practice merchant "Streamly" (the tests' fake site, served by routing, no port)

The conversation (word for word in texts.py, "round 10, slice V"): the cancel helper's web route offers it ("Say "do
it for me""); the first time for a site the person says "allow <merchant>" after the warning; the browser opens and the
person signs in themselves; on "I'm in" the bot follows the merchant's own path by exact names (FlowRunner, version 1:
no model) and stops before the last button with that page's own words; only "yes cancel <merchant>" presses it, bound
to a hash of that exact page (actions/browser.py, the registry's yes token); the bot then quotes what the page says
and offers a check reminder. The bot's own words never say the subscription ended. "stop" closes everything.

State `browserrun:<handle>` (30 minutes at most); tables `site_grants` and `browser_runs` (store.py). Nothing typed,
no cookie, no picture and no page text beyond the merchant's one quoted sentence (at most 200 characters) is kept.
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import browser_guard as G
from . import texts as T

ROUTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_routes.json")
RUN_MINUTES = 30          # a run's state ends this long after it started
YES_MINUTES = 10          # the last page waits this long for "yes cancel <merchant>"
HANDBACK_MINUTES = 10     # after a hand-back the window stays open this long for the person
RUNS_PER_DAY = 3
WARNING_VERSION = 1
REASON_PREF = ("prefer not to say", "other", "i don't use it", "too expensive")
NEXT_ONLY = ("offered", "permission", "reminder")   # steps answered by the next message only

# ---------- the words read while a run is open (the original text, never a normalised one: W-2) ----------
STOP = re.compile(r"^\W*(?:(?:please|no|ok|okay)[\s,!.]+)?(?:stop|stop it|stop that|stop now|stop everything|"
                  r"stop the browser|cancel that|kill it|don'?t|do not|abort|close it|close the browser|halt)"
                  r"(?:\s+please)?\W*$", re.I)
IM_IN = re.compile(r"^\W*(?:(?:ok(?:ay)?|yes|yep|right|done)[\s,!.]+)?(?:i'?m in|im in|i am in|i'?m signed in|"
                   r"i am signed in|signed in|i'?m logged in|logged in|i'?m done|i am done|done|go on|carry on|"
                   r"continue|ready|i did it|did it)(?:\s+now)?\W*$", re.I)
DO_IT = re.compile(r"^\W*(?:(?:yes|yep|yeah|ok|okay|sure|please)[\s,!.]*)*(?:do it for me|cancel it for me|"
                   r"you do it|do it|go ahead|please do|yes please|yes|yep|yeah|ok|okay|sure)(?:\s+please)?\W*$", re.I)
STEPS = re.compile(r"^\W*(?:(?:no|ok|okay)[\s,]+)?(?:steps|the steps|show me the steps|give me the steps|tell me how|"
                   r"how do i do it(?: myself)?|i'?ll do it(?: myself)?|myself|i'?ll do it myself)\W*$", re.I)
NO_THANKS = re.compile(r"^\W*(?:no|nope|nah|no thanks|no thank you|never ?mind|forget it|not now|leave it)\W*$", re.I)
ALLOW = re.compile(r"^\W*allow\s+(.{2,40}?)\W*$", re.I)
YES_CANCEL = re.compile(r"^\W*yes,?\s+cancel\s+(?:my\s+)?(.{2,40}?)(?:\s+now)?\W*$", re.I)
STATUS = re.compile(r"^\W*(?:what'?s happening|what is happening|what are you doing|status|where are you|"
                    r"how'?s it going|what now)\W*$", re.I)
REVOKE = re.compile(r"^\W*(?:please\s+)?stop acting on\s+(?:my\s+)?(.{2,40}?)\W*$", re.I)
# the live check of 19 Nov (DESIGN.md section 17.L, F1): a bare "I'm in" with no place name, read whatever the run's
# step; it never reaches the model, which read it as a move to New York time
SIGNED_IN = re.compile(r"^\W*(?:(?:ok(?:ay)?|yes|yep|right|so|alright|done)[\s,!.]+)?(?:(?:i'?m|im|i am)\s+(?:in|"
                       r"signed\s+in|logged\s+in)|(?:signed|logged)\s+in|i'?ve\s+(?:signed|logged)\s+in|"
                       r"i\s+(?:signed|logged)\s+in)(?:\s+now)?\W*$", re.I)
NOT_TAKEN = re.compile(r"\d|\b(?:rules?|reminders?|nudges?|lists?|to-?dos?|digest|recap|texts?|messages?|picks?)\b",
                       re.I)


# ---------- settings ----------
def mode():
    """'operator', 'vm' or 'off' (MVP_BROWSER)."""
    m = (os.environ.get("MVP_BROWSER") or "").strip().lower()
    return m if m in ("operator", "vm") else "off"


def demo():
    """MVP_BROWSER_DEMO=1 with the browser on: the practice merchant "Streamly" is known."""
    return (os.environ.get("MVP_BROWSER_DEMO") or "").strip() == "1" and mode() != "off"


def practice_routes():
    """The route file with the practice merchant when the demo is on (the cancel helper's request read), else None
    (the helper reads its own file, as before)."""
    return cancel_routes() if demo() or EXTRA else None


def merchants():
    keys = {k.strip().lower() for k in (os.environ.get("MVP_BROWSER_MERCHANTS") or "").split(",") if k.strip()}
    if demo():
        keys.add("streamly")
    return keys


def for_all():
    return mode() == "vm" and (os.environ.get("MVP_BROWSER_FOR") or "").strip().lower() == "all"


# ---------- routes ----------
def practice_entry(flow=5):
    """The practice merchant of MVP_BROWSER_DEMO=1 as a cancel_routes.json entry plus its browser block. Flow 5: a
    sign-in page first (the person signs in through the take-over view), then the plain way out."""
    from .tests.fakes import fake_merchant as M
    path, finals = M.PATHS[flow]
    return {"key": "streamly", "name": M.MERCHANT, "names": ["streamly"], "route": "web", "url": None,
            "steps": ["Open the Streamly practice page on the test page.", "Press \"Cancel membership\".",
                      "Press \"Finish Cancellation\"."], "billed_via": ["web"], "notice_email": None, "phone": None,
            "source_url": "practice", "checked_on": "2026-11-17", "practice": True,
            "browser": {"start_url": M.start(flow), "path": list(path), "final_names": list(finals),
                        "domains": list(M.DOMAINS), "asset_hosts": [], "outcome_phrases": []}}


# tests put more practice routes here ({key: entry}); the merchant's flow is chosen by its start URL
EXTRA = {}


def cancel_routes():
    """The cancel helper's route file, with the practice merchant when the demo is on."""
    from .cancel import load_routes
    routes = load_routes()
    extra = dict(EXTRA)
    if demo() and "streamly" not in extra:
        extra["streamly"] = practice_entry()
    if extra:
        routes = dict(routes, merchants=list(routes["merchants"]) + list(extra.values()))
    return routes


def route(key):
    """The browser route of a merchant: its cancel entry (name, names, steps, url) with the browser block (start_url,
    path, final_names, domains, asset_hosts, outcome_phrases); domains and final_names from cancel_routes.json win
    when that file has them. None when the merchant has no browser block."""
    e = next((m for m in cancel_routes()["merchants"] if m.get("key") == key), None)
    if e is None:
        return None
    b = dict(e.get("browser") or {})
    if not b:
        try:
            with open(ROUTES_PATH, encoding="utf-8") as f:
                b = dict(json.load(f)["merchants"].get(key) or {})
        except (OSError, ValueError, KeyError):
            b = {}
    if not b:
        return None
    for k in ("domains", "final_names"):
        if e.get(k):
            b[k] = list(e[k])
    return dict(e, **{k: b.get(k) for k in ("start_url", "path", "final_names", "domains", "asset_hosts",
                                            "outcome_phrases")})


def site_label(r):
    """'netflix.com' for the warning line."""
    d = (r.get("domains") or [""])[0]
    return d[4:] if d.startswith("www.") else d


def _complete(r):
    return bool(r and r.get("start_url") and isinstance(r.get("path"), list) and r.get("final_names")
                and r.get("domains"))


def is_denied(r):
    """A route on a denied site, or (checks of round 10) on a bare IP address, which could be any site at all: a
    merchant's route names the merchant's own hosts."""
    hosts = [G.canon(d) for d in (r or {}).get("domains") or []] + [G.host((r or {}).get("start_url") or "")]
    return any(G.denied(h) or _ip(h) for h in hosts if h)


def _ip(h):
    import ipaddress
    try:
        ipaddress.ip_address(h.strip("[]"))
        return True
    except ValueError:
        return False


# ---------- who may see it ----------
def make_host(m):
    """The host for a mode (tests replace this with a headless LocalHost)."""
    if m == "vm":
        from .browser_vm import VmHost
        return VmHost()
    from .browser_host import LocalHost
    return LocalHost()


def person_ok(handle):
    """Who may have the browser: with it on, the operator; with MVP_BROWSER=vm and MVP_BROWSER_FOR=all, anyone."""
    from . import config
    return mode() != "off" and (config.is_operator(handle) or for_all())


def why_not(bot, person, merchant_key):
    """'ok', or why the browser is not offered: off | person | merchant | route | denied | channel | no_screen |
    no_playwright."""
    m = mode()
    if m == "off":
        return "off"
    if not person_ok(person["handle"]):
        return "person"
    if (merchant_key or "").lower() not in merchants():
        return "merchant"
    r = route(merchant_key)
    if is_denied(r):
        return "denied"
    if not _complete(r):
        return "route"
    if m == "vm" and getattr(getattr(bot, "channel", None), "name", "") != "web":
        return "channel"
    ok, why = make_host(m).available()
    return "ok" if ok else why


def available(bot, person, merchant_key):
    """True when the bot may offer to cancel this merchant in a browser for this person."""
    try:
        return why_not(bot, person, merchant_key) == "ok"
    except Exception:  # noqa: BLE001 - the offer never breaks the cancel helper
        return False


def run_open(store, handle, now=None):
    """True while this person's browser run (or its offer) is open: at most 30 minutes."""
    if store is None:
        return False
    st = store.get_state(f"browserrun:{handle}")
    if not st:
        return False
    from datetime import timezone
    now = now or datetime.now(timezone.utc)
    return datetime.fromisoformat(st["started"]) > now - timedelta(minutes=RUN_MINUTES)


# ---------- the sessions of this process ----------
def _sessions(bot):
    if not hasattr(bot, "_browser"):
        bot._browser = {"lock": threading.Lock(), "runs": {}, "threads": {}, "timers": []}
        import atexit
        atexit.register(close_all, bot)   # the bot stops: every browser it opened is closed
    return bot._browser


def session_of(bot, handle, run_id):
    run = _sessions(bot)["runs"].get(handle)
    return run["session"] if run and run["run_id"] == run_id and run["session"].alive else None


def wait(bot, handle, timeout=60):
    """Waits for this person's background walk to finish (tests, and the self-test)."""
    t = _sessions(bot)["threads"].get(handle)
    if t is not None:
        t.join(timeout)
    return t is None or not t.is_alive()


def close_all(bot):
    """Ends every open browser of this bot (at shutdown, and in tests)."""
    b = _sessions(bot)
    for h in list(b["runs"]):
        _end_session(bot, h)
    for t in list(b["timers"]):
        t.cancel()


def _end_session(bot, handle):
    b = _sessions(bot)
    with b["lock"]:
        run = b["runs"].pop(handle, None)
    if run is not None:
        run["session"].kill()
        try:
            from . import browser_vm
            browser_vm.drop_views(run["run_id"])
        except Exception:  # noqa: BLE001
            pass


class FlowRunner:
    """Version 1: code follows the merchant's own path by exact names, stops at walls, finds the one last button.
    No model; page text never chooses anything. `walk()` goes from the page the browser is on now."""

    def __init__(self, session, r):
        self.s, self.r = session, r
        self.path = list(r.get("path") or [])
        self.finals = list(r.get("final_names") or [])
        self.domains = tuple(r.get("domains") or ())

    def walk(self):
        while True:
            if not self.s.alive:
                return {"status": "stopped"}
            snap = self.s.call("snapshot")
            st = G.page_state(snap, self.domains, self.finals)
            if st in G.WALLS:
                return {"status": st}
            if st == "kept":
                return {"status": "offer_taken"}
            if st == "outcome_ok":
                return {"status": "page_says_cancelled", "quote": G.outcome_quote(snap["text"],
                                                                                 self.r.get("outcome_phrases"))}
            if self.s.presses >= self.s.max_presses or self.s.bot_seconds > self.s.max_seconds:
                return {"status": "limit"}
            if self.path:
                want = self.path[0]
                if want == "@reason":
                    radios = {e["name"].lower(): e for e in snap["elements"] if e["tag"] == "input"
                              and e["type"] == "radio"}
                    el = next((radios[k] for k in REASON_PREF if k in radios), None)
                else:
                    hits = [e for e in snap["elements"] if e["name"].lower() == want.lower()]
                    el = hits[0] if len(hits) == 1 else None
                if el is None:
                    return {"status": "lost"}
                ok, why = G.allowed(el, "click", self.domains, snap, self.finals)
                if not ok:
                    return {"status": "refused", "why": why}
                got = self.s.call("press", el["name"], el["tag"], "click", None, self.finals)
                if "refused" in got:
                    why = got["refused"]
                    if why.startswith("wall:"):
                        continue   # the next snapshot names the wall
                    if why == "the person has the browser":
                        return {"status": "person_has_it"}
                    return {"status": "limit" if why == "limit" else "refused", "why": why}
                self.path.pop(0)
                continue
            cands = [e for e in snap["elements"] if G.is_final(e, snap, self.finals)
                     and G.allowed(e, "confirmed_click", self.domains, snap, self.finals)[0]]
            if len(cands) != 1:
                return {"status": "lost" if not cands else "unclear"}
            el = cands[0]
            return {"status": "final_shown", "name": el["name"], "tag": el["tag"], "hash": G.el_hash(snap, el),
                    "quote": G.effects_quote(snap["text"])}


def final_card(r, found):
    return T.browser_final(r["name"], found.get("quote") or "", found["name"], yes_word(r))


def yes_word(r):
    return f"yes cancel {r['name'].lower()}"


def _names_of(r):
    return {r["name"].lower(), r["key"].lower().replace("_", " "), *(n.lower() for n in r.get("names") or [])}


def names_match(r, said):
    s = " ".join((said or "").lower().split()).strip(" .!")
    return s in _names_of(r)


class BrowserMixin:
    """The conversation around one run. Every reply is code-written; the merchant's words appear only in quotes."""

    # ---------- the offer: the cancel helper's web route (cancel.py, the slice V block) ----------
    def browser_offer(self, person, e, now):
        """Row 2: instead of the steps, the offer. The next message answers it ("do it for me", "steps", "no")."""
        h = person["handle"]
        r = route(e["key"])
        self.note(intent="cancel")
        self._browser_state(h, {"step": "offered", "key": e["key"], "name": r["name"], "at": _iso(now),
                                "started": _iso(now)})
        return self.send(h, T.browser_offer(r["name"], vm=mode() == "vm", practice=bool(r.get("practice"))))

    def browser_note(self, person, e):
        """A line said before the steps when the browser is on for this person but cannot be used for this merchant
        (a denied site, the wrong channel, no screen). "" otherwise."""
        try:
            why = why_not(self, person, e["key"])
        except Exception:  # noqa: BLE001
            return ""
        if why == "denied":
            return T.browser_denied(e["name"], youtube=e["key"].startswith("youtube")) + "\n"
        if why == "channel":
            return T.BROWSER_PAGE_ONLY + "\n"
        if why == "no_screen":
            return T.BROWSER_NO_SCREEN + "\n"
        return ""

    def browser_not_for(self, person, e):
        """The live check of 19 Nov (F3): with the browser on for this person but not for this merchant, why, in plain
        words ("switch": its path was never tried on the real site, so it is not switched on; "unchecked": it has no
        checked path). None otherwise: the browser off, someone it is not for, or a merchant it can do (today's
        lines, byte-equal)."""
        try:
            if mode() == "off" or not person_ok(person["handle"]):
                return None
            why = why_not(self, person, e["key"])
            if why not in ("merchant", "route"):
                return None
            r = route(e["key"])
            kind = "switch" if why == "merchant" and _complete(r) and not is_denied(r) else "unchecked"
        except Exception:  # noqa: BLE001 - the steps never break on the browser
            return None
        from . import config
        return T.browser_not_for(e["name"], kind, operator=config.is_operator(person["handle"]))

    def browser_password(self, person, text):
        """The password line where the browser is on for this person and the merchant they name; it opens the offer,
        so "do it for me" goes on from there. None for everyone else (today's line)."""
        from .cancel import merchant_in
        e = merchant_in(text, cancel_routes())
        if e is None or not available(self, person, e["key"]):
            return None
        now = self.clock()
        h = person["handle"]
        st = self.store.get_state(f"browserrun:{h}") or {}
        if not st.get("run_id"):   # an open run is never replaced by an offer
            self._browser_state(h, {"step": "offered", "key": e["key"], "name": e["name"], "at": _iso(now),
                                    "started": _iso(now)})
        return T.browser_password(e["name"], vm=mode() == "vm")

    # ---------- the hook: handler._on_message, right after secret_reads ----------
    def browser_reads(self, person, text, now):
        h = person["handle"]
        t = " ".join((text or "").split())
        if not t or len(t) > 200:
            return None
        m = REVOKE.match(t)
        if m:
            ref = self._browser_revoke(person, m.group(1), now)
            if ref is not None:
                return ref
        st = self.store.get_state(f"browserrun:{h}")
        if not st:
            return self._signed_in_nothing(person, t, now)   # the live check of 19 Nov (F1)
        if datetime.fromisoformat(st["started"]) < now - timedelta(minutes=RUN_MINUTES):
            self._browser_close(h, st, "limit", now, say=None)
            return self._signed_in_nothing(person, t, now)
        step = st["step"]
        r = route(st["key"])
        if r is None:
            self._browser_state(h, None)
            return self._signed_in_nothing(person, t, now)
        if step in NEXT_ONLY:
            if SIGNED_IN.match(t):   # F1: nothing is open to sign in to yet (or any more); the question stays
                self.note(intent="browser")
                return self.send(h, T.SIGNED_IN_NOTHING)
            return self._browser_next(person, st, r, t, now)
        if STOP.match(t) and not NOT_TAKEN.search(t):
            return self._browser_stop(person, st, now)
        if STATUS.match(t):
            self.note(intent="browser")
            return self.send(h, T.browser_status(step, r["name"], yes_word(r)))
        if step == "walking":
            if IM_IN.match(t):
                self.note(intent="browser")
                return self.send(h, T.browser_status("walking", r["name"], yes_word(r)))
            return None
        if step in ("opened", "wall"):
            if IM_IN.match(t):
                return self._browser_go_on(person, st, r, now)
            return None
        if step == "final_shown":
            if datetime.fromisoformat(st["at"]) < now - timedelta(minutes=YES_MINUTES):
                self._browser_close(h, st, "no_answer", now, say=None)
                self._browser_state(h, {"step": "offered", "key": st["key"], "name": st["name"], "at": _iso(now),
                                        "started": _iso(now)})
                self.note(intent="browser")
                return self.send(h, T.BROWSER_NO_ANSWER)
            m = YES_CANCEL.match(t)
            if m and names_match(r, m.group(1)):
                return self._browser_press(person, st, r, now)
            if m or DO_IT.match(t) or t in ("👍",):
                self.note(intent="browser")
                return self.send(h, T.browser_plain_yes(yes_word(r)))
            if SIGNED_IN.match(t):   # the live check of 19 Nov (F1): the last step again, word for word
                self.note(intent="browser")
                return self.send(h, final_card(r, {"name": st.get("final_name") or "", "quote": st.get("final_quote")}))
            return None
        if step == "handed_back":
            if SIGNED_IN.match(t):   # F1: the browser is the person's; never the model
                self.note(intent="browser")
                return self.send(h, T.browser_status("handed_back", r["name"], yes_word(r)))
            return None
        return None

    def _signed_in_nothing(self, person, t, now):
        """The live check of 19 Nov (F1): "I'm in", "ok im signed in", "logged in" with no browser run that takes it:
        one plain line, never a time zone. While a YouTube code or an app's sign-in page waits, that one answers."""
        if not SIGNED_IN.match(t):
            return None
        h = person["handle"]
        from . import yt_auth
        if yt_auth.waiting(self.store, h, now):
            from . import ytreads
            self.note(intent="youtube")
            return ytreads._poll_now(self, person, now)
        waiting = self.store.get_state(f"oauthpending:{h}")
        if waiting:
            from . import oauth
            from .connectors import CONNECTORS
            con = CONNECTORS.get(waiting.get("connector") or "")
            if con is not None and oauth.pending(h):
                self.note(intent="places")
                return self.send(h, T.signed_in_app_wait(con.apps.get("todo") or con.name))
        self.note(intent="signed_in")
        return self.send(h, T.SIGNED_IN_NOTHING)

    def _browser_next(self, person, st, r, t, now):
        """The next message after the offer, the permission question or the reminder offer."""
        h = person["handle"]
        step = st["step"]
        if step == "reminder":
            return self._browser_reminder_answer(person, st, r, t, now)
        if NO_THANKS.match(t) or (STOP.match(t) and not NOT_TAKEN.search(t)):
            self._browser_state(h, None)
            self.note(intent="cancel")
            return self.send(h, T.CANCEL_LEFT)
        if step == "offered":
            if STEPS.match(t):
                self._browser_state(h, None)
                return self._browser_steps_reply(person, r, now)
            if DO_IT.match(t):
                if self.store.site_grant(h, r["key"]) is None:
                    self._browser_state(h, dict(st, step="permission", at=_iso(now)))
                    self.note(intent="browser")
                    return self.send(h, T.browser_permission(r["name"], site_label(r), r["name"].lower(),
                                                             vm=mode() == "vm", practice=bool(r.get("practice"))))
                return self._browser_start(person, st, r, now)
            self._browser_state(h, None)
            return None
        if step == "permission":
            m = ALLOW.match(t)
            if m and names_match(r, m.group(1)):
                self.store.add_site_grant(h, r["key"], WARNING_VERSION, at=now)
                self.store.log_action(h, None, None, "browser.grant", "done", detail={"site": r["key"]}, at=now)
                return self._browser_start(person, st, r, now)
            if m or DO_IT.match(t):
                self.note(intent="browser")
                return self.send(h, T.browser_allow_hint(r["name"].lower()))
            self._browser_state(h, None)
            return None
        return None

    def _browser_steps_reply(self, person, r, now):
        """"steps": today's reply of the cancel helper (the steps, the check-reminder offer)."""
        from .cancel import load_routes
        e = next((m for m in cancel_routes()["merchants"] if m["key"] == r["key"]), None) or r
        self._tl.browser_steps = True
        try:
            if e["key"] not in {m["key"] for m in load_routes()["merchants"]}:
                self.note(intent="cancel")
                return self.send(person["handle"], self._browser_steps_text(r, now, head=T.browser_steps_head(r["name"])))
            return self._cancel_entry(person, e, now)
        finally:
            self._tl.browser_steps = False

    def _browser_steps_text(self, r, now, head=None):
        """The numbered steps from the merchant's own help page (the link only while its check is fresh)."""
        from .cancel import checked_words, link_fresh
        today = now.astimezone(ZoneInfo("UTC")).date()
        steps = list(r.get("steps") or [])
        if steps and r.get("url") and link_fresh(r.get("checked_on"), today):
            steps[0] = f"Open {r['url']} and sign in if it asks."
        lines = [head] if head else []
        lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        if steps and r.get("checked_on") and r.get("source_url") not in (None, "practice"):
            lines.append(f"(From {r['name']}'s help page, checked {checked_words(r['checked_on'])}.)")
        return "\n".join(lines)

    # ---------- the run ----------
    def _browser_start(self, person, st, r, now):
        """Row 6: the browser opens at the merchant's start page; the person signs in themselves, then "I'm in"."""
        h = person["handle"]
        self.note(intent="browser")
        why = why_not(self, person, r["key"])
        if why != "ok":
            self._browser_state(h, None)
            note = {"denied": T.browser_denied(r["name"], youtube=r["key"].startswith("youtube")),
                    "channel": T.BROWSER_PAGE_ONLY, "no_screen": T.BROWSER_NO_SCREEN}.get(why, T.BROWSER_CANT_START)
            return self.send(h, self._browser_steps_text(r, now, head=note + " " + T.BROWSER_YOURSELF))
        from .store import now_iso
        from .actions import local_day_bounds
        start, end = local_day_bounds(now, person["timezone"])
        if self.store.browser_runs_between(h, now_iso(start), now_iso(end)) >= RUNS_PER_DAY:
            self._browser_state(h, None)
            return self.send(h, self._browser_steps_text(r, now, head=T.browser_runs_cap(RUNS_PER_DAY)))
        _end_session(self, h)
        m = mode()
        host = make_host(m)
        install = None
        from .tests.fakes import fake_merchant as M
        if G.host(r["start_url"]) in M.DOMAINS:   # the practice site (a reserved .example name) is served by the fake
            flow = int(re.search(r"/f(\d)/", r["start_url"]).group(1))
            install = (lambda ctx, _f=flow: M.install(ctx, signed_in=(_f != 5)))
        cid = self.store.add_cancellation(h, r["key"], "web", "browser_opened", at=now)
        self.store.log_action(h, None, None, "cancel.help", "done", detail={"route": "web", "known": True}, at=now)
        run_id = self.store.add_browser_run(h, r["key"], cid, host.kind, at=now)
        s = None
        try:
            s = host.start(r["domains"], install=install, asset_hosts=r.get("asset_hosts") or ())
            s.call("goto", r["start_url"], timeout=45)
        except Exception as e:  # noqa: BLE001 - a code only; never a page's words
            if s is not None:
                s.kill()
            self.store.end_browser_run(run_id, "stopped", at=now)
            self._cancel_update(cid, status="handed_back", now=now)
            self._browser_state(h, None)
            self.store.log_action(h, None, None, "browser.open", "failed", detail={"host": host.kind,
                                                                                   "error": type(e).__name__}, at=now)
            return self.send(h, self._browser_steps_text(r, now, head=T.BROWSER_CANT_START + " " + T.BROWSER_YOURSELF))
        b = _sessions(self)
        with b["lock"]:
            b["runs"][h] = {"run_id": run_id, "session": s, "runner": FlowRunner(s, r), "walls": {}}
        self.store.log_action(h, None, None, "browser.open", "done", detail={"host": host.kind}, at=now)
        link = None
        if m == "vm":
            from . import browser_vm
            link = browser_vm.open_view(self, h, run_id, s)
            s.call("takeover", True)   # the person holds it while they sign in
        self._browser_state(h, {"step": "opened", "key": r["key"], "name": r["name"], "at": _iso(now),
                                "started": _iso(now), "run_id": run_id, "cid": cid, "link": link})
        self._browser_timer(h, run_id, RUN_MINUTES * 60, "limit")
        return self.send(h, T.browser_opening(r["name"], link))

    def _browser_go_on(self, person, st, r, now):
        """Row 9: "I'm in". The person hands the browser back; the bot walks in the background."""
        h = person["handle"]
        run = _sessions(self)["runs"].get(h)
        if run is None or run["run_id"] != st.get("run_id") or not run["session"].alive:
            self._browser_state(h, None)
            return None
        self.note(intent="browser")
        try:
            run["session"].call("takeover", False)
        except Exception:  # noqa: BLE001
            pass
        self._browser_state(h, dict(st, step="walking", at=_iso(now)))
        ref = self.send(h, T.BROWSER_GOING)
        self._browser_spawn(h, st["run_id"])
        return ref

    def _browser_spawn(self, h, run_id):
        b = _sessions(self)
        t = threading.Thread(target=self._browser_walk, args=(h, run_id), daemon=True, name="browser-walk")
        b["threads"][h] = t
        t.start()

    def _browser_walk(self, h, run_id):
        """The background walk: its result is said under the person's lock, unless they stopped it meanwhile."""
        b = _sessions(self)
        run = b["runs"].get(h)
        if run is None or run["run_id"] != run_id:
            return
        try:
            found = run["runner"].walk()
        except Exception as e:  # noqa: BLE001
            found = {"status": "stopped" if not run["session"].alive else "refused", "why": type(e).__name__}
        with self.lock_for(h):
            st = self.store.get_state(f"browserrun:{h}")
            if not st or st.get("run_id") != run_id or st["step"] != "walking":
                return   # stopped by the person meanwhile: nothing more is said
            self._browser_result(h, st, found, self.clock())

    def _browser_result(self, h, st, found, now):
        r = route(st["key"])
        run = _sessions(self)["runs"].get(h)
        status = found["status"]
        name = r["name"]
        if status == "final_shown":
            self.store.update_browser_run(st["run_id"], status="final_shown", final_name=found["name"][:80],
                                          final_hash=found["hash"])
            self._cancel_update(st["cid"], status="final_shown", now=now)
            self.store.log_action(h, None, None, "browser.final_shown", "done", detail={"hash": found["hash"][:12]},
                                  at=now)
            self._browser_state(h, dict(st, step="final_shown", at=_iso(now), yes_hash=found["hash"],
                                        final_name=found["name"], final_tag=found["tag"],
                                        final_quote=found.get("quote") or ""))   # F1: the card said again
            self._browser_timer(h, st["run_id"], YES_MINUTES * 60, "no_answer")
            return self.send(h, final_card(r, found))
        if status in ("login_wall", "captcha", "otp"):
            walls = run["walls"] if run else {}
            walls[status] = walls.get(status, 0) + 1
            self.store.update_browser_run(st["run_id"], walls=sum(walls.values()))
            self.store.log_action(h, None, None, "browser.wall", "done", detail={"kind": status}, at=now)
            if walls[status] >= 2:
                self._browser_close(h, st, "handed_back", now, say=None)
                return self.send(h, self._browser_steps_text(r, now, head=T.browser_keeps_stopping(name)))
            if st.get("link") and run:
                try:
                    run["session"].call("takeover", True)
                except Exception:  # noqa: BLE001
                    pass
            self._browser_state(h, dict(st, step="wall", at=_iso(now)))
            return self.send(h, T.browser_wall(status, name, st.get("link")))
        if status == "page_says_cancelled":
            return self._browser_outcome(h, st, r, {"page": "outcome_ok", "quote": found.get("quote")}, now)
        if status == "offer_taken":
            return self._browser_outcome(h, st, r, {"page": "kept"}, now)
        if status == "off_site":
            self._browser_close(h, st, "stopped", now, say=None)
            return self.send(h, self._browser_steps_text(r, now, head=T.browser_off_site(name)))
        if status == "limit":
            self._browser_close(h, st, "limit", now, say=None)
            return self.send(h, self._browser_steps_text(r, now, head=T.BROWSER_LIMIT))
        if status == "person_has_it":
            self._browser_state(h, dict(st, step="wall", at=_iso(now)))
            return self.send(h, T.browser_person_has_it(st.get("link")))
        if status == "stopped":
            self._browser_state(h, None)
            return None
        # lost, unclear, refused: hand back; the window stays open for the person for 10 minutes
        if found.get("why"):
            self.store.log_action(h, None, None, "browser.refused", "done", detail={"reason": status}, at=now)
        self.store.update_browser_run(st["run_id"], status="handed_back")
        self._cancel_update(st["cid"], status="handed_back", now=now)
        if st.get("link") and run:
            try:
                run["session"].call("takeover", True)
            except Exception:  # noqa: BLE001
                pass
        self._browser_state(h, dict(st, step="handed_back", at=_iso(now)))
        self._browser_timer(h, st["run_id"], HANDBACK_MINUTES * 60, "handed_back")
        return self.send(h, self._browser_steps_text(r, now, head=T.browser_lost(name, st.get("link"))))

    def _browser_press(self, person, st, r, now):
        """Row 13: "yes cancel <merchant>" presses exactly the button shown, on exactly that page, through the
        registry (the yes token is the page's hash now; a changed page is shown again and nothing is pressed)."""
        from .actions import Refused, perform
        from .actions.base import Ctx
        h = person["handle"]
        self.note(intent="browser")
        if session_of(self, h, st.get("run_id")) is None:
            self._browser_state(h, None)
            return self.send(h, T.BROWSER_GONE)
        ctx = Ctx(bot=self, person=person, answer={}, picks=[], kind="manual", now=now, tz=person["timezone"])
        params = {"run_id": st["run_id"], "yes_hash": st["yes_hash"]}
        try:
            out = perform("browser.cancel", ctx, params, yes_token=st["yes_hash"])
        except Refused:   # the page now is not the page the yes was for (or the browser has gone)
            if session_of(self, h, st.get("run_id")) is None:
                self._browser_close(h, st, "stopped", now)
                return self.send(h, T.BROWSER_GONE)
            return self._browser_changed(person, st, r, now)
        if out.status == "skipped" and (out.detail or {}).get("cap"):
            self._browser_close(h, st, "limit", now, say=None)
            return self.send(h, out.line)
        if out.status != "done":
            why = (out.detail or {}).get("refused") or ""
            if why == "the person has the browser":
                return self.send(h, T.browser_held(yes_word(r)))
            return self._browser_changed(person, st, r, now)
        self.store.log_action(h, None, None, "browser.cancel", "done", detail={"hash": st["yes_hash"][:12]}, at=now)
        self.store.update_browser_run(st["run_id"], status="final_pressed")
        return self._browser_outcome(h, st, r, out.detail or {}, now)

    def _browser_changed(self, person, st, r, now):
        """The page differs from the one the yes was for: nothing pressed; the new last step is shown with a new hash."""
        h = person["handle"]
        run = _sessions(self)["runs"].get(h)
        found = None
        if run is not None and run["session"].alive:
            try:
                run["runner"].path = []
                found = run["runner"].walk()
            except Exception:  # noqa: BLE001
                found = None
        self.store.log_action(h, None, None, "browser.refused", "done", detail={"reason": "page_changed"}, at=now)
        if not found or found["status"] != "final_shown":
            self._browser_close(h, st, "handed_back", now, say=None)
            return self.send(h, self._browser_steps_text(r, now, head=T.browser_changed_gone(r["name"])))
        self.store.update_browser_run(st["run_id"], final_hash=found["hash"], final_name=found["name"][:80])
        self._browser_state(h, dict(st, at=_iso(now), yes_hash=found["hash"], final_name=found["name"],
                                    final_tag=found["tag"], final_quote=found.get("quote") or ""))
        return self.send(h, T.browser_changed(r["name"], found.get("quote") or "", found["name"], yes_word(r)))

    def _browser_outcome(self, h, st, r, got, now):
        """Row 14: what the merchant's page says now (quoted), the browser closed, a check reminder offered."""
        person = self.store.person(h) or {"timezone": "America/New_York", "handle": h}
        tz = person["timezone"]
        page = got.get("page")
        if page == "kept":
            self._browser_close(h, st, "offer_taken", now, say=None)
            self._cancel_update(st["cid"], status="offer_taken", now=now)
            self.store.log_action(h, None, None, "browser.outcome", "done", detail={"status": "offer_taken"}, at=now)
            self._browser_state(h, {"step": "offered", "key": st["key"], "name": st["name"], "at": _iso(now),
                                    "started": _iso(now)})
            return self.send(h, T.browser_offer_taken(r["name"]))
        quote = (got.get("quote") or "")[:200]
        status = "page_says_cancelled" if page == "outcome_ok" and quote else "page_unclear"
        today = now.astimezone(ZoneInfo(tz)).date()
        end = G.end_date(quote, today) if quote else None
        self._browser_close(h, st, status, now, say=None, quote=quote, end=end)
        self._cancel_update(st["cid"], status=status, now=now)
        self.store.log_action(h, None, None, "browser.outcome", "done", detail={"status": status}, at=now)
        at = check_day(now, tz, end)
        self._browser_state(h, {"step": "reminder", "key": st["key"], "name": st["name"], "cid": st["cid"],
                                "at": _iso(now), "started": _iso(now), "offer_at": _iso(at)})
        day = at.astimezone(ZoneInfo(tz)).strftime("%A %-d %B")
        if status == "page_says_cancelled":
            return self.send(h, T.browser_outcome(r["name"], quote, day))
        return self.send(h, T.browser_unclear(r["name"], st.get("final_name") or "", day))

    def _browser_reminder_answer(self, person, st, r, t, now):
        """The next message after row 14: "yes" takes the offered day, another day replaces it, "no" drops it."""
        from .cancel import STOP_ASKING, when_answer
        h = person["handle"]
        self._browser_state(h, None)
        info = {"name": st["name"], "cid": st.get("cid"), "key": st.get("key")}
        if STOP_ASKING.match(t):
            self.note(intent="cancel")
            return self.send(h, T.CANCEL_NO_REMINDER)
        if T.YES.match(t):
            at = datetime.fromisoformat(st["offer_at"])
            if at > now:
                return self._cancel_reminder(person, info, at, t, now)
        at = when_answer(t, now, person["timezone"])
        if at is None:
            return None
        return self._cancel_reminder(person, info, at, t, now)

    def _browser_stop(self, person, st, now):
        h = person["handle"]
        self.note(intent="browser")
        self._browser_close(h, st, "stopped", now, say=None)
        self.store.log_action(h, None, None, "browser.stopped", "done", detail={"by": "person"}, at=now)
        return self.send(h, T.BROWSER_STOPPED)

    def _browser_close(self, h, st, status, now, say=None, quote=None, end=None):
        """Ends the run: every Chromium process of it closed, the context thrown away, the row's counts kept."""
        b = _sessions(self)
        run = b["runs"].get(h)
        counts = {}
        if run is not None and run["run_id"] == st.get("run_id"):
            s = run["session"]
            counts = {"presses": s.presses, "refusals": s.refusals, "seconds": round(s.bot_seconds, 2),
                      "flags": s.flags, "aborted": s.aborted}
            _end_session(self, h)
        if st.get("run_id"):
            self.store.end_browser_run(st["run_id"], status, at=now, outcome_quote=quote,
                                       end_date=end.isoformat() if end else None, **counts)
            if status in ("handed_back", "stopped", "limit") and st.get("cid"):
                self._cancel_update(st["cid"], status="handed_back", now=now)
        self._browser_state(h, None)
        if say:
            self.send(h, say)

    def _browser_timer(self, h, run_id, seconds, why):
        b = _sessions(self)
        t = threading.Timer(seconds, self._browser_expire, args=(h, run_id, why))
        t.daemon = True
        b["timers"].append(t)
        t.start()

    def _browser_expire(self, h, run_id, why):
        """A timer: the last page waited 10 minutes, a hand-back window's 10 minutes passed, or the run's 30."""
        with self.lock_for(h):
            st = self.store.get_state(f"browserrun:{h}")
            now = self.clock()
            if not st or st.get("run_id") != run_id:
                return
            if why == "no_answer" and st["step"] == "final_shown":
                self._browser_close(h, st, "stopped", now)
                self._browser_state(h, {"step": "offered", "key": st["key"], "name": st["name"], "at": _iso(now),
                                        "started": _iso(now)})
                self.send(h, T.BROWSER_NO_ANSWER)
            elif why == "handed_back" and st["step"] == "handed_back":
                self._browser_close(h, st, "handed_back", now)
            elif why == "limit" and st["step"] not in NEXT_ONLY:
                self._browser_close(h, st, "limit", now)
                self.send(h, T.BROWSER_CLOSED_LATE)

    def browser_view_event(self, h, run_id, kind):
        """The take-over view's buttons (browser_vm): "I'm done" acts as "I'm in"; "Stop everything" as "stop"."""
        with self.lock_for(h):
            st = self.store.get_state(f"browserrun:{h}")
            if not st or st.get("run_id") != run_id:
                return None
            now = self.clock()
            person = self.store.person(h)
            if person is None:
                return None
            if kind == "stop":
                return self._browser_stop(person, st, now)
            if kind == "handback" and st["step"] in ("opened", "wall", "handed_back"):
                r = route(st["key"])
                if st["step"] == "handed_back":
                    return None
                return self._browser_go_on(person, st, r, now)
            return None

    def _browser_revoke(self, person, said, now):
        """"stop acting on netflix": the site's permission ends (and an open run of it is closed)."""
        h = person["handle"]
        from .cancel import merchant_in
        e = merchant_in(said, cancel_routes())
        if e is None or not names_match(dict(e, name=e["name"]), said) or self.store.site_grant(h, e["key"]) is None:
            return None
        self.note(intent="browser")
        st = self.store.get_state(f"browserrun:{h}")
        if st and st.get("key") == e["key"]:
            self._browser_close(h, st, "stopped", now)
        self.store.revoke_site_grants(h, e["key"], at=now)
        self.store.log_action(h, None, None, "browser.revoke", "done", detail={"site": e["key"]}, at=now)
        return self.send(h, T.browser_revoked(e["name"], e["name"].lower()))

    def _browser_state(self, h, value):
        self.store.set_state(f"browserrun:{h}", value)


def _iso(dt):
    from .store import now_iso
    return now_iso(dt)


def check_day(now, tz, end=None):
    """The day the check reminder is offered for, at 9am: five days before the end date the page names when that is
    at least two days away, else a week from today."""
    from zoneinfo import ZoneInfo as Z
    local = now.astimezone(Z(tz)).date()
    day = local + timedelta(days=7)
    if end is not None and (end - timedelta(days=5)) >= local + timedelta(days=2):
        day = end - timedelta(days=5)
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=Z(tz))


def forget(bot, handle):
    """"delete my data": an open browser of this person is closed first (its rows go with the store's delete)."""
    try:
        _end_session(bot, handle)
    except Exception:  # noqa: BLE001
        pass

