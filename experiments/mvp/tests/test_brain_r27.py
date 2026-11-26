"""mvp27 (DESIGN.md section 29): the baseline made right before the first prompt change.

Two values rules ("row_name": a title or name before a row marker is that row's own; "cell_found" with "day_typed": a
figure is found in a cell, never in code's prose), the values mode's own motive pattern ("motive_you"), a citable
`left_out` cell for the counts a result left out, the screen marked as data with the model's arguments neutralised, and
two prompt files beside brain_v3 (brain_v3b, the baseline; brain_v4_meaning, the arm). Full and cells mode are
unchanged (tests/test_brain_values.py pins their digests). Made-up library and made-up sentences only; no model call.
"""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import brain, built, call, no_real_keys, person, turn  # noqa: E402,F401
from mvp.tests.test_brain_slice import TODAY, harness  # noqa: E402,F401
from mvp.tests.test_brain_toolfix2 import S, W  # noqa: E402
from mvp.tests.test_brain_toolgaps import kept, ledger_of  # noqa: E402

# (the fixtures drop every mvp module between tests, so each test imports the brain's modules itself)


def _no_rules():
    """The values mode of 650062c (DESIGN 26), with none of this round's rules: for the twins."""
    from mvp.brain import verify as V
    return V.values_mode(rules=frozenset())


def _lead(t, sentence, mode="values"):
    from mvp.brain import verify as V
    led, vt = ledger_of(t)
    v = V.check_answer({"lead": sentence, "points": []}, led, vt, mode=mode)
    return v.outcomes[0]


# ================================================================ the pin
def test_the_rules_are_pinned_and_on_by_default():
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    # (mvp28 added its own rules; tests/test_brain_r28_checks.py pins them)
    assert V.VALUES_RULES >= frozenset({"row_name", "cell_found", "day_typed", "motive_you"})
    assert V.VALUES_RULES <= V.VALUES.rules and "row_name" in V.VALUES_REFUSE and "row_name" in V.VALUES_CODES
    assert not (V.VALUES_RULES & _no_rules().rules) and _no_rules().rule("values") and _no_rules().rule("nw_refuse")
    assert not (V.VALUES_RULES & (V.FULL.rules | V.CELLS.rules))   # full and cells never run them


# ================================================================ 1a. a name before a row marker is that row's own
SAVED = ("items", {"limit": 5, "order": "newest", "window": W(preset="lately"), "scope": S(how="saved")},
         "what have i saved lately")


def test_another_rows_title_before_a_row_marker_is_refused(brain):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    # run B N038.0, the one false sentence sent: the newest save is the pasta post (r1.items[0]); "Watercolor portrait
    # lesson 3" is r1.items[3]'s title, found in the turn's results, so 650062c's values mode let it out
    env_, t = call(brain, *SAVED)
    rows = env_["sheet"]["items"]
    assert rows[3]["title"] == "Watercolor portrait lesson 3" and rows[0]["title"] != rows[3]["title"]
    bad = "Your newest save is Watercolor portrait lesson 3[r1.items[0]]."
    assert _lead(t, bad).reasons == ["row_name"]
    assert _lead(t, bad, _no_rules()).kept   # the hole of DESIGN 26, closed by the rule alone
    # the true twins: the row's own title, a part of it, its channel
    assert _lead(t, "You saved Watercolor portrait lesson 3[r1.items[3]] on 5 October 2026[r1.items[3].when].").kept
    assert _lead(t, "You saved Sourdough starter day 3[r1.items[2]] on 5 October 2026[r1.items[2].when].").kept
    assert _lead(t, "Your newest save is from @noodle.nights[r1.items[0]], on 10 October 2026[r1.items[0].when].").kept
    # the repair detail quotes no title
    assert "Watercolor" not in " ".join(_lead(t, bad).details)


def test_the_title_bound_by_a_value_marker_only_is_not_closed(brain):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    # not closed (DESIGN 29.1): the rule reads a name before a ROW marker; an unquoted title of another row written
    # with only a date marker of this row is still found in the turn's results and goes out
    _env, t = call(brain, *SAVED)
    assert _lead(t, "Your newest save is Watercolor portrait lesson 3, saved on 10 October "
                    "2026[r1.items[0].when].").kept


# ================================================================ 1b. a figure is found in a cell, not in code's prose
def _ledger():
    from mvp.brain import verify as V
    env_ = {"rid": "r1", "tool": "breakdown",
            "meta": {"window_said": "the 4 weeks up to 30 October 2026, where your export ends",
                     "window_dates": {"start": "2026-10-03", "end": "2026-10-30", "days": 28,
                                      "said": "3 to 30 October 2026"},
                     "window_dates_before": {"start": "2026-09-05", "end": "2026-10-02", "days": 92,
                                             "said": "5 September to 2 October 2026"},
                     "notes": ["The window before has 77 days, against 28 here.", "Your export ends on 30 October 2026."]},
            "sheet": {"kind": "top_channels", "totals": {"items": 61},
                      "channels": [{"ref": "r1.channels[0]", "name": "Clip Factory", "items": 41, "days": 12},
                                   {"ref": "r1.channels[1]", "name": "Pan Theory", "items": 20, "days": 9}]}}
    return V.Ledger({"r1": env_})


@pytest.mark.parametrize("sentence, with_rule, without", [
    # a figure only in a note: found before, not now
    ("You opened 77 videos from new channels.", False, True),
    # a figure of a ref ("r1.channels[1]") or of a date ("2026-10-03"): no cell holds it as a value
    ("You opened 3 videos from Clip Factory.", False, True),
    # a window's figure with its unit: kept; alone: refused
    ("In the 4 weeks up to 30 October 2026, you opened 61 videos.", True, True),
    ("You opened 4 videos from Pan Theory.", False, True),
    # a count of days: found as days, not as videos (day_typed)
    ("This window has 28 days, against 92 in the window before.", True, True),
    ("You opened 92 videos from new channels.", False, True),
    ("Clip Factory was on 12 of those days.", True, True),
    ("You opened 12 videos from Clip Factory.", False, True),
    # cells as before
    ("You opened 61 videos, 41 from Clip Factory.", True, True),
    ("You opened 2 channels' videos.", True, True),   # the length of a list of rows
])
def test_found_means_a_cell(sentence, with_rule, without):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    led = _ledger()
    t = V.Turn(message="what did i watch lately")
    assert V.check_sentence_values(sentence, led, t, "lead").kept is with_rule, sentence
    assert V.check_sentence_values(sentence, led, t, "lead", mode=_no_rules()).kept is without, sentence


def test_the_merge_seam_is_closed(brain):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    # DESIGN 28: the note on unequal windows says the window before this fall has 92 days; a made-up "92 videos" got
    # out of values mode. A day count is a value of a cell (window_dates_before.days), so it is found as days only
    from mvp.tests.test_brain_r26_merge import FALL, _call
    env_, t = _call(brain, FALL)
    assert env_["meta"]["window_dates_before"]["days"] == 92
    assert kept(t, "This fall so far has 60 days, against 92 in the summer before.", mode="values") is True
    assert kept(t, "This fall you opened 92 videos from new channels.", mode="values") is False
    assert _lead(t, "This fall you opened 92 videos from new channels.", _no_rules()).kept


# ================================================================ 2. the motive pattern of values mode
MEANING_TRUE = ["2024 looks thin because you opened 8 videos that year.",
                "Gaming led because Clip Factory made 61 of its 142 videos.",
                "October stands out because you opened 142 videos in it, against 90 in September.",
                "It counts as new because you first opened it on 1 October 2026.",
                "Your spring of 2024 is thin because you saved 3 posts in it."]
MOTIVE_FALSE = ["Clip Factory led with 61 videos because you were bored.",
                "You opened 61 videos because you love cooking.",
                "That is because you wanted to relax after work.",
                "Gaming grew because it relaxes you.",
                "October was busy because of your stress at work.",
                "You must be into cooking, with 61 videos.",
                "You opened 40 of them because you're stressed.",
                "You watched them to unwind.",
                "You saved them because you need new recipes."]


def test_a_reading_with_because_is_no_motive():
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    for s in MEANING_TRUE:
        assert V._MOTIVE.search(s.lower()), s            # today's pattern (full and cells, unchanged) hits it
        assert not V._V_MOTIVE.search(s.lower()), s      # the values pattern does not
        assert not V.PSYCH.search(s.lower()), s
    for s in MOTIVE_FALSE:
        assert V.PSYCH.search(s.lower()) or V._V_MOTIVE.search(s.lower()), s


def test_every_planted_psych_case_is_still_refused():
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    from mvp.brain import planted as P
    data = P.load()
    cases = [c for c in data["cases"] if "psych" in str(c.get("class") or "") or "motive" in str(c.get("class") or "")
             or c["id"] in ("attack_T01", "attack_T02", "attack_T03", "f_psych")]
    assert {"attack_T01", "attack_T02", "attack_T03", "f_psych"} <= {c["id"] for c in cases}
    for c in cases:
        t = c.get("turn") or {}
        vt = V.Turn(message=t.get("message", ""), names=list(t.get("names") or []),
                    sensitive_names=list(t.get("sensitive_names") or []))
        for f in c.get("forms") or [c["form"]]:
            v = V.check_answer(f, V.Ledger(data["ledgers"][c["ledger"]]), vt, mode="values")
            assert any("psych" in o.reasons for o in v.outcomes), c["id"]


# ================================================================ 4. the counts a result left out, as a cell
FRIENDS = ("breakdown", {"by": "channel", "window": W(preset="all"), "scope": S(how="saved"), "compare": "none"},
           "what are my friends posting that i save")
SPRING = ("breakdown", {"by": "area", "window": W("spring 2024"), "compare": "none"}, "spring 2024, what was i watching")


def test_left_out_is_a_cell_of_counts_only(brain):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    env_, t = call(brain, *FRIENDS)
    assert env_["sheet"]["left_out"] == {"friends": 1} and env_["meta"]["hidden"]["friends"] == 1
    env2, t2 = call(brain, *SPRING)
    assert env2["sheet"]["left_out"] == {"private": 23} and env2["meta"]["hidden"]["sensitive"] == 23
    # a count of 0 has no cell, and the constant of a title-word scope is no count
    env3, _t = call(brain, "breakdown", {"by": "channel", "window": W("October"), "compare": "none"}, "october")
    assert "left_out" not in env3["sheet"] and env3["meta"]["hidden"]["friends"] == 0
    from mvp.brain import tools as TL
    env4, _t = call(brain, "breakdown", {"by": "none", "window": W(preset="all"), "compare": "none",
                                         "scope": S(only=["castle"])}, "videos with castle in the title")
    assert env4["meta"]["resolved"]["castle"].startswith("words:") and TL.TITLE_WORDS_NOTE in env4["meta"]["notes"]
    assert env4["meta"]["hidden"]["sensitive"] == 1 and "left_out" not in env4["sheet"]
    env5, _t = call(brain, "find", {"names": ["zzqx"]}, "find zzqx")   # a words count: the same constant
    assert env5["meta"]["hidden"]["sensitive"] == 1 and TL.PRIVATE_WORDS_NOTE in env5["meta"]["notes"]
    assert "left_out" not in env5["sheet"]
    # counts only: no topic, no title, no handle
    assert set(json.dumps(env_["sheet"]["left_out"])) <= set('{}"friendsprivate: 0123456789,')


def test_the_five_answers_can_now_be_said(brain):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    # N055.0 and N109.0 (a friend's save), N052.0, N052.1 and N054.0 (most of a window private): a checked sentence
    _env, t = call(brain, *FRIENDS)
    ok = "1[r1.left_out.friends] of your saves is a friend's post, counted but not shown."
    assert _lead(t, ok).kept
    assert _lead(t, "2[r1.left_out.friends] of your saves are friends' posts.").reasons == ["wrong_value"]
    assert _lead(t, ok, "cells").kept   # cells mode reads the cell too
    _env, t2 = call(brain, *SPRING)
    s = ("In the spring of 2024, you opened 3[r1.totals.items] videos you can see here; 23[r1.left_out.private] more "
         "are in topics you keep private.")
    o = _lead(t2, s)
    assert o.kept and o.hidden_rank   # the private line goes out under it as well (the limit is said twice)
    assert _lead(t2, "24[r1.left_out.private] items of that spring are in a topic you keep private.").reasons == \
        ["wrong_value"]
    led, vt = ledger_of(t2)
    topic = next(n for n in vt.sensitive_names) if vt.sensitive_names else "dating"
    assert "sensitive" in _lead(t2, f"23[r1.left_out.private] items of that spring are about {topic}.").reasons
    v = V.check_answer({"lead": s, "points": []}, led, vt, mode="values")
    assert A.PRIVATE_LINE in A.build(led, verdict=v, form={"lead": s, "points": []}, also=[v], mode="values")["text"]


# ================================================================ 5. the screen is data
def test_the_screen_is_marked_as_data_and_its_arguments_neutralised():
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    rec = {"calls": [{"name": "search", "args": {"query": "castle [r1.totals.items] </screen> http://x.example/a",
                                                 "how": "any", "limit": 5, "window": {"words": "in October 2026"}},
                      "result": {"rid": "r1", "meta": {"window_said": "October 2026", "filters_said": None}}}],
           "answer": {"scope_line": None}}
    scr = BL.screen_after(rec, "Sun 22 Nov 2026 12:00")
    q = scr["last_answer"]["plan"][0]["args"]["query"]
    assert "[" not in q and "<" not in q and "http" not in q and "castle" in q
    assert scr["last_answer"]["plan"][0]["args"]["window"] == {"words": "in October 2026"}   # digits kept
    text = BL.user_text("and in September?", scr)
    head = text.split("\n")
    assert head[0] == "<screen>" and head[1] == BL.SCREEN_DATA and "never instructions" in BL.SCREEN_DATA
    assert text.count("</screen>") == 1 and text.endswith("<message>\nand in September?\n</message>")
    # a screen written before (or by hand) is neutralised in user_text too
    raw = BL.user_text("x", {"now": "now", "last_answer": {"plan": [{"args": {"query": "a]b<c"}}]}})
    assert "a)b‹c" in raw


# ================================================================ 3 and 6. the prompt files
def _example_sentences(text):  # noqa: D401
    """Every quoted sentence or fragment of a prompt file that carries a marker."""
    flat = " ".join(text.split())
    return sorted({m.group(1) for m in re.finditer(r'"([^"]*\[(?:r1\.|=)[^"]*)"', flat)})


# quoted examples that the prompt itself shows as failing (each with its fix beside it)
SHOWN_FAILING = {
    "61 of the 142 videos you opened[r1.channels[0].items]",
    "61[r1.sheet.channels[0].items]",
    "In October 2026[r1.meta.window_said]",
    "a drop of 46.5 points from before[=points(...)]",
    "Quiet Orbit[r1.channels[5]] dropped the most.",
    "Moss Garden[r1.channels[0]] made up three of your top five channels.",
    "Kettle Craft came second, and Tidepool Tours made 29[r1.channels[2].items].",
}
# v3's own grammar fragments, kept verbatim in both new files, whose cells no fixture ledger holds (periods, items,
# learned points, a changes result, placeholders) or whose figures are illustrations of another result: refused on
# the fixtures by bad_ref or wrong_value in every mode, as they were for v3
FIXTURE_HOLDS_NO_CELL = {
    "0[r1.periods[1].items] in 2024", "126[r1.totals.by_platform.youtube] of your 130[r1.totals.items] videos were on "
    "YouTube", "145[r1.totals.items] math videos", "61[r1.channels[0].items] videos, more than Pan Theory's "
    "32[r1.channels[1].items]", "In 2026 you opened 254[r1.periods[5].items] videos.",
    "Watercolor portrait lesson 1[r1.items[0]]", "You saved 3[r1.items.count] lessons", "[r1.points[0]]",
    "[r1.points[1]]", "down 46 points[=points(r1.areas[1].share, r1.areas[1].previous_share)]",
    "fell from 94%[r1.areas_change.left[0].from_share] in 2021 to 31%[r1.areas_change.left[0].to_share] in 2026",
    "on 12 October 2026[r1.items[0].when]", "saved on 3 October 2026[r1.items[0].when]",
    "these 3[r1.items.count] lessons", "twice[=ratio(a, b)]", "up 40%[=pct_change(a, b)]"}


@pytest.mark.parametrize("version", ["brain_v3", "brain_v3b", "brain_v4_meaning"])
def test_every_example_of_the_prompts_passes_values_mode(harness, version):
    from mvp.brain import verify as V  # noqa: F401
    from mvp.tests import brain_prompt_fixture as PF
    text = open(os.path.join(MVP, "prompts", f"{version}.md"), encoding="utf-8").read()
    v3 = set(_example_sentences(open(os.path.join(MVP, "prompts", "brain_v3.md"), encoding="utf-8").read()))
    ledgers = PF.ledgers(harness) + [PF.saved_ledger(harness)]
    vt = V.Turn(message="x", today=TODAY)
    refused = {s for s in _example_sentences(text) if s not in SHOWN_FAILING and
               not any(V.check_sentence_values(s, V.Ledger(led), vt, "lead").kept for led in ledgers)}
    assert refused == FIXTURE_HOLDS_NO_CELL, refused ^ FIXTURE_HOLDS_NO_CELL
    new = [s for s in _example_sentences(text) if s not in v3]
    assert len(new) == {"brain_v3": 0, "brain_v3b": 2, "brain_v4_meaning": 5}[version], new
    assert not (set(new) & refused)
    # the limit lead the baseline asks for, said in full on the fixture of a result of saves (no likes in the export)
    led = ledgers[2]
    ch = led["r1"]["sheet"]["channels"][0]
    lead = (f"Your export holds no likes, so here is what you saved most: in the 4 weeks up to 30 October 2026, "
            f"{ch['name']}[r1.channels[0]] led with {ch['items']}[r1.channels[0].items] of "
            f"{led['r1']['sheet']['totals']['items']}[r1.totals.items] saves.")
    assert V.check_sentence_values(lead, V.Ledger(led), vt, "lead").kept, lead


def test_the_baseline_prompt_corrects_only_the_limit_lines_and_adds_left_out():
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    v3 = open(os.path.join(MVP, "prompts", "brain_v3.md"), encoding="utf-8").read()
    v3b = open(os.path.join(MVP, "prompts", "brain_v3b.md"), encoding="utf-8").read()
    v4 = open(os.path.join(MVP, "prompts", "brain_v4_meaning.md"), encoding="utf-8").read()
    assert "code adds the line for it" in v3 and "code adds the line for it" not in v3b
    assert "code writes those lines" in v3 and "code writes those lines" not in v3b
    assert "the lead says so once" in v3b and "left_out.friends" in v3b and "left_out" not in v3
    # the arm is the baseline plus the meaning change only: every line of v3b that v4_meaning drops is one of its
    # three hunks
    gone = [ln for ln in v3b.splitlines() if ln not in v4.splitlines()]
    assert len(gone) == 5 and all(("claim with no marker" in ln or "the only channel" in ln or "so what" in ln or
                                   "Craft items 32" in ln or "came next with 32" in ln) for ln in gone), gone
    assert "Each point says what its number means" in v4


@pytest.mark.parametrize("version", ["brain_v3b", "brain_v4_meaning"])
def test_the_new_prompts_load_by_name_and_v3_stays_the_default(version):
    from mvp.brain import answer as A, loop as BL, verify as V  # noqa: F401
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from mvp.brain import loop as BL; "
            "print(BL.PROMPT_VERSION, BL.PROMPT_PATH.endswith(BL.PROMPT_VERSION + '.md'), len(BL.system_text()))")
    envd = {k: v for k, v in os.environ.items() if k != "MVP_BRAIN_PROMPT"}
    out = subprocess.run([sys.executable, "-B", "-c", code, os.path.dirname(MVP)], capture_output=True, text=True,
                         env=dict(envd, MVP_BRAIN_PROMPT=version), check=True).stdout.split()
    assert out[:2] == [version, "True"] and int(out[2]) > 10000
    out = subprocess.run([sys.executable, "-B", "-c", code, os.path.dirname(MVP)], capture_output=True, text=True,
                         env=envd, check=True).stdout.split()
    assert out[:2] == ["brain_v3", "True"]


# ================================================================ through the loop (the fake provider)
def test_the_new_paths_run_through_the_loop(harness):
    from mvp import eval_brain as E
    from mvp.brain import loop as BL, provider as P
    from mvp.tests.test_brain_slice import ga, run
    items = P.tool_use("items", {"limit": 5, "order": "newest", "window": {"preset": "lately"},
                                 "scope": {"how": "saved"}})
    bad = "Your newest save is Watercolor portrait lesson 3[r1.items[0]]."
    good = "In the 4 weeks up to 30 October 2026, you saved Watercolor portrait lesson 3[r1.items[3]]."
    rec, prov, _t = run(harness, [[items], [ga(bad)], [ga(good)]], message="what have i saved lately",
                        check="values")
    assert rec["verdicts"][0]["outcomes"][0]["reasons"] == ["row_name"]
    assert "not that row's own" in rec["repair_message"] and "Watercolor" not in rec["repair_message"]
    assert rec["lead_source"] == "model_after_repair" and "lesson 3" in rec["answer"]["text"]
    rec.update(id="X", n=0, key="X.0", g2={"verdict": "understood"}, audit={"findings": [], "checked": 0},
               reading_errors=[], reading_window_failed=[], dropped=E.dropped_of(rec))
    assert E.summarize([rec], {"check": "values"})["check"] == "values"
    # the next turn: the screen is marked as data and carries the plan's arguments neutralised
    screen = BL.screen_after(rec, "Sun 22 Nov 2026 12:00")
    friends = P.tool_use("breakdown", {"by": "channel", "window": {"preset": "all"}, "scope": {"how": "saved"},
                                       "compare": "none"})
    lead = "1[r1.left_out.friends] of your saves is a friend's post, counted but not shown."
    prov2 = P.FakeProvider([[friends], [ga(lead)]])
    from mvp.tests.test_brain_slice import turn as sturn
    t2 = sturn(harness, "and my friends' posts?")
    rec2 = BL.run_turn(prov2, t2, screen=screen, check="values")
    first = prov2.sent[0][2][0]["content"]
    assert first.startswith("<screen>\n" + BL.SCREEN_DATA + "\n") and '"tool": "items"' in first
    assert rec2["lead_source"] == "model" and rec2["answer"]["text"].startswith("1 of your saves is a friend's post")
