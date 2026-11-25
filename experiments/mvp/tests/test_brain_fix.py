"""mvp20 fix (the brain's thin live slice, closed): what the two checkers of the tuned slice found, each class
reproduced first and fixed by a rule. Offline: no model call, no network. The library is the made-up one of
tests/brain_library.py; every title, channel and theme is made up.

Two sources: the hand recount of the held-out answers that were sent (5 false sentences, all in code-lead answers),
and the verifier attack (eval/brain_attack_cases.py: false and true sentences on real tool results, each recounted by
the attacker from the rows). Each class here has its false sentence (dropped) and a true twin (kept)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys, person  # noqa: E402,F401

MVP = os.path.dirname(HERE)
PLANTED = os.path.join(MVP, "eval", "brain_planted.json")


def _attack():
    import importlib.util
    spec = importlib.util.spec_from_file_location("brain_attack_cases",
                                                  os.path.join(MVP, "eval", "brain_attack_cases.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _attack_ledgers(e):
    """{name: (envelopes, turn dict)} of the attack's ledgers from today's tools (took_ms zeroed: a timing)."""
    from mvp.brain import tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine
    A = _attack()
    out = {}
    for name, (msg, calls) in A.LEDGERS.items():
        t = TL.Turn(e["bot"], person(e), NOW, message=msg, search=FakeEngine())
        envs = [TL.call(t, tool, args) for tool, args in calls]
        for env_ in envs:
            env_["took_ms"] = 0
            assert not env_.get("is_error"), (name, env_)
        vt = V.Turn.of(t)
        out[name] = (json.loads(json.dumps(envs, default=str)),
                     {"message": msg, "unlock": vt.unlock, "today": vt.today.isoformat(), "names": vt.names,
                      "sensitive_names": vt.sensitive_names})
    return out


def test_the_attack_ledgers_frozen_in_the_planted_set_are_todays_tools(brain):
    got = _attack_ledgers(brain)
    with open(PLANTED, encoding="utf-8") as f:
        data = json.load(f)
    if os.environ.get("MVP_FREEZE_ATTACK") == "1":   # rewrite them (then run eval/build_brain_planted.py)
        for name, (envs, t) in got.items():
            data["ledgers"]["attack_" + name] = envs
            data.setdefault("attack_turns", {})[name] = t
        with open(PLANTED, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
    for name, (envs, t) in got.items():
        assert data["ledgers"]["attack_" + name] == envs, name
        assert data["attack_turns"][name] == t, name


def test_every_false_sentence_of_the_attack_is_dropped_and_its_true_ones_counted():
    from mvp.brain import planted as P
    s = P.score()
    a, t = s["by_source"]["attack"], s["by_source"]["attack_true"]
    kept = [r["id"] for r in s["rows"] if r.get("source") == "attack" and r["kept"]]
    assert a["false"] == 169 and a["false_dropped"] == 169, kept   # 166 sentences, 3 tried as a lead and a point
    assert t["true"] == 60 and t["true_kept"] >= ATTACK_TRUE_KEPT
    # the builder's own bar is unchanged by the attack's cases
    assert s["false_dropped"] == s["false"] and s["true_kept"] == s["true"]


ATTACK_TRUE_KEPT = 41   # the tuned verifier kept 42 of 60; the fix closes t19 again (a change said "from 2021 to 2026")


# ================================================================ helpers on the frozen attack ledgers
_DATA = {}


def _data():
    if not _DATA:
        with open(PLANTED, encoding="utf-8") as f:
            _DATA.update(json.load(f))
    return _DATA


def _ledger(key):
    from datetime import date
    from mvp.brain import verify as V
    d = _data()
    t = d["attack_turns"][key]
    turn = V.Turn(message=t["message"], unlock=t["unlock"], today=date.fromisoformat(t["today"]), names=t["names"],
                  sensitive_names=t["sensitive_names"])
    return V.Ledger(json.loads(json.dumps(d["ledgers"]["attack_" + key]))), turn


def _check(key, lead, points=()):
    from mvp.brain import verify as V
    led, turn = _ledger(key)
    return V.check_answer({"lead": lead, "points": list(points)}, led, turn)


def _attack_case(cid):
    from mvp.brain import planted as P
    d = _data()
    c = next(c for c in d["cases"] if c["id"] in ("attack_" + cid, "attack_" + cid + "_P", "attack_" + cid + "_L"))
    kept, reasons, v = P.outcome(c, d["ledgers"])
    if c["expect"] == "private_line":
        kept = kept and not v.private_line
    return kept, reasons


OCT = "In October 2026, you opened 142[r1.totals.items] videos."
LATELY = "In the 4 weeks up to 30 October 2026, you opened 130[r1.totals.items] videos."
FELL = ("Digital drawing[r1.themes[2]] fell from 57%[r1.themes[2].previous_share] to 21%[r1.themes[2].share] of what "
        "you opened.")
NOGAMING = "In October 2026, without gaming, you opened 70[r1.totals.items] videos."
# (class, the attack's false sentences that the tuned verifier kept, a true twin: (ledger, lead, point or None))
CLASSES = [
    ("a time said with a range word is that stretch: since, by, until, up to, between, before, after, on a day, two "
     "times joined", ["E01", "E04", "E05", "E06", "E07", "D02", "D03", "D08", "S09", "C02", "C03", "C04"],
     ("tl_year", "In all your history, you opened 723[r1.totals.items] videos.",
      "You opened 134[r1.periods[0].items] in 2021, 108[r1.periods[1].items] in 2022 and 157[r1.periods[2].items] "
      "in 2023.")),
    ("'ever' needs all their history", ["D04"],
     ("changes_area", "Since 1 January 2021 up to 30 October 2026, you opened 723[r1.totals.items] videos.",
      "In 2025, Watercolor painting[r1.change.rising[2]] held 87%[r1.change.rising[2].peak_share] of what you "
      "opened.")),
    ("a platform, length or day word on a count is bound by the scope, a cell or the rows",
     ["A01", "A02", "A06", "A08", "B02", "B03", "B06", "B09", "N03", "M05"],
     ("ch_oct", OCT, "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] Shorts.")),
    ("a comparison needs the value it compares with, in the order the words say",
     ["F03", "P02", "D07", "X08", "G01", "G04"],
     ("ch_oct", OCT, "Clip Factory[r1.channels[0]] led with 61[r1.channels[0].items] videos, more than Pan Theory's "
                     "32[r1.channels[1].items].")),
    ("a percent change's word is its sign", ["G02"],
     ("cmp_2023", "In 2023 you opened 157[r1.totals.items] videos, against 108[r1.previous.items] in 2022.",
      "You opened 45% more[=pct_change(r1.totals.items, r1.previous.items)] videos in 2023 than in 2022.")),
    ("the window before is the result's own", ["G03", "F04"], ("area_lately", LATELY, FELL)),
    ("'from A to B': A is the earlier value", ["X01", "X02", "X03"], ("area_lately", LATELY, FELL)),
    ("'only', 'all', 'nothing else', 'just N areas' of a result that left the private topic out",
     ["R01", "R02", "R03", "R05", "R06", "R08", "R09", "R10", "R11"],
     ("area_2024", "In 2024 you opened 8[r1.totals.items] videos.",
      "In 2024, Pan Theory[r1.channels[0]] made 8[r1.channels[0].items] videos.")),
    ("'all from' a channel needs the row's own list to hold only it", ["S05"],
     ("ch_oct", OCT, "Gaming clips[r1.themes[0]] came to 66[r1.themes[0].items] videos, 61[r1.themes[0].channels[0]."
                     "items] of them from Clip Factory[r1.themes[0].channels[0]].")),
    ("'usually' at an hour needs more than half there", ["H02"],
     ("ch_oct", OCT, "Your busiest hour was 7 pm[r1.when.busiest_hours[0].hour].")),
    ("the first or the last item is the earliest or the latest shown, by its own time", ["Q03", "Q05", "Q12"],
     ("items_30oct", "On 30 October 2026, you opened 4[r1.items.count] videos.",
      "The last video you opened on 30 October was Cooking soup on the 30th[r1.items[3]].")),
    ("the count of a first-time list is the rows shown", ["N04"],
     ("first_cf", "In all your history, you first opened a Clip Factory video on 1 October 2026[r1.items[0].when].",
      None)),
    ("why they opened it, what a video told them, who makes it: not in the export",
     ["T01", "T02", "T05", "T07", "T09"],
     ("ch_oct", OCT, "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of your videos.")),
    ("a filtered result's numbers said of more than its scope",
     ["L01", "L03", "L05", "L06", "L07", "L09", "L11", "L13", "M02", "M03", "M04"],
     ("area_oct_nogaming", NOGAMING, "Pan Theory[r1.channels[0]] had 32[r1.channels[0].items] videos.")),
    ("the count of a filtered list never leans on the lead's scope", ["L10"],
     ("area_oct_nogaming", NOGAMING, "Pan Theory[r1.channels[0]] had 32[r1.channels[0].items] videos.")),
    ("an ordinal of a least-ordered result says 'least'", ["W02", "W05"],
     ("ch_oct", OCT, "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of your videos.")),
    ("a point on another window says its window", ["U01", "U02", "U05"],
     ("ch_oct+ch_week", OCT, "In the last 7 days, Clip Factory[r2.channels[0]] led with 13[r2.channels[0].items] "
                             "videos.")),
]


@pytest.mark.parametrize("cls,false_ids,twin", CLASSES, ids=[c[0][:40] for c in CLASSES])
def test_each_attack_class_drops_its_false_sentences_and_keeps_a_true_twin(cls, false_ids, twin):
    for cid in false_ids:
        kept, reasons = _attack_case(cid)
        assert not kept, (cid, reasons)
    key, lead, point = twin
    v = _check(key, lead, [point] if point else [])
    assert v.lead_ok, [o.reasons for o in v.lead]
    if point:
        o = [o for o in v.outcomes if o.where == "point"][0]
        assert o.kept, (point, o.reasons, o.details)


# ================================================================ the recount's five false sentences, by class
def test_a_base_said_in_words_carries_the_scope_in_its_own_clause():
    # B03.0's class: the long videos ranked "led what you opened"; F05.0's: a share of only gaming "of what you opened"
    v = _check("area_oct_long", "In October 2026, food and cooking[r1.areas[0]] led what you opened, with "
                                "32[r1.areas[0].items] long videos.")
    assert not v.lead_ok and "base" in v.lead[0].reasons
    v = _check("area_oct_long", "In October 2026, food and cooking[r1.areas[0]] led the long videos you opened, with "
                                "32[r1.areas[0].items].")
    assert v.lead_ok
    # the scope said in the sentence's opening words governs its base (the attack's true t39, t43)
    v = _check("area_oct_nogaming", "In October 2026, without gaming, art and design[r1.areas[0]] led what you "
                                    "opened, with 34[r1.areas[0].items] videos.")
    assert v.lead_ok
    v = _check("ch_year_art", "This year up to 30 October 2026, with only art and design, you opened "
                              "133[r1.totals.items] art videos.",
               ["Pixel Pencil[r1.channels[0]] made 69%[r1.channels[0].share] of what you opened."])
    assert not v.outcomes[1].kept and "base" in v.outcomes[1].reasons


def test_still_claims_another_time():
    # F05.0: "Minecraft builds is still the largest gaming theme" of one window
    v = _check("ch_oct", OCT, ["Clip Factory[r1.channels[0]] is still your top channel, with "
                               "61[r1.channels[0].items] videos."])
    assert "wrong_window" in v.outcomes[1].reasons
    v = _check("ch_oct", OCT, ["Clip Factory[r1.channels[0]] is your top channel, with 61[r1.channels[0].items] "
                               "videos."])
    assert v.outcomes[1].kept


def test_a_list_said_before_a_year_is_not_the_years_before_it():
    # F11.0: "Your full years before 2026 were 134 in 2021, 108 in 2022 and 157 in 2023" (2024 and 2025 left out)
    v = _check("tl_year", "In all your history, you opened 723[r1.totals.items] videos.",
               ["Your full years before 2026 were 134[r1.periods[0].items] in 2021, 108[r1.periods[1].items] in 2022 "
                "and 157[r1.periods[2].items] in 2023."])
    assert "wrong_window" in v.outcomes[1].reasons


def test_a_rank_of_rows_that_leave_most_of_the_total_out_is_not_proved(brain):
    # I02.0: the turn unlocked dating; 58 videos in 2024, 50 of them the unlocked topic, which no theme row holds
    from mvp.brain import tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine
    t = TL.Turn(brain["bot"], person(brain), NOW, message="did i watch a lot of dating advice in 2024",
                search=FakeEngine())
    env_ = TL.call(t, "breakdown", {"by": "none", "window": {"words": "2024"}})
    sh = env_["sheet"]
    th = sh["themes"][0]
    assert sh["totals"]["items"] - sum(r["items"] for r in sh["themes"]) >= th["items"]
    vt = V.Turn.of(t)
    lead = f"In 2024 you opened {sh['totals']['items']}[r1.totals.items] videos."
    v = V.check_answer({"lead": lead, "points": [f"The top theme was {th['name']}[r1.themes[0]] with "
                                                 f"{th['items']}[r1.themes[0].items]."]}, t.results, vt)
    assert v.lead_ok and "rank" in v.outcomes[1].reasons, [o.reasons for o in v.outcomes]
    ch = sh["channels"][0]
    v = V.check_answer({"lead": lead, "points": [f"{ch['name']}[r1.channels[0]] made {ch['items']}[r1.channels[0]."
                                                 f"items] of them."]}, t.results, vt)
    assert v.outcomes[1].kept, v.outcomes[1].reasons


# ================================================================ the code lead and the points under it
def _failed_lead_verdict(key, failing_lead, points):
    v = _check(key, failing_lead, points)
    assert not v.lead_ok
    return v


def test_points_are_checked_again_under_the_code_lead():
    # C04.0's class: the model's lead named an AREA first; its point "came next" went out under a code lead that named
    # a THEME first. Under a code_form lead a 'came next' point follows only the lead's own list
    from mvp.brain import fallback as FB
    led, turn = _ledger("ch_oct")
    v = _failed_lead_verdict("ch_oct", "In October 2026, gaming[r1.areas[0]] led what you opened because you were "
                                       "bored.",
                             ["Art and design[r1.areas[1]] came next with 34[r1.areas[1].items] videos.",
                              "Pan Theory[r1.channels[1]] came next with 32[r1.channels[1].items] videos."])
    a = FB.answer(led, v, turn)
    assert a["how"] == "code_form" and a["points"] == ["Pan Theory came next with 32 videos."], a
    # under a template lead (a scoped result), the template prefers the list the model's own lead cited
    led, turn = _ledger("area_oct_nogaming")
    v = _failed_lead_verdict("area_oct_nogaming", "In October 2026, without gaming, art and design[r1.areas[0]] led "
                                                  "what you opened because you were bored.",
                             ["Without gaming, food and cooking[r1.areas[1]] came next with 32[r1.areas[1].items] "
                              "videos."])
    a = FB.answer(led, v, turn)
    assert a["how"] == "template" and a["lead"].startswith("In October 2026, without gaming, art and design led"), a
    assert a["points"] == ["Without gaming, food and cooking came next with 32 videos."], a


def test_the_template_says_the_scope_first_and_a_length_in_the_rank_base():
    from mvp.brain import fallback as FB
    led, turn = _ledger("area_oct_long")
    lead = FB.code_lead(led, None, turn)
    assert lead["how"] == "template" and "led the long videos you opened, with" in lead["lead"], lead
    led, turn = _ledger("tl_year")
    lead = FB.code_lead(led, None, turn)
    assert lead["lead"].startswith("In all your history, ") and "(" not in lead["lead"], lead


def test_a_bare_counted_lead_with_no_point_is_the_plain_line_with_no_scope_line():
    # D04.1: "here is what I counted (Instagram only)." with nothing after it
    from mvp.brain import answer as A, fallback as FB
    led, turn = _ledger("ch_oct_sat")
    real = FB.code_lead

    def only_counted(ledger, verdict=None, turn=None, cited=None):
        out = real(ledger, verdict, turn, cited)
        return dict(out, how="template", lead="On Saturdays, here is what I counted.",
                    marked="On Saturdays, here is what I counted.")
    FB.code_lead = only_counted
    try:
        v = _failed_lead_verdict("ch_oct_sat", "On Saturdays in October 2026, you opened videos because you were "
                                               "bored.", [])
        a = FB.answer(led, v, turn)
    finally:
        FB.code_lead = real
    assert a["how"] == "plain" and a["lead"] == FB.PLAIN
    out = A.build(led, code=a)
    assert out["scope_line"] is None and out["text"] == FB.PLAIN


def test_the_scope_line_closes_its_bracket_and_says_a_part_once():
    from mvp.brain import answer as A
    led, _turn = _ledger("tl_year")
    res = next(iter(led.by_rid.values()))
    res.meta["filters_said"] = "only gaming (area)"
    line = A.scope_line(res)
    assert line.count("(") == line.count(")") and "export ends" not in line, line
    led, _turn = _ledger("ch_oct_sat")
    res = next(iter(led.by_rid.values()))
    line = A.scope_line(res)
    assert line.lower().count("saturdays") == 1, line
