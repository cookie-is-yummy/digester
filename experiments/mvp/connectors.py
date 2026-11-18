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
import re


class ConnectorError(Exception):
    """A connector did not do its work. `code`: blocked | timeout | unreachable | no_calendar | failed (or a code its
    module adds). `app`: which app said it ("Reminders", "Calendar"), when it matters. Never holds what was sent."""

    def __init__(self, code, app=None):
        super().__init__(code)
        self.code, self.app = code, app


# 3 of these in a row mark the connector broken (round 9, E adds the HTTP codes: a refused token, the service's own
# error, an address that is gone, a batch only partly taken)
COUNTS_AS_FAILURE = ("blocked", "timeout", "failed", "refused", "server", "gone", "partial")
BREAK_AFTER = 3


@dataclass(frozen=True)
class Connector:
    key: str
    name: str                                   # "Reminders and Calendar on this Mac"
    module: str                                 # the module in actions/ (run, yes_token, remove, check, reachable)
    actions: dict = field(default_factory=dict)  # kind -> action name
    apps: dict = field(default_factory=dict)     # kind -> the app's own short name, for the reply lines
    nouns: dict = field(default_factory=dict)    # action name -> (one, many): ("reminder", "reminders")
    # round 9, E (DESIGN.md section 16.E): connectors by token and a webhook ride on the same code
    kind: str = "mac"                            # mac | token | webhook: which reply lines it uses (texts.py)
    where: str = "on your Mac"                   # where things land, in a reply: "in TickTick", "to your webhook"
    needs_check: bool = True                     # True: unusable until "check my ..." passes once (the Mac's prompts)
    env: tuple = ()                              # the settings it reads (names only; the values never leave os.environ)


CONNECTORS = {
    "mac": Connector(key="mac", name="Reminders and Calendar on this Mac", module="mac",
                     actions={"todo": "mac.reminder", "calendar": "mac.event"},
                     apps={"todo": "Reminders", "calendar": "Calendar"},
                     nouns={"mac.reminder": ("reminder", "reminders"), "mac.event": ("event", "events")}),
    # round 9, E (DESIGN.md section 16.E): a token or an address in the environment is the whole setup, so no check
    # is needed before the first use ("check my ticktick" still tests it, and turns it back on after a failure)
    "ticktick": Connector(key="ticktick", name="TickTick", module="ticktick", actions={"todo": "ticktick.add"},
                          apps={"todo": "TickTick"}, nouns={"ticktick.add": ("task", "tasks")}, kind="token",
                          where="in TickTick", needs_check=False, env=("MVP_TICKTICK_TOKEN", "MVP_TICKTICK_PROJECT")),
    "todoist": Connector(key="todoist", name="Todoist", module="todoist", actions={"todo": "todoist.add"},
                         apps={"todo": "Todoist"}, nouns={"todoist.add": ("task", "tasks")}, kind="token",
                         where="in Todoist", needs_check=False, env=("MVP_TODOIST_TOKEN", "MVP_TODOIST_PROJECT")),
    "webhook": Connector(key="webhook", name="your webhook", module="webhook", actions={"todo": "webhook.post"},
                         apps={"todo": "your webhook"}, nouns={"webhook.post": ("thing", "things")}, kind="webhook",
                         where="to your webhook", needs_check=False, env=("MVP_WEBHOOK_URL",)),
}
# ---------- round 10, slice Y (DESIGN.md section 17.Y): the person's own YouTube, signed in by Google's device flow ---
# kind "oauth": each person connects their own account (a tester too), so `unavailable` reads this person's sign-in
# (yt_auth.py) instead of asking for the operator. Its actions are run by ytreads.py after a yes to the exact list.
CONNECTORS["youtube"] = Connector(key="youtube", name="YouTube", module="youtube",
                                  actions={"playlist": "youtube.playlist_add", "unsubscribe": "youtube.unsubscribe"},
                                  apps={"playlist": "YouTube", "unsubscribe": "YouTube"},
                                  nouns={"youtube.playlist_add": ("video", "videos"),
                                         "youtube.playlist_make": ("playlist", "playlists")},
                                  kind="oauth", where="on YouTube", needs_check=False,
                                  env=("MVP_YT_CLIENT_ID", "MVP_YT_CLIENT_SECRET"))
# ---------- end round 10, slice Y ----------
SECRET_ENV = ("MVP_TICKTICK_TOKEN", "MVP_TODOIST_TOKEN", "MVP_WEBHOOK_URL", "MVP_MAILBOX_APP_PASSWORD")
# ---------- round 10, slice K: the sealing key and the YouTube client's secret (read through settings.secret) ------
SECRET_ENV += ("MVP_TOKEN_KEY", "MVP_YT_CLIENT_SECRET")
# ---------- end round 10, slice K ----------


# ---------- round 10, slice C: Todoist also by its own MCP server, signed in with "Allow" (DESIGN.md 17.C) ----------
# The connector stays "todoist" (the app the person names, connections, placements, grants); the route under it is
# the personal token (actions/todoist.py, todoist.add) when one is set, else the MCP sign-in (actions/mcp.py,
# todoist.mcp_add) when this person has one. MCP_ROUTES: connector -> the MCP action that adds a to-do there.
from dataclasses import replace as _replace  # noqa: E402

MCP_ROUTES = {"todoist": "todoist.mcp_add"}
MCP_STATUSES = ("needs_signin", "changed")   # connection states only an MCP sign-in has
COUNTS_AS_FAILURE += ("protocol", "tool_error", "bad_result")   # an MCP server's own errors count toward 3 in a row
CONNECTORS["todoist"] = _replace(CONNECTORS["todoist"],
                                 nouns={**CONNECTORS["todoist"].nouns, "todoist.mcp_add": ("task", "tasks")})


def mcp_route(store, handle, connector):
    """True when this person's adds to `connector` go through its MCP server: no personal token is set and this
    person has an MCP sign-in sealed."""
    if connector not in MCP_ROUTES or module(connector).reachable():
        return False
    from . import oauth
    return oauth.connected(handle, connector)


def action_module(action):
    """The module in actions/ that runs a registry action (a connector can have more than one route)."""
    from .actions import REGISTRY
    return importlib.import_module(f"mvp.actions.{REGISTRY[action].module}")


def remove_rows(store, connector, rows):
    """Takes out placements, each through the module of the action that made it. {"removed": [...], "failed": [...]}"""
    out = {"removed": [], "failed": []}
    mcp_actions = set(MCP_ROUTES.values())
    rest = [r for r in rows if r.get("action") not in mcp_actions]
    if rest:   # today's route, unchanged: the connector's own module, all rows at once
        mod = module(connector)
        res = mod.remove(rest) if mod.reachable() else {"removed": [], "failed": [r["id"] for r in rest]}
        out["removed"] += res["removed"]
        out["failed"] += res["failed"]
    for action in sorted({r["action"] for r in rows if r.get("action") in mcp_actions}):
        res = action_module(action).remove([r for r in rows if r["action"] == action], store=store)
        out["removed"] += res["removed"]
        out["failed"] += res["failed"]
    return out


def route_for(store, handle, connector, kind):
    """The action name that adds a thing of `kind` ("todo", "calendar", "playlist") through `connector` for this
    person, or None: the MCP action when mcp_route() says so, else the connector's own action (today's route)."""
    con = CONNECTORS.get(connector)
    if not con:
        return None
    if kind == "todo" and store is not None and mcp_route(store, handle, connector):
        return MCP_ROUTES[connector]
    return con.actions.get(kind)
# ---------- end round 10, slice C ----------


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
    # ---------- round 10, slice Y: a connector each person signs in to themselves (kind "oauth": YouTube) ----------
    # Only this kind; the Mac, token, webhook and mailbox routes still answer "operator" for anyone else (M-4).
    if CONNECTORS[key].kind == "oauth":
        if not module(key).reachable():
            return "unreachable"            # no Google client is set up on this bot
        from . import yt_auth
        if not yt_auth.connected(store, handle):
            return "not_connected"
        st = status(store, handle, key)
        return st if st in ("off", "broken") else None
    # ---------- end round 10, slice Y ----------
    if not config.is_operator(handle):
        return "operator"
    # ---------- round 10, slice C: no personal token, but an MCP sign-in may be there ----------
    if key in MCP_ROUTES and not module(key).reachable():
        from .actions import mcp as _mcp
        return _mcp.unavailable(store, handle, key)
    # ---------- end round 10, slice C ----------
    if not module(key).reachable():
        return "unreachable"
    st = status(store, handle, key)
    if st is None:
        return "not_connected" if CONNECTORS[key].needs_check else None
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


# ---------- round 9, E (DESIGN.md section 16.E): a secret typed into the chat (the narrow guard) ----------
# Fires on the name of a secret setting, on "token is" / "api key is" / "app password is" / "password is" (or ":" /
# "=") followed by a run of 16 or more non-space characters, and on an automation service's own webhook address.
# Nothing broader (the critic rejected "four groups of four letters" and "any 32-character run": they hit ordinary
# messages and link tokens).
_SECRET_NAME = re.compile(r"\b(?:" + "|".join(SECRET_ENV) + r")\b", re.I)   # round 10, slice K: from SECRET_ENV
_SECRET_SAID = re.compile(r"\b(?:token|api[\s-]?key|app\s+password|password|passcode)\s*(?:is|=|:)\s*[\"'“‘]?\S{16,}",
                          re.I)
_HOOK_URL = re.compile(r"\bhttps?://(?:maker\.ifttt\.com/(?:trigger|use)/|hooks\.zapier\.com/hooks/|"
                       r"hook\.[a-z0-9-]+\.make\.com/)\S+", re.I)


def secret_said(text):
    """True when a chat message holds (or names) a secret the bot must never take there."""
    t = " ".join((text or "").split())
    return bool(_SECRET_NAME.search(t) or _SECRET_SAID.search(t) or _HOOK_URL.search(t))
