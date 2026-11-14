"""PROTOTYPE ONLY - the bot: message handler, executor and scheduler (docs/06 'Executor', BRIEF-10 sections 4 and 5).

Only this bot sends (AGENTS.md rule 5): retrieve and compose read; the interpreter fills forms (rule 6).
Bot is assembled from mixins: handler.py (messages in), onboarding.py (the setup after consent), todos.py (to-dos and library counts), outputs.py (a spec's
`do`, acting on an answer, the person's email), executor.py (one run with its outside block, and the send) and
scheduler.py (timed sends, and the inbox check of refresh.py). What it says is in texts.py. The names below stay
importable from mvp.core.
"""
import json
import os
import sys
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import config
from .attention import AttentionMixin
from .digest import DigestMixin
from .executor import ExecutorMixin
from .followup import FollowupMixin
from .handler import (
    ENDS_PENDING,
    MAX_MESSAGES_PER_HOUR,
    MAX_MESSAGES_PER_MINUTE,
    PENDING_TTL,
    HandlerMixin,
    norm_handle,
)
from .libview import LibraryView
from .onboarding import OnboardingMixin
from .outputs import OutputsMixin
from .scheduler import (
    MAX_RETRIES,
    MISSED_AFTER,
    RETRY_AFTER,
    UNANSWERED_CHECK,
    UNANSWERED_PAUSE,
    SchedulerMixin,
)
from .store import Store
from .todos import TodoMixin
from .texts import (
    AGREE,
    CONSENT,
    CONSENT_VERSION,
    HELP,
    LAST_SEND,
    LIMIT,
    LIMIT_TOTAL,
    LOADING,
    NEGATION,
    NO,
    NOTHING_PENDING,
    PAUSED_QUIET,
    QUICK_FEEDBACK,
    REACTION_TEXT,
    SCHEDULED_FOOTER,
    STILL_USEFUL,
    UNKNOWN,
    YES,
)

__all__ = [
    "AGREE",
    "CONSENT",
    "CONSENT_VERSION",
    "ENDS_PENDING",
    "HELP",
    "LAST_SEND",
    "LIMIT",
    "LIMIT_TOTAL",
    "LOADING",
    "MAX_MESSAGES_PER_HOUR",
    "MAX_MESSAGES_PER_MINUTE",
    "MAX_RETRIES",
    "MISSED_AFTER",
    "NEGATION",
    "NO",
    "NOTHING_PENDING",
    "PAUSED_QUIET",
    "PENDING_TTL",
    "QUICK_FEEDBACK",
    "REACTION_TEXT",
    "RETRY_AFTER",
    "SCHEDULED_FOOTER",
    "STILL_USEFUL",
    "UNANSWERED_CHECK",
    "UNANSWERED_PAUSE",
    "UNKNOWN",
    "YES",
    "Bot",
    "norm_handle",
]


class Bot(HandlerMixin, FollowupMixin, OnboardingMixin, TodoMixin, OutputsMixin, ExecutorMixin, SchedulerMixin,
          AttentionMixin, DigestMixin):   # round 8: trends and the theme check (attention.py), the recap (digest.py)
    def __init__(self, channel, store=None, pool=None, clock=None):
        self.channel = channel
        self.store = store or Store(config.DB)
        if pool is None:
            from .engines import EnginePool
            pool = EnginePool()
        self.pool = pool
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.views = {}
        self._views_lock = threading.Lock()
        self._locks = {}      # handle -> lock: one person's messages and timed sends never run at the same time
        self._tl = threading.local()   # what happened to the message this thread is handling (for the journal)
        self._arrivals = {}   # handle -> real times of recent messages
        self.max_per_minute = MAX_MESSAGES_PER_MINUTE   # None switches the flood guard off (batch test runs)
        self._refresher = None

    @property
    def refresher(self):
        """The inbox watcher and importer (refresh.py), made on first use."""
        if self._refresher is None:
            from .refresh import Refresher
            self._refresher = Refresher(self)
        return self._refresher

    @refresher.setter
    def refresher(self, value):
        self._refresher = value

    # ---------- people ----------
    def load_people(self, path=None):
        path = self.people_path = path or getattr(self, "people_path", None) or config.PEOPLE
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8") as f:
            people = json.load(f)
        # a person who asked for deletion is not added back from people.json (this store's own list: PRIV-3)
        deleted = self.store.deleted_handles()
        n = 0
        for i, (handle, p) in enumerate(people.items(), 1):
            handle = norm_handle(handle)
            if handle in deleted:
                print(f"people.json, person {i}: skipped, they asked for their data to be deleted", file=sys.stderr)
                continue
            n += 1
            lib = p["library"]
            if not os.path.isabs(lib):  # "data/all" means the repo's data folder, wherever the bot is started from
                lib = next((os.path.join(b, lib) for b in (config.REPO, os.getcwd(), os.path.dirname(os.path.abspath(path)))
                            if os.path.isdir(os.path.join(b, lib))), lib)
            lib = os.path.abspath(lib)
            if not os.path.isfile(os.path.join(lib, "corpus", "items.jsonl")):
                raise SystemExit(f"people.json, person {i}: there is no library at {lib}")
            try:
                ZoneInfo(p.get("timezone", "America/New_York"))
            except Exception:  # noqa: BLE001
                raise SystemExit(f"people.json, person {i}: unknown timezone {p.get('timezone')!r}") from None
            self.store.upsert_person(handle, p.get("name"), lib, p.get("timezone", "America/New_York"))
        return n

    def view(self, library):
        with self._views_lock:
            if library not in self.views:
                self.views[library] = LibraryView(library)
            return self.views[library]

    def lock_for(self, handle):
        with self._views_lock:
            return self._locks.setdefault(handle, threading.RLock())

    def note(self, **kw):
        """Facts about the message being handled (intent, run, reply), for the inbound journal. No text."""
        trace = getattr(self._tl, "trace", None)
        if trace is not None:
            trace.update(kw)
