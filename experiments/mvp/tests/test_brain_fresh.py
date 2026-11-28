"""The fresh eval set of the chat core (evalset/brain_fresh.jsonl, built by eval/build_brain_fresh.py; the lock rule
in evalset/README_brain_fresh.md).

Offline: no model call, no network. The tools run on the made-up library of tests/brain_library.py, built as
test_brain_tools.py builds it. No tool number is pinned here (the tools may change); what is pinned is the shape, the
halves, that every reading runs without an error, and the bytes of half B."""
import hashlib
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys, person  # noqa: F401  (fixtures)
from mvp.tests.test_mvp import env  # noqa: F401  (a fixture)

FRESH = os.path.join(os.path.dirname(HERE), "evalset", "brain_fresh.jsonl")
# the sha256 of half B's lines, in file order, each with its newline. Half B is locked: a change here means half B was
# edited, which needs a new fresh set, not a new pin (evalset/README_brain_fresh.md). Pinned once more by the
# independent check of the set (the writer's pin was 343275626e4f...; the check fixed facts, readings and wording and
# added conversations before the lock took hold); no pin after this one.
HALF_B_SHA256 = "3a121423684a58498d375df70685e09a59d31f33a305d48a4d1986f7bb79ec38"
# half B ids whose refused call is no longer refused (a tool learned to read it, e.g. a part of a period). Half B
# cannot be edited, so a lapse is listed here by id; half A's refusals are kept true by editing half A.
LAPSED_B = {"N096"}   # mvp25 toolgaps 1: a part of a period is read now (DESIGN 25.1); listed by id, never opened
TAGS_NEEDED = {"follow_up", "correction", "scoped", "private", "locked", "unlocked", "friends", "saved", "liked",
               "instagram", "shorts", "compare", "first_last", "timeline", "items", "wide", "no_answer_in_data",
               "part_of_period", "sloppy", "lately", "changes", "channels", "themes", "time_of_day", "weekday",
               "search", "after_end", "planted"}


def lines():
    with open(FRESH, encoding="utf-8") as f:
        return [x.rstrip("\n") for x in f if x.strip()]


def convs():
    return [json.loads(x) for x in lines()]


def half_of(cid):
    return "A" if int(hashlib.sha1(cid.encode()).hexdigest(), 16) % 2 == 0 else "B"


def plan_messages(cs=None):
    return [(c, m) for c in (cs or convs()) for m in c["messages"] if m["tier"] == "plan"]


def test_the_file_loads_with_the_agreed_shape():
    cs = convs()
    assert len(cs) >= 70
    ids = [c["id"] for c in cs]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"N\d{3}", i) for i in ids)
    pm = plan_messages(cs)
    assert len(pm) >= 100
    assert sum(1 for _c, m in pm if {"follow_up", "correction"} & set(m["tags"])) >= 30
    for c, m in pm:
        where = f"{c['id']}.{m['n']}"
        assert 1 <= len(m["readings"]) <= 3, where
        for rd in m["readings"]:
            assert set(rd) == {"rounds", "window", "note"} and rd["rounds"] and rd["note"], where
            assert all(isinstance(rnd, list) and rnd for rnd in rd["rounds"]), where
            for rid, w in rd["window"].items():
                assert re.fullmatch(r"r\d+", rid) and len(w) == 2 and all(re.fullmatch(r"\d{4}-\d\d-\d\d", d)
                                                                         for d in w), where
        assert m["facts"], where
        for f in m["facts"]:
            assert set(f) == {"say", "value", "how"} and f["say"] and f["how"], where
            assert isinstance(f["value"], (int, float, str)) and not isinstance(f["value"], bool), where
        assert m["good"]["means"] and m["good"]["offer"], where
        assert m["tags"], where
    for c in cs:
        assert [m["n"] for m in c["messages"]] == list(range(len(c["messages"]))), c["id"]


def test_every_tag_of_the_brief_is_covered_in_both_halves():
    cs = convs()
    for half in ("A", "B"):
        tags = {t for c, m in plan_messages(cs) if c["half"] == half for t in m["tags"]}
        assert TAGS_NEEDED <= tags, (half, sorted(TAGS_NEEDED - tags))
    assert TAGS_NEEDED <= {t for _c, m in plan_messages(cs) for t in m["tags"]}


def test_no_class_of_the_brief_is_thin():
    # the independent check: every class of the brief holds at least 4 messages over both halves
    from collections import Counter
    n = Counter(t for _c, m in plan_messages() for t in m["tags"])
    assert all(n[t] >= 4 for t in TAGS_NEEDED), sorted((t, n[t]) for t in TAGS_NEEDED if n[t] < 4)


def test_the_halves_are_as_the_brief_says():
    cs = convs()
    for c in cs:
        assert c["half"] == half_of(c["id"]), c["id"]
    a = [c for c in cs if c["half"] == "A"]
    b = [c for c in cs if c["half"] == "B"]
    assert len(a) >= 30 and len(b) >= 30
    for half in (a, b):
        assert sum(1 for c in half for m in c["messages"] if m["tier"] == "plan") >= 45


def test_half_b_is_pinned():
    hb = [ln for ln in lines() if half_of(json.loads(ln)["id"]) == "B"]
    got = hashlib.sha256("".join(ln + "\n" for ln in hb).encode("utf-8")).hexdigest()
    assert got == HALF_B_SHA256, "half B of evalset/brain_fresh.jsonl changed: it is locked (README_brain_fresh.md)"


def test_every_reading_names_real_tools_with_valid_arguments():
    from mvp.brain import tools as TL
    for c, m in plan_messages():
        for rd in m["readings"]:
            for rnd in rd["rounds"]:
                for call in rnd:
                    assert TL.REGISTRY[call["tool"]].kind == "read", call["tool"]
                    TL.REGISTRY[call["tool"]].params(**call["args"])     # raises when an argument is not valid
        for x in m.get("refuses") or []:
            TL.REGISTRY[x["tool"]].params(**x["args"])                  # refused by the tool's run, not its model


def test_no_message_repeats_or_comes_close_to_the_old_set():
    import difflib

    from mvp.eval.build_brain_fresh import CLOSE, norm, old_texts
    olds = [norm(o) for o in old_texts()]
    seen = set()
    for c in convs():
        for m in c["messages"]:
            n = norm(m["text"])
            assert n not in seen, c["id"]
            seen.add(n)
            assert n not in olds, c["id"]
            best = max(difflib.SequenceMatcher(None, n, o).ratio() for o in olds)
            assert best < CLOSE, (c["id"], m["n"], round(best, 3))


@pytest.fixture()
def harness(brain):  # noqa: F811  (the fixture of test_brain_tools)
    from mvp import eval_brain as E
    return E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                     now=NOW)


def test_every_reading_runs_without_an_error_and_every_refusal_still_refuses(harness):
    from mvp.eval.build_brain_fresh import replay
    problems = []
    for c in convs():
        got = replay(harness, c)
        if c["half"] == "B":
            # by id only (half B is locked); a lapsed refusal of half B is listed in LAPSED_B, not edited
            got = [c["id"] for p in got if not (p.endswith("was not refused") and c["id"] in LAPSED_B)]
        problems += got
    assert problems == []


def test_a_write_keeps_half_b_as_stored_whatever_the_tools_now_give():
    from mvp.eval.build_brain_fresh import keep_half_b
    a_id = next(c["id"] for c in convs() if c["half"] == "A")
    b_id = next(c["id"] for c in convs() if c["half"] == "B")
    stored = {a_id: json.dumps({"id": a_id, "v": "old"}), b_id: json.dumps({"id": b_id, "v": "old"})}
    rebuilt = [json.dumps({"id": a_id, "v": "new"}), json.dumps({"id": b_id, "v": "new"})]
    out, differ = keep_half_b(rebuilt, stored)
    assert out == [rebuilt[0], stored[b_id]] and differ == [b_id]
