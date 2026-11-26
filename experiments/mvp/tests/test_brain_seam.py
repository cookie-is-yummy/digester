"""The seam of the brain's step 1 (design/brain_v1/SPEC.md 2.3, 4.3, 4.6): the verifier reads the results the tools
really return (brain/results.py's envelope, built by brain/tools.py on the made-up library of tests/brain_library.py),
not only its own test helper's envelopes.

For each question: the tools are called; a true answer is written by hand in marker form, its numbers taken from an
independent recount of the made-up rows (test_brain_tools' helpers, which share nothing with facts.py), and kept; a
false answer of a shape that depends on what the tools write (a dropped scope, a saved count said as opened, the
second window's year on the first window's cell, a path into the envelope, a marker to a name that did not resolve,
a rank with a private topic above it) is dropped with its reason. The code lead (brain/fallback.py) of the same
results says only recounted numbers, and a template lead passes the verifier itself.

Offline: no model call, no network. Every title, channel and theme is made up."""
import json
import os
import re
import sys
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures and the independent recount)
    ART, COOK, GAMING, LATELY, OCTOBER, B, brain, built, by_channel, call, fake_search, known_long, local,
    no_real_keys, opened, visible_rows)

SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))
LATELY_BEFORE = (date(2026, 9, 5), date(2026, 10, 2))


def pc(part, whole):
    return round(100 * len(part) / len(whole))


def saved(a, b):
    """The ids saved (a save, a playlist or a collection event) between a and b, as a saved breakdown counts them."""
    return {r["id"] for r in visible_rows() for k, at in r["events"]
            if k in ("save", "playlist", "collection") and a <= local(at) <= b}


def first_day(keys):
    return min(local(at) for r in visible_rows() if r["theme"] in keys for k, at in r["events"] if k == "watch")


def day_words(d):
    return f"{d.day} {d.strftime('%B')} {d.year}"


# ---------------------------------------------------------------- helpers over the brain's modules
def ask(e, tool, args, message, **kw):
    """One tool call in a fresh turn -> (envelope, the tools' turn, the verifier's turn)."""
    from mvp.brain import verify as V
    r, t = call(e, tool, args, message, **kw)
    return r, t, V.Turn.of(t)


def verdict(t, vt, lead, points=(), items=()):
    from mvp.brain import verify as V
    return V.check_answer({"lead": lead, "points": list(points), "items": list(items)}, t.results, vt)


def kept(t, vt, lead, points=()):
    v = verdict(t, vt, lead, points)
    bad = [(o.where, o.index, o.reasons, o.details) for o in v.outcomes if not o.kept]
    assert not bad, (lead, points, bad)
    return v


def dropped(t, vt, sentence, reason, where="lead", lead=None):
    """The sentence (as the lead, or as a point after a kept `lead`) is dropped with `reason` among its reasons."""
    if where == "lead":
        v = verdict(t, vt, sentence)
        o = v.lead[0]
    else:
        v = verdict(t, vt, lead, [sentence])
        assert v.lead_ok, [o.reasons for o in v.lead]
        o = [x for x in v.outcomes if x.where == "point"][0]
    assert not o.kept and reason in o.reasons, (sentence, o.reasons, o.details)
    return o


def code_lead(t, vt, how, numbers):
    """The code lead of the turn's results: made the way `how` says, no marker left, every number in it one of the
    recounted `numbers` (window words and dates aside); a template lead passes the verifier itself."""
    from mvp.brain import fallback as FB, verify as V
    cl = FB.code_lead(t.results, turn=vt)
    assert cl["how"] == how, cl
    lead = cl["lead"]
    assert "[" not in lead and "{" not in lead, lead
    res = V.Ledger(t.results).get(cl["rid"]) if cl["rid"] else None
    rest = lead
    if res is not None:
        for ph in V._window_phrases(res):
            rest = re.sub(re.escape(ph), " ", rest, flags=re.I)
    rest = re.sub(V.I._DATE_RX, " ", rest, flags=re.I)
    rest = re.sub(r"\b(?:19|20)\d\d\b", " ", rest)
    said = {int(x) for x in re.findall(r"\d+", rest)}
    assert said <= set(numbers), (lead, said, numbers)
    if how == "template":
        # the template that was sent is one that passed check_answer: run it again from its marker form
        forms = [x for x in FB.templates(res) if V.strip_markers(x) == lead]
        assert forms, lead
        assert verdict(t, vt, forms[0]).lead_ok, forms[0]
    return lead


# ================================================================ 1. channels in October (code_form lead)
def test_channels_in_october(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"}}, "channels in October")
    ch = by_channel(opened(*OCTOBER))
    top = sorted(ch.items(), key=lambda x: -x[1])
    assert top[0] == ("Clip Factory", 61) and top[1][0] == "Pan Theory"
    kept(t, vt, f"In October 2026, Clip Factory[r1.channels[0]] led what you opened, with "
                f"{top[0][1]}[r1.channels[0].items] videos.",
         [f"Pan Theory[r1.channels[1]] came next with {top[1][1]}[r1.channels[1].items]."])
    # a path into the envelope: the probe's shape, with a repair text that teaches the path
    o = dropped(t, vt, f"In October 2026, you opened {len(opened(*OCTOBER))}[r1.sheet.totals.items] videos.", "bad_ref")
    assert "without 'sheet.'" in o.notes["bad_ref"] and "r1.totals.items" in o.notes["bad_ref"]
    # the second row's name on the first row's cell; the right number in the wrong month
    dropped(t, vt, "In October 2026, Pan Theory[r1.channels[0]] led, with 61[r1.channels[0].items] videos.",
            "wrong_name")
    dropped(t, vt, "In September 2026, Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.",
            "wrong_window", where="point", lead="In October 2026, Clip Factory[r1.channels[0]] led what you opened.")
    lead = code_lead(t, vt, "code_form", [])
    assert lead.startswith("In October 2026") and "Clip Factory led, ahead of Pan Theory and " + top[2][0] in lead


# ================================================================ 2. areas lately, shares in points (template)
def test_areas_lately_with_shares_and_a_change_in_points(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "area", "window": {"words": "lately"}}, "what am i into lately")
    now, before = opened(*LATELY), opened(*LATELY_BEFORE)
    g, g0 = opened(*LATELY, keys=GAMING), opened(*LATELY_BEFORE, keys=GAMING)
    share, share0 = pc(g, now), pc(g0, before)
    pts = round(100 * len(g) / len(now) - 100 * len(g0) / len(before))
    assert r["sheet"]["areas"][0]["name"] == "gaming"
    kept(t, vt, f"In the 4 weeks up to 30 October 2026, gaming[r1.areas[0]] led, with {share}%[r1.areas[0].share] "
                f"of what you opened.",
         [f"Gaming[r1.areas[0]] was up {pts} points[r1.areas[0].change_pts] on the 4 weeks before."])
    # the cell in points said as a fraction's percent, and the change said with the wrong sign
    dropped(t, vt, f"Gaming[r1.areas[0]] was down {pts} points[r1.areas[0].change_pts] on the 4 weeks before.",
            "direction", where="point",
            lead=f"In the 4 weeks up to 30 October 2026, gaming[r1.areas[0]] led, with {share}%[r1.areas[0].share] "
                 f"of what you opened.")
    art = pc(opened(*LATELY, keys=ART), now)
    code_lead(t, vt, "code_form", [share, share0, art])


# ================================================================ 3. a count in October; the verb is the base's
def test_a_count_says_the_verb_of_its_base(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "none", "window": {"words": "in October"}},
                   "how much did i watch in october")
    n = len(opened(*OCTOBER))
    kept(t, vt, f"In October 2026, you opened {n}[r1.totals.items] videos.")
    dropped(t, vt, f"In October 2026, you saved {n}[r1.totals.items] videos.", "base")
    # code_form has no answer for a plain count: the template, verified
    code_lead(t, vt, "template", [n])


# ================================================================ 4. only an area: the scope is said
def test_only_an_area_must_be_said(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"},
                                        "scope": {"only": ["gaming"]}}, "gaming channels in october")
    assert r["meta"]["filters_said"] == "only gaming (area)"
    g = opened(*OCTOBER, keys=GAMING)
    cf = by_channel(g)["Clip Factory"]
    kept(t, vt, f"In October 2026, you opened {len(g)}[r1.totals.items] gaming videos.",
         [f"Clip Factory[r1.channels[0]] made {round(100 * cf / len(g))}%[r1.channels[0].share] of the gaming videos "
          f"you opened."])
    kept(t, vt, f"In October 2026, Clip Factory[r1.channels[0]] led your gaming videos, with {cf}[r1.channels[0].items].")
    dropped(t, vt, f"Clip Factory[r1.channels[0]] made {round(100 * cf / len(g))}%[r1.channels[0].share] of what you "
                   f"opened.", "filter_dropped", where="point",
            lead=f"In October 2026, you opened {len(g)}[r1.totals.items] gaming videos.")
    # the probe's false pass: the scope dropped (72 is not what they opened in October: that is 142)
    o = dropped(t, vt, f"In October 2026, you opened {len(g)}[r1.totals.items] videos.", "filter_dropped")
    assert "only gaming" in o.notes["filter_dropped"]
    dropped(t, vt, f"In October 2026, Clip Factory[r1.channels[0]] led, with {cf}[r1.channels[0].items] videos.",
            "filter_dropped")
    # code_form is not used on a scoped result; the template says the scope (mvp20 fix: as the words that open the
    # sentence, so the rank after them is of the scope, not as a tag after the count)
    lead = code_lead(t, vt, "template", [cf, len(g)])
    assert lead.startswith("In October 2026, counting only gaming, ") and "(" not in lead


# ================================================================ 5. without an area
def test_without_an_area_needs_the_exclusion_said(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"},
                                        "scope": {"exclude": ["gaming"]}}, "october without gaming")
    rest = opened(*OCTOBER) - opened(*OCTOBER, keys=GAMING)
    kept(t, vt, f"In October 2026, without gaming, you opened {len(rest)}[r1.totals.items] videos.")
    dropped(t, vt, f"In October 2026, you opened {len(rest)}[r1.totals.items] videos.", "filter_dropped")
    dropped(t, vt, f"In October 2026, you opened {len(rest)}[r1.totals.items] gaming videos.", "filter_dropped")
    top = sorted(by_channel(rest).items(), key=lambda x: -x[1])[0]
    lead = code_lead(t, vt, "template", [top[1], len(rest)])
    assert lead.startswith("In October 2026, without gaming, ") and top[0] in lead


# ================================================================ 6. only the long videos
def test_only_long_videos(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"},
                                        "scope": {"length": "long"}}, "channels in october without shorts")
    lo = opened(*OCTOBER, pred=known_long)
    kept(t, vt, f"In October 2026, you opened {len(lo)}[r1.totals.items] long videos.")
    dropped(t, vt, f"In October 2026, you opened {len(lo)}[r1.totals.items] videos.", "filter_dropped")
    top = sorted(by_channel(lo).items(), key=lambda x: -x[1])
    assert top[0][0] != sorted(by_channel(opened(*OCTOBER)).items(), key=lambda x: -x[1])[0][0]
    # the leader of the long videos is not the leader of what they opened: its rank needs "long"
    dropped(t, vt, f"In October 2026, {top[0][0]}[r1.channels[0]] led, with {top[0][1]}[r1.channels[0].items] videos.",
            "filter_dropped")
    kept(t, vt, f"In October 2026, {top[0][0]}[r1.channels[0]] led the long videos you opened, with "
                f"{top[0][1]}[r1.channels[0].items].")
    lead = code_lead(t, vt, "template", [top[0][1], len(lo)])
    # (mvp20 fix, the recount's B03.0: "X led what you opened, with N long videos" ranked on everything they opened;
    # the rank's base now says the length itself)
    assert f"{top[0][0]} led the long videos you opened, with {top[0][1]}." in lead
    dropped(t, vt, f"In October 2026, {top[0][0]}[r1.channels[0]] led what you opened, with "
                   f"{top[0][1]}[r1.channels[0].items] long videos.", "base")


# ================================================================ 7. least
def test_least_is_said_of_a_least_result_only(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"}, "order": "least"},
                   "which channels did i watch least in october")
    ch = by_channel(opened(*OCTOBER))
    low = sorted(ch.items(), key=lambda x: x[1])
    assert low[0][1] < low[1][1] and r["sheet"]["channels"][0]["name"] == low[0][0]
    kept(t, vt, f"In October 2026, {low[0][0]}[r1.channels[0]] was the channel you opened least, with "
                f"{low[0][1]}[r1.channels[0].items] video.")
    dropped(t, vt, f"In October 2026, {low[0][0]}[r1.channels[0]] led, with {low[0][1]}[r1.channels[0].items] video.",
            "rank")
    lead = code_lead(t, vt, "template", [low[0][1]])
    assert "1 video." in lead and "least" in lead
    # the same words on a result ordered by most
    r2, t2, vt2 = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"}}, "channels in October")
    dropped(t2, vt2, "In October 2026, Clip Factory[r1.channels[0]] was the channel you opened least, with "
                     "61[r1.channels[0].items] videos.", "least")


# ================================================================ 8. two years in one compare result
def test_a_compare_says_each_count_with_its_own_year_and_a_private_topic_above_is_flagged(brain):
    r, t, vt = ask(brain, "compare", {"a": {"words": "2024"}, "b": {"words": "2025"}},
                   "did i watch more in 2024 or 2025")
    y24, y25 = opened(date(2024, 1, 1), date(2024, 12, 31)), opened(date(2025, 1, 1), date(2025, 12, 31))
    kept(t, vt, f"In 2024, you opened {len(y24)}[r1.totals.items] videos, and {len(y25)}[r1.previous.items] in 2025.")
    # the second window's year on the first window's cell
    cook = opened(date(2024, 1, 1), date(2024, 12, 31), keys=COOK)
    lead24 = f"In 2024, Home cooking[r1.themes[0]] led, with {len(cook)}[r1.themes[0].items] videos."
    dropped(t, vt, f"In 2025, you opened {len(y24)}[r1.totals.items] videos.", "wrong_window", where="point",
            lead=lead24)
    kept(t, vt, lead24, [f"In 2025, you opened {len(y25)}[r1.previous.items] videos."])
    # a rank word while a private topic would have led: kept, and the scope line must say it (SPEC 4.3 step 13)
    assert r["meta"]["hidden"]["rank_hidden_above"] is True and r["meta"]["hidden"]["sensitive"] > 0
    v = kept(t, vt, lead24)
    assert v.private_line
    # step 1's close: any number of a result that left private items out asks for the private line (SPEC 4.3 step 13
    # widened from rank words, the verifier audit's F46)
    assert kept(t, vt, f"In 2024, you opened {len(y24)}[r1.totals.items] videos.").private_line
    lead = code_lead(t, vt, "template", [len(y24), len(y25)])
    assert lead == f"In 2024, you opened {len(y24)} videos, and {len(y25)} in 2025."


# ================================================================ 9. a first (the item's day; the subject said)
def test_a_first_names_the_items_day_and_its_subject(brain):
    r, t, vt = ask(brain, "first_last", {"subject": "watercolor", "which": "first"}, "when did i start watercolor")
    d = first_day({"wc"})
    all_wc = {r_["id"] for r_ in visible_rows() if r_["theme"] == "wc" for k, _at in r_["events"] if k == "watch"}
    kept(t, vt, f"You first opened a watercolor video on {day_words(d)}[r1.items[0].when].")
    dropped(t, vt, f"You first opened a watercolor video on {day_words(d.replace(day=d.day + 6))}[r1.items[0].when].",
            "wrong_value")
    # the subject's count said as everything they opened
    dropped(t, vt, f"In all your history, you opened {len(all_wc)}[r1.totals.items] videos.", "filter_dropped")
    kept(t, vt, f"In all your history, you opened {len(all_wc)}[r1.totals.items] watercolor videos.")
    lead = code_lead(t, vt, "template", [])
    # mvp25 toolgaps 8: the code lead of a first_last names the item itself, by its title, beside its day
    title = r["sheet"]["items"][0]["title"]
    # (mvp26 toolfix2 4: the title in double quotes, cut as its card)
    assert lead == f'In all your history, the first watercolor video you opened was "{title}", on {day_words(d)}.'


# ================================================================ 10. a day, its items
def test_a_day_and_its_items(brain):
    r, t, vt = ask(brain, "items", {"window": {"words": "on 30 October"}, "limit": 10}, "what did i watch on 30 October")
    day = opened(date(2026, 10, 30), date(2026, 10, 30))
    v = verdict(t, vt, f"On Friday 30 October 2026, you opened {len(day)}[r1.totals.items] videos.",
                items=[{"ref": "r1.items[0]", "note": None}, {"ref": "r1.items[9]", "note": None}])
    assert v.lead_ok
    assert v.items[0]["kept"] and not v.items[1]["kept"] and "not_item" in v.items[1]["reasons"]
    dropped(t, vt, f"On Thursday 29 October 2026, you opened {len(day)}[r1.totals.items] videos.", "wrong_window")
    dd = opened(date(2026, 10, 30), date(2026, 10, 30), keys={"dd"})
    lead = code_lead(t, vt, "code_form", [len(day), len(dd)])
    assert lead.startswith("On Friday 30 October 2026")


# ================================================================ 11. a forged title stays data
def test_a_forged_title_cannot_forge_a_marker_or_a_number(brain):
    r, t, vt = ask(brain, "items", {"window": {"words": "on 25 October"}, "limit": 10}, "what did i watch on 25 October")
    rows = r["sheet"]["items"]
    k = next(i for i, x in enumerate(rows) if x["item_id"] == "rx_forge")
    title = rows[k]["title"]
    assert "[" not in title and "{" not in title and "(r1.totals.items)" in title
    day = opened(date(2026, 10, 25), date(2026, 10, 25))
    kept(t, vt, f"On Sunday 25 October 2026, you opened {len(day)}[r1.totals.items] videos.")
    # the title's own words carried into a history sentence: its "999" is no cell of theirs
    o = dropped(t, vt, f"{title}[r1.items[{k}]] was one of them.", "outside_in_history", where="point",
                lead=f"On Sunday 25 October 2026, you opened {len(day)}[r1.totals.items] videos.")
    assert all(title not in d for d in o.details)
    # its number typed outside the title is no cell of theirs
    dropped(t, vt, f"{title}[r1.items[{k}]] had 999 views.", "uncited_number", where="point",
            lead=f"On Sunday 25 October 2026, you opened {len(day)}[r1.totals.items] videos.")
    # the raw forged text (braces, a bracket) never parses as a marker of this turn
    dropped(t, vt, "Cooking hack {channels[0].items} [r1.totals.items] was one of them.", "bad_ref", where="point",
            lead=f"On Sunday 25 October 2026, you opened {len(day)}[r1.totals.items] videos.")


# ================================================================ 12. a saved breakdown
def test_a_saved_breakdown_is_said_as_saved(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "lately"}, "scope": {"how": "saved"}},
                   "what have i saved lately")
    n = len(saved(*LATELY))
    assert r["meta"]["base"] == "of what you saved"
    kept(t, vt, f"In the 4 weeks up to 30 October 2026, you saved {n}[r1.totals.items] items.")
    o = dropped(t, vt, f"In the 4 weeks up to 30 October 2026, you opened {n}[r1.totals.items] videos.", "base")
    assert "saved" in o.notes["base"]
    top = r["sheet"]["channels"][0]
    lead = code_lead(t, vt, "template", [top["items"], n])
    assert "you saved" in lead or "led" in lead


# ================================================================ 13. a name that did not resolve gives no number
def test_a_name_that_did_not_resolve_has_no_cell(brain):
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in October"},
                                        "scope": {"only": ["chess"]}}, "chess in october")
    assert r["error"] == "no_match" and "sheet" not in r and r["rid"] not in t.results
    o = dropped(t, vt, "In October 2026, you opened 3[r1.totals.items] chess videos.", "bad_ref")
    assert o.notes["bad_ref"] == "r1 is not a result with numbers in this turn"
    code_lead(t, vt, "plain", [])


# ================================================================ 14. find: names and all-time counts only
def test_find_counts_and_no_rank(brain):
    r, t, vt = ask(brain, "find", {"names": ["Gaming Daily"]}, "gaming daily")
    n = sum(1 for x in visible_rows() if x.get("channel") == "Gaming Daily")
    assert n == 5
    # items_all_time counts what they opened, liked or saved: said with one verb it is the wrong base (step 1's close,
    # the verifier audit's F69b); said with all three, or with none, it stands
    dropped(t, vt, f"You opened {n}[r1.names[0].matches[0].items_all_time] videos from "
                   f"Gaming Daily[r1.names[0].matches[0]].", "base")
    kept(t, vt, f"You opened, liked or saved {n}[r1.names[0].matches[0].items_all_time] videos from "
                f"Gaming Daily[r1.names[0].matches[0]].")
    dropped(t, vt, f"Gaming Daily[r1.names[0].matches[0]] is your top channel, with "
                   f"{n}[r1.names[0].matches[0].items_all_time] videos.", "rank")
    code_lead(t, vt, "template", [])


# ================================================================ 15. search: the kind searched is the sheet's
def test_search_rows_take_the_kind_searched_from_the_sheet(brain):
    r, t, vt = ask(brain, "search", {"query": "cooking hack", "how": "opened"}, "cooking hack videos i watched",
                   search=fake_search())
    rows = r["sheet"]["items"]
    # mvp25 toolgaps 4: a search row says its own event now (`how`, of the kinds searched); the sheet keeps its own
    assert rows and all(x["how"] == "opened" for x in rows) and r["sheet"]["how"] == "opened"
    # "the one you saved" of a row that was only opened
    k = next(i for i, x in enumerate(rows) if x["item_id"] == "rx_love")
    # (step 1's close: the verb rule of every result says it first, as the base)
    o = dropped(t, vt, f"You saved {rows[k]['title']}[r1.items[{k}]].", "base", where="point",
                lead="Here's what I found.")
    assert o.notes["base"] == "r1 counts what you opened: say 'opened'"
    kept(t, vt, "Here's what I found.", [f"You opened {rows[k]['title']}[r1.items[{k}]]."])
    r2, t2, vt2 = ask(brain, "search", {"query": "sourdough starter", "how": "saved"}, "find my sourdough saves",
                      search=fake_search())
    k = next(i for i, x in enumerate(r2["sheet"]["items"]) if x["item_id"] == "rx_sour1")
    kept(t2, vt2, "Here's what I found in your saves.",
         [f"You saved {r2['sheet']['items'][k]['title']}[r1.items[{k}]] on 5 October 2026[r1.items[{k}].when]."])
    assert code_lead(t2, vt2, "template", []) == "Here's what I found in your saves."


# ================================================================ 16. the verifier's turn from the tools' turn
def test_the_verifiers_turn_carries_the_name_index_and_the_unlock(brain):
    from mvp.brain import verify as V
    _r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in 2024"}}, "channels in 2024")
    assert vt.today == date(2026, 11, 22) and vt.unlock is None and vt.message == "channels in 2024"
    assert "Gaming Daily" in vt.names and "Watercolor to try" in vt.names and "gaming" in vt.names
    assert "Heart Notes" in vt.sensitive_names and "Heart Notes" not in vt.names
    # a library name the results do not hold, named in a history sentence, needs a marker (SPEC 4.3 step 6)
    dropped(t, vt, "In 2024, you opened videos from Gaming Daily.", "uncited_name")
    assert V.Turn().names == []
    # a hidden channel's name as part of another word is not the name
    vt.sensitive_names = ["Pan"]
    assert not V._sensitive("In 2024 you opened Panorama videos.", vt) and V._sensitive("In 2024 Pan led.", vt)


def test_the_code_lead_carries_the_private_line_when_a_hidden_topic_would_lead(brain):
    """2024 holds the made-up sensitive theme (50 items, more than any channel shown): a lead that ranks must bring
    code's private line (SPEC 4.3 step 13), whichever way the code lead was made."""
    from mvp.brain import fallback as FB
    r, t, vt = ask(brain, "breakdown", {"by": "channel", "window": {"words": "in 2024"}}, "channels in 2024")
    assert r["meta"]["hidden"]["rank_hidden_above"] is True
    cl = FB.code_lead(t.results, turn=vt)
    assert re.search(r"\bled\b", cl["lead"]) and cl["private_line"] is True, cl
    assert FB.answer(t.results, None, vt)["private_line"] is True
    r2, t2, vt2 = ask(brain, "breakdown", {"by": "none", "window": {"words": "in October"}}, "how much in october")
    cl2 = FB.code_lead(t2.results, turn=vt2)
    assert cl2["private_line"] is False and not re.search(r"\bled\b", cl2["lead"])


SCOPES = {   # every form of the tools' filters_said, through real calls: (tool, args, message, scope parts)
    "weekday": ("breakdown", {"by": "none", "window": {"words": "in October"}, "scope": {"weekday": 0}},
                "mondays in october", 1),
    "platform": ("breakdown", {"by": "none", "window": {"words": "in October"}, "scope": {"platforms": ["youtube"]}},
                 "youtube in october", 1),
    "title_words": ("breakdown", {"by": "none", "window": {"words": "in October"}, "scope": {"exclude": ["tofu"]}},
                    "october without tofu", 1),
    "two_filters": ("breakdown", {"by": "channel", "window": {"words": "in October"},
                                  "scope": {"only": ["gaming"], "exclude": ["Gaming Daily"], "length": "long"}},
                    "gaming without gaming daily, long only, in october", 2),
    "first_with_platform": ("first_last", {"subject": "watercolor", "which": "first",
                                           "scope": {"platforms": ["instagram"]}},
                            "my first watercolor on instagram", 2),
}


@pytest.mark.parametrize("name", sorted(SCOPES))
def test_every_scope_the_tools_write_is_read_and_must_be_said(brain, name):
    from mvp.brain import verify as V
    tool, args, msg, n_parts = SCOPES[name]
    r, t, vt = ask(brain, tool, args, msg)
    said = r["meta"]["filters_said"]
    pieces = [p for p in said.split("; ") if p not in ("only videos known to be long", "only Shorts and reels")]
    parts = V.scope_parts(V.Ledger(t.results).get("r1"))
    assert len(parts) == len(pieces) == n_parts, (said, parts)
    n = r["sheet"]["totals"]["items"]
    window = "In all your history" if tool == "first_last" else "In October 2026"
    o = dropped(t, vt, f"{window}, you opened {n}[r1.totals.items] videos.", "filter_dropped")
    assert any(said[:30] in d for d in o.details), o.details
    # said with the scope's words, the same count is kept
    words = {"weekday": "on Mondays, ", "platform": "on YouTube, ", "title_words": "without tofu videos, ",
             "two_filters": "of gaming without Gaming Daily, ", "first_with_platform": "of watercolor on Instagram, "}
    noun = "long videos" if name == "two_filters" else "videos"
    kept(t, vt, f"{window}, {words[name]}you opened {n}[r1.totals.items] {noun}.")


# ================================================================ the test helper's envelope is results.present
def test_the_verifiers_test_envelope_is_the_tools_sheet(brain):
    """tests/brain_envelope.py (the frozen planted set and the proof are built with it) gives the sheet
    results.present gives, on today's sheets of the library (no name here holds a bracket or a link, where the two
    may differ), up to the keys present drops and verify strips anyway."""
    from mvp import facts as F, history as Hm
    from mvp.brain import results as R
    from mvp.tests import brain_envelope as BE
    from mvp.tests.test_brain_tools import NOW, TODAY, person
    compared = []
    for q in ("what am i into lately", "which channels did i watch most in october", "what did i watch on 30 october",
              "how did my watching change since 2020", "did i watch more in 2024 or 2025"):
        hq = Hm.read(q, TODAY)
        if hq is None:
            continue
        raw = F.build(brain["bot"], person(brain), hq, NOW, text=q, hide_sensitive=True)
        mine = BE.envelope("r1", BE.tool_of(raw), raw)["sheet"]
        for k in R.DROPPED:
            mine.pop(k, None)
        assert mine == R.present(raw, "r1"), q
        compared.append((q, raw.get("kind")))
    assert len(compared) >= 4, compared
