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


def R(*rounds, win=None, note=""):
    """A reading: rounds of calls (a call alone is a round of one); `win` the window I read from their words for r1
    ([start, end] or None for no dated window), checked against the tool's."""
    rr = [list(r) if isinstance(r, (list, tuple)) else [r] for r in rounds]
    return {"rounds": rr, "win": win, "note": note}


def F(say, fn, how, tool=None):
    """A fact: `fn(rec)` counts it from the rows (rec: build_brain_fresh.Recount); `tool` an optional path into the
    preferred reading's results (r1.totals.items, r1.channels[name=Pan Theory].items) for the tool's own figure."""
    return {"say": say, "fn": fn, "how": how, "tool": tool}


def X(tool, **args):
    """A call the tools must refuse (an is_error result) for this message."""
    return {"tool": tool, "args": args}
