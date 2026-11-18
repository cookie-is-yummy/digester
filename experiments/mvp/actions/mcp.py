"""PROTOTYPE ONLY - adding to the person's own apps through the app's own MCP server (round 10, slice C; DESIGN.md
section 17.C; amendment A-015, Proposed). Todoist first, the operator only (verdict M-3).

Action `todoist.mcp_add` (registry): tasks in the person's Todoist, only after their yes to the exact rows shown
(places.py's preview, the same as the token route), or under a rule's standing yes (slice G's grant). It runs the
mapping of mcp_mappings.py through mcp_client.py with a fresh access token from oauth.py; one action spends at most
MVP_MCP_RUN_BUDGET_S seconds (default 25) on MCP calls (M-11). What the server sends back is read for ids only; every
title in a reply comes from the bot's own params.

The module contract of actions/ (connectors.py): run(ctx, params) -> Outcome(detail={"placed": [...]}),
yes_token(ctx, params), remove(rows, store) (STORE_REMOVE: connectors.remove_rows passes the store, which holds the
pins), check() and reachable(). And the conversation, called from places.py's token reads:
  connect_reply     "connect my todoist": the sign-in link (operator), the tester line, the key line
  on_code           the loopback page got the person back: seal the sign-in, pin the tools, say it is connected
  check_reply       "check my todoist": the tools are listed again and compared with the pins
  disconnect_reply  "disconnect todoist": stop adding, void the app's grants, REMOVE/KEEP, revoke, delete the sign-in
  disconnect_answer the REMOVE / KEEP after it (and the end of the disconnect whatever the next message is)
  yes_again         "yes todoist" after a changed tool: pin again (the old grants stay void)
  unavailable       connectors.unavailable's MCP branch
  signin_line_once  the "sign in again" line at most once a day, for a rule run that fell back (slice G)
State: pins:<connector>:<handle> ({tool: fingerprint}), oauthpending:<handle>, signinnote:<connector>:<handle>.
"""
import time
from datetime import datetime, timedelta

from .. import config, mcp_client, oauth, tokens
from .. import connectors as C
from .. import texts as T
from ..mcp_client import McpError
from ..mcp_mappings import MAPPINGS, SERVERS
from . import _tasks
from .base import Outcome

ACTION = "todoist.mcp_add"
STORE_REMOVE = True
LOOK_BACK = timedelta(days=30)
REMOVE_OPEN = timedelta(minutes=30)
_LAST_STORE = {"it": None}   # remove(rows) without a store (an older caller): the store the last run used


def _app(key):
    return SERVERS[key]["app"]


def _now_iso(now):
    from ..store import now_iso
    return now_iso(now)


def _mapping_of(key):
    return next(m for m in MAPPINGS.values() if m.server == key)


# ---------- pins ----------
def pins_key(key, handle):
    return f"pins:{key}:{handle}"


def get_pins(store, key, handle):
    return (store.get_state(pins_key(key, handle)) or {}).get("tools") or {}


def _set_pins(store, key, handle, pins, now):
    store.set_state(pins_key(key, handle), {"tools": pins, "at": _now_iso(now)} if pins else None)


# ---------- one person's server, with a fresh token ----------
def with_server(store, handle, key, fn, deadline=None):
    """fn(transport) with this person's access token. A 401 means the server did nothing: one refresh, one retry."""
    conf = SERVERS[key]
    tok = oauth.access_token(handle, key)
    try:
        return fn(mcp_client.transport_for(conf, tok))
    except McpError as e:
        if e.code != "auth":
            raise
    if deadline is not None and deadline - time.monotonic() <= 0:
        raise McpError("timeout")
    tok2 = oauth.access_token(handle, key, refused=tok)
    try:
        return fn(mcp_client.transport_for(conf, tok2))
    except McpError as e:
        if e.code == "auth":
            raise McpError("refused") from None
        raise


def _mark(store, handle, key, code, now):
    """What an error means for the connection: needs_signin and changed stop the route until the person acts;
    changed also voids every grant on the app (the yes was to what the app did then)."""
    if code == "needs_signin":
        store.set_connection(handle, key, status="needs_signin", last_error=code, at=now)
    elif code in ("changed", "unpinned"):
        store.set_connection(handle, key, status="changed", last_error=code, at=now)
        store.end_grants(handle, connector=key, reason="changed", at=now)
        store.log_action(handle, None, None, "pins.changed", "done", detail={"connector": key}, at=now)


def deadline_now():
    return time.monotonic() + mcp_client.run_budget()


# ---------- the action ----------
def reachable():
    """The MCP route needs a person's sign-in, which is checked per person (connectors.unavailable)."""
    return True


def yes_token(ctx, params):
    return _tasks.yes_token("todoist.mcp", ctx, params)


def run(ctx, params):
    return run_mapped(ACTION, ctx, params)


def run_mapped(action, ctx, params):
    m = MAPPINGS[action]
    key, h, store = m.server, ctx.handle, ctx.store
    _LAST_STORE["it"] = store
    now = ctx.now if ctx.now is not None else ctx.bot.clock()
    pins = get_pins(store, key, h)
    try:
        if not pins:
            raise McpError("unpinned")
        dl = deadline_now()
        ids = with_server(store, h, key, lambda t: mcp_client.call_mapped(t, pins, m, params, ctx, dl), dl)
    except McpError as e:
        _mark(store, h, key, e.code, now)
        raise McpError(e.code, _app(key), maybe_arrived=e.maybe_arrived) from None
    return Outcome("done", detail={"placed": [{"action": action, "remote_id": i} for i in ids], "count": len(ids),
                                   "route": "mcp"})


def remove(rows, store=None):
    """{"removed": [placement ids], "failed": [...]}; a task already gone counts as removed."""
    store = store or _LAST_STORE["it"]
    out = {"removed": [], "failed": []}
    if not rows:
        return out
    if store is None:
        out["failed"] = [r["id"] for r in rows]
        return out
    by = {}
    for r in rows:
        by.setdefault((r["handle"], r["action"]), []).append(r)
    for (h, action), group in by.items():
        m = MAPPINGS.get(action)
        pins = get_pins(store, m.server, h) if m else {}
        if not m or not pins:
            out["failed"] += [r["id"] for r in group]
            continue
        try:
            dl = deadline_now()
            rids = [r["remote_id"] for r in group]
            res = with_server(store, h, m.server,
                              lambda t, p=pins, mp=m, ids=rids, d=dl: mcp_client.undo_ids(t, p, mp, ids, d), dl)
        except McpError as e:
            _mark(store, h, m.server, e.code, datetime.now().astimezone())
            out["failed"] += [r["id"] for r in group]
            continue
        for r in group:
            out["removed" if res.get(r["remote_id"]) in ("removed", "gone") else "failed"].append(r["id"])
    return out


def check():
    raise C.ConnectorError("unreachable", "Todoist")   # per person: check_reply


# ---------- connectors.unavailable's branch ----------
def unavailable(store, handle, key):
    """None when this person's MCP sign-in can be used now; else why not."""
    if not oauth.connected(handle, key):
        return "unreachable"
    row = store.connection(handle, key) or {}
    st = row.get("status")
    if st in ("off", "broken") or st in C.MCP_STATUSES:
        return st
    if st != "connected" or not get_pins(store, key, handle):
        return "unreachable"
    return None


def signin_line_once(store, handle, key, now):
    """The "sign in again" line, at most once a local day per person and app; "" when it was said today."""
    day = now.strftime("%Y-%m-%d")
    k = f"signinnote:{key}:{handle}"
    if store.get_state(k) == day:
        return ""
    store.set_state(k, day)
    return T.mcp_needs_signin(_app(key), key)


# ---------- the conversation ----------
def _key_ok():
    """False when no sign-in can be sealed: no key and none may be made, or a key that cannot be used."""
    if tokens.key_source() is None:
        return tokens.can_make_key()
    try:
        tokens.key(create=False)
        return True
    except tokens.TokenError:
        return False


def connect_reply(bot, person, key, now):
    """'connect my todoist'. None: the token route answers (a personal token is set)."""
    h, app = person["handle"], _app(key)
    if not config.is_operator(h):
        bot.store.log_request(h, f"connect {key}", f"wanted:{key}")
        return bot.send(h, T.mcp_tester(app))
    if C.module(key).reachable():
        return None
    if not _key_ok():
        return bot.send(h, T.MCP_NO_KEY)
    row = bot.store.connection(h, key) or {}
    if oauth.connected(h, key) and row.get("status") == "connected" and get_pins(bot.store, key, h):
        return bot.send(h, T.mcp_already(app, key))
    try:
        port = oauth.connect_port()
        listener = oauth.ensure_listener(lambda s, c, i, e: on_code(bot, s, c, i, e), port)
        link = oauth.start(h, key, listener.port)
    except oauth.OAuthError as e:
        bot.store.log_action(h, None, None, f"connect.{key}", "failed", detail={"error": e.code}, at=now)
        return bot.send(h, T.mcp_connect_failed(app, e.code, key))
    bot.store.set_state(f"oauthpending:{h}", {"connector": key, "at": _now_iso(now)})
    bot.store.log_action(h, None, None, f"connect.{key}", "waiting", detail={"route": "loopback"}, at=now)
    return bot.send(h, T.mcp_connect_link(app, link, key))


def on_code(bot, state, code, iss, error):
    """The loopback page got the person back from the sign-in. True when the app is connected."""
    now = bot.clock()
    try:
        h, key = oauth.finish(state, code, iss, error)
    except oauth.OAuthError as e:
        p = getattr(e, "pending", None)
        if p:
            bot.store.set_state(f"oauthpending:{p['handle']}", None)
            bot.store.log_action(p["handle"], None, None, f"connect.{p['key']}", "failed", detail={"error": e.code},
                                 at=now)
            bot.send(p["handle"], T.mcp_signin_failed(_app(p["key"]), e.code, p["key"]))
        return False
    app = _app(key)
    bot.store.set_state(f"oauthpending:{h}", None)
    try:
        pins = with_server(bot.store, h, key, lambda t: mcp_client.pin(t, _mapping_of(key), deadline_now()))
    except McpError as e:
        oauth.revoke(h, key)
        tokens.delete(h, key)
        bot.store.log_action(h, None, None, f"connect.{key}", "failed", detail={"error": e.code}, at=now)
        bot.send(h, T.mcp_pin_failed(app) if e.code in ("unpinned", "changed") else
                 T.mcp_signin_failed(app, e.code, key))
        return False
    _set_pins(bot.store, key, h, pins, now)
    bot.store.set_connection(h, key, status="connected", fails=0, last_error="", at=now, checked=True)
    bot.store.log_action(h, None, None, f"connect.{key}", "done", detail={"route": "loopback", "tools": len(pins)},
                         at=now)
    bot.send(h, T.mcp_connected(app, key))
    return True


def check_reply(bot, person, key, now):
    """'check my todoist' on the MCP route. None: not this route (the token route answers)."""
    h, app = person["handle"], _app(key)
    if C.module(key).reachable() or not oauth.connected(h, key):
        return None
    store = bot.store
    pins = get_pins(store, key, h)
    try:
        if not pins:
            raise McpError("changed")
        gone = with_server(store, h, key, lambda t: mcp_client.changed_pins(t, pins, deadline_now()))
        if gone:
            raise McpError("changed")
    except McpError as e:
        _mark(store, h, key, e.code, now)
        if e.code in ("changed", "unpinned"):
            return bot.send(h, T.mcp_changed(app, key))
        if e.code == "needs_signin":
            return bot.send(h, T.mcp_needs_signin(app, key))
        C.failed(store, h, key, e.code, now)
        return bot.send(h, T.token_check_failed(e.code, app, key))
    row = store.connection(h, key) or {}
    if row.get("status") == "changed":   # only "yes todoist" takes a change back
        return bot.send(h, T.mcp_changed(app, key))
    store.set_connection(h, key, status="connected", fails=0, last_error="", at=now, checked=True)
    for g in store.grants_of(h, key, active_only=False):
        if g["status"] == "paused":
            store.resume_grant(g["id"])
    return bot.send(h, T.mcp_checked(app))


def _rules_on(store, h, key, reason):
    return sum(1 for g in store.grants_of(h, key, active_only=False) if g.get("end_reason") == reason)


def disconnect_reply(bot, person, key, now):
    """'disconnect todoist' when an MCP sign-in is kept. None: no sign-in here (the token route answers)."""
    h, app = person["handle"], _app(key)
    store = bot.store
    if not oauth.connected(h, key):
        return None
    oauth.drop_pending(h)
    store.set_state(f"oauthpending:{h}", None)
    store.set_connection(h, key, status="off", at=now)
    if store.person_context(h)["prefs"].get("place_todo") == key:
        store.set_prefs(h, place_todo=None)
    rules = store.end_grants(h, connector=key, reason="disconnect", at=now)
    mcp_actions = {a for a, m in MAPPINGS.items() if m.server == key}
    rows = [r for r in store.placements(h, key, since=now - LOOK_BACK) if r["action"] in mcp_actions]
    if rows:
        store.set_state(f"placeremove:{h}", {"at": _now_iso(now), "connector": key, "ids": [r["id"] for r in rows],
                                             "mcp_disconnect": True, "rules": rules})
        return bot.send(h, T.mcp_off_ask(app, len(rows)))
    revoked = _finish_disconnect(store, h, key, now, 0)
    return bot.send(h, T.mcp_off(app, revoked, rules))


def _finish_disconnect(store, h, key, now, removed):
    revoked = oauth.revoke(h, key)
    tokens.delete(h, key)
    _set_pins(store, key, h, None, now)
    store.log_action(h, None, None, f"disconnect.{key}", "done", detail={"revoked": revoked, "removed": removed}, at=now)
    return revoked


def disconnect_answer(bot, person, st, text, now):
    """The message after "disconnect todoist" asked REMOVE or KEEP. Whatever it is, the disconnect ends here (the
    sign-in is revoked and deleted); None when the message was not an answer (it is then handled as usual)."""
    from ..places import KEEP, REMOVE
    h, key = person["handle"], st["connector"]
    store = bot.store
    store.set_state(f"placeremove:{h}", None)
    fresh = now - datetime.fromisoformat(st["at"]) <= REMOVE_OPEN
    if fresh and REMOVE.match(text):
        bot.note(intent="place_remove")
        rows = store.placements(h, ids=st.get("ids") or [])
        res = remove(rows, store=store) if rows else {"removed": [], "failed": []}
        store.remove_placements(res["removed"], now)
        revoked = _finish_disconnect(store, h, key, now, len(res["removed"]))
        return bot.send(h, T.mcp_off_done(_app(key), len(res["removed"]), len(res["failed"]), revoked))
    if fresh and KEEP.match(text):
        bot.note(intent="place_keep")
        revoked = _finish_disconnect(store, h, key, now, 0)
        return bot.send(h, T.mcp_off_done(_app(key), None, 0, revoked))
    _finish_disconnect(store, h, key, now, 0)
    return None


def yes_again(bot, person, key, now):
    """'yes todoist' after the app changed a tool: pin what it offers now. None when nothing is waiting for it."""
    h, app = person["handle"], _app(key)
    store = bot.store
    row = store.connection(h, key) or {}
    if row.get("status") != "changed" or not oauth.connected(h, key):
        return None
    bot.note(intent="places")
    try:
        pins = with_server(store, h, key, lambda t: mcp_client.pin(t, _mapping_of(key), deadline_now()))
    except McpError as e:
        if e.code == "needs_signin":
            _mark(store, h, key, e.code, now)
            return bot.send(h, T.mcp_needs_signin(app, key))
        if e.code in ("unpinned", "changed"):
            _drop(store, h, key, now)
            return bot.send(h, T.mcp_pin_failed(app))
        return bot.send(h, T.token_check_failed(e.code, app, key))
    _set_pins(store, key, h, pins, now)
    store.set_connection(h, key, status="connected", fails=0, last_error="", at=now, checked=True)
    store.log_action(h, None, None, "pins.approved", "done", detail={"connector": key, "tools": len(pins)}, at=now)
    return bot.send(h, T.mcp_yes_again(app, key, _rules_on(store, h, key, "changed")))


def _drop(store, h, key, now):
    """The app no longer offers what the bot knows: the sign-in is revoked and deleted, the connection is off."""
    store.set_connection(h, key, status="off", at=now)
    _finish_disconnect(store, h, key, now, 0)
