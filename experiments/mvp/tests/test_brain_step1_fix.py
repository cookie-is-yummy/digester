"""Step 1's close (design/brain_v1/SPEC.md 12.2 step 1): what two independent audits of the tools and the verifier found,
each class reproduced first and fixed by construction. Offline: no model call, no network. The library is the made-up
one of tests/brain_library.py (fixtures of test_brain_tools); every title, channel and theme is made up.

Each verifier class has the auditor's sentence, a variant of the same class, and a true twin that is kept. The counts
behind each truth are from the made-up rows (test_brain_tools' recount helpers, which share nothing with facts.py)."""
import json
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


def test_a_new_list_facts_filled_is_never_shown_empty(brain):
    # the tools audit's B24: 2025's new channel (Wet Paper, first opened 10 January 2025) was shown as no new channel
    first_wp = min(local(at) for r in visible_rows() if r.get("channel") == "Wet Paper" and r["platform"] == "youtube"
                   for k, at in r["events"] if k == "watch")
    assert first_wp.year == 2025
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W("in 2025"), "top": 1}, "the top channel in 2025")
    new = env_["sheet"].get("new") or {}
    assert new.get("channels") != [] and ("channels" not in new or any(c["name"] == "Wet Paper"
                                                                        for c in new["channels"]))


@pytest.mark.parametrize("word", ["texting", "zzqx"])
def test_a_title_word_scope_never_says_how_many_private_items_it_left_out(brain, word):
    # the tools audit's L14: 17 private items under "texting", 0 under "zzqx": private titles probed word by word
    env_, _t = call(brain, "breakdown", {"by": "none", "window": {"preset": "all"},
                                         "scope": {"only": [f"words:{word}"]}}, "how about these words")
    h = env_["meta"]["hidden"]
    assert (h["sensitive"], h["rank_hidden_above"]) == (1, True)


def test_rows_of_every_ranking_are_in_meta(brain):
    env_, _t = call(brain, "breakdown", {"by": "area", "window": {"preset": "lately"}}, "lately")
    ro = env_["meta"]["rows_of"]
    assert ro["channels"] == len(by_channel(opened(*LATELY))) and ro["channels"] > len(env_["sheet"]["channels"])


# ================================================================ the verifier (the verifier audit)
# the audit's ledgers: one turn each, real tool calls on the made-up library (the audit's ledgers.py)
LEDGERS = {
    "ch": ("which channels did i watch most in october",
           [("breakdown", {"by": "channel", "window": W("in october")})]),
    "area": ("what am i most into lately", [("breakdown", {"by": "area", "window": {"preset": "lately"}})]),
    "fwc": ("when did i first watch watercolor", [("first_last", {"subject": "watercolor", "which": "first"})]),
    "lmc": ("when did i last watch minecraft", [("first_last", {"subject": "minecraft", "which": "last"})]),
    "items": ("what did i watch most in october", [("items", {"window": W("in october")})]),
    "find": ("watercolor and gaming and pan theory", [("find", {"names": ["watercolor", "gaming", "Pan Theory"]})]),
    "art": ("only art lately by theme",
            [("breakdown", {"by": "theme", "window": {"preset": "lately"}, "scope": {"only": ["art"]}})]),
    "y2024": ("channels in 2024", [("breakdown", {"by": "channel", "window": W("in 2024")})]),
    "tly": ("how has my watching changed over the years", [("timeline", {"unit": "year", "window": {"preset": "all"}})]),
    "fri": ("channels on fridays in october",
            [("breakdown", {"by": "channel", "window": W("in october"), "scope": {"weekday": 4}})]),
    "insta": ("instagram in october", [("breakdown", {"by": "channel", "window": W("in october"),
                                                      "scope": {"platforms": ["instagram"], "how": "any"}})]),
    "search": ("find my sourdough saves", [("search", {"query": "sourdough starter", "how": "saved"})]),
    "lsr": ("when did i last watch speedrun videos", [("first_last", {"subject": "speedrun", "which": "last"})]),
    "lnp": ("when did i last watch number puzzles", [("first_last", {"subject": "number puzzles", "which": "last"})]),
    "two2": ("channels in october, and how has it changed over the years",
             [("breakdown", {"by": "channel", "window": W("in october")}),
              ("timeline", {"unit": "year", "window": {"preset": "all"}})]),
    "reopen": ("what did i watch most in october", [("items", {"window": W("in october")})]),
}


def ledger(e, name):
    from mvp.brain import tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine
    msg, calls = LEDGERS[name]
    t = TL.Turn(e["bot"], person(e), NOW, message=msg, search=FakeEngine())
    envs = [TL.call(t, tool, args) for tool, args in calls]
    if name == "reopen":   # SYNTHETIC: the library has no re-opens, so the first row is patched to 3 openings
        envs[0]["sheet"]["items"][0]["times_opened"] = 3
    return envs, V.Turn.of(t)


def verdict(e, name, sentence, where="point"):
    from mvp.brain import verify as V
    envs, vt = ledger(e, name)
    form = {"lead": sentence} if where == "lead" else {"lead": "", "points": [sentence]}
    v = V.check_answer(form, envs, vt)
    o = [x for x in v.outcomes if x.where == where]
    return bool(o) and all(x.kept for x in o), sorted({r for x in o for r in x.reasons}), v


def dropped(e, name, sentence, reasons=None, where="point"):
    k, why, _v = verdict(e, name, sentence, where)
    assert not k, sentence
    if reasons:
        assert set(why) & set(reasons), (sentence, why)


def kept(e, name, sentence, where="point", private=None):
    k, why, v = verdict(e, name, sentence, where)
    assert k, (sentence, why, [o.details for o in v.outcomes])
    if private is not None:
        assert v.private_line is private, sentence


# ---------------------------------------------------------------- 1. a scope satisfied by the scoped row's own name
def test_the_scoped_rows_own_name_is_not_the_scope_said(brain):
    # all visible history by theme: Minecraft builds 163, Watercolor 95, Digital drawing 92, Speedruns 90 (4th)
    dropped(brain, "lsr", "In all your history, Speedruns[r1.themes[0]] led, with 90[r1.themes[0].items] videos.",
            ["filter_dropped"])
    dropped(brain, "lnp", "Number puzzles[r1.themes[0]] was your top theme, with 60[r1.themes[0].items] videos.",
            ["filter_dropped"])
    lately = opened(*LATELY)
    art = {i for i in lately if ROWS[i]["theme"] in ("wc", "dd")}
    assert (len(art), len(lately)) == (32, 130)   # art and design lately is 25% of what they opened, not 100%
    dropped(brain, "art", "Lately, art and design[r1.areas[0]] led what you opened, with 32[r1.areas[0].items] videos.",
            ["filter_dropped"])
    dropped(brain, "art", "Art and design[r1.areas[0]] was 100%[r1.areas[0].share] of what you opened lately.",
            ["filter_dropped"])
    dropped(brain, "lsr", "Speedruns[r1.themes[0]] was your biggest theme, with 90[r1.themes[0].items] videos.",
            ["filter_dropped"])   # a variant of our own
    dd = {i for i in art if ROWS[i]["theme"] == "dd"}
    kept(brain, "art", f"Of the art and design videos you opened lately, Digital drawing[r1.themes[0]] made "
                       f"{len(dd)}[r1.themes[0].items].")
    kept(brain, "lsr", "In all your history, the last speedrun video you opened was on 1 May 2023[r1.items[0].when].",
         where="lead")


# ---------------------------------------------------------------- 2. numbers of a result that left private items out
def test_a_result_with_private_items_left_out_asks_for_the_private_line(brain):
    y24 = opened(date(2024, 1, 1), date(2024, 12, 31))
    assert len(y24) == 8 and len(opened(date(2024, 1, 1), date(2024, 12, 31), unlock_sensitive=True)) == 58
    dropped(brain, "y2024", "In 2024, 100%[r1.channels[0].share] of what you opened was Pan Theory[r1.channels[0]].",
            ["private_total"])
    dropped(brain, "y2024", "In 2024, everything you opened came from Pan Theory[r1.channels[0]], "
                            "8[r1.channels[0].items] videos.", ["private_total"])
    kept(brain, "y2024", "In 2024 you opened 8[r1.totals.items] videos.", where="lead", private=True)
    assert len(opened(None, None)) == 723 and len(opened(None, None, unlock_sensitive=True)) == 773
    kept(brain, "tly", "In all your history you opened 723[r1.totals.items] videos.", where="lead", private=True)
    kept(brain, "ch", f"In October 2026, you opened {len(opened(*OCTOBER))}[r1.totals.items] videos.", where="lead",
         private=False)   # nothing private in October: no line


# ---------------------------------------------------------------- 3. a row placed in the wrong group
@pytest.mark.parametrize("s", [
    "Gaming Daily[r1.channels[4]], part of Minecraft builds[r1.themes[3]], made 5[r1.channels[4].items] videos.",
    "Brick Realm[r1.channels[3]] (Gaming clips[r1.themes[0]]) made 6[r1.channels[3].items] videos.",
    "Inside Digital drawing[r1.themes[2]], Wet Paper[r1.channels[7]] made 1[r1.channels[7].items] video.",
    "Pixel Pencil[r1.channels[2]] (food and cooking[r1.areas[2]]) made 29[r1.channels[2].items] videos.",
    "Limit Lane[r1.channels[5]] (gaming[r1.areas[0]]) made 4[r1.channels[5].items] videos.",
    "Clip Factory[r1.channels[0]] (Home cooking[r1.themes[1]]) made 61[r1.channels[0].items] videos.",   # variant
])
def test_a_row_in_a_group_its_own_row_does_not_name_is_dropped(brain, s):
    dropped(brain, "ch", s, ["wrong_group"])


def test_a_row_in_its_own_group_is_kept(brain):
    envs, _vt = ledger(brain, "ch")
    sh = envs[0]["sheet"]
    assert sh["channels"][0]["theme"] == sh["themes"][0]["name"] == "Gaming clips"
    kept(brain, "ch", "Clip Factory[r1.channels[0]] (Gaming clips[r1.themes[0]]) made 61[r1.channels[0].items] videos.")


# ---------------------------------------------------------------- 4. ordinals and ties
def test_an_ordinal_is_the_rows_place_and_no_tie(brain):
    dropped(brain, "area", "Watercolor painting[r1.themes[3]] came fourth lately, with 5[r1.themes[3].items] videos.",
            ["tie"])
    fri = {i for i in opened(*OCTOBER) if any(k == "watch" and local(at).weekday() == 4 for k, at in ROWS[i]["events"])}
    bc = by_channel(fri)
    assert bc["Pan Theory"] == bc["Pixel Pencil"] == 6
    dropped(brain, "fri", "On Fridays, Pan Theory[r1.channels[1]] came second, with 6[r1.channels[1].items] videos.",
            ["tie"])
    dropped(brain, "ch", "Pixel Pencil[r1.channels[2]] came second in October, with 29[r1.channels[2].items] videos.",
            ["rank"])   # variant: it is third
    kept(brain, "ch", "Pan Theory[r1.channels[1]] came second in October, with 32[r1.channels[1].items] videos.")


def test_most_watched_on_an_item_list_where_every_row_was_opened_once_is_a_tie(brain):
    dropped(brain, "items", "Your most-watched video in October was Cooking soup on the 30th[r1.items[0]].", ["tie"])
    dropped(brain, "items", "The video you opened most was Cooking soup on the 30th[r1.items[0]], "
                            "1[r1.items[0].times_opened] time.", ["tie"])


# ---------------------------------------------------------------- 5. a calc said of another row
def test_a_calc_is_said_of_its_own_two_rows(brain):
    dropped(brain, "ch", "Clip Factory[r1.channels[0]] made 32 more[=diff(r1.channels[0].items, "
                         "r1.channels[2].items)] videos than Pan Theory[r1.channels[1]].", ["calc"])
    dropped(brain, "ch", "Clip Factory[r1.channels[0]] made 32 more[=diff(r1.channels[0].items, "
                         "r1.channels[2].items)] videos than the next channel.", ["calc"])   # variant: unnamed
    kept(brain, "ch", "Clip Factory[r1.channels[0]] made 29 more[=diff(r1.channels[0].items, r1.channels[1].items)] "
                      "videos than Pan Theory[r1.channels[1]].")


# ---------------------------------------------------------------- 6. a month said of a 4-week result
def test_a_month_said_of_four_weeks_is_the_wrong_window(brain):
    assert len(opened(*LATELY)) == 130 and len(opened(*OCTOBER)) == 142
    dropped(brain, "area", "In October, gaming[r1.areas[0]] was 49%[r1.areas[0].share] of what you opened.",
            ["wrong_window"])
    dropped(brain, "area", "In October, Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.",
            ["wrong_window"])
    dropped(brain, "area", "Since October, Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.",
            ["wrong_window"])   # variant
    kept(brain, "area", "Lately, Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.")
    kept(brain, "ch", "In October, Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.")


# ---------------------------------------------------------------- 7. a claim in a clause with no marker
def test_a_clause_with_no_marker_claims_nothing(brain):
    dropped(brain, "two2", "Pixel Pencil[r1.channels[2]] made 29[r1.channels[2].items] videos in October 2026, its "
                           "busiest month.", ["uncited_claim"])
    dropped(brain, "ch", "Clip Factory[r1.channels[0]] led October with 61[r1.channels[0].items] videos, as it did "
                         "the month before.", ["uncited_claim"])
    dropped(brain, "ch", "Pan Theory[r1.channels[1]] made 32[r1.channels[1].items] videos, its best month yet.",
            ["uncited_claim"])   # variant
    kept(brain, "ch", "Pixel Pencil[r1.channels[2]] made 29[r1.channels[2].items] videos in October 2026, and Pan "
                      "Theory[r1.channels[1]] made 32[r1.channels[1].items].")


# ---------------------------------------------------------------- 8. outside knowledge with no comma
@pytest.mark.parametrize("s", [
    "Clip Factory[r1.channels[0]] posts a new Short every day, and you opened 61[r1.channels[0].items] of them.",
    "Clip Factory[r1.channels[0]] is a huge channel, and you opened 61[r1.channels[0].items] of its videos.",
    "Brick Realm[r1.channels[3]] is the channel you have followed longest, with 6[r1.channels[3].items] videos in "
    "October.",
    "Pixel Pencil[r1.channels[2]] uploads drawing lessons every week, and you opened 29[r1.channels[2].items] of "
    "them.",   # variant
])
def test_what_a_channel_is_or_does_is_outside_knowledge(brain, s):
    dropped(brain, "ch", s, ["outside_in_history"])


def test_a_channel_said_by_what_they_opened_is_kept(brain):
    kept(brain, "ch", "Clip Factory[r1.channels[0]] led October, with 61[r1.channels[0].items] videos.")


# ---------------------------------------------------------------- 9. first and last
def test_a_first_or_a_last_is_the_date_of_the_results_first_item(brain):
    dropped(brain, "fwc", "You first watched a watercolor video on 12 October 2026[r1.channels[1].first_watched].",
            ["first_last"])
    dropped(brain, "lmc", "You last watched a minecraft video on 30 October 2026.", ["uncited_claim"])
    dropped(brain, "lmc", "Your last minecraft video was on 17 October 2026.", ["uncited_claim"])   # variant
    first_wc = min(local(at) for r in visible_rows() if r["theme"] == "wc" for k, at in r["events"] if k == "watch")
    assert first_wc == date(2025, 1, 10)
    kept(brain, "fwc", "In all your history, you first opened a watercolor video on 10 January 2025[r1.items[0].when].",
         where="lead")
    last_mc = max(local(at) for r in visible_rows() if r["theme"] == "mc" for k, at in r["events"] if k == "watch")
    assert last_mc == date(2026, 10, 20)
    kept(brain, "lmc", "The last Minecraft video you watched was on 20 October 2026[r1.items[0].when].", where="lead")


# ---------------------------------------------------------------- 10. the base said with the wrong verb
def test_the_verbs_said_are_the_bases(brain):
    assert len(opened(None, None, keys={"wc"})) == 95
    dropped(brain, "find", "You've watched 98[r1.names[0].matches[0].items_all_time] videos of Watercolor "
                           "painting[r1.names[0].matches[0]].", ["base"])
    dropped(brain, "insta", "Watercolor painting[r1.themes[0]] made 57%[r1.themes[0].share] of what you opened on "
                            "Instagram.", ["base"])
    dropped(brain, "find", "You saved 98[r1.names[0].matches[0].items_all_time] watercolor things.", ["base"])  # variant
    kept(brain, "find", "You opened, liked or saved 98[r1.names[0].matches[0].items_all_time] videos of Watercolor "
                        "painting[r1.names[0].matches[0]].")


def test_a_saved_row_of_a_search_is_never_said_watched(brain):
    envs, _vt = ledger(brain, "search")
    row = envs[0]["sheet"]["items"][0]
    day = date.fromisoformat(row["when"][:10])
    when = f"{day.day} {day.strftime('%B')} {day.year}"
    dropped(brain, "search", f"You watched {row['title']}[r1.items[0]] on {when}[r1.items[0].when].", ["base"])
    kept(brain, "search", f"You saved {row['title']}[r1.items[0]] on {when}[r1.items[0].when].")


# ---------------------------------------------------------------- 11. a cell said under another measure
def test_a_cell_is_said_under_its_own_measure(brain):
    dropped(brain, "ch", "Clip Factory[r1.channels[0]] made 30[r1.channels[0].days] videos.", ["wrong_measure"])
    dropped(brain, "ch", "Pan Theory[r1.channels[1]] made 26[r1.channels[1].days] clips.", ["wrong_measure"])  # variant
    o = sorted(ROWS[i]["length"] for i in opened(*OCTOBER) if known_long(ROWS[i]))
    assert (o[len(o) // 2 - 1] + o[len(o) // 2]) / 2 / 60 == 10.0 and round(sum(o) / len(o) / 60, 1) == 16.0
    dropped(brain, "ch", "Your long videos ran 10 minutes[r1.totals.long_median_min] on average.", ["wrong_measure"])
    kept(brain, "ch", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos on 30[r1.channels[0].days] "
                      "days.")


def test_reopenings_are_not_distinct_items_synthetic(brain):
    # SYNTHETIC: the library has no re-opens; items[0].times_opened is patched to 3
    dropped(brain, "reopen", "Cooking soup on the 30th[r1.items[0]] was 3[r1.items[0].times_opened] of the clips you "
                             "opened that day.", ["wrong_measure"])
    dropped(brain, "reopen", "You opened 3[r1.items[0].times_opened] different cooking clips on 30 October 2026.",
            ["wrong_measure"])


# ---------------------------------------------------------------- 12. a count of a list the tools cut
def test_a_count_of_a_cut_list_is_the_top_n_only(brain):
    assert len(by_channel(opened(*LATELY))) == 8
    dropped(brain, "area", "Lately you opened videos from 7[r1.channels.count] channels.", ["wrong_value"])
    dropped(brain, "area", "You opened 7[r1.channels.count] different channels lately.", ["wrong_value"])  # variant
    kept(brain, "area", "Lately, your top 7[r1.channels.count] channels were led by Clip Factory[r1.channels[0]].")


# ---------------------------------------------------------------- 13. a sentence the checks cannot read
@pytest.mark.parametrize("s", [
    "Clip Factory[r1.channels[0]] hizo 61[r1.channels[0].items] de los videos que abriste en septiembre.",
    "Clip Factory[r1.channels[0]] hizo 61[r1.channels[0].items] videos, la mayoría de lo que abriste.",
    "Pan Theory[r1.channels[1]] hizo 32[r1.channels[1].items] videos, casi tantos como Clip Factory[r1.channels[0]].",
])
def test_a_sentence_not_in_the_results_language_is_refused(brain, s):
    dropped(brain, "ch", s, ["language"])


# ---------------------------------------------------------------- 14. a close fit said as exactly what was asked
def test_a_close_fit_is_never_exactly_what_was_asked(brain):
    envs, _vt = ledger(brain, "search")
    rows = envs[0]["sheet"]["items"]
    k = next((i for i, r in enumerate(rows) if r["fit"] != "clear"), None)
    assert k is not None
    dropped(brain, "search", f"{rows[k]['title']}[r1.items[{k}]] is exactly what you asked for.", ["weak_fit"])


# ================================================================ the audit's sentences in the planted set
MVP = os.path.dirname(HERE)
PLANTED = os.path.join(MVP, "eval", "brain_planted.json")


def _audit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("brain_audit_cases", os.path.join(MVP, "eval", "brain_audit_cases.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _audit_ledgers(e):
    """{name: (envelopes, turn dict)} of the audit's ledgers from today's tools (took_ms zeroed: a timing)."""
    from mvp.brain import tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine
    A = _audit()
    out = {}
    for name, (msg, calls) in A.LEDGERS.items():
        t = TL.Turn(e["bot"], person(e), NOW, message=msg, search=FakeEngine())
        envs = [TL.call(t, tool, args) for tool, args in calls]
        for env_ in envs:
            env_["took_ms"] = 0
        if name in A.PATCH:   # SYNTHETIC
            lst, i, k, v = A.PATCH[name]
            envs[0]["sheet"][lst][i][k] = v
        vt = V.Turn.of(t)
        out[name] = (json.loads(json.dumps(envs, default=str)),
                     {"message": msg, "unlock": vt.unlock, "today": vt.today.isoformat(), "names": vt.names,
                      "sensitive_names": vt.sensitive_names})
    return out


def test_the_audit_ledgers_frozen_in_the_planted_set_are_todays_tools(brain):
    got = _audit_ledgers(brain)
    with open(PLANTED, encoding="utf-8") as f:
        data = json.load(f)
    if os.environ.get("MVP_FREEZE_AUDIT") == "1":   # rewrite them (then run eval/build_brain_planted.py)
        for name, (envs, t) in got.items():
            data["ledgers"]["audit_" + name] = envs
            data.setdefault("audit_turns", {})[name] = t
        with open(PLANTED, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
    for name, (envs, t) in got.items():
        assert data["ledgers"]["audit_" + name] == envs, name
        assert data["audit_turns"][name] == t, name


def test_every_false_sentence_of_the_audit_is_dropped_and_its_true_ones_counted():
    from mvp.brain import planted as P
    s = P.score()
    a, t = s["by_source"]["audit"], s["by_source"]["audit_true"]
    assert a["false"] == 137 and a["false_dropped"] == 137          # 133 false + 4 synthetic re-opens, all handled
    assert t["true"] == 61 and t["true_kept"] >= 42                  # the audit's true sentences: 42 of 61 kept
    assert s["false_dropped"] == s["false"] and s["true_kept"] / s["true"] >= 0.97


# ================================================================ the code lead (the verifier audit's code leads)
def code_lead(e, name=None, msg=None, calls=None):
    from mvp.brain import fallback as FB, tools as TL, verify as V
    if calls is None:
        envs, vt = ledger(e, name)
    else:
        t = TL.Turn(e["bot"], person(e), NOW, message=msg)
        envs, vt = [TL.call(t, tool, args) for tool, args in calls], V.Turn.of(t)
    return FB.code_lead(envs, None, vt)


def test_the_code_lead_of_a_last_says_its_day_never_a_rank(brain):
    for name, day in (("lsr", "1 May 2023"), ("lnp", "22 August 2023"), ("lmc", "20 October 2026")):
        lead = code_lead(brain, name)
        assert lead["how"] == "template" and day in lead["lead"] and " led" not in lead["lead"], lead


def test_the_code_lead_of_a_changes_result_by_month_is_no_every_year_line(brain):
    this_year = opened(date(2026, 1, 1), date(2026, 10, 30))
    art = sum(1 for i in this_year if ROWS[i]["theme"] in ("wc", "dd"))
    gaming = sum(1 for i in this_year if ROWS[i]["theme"] in ("mc", "sr", "cl"))
    assert art > gaming   # art and design led this year, not gaming
    lead = code_lead(brain, msg="what changed this year",
                     calls=[("changes", {"level": "area", "window": {"preset": "this_year"}})])
    assert "every year" not in lead["lead"] and lead["how"] == "template"


def test_the_code_lead_of_all_history_asks_for_the_private_line(brain):
    lead = code_lead(brain, "tly")
    assert "723" in lead["lead"] and lead["private_line"] is True
