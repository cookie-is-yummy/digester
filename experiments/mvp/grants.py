"""PROTOTYPE ONLY - rules that add to the person's own apps with one yes per rule (round 10, slice G; DESIGN.md section
17.G; amendment A-015, Proposed).

The founder's decision (17 Nov): a timed rule that adds to the person's own apps needs one yes, when the rule is made.
So a rule may carry a place (`RuleSpec.place`, set by code from the person's own words, never from a model form or a
caption), and the YES that starts it makes one grant (store table `grants`): this rule, this action, this app, this
list, these two caps, and a hash of the rule as it was shown. Each run then adds through `actions.perform(...,
grant=g)`, which runs only when every part of the grant fits (`check`), and the run's message always says what was
added, with "undo". Anything that changes the rule, the app's settings or the account ends the grant: a new yes on a
new preview is the only way back.

Never under a grant: a webhook (no undo), the mailbox (it sends), anything that reaches another person (an email to
someone else from a rule is refused with its own line), and every action whose registry entry has rule_grant False.

Routes this round: TickTick and Todoist by the operator's token, Reminders and Calendar on the operator's Mac. Slices C
and Y add routes on the same grant through `connectors.route_for` and their own registry entries.
"""
import hashlib
import json
import re
from datetime import timedelta

from . import connectors as C
from . import texts as T
from .store import now_iso

PAUSE_AFTER = 3                          # failed runs in a row before a grant pauses
RULE_UNDO_WINDOW = timedelta(hours=24)   # "undo" takes out a rule's last adds this long after the run
RULE_UNDO_DAYS = timedelta(days=7)       # "undo rule 3" reaches back this far
SAME_SLOT = timedelta(days=7)            # a retried slot never adds twice within this
KIND_OF = {"todo.add": "todo", "calendar.add": "calendar",
           "youtube.playlist_add": "playlist"}   # second merge of round 10 (Y4): outputs.deliver adds it for a playlist
MAX_PER_RUN = 5                          # a rule sends 1 to 5 picks; its per_run follows its count
# what the person types to connect, check, or name the place in "use X for rule 3"
CONNECT_WORD = {"mac": "my mac", "ticktick": "ticktick", "todoist": "todoist", "youtube": "youtube"}
CHECK_WORD = {"mac": "mac", "ticktick": "ticktick", "todoist": "todoist", "youtube": "youtube"}
USE_WORD = {"mac_reminders": "reminders", "mac_calendar": "my mac calendar", "ticktick": "ticktick",
            "todoist": "todoist", "youtube_playlist": "my youtube playlist"}
TIMED = ("schedule", "random")
PLAYLIST_DEFAULT = "From my saves"       # second merge of round 10 (Y4): the private playlist a rule adds to unnamed


class GrantRefused(Exception):
    """Raised as actions.Refused (below) with a code only: never a title, a list name or an address."""


def _refused(code):
    from .actions import Refused
    return Refused(f"grant:{code}")


# ---------- the place a rule names, read from the person's own words ----------
# "in my ticktick", "into todoist", "to my apple reminders", "on my mac calendar". "to" and "on" need "my" or "our":
# "a guide to notion" and "tips on todoist" name a topic, not a place (M-7).
_VERB = r"\b(?:put|add|save|drop|send|push|move|stick|place|copy|log|throw|schedule|block|pop|dump)\b"
_RULE_PREP = r"\b(?:(?:in|into|onto)\s+(?:my\s+|the\s+|our\s+|a\s+)?|(?:to|on)\s+(?:my|our|a)\s+)"
# checks of round 10 (reading): Spanish ("cada domingo pon 3 recetas en mi ticktick")
_VERB = _VERB[:-3] + r"|pon|ponme|pone|poner|agrega|agr[eé]game|a[nñ]ade|a[nñ][aá]deme|mete|guarda|manda)\b"
_RULE_PREP = _RULE_PREP[:-1] + r"|(?:en|a)\s+(?:mi|mis|el|la)\s+)"


def _rule_rx(p):
    from .places import _TAIL
    return re.compile(_RULE_PREP + p.words + _TAIL, re.I)


def rule_named(text):
    """The place the person's request names for a rule's picks (stricter than places.named), or None."""
    from .places import PLACES, _BARE_REMINDERS
    t = " ".join((text or "").split())
    if not re.search(_VERB, t, re.I):
        return None
    for p in PLACES:
        if _rule_rx(p).search(t) or (p.key == "mac_reminders" and _BARE_REMINDERS.search(t)):
            return p
    return None


def _app(p):
    return p.app


def _use_word(p):
    """What the person says in "use X for rule N" when it differs from the connect word (second merge of round 10:
    "connect youtube", then "use my youtube playlist for rule 1"); None: the connect word."""
    return USE_WORD.get(p.key) if p.connector == "youtube" else None


def email_who(text):
    """Who an email in a rule's request is to, in the person's own words ("my team", "my landlord"), for the M-14
    line; "them" when no such words are found. Never an address."""
    from .drafts import OTHER_RE
    m = OTHER_RE.search(text or "")
    return m.group(0).lower() if m else "them"


def _names_place(list_name, p):
    from .schema import list_name as norm
    ln = norm(list_name) if list_name else None
    return bool(ln) and (ln in p.names or ln == p.key or ln == (p.connector or ""))


def next_number(store, handle):
    """The number the person's next rule will get (rules are numbered by the store, never reused)."""
    r = store.one("SELECT COALESCE(MAX(number), 0) AS n FROM rules WHERE handle=?", (handle,))
    return int(r["n"] if r else 0) + 1


def _target(p, list_name=None, text=""):
    """The list, calendar or playlist inside the app: None means the app's own default (Inbox, default list)."""
    if p.kind == "calendar":
        from .actions import mac
        return mac.CALENDAR if p.connector == "mac" else None
    if p.kind == "playlist":
        m = re.search(r"\bplaylist\s+(?:called|named)\s+([\w' -]{1,40})", text or "", re.I) or \
            re.search(r"\bmy\s+([\w' -]{1,40}?)\s+playlist\b", text or "", re.I)
        name = m.group(1).strip() if m else ""
        if re.fullmatch(r"(?:(?:my|a|the|private|new)\s+)*(?:youtube|yt)?", name, re.I):
            return None   # second merge of round 10: "my youtube playlist" names no playlist (Y4 uses its default)
        return name.title()[:80]
    if p.connector == "mac" and list_name and not _names_place(list_name, p):
        from .places import _app_list
        return _app_list(list_name, None, p)
    return None   # token apps: the Inbox, or the project in the settings


def _strip_place_todos(spec, p):
    """The model's todo.add for this app is dropped: the picks stay in the message instead. Live, the interpreter
    reads "put them in my ticktick" as a todo.add with no list (the list here): that one goes too, since the person
    named the app, not the list here."""
    if p.kind != "todo":
        return

    def for_app(a):
        lst = (a.params or {}).get("list")
        return a.action == "todo.add" and (not lst or lst == "todo" or _names_place(lst, p))
    keep = [a for a in spec.do if not for_app(a)]
    if keep != spec.do:
        from .schema import Action
        spec.do = keep or [Action()]


def _ensure_do(spec, p):
    """The todo.add or calendar.add the place needs, added by code (validated as a code-made rule action)."""
    from .actions import validate_action
    from .schema import Action
    name = "todo.add" if p.kind == "todo" else "calendar.add" if p.kind == "calendar" else None
    if name is None:
        return
    word = p.names[0] if p.names else p.key
    do = []
    have = False
    for a in spec.do:
        if a.action == name:
            have = True
            params = dict(a.params or {})
            if name == "todo.add":
                params["list"] = word
            validate_action(name, params, by="code", where="rule")
            do.append(Action.model_validate({"action": name, "params": params}))
        else:
            do.append(a)
    if not have:
        params = {"list": word} if name == "todo.add" else {}
        validate_action(name, params, by="code", where="rule")
        do.insert(0, Action.model_validate({"action": name, "params": params}))
    spec.do = do[:4]


def _per_run(spec, p):
    if p.kind == "calendar":
        return 1
    return max(1, min(MAX_PER_RUN, int(spec.content.count or 1)))


def _per_day(action):
    from .actions import REGISTRY
    cap = REGISTRY[action].max_per_day
    return min(10, cap) if cap else 10


def route_of(store, handle, p):
    """The registry action that adds through this place for this person, when a rule may use it under a grant."""
    from .actions import REGISTRY
    if not p.connector or p.connector not in C.CONNECTORS:
        return None
    action = C.route_for(store, handle, p.connector, p.kind)
    d = REGISTRY.get(action) if action else None
    return action if d is not None and d.rule_grant else None


def rule_place(store, handle, text, spec, to_other=False, who=None, when_words="", number=None):
    """G1, after the interpreter's new_rule: reads the place from the person's whole request (never from a caption or
    a model form) and sets `spec.place` and the do it needs when the place can be used under a grant now. Returns a
    note for the preview or the start line, or None when the request names no place:
      {"status": "grant", "place", "action", "lines", "yes", "app"}
      {"status": "unusable" | "no_route" | "not_timed" | "email_other", "line", "app"}"""
    spec.place = None
    if to_other:
        return {"status": "email_other", "line": T.rule_email_other(when_words, who or "them"), "app": None}
    if spec.content.source not in ("library", "recent"):
        return None
    p = rule_named(text)
    if p is None:   # the model's own list name, only when the person's words name that app too
        from .places import PLACES
        for a in spec.do:
            if a.action == "todo.add":
                hit = next((x for x in PLACES if _names_place((a.params or {}).get("list"), x)), None)
                if hit and re.search(r"\b" + hit.words + r"\b", text or "", re.I):
                    p = hit
                    break
    if p is None:
        return None
    app = _app(p)
    if spec.when.type not in TIMED:
        _strip_place_todos(spec, p)
        return {"status": "not_timed", "line": T.place_not_timed(app), "app": app}
    action = route_of(store, handle, p)
    if action is None:
        _strip_place_todos(spec, p)
        return {"status": "no_route", "line": T.place_no_route(app), "app": app}
    why = C.unavailable(store, handle, p.connector)
    if why:
        _strip_place_todos(spec, p)
        return {"status": "unusable", "app": app, "why": why,
                "line": T.place_unusable(app, CONNECT_WORD.get(p.connector, p.connector),
                                         number or next_number(store, handle), why=why, use=_use_word(p))}
    model_list = next(((a.params or {}).get("list") for a in spec.do if a.action == "todo.add"), None)
    from .schema import RulePlace
    target = _target(p, model_list, text)
    if p.kind == "playlist" and not target:
        target = PLAYLIST_DEFAULT   # second merge of round 10 (Y4): a playlist always has a name the preview shows
    spec.place = RulePlace(connector=p.connector, kind=p.kind, target=target,
                           per_run=_per_run(spec, p), per_day=_per_day(action))
    _ensure_do(spec, p)
    lines, yes = note_lines(store, handle, spec)
    return {"status": "grant", "place": p, "action": action, "lines": lines, "yes": yes, "app": app}


def place_of(spec):
    """The places.Place a stored spec's place stands for."""
    from .places import PLACES
    pl = spec.place
    if pl is None:
        return None
    return next((p for p in PLACES if p.connector == pl.connector and p.kind == pl.kind), None)


def note_lines(store, handle, spec):
    """(the G3 lines, the YES line) for a spec with a place."""
    p = place_of(spec)
    pl = spec.place
    con = C.CONNECTORS.get(pl.connector)
    action = route_of(store, handle, p) if p else None
    many = con.nouns.get(action, ("thing", "things"))[1] if con and action else "things"
    project = False
    if con and con.kind == "token":
        from .settings import secret
        project = bool(next((secret(n) for n in con.env if n.endswith("_PROJECT")), None))
    w = spec.when
    daily = w.every_days == 1 or (w.type == "schedule" and not (w.days or w.month_days or w.month_weeks or w.every_weeks
                                                                or w.every_months or w.every_days))
    each = "each time" if len(w.times) > 1 or w.every_hours or w.type == "random" else T.grant_each(w.days, daily)
    if pl.kind == "playlist":   # second merge of round 10 (Y4): slice Y's own preview line (T.yt_rule_place)
        return ("\n" + T.yt_rule_place(pl.target or PLAYLIST_DEFAULT, pl.per_run, each, pl.per_day)
                + "\nEach time I'll tell you here what I added, and you can say \"undo\".",
                "\nReply YES to start and let me add them")
    return T.place_grant_note(_app(p) if p else pl.connector, T.grant_where(pl.kind, _app(p) if p else "", pl.target,
                                                                              project),
                              T.grant_thing(pl.kind, many), pl.per_run, each, pl.per_day,
                              calendar=pl.kind == "calendar", youtube=pl.connector == "youtube")


def strip_place(spec):
    """The spec without its place and the add it needed (a rule that starts with no grant sends here only)."""
    p = place_of(spec)
    spec.place = None
    if p is not None:
        _strip_place_todos(spec, p)
    return spec


# ---------- the grant: made by the yes, checked at every add ----------
def pins_of(store, handle, connector):
    """The pinned tools of a connector for this person (slice C keeps them in state `pins:<connector>:<handle>`);
    None for the routes that have none (token, Mac)."""
    return store.get_state(f"pins:{connector}:{handle}")


def account_hint(connector):
    """A short hash that changes when the account behind a connector changes (a new token or project for a token
    app; a module may give its own `account_hint()`). Never the value itself."""
    con = C.CONNECTORS.get(connector)
    if con is None:
        return None
    try:
        mod = C.module(connector)
    except Exception:  # noqa: BLE001
        mod = None
    own = getattr(mod, "account_hint", None)
    if callable(own):
        return own()
    if con.kind == "token":
        from .settings import secret
        vals = "|".join(secret(n) or "" for n in con.env)
        return hashlib.sha256(vals.encode("utf-8")).hexdigest()[:16]
    return None


def scope_hash(spec, connector, action, target, per_run, per_day, pins=None, hint=None):
    """The hash of what the yes was given for: the rule as shown (its timing, content, do and place; not whether it
    stays quiet on an empty day), the app, the action, the list, the caps, the app's pinned tools and the account."""
    d = spec.stored()
    d.get("when", {}).pop("if_empty", None)
    blob = json.dumps([d, connector, action, target, per_run, per_day, pins, hint], sort_keys=True, ensure_ascii=False,
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def scope_now(store, handle, spec, connector, action, target, per_run, per_day):
    return scope_hash(spec, connector, action, target, per_run, per_day, pins_of(store, handle, connector),
                      account_hint(connector))


def make(store, handle, rule_id, spec, now):
    """G2: the grant the YES that starts (or changes) a rule makes, only when the place can be used now. Returns
    (grant id, None) or (None, why)."""
    pl = spec.place
    if pl is None:
        return None, None
    p = place_of(spec)
    action = route_of(store, handle, p) if p else None
    if action is None:
        return None, "no_route"
    why = C.unavailable(store, handle, pl.connector)
    if why:
        return None, why
    store.end_grants(handle, rule_id=rule_id, reason="replaced", at=now)
    scope = scope_now(store, handle, spec, pl.connector, action, pl.target, pl.per_run, pl.per_day)
    return store.add_grant(handle, rule_id, pl.connector, action, pl.target, pl.per_run, pl.per_day, scope, at=now), None


def target_of(params):
    name = type(params).__name__
    if name == "MacEventParams":
        return params.calendar
    if hasattr(params, "list"):
        return params.list
    return getattr(params, "target", None)


def _items_of(params):
    items = getattr(params, "items", None)
    return len(items) if items is not None else 1


def added_today(store, handle, rule_id, action, now, tz):
    from .actions import local_day_bounds
    start, end = local_day_bounds(now, tz)
    r = store.one("SELECT COUNT(*) AS n FROM placements WHERE handle=? AND rule_id=? AND action=? AND created_at>=? "
                  "AND created_at<?", (handle, int(rule_id), action, now_iso(start), now_iso(end)))
    return int(r["n"]) if r else 0


def check(name, ctx, params, grant):
    """actions.perform's grant check: raises actions.Refused unless the action may run under a grant and every part
    of this grant fits this call. Reads the grant and the rule again from the store (never a copy the caller holds)."""
    from .actions import REGISTRY
    from .schema import RuleSpec
    d = REGISTRY.get(name)
    if d is None or not d.rule_grant:
        raise _refused("action")
    store = ctx.store
    gid = grant.get("id") if isinstance(grant, dict) else grant
    g = store.grant(gid) if gid is not None else None
    if g is None or g["status"] != "active":
        raise _refused("status")
    if g["handle"] != ctx.handle or ctx.rule_id is None or int(g["rule_id"]) != int(ctx.rule_id) or g["action"] != name:
        raise _refused("who")
    rule = store.rule(g["rule_id"])
    if not rule or rule["handle"] != ctx.handle or rule["status"] != "active":
        raise _refused("rule")
    spec = RuleSpec.model_validate(rule["spec"])
    pl = spec.place
    if pl is None or pl.connector != g["connector"] or pl.target != g["target"] or pl.per_run != g["per_run"] \
            or pl.per_day != g["per_day"]:
        raise _refused("scope")
    if scope_now(store, ctx.handle, spec, g["connector"], name, g["target"], g["per_run"], g["per_day"]) \
            != g["scope_hash"]:
        raise _refused("scope")
    if target_of(params) != g["target"]:
        raise _refused("target")
    n = _items_of(params)
    if n > int(g["per_run"]):
        raise _refused("per_run")
    tz = (ctx.person or {}).get("timezone") or ctx.tz or "America/New_York"
    now = ctx.now if ctx.now is not None else ctx.bot.clock()
    if added_today(store, ctx.handle, g["rule_id"], name, now, tz) + n > int(g["per_day"]):
        raise _refused("per_day")


# ---------- each run (G4): the add under the grant, and the line that always says what it added ----------
def _strong(bot, person, pick):
    if pick.get("caption_mark") == "strong" or pick.get("cm") == "strong":   # merge of round 10: slice S's level
        return True                                                           # (what the person said included)
    try:
        from . import captionmark
        it = bot.view(person["library"]).get(pick.get("item_id"))
        if it is None:
            return False
        # review of the round 10 merge: the level with what the person said (slice S's effective, design C2), not the
        # library's mark alone: "that one was fine" puts a reel back; "nothing to do with it" leaves one out
        fb = captionmark.index(bot.store.caption_feedback(person["handle"]))
        return captionmark.effective(it, fb)[0] == "strong"
    except Exception:  # noqa: BLE001 - a mark that cannot be read is no mark (today's behaviour)
        return False


def run_place(bot, ctx, name, params):
    """places.route for a timed run of a rule with a place (todo.add or calendar.add). None: the rule has no place
    of this kind (today's path). Else the Outcome to log under `name`: what was added (with the line), or why not."""
    from .actions import CalendarParams, MacEventParams, PlaceTodoParams, Refused, TodoParams, perform
    from .actions import todo as todo_action
    from .actions.base import Outcome
    from .schema import RuleSpec
    if ctx.kind != "scheduled" or not ctx.rule_id or name not in KIND_OF:
        return None
    store, h = bot.store, ctx.handle
    rule = store.rule(ctx.rule_id)
    if not rule or rule["handle"] != h:
        return None
    spec = RuleSpec.model_validate(rule["spec"])
    pl, p = spec.place, place_of(spec)
    if pl is None or p is None or pl.kind != KIND_OF[name]:
        return None
    n = store.rule_number(h, rule["id"])
    app = _app(p)
    action = route_of(store, h, p)
    g = store.grant_for(h, rule["id"], action) if action else None
    if g is None and action:
        # ---------- review of the round 10 merge: the route under the app changed since the yes ----------
        # (a token set after a Todoist sign-in, or the other way round): the yes was for the other route, so nothing
        # is added; that grant ends and the person is told once, with the words that ask again
        old = [x for x in store.grants_of(h, pl.connector, active_only=False)
               if x["status"] != "ended" and int(x["rule_id"]) == int(rule["id"]) and x["action"] != action]
        if old:
            store.end_grants(h, rule_id=rule["id"], connector=pl.connector, reason="route_changed", at=ctx.now)
            return Outcome("skipped", line=T.grant_route_changed(_app(p), USE_WORD.get(p.key, p.key), n),
                           detail={"grant": "route_changed"})
        # ---------- end review of the round 10 merge ----------
    if g is None or g["status"] != "active":
        # no standing yes now (it ended, or paused after failures, and the person was told then): the picks are in
        # the message only, and nothing goes to the app or to the list here
        return Outcome("skipped", line="", detail={"grant": (g or {}).get("status") or "none"})
    now, tz = ctx.now, (ctx.person or {}).get("timezone") or ctx.tz
    con = C.CONNECTORS[pl.connector]
    one, many = con.nouns.get(action, ("thing", "things"))
    more = 0
    if pl.kind == "todo":
        tp = TodoParams.model_validate(params or {})
        picks = [x for x in ctx.picks if not _strong(bot, ctx.person, x)]   # S3: a strong-marked reel is never placed
        left_out = len(ctx.picks) - len(picks)   # merge of round 10: said with slice S's line (T.cm_left_out)
        rows, problem = todo_action.rows_for(picks, tp.what) if picks else ([], "none")
        if problem or not rows:
            return Outcome("skipped", line=T.cm_left_out(left_out) if left_out else "",
                           detail={"grant_id": g["id"], "why": problem or "none"})
        keep = rows[:int(g["per_run"])]
        more = len(rows) - len(keep)
        left = int(g["per_day"]) - added_today(store, h, rule["id"], action, now, tz)
        if left <= 0:
            return Outcome("skipped", line=T.grant_day_full(app, n, g["per_day"]), detail={"grant_id": g["id"],
                                                                                       "why": "per_day"})
        more += max(0, len(keep) - left)
        keep = keep[:left]
        out = PlaceTodoParams(list=g["target"], items=[{"title": t[:200], "notes": url or "", "due": None}
                                                       for t, iid, url, due in keep])
        titles = [i.title for i in out.items]
        keys = [r[1] or r[0] for r in keep]
    elif pl.kind == "playlist":
        # ---------- second merge of round 10, Y4: the run's YouTube picks go to the private playlist; an Instagram
        # pick is counted and never placed; a video id comes only from the library's own YouTube item ----------
        from .actions import YtPlaylistAdd
        from .ytreads import video_id_of
        picks = [x for x in ctx.picks if not _strong(bot, ctx.person, x)]
        left_out = len(ctx.picks) - len(picks)
        view = bot.view(ctx.person["library"])
        videos, seen = [], set()
        for x in picks:
            it = view.get(x.get("item_id"))
            vid = video_id_of(it) if it is not None else None
            if vid and vid not in seen:
                seen.add(vid)
                videos.append({"video_id": vid, "title": (x.get("title") or vid)[:200]})
        ig_left = len(picks) - len(videos)
        extra = T.yt_rule_ig_left(ig_left) if ig_left else ""
        if not videos:
            line = " ".join(x for x in (extra, T.cm_left_out(left_out) if left_out else "") if x)
            return Outcome("skipped", line=line, detail={"grant_id": g["id"], "why": "no_youtube"})
        keep = videos[:int(g["per_run"])]
        more = len(videos) - len(keep)
        left = int(g["per_day"]) - added_today(store, h, rule["id"], action, now, tz)
        if left <= 0:
            return Outcome("skipped", line=T.grant_day_full(app, n, g["per_day"]), detail={"grant_id": g["id"],
                                                                                       "why": "per_day"})
        more += max(0, len(keep) - left)
        keep = keep[:left]
        out = YtPlaylistAdd(playlist_title=g["target"] or PLAYLIST_DEFAULT, videos=keep)
        titles = [v["title"] for v in keep]
        keys = [v["video_id"] for v in keep]
        # ---------- end second merge of round 10 ----------
    else:
        from .actions import calendar as cal
        from .places import _local
        picks = [x for x in ctx.picks if not _strong(bot, ctx.person, x)]
        left_out = len(ctx.picks) - len(picks)   # merge of round 10: said with slice S's line (T.cm_left_out)
        if not picks:
            return Outcome("skipped", line=T.cm_left_out(left_out) if left_out else "",
                           detail={"grant_id": g["id"], "why": "none"})
        from dataclasses import replace as _with
        ev = cal.event_for(_with(ctx, picks=picks[:1]), CalendarParams.model_validate(params or {}))   # ctx unchanged
        if ev is None:
            return Outcome("skipped", line="", detail={"grant_id": g["id"], "why": "passed"})
        if added_today(store, h, rule["id"], action, now, tz) + 1 > int(g["per_day"]):
            return Outcome("skipped", line=T.grant_day_full(app, n, g["per_day"]), detail={"grant_id": g["id"],
                                                                                       "why": "per_day"})
        if ev["all_day"]:
            start, end = f"{ev['day']:%Y-%m-%d}T00:00", f"{ev['day'] + timedelta(days=1):%Y-%m-%d}T00:00"
        else:
            start, end = _local(ev["start"], ev["tz"]), _local(ev["end"], ev["tz"])
        out = MacEventParams(calendar=g["target"] or "Digest", title=ev["title"][:200],
                             notes=f"From your saves: {ev['url']}" if ev.get("url") else "", all_day=ev["all_day"],
                             start=start, end=end)
        titles, keys = [out.title], [picks[0].get("item_id") or out.title, start]
    slot = now_iso(ctx.slot_at) if ctx.slot_at else str(ctx.run_id)
    idem = hashlib.sha256(json.dumps([h, action, g["id"], slot, keys], ensure_ascii=False).encode()).hexdigest()
    if store.placement_idem(h, idem, now - SAME_SLOT):   # a retried slot (a restart mid-run): never twice
        return Outcome("done", line=T.grant_already(app, n), detail={"grant_id": g["id"], "already": True})
    base = {"grant_id": g["id"], "route": action}
    try:
        o = perform(action, ctx, out.model_dump(mode="json"), grant=g)
    except C.ConnectorError as e:
        # ---------- merge of round 10: slice C's MCP route under slice G's grant ----------
        # A changed (or gone) pinned tool and a sign-in that needs the person are not the app failing:
        # actions/mcp._mark already set the connection (a changed tool also ended every grant on the app). The run
        # says slice C's own line (the sign-in line at most once a day), counts no failure and opens nothing.
        if action in C.MCP_ROUTES.values() and e.code in ("changed", "unpinned", "needs_signin"):
            store.log_action(h, ctx.run_id, rule["id"], action, "failed", detail=dict(base, error=e.code), slot=None,
                             at=now)
            from .actions import mcp as _mcp
            line = _mcp.signin_line_once(store, h, pl.connector, now) if e.code == "needs_signin" else \
                T.mcp_changed(app, pl.connector)
            return Outcome("failed", line=line, detail=dict(base, error=e.code))
        # ---------- end merge of round 10 ----------
        # ---------- second merge of round 10, Y4: YouTube's own limits and a withdrawn sign-in are not the app
        # failing: the person has to act (or wait), so no failure is counted and nothing pauses ----------
        if pl.connector == "youtube" and e.code in ("quota", "rate", "too_many", "needs_signin"):
            store.log_action(h, ctx.run_id, rule["id"], action, "failed", detail=dict(base, error=e.code), slot=None,
                             at=now)
            if e.code == "needs_signin":
                from .ytreads import revoked
                line = revoked(bot, h, now)   # the sign-in goes and every YouTube grant ends (slice Y's line)
            else:
                line = T.YT_RULE_QUOTA
            return Outcome("failed", line=line, detail=dict(base, error=e.code))
        # ---------- end second merge of round 10 ----------
        C.failed(store, h, pl.connector, e.code, now)
        row = store.grant_failed(g["id"], pause_after=PAUSE_AFTER) or {}
        maybe = getattr(e, "maybe_arrived", False)   # merge of round 10: an MCP stream broke after the create
        if e.code == "timeout" or maybe:   # it may have arrived: a repeat of the same slot is never sent
            from .places import _unsure_mark
            _unsure_mark(bot, h, idem, now)
        store.log_action(h, ctx.run_id, rule["id"], action, "failed", detail=dict(base, error=e.code), slot=None,
                         at=now)
        line = T.grant_paused(app, n, CHECK_WORD.get(pl.connector, pl.connector)) if row.get("status") == "paused" \
            else T.grant_failed_once(app)
        if maybe:
            line += T.mcp_maybe_arrived(app)
        return Outcome("failed", line=line, detail=dict(base, error=e.code))
    except Refused as e:
        code = str(e).split(":", 1)[-1]
        store.log_action(h, ctx.run_id, rule["id"], action, "failed", detail=dict(base, error=f"refused_{code}"),
                         at=now)
        if code == "scope":   # the rule (or the app's account or tools) changed since the yes: the grant ends
            store.end_grants(h, rule_id=rule["id"], reason="rule_changed", at=now)
            return Outcome("skipped", line=T.grant_rule_changed(app, USE_WORD.get(p.key, p.key), n),
                           detail=dict(base, why="rule_changed"))
        if code == "per_day":
            return Outcome("skipped", line=T.grant_day_full(app, n, g["per_day"]), detail=dict(base, why="per_day"))
        return Outcome("skipped", line=T.grant_not_added(app), detail=dict(base, why=code))
    stopped = None
    if o.status == "partial":   # second merge of round 10 (Y4): YouTube stopped part way; what was added is kept
        stopped = (o.detail or {}).get("stop")
        if stopped == "needs_signin":
            from .ytreads import revoked
            stopped = revoked(bot, h, now)
        else:
            stopped = T.YT_RULE_STOPPED_PART
        o.status = "done"
    if o.status != "done":   # perform's own daily cap across every outside add
        store.log_action(h, ctx.run_id, rule["id"], action, o.status, detail=dict(base, **(o.detail or {})), at=now)
        return Outcome("skipped", line=o.line, detail=dict(base, why="cap"))
    placed = (o.detail or {}).get("placed") or []
    ids = [store.add_placement(h, pl.connector, x["action"], x["remote_id"], ctx.run_id, idem, now, route=action,
                               rule_id=rule["id"]) for x in placed]
    C.worked(store, h, pl.connector, now)
    store.grant_worked(g["id"])
    store.log_action(h, ctx.run_id, rule["id"], action, "done", ref=",".join(map(str, ids)),
                     detail=dict(base, count=o.detail.get("count"), placements=ids), at=now)
    named = [i for i, x in zip(ids, placed) if x["action"] not in ("mac.list", "youtube.playlist_make")]
    store.set_state(f"lastwrite_rule:{h}", {
        "kind": "placed", "say": f"added {len(named)} {one if len(named) == 1 else many} to {app} (rule {n})",
        "at": now_iso(now), "undo": {"ids": ids, "connector": pl.connector, "app": app, "rule_id": rule["id"],
                                     "n": n, "one": one, "many": many,
                                     "titles": {str(i): t for i, t in zip(named, titles)}}})
    line = T.grant_ran(len(named), one, many, app, n, titles, more)
    if left_out:   # merge of round 10: slice S's line for the strong-marked picks left out
        line += " " + T.cm_left_out(left_out)
    if pl.kind == "playlist":   # second merge of round 10 (Y4)
        line += "".join(" " + x for x in (stopped, extra) if x)
    return Outcome("done", line=line, ref=",".join(map(str, ids)),
                   detail=dict(base, count=len(named), placements=ids, more=more))


# ---------- undo (G5) ----------
def rule_write(store, handle, now):
    """The last adds a rule's run made, while "undo" may still take them out (24 hours), or None."""
    from datetime import datetime
    st = store.get_state(f"lastwrite_rule:{handle}")
    if st and datetime.fromisoformat(st["at"]) >= now - RULE_UNDO_WINDOW:
        return st
    return None


def _take_out(store, handle, rows, now):
    """Removes these placements where they were made; returns (removed rows, rows that could not be removed)."""
    by = {}
    for r in rows:
        by.setdefault(r["connector"], []).append(r)
    gone, left = [], []
    for key, group in by.items():
        try:
            # second merge of round 10: each row through the module of the action that made it (connectors.remove_rows:
            # a Todoist sign-in's adds through Todoist's MCP server, self-test c26; YouTube's through its API)
            if key == "youtube":
                from .actions import youtube as Y
                res = Y.remove(group, store, now)
            else:
                res = C.remove_rows(store, key, group)
        except Exception:  # noqa: BLE001
            res = {"removed": [], "failed": [r["id"] for r in group]}
        store.remove_placements(res["removed"], now)
        gone += [r for r in group if r["id"] in res["removed"]]
        left += [r for r in group if r["id"] in res["failed"]]
    return gone, left


def undo_write(bot, handle, w, now):
    """"undo" for the last adds of a rule's run (within 24 hours)."""
    u = w["undo"]
    rows = bot.store.placements(handle, ids=u.get("ids") or [])
    if not rows:
        return T.token_undo_gone(u.get("app") or "the app")
    gone, left = _take_out(bot.store, handle, rows, now)
    return _undo_line(u, gone, left)


def _undo_line(u, gone, left):
    titles = u.get("titles") or {}
    gone = [r for r in gone if r["action"] != "mac.list"]
    left = [r for r in left if r["action"] != "mac.list"]
    out = []
    if gone:
        out.append(T.grant_undone(len(gone), u.get("one") or "thing", u.get("many") or "things", u["app"], u["n"]))
    if left:
        out.append(T.grant_undo_failed(u["app"], [titles.get(str(r["id"]), "") for r in left if
                                                  titles.get(str(r["id"]))]))
    return " ".join(out) or T.grant_undo_none(u["n"])


def undo_rule(bot, person, n, now):
    """"undo rule 3" / "take out what rule 3 added": the adds of rule 3's last run in the last 7 days."""
    from .schema import RuleSpec
    h = person["handle"]
    r = bot.store.one("SELECT id FROM rules WHERE handle=? AND number=?", (h, int(n)))
    if not r:
        return T.GRANT_NO_RULE
    rows = bot.store.q("SELECT * FROM placements WHERE handle=? AND rule_id=? AND removed_at IS NULL AND created_at>=? "
                       "ORDER BY id", (h, r["id"], now_iso(now - RULE_UNDO_DAYS)))
    if not rows:
        return T.grant_undo_none(n)
    last = max(x["run_id"] or 0 for x in rows)
    rows = [x for x in rows if (x["run_id"] or 0) == last]
    rule = bot.store.rule(r["id"])
    p = place_of(RuleSpec.model_validate(rule["spec"])) if rule else None
    key = rows[0]["connector"]
    con = C.CONNECTORS.get(key)
    one, many = con.nouns.get(rows[0].get("route") or "", ("thing", "things")) if con else ("thing", "things")
    if con and (one, many) == ("thing", "things"):
        one, many = next(iter(con.nouns.values()))
    u = {"app": _app(p) if p else (con.name if con else key), "n": n, "one": one, "many": many, "titles": {}}
    gone, left = _take_out(bot.store, h, rows, now)
    st = bot.store.get_state(f"lastwrite_rule:{h}")
    if st and set(st["undo"].get("ids") or []) & {x["id"] for x in gone}:
        bot.store.set_state(f"lastwrite_rule:{h}", None)
    return _undo_line(u, gone, left)


# ---------- the reads (hook 8a): "stop adding to X", "use X for rule N", "undo rule N" ----------
_APP_TAIL = r"(?P<app>[a-z][a-z0-9' -]{1,40}?)"
STOP_ADDING = re.compile(r"^(?:please\s+)?(?:stop|quit)\s+(?:adding|putting)\s+(?:things\s+|stuff\s+|anything\s+|them\s+)?"
                         r"(?:to|in|into)\s+(?:my\s+|the\s+)?" + _APP_TAIL + r"(?:\s+on\s+your\s+own)?$"
                         r"|^(?:please\s+)?don'?t\s+add\s+(?:anything|things|stuff)\s+(?:to|in|into)\s+(?:my\s+|the\s+)?"
                         + _APP_TAIL.replace("app>", "app2>") + r"(?:\s+any\s*more)?$")
USE_FOR = re.compile(r"^(?:please\s+)?(?:use|add\s+to|put\s+(?:them|it)\s+in(?:to)?)\s+(?:my\s+|the\s+)?" + _APP_TAIL +
                     r"\s+for\s+rule\s+#?(?P<n>\d{1,3})$")
UNDO_RULE = re.compile(r"^(?:please\s+)?(?:undo|take\s+out\s+what|remove\s+what)\s+rule\s+#?(?P<n>\d{1,3})"
                       r"(?:\s+(?:added|did|put\s+in))?$")


def _norm(text):
    t = " ".join((text or "").lower().replace("’", "'").split())
    return re.sub(r"^[\s\"'“”]+|[\s\"'“”.!?]+$", "", t)


def _place_of_words(words):
    """The place an app's name means ("ticktick", "my mac calendar", "apple reminders", "reminders")."""
    from .places import named
    return named(f"in my {words}") or named(f"in {words}")


def grant_reads(bot, person, text, now):
    """handler.answer_normally, hook 8a. None when the message is none of these."""
    t = _norm(text)
    if not t or len(t) > 80:
        return None
    h = person["handle"]
    m = UNDO_RULE.match(t)
    if m:
        bot.note(intent="grant_undo")
        return bot.send(h, undo_rule(bot, person, int(m.group("n")), now))
    m = STOP_ADDING.match(t)
    if m:
        p = _place_of_words(m.group("app") or m.group("app2"))
        if p is None:
            return None
        bot.note(intent="grant_stop")
        return bot.send(h, stop_adding(bot.store, h, p, now))
    m = USE_FOR.match(t)
    if m:
        p = _place_of_words(m.group("app"))
        if p is None:
            return None
        bot.note(intent="grant_use")
        return bot.send(h, use_for_rule(bot, person, p, int(m.group("n")), now))
    return None


def stop_adding(store, handle, p, now):
    """Ends every grant that adds to this app; the rules keep sending here."""
    rows = [g for g in store.grants_of(handle, p.connector, active_only=False) if g["status"] != "ended"
            and KIND_FOR_ACTION.get(g["action"], p.kind) == p.kind]
    if not rows:
        return T.grant_nothing_to_stop(_app(p))
    numbers = []
    for g in rows:
        store.end_grants(handle, rule_id=g["rule_id"], connector=p.connector, reason="stopped_by_person", at=now)
        rule = store.rule(g["rule_id"])
        if rule and rule["status"] in ("active", "paused"):
            numbers.append(store.rule_number(handle, g["rule_id"]))
    return T.grant_stopped_adding(_app(p), sorted(set(numbers)))


KIND_FOR_ACTION = {"mac.reminder": "todo", "mac.event": "calendar", "ticktick.add": "todo", "todoist.add": "todo",
                   "youtube.playlist_add": "playlist"}   # second merge of round 10 (Y4)


def use_for_rule(bot, person, p, n, now):
    """"use ticktick for rule 3": a change preview with the place lines; the YES (confirm_rule) makes the grant."""
    from .schedule import describe
    from .schema import RuleSpec
    store, h = bot.store, person["handle"]
    r = store.one("SELECT id FROM rules WHERE handle=? AND number=? AND status IN ('active','paused')", (h, int(n)))
    if not r:
        return T.GRANT_NO_RULE
    rule = store.rule(r["id"])
    old = RuleSpec.model_validate(rule["spec"])
    if old.content.source not in ("library", "recent"):
        return T.GRANT_ONLY_PICKS
    app = _app(p)
    if old.when.type not in TIMED:
        return T.place_not_timed(app).strip()
    action = route_of(store, h, p)
    if action is None:
        return T.place_no_route(app).strip()
    why = C.unavailable(store, h, p.connector)
    if why:
        return T.place_unusable(app, CONNECT_WORD.get(p.connector, p.connector), n, why=why, use=_use_word(p)).strip()
    spec = RuleSpec.model_validate(rule["spec"])
    from .schema import RulePlace
    target = _target(p, None, rule.get("text") or "") if p.kind == "playlist" else _target(p, None, "")
    if p.kind == "playlist" and not target:   # second merge of round 10 (Y4): the playlist the rule's words named
        target = PLAYLIST_DEFAULT
    spec.place = RulePlace(connector=p.connector, kind=p.kind, target=target,
                           per_run=_per_run(spec, p), per_day=_per_day(action))
    _ensure_do(spec, p)
    g = store.grant_for(h, r["id"], action)
    if old.place is not None and old.same_as(spec) and g and g["status"] == "active":
        return T.grant_use_same(n, app)
    lines, yes = note_lines(store, h, spec)
    store.set_pending(h, "confirm_rule", {"text": rule.get("text") or "", "spec": spec.stored(), "run_id": None,
                                          "change_of": r["id"], "base": rule["spec"]}, at=now)
    return T.grant_use_preview(n, describe(spec.when), T.picks_for(spec.content.count, spec.content.goal), lines, yes)


# ---------- a rule changed, stopped, or its YES to a change preview (G5, M-8) ----------
DROP_PLACE = re.compile(r"\b(?:not|don'?t|no\s+longer|stop)\s+(?:add(?:ing)?\s+(?:them\s+|it\s+)?)?(?:in|to|into)\s+"
                        r"(?:my\s+|the\s+)?(?P<app>[a-z][a-z0-9' -]{1,30})", re.I)


def on_change(store, handle, rule_id, old, new, text, now):
    """handler's change_rule, before the changed spec is stored. M-8: the old place is kept unless the change names
    another app (then that place is read as for a new rule) or "not in <app>" (the place goes). Any change ends the
    rule's grant; when a place stays, the reply asks for a new yes (a confirm_rule waiting with change_of). Returns
    the line to add to the change's reply ("" when the rule has and gets no place)."""
    n = store.rule_number(handle, rule_id)
    drop = DROP_PLACE.search(text or "")
    named_now = rule_named(text)
    if old.place is not None and drop and _place_of_words(drop.group("app")) is not None:
        p_old = place_of(old)
        new.place = None
        if p_old is not None:
            _strip_place_todos(new, p_old)
        ended = store.end_grants(handle, rule_id=rule_id, reason="rule_changed", at=now)
        return T.grant_dropped(_app(p_old) if p_old else "the app") if (ended or p_old) else ""
    if named_now is not None:
        note = rule_place(store, handle, text, new, number=n)
    elif old.place is not None:
        new.place = old.place.model_copy()
        p = place_of(new)
        if p is not None:
            _ensure_do(new, p)
        note = {"status": "grant", "app": _app(p) if p else old.place.connector} if p else None
    else:
        return ""
    if new.same_as(old):
        return ""
    store.end_grants(handle, rule_id=rule_id, reason="rule_changed", at=now)
    if note is None:
        return ""
    if note["status"] != "grant":
        return note["line"]
    lines, yes = note_lines(store, handle, new)
    rule = store.rule(rule_id)
    store.set_pending(handle, "confirm_rule", {"text": (rule or {}).get("text") or text, "spec": new.stored(),
                                               "run_id": None, "change_of": rule_id, "base": new.stored()}, at=now)
    return T.grant_change_ask(note["app"], lines, yes)


def change_yes(bot, person, payload, now):
    """The YES to a change preview ("use ticktick for rule 3", or the place line after "change 3 ..."): the rule
    takes the spec shown, and the grant is made for exactly that. Nothing happens when the rule changed again since."""
    from .schema import RuleSpec
    store, h = bot.store, person["handle"]
    rid = payload["change_of"]
    rule = store.rule(rid)
    if not rule or rule["handle"] != h or rule["status"] not in ("active", "paused"):
        return T.GRANT_NO_RULE
    n = store.rule_number(h, rid)
    if rule["spec"] not in (payload.get("base"), payload.get("spec")):
        return T.grant_change_stale(n)
    spec = RuleSpec.model_validate(payload["spec"])
    p = place_of(spec)
    store.update_rule(rid, spec=spec.stored())
    gid, why = make(store, h, rid, spec, now)
    app = _app(p) if p else "the app"
    if gid is None:
        word = CHECK_WORD.get(p.connector, p.connector) if p else "app"
        store.update_rule(rid, spec=strip_place(spec).stored())
        return T.grant_not_made(app, word, n).strip()
    return T.grant_change_done(app, n)


def end_for_rules(store, handle, rule_ids, reason, now):
    """"stop 3", "delete rule 3", the undo of a rule just started: its grant ends."""
    for rid in rule_ids:
        store.end_grants(handle, rule_id=rid, reason=reason, at=now)


def resume_for(store, handle, connector):
    """"check my ticktick" (or the Mac) worked: paused grants on it are active again (the scope is checked at the
    next run as always)."""
    for g in store.grants_of(handle, connector, active_only=False):
        if g["status"] == "paused":
            store.resume_grant(g["id"])


def standing(store, handle):
    """[(rule number, app, many, per_run, per_day, status)] of the person's grants that have not ended."""
    from .places import PLACES
    out = []
    for g in store.grants_of(handle, active_only=False):
        if g["status"] == "ended":
            continue
        rule = store.rule(g["rule_id"])
        if not rule or rule["status"] not in ("active", "paused"):
            continue
        con = C.CONNECTORS.get(g["connector"])
        kind = KIND_FOR_ACTION.get(g["action"], "todo")
        p = next((x for x in PLACES if x.connector == g["connector"] and x.kind == kind), None)
        many = con.nouns.get(g["action"], ("thing", "things"))[1] if con else "things"
        out.append((store.rule_number(handle, g["rule_id"]), _app(p) if p else g["connector"], many, g["per_run"],
                    g["per_day"], g["status"]))
    return out
