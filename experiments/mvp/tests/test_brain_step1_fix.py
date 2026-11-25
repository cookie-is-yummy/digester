"""Step 1's close (design/brain_v1/SPEC.md 12.2 step 1): what two independent audits of the tools and the verifier found,
each class reproduced first and fixed by construction. Offline: no model call, no network. The library is the made-up
one of tests/brain_library.py (fixtures of test_brain_tools); every title, channel and theme is made up.

Each verifier class has the auditor's sentence, a variant of the same class, and a true twin that is kept. The counts
behind each truth are from the made-up rows (test_brain_tools' recount helpers, which share nothing with facts.py)."""
import os
import sys
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures and the recount helpers)
    LATELY, NOW, OCTOBER, B, brain, built, by_channel, call, known_long, local, no_real_keys, opened, person, turn,
    visible_rows)

ROWS = {r["id"]: r for r in B.rows()}


def W(words):
    return {"words": words}


# ================================================================ the tools (the tools audit)
def test_items_oldest_reads_from_the_windows_start_and_pages_past_ten(brain):
    env_, _t = call(brain, "items", {"window": W("in october"), "order": "oldest", "limit": 3}, "oldest in october")
    days = [local(ROWS[x["item_id"]]["events"][0][1]) for x in env_["sheet"]["items"]]
    want = sorted(local(at) for i in opened(*OCTOBER) for k, at in ROWS[i]["events"] if k == "watch")[:3]
    assert days == want and all(OCTOBER[0] <= d <= OCTOBER[1] for d in days)
    # the auditor's I03: a few more, past the first page
    env2, _t = call(brain, "items", {"window": W("in october"), "order": "oldest", "limit": 3, "offset": 5},
                    "oldest in october, a few more")
    d2 = [local(ROWS[x["item_id"]]["events"][0][1]) for x in env2["sheet"]["items"]]
    assert len(d2) == 3 and all(OCTOBER[0] <= d <= OCTOBER[1] for d in d2) and min(d2) >= max(days)
    # all history, past the tenth item (it stopped at 10)
    env3, _t = call(brain, "items", {"window": {"preset": "all"}, "order": "oldest", "limit": 5, "offset": 10},
                    "oldest ever, more")
    assert len(env3["sheet"]["items"]) == 5


@pytest.mark.parametrize("a,b", [("in october", "in november"), ("in november", "in october")])
def test_a_compare_with_a_window_after_the_export_is_refused(brain, a, b):
    env_, _t = call(brain, "compare", {"a": W(a), "b": W(b), "by": "channel"}, f"{a} against {b}")
    assert env_.get("is_error") and "after where the export ends" in env_["error"]
    ok, _t = call(brain, "compare", {"a": W("in october"), "b": W("in september"), "by": "channel"},
                  "october against september")
    assert not ok.get("is_error") and ok["sheet"]["previous"]["items"] == len(opened(date(2026, 9, 1),
                                                                                    date(2026, 9, 30)))


def test_new_and_stopped_are_not_shown_empty_when_there_is_no_window_before(brain):
    env_, _t = call(brain, "changes", {"level": "theme", "window": {"preset": "lately"}}, "new themes lately")
    assert "new" not in env_["sheet"] and "stopped" not in env_["sheet"]
    assert any("not computed" in n for n in env_["meta"]["notes"])
    with_prev, _t = call(brain, "breakdown", {"by": "channel", "window": W("in october")}, "channels in october")
    assert "new" in with_prev["sheet"] and any(n.startswith("New: at least") for n in with_prev["meta"]["notes"])


def test_first_watched_is_never_a_first_save(brain):
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W("in october"), "scope": {"how": "saved"}},
                    "what did i save in october")
    assert env_["sheet"]["channels"] and all("first_watched" not in r for r in env_["sheet"]["channels"])
    opened_, _t = call(brain, "breakdown", {"by": "channel", "window": W("in october")}, "channels in october")
    assert all("first_watched" in r for r in opened_["sheet"]["channels"])


def test_a_sensitive_word_resolves_only_when_their_message_unlocked_it(brain):
    env_, _t = call(brain, "find", {"names": ["dating"]}, "what are my channels")
    row = env_["sheet"]["names"][0]
    assert row["status"] == "no_match" and not row["matches"] and not row["options"]
    open_, _t = call(brain, "find", {"names": ["dating"]}, "what about dating")
    assert open_["sheet"]["names"][0]["status"] == "ok"


def test_a_learned_point_with_a_source_they_may_not_see_is_dropped(brain):
    from mvp.tests.fakes.fake_brain import fake_learned  # noqa: F401  (the fake backend's module exists)
    hidden = next(r["id"] for r in B.rows() if r.get("friend"))
    seen = next(r["id"] for r in B.rows() if r["platform"] == "instagram" and not r.get("friend"))

    def learned(turn_, topic, q):
        return {"points": [{"text": "A point from a friend's post and one of theirs.", "item_ids": [seen, hidden]},
                           {"text": "A point from their own post.", "item_ids": [seen]}], "cost_usd": 0.0}
    env_, _t = call(brain, "learned", {"topic": "bread"}, "what have i learned about bread", learned=learned)
    assert [p["text"] for p in env_["sheet"]["points"]] == ["A point from their own post."]


@pytest.mark.parametrize("words", ["early october", "late october", "the first week of october", "mid october",
                                   "the end of 2024"])
def test_part_of_a_period_is_refused_not_read_as_the_whole(brain, words):
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W(words)}, words)
    assert env_.get("is_error") and "part of a period" in env_["error"]


def test_lately_is_still_read(brain):
    env_, _t = call(brain, "breakdown", {"by": "area", "window": W("lately")}, "lately")
    assert not env_.get("is_error")


def test_fields_of_one_name_are_one_row(brain):
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W("in october")}, "channels in october")
    names = [r["name"] for r in env_["sheet"]["fields"]]
    assert len(names) == len(set(names))
    g = next(r for r in env_["sheet"]["fields"] if r["name"] == "Gaming")
    gaming_ids = {i for i in opened(*OCTOBER) if ROWS[i]["theme"] in ("mc", "sr", "cl")}
    assert g["items"] == len(gaming_ids)
    assert [r["ref"] for r in env_["sheet"]["fields"]] == [f"r1.fields[{k}]" for k in range(len(names))]


def test_an_instagram_photo_post_has_no_length_word(brain):
    env_, _t = call(brain, "items", {"window": W("in october"), "order": "newest", "limit": 10,
                                     "scope": {"how": "saved"}}, "what did i save in october")
    for x in env_["sheet"]["items"]:
        r = ROWS[x["item_id"]]
        if r["platform"] == "instagram":
            assert x["length"] == ("short" if (r.get("media") or "reel") in ("reel", "video") else "unknown")
    assert any(ROWS[x["item_id"]].get("media") == "post" for x in env_["sheet"]["items"])


def test_rows_of_every_ranking_are_in_meta(brain):
    env_, _t = call(brain, "breakdown", {"by": "area", "window": {"preset": "lately"}}, "lately")
    ro = env_["meta"]["rows_of"]
    assert ro["channels"] == len(by_channel(opened(*LATELY))) and ro["channels"] > len(env_["sheet"]["channels"])
