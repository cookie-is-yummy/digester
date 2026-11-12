"""PROTOTYPE ONLY - the MVP rule spec (RuleSpec v 2, experiments/mvp/DESIGN.md sections 1 and 11) and the interpreter's
reply shape. The LLM fills these forms; code validates them and works out every date and time (AGENTS.md rule 6).

A rule = when (trigger) x content (what) x do (where it goes). Specs stored by v1 still validate: they are read as v 2.
Validation leaves one canonical form per meaning (`time` folded into `times`, 31 as -1, 14 days on named days as
every_weeks 2, fields that do not belong to the type dropped), and `RuleSpec.stored()` is what goes into the store, so
describe, duplicate checks and tests agree.
"""
from datetime import date as _date
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

from .actions import validate_action

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
KINDS = ["save", "collection", "share_self", "playlist", "like", "watch", "view"]
PLATFORMS = ["instagram", "youtube"]
EXTRACTS = ["ingredients", "steps", "key_points"]

DEFAULT_TIME = "09:00"                       # a schedule with no time and no window
RANDOM_WINDOW = ["09:00", "21:00"]           # random moments fall inside this unless the person names a window
RANDOM_DEFAULT_COUNT = 3                     # "randomly" with nothing else: 3 a week
PER_MAX = {"day": 4, "week": 14, "month": 30}  # random sends per period at most (the daily limit applies as well)
MAX_ASK_PICKS, MAX_RULE_PICKS = 10, 5


def hhmm(v):
    if v is None:
        return v
    h, _, m = str(v).strip().partition(":")
    h, m = int(h), int(m or 0)
    if h == 24 and m == 0:
        h = 0
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("time must be HH:MM")
    return f"{h:02d}:{m:02d}"


def iso_date(v):
    if v is None:
        return v
    return _date.fromisoformat(str(v)[:10]).isoformat()   # "last month" is not a date: the form is refused


def _days(v):
    v = [str(d).upper()[:3] for d in v]
    bad = [d for d in v if d not in DAYS]
    if bad:
        raise ValueError(f"unknown days {bad}")
    return sorted(set(v), key=DAYS.index)


def minutes(hm):
    h, m = map(int, hm.split(":"))
    return h * 60 + m


class When(BaseModel):
    """When a rule sends.
    now: answer this message. once: one send (in_minutes, or date + time). schedule: repeating, with exactly one
    cadence (weekly days / every_weeks, every_days, or monthly month_days / month_weeks with every_months) and 1 to 4
    times, or a window (one send a day at a different minute) or every_hours inside a window. random: `count` sends per
    `per` at seeded random moments inside `window`. on_request: run when asked. new_items: when the library gains items
    that fit. Any repeating type may carry start, until, max_sends and except_dates; tz pins one rule to a zone."""
    type: Literal["now", "once", "schedule", "random", "on_request", "new_items"] = "now"
    date: Optional[str] = None                           # once: YYYY-MM-DD local
    time: Optional[str] = None                           # an alias for one entry of `times`; folded into times
    in_minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 60)  # once: "in two hours"; code sets date and time
    days: list[str] = Field(default_factory=list)       # MON..SUN: weekly days, random's allowed days, month_weeks' day
    every_weeks: Optional[int] = Field(default=None, ge=1, le=8)
    every_days: Optional[int] = Field(default=None, ge=1, le=90)
    month_days: list[int] = Field(default_factory=list, max_length=31)    # 1..31, -1 = the last day
    month_weeks: list[int] = Field(default_factory=list, max_length=6)    # 1..5, -1 = the last (with days)
    every_months: Optional[int] = Field(default=None, ge=1, le=12)
    every_hours: Optional[int] = Field(default=None, ge=1, le=12)         # inside window
    times: list[str] = Field(default_factory=list)      # 1 to 4 clock times, HH:MM local
    window: Optional[list[str]] = None                   # [start, end] local
    per: Optional[Literal["day", "week", "month"]] = None   # random
    count: Optional[int] = Field(default=None, ge=1, le=30)  # random: sends per period (content.count is picks per send)
    start: Optional[str] = None
    until: Optional[str] = None                          # inclusive
    max_sends: Optional[int] = Field(default=None, ge=1, le=100)
    except_dates: list[str] = Field(default_factory=list, max_length=60)
    tz: Optional[str] = None                             # an IANA zone that pins this rule ("7pm New York time")

    @field_validator("date", "start", "until")
    @classmethod
    def _date(cls, v):
        return iso_date(v)

    @field_validator("except_dates")
    @classmethod
    def _dates(cls, v):
        return sorted({iso_date(d) for d in v})

    @field_validator("days")
    @classmethod
    def _days(cls, v):
        return _days(v)

    @field_validator("time")
    @classmethod
    def _time(cls, v):
        return hhmm(v)

    @field_validator("times")
    @classmethod
    def _times(cls, v):
        return sorted({hhmm(t) for t in v})

    @field_validator("window")
    @classmethod
    def _window(cls, v):
        if v is None:
            return v
        if len(v) != 2:
            raise ValueError("window is [start, end]")
        a, b = hhmm(v[0]), hhmm(v[1])
        if b == "00:00":
            b = "23:59"
        if minutes(b) - minutes(a) < 15:
            raise ValueError("a window runs from an earlier time to a later one on the same day")
        return [a, b]

    @field_validator("month_days")
    @classmethod
    def _month_days(cls, v):
        out = set()
        for d in v:
            d = int(d)
            if d == 31:
                d = -1   # "the 31st" means the last day in every month: one form for one meaning
            if not (1 <= d <= 30 or d == -1):
                raise ValueError("month_days are 1 to 31, or -1 for the last day")
            out.add(d)
        return sorted(out, key=lambda d: 99 if d == -1 else d)

    @field_validator("month_weeks")
    @classmethod
    def _month_weeks(cls, v):
        out = set()
        for w in v:
            w = int(w)
            if not (1 <= w <= 5 or w == -1):
                raise ValueError("month_weeks are 1 to 5, or -1 for the last")
            out.add(w)
        return sorted(out, key=lambda w: 99 if w == -1 else w)

    @field_validator("tz")
    @classmethod
    def _tz(cls, v):
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except Exception:  # noqa: BLE001
            raise ValueError("tz must be an IANA zone such as America/New_York") from None
        return v

    # ---------- the canonical form ----------
    def _clear(self, *names):
        for n in names:
            default = When.model_fields[n].get_default(call_default_factory=True)
            setattr(self, n, default)

    @model_validator(mode="after")
    def _complete(self):
        if self.time:
            self.times = sorted(set(self.times) | {self.time})
        self.time = None
        if len(self.times) > 4:
            raise ValueError("at most 4 times a day")
        t = self.type
        timing = ("date", "in_minutes", "days", "every_weeks", "every_days", "month_days", "month_weeks", "every_months",
                  "every_hours", "times", "window", "per", "count")
        limits = ("start", "until", "max_sends", "except_dates")
        if t in ("now", "on_request"):
            self._clear(*timing, *limits, "tz")
            return self
        if t == "new_items":
            self._clear(*timing, "tz")
            return self._check_limits()
        if t == "once":
            if self.in_minutes:
                self._clear("date", "times")  # code works out the moment (schedule.resolve_relative)
            elif not (self.date and len(self.times) == 1):
                raise ValueError("a one-time send needs in_minutes, or a date and one time")
            self._clear(*[n for n in timing if n not in ("date", "in_minutes", "times")], *limits)
            return self
        if t == "random":
            if self.times or self.every_days or self.every_weeks or self.month_days or self.month_weeks \
                    or self.every_months or self.every_hours:
                raise ValueError("random takes count, per, window and days; it has no fixed times or cadence")
            self.per = self.per or "week"
            if self.count is None:
                self.count = RANDOM_DEFAULT_COUNT if self.per == "week" else 1
            if self.count > PER_MAX[self.per]:
                raise ValueError(f"at most {PER_MAX[self.per]} random sends per {self.per}")
            self.window = self.window or list(RANDOM_WINDOW)
            self._clear("date", "in_minutes")
            return self._check_limits()
        # schedule
        if self.per or self.count:
            raise ValueError("count and per are for random times; a schedule uses times (\"twice a day\" is two times)")
        self._clear("date", "in_minutes")
        if self.every_days == 1:
            if self.days or self.month_days or self.month_weeks or self.every_months:
                raise ValueError("every day plus another cadence: pick one")
            self.days, self.every_days = list(DAYS), None
        if self.every_days and self.days and self.every_days % 7 == 0 and not (self.month_weeks or self.month_days):
            weeks = self.every_days // 7     # "every 14 days on Monday" is every_weeks 2: one form for one meaning
            if self.every_weeks not in (None, weeks) or weeks > 8:
                raise ValueError("every_days and every_weeks disagree")
            self.every_weeks, self.every_days = weeks, None
        monthly = bool(self.month_days or self.month_weeks or self.every_months)
        weekly = bool(self.days and not self.month_weeks) or self.every_weeks is not None
        interval = self.every_days is not None
        if monthly + weekly + interval > 1:
            raise ValueError("a schedule has one cadence: days of the week, every_days, or days of the month")
        if self.month_days and self.month_weeks:
            raise ValueError("month_days or month_weeks, not both")
        if self.month_weeks and not self.days:
            raise ValueError("month_weeks needs a day (\"the first Monday\")")
        if interval and self.every_days < 2:
            raise ValueError("every_days is 2 to 90")
        if not (monthly or weekly or interval):
            self.days = list(DAYS)      # times with no cadence ("twice a day") are every day
            weekly = True
        if weekly:
            self.every_weeks = self.every_weeks or 1
        if monthly:
            self.every_months = self.every_months or 1
        if self.every_hours and not self.window:
            raise ValueError("every_hours needs a window (\"every 2 hours from 9 to 5\")")
        if self.window and self.times:
            raise ValueError("a window or times, not both")
        if not self.window and not self.times:
            self.times = [DEFAULT_TIME]
        return self._check_limits()

    def _check_limits(self):
        if self.start and self.until and self.until < self.start:
            raise ValueError("until is before start")
        return self

    # ---------- reading ----------
    @property
    def named_time(self) -> bool:
        """True when every send is at a clock time the person named (honoured even inside quiet hours)."""
        return self.type == "once" or (self.type == "schedule" and bool(self.times) and not self.window)

    @property
    def repeating(self) -> bool:
        return self.type in ("schedule", "random", "new_items")


class Content(BaseModel):
    """What a rule sends. source: library (search), note (the person's own words, sent as they are), todos (their
    open to-dos), recent (what they kept in the last since_days, newest first), items (item_ids set by code from pick
    numbers, never by the model)."""
    source: Literal["library", "note", "todos", "recent", "items"] = "library"
    text: Optional[str] = Field(default=None, max_length=300)   # note: sent as is
    goal: Optional[str] = Field(default=None, min_length=2, max_length=200)  # what the person wants, in a few words
    searches: list[str] = Field(default_factory=list, max_length=4)          # search texts over the library
    kinds: list[str] = Field(default_factory=list)          # preference order; empty = any
    platforms: list[str] = Field(default_factory=list)      # empty = all the person has
    creators: list[str] = Field(default_factory=list, max_length=10)
    collections: list[str] = Field(default_factory=list, max_length=10)       # also YouTube playlist names
    avoid_creators: list[str] = Field(default_factory=list, max_length=10)
    avoid_collections: list[str] = Field(default_factory=list, max_length=10)
    count: int = Field(default=1, ge=1)                     # picks per send: 1-10 for an ask, 1-5 for a rule (cut)
    asked_count: Optional[int] = None                       # set by code when count was cut ("here are the top N")
    extract: list[Literal["ingredients", "steps", "key_points"]] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list, max_length=5)   # must-haves in plain words
    avoid: list[str] = Field(default_factory=list, max_length=8)
    since_days: Optional[int] = Field(default=None, ge=1, le=3650)  # "this month", "this year": the model gives days
    saved_after: Optional[str] = None                        # ISO date, inclusive
    saved_before: Optional[str] = None                       # ISO date, exclusive
    order: Literal["best", "newest", "oldest", "random", "easiest_first"] = "best"
    outside: Literal["none", "some", "only"] = "none"
    exclude_sent: bool = True
    style: Literal["full", "brief"] = "full"
    item_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("saved_after", "saved_before")
    @classmethod
    def _iso(cls, v):
        return iso_date(v)

    @field_validator("extract", mode="before")
    @classmethod
    def _extract(cls, v):
        """A v1 string ("ingredients", "none") still loads."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        out = []
        for x in v:
            x = str(x).strip().lower().replace(" ", "_")
            if x and x != "none" and x not in out:
                out.append(x)
        return out

    @field_validator("searches")
    @classmethod
    def _searches(cls, v):
        return [" ".join(s.split())[:120] for s in v if s and s.strip()]

    @field_validator("criteria")
    @classmethod
    def _criteria(cls, v):
        return list(dict.fromkeys(" ".join(s.split())[:100] for s in v if s and s.strip()))

    @field_validator("creators", "avoid_creators")
    @classmethod
    def _creators(cls, v):
        return list(dict.fromkeys(s.strip().lstrip("@").lower() for s in v if s and s.strip().lstrip("@")))

    @field_validator("collections", "avoid_collections")
    @classmethod
    def _collections(cls, v):
        return list(dict.fromkeys(" ".join(s.split())[:80] for s in v if s and s.strip()))

    @field_validator("kinds")
    @classmethod
    def _kinds(cls, v):
        bad = [k for k in v if k not in KINDS]
        if bad:
            raise ValueError(f"unknown kinds {bad}")
        return list(dict.fromkeys(v))

    @field_validator("platforms")
    @classmethod
    def _platforms(cls, v):
        bad = [p for p in v if p not in PLATFORMS]
        if bad:
            raise ValueError(f"unknown platforms {bad}")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _by_source(self):
        s = self.source
        if s == "library":
            if not self.goal:
                raise ValueError("goal is needed")
            if not self.searches:
                raise ValueError("at least one search")
        elif s == "note":
            self.text = " ".join((self.text or "").split())
            if not self.text:
                raise ValueError("a note needs its text")
            self.goal = self.goal or self.text[:200].ljust(2, ".")
        elif s == "todos":
            self.goal = self.goal or "your to-do list"
        elif s == "recent":
            self.goal = self.goal or "what you saved recently"
            if not (self.since_days or self.saved_after):
                self.since_days = 7
        elif s == "items":
            if not self.item_ids:
                raise ValueError("source items needs item_ids")
            self.goal = self.goal or "the picks you asked for"
        if s != "items" and self.item_ids:
            raise ValueError("item_ids go with source items")
        if self.saved_after and self.saved_before and self.saved_before <= self.saved_after:
            raise ValueError("saved_before must be after saved_after")
        if self.count > MAX_ASK_PICKS:
            self.asked_count, self.count = self.asked_count or self.count, MAX_ASK_PICKS
        return self

    @model_validator(mode="after")
    def _kinds_reach_platforms(self):
        """A filter that removes every item of a listed platform is a validation error (BRIEF-10 section 7)."""
        yt_kinds = {"playlist", "share_self", "like", "watch"}
        ig_kinds = {"save", "collection", "share_self", "like", "watch", "view"}
        if self.kinds and "youtube" in self.platforms and not (set(self.kinds) & yt_kinds):
            raise ValueError("these kinds exclude every YouTube item")
        if self.kinds and "instagram" in self.platforms and not (set(self.kinds) & ig_kinds):
            raise ValueError("these kinds exclude every Instagram item")
        return self


class Action(BaseModel):
    """One entry of `do`, validated against the action registry (actions/). A bare name ("email.send") is accepted."""
    action: str = "message.send"
    params: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _name_only(cls, v):
        if isinstance(v, str):
            return {"action": v}
        if isinstance(v, dict) and v.get("params") is None:
            return {**v, "params": {}}   # "params": null from the model means no params
        return v

    @model_validator(mode="after")
    def _registry(self):
        self.action, self.params = validate_action(self.action, self.params)
        return self


class RuleSpec(BaseModel):
    v: Literal[1, 2] = 2
    when: When
    content: Content
    do: list[Action] = Field(default_factory=lambda: [Action()], min_length=1, max_length=4)

    @field_validator("do", mode="before")
    @classmethod
    def _do_list(cls, v):
        """One action given on its own ("email.send") is a list of one; none at all (null, []) is the reply."""
        if v is None or v == []:
            return [{"action": "message.send"}]
        return [v] if isinstance(v, (str, dict)) else v

    @model_validator(mode="after")
    def _v2(self):
        self.v = 2   # a v1 spec is read as v 2: every v1 field means the same thing here
        seen, do = set(), []
        for a in self.do:
            if a.action not in seen:
                seen.add(a.action)
                do.append(a)
        self.do = do
        c = self.content
        if self.when.type != "now" and c.count > MAX_RULE_PICKS:
            c.asked_count, c.count = c.asked_count or c.count, MAX_RULE_PICKS
        return self

    def stored(self) -> dict:
        """The canonical stored form: no empty lists and no unset fields."""
        return _compact(self.model_dump(exclude_none=True))

    def same_as(self, other: "RuleSpec") -> bool:
        return self.stored() == other.stored()


def _compact(v):
    if isinstance(v, dict):
        return {k: _compact(x) for k, x in v.items() if x not in ([], {}, None)}
    if isinstance(v, list):
        return [_compact(x) for x in v]
    return v


# ---------- person-level timing ----------
class QuietBlock(BaseModel):
    """One block of quiet hours: no timed send starts inside it unless the person named that exact time. A block whose
    end is earlier than its start runs past midnight; `days` are the days it starts on (empty = every day)."""
    start: str
    end: str
    days: list[str] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def _t(cls, v):
        return hhmm(v)

    @field_validator("days")
    @classmethod
    def _d(cls, v):
        return _days(v)

    @model_validator(mode="after")
    def _len(self):
        if self.start == self.end:
            raise ValueError("a quiet block needs a start and a different end")
        return self


DEFAULT_QUIET = [{"start": "22:00", "end": "08:00"}]
MAX_QUIET_BLOCKS = 4


def quiet_blocks(value) -> list[QuietBlock]:
    """Validated quiet blocks (None means the default 22:00 to 08:00)."""
    value = DEFAULT_QUIET if value is None else value
    if len(value) > MAX_QUIET_BLOCKS:
        raise ValueError(f"at most {MAX_QUIET_BLOCKS} quiet blocks")
    return [b if isinstance(b, QuietBlock) else QuietBlock.model_validate(b) for b in value]


INTENTS = ["new_rule", "ask", "follow_up", "more", "change_rule", "run_rule", "skip", "list_rules", "pause", "resume", "stop",
           "feedback", "set_timezone", "delete_data", "help", "confirm", "decline", "unsupported", "chat"]


class Interpretation(BaseModel):
    intent: Literal[tuple(INTENTS)]
    spec: Optional[RuleSpec] = None            # new_rule, ask, change_rule (the full new spec)
    rule_number: Optional[int] = None          # change_rule, run_rule, skip, pause, resume, stop: as listed to them
    timezone: Optional[str] = None             # set_timezone: an IANA name ("America/Los_Angeles")
    all_rules: bool = False                    # "stop everything"
    edits_pending: bool = False                # new_rule that changes the rule whose preview is waiting for YES
    feedback: Optional[Literal["up", "down", "more", "less"]] = None
    pick_number: Optional[int] = None          # feedback on one pick of the last answer
    question: Optional[str] = Field(default=None, max_length=300)    # follow_up: the question to answer
    avoid: list[str] = Field(default_factory=list, max_length=8)     # follow_up: things the question rules out
    reply: Optional[str] = Field(default=None, max_length=400)       # unsupported, chat, help: a short answer
    # managing rules (DESIGN.md section 11)
    until: Optional[str] = None                # pause, set_timezone: YYYY-MM-DD or YYYY-MM-DDTHH:MM local; code acts on it
    in_minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 90)   # pause: "for two hours"
    count: Optional[int] = Field(default=None, ge=1, le=20)                  # skip: "skip the next two"
    date: Optional[str] = None                 # skip: "not on the 26th" (with until: a run of days)
    skip_next: bool = False                    # run_rule: "send Friday's one now" (and not on Friday)

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        return iso_date(v)

    @field_validator("until")
    @classmethod
    def _until(cls, v):
        if v is None:
            return v
        from datetime import datetime
        v = str(v).strip().replace(" ", "T")
        if len(v) <= 10:
            return iso_date(v)
        return datetime.fromisoformat(v[:16]).strftime("%Y-%m-%dT%H:%M")

    @model_validator(mode="after")
    def _needs(self):
        if self.intent in ("new_rule", "ask", "change_rule") and self.spec is None:
            raise ValueError(f"{self.intent} needs a spec")
        if self.spec is not None and self.spec.content.item_ids:
            raise ValueError("item_ids are set by code from pick numbers; give pick_number instead")
        if self.intent == "change_rule" and self.spec.when.type == "now":
            self.intent, self.spec = "run_rule", None   # "send the pasta one now" runs the rule; it never ends it
        if self.intent == "new_rule" and self.spec.when.type == "now":
            raise ValueError("a rule needs a time, a schedule, or on_request")
        if self.intent == "ask" and self.spec.when.type != "now":
            self.intent = "new_rule"
        if self.intent == "follow_up" and not self.question:
            raise ValueError("follow_up needs the question")
        if self.intent == "feedback" and not self.feedback:
            raise ValueError("feedback needs a kind")
        if self.intent == "set_timezone":
            try:
                ZoneInfo(self.timezone or "")
            except Exception:  # noqa: BLE001
                raise ValueError("set_timezone needs an IANA timezone name such as America/Chicago") from None
        return self
