"""Round 12, second pass (DESIGN.md section 19.P2): what was still wrong with the history answers, T1 to T15.

Made-up data only: the eval's made-up sheets (eval/insight_cases.json), the made-up library (tests/r12_library.py) and
the made-up writer (tests/r12_writer.py, insight_v5's form: sheet paths in braces). Each block reproduces a finding
(the line that failed on ace4be2) and guards its near variants.
"""
import copy
import json
import os
import re
import time

import pytest

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round11_h import ask
from mvp.tests.test_round12_d import r12, person, mods, no_real_keys, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_merge import wr, later, last_steps, QS  # noqa: F401  (fixtures)
from mvp.tests import r12_writer as RW

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(os.path.dirname(HERE), "eval", "insight_cases.json")


def case(cid):
    with open(CASES, encoding="utf-8") as f:
        return copy.deepcopy(next(c for c in json.load(f)["cases"] if c["id"] == cid))


def ins():
    from mvp import insight
    return insight


def strict_obs(text, s):
    I = ins()
    f = I.check({"answer": "-", "observations": [{"text": text, "uses": []}]}, s, strict=True)
    return f["observations"][0] if f["observations"] else None, [d[1] for d in f["dropped"] if d[0] == "observation"]


def sheet_of(e, text):
    Hm, F, _L, _T = mods()
    q = Hm.read(text, TODAY)
    s = F.build(e["bot"], person(e), q, e["clock"][0], text=text)
    s["lang"] = q.lang
    return s


# ================================ T1: a number can only stand next to its own thing ==============================
def test_t1_the_writer_is_insight_v5_and_its_live_path_is_strict():
    I = ins()
    assert I.PROMPT_VERSION == "insight_v5" and I.strict()
    assert "{themes[0].channels[0].items}" in I.prompt() and "never type a number" in I.prompt().lower()


@pytest.mark.parametrize("text, why", [
    # seen live: a channel's count for the whole window said as a part of one theme
    ("{channels[0].name} was behind {channels[0].items} of your {themes[1].name} videos.", "bound_to_other"),
    # seen live: a channel's days taken from another row
    ("{channels[1].name} is behind {channels[1].items} videos, and it spread across {channels[2].days} days.",
     "unnamed_owner"),
    ("{themes[0].name} had {totals.shorts} Shorts.", "bound_global"),
    ("{themes[0].share} of your {themes[1].name} videos came from {themes[0].name}.", "bound_to_other"),
    ("{themes[2].name} led with {themes[2].share}.", "rank"),
    ("{themes[0].name} led, followed by {themes[2].name}.", "order"),
    ("Mostly {themes[0].name} ({themes[0].share}).", "spread"),
    ("A wide mix, led by {themes[0].name} at {themes[0].share}.", "mix"),
    ("{themes[0].name} had {themes[0].items}, {themes[1].items} more than {themes[1].name}.", "made_up_difference"),
    ("{themes[0].name} had twice as many as {themes[1].name} ({themes[0].items} against {themes[1].items}).",
     "ratio"),
    ("{themes[0].name} had 28 more videos than {themes[1].name}.", "free_number"),
    ("{themes[9].name} grew.", "bad_path"),
    ("{themes[0].name} videos add up to {themes[0].length_hours} hours.", "bad_path"),
])
def test_t1_a_planted_false_sentence_is_dropped_by_its_binding(text, why):
    kept, whys = strict_obs(text, case("top_lately")["sheet"])
    assert kept is None and whys == [why], (text, whys)


@pytest.mark.parametrize("text, want", [
    ("{themes[0].channels[0].name} was behind {themes[0].channels[0].items} of your {themes[0].name} videos.",
     "Pixel Forge was behind 41 of your Blender 3D videos."),
    ("{themes[0].name} grew to {themes[0].share}, up {themes[0].change_vs_previous}.",
     "Blender 3D grew to 31%, up 12 points."),
    ("{totals.shorts} of the {totals.items} were Shorts.", "120 of the 312 were Shorts."),
    ("{themes[0].name} led, followed by {themes[1].name}.", "Blender 3D led, followed by home cooking."),
    ("Mostly {themes[0].name} and {themes[1].name} ({themes[0].share} and {themes[1].share}).",
     "Mostly Blender 3D and home cooking (31% and 22%)."),
    ("{themes[0].name} had about twice as many as {themes[2].name} ({themes[0].items} against {themes[2].items}).",
     "Blender 3D had about twice as many as speedrun clips (97 against 56)."),
])
def test_t1_a_true_sentence_is_kept_with_code_filling_its_paths(text, want):
    kept, whys = strict_obs(text, case("top_lately")["sheet"])
    assert kept == want, whys


def test_t1_the_v5_eval_set_every_plant_caught_every_true_kept():
    from mvp import eval_insight as E
    sc = E.v5_scores()
    assert sc["planted_v5"] >= 12 and sc["caught_v5"] == sc["planted_v5"]
    assert sc["kept_v5"] == sc["true_v5"] >= 10
    assert all(sc["by_why"].get(k, [0, 0])[0] >= 3 for k in ("bound", "rank", "mostly", "difference"))


def test_t1_the_legacy_eval_set_still_catches_every_plant_and_keeps_every_true_one():
    from mvp import eval_insight as E
    rows = E.run("fake", E.load())
    s = E.summary(rows, "fake")
    assert s["caught"] == s["planted"] and s["true_kept"] == s["true_obs"]


def test_t1_a_typed_number_is_dropped_only_in_the_strict_mode():
    I = ins()
    s = case("top_lately")["sheet"]
    text = "Pixel Forge is behind 41 of the 97 Blender 3D videos."
    assert strict_obs(text, s)[1] == ["free_number"]
    f = I.check({"answer": "-", "observations": [{"text": text, "uses": ["themes"]}]}, s)
    assert f["observations"] == [text]


def test_t1_the_window_words_years_and_dates_may_be_typed():
    s = case("top_lately")["sheet"]
    kept, whys = strict_obs("Since 30 October 2026 {themes[0].name} grew to {themes[0].share}.", s)
    assert kept and not whys


def test_t1_the_writer_end_to_end_fills_its_paths_on_the_made_up_library(wr):
    out, calls = ask(wr, QS["q1"])
    assert calls == ["mvp_insight"] and "{" not in out and "• " in out
    assert last_steps(wr)["writer"]["used"]


# ================================ T2: no total of video length anywhere ==========================================
def test_t2_the_writer_never_sees_a_length_total_and_code_never_says_one(r12):
    I = ins()
    for k, q in QS.items():
        s = sheet_of(r12, q)
        sh = I.shown(s)
        assert "length_hours" not in json.dumps(sh), k
        cf = I.code_form(s)
        text = " ".join([cf["answer"] or ""] + [o["text"] for o in cf["observations"]] + [cf["so_what"] or ""])
        assert not re.search(r"\d[\d,.]*\s*hours?\b", text), (k, text)


@pytest.mark.parametrize("text", ["What you opened adds up to about 3,356 hours of video on 359 days.",
                                  "Those videos add up to about 62 hours in length.",
                                  "By length the order changes: about 70 hours against 11."])
def test_t2_a_length_total_in_any_words_is_dropped(text):
    I = ins()
    assert I.check_sentence(text, I.Facts(I.shown(case("channels_october")["sheet"]))) == "hours"


def test_t2_the_median_long_video_is_a_length_that_stays_true(r12):
    s = sheet_of(r12, QS["q8"])
    assert s["totals"]["long_median_min"] == 10   # every made-up long video but drawing is 600 s
    kept, whys = strict_obs("The long videos were typically about {totals.long_median_min}.", s)
    assert kept == "The long videos were typically about 10 minutes."


# ================================ T13: derived data found by real path and content; said loudly when missing =======
def test_t13_a_library_reached_through_a_symlink_finds_its_themes(r12, tmp_path):
    Hm, F, L, T = mods()
    link = tmp_path / "linked_data"
    os.symlink(r12["lib"], link)
    assert T.lib_key(str(link)) == T.lib_key(str(r12["lib"]))
    th = T.load(str(link))
    assert th is not None and T.find(str(link))[1] == "path"


def test_t13_a_copy_of_the_library_at_another_path_finds_its_themes_by_content(r12, tmp_path):
    import shutil
    Hm, F, L, T = mods()
    other = tmp_path / "moved" / "lib"
    shutil.copytree(r12["lib"], other)
    assert T.lib_key(str(other)) != T.lib_key(str(r12["lib"]))
    d, how = T.find(str(other))
    assert how == "content" and T.load(str(other)) is not None


def test_t13_status_says_loudly_when_themes_or_lengths_are_missing(r12, tmp_path, monkeypatch, capsys):
    Hm, F, L, T = mods()
    st = T.status(str(r12["lib"]))
    assert st["ok"] and st["found"] == "path" and st["themed_share"] > 0.8 and st["lengths"]["rows"] > 0
    monkeypatch.setenv("MVP_DERIVED_HOME", str(tmp_path / "empty"))
    T._FOUND.clear()
    st = T.status(str(r12["lib"]))
    assert not st["ok"] and any("no themes build" in p for p in st["problems"])
    assert any("no video lengths" in p for p in st["problems"])
    lines = T.status_lines(st)
    assert lines[0].startswith("WARNING") and any("python3 -m mvp.themes build" in x for x in lines)


def test_t13_the_trace_says_when_the_sheet_had_no_themes(wr, monkeypatch, tmp_path):
    Hm, F, L, T = mods()
    monkeypatch.setenv("MVP_DERIVED_HOME", str(tmp_path / "empty"))
    T._FOUND.clear()
    T._LOADED.clear()
    F._IDX.clear()
    ask(wr, QS["q1"])
    assert last_steps(wr)["writer"]["versions"]["themes"] is None


# ================================ T3: the broad picture first (areas) ===========================================
def test_t3_the_sheet_has_areas_that_add_up_to_most_of_the_window(r12):
    s = sheet_of(r12, QS["q1"])
    areas = s["areas"]
    assert [a["name"] for a in areas][:2] == ["gaming", "art and design"]
    assert sum(a["share"] for a in areas) >= 0.9 and all(a["themes"] for a in areas[:2])


def test_t3_the_answer_and_the_chart_are_at_the_level_of_areas(r12):
    I = ins()
    s = sheet_of(r12, QS["q1"])
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    # round 12, pass 3 fix (judge A, row 1, on purpose): over 4 weeks the leader's move against the 4 weeks before leads
    assert f["answer"].startswith("Gaming doubled to 48% of what you opened, from 24% in the 4 weeks before")
    assert any(o.startswith("Inside gaming:") for o in f["observations"])
    assert I.chart(s)[0].startswith("Share of what you opened, by area:")


def test_t3_a_sensitive_theme_never_becomes_an_area(r12):
    s = sheet_of(r12, "what did i watch the most in 2024")
    assert all("dating" not in a["name"].lower() for a in s.get("areas") or [])


# ================================ T4: a change told as eras ======================================================
def test_t4_changed_is_told_as_eras_with_what_was_left_and_what_arrived(r12):
    I = ins()
    s = sheet_of(r12, QS["q7"])
    assert [e["area"] for e in s["eras"]][:1] == ["gaming"] and s["eras"][-1]["area"] == "art and design"
    ac = s["areas_change"]
    assert ac["left"][0]["name"] == "gaming" and ac["arrived"][0]["name"] == "art and design"
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"] == "Gaming led from 2021 to 2022; since 2025, art and design has."
    assert any(o.startswith("Shorts went from") for o in f["observations"])


def test_t4_the_change_chart_shows_one_measure_its_caption_names():
    I = ins()
    s = {"kind": "changed", "lang": "en", "periods": [
        {"label": str(y), "items": 100 + y, "areas": [{"name": a, "share": sh}]}
        for y, a, sh in ((2020, "gaming", 0.5), (2021, "gaming", 0.4), (2022, "comedy", 0.3))]}
    text, _ = I.chart(s)
    lines = text.split("\n")
    assert lines[0] == "The main area each year (the bar: its share of that year):"
    assert lines[1] == "████████ 2020 gaming" and lines[3].endswith("2022 comedy")


# ================================ T5: a so-what worth saying, or none ============================================
def test_t5_candidates_by_code_none_for_a_day_and_none_for_one_or_two_saved(r12):
    s = sheet_of(r12, QS["q6"])
    assert s["so_what_candidates"] == []
    from mvp import facts as F
    sh = {"kind": "top", "themes": [{"name": "A", "share": 0.3, "change_vs_previous": -3.0}],
          "library": {"saved_not_opened": [{"theme": "A", "n": 2}]}}
    assert F._so_what_candidates(sh, "top", None) == []
    sh["library"]["saved_not_opened"][0]["n"] = 3
    assert [c["kind"] for c in F._so_what_candidates(sh, "top", None)] == ["lapsed_saves"]


def test_t5_a_learning_theme_that_faded_against_entertainment_that_grew():
    from mvp import facts as F
    sh = {"kind": "top", "themes": [
        {"name": "Calc", "area": "math", "share": 0.05, "previous_share": 0.2, "change_vs_previous": -15.0},
        {"name": "Clips", "area": "gaming", "share": 0.4, "previous_share": 0.1, "change_vs_previous": 30.0}]}
    c = F._so_what_candidates(sh, "top", None)
    assert c[0]["kind"] == "learning_faded" and c[0]["faded"] == "Calc" and c[0]["grew"] == "Clips"
    I = ins()
    assert I.so_what_text(c[0], {"lang": "en"}).startswith("Calc fell from 20% to 5% while Clips grew from 10%")


def test_t5_never_the_same_so_what_on_two_answers_in_a_row(wr):
    out1, _ = ask(wr, QS["q2"])
    later(wr, 1)
    out2, _ = ask(wr, QS["q2"])
    assert "You saved 3 Watercolor painting videos" in out1
    assert "You saved 3 Watercolor painting videos" not in out2


def test_t5_a_so_what_must_be_one_of_the_candidates():
    I = ins()
    c = case("top_lately")
    raw = dict(c["fake"], so_what="You should learn guitar, it is fun; want a list?")
    f = I.check(raw, c["sheet"])
    f = I.fill(f, raw, c["sheet"])
    assert ("so_what", "not_a_candidate") in [(d[0], d[1]) for d in f["dropped"]] or not f["so_what"] or \
        "Blender 3D" in (f["so_what"] or "")


# ================================ T6: no export hint on a history answer ==========================================
def test_t6_a_lately_answer_says_where_the_record_ends_in_its_words_and_no_hint(wr):
    from mvp import insight as I
    out, _ = ask(wr, QS["q1"])
    assert "where your export ends" in out and I.REFRESH_SHORT["en"] not in out and "send me a new export" not in out


def test_t6_the_hint_is_said_when_the_whole_window_is_after_the_record(wr):
    out, _ = ask(wr, "what did i watch last week")
    assert out.startswith("I can't see") and "send me a new export" in out


# ================================ T7: filler ======================================================================
def test_t7_new_in_the_window_is_not_shown_for_a_year_or_a_day():
    I = ins()
    s = case("channels_2025")["sheet"]
    s["window"] = {"words": "2025", "start": "2025-01-01", "end": "2025-12-31"}
    s["channels"][0]["new_in_window"] = True
    s["new"] = {"channels": [{"name": s["channels"][0]["name"], "items": 3}], "themes": []}
    sh = I.shown(s)
    assert "new_in_window" not in json.dumps(sh) and sh["new"]["channels"] == []


def test_t7_the_weekday_line_only_when_it_differs_from_his_usual_week():
    I = ins()
    s = case("top_lately")["sheet"]
    s["when"] = {"busiest_hours": [21], "weekday_share": 0.55, "weekend_share": 0.45, "busiest_weekday": "Saturday",
                 "usual_weekday_share": 0.58}
    assert I.check_sentence("You opened 45% of it on weekends.", I.Facts(I.shown(s))) == "weekpart"
    s["when"]["usual_weekday_share"] = 0.75
    assert I.check_sentence("You opened 45% of it on weekends.", I.Facts(I.shown(s))) is None


def test_t7_a_bullet_that_repeats_the_lead_goes():
    I = ins()
    c = case("top_lately")
    raw = dict(c["fake"], answer="Mostly Blender 3D (31%) and home cooking (22%).", observations=[
        {"text": "Blender 3D was 31% and home cooking 22%.", "uses": ["themes"]},
        {"text": "Pixel Forge is behind 41 of the 97 Blender 3D videos.", "uses": ["themes"]}])
    f = I.check(raw, c["sheet"])
    assert ("observation", "repeat") in [(d[0], d[1]) for d in f["dropped"]]


# ================================ T8: a topic's count code can defend ==============================================
def test_t8_a_theme_named_after_the_topic_whose_titles_do_not_say_it_is_not_counted(r12, monkeypatch):
    Hm, F, L, T = mods()
    from mvp.libview import LibraryView
    v = LibraryView(str(r12["lib"]))
    rec = Hm.record(v, "America/New_York")
    th = T.load(v.lib)
    sr = next(t for t in th.themes if th.shown(t) == "Speedruns")
    monkeypatch.setitem(th.themes[sr], "name", "Minecraft speedruns")   # a name its titles never say
    got = {th.shown(t) for t in T.for_topic(v, rec, "minecraft", th)}
    assert "Minecraft builds" in got and "Minecraft speedruns" not in got


def test_t8_a_count_with_themes_in_it_says_about(r12):
    I = ins()
    s = sheet_of(r12, QS["q3"])
    s["topics"][0]["matched_by"] = "themes and words"
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"].startswith("About 12 minecraft videos on 12 days")


# ================================ T9: more X or Y: inside each side, the balance before ============================
def test_t9_a_comparison_says_the_ratio_in_words_what_is_inside_each_side_and_the_span_before(r12):
    I = ins()
    s = sheet_of(r12, QS["q5"])
    cm = s["comparison"]
    assert cm["more"] == "art" and cm["ratio_words"].startswith("about") and "difference" in cm
    assert all(t.get("top_themes") and "previous_items" in t for t in s["topics"])
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"].startswith("Much more art than gaming: about 2 times as many (132 against 73)")
    assert I.n_numbers(f["answer"], I.Facts(I.shown(s))) <= 3
    assert any(o.startswith("Inside art:") for o in f["observations"])


# ================================ T10: a day against the usual day ================================================
def test_t10_a_day_says_how_it_compares_with_the_usual_day(r12):
    I = ins()
    s = sheet_of(r12, QS["q6"])
    assert s["usual"]["median_items"] >= 1 and "day_shorts_share" in s["usual"]
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    # round 12, pass 3 fix (judge A, row 6, on purpose): the export's last day is never set against a usual day's count
    assert f["answer"].startswith("4 videos;") and "usual" not in f["answer"]
    assert any("on a usual day of the months before" in o for o in f["observations"])


def test_t10_no_mostly_for_three_of_ten():
    s = case("day_oct30")["sheet"]   # speedrun clips 45% of the day
    assert strict_obs("Mostly {themes[0].name} that day ({themes[0].share}).", s)[1] == ["spread"]


# ================================ T11: what each top channel is ===================================================
def test_t11_channels_say_their_area_the_ranking_says_what_and_the_offers_are_by_area(r12):
    I = ins()
    s = sheet_of(r12, QS["q2"])
    assert all(c.get("area") for c in s["channels"][:2]) and s["top_areas"]["of"] == len(s["channels"][:5])
    assert any(o.startswith("only_topic:") and o.split(":", 1)[1] in {a["name"] for a in s["areas"]}
               for o in s["offers"])
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    # round 12, pass 2 fix: the line says what most of the top 5 are and what the others are ("2 of your top 5 are
    # ... channels (A, B); C is ...")
    assert any(re.match(r"^(?:All )?\d+ of your top \d+ are .+ channels|^What they are:", o) for o in f["observations"])


# ================================ T12: every chart row is one line at 430 px =========================================
def test_t12_chart_rows_are_short_and_labels_are_cut_with_an_ellipsis():
    I = ins()
    s = {"kind": "top", "lang": "en", "themes": [
        {"name": "A very long theme name about painting things", "share": 0.3},
        {"name": "Short", "share": 0.2}]}
    text, _ = I.chart(s)
    rows = text.split("\n")[1:]
    assert rows[0] == "████████ 30% A very long theme…" and all(len(r) <= 34 for r in rows)
    assert I.BAR_CELLS == 8


# ================================ T14: a history answer not ready in time sends the code reply ===================
def test_t14_a_slow_sheet_sends_the_code_reply_and_no_model_call(wr, monkeypatch):
    Hm, F, L, T = mods()
    monkeypatch.setattr(Hm, "WRITE_TIMEOUT_S", 0.3)
    real = F.build

    def slow(*a, **k):
        time.sleep(1.0)
        return real(*a, **k)
    monkeypatch.setattr(F, "build", slow)
    t0 = time.time()
    out, calls = ask(wr, QS["q1"])
    assert time.time() - t0 < 1.0 and calls == [] and "• " not in out
    assert last_steps(wr)["writer"]["error"] == "late"
    time.sleep(1.2)   # the late worker finishes without a model call
    assert "mvp_insight" not in wr["calls"]


# ================================ T15: the Spanish of row 7 ==========================================================
@pytest.mark.parametrize("text", ["¿cómo ha cambiado lo que veo desde 2020?", "como cambió lo que veo desde 2020",
                                  "¿cómo han cambiado mis gustos desde 2020?",
                                  "¿cómo ha ido cambiando lo que veo desde 2020?",
                                  "¿cómo cambiaron mis intereses desde 2020?"])
def test_t15_spanish_ways_of_asking_how_it_changed_are_read_as_changed(text):
    Hm = mods()[0]
    q = Hm.read(text, TODAY)
    assert q is not None and q.kind == "changed" and q.lang == "es"


@pytest.mark.parametrize("text", ["¿cuántos videos vi en 2020?", "¿qué vi el 30 de octubre?",
                                  "cambia el idioma a inglés", "¿cómo cambio mi contraseña?"])
def test_t15_near_spanish_traps_are_not_changed(text):
    Hm = mods()[0]
    q = Hm.read(text, TODAY)
    assert q is None or q.kind != "changed"


def test_t15_the_spanish_change_answer_is_eras_not_a_run_of_numbers(r12):
    I = ins()
    s = sheet_of(r12, "¿cómo ha cambiado lo que veo desde 2020?")
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"].startswith("De 2021 a 2022 lideró gaming") and not re.search(r"\b20\d\d: \d", f["answer"])


# ================================ the live reading on the real library (made-up stand-ins) ======================
def test_live_a_count_said_as_a_share_is_dropped():
    s = case("cmp_years")["sheet"]   # totals.shorts and previous.shorts are counts
    kept, whys = strict_obs("Your Shorts share jumped from {previous.shorts} to {totals.shorts}.", s)
    assert kept is None and whys == ["count_as_share"]
    kept, _ = strict_obs("Shorts went from {previous.shorts} to {totals.shorts} videos.", s)
    assert kept == "Shorts went from 3,400 to 11,000 videos."


def test_live_a_so_what_question_code_cannot_follow_is_said_as_a_notice():
    I = ins()
    c = case("cmp_years")
    raw = dict(c["fake"], so_what={"pick": "shorts_shift:up", "text": "Shorts rose to {totals.shorts} videos; want to look at what changed?"})
    f = I.fill(I.check(raw, c["sheet"]), raw, c["sheet"])
    assert ("so_what", "dead_question") in [(d[0], d[1]) for d in f["dropped"]]
    # round 12, pass 4 (V4, changed on purpose): a notice with no step is a bullet, not a so-what
    # (here the answer says the Shorts already, so it is no bullet either: one fact once)
    assert not f["so_what"] and ("so_what", "no_step") in [(d[0], d[1]) for d in f["dropped"]], f
    assert not any(o.endswith("?") for o in f["observations"])


def test_live_a_comparisons_answer_is_codes_ratio_in_words():
    I = ins()
    c = case("cmp_gaming_art")
    raw = dict(c["fake"], answer="This year you opened gaming about 3 times as many as many gaming videos as art.")
    f = I.fill(I.check(raw, c["sheet"]), raw, c["sheet"])
    assert f["answer"].startswith("Much more gaming than art: about 3 times as many (640 against 212)")


def test_live_a_topics_share_is_of_its_own_videos_and_an_estimate_says_about():
    I = ins()
    s = {"kind": "count", "lang": "en", "filters": {"topic": "blender"},
         "topics": [{"name": "blender", "items": 300, "matched_by": "themes and words"}]}
    assert I.scoped("Art and design made up 89% of what you opened.", s) == \
        "Art and design made up 89% of your blender videos."
    # round 12, pass 3 fix (judge A, row 3, on purpose): the count as counted, with what it counts (no "about")
    # round 12, pass 4 (V6, changed on purpose): what it counts, in words
    assert I.scoped("You opened 300 blender videos.", s, answer=True) == \
        "You opened 300 videos whose title or theme is about blender."
    assert I.scoped("You opened about 300 blender videos.", s, answer=True) == \
        "You opened 300 videos whose title or theme is about blender."


def test_live_one_area_every_year_charts_the_move_to_shorts():
    I = ins()
    s = {"kind": "changed", "lang": "en", "periods": [
        {"label": str(y), "items": 100, "areas": [{"name": "gaming", "share": 0.3}], "shorts_share": sh}
        for y, sh in ((2020, 0.04), (2023, 0.5), (2026, 0.81))]}
    lines = I.chart(s)[0].split("\n")
    assert lines[0] == "Shorts' share of your YouTube videos, by year:" and lines[-1].endswith("2026 81%")


@pytest.mark.parametrize("text, want", [
    ("The long videos were typically about {totals.long_median_min} minutes.",
     "The long videos were typically about 23 minutes."),
    ("Typically {totals.long_median_min} minute videos.", "Typically 23 minute videos."),
    ("Typically about {totals.long_median_min}.", "Typically about 23 minutes.")])
def test_live_the_median_length_is_said_once_in_minutes(text, want):
    I = ins()
    s = {"kind": "top", "lang": "en", "totals": {"items": 10, "long_median_min": 23}}
    assert I.render(text, I.shown(s), I.Facts(I.shown(s)), True)[0] == want
