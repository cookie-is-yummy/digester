"""PROTOTYPE ONLY - the outside places the bot can write to, one entry each (round 9, C3; DESIGN.md section 16.D).

A connector is a place outside the bot (the operator's Mac today) with one action per kind of thing it takes ("todo":
a to-do or a list of them; "calendar": one event). Its state for a person is one `connections` row: connected, broken
(3 failures in a row: no more calls until the person checks it) or off (they disconnected it); no row is "not
connected". What it made is in `placements` (ids only, never a title). places.py decides when to use one.

Adding a connector later (a task app by token, a webhook) is:
  1. one REGISTRY entry per kind in actions/__init__.py (outside=True, undo="delete" or "none", confirm="send_word",
     who="operator", from_model=False, connector="<key>", fallback="todo.add" or "calendar.add", max_per_day, and
     params PlaceTodoParams / MacEventParams or its own),
  2. a module actions/<key>.py with run(ctx, params) -> Outcome(detail={"placed": [{"action", "remote_id"}]}),
     yes_token(ctx, params), remove(rows) -> {"removed", "failed"}, check() and reachable(); errors are
     ConnectorError(code),
  3. one entry in CONNECTORS below, and one entry per app name in places.PLACES (the words people use for it).
"""
from dataclasses import dataclass, field
import importlib


class ConnectorError(Exception):
    """A connector did not do its work. `code`: blocked | timeout | unreachable | no_calendar | failed (or a code its
    module adds). `app`: which app said it ("Reminders", "Calendar"), when it matters. Never holds what was sent."""

    def __init__(self, code, app=None):
        super().__init__(code)
        self.code, self.app = code, app


COUNTS_AS_FAILURE = ("blocked", "timeout", "failed")   # 3 of these in a row mark the connector broken
BREAK_AFTER = 3


@dataclass(frozen=True)
class Connector:
    key: str
    name: str                                   # "Reminders and Calendar on this Mac"
    module: str                                 # the module in actions/ (run, yes_token, remove, check, reachable)
    actions: dict = field(default_factory=dict)  # kind -> action name
    apps: dict = field(default_factory=dict)     # kind -> the app's own short name, for the reply lines
    nouns: dict = field(default_factory=dict)    # action name -> (one, many): ("reminder", "reminders")


CONNECTORS = {
    "mac": Connector(key="mac", name="Reminders and Calendar on this Mac", module="mac",
                     actions={"todo": "mac.reminder", "calendar": "mac.event"},
                     apps={"todo": "Reminders", "calendar": "Calendar"},
                     nouns={"mac.reminder": ("reminder", "reminders"), "mac.event": ("event", "events")}),
}


def module(key):
    return importlib.import_module(f"mvp.actions.{CONNECTORS[key].module}")


def status(store, handle, key):
    """connected | broken | off, or None (never connected)."""
    row = store.connection(handle, key)
    return row["status"] if row else None


def unavailable(store, handle, key):
    """None when the connector can be used for this person now; else why not: operator (only the person who runs the
    bot), unreachable (not on a Mac), not_connected, off, broken."""
    from . import config
    if not config.is_operator(handle):
        return "operator"
    if not module(key).reachable():
        return "unreachable"
    st = status(store, handle, key)
    if st is None:
        return "not_connected"
    if st in ("off", "broken"):
        return st
    return None


def failed(store, handle, key, code, now):
    """Records one failure; 3 in a row mark the connector broken. Codes that are not the connector failing (not on a
    Mac, no "Digest" calendar) only record the code."""
    row = store.connection(handle, key) or {}
    if code not in COUNTS_AS_FAILURE:
        store.set_connection(handle, key, last_error=code, at=now)
        return
    fails = int(row.get("fails") or 0) + 1
    st = "broken" if fails >= BREAK_AFTER else (row.get("status") or "connected")
    store.set_connection(handle, key, status=st, fails=fails, last_error=code, at=now)


def worked(store, handle, key, now):
    """A call that did its work ends a run of failures (a "no_calendar" note stays until a check finds the calendar)."""
    row = store.connection(handle, key) or {}
    if row.get("fails") or row.get("last_error") in COUNTS_AS_FAILURE:
        keep = row.get("last_error") if row.get("last_error") not in COUNTS_AS_FAILURE else ""
        store.set_connection(handle, key, fails=0, last_error=keep, at=now)
