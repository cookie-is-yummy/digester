"""Round 12, merge (DESIGN.md section 19): builder D's fact sheet and builder W's writer wired into hook 8h.

The seams, each with its tests: (a) the sheet D builds has what W's writer and layout need, for every kind; (b) an
offer the writer prints is taken by code in the same words, for 6 hours, and never with a pick or a rule in view;
(c) a day / first / last keeps its cards, and "the first one" and "show the videos" still work; (d) one place decides
when the export hint and the friends line are said, for the writer and today's code reply; (e) what a history answer
stores; (f) the caps before the writer's call, and one call per answer. Made-up data only (tests/r12_library.py); the
writer's form is made up by code (tests/r12_writer.py).
"""
import json
import re
from datetime import timedelta

import pytest

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round11_h import ask
from mvp.tests.test_round12_d import r12, person, mods, no_real_keys, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_slice2 import H
from mvp.tests import r12_writer as RW

QS = {   # the brief's eight questions, on the made-up library
    "q1": "what have i been watching the most lately",
    "q2": "which channels did i watch the most in 2025",
    "q3": "how many minecraft videos did i watch this year",
    "q4": "when did i first start watching watercolor videos",
    "q5": "did i watch more gaming or more art videos this year",
    "q6": "what did i watch on october 30",
    "q7": "how has what i watch changed since 2020",
    "q8": "what was i into in the summer of 2023",
}
KINDS = {"q1": "top", "q2": "channels", "q3": "count", "q4": "first", "q5": "compare_topics", "q6": "day",
         "q7": "changed", "q8": "top"}


@pytest.fixture()
def wr(r12, monkeypatch):
    """The made-up library with the writer on and the made-up writer as the model."""
    monkeypatch.setenv("MVP_INSIGHT", "1")
    r12["state"]["answers"]["mvp_insight"] = RW.fake_insight
    return r12


def later(e, hours=7):
    e["clock"][0] += timedelta(hours=hours)


def last_steps(e):
    return json.loads(e["bot"].store.q("SELECT steps FROM runs WHERE handle=? ORDER BY id DESC LIMIT 1", (H,))[0]
                      ["steps"])


def code_reply(e, monkeypatch, text):
    """Today's code reply for `text` on a fresh stretch (the writer off)."""
    monkeypatch.setenv("MVP_INSIGHT", "0")
    out, _ = ask(e, text)
    monkeypatch.setenv("MVP_INSIGHT", "1")
    return out


# ================================ (a) the sheet has what the writer and the layout need ===========================
@pytest.mark.parametrize("key", sorted(QS))
def test_a_every_kind_of_the_brief_gets_a_sheet_the_writer_can_use(wr, key):
    Hm, F, _L, _T = mods()
    from mvp import insight as I
    q = Hm.read(QS[key], TODAY)
    s = F.build(wr["bot"], person(wr), q, wr["clock"][0], text=QS[key])
    assert s["kind"] == KINDS[key]
    w = s["window"]
    assert w["words"] and w["start"] and w["end"] and isinstance(w["clipped"], bool)
    assert s["totals"]["items"] > 0 and all(o.split(":")[0] in I.OFFER_WORDS for o in s["offers"])
    if s["kind"] in I.CHART_KINDS:
        assert I.chart(s)[0], key   # the layout draws the chart this kind has
    if s["kind"] in I.ITEM_KINDS:
        assert s["items"] and all(it["id"] and it["title"] and it["at"] for it in s["items"])
    s["lang"] = q.lang
    form = I.check(RW.true_form(I.shown(s)), s, chart_vals=I.chart(s)[1])
    assert form["answer"] and len(form["observations"]) >= I.OBS_MIN, (key, form["dropped"])


@pytest.mark.parametrize("key", sorted(QS))
def test_a_the_eight_questions_are_answered_by_the_writer_in_one_call(wr, key):
    later(wr)
    out, calls = ask(wr, QS[key])
    assert calls == ["mvp_insight"], (key, calls)
    st = last_steps(wr)
    assert st["writer"]["used"] and st["writer"]["sheet_kind"] == KINDS[key]
    assert "• " in out and "MODEL WAS CALLED" not in out
    assert not re.search(r"\b20\d\d: \d", out)   # no run of "2024: 6, 2025: 11"
    assert "you watched" not in out.split("\n")[0].lower() or key in ("q3",)


@pytest.mark.parametrize("words, opening", [
    ("the 4 weeks up to 30 October 2026, where your export ends",
     "In the 4 weeks up to 30 October 2026, where your export ends"),
    ("Friday 30 October 2026, the last day of your export", "On Friday 30 October 2026, the last day of your export"),
    ("2025", "In 2025"), ("October 2026", "In October 2026"),
    ("this year up to 30 October 2026, where your export ends", "This year up to 30 October 2026, where your export ends"),
    ("since 1 January 2020 up to 30 October 2026", "Since 1 January 2020 up to 30 October 2026"),
    ("the summer of 2023 (1 June to 31 August 2023)", "In the summer of 2023 (1 June to 31 August 2023)"),
])
def test_a_the_sheets_window_words_open_the_answer_as_a_person_says_them(words, opening):
    from mvp import history as Hm
    q = Hm.HistoryQuery(kind="count", window=Hm.Window(kind="all"))
    assert Hm.opening_words({"words": words}, q) == opening


def test_a_the_answer_opens_with_the_window_and_where_the_export_ends(wr):
    out, _ = ask(wr, QS["q1"])
    assert out.startswith("In the 4 weeks up to 30 October 2026, where your export ends, ")
    later(wr)
    out, _ = ask(wr, QS["q6"])
    assert out.startswith("On Friday 30 October 2026, the last day of your export, ")
    later(wr)
    out, _ = ask(wr, QS["q4"])
    assert out.startswith("You first opened a watercolor video on 10 January 2025.")   # the date is the answer


def test_a_a_window_wholly_after_the_record_keeps_todays_honest_reply(wr, monkeypatch):
    out, calls = ask(wr, "what did i watch last week")
    assert "mvp_insight" not in calls and "I can't see" in out


# ================================ (b) offers taken in the same words, for 6 hours ==================================
def test_b_every_offer_the_writer_prints_is_taken_in_its_own_words(wr):
    from mvp import insight as I
    Hm = mods()[0]
    out, _ = ask(wr, "which channels did i watch the most this year")
    st = wr["bot"].store.get_state(Hm.STATE.format(h=H))
    assert "Want it " in out
    sheet = {"offers": ["without_shorts", "only_topic:Digital drawing", "show_videos", "by_month", "by_theme"]}
    for o in sheet["offers"]:
        phrase = I.offer_phrase(o)
        for said in (phrase, "yes, " + phrase, phrase + " please"):
            f = Hm.follow_up(st, said, TODAY, known=lambda x: True)
            assert f is not None and not isinstance(f, tuple), said
            q0 = Hm.HistoryQuery.model_validate(st["q"])
            if o == "without_shorts":
                assert f.without_shorts
            elif o.startswith("only_topic"):
                assert f.topic == ["digital drawing"]
            elif o == "show_videos":
                assert f.kind == "list"
            elif o == "by_month":
                assert f.by == "month"
            else:
                assert f.kind == "top" and f.topics_too
            assert q0.window == f.window


def test_b_the_reply_to_an_offer_taken_opens_with_its_words_and_answers_again(wr):
    out, _ = ask(wr, "which channels did i watch the most this year")
    assert "Clip Factory" in out and "without Shorts" in out
    out, calls = ask(wr, "without Shorts")
    assert out.startswith("Without Shorts:\n\n") and "Clip Factory" not in out and calls == ["mvp_insight"]
    out, calls = ask(wr, "only Digital drawing")
    # round 12, pass 3 fix (judge A, on purpose): both filters said after "without Shorts" then "only X"
    assert out.startswith("Only Digital drawing, without Shorts:\n\n") and calls == ["mvp_insight"]
    assert "Pixel Pencil" in out and "Wet Paper" not in out


def test_b_an_only_theme_offer_falls_back_to_the_sheets_counts_never_to_no_videos(wr):
    out, _ = ask(wr, "which channels did i watch the most this year")
    wr["state"]["answers"]["mvp_insight"] = lambda u: {}
    out, _ = ask(wr, "only Digital drawing")
    assert out.startswith("Only Digital drawing:\n\n") and "no videos" not in out
    assert "you opened 92 videos on digital drawing" in out and "1. Pixel Pencil: 92" in out


def test_b_offers_are_taken_for_6_hours_then_not(wr):
    out, _ = ask(wr, "which channels did i watch the most this year")
    later(wr, 5)
    out, calls = ask(wr, "by month")
    assert out.startswith("By month:") and calls == ["mvp_insight"]
    later(wr, 7)
    out, calls = ask(wr, "by month")
    assert not out.startswith("By month:")


def test_b_never_with_a_pick_in_view(wr):
    from mvp.tests.test_mvp import compose_picks
    out, _ = ask(wr, "which channels did i watch the most this year")
    wr["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "verdict": "clear", "title": "x"})
    ask(wr, "find me a watercolor video", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a watercolor video", "searches": ["watercolor"], "count": 1}}})
    Hm = mods()[0]
    assert Hm._fresh_state(wr["bot"], H, wr["clock"][0]) is None
    out, calls = ask(wr, "without shorts")
    assert not out.startswith("Without Shorts:") and "mvp_insight" not in calls


@pytest.mark.parametrize("text", ["no shorts in my rules please, remind me tomorrow", "yes", "only you", "by tomorrow",
                                  "just kidding", "with you", "yes, remind me by month"])
def test_b_the_offer_traps_are_not_taken(wr, text):
    Hm = mods()[0]
    ask(wr, "which channels did i watch the most this year")
    st = wr["bot"].store.get_state(Hm.STATE.format(h=H))
    f = Hm.follow_up(st, text, TODAY, known=lambda x: True)
    assert f is None or isinstance(f, tuple) or not Hm.offer_words(Hm.normal(text)), text


def test_b_yes_to_the_so_what_lists_the_saved_videos_with_their_cards(wr):
    out, _ = ask(wr, QS["q4"])
    assert "You saved 3 Watercolor painting videos you never opened; want them as a list?" in out
    out, calls = ask(wr, "yes please")
    assert calls == [] and out.startswith("Saved on Watercolor painting and never opened:\n1. ")
    assert out.count("youtube.com/watch") == 3
    out, _ = ask(wr, "the first one")
    assert "youtube.com/watch" in out and "Which one" not in out


def test_b_yes_with_no_so_what_said_is_not_taken(wr, monkeypatch):
    # round 12, fix: with no so-what from the model a first now gets the code's (the path, then the saved ones), so
    # the "not said" case is a so-what code cannot write either
    from mvp import insight as I
    monkeypatch.setattr(I, "_path_line", lambda *a, **k: None)
    monkeypatch.setattr(I, "_saved_line", lambda *a, **k: None)
    wr["state"]["answers"]["mvp_insight"] = lambda u: dict(RW.fake_insight(u), so_what=None)
    ask(wr, QS["q4"])
    Hm = mods()[0]
    st = wr["bot"].store.get_state(Hm.STATE.format(h=H))
    assert not st.get("saved")


# ================================ (c) the items of a day / first / last ==========================================
def test_c_a_day_gives_the_overview_then_the_items_and_their_cards_and_the_first_one_works(wr):
    out, _ = ask(wr, QS["q6"])
    head, items = out.split("\n1. ", 1)
    assert "• " in head and items.count("youtube.com/watch") == 4
    msgs = [t for _, _, t in wr["ch"].outbox[-6:]]
    out, calls = ask(wr, "the first one")
    assert calls == [] and "Digital drawing on the 30th" in out and "youtube.com/watch?v=vrday1" in out
    assert msgs


def test_c_show_the_videos_after_a_writer_answer_is_todays_list(wr):
    ask(wr, QS["q3"])
    out, calls = ask(wr, "show the videos")
    assert calls == [] and "youtube.com/watch" in out
    later(wr)
    ask(wr, "which channels did i watch the most this year")
    out, calls = ask(wr, "with the videos")
    assert calls == [] and "youtube.com/watch" in out and "• " not in out


def test_c_the_second_one_after_a_channels_answer_is_the_charts_second_channel(wr):
    out, _ = ask(wr, "which channels did i watch the most this year")
    chart = [ln for ln in out.split("\n") if ln.startswith(("█", "░"))]
    second = chart[1].split(" ", 2)[2]
    out, calls = ask(wr, "the second one")
    assert calls == [] and f"by {second}" in out


# ================================ (d) one place decides the hint and the friends line ============================
def test_d_the_hint_once_in_6_hours_across_the_writer_and_the_code_reply(wr):
    from mvp import insight as I
    # round 12, pass 2 (T6, the founder: "dont say that at the end"): no export hint on a history answer, from the
    # writer or the code reply; the window's own words say where the record ends
    out, _ = ask(wr, QS["q1"])
    assert I.REFRESH_SHORT["en"] not in out
    wr["state"]["answers"]["mvp_insight"] = lambda u: {}   # the writer fails: today's code reply
    later(wr, 1)
    out, _ = ask(wr, "what have i been watching lately")
    assert "send me a new export" not in out
    later(wr, 7)
    out, _ = ask(wr, "what have i been watching lately")
    assert "send me a new export" not in out and "where your" in out
    wr["state"]["answers"]["mvp_insight"] = RW.fake_insight
    later(wr, 1)
    out, _ = ask(wr, QS["q1"])
    assert "send me a new export" not in out and "• " in out


def test_d_the_friends_line_only_when_the_question_is_about_friends(wr):
    from mvp import insight as I
    out, _ = ask(wr, QS["q1"])
    assert "friends" not in out.lower()
    later(wr)
    out, _ = ask(wr, "what have my friends and i been watching the most lately")
    assert "friends" not in out.lower() or I.FRIENDS_LINE["en"] in out


def test_d_no_closing_paragraph_about_limits_in_a_writer_reply(wr):
    for key in sorted(QS):
        later(wr)
        out, _ = ask(wr, QS[key])
        assert "can't see" not in out and "so I can't" not in out and "not counted" not in out, key


# ================================ (e) what a history answer stores =================================================
def test_e_the_run_keeps_the_forms_shape_and_the_sheets_kind_never_words_or_titles(wr):
    from mvp.tests import r12_library as R
    ask(wr, QS["q6"])
    st = last_steps(wr)
    assert set(st["writer"]) == {"sheet_kind", "used", "called", "kept", "dropped", "so_what", "offers",
                                 "without_shorts", "error", "sheet_s", "versions"}
    blob = json.dumps(st).lower()
    titles = {r["caption"].lower() for r in R.rows()} | {r["channel"].lower() for r in R.rows() if r.get("channel")} | \
        {"october 30", "what did i watch"}
    assert not any(t in blob for t in titles)
    assert all(o in ("without_shorts", "only_topic", "show_videos", "by_month", "by_theme")
               for o in st["writer"]["offers"])
    run = wr["bot"].store.q("SELECT cost_usd, prompt_version FROM runs WHERE handle=? ORDER BY id DESC LIMIT 1",
                            (H,))[0]
    from mvp import insight as I
    assert run["prompt_version"] == I.PROMPT_VERSION and run["cost_usd"] == pytest.approx(0.001)


def test_e_the_state_keeps_the_query_and_ids_never_the_question_or_the_sheet(wr):
    Hm = mods()[0]
    ask(wr, QS["q4"])
    st = wr["bot"].store.get_state(Hm.STATE.format(h=H))
    # round 12, pass 2 (T5): the key of the so-what said (never the same one twice in a row); no words, no titles
    assert set(st) <= {"q", "at", "run_id", "ids", "channels", "saved", "so_what_id"}
    assert "first start" not in json.dumps(st)


def test_e_the_export_lists_the_answer_and_delete_removes_it(wr, tmp_path):
    from mvp import export
    ask(wr, QS["q2"])
    p = wr["bot"].store.q("SELECT * FROM people WHERE handle=?", (H,))[0]
    files = export.export(wr["bot"], p, wr["clock"][0])
    text = "\n".join(open(f[1], encoding="utf-8").read() for f in (files.get("files") if isinstance(files, dict)
                                                                     else files) if str(f[1]).endswith(".md"))
    assert "history: top_channels" in text and "• " in text
    wr["bot"].store.delete_person_data(H)
    Hm = mods()[0]
    assert wr["bot"].store.get_state(Hm.STATE.format(h=H)) is None
    assert not wr["bot"].store.q("SELECT * FROM runs WHERE handle=?", (H,))
    assert not wr["bot"].store.q("SELECT * FROM answers WHERE handle=?", (H,))


# ================================ (f) cost and time =================================================================
def test_f_a_cap_reached_means_no_call_and_todays_code_reply(wr, monkeypatch):
    base = code_reply(wr, monkeypatch, QS["q2"])
    later(wr)
    monkeypatch.setattr(type(wr["bot"]), "_over_cap", lambda self, p: "daily")
    out, calls = ask(wr, QS["q2"])
    assert calls == [] and out == base


# round 12, fix: "one_observation" left this list (code fills the observations; tests/test_round12_fix.py)
@pytest.mark.parametrize("how", ["raise", "no_script", "empty"])
def test_f_the_code_reply_byte_for_byte_when_the_writer_gives_nothing(wr, monkeypatch, how):
    base = code_reply(wr, monkeypatch, QS["q3"])
    later(wr)
    if how == "raise":
        def boom(u):
            raise TimeoutError("the model did not answer")
        wr["state"]["answers"]["mvp_insight"] = boom
    elif how == "no_script":
        del wr["state"]["answers"]["mvp_insight"]
    elif how == "empty":
        wr["state"]["answers"]["mvp_insight"] = lambda u: {}
    else:
        wr["state"]["answers"]["mvp_insight"] = lambda u: dict(RW.fake_insight(u),
                                                               observations=RW.fake_insight(u)["observations"][:1])
    out, calls = ask(wr, QS["q3"])
    assert calls == ["mvp_insight"] and out == base
    assert last_steps(wr)["writer"]["used"] is False


def test_f_one_call_per_answer_and_per_follow_up_and_none_for_a_list(wr):
    _, calls = ask(wr, QS["q2"])
    assert calls == ["mvp_insight"]
    _, calls = ask(wr, "without shorts")
    assert calls == ["mvp_insight"]
    _, calls = ask(wr, "show me them")
    assert calls == []
    _, calls = ask(wr, "more")
    assert calls == []
    later(wr)
    _, calls = ask(wr, "what was i watching in march 2024")
    assert calls == []   # a plain list stays code


def test_f_the_writer_off_builds_no_sheet(r12, monkeypatch):
    from mvp import facts
    monkeypatch.setattr(facts, "build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sheet built")))
    out, calls = ask(r12, QS["q1"])
    assert calls == [] and out


def test_f_the_sheet_is_built_in_well_under_a_second_on_the_made_up_library(wr):
    ask(wr, QS["q7"])
    assert last_steps(wr)["writer"]["sheet_s"] < 1.0


def test_a_the_writer_reads_a_themes_change_as_a_fraction_and_may_say_of_n_then(wr):
    seen = []

    def spy(user):
        seen.append(RW.sheet_of(user))
        return RW.fake_insight(user)
    wr["state"]["answers"]["mvp_insight"] = spy
    ask(wr, QS["q1"])
    for t in seen[0]["themes"]:
        if "change_vs_previous" in t:
            assert abs(t["change_vs_previous"] - (t["share"] - t["previous_share"])) < 0.002, t
    later(wr)
    out, _ = ask(wr, QS["q3"])
    assert "That is 12 of the 246 videos you opened then." in out


# ================================ the live run's defects (22 Nov, the real library; made-up words here) ==========
def _topics_sheet():
    return {"kind": "compare_topics", "lang": "en", "question": "did i watch more gaming or more art this year",
            "window": {"words": "This year up to 30 October 2026, where your export ends", "start": "2026-01-01",
                       "end": "2026-10-30", "clipped": True},
            "totals": {"items": 3830, "days_active": 290},
            "topics": [{"name": "gaming", "items": 3455, "days": 287, "length_hours": 723.1, "shorts": 2236,
                        "long": 1182},
                       {"name": "art", "items": 375, "days": 153, "length_hours": 23.4, "shorts": 259, "long": 53}],
            "offers": ["without_shorts"]}


@pytest.mark.parametrize("text, why", [
    ("Gaming also reached 723.1 videos adding up to about 723 hours.", "count_of_videos"),
    ("Art reached 23 videos adding up to about 23 hours.", "count_of_videos"),
    ("You opened 10 videos across 1 day.", "one_day"),
    ("You opened them on one single day.", "one_day"),
])
def test_live_an_hours_figure_said_as_videos_and_one_day_are_dropped(text, why):
    from mvp import insight as I
    s = _topics_sheet()
    assert I.check_sentence(text, I.Facts(I.shown(s)), ["topics"]) == why


def test_live_the_true_sentences_of_that_answer_stay():
    from mvp import insight as I
    s = _topics_sheet()
    # round 12, pass 2 (T2): "Gaming videos add up to about 723 hours, ..." left: no total of video length
    assert I.check_sentence("Gaming videos add up to about 723 hours, art videos to about 23.", I.Facts(I.shown(s)),
                            ["topics"]) == "hours"
    for text in ("You opened gaming on 287 days, art on 153.",
                 "Gaming had 2,236 Shorts and 1,182 long videos."):
        assert I.check_sentence(text, I.Facts(I.shown(s)), ["topics"]) is None, text


def test_live_yes_to_a_so_what_on_two_themes_lists_both(wr, monkeypatch):
    Hm = mods()[0]
    from mvp import facts as F
    real = F.build

    def two(*a, **k):
        s = real(*a, **k)
        if s and s.get("library", {}).get("saved_not_opened"):
            one = s["library"]["saved_not_opened"][0]
            # round 12, pass 4 (V4, changed on purpose): a so-what is said only with a step code takes; the first
            # group says the 3 saved videos the so-what's offer names (with 2, the path alone was a bullet)
            s["library"]["saved_not_opened"] = [dict(one, ids=None, examples=one["examples"][:2], n=3),
                                                dict(one, theme="Second theme", examples=one["examples"][2:], n=1)]
        return s
    monkeypatch.setattr(F, "build", two)
    ask(wr, QS["q4"])
    st = wr["bot"].store.get_state(Hm.STATE.format(h=H))
    assert [len(g["ids"]) for g in st["saved"]["groups"]] == [2, 1]
    out, _ = ask(wr, "yes")
    assert "Saved on Watercolor painting and never opened (the 2 saved last, of 3):\n1. " in out and \
        "Saved on Second theme and never opened:\n3. " in out


def test_live_a_first_in_an_earlier_year_says_the_year_on_its_lines(wr):
    out, _ = ask(wr, QS["q4"])
    assert "1. Wet Paper · 10 Jan 2025 · 10 min" in out   # round 12, pass 3 (U4): the card's caption line


def test_one_hook_8h_and_the_order_inside_it_and_its_send_path():
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "history.py"), encoding="utf-8").read()

    def order(fn, needles):
        body = src[src.index(f"\ndef {fn}("):]
        body = body[:body.index("\ndef ", 1)]
        at = [body.index(n) for n in needles]
        assert at == sorted(at), (fn, needles)
    order("history_reads", ['if st.get("saved") and YES_SAVED.match(normal(text))', "f = follow_up(st, text, today, known)",
                            "r = read_recall(text, today)", "q = read(text, today)"])
    order("send_answer", ["text, ids, extra = answer(view, q", "written, winfo, sheet = _write(bot, person, q",
                          "note_said(bot, h, now, said)", "bot.store.add_run(handle=h, kind=\"history\""])
    handler = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "handler.py"), encoding="utf-8").read()
    assert "insight" not in handler and "facts.build" not in handler   # no new hook
