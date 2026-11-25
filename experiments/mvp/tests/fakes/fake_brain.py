"""A fake brain for the offline eval and the tests (design/brain_v1/SPEC.md 11.2): a provider that replays recorded
steps. No network, no money.

    from mvp.tests.fakes.fake_brain import FakeBrain, FakeEngine, fake_learned
    fb = FakeBrain([[{"tool": "breakdown", "args": {...}}], [{"tool": "items", "args": {...}}]])
    while (step := fb.step(results_so_far)) is not None: ...     # each step is one round of tool calls
    fb.give_answer(form)                                          # the final step, when the plan has one

Step 1 has no loop: `run_rounds(turn, rounds, call)` is the replay the eval uses (each round's calls run in order and
see the earlier rounds' results, as one model request's parallel calls would). A step that is not a list of calls, or
a call that names no tool, raises: a recorded plan that cannot be replayed is a broken fixture, never a quiet skip.

FakeEngine stands in for the search engine (word overlap with each item's own text, no embedding); fake_learned for
the paid synth call (a point per saved item whose text holds the topic's word, its text the item's first sentence).
Both are made-up stand-ins with a fixed, readable rule.
"""
import re


class FakeBrainError(AssertionError):
    pass


class FakeBrain:
    """Replays recorded rounds of tool calls, then an optional give_answer form."""

    def __init__(self, rounds, answer=None):
        for r in rounds:
            if not isinstance(r, list) or not r:
                raise FakeBrainError(f"a round is a non-empty list of calls: {r!r}")
            for c in r:
                if not isinstance(c, dict) or not isinstance(c.get("tool"), str) or not isinstance(c.get("args"), dict):
                    raise FakeBrainError(f"a call is {{tool, args}}: {c!r}")
        self.rounds = [list(r) for r in rounds]
        self.answer = answer
        self.requests = 0       # model requests the replay stood for (each round, then the answer)
        self._next = 0

    def step(self, results=None):
        """The next round of calls, or None when the plan has no more."""
        if self._next >= len(self.rounds):
            return None
        self.requests += 1
        self._next += 1
        return self.rounds[self._next - 1]

    def give_answer(self):
        self.requests += 1
        return self.answer


def run_rounds(turn, rounds, call, answer=None):
    """Replay `rounds` on a tools.Turn with `call(turn, name, args)` -> [(round index, call, result)] and the fake."""
    fb = FakeBrain(rounds, answer)
    out, k = [], 0
    while True:
        step = fb.step()
        if step is None:
            break
        for c in step:
            out.append((k, c, call(turn, c["tool"], c["args"])))
        k += 1
    return out, fb


# ---------------------------------------------------------------- stand-ins for the paid or embedding backends
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "my", "me", "i", "that", "this", "thing",
         "things", "saved", "save", "watched", "find", "stuff", "video", "videos", "post", "posts"}


def _words(text):
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 2]


def _holds(text, w):
    toks = set(_WORD.findall((text or "").lower()))
    return w in toks or (w.endswith("s") and w[:-1] in toks) or (w + "s") in toks


HOW_KINDS = {"saved": ("save", "collection", "share_self", "playlist"), "opened": ("watch", "view"),
             "any": ("watch", "view", "like", "save", "collection", "share_self", "playlist")}


class FakeEngine:
    """search(turn, query, how, start, end, limit) -> {"items": [{item_id, score, why}], "cost_usd": 0}: every item of
    the library of the kind asked (a save, an open) in the window, whose own text holds a word of the query, scored by
    the share of the query's words it holds (ties by id), as the real engine filters by kind and window before it
    ranks. Code (tools.run_search) still keeps only what they may see, of the kind and window asked."""

    def __init__(self):
        self.calls = []

    def __call__(self, turn, query, how, start, end, limit):
        self.calls.append((query, how, start, end, limit))
        words = _words(query)
        if not words:
            return {"items": [], "cost_usd": 0.0}
        view, rec = turn.lib.view, turn.lib.rec
        kinds = HOW_KINDS.get(how, HOW_KINDS["any"])
        scored = []
        for iid, it in view.items.items():
            if not any(k in kinds and (start is None or d >= start) and (end is None or d <= end)
                       for d, k in rec.events.get(iid, [])):
                continue
            cap = it.caption or ""
            hit = sum(1 for w in words if _holds(cap, w))
            if hit:
                scored.append((-hit / len(words), iid))
        scored.sort()
        return {"items": [{"item_id": i, "score": round(-s, 3), "why": None} for s, i in scored[:max(limit * 4, 20)]],
                "cost_usd": 0.0}


def fake_learned(turn, topic, q):
    """A point per item they SAVED whose text holds the topic's word: the text's first sentence, its source the item."""
    words = _words(topic)
    view = turn.lib.view
    rec = turn.lib.rec
    points = []
    for iid in sorted(view.items):
        it = view.items[iid]
        cap = it.caption or ""
        saved = any(k in ("save", "collection", "share_self", "playlist") for _d, k in rec.events.get(iid, []))
        if saved and words and all(_holds(cap, w) for w in words):
            first = re.split(r"(?<=[.!?])\s+", cap.strip())[0]
            points.append({"text": first, "item_ids": [iid]})
    return {"points": points, "cost_usd": 0.0}
