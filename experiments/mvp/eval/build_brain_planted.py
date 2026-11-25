"""Builds eval/brain_planted.json (SPEC 4.8): the verifier's planted set. Made-up data only.

    python3 eval/build_brain_planted.py        (from experiments/mvp; no model call)

Sources: (1) six results of the round 12 test library (tests/r12_library.py through facts.build, as
tests/test_round12_d.py builds it). They are read back from the brain_planted.json in place, and
tests/test_brain_verify.py checks they are still what facts.build gives today; (2) hand-made results in the same
names (a result ordered by least, ties, a hidden sensitive row, SPEC 4.7's worked example and a September result,
a search and an item list); (3) the insight_v5 sentences of eval/insight_cases.json in marker form
(eval/convert_insight_cases.py). Each new case is one class: the steps of SPEC 4.3 and the sixth pass's hand-check
classes; most false ones are a one-change twin of a kept true one.
"""
import copy
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.brain_envelope import envelope, items_envelope, tool_of  # noqa: E402

PATH = os.path.join(HERE, "brain_planted.json")
_spec = importlib.util.spec_from_file_location("convert_insight_cases", os.path.join(HERE, "convert_insight_cases.py"))
CONV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CONV)

R12 = {"lately": "what have i been watching the most lately",
       "oct_channels": "which channels did i watch the most in october",
       "lately_long": "what have i been watching the most lately without shorts",
       "years": "how has what i watch changed over the years",
       "first_wc": "when did i first watch watercolor",
       "oct_count": "how many videos did i watch in october"}
with open(PATH, encoding="utf-8") as _f:
    _old_all = json.load(_f)
_old = _old_all["ledgers"]
S = {q: copy.deepcopy(_old[k][0]["sheet"]) for k, q in R12.items()}


def env(rid, sheet, **meta):
    return envelope(rid, tool_of(sheet), sheet, shown=False, **meta)


L = {}
L["lately"] = [env("r1", S["what have i been watching the most lately"])]
L["oct_channels"] = [env("r1", S["which channels did i watch the most in october"])]
L["lately_long"] = [env("r1", S["what have i been watching the most lately without shorts"])]
L["years"] = [env("r1", S["how has what i watch changed over the years"])]
L["first_wc"] = [env("r1", S["when did i first watch watercolor"])]
L["oct_count"] = [env("r1", S["how many videos did i watch in october"])]

# least: the October channels ordered by least, the channel with the tie left out
ch = copy.deepcopy(S["which channels did i watch the most in october"])
rows = [c for c in ch["channels"] if c["name"] != "@wetpaper.ig"][::-1]
ch["channels"] = rows
L["least"] = [env("r1", ch, order="least", complete=True)]
ch2 = copy.deepcopy(S["which channels did i watch the most in october"])
ch2["channels"] = ch2["channels"][::-1]   # @wetpaper.ig 4, Limit Lane 4: a tie at the bottom
ch2["channels"][0]["name"] = "Paper Moon"   # a made-up name, so no handle trips the link rule
L["least_tie"] = [env("r1", ch2, order="least", complete=True)]
inc = copy.deepcopy(ch)
L["least_incomplete"] = [env("r1", inc, order="least", complete=False)]
# a tie at the top
t = copy.deepcopy(S["which channels did i watch the most in october"])
t["channels"][1]["items"] = t["channels"][0]["items"]
L["top_tie"] = [env("r1", t)]
# a hidden sensitive row would have ranked first
L["hidden"] = [env("r1", S["what have i been watching the most lately"],
                   hidden={"sensitive": 9, "friends": 0, "rank_hidden_above": True})]

# the worked example of SPEC 4.7 (made up), and a second result for September
W47 = {
    "question": "what am i most into right now based on what i watch", "kind": "top", "lang": "en",
    "filters": {"topic": None, "without_shorts": False, "platform": None, "channel": None, "how": "watched"},
    "window": {"words": "the 4 weeks to 30 Oct 2026, where your YouTube export ends", "start": "2026-10-03",
               "end": "2026-10-30", "clipped": True},
    "totals": {"items": 180, "days_active": 28, "shorts": 61, "long": 110, "shorts_share": 0.3389},
    "previous": {"items": 120, "days_active": 27, "shorts": 5, "long": 110, "shorts_share": 0.0417,
                 "words": "the 4 weeks before (5 September to 2 October 2026)"},
    "areas": [
        {"name": "gaming", "items": 64, "share": 0.356, "previous_share": 0.2, "change_vs_previous": 0.156,
         "themes": [{"name": "Gaming clips", "share": 0.339}]},
        {"name": "art and design", "items": 52, "share": 0.289, "previous_share": 0.333,
         "change_vs_previous": -0.044, "themes": [{"name": "Digital drawing", "share": 0.2}]},
        {"name": "food and cooking", "items": 31, "share": 0.172, "previous_share": 0.083,
         "change_vs_previous": 0.089, "themes": [{"name": "Home cooking", "share": 0.172}]},
    ],
    "themes": [
        {"name": "Gaming clips", "field": "Gaming", "items": 61, "share": 0.339, "previous_share": 0.0,
         "change_vs_previous": 33.9, "area": "gaming", "channels": [{"name": "Clip Factory", "items": 61}]},
        {"name": "Digital drawing", "field": "Art", "items": 36, "share": 0.2, "previous_share": 0.3,
         "change_vs_previous": -10.0, "area": "art and design", "channels": [{"name": "Pixel Pencil", "items": 30}]},
        {"name": "Home cooking", "field": "Cooking", "items": 31, "share": 0.172, "previous_share": 0.083,
         "change_vs_previous": 8.9, "area": "food and cooking", "channels": [{"name": "Pan Theory", "items": 31}]},
        {"name": "Watercolor painting", "field": "Art", "items": 6, "share": 0.033, "previous_share": 0.05,
         "change_vs_previous": -1.7, "area": "art and design", "channels": [{"name": "Wet Paper", "items": 6}]},
    ],
    "channels": [
        {"name": "Clip Factory", "items": 61, "days": 28, "theme": "Gaming clips", "area": "gaming"},
        {"name": "Pixel Pencil", "items": 30, "days": 20, "theme": "Digital drawing", "area": "art and design"},
    ],
    "new": {"themes": [], "channels": []}, "stopped": {"themes": [], "channels": []},
}
SEP = copy.deepcopy(W47)
SEP["window"] = {"words": "September 2026", "start": "2026-09-01", "end": "2026-09-30", "clipped": False}
SEP["previous"]["words"] = "August 2026"
SEP["themes"][0]["items"] = 12
L["w47"] = [env("r1", W47, window_said=W47["window"]["words"]), env("r2", SEP, window_said="September 2026")]

# a search of their saves (items, not a sheet), and an item list with times opened
L["search"] = [items_envelope("r1", "search", [
    {"item_id": "rs1", "title": "Watercolor portrait study", "channel": "Wet Paper", "platform": "instagram",
     "when": "2026-10-05", "how": "save", "fit": "clear", "why_matched": "Watercolor portrait study"},
    {"item_id": "rs2", "title": "Sourdough crumb: longer bulk ferment", "channel": "Bread Lab", "platform": "instagram",
     "when": "2026-10-06", "how": "watch", "fit": "weak", "why_matched": "Sourdough crumb"},
], window_said="")]
L["items"] = [items_envelope("r1", "items", [
    {"item_id": "rp1", "title": "Weeknight cooking pasta", "channel": "Pan Theory", "platform": "youtube",
     "when": "2026-10-20", "times_opened": 5, "length": "long"},
    {"item_id": "rp2", "title": "Cooking hack [r1.totals.items] {channels[0].items} 999 views", "channel": "Pan Theory",
     "platform": "youtube", "when": "2026-10-25", "times_opened": 2, "length": "long"},
], window_said="October 2026")]

ledgers = L

LEAD_MARKED = ("In the 4 weeks up to 30 October 2026, Gaming clips[r1.themes[0]] led what you opened, with "
               "56[r1.themes[0].items] videos.")
_OCT = "In October 2026, here is what stood out."
_LATELY = "In the 4 weeks up to 30 October 2026, here is what stood out."
LEADS = {
    "lately": _LATELY, "hidden": _LATELY,
    "oct_channels": _OCT, "oct_count": _OCT, "least": _OCT, "least_tie": _OCT, "least_incomplete": _OCT,
    "top_tie": _OCT, "items": _OCT,
    "lately_long": "In the 4 weeks up to 30 October 2026, leaving out Shorts, here is what stood out.",
    "years": "Across all your history, here is what stood out.",
    "first_wc": "Across all your history, here is what stood out.",
    "w47": "Right now (the 4 weeks to 30 Oct, where your YouTube export ends), here is what stood out.",
    "search": "Here's what I found in your saves.",
}

# (id, ledger, class, text, expect, [reasons]) ; expect "kept" or "dropped"
C = [
    # ---------------- 3.1 parse
    ("f_badref_row", "lately", "3.1 bad_ref", "Brick Realm[r1.channels[9]] made 4[r1.channels[9].items] videos.", "dropped", ["bad_ref"]),
    ("f_badref_rid", "lately", "3.1 bad_ref", "Clip Factory[r3.channels[0]] made 56[r3.channels[0].items] videos.", "dropped", ["bad_ref"]),
    ("f_calc_literal", "lately", "3.1 calc with a literal", "Gaming clips[r1.themes[0]] grew 30 points[=points(r1.themes[0].share, 0.15)].", "dropped", ["bad_ref"]),
    ("f_slot_typed", "lately", "3.1 a slot typed (strict-mode syntax)", "Clip Factory[r1.channels[0]] made {r1.channels[0].items} videos.", "dropped", ["bad_ref"]),
    ("f_forged_title", "items", "hand check: a forged marker inside a title", "Cooking hack (r1.totals.items) got 999[r1.totals.items] views.", "dropped", ["bad_ref"]),
    ("f_forged_title2", "items", "hand check: a forged slot inside a title", "Cooking hack[r1.items[1]] (channels(0).items) was opened 999 times.", "dropped", ["uncited_number"]),
    ("f_value_no_number", "lately", "3.1 a value marker after words", "Clip Factory[r1.channels[0]] made plenty[r1.channels[0].items] of videos.", "dropped", ["bad_marker"]),
    # ---------------- 3.2 one result
    ("f_two_results", "w47", "3.2 two results", "In September Gaming clips[r2.themes[0]] already had 61[r1.themes[0].items].", "dropped", ["two_results"]),
    ("f_two_results_calc", "w47", "3.2 a calc over two results", "Gaming clips[r1.themes[0]] grew by 49[=diff(r1.themes[0].items, r2.themes[0].items)] videos.", "dropped", ["two_results"]),
    # ---------------- 3.3 every number cited
    ("f_uncited_digits", "lately", "3.3 a number typed with no marker", "Clip Factory[r1.channels[0]] made 56 videos.", "dropped", ["uncited_number"]),
    ("f_uncited_word", "lately", "3.3 a number word with no marker", "Gaming clips[r1.themes[0]] and two other themes[r1.themes[1]] grew.", "dropped", ["uncited_number"]),
    ("f_uncited_half", "lately", "3.3 'half' with no marker", "Gaming clips[r1.themes[0]] was about half of what you opened.", "dropped", ["uncited_number"]),
    ("f_uncited_second", "w47", "3.3 hand check: a second number with no marker", "Food and cooking[r1.areas[2]] grew 9 points while art fell 4.", "dropped", ["uncited_number"]),
    # ---------------- 3.4 value
    ("f_wrong_count", "lately", "3.4 the right marker, a wrong number", "Clip Factory[r1.channels[0]] made 65[r1.channels[0].items] videos.", "dropped", ["wrong_value"]),
    ("f_wrong_share", "w47", "3.4 a wrong share", "Gaming[r1.areas[0]] was 38%[r1.areas[0].share] of what you opened.", "dropped", ["wrong_value"]),
    ("f_true_wrong_marker", "lately", "3.4 a true number under the wrong marker", "Pan Theory[r1.channels[1]] made 27[r1.channels[1].items] videos.", "dropped", ["wrong_value"]),
    ("f_pct_on_count", "lately", "3.4 a percent cited to a count", "Clip Factory[r1.channels[0]] made 56%[r1.channels[0].items] of what you opened.", "dropped", ["wrong_measure"]),
    ("f_count_on_share", "lately", "3.4 a count cited to a share", "Clip Factory[r1.channels[0]] made 45[r1.channels[0].share] videos.", "dropped", ["wrong_measure"]),
    ("f_over_hedge", "lately", "3.4 'over' above the cell", "Clip Factory[r1.channels[0]] made over 58[r1.channels[0].items] videos.", "dropped", ["wrong_value"]),
    ("f_wrong_date", "first_wc", "3.4 a date at the wrong day", "You first opened Watercolor wet on wet[r1.items[0]] on 4 January 2025[r1.items[0].at].", "dropped", ["wrong_value"]),
    ("f_length", "lately", "watch time: a length cell", "You opened 64[r1.totals.long] long videos, about 30 hours of them.", "dropped", ["watch_time"]),
    # ---------------- 3.5 calc
    ("f_calc_diff", "lately", "3.5 a difference wrong", "Clip Factory[r1.channels[0]] made 30[=diff(r1.channels[0].items, r1.channels[1].items)] more videos than Pan Theory[r1.channels[1]].", "dropped", ["calc"]),
    ("f_calc_points", "w47", "3.5 points wrong", "Gaming[r1.areas[0]] rose 20 points[=points(r1.areas[0].share, r1.areas[0].previous_share)].", "dropped", ["calc"]),
    ("f_calc_doubled", "w47", "3.5 'doubled' out of its band", "Gaming[r1.areas[0]] tripled[=ratio(r1.areas[0].share, r1.areas[0].previous_share)], to 36%[r1.areas[0].share].", "dropped", ["calc"]),
    ("f_calc_direction", "lately", "3.5 'rose' on a fall", "Digital drawing[r1.themes[2]] rose 37 points[=points(r1.themes[2].share, r1.themes[2].previous_share)].", "dropped", ["direction"]),
    ("f_calc_small", "w47", "3.5 'up' under 3 points", "Art and design[r1.areas[1]] went up 4 points[=points(r1.areas[1].previous_share, r1.areas[1].share)].", "dropped", ["calc"]),
    ("f_more_reopens", "items", "hand check: 'more' that counts re-opens", "Weeknight cooking pasta[r1.items[0]] was opened 3[=diff(r1.items[0].times_opened, r1.items[1].times_opened)] more videos than Cooking hack[r1.items[1]].", "dropped", ["wrong_measure"]),
    ("f_reopens_as_videos", "items", "hand check: openings said as videos", "From Pan Theory you opened 5[r1.items[0].times_opened] videos.", "dropped", ["wrong_measure"]),
    ("f_pct_change", "oct_count", "3.5 a percent change wrong", "You opened 134[r1.totals.items] videos, up 150%[=pct_change(r1.totals.items, r1.previous.items)] on September 2026.", "dropped", ["calc"]),
    # ---------------- 3.6 names
    ("f_wrong_row_name", "lately", "3.6 a row marker after another name", "Pan Theory[r1.channels[0]] led with 56[r1.channels[0].items] videos.", "dropped", ["wrong_name"]),
    ("f_invented_start", "lately", "3.6 an invented channel at the start", "Brickstorm Gaming made 56[r1.channels[0].items] of your videos.", "dropped", ["unknown_name"]),
    ("f_invented_mid", "lately", "3.6 an invented channel inside", "Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos, more than Lava Lamp Studio.", "dropped", ["unknown_name"]),
    ("f_uncited_name", "lately", "3.6 a library name with no marker", "Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos, well ahead of Pixel Pencil.", "dropped", ["uncited_name"]),
    ("f_under_other_name", "lately", "hand check: a value of one record under another's name", "Pan Theory[r1.channels[1]] made 56[r1.channels[0].items] videos.", "dropped", ["unnamed_owner", "bound_to_other", "bound"]),
    ("f_channel_behind_theme", "lately", "hand check: a channel behind a theme it is not in", "Pixel Pencil[r1.channels[2]] is behind Gaming clips[r1.themes[0]], with 27[r1.channels[2].items] videos.", "dropped", ["channel_not_in_theme"]),
    # ---------------- 3.7 outside in history
    ("f_appositive", "w47", "3.7 an appositive", "Clip Factory[r1.channels[0]], the most popular clips channel on YouTube, made 61[r1.channels[0].items] of them.", "dropped", ["outside_in_history"]),
    ("f_world_claim", "lately", "3.7 a world claim", "Clip Factory[r1.channels[0]] has millions of subscribers and made 56[r1.channels[0].items] of your videos.", "dropped", ["outside_in_history"]),
    # ---------------- 3.8 insight
    ("f_mostly", "lately", "3.8 'mostly' under 50%", "You mostly opened Gaming clips[r1.themes[0]], 45%[r1.themes[0].share] of what you opened.", "dropped", ["spread"]),
    ("f_led_not_first", "lately", "3.8 'led' on a row that is not first", "Pan Theory[r1.channels[1]] led with 29[r1.channels[1].items] videos.", "dropped", ["rank"]),
    ("f_close_behind", "lately", "3.8 'close behind' with a wide gap", "Clip Factory[r1.channels[0]] led with 56[r1.channels[0].items] videos, with Pan Theory[r1.channels[1]] close behind at 29[r1.channels[1].items].", "dropped", ["not_close"]),
    ("f_base_yt", "w47", "3.8 a share on the wrong base", "Gaming[r1.areas[0]] was 36%[r1.areas[0].share] of your YouTube videos.", "dropped", ["share_of_topic", "base"]),
    ("f_base_filtered", "lately_long", "hand check: a share on the wrong base (filtered)", "Home cooking[r1.themes[0]] made up 45%[r1.themes[0].share] of what you opened.", "dropped", ["base"]),
    ("f_one_value", "lately", "hand check: a change with one value", "Digital drawing[r1.themes[2]] fell to 22%[r1.themes[2].share].", "dropped", ["one_value"]),
    ("f_end_in_base", "lately", "hand check: an end value in the base period", "Digital drawing[r1.themes[2]] fell from 59%[r1.themes[2].previous_share] to 22%[r1.themes[2].share] in the 4 weeks before (5 September to 2 October 2026).", "dropped", ["wrong_window"]),
    ("f_small_move", "w47", "3.8 a move under 3 points", "Watercolor painting[r1.themes[3]] slipped 2 points[r1.themes[3].change_vs_previous] against the 4 weeks before.", "dropped", ["small_move"]),
    ("f_vague", "lately", "3.8 a direction with no number", "Digital drawing[r1.themes[2]] faded while Gaming clips[r1.themes[0]] grew.", "dropped", ["vague", "direction_unbound"]),
    ("f_dropped_not_stopped", "years", "3.8 'stopped' on a fading row", "You stopped watching Minecraft builds[r1.themes[0]] after 162[r1.themes[0].items] videos.", "dropped", ["not_stopped"]),
    ("f_new_not_new", "lately", "3.8 'new' on an old channel", "Pan Theory[r1.channels[1]] was new to you, with 29[r1.channels[1].items] videos.", "dropped", ["not_new"]),
    # ---------------- 3.9 claims with no marker
    ("f_uncited_claim", "lately", "3.9 a consumption claim with no marker", "You've been watching a lot more cooking lately.", "dropped", ["uncited_claim"]),
    ("f_uncited_compare", "lately", "3.9 a comparative with no marker", "Your art videos got longer than before.", "dropped", ["uncited_claim"]),
    # ---------------- 3.10 psych, outcome, limits
    ("f_psych", "lately", "3.10 a caption obeyed: 'you love'", "You love painting more than anything, with 4[r1.themes[4].items] watercolor videos.", "dropped", ["psych"]),
    ("f_outcome", "lately", "3.10 a claimed outcome", "I've set up a rule to send you Clip Factory[r1.channels[0]]'s 56[r1.channels[0].items] videos.", "dropped", ["outcome"]),
    ("f_limits", "lately", "3.10 limits talk", "I can't see what you watched after 30 October, but Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.", "dropped", ["limits"]),
    ("f_watch_hours", "lately", "watch time: hours' worth", "Gaming clips[r1.themes[0]] was hours' worth of your 56[r1.themes[0].items] videos.", "dropped", ["watch_time"]),
    # ---------------- 3.11 sensitive
    ("f_sensitive", "lately", "3.11 a sensitive topic named", "Dating advice made up 23%[r1.themes[1].share] of what you opened.", "dropped", ["sensitive"]),
    # ---------------- 3.12 least, 3.13, ties
    ("f_least_on_most", "oct_channels", "3.12 'least' on a result ordered by most", "Clip Factory[r1.channels[0]] was the channel you opened least, with 61[r1.channels[0].items] videos.", "dropped", ["least"]),
    ("f_least_incomplete", "least_incomplete", "3.12 'least' on a result not over every entity", "Limit Lane[r1.channels[0]] was the channel you opened least, with 4[r1.channels[0].items] videos.", "dropped", ["least"]),
    ("f_least_other_list", "least", "3.12 'least' on a list the result did not rank", "Gaming clips[r1.themes[0]] was the theme you opened least, with 61[r1.themes[0].items] videos.", "dropped", ["least"]),
    ("f_most_on_least", "least", "3.12 'most' on a result ordered by least", "Limit Lane[r1.channels[0]] was your top channel, with 4[r1.channels[0].items] videos.", "dropped", ["rank"]),
    ("f_tie_top", "top_tie", "hand check: a rank word on a tie", "Clip Factory[r1.channels[0]] led your channels with 61[r1.channels[0].items] videos.", "dropped", ["tie"]),
    ("f_tie_least", "least_tie", "hand check: 'least' on a tie", "Paper Moon[r1.channels[0]] was the channel you opened least, with 4[r1.channels[0].items] videos.", "dropped", ["tie"]),
    # ---------------- 3.15 window
    ("f_wrong_month", "oct_channels", "hand check: a right number with a wrong window", "In September, Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.", "dropped", ["wrong_window"]),
    ("f_wrong_year", "lately", "3.15 a year outside the window", "In 2025 Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.", "dropped", ["wrong_window"]),
    ("f_lately_on_month", "oct_channels", "3.15 'lately' on a month's result", "Lately Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.", "dropped", ["wrong_window"]),
    ("f_day_outside", "oct_channels", "3.15 a day outside the window", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos up to 12 November.", "dropped", ["wrong_window"]),
    ("f_prev_in_now", "lately", "3.15 a base value said in the window's words", "Gaming clips[r1.themes[0]] had 5[r1.themes[0].previous_items] videos in the 4 weeks up to 30 October 2026.", "dropped", ["wrong_window"]),
    # ---------------- hand check: a count that drops a filter
    ("f_count_drops_long", "lately_long", "hand check: a count that drops 'long'", "You opened 64[r1.totals.items] videos in these 4 weeks.", "dropped", ["filter_dropped"]),
    # ---------------- step 4: results that are not sheets
    ("f_search_weak", "search", "4 a weak match presented as the thing", "Here's the one you saved: Sourdough crumb: longer bulk ferment[r1.items[1]].", "dropped", ["weak_fit"]),
    ("f_search_not_saved", "search", "4 'the one you saved' on a row that was watched", "The one you saved is Sourdough crumb: longer bulk ferment[r1.items[1]].", "dropped", ["wrong_name"]),
    ("f_search_quote", "search", "4 a quoted title that is not the row's", "\"Watercolor portrait class\" by Wet Paper[r1.items[0]] is the closest.", "dropped", ["wrong_name"]),
    ("f_search_value", "search", "4 a count of a search over rows", "You saved 12[r1.items.count] watercolor posts.", "dropped", ["wrong_value"]),
]

T = [
    # ---------------- true sentences (twins of the false ones where they can be)
    ("t_count", "lately", "3.4 count", "Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.", "kept", []),
    ("t_count_hedged", "lately", "3.4 a hedged count", "Clip Factory[r1.channels[0]] made over 55[r1.channels[0].items] videos.", "kept", []),
    ("t_count_word", "lately", "3.4 a count in words", "Pan Theory[r1.channels[1]] made 29[r1.channels[1].items] videos on 25[r1.channels[1].days] days.", "kept", []),
    ("t_share", "w47", "3.4 share, rounded", "Gaming[r1.areas[0]] was 36%[r1.areas[0].share] of what you opened.", "kept", []),
    ("t_share_decimal", "w47", "3.4 share with a decimal", "Gaming[r1.areas[0]] was 35.6%[r1.areas[0].share] of what you opened.", "kept", []),
    ("t_share_theme", "lately", "3.4 a theme's share", "Gaming clips[r1.themes[0]] made up 45%[r1.themes[0].share] of what you opened.", "kept", []),
    ("t_points_cell", "lately", "3.4 points from a cell", "Gaming clips[r1.themes[0]] rose 35 points[r1.themes[0].change_vs_previous] against the 4 weeks before.", "kept", []),
    ("t_change_pts", "oct_channels", "3.4 change_pts of an area", "Gaming[r1.areas[0]] rose 33 points[r1.areas[0].change_pts] against September 2026.", "kept", []),
    ("t_two_values", "lately", "hand check twin: a change with both values", "Digital drawing[r1.themes[2]] fell from 59%[r1.themes[2].previous_share] to 22%[r1.themes[2].share] against the 4 weeks before.", "kept", []),
    ("t_date", "first_wc", "3.4 a date", "You first opened Watercolor wet on wet[r1.items[0]] on 10 January 2025[r1.items[0].at].", "kept", []),
    ("t_date_month", "first_wc", "3.4 a date at month precision", "Wet Paper[r1.channels[0]] goes back to January 2025[r1.channels[0].first_watched].", "kept", []),
    ("t_calc_diff", "lately", "3.5 a difference", "Clip Factory[r1.channels[0]] made 27[=diff(r1.channels[0].items, r1.channels[1].items)] more videos than Pan Theory[r1.channels[1]].", "kept", []),
    ("t_calc_points", "w47", "3.5 points", "Gaming[r1.areas[0]] rose 16 points[=points(r1.areas[0].share, r1.areas[0].previous_share)] against the 4 weeks before.", "kept", []),
    ("t_calc_doubled", "w47", "3.5 'doubled' (4.7)", "Food and cooking[r1.areas[2]] doubled[=ratio(r1.areas[2].share, r1.areas[2].previous_share)], to 17%[r1.areas[2].share].", "kept", []),
    ("t_calc_times", "lately", "3.5 'N times'", "Clip Factory[r1.channels[0]] made 1.9 times[=ratio(r1.channels[0].items, r1.channels[1].items)] as many videos as Pan Theory[r1.channels[1]].", "kept", []),
    ("t_calc_fell", "lately", "3.5 a fall", "Digital drawing[r1.themes[2]] fell 37 points[=points(r1.themes[2].share, r1.themes[2].previous_share)] against the 4 weeks before.", "kept", []),
    ("t_pct_change", "oct_count", "3.5 a percent change", "You opened 134[r1.totals.items] videos, up 205%[=pct_change(r1.totals.items, r1.previous.items)] on September 2026.", "kept", []),
    ("t_count_marker", "w47", "an honest incidental number: the top 3", "Your top 2[r1.channels.count] channels were led by Clip Factory[r1.channels[0]] with 61[r1.channels[0].items] videos.", "kept", []),
    ("t_alias", "w47", "3.6 an area said by its alias", "Cooking[r1.areas[2]] was 17%[r1.areas[2].share] of what you opened.", "kept", []),
    ("t_plain_subject", "lately", "3.6 a name that is the subject of its value marker", "Clip Factory made 56[r1.channels[0].items] videos.", "kept", []),
    ("t_inside", "w47", "4.7 P1", "Inside it, Gaming clips[r1.themes[0]] is the biggest theme, and Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of those videos.", "kept", []),
    ("t_led", "lately", "3.8 'led' on the first row", "Clip Factory[r1.channels[0]] led your channels with 56[r1.channels[0].items] videos.", "kept", []),
    ("t_next", "lately", "3.8 'came next' on the second row", "Pan Theory[r1.channels[1]] came next with 29[r1.channels[1].items] videos.", "kept", []),
    ("t_base_filtered", "lately_long", "hand check twin: a share on its own base", "Home cooking[r1.themes[0]] made up 45%[r1.themes[0].share] of your long videos.", "kept", []),
    ("t_count_long", "lately_long", "hand check twin: a count with its filter", "You opened 64[r1.totals.items] long videos in these 4 weeks.", "kept", []),
    ("t_least", "least", "3.12 'least' on a least result", "Limit Lane[r1.channels[0]] was the channel you opened least, with 4[r1.channels[0].items] videos.", "kept", []),
    ("t_no_tie", "oct_channels", "hand check twin: a rank word with no tie", "Clip Factory[r1.channels[0]] led your channels with 61[r1.channels[0].items] videos.", "kept", []),
    ("t_hidden_rank", "hidden", "3.13 a rank word with a hidden row above (kept, the private line)", "Clip Factory[r1.channels[0]] led your channels with 56[r1.channels[0].items] videos.", "kept", []),
    ("t_month", "oct_channels", "3.15 the window's month", "In October, Pan Theory[r1.channels[1]] made 31[r1.channels[1].items] videos.", "kept", []),
    ("t_prev_window", "oct_channels", "3.15 the compare window for a previous cell", "Digital drawing[r1.themes[2]] fell from 70%[r1.themes[2].previous_share] in September to 22%[r1.themes[2].share] in October.", "kept", []),
    ("t_lately", "lately", "3.15 'lately' on the lately window", "Lately Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.", "kept", []),
    ("t_years", "years", "3.15 a year inside the window", "Minecraft builds[r1.themes[0]] made 162[r1.themes[0].items] videos since 2021.", "kept", []),
    ("t_fading", "years", "3.8 a fading row with its values", "Minecraft builds[r1.change.fading[0]] fell from 68%[r1.change.fading[0].from_share] in 2021 to 5%[r1.change.fading[0].to_share] in 2026.", "kept", []),
    ("t_search", "search", "4 a search row", "Watercolor portrait study[r1.items[0]] from Wet Paper is the one you saved.", "kept", []),
    ("t_search_date", "search", "4 a search row's date", "You saved Watercolor portrait study[r1.items[0]] on 5 October[r1.items[0].when].", "kept", []),
    ("t_search_count", "search", "4 a count marker on a search", "I found 2[r1.items.count] posts in your saves.", "kept", []),
    ("t_items_opened", "items", "an item's openings said as openings", "You opened Weeknight cooking pasta[r1.items[0]] 5 times[r1.items[0].times_opened].", "kept", []),
    ("t_no_marker_plain", "lately", "a sentence with no claim", "Here is the picture.", "kept", []),
    ("t_shorts", "lately", "3.8 Shorts with their base", "Shorts were 47%[r1.totals.shorts_share] of your YouTube videos.", "kept", []),
    ("t_days", "oct_count", "3.4 days of the window", "You opened something on 30[r1.totals.days_active] days in October 2026.", "kept", []),
    ("t_two_names", "lately", "3.6 two rows, each with its number", "Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos and Pixel Pencil[r1.channels[2]] made 27[r1.channels[2].items].", "kept", []),
    ("t_theme_channel", "lately", "hand check twin: a channel inside its own theme", "Clip Factory[r1.themes[0].channels[0]] is behind all 56[r1.themes[0].channels[0].items] of your Gaming clips[r1.themes[0]] videos.", "kept", []),
]

OUTSIDE = [
    # (id, ledger, form, target, expect, reasons)
    ("o_ok", "w47", {"lead": LEADS["w47"], "points": ["Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos."],
                     "outside": [{"about": "r1.channels[0]", "text": "A channel of short gaming clips.", "source": "general"}]},
     "outside:0", "kept", []),
    ("o_subscribers", "w47", {"lead": LEADS["w47"], "points": ["Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos."],
                              "outside": [{"about": "r1.channels[0]", "text": "It has 2 million subscribers.", "source": "general"}]},
     "outside:0", "dropped", ["number"]),
    ("o_you", "w47", {"lead": LEADS["w47"], "points": ["Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos."],
                      "outside": [{"about": "r1.channels[0]", "text": "You clearly enjoy its fast edits.", "source": "general"}]},
     "outside:0", "dropped", ["second_person"]),
    ("o_not_cited", "w47", {"lead": LEADS["w47"], "points": [],
                            "outside": [{"about": "r1.channels[1]", "text": "A channel of drawing lessons.", "source": "general"}]},
     "outside:0", "dropped", ["about_not_cited"]),
    ("o_other_name", "w47", {"lead": LEADS["w47"], "points": ["Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos."],
                             "outside": [{"about": "r1.channels[0]", "text": "It often appears next to Pixel Pencil.", "source": "general"}]},
     "outside:0", "dropped", ["other_name"]),
    ("o_web", "w47", {"lead": LEADS["w47"], "points": ["Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos."],
                      "outside": [{"about": "r1.channels[0]", "text": "A channel of short gaming clips.", "source": "web"}]},
     "outside:0", "dropped", ["source"]),
    ("i_note_number", "search", {"lead": LEADS["search"], "points": [], "items": [{"ref": "r1.items[0]", "note": "Saved 3 times."}]},
     "item:0", "dropped", ["uncited_number"]),
    ("i_not_item", "lately", {"lead": LEADS["lately"], "points": [], "items": [{"ref": "r1.channels[0]", "note": None}]},
     "item:0", "dropped", ["not_item"]),
    ("i_ok", "search", {"lead": LEADS["search"], "points": [], "items": [{"ref": "r1.items[0]", "note": None}]},
     "item:0", "kept", []),
    ("r_repeat", "lately", {"lead": LEAD_MARKED, "points": ["Gaming clips[r1.themes[0]] had 56[r1.themes[0].items] videos, all of them Shorts."]},
     "point:0", "dropped", ["repeat"]),
    ("l_window_missing", "lately", {"lead": "Clip Factory[r1.channels[0]] led your channels with 56[r1.channels[0].items] videos.", "points": []},
     "lead", "dropped", ["window_missing"]),
    ("l_too_long", "lately", {"lead": "In the 4 weeks up to 30 October 2026, " + "Clip Factory[r1.channels[0]] led your channels with 56[r1.channels[0].items] videos and " * 6 + "more.", "points": []},
     "lead", "dropped", ["too_long"]),
]

TODAY = {"today": "2026-11-22"}
REL = {"today": "2026-11-22", "message": "what about dating", "unlock": "relationships"}
# (id, ledger, class, text, expect, [reasons], turn)
C2 = [
    ("f_month_end_in_base", "oct_channels", "hand check: an end value in the base period (said by its month)", "Digital drawing[r1.themes[2]] fell from 70%[r1.themes[2].previous_share] to 22%[r1.themes[2].share] in September.", "dropped", ["wrong_window"], TODAY),
    ("f_months_swapped", "oct_channels", "3.15 the two periods' months swapped", "Digital drawing[r1.themes[2]] fell from 70%[r1.themes[2].previous_share] in October to 22%[r1.themes[2].share] in September.", "dropped", ["wrong_window"], TODAY),
    ("f_this_week", "oct_channels", "3.15 'this week' on a month's result", "This week Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.", "dropped", ["wrong_window"], TODAY),
    ("f_this_month", "oct_channels", "3.15 'this month' on last month's result", "This month Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.", "dropped", ["wrong_window"], TODAY),
    ("f_today", "oct_channels", "3.15 'today' on a month's result", "Today Clip Factory[r1.channels[0]] has 61[r1.channels[0].items] videos.", "dropped", ["wrong_window"], TODAY),
    ("f_year_on_weeks", "lately", "hand check: a right number with a wrong window (a year around 4 weeks)", "In 2026 Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] videos.", "dropped", ["wrong_window"], TODAY),
    ("f_label_not_period", "years", "3.15 a period label on a count of all the history", "In 2021 Minecraft builds[r1.themes[0]] made 162[r1.themes[0].items] videos.", "dropped", ["wrong_window"], TODAY),
    ("f_alias_theme_word", "lately", "3.6 an area under a word that is a theme's", "Painting[r1.areas[1]] was 25%[r1.areas[1].share] of what you opened.", "dropped", ["wrong_name"], TODAY),
    ("f_sign", "w47", "3.4 a typed sign against the cell's", "Art and design[r1.areas[1]] moved +4 points[r1.areas[1].change_pts] against the 4 weeks before.", "dropped", ["direction"], TODAY),
    ("f_up_on_fall", "w47", "3.4 'up' on a fall in points", "Art and design[r1.areas[1]] went up 4 points[r1.areas[1].change_pts] against the 4 weeks before.", "dropped", ["direction"], TODAY),
    ("f_second_topic", "search", "3.11 a second sensitive topic beside the unlocked one", "Here is what I found about dating and your debt.", "dropped", ["sensitive"], REL),
    ("t_last_month", "oct_channels", "3.15 'last month' on last month's result", "Last month Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.", "kept", [], TODAY),
    ("t_months", "oct_channels", "3.15 each value with its own month", "Digital drawing[r1.themes[2]] fell from 70%[r1.themes[2].previous_share] in September to 22%[r1.themes[2].share] in October.", "kept", [], TODAY),
    ("t_sign", "w47", "3.4 a typed sign that is the cell's", "Gaming[r1.areas[0]] rose +16 points[r1.areas[0].change_pts] against the 4 weeks before.", "kept", [], TODAY),
    ("t_unlocked", "search", "3.11 the unlocked topic's own words", "Here is what I found about dating.", "kept", [], REL),
    ("t_label_period", "years", "3.15 a period label on that period's cell", "In 2021, Minecraft builds[r1.periods[0].themes[0]] took 68%[r1.periods[0].themes[0].share] of what you opened.", "kept", [], TODAY),
]


out = []
for cid, led, cls, text, expect, reasons in C + T:
    out.append({"id": cid, "source": "new", "class": cls, "ledger": led,
                "form": {"lead": LEADS[led], "points": [text]}, "target": "point:0", "expect": expect,
                "reasons": reasons})
for cid, led, cls, text, expect, reasons, turn in C2:
    out.append({"id": cid, "source": "new", "class": cls, "ledger": led,
                "form": {"lead": LEADS[led], "points": [text]}, "target": "point:0", "expect": expect,
                "reasons": reasons, "turn": turn})
for cid, led, form, target, expect, reasons in OUTSIDE:
    out.append({"id": cid, "source": "new", "class": "4.3 steps 2, 5, 6, 14", "ledger": led, "form": form,
                "target": target, "expect": expect, "reasons": reasons})

# the step 1 verifier audit's sentences on real tool results (eval/brain_audit_cases.py), with the ledgers that
# tests/test_brain_step1_fix.py froze here (MVP_FREEZE_AUDIT=1 rewrites them from today's tools)
_aspec = importlib.util.spec_from_file_location("brain_audit_cases", os.path.join(HERE, "brain_audit_cases.py"))
AUD = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(AUD)
audit_turns = _old_all.get("audit_turns") or {}
for name in AUD.LEDGERS:
    ledgers["audit_" + name] = _old["audit_" + name]
for cid, led, where, truth, cls, text, fam in AUD.CASES:
    expect = "kept" if truth == "T" else ("private_line" if cid in AUD.PRIVATE_LINE else "dropped")
    out.append({"id": "audit_" + cid, "source": "audit_true" if truth == "T" else "audit",
                "class": f"{cls} (the audit expected: {fam or 'kept'})" + (" SYNTHETIC" if truth == "FS" else ""),
                "ledger": "audit_" + led,
                "form": {"lead": text, "points": []} if where == "L" else {"lead": "", "points": [text]},
                "target": "lead" if where == "L" else "point:0", "expect": expect, "reasons": [],
                "turn": audit_turns[led]})

# mvp20 fix: the verifier attack's sentences on real tool results (eval/brain_attack_cases.py), with the ledgers that
# tests/test_brain_fix.py froze here (MVP_FREEZE_ATTACK=1 rewrites them from today's tools). False ones are source
# "attack" (expected dropped), true ones "attack_true" (scored apart, like the audit's). A point is tried under each
# of its true carrier leads (case "forms"): kept when any carrier keeps it.
_kspec = importlib.util.spec_from_file_location("brain_attack_cases", os.path.join(HERE, "brain_attack_cases.py"))
ATK = importlib.util.module_from_spec(_kspec)
_kspec.loader.exec_module(ATK)
attack_turns = _old_all.get("attack_turns") or {}
for name in ATK.LEDGERS:
    if "attack_" + name in _old:
        ledgers["attack_" + name] = _old["attack_" + name]
for cid, led, where, truth, cls, text, why, carriers in ATK.CASES:
    if "attack_" + led not in ledgers:
        continue   # (not frozen yet: run tests/test_brain_fix.py with MVP_FREEZE_ATTACK=1 first)
    for w in (["L", "P"] if where == "B" else [where]):
        base = {"source": "attack" if truth == "F" else "attack_true", "class": f"{cls}: {why}",
                "ledger": "attack_" + led, "expect": "dropped" if truth == "F" else "kept", "reasons": [],
                "turn": attack_turns[led]}
        if w == "L":
            out.append(dict(base, id=f"attack_{cid}" + ("_L" if where == "B" else ""),
                            form={"lead": text, "points": []}, target="lead"))
        else:
            out.append(dict(base, id=f"attack_{cid}" + ("_P" if where == "B" else ""),
                            form={"lead": carriers[0], "points": [text]},
                            forms=[{"lead": c, "points": [text]} for c in carriers], target="point:0"))

# the insight_v5 sentences (SPEC 4.8 source 1)
d, cases, extra = CONV.load()
rows = CONV.rows()
by_block = {}
for n, x in enumerate((d.get("v5") or {}).get("cases") or []):
    s = extra[x["case"]] if x["case"] in extra else cases[x["case"]]["sheet"]
    key = f"v5_{n:02d}_{x['case']}"
    ledgers[key] = [envelope("r1", tool_of(s), s)]
    by_block[n] = key
k = 0
for r in rows:
    key = by_block[r["block"]]
    env = ledgers[key][0]
    lead = CONV.window_lead(env)
    if r["as"] == "answer":
        m = r["marked"]
        form = {"lead": lead + " " + m[:1].upper() + m[1:], "points": []}
        target = "lead:1"
    else:
        form = {"lead": lead, "points": [r["marked"]]}
        target = "point:0"
    k += 1
    out.append({"id": f"v5_{k:03d}", "source": "insight_v5",
                "class": r["class"] + (f": {r['why']}" if r["why"] else ""), "ledger": key, "form": form,
                "target": target, "expect": "kept" if r["class"] == "true_as_typed" else "dropped", "reasons": [],
                "slotted": r["slotted"]})

data = {"about": "SPEC 4.8: the verifier's planted set. Every result here is made up: the round 12 test library's "
                 "sheets (tests/r12_library.py through facts.build), hand-made results in its names, and the sheets of "
                 "eval/insight_cases.json. 'new' cases are one class each (the 4.3 steps and the sixth pass's hand-check "
                 "classes); 'insight_v5' cases are the writer's eval sentences in marker form (eval/convert_insight_cases.py): "
                 "a sentence true only after today's code rewrote it is expected dropped.",
        "ledgers": ledgers, "audit_turns": audit_turns, "attack_turns": attack_turns, "cases": out}
with open(PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=1, ensure_ascii=False)
print(len(out), sum(1 for c in out if c["expect"] == "dropped"), sum(1 for c in out if c["expect"] == "kept"))
