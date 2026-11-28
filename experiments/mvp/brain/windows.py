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
# a part of a month, a season or a year ("early October", "the end of 2024", "the first week of March"): no reader
PART_OF = re.compile(r"\b(?:early|late|mid|middle of|beginning of|start of|end of|first half of|second half of|"
                     r"(?:first|second|third|fourth|last) (?:week|weekend|days?|fortnight) of)\b")
PART_NOT_READ = ("'{w}' names part of a period, which code cannot read yet: use the whole period ('in October'), or "
                 "ask them for the days.")


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
    part = PART_SAID.match(t.strip(" .!?"))
    if part:
        # mvp25 toolgaps 1 (N063.0 "late October", N064.0 "mid 2023" were refused): early, mid and late of a month, a
        # year or a season, read by the convention of DESIGN 25 (part_of)
        return part_of(part.group(1), part.group(2), words, today)
    if PART_OF.search(t):
        # step 1 fix (the tools audit: "early october", "late october", "the first week of october" were read as all
        # of October and said "October 2026"): history.py has no reader for a part of a period, so code refuses
        # rather than count a window the words did not name (mvp25: only what part_of cannot read is left here)
        raise WindowError(PART_NOT_READ.format(w=words))
    if t.strip(" .!?") in ALL_WORDS:
        return Hm.Window()
    s = season(t.strip(" .!?"), today)
    if s is not None:
        return s
    found = [w for w, _span in Hm.find_windows(t, today) if isinstance(w, Hm.Window)]
    if not found:
        found = [w for w, _span in Hm.season_windows(t, today)]
    if not found:
        raise WindowError(NOT_UNDERSTOOD.format(w=words))
    if len(found) > 1:
        raise WindowError(TWO_WINDOWS.format(w=words))
    return found[0]


# ================================================================ mvp25 toolgaps 1: seasons and parts of a period
# The convention (DESIGN 25.1), one rule each, the same in every message:
# - a season said alone ("the summer", "over the summer") is "this <season>";
# - "this <season>" is the latest one that has begun (history.season_windows: in November 2026, the summer of 2026);
# - "last <season>" is always the one a year before "this <season>" (in November 2026, the summer of 2025), as "last
#   year" is the year before this one. Said alone in November it reads as 2025: the result's dates say which.
# - early / mid / late of a month: days 1 to 10, 11 to 20, 21 to its end; of a year: January to April, May to August,
#   September to December; of a season: its first, middle and last month. "The start of" / "the beginning of" are
#   early, "the end of" is late; "the first half of" / "the second half of" a month are days 1 to 15 and 16 to its end,
#   of a year January to June and July to December. Anything else ("the first week of March") is still refused.
_SEASON_RX = r"(spring|summer|fall|autumn|winter)"
_BARE_SEASON = re.compile(r"^(?:(?:in|during|over|for|of|across)\s+)?(?:the\s+)?(?:(this|last|past|previous)\s+)?"
                          + _SEASON_RX + r"$")
PART_SAID = re.compile(r"^(?:(?:in|during|over|for|at|around|from)\s+)?(?:the\s+)?(early|mid|middle\s+of|late|"
                       r"start\s+of|beginning\s+of|end\s+of|first\s+half\s+of|second\s+half\s+of)(?:\s+|-)"
                       r"(?:the\s+)?(?!week|weekend|days?|fortnight|month|year)(.+)$")
PART_WORD = {"early": "early", "start of": "early", "beginning of": "early", "mid": "mid", "middle of": "mid",
             "late": "late", "end of": "late", "first half of": "first half", "second half of": "second half"}


def _this_season(name, today):
    got = [w for w, _s in Hm.season_windows(f"this {name}", today)]
    return got[0] if got else None


def season(t, today):
    """A season said alone, "this", "last" (or "past", "previous") season, by the convention above; None for other
    words (a season with its year, "the summer of 2023", is history's own reader)."""
    m = _BARE_SEASON.match(t)
    if not m:
        return None
    rel, name = m.group(1), m.group(2)
    this = _this_season(name, today)
    if this is None:
        return None
    if rel in (None, "this"):
        return this
    y = this.start.year - 1
    got = [w for w, _s in Hm.season_windows(f"the {name} of {y}", today)]
    return got[0] if got else None


def _month_end(y, m):
    from datetime import date, timedelta
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def part_of(part, rest, words, today):
    """The part of the period `rest` names (a month, a year or a season), as a range said with its own label."""
    from datetime import date
    part = PART_WORD[" ".join(part.split())]
    try:
        w = read_words(rest, today, scheduled=True)
    except WindowError:
        raise WindowError(PART_NOT_READ.format(w=words)) from None
    s = w.start
    if s is None:
        raise WindowError(PART_NOT_READ.format(w=words))
    if w.kind == "month":
        end = _month_end(s.year, s.month)
        mon = Hm.MONTH_EN[s.month - 1]
        cuts = {"early": (1, 10), "mid": (11, 20), "late": (21, end.day), "first half": (1, 15),
                "second half": (16, end.day)}
        a, b = cuts[part]
        start, stop = date(s.year, s.month, a), date(s.year, s.month, b)
        label = f"the {part} of {mon} {s.year}" if "half" in part else f"{part} {mon} {s.year}"
    elif w.kind == "year":
        cuts = {"early": (1, 4), "mid": (5, 8), "late": (9, 12), "first half": (1, 6), "second half": (7, 12)}
        a, b = cuts[part]
        start, stop = date(s.year, a, 1), _month_end(s.year, b)
        label = f"the {part} of {s.year}" if "half" in part else f"{part} {s.year}"
    elif w.kind == "range" and (w.label or "").startswith("the ") and part in ("early", "mid", "late"):
        k = {"early": 0, "mid": 1, "late": 2}[part]
        y, mo = s.year + (s.month + k - 1) // 12, (s.month + k - 1) % 12 + 1
        start, stop = date(y, mo, 1), _month_end(y, mo)
        label = f"{part} {w.label[4:]}"   # "late summer of 2026", "early winter of 2025 to 2026"
    else:
        raise WindowError(PART_NOT_READ.format(w=words))
    if start > today:
        raise WindowError(f"'{words}' has not begun yet: use a period that has.")
    return Hm.Window(kind="range", start=start, end=min(stop, today), label=label)


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
            # mvp26 toolfix2 3: every refusal says a next step that exists
            have = sorted(earlier or {}, key=lambda r: int(r[1:]) if r[1:].isdigit() else 0)
            raise WindowError(f"no result {arg.same_as} with a window in this turn: "
                              + (f"use same_as {' or '.join(repr(r) for r in have)}, or say the window"
                                 if have else "say the window in their words, or use a preset"))
        return w
    return read_words(arg.words, today, message, screen, scheduled)
