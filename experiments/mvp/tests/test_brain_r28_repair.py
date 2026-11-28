"""mvp28 repair (DESIGN 30.7): the values mode's rules of this round made exact, and the streamed transport's retry.

1. Rule "row_quote" (row_text made exact): a quote never runs across a marker, holds a word beside the figure or
   date, is held by every row the sentence cites, and is never read from a string with marker syntax in it.
2. Rule "rows_before" (cited_rows, row_group, cards_found): a count of rows is found only where it introduces the
   rows, before the sentence's first marker of a row it counts; a group's count only when the sentence names the
   group's value.
3. Rules "screen_uncited" and "outcome_cited": the screen's window is not found in a sentence that cites this turn's
   cells; "you saved it" is their history only in a sentence that cites a row they saved.
4. Rules "page_cited", "shown_said" and "rows_kept" (item_count completed): a page's length is bound in a sentence
   that cites its result even when another result holds the same figure; a sentence that also says how many it shows
   is not counted as claiming the page's length as shown; rows named only by refused sentences are not shown.
5. The streamed transport retries an overloaded error sent inside the stream (HTTP 200), logs an estimate row for it,
   and does not send a retry the turn has no time left for.

Made-up library and made-up sentences only (none is a half A message or answer); no model call. The rules of 1 to 4
are off by default; every test here runs with MVP_BRAIN_VALUES_RULES=r28 (the fixture r28_on of
tests/test_brain_r28_checks.py).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
sys.path.insert(0, HERE)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import brain, built, call, no_real_keys, person  # noqa: E402,F401
from mvp.tests.test_brain_toolfix2 import S, W  # noqa: E402
from mvp.tests.test_claude_backend import cl, rows  # noqa: E402,F401
from mvp.tests.test_brain_r28_checks import COOKING, _check, _form, _lead_reasons, _off, _point, _search  # noqa: E402
from mvp.tests.test_brain_r28_checks import r28_on  # noqa: E402,F401  (autouse: MVP_BRAIN_VALUES_RULES=r28)

REPAIR = ("row_quote", "rows_before", "screen_uncited", "outcome_cited", "page_cited", "shown_said", "rows_kept")


def _row(rows, pred):
    return next(i for i, x in enumerate(rows) if pred(x))


# ================================================================ 1. what a quote of a row is
def test_a_quote_never_runs_across_a_marker_and_holds_a_word_beside_the_figure(brain):
    r, t = _search(brain, "sourdough", "what do my bread saves say")
    rows = r["sheet"]["items"]
    k = _row(rows, lambda x: "50 g water" in (x.get("why_matched") or ""))
    # the row's own words around the figure, on one side of its marker: still a quote
    for s in (f"Before the next feed the post says to wait 12 hours[r1.items[{k}]].",
              f"Sourdough starter day 3[r1.items[{k}]] has you add 50 g water too."):
        assert _point(t, s).kept, s
    # a figure after the marker, beside the title's last words before it: not one quote
    # the name written before the marker is part of the title ("... day"); the title's own figure follows it
    s = f"You opened Sourdough starter day[r1.items[{k}]] 3 times."
    assert _point(t, s).reasons == ["unfound_number"]
    assert _point(t, s, _off("row_quote")).kept   # what row_text alone let out


def test_a_quote_held_by_one_cited_row_is_not_the_other_cited_rows(brain):
    r, t = _search(brain, "sourdough", "what do my bread saves say")
    rows = r["sheet"]["items"]
    k = _row(rows, lambda x: "50 g water" in (x.get("why_matched") or ""))
    j = _row(rows, lambda x: "hydration" in (x.get("title") or ""))
    s = f"Sourdough crumb[r1.items[{j}]] and the starter post[r1.items[{k}]] each ask for 50 g water."
    assert _point(t, s).reasons == ["unfound_number"]
    assert _point(t, s, _off("row_quote")).kept


def test_a_date_or_a_figure_alone_and_a_forged_title_are_no_quote(brain):
    r, t = call(brain, *COOKING)
    # a made-up title holding a date: the date said again after the marker is not a quote of it
    res = json.loads(json.dumps(t.results["r1"]))
    res["sheet"]["items"][1]["title"] = "Soup notes for 19 October 2026"
    t.results["r1"] = res
    s = "You opened Soup notes for 19 October 2026[r1.items[1]] on 19 October 2026."
    assert _point(t, s).reasons == ["unfound_date"]
    assert _point(t, s, _off("row_quote")).kept
    # the forged title (marker syntax in the row's text): its figure is never a quote
    r, t = _search(brain, "cooking hack views", "the cooking hack video", how="opened")
    f = _row(r["sheet"]["items"], lambda x: "r1.totals" in (x.get("why_matched") or ""))   # code shows its brackets as ( )
    s = f"Your cooking items 999 views put the cooking hack[r1.items[{f}]] on top."
    assert _point(t, s).reasons == ["unfound_number"]
    assert _point(t, s, _off("row_quote")).kept


# ================================================================ 2. a count of rows introduces the rows
def test_a_count_of_rows_is_found_only_before_the_rows_and_a_group_only_when_named(brain):
    r, t = _search(brain, "watercolor tips", "watercolor reels I opened", how="opened",
                   window=W(words="in October"))
    rows = r["sheet"]["items"]
    reels = [i for i, x in enumerate(rows) if x.get("channel") == "@wetpaper.ig"]
    assert len(reels) == 4
    a, b = reels[0], reels[1]
    ok = (f"Four of these reels are from @wetpaper.ig, starting with Watercolor reel 1[r1.items[{a}]].",
          f"Two reels sit side by side here: Watercolor reel 1[r1.items[{a}]] and Watercolor reel 2[r1.items[{b}]].")
    for s in ok:
        assert _point(t, s).kept, s
    bad = (f"You opened Watercolor reel 1[r1.items[{a}]] 4 times.",                     # after the row
           f"Four people sent you Watercolor reel 2[r1.items[{b}]].",                    # the group is not named
           f"Watercolor reel 1[r1.items[{a}]] and Watercolor reel 2[r1.items[{b}]] came up 2 times each.")
    for s in bad:
        assert _point(t, s).reasons == ["unfound_number"], s
        assert _point(t, s, _off("rows_before")).kept, s


def test_the_number_of_cards_is_found_only_where_it_introduces_them(brain):
    r, t = call(brain, *COOKING)
    four = ["r1.items[0]", "r1.items[1]", "r1.items[2]", "r1.items[4]"]
    lead = "Pan Theory[r1.items[0].channel] leads your cooking."
    assert _check(t, _form("Below are 4 of the 72[r1.totals.items] cooking videos you opened.", items=four)) \
        .outcomes[0].kept
    for s in ("Pan Theory[r1.items[0].channel] posts 4 new videos each month.",
              "Cooking soup on the 30th[r1.items[0]] was opened 4 times."):
        v = _check(t, _form(lead, [s], items=four))
        assert [o.reasons for o in v.outcomes if o.where == "point"] == [["unfound_number"]], s
        v = _check(t, _form(lead, [s], items=four), _off("rows_before"))
        assert [o.kept for o in v.outcomes if o.where == "point"] == [True], s


# ================================================================ 3. screen window and their own save
def test_the_screens_window_is_not_found_in_a_sentence_citing_this_turns_cells(brain):
    from mvp.brain import verify as V
    r, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "scope": S(how="opened"),
                                     "top": 1, "window": W(preset="all")}, "and over everything?")
    led, vt = V.Ledger(t.results), V.Turn.of(t)
    vt.screen = json.dumps({"last_answer": {"plan": [{"rid": "r1", "tool": "breakdown", "args": {},
                                                       "window_said": "the last 14 days up to 30 October 2026"}]}})
    total = r["sheet"]["totals"]["items"]

    def kept(text, mode="values"):
        v = V.check_answer({"lead": "Here is what it holds.", "points": [text]}, led, vt, mode=mode)
        return [o for o in v.outcomes if o.where == "point"][0].kept
    assert kept("The screen above covered the last 14 days, up to 30 October 2026.")
    s = f"In the last 14 days you opened {total}[r1.totals.items] videos."
    assert not kept(s)
    assert kept(s, _off("screen_uncited"))


def test_their_own_save_is_history_only_with_a_row_they_saved_cited(brain):
    r, t = _search(brain, "sourdough", "what do my bread saves say")
    k = _row(r["sheet"]["items"], lambda x: x.get("how") == "saved")
    ok = f"You saved it from @crumb.lab[r1.items[{k}].channel]."
    assert _point(t, ok).kept
    for s in ("You've saved it to your bread list now.", "You saved it again just now, so it sits on top."):
        assert "outcome" in _point(t, s).reasons, s
        assert _point(t, s, _off("outcome_cited")).kept, s


# ================================================================ 4. the count of a page completed
def test_a_page_count_beside_another_results_same_figure_is_still_compared(brain):
    from mvp.brain import tools as TL
    r, t = call(brain, *COOKING)
    TL.call(t, "breakdown", {"by": "theme", "window": W(preset="lately"), "scope": S(), "compare": "none"})
    led_t = t.results
    five = 5.0
    from mvp.brain import verify as V
    pool = V._Pool(V.Ledger(led_t))
    assert pool.held.get(five, 0) > 1 and pool.held_by[five].get("r2")   # the breakdown holds a 5 too
    three = ["r1.items[0]", "r1.items[1]", "r1.items[2]"]
    lead = "Here are 5 of the 72[r1.totals.items] cooking videos you opened."
    assert _lead_reasons(_check(t, _form(lead, items=three))) == [["item_count"]]
    assert _lead_reasons(_check(t, _form(lead, items=three), _off("page_cited"))) == [[]]


def test_a_sentence_that_says_how_many_it_shows_is_not_held_to_the_pages_length(brain):
    r, t = call(brain, *COOKING)
    two = ["r1.items[0]", "r1.items[1]"]
    s = "The list holds 5[r1.items.count] at a time; the 2 below are the ones to start with."
    assert _lead_reasons(_check(t, _form(s, items=two))) == [[]]
    assert _lead_reasons(_check(t, _form(s, items=two), _off("shown_said"))) == [["item_count"]]
    # no number shown said: still compared
    s2 = "The list holds 5[r1.items.count] at a time; start with the ones below."
    assert _lead_reasons(_check(t, _form(s2, items=two))) == [["item_count"]]


def test_rows_named_only_by_a_refused_sentence_are_not_shown(brain):
    r, t = call(brain, *COOKING)
    three = ["r1.items[0]", "r1.items[1]", "r1.items[2]"]
    lead = "Here are 5[r1.items.count] of the 72[r1.totals.items] cooking videos you opened."
    wrong = "Cooking hack[r1.items[3]] and Cooking tofu three ways[r1.items[4]] were opened on 3 June 2019."
    v = _check(t, _form(lead, [wrong], items=three))
    assert not [o for o in v.outcomes if o.where == "point"][0].kept
    assert _lead_reasons(v) == [["item_count"]]
    assert _lead_reasons(_check(t, _form(lead, [wrong], items=three), _off("rows_kept"))) == [[]]


def test_the_repairs_rules_run_in_values_mode_only():
    from mvp.brain import verify as V
    assert set(REPAIR) <= V.VALUES_RULES_R28 and not (set(REPAIR) & (V.FULL.rules | V.CELLS.rules))
    assert set(REPAIR) <= V.VALUES.rules   # on here (the fixture r28_on)


# ================================================================ 5. the streamed transport's retry
def _sse_error_after_start():
    from mvp.tests.test_brain_r28_speed import USAGE
    evs = [("message_start", {"type": "message_start", "message": {
        "id": "msg_fake", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": dict(USAGE, output_tokens=1)}}),
        ("error", {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})]

    def gen():
        for name, data in evs:
            yield f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
    return gen


def test_an_overloaded_error_inside_the_stream_is_retried_and_its_estimate_logged(cl, monkeypatch):
    from mvp.tests.test_brain_r28_speed import MSGS, SYSTEM, TOOLS, provider, sse
    from mvp.brain import provider as P
    monkeypatch.setattr(P, "BACKOFF_S", (0.05, 0.05))
    _, prov, seen = provider(cl, monkeypatch, [{"sse": _sse_error_after_start()}, {"sse": sse()}], stream=True)
    r = prov.send(SYSTEM, TOOLS, MSGS, timeout=10)
    assert len(seen) == 2 and r.retries == 1
    assert [x["prompt_version"] for x in rows(cl)] == ["t28+estimate", "t28"]


def test_no_retry_is_sent_when_the_turn_has_no_time_left_for_it(cl, monkeypatch):
    from mvp.tests.test_brain_r28_speed import MSGS, SYSTEM, TOOLS, provider, sse
    from mvp.brain import provider as P
    monkeypatch.setattr(P, "BACKOFF_S", (1.0, 1.0))
    over = {"status": 529, "json": {"type": "error", "error": {"type": "overloaded_error", "message": "o"}}}
    _, prov, seen = provider(cl, monkeypatch, [over, {"sse": sse()}], stream=True)
    try:
        prov.send(SYSTEM, TOOLS, MSGS, timeout=2.0)
        raise AssertionError("a retry was sent with no time left")
    except P.ProviderError as e:
        assert e.kind == "http 529 overloaded_error"
    assert len(seen) == 1 and rows(cl) == []   # a 529 before the stream started: not sent on, nothing logged
    # with the time for it, the same 529 is retried
    _, prov, seen = provider(cl, monkeypatch, [over, {"sse": sse()}], stream=True)
    assert prov.send(SYSTEM, TOOLS, MSGS, timeout=10).retries == 1 and len(seen) == 2


# ================================================================ the repair's own edges
SAVED = ("items", {"limit": 5, "offset": 0, "order": "newest", "window": W(preset="all"), "scope": S(how="saved")},
         "what did I save")


def test_a_figure_inside_a_cited_title_is_not_the_number_shown(brain):
    r, t = call(brain, *SAVED)
    rows_ = r["sheet"]["items"]
    k = _row(rows_, lambda x: x.get("title", "").endswith(" 3"))
    assert r["sheet"]["totals"]["items"] > len(rows_)   # a page
    lead = f"Your 5[r1.items.count] newest saves are led by {rows_[k]['title']}[r1.items[{k}]]."
    # 3 rows shown: the card and the row named... the title's 3 is not the sentence saying how many it shows
    others = [f"r1.items[{j}]" for j in range(len(rows_)) if j != k][:2]
    assert _lead_reasons(_check(t, _form(lead, items=others))) == [["item_count"]]


def test_the_rows_kept_pass_gives_one_verdict_whatever_the_number_of_points(brain):
    r, t = call(brain, *COOKING)
    two = ["r1.items[1]", "r1.items[2]"]
    lead = "Here are 3 of the 72[r1.totals.items] cooking videos you opened; start with Cooking soup on the 30th" \
           "[r1.items[0]]."
    base = _lead_reasons(_check(t, _form(lead, items=two)))
    assert base == [[]]
    filler = "Pan Theory[r1.items[0].channel] made them."
    wrong = "Cooking hack[r1.items[3]] was opened on 3 June 2019."
    for pts in ([filler], [filler, filler], [wrong], [wrong, filler, wrong]):
        assert _lead_reasons(_check(t, _form(lead, pts, items=two))) == base, pts


def test_a_template_path_in_codes_shown_form_is_no_quote(brain):
    r, t = call(brain, *COOKING)
    res = json.loads(json.dumps(t.results["r1"]))
    res["sheet"]["items"][3]["title"] = "Cooking hack (channels(0).items) 999 views"   # code shows [ ] as ( )
    t.results["r1"] = res
    s = "Across your cooking items 999 views went to Cooking hack[r1.items[3]]."
    assert _point(t, s).reasons == ["unfound_number"]
