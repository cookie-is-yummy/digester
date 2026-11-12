"""PROTOTYPE ONLY - the MVP rule spec (a subset of RuleSpec v1, docs/06-rules-and-actions.md) and the interpreter's
reply shape. The LLM fills these forms; code validates them and works out every date and time (AGENTS.md rule 6)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
KINDS = ["save", "collection", "share_self", "playlist", "like", "watch", "view"]
PLATFORMS = ["instagram", "youtube"]


class When(BaseModel):
    type: Literal["now", "once", "schedule"] = "now"
    days: list[str] = Field(default_factory=list)       # schedule: MON..SUN
    every_weeks: int = 1                                 # schedule: 1 = weekly, 2 = every two weeks
    time: Optional[str] = None                           # HH:MM, 24-hour, local
    date: Optional[str] = None                           # once: YYYY-MM-DD local

    @field_validator("days")
    @classmethod
    def _days(cls, v):
        v = [d.upper()[:3] for d in v]
        bad = [d for d in v if d not in DAYS]
        if bad:
            raise ValueError(f"unknown days {bad}")
        return sorted(set(v), key=DAYS.index)

    @field_validator("time")
    @classmethod
    def _time(cls, v):
        if v is None:
            return v
        h, _, m = v.partition(":")
        h, m = int(h), int(m or 0)
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError("time must be HH:MM")
        return f"{h:02d}:{m:02d}"

    @model_validator(mode="after")
    def _complete(self):
        if self.type == "schedule":
            if not self.days:
                raise ValueError("a schedule needs days")
            if not self.time:
                raise ValueError("a schedule needs a time")
            if not 1 <= self.every_weeks <= 4:
                raise ValueError("every_weeks must be 1 to 4")
        if self.type == "once" and not (self.date and self.time):
            raise ValueError("a one-time rule needs a date and a time")
        return self


class Content(BaseModel):
    goal: str = Field(min_length=2, max_length=200)          # what the person wants, in a few words
    searches: list[str] = Field(min_length=1, max_length=4)  # search texts over the library
    kinds: list[str] = Field(default_factory=list)          # preference order; empty = any
    platforms: list[str] = Field(default_factory=list)      # empty = all the person has
    count: int = Field(default=1, ge=1, le=5)
    extract: Literal["none", "ingredients", "steps", "key_points"] = "none"
    avoid: list[str] = Field(default_factory=list, max_length=8)
    since_days: Optional[int] = Field(default=None, ge=1, le=3650)  # "this month", "this year": the model gives days
    saved_after: Optional[str] = None                        # ISO date, worked out by code from since_days
    saved_before: Optional[str] = None
    exclude_sent: bool = True

    @field_validator("searches")
    @classmethod
    def _searches(cls, v):
        v = [" ".join(s.split())[:120] for s in v if s and s.strip()]
        if not v:
            raise ValueError("at least one search")
        return v

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
    def _kinds_reach_platforms(self):
        """A filter that removes every item of a listed platform is a validation error (BRIEF-10 section 7)."""
        yt_kinds = {"playlist", "share_self", "like", "watch"}
        if self.kinds and "youtube" in self.platforms and not (set(self.kinds) & yt_kinds):
            raise ValueError("these kinds exclude every YouTube item")
        return self


class Action(BaseModel):
    action: Literal["message.send"] = "message.send"


class RuleSpec(BaseModel):
    v: Literal[1] = 1
    when: When
    content: Content
    do: list[Action] = Field(default_factory=lambda: [Action()])


INTENTS = ["new_rule", "ask", "follow_up", "change_rule", "list_rules", "pause", "resume", "stop", "feedback",
           "delete_data", "help", "confirm", "decline", "unsupported", "chat"]


class Interpretation(BaseModel):
    intent: Literal[tuple(INTENTS)]
    spec: Optional[RuleSpec] = None            # new_rule, ask, change_rule (the full new spec)
    rule_number: Optional[int] = None          # change_rule, pause, resume, stop: as listed to the person
    all_rules: bool = False                    # "stop everything"
    feedback: Optional[Literal["up", "down", "more", "less"]] = None
    pick_number: Optional[int] = None          # feedback on one pick of the last answer
    question: Optional[str] = Field(default=None, max_length=300)    # follow_up: the question to answer
    reply: Optional[str] = Field(default=None, max_length=400)       # unsupported, chat, help: a short answer

    @model_validator(mode="after")
    def _needs(self):
        if self.intent in ("new_rule", "ask", "change_rule") and self.spec is None:
            raise ValueError(f"{self.intent} needs a spec")
        if self.intent == "new_rule" and self.spec.when.type == "now":
            raise ValueError("a new rule needs a schedule or a time")
        if self.intent == "ask" and self.spec.when.type != "now":
            self.intent = "new_rule"
        if self.intent == "follow_up" and not self.question:
            raise ValueError("follow_up needs the question")
        if self.intent == "feedback" and not self.feedback:
            raise ValueError("feedback needs a kind")
        return self
