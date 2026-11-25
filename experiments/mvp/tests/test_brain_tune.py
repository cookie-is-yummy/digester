"""The brain's tune of mvp20 (the tune half of the live slice): each verifier change keeps a TRUE sentence the live run
or the step-1 audit wrote, and its one-change FALSE twin is still dropped; the scope rule's waiver for points and the
scope line it relies on; the code lead of a result of saves; the invented top-level key (test_brain_slice); a learned
point rendered from its marker; and the examples of prompts/brain_v2.md. Offline, the FAKE provider only. The library
is the made-up one of tests/brain_library.py; every expected number was recounted by hand from its rows.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures)
    NOW, TODAY, brain, built, no_real_keys, person)

W = {"preset": None, "same_as": None, "words": None}
SC = {"exclude": [], "how": "opened", "length": "any", "only": [], "platforms": [], "weekday": None}


def win(**kw):
    return dict(W, **kw)


def scope(**kw):
    return dict(SC, **kw)


CALLS = {
    "oct": ("breakdown", {"by": "channel", "window": win(words="in October"), "scope": scope()}),
    "art": ("breakdown", {"by": "channel", "window": win(words="this year"), "scope": scope(only=["art"])}),
    "ytweek": ("breakdown", {"by": "none", "window": win(preset="last_week"), "scope": scope(platforms=["youtube"])}),
    "mathmonths": ("timeline", {"unit": "month", "window": win(preset="this_year"), "scope": scope(only=["math"])}),
    "years": ("timeline", {"unit": "year", "window": win(words="since 2021"), "scope": scope()}),
    "autumn_any": ("compare", {"a": win(words="this autumn"), "b": win(words="last autumn"), "by": "none",
                               "scope": scope(how="any")}),
    "autumn_nogaming": ("compare", {"a": win(words="this autumn"), "b": win(words="last autumn"), "by": "area",
                                    "scope": scope(exclude=["gaming"])}),
    "lately": ("breakdown", {"by": "area", "window": win(preset="lately"), "scope": scope()}),
    "saved_oct": ("breakdown", {"by": "area", "window": win(words="in October"), "scope": scope(how="saved")}),
    "y2023": ("compare", {"a": win(words="2023"), "b": win(words="2022"), "by": "none", "scope": scope()}),
}


@pytest.fixture()
def harness(brain):
    from mvp import eval_brain as E
    return E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                     now=NOW)


MESSAGE = "what did i watch since 2021, and in 2023 against 2022"


def ledger(h, *keys, message=MESSAGE):
    """The results of the named calls, in order (r1, r2, ...), on one turn."""
    from mvp.brain import tools as TL, verify as V
    t = h.turn(message)
    for k in keys:
        tool, args = CALLS[k]
        r = TL.call(t, tool, args)
        assert not r.get("is_error"), (k, r)
    return V.Ledger(t.results), V.Turn.of(t), t


def check(h, keys, s, where="point"):
    from mvp.brain import verify as V
    led, vt, _t = ledger(h, *([keys] if isinstance(keys, str) else keys))
    return V.check_sentence(s, led, vt, where)


def kept(h, keys, s, where="point"):
    o = check(h, keys, s, where)
    assert o.kept, (s, o.reasons, o.details)


def dropped(h, keys, s, where="point", reason=None):
    o = check(h, keys, s, where)
    assert not o.kept, s
    if reason:
        assert reason in o.reasons, (s, o.reasons)
    return o


# ================================================================ verifier classes: true kept, false twin dropped
def test_a_rows_count_said_as_n_of_the_videos_you_opened_is_a_count(harness):
    # this year, only art: Wet Paper 37 of 133 art videos (recount); October: Clip Factory 61 of 142
    kept(harness, "art", "Wet Paper[r1.channels[1]] came next with 37[r1.channels[1].items] of your art videos.")
    dropped(harness, "art", "Wet Paper[r1.channels[1]] came next with 73[r1.channels[1].items] of your art videos.",
            reason="wrong_value")
    dropped(harness, "art", "Wet Paper[r1.channels[1]] came next with 37[r1.channels[1].items] of the art videos you "
                            "saved.", reason="base")
    kept(harness, "oct", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of the videos you opened.")
    kept(harness, "oct", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of what you opened.")
    dropped(harness, "oct", "Pan Theory[r1.channels[1]] made 61[r1.channels[0].items] of the videos you opened.")


def test_the_platform_of_a_platform_scoped_result_is_its_scope_said_and_never_of_an_unscoped_one(harness):
    # the last 7 days, YouTube only: 24 videos (all 24 of the window were YouTube)
    kept(harness, "ytweek", "In the last 7 days up to 30 October 2026, you opened 24[r1.totals.items] YouTube videos.",
         "lead")
    dropped(harness, "ytweek", "In the last 7 days up to 30 October 2026, you opened 24[r1.totals.items] Instagram "
                               "videos.", "lead")
    # October unscoped: 142 items, 4 of them Instagram reels: "142 YouTube videos" is false (new guard)
    dropped(harness, "oct", "In October 2026, you opened 142[r1.totals.items] YouTube videos.", "lead",
            reason="platform_word")
    kept(harness, "oct", "In October 2026, you opened 142[r1.totals.items] videos.", "lead")
    kept(harness, "oct", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] YouTube videos.")


def test_a_periods_count_said_with_its_own_label_in_words(harness):
    # math this year by month: 6 in September 2026, 4 in October 2026; by year: 134 in 2021
    kept(harness, "mathmonths", "Of your math videos this year, 6[r1.periods[0].items] were in September 2026 and "
                                "4[r1.periods[1].items] in October 2026.")
    dropped(harness, "mathmonths", "Of your math videos this year, 6[r1.periods[0].items] were in October 2026 and "
                                   "4[r1.periods[1].items] in September 2026.")
    kept(harness, "years", "In 2021 you opened 134[r1.periods[0].items] videos.")
    dropped(harness, "years", "In 2022 you opened 134[r1.periods[0].items] videos.")
    dropped(harness, "years", "You opened 254[r1.periods[5].items] videos.")


def test_a_change_said_with_its_move_and_its_value_now(harness):
    # this autumn without gaming: food and cooking 30% (32 of 107), 13% last autumn (2 of 15): up 16.6 points
    led, vt, _t = ledger(harness, "autumn_nogaming")
    from mvp.brain import verify as V
    rows = led.get("r1").sheet["areas"]
    k = next(i for i, r in enumerate(rows) if r["name"] == "food and cooking")
    s = (f"Without gaming, food and cooking[r1.areas[{k}]] rose to 30%[r1.areas[{k}].share] of what you opened, up 17 "
         f"points[r1.areas[{k}].change_pts].")
    o = V.check_sentence(s, led, vt, "point")
    assert o.kept, (o.reasons, o.details)
    for bad in (s.replace("rose to", "fell to").replace("up 17", "down 17"),        # the direction
                s.replace("up 17 points", "up 16 points"),                         # the move
                s.split(", up 17")[0] + "."):                                      # one value only
        assert not V.check_sentence(bad, led, vt, "point").kept, bad


def test_a_base_of_everything_said_with_its_three_verbs(harness):
    # this autumn, opened, liked or saved: 192 items; last autumn 15 (recount)
    kept(harness, "autumn_any", "In the autumn of 2026 up to 30 October 2026, you opened, liked or saved "
                                "192[r1.totals.items] items, against 15[r1.previous.items] in the autumn of 2025.",
         "lead")
    dropped(harness, "autumn_any", "In the autumn of 2026 up to 30 October 2026, you opened 192[r1.totals.items] items, "
                                   "against 15[r1.previous.items] in the autumn of 2025.", "lead", reason="base")


def test_fell_into_is_where_things_sit_and_fell_to_is_still_a_fall(harness):
    kept(harness, "lately", "In the 4 weeks up to 30 October 2026, what you opened fell into these "
                            "4[r1.areas.count] areas.", "lead")
    dropped(harness, "lately", "In the 4 weeks up to 30 October 2026, what you opened fell into these "
                               "5[r1.areas.count] areas.", "lead")
    dropped(harness, "lately", "Gaming[r1.areas[0]] fell to 49%[r1.areas[0].share] of what you opened.")


def test_a_theme_followed_by_posts_is_a_noun_and_a_channel_that_posts_is_outside_knowledge(harness):
    # saved in October: 3 watercolor painting, 3 home cooking (the friend's post is left out)
    led, vt, _t = ledger(harness, "saved_oct")
    from mvp.brain import verify as V
    th = led.get("r1").sheet["themes"]
    w = next(i for i, r in enumerate(th) if r["name"] == "Watercolor painting")
    c = next(i for i, r in enumerate(th) if r["name"] == "Home cooking")
    s = (f"In October 2026, you saved 6[r1.totals.items] items: 3[r1.themes[{w}].items] Watercolor "
         f"painting[r1.themes[{w}]] lessons and 3[r1.themes[{c}].items] Home cooking[r1.themes[{c}]] posts.")
    o = V.check_sentence(s, led, vt, "lead")
    assert o.kept, (o.reasons, o.details)
    o = V.check_sentence("Wet Paper[r1.channels[0]] posts watercolor lessons.", led, vt, "point")
    assert "outside_in_history" in o.reasons


def test_n_percent_more_before_a_calc_marker(harness):
    # 2023: 157 opened, 2022: 108: +45.4%
    kept(harness, "y2023", "You opened 45% more[=pct_change(r1.totals.items, r1.previous.items)] videos in 2023 than "
                           "in 2022.")
    dropped(harness, "y2023", "You opened 54% more[=pct_change(r1.totals.items, r1.previous.items)] videos in 2023 "
                              "than in 2022.")


def test_a_busiest_hour_is_no_watch_time_and_a_tied_one_is_a_tie(harness):
    # October: 19:00 holds 23.2%, the next 22.5% (no tie); lately: 17:00 and 19:00 both 23.1% (a tie)
    kept(harness, "oct", "Your busiest hour was 7 pm[r1.when.busiest_hours[0].hour].")
    dropped(harness, "lately", "Your busiest hour lately was 5 pm[r1.when.busiest_hours[0].hour].", reason="tie")
    dropped(harness, "oct", "You watched 3 hours of videos.", reason="watch_time")


# ================================================================ the scope rule: the lead says it, points may not
def _verdict(h, keys, lead, points):
    from mvp.brain import verify as V
    led, vt, t = ledger(h, *keys)
    return V.check_answer({"lead": lead, "points": points}, led, vt), led


SCOPED_LEAD = ("This year up to 30 October 2026, with only art and design, Pixel Pencil[r1.channels[0]] led what you "
               "opened, with 92[r1.channels[0].items] of 133[r1.totals.items] art videos.")
BARE_POINT = "Wet Paper[r1.channels[1]] came next with 37[r1.channels[1].items] videos."


def test_a_point_on_the_leads_own_filtered_result_need_not_repeat_the_filter_and_the_scope_line_is_printed(harness):
    from mvp.brain import answer as A
    v, led = _verdict(harness, ["art"], SCOPED_LEAD, [BARE_POINT])
    assert v.lead_ok and [o.kept for o in v.outcomes] == [True, True], [o.reasons for o in v.outcomes]
    assert v.outcomes[1].notes.get("scope_waived")
    out = A.build(led, verdict=v)
    assert out["points"] == ["Wet Paper came next with 37 videos."]
    assert out["scope_line"] and out["scope_line"].endswith("only art and design (area)") and \
        out["scope_line"] in out["text"]
    # the same point alone (no lead that says the scope) is still dropped
    assert "filter_dropped" in check(harness, "art", BARE_POINT).reasons
    # a share, a total or a base said in words is never waived: "28% of what you opened" of only art is wrongly based
    # (Wet Paper is 37 of 254, 15%, of what they opened this year)
    for p in ("Wet Paper[r1.channels[1]] made 28%[r1.channels[1].share] of what you opened.",
              "Wet Paper[r1.channels[1]] made 37[r1.channels[1].items] of the 133[r1.totals.items] videos you opened.",
              "Wet Paper[r1.channels[1]] made 37[r1.channels[1].items] of the videos you opened."):
        v, _led = _verdict(harness, ["art"], SCOPED_LEAD, [p])
        assert v.lead_ok and not v.outcomes[1].kept, p


def test_no_waiver_under_a_lead_that_does_not_say_the_scope_or_failed(harness):
    lead_no_scope = ("This year up to 30 October 2026, Pixel Pencil[r1.channels[0]] led what you opened, with "
                     "92[r1.channels[0].items] videos.")
    v, _led = _verdict(harness, ["art"], lead_no_scope, [BARE_POINT])
    assert not v.lead_ok and not v.outcomes[1].kept
    false_lead = SCOPED_LEAD.replace("92[", "93[")
    v, _led = _verdict(harness, ["art"], false_lead, [BARE_POINT])
    assert not v.lead_ok and not v.outcomes[1].kept and "filter_dropped" in v.outcomes[1].reasons


def test_no_waiver_for_a_point_on_another_filtered_result(harness):
    # r1 (only art, said in the lead) and r2 (YouTube only, last week): a point on r2 without "YouTube" stays dropped
    v, _led = _verdict(harness, ["art", "ytweek"], SCOPED_LEAD,
                       ["In the last 7 days you opened 24[r2.totals.items] videos."])
    assert v.lead_ok and not v.outcomes[1].kept and "filter_dropped" in v.outcomes[1].reasons


def test_a_waived_point_under_a_code_lead_is_not_sent_unscoped(harness):
    # the loop: the lead fails twice (a false number), so the code lead goes out with the points that PASSED; the bare
    # point was never waived (its lead failed), so it is not among them
    from mvp.brain import loop as BL, provider as P
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    tool, args = CALLS["art"]
    false_lead = SCOPED_LEAD.replace("92[", "93[")
    script = [[P.tool_use(tool, args)], [P.tool_use("give_answer", {"lead": false_lead, "points": [BARE_POINT]})],
              [P.tool_use("give_answer", {"lead": false_lead, "points": [BARE_POINT]})]]
    t = harness.turn("what about just art", search=FakeEngine(), learned=fake_learned)
    rec = BL.run_turn(P.FakeProvider(script), t, screen={"now": "Sun 22 Nov 2026 12:00"})
    assert rec["lead_source"] in ("code", "plain")
    assert "Wet Paper came next with 37 videos." not in rec["answer"]["points"]


# ================================================================ the code lead of a result of saves
def test_the_code_lead_of_a_breakdown_of_saves_says_saved_and_never_of_what_you_opened(harness):
    from mvp.brain import fallback as FB
    led, vt, _t = ledger(harness, "saved_oct")
    cl = FB.code_lead(led, None, vt)
    assert cl["how"] == "template" and "you saved" in cl["lead"] and "opened" not in cl["lead"], cl
    assert "mostly" not in cl["lead"]
    # a breakdown of what they opened still gets code_form's lead
    led, vt, _t = ledger(harness, "oct")
    assert FB.code_lead(led, None, vt)["how"] == "code_form"


# ================================================================ a learned point goes out as its checked text
def test_a_kept_learned_point_marker_goes_out_as_the_points_text(harness):
    from mvp.brain import answer as A, tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    t = harness.turn("what have i learned about sourdough", search=FakeEngine(), learned=fake_learned)
    r = TL.call(t, "learned", {"topic": "sourdough", "scope": scope(how="any")})
    if r.get("is_error") or not (r.get("sheet") or {}).get("points"):
        pytest.skip("the fake learned backend returned no points")
    led = V.Ledger(t.results)
    v = V.check_answer({"lead": "Your saved posts on sourdough come down to these points.",
                        "points": ["[r1.points[0]]"]}, led, V.Turn.of(t))
    assert v.outcomes[1].kept, v.outcomes[1].reasons
    out = A.build(led, verdict=v)
    assert out["points"] == [" ".join(r["sheet"]["points"][0]["text"].split())]
    # the twins: a point that names no point of the result, and words around the marker, are still dropped
    n = len(r["sheet"]["points"])
    for bad in (f"[r1.points[{n}]]", "Starter routine: [r1.points[0]]", "[r1.points[0]] and more."):
        v = V.check_answer({"lead": "Your saved posts on sourdough come down to these points.", "points": [bad]},
                           led, V.Turn.of(t))
        assert not v.outcomes[1].kept, bad


# ================================================================ the prompt (brain_v2) and its examples
def test_the_prompt_is_v2_and_its_new_examples_pass_or_fail_as_it_says(harness):
    from mvp.brain import loop as BL, verify as V
    from mvp.tests import brain_prompt_fixture as PF
    assert BL.PROMPT_VERSION == "brain_v2" and BL.PROMPT_PATH.endswith("brain_v2.md")
    text = " ".join(BL.system_text().split())
    ledgers = PF.ledgers(harness)
    vt = V.Turn(message="x", today=TODAY)
    for s in ("Moss Garden[r1.channels[0]] made 61[r1.channels[0].items] of the videos you opened.",
              "Gardening[r1.areas[0]] rose to 51%[r1.areas[0].share] of what you opened, up 35 "
              "points[r1.areas[0].change_pts]."):
        assert " ".join(s.split()) in text, s
        o = V.check_sentence(s, V.Ledger(ledgers[0]), vt, "point")
        assert o.kept, (s, o.reasons, o.details)
    for s in ("Moss Garden[r1.channels[0]] made up three of your top five channels.",
              "You opened 142[r1.totals.items] videos, mostly from gardening.",
              "Your export ends on 30 October 2026, so I can't see last week."):
        assert s in text, s
        assert not V.check_sentence(s, V.Ledger(ledgers[0]), vt, "point").kept, s
