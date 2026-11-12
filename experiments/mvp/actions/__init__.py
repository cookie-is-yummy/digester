"""PROTOTYPE ONLY - the action registry (DESIGN.md section 1 'do'). Nothing outside this registry can run.

This module only validates: each action's name, its params and what it needs. The actions themselves (email, calendar
links and files, to-dos) are built in later slices; a rule spec is checked against this registry before it is stored.
"""
from datetime import date
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
    """todo.add: each main pick (title and link) goes on the person's list."""
    model_config = ConfigDict(extra="forbid")
    list: str = Field(default="todo", min_length=1, max_length=40)   # a list name ("shopping"); default "todo"


class ActionDef(BaseModel):
    name: str
    params: type
    needs: Optional[Literal["verified_email"]] = None
    does: str


REGISTRY = {
    "message.send": ActionDef(name="message.send", params=NoParams, does="The reply in the thread"),
    "email.send": ActionDef(name="email.send", params=NoParams, needs="verified_email",
                            does="The same answer as an email to the person's own verified address"),
    "calendar.add": ActionDef(name="calendar.add", params=CalendarParams,
                              does="An 'add to calendar' link in the message and an .ics file on the email"),
    "todo.add": ActionDef(name="todo.add", params=TodoParams, does="Each main pick goes on the person's to-do list"),
}


def validate_action(name, params=None):
    """(name, params as a plain dict with defaults left out). Raises ValueError for anything not in the registry."""
    d = REGISTRY.get(name)
    if d is None:
        raise ValueError(f"unknown action {name!r}; known: {', '.join(REGISTRY)}")
    p = d.params.model_validate(params or {})
    return name, p.model_dump(exclude_defaults=True, exclude_none=True)


def needs(name):
    """What an action needs before it can run (None, or 'verified_email')."""
    return REGISTRY[name].needs
