"""The small builders the fresh set's half files use (brain_fresh_a.py, brain_fresh_b.py). Made-up messages only.

M: one message as a person types it, its tags, its tier ("plan" unless said), and, for a plan message, its readings
(R), its facts (F: a figure recounted by build_brain_fresh.py from tests/brain_library.py rows, never from a tool),
the good line (means, offer) and the calls the tools must refuse (X)."""


def M(text, tags, tier="plan", readings=(), facts=(), means="", offer="", refuses=(), why=""):
    return {"text": text, "tags": tags.split(), "tier": tier, "readings": list(readings), "facts": list(facts),
            "means": means, "offer": offer, "refuses": list(refuses), "why": why}


def C(tool, **args):
    """One tool call."""
    return {"tool": tool, "args": args}


def R(*rounds, win=None, note="", check=False):
    """A reading: rounds of calls (a call alone is a round of one); `win` the window I read from their words for r1
    ([start, end] or None for no dated window), checked against the tool's. The facts are checked against the
    preferred (first) reading's results; `check=True` checks them against this one too (its figures rest on the
    same rows)."""
    rr = [list(r) if isinstance(r, (list, tuple)) else [r] for r in rounds]
    return {"rounds": rr, "win": win, "note": note, "check": check}


def F(say, fn, how, tool=None):
    """A fact: `fn(rec)` counts it from the rows (rec: build_brain_fresh.Recount); `tool` an optional path into the
    preferred reading's results (r1.totals.items, r1.channels[name=Pan Theory].items) for the tool's own figure."""
    return {"say": say, "fn": fn, "how": how, "tool": tool}


def X(tool, **args):
    """A call the tools must refuse (an is_error result) for this message."""
    return {"tool": tool, "args": args}


# windows as I read their words (start, end inclusive, New York days); the export ends 30 Oct 2026 (YouTube) and
# 15 Oct 2026 (Instagram); the clock is Sunday 22 November 2026
LATELY = ["2026-10-03", "2026-10-30"]       # the 4 weeks up to where the newest export ends
BEFORE_LATELY = ["2026-09-05", "2026-10-02"]
ALL = ["2021-01-05", "2026-10-30"]          # the whole record of what they opened
OCT, SEP, AUG = ["2026-10-01", "2026-10-30"], ["2026-09-01", "2026-09-30"], ["2026-08-01", "2026-08-31"]
Y26 = ["2026-01-01", "2026-10-30"]
Y25, Y24, Y23, Y22, Y21 = (["2025-01-01", "2025-12-31"], ["2024-01-01", "2024-12-31"], ["2023-01-01", "2023-12-31"],
                           ["2022-01-01", "2022-12-31"], ["2021-01-01", "2021-12-31"])
SUMMER26, SUMMER25, SUMMER23 = ["2026-06-01", "2026-08-31"], ["2025-06-01", "2025-08-31"], ["2023-06-01", "2023-08-31"]
FALL26 = ["2026-09-01", "2026-10-30"]
LAST7 = ["2026-10-24", "2026-10-30"]        # the last 7 days the export holds
NOV_SO_FAR = ["2026-11-01", "2026-11-22"]


def lately(**kw):
    return {"preset": "lately"}


def words(w):
    return {"words": w}


def preset(p):
    return {"preset": p}


LAST = {"same_as": "last"}
