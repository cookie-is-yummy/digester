"""PROTOTYPE ONLY - a tool's window, read by code (design/brain_v1/SPEC.md 2.2), step 1.

The model never writes a date. It passes their own words ("lately", "in October", "the summer of 2024"), a preset, or
the window of an earlier result; code reads the words with history.py's own readers. Any digit in the words must be
theirs: in their message or on the screen (a scheduled plan's words are exempt: they were checked when it was saved).
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from .. import history as Hm

PRESETS = ("lately", "all", "this_year", "last_year", "this_month", "last_month", "this_week", "last_week")
PRESET_WORDS = {"this_year": "this year", "last_year": "last year", "this_month": "this month",
                "last_month": "last month", "this_week": "this week", "last_week": "last week"}
LATELY = re.compile(r"\b(?:these\s+days|right\s+now|nowadays|at\s+the\s+moment|recently)\b")
ALL_WORDS = {"all", "all time", "ever", "overall", "all my history", "everything", "all of it", "in total"}
NOT_UNDERSTOOD = ("window words not understood: '{w}'. Use words like: lately, in October, this autumn, the last 3 "
                  "months, 2024, since March.")
TWO_WINDOWS = "two windows in '{w}': use compare, or one window per call."
NOT_THEIRS = "use their own words for the window"


class WindowArg(BaseModel):
    """Exactly one of the three is set."""
    model_config = ConfigDict(extra="forbid")
    words: Optional[str] = None
    preset: Optional[Literal["lately", "all", "this_year", "last_year", "this_month", "last_month", "this_week",
                             "last_week"]] = None
    same_as: Optional[str] = None

    @model_validator(mode="after")
    def _one(self):
        n = sum(1 for v in (self.words, self.preset, self.same_as) if v not in (None, ""))
        if n != 1:
            raise ValueError("a window sets exactly one of words, preset, same_as")
        if self.words is not None and len(self.words) > 80:
            raise ValueError("window words are up to 80 characters")
        return self


class WindowError(ValueError):
    pass


def digits_theirs(words, message="", screen=""):
    """Every run of digits in `words` is a whole run of digits in their message or on the screen."""
    have = set(re.findall(r"\d+", message or "")) | set(re.findall(r"\d+", screen or ""))
    return all(d in have for d in re.findall(r"\d+", words or ""))


def read_words(words, today, message="", screen="", scheduled=False):
    """The one history.Window their words name; WindowError with code's reason otherwise."""
    if not scheduled and not digits_theirs(words, message, screen):
        raise WindowError(NOT_THEIRS)
    t = Hm.normal(words or "")
    t = " ".join(LATELY.sub("lately", t).split())
    if t.strip(" .!?") in ALL_WORDS:
        return Hm.Window()
    found = [w for w, _span in Hm.find_windows(t, today) if isinstance(w, Hm.Window)]
    if not found:
        found = [w for w, _span in Hm.season_windows(t, today)]
    if not found:
        raise WindowError(NOT_UNDERSTOOD.format(w=words))
    if len(found) > 1:
        raise WindowError(TWO_WINDOWS.format(w=words))
    return found[0]


def resolve(arg, today, message="", screen="", scheduled=False, earlier=None, last=None):
    """A WindowArg (or its dict) as a history.Window. `earlier`: {rid: Window} of this turn's results; `last`: the last
    answer's window (from the screen)."""
    if isinstance(arg, dict):
        arg = WindowArg(**arg)
    if arg.preset:
        if arg.preset == "lately":
            return Hm.Window(kind="lately")
        if arg.preset == "all":
            return Hm.Window()
        return read_words(PRESET_WORDS[arg.preset], today, scheduled=True)
    if arg.same_as:
        if arg.same_as == "last":
            if last is None:
                raise WindowError("no earlier answer's window on the screen: say the window")
            return last
        w = (earlier or {}).get(arg.same_as)
        if w is None:
            raise WindowError(f"no result {arg.same_as} with a window in this turn")
        return w
    return read_words(arg.words, today, message, screen, scheduled)
