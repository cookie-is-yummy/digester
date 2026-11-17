"""PROTOTYPE ONLY - the action registry (DESIGN.md sections 1 'do', 6 and 11). Nothing outside this registry can run.

Each entry names an action, its params (validated here, before a rule spec is stored), what it needs, and the module
in this package that does it. Each module has one plain function, `run(ctx, params) -> Outcome` (base.py), that the
executor calls once per answer (outputs.py). A new output is one new module plus one entry in REGISTRY.

    message.send  message.py   the reply in the thread
    email.send    email.py     the same answer as an email to the person's own confirmed address
    calendar.add  calendar.py  a Google Calendar "add event" link in the reply and an .ics file (attached to the email)
    todo.add      todo.py      each main pick (checked title and link), or its checked ingredient lines, on a list
"""
import hashlib
import hmac
import importlib
from datetime import date, datetime, time as _time, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _hhmm(v):
    if v is None:
        return v
    h, _, m = str(v).strip().partition(":")
    h, m = int(h), int(m or 0)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("time must be HH:MM")
    return f"{h:02d}:{m:02d}"


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CalendarParams(BaseModel):
    """calendar.add: an 'add to calendar' link in the message and an .ics file on the email."""
    model_config = ConfigDict(extra="forbid")
    date: Optional[str] = None                                  # YYYY-MM-DD; default: the day of the send
    day_offset: Optional[int] = Field(default=None, ge=0, le=60)  # "in two days": days after the send
    time: Optional[str] = None                                  # HH:MM local
    duration_min: int = Field(default=30, ge=5, le=8 * 60)
    title: Optional[str] = Field(default=None, max_length=100)  # default: the pick's own title, set by code

    @field_validator("time")
    @classmethod
    def _time(cls, v):
        return _hhmm(v)

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        return None if v is None else date.fromisoformat(str(v)[:10]).isoformat()

    @model_validator(mode="after")
    def _one_day(self):
        if self.date and self.day_offset is not None:
            raise ValueError("calendar.add takes a date or a day_offset, not both")
        return self


class TodoParams(BaseModel):
    """todo.add: each main pick (its checked title and link) goes on the person's list; with what "ingredients", each
    checked ingredient line of the pick does."""
    model_config = ConfigDict(extra="forbid")
    list: str = Field(default="todo", min_length=1, max_length=40)   # a list name ("shopping"); default "todo"
    what: Literal["pick", "ingredients"] = "pick"


class ActionDef(BaseModel):
    name: str
    params: type
    needs: Optional[Literal["verified_email"]] = None
    does: str
    module: str          # the module in this package whose run(ctx, params) does it
    order: int           # actions run in this order; the thread's message goes last, so it can say what was done
    # ---------- round 9, C1 (DESIGN.md section 16.D): what an outward action may do ----------
    # Every default is today's behaviour, so the four actions below are unchanged.
    outside: bool = False                                   # reaches another person or an outside account
    undo: Literal["delete", "hold", "none"] = "none"        # how it is taken back: delete what it made, a hold, nothing
    confirm: Literal["never", "send_word"] = "never"        # send_word: perform needs the yes token of the exact text
    max_per_day: Optional[int] = Field(default=None, ge=1)  # per person, per local day, counted in action_log
    in_rules: bool = True                                   # False: never in a rule's do, never in act_on_last
    who: Literal["anyone", "operator"] = "anyone"           # operator: only config.is_operator(handle)
    from_model: bool = True                                 # False: no model form may name it; only code calls it
    connector: Optional[str] = None                         # the outside place it writes to ("mailbox", "mac")
    fallback: Optional[str] = None                          # the action to offer when it cannot run


REGISTRY = {
    "todo.add": ActionDef(name="todo.add", params=TodoParams, module="todo", order=10,
                          does="Each main pick goes on the person's to-do list"),
    "calendar.add": ActionDef(name="calendar.add", params=CalendarParams, module="calendar", order=20,
                              does="An 'add to calendar' link in the message and an .ics file on the email"),
    "email.send": ActionDef(name="email.send", params=NoParams, needs="verified_email", module="email", order=30,
                            does="The same answer as an email to the person's own verified address"),
    "message.send": ActionDef(name="message.send", params=NoParams, module="message", order=90,
                              does="The reply in the thread"),
}


# ---------- round 9, slice A (DESIGN.md section 16.A): emails to other people; only the bot's own code runs these ----
class DraftParams(BaseModel):
    """A draft card (drafts.py) by its id; cut_note ends a body cut for the link."""
    model_config = ConfigDict(extra="forbid")
    draft_id: int
    cut_note: Optional[str] = Field(default=None, max_length=300)


REGISTRY.update({
    "email.draft_link": ActionDef(name="email.draft_link", params=DraftParams, module="email_link", order=40,
                                  does="A mailto: link that opens one draft in the person's own mail app",
                                  max_per_day=20, in_rules=False, from_model=False),
})


def validate_action(name, params=None, by="model", where="form"):
    """(name, params as a plain dict with defaults left out). Raises ValueError for anything not in the registry.
    Round 9, C1: `by` is who names it ("model": a form the model filled, the default; "code"); `where` is where it is
    named ("form": any form, the default; "rule": a RuleSpec's do; "act": act_on_last's actions). A from_model=False
    action named by the model, and an in_rules=False action in a rule or in act_on_last, are refused."""
    d = REGISTRY.get(name)
    if d is None:
        raise ValueError(f"unknown action {name!r}; known: {', '.join(REGISTRY)}")
    if by not in ("model", "code") or where not in ("form", "rule", "act"):
        raise ValueError(f"validate_action: unknown by={by!r} or where={where!r}")
    if by == "model" and not d.from_model:
        raise ValueError(f"{name} can't be named in a form; only the bot's own code runs it")
    if where in ("rule", "act") and not d.in_rules:
        raise ValueError(f"{name} can't be part of a rule or a later action")
    p = d.params.model_validate(params or {})
    return name, p.model_dump(exclude_defaults=True, exclude_none=True)


def needs(name):
    """What an action needs before it can run (None, or 'verified_email')."""
    return REGISTRY[name].needs


def ordered(actions):
    """Actions (objects with .action) in the order they run: outputs first, the thread's message last."""
    return sorted(actions, key=lambda a: REGISTRY[a.action].order)


# ---------- round 9, C1 (DESIGN.md section 16.D): the yes token, who may run it, the daily cap ----------
class Refused(PermissionError):
    """perform would not run an action: no yes token or a wrong one, or not the operator. Raised to the caller."""


def make_yes_token(*parts):
    """The token of one exact version of what will leave (W4: draft id, version, text_hash of its exact text). The
    caller makes it when the person says "send" to the version last shown; the action's module makes it again, in
    `yes_token(ctx, params)`, from what it is about to send; perform runs only when the two are the same."""
    h = hashlib.sha256()
    for x in parts:
        h.update(str(x).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def text_hash(text):
    """The hash of one exact text, for make_yes_token (one changed character is a new hash)."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def local_day_bounds(now, tz):
    """(start, end) in UTC of the local day in `tz` that holds `now`."""
    from zoneinfo import ZoneInfo
    z = ZoneInfo(tz)
    day = now.astimezone(z).date()
    start = datetime.combine(day, _time(0, 0), tzinfo=z)
    end = datetime.combine(day + timedelta(days=1), _time(0, 0), tzinfo=z)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _day_of(ctx):
    now = ctx.now if ctx.now is not None else ctx.bot.clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    tz = (ctx.person or {}).get("timezone") or ctx.tz or "America/New_York"
    return local_day_bounds(now, tz)


def used_today(names, ctx):
    """How many times these actions ran for this person on their local day: action_log rows that are not skipped or
    failed. Whoever calls perform logs each run (outputs._perform does; a slice calling perform itself logs with
    store.log_action), so the count is what was really done."""
    start, end = _day_of(ctx)
    return ctx.store.actions_in(ctx.handle, list(names), start, end)


def over_cap(name, ctx):
    """None when the action may run today; else the cap reached: its own max_per_day, or
    config.OUTSIDE_WRITES_PER_DAY across every outside action. A slice can call this first to show its own line."""
    from .. import config
    d = REGISTRY[name]
    if d.max_per_day is not None and used_today([name], ctx) >= d.max_per_day:
        return d.max_per_day
    if d.outside:
        outside = [n for n, x in REGISTRY.items() if x.outside]
        if used_today(outside, ctx) >= config.OUTSIDE_WRITES_PER_DAY:
            return config.OUTSIDE_WRITES_PER_DAY
    return None


def perform(name, ctx, params=None, yes_token=None):
    """Runs one action through its module. Returns its Outcome (base.py); an error is raised to the caller.
    Round 9, C1: an action with who="operator" runs only for config.is_operator(handle); one with
    confirm="send_word" runs only when `yes_token` equals what its module's `yes_token(ctx, params)` makes from what
    it is about to send (else Refused is raised); past its daily cap it does not run and returns
    Outcome("skipped", line=T.over_action_cap(label, cap)). Actions with none of these fields set run as before."""
    d = REGISTRY[name]
    module = importlib.import_module(f"{__name__}.{d.module}")
    p = d.params.model_validate(params or {})
    if d.who == "operator":
        from .. import config
        if not config.is_operator(ctx.handle):
            raise Refused(f"{name} runs only for the operator")
    if d.confirm == "send_word":
        make = getattr(module, "yes_token", None)
        if make is None:
            raise Refused(f"{name} has no yes_token(ctx, params) in its module")
        if not yes_token or not hmac.compare_digest(str(yes_token), str(make(ctx, p))):
            raise Refused(f"{name} needs the yes token of the exact text")
    if d.max_per_day is not None or d.outside:
        cap = over_cap(name, ctx)
        if cap is not None:
            from .. import texts as T
            from .base import Outcome
            return Outcome("skipped", line=T.over_action_cap(T.ACTION_CAP_LABEL.get(name), cap), detail={"cap": cap})
    return module.run(ctx, p)
