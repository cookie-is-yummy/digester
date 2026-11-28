"""PROTOTYPE ONLY - the self-test (round 10, slice T; DESIGN.md section 17.T).

Plays everyday conversations against the bot on a made-up library and checks a few plain things per step. Every
example a founder gave is one of the conversations (paraphrased; his exact words only under --private, from a file
outside git). Anyone can read its transcripts: everything in them is made up.

    python3 -m mvp.selftest [--dry] [--quick] [--only c03,c07] [--private] [--slices W,S] [--counts PATH]

from `experiments/`. It refuses to start unless MVP_HOME names a new (missing or empty) folder and MVP_TOTAL_CAP_USD is
set. A live run (no --dry) also needs MVP_LEDGER_HOME, so the shared cap counts, and stops when its own spend passes
MVP_SELFTEST_CAP_USD (default $1.00).

- In process: the console channel, one store under MVP_HOME, a clock that moves 3 minutes a step, no server, no port.
- Outside apps are fakes (TickTick, Todoist, a webhook, the operator's mailbox, Google, the Mac runner); there is no
  SMTP (email to self goes to the outbox or a link), and nothing is fetched from the web.
- --dry: a fake model (each step's scripted answers, else harmless defaults) and a word-match search instead of the
  search engine: 0 model calls, $0. It tests the harness itself; the real check is the live run after a merge.
- Conversations carry `needs` (round 10 slices W S D G C Y V). A conversation whose slices are not in this code is
  skipped and counted, never failed.
- Each reply is printed; the transcript goes to $MVP_HOME/selftest/<stamp>.md; one line of counts (no text) goes to
  mvp/evalset/selftest_runs.jsonl (a dry run: $MVP_HOME/selftest/counts.jsonl unless --counts says otherwise).
- Exit code 1 when any check fails (or the run stopped at its cap), else 0.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
REPO = os.path.dirname(EXP)
DATA = os.path.join(HERE, "selftest")
CONVERSATIONS = os.path.join(DATA, "conversations.jsonl")
TRUTH = os.path.join(DATA, "truth.json")
LIBRARY = os.path.join(DATA, "library")
RUNS = os.path.join(HERE, "evalset", "selftest_runs.jsonl")
PRIVATE = os.path.join(REPO, "data", "mvp", "selftest_private.jsonl")   # the founder's exact words; never in git
SLICES = ("W", "S", "D", "G", "C", "Y", "V")
QUICK = ("c02", "c03", "c05", "c07", "c10", "c19", "c20", "c23")
START = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)   # a Tuesday, 1pm in New York
MAX_SLOT_STOPS = 20   # an "advance" stops at most this often at the person's rule slots on the way
STEP_MINUTES = 3
TZ = "America/New_York"
SELF_ADDR = "me@example.com"          # the made-up person's own address (verified in setups that need it)
DEFAULT_CHECKS = ("no_refusal", "no_not_caught", "no_claim", "no_inside", "no_mismatch_lead", "no_friends")
CHECKS = DEFAULT_CHECKS + ("helper", "helper_not", "reply_has", "reply_any", "reply_not", "pending", "rule_made",
                           "draft_open", "model_calls", "sent_to_other", "placed", "new_creator", "last_lead_not",
                           "email_has")


class SelftestError(Exception):
    """The harness cannot start (a plain reason, no secret, no path beyond MVP_HOME)."""


class CapReached(BaseException):
    """The self-test's own spend reached MVP_SELFTEST_CAP_USD. A BaseException, so the bot's own "except Exception"
    around a model call cannot turn it into a reply: the run stops there."""


# ---------- start-up guard (runs before any mvp module is imported: config reads MVP_HOME at import) ----------
def start_problem(environ, dry):
    """Why the self-test must not start, or None. MVP_HOME must be a new folder (missing or empty), so no store,
    library or ledger of anyone is touched; MVP_TOTAL_CAP_USD must be set; a live run needs MVP_LEDGER_HOME."""
    home = environ.get("MVP_HOME")
    if not home:
        return "Set MVP_HOME to a new folder first."
    if os.path.exists(home) and (not os.path.isdir(home) or os.listdir(home)):
        return "MVP_HOME must be a new, empty folder."
    cap = environ.get("MVP_TOTAL_CAP_USD")
    try:
        float(cap or "")
    except ValueError:
        return "Set MVP_TOTAL_CAP_USD (the shared cap in dollars) first."
    if not dry and not environ.get("MVP_LEDGER_HOME"):
        return "A live run needs MVP_LEDGER_HOME (the shared ledger), so the cap counts every call."
    return None


def prepare_environ(environ, dry):
    """Settings for the run, set before any mvp module is imported."""
    home = os.path.abspath(environ["MVP_HOME"])
    environ["MVP_HOME"] = home
    environ.setdefault("MVP_INBOX", os.path.join(home, "inbox"))
    if dry:
        environ.setdefault("MVP_LEDGER_HOME", os.path.join(home, "ledger"))
    environ["MVP_OUTSIDE"] = "0"      # no web search for outside results: the self-test makes no web request
    environ["MVP_TOKEN_KEY_AUTO"] = environ.get("MVP_TOKEN_KEY_AUTO", "1")
    for k in ("YOUTUBE_API_KEY", "MVP_SMTP_HOST", "MVP_SMTP_PORT", "MVP_SMTP_USER", "MVP_SMTP_PASSWORD",
              "MVP_SMTP_FROM", "MVP_OPERATOR", "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_TICKTICK_TOKEN",
              "MVP_TODOIST_TOKEN", "MVP_WEBHOOK_URL", "MVP_BROWSER", "MVP_BROWSER_MERCHANTS", "MVP_BROWSER_FOR",
              "MVP_BROWSER_DEMO"):
        environ.pop(k, None)   # every outside route starts off; a conversation's setup turns on what it uses
    os.makedirs(home, exist_ok=True)


# ---------- which round 10 slices this code holds ----------
def merged_slices():
    """The round 10 slices present in this code, read from the code itself: a stub the foundation published is
    replaced (W phrasing.py, S captionmark.py, Y yt_auth.py, V browser.py), or the slice's own module exists (W
    errand.py, D panel.py, G grants.py, C mcp_client.py)."""
    import importlib
    import importlib.util

    def real(name):
        try:
            mod = importlib.import_module(f"mvp.{name}")
        except Exception:  # noqa: BLE001 - a module that does not load is not merged
            return False
        return not getattr(mod, "STUB", False)

    def exists(name):
        try:
            return importlib.util.find_spec(f"mvp.{name}") is not None
        except (ImportError, ValueError):
            return False
    out = set()
    if real("phrasing") and exists("errand"):
        out.add("W")
    if real("captionmark"):
        out.add("S")
    if exists("panel"):
        out.add("D")
    if exists("grants"):
        out.add("G")
    if exists("mcp_client"):
        out.add("C")
    if real("yt_auth"):
        out.add("Y")
    if real("browser"):
        out.add("V")
    return out


# ---------- conversations ----------
def load_conversations(path=CONVERSATIONS, private=False):
    convs = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    if private and os.path.exists(PRIVATE):
        for line in open(PRIVATE, encoding="utf-8"):
            if line.strip():
                c = json.loads(line)
                c["id"] = c["id"] + "p"   # the founder's exact words beside the paraphrase
                c["private"] = True
                convs.append(c)
    return convs


def select(convs, only=None, quick=False):
    if only:
        want = {x.strip() for x in only.split(",") if x.strip()}
        return [c for c in convs if c["id"] in want or c["id"].rstrip("p") in want]
    if quick:
        return [c for c in convs if c["id"] in QUICK]
    return convs


# ---------- fakes for outside apps (in process; nothing leaves this machine) ----------
class FakeSMTP:
    """smtplib.SMTP_SSL / SMTP stand-in for the operator's mailbox: accepts everything, keeps each recipient."""
    sent = []    # (sender, [recipients])

    def __init__(self, host, port, timeout=None, context=None, **kw):
        self._from, self._to, self._next = None, [], "250"

    def starttls(self, context=None):
        pass

    def ehlo(self, name=""):
        return 250, b"ok"

    def login(self, user, password):
        pass

    def mail(self, sender, options=()):
        self._from = sender
        return 250, b"ok"

    def rcpt(self, to, options=()):
        self._to.append(to)
        return 250, b"ok"

    def putcmd(self, cmd, args=""):
        self._next = "354"

    def send(self, data):
        FakeSMTP.sent.append((self._from, list(self._to)))
        self._next = "250"

    def getreply(self):
        return (354, b"go ahead") if self._next == "354" else (250, b"2.0.0 OK queued")

    def rset(self):
        pass

    def quit(self):
        pass

    def close(self):
        pass


class FakeApps:
    """The opener of actions/web.py: TickTick and Todoist by token, a webhook, and (when set) the fake Google. Any
    other host is refused, so nothing reaches the network."""

    def __init__(self):
        self.calls, self.n, self.google = [], 0, None

    def __call__(self, method, url, headers, body, timeout):
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        self.calls.append((method, host))
        if self.google is not None and host.endswith("googleapis.com"):
            return self.google(method, url, headers, body, timeout)
        if method == "POST" and "ticktick" in host:
            self.n += 1
            return 200, json.dumps({"id": f"tt{self.n}", "projectId": "inbox1", "title": "x"}).encode()
        if method == "POST" and "todoist" in host:
            self.n += 1
            return 200, json.dumps({"id": f"td{self.n}", "content": "x"}).encode()
        if host.endswith("example.com"):
            return 200, b"ok"
        if method == "DELETE":
            return 204, b""
        if "ticktick" in host or "todoist" in host:
            return 200, b"[]" if method == "GET" else b""
        raise OSError("selftest: no network")

    def adds(self):
        return sum(1 for m, h in self.calls if m == "POST" and ("ticktick" in h or "todoist" in h))


def fake_mac_runner(script, argv, timeout):
    """No Mac here: every AppleScript call fails plainly (a live run on a Mac never touches Reminders or Calendar)."""
    return 1, "", "selftest: no Mac"


class WordPool:
    """--dry: a stand-in for the search engine. Ranks every item of the library by the words it shares with the search
    text (then the shorter caption, then the id), so every search returns the whole library in a fixed order. No
    embeddings, no money."""
    max_resident = 4

    def __init__(self):
        self._libs = {}

    @staticmethod
    def _words(text):
        return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", text.lower())
                if len(w) > 2}

    def _load(self, lib):
        if lib not in self._libs:
            rows = []
            with open(os.path.join(lib, "corpus", "items.jsonl"), encoding="utf-8") as f:
                for line in f:
                    raw = json.loads(line)
                    cap = raw.get("caption") or ""
                    rows.append((raw["id"], self._words(cap), len(cap)))
            self._libs[lib] = rows
        return self._libs[lib]

    def search(self, lib, q, depth=300):
        qw = self._words(q)
        rows = sorted(self._load(lib), key=lambda r: (-len(qw & r[1]), r[2], r[0]))
        return {"ids": [r[0] for r in rows][:depth], "mode": "normal", "cost_usd": 0.0}

    def get(self, lib):
        self._load(lib)

    def warm(self, lib):
        pass

    def stop_all(self):
        pass


# ---------- dry answers: what the fake model says when a step scripts nothing ----------
def _dry_compose(user, system=None, words=None, most=3):
    """The fake composer: the first `most` candidates as clear picks; with `words`, only candidates whose own text
    holds one of them (a step's {"mvp_compose": {"pick_words": [...]}})."""
    nums = []
    for b in re.split(r"(?m)^(?=\d+\. )", user or ""):
        m = re.match(r"(\d+)\. ", b)
        if m and (not words or any(w.lower() in b.lower() for w in words)):
            nums.append(int(m.group(1)))
    picks = [{"n": i, "title": "", "why": "It fits what you asked.", "verdict": "clear", "lines": []}
             for i in nums[:most]]
    return {"picks": picks, "intro": "Here you go."}


def _dry_extract(user, system=None):
    """Round 11: the fake details step for a summary: the item's own sentences as its key points, copied exactly."""
    body = user.split("<item>", 1)[1].rsplit("</item>", 1)[0] if "<item>" in user else ""
    parts = [x.strip(" -") for x in re.split(r"(?<=[.!?])\s+|\n", body) if len(x.strip(" -")) > 12]
    return {"key_points": parts[:3]}


def _dry_synth(user, system=None, most=4):
    """Round 11: the fake summary call: one point per item that names the topic, its first key point quoted (the
    items that do not name it are not called about it, as the model is asked to judge)."""
    m = re.search(r'Topic: "(.*?)"', user or "")
    words = [w for w in re.findall(r"[a-z]+", (m.group(1) if m else "").lower()) if len(w) > 2]
    blocks = [(n, body) for n, title, body in re.findall(
        r"(?m)^(\d+)\. <item>Title: (.*?)\nPoints from its own text:\n(.*?)</item>", user or "", re.S)
        if not words or any(w in (title + " " + body).lower() for w in words)]
    pts = []
    for n, body in blocks[:most]:
        first = body.split("\n")[0][2:].strip()
        if first:
            pts.append({"text": first, "sources": [{"n": int(n), "quote": first}]})
    return {"points": pts, "about": [int(n) for n, _ in blocks]}


def _dry_answer(purpose, ans):
    """A step's scripted answer; a compose answer may name words to pick candidates by instead of fixed numbers. Round
    11: {"mvp_extract": "own_text"} and {"mvp_synth": "quote_points"} answer from the items' own text. Round 12:
    {"mvp_insight": "from_sheet"} fills the history writer's form from the fact sheet by code (tests/r12_writer.py)."""
    if purpose == "mvp_compose" and isinstance(ans, dict) and "pick_words" in ans:
        words, most = ans["pick_words"], ans.get("most", 3)
        return lambda user, system=None: _dry_compose(user, system, words, most)
    if purpose == "mvp_extract" and ans == "own_text":
        return _dry_extract
    if purpose == "mvp_synth" and ans == "quote_points":
        return _dry_synth
    if purpose == "mvp_insight" and ans == "from_sheet":   # round 12, merge: the made-up writer of the tests
        from mvp.tests.r12_writer import fake_insight
        return fake_insight
    return ans


DRY_DEFAULTS = {
    "mvp_interpret": {"intent": "chat", "reply": "OK."},
    "mvp_compose": _dry_compose,
    "mvp_extract": {},
    "mvp_profile_guess": {"interests": [], "summary": ""},
    "mvp_first_requests": {"requests": []},
    "mvp_profile_merge": {"kind": "about_me"},
}


# ---------- one run ----------
class Run:
    def __init__(self, dry, slices, counts_path=None, printer=print, cap_usd=None):
        self.dry = dry
        self.slices = set(slices)
        self.counts_path = counts_path
        self.printer = printer or (lambda *a, **k: None)
        self.cap = float(os.environ.get("MVP_SELFTEST_CAP_USD", "1.00")) if cap_usd is None else cap_usd
        self.home = os.environ["MVP_HOME"]
        self.truth = json.load(open(TRUTH, encoding="utf-8"))
        self.results = []          # one per conversation
        self.transcript = []
        self.model_calls = {}      # purpose -> n (dry: the fake's answers; live: real calls)
        self._undo = []
        self.stopped = None
        self._handles = {}           # conversation id -> the made-up person's handle
        self._lead_creator = None    # the creator of the last answer's first pick (for new_creator)
        self._closers = []           # what a slice's fake needs stopped at the end

    # ----- set up the bot -----
    def _patch(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self._undo.append((obj, name, old))

    def setup(self):
        from mvp import config, llm
        from mvp.actions import mac, mailbox, web
        from mvp.channels.console import ConsoleChannel
        from mvp.core import Bot
        from mvp.store import Store
        self.config = config
        self.apps = FakeApps()
        self._patch(web, "OPENER", self.apps)
        self._patch(mac, "RUNNER", fake_mac_runner)
        self._patch(mailbox.smtplib, "SMTP_SSL", FakeSMTP)
        self._patch(mailbox.smtplib, "SMTP", FakeSMTP)
        FakeSMTP.sent = []
        self._patch(config, "OPERATOR", None)
        self._patch(config, "PAGE_OPERATOR", False)
        if self.dry:
            from mvp.tests.fakes.fake_llm import FakeLLM
            self.fake = FakeLLM(dict(DRY_DEFAULTS), strict=False, cost_per_call=0.0)
            self._undo_llm = self.fake.install()
            self._patch(config, "JUDGE_MODEL", "")    # the judge is one more model call; the dry run has no model
        else:
            self.fake, self._undo_llm = None, None
        real_chat = llm.chat_json

        def counted(system, user, purpose, prompt_version, *a, **kw):
            if self.spent() >= self.cap:   # before the call: a run never passes its own cap by more than one call
                raise CapReached()
            self.model_calls[purpose] = self.model_calls.get(purpose, 0) + 1
            self._step_calls.append(purpose)
            return real_chat(system, user, purpose, prompt_version, *a, **kw)
        self._patch(llm, "chat_json", counted)
        self._step_calls = []
        self.lib = self._library(LIBRARY, "selftest_lib")
        self.clock = [START]
        self.ch = ConsoleChannel(printer=None)
        pool = WordPool() if self.dry else None
        self.bot = Bot(self.ch, store=Store(config.DB), pool=pool, clock=lambda: self.clock[0])
        self.bot.max_per_minute = None
        self.ledger0 = self._ledger()
        self._wrap_hooks()

    def _library(self, src, name, drop=(), extra=()):
        """A copy of the made-up library under MVP_HOME (items matching `drop` left out; `extra`, made-up items of one
        conversation, added with their one event each). A live run builds its search vectors once (about $0.002 of
        embeddings) with the engine's own prepare."""
        lib = os.path.join(self.home, name)
        if os.path.isdir(lib):
            return lib
        os.makedirs(os.path.join(lib, "corpus"))
        shutil.copyfile(os.path.join(src, "library.json"), os.path.join(lib, "library.json"))
        kept = set()
        with open(os.path.join(src, "corpus", "items.jsonl"), encoding="utf-8") as f, \
                open(os.path.join(lib, "corpus", "items.jsonl"), "w", encoding="utf-8") as out:
            for line in f:
                iid = json.loads(line)["id"]
                if not any(fnmatch.fnmatch(iid, d) for d in drop):
                    kept.add(iid)
                    out.write(line)
        with open(os.path.join(src, "corpus", "interactions.jsonl"), encoding="utf-8") as f, \
                open(os.path.join(lib, "corpus", "interactions.jsonl"), "w", encoding="utf-8") as out:
            for line in f:
                if json.loads(line)["item_id"] in kept:
                    out.write(line)
        if extra:   # the merge of round 11's fixes: e.g. reels the person watched, for a watched-only summary
            with open(os.path.join(lib, "corpus", "items.jsonl"), "a", encoding="utf-8") as items, \
                    open(os.path.join(lib, "corpus", "interactions.jsonl"), "a", encoding="utf-8") as inter:
                for x in extra:
                    pd = {"owner_handle": x["by"], "owner_name": x["by"], "owner_relation": "none",
                          "media_kind": "reel", "hashtags": [], "collections": []}
                    items.write(json.dumps({
                        "id": x["id"], "platform": "instagram", "source_url": f"https://www.instagram.com/reel/{x['id']}/",
                        "dedup_key": f"instagram:{x['id']}", "first_seen_at": x["at"], "caption": x["caption"],
                        "platform_data": pd, "importance": 0.5, "processing_depth": "full",
                        "interaction_kinds": [x["kind"]]}) + "\n")
                    inter.write(json.dumps({"item_id": x["id"], "kind": x["kind"], "at": x["at"],
                                            "capture_method": "export_import", "weight": 0.1}) + "\n")
        if not self.dry:
            sys.path.insert(0, os.path.join(EXP, "demo"))
            import library as LIB

            from mvp import refresh
            LIB.ensure_empty_te_files(lib)
            router = os.path.join(REPO, "data", "all", "r7", "router.npz")
            if os.path.isfile(router):
                os.makedirs(os.path.join(lib, "r7"), exist_ok=True)
                shutil.copyfile(router, os.path.join(lib, "r7", "router.npz"))
            r = refresh.prepare_library(lib, 0.05)
            if not r["ok"]:
                raise SelftestError("The made-up library could not be prepared for search.")
        # slice S: the caption marks, built as the bot builds them at start and after an import (derived data under
        # the library; without the file no item is marked)
        from mvp import captionmark
        if hasattr(captionmark, "ensure_lib"):
            captionmark.ensure_lib(lib)
        return lib

    def _ledger(self):
        """Dollars in the shared MVP ledger and the made-up libraries' own ledgers (live runs only)."""
        if self.dry:
            return 0.0
        from mvp import llm
        total = 0.0
        paths = [llm.ai.LEDGER] + [os.path.join(self.home, d, "ai_runs.jsonl") for d in os.listdir(self.home)]
        for p in paths:
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    total += sum(json.loads(x).get("cost_usd") or 0 for x in f if x.strip())
        return total

    def spent(self):
        """This run's spend: the ledgers' growth since it started (a dry run: what the fake model said it cost, $0)."""
        if self.dry:
            return self.fake.cost if self.fake is not None else 0.0
        return self._ledger() - self.ledger0

    # ----- which read answered -----
    BOT_HOOKS = ("secret_reads", "browser_reads", "_deadline_answer", "_overdue_reply", "_cancel_answer",
                 "youtube_answer", "_mismatch_answer", "_doit_answer", "fit_reads", "draft_reads", "offer_reads",
                 "_rule_reads", "export_reads", "email_reads", "youtube_reads", "cancel_reads", "postact_reads",
                 "grant_reads", "receipts_reads", "do_it", "split_reads", "integration_reads", "onboard_step",
                 "understanding_reads", "_email_text")
    MODULE_HOOKS = (("places", "place_reads"), ("places", "asked_reads"), ("refresh", "export_reads"),
                    ("grants", "grant_reads"), ("ytreads", "youtube_reads"),
                    ("history", "history_reads"), ("videoask", "reads"), ("synth", "synth_reads"))   # round 11

    def _wrap_hooks(self):
        import importlib

        from mvp.core import Bot
        claimed = self._claimed = []

        def wrap(name, f):
            def w(*a, **kw):
                out = f(*a, **kw)
                ok = out is not None and out is not False and out != (False, None)
                if isinstance(out, tuple) and len(out) == 2 and out[0] is False:
                    ok = False
                if ok:
                    claimed.append(name)
                return out
            w.__wrapped__ = f
            return w
        for name in self.BOT_HOOKS:
            if hasattr(Bot, name):
                self._patch(Bot, name, wrap(name, getattr(Bot, name)))
        for mod, name in self.MODULE_HOOKS:
            try:
                m = importlib.import_module(f"mvp.{mod}")
            except Exception:  # noqa: BLE001 - a slice not merged
                continue
            if hasattr(m, name):
                self._patch(m, name, wrap(name, getattr(m, name)))
        orig = Bot.code_reads

        def code_reads(bot, person, text, last):
            it, paid = orig(bot, person, text, last)
            if it is not None:
                claimed.append("code_reads:" + it.intent)
            return it, paid
        self._patch(Bot, "code_reads", code_reads)

    def close(self):
        for f in reversed(self._closers):
            try:
                f()
            except Exception:  # noqa: BLE001 - every closer runs
                pass
        self._closers = []
        try:
            self.bot.pool.stop_all()
        except Exception:  # noqa: BLE001
            pass
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)
        self._undo = []
        if self._undo_llm:
            self._undo_llm()
            self._undo_llm = None

    # ----- one conversation -----
    def handle_for(self, n):
        return f"+1555020{n:04d}"

    def run_conversation(self, conv, n):
        """One conversation as one made-up person. `continues: <id>` goes on as the person of that conversation (the
        same store rows), e.g. a rule made in one conversation and its later runs in the next."""
        h = self._handles.get(conv.get("continues")) or self.handle_for(n)
        self._handles[conv["id"]] = h
        self._lead_creator = None
        setup = conv.get("setup") or {}
        lib = self.lib
        if setup.get("drop") or setup.get("extra"):
            lib = self._library(LIBRARY, f"selftest_lib_{conv['id']}", drop=setup.get("drop") or (),
                                extra=setup.get("extra") or ())
        if setup.get("vectors"):
            # the merge of round 11's fixes: a copy of the library with item vectors, so fix A's fit (R3) is read; a
            # live run builds the engine's own, a dry run writes made-up ones (setup["vectors"]: word, off)
            lib = self._library(LIBRARY, f"selftest_lib_{conv['id']}")
            if self.dry:
                self._dry_vectors(lib, setup["vectors"])
        store = self.bot.store
        store.upsert_person(h, "Sam Example", lib, TZ)
        if not setup.get("fresh") and not conv.get("continues"):
            store.set_consent(h, "selftest")   # consent given, setup not open: the everyday path
        env_set = self._setup(h, conv, setup)
        res = {"id": conv["id"], "steps": [], "skipped": None}
        self.transcript.append(f"## {conv['id']} ({conv.get('who', 'tester')}): {conv.get('title', '')}\n")
        if conv.get("note"):
            self.transcript.append(f"_{conv['note']}_\n")
        try:
            for i, step in enumerate(conv["steps"], 1):
                res["steps"].append(self.run_step(conv, h, i, step))
        finally:
            for k, old in env_set.items():
                if old is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old
            self.config.OPERATOR = None
            self.apps.google = None
        return res

    def _setup(self, h, conv, setup):
        """Turns on what this conversation uses; returns the environment values to put back."""
        env = {}

        def setenv(k, v):
            env.setdefault(k, os.environ.get(k))
            os.environ[k] = v
        if conv.get("who") == "operator":
            self.config.OPERATOR = h
        if setup.get("mailbox"):
            setenv("MVP_MAILBOX_ADDRESS", SELF_ADDR)
            setenv("MVP_MAILBOX_APP_PASSWORD", "made-up-app-password-0000")
            setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
            setenv("MVP_MAILBOX_IMAP_HOST", "imap.example.invalid")
        if setup.get("ticktick"):
            setenv("MVP_TICKTICK_TOKEN", "tt-made-up-selftest-000000000000")
        if setup.get("todoist_token"):
            setenv("MVP_TODOIST_TOKEN", "td-made-up-selftest-000000000000")
        if setup.get("email"):
            self.bot.store.set_email(h, SELF_ADDR, verified=True)   # their own address, already confirmed
        if setup.get("google"):
            from mvp.tests.fakes.fake_google import FakeGoogle
            g = FakeGoogle()
            chans = self.truth["youtube_channels"]
            g.add_channels(list(chans), chans)
            for vid, cid in self.truth.get("youtube_videos", []):
                g.add_video(vid, cid)
            self.apps.google = self.google = g
            setenv("MVP_YT_CLIENT_ID", "made-up-client.example.com")
            setenv("MVP_YT_CLIENT_SECRET", "made-up-client-secret")
        if setup.get("browser"):
            setenv("MVP_BROWSER", "operator")
            setenv("MVP_BROWSER_MERCHANTS", "streamly")
            self._setup_browser()
        if setup.get("mcp"):
            setenv("MVP_CONNECT_PORT", "0")   # the sign-in's loopback page on a free port (never 8765 or 8791)
            self._setup_mcp()
        for k, v in (setup.get("env") or {}).items():
            setenv(k, v)
        if "gemini" in setup:   # round 11, slice Q: the fake Gemini answers "ask the video", dry and live alike
            from mvp import videoask
            from mvp.tests.fakes.fake_gemini import FakeGemini
            answer = setup["gemini"]
            fail = set(setup.get("gemini_fail") or ())
            if fail:   # the merge of round 11's fixes: these made-up video ids fail as a private video does (403)

                def answer(req, ok=setup["gemini"]):
                    import urllib.error
                    if any(v in FakeGemini.sent_url(req) for v in fail):
                        raise urllib.error.HTTPError("https://example.invalid", 403, "Forbidden", {}, None)
                    return ok
            self._patch(videoask, "call_model", FakeGemini(answer, cost_per_call=0.0).call)
            setenv("GEMINI_API_KEY", "selftest-not-a-key")
        return env

    @staticmethod
    def _dry_vectors(lib, spec):
        """Made-up 8-dimension item vectors (dry runs only): the items whose caption holds spec["word"] point one way,
        the ids in spec["off"] another, the rest elsewhere; written where the library's float store lives."""
        import numpy as np
        d = os.path.join(lib, "corpus", "emb", "oai3l_1024")
        if os.path.isfile(os.path.join(d, "ids.json")):
            return
        word, off = spec["word"].lower(), set(spec.get("off") or ())
        rng = np.random.default_rng(5)
        ids, vecs = [], []
        with open(os.path.join(lib, "corpus", "items.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                v = rng.normal(0, 0.05, 8)
                v[1 if r["id"] in off else 0 if word in (r.get("caption") or "").lower() else 2 + len(ids) % 6] += 1.0
                ids.append(r["id"])
                vecs.append(v)
        os.makedirs(d)
        with open(os.path.join(d, "ids.json"), "w", encoding="utf-8") as f:
            json.dump(ids, f)
        np.save(os.path.join(d, "emb.npy"), np.asarray(vecs, dtype=np.float16))

    # ----- slice fakes (only reached when the slice is in this code) -----
    def _setup_browser(self):
        """Slice V: the practice merchant "Streamly" (tests/fakes/fake_merchant.py, served by routing, no port) in a
        headless browser standing in for the window on the operator's computer. The person's own sign-in is played by
        the fake person here, never by the bot."""
        if getattr(self, "_browser_on", False):
            return
        from mvp import browser
        from mvp.browser_host import LocalHost, Session

        class PersonSession(Session):
            def _c_person_signs_in(self):
                self.page.fill("input[type=email]", "person@example.com")
                self.page.fill("input[type=password]", "not-a-real-password")
                self.page.click("button:has-text(\"Sign in\")")
                self.page.wait_for_load_state("domcontentloaded")
                return True

        class PracticeHost(LocalHost):
            session_class = PersonSession
        entry = browser.practice_entry(1)
        entry["browser"] = dict(entry["browser"])
        self._patch(browser, "EXTRA", {"streamly": entry})
        self._patch(browser, "make_host", lambda m: PracticeHost(headless=True, screen=lambda: True))
        self._closers.append(lambda: browser.close_all(self.bot))
        self._browser_on = True

    def _setup_mcp(self):
        """Slice C: the fake OAuth server (through an ASGI client, no socket) and the fake Todoist MCP server, joined as
        in the slice's own tests: the MCP server takes only the access tokens the OAuth server handed out."""
        if getattr(self, "_mcp", None):
            return
        import urllib.parse

        from starlette.testclient import TestClient

        from mvp import mcp_client, oauth
        from mvp.mcp_mappings import SERVERS
        from mvp.tests.fakes.fake_mcp import FakeMcpServer
        from mvp.tests.fakes.fake_oauth import fake_oauth_app
        import logging
        logging.getLogger("httpx").setLevel(logging.WARNING)   # no request lines (with codes in their URLs) in output
        oa = fake_oauth_app(access_ttl=3600)
        client = TestClient(oa.asgi, base_url=oa.base)
        client.__enter__()
        srv = FakeMcpServer("todoist")

        def opener(method, url, headers, body, timeout):
            u = urllib.parse.urlsplit(url)
            if u.scheme != "https" or u.netloc != "fake-auth.example":
                raise OSError("selftest: no network")
            r = client.request(method, u.path + (f"?{u.query}" if u.query else ""), headers=headers, content=body,
                               follow_redirects=False)
            return r.status_code, dict(r.headers), r.content

        def transport(conf, token):
            ok = token in oa.provider.access
            return srv.transport(srv.access_token if ok else "stale-" + str(token)[:4])
        old = SERVERS["todoist"]
        SERVERS["todoist"] = dict(old, url="https://fake-auth.example/mcp", issuer="https://fake-auth.example",
                                  scope="tasks")
        self._patch(oauth, "OPENER", opener)
        self._patch(mcp_client, "TRANSPORT", transport)

        def stop():
            SERVERS["todoist"] = old
            oauth.stop_listener()
            client.__exit__(None, None, None)
        self._closers.append(stop)
        self._mcp = {"client": client, "srv": srv}

    def _mcp_allow(self, h):
        """The person opens the link the bot sent and presses Allow; the bot's loopback page gets them back."""
        import urllib.parse

        from mvp.actions import mcp as M
        link = next((re.search(r"press Allow: (\S+)", t).group(1) for _, hh, t in reversed(self.ch.outbox)
                     if hh == h and "press Allow: " in t), None)
        if not link:
            return False
        u = urllib.parse.urlsplit(link)
        r = self._mcp["client"].get(u.path + "?" + u.query, follow_redirects=False)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers.get("location", "")).query))
        return M.on_code(self.bot, q.get("state"), q.get("code"), q.get("iss"), q.get("error")) is True

    def _advance(self, h, spec):
        """Moves the clock: "3m", "2h", "2d", or "SUN 18:05" (the next such local time). On the way, the clock stops
        just after each slot of this person's active rules and the scheduler ticks there, as the running bot ticks
        every minute (the first live run: a rule the model set for 9am never ran when the clock jumped to 18:05, as
        the scheduler skips a send more than 2 hours late). The step's own tick then runs at the end."""
        target = self._target(spec, h)
        for _ in range(MAX_SLOT_STOPS):
            due = sorted(r["next_run_at"] for r in self.bot.store.rules(h, statuses=("active",))
                         if r.get("next_run_at"))
            due = [datetime.fromisoformat(d) for d in due]
            due = [d for d in due if self.clock[0] < d + timedelta(minutes=1) <= target]
            if not due:
                break
            self.clock[0] = due[0] + timedelta(minutes=1)
            self.bot.tick()
        self.clock[0] = max(self.clock[0], target)

    def _target(self, spec, h=None):
        """The time an "advance" goes to. "next run": one minute after this person's next rule slot (the time a real
        model chose for "every sunday" is not known in advance; "undo" right after the run is then inside its 10
        minutes)."""
        from zoneinfo import ZoneInfo
        now = self.clock[0]
        if spec.strip() == "next run":
            due = [datetime.fromisoformat(r["next_run_at"]) for r in self.bot.store.rules(h, statuses=("active",))
                   if r.get("next_run_at")]
            due = [d for d in due if d + timedelta(minutes=1) > now]
            if not due:
                raise SelftestError("no rule slot ahead for 'next run'")
            return min(due) + timedelta(minutes=1)
        m = re.fullmatch(r"(\d+)([mhd])", spec.strip())
        if m:
            n, u = int(m.group(1)), m.group(2)
            return now + timedelta(**{"m": {"minutes": n}, "h": {"hours": n}, "d": {"days": n}}[u])
        day, hhmm = spec.split()
        days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        hh, mm = (int(x) for x in hhmm.split(":"))
        local = now.astimezone(ZoneInfo(TZ))
        for k in range(1, 9):
            cand = (local + timedelta(days=k - 1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand > local and days[cand.weekday()] == day.upper()[:3]:
                return cand.astimezone(timezone.utc)
        raise SelftestError(f"bad clock step {spec!r}")

    def _do(self, h, what):
        """A harness action between messages: the fake Google's "Allow" (the person typed the code), and others a
        slice's fake offers. Unknown actions fail the step."""
        if what == "google_approve":
            self.google.approve()
            return True
        if what == "mcp_allow":
            return self._mcp_allow(h)
        if what == "mcp_change_tool":   # the vendor edits the add tool after the person's yes
            self._mcp["srv"].change_tool("add-tasks", description="Add tasks to Todoist, now with more options.")
            return True
        return False

    def _acts(self, h):
        st = self.bot.store

        def n(sql, args=(h,)):
            try:
                return st.one(sql, args)["n"]
            except Exception:  # noqa: BLE001 - a table a slice adds may not exist
                return 0
        return {
            "email": n("SELECT COUNT(*) n FROM outbox WHERE handle=?")
            + n("SELECT COUNT(*) n FROM drafts WHERE handle=? AND status IN ('sent','sending')")
            + n("SELECT COUNT(*) n FROM action_log WHERE handle=? AND (action LIKE 'email.%' OR action LIKE "
                "'mailbox.%') AND status IN ('done','ok','sent')"),
            "add": n("SELECT COUNT(*) n FROM placements WHERE handle=?") + n("SELECT COUNT(*) n FROM todos WHERE handle=?")
            + n("SELECT COUNT(*) n FROM action_log WHERE handle=? AND status IN ('done','ok')"),
            "unsubscribe": n("SELECT COUNT(*) n FROM action_log WHERE handle=? AND action LIKE 'youtube.%' AND "
                             "status IN ('done','ok')"),
            "rules": n("SELECT COUNT(*) n FROM rules WHERE handle=?"),
            "placements": n("SELECT COUNT(*) n FROM placements WHERE handle=?"),
        }

    def run_step(self, conv, h, i, step):
        sid = f"{conv['id']}.{i}"
        if self.dry and self.fake is not None:
            self.fake.answers = dict(DRY_DEFAULTS)
            for purpose, ans in (step.get("dry") or {}).items():
                self.fake.answers[purpose] = _dry_answer(purpose, ans)
        # (the counts before the clock moves: what a rule's run says on the way belongs to this step)
        acts0, n_out, smtp0 = self._acts(h), len(self.ch.outbox), len(FakeSMTP.sent)
        last0 = (self.bot.store.last_answer(h) or {}).get("run_id")
        self._claimed.clear()
        self._step_calls = []
        trace = self.bot._tl.trace = {}
        error = None
        self.clock[0] += timedelta(minutes=step.get("gap", STEP_MINUTES))
        try:
            for what in step.get("do") or []:   # what the outside world does first (an Allow, a changed tool)
                if not self._do(h, what):
                    error = f"harness action {what} not available"
            if step.get("advance"):   # then the clock, stopping at this person's rule slots on the way
                self._advance(h, step["advance"])
            self.bot.tick()   # then the timed work due by now (held sends, rule runs, a device code's poll)
            if step.get("tap"):
                ref = next((r for r, hh, _ in reversed(self.ch.outbox) if hh == h), None)
                self.bot.on_message(h, "", tapback=step["tap"], tapback_ref=ref)
            if "say" in step:
                self.bot.on_message(h, step["say"])
            if step.get("wait") == "browser":   # slice V: the walk after "I'm in" runs in the background
                from mvp import browser
                browser.wait(self.bot, h, timeout=60)
        except CapReached:
            raise
        except Exception as e:  # noqa: BLE001 - a crash is a failed step, never a crashed run
            error = type(e).__name__
        finally:
            self.bot._tl.trace = None
        replies = [t for _, hh, t in self.ch.outbox[n_out:] if hh == h]
        acts1 = self._acts(h)
        last = self.bot.store.last_answer(h) or {}
        ctx = {"h": h, "replies": replies, "text": "\n\n".join(replies), "acts0": acts0, "acts1": acts1,
               "claimed": list(self._claimed), "intent": trace.get("intent"), "calls": list(self._step_calls),
               "new_answer": last.get("run_id") not in (None, last0), "items": last.get("items") or [],
               "smtp": FakeSMTP.sent[smtp0:], "error": error, "lead_creator0": self._lead_creator}
        if ctx["new_answer"] and ctx["items"]:
            it = self.bot.view(self.bot.store.person(h)["library"]).get(ctx["items"][0])
            self._lead_creator = it.creator if it else None
        ctx["lead_creator"] = self._lead_creator
        exp = dict(step.get("expect") or {})
        if not self.dry:   # what only a real model can be asked to get right (a dry run's fake model cannot)
            exp.update(step.get("expect_live") or {})
        checks = self.check(ctx, exp, conv)
        ok = all(v for v, _ in checks.values())
        self._print_step(sid, step, replies, checks, error)
        return {"id": sid, "ok": ok, "checks": {k: v for k, (v, _) in checks.items()},
                "why": {k: why for k, (v, why) in checks.items() if not v}}

    def _print_step(self, sid, step, replies, checks, error):
        said = step.get("say")
        head = f"### {sid}" + (f" (clock: {step['advance']})" if step.get("advance") else "")
        lines = [head]
        if step.get("do"):
            lines.append(f"(the fake outside app: {', '.join(step['do'])})")
        if step.get("tap"):
            lines.append(f"(reaction: {step['tap']})")
        if said is not None:
            lines.append(f"> {said}")
        lines += [r for r in replies] or ["(no reply)"]
        bad = [f"{k}: {why}" for k, (v, why) in checks.items() if not v]
        if error:
            bad.insert(0, f"error: {error}")
        lines.append("FAILED: " + "; ".join(bad) if bad else "ok")
        out = "\n\n".join(lines) + "\n"
        self.transcript.append(out)
        self.printer(out)

    # ----- the checks -----
    CANT_OPEN = re.compile(r"^(?:sorry,\s*)?(?:I can'?t|I cannot|I'm not able|That's not something I can do)", re.I)
    INSIDE = re.compile(r"\b(?:json|structured|prompt|schema|interpreter)\b", re.I)
    CLAIM = re.compile(r"\b(?:I'?ve|I have|I)\s+(?:just\s+|already\s+|now\s+)?(sent|emailed|cancell?ed|canceled|booked|"
                       r"ordered|bought|paid|added|unsubscribed|signed you up|reserved|purchased)\b"
                       r"|^(Added|Sent|Emailed|Unsubscribed)\b|\b(?:has|have) been (sent|cancell?ed|canceled|booked)\b"
                       r"|\byou(?:'re| are) (?:now )?(unsubscribed|cancell?ed)\b", re.I | re.M)
    QUOTED = re.compile(r"\"[^\"\n]{0,400}\"|“[^”\n]{0,400}”")
    DOUBT = re.compile(r"Heads-up: its caption|Going by its caption|The only match I found is", re.I)

    def _email_has(self, h, want):
        import email
        from email import policy
        rows = self.bot.store.outbox(h, limit=1)
        if not rows:
            return False, "no email kept"
        try:
            m = email.message_from_bytes(open(rows[0]["path"], "rb").read(), policy=policy.default)
            body = m.get_body(preferencelist=("plain",)).get_content()
        except (OSError, AttributeError, ValueError):
            return False, "the email could not be read"
        got = (rows[0]["subject"] or "") + "\n" + body
        miss = [w for w in want if w.lower() not in got.lower()]
        return not miss, "missing: " + " | ".join(miss)

    def check(self, ctx, exp, conv):
        from mvp import texts as T
        allow_cant = exp.get("allow_cant", False)
        off = set(exp.get("off") or [])
        text, replies = ctx["text"], ctx["replies"]
        out = {}

        def put(name, ok, why=""):
            out[name] = (bool(ok), why)
        if ctx["error"]:
            put("no_error", False, ctx["error"])
        if "no_refusal" not in off and not allow_cant:
            bad = [r for r in replies if self.CANT_OPEN.match(r.strip())
                   or r.strip().startswith(T.UNSUPPORTED[:40])
                   or r.strip().startswith(T.EMAIL_ONLY_YOU[:30])]
            put("no_refusal", not bad, bad[0][:80] if bad else "")
        if "no_not_caught" not in off:
            put("no_not_caught", T.NOT_CAUGHT not in text, "the didn't-catch-that line")
        if "no_claim" not in off:
            put("no_claim", *self._claims_ok(ctx))
        if "no_inside" not in off:
            m = self.INSIDE.search(text)
            put("no_inside", not m, m.group(0) if m else "")
        if "no_mismatch_lead" not in off:
            put("no_mismatch_lead", *self._lead_ok(ctx))
        if "no_friends" not in off:
            friends = set(self.truth["friends"])
            bad = [i for i in ctx["items"] if i in friends] if ctx["new_answer"] else []
            put("no_friends", not bad and "Friend's dinner party" not in text, ",".join(bad))
        if "helper" in exp:
            want = exp["helper"] if isinstance(exp["helper"], list) else [exp["helper"]]
            got = ctx["claimed"] + ([f"intent:{ctx['intent']}"] if ctx["intent"] else [])
            hit = any(w in got or f"intent:{w}" in got for w in want)
            put("helper", hit, f"wanted {'/'.join(want)}, got {', '.join(got) or 'nothing'}")
        if "reply_has" in exp:
            want = exp["reply_has"] if isinstance(exp["reply_has"], list) else [exp["reply_has"]]
            miss = [w for w in want if w.lower() not in text.lower()]
            put("reply_has", not miss, "missing: " + " | ".join(miss))
        if "reply_any" in exp:
            put("reply_any", any(w.lower() in text.lower() for w in exp["reply_any"]),
                "none of: " + " | ".join(exp["reply_any"]))
        if "reply_not" in exp:
            want = exp["reply_not"] if isinstance(exp["reply_not"], list) else [exp["reply_not"]]
            hit = [w for w in want if w.lower() in text.lower()]
            put("reply_not", not hit, "has: " + " | ".join(hit))
        if "email_has" in exp:   # the merge of round 11's fixes: the newest email kept for this person, subject and text
            put("email_has", *self._email_has(ctx["h"], exp["email_has"]))
        if "pending" in exp:
            p = self.bot.store.pending(ctx["h"])
            want = exp["pending"]
            ok = (p is not None) if want is True else (p is None) if want is False else (p or {}).get("kind") == want
            put("pending", ok, f"pending is {(p or {}).get('kind')}")
        if "rule_made" in exp:
            put("rule_made", *self._rule_ok(ctx, exp["rule_made"]))
        if "draft_open" in exp:
            d = self.bot.store.drafts_of(ctx["h"])
            open_ = bool(d) and d[-1]["status"] not in ("sent", "sending", "cancelled", "expired", "done",
                                                         "person_sent", "unknown", "held")
            put("draft_open", open_ == exp["draft_open"], f"latest draft is {d[-1]['status'] if d else 'none'}")
        if "model_calls" in exp:
            bad = {p: ctx["calls"].count(p) for p, mx in exp["model_calls"].items() if ctx["calls"].count(p) > mx}
            put("model_calls", not bad, json.dumps(bad))
        if "sent_to_other" in exp:   # emails from the person's mailbox to anyone but them, in this step
            others = [r for _, rs in ctx["smtp"] for r in rs if r.lower() != SELF_ADDR]
            put("sent_to_other", len(others) == exp["sent_to_other"], f"{len(others)} email(s) to another address")
        if "helper_not" in exp:
            want = exp["helper_not"] if isinstance(exp["helper_not"], list) else [exp["helper_not"]]
            got = ctx["claimed"] + ([f"intent:{ctx['intent']}"] if ctx["intent"] else [])
            hit = [w for w in want if w in got or f"intent:{w}" in got]
            put("helper_not", not hit, "taken by " + ", ".join(hit))
        if "new_creator" in exp:
            put("new_creator", ctx["new_answer"] and ctx["lead_creator"] != ctx["lead_creator0"],
                f"the lead is still by {ctx['lead_creator']}")
        if "placed" in exp:
            got = ctx["acts1"]["placements"] - ctx["acts0"]["placements"]
            put("placed", got == exp["placed"], f"{got} placed")
        if "last_lead_not" in exp:
            lead = ctx["items"][0] if ctx["items"] else None
            put("last_lead_not", lead not in set(exp["last_lead_not"]), f"lead {lead}")
        return out

    def _claims_ok(self, ctx):
        """A reply may say it sent, added or unsubscribed only when the store shows that act for this person; the bot's
        own words never say something was cancelled, booked, ordered, bought or paid (a quote from a page may)."""
        for r in ctx["replies"]:
            plain = self.QUOTED.sub(" ", r)
            for m in self.CLAIM.finditer(plain):
                verb = next(g for g in m.groups() if g).lower()
                before = plain[max(0, m.start() - 16):m.start()].lower()
                if re.search(r"\b(?:nothing|not|never|no)\b|n't\s*$|\b(?:what|if|once|when|after)\s*$", before):
                    continue   # "Nothing has been sent", "I haven't sent ...", "I'll tell you what I added"
                if verb in ("sent", "emailed"):
                    if ctx["acts1"]["email"] > 0:
                        continue
                elif verb == "added":
                    if ctx["acts1"]["add"] > 0:
                        continue
                elif verb == "unsubscribed":
                    if ctx["acts1"]["unsubscribe"] > 0:
                        continue
                return False, m.group(0)
        return True, ""

    def _lead_ok(self, ctx):
        if not ctx["new_answer"] or not ctx["items"]:
            return True, ""
        bad = set(self.truth["mismatched"])
        items = ctx["items"]
        if items[0] in bad and any(i not in bad for i in items[1:]):
            return False, f"a mismatched reel leads ({items[0]}) though another pick fits"
        if "S" in self.slices and items[0] in bad and not self.DOUBT.search(ctx["text"]):
            return False, "a mismatched reel leads without the doubt line"
        return True, ""

    def _rule_ok(self, ctx, want):
        rows = self.bot.store.rules(ctx["h"], statuses=("active",))
        if want is False:
            return ctx["acts1"]["rules"] == ctx["acts0"]["rules"], "a rule was made"
        if not rows:
            return False, "no active rule"
        if isinstance(want, dict) and want.get("connector"):
            spec = rows[-1]["spec"]
            spec = json.loads(spec) if isinstance(spec, str) else spec
            got = ((spec or {}).get("place") or {}).get("connector")
            return got == want["connector"], f"place is {got}"
        return True, ""

    # ----- the whole run -----
    def run(self, convs):
        self.setup()
        n_conv = 0
        skipped = {}
        try:
            for k, conv in enumerate(convs, 1):
                missing = [s for s in conv.get("needs") or [] if s not in self.slices]
                if missing:
                    for s in missing:
                        skipped[s] = skipped.get(s, 0) + 1
                    self.results.append({"id": conv["id"], "skipped": missing, "steps": []})
                    self.transcript.append(f"## {conv['id']}: skipped (needs {', '.join(missing)})\n")
                    continue
                if self.stopped:
                    self.results.append({"id": conv["id"], "skipped": ["cap"], "steps": []})
                    continue
                n_conv += 1
                try:
                    self.results.append(self.run_conversation(conv, k))
                except CapReached:
                    self.stopped = "cap"
                    self.results.append({"id": conv["id"], "skipped": ["cap"], "steps": []})
                    self.printer("Stopped: the self-test's own spend reached its cap.")
        finally:
            spend = self.spent()
            self.close()
        return self.summary(convs, skipped, spend)

    def summary(self, convs, skipped, spend):
        steps = [s for r in self.results for s in r["steps"]]
        by_check = {}
        for s in steps:
            for k, v in s["checks"].items():
                ok, n = by_check.get(k, [0, 0])
                by_check[k] = [ok + bool(v), n + 1]
        failed = [s["id"] for s in steps if not s["ok"]]
        from mvp import config
        build = config.BUILD
        return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "head": build.split()[0],
                "build": build, "mode": "dry" if self.dry else "live", "slices": sorted(self.slices),
                "conversations": len(convs), "ran": sum(1 for r in self.results if r["steps"]),
                "skipped": sum(1 for r in self.results if r.get("skipped")), "skipped_by_slice": skipped,
                "steps": len(steps), "steps_ok": len(steps) - len(failed), "by_check": by_check, "failed": failed,
                "stopped": self.stopped, "spend_usd": round(spend, 4),
                "models": dict(sorted(self.model_calls.items()))}

    def write(self, counts):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tdir = os.path.join(self.home, "selftest")
        os.makedirs(tdir, exist_ok=True)
        path = os.path.join(tdir, f"{stamp}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Self-test {counts['mode']} run, build {counts['build']} (made-up library and people)\n\n")
            f.write("\n".join(self.transcript))
        cp = self.counts_path or (RUNS if not self.dry else os.path.join(tdir, "counts.jsonl"))
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "a", encoding="utf-8") as f:
            f.write(json.dumps(counts) + "\n")
        return path, cp


def main(argv=None, environ=None):
    ap = argparse.ArgumentParser(prog="python3 -m mvp.selftest")
    ap.add_argument("--dry", action="store_true", help="a fake model and a word-match search: 0 model calls, $0")
    ap.add_argument("--quick", action="store_true", help=f"only {', '.join(QUICK)}")
    ap.add_argument("--only", default=None, help="conversation ids, comma-separated")
    ap.add_argument("--private", action="store_true", help="also the founder's exact words (a file outside git)")
    ap.add_argument("--slices", default=None, help="pretend only these round 10 slices are here (W,S,D,G,C,Y,V)")
    ap.add_argument("--counts", default=None, help="where the line of counts goes")
    ap.add_argument("--quiet", action="store_true", help="print only the line of counts")
    ap.add_argument("--conversations", default=CONVERSATIONS, help=argparse.SUPPRESS)   # tests: another file
    a = ap.parse_args(argv)
    environ = os.environ if environ is None else environ
    why = start_problem(environ, a.dry)
    if why:
        print(why, file=sys.stderr)
        return 2
    prepare_environ(environ, a.dry)
    sys.path.insert(0, EXP)
    have = merged_slices()
    slices = have if a.slices is None else {s.strip().upper() for s in a.slices.split(",") if s.strip()} & have
    convs = select(load_conversations(a.conversations, private=a.private), a.only, a.quick)
    run = Run(a.dry, slices, a.counts, printer=None if a.quiet else print)
    t0 = time.time()
    counts = run.run(convs)
    counts["seconds"] = round(time.time() - t0, 1)
    path, _ = run.write(counts)
    print(json.dumps(counts))
    print(f"Transcript: {path}", file=sys.stderr)
    return 1 if counts["failed"] or counts["stopped"] else 0


if __name__ == "__main__":
    sys.exit(main())
