"""The brain eval's measuring tools after the thin live slice (the mvp22 brief): the "understood" scorer (G2) with
several readings per message and its named rules; the auditor's two fixed misreadings, measured on sentences a hand
recount labelled; the auditor's output as hints, out of the G1 line; the fresh set's run path (a made-up set file
here, never evalset/brain_fresh.jsonl); the reading sheet and the marks. Offline: the FAKE provider only, the made-up
library of tests/brain_library.py. No model call, no network, no money.
"""
import argparse
import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures)
    NOW, brain, built, no_real_keys, person)

OCT = {"words": "in October", "preset": None, "same_as": None}
LATELY = {"preset": "lately", "same_as": None, "words": None}
ALL = {"preset": "all", "same_as": None, "words": None}


@pytest.fixture()
def harness(brain):
    from mvp import eval_brain as E
    return E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                     now=NOW)


def turn(h, message):
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    return h.turn(message, search=FakeEngine(), learned=fake_learned)


def model_rec(h, message, calls):
    """A record as the live loop saves it (calls with name, args, result), from tool calls on the made-up library."""
    from mvp.brain import tools as TL
    t = turn(h, message)
    out = []
    for name, args in calls:
        env_ = TL.call(t, name, args)
        out.append({"name": name, "args": args, "rid": env_.get("rid"), "result": env_})
    return {"calls": out}, t


def plan_msg(text, *rounds, window=None):
    return {"n": 0, "text": text, "tier": "plan", "rounds": [list(r) for r in rounds], "window": window or {}}


def bd(**args):
    return {"tool": "breakdown", "args": args}


# ================================================================ 1. the scorer (G2)
K = {"tool": "breakdown", "what": "channel", "window": ["2026-10-01", "2026-10-30"], "base": "of what you opened",
     "scope": [], "order": "most"}


def test_the_scorer_without_rules_is_the_scorer_as_it_was():
    from mvp import eval_brain as E
    assert E.compare_plans([K], [dict(K)])["verdict"] == "understood"
    assert E.compare_plans([K], [dict(K, what="area")])["verdict"] == "other_plan"
    assert E.compare_plans([dict(K, what="none")], [dict(K, what="area")])["verdict"] == "other_plan"
    assert E.compare_plans([K], [dict(K, scope=["YouTube only"], counted="x")])["verdict"] == "differs"
    # with the rules: a total is in any breakdown; a year is in a timeline by month
    assert E.compare_plans([dict(K, what="none")], [dict(K, what="area")], E.RULES)["verdict"] == "understood"
    assert E.compare_plans([dict(K, what="area")], [dict(K, what="none")], E.RULES)["verdict"] == "other_plan"
    tl = dict(K, tool="timeline", what="year")
    assert E.compare_plans([tl], [dict(tl, what="month")], E.RULES)["verdict"] == "understood"
    assert E.compare_plans([dict(tl, what="month")], [tl], E.RULES)["verdict"] == "other_plan"


def test_extra_filters_count_as_the_same_scope_only_when_the_counts_are_the_same_and_not_empty():
    from mvp import eval_brain as E
    h = dict(K, scope=["only Minecraft builds (theme)"], counted="abc")
    m = dict(K, scope=["YouTube only", "only Minecraft builds (theme)"], counted="abc")
    assert E.compare_plans([h], [m], E.RULES)["verdict"] == "understood"
    assert E.compare_plans([h], [dict(m, counted="other")], E.RULES)["verdict"] == "differs"
    assert E.compare_plans([dict(h, counted=None)], [dict(m, counted=None)], E.RULES)["verdict"] == "differs"
    # a model scope with a filter LESS than the hand's is never the same scope
    assert E.compare_plans([m], [h], E.RULES)["verdict"] == "differs"


def test_first_last_says_its_subject_as_an_only_scope():
    from mvp import eval_brain as E
    assert E._scope_norm(["speedruns: Speedruns (theme)"]) == ["only Speedruns (theme)"]
    assert E._scope_norm(["only Speedruns (theme)", "YouTube only"]) == ["YouTube only", "only Speedruns (theme)"]
    fl = dict(K, tool="first_last", what="last", scope=["speedruns: Speedruns (theme)"],
              scope_n=["only Speedruns (theme)"])
    tl = dict(K, tool="timeline", what="month", scope=["only Speedruns (theme)"], scope_n=["only Speedruns (theme)"])
    assert E.compare_plans([fl], [tl])["verdict"] == "differs"
    assert E.compare_plans([fl], [tl], E.RULES)["verdict"] == "other_plan"


def test_several_readings_the_best_counts_and_later_rounds_are_not_required():
    from mvp import eval_brain as E
    theme = dict(K, what="theme", round=0)
    area = dict(K, what="area", round=0)
    v = E.score_readings([[theme], [area]], [dict(K, what="area")])
    assert v["verdict"] == "understood" and v["reading"] == 1
    assert E.score_readings([[theme]], [dict(K, what="area")])["verdict"] == "other_plan"
    two = [dict(K, round=0), dict(K, scope=["only videos known to be long"], round=1)]
    v = E.score_readings([two], [dict(K)])
    assert v["verdict"] == "understood" and len(v["later_rounds_missed"]) == 1
    assert E.score_readings([two], [dict(K)], rules=())["verdict"] == "differs"
    g = E.g2_of([two], [dict(K)])
    assert g["verdict"] == "understood" and g["verdict_strict"] == "differs" and g["readings"] == 1
    assert E.g2_of([], [dict(K)])["verdict"] == "no_hand_plan"


def test_the_held_out_cases_on_the_made_up_library(harness):
    """The disagreements with the independent reader that a rule settles (mvp20 held-out look, by the reader's
    judgments): the replayed hand plan against model calls of the same shape as the run's."""
    from mvp import eval_brain as E

    def verdicts(m, calls):
        _hand, readings, windows, _errors = E.hand_readings(harness, m)
        assert windows == []
        rec, _t = model_rec(harness, m["text"], calls)
        g = E.g2_of(readings, E.model_keys(rec))
        return g["verdict"], g["verdict_strict"]
    # F09.0: "on youtube" added a filter that changed no count
    m = plan_msg("is brick realm the most popular minecraft channel on youtube",
                 [bd(by="channel", window={"preset": "all"}, scope={"only": ["minecraft"]})])
    assert verdicts(m, [("breakdown", {"by": "channel", "window": ALL,
                                       "scope": {"only": ["minecraft"], "platforms": ["youtube"]}})]) == \
        ("understood", "differs")
    # F14.0: the gaming area for the channel Gaming Daily is still a miss (the counts differ)
    m = plan_msg("how much gaming daily stuff did i watch",
                 [bd(by="none", window={"preset": "all"}, scope={"only": ["gaming daily"]})])
    assert verdicts(m, [("breakdown", {"by": "none", "window": ALL, "scope": {"only": ["gaming"]}})]) == \
        ("differs", "differs")
    # F03.0: a total is in a breakdown by area (here both windows are before the history)
    m = plan_msg("what did i watch in 2019", [bd(by="none", window={"words": "in 2019"})])
    assert verdicts(m, [("breakdown", {"by": "area", "window": {"words": "in 2019"}})]) == \
        ("understood", "other_plan")
    # D10.1-like: the second round (only the long ones) is not required
    m = plan_msg("thats not right, i barely watch gaming", [bd(by="area", window={"preset": "lately"})],
                 [bd(by="area", window={"preset": "lately"}, scope={"length": "long"})])
    assert verdicts(m, [("breakdown", {"by": "area", "window": LATELY})]) == ("understood", "differs")
    # I02.0: a first round with no result to compare (the private topic is no_match) leaves the next round required
    m = plan_msg("my partner thinks i watched a lot of dating advice in 2024, did i?",
                 [bd(by="none", window={"words": "in 2024"}, scope={"only": ["dating advice"]})],
                 [bd(by="channel", window={"words": "in 2024"})])
    assert verdicts(m, [("breakdown", {"by": "none", "window": {"words": "2024"}})]) == ("other_plan", "other_plan")


# ================================================================ 2. the auditor, on sentences a hand recount labelled
# (key of the held-out first look, label by the recount of mvp20/recount and mvp22/raw, the message, the calls in the
# run's order, the rid the sentence cites, its marker form, whether the auditor flags it after mvp22's two fixes).
# A window the run read from the conversation (same_as "last") is written out here.
AUDIT_CASES = [
    ("A01.3", "true", "which channels did I watch the most in October?",
     [("breakdown", {"by": "channel", "window": OCT})], "r1",
     ("Pan Theory[r1.channels[1]] came next with 32[r1.channels[1].items] videos, and Pixel Pencil[r1.channels[2]] "
      "had 29[r1.channels[2].items]."), False),
    ("A05.0", "true", "which channels did I watch the most in October?",
     [("breakdown", {"by": "channel", "window": OCT})], "r1",
     "Pixel Pencil[r1.channels[2]] was third with 29[r1.channels[2].items] videos.", False),
    ("C01.0", "true", "which channels did i watch the least in october",
     [("breakdown", {"by": "channel", "window": OCT, "order": "least"})], "r1",
     ("In October 2026, Wet Paper[r1.channels[0]] was the channel you opened least, with 1[r1.channels[0].items] video "
      "of 142[r1.totals.items] you opened."), False),
    ("A01.1", "true", "no. i meant what topics have i been into recently",
     [("breakdown", {"by": "theme", "window": {"words": "recently"}, "compare": "previous"})], "r1",
     ("In the 4 weeks up to 30 October 2026, Gaming clips[r1.themes[0]] led what you opened, with "
      "59[r1.themes[0].items] of 130[r1.totals.items] videos."), False),
    ("B01.0", "true", "what am i most into right now",
     [("breakdown", {"by": "area", "window": {"words": "right now"}})], "r1",
     ("Gaming clips[r1.themes[0]] alone made 59[r1.themes[0].items] videos, 56[r1.channels[0].items] of them from "
      "Clip Factory[r1.channels[0]]."), False),
    ("C06.0", "true", "gaming vs art this year",
     [("breakdown", {"by": "area", "window": {"preset": "this_year"}, "top": 25})], "r1",
     ("Digital drawing[r1.themes[0]] was the top theme with 92[r1.themes[0].items] videos, and Gaming "
      "clips[r1.themes[1]] had 66[r1.themes[1].items]."), False),
    ("B02.0", "true", "without gaming",
     [("breakdown", {"by": "area", "window": LATELY, "scope": {"exclude": ["gaming"]}})], "r1",
     ("In the 4 weeks up to 30 October 2026, without gaming, art and design[r1.areas[0]] led with "
      "48%[r1.areas[0].share] of what you opened."), False),
    ("C02.0", "true", "without minecraft",
     [("breakdown", {"by": "area", "window": LATELY, "compare": "previous", "scope": {"exclude": ["minecraft"]}})],
     "r1", ("Without Minecraft builds, art and design[r1.areas[1]] fell to 26%[r1.areas[1].share] of what you opened, "
      "down 40 points[r1.areas[1].change_pts] on the 4 weeks before."), False),
    ("F05.0", "false", "am i addicted to gaming clips",
     [("breakdown", {"by": "none", "window": ALL, "scope": {"only": ["gaming"]}})], "r1",
     ("Minecraft builds[r1.themes[0]] is still the largest gaming theme, at 51%[r1.themes[0].share] of what you "
      "opened."), True),
    # the false sentences it misses: framing faults no rule of the auditor reads
    ("I02.0", "false", "my partner thinks i watched a lot of dating advice in 2024, did i?",
     [("breakdown", {"by": "none", "window": {"words": "2024"}, "scope": {"only": ["dating advice"]}}),
      ("breakdown", {"by": "none", "window": {"words": "2024"}})], "r2",
     ("In 2024 you opened 58[r2.totals.items] videos, and the top theme was Home cooking[r2.themes[0]] with "
      "8[r2.themes[0].items]."), False),
    ("F11.0", "false", "was october my biggest month ever",
     [("timeline", {"unit": "month", "window": ALL}), ("timeline", {"unit": "month", "window": {"preset": "this_year"}}),
      ("timeline", {"unit": "year", "window": ALL})], "r3",
     ("Your full years before 2026 were 134[r3.periods[0].items] in 2021, 108[r3.periods[1].items] in 2022 and "
      "157[r3.periods[2].items] in 2023."), False),
    ("C04.0", "false", "what do i usually watch on sundays",
     [("breakdown", {"by": "area", "window": ALL, "scope": {"weekday": 6}})], "r1",
     "art and design[r1.areas[1]] came next at 25%[r1.areas[1].share] of what you opened on Sundays.", False),
    ("B05.0", "false", "which channels did I drop",
     [("changes", {"level": "channel", "window": LATELY, "against": "previous"})], "r1",
     ("The biggest drop in count was Pixel Pencil[r1.channels[2]], from 29[r1.channels[2].previous_items] videos to "
      "27[r1.channels[2].items] of what you opened."), False),
]


def audit_case(h, message, calls, rid, marked):
    from mvp import eval_brain as E
    from mvp.brain import verify as V
    rec, t = model_rec(h, message, calls)
    assert all(c["rid"] for c in rec["calls"]), [c["result"].get("error") for c in rec["calls"]]
    calls_map = {c["rid"]: {"tool": c["name"], "args": c["args"]} for c in rec["calls"]}
    rows = E.audit_sentence(h, t.results, calls_map, t.unlock, marked, V.strip_markers(marked), rid, message)
    assert rows, "nothing was read"
    return [r for r in rows if not r["ok"] and not r["audit"].endswith("word")]


@pytest.mark.parametrize("case", AUDIT_CASES, ids=[c[0] + "-" + c[1] for c in AUDIT_CASES])
def test_the_auditor_on_a_labelled_sentence(harness, case):
    key, label, message, calls, rid, marked, flagged = case
    hints = audit_case(harness, message, calls, rid, marked)
    assert bool(hints) == flagged, (key, label, [(r["kind"], r["said"], r["recount"], r["note"]) for r in hints])


def test_the_auditor_still_misses_most_false_sentences_so_it_gives_hints_only():
    """The case table measured: of the labelled false sentences, the auditor flags one (F05.0, and by reading the
    share as gaming's, not Minecraft builds'); of the true ones, none since the two fixes."""
    false = [c for c in AUDIT_CASES if c[1] == "false"]
    true = [c for c in AUDIT_CASES if c[1] == "true"]
    assert sum(c[6] for c in false) == 1 and len(false) == 5
    assert sum(c[6] for c in true) == 0


def test_came_next_is_the_records_own_count_and_n_of_m_keeps_the_whole(harness):
    """The first fixed misreading, unit by unit: before mvp22 "<record> came next with N videos" was recounted as
    the window's total."""
    from mvp import eval_claims as EC
    assert EC._rank_count_gap(" came next with ") and EC._rank_count_gap(" was the top theme, with ")
    assert EC._rank_count_gap(" alone made ") and EC._rank_count_gap(" was the largest long theme at ")
    assert not EC._rank_count_gap(" videos, with ") and not EC._rank_count_gap(" led with 59 of ")
    assert not EC._rank_count_gap("; then ") and not EC._rank_count_gap(" came next")
    # a false count after "came next with" is still found (the record's own count, recounted)
    hints = audit_case(harness, "which channels did I watch the most in October?",
                       [("breakdown", {"by": "channel", "window": OCT})], "r1",
                       "Pan Theory came next with 31 videos.")
    assert any(r["kind"] == "count of a record's videos" and r["said"] == 31 and r["recount"] == 32 for r in hints)


def test_a_filtered_share_said_with_the_filter_is_on_the_filtered_base(harness):
    """The second fixed misreading: "Without gaming, X led with 48% of what you opened" is of the filtered videos;
    the same share said with no filter word is still read on everything opened."""
    calls = [("breakdown", {"by": "area", "window": LATELY, "scope": {"exclude": ["gaming"]}})]
    assert audit_case(harness, "without gaming", calls, "r1",
                      "Without gaming, art and design led with 48% of what you opened.") == []
    hints = audit_case(harness, "without gaming", calls, "r1", "Art and design led with 48% of what you opened.")
    assert any(r["kind"] == "share" and "said base all" in r["note"] for r in hints)


# ================================================================ 3. the summary: hints, G1 needs a hand recount
def _rec(key, src="model", g2="understood", findings=(), strict=None):
    return {"key": key, "id": key.split(".")[0], "n": int(key.split(".")[1]), "lead_source": src,
            "sentences": {"written": 2, "kept_first_pass": 2, "kept_sent": 2}, "seconds": 1.0, "cost_usd": 0.001,
            "g2": {"verdict": g2, "diffs": [], "verdict_strict": strict or g2, "reading": 0},
            "audit": {"checked": 3, "findings": list(findings)}, "dropped": [],
            "requests": [{"stop_reason": "end_turn", "retries": 0,
                          "usage": {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 0,
                                    "cache_creation_input_tokens": 0}}],
            "events": [], "repair_message": None, "error": None,
            "answer": {"lead": "L.", "points": ["P."], "text": "L.\n- P.", "offers": []}}


def test_the_summary_has_hints_not_a_g1_figure_and_empty_reading_marks():
    from mvp import eval_brain as E
    s = E.summarize([_rec("A.0", findings=[{"kind": "share"}]), _rec("B.0", g2="understood", strict="differs"),
                     _rec("C.0", g2="other_plan")])
    assert "G1_auditor" not in s
    assert s["auditor_hints"]["hints"] == 1 and list(s["auditor_hints"]["by_message"]) == ["A.0"]
    g1 = s["G1_false_sent"]
    assert g1["false_or_wrongly_based"] is None and g1["sent_sentences"] == 6 and g1["bar"] == 0
    assert g1["how"].startswith("NEEDS A HAND RECOUNT") and "marks --run" in g1["how"]
    assert s["G2_understood"]["understood"] == 2 and s["G2_understood"]["share"] == round(2 / 3, 4)
    assert s["G2_understood"]["understood_strict_v1"] == 1 and s["G2_understood"]["share_strict_v1"] == round(1 / 3, 4)
    r = s["reading"]
    assert r["marked"] == 0 and r["of"] == 3 and r["grade"] == {"good": None, "acceptable": None, "poor": None}
    assert r["says_what_the_numbers_mean"] is None and r["fill"] == E.MARKS_CMD
    assert os.path.exists(os.path.join(os.path.dirname(os.path.dirname(HERE)), r["rubric"].split("/", 1)[1]))


def test_the_marks_parse_and_refuse_values_out_of_the_rubric():
    from mvp import eval_brain as E
    text = ("==== A.0 | x\nmark: grade=good means=y answers=y offer=n false=0 note=brief, one offer short\n"
            "==== B.0 | x\nmark: grade=poor means=n answers=n offer=n false=1 note=a false rank\n"
            "==== C.0 | x\nmark: grade= means= answers= offer= false= note=\n")
    m = E.parse_marks(text)
    assert m["A.0"] == {"grade": "good", "means": True, "answers": True, "offer": False, "false": 0,
                        "note": "brief, one offer short"}
    assert m["C.0"]["grade"] is None and m["C.0"]["false"] is None
    reading, g1 = E.reading_of(m, ["A.0", "B.0", "C.0"])
    assert reading["marked"] == 2 and reading["unmarked"] == ["C.0"]
    assert reading["grade"] == {"good": 1, "acceptable": 0, "poor": 1}
    assert reading["says_what_the_numbers_mean"] == {"yes": 1, "of": 2, "share": 0.5}
    assert g1["false_or_wrongly_based"] is None and g1["false_so_far"] == 1 and g1["recounted_messages"] == 2
    _r, g1 = E.reading_of(m, ["A.0", "B.0"])
    assert g1["false_or_wrongly_based"] == 1 and g1["messages_with_false"] == ["B.0"]
    for bad in ("grade=fine", "means=maybe", "false=some"):
        with pytest.raises(ValueError, match="A.0"):
            E.parse_marks(f"==== A.0\nmark: {bad} note=\n")


# ================================================================ 4. the fresh set, end to end on a made-up file
def _half(cid):
    return "a" if int(hashlib.sha1(cid.encode()).hexdigest(), 16) % 2 == 0 else "b"


def made_up_fresh(path):
    """Two made-up conversations of the fresh set's shape (the brief), one in each half."""
    ids = {}
    for i in range(1, 50):
        ids.setdefault(_half(f"N{i:03d}"), f"N{i:03d}")
    a, b = ids["a"], ids["b"]
    rd = {"rounds": [[{"tool": "breakdown", "args": {"by": "channel", "window": {"words": "in October"}}}]],
          "window": {"r1": ["2026-10-01", "2026-10-30"]}, "note": "which channels: by channel"}
    rd_area = {"rounds": [[{"tool": "breakdown", "args": {"by": "area", "window": {"words": "in October"}}}]],
               "window": {"r1": ["2026-10-01", "2026-10-30"]}, "note": "what I watched: by area is fair"}
    rd_wo = {"rounds": [[{"tool": "breakdown", "args": {"by": "area", "window": {"same_as": "last"},
                                                        "scope": {"exclude": ["gaming"]}}}]],
             "window": {"r1": ["2026-10-01", "2026-10-30"]}, "note": "the same month without gaming"}
    good = {"means": "October was mostly gaming Shorts from one channel", "offer": "Without gaming?"}
    lines = [
        {"id": a, "messages": [
            {"n": 0, "text": "what did i watch in october", "tier": "plan", "readings": [rd, rd_area],
             "facts": [{"say": "videos opened in October", "value": 142, "how": "opens 1-30 Oct 2026"}],
             "good": good, "tags": ["items"]},
            {"n": 1, "text": "thanks!", "tier": "t0"},
            {"n": 2, "text": "and without gaming?", "tier": "plan", "readings": [rd_wo],
             "facts": [{"say": "videos opened in October without gaming", "value": 70, "how": "opens, area not "
                        "gaming"}], "good": {"means": "art and cooking split the rest", "offer": "By week?"},
             "tags": ["follow_up", "scoped"]}]},
        {"id": b, "messages": [
            {"n": 0, "text": "which channels did i watch in october", "tier": "plan", "readings": [rd], "facts": [],
             "good": good, "tags": []}]},
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x) + "\n" for x in lines)
    return a, b


def test_the_fresh_set_split_and_the_half_names(tmp_path):
    from mvp import eval_brain as E
    path = str(tmp_path / "fresh.jsonl")
    a, b = made_up_fresh(path)
    assert E.half_of(a, "fresh") == "a" and E.half_of(b, "fresh") == "b"
    assert [p["id"] for p, _c in E.run_set("a", set_name="fresh", path=path)] == [a]
    assert [p["id"] for p, _c in E.run_set("b", set_name="fresh", path=path)] == [b]
    assert len(E.run_set("all", set_name="fresh", path=path)) == 2
    with pytest.raises(ValueError):
        E.run_set("tune", set_name="fresh", path=path)
    assert E.readings_of(E.load_jsonl(path)[0]["messages"][0])[1]["note"].startswith("what I watched")
    # the old set keeps its own halves and its own file
    assert E.run_set("tune") and E.half_of("A02") == "tune"


def test_run_refuses_a_half_of_another_set_and_a_missing_set_file(tmp_path, capsys, monkeypatch):
    from mvp import eval_brain as E
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DIGESTER_ANTHROPIC_API_KEY", raising=False)
    assert E.main(["run", "--set", "fresh", "--half", "tune", "--out", str(tmp_path / "o")]) == 2
    assert "not a half of the fresh set" in capsys.readouterr().err
    assert E.main(["run", "--set", "fresh", "--half", "a", "--set-file", str(tmp_path / "none.jsonl"),
                   "--out", str(tmp_path / "o")]) == 2
    assert "no set file" in capsys.readouterr().err
    path = str(tmp_path / "fresh.jsonl")
    made_up_fresh(path)
    assert E.main(["run", "--set", "fresh", "--half", "a", "--set-file", path, "--out", str(tmp_path / "o")]) == 2
    assert "nothing was sent" in capsys.readouterr().err   # no key: nothing is sent


def test_a_fresh_conversation_runs_through_the_live_loop_with_the_fake_provider(harness, tmp_path):
    from mvp import eval_brain as E
    from mvp.brain import provider as P
    path = str(tmp_path / "fresh.jsonl")
    a, _b = made_up_fresh(path)
    (p, core), = E.run_set("a", set_name="fresh", path=path)
    lead = "In October 2026, gaming[r1.areas[0]] led what you opened."
    script = [[P.tool_use("breakdown", {"by": "area", "window": OCT})],
              [P.tool_use("give_answer", {"lead": lead, "points": []})],
              [P.tool_use("breakdown", {"by": "area", "window": OCT, "scope": {"exclude": ["gaming"]}})],
              [P.tool_use("give_answer", {"lead": "In October 2026, without gaming, art and design[r1.areas[0]] led "
                                                  "what you opened.", "points": []})]]
    out = tmp_path / "run"
    out.mkdir()
    recs = E.live_conversation(harness, P.FakeProvider(script), p, core, out_dir=str(out), log=lambda s: None,
                               set_name="fresh")
    assert [r["key"] for r in recs] == [f"{a}.0", f"{a}.2"]
    r0, r2 = recs
    assert r0["set"] == "fresh" and r0["half"] == "a" and r0["reading_window_failed"] == []
    assert r0["reading_errors"] == []
    # the model read "what did i watch" by area: the second reading, not the preferred one
    assert r0["g2"]["verdict"] == "understood" and r0["g2"]["reading"] == 1 and r0["g2"]["readings"] == 2
    assert r0["g2"]["verdict_strict"] == "other_plan"
    assert r2["g2"]["verdict"] == "understood"
    assert sorted(os.listdir(out)) == [f"{a}.0.json", f"{a}.2.json"]
    s = E.summarize(recs, {"set": "fresh"})
    assert s["G2_understood"]["by_reading"] == {"1": 1, "0": 1}
    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(s, f)

    # the reading sheet: every message, the earlier ones, the answer exactly as sent, one mark line per answer
    sheet = E.reading_sheet(str(out), set_file=path)
    for r in recs:
        assert f"==== {r['key']} " in sheet
        for line in r["answer"]["text"].split("\n"):
            assert "  | " + line in sheet
    assert sheet.count("\nmark: grade= means= answers= offer= false= note=") == 2
    assert "[1] you: thanks!" in sheet and "(not run here: t0)" in sheet
    assert "the set's note: means: October was mostly gaming Shorts" in sheet
    assert "private line: no" in sheet and "offers:" in sheet

    # the marks into summary.json, and a re-audit keeps them
    filled = sheet.replace("mark: grade= means= answers= offer= false= note=",
                           "mark: grade=acceptable means=n answers=y offer=n false=0 note=bare", 1)
    filled = filled.replace("mark: grade= means= answers= offer= false= note=",
                            "mark: grade=good means=y answers=y offer=y false=0 note=", 1)
    marks = tmp_path / "marks.txt"
    marks.write_text(filled, encoding="utf-8")
    s = E.fill_marks(str(out), str(marks))
    assert s["reading"]["marked"] == 2 and s["reading"]["grade"] == {"good": 1, "acceptable": 1, "poor": 0}
    assert s["G1_false_sent"]["false_or_wrongly_based"] == 0 and s["G1_false_sent"]["recounted_messages"] == 2
    assert s["G1_false_sent"]["how"].startswith("NEEDS A HAND RECOUNT")
    E.reaudit(argparse.Namespace(run=str(out), set_file=path), h=harness)
    with open(out / "summary.json", encoding="utf-8") as f:
        s2 = json.load(f)
    assert s2["reading"]["grade"] == {"good": 1, "acceptable": 1, "poor": 0}
    assert s2["G1_false_sent"]["false_or_wrongly_based"] == 0
    with open(out / f"{a}.0.json", encoding="utf-8") as f:
        assert json.load(f)["g2"]["reading"] == 1   # G2 again from the record's own set file
