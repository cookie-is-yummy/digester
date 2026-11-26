"""The answer verifier of the brain (SPEC.md section 4): nothing made up, with free numbers.

The model sees the real numbers of this turn's tool results and types them, each followed by a marker naming the cell
it claims to be (`36%[r1.areas[0].share]`, `Clip Factory[r1.channels[0]]`, `up 16 points[=points(r1.areas[0].share,
r1.areas[0].previous_share)]`, `the top 3[r1.channels.count]`). Code checks every sentence against the ledger (the
results of the turn, in the envelope of SPEC 2.3) before anything is sent, one sentence at a time, and sends nothing it
could not verify. Pure code: the same input always gives the same verdict. No model call, no network, no store.

Steps (SPEC 4.3): shape; split; per sentence: parse the markers, one result per sentence, every number cited, the
typed value equals the cell, calc markers re-done by code, row names, outside text kept apart, insight's checks (the
sentence turned into insight's slotted form and run through `insight.render` and `insight.check_sentence` against
the cited result's sheet), claims with no marker, psych and outcome words, sensitive words, "least", rank with hidden
rows, once, window words; then items, outside lines (4.4) and the verdict, with the repair text of 4.5.

How insight's checks are used one sentence at a time (the proof is in eval/convert_insight_cases.py and the design
session's verify_proof.md): every verified row marker and every cited plain name becomes that row's name slot (a name
left as typed beside a number slot fails `typed_name` in strict mode); the sheet given to insight is the result's sheet
without the keys the tools add (`ref`, `change_pts`), so insight's number pools are today's; `Facts.slotted` is set for
each call and the gate gets a fresh state; and every rewrite insight would make to a sentence (a value added to a
one-value change, a base inserted, a clause dropped) is a failure here, never applied: code never puts words into the
model's sentence. The one rewrite let through is the comparison period insight appends to a change ("against the 4
weeks before"): the scope line under every answer states it.
"""
from __future__ import annotations

import copy
import difflib
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import insight as I

VERIFY_VERSION = "brain_verify_v1"

# ------------------------------------------------------------------ the checker's mode (mvp24, DESIGN 24)
# "full": every rule (today's checker, unchanged). "cells": code checks the cells only (numbers, names, dates,
# calculations and what each number is bound to), the policy lines (outside knowledge, feelings, outcomes, watch time,
# sensitive topics) and the marker grammar; every framing rule (window, base, scope, rank, tie, list, only/all,
# direction words) is off at the source: its code is never added, and a rule chain that stops at its first hit walks
# past a rule that is off. Chosen by the `mode` argument, else by the environment variable MVP_BRAIN_CHECK.
CHECK_ENV = "MVP_BRAIN_CHECK"
CHECK_MODES = ("full", "cells", "values")

# every reason code the checker or insight's checks can give, by what it checks (pinned by tests/test_brain_cells.py:
# a code seen on any set that is in none of these fails the test)
CELL_CODES = frozenset({
    "bad_marker", "bad_ref", "two_results", "uncited_number", "free_number", "number", "wrong_value", "date",
    "wrong_measure", "count_as_share", "count_of_videos", "wrong_name", "typed_name", "bound_to_other", "calc", "ratio",
    "made_up_difference", "unknown_name", "uncited_name", "other_name", "wrong_group", "wrong_area",
    "channel_not_in_theme", "not_item", "link", "about_not_cited", "source", "marker", "garbled", "too_long",
    "language", "point_text", "insight_error", "bound", "fraction", "month", "quote", "number_word", "empty",
    "bad_path", "bad_value",
    "name", "word",   # insight's "name:<w>" (a capitalised word no name of the sheet holds), "word:<w>" (a topic word
                      # the sheet's vocabulary does not hold): a made-up name
    # mvp24: two of insight's binding rules the paper's taxonomy had filed among framing; each reads which row or which
    # measure a cell is of (insight.py, beside channel_not_in_theme and count_as_share), and each is the only check of
    # a planted cell-class case (v5_054, v5_056)
    "median_of_window", "shorts_as_long",
    # mvp25: the cells-only rules' codes (DESIGN 24.4)
    "other_period", "item_field", "length_cell",
    "share_of_name",   # insight's R3 (a share said "of your <name>"): a binding reason insight_walk counts
    # mvp26 (DESIGN 26): insight's "percent" (a percent no share of the sheet gives), seen live in run 2 and in no
    # pinned set before; a value check, so a cell code. Classing it changes nothing in cells mode (it was never off)
    "percent"})
POLICY_CODES = frozenset({"outside_in_history", "psych", "outcome", "sensitive", "watch_time", "filler",
                          "second_person", "generic_claim", "weak_fit", "too_many"})
FRAMING_CODES = frozenset({
    "wrong_window", "window_missing", "filter_dropped", "scope_broadened", "base", "base_missing", "no_base",
    "insight_rewrite", "rank", "not_top", "tie", "least", "spread", "mostly", "mix", "previous",
    "direction_unbound", "no_direction", "small_move", "vague", "one_value", "first_last", "private_total",
    "platform_word", "length_word", "shorts_left_out", "own_shorts_share", "share_of_topic",
    "weekpart", "weekday", "year", "hour", "time_of_day", "not_close", "not_new", "not_stopped", "order",
    "gap_words", "number_run", "season",
    "unsupported"})   # insight's "steadier", "consistent" with no number: a direction word
# a framing-listed rule that stays on in cells mode, and why (DESIGN 24.2)
FRAMING_KEPT = {"weekday": "insight's weekday rule also checks the weekday of an item's own date; it is the only check "
                           "of the attack's Q01 ('on 1 October 2026, a Sunday'), and it cost no true sentence on any set"}
# the codes whose place can be argued; each was decided by the evidence of DESIGN 24.2 (on = kept in cells mode)
DOUBT_CODES = {
    # "code@emitter": one rule of a code several rules give. A doubtful code (or emitter) stays on only when switching
    # it off alone lets a cell-class false case out (pin/loo.py over the planted, attack, skeptic and record sets).
    "direction@sign": "on",       # a typed sign or 'up' / 'down' on a points cell: f_sign, f_up_on_fall get out
    "direction@calc": "on",       # check_calc's sign: the attack's G02 ('45% fewer' of +45%) gets out
    "direction@from_to": "on",    # 'from' the now cell: the attack's X01 to X03 and the record set's N25 get out
    "direction@compare": "off",   # _compare_unbound's direction words: no cell-class case gets out
    "direction@insight": "on",    # insight's direction rule: alone, nothing gets out and no true sentence comes back;
                                  # off with uncited_claim@compare off, the attack's D01 gets out (insight stops at its
                                  # first reason, so a direction reason off hides its unnamed_owner reason)
    "uncited_claim@nomarker": "on",   # a claim with no marker: the audit's F32d (a last date with no marker) gets out
    "uncited_claim@bare": "off",      # _bare_clause: 7 true sentences back, no cell-class case out
    "uncited_claim@compare": "off",
    "uncited_claim@all_from": "off",
    # mvp25 (DESIGN 24.4): limits and repeat enforce the founder's own rules (never keep saying what the bot cannot
    # do; be brief), so each emitter was judged by what it would drop on run1 and the two looks, sentence by sentence
    # (step4.txt): on only when at most a quarter of its drops, and at most 3 per 65 answers, are useful true sentences
    "limits@words": "off",    # LIMITS words: 5 drops, all leads, 4 of them useful true sentences ("export ends", "I
                              # can't predict next week, but ... gaming was 49%")
    "limits@self": "off",     # what the assistant found or could not find: 6 drops, all leads. 2 wanted (look2's
                              # I02.0 false absence, twice); 4 are the one honest line of an answer whose code lead
                              # would be bare ("I couldn't check an answer to that in time.", "Here's what I found in
                              # your saves."): run1's N004.0 and N109.0, the looks' K04.0. 4 of 6 unwanted
    "limits@insight": "off",  # insight's own limits words: 8 drops, 5 of them useful true sentences
    "unnamed_owner": "on",    # 16 cell-class cases get out (a number beside another row's name)
    "bound_global": "off",    # no cell-class case out; 3 true sentences back
    "repeat": "off",          # no cell-class case out; a POLICY case (r_repeat, a fact said twice) gets out. mvp25:
                              # "repeat@once" would drop 2 points of run1 and the looks, 1 of them a useful true one
                              # (look1 D08.0: "All 32 were long videos, in the Home cooking theme"); insight's repeat
                              # drops none: both stay off
}
# marker-bookkeeping loosenings of cells mode (mvp23 record/d1b.txt; IN SAMPLE): a title in quotes, an item's own
# channel. mvp25: "short_word" ("a short" / "a long video" before an item's marker) is out: it let a short go out under
# another channel's name (the second attack's e12, l07); "platform_all" ("on YouTube[...by_platform.youtube]" when
# every item is) is out as asked; it had kept 2 true sentences of the held-out looks (DESIGN 24.4)
CELLS_LOOSE = frozenset({"title_quote", "item_channel", "own_fields", "hour_word", "handle", "month_alone",
                         "label_in_date", "quoted_title"})
# mvp25: the cells-only rules, each switchable (a CheckMode's `rules`), each kept only on a measured catch and a
# measured true-sentence cost (DESIGN 24.4; every figure IN SAMPLE). Full mode runs none of them.
CELLS_RULES = frozenset({"period_bind", "period_named", "free_date", "weekday_typed", "insight_walk",
                         "item_fields", "length_cell", "pairs_crossed", "date_owner"})
# the later reasons insight_walk counts (DESIGN 24.4, IN SAMPLE): the binding reasons (a number or a name beside
# another row, another area, another theme, another measure) and a name, word, title or link the sheet does not hold.
# Walked to on the true sentences of every set, "date", "percent" (twice), "number", "count_as_share", "filler" and
# "weekday" fell on true sentences (insight's text rules misread a window's end date, a weekday share, "163 of the
# videos"): not counted
WALK_ACCEPT = frozenset({"unnamed_owner", "bound_to_other", "bound", "wrong_area", "channel_not_in_theme",
                         "shorts_as_long", "median_of_window", "share_of_name", "wrong_group", "word", "name", "link",
                         "quote"})


@dataclass(frozen=True)
class CheckMode:
    """What the checker runs. `off`: reason codes never added (a code, or "code@emitter" for one emitter of a code
    several rules give); `loose`: the marker loosenings; `insight`: "on" (insight's checks run; a first reason that is
    off counts as none) or "off"; `rules` (mvp25): the cells-only rules of CELLS_RULES that run."""
    name: str
    off: frozenset = frozenset()
    loose: frozenset = frozenset()
    insight: str = "on"
    cells: bool = False
    rules: frozenset = frozenset()   # mvp25: the cells-only rules that run (CELLS_RULES)

    def rule(self, name):
        return name in self.rules

    def is_off(self, code, src=None):
        if not self.off:
            return False
        c = str(code).split(":")[0]
        return code in self.off or c in self.off or (src is not None and f"{c}@{src}" in self.off)


def _insight_skip(cm):
    """The reasons insight walks past in a mode (its codes that are off, alone or as "code@insight")."""
    return frozenset({x for x in cm.off if "@" not in x} | {x.split("@")[0] for x in cm.off if x.endswith("@insight")})


# the loosenings insight's reading takes (verify.insight_check, slotted)
_INSIGHT_LOOSE = frozenset({"handle", "month_alone", "label_in_date"})


def _cited_handles(markers, res):
    """The '@handles' the rows the sentence cites hold in their own fields (name, title, channel, handle), lower
    case."""
    out = set()
    for mk in markers:
        if mk.kind not in ("row", "value") or not mk.owner or mk.rid != res.rid:
            continue
        try:
            row = _resolve(res.sheet, mk.owner)
        except KeyError:
            continue
        if not isinstance(row, dict):
            continue
        for k in ("name", "title", "channel"):
            for h in re.findall(r"@[\w][\w.]*\w", str(row.get(k) or "")):
                out.add(h.lower())
        if isinstance(row.get("handle"), str) and row["handle"].strip():
            out.add("@" + row["handle"].strip().lstrip("@").lower())
    return out


def _hour_cell_after(raw, pos, markers):
    """'Hour' right before a marker of an hour cell ("Hour 18[r1.when.busiest_hours[1].hour]")."""
    return any(mk.kind == "value" and mk.key == "hour" and not raw[pos:mk.start].strip() for mk in markers)


def _hour_cells_out(raw, markers):
    """The sentence's plain lower text with every "hour N[...hour]" span taken out (an hour of the day, never watch
    time)."""
    t = list(raw)
    for mk in markers:
        if mk.kind == "value" and mk.key == "hour":
            pre = re.search(r"\bhours?\s*$", raw[:mk.start], re.I)
            for i in range(pre.start() if pre else mk.start, mk.end):
                t[i] = " "
    return strip_markers("".join(t)).lower()


def _cells_off():
    return frozenset((FRAMING_CODES - set(FRAMING_KEPT)) | {c for c, v in DOUBT_CODES.items() if v == "off"})


FULL = CheckMode("full")
CELLS = CheckMode("cells", off=_cells_off(), loose=CELLS_LOOSE, cells=True, rules=CELLS_RULES)


def check_mode(mode=None):
    """The CheckMode of `mode` ("full", "cells", a CheckMode), else of MVP_BRAIN_CHECK, else "full"."""
    if isinstance(mode, CheckMode):
        return mode
    name = mode if mode is not None else (os.environ.get(CHECK_ENV) or "full")
    name = str(name).strip().lower()
    if name == "full":
        return FULL
    if name == "cells":
        return CELLS
    if name == "values":
        return VALUES
    raise ValueError(f"{CHECK_ENV} / check mode must be one of {CHECK_MODES}, not {name!r}")

# ------------------------------------------------------------------ the marker grammar (SPEC 4.2)
PATH = r"(?:r\d+|ctx[12])(?:\.[A-Za-z_]+(?:\[\d+\])?)+"
VALUE = re.compile(r"(?P<said>[^\[\]]{1,40}?)\[(?P<path>" + PATH + r")\]")   # the spec's form (kept for reference)
CALC = re.compile(r"\[=(?P<op>diff|points|ratio|pct_change)\(\s*(?P<a>" + PATH + r")\s*,\s*(?P<b>" + PATH +
                  r")\s*\)\]")
_BRACKET = re.compile(r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]")   # one marker: its index brackets inside it
_PATH_RX = re.compile(PATH)

LEAD_MAX, SENT_MAX, POINTS_MAX, ITEMS_MAX, NOTE_MAX = I.ANSWER_MAX, I.SENT_MAX, 3, 5, 80
OUTSIDE_MAX, OUTSIDE_CHARS, UNDERSTOOD_MAX = 1, 240, 140
MOVE_MIN_POINTS = 3.0   # facts.MOVE_MIN: "up", "rose" of a share need at least 3 points

_MONTHS = I.MONTHS
_MON_RX = r"(?:" + "|".join(sorted(set(_MONTHS) | {m[:3] for m in _MONTHS} | {"sept"}, key=len, reverse=True)) + r")"
_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "eleven": 11, "twelve": 12, "a dozen": 12, "dozen": 12}
_NUM_WORD_RX = r"(?:" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r")"
_HEDGE_RX = (r"(?:just over|just under|more than|less than|fewer than|close to|about|around|nearly|almost|roughly|"
             r"over|under|some)")
_NUM_RX = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# a number typed right before a value or count marker, with its unit
NUM_TAIL = re.compile(r"(?:(?P<hedge>\b" + _HEDGE_RX + r")\s+)?(?P<sign>[+\-−])?(?P<num>" + _NUM_RX + r"|\b" +
                      _NUM_WORD_RX + r")(?P<unit>\s?%|\s?percent|\s?per cent|\s+percentage points?|\s+points?|"
                      r"\s+pts|\s+minutes?|\s+times)?\s*$", re.I)
DATE_TAIL = re.compile(r"(?P<date>\b\d{1,2}(?:st|nd|rd|th)? " + _MON_RX + r"\w*\.?(?:,? \d{4})?|\b" + _MON_RX +
                       r"\w*\.? \d{1,2}(?:st|nd|rd|th)?(?:,? \d{4})?|\b" + _MON_RX + r"\w*\.?(?: \d{4})?|"
                       r"\b(?:19|20)\d\d)\s*$", re.I)
_RATIO_WORDS = (r"(?:(?:nearly|almost|about|roughly|more than|over|just over|just under)\s+)?(?:twice|doubled|double|"
                r"doubling|tripled|triple|thrice|halved|half|a third|a quarter|" + _NUM_RX +
                r"\s+times|(?:two|three|four|five|six|seven|eight|nine|ten) times)")
CALC_TAIL = re.compile(r"(?:(?P<words>\b" + _RATIO_WORDS + r")|(?:(?P<hedge>\b" + _HEDGE_RX + r")\s+)?(?P<num>" +
                       _NUM_RX + r")(?P<unit>\s?%\s+(?:more|fewer|less)|\s?%|\s?percent|\s?per cent|\s+percentage points?|\s+points?|\s+pts|"
                       r"\s+more|\s+fewer|\s+times)?)\s*$", re.I)
HOUR_TAIL = re.compile(r"(?P<num>\d{1,2})(?::\d\d)?\s*(?P<ap>am|pm|a\.m\.|p\.m\.)\s*$", re.I)

# words of numbers that need a marker (step 3.3); "one" is left out ("the one you saved")
_NUMBERISH = re.compile(r"\d|%|\b(?:" + _NUM_WORD_RX + r"|half|halves|halved|a third|a quarter|twice|thrice|double|"
                        r"doubled|doubling|tripled|triple|quadrupled|hundreds?|thousands?|dozens?)\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_DATE_IN = re.compile(I._DATE_RX, re.I)
_SPAN_N = re.compile(r"\b(?:the\s+)?(?:last\s+|past\s+)?(\d{1,3})\s+(weeks?|days?|months?|years?)\b", re.I)

# step 3.6: capitalised words that are not names
OPENERS = {"in", "on", "inside", "lately", "right", "your", "you", "since", "over", "next", "then", "most", "both",
           "across", "during", "from", "after", "before", "of", "this", "that", "these", "those", "it", "its", "the",
           "a", "an", "and", "but", "with", "at", "among", "overall", "almost", "nearly", "about", "only", "every",
           "each", "all", "last", "mostly", "here", "there", "compared", "against", "up", "down", "what", "when",
           "where", "which", "while", "by", "for", "so", "also", "together", "behind", "close", "just", "more",
           "fewer", "less", "recently", "these", "now", "around", "between", "through", "until", "to", "outside",
           "apart", "besides", "beyond", "within", "without", "including", "like", "unlike", "as", "if", "no",
           "not", "nothing", "none", "some", "many", "much", "few", "one", "first", "second", "third", "lastly",
           "finally", "meanwhile", "still", "yet", "even", "again", "once", "today", "yesterday", "earlier",
           "later", "back", "ok", "okay", "yes", "sure", "i", "i've", "i'm", "you're", "you've", "we", "they"}
# step 3.7: outside text in a history sentence
WORLD_CLAIMS = re.compile(r"\b(?:most popular|best[- ]known|well[- ]known|famous|renowned|on youtube\b(?! (?:export|"
                          r"videos|history))|in the world|everyone|everybody|subscribers?|views\b|viewers|followers|"
                          r"trending|viral|award[- ]winning|critically)\b", re.I)
_APPOSITIVE = re.compile(r"^\s*,\s*(?:a|an|the|which|who|whose|known for|famous for|run by|made by|hosted by)\b", re.I)
# step 1 fix (the verifier audit's F42, "the channel you have followed longest"): following and subscribing are not
# in the record
_UNRECORDED = re.compile(r"\byou(?:'ve| have|'d| had)?\s+(?:\w+\s+)?(?:followed|subscribed|been following|been "
                         r"subscribed)\b|\bsubscri(?:bed|ption)\b", re.I)
_KNOWN_FOR = re.compile(r"^\s*(?:,\s*)?(?:known for|famous for|run by|hosted by)\b", re.I)
# step 3.9: claims with no marker
_CONSUME = re.compile(r"\byou(?:'ve| have|'d| had)?\s+(?:(?:first|last|also|just|recently|mostly|mainly|often|"
                      r"usually|still|only|ever|then|later)\s+)?(?:been\s+)?(?:watch\w*|open\w*|sav\w*|lik\w*|view\w*|"
                      r"into|drop\w*|stopp\w*|start\w*|switch\w*|binge\w*|spent|spend\w*|follow\w*|keep|kept|"
                      r"mostly|mainly|often|usually|always|never|rarely)\b", re.I)
_COMPARATIVE = re.compile(r"\b(?:more|less|fewer)\b|\b\w+er than\b", re.I)
# step 3.10
PSYCH = re.compile(r"\byou(?:'re| are)? (?:really |clearly |truly |must )?(?:love|adore|obsessed|hooked|addicted|"
                   r"passionate|crave|want to learn|want to be|dream|need)\b|\bobsess\w*|\byou are an?\b|\byou're an?\b|"
                   r"\byour (?:passion|personality|identity|true self)\b|\baddict\w*", re.I)
OUTCOME = re.compile(r"\bi(?:'ve| have)? (?:sent|set up|scheduled|saved|created|added|emailed|booked|made|deleted|"
                     r"turned on|turned off)\b|\b(?:done|all set)\b[.!]?$|\bsaved it\b|\bit'?s (?:done|sent|set)\b",
                     re.I)
LIMITS = re.compile(r"\b(?:can'?t|cannot|can not|unable to|don'?t have|do not have|no access|export ends|"
                    r"doesn'?t (?:record|show|include)|not recorded)\b", re.I)
WATCH_TIME = re.compile(r"(?<!busiest )(?<!peak )(?<!top )(?<!usual )\bhours?\b(?!\s+of\s+the\s+day)(?:'|’)?(?: (?:of|worth|watching|watched|spent|on))?|\bminutes? (?:of|watching|"
                        r"watched|spent)\b|\bwatch(?:ing)? time\b|\btime spent\b|\bscreen time\b|\bbinge[- ]?hours\b",
                        re.I)
_LEAST = re.compile(r"\b(?:least|fewest|barely|lowest|smallest|bottom)\b", re.I)
_RANK = re.compile(r"\b(?:led|leads|leading|leader|top|most|biggest|largest|main|number one|first place|favou?rite|"
                   r"topped|tops|came first|ahead of (?:all|every)|dominat\w*|the most)\b", re.I)
_UPW = re.compile(r"\b(?:up|rose|risen|rise|rising|grew|grown|grow|growing|climb\w*|jump\w*|gain\w*|increas\w*|"
                  r"more than doubled|doubled|tripled|higher|surg\w*)\b", re.I)
_DOWNW = re.compile(r"\b(?:down|fell|fallen|fall|falling|drop\w*|slipp\w*|declin\w*|shr[aiu]nk\w*|fad\w*|"
                    r"decreas\w*|halved|lower|cool\w*)\b", re.I)
_LATELY = re.compile(r"\b(?:lately|right now|recently|these days|nowadays|at the moment|currently)\b", re.I)
_REL_YEAR = re.compile(r"\b(this|last) (year|month|week)\b", re.I)
_SEASON = re.compile(r"\b(spring|summer|autumn|fall|winter)\b", re.I)
_BREAKS = re.compile(r"[,;:()—–]|\b(?:while|whereas|but|and|than|against|compared|versus|vs)\b", re.I)
_OF_BASE = re.compile(r"^\s*(?:of\s+(?:what|everything|all|your|the|those|these|them|it)[^,;.()]{0,60})", re.I)

COUNT_KEYS = set(I.COUNT_KEYS) | {"times_opened", "items_all_time", "rows_total"}
DATE_KEYS = set(I.DATE_KEYS) | {"date", "when", "first", "last", "saved_at", "opened_at"}
OPEN_KEYS = {"times_opened", "events", "opens"}   # counts of openings, never of distinct videos
DAY_KEYS = {"days", "days_active"}                  # counts of days, never of videos
ITEM_KEYS = {"items", "previous_items", "items_all_time", "shorts", "long", "since_items", "since_new"}
# step 1 fix (the verifier audit, F05b, FS35d): the noun said after a count is its measure's ("30[days] videos" is a
# count of days said as videos; "3[times_opened] of the clips" openings said as distinct items)
_VIDEO_NOUN = re.compile(r"^\s*(?:[\w'’-]+\s+){0,3}?(?:videos?|items?|clips?|posts?|reels?|shorts|things|ones)\b", re.I)
_DAY_NOUN = re.compile(r"^\s*(?:[\w'’-]+\s+){0,1}?days?\b", re.I)
_AVERAGE = re.compile(r"\b(?:average|averaged|on average|mean)\b", re.I)
_CLAUSE_BREAKS = re.compile(r"[,;:—–]|\b(?:while|whereas|but)\b", re.I)   # clause ends for _bare_clause
# ordinals: a rank said by place (step 1 fix, F17, F21: "came fourth" of a row tied with the next)
_ORDINAL = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
            "tenth": 10, "runner-up": 2, "runner up": 2}
_ORD_RX = re.compile(r"\b(?:" + "|".join(sorted(_ORDINAL, key=len, reverse=True)) + r")\b", re.I)
# a clause with no marker that still claims something about their history (step 1 fix, F39 "its busiest month", F37b
# "as it did the month before"): rank, peak, direction, "before" words, or a consumption verb
_CLAUSE_CLAIM = re.compile(r"\b(?:led|leads|leading|top|most|biggest|largest|busiest|peak\w*|highest|record|main|"
                           r"favou?rite|first place|number one|rose|grew|fell|dropped|up(?! to)|down|more than doubled|"
                           r"doubled|halved|best|worst|lowest|before|previous|earlier|prior|again|as it did|as before|like last|"
                           r"same as|still|also did|every (?:year|month|week))\b", re.I)
# an entity described in the present tense after its row marker, with no cell (step 1 fix, F40 "posts a new Short
# every day", F86c "is a huge channel"): what a channel is or does is outside knowledge, not their history
_ENTITY_PRESENT = re.compile(r"^\s*(?:posts|uploads|publishes|makes|creates|streams|covers|focuses|runs|releases|"
                             r"puts out|produces|specializes|specialises|is (?:a|an|one of|known|famous|popular|huge|"
                             r"big|small|massive|tiny)|has (?:a|an|over|more|millions|thousands|hundreds))\b", re.I)
# Spanish function words: the checks read English only (step 1 fix, F59, F64b, F64c); a sentence in another language
# is refused until a reader exists for it (step 2 must give the brain the turn's language)
_ES_WORDS = re.compile(r"\b(?:de|los|las|que|lo|con|del|una|el|y|más|casi|tantos|como|hizo|abriste|viste|guardaste|"
                       r"mayoría|octubre|septiembre|videos? de|en el|en la|por|para|fue|fueron|tus|tu)\b", re.I)
_EN_WORDS = re.compile(r"\b(?:the|of|you|your|and|with|was|were|what|made|opened|watched|in|on|from|than)\b", re.I)
# a search row said as the exact thing asked for: only a clear fit (step 1 fix, F94)
_EXACT = re.compile(r"\b(?:exactly|precisely|just what you|what you asked for|that's the one|is the one|found it|"
                    r"the very)\b", re.I)
SHARE_EXTRA = {"faded_from", "faded_to", "grew_from", "grew_to"}
ADDED_KEYS = ("ref", "change_pts", "third_party_text")   # keys results.present() adds; insight never sees them
NON_SHEET_TOOLS = ("find", "search", "learned")
NAME_LISTS_SKIP = {"periods", "busiest_hours", "eras", "items", "examples", "so_what_candidates", "offers", "points",
                   "sources", "options", "matches"}

REASON_TEXT = {
    "bad_ref": "a marker that names no cell of this turn's results",
    "bad_marker": "a marker with no number or name right before it",
    "two_results": "one sentence cites two results; compare two windows through one compare result",
    "uncited_number": "a number with no marker right after it",
    "wrong_value": "the number typed is not the cell's value",
    "wrong_measure": "a percent cited to a count, or a count to a share",
    "wrong_name": "the name before a row marker is not that row's name",
    "calc": "the computed number is not what the two cells give",
    "direction": "the direction word does not fit the cited values",
    "unknown_name": "a name that is not in the results",
    "uncited_name": "a name of the library with no marker in the sentence",
    "outside_in_history": "outside knowledge inside a history sentence (put it in outside)",
    "uncited_claim": "a claim about what they watched with no marker",
    "psych": "a claim about their feelings or who they are, or a guess at why they opened something",
    "outcome": "a claim that something was done",
    "limits": "talk of limits (code writes those lines)",
    "sensitive": "a sensitive topic",
    "least": "'least' needs the first row of a result ordered by least, over every entity",
    "rank": "a rank word that the cited result does not support",
    "tie": "a rank word on a tie",
    "repeat": "the same cells said again",
    "wrong_window": "the window words are not the cited result's window",
    "window_missing": "the lead does not name its window",
    "too_long": "too long",
    "watch_time": "watch time is never said",
    "filter_dropped": "a count said without the filter it was counted with",
    "one_value": "a change said with one value",
    "base": "the base said is not the result's base",
    "base_missing": "a share said without its base",
    "insight_rewrite": "the sentence would need code's words added to be true",
    "not_item": "an item ref that is not an item row of this turn's results",
    "weak_fit": "a weak match presented as the thing asked for",
    "point_text": "a learned point is only its marker",
    "wrong_group": "a row placed in a group its own row does not name",
    "language": "the checks read English only: write the sentence in English",
    "first_last": "a first or a last is said by the date of the result's first item",
    "private_total": "an 'all' claim on a result that left private topics out",
    "platform_word": "a count of every platform said as one platform's",
}


# ------------------------------------------------------------------ the answer form (SPEC 3.6)
class ItemPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    note: Optional[str] = None


class ChartPick(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    list: Literal["areas", "themes", "channels", "periods"]
    value: Literal["share", "items"]


class OutsideLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    about: str
    text: str
    source: str


class AskBack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    between: list[str]


class OfferPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["exclude", "only", "length_long", "length_any", "window", "by_month", "examples"]
    ref: Optional[str] = None
    window_words: Optional[str] = None


class SetupPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers_step: bool
    own_words: Optional[str] = None


class HandBack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reminder", "todo", "email_other", "app", "cancel", "library_rule", "setting", "other"]
    words: str


class AnswerForm(BaseModel):
    """The `give_answer` form. Sizes are checked in `check_answer` (a breach fails that field, not the form)."""
    model_config = ConfigDict(extra="forbid")
    understood: str = ""
    lead: str = ""
    points: list[str] = []
    items: list[ItemPick] = []
    chart: Optional[ChartPick] = None
    outside: list[OutsideLine] = []
    ask_back: Optional[AskBack] = None
    offers: list[OfferPick] = []
    setup: Optional[SetupPick] = None
    corrects_previous: bool = False
    hand_back: Optional[HandBack] = None


@dataclass
class Turn:
    """What the verifier knows of the turn besides the results: their message, the topic the turn unlocked, the
    screen, today, and extra names of their library (the person's name index; the results' own names are added)."""
    message: str = ""
    unlock: Optional[str] = None
    screen: str = ""
    today: Optional[date] = None
    names: list[str] = field(default_factory=list)
    sensitive_names: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, tturn):
        """The verifier's turn from the tools' turn (brain/tools.Turn): the same message, screen, today and unlock
        (code's, from their message), and the person's name index from the library the tools read: the areas,
        themes, channels and collections they may see as `names`, the channels hidden as sensitive as
        `sensitive_names` (a hidden channel is never offered; naming it fails step 3.11 unless its topic is the
        turn's unlock). Duck-typed: verify does not import the tools."""
        names, sens = [], []
        lib = getattr(tturn, "lib", None) if getattr(tturn, "bot", None) is not None else None
        if lib is not None:
            from . import names as N
            names += sorted(set(N._area_words(lib).values()))
            names += [nm for _t, nm, _w in N._themes(lib)]
            for nm, hidden in sorted(N._channels(lib).items()):
                (sens if hidden else names).append(nm)
            names += sorted(N._collections(lib).values())
        return cls(message=getattr(tturn, "message", "") or "", unlock=getattr(tturn, "unlock", None),
                   screen=getattr(tturn, "screen", "") or "", today=getattr(tturn, "today", None),
                   names=[n for n in names if isinstance(n, str) and len(n) >= 2],
                   sensitive_names=[n for n in sens if isinstance(n, str) and len(n) >= 2])


@dataclass
class Marker:
    kind: str                 # value | row | calc | count
    start: int                # the said text's start
    end: int                  # the marker's end
    mstart: int               # the bracket's start
    said: str = ""
    path: str = ""            # the full path (r1.channels[0].items)
    rid: str = ""
    rest: str = ""            # the path inside the result (channels[0].items)
    value: Any = None
    key: str = ""
    owner: Optional[str] = None   # the row the cell belongs to (channels[0])
    op: str = ""
    a: str = ""
    b: str = ""
    hedge: str = ""
    num: Optional[float] = None
    unit: str = ""
    sign: str = ""            # a sign typed before the number ("+16 points")


@dataclass
class Outcome:
    where: str                # lead | point | note | outside
    index: int
    text: str                 # as the model wrote it (markers in)
    sent: Optional[str] = None   # as it would go out (markers out); None when dropped
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)   # what is true, for the repair text
    cells: dict = field(default_factory=dict)          # cited path -> value
    rid: Optional[str] = None
    hidden_rank: bool = False
    layer: Optional[str] = None   # where it failed: "marker" (verify's own steps) or "insight" (step 3.8)
    insight: Optional[str] = None  # insight's own verdict on the sentence (step 3.8), when it ran
    notes: dict = field(default_factory=dict)   # reason -> its first detail (the repair text's words)
    flags: list = field(default_factory=list)   # mvp26, values mode only: [{"code", "mode"}] that refuse nothing

    @property
    def kept(self):
        return not self.reasons


@dataclass
class Verdict:
    outcomes: list[Outcome]
    items: list[dict] = field(default_factory=list)       # {ref, note, kept, reasons}
    outside: list[dict] = field(default_factory=list)     # {about, text, kept, reasons}
    chart: Optional[dict] = None
    form_error: Optional[str] = None
    private_line: bool = False   # SPEC 4.3 step 13: code's scope line adds "Leaving out topics you keep private."
    repair: bool = False
    version: str = VERIFY_VERSION
    check: str = "full"          # the checker's mode (mvp24): "full" or "cells"

    @property
    def lead(self):
        return [o for o in self.outcomes if o.where == "lead"]

    @property
    def lead_ok(self):
        return bool(self.lead) and all(o.kept for o in self.lead)

    def kept_text(self, where):
        return [o.sent for o in self.outcomes if o.where == where and o.kept]

    def reason_counts(self):
        out = {}
        for o in self.outcomes:
            for r in o.reasons:
                out[r] = out.get(r, 0) + 1
        return out


# ------------------------------------------------------------------ the ledger
def _strip_added(o):
    if isinstance(o, dict):
        return {k: _strip_added(v) for k, v in o.items() if k not in ADDED_KEYS}
    if isinstance(o, list):
        return [_strip_added(v) for v in o]
    return o


def _segs(rest):
    return I._path_segs(rest)


def _resolve(sheet, rest):
    return I._resolve_raw(sheet, _segs(rest))


class Result:
    def __init__(self, env):
        self.env = env
        self.rid = env.get("rid")
        self.tool = env.get("tool") or ""
        self.meta = env.get("meta") or {}
        self.sheet = env.get("sheet") or {}
        self.is_sheet = self.tool not in NON_SHEET_TOOLS and bool(self.sheet.get("kind"))
        self._k = None
        self._facts = None
        self.names = _names_of(self.sheet)

    @property
    def sheet_k(self):
        """The sheet as insight reads it: without the keys the tools add."""
        if self._k is None:
            self._k = {k: v for k, v in _strip_added(self.sheet).items() if k not in ("hidden", "ranked")}
        return self._k

    @property
    def facts(self):
        if self._facts is None:
            self._facts = I.Facts(self.sheet_k)
        return self._facts

    def window(self):
        w = self.sheet.get("window") or {}
        return _as_d(w.get("start")), _as_d(w.get("end"))

    def prev_window(self):
        p = self.sheet.get("previous") or {}
        a, b = _as_d(p.get("start")), _as_d(p.get("end"))
        if a and b:
            return a, b
        w = str(p.get("words") or "").strip()
        my = re.fullmatch(r"(?:in\s+)?([A-Za-z]+)\s+((?:19|20)\d\d)", w)
        if my and my.group(1).lower() in _MONTHS:   # "September 2026": the whole month
            mi, y = _MONTHS.index(my.group(1).lower()) + 1, int(my.group(2))
            nxt = date(y + (mi == 12), mi % 12 + 1, 1)
            return date(y, mi, 1), date.fromordinal(nxt.toordinal() - 1)
        if re.fullmatch(r"(?:19|20)\d\d", w):
            return date(int(w), 1, 1), date(int(w), 12, 31)
        m = re.search(r"\((\d{1,2}) (\w+)(?: (\d{4}))? to (\d{1,2}) (\w+) (\d{4})\)", str(p.get("words") or ""))
        if m:
            try:
                y2 = int(m.group(6))
                b = date(y2, _MONTHS.index(m.group(5).lower()) + 1, int(m.group(4)))
                y1 = int(m.group(3)) if m.group(3) else y2
                a = date(y1, _MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
                return a, b
            except ValueError:
                return None
        return None


def _as_d(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v[:10]).date()
        except ValueError:
            return None
    return None


def _names_of(sheet):
    """[(name, row path)] of every named row of a sheet (areas, themes, channels, fields, topics, nested rows, the
    new and stopped lists), periods, items and examples left out (their labels are times, their titles third-party)."""
    out = []

    def walk(o, path, top):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in NAME_LISTS_SKIP or k in ("window", "filters", "when", "totals", "previous", "question"):
                    continue
                walk(v, (path + "." if path else "") + k, top)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                p = f"{path}[{i}]"
                if isinstance(v, dict):
                    nk = I._record_name_key(v)
                    if nk and nk != "title" and isinstance(v.get(nk), str):
                        out.append((v[nk].strip(), p))
                    walk(v, p, False)
                elif isinstance(v, str) and v.strip():
                    out.append((v.strip(), p))
    walk(sheet, "", True)
    return [(n, p) for n, p in out if len(n) >= 2]


class Ledger:
    """Every result of the turn by rid (a list of envelopes, or a dict rid -> envelope; `ctx1`, `ctx2` count)."""

    def __init__(self, results):
        envs = list(results.values()) if isinstance(results, dict) else list(results or [])
        self.by_rid = {}
        for e in envs:
            if isinstance(e, dict) and e.get("rid"):
                self.by_rid[e["rid"]] = Result(e)

    def get(self, rid):
        return self.by_rid.get(rid)

    def all_names(self):
        out = {}
        for r in self.by_rid.values():
            for n, p in r.names:
                out.setdefault(_low(n), []).append((r.rid, p, n))
        return out


def _low(s):
    return " ".join(str(s or "").lower().split())


# ------------------------------------------------------------------ parse (SPEC 4.2)
def _measure(rest, v):
    key = _segs(rest)[-1][0] if _segs(rest) else ""
    if isinstance(v, bool):
        return key, "bad"
    if key in I.LENGTH_KEYS:
        return key, "watch_time"
    if isinstance(v, str):
        if key in DATE_KEYS or (_as_d(v) and re.match(r"^\d{4}-\d\d-\d\d", v)):
            return key, "date"
        return key, "name"
    if not isinstance(v, (int, float)):
        return key, "bad"
    if key.endswith("share") or key in SHARE_EXTRA:
        return key, "share"
    if key == "change_pts" or key == "change":
        return key, "points"
    if key == "change_vs_previous":
        return key, "points"
    if key in I.HOUR_KEYS:
        return key, "hour"
    if key == "times":
        return key, "times"
    return key, "count"


def _points_of(rest, v):
    """A cell's value in percentage points (area rows carry change_vs_previous as a fraction, SPEC 2.3)."""
    key = _segs(rest)[-1][0]
    if key == "change_vs_previous" and (re.match(r"^(?:areas|top_areas|areas_change)\[", rest) or abs(v) <= 1):
        # areas carry it as a fraction (SPEC 2.3); older sheets carry a theme's as a fraction too (insight's own rule,
        # `_fmt_value`: a value of at most 1 is a fraction; a move under 1 point is never said)
        return float(v) * 100
    return float(v)


def _owner(rest):
    segs = _segs(rest)
    last = max((n for n, (_k, i) in enumerate(segs) if i is not None), default=None)
    return None if last is None else I._path_str(segs[:last + 1])


def _num_of(tok):
    t = tok.strip().lower()
    if t in _NUM_WORDS:
        return float(_NUM_WORDS[t])
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def parse(sentence, ledger, loose=frozenset()):
    """([Marker], [reason]) of one sentence. A bracket that is not a path, a calc of two paths or a count fails
    `bad_ref` (a calc with a literal number inside does not parse); a path that does not resolve in the ledger fails
    `bad_ref`; braces (insight's slots) are not part of this grammar and fail `bad_ref`. `loose` (cells mode only):
    the row-name loosenings of CELLS_LOOSE."""
    out, bad = [], []
    if re.search(r"[{}]", sentence):
        bad.append("bad_ref")
    spans = list(_BRACKET.finditer(sentence))
    rest_txt = _BRACKET.sub(" ", sentence)
    if "[" in rest_txt or "]" in rest_txt:
        bad.append("bad_ref")
    prev_end = 0
    for m in spans:
        body = m.group(0)[1:-1]
        prefix = sentence[prev_end:m.start()]
        cm = CALC.fullmatch(m.group(0))
        if cm:
            mk = Marker("calc", m.start(), m.end(), m.start(), op=cm.group("op"), a=cm.group("a"), b=cm.group("b"))
            ok = True
            for p in (mk.a, mk.b):
                r = ledger.get(p.split(".", 1)[0])
                try:
                    v = _resolve(r.sheet, p.split(".", 1)[1]) if r else None
                except KeyError:
                    v = None
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    ok = False
            if not ok:
                bad.append("bad_ref")
                prev_end = m.end()
                continue
            mk.rid = mk.a.split(".", 1)[0]
            t = CALC_TAIL.search(prefix)
            if t:
                mk.start = prev_end + t.start()
                mk.said = t.group(0).strip()
                mk.hedge = (t.group("hedge") or "").lower()
                if t.group("num"):
                    mk.num = _num_of(t.group("num"))
                    mk.unit = (t.group("unit") or "").strip().lower()
            out.append(mk)
            prev_end = m.end()
            continue
        if not re.fullmatch(PATH, body):
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        rid, rest = body.split(".", 1)
        r = ledger.get(rid)
        if r is None:
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        if rest.endswith(".count") or rest == "count":
            lp = rest[:-len(".count")] if rest != "count" else ""
            try:
                lst = _resolve(r.sheet, lp) if lp else None
            except KeyError:
                lst = None
            if not isinstance(lst, list):
                bad.append("bad_ref")
                prev_end = m.end()
                continue
            mk = Marker("count", m.start(), m.end(), m.start(), path=body, rid=rid, rest=rest, value=len(lst))
            t = NUM_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
                mk.num, mk.unit = _num_of(t.group("num")), (t.group("unit") or "").strip().lower()
                mk.hedge = (t.group("hedge") or "").lower()
            out.append(mk)
            prev_end = m.end()
            continue
        try:
            v = _resolve(r.sheet, rest)
        except KeyError:
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        segs = _segs(rest)
        if isinstance(v, dict) and segs and segs[-1][1] is not None:
            mk = Marker("row", m.start(), m.end(), m.start(), path=body, rid=rid, rest=rest, value=v, owner=rest)
            names = _row_names(v, rest)
            pfx = prefix
            if loose:
                names, pfx = _loose_names(names, v, rest, prefix, loose)
            low = _low(pfx)
            hit = next((n for n in sorted(names, key=len, reverse=True) if low.endswith(_low(n))), None)
            if hit is not None:
                # the said name's start in the original prefix (case and spacing as typed)
                mt = re.search(r"\s+".join(re.escape(w) for w in hit.split()) + r"\s*$", pfx, re.I)
                if mt:
                    mk.start, mk.said = prev_end + mt.start(), prefix[mt.start():].strip()
            out.append(mk)
            prev_end = m.end()
            continue
        if isinstance(v, (dict, list)) or v is None:
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        key, meas = _measure(rest, v)
        mk = Marker("value", m.start(), m.end(), m.start(), path=body, rid=rid, rest=rest, value=v, key=key,
                    owner=_owner(rest))
        if meas == "name":
            t = re.search(r"\s+".join(re.escape(w) for w in str(v).split()) + r"\s*$", prefix, re.I)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
        elif meas == "date":
            t = DATE_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
        elif meas == "hour":
            t = HOUR_TAIL.search(prefix) or NUM_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
        else:
            t = NUM_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
                mk.num, mk.unit = _num_of(t.group("num")), (t.group("unit") or "").strip().lower()
                mk.hedge = (t.group("hedge") or "").lower()
                mk.sign = t.group("sign") or ""
        out.append(mk)
        prev_end = m.end()
    return out, bad


def _loose_names(names, v, rest, prefix, loose):
    """cells mode (mvp23 record/d1b.txt, in sample): the names that may stand before a row marker, and the prefix read.
    title_quote: a title in quotes, or the title without its trailing '#n'; item_channel: an item's own channel;
    short_word: 'a short' / 'a long video' for an item of that length."""
    names = list(names)
    pfx = prefix
    if "title_quote" in loose:
        pfx = re.sub(r"[\"“”]\s*$", "", prefix)
        names += [re.sub(r"\s*#\s*\d+\s*$", "", n) for n in names if re.search(r"#\s*\d+\s*$", n)]
    item = bool(re.match(r"^items\[\d+\]$", rest))
    if "item_channel" in loose and item and isinstance(v.get("channel"), str):
        names.append(v["channel"])
    if "short_word" in loose and item and v.get("length") in ("short", "long"):
        names += ["a short", "a Short"] if v["length"] == "short" else ["a long video", "a long one"]
    return names, pfx


def _bad_detail(sentence, ledger):
    """The repair text for a bracket that is no marker, as exact as code can make it (the live probe's shapes:
    `[r1.sheet.totals.items]`, `[r1.meta.window_said]`, a rid with no result)."""
    if re.search(r"[{}]", sentence):
        return "braces are not markers: type the number, then [r1.path]"
    for m in _BRACKET.finditer(sentence):
        body = m.group(0)[1:-1].strip()
        if body.startswith("="):
            continue
        rid = body.split(".", 1)[0]
        if re.fullmatch(r"r\d+|ctx[12]", rid) and ledger.get(rid) is None:
            return f"{rid} is not a result with numbers in this turn"
        if re.match(r"^(?:r\d+|ctx[12])\.(?:sheet|meta)\.", body):
            fixed = re.sub(r"^((?:r\d+|ctx[12]))\.sheet\.", r"\1.", body)
            if ".meta." in body:
                return f"'{_clip(body, 40)}': meta is not cited; window words need no marker"
            return f"'{_clip(body, 40)}': a path starts after the result id, without 'sheet.' ({_clip(fixed, 40)})"
    return "a bracket that is not a marker of this turn's results"


def _row_names(row, rest):
    names = []
    for k in ("name", "title", "label", "theme", "channel"):
        if isinstance(row.get(k), str) and row[k].strip():
            names.append(row[k].strip())
            break
    if re.match(r"^(?:areas|top_areas)\[", rest) and names:
        names += _area_aliases(names[0])
    return names


def _area_aliases(name):
    """The words an area may be called by beside its own name: a whole word of the name ("cooking" for "food and
    cooking", "art" for "art and design"). themes.CATEGORY_WORDS is wider ("painting", "drawing" for art and design,
    which are themes' names too); the code-owned alias table of SPEC 2.2 (names.py) replaces this when it exists."""
    from .. import themes as T
    own = set(_low(name).split()) - {"and", "the", "of", "&"}
    return [w for w in (T.CATEGORY_WORDS or {}).get(_low(name), ()) if w in own]


def strip_markers(sentence, markers=None):
    """The sentence as it goes out: every marker removed, the words and numbers typed before it kept."""
    s = CALC.sub("", sentence)
    s = _BRACKET.sub("", s)
    s = re.sub(r"\s+([,.;:!?)])", r"\1", s)
    return " ".join(s.split())


# ------------------------------------------------------------------ the value checks (step 3.4, 3.5)
def _hedge_ok(said, cell, hedge, tol_abs):
    """A typed number against a cell with a hedge's direction: "over" / "more than" need the cell above it, "nearly" /
    "almost" / "under" below it."""
    h = (hedge or "").lower()
    if h in ("over", "more than", "just over"):
        return cell >= said - 1e-9 and cell - said <= tol_abs
    if h in ("under", "less than", "fewer than", "nearly", "almost", "just under"):
        return cell <= said + 1e-9 and said - cell <= tol_abs
    return abs(cell - said) <= tol_abs


def check_value(mk):
    """None, or (reason, detail) for one value or count marker."""
    if mk.kind == "count":
        if mk.num is None:
            return "bad_marker", f"{mk.path} = {mk.value}"
        if mk.unit:
            return "wrong_measure", f"{mk.path} is a count ({mk.value})"
        if mk.num != mk.value:
            return "wrong_value", f"'{mk.said}' is {mk.path} = {mk.value}"
        return None
    key, meas = _measure(mk.rest, mk.value)
    v = mk.value
    if meas == "watch_time":
        return "watch_time", f"{mk.path} is a length total, never said"
    if meas == "bad":
        return "bad_ref", f"{mk.path} is not a value"
    if meas == "name":
        if not mk.said or _low(mk.said) != _low(v):
            if _segs(mk.rest)[-1][0] in ("title", "text", "why_matched", "caption"):
                return "wrong_name", f"the words before {mk.path} are not that cell's text"
            return "wrong_name", f"{mk.path} = '{_clip(v)}'"
        return None
    if meas == "date":
        return _date_ok(mk)
    if meas == "hour":
        if not mk.said:
            return "bad_marker", f"{mk.path} = {v}"
        m = HOUR_TAIL.search(mk.said)
        h = int(m.group("num")) % 12 + (12 if m and m.group("ap").lower().startswith("p") else 0) if m else \
            _num_of(mk.said)
        hv = v.get("hour") if isinstance(v, dict) else v
        return None if h is not None and int(h) == int(hv) else ("wrong_value", f"{mk.path} = {hv}")
    if mk.num is None:
        return "bad_marker", f"{mk.path} = {_fmt(mk.rest, v)}"
    hedged = bool(mk.hedge)
    unit = mk.unit
    if meas == "share":
        if not unit or "point" in unit or unit == "pts":
            return "wrong_measure", f"{mk.path} is a share = {v} ({_fmt(mk.rest, v)})"
        if not _hedge_ok(mk.num, float(v) * 100, mk.hedge, 1.5 if hedged else 0.5):
            return "wrong_value", f"'{mk.said}' is {mk.path} = {round(float(v), 4)} ({_fmt(mk.rest, v)})"
        return None
    if meas == "points":
        if unit and ("%" in unit or "percent" in unit or "per cent" in unit):
            return "wrong_measure", f"{mk.path} is in points ({_fmt(mk.rest, v)})"
        pts = abs(_points_of(mk.rest, v))
        if not _hedge_ok(abs(mk.num), pts, mk.hedge, 1.5 if hedged else 0.5):
            return "wrong_value", f"'{mk.said}' is {mk.path} = {round(pts, 1)} points"
        return None
    if meas == "times":
        return None if abs(mk.num - float(v)) <= max(0.1 * float(v), 0.05) else \
            ("wrong_value", f"{mk.path} = {round(float(v), 2)}")
    # counts
    if (unit.startswith("minute") and key == "long_median_min") or (unit == "times" and key in OPEN_KEYS):
        unit = ""
    if unit:
        return "wrong_measure", f"{mk.path} is a count ({_fmt(mk.rest, v)})"
    if not hedged:
        if mk.num != float(v):
            return "wrong_value", f"'{mk.said}' is {mk.path} = {_fmt(mk.rest, v)}"
        return None
    if not (float(v) and _hedge_ok(mk.num, float(v), mk.hedge, 0.1 * float(v))):
        return "wrong_value", f"'{mk.said}' is {mk.path} = {_fmt(mk.rest, v)}"
    return None


def _date_ok(mk):
    d = _as_d(mk.value)
    if not mk.said or d is None:
        return "bad_marker", f"{mk.path} = {mk.value}"
    s = mk.said.lower()
    ys = re.findall(r"\b((?:19|20)\d\d)\b", s)
    mo = re.search(r"\b(" + _MON_RX + r")", s)
    dm = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)", re.sub(r"\b(?:19|20)\d\d\b", " ", s))
    ok = True
    if ys and int(ys[0]) != d.year:
        ok = False
    if mo:
        mi = next(i for i, m in enumerate(_MONTHS) if m.startswith(mo.group(1)[:3]))
        if mi + 1 != d.month:
            ok = False
    if dm and mo and int(dm.group(1)) != d.day:
        ok = False
    return None if ok else ("wrong_value", f"'{mk.said}' is {mk.path} = {d.day} {_MONTHS[d.month - 1].title()} "
                                           f"{d.year}")


def _fmt(rest, v):
    key = _segs(rest)[-1][0] if _segs(rest) else ""
    if key == "change_pts":
        return f"{round(abs(float(v)))} points"
    t = I._fmt_value(key, v)
    return t if t is not None else str(v)


def _clip(s, n=60):
    s = re.sub(r"[\[\]{}<>]", " ", " ".join(str(s or "").split()))
    return s if len(s) <= n else s[:n - 1] + "…"


_RATIO_BANDS = [(re.compile(r"^(?:nearly|almost) (?:twice|doubled|double|doubling)$"), 1.7, 2.0),
                (re.compile(r"^(?:twice|doubled|double|doubling)$"), 1.8, 2.2),
                (re.compile(r"^(?:more than|over|just over) (?:twice|doubled|double|doubling)$"), 2.0, 2.6),
                (re.compile(r"^(?:nearly|almost) (?:tripled|triple|thrice|three times)$"), 2.6, 3.0),
                (re.compile(r"^(?:tripled|triple|thrice|three times)$"), 2.7, 3.3),
                (re.compile(r"^(?:four times)$"), 3.6, 4.4),
                (re.compile(r"^(?:halved|half)$"), 0.45, 0.55),
                (re.compile(r"^(?:nearly|almost) (?:halved|half)$"), 0.5, 0.6),
                (re.compile(r"^a third$"), 0.3, 0.37),
                (re.compile(r"^a quarter$"), 0.22, 0.28)]


def _cell(ledger, p):
    rid, rest = p.split(".", 1)
    return _resolve(ledger.get(rid).sheet, rest), rest


def _family(rest):
    key = _segs(rest)[-1][0]
    if key in OPEN_KEYS:
        return "opens"
    if key.endswith("share") or key in SHARE_EXTRA:
        return "share"
    if key in ("change_pts", "change_vs_previous", "change"):
        return "points"
    if key in I.LENGTH_KEYS:
        return "length"
    return "count"


def _is_before(rest):
    key = _segs(rest)[-1][0]
    return rest.startswith("previous.") or key.startswith("previous_") or key in ("faded_from", "grew_from",
                                                                                   "from_share")


_CLOSE = re.compile(r"\b(?:close behind|right behind|just behind|not far behind|a close second|close second|"
                    r"neck and neck|nearly level|almost level|almost as (?:many|much)|nearly as (?:many|much)|"
                    r"close to|hot on)\b", re.I)
CLOSE_RATIO = 0.8   # "close behind": the second value at least four fifths of the first


def _close_check(low, markers, res):
    """'close behind' and its kin: the two values said (or the row and the row above it) within a fifth."""
    if not _CLOSE.search(low) or res is None:
        return None
    vals = [(mk.owner, mk.key, float(mk.value)) for mk in markers if mk.kind == "value" and mk.owner and
            isinstance(mk.value, (int, float)) and _family(mk.rest) in ("count", "share")]
    pairs = []
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            if a[1] == b[1] and a[0] != b[0]:
                pairs.append((a[2], b[2]))
    if not pairs:
        for ow, key, v in vals:
            m = re.match(r"^(.*)\[(\d+)\]$", ow)
            if m and int(m.group(2)) > 0:
                try:
                    above = _resolve(res.sheet, f"{m.group(1)}[{int(m.group(2)) - 1}].{key}")
                except KeyError:
                    continue
                if isinstance(above, (int, float)):
                    pairs.append((float(above), v))
    for a, b in pairs:
        hi, lo = max(a, b), min(a, b)
        if hi and lo / hi < CLOSE_RATIO:
            return "not_close", f"'close' needs the two within a fifth: {round(lo, 4)} against {round(hi, 4)}"
    return None


def check_calc(mk, ledger, clause):
    """None, or (reason, detail): the op computed from the two cells, the typed number or words against it, and the
    direction words of its clause against its sign."""
    (va, ra), (vb, rb) = _cell(ledger, mk.a), _cell(ledger, mk.b)
    fa, fb = _family(ra), _family(rb)
    if "length" in (fa, fb):
        return "watch_time", "a length total is never said"
    va, vb = float(va), float(vb)
    op = mk.op
    det = f"{mk.a} = {round(va, 4)}, {mk.b} = {round(vb, 4)}"
    if op in ("diff", "pct_change") and (fa != "count" or fb != "count"):
        return "wrong_measure", f"{op} needs two counts of videos; {det}"
    if op == "points" and (fa != "share" or fb != "share"):
        return "wrong_measure", f"points needs two shares; {det}"
    if op == "ratio" and (fa != fb or fa not in ("count", "share")):
        return "wrong_measure", f"ratio needs two counts or two shares; {det}"
    if _is_before(ra) and not _is_before(rb):
        # the value of the period before goes second: "up" is now against before, never the other way round
        return "calc", f"{op}(now, before): {mk.b} is now, {mk.a} is the period before; {det}"
    if op == "diff":
        val = va - vb
    elif op == "points":
        val = (va - vb) * 100
    elif op == "pct_change":
        if vb == 0:
            return "calc", f"pct_change from 0; {det}"
        val = (va - vb) / vb * 100
    else:
        if vb == 0:
            return "calc", f"ratio over 0; {det}"
        val = va / vb
    said = (mk.said or "").lower()
    up, down = bool(_UPW.search(clause)), bool(_DOWNW.search(clause))
    if op == "ratio":
        words = " ".join(said.split())
        if mk.num is not None and (mk.unit or "").strip() == "times":
            if abs(mk.num - val) > 0.1 * val:
                return "calc", f"{mk.a} / {mk.b} = {round(val, 2)}"
        elif mk.num is not None:
            return "calc", f"a ratio is said in words or 'N times'; {mk.a} / {mk.b} = {round(val, 2)}"
        else:
            nt = re.match(r"^(?:(nearly|almost|about|roughly) )?(\S+) times$", words)
            if nt:
                n = _num_of(nt.group(2))
                if n is None or abs(n - val) > 0.1 * n:
                    return "calc", f"{mk.a} / {mk.b} = {round(val, 2)}"
            else:
                band = next(((lo, hi) for rx, lo, hi in _RATIO_BANDS if rx.match(words)), None)
                if band is None:
                    return "calc", f"{mk.a} / {mk.b} = {round(val, 2)}"
                if not (band[0] <= val <= band[1]):
                    return "calc", f"'{words}' needs {band[0]} to {band[1]}; {mk.a} / {mk.b} = {round(val, 2)}"
        if (up and val <= 1) or (down and val >= 1) or (re.search(r"doubl|tripl|twice|times", words) and val < 1) or \
                (re.search(r"halv|half|third|quarter", words) and val > 1):
            return "direction", f"{mk.a} / {mk.b} = {round(val, 2)}"
        return None
    if mk.num is None:
        return "bad_marker", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    tol = 0.0 if op == "diff" else (0.5 if op == "points" else 1.0)
    if mk.hedge:
        tol = max(tol, 1.5 if op == "points" else abs(val) * 0.1)
    if abs(abs(mk.num) - abs(val)) > tol + 1e-9:
        return "calc", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    if op == "points" and (mk.unit or "") and ("%" in mk.unit or "percent" in mk.unit):
        return "wrong_measure", f"a change of two shares is in points: {round(val, 1)} points"
    if op == "pct_change" and not (mk.unit and ("%" in mk.unit or "percent" in mk.unit)):
        return "wrong_measure", f"a percent change is said with %: {round(val)}%"
    if up and down:
        return None
    if up and (val <= 0 or (op == "points" and val < MOVE_MIN_POINTS)):
        return "direction", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    if down and (val >= 0 or (op == "points" and -val < MOVE_MIN_POINTS)):
        return "direction", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    if op == "pct_change" and ((re.search(r"\bmore\b", said) and val < 0) or
                               (re.search(r"\b(?:fewer|less)\b", said) and val > 0)):
        # mvp20 fix (the attack's G02: "45% fewer[=pct_change(2023, 2022)]" of +45%): the word typed with the number
        return "direction", f"pct_change = {round(val)}%"
    if re.search(r"\bmore\b", said + " " + clause) and val < 0 and op == "diff":
        return "direction", f"diff = {round(val)}"
    if re.search(r"\b(?:fewer|less)\b", said + " " + clause) and val > 0 and op == "diff":
        return "direction", f"diff = {round(val)}"
    return None


def _cross_row_move(mk):
    """cells mode (mvp24, the attack's V05: "Gaming rose 29 points[=points(r1.areas[0].share,
    r1.areas[2].previous_share)]"): a change that sets one row's value now against ANOTHER row's value before is bound
    to no row's move. Read from the two paths only."""
    if mk.op not in ("diff", "points", "pct_change"):
        return None
    ra, rb = mk.a.split(".", 1)[1], mk.b.split(".", 1)[1]
    oa, ob = _owner(ra), _owner(rb)
    if oa and ob and oa != ob and _is_before(ra) != _is_before(rb):
        return "calc", f"{mk.op}({mk.a}, {mk.b}) sets {oa} now against {ob} before: a change is of one row"
    return None


def _mixed_move(markers):
    """cells mode (mvp24, the planted v5_112: "Speed runs[r1.themes[1]] climbed to 9%[r1.themes[1].share] from
    27[r1.themes[1].previous_items] videos before"): a row said with a value now and a value before says them in one
    measure; a before value with no now value of its own measure (a count against a share) is bound to the wrong
    measure. Read from the paths only."""
    groups = {}
    for mk in markers:
        if mk.kind != "value" or isinstance(mk.value, (str, bool)) or not isinstance(mk.value, (int, float)):
            continue
        fam = _family(mk.rest)
        if fam not in ("count", "share"):
            continue
        own = mk.owner   # a row's own cells only (the window's totals and previous may be said apart)
        if own is None:
            continue
        g = groups.setdefault((mk.rid, own), (set(), set()))
        g[1 if _is_before(mk.rest) else 0].add(fam)
    for (rid, own), (now, before) in groups.items():
        if now and before and not (now & before):
            return "wrong_measure", f"{rid}.{own}: a value before in {'/'.join(sorted(before))} against a value " \
                                    f"now in {'/'.join(sorted(now))}: say both in one measure"
    return None


def _window_median_of_row(markers, res):
    """cells mode (mvp24): insight's own binding rule (b), "the window's median long video said next to one record",
    read from the paths, so that no framing reason insight gives first can hide it (the compound probe p17: "Speed
    runs[r1.themes[1]] led on 18 days, and its long videos ran about 23[r1.totals.long_median_min] minutes")."""
    if res is None or not res.is_sheet or not any(mk.kind == "value" and mk.rest == "totals.long_median_min"
                                                   for mk in markers):
        return None
    for mk in markers:
        if mk.kind in ("row", "value") and mk.owner and mk.rid == res.rid and \
                not I._is_question_topic(res.sheet_k, mk.owner):
            return "median_of_window", f"{res.rid}.totals.long_median_min is the window's median, not {mk.owner}'s"
    return None


def _platform_all(raw, mk, ledger):
    """cells mode (mvp23 D1b, in sample): 'on YouTube[r1.totals.by_platform.youtube]', a marker after a word with no
    number, when that cell equals the result's totals.items (every item is on that platform)."""
    if not re.search(r"(?:^|\.)by_platform\.(youtube|instagram)$", mk.rest or ""):
        return False
    if not re.search(r"\bon (?:youtube|instagram)\s*$", raw[:mk.start], re.I):
        return False
    if not re.search(mk.rest.rsplit(".", 1)[1], raw[max(0, mk.start - 12):mk.start], re.I):
        return False
    r = ledger.get(mk.rid)
    tot = ((r.sheet or {}).get("totals") or {}).get("items") if r is not None else None
    return isinstance(tot, (int, float)) and not isinstance(tot, bool) and mk.value == tot


# ------------------------------------------------------------------ one sentence (step 3)
def _clause_around(s, a, b):
    """The clause of s that holds [a, b): from the last break before a to the next break after b."""
    pre = [m.end() for m in _BREAKS.finditer(s[:a])]
    post = _BREAKS.search(s, b)
    return s[(pre[-1] if pre else 0):(post.start() if post else len(s))]


def _name_spans(text, names_idx, extra=()):
    """[(start, end, low name)] of library names in text, longest first, no overlaps."""
    found, taken = [], []
    cands = sorted(set(list(names_idx.keys()) + [_low(x) for x in extra if x]), key=len, reverse=True)
    low = text.lower()
    for n in cands:
        if len(n) < 2:
            continue
        for m in re.finditer(r"(?<![\w@])" + re.escape(n) + r"(?:s|es)?(?![\w])", low):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            found.append((m.start(), m.end(), n))
            taken.append((m.start(), m.end()))
    return sorted(found)


def _window_phrases(res, prev=True):
    out = []
    for x in ((res.meta or {}).get("window_said"), (res.sheet.get("window") or {}).get("words"),
              (res.sheet.get("previous") or {}).get("words") if prev else None):
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
            out.append(re.split(r"[(,]", x)[0].strip())
    return sorted({x for x in out if len(x) >= 4}, key=len, reverse=True)


def _remove_phrases(text, phrases):
    for ph in phrases:
        text = re.sub(re.escape(ph), lambda m: " " * len(m.group(0)), text, flags=re.I)
    return text


def _allowed_numbers_out(text, res):
    """text with what may stand with no marker blanked: years, day-month dates, "the 4 weeks" of the window's own
    words, hours said inside window words."""
    t = _remove_phrases(text, _window_phrases(res) if res else [])
    t = _DATE_IN.sub(lambda m: " " * len(m.group(0)), t)
    t = re.sub(r"\b" + _MON_RX + r"\w*\.?\s+(?:19|20)\d\d\b", lambda m: " " * len(m.group(0)), t, flags=re.I)
    t = _YEAR.sub("    ", t)
    words = " ".join(_window_phrases(res)).lower() if res else ""
    for m in list(_SPAN_N.finditer(t)):
        unit = m.group(2).lower().rstrip("s")
        if re.search(r"\b" + m.group(1) + r"\s+" + unit, words):
            t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
    return t


def _months_in(a, b):
    out, y, m = set(), a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.add((y, m))
        y, m = (y + (m == 12), m % 12 + 1)
    return out


_PHRASE = re.compile(
    r"\b(?P<since>since\s+|after\s+)?(?:"
    r"(?:the\s+)?(?P<season>spring|summer|autumn|winter)(?:\s+of)?(?:\s+(?P<sy>(?:19|20)\d\d))?"
    r"|(?P<mon>january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?(?:\s+(?P<my>(?:19|20)\d\d))?"
    r"|(?P<year>(?:19|20)\d\d)"
    r"|(?P<rel>today|yesterday|(?:this|last|past) (?:week|month|year))"
    r")\b", re.I)
_SEASON_M = {"spring": (3, 5), "summer": (6, 8), "autumn": (9, 11), "winter": (12, 2)}
FAR = date(2999, 12, 31)
WINDOW_MATCH = 0.85   # a time said of a count covers its window, and the window covers it, to this share of days


def _month_range(y, m):
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date(y, m, 1), date.fromordinal(nxt.toordinal() - 1)


def _season(y, s0, s1):
    if s0 > s1:   # winter: December to February
        return date(y, 12, 1), _month_range(y + 1, 2)[1]
    return date(y, s0, 1), _month_range(y, s1)[1]


def _overlap(p, w):
    a, b = max(p[0], w[0]), min(p[1], w[1])
    return max(0, b.toordinal() - a.toordinal() + 1)


def _phrase_range(m, wins, turn):
    """(start, end) of a time phrase, or None when it cannot be placed (a relative word with no today)."""
    g = m.groupdict()
    end_year = max((b.year for _a, b in wins), default=None)
    if g.get("rel"):
        today = turn.today if turn and turn.today else None
        if today is None:
            return None
        r = g["rel"].lower()
        if r == "today":
            a = b = today
        elif r == "yesterday":
            a = b = date.fromordinal(today.toordinal() - 1)
        elif r.endswith("week"):
            mon = date.fromordinal(today.toordinal() - today.weekday())
            if r.startswith("last"):
                mon = date.fromordinal(mon.toordinal() - 7)
            a, b = (date.fromordinal(today.toordinal() - 7), today) if r.startswith("past") else \
                (mon, date.fromordinal(mon.toordinal() + 6))
        elif r.endswith("month"):
            y, mo = today.year, today.month
            if r.startswith("last"):
                y, mo = (y - (mo == 1), 12 if mo == 1 else mo - 1)
            a, b = _month_range(y, mo)
        else:
            y = today.year - r.startswith("last")
            a, b = date(y, 1, 1), date(y, 12, 31)
    elif g.get("season"):
        s0, s1 = _SEASON_M[g["season"].lower()]
        if g.get("sy"):
            y = int(g["sy"])
        else:   # the instance that overlaps the windows most
            cands = sorted({a.year for a, _b in wins} | {b.year for _a, b in wins} | {(end_year or 2000) - 1})
            y = max(cands, key=lambda yy: (sum(_overlap(_season(yy, s0, s1), w) for w in wins), yy))
        a, b = _season(y, s0, s1)
    elif g.get("mon"):
        mi = next(i for i, x in enumerate(_MONTHS) if x.startswith(g["mon"].lower()[:3])) + 1
        if g.get("my"):
            a, b = _month_range(int(g["my"]), mi)
        else:
            cands = sorted({y for w in wins for y in range(w[0].year, w[1].year + 1)} or {end_year or 2000})
            y = max(cands, key=lambda yy: (sum(_overlap(_month_range(yy, mi), w) for w in wins), yy))
            a, b = _month_range(y, mi)
    else:
        y = int(g["year"])
        a, b = date(y, 1, 1), date(y, 12, 31)
    if g.get("since"):
        b = FAR
    return a, b


def _matches(p, w, clipped):
    """The phrase's range is the window: the same first day, and the same last day (a window cut at the export's
    end, or an open "since", is read up to the window's end). Step 1 fix (the verifier audit, F15, F15b: "In
    October" of the 4 weeks from 3 October passed at WINDOW_MATCH's tolerance, a count about 8% off): a calendar
    period said of a count is that period, never a stretch most of it."""
    a, b = p
    if b == FAR or (clipped and b > w[1]):
        b = w[1]
    if b < a:
        return False
    return a == w[0] and b == w[1]


def _labels(sheet):
    """The periods a sheet names itself ("2021", "Oct 2026": periods, eras, the change's ends)."""
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("label", "from", "to", "peak_period", "peak_label", "last_label") and isinstance(v, str):
                    out.add(_low(v))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk({k: v for k, v in sheet.items() if k in ("periods", "eras", "change", "areas_change", "seasonal")})
    return out


def _label_range(label):
    m = _PHRASE.fullmatch(label.strip())
    if not m or m.group("rel") or m.group("since") or not (m.group("year") or m.group("my") or m.group("sy")):
        return None
    return _phrase_range(m, [], None)


def _phrase_ok(m, rng, res, wins, period_cells=False):
    """The phrase is the window (or the compare window); or, when the sentence cites a period's own cells (periods,
    eras, a change's two ends), one of the periods the sheet names. A window of all their history starts where the
    record starts: a phrase may start earlier in that year ("since 2021" of a history from 5 January 2021)."""
    if rng is None:
        return False
    clipped = bool((res.sheet.get("window") or {}).get("clipped"))
    if any(_matches(rng, w, clipped) for w in wins):
        return True
    said = _low((res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or "")
    if said.startswith("all your history") and wins and rng[0] <= wins[0][0] and rng[0].year == wins[0][0].year \
            and _matches((wins[0][0], rng[1]), wins[0], clipped):
        return True
    if not period_cells:
        return False
    lab = _labels(res.sheet)
    return _low(m.group(0)) in lab or any(rng == _label_range(x) for x in lab)


def _windows_of(res, cites_prev):
    out = []
    w = res.window()
    if w[0] and w[1]:
        out.append(w)
    if cites_prev or res.tool == "compare" or res.sheet.get("kind") in ("compare", "compare_windows"):
        pw = res.prev_window()
        if pw:
            out.append(pw)
    return out


def _window_check(text, res, cites_prev, turn, period_cells=False):
    """None or (reason, detail): every time said in the sentence against the cited result's window (and its compare
    window when a previous or change cell is cited, or the result is a compare). A day must lie inside one; a month,
    a year, a season or a relative word ("this year", "last week") must be that window, not a stretch around or
    inside it (a count of 4 weeks said "in 2026" is the right number with a wrong window), unless the sheet names
    that period itself (its periods, eras, a change's ends)."""
    if res is None:
        return None
    wins = _windows_of(res, cites_prev)
    if not wins:
        return None
    said = (res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or ""
    det = f"{res.rid}'s window is '{_clip(said, 90)}'"
    # the window before's own words are left out of the check only when they are the sentence's (a previous or
    # change cell, a compare): "In September 2026, Clip Factory made 61" of an October cell is the wrong window (merge
    # seam: every breakdown the tools return carries the window before)
    t = _remove_phrases(text, _window_phrases(res, prev=len(wins) > 1))
    for m in _DATE_IN.finditer(t):
        g = m.groups()
        d_, mon, y = (g[0], g[1], g[2]) if g[0] else (g[4], g[3], g[5])
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(mon.lower()[:3])), None)
        if mi is None:
            continue
        ok = False
        for a, b in wins:
            for yy in ([int(y)] if y else range(a.year, b.year + 1)):
                try:
                    dd = date(yy, mi + 1, int(d_))
                except ValueError:
                    continue
                ok = ok or a <= dd <= b
        if not ok:
            return "wrong_window", det
    t2 = _DATE_IN.sub(lambda m: " " * len(m.group(0)), t)
    for m in _PHRASE.finditer(t2):
        if m.group("mon") and m.group("mon").lower() in ("may", "mar") and not m.group("my"):
            continue   # "may" and "mar" are words as often as months
        if not _phrase_ok(m, _phrase_range(m, wins, turn), res, wins, period_cells):
            return "wrong_window", det
    if _LATELY.search(t2):
        lately = re.search(r"\b(?:4|four) weeks\b", said, re.I) or _LATELY.search(said)
        if not lately:
            return "wrong_window", det
    return None


def _end_in_base(sentence, markers, res, turn=None):
    """A value said with the other period's words: the end value of a change inside the base period ("from 12% to
    9% in the 4 weeks before"), or a value of the period before inside the window's words or dates."""
    if res is None:
        return None
    prevw = (res.sheet.get("previous") or {}).get("words")
    w, pw = res.window(), res.prev_window()
    clipped = bool((res.sheet.get("window") or {}).get("clipped"))
    first_value = next((mk for mk in markers if mk.kind == "value" and isinstance(mk.value, (int, float))), None)
    for mk in markers:
        if mk.kind != "value" or not isinstance(mk.value, (int, float)):
            continue
        after = sentence[mk.end:mk.end + 120]
        stop = re.search(r"[;]|,\s*(?:while|and|but)\b|\b(?:while|whereas|but)\b|"
                         r"\b(?:to|from)\s+[+\-−]?\d[\d.,]*\s*(?:%|\[|points?\b)", after)
        after = after[:stop.start()] if stop else after
        if (mk.key or "") in ("change_vs_previous", "change_pts", "change"):
            continue   # a change is of both periods
        prev_cell = _is_before(mk.rest)
        m = re.match(r"^\s*(?:,\s*)?(?:[a-z]+\s+){0,2}?(?:in|during|over|across)\s+(.{3,80})", after, re.I)
        if not m and mk is first_value:
            # merge seam (a compare result holds both windows, so step 15 lets either year stand anywhere; a
            # previous cell lets the window before stand): the time that opens the sentence is its first value's
            # ("In 2025, you opened 8[r1.totals.items]" says a count of 2024 under 2025's name)
            m = re.match(r"^\s*(?:in|during|over|across)\s+(.{3,80})", sentence[:mk.start], re.I)
        if not m:
            continue
        ph = m.group(1).lower()
        says_prev = bool(re.search(r"\bbefore\b|\bprevious\b|\bearlier\b|\bprior\b", ph)) or \
            bool(prevw and _low(prevw)[:20] in _low(ph))
        nw = [x for x in ((res.meta or {}).get("window_said"), (res.sheet.get("window") or {}).get("words")) if x]
        says_now = not says_prev and any(_low(re.split(r"[(,]", x)[0])[:24] in _low(ph) for x in nw)
        if not (says_prev or says_now):
            pm = _PHRASE.match(m.group(1))
            wins = [x for x in (w, pw) if x and x[0]]
            rng = _phrase_range(pm, wins, turn) if pm else None
            if rng and w[0]:
                in_now = _matches(rng, w, clipped)
                in_prev = bool(pw) and _matches(rng, pw, False)
                says_prev, says_now = in_prev and not in_now, in_now and not in_prev
        if says_prev and not prev_cell:
            return "wrong_window", f"{mk.path} is of {res.rid}'s window, not the period before"
        if says_now and prev_cell:
            return "wrong_window", f"{mk.path} is of the period before, not {res.rid}'s window"
    return None


# ------------------------------------------------------------------ mvp25: cells-only rules (DESIGN 24.4, IN SAMPLE)
_SAME_PART = re.compile(r"\b(?:the\s+)?same\s+(?:part|stretch|weeks|period|time)\s+of\s+(?P<y>(?:19|20)\d\d)\b", re.I)
_RANGE_WORDS = re.compile(r"(\d{1,2}) ([A-Za-z]+)(?: (\d{4}))? to (\d{1,2}) ([A-Za-z]+) (\d{4})")


def _prev_range(res):
    """The window before of a result: prev_window(), else the dates in its previous words ("from 1 January to 30
    October 2025", the changes tool's words, with no brackets)."""
    pw = res.prev_window()
    if pw:
        return pw
    m = _RANGE_WORDS.search(str((res.sheet.get("previous") or {}).get("words") or ""))
    if not m:
        return None
    try:
        y2 = int(m.group(6))
        b = date(y2, _MONTHS.index(m.group(5).lower()) + 1, int(m.group(4)))
        a = date(int(m.group(3)) if m.group(3) else y2, _MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
    except ValueError:
        return None
    return a, b


def _row_period(res, rest):
    """The period a period row's cell is of (periods[i], eras[i]: the row's own label), else None."""
    m = re.match(r"^((?:periods|eras)\[\d+\])", rest)
    if not m:
        return None
    try:
        row = _resolve(res.sheet, m.group(1))
    except KeyError:
        return None
    lab = row.get("label") if isinstance(row, dict) else None
    return _label_range(_low(lab)) if isinstance(lab, str) else None


def _cell_anchors(markers, res):
    """[(start, end, path, (start, end) or "both")] of every numeric cell of `res` the sentence cites, in order (a
    change, or a calc of a change, is of both periods); None when a cell has no period code can place."""
    out = []
    for mk in markers:
        if mk.kind == "value" and isinstance(mk.value, (int, float)) and not isinstance(mk.value, bool) and \
                mk.rid == res.rid:
            rests = [mk.rest]
        elif mk.kind == "calc":
            rests = [x.split(".", 1)[1] for x in (mk.a, mk.b) if x.split(".", 1)[0] == res.rid]
        else:
            continue
        ws = []
        for rest in rests:
            if _segs(rest)[-1][0] in ("change_vs_previous", "change_pts", "change"):
                ws.append("both")
                continue
            if re.match(r"^(?:periods|eras)\[", rest):
                w = _row_period(res, rest)
            elif re.match(r"^(?:change|areas_change|seasonal)\b", rest):
                return None
            elif _is_before(rest):
                w = _prev_range(res)
            else:
                w = res.window()
                w = w if w[0] and w[1] else None
            if w is None:
                return None
            ws.append(w)
        if mk.kind == "calc" and len(set(map(str, ws))) > 1:
            ws = ["both"]
        out.append((mk.start, mk.end, mk.path, ws[0] if ws else "both"))
    return out


def _known_periods(ledger):
    """[(range, name, clipped)] of every period the turn's results name: each result's window and window before, and
    the periods its sheet names itself (periods, eras, a change's ends)."""
    out = []
    for r in ledger.by_rid.values():
        w = r.window()
        if w[0] and w[1]:
            out.append((w, f"{r.rid}'s window", bool((r.sheet.get("window") or {}).get("clipped"))))
        pw = _prev_range(r)
        if pw:
            out.append((pw, f"{r.rid}'s window before", False))
        for lab in sorted(_labels(r.sheet)):
            rng = _label_range(lab)
            if rng:
                out.append((rng, f"'{lab}'", False))
    return out


_LAST_BEFORE = re.compile(r"\b(?:last|past|previous)\s+$", re.I)


def _last_season(name, turn):
    """mvp25 merge (the tools' convention of DESIGN 25.1, brain/windows.py): "last <season>" is the one a year before the
    latest one that has begun on the turn's day. None (left alone) when the turn has no day. Before this, "last summer"
    took the instance the cited windows overlap most, which in a this-summer-against-last-summer compare is a tie and
    went to this summer."""
    today = turn.today if turn and turn.today else None
    if today is None:
        return None
    s0, s1 = _SEASON_M[name.lower()]
    y = today.year if today.month >= s0 else today.year - 1
    return _season(y - 1, s0, s1)


_CLAUSE_BREAK = re.compile(r"[;:]|,\s*(?:and|but|while|whereas|against|with|so|though)\b|\b(?:while|whereas|but)\b",
                           re.I)


def _period_named(raw, markers, res, ledger, turn):
    """mvp25 cells rule "period_named" (the second attack's f16, f21, f22, p04, p05, p07): a period the sentence names
    (a year, a month, a season, 'this year', 'the same part of 2025') bound to a numeric cell, when the cell has no day
    in it, or when it is another period one of the turn's results holds (a window, a window before, a period row),
    names the cell under another period's name. A phrase binds to the cell right before it in the same clause (one
    phrase per cell), or, before the first cell, the phrase nearest it binds that cell. Read from the cells' paths and
    the results' window fields; a phrase that holds the cell's period (the frame: 'this year' of an October row), one
    after 'before', 'after', 'since', 'until' or 'up to', or one bound to no cell, is left alone (framing)."""
    if res is None or not res.is_sheet:
        return None
    cells = _cell_anchors(markers, res)
    if not cells:
        return None
    w = res.window()
    if w[0] and w[1] and _prev_range(res) == w:
        return None   # a window compared with itself: which period a cell is of cannot be read
    clipped_now = bool((res.sheet.get("window") or {}).get("clipped"))
    known = _known_periods(ledger)
    t = list(raw)
    for mk in markers:
        for i in range(mk.start if mk.kind == "row" else mk.mstart, mk.end):
            t[i] = " "
    t = "".join(t)
    t = _DATE_IN.sub(lambda m: " " * len(m.group(0)), t)
    said = []
    for m in _SAME_PART.finditer(t):
        if w[0] and w[1]:
            y = int(m.group("y"))
            try:
                said.append((m.start(), m.end(), m.group(0), (w[0].replace(year=y), w[1].replace(year=y))))
            except ValueError:
                pass
    t = _SAME_PART.sub(lambda m: " " * len(m.group(0)), t)
    wins = [x for *_r, x in cells if x != "both"] or [w]
    for m in _PHRASE.finditer(t):
        if m.group("since"):
            continue
        if m.group("mon") and m.group("mon").lower() in ("may", "mar") and not m.group("my"):
            continue
        if re.search(r"\b(?:before|after|since|until|till|up to|through|by|from)\s*$", t[:m.start()], re.I):
            continue
        rng = _phrase_range(m, wins, turn)
        if m.group("season") and not m.group("sy") and _LAST_BEFORE.search(t[:m.start()]):
            rng = _last_season(m.group("season"), turn)
        if rng is not None:
            said.append((m.start(), m.end(), m.group(0), rng))
    said.sort()
    bound = {}
    for k, (a, b, text, rng) in enumerate(said):
        before = [c for c in cells if c[1] <= a]
        if before:
            c = before[-1]
            gap = raw[c[1]:a]
            if c[2] in bound or _CLAUSE_BREAK.search(gap) or any(c[1] <= x[0] < a for x in said[:k]):
                continue
        else:
            c = cells[0]
            if any(b <= x[0] < c[0] for x in said[k + 1:]):
                continue   # a nearer phrase binds the first cell
        bound[c[2]] = (text, rng)
        cw = c[3]
        if cw == "both":
            continue
        if _matches(rng, cw, clipped_now and cw == w) or (rng[0] <= cw[0] and cw[1] <= rng[1]):
            continue   # the cell's own period, or a period that holds it (the frame)
        disjoint = rng[1] < cw[0] or cw[1] < rng[0]
        other = next((nm for kr, nm, kc in known if _matches(rng, kr, kc)), None)
        if disjoint or other:
            return "other_period", (f"{c[2]} is of {cw[0].isoformat()} to {cw[1].isoformat()}, not '{_clip(text, 30)}'"
                                    + (f" ({other})" if other else ""))
    return None


_ISO_DAY = re.compile(r"^((?:19|20)\d\d)-(\d\d)-(\d\d)")
_MON_YEAR = re.compile(r"\b(" + _MON_RX + r")\.?\s+((?:19|20)\d\d)\b", re.I)
_BOUND_WORDS = re.compile(r"\b(?:to|up to|until|till|through|ends?|ending|ended|from|since|between|and|before|after)"
                          r"(?:\s+on)?\s*$", re.I)


def _row_days(res, markers):
    """The dates (date) in the rows the sentence cites of `res` (an item's 'when', a channel's 'first_watched', ...)."""
    out = set()
    for mk in markers:
        if mk.kind not in ("row", "value") or not mk.owner or mk.rid != res.rid:
            continue
        try:
            row = _resolve(res.sheet, mk.owner)
        except KeyError:
            continue
        if not isinstance(row, dict):
            continue
        for v in row.values():
            m = _ISO_DAY.match(v) if isinstance(v, str) else None
            if m:
                try:
                    out.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                except ValueError:
                    pass
    return out


def _typed_dates(raw, markers, res):
    """[(start, text, (first day, last day), day: bool)] of the dates typed with no marker: a full date, a month and a
    year, a year after 'in' or 'starting'; the window's own words and every marker's said text left out."""
    t = list(raw)
    for mk in markers:
        for i in range(mk.start, mk.end):
            t[i] = " "
    t = _remove_phrases("".join(t), _window_phrases(res))
    out = []
    for m in _DATE_IN.finditer(t):
        g = m.groups()
        d_, mon, y = (g[0], g[1], g[2]) if g[0] else (g[4], g[3], g[5])
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(mon.lower()[:3])), None)
        if mi is None:
            continue
        if not y:
            # a day with no year ("on 30 October"): held when a row's date is that day of any year
            out.append((m.start(), m.group(0), ("md", mi + 1, int(d_)), True))
            continue
        try:
            dd = date(int(y), mi + 1, int(d_))
        except ValueError:
            continue
        out.append((m.start(), m.group(0), (dd, dd), True))
    t = _DATE_IN.sub(lambda m: " " * len(m.group(0)), t)
    for m in _MON_YEAR.finditer(t):
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(m.group(1).lower()[:3])), None)
        if mi is not None:
            out.append((m.start(), m.group(0), _month_range(int(m.group(2)), mi + 1), False))
    t = _MON_YEAR.sub(lambda m: " " * len(m.group(0)), t)
    for m in re.finditer(r"\b(?:in|starting in|started in|starting|beginning in|back in)\s+((?:19|20)\d\d)\b", t, re.I):
        y = int(m.group(1))
        out.append((m.start(1), m.group(1), (date(y, 1, 1), date(y, 12, 31)), False))
    for m in re.finditer(r"\b(?:starting|started|start|beginning|began|begun|since|first\s+\w+)\s+"
                         r"(?:in\s+|on\s+|from\s+)?(" + _MON_RX + r")\b(?!\.?\s+(?:19|20)\d\d)", t, re.I):
        # a month with no year said as where a row starts ("starting in April"): held when a row's date is in it
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(m.group(1).lower()[:3])), None)
        if mi is not None and not (m.group(1).lower() in ("may", "mar") and not m.group(1)[0].isupper()):
            out.append((m.start(1), m.group(1), ("m", mi + 1), False))
    return sorted(out, key=lambda x: x[0])


def _free_date(raw, markers, res, ledger):
    """mvp25 cells rule "free_date" (the second attack's c09, c10, g05): a date typed with no marker in a sentence that
    cites a row holding dates must be that row's: it holds one of the cited rows' dates (an item's day, a channel's
    first day), or it is a period one of the turn's results holds (a window, a window before, a period row), or a
    window's first or last day said as an end ('up to', 'from', 'since'), or the window itself when the window is one
    day. Else no cell holds it. Read from the rows' date fields and the results' window fields only."""
    if res is None or not res.is_sheet:
        return None
    days = _row_days(res, markers)
    if not days:
        return None
    known = _known_periods(ledger)
    bounds = {d for kr, _nm, _c in known for d in kr}
    w = res.window()
    for a, text, rng, is_day in _typed_dates(raw, markers, res):
        if rng[0] == "md":
            edge = _BOUND_WORDS.search(raw[:a]) and any((b_.month, b_.day) == rng[1:] for b_ in bounds)
            if not edge and not any((d.month, d.day) == rng[1:] for d in days) and \
                    not any(kr[0] == kr[1] and (kr[0].month, kr[0].day) == rng[1:] for kr, _nm, _c in known):
                return "date", f"'{_clip(text, 30)}' is no date of the rows cited"
            continue
        if rng[0] == "m":
            if not any(d.month == rng[1] for d in days):
                return "date", f"'{_clip(text, 30)}' is no month of the rows cited"
            continue
        d0, d1 = rng
        if any(d0 <= d <= d1 for d in days):
            continue
        if any(kr == (d0, d1) or (c and kr[0] == d0 and d1 >= kr[1]) for kr, _nm, c in known):
            continue
        if _BOUND_WORDS.search(raw[:a]) and (d0 in bounds or d1 in bounds):
            continue
        if is_day and w[0] and w[0] == w[1] == d0:
            continue
        said = ", ".join(sorted(d.isoformat() for d in days))[:80]
        return "date", f"'{_clip(text, 30)}' is no date of the rows cited ({said})"
    return None


_WD_DATE = re.compile(r"\b(" + "|".join(I.WEEKDAYS) + r"),?\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" +
                      _MON_RX + r")\.?,?\s+((?:19|20)\d\d)\b", re.I)


def _typed_weekday(raw):
    """mvp25 cells rule "weekday_typed" (the second attack's w01): 'Thursday 30 October 2026' typed with a weekday that
    is not that date's (calendar arithmetic on the words only)."""
    for m in _WD_DATE.finditer(strip_markers(raw)):
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(m.group(3).lower()[:3])), None)
        try:
            dd = date(int(m.group(4)), mi + 1, int(m.group(2)))
        except (TypeError, ValueError):
            continue
        if I.WEEKDAYS[dd.weekday()] != m.group(1).lower():
            return "weekday", f"{dd.isoformat()} is a {I.WEEKDAYS[dd.weekday()].title()}, not a {m.group(1).title()}"
    return None


_HOUR_OF = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_LENGTH_SAID = re.compile(r"\b(?:(?P<short>shorts?)|(?P<long>long(?:-form)?(?:\s+(?:videos?|ones?))?|longer))\b", re.I)
_ITEM_CLAUSE_STOP = re.compile(r"[,;:]|\b(?:and|but|while|whereas|then|after|before)\b", re.I)


def _cited_items(markers, res):
    """[(marker, row)] of the items the sentence cites (a row marker or a cell of items[i])."""
    out = []
    for mk in markers:
        if mk.kind not in ("row", "value") or mk.rid != res.rid or not mk.owner or \
                not re.fullmatch(r"items\[\d+\]", mk.owner):
            continue
        try:
            row = _resolve(res.sheet, mk.owner)
        except KeyError:
            continue
        if isinstance(row, dict):
            out.append((mk, row))
    return out


def _item_hour(row):
    m = _HOUR_OF.search(str(row.get("when") or ""))
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    return h


def _item_fields(raw, markers, res):
    """mvp25 cells rule "item_fields" (the second attack's h01 to h03, e09, e13): what a sentence says of a cited item
    in words must be that item's own field. A time of day ('in the morning', 'late at night') said after an item is its
    hour's; 'a Short' / 'a long video' said of an item in the same clause is its length; a channel cited with 'from' or
    'by' right after an item is the item's own channel. Read from the item row's fields (when, length, channel)."""
    if res is None or not res.is_sheet:
        return None
    items = _cited_items(markers, res)
    if not items:
        return None
    t = list(raw)
    for mk in markers:
        for i in range(mk.start if mk.kind == "row" else mk.mstart, mk.end):
            t[i] = " "
    t = "".join(t)
    t = re.sub(r"@[\w.]+|\"[^\"]{1,120}\"|“[^”]{1,120}”", lambda m: " " * len(m.group(0)), t)   # names and titles
    # a title in quotes beside a cited item is that item's own, not another item's of the result
    own_titles = {_low(row.get("title")) for _mk, row in items if isinstance(row.get("title"), str)}
    all_titles = {_low(x.get("title")) for x in (res.sheet.get("items") or []) if isinstance(x, dict) and
                  isinstance(x.get("title"), str)}
    for q in re.findall(r"[\"“]([^\"”]{2,120})[\"”]", raw):
        if _low(q) in all_titles and _low(q) not in own_titles:
            return "item_field", f"'{_clip(q, 40)}' is the title of another item of {res.rid}"

    def owner_before(pos, clause=False):
        best = None
        for mk, row in items:
            if mk.end <= pos and (best is None or mk.end > best[0].end):
                best = (mk, row)
        if best is None:
            return None
        if clause and _ITEM_CLAUSE_STOP.search(t[best[0].end:pos]):
            return None
        return best
    # a time of day
    for m in re.finditer(r"[a-z]+", t.lower()):
        hours = I._TIME_WORD.get(m.group(0))
        if hours is None or m.group(0) in ("manana", "mananas", "tarde", "tardes", "noche", "noches"):
            continue
        if m.group(0) == "late" and not re.match(r"^[\s-]*(?:at\s+night|night|in\s+the\s+evening|evening)",
                                                 t.lower()[m.end():]):
            continue   # "late January", "late in the year": no hour
        it = owner_before(m.start()) or (items[0] if len(items) == 1 else None)
        if it is None:
            continue
        h = _item_hour(it[1])
        if h is not None and h not in hours:
            return "item_field", f"{res.rid}.{it[0].owner} was opened at {h}:00, not in the {m.group(0)}"
    # its length
    for m in _LENGTH_SAID.finditer(t):
        it = owner_before(m.start(), clause=True)
        if it is None or it[1].get("length") not in ("short", "long"):
            continue
        said = "short" if m.group("short") else "long"
        if said != it[1]["length"]:
            return "item_field", f"{res.rid}.{it[0].owner} is a {it[1]['length']} video, not a {said} one"
    # its channel
    for mk in markers:
        if mk.kind != "row" or mk.rid != res.rid or not re.fullmatch(r"channels\[\d+\]", mk.owner or ""):
            continue
        if not re.search(r"\b(?:from|by)\s*$", raw[:mk.start]):
            continue
        it = owner_before(mk.start, clause=True)
        ch = it[1].get("channel") if it else None
        name = (mk.value or {}).get("name") if isinstance(mk.value, dict) else None
        if isinstance(ch, str) and isinstance(name, str) and _low(ch) != _low(name):
            return "item_field", f"{res.rid}.{it[0].owner} is from {ch}, not {name}"
    return None


_ALL_LEN = re.compile(r"\b(?:all|every one|each|each one)\s+(?:of\s+(?:them|those|these|it)\s+)?(?:were\s+|was\s+)?"
                      r"(?:an?\s+)?(?P<w>shorts?|long(?:-form)?(?: videos?| ones?)?)\b|"
                      r"\bonly\s+(?P<w2>shorts|long videos)\b", re.I)
_SHORTS_KEYS = ("shorts", "shorts_share", "previous_shorts", "previous_shorts_share")
_LONG_KEYS = ("long", "long_share", "previous_long", "previous_long_share")


def _length_cell(raw, markers, res):
    """mvp25 cells rule "length_cell" (the second attack's a19, n09, p06): a length cell said under the other length's
    word ("72[...totals.long] of them Shorts"; "long videos, at 47%[...shorts_share]"), and "all of them Shorts" of a
    row whose Shorts share says otherwise. The word read is the length word right after the cell (up to four words),
    else the nearest one before it with no other number between. Read from the cells' keys and the row's
    shorts_share."""
    if res is None or not res.is_sheet:
        return None
    nums = [mk for mk in markers if mk.kind == "value" and isinstance(mk.value, (int, float))
            and not isinstance(mk.value, bool)]
    t = list(raw)
    for mk in markers:
        for i in range(mk.start if mk.kind == "row" else mk.mstart, mk.end):
            t[i] = " "
    t = "".join(t)
    for mk in nums:
        key = _segs(mk.rest)[-1][0]
        kind = "short" if key in _SHORTS_KEYS else "long" if key in _LONG_KEYS else None
        if kind is None:
            continue
        after = re.match(r"^(?:\s*[^\s,;:.]+){1,4}", t[mk.end:mk.end + 80])
        aw = _LENGTH_SAID.search(after.group(0)) if after else None
        if aw:
            said = "short" if aw.group("short") else "long"
        else:
            prev_num = max((x.end for x in nums if x.end <= mk.start), default=0)
            bw = list(_LENGTH_SAID.finditer(t[prev_num:mk.start]))
            if not bw:
                continue
            said = "short" if bw[-1].group("short") else "long"
        if said != kind:
            return "length_cell", f"{mk.path} is a {'Shorts' if kind == 'short' else 'long-video'} cell, said as " \
                                  f"{'Shorts' if said == 'short' else 'long videos'}"
    for mk in nums:
        # a row's count of videos said as Shorts or as long videos ("32[r1.channels[1].items] Shorts"): all of the
        # row's videos are of that length
        if _segs(mk.rest)[-1][0] != "items":
            continue
        nx = re.match(r"^\s*(?P<w>shorts?|long(?:-form)?\s+(?:videos?|ones?))\b", t[mk.end:mk.end + 30], re.I)
        if not nx:
            continue
        try:
            row = _resolve(res.sheet, mk.owner) if mk.owner else (res.sheet.get("totals") or {})
        except KeyError:
            continue
        sh = row.get("shorts_share") if isinstance(row, dict) else None
        if isinstance(sh, (int, float)) and not isinstance(sh, bool):
            w = nx.group("w").lower()
            if (w.startswith("short") and sh < 0.995) or (w.startswith("long") and sh > 0.005):
                return "length_cell", f"{mk.path}: {round(100 * sh)}% of them are Shorts, not all " + \
                                      ("Shorts" if w.startswith("short") else "long videos")
    m = _ALL_LEN.search(t)
    if m:
        w = (m.group("w") or m.group("w2")).lower()
        own = next((mk.owner for mk in markers if mk.kind in ("row", "value") and mk.owner and mk.rid == res.rid), None)
        try:
            row = _resolve(res.sheet, own) if own else (res.sheet.get("totals") or {})
        except KeyError:
            row = None
        sh = row.get("shorts_share") if isinstance(row, dict) else None
        if isinstance(sh, (int, float)) and not isinstance(sh, bool):
            if (w.startswith("short") and sh < 0.995) or (w.startswith("long") and sh > 0.005):
                return "length_cell", f"{res.rid}.{own or 'totals'}.shorts_share = {round(100 * sh)}%: not all " + \
                                      ("Shorts" if w.startswith("short") else "long videos")
    return None


def _own_field_of(name, at, markers, ledger):
    """mvp25 cells loosening "own_fields": the path of the field ("items[3].channel", "channels[1].theme") that holds
    `name` in the row cited right before position `at` (a row marker, or the row of a cell; the first row cited after
    it when none comes before), else None."""
    rows = []
    for mk in markers:
        if mk.kind == "row" and mk.owner:
            rows.append((mk.start, mk.rid, mk.owner))
        elif mk.kind == "value" and mk.owner:
            rows.append((mk.start, mk.rid, mk.owner))
    if not rows:
        return None
    before = [r for r in rows if r[0] < at]
    pos, rid, own = max(before) if before else min(rows)
    res = ledger.get(rid)
    try:
        row = _resolve(res.sheet, own) if res is not None else None
    except KeyError:
        return None
    if not isinstance(row, dict):
        return None
    f_ = res.sheet.get("filters") or {}
    scope = {_low(v) for v in (f_.get("topic"), f_.get("channel")) if isinstance(v, str)}
    for k_ in ("channel", "theme", "area"):
        v = row.get(k_)
        if not isinstance(v, str) or not v.strip() or _low(v) in scope:
            continue
        if _low(v) == name or (k_ == "area" and name in {_low(x) for x in _area_aliases(v)}):
            return f"{own}.{k_}"
    return None


def _date_owner(markers, plain_rows):
    """mvp25 cells rule "date_owner" (the second attack's b09: "You started on @wetpaper.ig[r1.channels[1]] on 10
    January 2025[r1.channels[0].first_watched]"): a date cell of a row (a channel's first day, an item's day) said
    where another row of the same list is named and its own row is not. Insight never reads a date cell's row (its
    slot is taken out), so this binding is read here, from the paths only. `plain_rows`: the rows named in plain
    words."""
    named = {(mk.rid, mk.owner) for mk in markers if mk.kind == "row" and mk.owner} | set(plain_rows)
    for mk in markers:
        if mk.kind != "value" or not isinstance(mk.value, str) or not mk.owner or \
                _measure(mk.rest, mk.value)[1] != "date":
            continue
        lst, _i = _list_and_index(mk.owner)
        if lst is None or (mk.rid, mk.owner) in named:
            continue
        others = [o for r_, o in named if r_ == mk.rid and _list_and_index(o)[0] == lst and o != mk.owner]
        if others:
            return "bound_to_other", f"{mk.path} is {mk.owner}'s date, said beside {others[0]}"
    return None


def _pairs_crossed(raw, markers):
    """mvp25 cells rule "pairs_crossed" (the second attack's p02): "A[...] and B[...] had X[B's cell] and Y[A's cell]":
    two rows said in one order and their two cells in the crossed order. Read from the paths only."""
    rows = [mk for mk in markers if mk.kind == "row" and mk.owner]
    vals = [mk for mk in markers if mk.kind == "value" and mk.owner and isinstance(mk.value, (int, float))]
    if len(rows) != 2 or len(vals) != 2 or not (rows[1].end <= vals[0].start):
        return None
    if not re.search(r"^\s*and\s*$", raw[rows[0].end:rows[1].start]) or \
            not re.search(r"^\s*and\s*$", raw[vals[0].end:vals[1].start]):
        return None
    a, b = (rows[0].rid, rows[0].owner), (rows[1].rid, rows[1].owner)
    x, y = (vals[0].rid, vals[0].owner), (vals[1].rid, vals[1].owner)
    if x == b and y == a and a != b:
        return "bound_to_other", f"{vals[0].path} is {rows[1].owner}'s and {vals[1].path} is {rows[0].owner}'s: " \
                                 "said in the crossed order"
    return None


def check_sentence(sentence, ledger, turn=None, where="point", index=0, state=None, probe=False, mode=None):
    """One sentence -> Outcome (kept, or dropped with reason codes and the true values of its cells). `probe` (the
    proof and the tests only): insight's step runs even when an earlier step failed, its verdict in `insight`. `mode`:
    a CheckMode or its name ("full" when None; check_answer reads MVP_BRAIN_CHECK)."""
    cm = check_mode(mode) if mode is not None else FULL
    if cm.rule("values"):
        return check_sentence_values(sentence, ledger, turn, where, index, mode=cm, with_flags=True)
    turn = turn or Turn()
    state = state if state is not None else {}
    out = Outcome(where, index, sentence)
    raw = " ".join(str(sentence or "").split())
    if not raw:
        out.reasons.append("too_long" if sentence else "bad_marker")
        return out
    if len(strip_markers(raw)) > SENT_MAX:
        out.reasons.append("too_long")
        return out
    markers, bad = parse(raw, ledger, cm.loose)
    fail = out.reasons

    def add(r, d=None, src=None):
        if cm.off and cm.is_off(r, src):
            return   # cells mode: a framing rule is off at the source
        if r not in fail:
            fail.append(r)
        if d:
            out.details.append(d)
            out.notes.setdefault(r, d)
    for b in bad:
        add(b, _bad_detail(raw, ledger))
    for mk in markers:
        if mk.kind == "calc":
            for p in (mk.a, mk.b):
                try:
                    out.cells[p] = _cell(ledger, p)[0]
                except (KeyError, AttributeError):
                    pass
        elif mk.kind in ("value", "count"):
            out.cells[mk.path] = mk.value
    # 3.2 one sentence, one result
    rids = {mk.rid for mk in markers if mk.rid} | {p.split(".", 1)[0] for mk in markers if mk.kind == "calc"
                                                     for p in (mk.a, mk.b)}
    if len(rids) > 1:
        add("two_results", "markers of " + ", ".join(sorted(rids)))
    rid = sorted(rids)[0] if rids else None
    res = ledger.get(rid) if rid else None
    # a sentence with no marker says the turn's window in words: it is read against the turn's first result
    wres = res or next(iter(ledger.by_rid.values()), None)
    out.rid = rid
    plain = strip_markers(raw)
    low = plain.lower()
    # the text with every marked span blanked (what is left must cite nothing)
    blank = list(raw)
    for mk in markers:
        for i in range(mk.start, mk.end):
            blank[i] = " "
    blank = "".join(blank)
    # 3.3 every number cited
    left = _allowed_numbers_out(blank, wres)
    names_idx = ledger.all_names()
    for a, b, _n in _name_spans(left, names_idx):
        left = left[:a] + " " * (b - a) + left[b:]
    if _NUMBERISH.search(left):
        add("uncited_number", "every number needs its marker right after it")
    # 3.4 value, 3.5 calc
    for mk in markers:
        if mk.kind in ("value", "count"):
            if mk.kind == "value" and not mk.said and "platform_all" in cm.loose and _platform_all(raw, mk, ledger):
                continue   # cells mode (mvp23 D1b, in sample): 'all on YouTube[cell]', the cell being every item
            if mk.kind == "value" and not mk.said and _measure(mk.rest, mk.value)[1] not in ("name",):
                add("bad_marker", f"{mk.path} = {_fmt(mk.rest, mk.value) if not isinstance(mk.value, str) else mk.value}")
                continue
            r = check_value(mk)
            if r:
                add(*r)
            elif mk.kind == "value" and _measure(mk.rest, mk.value)[1] == "points":
                # a move in points: its typed sign and the direction words of its clause against the cell's sign
                pts = _points_of(mk.rest, mk.value)
                clause = _clause_around(raw, mk.start, mk.mstart).lower()
                up, down = bool(_UPW.search(clause)), bool(_DOWNW.search(clause))
                if (mk.sign == "+" and pts < 0) or (mk.sign in ("-", "−") and pts > 0) or \
                        (up and not down and pts < 0) or (down and not up and pts > 0):
                    add("direction", f"{mk.path} = {round(pts, 1)} points", src="sign")
        elif mk.kind == "row":
            if not mk.said and re.fullmatch(r"points\[\d+\]", mk.rest) and getattr(ledger.get(mk.rid), "tool", None) \
                    == "learned" and re.fullmatch(r"\s*\[" + re.escape(mk.path) + r"\]\s*\.?\s*", raw):
                # mvp20 tune (the live run's B10): SPEC 4.3 step 4's own shape for a learned point, the point being
                # exactly its marker ("[r1.points[0]]"), failed here as a row marker with no name before it; it is the
                # shape the learned rule (_non_sheet) requires, and code puts in the point's checked text
                continue
            if not mk.said:
                nm = _row_names(mk.value, mk.rest)
                if isinstance(mk.value, dict) and mk.value.get("title"):
                    # an item's title is third-party text: never put back into a message to the model
                    add("wrong_name", f"the words before {mk.path} are not that item's title")
                else:
                    add("wrong_name", f"{mk.path} is '{_clip(nm[0]) if nm else '?'}'")
        elif mk.kind == "calc":
            if len({mk.a.split('.', 1)[0], mk.b.split('.', 1)[0]}) > 1:
                add("two_results", f"{mk.a} and {mk.b}")
                continue
            if not mk.said:
                add("bad_marker", f"{mk.op}({mk.a}, {mk.b})")
                continue
            r = check_calc(mk, ledger, _clause_around(raw, mk.start, mk.mstart).lower())
            if r:
                add(*r, src="calc")
            elif cm.cells:
                r = _cross_row_move(mk)
                if r:
                    add(*r)
    if cm.cells:
        r = _mixed_move(markers) or _window_median_of_row(markers, res)
        if r:
            add(*r)
    # value markers of a count of opens said as "videos" (re-opens are not videos); a count of days said as videos,
    # a count of videos said as days; a median said as an average (step 1 fix: one table of key to noun)
    for mk in markers:
        if mk.kind != "value":
            continue
        after = raw[mk.end:mk.end + 60]
        if mk.key in OPEN_KEYS and _VIDEO_NOUN.match(after):
            add("wrong_measure", f"{mk.path} counts openings, not videos")
        elif mk.key in DAY_KEYS and _VIDEO_NOUN.match(after):
            add("wrong_measure", f"{mk.path} counts days ({mk.value}), not videos")
        elif mk.key in ITEM_KEYS and _DAY_NOUN.match(after):
            add("wrong_measure", f"{mk.path} counts videos ({mk.value}), not days")
        if "median" in (mk.key or "") and _AVERAGE.search(low):
            add("wrong_measure", f"{mk.path} is a median, not an average")
        if mk.kind == "calc" and any(_family(p.split(".", 1)[1]) == "opens" for p in (mk.a, mk.b)) and \
                re.search(r"\bvideos?\b", raw[mk.end:mk.end + 30]):
            add("wrong_measure", "a count of openings is not a count of videos")
    # 3.6 rows and names
    cited_rows = {}   # row rest -> rid
    for mk in markers:
        if mk.kind == "row" and mk.said:
            cited_rows[mk.rest] = mk.rid
        if mk.kind == "value" and mk.owner:
            cited_rows.setdefault(mk.owner, mk.rid)
        if mk.kind == "calc":
            for p in (mk.a, mk.b):
                ow = _owner(p.split(".", 1)[1])
                if ow:
                    cited_rows.setdefault(ow, p.split(".", 1)[0])
    allowed_scope = set()
    if res is not None:
        f = res.sheet.get("filters") or {}
        for v in (f.get("topic"), f.get("channel")):
            if isinstance(v, str) and v.strip():
                allowed_scope.add(_low(v))
        for k, v in ((res.meta or {}).get("resolved") or {}).items():
            allowed_scope.add(_low(k))
        for p in scope_parts(res):   # the labels of the tools' scope ("only gaming (area)": "gaming")
            if p.get("label"):
                allowed_scope.add(_low(p["label"]))
    cited_names = {}
    for rest_, rid_ in cited_rows.items():
        r_ = ledger.get(rid_)
        try:
            row = _resolve(r_.sheet, rest_)
        except (KeyError, AttributeError):
            continue
        if isinstance(row, dict):
            for n in _row_names(row, rest_):
                cited_names.setdefault(_low(n), rest_)
        elif isinstance(row, str):
            cited_names.setdefault(_low(row), rest_)
    blank2 = list(raw)
    for mk in markers:
        if mk.kind in ("row",) or (mk.kind == "value" and isinstance(mk.value, str)):
            for i in range(mk.start, mk.end):
                blank2[i] = " "
        else:
            for i in range(mk.mstart, mk.end):
                blank2[i] = " "
    blank2 = _remove_phrases("".join(blank2), _window_phrases(wres) if wres else [])
    plain_names = []
    for a, b, n in _name_spans(blank2, names_idx, turn.names):
        base_n = n
        if base_n in cited_names or base_n in allowed_scope:
            plain_names.append((a, b, base_n))
            continue
        if "own_fields" in cm.loose:
            fld = _own_field_of(base_n, a, markers, ledger)
            if fld:
                # mvp25 cells loosening (run1's N014, N063; the looks' D03.1, D04.0, F06.0, F10.0, F15.0): a name the
                # row cited right before it holds in its own field (an item's channel, a channel's or a theme's
                # area or theme) is cited by that row, and read as that field's slot
                cited_names.setdefault(base_n, fld)
                plain_names.append((a, b, base_n))
                continue
        add("uncited_name", f"'{_clip(blank2[a:b])}' is named with no marker")
    if cm.rule("date_owner"):
        r = _date_owner(markers, {(cited_rows.get(cited_names[n_].split(".")[0]) or rid,
                                   re.sub(r"\.(?:channel|theme|area)$", "", cited_names[n_]))
                                  for _a, _b, n_ in plain_names if n_ in cited_names})
        if r:
            add(*r)
    # capitalised words that are no name (the first word too)
    caps_text = blank2
    for a, b, _n in _name_spans(caps_text, names_idx, list(turn.names) + list(allowed_scope)):
        caps_text = caps_text[:a] + " " * (b - a) + caps_text[b:]
    titles = []
    for mk in markers:
        if mk.kind == "row" and isinstance(mk.value, dict) and isinstance(mk.value.get("title"), str):
            titles.append(mk.value["title"])
            if isinstance(mk.value.get("channel"), str):
                titles.append(mk.value["channel"])   # a cited item's own channel may be named (step 4)
        elif "quoted_title" in cm.loose and mk.kind == "value" and mk.owner and \
                re.fullmatch(r"items\[\d+\]", mk.owner) and res is not None and mk.rid == res.rid:
            # mvp25 cells loosening (run1's N049.0): the title of an item one of whose cells is cited, said in quotes
            try:
                it_ = _resolve(res.sheet, mk.owner)
            except KeyError:
                it_ = None
            if isinstance(it_, dict) and isinstance(it_.get("title"), str):
                qt = it_["title"].strip()
                if re.search(r"[\"“]" + re.escape(qt) + r"[\"”]", raw, re.I):
                    titles.append(qt)
    caps_text = _remove_phrases(caps_text, titles)
    caps_text = re.sub(r"\"[^\"]{1,90}\"|“[^”]{1,90}”", lambda m: " " * len(m.group(0)), caps_text) if titles else \
        caps_text
    for m in re.finditer(r"(?<![\w'’-])([A-Z][\w'’&-]*)", caps_text):
        w = m.group(1).lower().strip("'’")
        w0 = re.split(r"['’]", w)[0]
        if w in OPENERS or w0 in OPENERS or w in I.ALLOWED_CAPS or w0 in I.ALLOWED_CAPS or \
                any(x.startswith(w0[:3]) for x in _MONTHS if len(w0) >= 3 and w0[:3] == x[:3]) or \
                w0 in I.WEEKDAYS or w0.rstrip("s") in I.WEEKDAYS or w0 in ("shorts", "reels", "reel", "youtube's"):
            continue
        if re.fullmatch(r"[a-z]{3,}ly", w0) and not m.start():
            continue   # an adverb opening the sentence ("Mostly", "Overwhelmingly"): a word, not a name
        if not caps_text[:m.start()].strip() and w0 in ("is", "was", "were", "are", "had", "has", "did"):
            continue
        if "hour_word" in cm.loose and w0 == "hour" and _hour_cell_after(raw, m.end(), markers):
            continue   # mvp25 cells loosening (run1's N027.0): "Hour 18[...hour]" names an hour cell
        add("unknown_name", f"'{_clip(m.group(1), 30)}' is not a name of the results")
    # 3.7 outside text in a history sentence
    for mk in markers:
        if mk.kind == "row" and (_APPOSITIVE.match(raw[mk.end:]) or _KNOWN_FOR.match(raw[mk.end:])):
            add("outside_in_history")
        elif mk.kind == "row" and not re.match(r"^items\[", mk.rest) and not (
                re.match(r"^(?:themes|areas|fields)\[", mk.rest) and
                re.match(r"^\s*(?:posts|videos|clips|reels|shorts|items)\b\s*(?:[,.;:]|$|and\b|from\b|in\b|on\b)",
                         raw[mk.end:], re.I)) and \
                _ENTITY_PRESENT.match(raw[mk.end:]):
            # (mvp20 tune, the live run's I05: "3 Home cooking[r1.themes[1]] posts." read "posts" as a verb: an area
            # or a theme posts, makes or is nothing in the world; what a CHANNEL is or does stays outside knowledge)
            cl_end = _BREAKS.search(raw, mk.end)
            cl = raw[mk.end:cl_end.start() if cl_end else len(raw)]
            if not _BRACKET.search(cl):
                add("outside_in_history", "what a channel is or does is outside knowledge: put it in outside")
    for a, b, _n in plain_names:
        if _APPOSITIVE.match(blank2[b:]) and re.match(r"^\s*,\s*(?:a|an|the)\s+\w+\s+(?:channel|creator|show|"
                                                      r"series|youtuber|artist|brand|studio)\b", blank2[b:], re.I):
            add("outside_in_history")
    wl = _remove_phrases(low, [p.lower() for p in _window_phrases(wres)] if wres else [])
    byp_ = ((res.sheet.get("totals") or {}).get("by_platform") or {}) if res is not None and res.is_sheet else {}
    for p_ in ("youtube", "instagram"):
        if isinstance(byp_, dict) and byp_.get(p_) and all(not v for k, v in byp_.items() if k != p_) and \
                any(mk.rid == res.rid for mk in markers):
            # mvp20 fix (the recount's F02.0, D07.0: "4 videos, all of them on YouTube" when all 4 were): every item
            # of the cited result is that platform's, so "on YouTube" says where their own items were
            wl = re.sub(r"\bon " + p_ + r"\b", " ", wl)
        if any(mk.kind == "value" and mk.path.endswith(".by_platform." + p_) for mk in markers):
            # (mvp20 tune, the audit's T56, run2's C10: "126[r1.totals.by_platform.youtube] ... on YouTube" says where
            # their own count was, a cell of their history, not a claim about the world)
            wl = re.sub(r"\bon " + p_ + r"\b", " ", wl)
    if res is not None and any(p["kind"] == "platform" and p["words"] == ["youtube"] for p in scope_parts(res)):
        # merge seam: a result the tools scoped to YouTube only says its scope as "on YouTube" (not a world claim)
        wl = re.sub(r"\bon youtube\b", " ", wl)
    if WORLD_CLAIMS.search(wl):
        add("outside_in_history", "claims about the world go in outside")
    if _UNRECORDED.search(wl):
        add("outside_in_history", "the export records what they opened, liked or saved, not whom they follow")
    # 3.9 claims with no marker (step 1 fix, F32d: a first or a last said by a date with no marker is a claim too)
    if not markers and (_CONSUME.search(low) or _COMPARATIVE.search(low) or _RANK.search(low) or (
            re.search(r"\b(?:first|last|latest|earliest|newest|oldest|most recent)\b", low) and _DATE_IN.search(low))):
        add("uncited_claim", "a claim about their history needs its marker", src="nomarker")
    elif markers and res is not None and res.is_sheet:
        r_ = _bare_clause(raw, markers, wres)
        if r_:
            add(*r_, src="bare")
    if _not_english(plain) and ((wres.sheet.get("lang") if wres is not None else None) or "en") == "en":
        # the checks read the result's own language (insight's Spanish rules run on a Spanish sheet)
        add("language", "the checks read English only")
    # 3.10 psych, outcome, limits; watch time
    if PSYCH.search(low):
        add("psych")
    if OUTCOME.search(low):
        add("outcome")
    no_win = re.sub(r"where your (?:youtube |instagram )?export ends", " ",
                    _remove_phrases(low, [p.lower() for p in _window_phrases(wres)] if wres else []))
    if LIMITS.search(no_win) and not cm.is_off("limits", "words"):
        add("limits")
    elif _SELF_TALK.search(plain):
        # mvp20 fix, after the final live runs (the held-out second look's I02.0: "I found no dating advice theme or
        # channel in your history, so that label doesn't match anything I can count", on a turn that unlocked the
        # topic and counted 50 of its videos): what the assistant found or can count is a limits line code writes
        add("limits", "say what the results hold; what was or was not found is code's line", src="self")
    if WATCH_TIME.search(_hour_cells_out(raw, markers) if "hour_word" in cm.loose else low):
        add("watch_time")
    # 3.11 sensitive
    if _sensitive(plain, turn):
        add("sensitive")
    # 3.12 least; rank words on a least result; ties
    if res is not None:
        order = (res.meta or {}).get("order") or "most"
        rows0 = [mk for mk in markers if mk.kind in ("row", "value") and mk.owner and re.search(r"\[0\]$", mk.owner)]
        if _LEAST.search(low) and _least_of_whole_list(markers, res):
            pass   # mvp20 fix (the recount's A06.0): the last row of a complete list, strictly its smallest
        elif _LEAST.search(low):
            if not (order == "least" and (res.meta or {}).get("complete") is True and rows0):
                add("least", f"{res.rid} is ordered by {order}" + ("" if (res.meta or {}).get("complete") else
                                                                    ", not over every entity"))
            elif not any(_smallest(res, mk.owner) for mk in rows0):
                # the result is ordered by least, but the list cited is not the one it ranked (a sheet's other lists
                # keep their "most" order): its first row must be the smallest of its list, by code's own reading
                add("least", f"{res.rid}'s list cited is not ranked from the least")
        if order == "least" and _RANK.search(re.sub(r"\bthe least\b|\bleast\b", " ", low)):
            add("rank", f"{res.rid} is ordered by least: its first row is the smallest")
        r_ = _close_check(low, markers, res)
        if r_:
            add(*r_)
        if (_RANK.search(low) or _LEAST.search(low) or re.search(r"\bmost[- ]\w+|\bbusiest\b|\bpeak\b", low)) and rows0:
            # ("busiest" / "peak": mvp20 tune, once "your busiest hour" is no longer read as watch time, a busiest hour
            # tied with the next one is a tie like any other rank word's)
            for mk in rows0:
                tie = _tie(res, mk.owner, opens=((res.meta or {}).get("order") == "most_opened"))
                if tie:
                    add("tie", tie)
                    break
        # 3.13 rank with hidden rows (the founder's answer 4: code's scope line says it)
        hid = (res.meta or {}).get("hidden") or {}
        if hid.get("rank_hidden_above") and _RANK.search(low):
            out.hidden_rank = True
        # step 1 fix (the verifier audit, F45, F45b, F46, F46b: "In 2024 you opened 8 videos" of 58 with the private
        # topic; "100% of what you opened", "everything you opened"): any number of a result that left private items
        # out is a number of what is shown, so the scope line says the private topics were left out (SPEC 4.3 step 13
        # widened from rank words to every count, share, calc and "all" word)
        if int(hid.get("sensitive") or 0) > 0 and (any(mk.kind in ("value", "count", "calc") and
                                                        (mk.rid == res.rid or mk.a.startswith(res.rid + "."))
                                                        for mk in markers) or _RANK.search(low) or
                                                    re.search(r"\b(?:everything|all of|every|only|nothing but)\b",
                                                              low)):
            out.hidden_rank = True
            # a claim of everything ("everything you opened came from", "100% of what you opened") cannot be true of a
            # result that left private items out: no line under it makes it true, so it is dropped
            if re.search(r"\b(?:everything|all of (?:what|it|them)|every (?:video|item|one)|nothing but|100 ?%|"
                         r"all you)\b", low) or any(mk.kind == "value" and _measure(mk.rest, mk.value)[1] == "share"
                                                   and float(mk.value) >= 0.995 for mk in markers):
                add("private_total", f"{res.rid} left {int(hid.get('sensitive'))} private items out: 'all' is not "
                                     "all of what they opened")
        r_ = _ordinal_check(low, markers, res)
        if r_:
            add(*r_)
        r_ = _group_check(markers, res, ledger)
        if r_:
            add(*r_)
        r_ = _calc_owners(raw, markers, res)
        if r_:
            add(*r_)
        r_ = _cut_count(raw, markers, res)
        if r_:
            add(*r_)
        r_ = _first_last(low, markers, res)
        if r_:
            add(*r_)
    # 3.15 window words; the end value of a change inside the base period's words
    cites_prev = any((mk.rest.startswith("previous.") or (mk.key or "").startswith("previous_") or
                      mk.key in ("change_vs_previous", "change_pts", "change")) for mk in markers
                     if mk.kind == "value") or any(
        ".previous" in p or p.split(".", 1)[1].startswith("previous.") for mk in markers if mk.kind == "calc"
        for p in (mk.a, mk.b))
    period_cells = any(re.match(r"^(?:periods|eras|change|areas_change|seasonal)\b", p.split(".", 1)[1])
                       for mk in markers for p in ([mk.path] if mk.kind != "calc" else [mk.a, mk.b]) if "." in p)
    # (a date said by a date marker is checked against its own cell: its words are left out here)
    wtext = list(raw)
    for mk in markers:
        dated = mk.kind == "value" and isinstance(mk.value, str) and _measure(mk.rest, mk.value)[1] == "date"
        for i in range(mk.start if dated else mk.mstart, mk.end):
            wtext[i] = " "
    r = _window_check("".join(wtext), wres, cites_prev, turn, period_cells)
    if r:
        add(*r)
    r = _end_in_base(raw, markers, res, turn)
    if r:
        add(*r)
        if cm.rule("period_bind") and not (res is not None and res.window()[0] and _prev_range(res) == res.window()):
            # mvp25 cells rule (the second attack's f08; the planted f_prev_in_now, f_months_swapped, audit_F72,
            # audit_F82, attack_E02): the period-binding part of wrong_window, read from each cell's path (now or
            # before) and the window words said right after it, kept under a cell code
            add("other_period", r[1])
    if cm.rule("period_named"):
        r = _period_named(raw, markers, res, ledger, turn)
        if r:
            add(*r)
    if cm.rule("free_date"):
        r = _free_date(raw, markers, res, ledger)
        if r:
            add(*r)
    if cm.rule("weekday_typed"):
        r = _typed_weekday(raw)
        if r:
            add(*r)
    if cm.rule("item_fields"):
        r = _item_fields(raw, markers, res)
        if r:
            add(*r)
    if cm.rule("length_cell"):
        r = _length_cell(raw, markers, res)
        if r:
            add(*r)
    if cm.rule("pairs_crossed"):
        r = _pairs_crossed(raw, markers)
        if r:
            add(*r)
    # a count of a result filtered to long (or short) videos said without that word
    if res is not None:
        r = _filter_dropped(raw, markers, res)
        if r:
            add(*r)
        # a number, a date or a rank of a result the tools scoped by a name, a weekday or a platform, said without
        # the scope's words (merge seam: the scope lives in meta.filters_said, not in the sheet's filters)
        r = _scope_dropped(raw, markers, res, low)
        if r:
            add(*r)
        r = _verb_dropped(raw, markers, res, low)
        if r:
            add(*r)
        r = _platform_said(raw, markers, res)
        if r:
            add(*r)
        r = _change_period_said(raw, markers, res)
        if r:
            add(*r)
        r = _fix_rules(raw, markers, res, ledger, turn, low, period_cells, cites_prev, cm)
        if r:
            add(r[0], r[1], src=r[2])
    # 3.8 insight's checks, one sentence (sheets only), or the rules of a result that is not a sheet (step 4)
    # (a sentence with no marker is read by insight against the turn's first result: insight's strict render drops a
    # direction or a number with no path, "the mix narrowed")
    ires = res if res is not None else (wres if not markers else None)
    # insight also runs after a failed value or name check, so the repair names every fault at once (its slots hold
    # the cells' true values); not after a marker that does not parse or resolve
    structural = {"bad_ref", "bad_marker", "two_results", "wrong_name", "too_long"}
    if ires is not None and ires.is_sheet and cm.insight != "off" and \
            (not fail or probe or not (set(fail) & structural)):
        try:
            why = insight_check(raw, markers, plain_names, cited_names, ires, where, turn.unlock,
                                loose=cm.loose & _INSIGHT_LOOSE) if cm.loose & _INSIGHT_LOOSE else \
                insight_check(raw, markers, plain_names, cited_names, ires, where, turn.unlock)
            if why and cm.rule("insight_walk") and cm.is_off(why[0], "insight"):
                # mvp25 cells rule (the compound probes p16, p19): when insight's first reason is off, its checks
                # run again walking past every reason that is off, and a later reason counts when it is one of
                # WALK_ACCEPT (a number bound to another row, a name or word the sheet does not hold)
                w2 = insight_check(raw, markers, plain_names, cited_names, ires, where, turn.unlock,
                                   skip=_insight_skip(cm), loose=cm.loose & _INSIGHT_LOOSE)
                if w2 and str(w2[0]).split(":")[0] in WALK_ACCEPT:
                    out.notes["insight_walk"] = f"{why[0]} -> {w2[0]}"
                    why = w2
        except Exception as e:   # noqa: BLE001  (a sentence insight cannot read is dropped, never sent)
            why = ("insight_error", type(e).__name__)
        if why and cm.is_off(why[0], "insight"):
            # cells mode: insight's checks stop at their first reason; a first reason that is off counts as none
            # (a later reason of insight's own is reached only by the rule insight_walk, DESIGN 24.8)
            out.notes["insight_off"] = str(why[0])
            why = None
        out.insight = why[0] if why else None
        if why and (not fail or not (set(fail) & structural)):
            if not fail:
                out.layer = "insight"
            add(*why)
    elif not fail and res is not None and not res.is_sheet:
        why = _non_sheet(raw, markers, res, low, cm.loose) if "quoted_title" in cm.loose else \
            _non_sheet(raw, markers, res, low)
        if why:
            add(*why)
    # (a sentence with no marker holds plain words only: no number, name or claim passed the steps above)
    if not fail:
        out.sent = plain
    elif out.layer is None:
        out.layer = "marker"
    return out


def _tie(res, owner, opens=False):
    """A rank word on the first row of a list whose second row has the same value (`opens`: an item list ranked by
    times opened, step 1 fix F22: "your most-watched video" when every row was opened once)."""
    try:
        lp = re.sub(r"\[0\]$", "", owner)
        lst = _resolve(res.sheet, lp)
    except KeyError:
        return None
    if not isinstance(lst, list) or len(lst) < 2 or not all(isinstance(x, dict) for x in lst[:2]):
        return None
    for k in ("items", "share", "n") + (("times_opened",) if opens else ()):
        a, b = lst[0].get(k), lst[1].get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if a == b:
                return f"{res.rid}.{lp}[0] and [1] are tied at {a}"
            return None
    return None


def _list_and_index(owner):
    m = re.match(r"^(?P<lst>.*)\[(?P<i>\d+)\]$", owner or "")
    return (m.group("lst"), int(m.group("i"))) if m else (None, None)


def _row_value(res, lst, i, key=None):
    try:
        row = _resolve(res.sheet, f"{lst}[{i}]")
    except KeyError:
        return None, None
    if not isinstance(row, dict):
        return None, None
    for k in ([key] if key else []) + ["items", "share", "n", "times_opened"]:
        if isinstance(row.get(k), (int, float)) and not isinstance(row.get(k), bool):
            return k, row[k]
    return None, None


def _ordinal_check(low, markers, res):
    """A place said by an ordinal ("came second", "fourth") must be the cited row's place in its list, and the row
    may not tie the rows beside it (step 1 fix, F17, F21)."""
    m = _ORD_RX.search(low)
    if not m:
        return None
    rows = [mk for mk in markers if mk.kind in ("row", "value") and mk.owner and mk.rid == res.rid]
    if not rows:
        return None
    lst, i = _list_and_index(rows[0].owner)
    if lst is None:
        return None
    want = _ORDINAL[m.group(0).lower()]
    if i + 1 != want:
        return "rank", f"{res.rid}.{lst}[{i}] is number {i + 1} of its list, not {m.group(0).lower()}"
    k, v = _row_value(res, lst, i)
    for j in (i - 1, i + 1):
        if j < 0 or k is None:
            continue
        _k2, v2 = _row_value(res, lst, j, k)
        if v2 is not None and v2 == v:
            return "tie", f"{res.rid}.{lst}[{i}] and [{j}] are tied at {v}"
    return None


_GROUP_FIELD = {"themes": "theme", "areas": "area"}


def _group_check(markers, res, ledger):
    """A row placed in a group by markers (a channel "(Gaming clips[r1.themes[0]])", "part of", "inside" a theme;
    a channel or a theme in an area) when the group row has no number of its own in the sentence: the child row's
    own theme or area must be that group (step 1 fix, F28b, F29b, F30c, F30d, F30f). A sentence that sets a number
    of the group row beside the child's compares them instead, which other steps check."""
    groups, kids = [], []
    for mk in markers:
        if mk.kind != "row" or mk.rid != res.rid:
            continue
        lst, _i = _list_and_index(mk.rest)
        top = (lst or "").split(".")[-1].split("[")[0]
        if top in _GROUP_FIELD and "." not in (lst or ""):
            groups.append(mk)
        if top in ("channels", "themes") or (lst and "." in lst):
            kids.append(mk)
    if not groups:
        return None
    valued = {mk.owner for mk in markers if mk.kind == "value" and mk.owner} | {
        _owner(p.split(".", 1)[1]) for mk in markers if mk.kind == "calc" for p in (mk.a, mk.b)}
    by_list = {}
    for g in groups:
        if g.rest in valued:
            continue
        glist = _list_and_index(g.rest)[0]
        by_list.setdefault(glist, []).append(g)
    for glist, gs in by_list.items():
        gnames = {_low((g.value or {}).get(I._record_name_key(g.value) or "name")) for g in gs}
        field_ = _GROUP_FIELD[glist]
        for k in kids:
            if k in gs or any(k.rest.startswith(g.rest + ".") for g in gs):
                continue   # a nested row sits inside its own group
            if _list_and_index(k.rest)[0] == glist:
                continue   # two rows of one list: a comparison, not a placement
            have = (k.value or {}).get(field_) if isinstance(k.value, dict) else None
            if not isinstance(have, str):
                return "wrong_group", f"{k.path} carries no {field_} to place it in {gs[0].path}"
            if _low(have) not in gnames:
                return "wrong_group", f"{k.path}'s {field_} is '{_clip(have, 40)}', not " + \
                    " or ".join(g.path for g in gs)
    return None


def _calc_owners(raw, markers, res):
    """A calc of two rows' cells is said of those two rows: no other row of the same list is named in the sentence,
    and both rows are named (step 1 fix, F52: "Clip Factory made 32 more than Pan Theory" where the 32 was against
    Pixel Pencil)."""
    low = _low(strip_markers(raw))
    for mk in markers:
        if mk.kind != "calc":
            continue
        oa, ob = _owner(mk.a.split(".", 1)[1]), _owner(mk.b.split(".", 1)[1])
        if not oa or not ob or oa == ob:
            continue
        la, lb = _list_and_index(oa)[0], _list_and_index(ob)[0]
        for r in markers:
            if r.kind == "row" and r.rid == res.rid and _list_and_index(r.rest)[0] in (la, lb) and \
                    r.rest not in (oa, ob):
                return "calc", f"{mk.op}({mk.a}, {mk.b}) is of {oa} and {ob}, not {r.rest}"
        for own in (oa, ob):
            try:
                row = _resolve(res.sheet, own)
            except KeyError:
                continue
            names = _row_names(row, own) if isinstance(row, dict) else []
            if names and not any(re.search(r"(?<!\w)" + re.escape(_low(n)) + r"(?!\w)", low) for n in names):
                return "calc", f"{mk.op}({mk.a}, {mk.b}): name {own} ('{_clip(names[0], 40)}') in the sentence"
    return None


def _cut_count(raw, markers, res):
    """A count marker of a ranked list that the tools cut is the length of what is shown, not of everything: it
    passes only as "the top N" (step 1 fix, F67: "videos from 7[r1.channels.count] channels" of 8)."""
    ro = (res.meta or {}).get("rows_of") or {}
    for mk in markers:
        if mk.kind != "count" or mk.rid != res.rid:
            continue
        lp = mk.rest[:-len(".count")] if mk.rest.endswith(".count") else ""
        total = ro.get(lp) if lp in ro else None
        cut = (total is not None and total > mk.value) or (total is None and "." in lp and
                                                           (res.meta or {}).get("truncated"))
        if cut and not re.search(r"\b(?:top|first|leading|biggest)\s+(?:\w+\s+)?$", raw[:mk.start].lower()):
            return "wrong_value", (f"{mk.path} is the {mk.value} rows shown of {total}: say 'the top {mk.value}'"
                                   if total is not None else f"{mk.path} is a list cut to fit: say 'the top'")
    return None


def _first_last(low, markers, res):
    """On a first or a last result, a 'first' or a 'last' said with a date is the date of the result's first item
    (step 1 fix, F31c: a channel's first_watched said as the subject's first)."""
    if res.sheet.get("kind") not in ("first", "last") or not re.search(
            r"\b(?:first|last|latest|most recent|earliest|newest|oldest)\b", low):
        return None
    dated = [mk for mk in markers if mk.kind == "value" and isinstance(mk.value, str) and
             _measure(mk.rest, mk.value)[1] == "date" and mk.rid == res.rid]
    for mk in dated:
        if not re.fullmatch(r"items\[0\]\.(?:when|at|date)", mk.rest):
            return "first_last", f"the {res.sheet.get('kind')} is {res.rid}.items[0].when, not {mk.path}"
    return None


_VERB_LIST = re.compile(r"\b(?:opened|watched),\s+(?:liked|saved)(?:,)?\s+(?:or|and)\s+(?:saved|liked)\b", re.I)


def _bare_clause(raw, markers, res):
    """A clause of a marked sentence that holds no marker and still claims something about their history (a rank, a
    peak, a direction, a 'before'): the claim is of no cell (step 1 fix, F39, F37b)."""
    spans = [(mk.start, mk.end) for mk in markers]
    win = [p.lower() for p in _window_phrases(res)] if res else []
    # (mvp20 tune, the live run's B04: "you opened, liked or saved 192[r2.totals.items] items" was cut at its comma and
    # its bare "you opened" read as a claim): the base's own list of verbs is one phrase, not two clauses
    cut_text = _VERB_LIST.sub(lambda m: m.group(0).replace(",", " "), raw)
    cuts = [0] + [m.end() for m in _CLAUSE_BREAKS.finditer(cut_text)] + [len(raw) + 1]
    for a, b in zip(cuts, cuts[1:]):
        cl = raw[a:b - 1] if b <= len(raw) else raw[a:]
        if not cl.strip() or any(x < b and a < y for x, y in spans):
            continue
        t = _remove_phrases(cl.lower(), win)
        t = re.sub(r"\b(?:in|during|over)\s+the\s+(?:\d+|four)\s+weeks\s+before\b", " ", t)
        # a base phrase ("of the art videos you opened lately") is a relative clause, not a claim
        t = re.sub(r"\b(?:videos?|items?|what|everything|things|clips?|posts?|ones|those|that)\s+(?:that\s+|which\s+)?"
                   r"you\b.*$", " ", t)
        if _CLAUSE_CLAIM.search(t) or _CONSUME.search(t):
            return "uncited_claim", f"'{_clip(cl.strip(), 50)}' claims something with no marker"
    return None


def _not_english(text):
    es, en = len(_ES_WORDS.findall(text)), len(_EN_WORDS.findall(text))
    return es >= 2 and es > en


def _smallest(res, owner):
    """The first row of its list holds the smallest value of the list (items, else share); a tie counts as not."""
    try:
        lst = _resolve(res.sheet, re.sub(r"\[0\]$", "", owner))
    except KeyError:
        return False
    if not isinstance(lst, list) or not lst or not all(isinstance(x, dict) for x in lst):
        return False
    for k in ("items", "share", "n"):
        vals = [x.get(k) for x in lst]
        if all(isinstance(v, (int, float)) for v in vals):
            return all(vals[0] < v for v in vals[1:])
    return False


def _filter_dropped(raw, markers, res):
    f = res.sheet.get("filters") or {}
    said = " ".join(str(x) for x in ((res.meta or {}).get("filters_said"), (res.meta or {}).get("base")) if x).lower()
    length = f.get("length") or ("long" if f.get("without_shorts") or re.search(r"\blong\b|without shorts", said)
                                 else ("short" if re.search(r"\bonly shorts\b|\bshorts only\b", said) else None))
    if not length:
        return None
    word = "long" if length == "long" else r"(?:short|shorts|reels?)"
    if (_RANK.search(raw) or _LEAST.search(raw)) and any(mk.kind in ("row", "value") and mk.rid == res.rid and
                                                        mk.owner for mk in markers) and \
            not re.search(r"\b" + word + r"\b|without shorts|no shorts", raw, re.I):
        # merge seam: a rank among the long videos only ("Pan Theory led") is not the rank of what they opened
        return "filter_dropped", f"{res.rid} ranked only {length} videos ({_clip(said, 60)})"
    for mk in markers:
        if mk.kind != "value" or _family(mk.rest) != "count":
            continue
        if not re.match(r"^(?:totals|previous)\.", mk.rest):
            continue
        tail = raw[mk.end:mk.end + 40]
        m = re.match(r"^\s*((?:[\w&'-]+\s+){0,3}?)(?:videos?|items?|posts?|clips?)\b", tail, re.I)
        if m and not re.search(r"\b" + word + r"\b", m.group(1), re.I):
            return "filter_dropped", f"{res.rid} counted only {length} videos ({_clip(said, 60)})"
    return None


# the scope lines brain/tools.py writes in meta.filters_said, joined by "; " (tools._filters_said, tools._label_of):
# "only gaming (area)", "without Minecraft builds (theme)", "only videos with 'speedrun' in the title", "on Mondays",
# "YouTube only", and first_last's "watercolor: Watercolor painting (theme)". The length lines ("only videos known to
# be long", "only Shorts and reels") are _filter_dropped's.
_SCOPE_REF = re.compile(r"^(?:(?P<op>only|without)|(?P<subj>[^:]{1,80}):) (?:(?P<label>.+) \((?:area|theme|channel|"
                        r"collection)\)|videos with '(?P<words>.+)' in the title)$")
_SCOPE_DAY = re.compile(r"^on (?P<day>" + "|".join(d.capitalize() for d in
                                                   ("monday", "tuesday", "wednesday", "thursday", "friday",
                                                    "saturday", "sunday")) + r")s$")
_SCOPE_PLATFORM = re.compile(r"^(?P<p>YouTube|Instagram) only$")
_EXCLUDE_WORDS = re.compile(r"\b(?:without|except|excluding|leaving out|left out|other than|not counting|apart from|"
                            r"besides|outside of|minus|setting aside|no)\b", re.I)
_SCOPE_STOP = {"and", "the", "of", "for", "with", "videos", "video", "title", "your", "my"}


def scope_parts(res):
    """[{kind: only|without|subject|weekday|platform, label, words}] of a result the tools scoped (from
    meta.filters_said in the tools' own fixed forms; any other line, the helper's "only <topic>" included, is not a
    scope part here: insight's topic rules read the sheet's filters.topic)."""
    said = (res.meta or {}).get("filters_said") if res is not None else None
    if not isinstance(said, str) or not said.strip():
        return []
    theirs = [k for k in ((res.meta or {}).get("resolved") or {})]
    out = []
    for part in [p.strip() for p in said.split("; ") if p.strip()]:
        m = _SCOPE_REF.match(part)
        if m:
            label = m.group("label") or m.group("words") or ""
            kind = m.group("op") or "subject"
            extra = [m.group("subj")] if m.group("subj") else []
            words = {w for x in [label] + extra + theirs for w in re.findall(r"[a-z0-9]+", _low(x))
                     if len(w) >= 3 and w not in _SCOPE_STOP}
            out.append({"kind": kind, "label": label, "words": sorted(words)})
            continue
        m = _SCOPE_DAY.match(part)
        if m:
            out.append({"kind": "weekday", "label": "", "words": [m.group("day").lower()]})
            continue
        m = _SCOPE_PLATFORM.match(part)
        if m:
            out.append({"kind": "platform", "label": "", "words": [m.group("p").lower()]})
    return out


def _scope_dropped(raw, markers, res, low):
    """A number, a date, a count or a rank word of a scoped result needs the scope's words in the same sentence (a
    channel's count inside "only Minecraft builds" is its Minecraft videos only; a share is of the scoped items): the
    label or their own word for it, and for a "without" an exclusion word too. A sentence that only names a row
    claims nothing the scope changes."""
    parts = scope_parts(res)
    if not parts:
        return None
    mine = [mk for mk in markers if mk.rid == res.rid or (mk.kind == "calc" and mk.a.startswith(res.rid + "."))]
    claims = any(mk.kind != "row" for mk in mine) or (bool(mine) and bool(_RANK.search(low) or _LEAST.search(low)))
    if not claims:
        return None
    # step 1 fix (the verifier audit, F96 to F99: "Speedruns[r1.themes[0]] led" of a result scoped to the subject
    # Speedruns, "art and design[r1.areas[0]] led" of only art and design): a cited row's own name is not the scope
    # said, so the names of the cited rows are blanked before the scope's words are looked for
    t_ = list(raw)
    for mk in markers:
        for i in range(mk.start if mk.kind == "row" else mk.mstart, mk.end):
            t_[i] = " "
    blanked = "".join(t_)
    for mk in markers:
        own = mk.owner if mk.kind in ("row", "value") else None
        if own and mk.rid == res.rid:
            try:
                row = _resolve(res.sheet, own)
            except KeyError:
                row = None
            # mvp20 tune (run2's K02 "... Clip Factory[r1.channels[0]] ... 61[...] videos you opened, counting only
            # Clip Factory", C03, D06.1): the row's OWN name is blanked where it names the row (its marker's span,
            # done above, or the last time it is typed before its value marker), not every time it is written, so a
            # scope said again in words ("counting only Clip Factory", "of your art videos") is the scope said
            if mk.kind != "value":
                continue
            best = None
            for n in (_row_names(row, own) if isinstance(row, dict) else []):
                for m_ in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?!\w)", blanked[:mk.start], flags=re.I):
                    if best is None or m_.start() > best[0]:
                        best = (m_.start(), m_.end())
            if best:
                blanked = blanked[:best[0]] + " " * (best[1] - best[0]) + blanked[best[1]:]
    text = strip_markers(blanked).lower()
    for p in parts:
        hit = any(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", text) for w in p["words"])
        if p["kind"] == "without" and not _EXCLUDE_WORDS.search(text):
            hit = False
        if not hit:
            said = (res.meta or {}).get("filters_said") or ""
            return "filter_dropped", f"{res.rid} counts {_clip(said, 80)}: say it in the sentence"
    return None


_VERBS = {"opened": re.compile(r"\b(?:opened|watched|viewed)\b", re.I), "saved": re.compile(r"\bsaved\b", re.I),
          "liked": re.compile(r"\bliked\b", re.I)}


def _verb_dropped(raw, markers, res, low):
    """A count of a result the tools counted by saves (or likes) said as what they opened, or the reverse (merge seam:
    the tools' meta.base is "of what you saved" for a saved breakdown, and insight's checks read no verb). Step 1 fix
    (the verifier audit, F69b, F85b, F93): a base of everything opened, liked or saved said with one verb ("you've
    watched 98", "of what you opened on Instagram"), and a search of saves said as watched, on every kind of result:
    every verb said must be one of the base's, and a base of three verbs is said with all three or none."""
    base = _low((res.meta or {}).get("base") or "")
    if res.tool == "find":
        base = "of everything you opened, liked or saved"   # items_all_time (the find tool's own note)
    m = re.fullmatch(r"of what you (opened|saved|liked)", base)
    own = {m.group(1)} if m else ({"opened", "liked", "saved"} if base == "of everything you opened, liked or saved"
                                  else None)
    if not own:
        return None
    if not any((mk.rid == res.rid and not mk.rest.startswith("library.")) or
               (mk.kind == "calc" and mk.a.startswith(res.rid + ".")) for mk in markers):
        return None   # (the cells of `library`, things saved and never opened, are of the saves)
    if not res.is_sheet and res.tool not in ("find", "search"):
        return None
    said = {v for v, rx in _VERBS.items() if rx.search(low)}
    if said and (said - own or (len(own) > 1 and said != own)):
        words = "opened, liked or saved" if len(own) > 1 else next(iter(own))
        return "base", f"{res.rid} counts what you {words}: say '{words}'"
    return None


def _change_period_said(raw, markers, res):
    """mvp20 tune (the live run2's C13: "Since 1 January 2021 up to 30 October 2026, art and design came in at
    52%[r1.areas_change.arrived[0].to_share] of what you opened" went out; 52% is its share IN 2026, and since 2021 it
    is 26%): a share of a changes result's periods (areas_change / change rows: from_share, to_share, peak_share; the
    Shorts block) belongs to ONE period ("2021", "2026", the row's peak_period), not to the result's window; the
    sentence says that period's label beside it, or it is wrongly based. (The window's own words are left out first:
    the "2026" of "up to 30 October 2026" names no period.)"""
    # the period labels typed in the sentence (outside every marker and the window's own words), with their places
    blank = list(raw)
    for mk in markers:
        for i in range(mk.mstart, mk.end):
            blank[i] = " "
    blank = "".join(blank)
    for ph in sorted(_window_phrases(res), key=len, reverse=True):
        for m in re.finditer(re.escape(ph), blank, re.I):
            blank = blank[:m.start()] + " " * (m.end() - m.start()) + blank[m.end():]
    for m in re.finditer(r"\b\d{1,2} " + _MON_RX + r"\w* (?:19|20)\d\d\b", blank, re.I):
        blank = blank[:m.start()] + " " * (m.end() - m.start()) + blank[m.end():]
    labs_at = [(m.start(), m.group(0)) for m in
               re.finditer(r"\b(?:" + _MON_RX + r"\w* )?(?:19|20)\d\d\b", blank, re.I)]
    for mk in markers:
        if mk.kind != "value" or mk.rid != res.rid:
            continue
        m = re.match(r"^(areas_change|change)\.(?:(\w+)\[\d+\]\.|(shorts)\.)(from_share|to_share|peak_share)$",
                     mk.rest)
        if not m:
            continue
        blk = res.sheet.get(m.group(1)) or {}
        if m.group(4) == "peak_share":
            try:
                lab = (_resolve(res.sheet, mk.owner) or {}).get("peak_period")
            except (KeyError, AttributeError):
                lab = None
        else:
            src = blk.get("shorts") if m.group(3) else blk
            lab = (src or {}).get("from" if m.group(4) == "from_share" else "to")
        lab = str(lab or "").strip()
        # its period is said in its own stretch of the sentence, between the value markers before and after it
        # ("from 94%[a] in 2021 to 31%[b] in 2026"; the years swapped fail on the first cell)
        vals = sorted(x.start for x in markers if x.kind == "value")
        lo = max([x_.end for x_ in markers if x_.kind == "value" and x_.end <= mk.start] or [0])
        hi = min([x_ for x_ in vals if x_ > mk.start] or [len(raw)])
        mine = [t for t in labs_at if lo <= t[0] < hi]
        if not lab or not any(_low(t[1]) == _low(lab) for t in mine):
            return "wrong_window", f"{mk.path} is the share in {lab or 'one period'}: say 'in {lab}' right beside it"
    return None


_PLAT_NOUN = re.compile(r"^\s*(?:[\w'’-]+\s+){0,2}?(?P<p>youtube|instagram)\b|^\s*(?:[\w'’-]+\s+){0,2}?(?:videos?|items?|"
                        r"clips?|posts?|reels?|shorts)\s+(?:on|from)\s+(?P<q>youtube|instagram)\b", re.I)


def _platform_said(raw, markers, res):
    """mvp20 tune (found while loosening the platform words of a platform-scoped result): a count of the window
    ("142[r1.totals.items] YouTube videos", "130[r1.totals.items] videos on YouTube") or of an area or a theme said as
    one platform's, of a result the tools did NOT scope to that platform, is true only when every item of it is that
    platform's (totals.by_platform); a channel's own count is its platform's by construction."""
    plats = {w for p in scope_parts(res) if p["kind"] == "platform" for w in p["words"]}
    for mk in markers:
        if mk.kind != "value" or mk.rid != res.rid or _family(mk.rest) != "count" or \
                not isinstance(mk.value, (int, float)) or isinstance(mk.value, bool):
            continue
        if not re.match(r"^(?:totals|previous|areas\[\d+\]|themes\[\d+\])\.", mk.rest) or ".by_platform." in mk.rest:
            continue
        m = _PLAT_NOUN.match(raw[mk.end:mk.end + 50])
        if not m:
            continue
        p = (m.group("p") or m.group("q")).lower()
        if p in plats:
            continue
        blk = (res.sheet.get(mk.rest.split(".", 1)[0]) or {}) if mk.rest.startswith(("totals.", "previous.")) else {}
        byp = blk.get("by_platform") if isinstance(blk, dict) else None
        if isinstance(byp, dict) and mk.rest.endswith(".items") and byp.get(p) == mk.value:
            continue
        return "platform_word", f"{mk.path} counts every platform, not only {p.capitalize()}"
    return None


# ------------------------------------------------------------------ mvp20 fix: the two checkers' classes, by rule
# (the hand recount of the held-out answers that went out, and the verifier attack; eval/brain_attack_cases.py). Each
# rule reads what a sentence CLAIMS (a time said with a range word, a qualifier on a count, a comparison, a base, an
# exclusive word) against what its cells can prove, and drops what they cannot; the attack's true sentences and the
# planted set's true twins are the keep figures it is measured on.
def _least_of_whole_list(markers, res):
    """A cited row that is the strictly smallest of a complete list (every row of it shown, not cut), whatever the
    list's order: 'the fewest' of it is proved by the rows themselves."""
    ro = (res.meta or {}).get("rows_of") or {}
    for mk in markers:
        if mk.rid != res.rid or mk.kind not in ("row", "value") or not mk.owner:
            continue
        lst, i = _list_and_index(mk.owner)
        if lst is None or "." in lst:
            continue
        rows = res.sheet.get(lst)
        if not isinstance(rows, list) or ro.get(lst) != len(rows) or (res.meta or {}).get("truncated"):
            continue
        vals = [r.get("items") for r in rows if isinstance(r, dict)]
        if len(vals) == len(rows) and all(isinstance(v, (int, float)) for v in vals) and len(vals) > 1:
            if all(vals[i] < v for j, v in enumerate(vals) if j != i):
                return True
    return False


_SELF_TALK = re.compile(r"\bI (?:found no|find no|couldn'?t find|could not find|did not find|didn'?t find|see no|"
                        r"have no)\b|\banything I can (?:count|see|find)\b|\bgave no checked\b|\bchecked points?\b",
                        re.I)


def _blank_marked(raw, markers):
    """raw with every marker's brackets blanked, and a row marker's or a dated value's said words too (a cited row's own
    name, an item's title, a cell's own date are not words of the sentence)."""
    t = list(raw)
    for mk in markers:
        dated = mk.kind == "value" and isinstance(mk.value, str) and _measure(mk.rest, mk.value)[1] == "date"
        for i in range(mk.start if (mk.kind == "row" or dated) else mk.mstart, mk.end):
            t[i] = " "
    return "".join(t)


_TIME_PH = re.compile(r"\b(?:(?:the\s+)?(?:spring|summer|autumn|winter)(?:\s+of)?(?:\s+(?:19|20)\d\d)?|" + _MON_RX +
                      r"\.?\s+(?:19|20)\d\d|(?:19|20)\d\d|(?:this|last|past|next) (?:week|month|year|spring|summer|"
                      r"autumn|winter)|today|yesterday)\b", re.I)
# the words right before a time that make it a stretch other than the time itself ("since 2021", "by 2026", "up to
# this year", "between 2021 and 2023", "after 30 October", "by the end of 2021")
_PRE_TIME = re.compile(r"\b(?P<w>since|after|before|by|until|till|through|thru|between|from|prior to|following|as of|"
                       r"up to|up until|to|ahead of|pre|post|start of|beginning of|end of|on)\s+(?:the\s+(?:end|start|"
                       r"beginning|middle|close)\s+of\s+)?(?:the\s+)?$", re.I)
_TIME_GAP = re.compile(r"^\s*(?:,|and|or|to|through|thru|-|–|&|and in|or in)\s*$", re.I)
_EVER = re.compile(r"\b(?:ever|all[- ]time|of all time|never before)\b", re.I)
_PERSIST = re.compile(r"\b(?:still|no longer|any ?more|remains?|remained|stayed|stays|as before)\b", re.I)
_BEFORE_PH = re.compile(r"\b(?:the\s+)?(?:(?P<n>\d{1,2}|two|three|four|five|six)\s+)?(?P<u>day|week|month|year|"
                        r"fortnight)s?\s+before\b|\bthe previous (?P<u2>day|week|month|year)\b", re.I)
_UNIT_DAYS = {"day": (1, 1), "week": (7, 7), "fortnight": (14, 14), "month": (28, 31), "year": (365, 366)}


def _time_spans(text, wins, turn):
    """[(start, end, 'day' | 'period', (first, last) or None)] of the times said in text (a day date, a month or a
    year, a season, a relative word)."""
    out = []
    for m in _DATE_IN.finditer(text):
        g = m.groups()
        d_, mon, y = (g[0], g[1], g[2]) if g[0] else (g[4], g[3], g[5])
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(mon.lower()[:3])), None)
        rng = None
        if mi is not None:
            yy = int(y) if y else max((b.year for _a, b in wins), default=None)
            try:
                rng = (date(yy, mi + 1, int(d_)),) * 2 if yy else None
            except ValueError:
                rng = None
        out.append((m.start(), m.end(), "day", rng))
    t2 = _DATE_IN.sub(lambda m: " " * len(m.group(0)), text)
    for m in _TIME_PH.finditer(t2):
        pm = _PHRASE.fullmatch(m.group(0))
        rng = _phrase_range(pm, wins, turn) if pm else None
        out.append((m.start(), m.end(), "period", rng))
    return sorted(out)


def _range_said(raw, markers, res, turn, period_cells, cites_prev):
    """mvp20 fix (the attack's E, D, C, S09 and the recount's F11.0: "Since 2021 you opened 134[periods[0]]", "by 2026
    254[...]", "Between 2021 and 2023", "In 2025 and 2026, ... 87%[peak_share]", "On 30 October 2026, Clip Factory led
    ... 61[...]" of October, "Up to this year", "Your full years before 2026 were ..."): a time said with a word that
    makes it another stretch (since, by, until, up to, before, after, between, from ... to, two times joined by 'and')
    claims that stretch. It passes only where it IS the cited window: 'since' or 'from' its first day (or the first
    year of a history that starts in it, and no period's cell cited), 'up to' / 'to' / 'until' its last day, 'on' a
    one-day window. A time said 'ever' needs a window of all their history."""
    wins = _windows_of(res, True)
    if not wins:
        return None
    said = (res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or ""
    det = f"{res.rid}'s window is '{_clip(said, 90)}'"
    # (the window's own words are read too, not taken out: "2023" of a window of 2023 said "Until 2023" is another
    # stretch; the window's words pass by these same rules, "up to" its last day)
    text = _blank_marked(raw, markers)
    text = re.sub(r"where your (?:youtube |instagram )?export ends", lambda m: " " * len(m.group(0)), text, flags=re.I)
    all_hist = _low(said).startswith("all your history")
    spans = _time_spans(text, wins, turn)
    prev_end, prev_rng = None, None
    for a, b, kind, rng in spans:
        pre = text[max(0, a - 40):a]
        if prev_end is not None and _TIME_GAP.match(text[prev_end:a]) and not (
                prev_rng and rng and any(prev_rng[0] == x[0] and rng[1] == x[1] for x in wins)):
            return "wrong_window", det + f": '{_clip(text[a - 20 if a > 20 else 0:b].strip(), 40)}' joins two times"
        prev_end, prev_rng = b, rng
        m = _PRE_TIME.search(pre)
        if not m:
            continue
        w = " ".join(m.group("w").lower().split())
        if w in ("since", "from", "start of", "beginning of"):
            ok = rng is not None and (kind == "day" or not period_cells) and any(
                rng[0] == x[0] or (all_hist and kind == "period" and rng[0].year == x[0].year and rng[0] <= x[0])
                for x in wins)
        elif w in ("to", "up to", "up until", "until", "till", "through", "thru"):
            ok = kind == "day" and rng is not None and any(rng[0] == x[1] for x in wins)
        elif w == "on":
            ok = kind != "day" or (rng is not None and any(x[0] == x[1] == rng[0] for x in wins))
            if kind != "day":
                continue
        else:
            ok = False
        if not ok:
            return "wrong_window", det + f": '{_clip((m.group(0) + text[a:b]).strip(), 40)}' is another stretch"
    # a period's own cell (a timeline's periods[i]) says its own period as a time of its own ("134[periods[0].items]
    # in 2021"), not only the window's words around it ("Since 5 January 2021 you opened 134[periods[0].items]")
    pspans = [rng for _a, _b, kind, rng in spans if kind == "period" and rng]
    for mk in markers:
        if mk.kind != "value" or mk.rid != res.rid or not re.match(r"^periods\[\d+\]\.", mk.rest):
            continue
        try:
            lab = str((_resolve(res.sheet, mk.owner) or {}).get("label") or "")
        except (KeyError, AttributeError):
            lab = ""
        lr = _label_range(lab) if lab else None
        if any(x.kind == "row" and x.rid == mk.rid and x.rest == mk.owner for x in markers):
            continue   # the period named by its own row marker ("In 2021[r1.periods[0]], ...")
        if lr is not None and lr not in pspans:
            return "wrong_window", f"{mk.path} is the count of {lab}: say '{lab}' beside it"
    if _EVER.search(_low(strip_markers(raw))) and not all_hist:
        return "wrong_window", det + ": 'ever' needs all their history"
    for m in _BEFORE_PH.finditer(text):
        u = (m.group("u") or m.group("u2") or "").lower()
        n = _num_of(m.group("n")) if m.group("n") else 1
        pw = res.prev_window() if hasattr(res, "prev_window") else None
        lo, hi = _UNIT_DAYS.get(u, (0, 0))
        days = (pw[1].toordinal() - pw[0].toordinal() + 1) if pw and pw[0] and pw[1] else None
        if days is None or not (lo * (n or 1) <= days <= hi * (n or 1)):
            return "wrong_window", det + f": '{_clip(m.group(0), 30)}' is not the window before" + (
                f" ({days} days)" if days else "")
    if _PERSIST.search(_low(strip_markers(raw))) and not cites_prev:
        return "wrong_window", "'still' (or 'no longer', 'again') claims another time: cite the window before"
    return None


_PLAT_WORD = re.compile(r"\b(?P<p>youtube|instagram|reels?|ig)\b", re.I)
_LEN_WORD = re.compile(r"\b(?P<s>shorts|short videos?|short ones|reels?)\b|\b(?P<l>long)\b(?!\s+(?:time|ago|while|run))",
                       re.I)
_DAY_WORD = re.compile(r"\b(?P<d>weekends?|weekdays?|mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|"
                       r"sundays?|mornings?|evenings?|nights?|afternoons?)\b", re.I)


def _items_of(res):
    return [x for x in (res.sheet.get("items") or []) if isinstance(x, dict)]


def _cited_rows(markers, res):
    out = []
    for mk in markers:
        if mk.rid != res.rid or mk.kind not in ("row", "value") or not mk.owner:
            continue
        try:
            row = _resolve(res.sheet, mk.owner)
        except (KeyError, AttributeError):
            continue
        if isinstance(row, dict):
            out.append((mk.owner, row))
    return out


def _qualifier_unbound(raw, markers, res):
    """mvp20 fix (the attack's A, B, N03, M05: "61[channels[0].items] of your long videos" of a channel of Shorts,
    "29 of your Instagram videos" of a YouTube channel, "of the Shorts you opened" of a channel of long videos, "of your
    weekend videos", "61 Instagram reels", "34[fields[1].items] YouTube videos" of 30 and 4 reels, "138 videos on
    YouTube, all of them Shorts", "From YouTube alone, ...", "all of them from Instagram", "on Instagram and YouTube" of
    Instagram only): a platform, a length or a day word in a sentence narrows its counts; it is true only when the
    result is scoped to it, a cited cell is that platform's or that length's, or every cited row (or the whole result)
    is of it."""
    marked = [mk for mk in markers if mk.rid == res.rid and mk.kind in ("value", "count", "row", "calc")]
    if not marked:
        return None
    text = _remove_phrases(_blank_marked(raw, markers), _window_phrases(res))
    text = re.sub(r"where your (?:youtube |instagram )?export ends|your (?:youtube|instagram) export|\b(?:mon|tues|"
                  r"wednes|thurs|fri|satur|sun)day,?\s+(?=\d{1,2}\b)|\bshorts (?:and|or) reels\b",
                  lambda m: " " * len(m.group(0)) if not m.group(0).lower().startswith("shorts") else
                  "shorts" + " " * (len(m.group(0)) - 6), text, flags=re.I)
    low = text.lower()
    parts = scope_parts(res)
    plats = {w for p in parts if p["kind"] == "platform" for w in p["words"]}
    days = {w for p in parts if p["kind"] == "weekday" for w in p["words"]}
    f = res.sheet.get("filters") or {}
    fsaid = _low(" ".join(str(x) for x in ((res.meta or {}).get("filters_said"), (res.meta or {}).get("base")) if x))
    length = f.get("length") or ("long" if f.get("without_shorts") or re.search(r"\blong\b|without shorts", fsaid)
                                 else ("short" if re.search(r"\bonly shorts\b|\bshorts only\b", fsaid) else None))
    rests = [mk.rest for mk in markers if mk.kind in ("value", "count") and mk.rid == res.rid] + [
        p.split(".", 1)[1] for mk in markers if mk.kind == "calc" for p in (mk.a, mk.b)]
    rows = _cited_rows(markers, res)
    items = _items_of(res)
    byp = (res.sheet.get("totals") or {}).get("by_platform") or {}
    for m in _PLAT_WORD.finditer(low):
        p = m.group("p").lower()
        if p.startswith("reel") and length == "short":
            continue   # "reels" of a result of Shorts and reels is its length word
        p = "instagram" if p in ("reel", "reels", "ig") else p
        if p in plats or any(r.endswith("by_platform." + p) for r in rests):
            continue
        if p == "youtube" and any(r.endswith("shorts_share") for r in rests):
            continue   # a share of Shorts is of the YouTube videos (Shorts are YouTube's)
        if isinstance(byp, dict) and byp and all((v or 0) == 0 for k, v in byp.items() if k != p) and byp.get(p):
            continue   # every item of the result is that platform's
        if not byp and not items:
            continue   # a sheet that says no platform (a hand-made or round 12 sheet) is not read here
        if rows and all(_row_platform(row, own) == p for own, row in rows):
            continue
        if not rows and items and all(_low(it.get("platform") or "") == p for it in items) and \
                not (res.meta or {}).get("truncated"):
            continue
        return "platform_word", f"{res.rid} is not only {p.capitalize()}'s: cite its by_platform cell or say no platform"
    for m in _LEN_WORD.finditer(low):
        want = "short" if m.group("s") else "long"
        if length == want or (want == "short" and length == "long" and re.search(
                r"\b(?:without|no|not|excluding|leaving out|left out)\s+(?:the\s+)?$", low[:m.start()])):
            continue
        if any(re.search(r"(?:^|\.)(?:shorts|shorts_share|long|long_median_min)$", r) for r in rests):
            continue
        if rows and all(_row_length(row) == want for _own, row in rows):
            continue
        return "length_word", f"{res.rid} counts videos of any length: cite a Shorts cell or say no length"
    for m in _DAY_WORD.finditer(low):
        d = m.group("d").lower().rstrip("s")
        if d in {x.rstrip("s") for x in days}:
            continue
        if d in ("weekend", "weekday") and any(r.endswith(d + "_share") for r in rests):
            continue
        if any(r.endswith("busiest_weekday") for r in rests) and d in I.WEEKDAYS:
            continue
        if d in ("morning", "evening", "night", "afternoon") and any("busiest_hours" in r for r in rests):
            continue
        return "wrong_window", f"{res.rid} counts every day, not only {m.group('d')}"
    return None


def _row_platform(row, own):
    if isinstance(row.get("platform"), str):
        return _low(row["platform"])
    if re.match(r"^channels\[\d+\]$|\.channels\[\d+\]$", own or "") and isinstance(row.get("name"), str):
        return "instagram" if row["name"].startswith("@") else "youtube"
    return None


def _row_length(row):
    s = row.get("shorts_share")
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return "short" if s >= 0.999 else ("long" if s <= 0.001 else None)
    if isinstance(row.get("length"), str):
        return {"long": "long", "short": "short"}.get(_low(row["length"]))
    return None


_CMP_KEY = re.compile(r"\b(?:than|as (?:many|much|often) as|ahead of|beat|beats|beating|outnumber\w*|outpac\w*|"
                      r"overtook|overtaking|surpass\w*)\b", re.I)
_SUM_KEY = re.compile(r"\b(?:together|combined|put together|between them)\b", re.I)
_MORE_W = re.compile(r"\b(?:more|bigger|larger|higher|greater|busier|ahead|beat|beats|outnumber\w*|outpac\w*|"
                     r"overtook|surpass\w*)\b", re.I)
_LESS_W = re.compile(r"\b(?:less|fewer|smaller|lower|quieter)\b", re.I)


def _compare_unbound(raw, markers, res, ledger, turn):
    """mvp20 fix (the attack's F03, P02, D07, X08, G01, G04: "..., more than math[areas[3]] gained", "more than Pan
    Theory and Pixel Pencil together", "as many as in 2021 and 2022 together", "more than Watercolor painting[...]",
    "45% more[calc] videos in 2022 than in 2023" of 2023 against 2022, "Limit Lane made 45% more[calc of the totals]"):
    a comparison claims the value of what it is compared with. The thing after 'than' needs its own value marker (or a
    calc said before it in the clause), the two values must stand in the order the words say, a sum ('together') is
    never a cell, a calc's 'than <time>' names the calc's second window, and a calc of the result's totals is said of
    the result, not of a row."""
    plain_low = _low(strip_markers(raw))
    if _SUM_KEY.search(plain_low):
        return "uncited_claim", "a sum of rows ('together') is not a cell of the results"
    vals = [mk for mk in markers if mk.kind in ("value", "count") and isinstance(mk.value, (int, float)) and
            not isinstance(mk.value, bool)]
    calcs = [mk for mk in markers if mk.kind == "calc"]
    for mk in calcs:
        ops = [p.split(".", 1)[1] for p in (mk.a, mk.b)]
        if all(re.match(r"^(?:totals|previous)\.", o) for o in ops) and any(
                x.kind == "row" or (x.kind == "value" and x.owner) for x in markers if x.rid == mk.a.split(".")[0]):
            return "calc", f"{mk.op}({mk.a}, {mk.b}) is of every item of the window, not of a row"
    braw = _blank_marked(raw, markers)
    for m in _CMP_KEY.finditer(raw):
        if re.search(r"\b(?:other|rather|no more|no less|nothing more)\s+$", raw[max(0, m.start() - 14):m.start()],
                     re.I):
            continue
        cl_end = re.search(r"[,;.]|\band\b(?!\s+(?:the\s+)?\d)", braw[m.end():])
        after_end = m.end() + (cl_end.start() if cl_end else len(raw) - m.end())
        after = [x for x in markers if m.end() <= x.start < after_end or (m.end() <= x.mstart < after_end)]
        before_calc = [c for c in calcs if c.end <= m.start() and not re.search(r"[;.]", raw[c.end:m.start()])]
        if before_calc:
            c = before_calc[-1]
            r = _calc_than_window(braw[m.end():after_end], braw[:m.start()], c, ledger, turn)
            if r:
                return r
            continue
        av = [x for x in after if x.kind in ("value", "count", "calc")]
        if not av:
            r = _rows_compared(raw, markers, m, after, res)
            if r is None:
                continue
            if r:
                return r
            return "uncited_claim", f"'{_clip(strip_markers(raw[m.start():after_end]), 40)}' compares with a value " \
                                    "it does not cite"
        bv = [x for x in vals if x.end <= m.start()]
        a2 = [x for x in av if x in vals]
        if bv and a2 and _family(bv[-1].rest) == _family(a2[0].rest):
            v1, v2 = float(bv[-1].value), float(a2[0].value)
            head = raw[max(0, m.start() - 40):m.start()]
            word = m.group(0).lower()
            if (word == "than" and _MORE_W.search(head) and not v1 > v2) or \
                    (word == "than" and _LESS_W.search(head) and not v1 < v2) or \
                    (word.startswith("as ") and abs(v1 - v2) > 0.005 * max(abs(v1), abs(v2), 1)) or \
                    (word in ("ahead of", "beat", "beats", "beating") and not v1 > v2):
                return "direction", f"{bv[-1].path} = {bv[-1].value}, {a2[0].path} = {a2[0].value}"
    return None


def _rows_compared(raw, markers, m, after, res):
    """A comparison of two rows of one list with no value after 'than' ("more gaming than comedy", "more than math
    gained"): None when the rows' own cells prove it (the key of the value cited before, else the list's count), a
    reason when they disprove it, False when it cannot be read."""
    rows_after = [x for x in after if x.kind == "row" and x.rid == res.rid]
    before = [x for x in markers if x.end <= m.start() and x.rid == res.rid and x.kind in ("row", "value") and x.owner]
    if not rows_after or not before:
        return False
    a_own, b_own = before[-1].owner, rows_after[0].rest
    la, ia = _list_and_index(a_own)
    lb, ib = _list_and_index(b_own)
    if la is None or la != lb:
        return False
    key = before[-1].key if before[-1].kind == "value" and isinstance(before[-1].value, (int, float)) else None
    _k, va = _row_value(res, la, ia, key)
    _k2, vb = _row_value(res, lb, ib, key or _k)
    if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
        return False
    head = raw[max(0, m.start() - 60):m.start()]
    if _MORE_W.search(head) and not va > vb:
        return "direction", f"{res.rid}.{a_own} = {va}, {res.rid}.{b_own} = {vb}"
    if _LESS_W.search(head) and not va < vb:
        return "direction", f"{res.rid}.{a_own} = {va}, {res.rid}.{b_own} = {vb}"
    if not (_MORE_W.search(head) or _LESS_W.search(head)):
        return False
    return None


def _calc_than_window(after, before, c, ledger, turn):
    """A calc of a window against the one before, said 'in A than in B': B is the calc's second window, A its first."""
    try:
        res = ledger.get(c.a.split(".", 1)[0])
    except Exception:   # noqa: BLE001
        return None
    if res is None:
        return None
    cur, prev = res.window(), res.prev_window()
    if not (cur and cur[0] and prev and prev[0]):
        return None
    wins = [cur, prev]
    first_is_now = not _is_before(c.a.split(".", 1)[1])
    now_w, then_w = (cur, prev) if first_is_now else (prev, cur)
    clipped = bool((res.sheet.get("window") or {}).get("clipped"))
    for part, bad in ((after, now_w), (before[-80:], then_w)):
        for _a, _b, kind, rng in _time_spans(_remove_phrases(part, []), wins, turn):
            if rng is not None and kind == "period" and _matches(rng, bad, clipped) and not _matches(
                    rng, then_w if bad is now_w else now_w, clipped):
                return "calc", f"{c.op}({c.a}, {c.b}) is the first window against the second, not the other way"
    return None


_FROM_TO = re.compile(r"\bfrom\b(?P<x>[^.;]{0,80}?)\bto\b", re.I)


def _from_to_swapped(raw, markers):
    """mvp20 fix (the attack's X01 to X03: "went from 13[items] the week before to 14[previous_items]"): 'from A to B'
    says A is the earlier value; a value of the window before after 'to' with one of the window after 'from' is the
    move said backwards."""
    vals = [mk for mk in markers if mk.kind == "value"]
    for m in _FROM_TO.finditer(_blank_marked(raw, markers)):
        a = [x for x in vals if m.start() <= x.start and x.end <= m.end()]
        b = [x for x in vals if x.start >= m.end()]
        if not a or not b:
            continue
        x, y = a[0], b[0]
        if re.search(r"[,;]", raw[m.end():y.start]) and not re.match(r"^\s*(?:the\s+)?$", raw[m.end():y.start]):
            continue
        if _is_before(y.rest) and not _is_before(x.rest):
            return "direction", f"{x.path} is now and {y.path} is before: 'from' the earlier 'to' the later"
        if x.key == "to_share" and y.key == "from_share":
            return "direction", f"{x.path} is the later end of the change"
    return None


_EXCL = re.compile(r"\b(?:only|nothing else|nothing but|on (?:its|their) own|alone|sole(?:ly)?|exclusively|"
                   r"(?:only|just) \d+ (?:areas|themes|channels|topics|kinds|types)|the one (?:theme|channel|area)|"
                   r"your one|one (?:theme|channel|area)\b|was all|were all|"
                   r"all (?:you|of (?:what|it|them|your))|every (?:video|item|one))\b", re.I)
# ("all from <row>" is a row's make-up, not 'nothing else': _all_from reads it)


def _exclusive_words(low, res):
    """The 'only' words of a sentence that claim nothing else was there ("Pan Theory was the only channel", "and nothing
    else", "on its own", "just 4 areas"), not a scope ("counting only long videos", "only gaming") nor 'only once'."""
    scope_w = {w for p in scope_parts(res) for w in p["words"]} | {"long", "shorts", "short", "reels", "youtube",
                                                                     "instagram", "once", "twice", "counting"}
    for m in _EXCL.finditer(low):
        if m.group(0).lower() == "only":
            if re.match(r"\s+(?:about\s+|around\s+)?\d", low[m.end():]):
                continue   # "only 1 video": a small count, not 'nothing else'
            nxt = low[m.end():m.end() + 30].split()
            prv = low[max(0, m.start() - 12):m.start()].split()
            if (nxt and nxt[0].strip(",.") in scope_w) or (len(nxt) > 1 and nxt[1].strip(",.") in scope_w) or \
                    (prv and prv[-1] in ("counting", "with", "showing", "keeping")):
                continue
        return m.group(0)
    return None


def _uncovered(res, lst):
    """How many of the result's items fall in no row of a complete list (rows that do not add up to the total: an
    unlocked topic counted in the total but in no theme row, the private topic, items with no theme), or None."""
    rows = res.sheet.get(lst)
    tot = (res.sheet.get("totals") or {}).get("items")
    ro = ((res.meta or {}).get("rows_of") or {}).get(lst)
    if not isinstance(rows, list) or not rows or not isinstance(tot, (int, float)) or ro != len(rows):
        return None
    vals = [r.get("items") for r in rows if isinstance(r, dict)]
    if not all(isinstance(v, (int, float)) for v in vals):
        return None
    return tot - sum(vals)


def _hidden_claims(low, markers, res, turn):
    """mvp20 fix (the attack's R01, R02, R06, R08 to R11, R05 and the recount's I02.0): an 'only', 'all', 'nothing
    else', 'on its own' or 'just N' of a result that left the private topic out is not true of what they opened; a rank
    or an 'only' of a complete list whose rows leave more items out than its first row holds (I02.0: "the top theme was
    Home cooking with 8" of 58, 50 of them an unlocked topic in no theme row) cannot be proved."""
    hid = (res.meta or {}).get("hidden") or {}
    excl = _exclusive_words(low, res)
    if excl and int(hid.get("sensitive") or 0) > 0:
        return "private_total", f"{res.rid} left {int(hid.get('sensitive'))} private items out: '{excl}' is not " \
                                "all of what they opened"
    rank = _RANK.search(low) or _ORD_RX.search(low) or excl
    if not rank:
        return None
    for own, row in _cited_rows(markers, res):
        lst, i = _list_and_index(own)
        if lst is None or "." in lst:
            continue
        rem = _uncovered(res, lst)
        if rem is not None and rem > 0 and rem >= (row.get("items") or 0):
            return "rank", f"{res.rid}.{lst} leaves {rem} of {(res.sheet.get('totals') or {}).get('items')} items " \
                           "in no row: its first row is not proved the top"
    return None


_ALL_FROM = re.compile(r"\b(?:all|each|every one|entirely|solely|exclusively|only)\s+(?:of\s+(?:them|it|these|those)\s+)?"
                       r"(?:from|by|made by|on)\s+$", re.I)


def _all_from(raw, markers, res):
    """mvp20 fix (the attack's S05: "Gaming clips came to 66 videos, all from Clip Factory[themes[0].channels[0]]" of
    61 and 5): 'all from' a row is true only of a row's own single channel (its channels list has one row, or that
    row's count is the whole row's)."""
    for mk in markers:
        if mk.kind != "row" or mk.rid != res.rid or not _ALL_FROM.search(raw[max(0, mk.start - 40):mk.start]):
            continue
        m = re.match(r"^(?P<own>.+)\.channels\[(?P<k>\d+)\]$", mk.rest)
        ok = False
        if m:
            try:
                parent = _resolve(res.sheet, m.group("own"))
            except (KeyError, AttributeError):
                parent = None
            chs = (parent or {}).get("channels") if isinstance(parent, dict) else None
            if isinstance(chs, list) and chs:
                ch = chs[int(m.group("k"))] if int(m.group("k")) < len(chs) else {}
                ok = len(chs) == 1 or (isinstance(ch, dict) and ch.get("items") == parent.get("items"))
        elif re.fullmatch(r"channels\[\d+\]", mk.rest) and isinstance(mk.value, dict):
            # a channel of the result said to make ALL of a theme's (or an area's) videos: its own theme is that
            # theme, every one of its videos is of it (theme_share 1), and it holds as many as the row cited before
            ch = mk.value
            for x in markers:
                if x.kind == "value" and x.rid == res.rid and x.rest == "totals.items" and x.end <= mk.start:
                    ok = ch.get("items") == x.value   # one channel holds every item of the result
                    continue
                if x.kind not in ("row", "value") or x.rid != res.rid or not x.owner or x.owner == mk.rest or \
                        x.end > mk.start:
                    continue
                try:
                    parent = _resolve(res.sheet, x.owner)
                except (KeyError, AttributeError):
                    continue
                if not isinstance(parent, dict) or not re.fullmatch(r"(?:themes|areas)\[\d+\]", x.owner):
                    continue
                fld = "theme" if x.owner.startswith("themes") else "area"
                same = _low(ch.get(fld) or "") == _low(parent.get("name") or "")
                full = fld == "area" or (ch.get("theme_share") or 0) >= 0.999
                ok = same and full and ch.get("items") == parent.get("items")
        if not ok:
            return "uncited_claim", f"'all from {mk.said}' needs the row's own channel list to have only it"
    return None


_USUALLY = re.compile(r"\b(?:usually|typically|normally|mostly|generally|tend to|tends to|most often|most of the time|"
                      r"always)\b", re.I)


def _usually_hour(low, markers, res):
    """mvp20 fix (the attack's H02: "You usually opened videos at 7 pm[busiest_hours[0].hour]" when 23% were then):
    'usually' of a busiest hour or day needs more than half of the items there."""
    if not _USUALLY.search(low):
        return None
    for mk in markers:
        if mk.rid != res.rid or "busiest_hours[" not in mk.rest:
            continue
        own = re.sub(r"\.hour$", "", mk.rest)
        try:
            share = (_resolve(res.sheet, own) or {}).get("share")
        except (KeyError, AttributeError):
            share = None
        if not isinstance(share, (int, float)) or share <= 0.5:
            return "rank", f"{mk.path}'s hour holds {share if share is not None else '?'} of the items: not 'usually'"
    return None


_WHEN_RX = re.compile(r"^(\d{4}-\d\d-\d\d)(?:[ T](\d{1,2}):(\d\d)\s*([ap]m)?)?", re.I)


def _when_key(w):
    m = _WHEN_RX.match(str(w or ""))
    if not m:
        return None
    h = int(m.group(2)) if m.group(2) else None
    if h is not None and m.group(4):
        h = h % 12 + (12 if m.group(4).lower() == "pm" else 0)
    return (m.group(1), h, int(m.group(3)) if m.group(3) else None)


def _item_order(low, markers, res):
    """mvp20 fix (the attack's Q03, Q05, Q12: "The last video you opened on 30 October was X[items[0]]" of a list
    whose first row is that day's first, "Your first Pan Theory video in October was X[items[1]]", "The first thing you
    saved in October was X[items[3]]"): an item said to be the first or the last (earliest, newest, most recent) is the
    earliest or the latest of the rows shown, by their own times, with no other row at the same time; a list cut to fit
    proves only the end its order starts from."""
    if res.sheet.get("kind") in ("first", "last"):
        return None
    low2 = re.sub(r"\blast (?:week|month|year|spring|summer|autumn|winter|\d+ \w+|day of)\b", " ",
                  _remove_phrases(low, [p.lower() for p in _window_phrases(res)]))
    m = re.search(r"\b(?:(?P<f>first|earliest|oldest)|(?P<l>last|latest|newest|most recent|final))\b", low2)
    if not m:
        return None
    items = _items_of(res)
    cited = [mk for mk in markers if mk.kind == "row" and mk.rid == res.rid and re.fullmatch(r"items\[\d+\]", mk.rest)]
    if not cited or not items:
        return None
    keys = [_when_key(it.get("when")) for it in items]
    if any(k is None for k in keys):
        return None
    order = (res.meta or {}).get("order") or ""
    cut = bool((res.meta or {}).get("truncated")) or (isinstance((res.meta or {}).get("rows_total"), int) and
                                                       (res.meta or {}).get("rows_total") > len(items))
    want_first = bool(m.group("f"))
    if cut and order != ("oldest" if want_first else "newest"):
        return "first_last", f"{res.rid}.items is cut to fit and ordered {order or 'by opens'}: its " \
                             f"{'first' if want_first else 'last'} is not shown"
    i = int(re.search(r"\d+", cited[0].rest).group(0))
    if all(k[1] is None for k in keys):
        # days only (a list over more than a day): the tools order by the full time, so the row the order starts
        # from is the first (oldest) or the last (newest); any other row must be the only one of its day at that end
        if i == 0 and order == ("oldest" if want_first else "newest"):
            return None
        days_ = [k[0] for k in keys]
        end = min(days_) if want_first else max(days_)
        if days_[i] == end and days_.count(end) == 1:
            return None
        return "first_last", f"{cited[0].path} is not the {'first' if want_first else 'last'} of the rows shown"

    def full(k):
        return (k[0], k[1] if k[1] is not None else -1, k[2] if k[2] is not None else -1)
    ks = [full(k) for k in keys]
    target = min(ks) if want_first else max(ks)
    if ks[i] != target or ks.count(target) > 1 or (keys[i][1] is None and sum(k[0] == keys[i][0] for k in keys) > 1):
        return "first_last", f"{cited[0].path} is not the {'first' if want_first else 'last'} of the rows shown " \
                             f"(by their times)"
    return None


_MOTIVE = re.compile(r"\bbecause\b|\bto (?:unwind|relax|chill|escape|de-?stress|switch off|wind down|kill time|pass "
                     r"the time|feel better|learn)\b|\bafter (?:a long day|work|school)\b|\bwhen you (?:were|felt|are) "
                     r"(?:bored|tired|sad|stressed|lonely|anxious)\b|\bout of (?:boredom|habit)\b|\bfor fun\b", re.I)
_TAUGHT = re.compile(r"\b(?:taught|teaches|told|tells|showed|shows|helped|helps|inspired|inspires|convinced|"
                     r"encouraged|encourages|reminded|reminds|wanted|wants|asked)\s+(?:you|them)\b|\b(?:a|an|the)\s+"
                     r"[a-z]+\s+who\b|,?\s+who\s+(?:cooks|makes|draws|paints|plays|lives|is|was|teaches|streams|posts|"
                     r"loves|knows)\b", re.I)


def _library_window(raw, markers, res, turn):
    """mvp20 fix, after the final live runs (the held-out second look's I01.0: "3[r1.library.saved_not_opened[0].n]
    saved Home cooking posts were not opened in 2024" of saves made in 2026): the library block (saved and never
    opened) counts every save of their history, whatever the window, so it is said with no time of the window's."""
    if not any(mk.rid == res.rid and mk.rest.startswith("library.") for mk in markers):
        return None
    wins = _windows_of(res, True)
    text = re.sub(r"where your (?:youtube |instagram )?export ends", " ", _blank_marked(raw, markers), flags=re.I)
    if _time_spans(text, wins, turn) or _LATELY.search(text):
        return "wrong_window", f"{res.rid}.library counts every save of their history, not the window's"
    return None


def _fix_rules(raw, markers, res, ledger, turn, low, period_cells, cites_prev, cm=None):
    """The mvp20 fix rules of one sentence (None or (reason, detail, emitter)). The rules stop at the first hit; in
    cells mode (`cm`) a rule whose code is off is walked past, so it hides no later rule."""
    cm = cm or FULL
    for src, fn in (("library", lambda: _library_window(raw, markers, res, turn)),
                    ("motive", lambda: ("psych", "why they opened something is not in the export")
                     if _MOTIVE.search(low) else None),
                    ("taught", lambda: ("outside_in_history", "what a video or a channel told them, or who makes it, "
                                        "is not in the export") if _TAUGHT.search(low) else None),
                    ("range", lambda: _range_said(raw, markers, res, turn, period_cells, cites_prev)),
                    ("qualifier", lambda: _qualifier_unbound(raw, markers, res)),
                    ("compare", lambda: _compare_unbound(raw, markers, res, ledger, turn)),
                    ("from_to", lambda: _from_to_swapped(raw, markers)),
                    ("hidden", lambda: _hidden_claims(low, markers, res, turn)),
                    ("all_from", lambda: _all_from(raw, markers, res)),
                    ("usually", lambda: _usually_hour(low, markers, res)),
                    ("item_order", lambda: _item_order(low, markers, res)),
                    ("items_count", lambda: _items_count(raw, markers, res)),
                    ("base_unscoped", lambda: _base_unscoped(raw, markers, res)),
                    ("broadened", lambda: _broadened(low, res))):
        r = fn()
        if r and not cm.is_off(r[0], src):
            return r[0], r[1], src
    order = (res.meta or {}).get("order") or "most"
    if order == "least" and _ORD_RX.search(low) and not _LEAST.search(low) and not cm.is_off("rank", "least_ordinal"):
        return "rank", f"{res.rid} is ordered by least: an ordinal says its place from the least", "least_ordinal"
    return None


def _items_count(raw, markers, res):
    """mvp20 fix (the attack's N04: "You have opened 3[r1.items.count] Clip Factory videos" of a first-time result's
    three rows): the count of an item list that shows a first, a last or a page is the rows shown, not all of them."""
    kind = res.sheet.get("kind")
    meta = res.meta or {}
    cut = kind in ("first", "last") or bool(meta.get("truncated")) or (
        isinstance(meta.get("rows_total"), int) and meta.get("rows_total") > len(_items_of(res)))
    if not cut:
        return None
    for mk in markers:
        if mk.kind == "count" and mk.rid == res.rid and mk.rest == "items.count":
            pre = raw[max(0, mk.start - 30):mk.start].lower()
            post = raw[mk.end:mk.end + 30].lower()
            if not re.search(r"\b(?:the|these|those)?\s*(?:first|last|latest|newest|oldest|top)\s*$|here are\s*$", pre) \
                    and not re.search(r"\b(?:shown|listed|here)\b", post):
                return "wrong_value", f"{mk.path} is the {mk.value} rows shown, not every one"
    return None


_BASE_PH = re.compile(r"\b(?:of\s+)?(?:what|everything|all(?: of)? what)\s+you(?:'ve| have)?\s+(?:opened|watched|saved|"
                      r"liked)(?:,?\s*liked\s+or\s+saved)?\b", re.I)


def _scope_words_of(res):
    """(words that say the result's scope, its 'without' parts, its length) for a filtered result, or None."""
    parts = scope_parts(res)
    f = res.sheet.get("filters") or {}
    fsaid = _low(" ".join(str(x) for x in ((res.meta or {}).get("filters_said"), (res.meta or {}).get("base")) if x))
    length = f.get("length") or ("long" if f.get("without_shorts") or re.search(r"\blong\b|without shorts", fsaid)
                                 else ("short" if re.search(r"\bonly shorts\b|\bshorts only\b", fsaid) else None))
    if not parts and length not in ("long", "short"):
        return None
    words = {w for p in parts for w in p["words"]}
    if length == "long":
        words |= {"long"}
    elif length == "short":
        words |= {"short", "shorts", "reels", "reel"}
    return words, any(p["kind"] == "without" for p in parts)


def _base_unscoped(raw, markers, res):
    """mvp20 fix (the recount's B03.0 and F05.0: "Home cooking led what you opened, with 30 long videos" of the long
    videos only, "Minecraft builds is still the largest gaming theme, at 51% of what you opened" of only gaming: 51% is
    of the gaming videos, 23% of what they opened): on a filtered result, a base said in words ("of what you opened",
    "led what you opened") is the base the rank or the share is of; it must carry the scope in its own clause ("of what
    you opened on Sundays", "of the long videos you opened"), not elsewhere in the sentence."""
    sw = _scope_words_of(res)
    if not sw:
        return None
    words, without = sw
    if not any(mk.rid == res.rid for mk in markers):
        return None
    text = _blank_marked(raw, markers)
    for m in _BASE_PH.finditer(text):
        pre = [x.end() for x in re.finditer(r"[,;:—–()]", text[:m.start()])]
        post = re.search(r"[,;:—–()]", text[m.end():])
        cl = text[(pre[-1] if pre else 0):m.end() + (post.start() if post else len(text) - m.end())].lower()
        first = min((mk.start for mk in markers), default=len(text))
        local = cl + " " + (text[:first].lower() if first <= m.start() else "")
        hit = any(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", local) for w in words)
        if without and not _EXCLUDE_WORDS.search(local) and not re.search(r"\bthe rest\b", local):
            hit = False
        if not hit and not re.search(r"\b(?:of the rest|of those|of them|of these)\b", cl):
            return "base", f"{res.rid} is filtered: say the scope with '{_clip(m.group(0), 30)}' " \
                                     "('of the long videos you opened', 'of what you opened on Sundays')"
    return None


_BROADEN = re.compile(r"\b(?:overall|in total|altogether|all told|in general|across the board|with or without|"
                      r"every other|everything else|every day of the week|the whole (?:month|year|week|window|history)|"
                      r"whole month|of any length|any length|all lengths|all (?:of )?your (?:channels|areas|themes)|"
                      r"all channels|all the channels|of all (?:your |the )?(?:channels|areas|themes)|every channel|"
                      r"everything you opened|of all\b(?=\s*(?:[,.;]|with\b|$)))\b", re.I)


def _broadened(low, res):
    """mvp20 fix (the attack's L and M rows: "top channel overall", "In total, ... came second", "on every day of the
    week", "across the whole month", "of all your channels", "your biggest area of all", "beat every other channel",
    "with or without gaming", "on Saturdays and every other day", "and everything else"): a filtered result's numbers
    said of more than its scope."""
    if not _scope_words_of(res):
        return None
    m = _BROADEN.search(low)
    if m:
        return "scope_broadened", f"{res.rid} counts {_clip((res.meta or {}).get('filters_said') or 'a filtered scope', 60)}" \
                                 f", not '{m.group(0)}'"
    return None


def _sensitive(text, turn):
    from .. import profile as P
    # a sensitive name as whole words (merge seam: Turn.of fills sensitive_names from a real library, where a short
    # hidden channel name inside another word must not drop the sentence)
    named = [n for n in turn.sensitive_names if n and re.search(r"(?<![\w@])" + re.escape(_low(n)) + r"(?!\w)",
                                                                _low(text))]
    if named:
        if not (turn.unlock and any(_low(turn.unlock) in _low(n) for n in named)):
            return True
    # the unlock is per topic (SPEC 8.4): its own words are taken out, any other sensitive word still fails
    return bool(P.sensitive(_mask_unlocked(text, turn.unlock)))


# ------------------------------------------------------------------ step 3.8: insight's checks, one sentence
_NEUTRAL = "changed"


_OF_VIDEOS = re.compile(r"\s+of\s+(?:(?:the|your|all(?: the)?|all your)\s+)?(?:[A-Za-z][\w'’&-]*\s+){0,3}?(?:videos?|items?|"
                        r"clips?|posts?|reels?)(?:\s+(?:that\s+)?you(?:'ve| have)?\s+(?:opened|watched|saved|liked)"
                        r"(?:,\s*liked\s+or\s+saved)?)?(?![\w\[])|\s+of\s+(?:what|everything)\s+you(?:'ve| have)?\s+"
                        r"(?:opened|watched|saved|liked)(?:,\s*liked\s+or\s+saved)?(?![\w\[])", re.I)


def slotted(raw, markers, plain_names, cited_names, res, loose=frozenset()):
    """The sentence in insight's slotted form: value markers -> `{path}` (the hedge kept; a date stays as typed), row
    markers and cited plain names -> the row's name slot; a calc of a row's share against its share before -> that
    row's `{change_vs_previous}` slot; any other calc -> a neutral word for ratio words ("doubled" -> "changed") or
    nothing for a typed number (the direction words of its clause stay); count spans -> nothing (their words stay);
    the model's own "the 4 weeks" loses its digit unless it is the sheet's exact window phrase. None when a cited row
    has no name slot."""
    edits = []   # (start, end, new)
    for mk in markers:
        if mk.kind == "value":
            rest = re.sub(r"\.change_pts$", ".change_vs_previous", mk.rest)
            if isinstance(mk.value, str) and _measure(mk.rest, mk.value)[1] == "date":
                # a date code verified against its own cell (step 3.4) is not read again by insight: the tools' item
                # rows carry it as `when`, which insight's dates do not hold (step 1 fix, the auditor's T31, T61: a
                # last's true "on 20 October 2026[r1.items[0].when]" failed insight's date rule)
                edits.append((mk.start if mk.key in ("when",) else mk.mstart, mk.end,
                              "that day" if mk.key in ("when",) else ""))
                continue
            if isinstance(mk.value, str):
                edits.append((mk.start, mk.end, "{" + rest + "}"))
                continue
            h = NUM_TAIL.search(raw[:mk.mstart])
            # the number (and its sign) becomes the slot; a hedge before it stays as typed
            st = (h.start("sign") if h.group("sign") else h.start("num")) if h else mk.start
            edits.append((max(st, mk.start), mk.end, "{" + rest + "}"))
        elif mk.kind == "row":
            nk = I._record_name_key(mk.value) if isinstance(mk.value, dict) else None
            if nk is None:
                return None
            edits.append((mk.start, mk.end, "{" + mk.rest + "." + nk + "}"))
        elif mk.kind == "calc":
            words = CALC_TAIL.search(raw[:mk.mstart])
            ra, rb = mk.a.split(".", 1)[1], mk.b.split(".", 1)[1]
            own = _owner(ra)
            if mk.op == "points" and own and own == _owner(rb) and {_segs(ra)[-1][0], _segs(rb)[-1][0]} == \
                    {"share", "previous_share"}:
                # a row's move in points, its share now against before: insight's own change cell says it, so
                # insight still reads a number beside the direction word (code verified the typed one)
                try:
                    has = isinstance(_resolve(res.sheet, own + ".change_vs_previous"), (int, float))
                except KeyError:
                    has = False
                if has:
                    edits.append((mk.start, mk.end, "{" + own + ".change_vs_previous}"))
                    continue
            if words and words.group("words"):
                edits.append((mk.start, mk.end, _NEUTRAL))
            else:
                edits.append((mk.start, mk.end, ""))
        elif mk.kind == "count":
            # the length of a list ("the top 3"): verified by code; insight's strict reading takes any number word
            # for a free number ("with four areas rising"), so the count goes and its words stay ("the top")
            edits.append((mk.start, mk.end, ""))
    # plain cited names (not inside a marker's span)
    spans = [(mk.start, mk.end) for mk in markers]
    for a, b, n in plain_names:
        if any(x < b and a < y for x, y in spans):
            continue
        rest = cited_names.get(n)
        if rest is None:
            f_ = res.sheet.get("filters") or {}
            if n in {_low(v) for v in (f_.get("topic"), f_.get("channel")) if isinstance(v, str)}:
                continue   # the filter's topic: insight allows it typed
            # a scope word of the tools (meta.resolved, meta.filters_said: "gaming" of "only gaming (area)"): insight
            # does not know the tools' scope and would read it as a name typed beside a number (typed_name); the
            # scope rule (_scope_dropped) has checked it, so insight reads the sentence without it
            edits.append((a, b, ""))
            continue
        try:
            row = _resolve(res.sheet, rest)
        except KeyError:
            return None
        nk = I._record_name_key(row) if isinstance(row, dict) else None
        if isinstance(row, str):
            edits.append((a, b, "{" + rest + "}"))
        elif nk:
            edits.append((a, b, "{" + rest + "." + nk + "}"))
    # step 1 fix (the verifier audit's true T04, T16, T42, T46, T53: "down from 31[previous_items] in September" failed
    # insight's no_base): a time phrase that step 15 read as the window before, beside a cell of the window before, is
    # insight's own base slot `{previous.words}`
    pw = res.prev_window()
    if pw and (res.sheet.get("previous") or {}).get("words") and any(
            mk.kind == "value" and _is_before(mk.rest) for mk in markers):
        for m in _PHRASE.finditer(raw):
            if any(x < m.end() and m.start() < y for x, y in spans) or any(a < m.end() and m.start() < b for a, b, _t
                                                                            in edits):
                continue
            if m.group("since") or m.group("rel"):
                continue
            rng = _phrase_range(m, [pw], None)
            if rng and _matches(rng, pw, False):
                st = m.start()
                pre = re.search(r"\b(?:in|during|over)\s+$", raw[:st], re.I)
                edits.append((pre.start() if pre else st, m.end(), "in {previous.words}"))
    # the window said in the model's own words ("the 4 weeks to 30 Oct"), checked by step 15: its count of weeks is
    # no number of the sheet's, so it is taken out ("the weeks to 30 Oct") rather than read as a free number
    words = " ".join(_window_phrases(res)).lower()
    full = [x for x in ((res.meta or {}).get("window_said"), (res.sheet.get("window") or {}).get("words"),
                        (res.sheet.get("previous") or {}).get("words")) if isinstance(x, str) and x.strip()]
    exact = [(m.start(), m.end()) for ph in full for m in re.finditer(re.escape(ph.strip()), raw, re.I)]
    for m in _SPAN_N.finditer(raw):
        if any(x < m.end() and m.start() < y for x, y in spans) or any(a < m.end() and m.start() < b for a, b, _t in
                                                                        edits):
            continue
        if any(x <= m.start() and m.end() <= y for x, y in exact):
            continue   # the window's own words as the sheet says them: insight reads those itself
        if re.search(r"\b" + m.group(1) + r"\s+" + m.group(2).lower().rstrip("s"), words):
            edits.append((m.start(1), m.end(1) + 1, ""))
    # mvp20 tune (the live run's D06.1, E07 and the audit's T17, T23, T37, T54, T55: "Wet Paper[r1.channels[1]] came next
    # with 37[r1.channels[1].items] of your art videos", "Clip Factory made 61[...] of the videos you opened" failed
    # insight's count_as_share, a rule against a count said where its share belongs ("12,080 of your window"): a row's
    # count of videos said as "N of the (art) videos you opened" / "N of what you opened" is a count of videos, read by
    # insight as "N videos". The verb is still checked against the base (_verb_dropped, on the raw text), the scope
    # words by the scope rule, and a count of openings or of days never takes this path.
    for mk in markers:
        if mk.kind != "value" or not mk.owner or mk.key not in ITEM_KEYS or mk.rid != res.rid or \
                not isinstance(mk.value, (int, float)):
            continue
        m = _OF_VIDEOS.match(raw, mk.end)
        if not m:
            continue
        inside = [e for e in edits if e[0] < m.end() and m.start() < e[1]]
        if any(x < m.end() and m.start() < y for x, y in spans) or any(
                e[2] or e[0] < m.start() or e[1] > m.end() for e in inside):
            continue
        # (a scope word inside it, "art" of "of your art videos", was a deletion: the span replaces it)
        edits = [e for e in edits if e not in inside]
        edits.append((m.start(), m.end(), " videos"))
    # mvp20 tune (the live run's C03, F07 and the audit's T25: "In 2021 you opened 134[r1.periods[0].items] videos",
    # "6[r2.periods[0].items] in September 2026" failed insight's unnamed_owner): a period row's name is its label, which
    # the model says in words ("2021", "Sep 2026" as "September 2026"); the label typed in the sentence, outside every
    # marker, is that row's name slot. A label of another period stays as typed (still unnamed_owner, or wrong_window).
    for mk in markers:
        own = mk.owner if mk.kind == "value" else None
        if not own or not re.fullmatch(r"periods\[\d+\]", own) or mk.rid != res.rid:
            continue
        try:
            row = _resolve(res.sheet, own)
        except KeyError:
            continue
        lab = str((row or {}).get("label") or "").strip() if isinstance(row, dict) else ""
        if not lab:
            continue
        alts = {lab}
        mm = re.fullmatch(r"([A-Za-z]{3})\w* (\d{4})", lab)
        if mm:
            full = next((x for x in _MONTHS if x[:3] == mm.group(1).lower()), None)
            if full:
                alts |= {f"{full} {mm.group(2)}", f"{mm.group(1)} {mm.group(2)}"}
                if "month_alone" in loose and sum(
                        1 for x in (res.sheet.get("periods") or []) if isinstance(x, dict) and
                        str(x.get("label") or "")[:3].lower() == mm.group(1).lower()) == 1:
                    # mvp25 cells loosening (run1's N008.0: "August had 36[r1.periods[7].items]"): the month alone
                    # names the period row when no other row of the sheet is that month
                    alts |= {full, mm.group(1)}
        for alt in sorted(alts, key=len, reverse=True):
            hit = None
            for m in re.finditer(r"(?<![\w-])" + re.escape(alt) + r"(?![\w-])", raw, re.I):
                if any(x < m.end() and m.start() < y for x, y in spans) or any(
                        a < m.end() and m.start() < b for a, b, _t in edits):
                    continue
                if "label_in_date" in loose and re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s+$", raw[:m.start()]):
                    continue   # mvp25 cells loosening (run1's N008.0): a month inside a full date is no period's name
                hit = m
                break
            if hit:
                edits.append((hit.start(), hit.end(), "{" + own + ".label}"))
                break
    # mvp20 tune (the live run's C07, F01: "you opened 24[r1.totals.items] YouTube videos" of a result the tools scoped
    # to YouTube only failed as a rewrite: insight does not know the tools' platform scope and took "YouTube" out): the
    # platform of a result scoped to that platform is its scope said (the scope rule has checked it), so insight reads
    # the sentence without it, as it reads a scope word of a name
    plats = {w for p in scope_parts(res) if p["kind"] == "platform" for w in p["words"]}
    for m in re.finditer(r"\b(?:on |from |of |in )?(youtube|instagram)\b", raw, re.I):
        if m.group(1).lower() not in plats:
            continue
        if any(x < m.end() and m.start() < y for x, y in spans) or any(a < m.end() and m.start() < b for a, b, _t in
                                                                        edits):
            continue
        edits.append((m.start(), m.end(), ""))
    # mvp20 tune (the live run's D05.1: "what you opened fell into these 4[r1.areas.count] areas" failed insight's
    # direction_unbound): "fell into" / "falls into" is where things sit, not a fall; any other "fell" stays
    for m in re.finditer(r"\b(?:fell|falls?|falling)\s+into\b", raw, re.I):
        if not any(x < m.end() and m.start() < y for x, y in spans) and not any(
                a < m.end() and m.start() < b for a, b, _t in edits):
            edits.append((m.start(), m.end(), "sat in"))
    s = raw
    for a, b, t in sorted(edits, key=lambda e: e[0], reverse=True):
        s = s[:a] + t + s[b:]
    s = re.sub(r"\s+([,.;:!?)])", r"\1", " ".join(s.split()))
    return s


def _plain_fill(text, sheet, lang="en"):
    sl = I.slots_of(text, sheet, lang)
    if isinstance(sl, str):
        return None
    out, last = [], 0
    for x in sl:
        out.append(text[last:x.start])
        t_ = x.text
        if x.key == "long_median_min" and re.match(r"^\s*-?\s*(?:min|minut)", text[x.end:x.end + 12], re.I):
            t_ = str(int(x.value))
        out.append(t_)
        last = x.end
    out.append(text[last:])
    r = re.sub(r"\s+", " ", "".join(out)).strip()
    return re.sub(r"\b(points?|puntos?)\s+(?:points?|puntos?|percentage points?)\b", r"\1", r)


def _norm_cmp(s):
    return " ".join(str(s or "").split()).strip()


def _inserted(a, b):
    """The pieces b has that a has not (words, case and punctuation aside), and whether b only inserts."""
    aw = re.findall(r"[\w%'’]+", a.lower())
    bw = re.findall(r"[\w%'’]+", b.lower())
    sm = difflib.SequenceMatcher(a=aw, b=bw, autojunk=False)
    ins, only = [], True
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "insert":
            ins.append(" ".join(bw[j1:j2]))
        else:
            only = False
            ins.append(" ".join(bw[j1:j2]) or "-" + " ".join(aw[i1:i2]))
    return ins, only


def _rewrite_reason(ins, only):
    t = " ".join(ins).lower()
    if not only:
        return "insight_rewrite"
    if re.search(r"\bto\b|\bfrom\b", t):
        return "one_value"
    if re.search(r"\bof\b", t):
        return "base_missing"
    if re.search(r"\babout\b|\bwhose\b", t):
        return "filter_dropped"
    return "insight_rewrite"


def _mask_unlocked(text, unlock):
    """The words of the turn's unlocked sensitive topic (SPEC 8.4) taken out of what insight's sensitive rule reads;
    any other sensitive word stays and still fails."""
    if not unlock:
        return text
    from .. import outside as O

    def sub(m):
        return "topic" if O.sensitive_topic([m.group(0)]) == unlock else m.group(0)
    return re.sub(r"[A-Za-z][A-Za-z'’-]*", sub, text)


def _change_and_value(markers):
    """A row's move (change_pts / change_vs_previous, a value marker) and the same row's value now (its share, or its
    items for a move of a count) both cited in the sentence."""
    moves = {mk.owner for mk in markers if mk.kind == "value" and mk.owner and
             _segs(mk.rest)[-1][0] in ("change_pts", "change_vs_previous")}
    nows = {mk.owner for mk in markers if mk.kind == "value" and mk.owner and _segs(mk.rest)[-1][0] == "share"}
    return bool(moves & nows)


def insight_check(raw, markers, plain_names, cited_names, res, where, unlock=None, skip=frozenset(),
                  loose=frozenset()):
    """None or (reason, detail): the sentence through insight's own checks against the cited result's sheet. `skip`
    (mvp25, cells mode's rule "insight_walk"): reasons walked past, here and inside insight, so a later reason is still
    looked at (empty: every reason stops, as before)."""
    def go(w):
        return not skip or str(w).split(":")[0] not in skip
    s = slotted(raw, markers, plain_names, cited_names, res, loose) if loose else \
        slotted(raw, markers, plain_names, cited_names, res)
    if s is None:
        return "bad_ref", "a cited row with no name"
    s = _mask_unlocked(s, unlock)
    sheet, facts = res.sheet_k, res.facts
    lang = sheet.get("lang") or "en"
    text, why = I.render(s, sheet, facts, strict=True, skip=skip) if skip else I.render(s, sheet, facts, strict=True)
    if why and go(why):
        return why, _insight_detail(why)
    if why:
        return None   # (a structural reason walked past: insight has no text to read further)
    fill = _plain_fill(s, sheet, lang)
    if fill is not None and _norm_cmp(text) != _norm_cmp(fill):
        ins, only = _inserted(_norm_cmp(fill), _norm_cmp(text))
        base = I._base_of(sheet)
        bw_ = " ".join(re.findall(r"[\w%'’]+", str(base or "").lower()))
        benign = only and bool(base) and all(x in ("against " + bw_, "in " + bw_) for x in ins)
        if not benign and only and _change_and_value(markers) and all(
                re.fullmatch(r"from [\d.,]+(?: ?%| points?)?(?: (?:against|in) " + re.escape(bw_) + r")?", x) or
                x in ("against " + bw_, "in " + bw_) for x in ins):
            # mvp20 tune (the live run's K01, B04: "rose to 30%[r2.areas[1].share] ..., up 17
            # points[r2.areas[1].change_pts]"): a change said with its move AND its value now, both cells of the same
            # row checked by code (the move's sign against the direction words), says the value before as well
            # (30 - 17): insight's "from 13%" adds nothing the sentence does not already claim
            benign = True
        if not benign and go(_rewrite_reason(ins, only)):
            return _rewrite_reason(ins, only), "code would have to add: " + _clip(" / ".join(ins), 80)
        if benign:
            text = fill
    facts.slotted = bool(I.SLOT.search(s))
    skip_c = skip
    if "handle" in loose:
        # mvp25 cells loosening (run1's N036, N038): an '@handle' that is a cited row's own name, filled in by insight,
        # is that name, not a link
        hs = sorted(_cited_handles(markers, res) | {h for h in cited_names if h.startswith("@")}, key=len,
                    reverse=True)
        lk = list(I._LINK.finditer(text))
        if hs and lk and all(any(text.lower().find(h, max(0, m.start() - 60)) != -1 and
                                 any(a <= m.start() < a + len(h) for a in [i_.start() for i_ in
                                     re.finditer(re.escape(h), text.lower())]) for h in hs) for m in lk):
            skip_c = frozenset(skip) | {"link"}
    try:
        why = I.check_sentence(text, facts, need_fact=False, skip=skip_c) if skip_c else \
            I.check_sentence(text, facts, need_fact=False)
        if not why and where != "lead":
            why = I._obs_more(text, "", sheet, s, facts, skip=skip) if skip else I._obs_more(text, "", sheet, s, facts)
        if not why and I.n_numbers(text, facts) > I.NUMBERS_MAX and go("number_run"):
            why = "number_run"
        if not why and I.shorts_left_out(text, sheet) and go("shorts_left_out"):
            why = "shorts_left_out"
    finally:
        facts.slotted = False
    if why:
        return why, _insight_detail(why)
    sc = I.scoped(text, sheet)
    if _norm_cmp(sc) != _norm_cmp(text):
        ins, only = _inserted(_norm_cmp(text), _norm_cmp(sc))
        r = "base" if not only else _rewrite_reason(ins, only)
        if go(r):
            return r, "the base is " + _clip(" / ".join(ins) or (I.bases(sheet) or {}).get("opened") or "", 80)
    g, gwhy = I.gate_sentence(text, sheet, I._gate_names(sheet), {"opened_said": True})
    if gwhy and go(gwhy):
        return gwhy, _insight_detail(gwhy)
    if _norm_cmp(g) != _norm_cmp(text):
        ins, only = _inserted(_norm_cmp(text), _norm_cmp(g))
        # the gate takes out a second "of what you opened" (the answer's base, said once): words it removes that are
        # the result's own base change nothing the sentence claims
        if not all(re.fullmatch(r"-of (?:what|everything|all) you (?:opened|watched)", x) for x in ins) and \
                go(_rewrite_reason(ins, only)):
            return _rewrite_reason(ins, only), "code would have to add: " + _clip(" / ".join(ins), 80)
    return None


_INSIGHT_TEXT = {"bound": "a number stands only next to the name of its own row",
                 "mostly": "'mostly' needs a share of 50% or more", "spread": "'mostly' needs a share of 50% or more",
                 "not_top": "'led', 'top', 'most' need the first row", "typed_name": "every name needs its marker",
                 "free_number": "a number with no marker", "direction": "the direction does not fit the values",
                 "small_move": "a move under 3 points is not said", "no_base": "a change needs its base period",
                 "vague": "a direction with no number"}


def _insight_detail(why):
    return _INSIGHT_TEXT.get(str(why).split(":")[0], f"insight: {why}")


def _non_sheet(raw, markers, res, low, loose=frozenset()):
    """Step 4 of 4.3: the rules of `search`, `learned` and `find` results (and item lists)."""
    tool = res.tool
    if tool == "find":
        if _RANK.search(low) or _UPW.search(low) or _DOWNW.search(low):
            return "rank", "a find result has names and counts only"
        return None
    if tool == "learned":
        if not re.fullmatch(r"\s*\[" + re.escape(res.rid) + r"\.points\[\d+\]\]\s*\.?\s*", raw) and any(
                mk.kind == "row" and ".points[" in mk.path for mk in markers):
            return "point_text", "a learned point is exactly its marker"
        for mk in markers:
            if mk.kind == "value":
                return "bad_marker", "a learned result carries a count marker and row markers only"
        return None
    # search and item lists
    for mk in markers:
        if mk.kind == "row" and not re.match(r"^items\[\d+\]$", mk.rest):
            return "not_item", f"{mk.path} is not an item row"
        if mk.kind == "value" and _measure(mk.rest, mk.value)[1] not in ("date", "count", "name"):
            return "bad_marker", f"{mk.path}"
    rows = [mk for mk in markers if mk.kind == "row"]
    for mk in rows:
        fit = mk.value.get("fit") if isinstance(mk.value, dict) else None
        if fit == "weak" and re.search(r"\b(?:here is|here's|this is|found it|that's the one|is the one)\b", low):
            return "weak_fit", f"{mk.path} is a weak match"
        if fit != "clear" and _EXACT.search(low):
            return "weak_fit", f"{mk.path} is a {fit or 'weak'} match, not exactly what was asked"
        # a search row carries no `how` of its own: the result's sheet says which kind it searched (merge seam)
        how = str((mk.value.get("how") if isinstance(mk.value, dict) else None) or res.sheet.get("how") or "")
        if re.search(r"\bsaved\b", low) and how and not re.search(r"save|collection|playlist", how):
            return "wrong_name", f"{mk.path} was not saved ({how})"
    own_titles = [mk.value.get("title") for mk in rows if isinstance(mk.value, dict)]
    if "quoted_title" in loose:
        # mvp25 cells loosening (run1's N049.0): the title of an item one of whose cells is cited
        for mk in markers:
            if mk.kind == "value" and mk.owner and re.fullmatch(r"items\[\d+\]", mk.owner) and mk.rid == res.rid:
                try:
                    it_ = _resolve(res.sheet, mk.owner)
                except KeyError:
                    continue
                if isinstance(it_, dict):
                    own_titles.append(it_.get("title"))
    for m in re.finditer(r"[\"“]([^\"”]{2,120})[\"”]", raw):
        if not any(_low(t_) == _low(m.group(1)) for t_ in own_titles if isinstance(t_, str)):
            return "wrong_name", "a quoted title must be the row's own title"
    return None


# ------------------------------------------------------------------ outside lines (4.3 step 6) and items (step 5)
def check_outside(entry, ledger, kept_rows, turn=None):
    """(kept, [reasons]) for one outside entry. `kept_rows`: row paths cited in kept history sentences."""
    reasons = []
    about, text, source = entry.get("about"), entry.get("text") or "", entry.get("source")
    if source != "general":
        reasons.append("source")
    if about not in kept_rows:
        reasons.append("about_not_cited")
    t = " ".join(str(text).split())
    if not t or len(t) > OUTSIDE_CHARS or len(I._sentences(t)) > 2:
        reasons.append("too_long")
    if re.search(r"\d", _YEAR.sub(" ", t)):
        reasons.append("number")
    if re.search(r"\b(?:you|your|you're|yours|you've|yourself)\b", t, re.I):
        reasons.append("second_person")
    if re.search(r"[\[\]{}]", t):
        reasons.append("marker")
    if I._LINK.search(t) or re.search(r"@\w|\S+@\S+", t):
        reasons.append("link")
    if WORLD_CLAIMS.search(t) and re.search(r"\bsubscribers?|followers|views\b", t, re.I):
        reasons.append("number")
    turn = turn or Turn()
    if _sensitive(t, turn):
        reasons.append("sensitive")
    # no library name other than its own entity's
    own = set()
    if about and "." in about:
        rid, rest = about.split(".", 1)
        r = ledger.get(rid)
        try:
            row = _resolve(r.sheet, rest) if r else None
        except KeyError:
            row = None
        if isinstance(row, dict):
            # its own names, and what its row says of it (its theme, its area)
            own = {_low(n) for n in _row_names(row, rest)} | {_low(x) for x in row.values() if isinstance(x, str)}
    for a, b, n in _name_spans(t, ledger.all_names(), turn.names):
        if n not in own:
            reasons.append("other_name")
            break
    return (not reasons), reasons


def _item_rows(ledger):
    out = {}
    for r in ledger.by_rid.values():
        for i, it in enumerate(r.sheet.get("items") or []):
            if isinstance(it, dict):
                out[f"{r.rid}.items[{i}]"] = it
    return out


# ------------------------------------------------------------------ the whole answer
def _split(text):
    return I._sentences(text or "")


def _claim_key(o, markers):
    return frozenset(mk.path for mk in markers if mk.kind == "value") | frozenset(
        f"{mk.op}({mk.a},{mk.b})" for mk in markers if mk.kind == "calc")


def _lead_names_window(lead_text, ledger, rid):
    r = ledger.get(rid) if rid else None
    if r is None:
        r = next(iter(ledger.by_rid.values()), None)
    if r is None or not r.sheet.get("window"):
        return True
    plain = strip_markers(lead_text)
    said = (r.meta or {}).get("window_said") or ""
    if said and _low(re.split(r"[(,]", said)[0]) in _low(plain):
        return True
    core = re.split(r"[(,]", said)[0]
    if " up to " in core and re.search(r"(?<!\w)" + re.escape(_low(core.split(" up to ")[0])) + r"(?!\w)",
                                       _low(plain)):
        # mvp20 tune (run2's E05: "This year, Pixel Pencil ... is your top channel" of "this year up to 30 October 2026,
        # where your export ends"): the window's own words before the clip ("this year", "October 2026") name it; the
        # clip is the export's end
        return True
    pmk = [mk for mk in parse(" ".join(lead_text.split()), ledger)[0] if mk.kind == "value"]
    if pmk and all(mk.rid == r.rid and mk.owner and re.fullmatch(r"periods\[\d+\]", mk.owner) for mk in pmk):
        labs = []
        for mk in pmk:
            try:
                labs.append(str((_resolve(r.sheet, mk.owner) or {}).get("label") or ""))
            except (KeyError, AttributeError):
                labs.append("")
        if all(lab and re.search(r"(?<![\w-])" + re.escape(lab) + r"(?![\w-])", plain, re.I) for lab in labs):
            # (run2's F07: "you opened 10[r1.periods[3].items] math videos in 2026, after 0[...] in 2024 ...": a lead
            # of period cells names each cell's own period, which is the time it claims)
            return True
    if r.sheet.get("kind") in ("first", "last") and _low(said).startswith("all your history") and re.search(
            r"\[" + re.escape(r.rid) + r"\.items\[\d+\]\.(?:when|at|date)\]", lead_text):
        # merge seam (first_last over all of their history): the item's own day, checked against its cell, is the
        # time the lead claims; "in all your history" adds nothing to "you first opened ... on 10 January 2025"
        return True
    sheet = r.sheet_k
    wl = I.window_lead(plain, sheet)
    if wl == plain:
        return True
    w = r.window()
    if _LATELY.search(plain) and re.search(r"\b(?:4|four) weeks\b|\blately\b", said + " " +
                                           str((r.sheet.get("window") or {}).get("words") or ""), re.I):
        return True
    if w[0] and w[1]:
        # a month or a year that is the whole window ("In October 2026", "In 2025")
        if w[0].day == 1 and w[0].year == w[1].year:
            m = _MONTHS[w[0].month - 1]
            if w[0].month == w[1].month and re.search(r"\b" + m[:3] + r"\w*\b", plain, re.I):
                return True
            if w[0].month == 1 and w[1].month == 12 and re.search(r"\b" + str(w[0].year) + r"\b", plain):
                return True
    return False


def scope_said(text, res):
    """The text says every part of the result's scope (the tools' meta.filters_said: a name with "only" / "without",
    a weekday, a platform; and a length filter): the words _scope_dropped and _filter_dropped look for."""
    low = strip_markers(text or "").lower()
    for p in scope_parts(res):
        hit = any(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", low) for w in p["words"])
        if p["kind"] == "without" and not _EXCLUDE_WORDS.search(low):
            hit = False
        if not hit:
            return False
    f = res.sheet.get("filters") or {}
    said = " ".join(str(x) for x in ((res.meta or {}).get("filters_said"), (res.meta or {}).get("base")) if x).lower()
    length = f.get("length") or ("long" if f.get("without_shorts") or re.search(r"\blong\b|without shorts", said)
                                 else ("short" if re.search(r"\bonly shorts\b|\bshorts only\b", said) else None))
    if length == "long" and not re.search(r"\blong\b|without shorts|no shorts", low):
        return False
    if length == "short" and not re.search(r"\b(?:short|shorts|reels?)\b", low):
        return False
    return True


_UNSCOPED_BASE = re.compile(r"\bof (?:what|everything|all(?: of)? (?:what|the|your)) (?:you|videos|items)\b|\b(?:videos?|"
                            r"items?|clips?|posts?|things) (?:that )?you(?:'ve| have)? (?:opened|watched|saved|liked)\b",
                            re.I)


def _waive_scope_repeats(v, ledger, lead_text):
    """mvp20 tune, the scope rule of the brief's (c): a point dropped ONLY because it did not repeat its result's
    filter is kept when the lead that goes out with it cites the SAME filtered result and says that filter. The answer
    then prints code's scope line for that result (answer.build: the first kept sentence's result, which is the lead's),
    so the filter is said twice already. A point on another result, or under a lead that failed (a code lead takes its
    place), keeps the rule: nothing is waived."""
    lead_os = [o for o in v.outcomes if o.where == "lead"]
    if not lead_os or not all(o.kept for o in lead_os):
        return
    lrid = next((o.rid for o in lead_os if o.rid), None)
    res = ledger.get(lrid) if lrid else None
    if res is None or not (scope_parts(res) or (res.sheet.get("filters") or {}).get("without_shorts") or
                           (res.sheet.get("filters") or {}).get("length") in ("long", "short")):
        return
    if not scope_said(lead_text, res):
        return
    for o in v.outcomes:
        if o.where != "point" or o.kept or o.rid != lrid or o.reasons != ["filter_dropped"]:
            continue
        if str(o.notes.get("filter_dropped") or "").startswith("code would have to add"):
            continue   # insight's own rewrite (a clause it would add), not the scope said again
        mks, _b = parse(" ".join(o.text.split()), ledger)
        if any(mk.kind in ("calc", "count") or (mk.kind == "value" and (_family(mk.rest) in ("share", "points") or
                                                            re.match(r"^(?:totals|previous)\.", mk.rest)))
               for mk in mks) or _UNSCOPED_BASE.search(strip_markers(o.text)):
            # a share, a move, a total of the window, or a base said in words ("of what you opened", "the 107 items
            # you opened") claims the WHOLE base: said without the scope it is wrongly based, whatever the line under
            # it says ("85% of what you opened" of only gaming is 43% of what they opened). Only a row's own count, a
            # rank or a day of the scoped result may lean on the lead and the scope line.
            continue
        o.reasons = []
        o.details = []
        o.notes = {"scope_waived": f"the lead says {res.rid}'s scope"}
        o.sent = " ".join(strip_markers(" ".join(o.text.split())).split())


_NEXT = re.compile(r"\b(?:came next|comes next|next came|was next|is next|next,|then came|followed by|followed|"
                   r"behind (?:it|them|that|this)|after (?:it|that|them)|runner-up)\b|^\s*next\b", re.I)


def _bind_points_to_lead(v, ledger, cm=None):
    """mvp20 fix. (a) The recount's C04.0 ("art and design came next at 25%" kept under a lead that named a THEME
    first): a point that places its row relative to the one before ('came next', 'followed', 'behind it') is true only
    under a kept lead that cites the row just before it in the same list. (b) The attack's U01, U02, U05 ("Clip
    Factory[r2.channels[0]] led with 13" of the last 7 days under a lead of October): a point on another result, whose
    window is not the lead's, says its own window."""
    cm = cm or FULL
    if cm.is_off("rank", "next") and cm.is_off("window_missing", "point"):
        return   # cells mode: both rules are framing rules
    lead_os = [o for o in v.outcomes if o.where == "lead"]
    lead_ok = bool(lead_os) and all(o.kept for o in lead_os)
    lead_rows = set()
    for o in (lead_os if lead_ok else []):   # (a failed lead is not sent: the code lead's own check decides)
        for mk in parse(" ".join(o.text.split()), ledger)[0]:
            if mk.kind in ("row", "value") and mk.owner:
                lead_rows.add((mk.rid, mk.owner))
    lrid = next((o.rid for o in lead_os if o.rid), None)
    lres = ledger.get(lrid) if lrid else None
    for o in v.outcomes:
        if o.where != "point" or not o.kept:
            continue
        mks, _b = parse(" ".join(o.text.split()), ledger)
        plain = strip_markers(o.text)
        mine = {(mk.rid, mk.owner) for mk in mks if mk.kind in ("row", "value") and mk.owner}
        if _NEXT.search(plain) and not cm.is_off("rank", "next"):
            own = next((mk for mk in mks if mk.kind in ("row", "value") and mk.owner), None)
            lst, i = _list_and_index(own.owner) if own else (None, None)
            # the lead names the first row of ANOTHER list (or result), and not the row just before this one: 'came
            # next' then reads as after the lead's row, which it is not
            other_first = any(rid_ == (own.rid if own else None) and re.fullmatch(r"\w+\[0\]", ow) and
                              _list_and_index(ow)[0] != lst for rid_, ow in lead_rows) or \
                any(rid_ != (own.rid if own else None) and re.search(r"\[0\]$", ow) for rid_, ow in lead_rows)
            ok = lst is not None and bool(i) and (not other_first or (own.rid, f"{lst}[{i - 1}]") in lead_rows)
            if not ok:
                o.reasons.append("rank")
                o.details.append("'came next' places a row after the one the lead names first: cite that row in the "
                                 "lead, or say its place")
                o.sent = None
                continue
        lead_rows |= mine   # what comes after may follow this point's rows ("came next" after a theme it named)
        if lres is not None and o.rid and o.rid != lrid and not cm.is_off("window_missing", "point"):
            pres = ledger.get(o.rid)
            if pres is not None and pres.window() != lres.window() and \
                    not _lead_names_window(o.text, ledger, o.rid):
                o.reasons.append("window_missing")
                o.details.append(f"{o.rid} is another window than the lead's: say "
                                 f"'{_clip((pres.meta or {}).get('window_said') or '', 80)}'")
                o.sent = None


def check_answer(form, ledger, turn=None, mode=None):
    """The form against the ledger -> Verdict (SPEC 4.3). `form`: an AnswerForm or its dict; `ledger`: a Ledger, or
    the turn's result envelopes (a list, or a dict by rid); `mode`: "full", "cells" or a CheckMode (None: the
    environment's MVP_BRAIN_CHECK, else "full")."""
    cm = check_mode(mode)
    if cm.rule("values"):
        return check_answer_values(form, ledger, turn, mode=cm)
    turn = turn or Turn()
    if not isinstance(ledger, Ledger):
        ledger = Ledger(ledger)
    try:
        f = form if isinstance(form, AnswerForm) else AnswerForm.model_validate(form)
    except ValidationError as e:
        return Verdict(outcomes=[], form_error=str(e.errors()[0].get("type")), repair=True, check=cm.name)
    v = Verdict(outcomes=[], check=cm.name)
    state = {}
    claimed = []
    # the lead (1 to 2 sentences, <= ANSWER_MAX) and the points (0 to 3, each <= SENT_MAX)
    lead_s = _split(f.lead)
    if not lead_s:
        # (a lead with text but no sentence; cells mode names it without the framing code)
        v.outcomes.append(Outcome("lead", 0, f.lead or "", reasons=[
            ("garbled" if cm.cells else "window_missing") if f.lead else "too_long"]))
    elif len(strip_markers(f.lead)) > LEAD_MAX or len(lead_s) > 2:
        for k, s in enumerate(lead_s):
            v.outcomes.append(Outcome("lead", k, s, reasons=["too_long"]))
    else:
        for k, s in enumerate(lead_s):
            v.outcomes.append(check_sentence(s, ledger, turn, "lead", k, state, mode=cm))
    for k, p in enumerate(f.points):
        sents = _split(p)
        if k >= POINTS_MAX:
            v.outcomes.append(Outcome("point", k, p, reasons=["too_long"]))
            continue
        if len(sents) != 1:
            v.outcomes.append(Outcome("point", k, p, reasons=["too_long"]))
            continue
        v.outcomes.append(check_sentence(sents[0], ledger, turn, "point", k, state, mode=cm))
    # the lead names its window (step 2), when the lead holds no failure of its own
    lead_os = [o for o in v.outcomes if o.where == "lead"]
    if lead_os and all(o.kept for o in lead_os) and not cm.is_off("window_missing", "lead"):
        rid = next((o.rid for o in lead_os if o.rid), None)
        if not _lead_names_window(f.lead, ledger, rid):
            lead_os[0].reasons.append("window_missing")
            r = ledger.get(rid) if rid else None
            lead_os[0].details.append(f"say the window: '{_clip((r.meta or {}).get('window_said') if r else '', 90)}'")
            lead_os[0].sent = None
    _waive_scope_repeats(v, ledger, f.lead)
    _bind_points_to_lead(v, ledger, cm)
    # 3.14 once: the same cells said again (the later sentence goes)
    for o in v.outcomes:
        if not o.kept or cm.is_off("repeat", "once"):
            continue
        mks, _b = parse(" ".join(o.text.split()), ledger)
        key = _claim_key(o, mks)
        if key and any(key <= c for c in claimed):
            o.reasons.append("repeat")
            o.sent = None
            continue
        if key:
            claimed.append(key)
    v.private_line = any(o.kept and o.hidden_rank for o in v.outcomes)
    # items (step 5)
    rows = _item_rows(ledger)
    for k, it in enumerate(f.items[:ITEMS_MAX]):
        reasons = []
        if it.ref not in rows:
            reasons.append("not_item")
        note_o = None
        if it.note:
            if len(it.note) > NOTE_MAX:
                reasons.append("too_long")
            else:
                note_o = check_sentence(it.note, ledger, turn, "note", k, state, mode=cm)
                reasons += note_o.reasons
        v.items.append({"ref": it.ref, "note": note_o.sent if note_o and note_o.kept else None,
                        "kept": "not_item" not in reasons, "reasons": reasons})
    for it in f.items[ITEMS_MAX:]:
        v.items.append({"ref": it.ref, "note": None, "kept": False, "reasons": ["too_long"]})
    # outside (step 6): about a row cited in a kept history sentence
    kept_rows = set()
    for o in v.outcomes:
        if o.kept:
            for mk in parse(" ".join(o.text.split()), ledger)[0]:
                if mk.kind == "row":
                    kept_rows.add(mk.path)
    for k, e in enumerate(f.outside):
        if k >= OUTSIDE_MAX:
            v.outside.append({"about": e.about, "text": None, "kept": False, "reasons": ["too_many"]})
            continue
        ok, rs = check_outside(e.model_dump(), ledger, kept_rows, turn)
        v.outside.append({"about": e.about, "text": " ".join(e.text.split()) if ok else None, "kept": ok,
                          "reasons": rs})
    # chart (step 7)
    if f.chart is not None:
        v.chart = f.chart.model_dump(by_alias=True) if ledger.get(f.chart.from_) else None
    # repair (4.5): the lead failed, or more than half of the sentences
    sents = [o for o in v.outcomes if o.where in ("lead", "point")]
    failed = [o for o in sents if not o.kept]
    v.repair = (not v.lead_ok) or (len(sents) > 0 and len(failed) * 2 > len(sents))
    return v


# ------------------------------------------------------------------ the values mode (mvp26, DESIGN 26)
# A check refuses a sentence only on values, with no reading of words: (a) a marker whose cell does not hold the value
# written beside it; (b) a marker whose path or result does not exist; (c) a calc marker whose arithmetic does not give
# the written value; (d) a number, date, clock time or name written with no marker that no result of this turn holds
# (nor the user's message). Privacy and safety refusals keep their power (VALUES_SAFETY). Every code today's full and
# cells checks give is computed as today and written as a FLAG ({"code", "mode"}) that refuses nothing and asks for no
# reword. Code words no part of a sentence.
VALUES_CODES = frozenset({"wrong_value", "wrong_name", "wrong_measure", "bad_ref", "calc", "empty", "garbled",
                          "unfound_number", "unfound_date", "unfound_time", "unfound_name", "row_name"})
# the refuse list: code -> why it refuses (pinned and hashed by tests/test_brain_values.py)
VALUES_REFUSE = {
    "wrong_value": "(a) a marked number, share, hour or date the cell does not hold, within the grammar's rounding; "
                   "a typed sign against a points cell",
    "wrong_name": "(a) a marked name the cell does not hold; a row marker after another row's name or after a "
                  "quoted title that is not the row's",
    "wrong_measure": "(a) a typed unit against the cell's kind: a count typed as a share or in points, a share typed "
                     "with no %, points typed as %",
    "bad_ref": "(b) a bracket that names no cell of this turn's results (or braces)",
    "calc": "(c) a calc marker whose arithmetic from the two cells does not give the written value",
    "unfound_number": "(d) a figure with no marker that no result of this turn holds, nor the message",
    "unfound_date": "(d) a date, month or year with no marker that no result of this turn holds, nor the message",
    "unfound_time": "(d) a clock time with no marker that no result of this turn holds, nor the message",
    "unfound_name": "(d) a name with no marker that no result of this turn holds, nor the message",
    "row_name": "(a) a title or name written before a row marker that the row does not hold (another row's)",
    "empty": "nothing to send (an empty sentence)",
    "garbled": "a lead with text and no sentence in it (nothing to send)",
    # privacy and safety (VALUES_SAFETY)
    "sensitive": "a private or sensitive topic named when the turn did not unlock it",
    "psych": "a claim about their feelings or who they are, or a guess at why they opened something",
    "outcome": "a claim that something was done (an instruction obeyed)",
    "language": "the checks read English only",
    "link": "a link or web address (an instruction's payload)",
    "watch_time": "a marker citing a length total (watch time is never said); no word is read",
    "not_item": "an item card whose ref is no item row of this turn's results",
}
VALUES_SAFETY = ("sensitive", "psych", "outcome", "language", "link", "watch_time")
# the number-word variant: "refuse" (a small number word or a fraction word is a value: refused when no result holds
# it) or "flag" (never refused). Chosen by DESIGN 26's measure
VALUES_NUMBER_WORDS = "refuse"
_V_NUM_WORDS = {**_NUM_WORDS, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
_V_FRACTIONS = {"half": 50.0, "a third": 100 / 3, "a quarter": 25.0, "two thirds": 200 / 3, "three quarters": 75.0}
_V_FRACTION_RX = re.compile(r"(?:(?P<h>" + _HEDGE_RX + r")\s+)?\b(?P<w>half|a third|a quarter|two thirds|three "
                            r"quarters)(?:\s+of)?\s*$", re.I)
_V_NUMWORD_RX = re.compile(r"\b(?P<w>" + "|".join(sorted(set(_V_NUM_WORDS) | set(_V_FRACTIONS), key=len,
                                                          reverse=True)) + r")\b", re.I)
_V_RATIO_BEFORE = re.compile(r"(?P<w>(?:(?:nearly|almost|about|roughly|more than|over|just over|just under)\s+)?"
                             r"(?:twice|doubled|double|tripled|triple|thrice|halved|half|a third|a quarter|"
                             r"\d+(?:\.\d+)?\s+times|(?:two|three|four|five|six|seven|eight|nine|ten) times))"
                             r"(?:\s+(?:as|the))?(?:\s+"
                             r"(?:many|much|busy|big|large|long|often|high))?(?:\s+[a-z]+){0,2}\s*$", re.I)
_V_RATIO_FREE = re.compile(r"\b(?:(?:more than|over|nearly|almost|about|roughly)\s+)?(?:twice|doubled|tripled|halved|"
                           r"quadrupled|(?:two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?) times)\b", re.I)
_V_COUNT_TWICE = re.compile(r"\b(?:opened|watched|saved|liked|played|viewed|seen)(?:\s+\w+)?\s*$", re.I)
_V_ISO = re.compile(r"^((?:19|20)\d\d)-(\d\d)-(\d\d)(?:[ T](\d{1,2}):(\d\d)\s*([ap]\.?m\.?)?)?", re.I)
_V_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d\d))?\s*(am|pm|a\.m\.|p\.m\.)(?![\w])", re.I)
_V_MONTH = r"(?:" + "|".join(_MONTHS) + r"|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"
_V_RANGE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|and|-|–|until|through|till)\s*(\d{1,2})(?:st|nd|rd|th)?"
                      r"\s+(?:of\s+)?(" + _V_MONTH + r")\w*\.?(?:,?\s+((?:19|20)\d\d))?\b", re.I)
_V_DAYMON = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _V_MONTH + r")\w*\.?(?:,?\s+((?:19|20)\d\d))?\b",
                       re.I)
_V_MONDAY = re.compile(r"\b(" + _V_MONTH + r")\w*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+((?:19|20)\d\d))?\b", re.I)
_V_RANGE_END = re.compile(r"\s*(?:to|and|-|–|until|through|till)\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:of\s+)?" +
                          _V_MONTH + r"\w*\.?(?:\s+\d{1,2}(?:st|nd|rd|th)?)?,?\s+((?:19|20)\d\d)\b", re.I)
_V_MONYEAR = re.compile(r"\b(" + _V_MONTH + r")\w*\.?,?\s+((?:19|20)\d\d)\b", re.I)
_V_MONALONE = re.compile(r"\b(" + "|".join(m for m in _MONTHS if m != "may") + r"|May)\b", re.I)
_V_YEAR = re.compile(r"(?<![\w.,])((?:19|20)\d\d)(?![\w.,]\d)")
_V_FIG = re.compile(r"(?<![\w.,@#-])(?P<sign>[+\-−])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
                    r"(?P<ord>st|nd|rd|th)?(?P<pct>\s?%|\s?percent|\s?per cent)?")
_V_QUOTE = re.compile(r"[\"“]([^\"”]{2,160})[\"”]")
_V_HANDLE = re.compile(r"@[\w][\w.]*\w")
# third-party text: never a holder of a figure, a date or a time (a name is matched against it)
_V_THIRD_PARTY = frozenset({"title", "text", "why_matched", "caption", "snippet", "description", "name", "channel",
                            "handle"})
_V_CAPS = re.compile(r"(?<![\w'’@&.-])[A-Z][\w'’&-]*(?:\s+[A-Z][\w'’&-]*)*")
# mvp27 (rule "cell_found"): the code-written strings that are values (a period's label, an era's months, a part of the
# day), the strings that are a window's words (a figure there counts only with its unit), and the prose (never a value)
_V_VALUE_KEYS = frozenset({"label", "part", "from", "to", "question"})
_V_WINDOW_KEYS = frozenset({"window_said", "words", "said", "asked", "rest_words"})
_V_DAY_KEYS = frozenset({"days", "days_active"})
_V_COUNT_NOUN = re.compile(r"^(?:videos?|items?|posts?|saves?|reels?|shorts?|clips?|times?|opens?|channels?|themes?|"
                           r"areas?|lessons?|episodes?|things?|ones?|opened|saved)$", re.I)
_V_PROSE_KEYS = frozenset({"notes", "note", "error", "next", "holds", "holds_not", "busiest_weekdays"})


def _mon_i(tok):
    t = tok.lower()[:3]
    return next((i + 1 for i, m in enumerate(_MONTHS) if m[:3] == t), None)


class _Pool:
    """What this turn's results hold, read once per ledger: every numeric value and list length, every date and
    date-time, every hour, and every string (lower case), from every result's envelope (sheet and meta, notes
    included), and the user's message. Figures, dates and times are read from code's own strings only (window words,
    labels, notes), never from third-party text (a title, a post's text, a name): a number inside a title is no count
    of their history (the planted f_forged_title2, audit F50b, F50c)."""

    def __init__(self, ledger, message=""):
        self.nums, self.fracs, self.dates, self.hours, self.times = set(), [], set(), set(), set()
        self.months, self.years = set(), set()   # (year, month) and years a date part of the results holds
        self.pcts, self.labels = [], set()   # percent-keyed values; the rows' own labels and parts ("2021", "evening")
        strs, code = [], []
        # mvp27 (DESIGN 29, rule "cell_found"): what a CELL holds, apart from code's prose (notes, errors, the codes of
        # `resolved`, refs and ids): numeric leaves, the lengths of row lists, the figures of labels and the message;
        # a figure of code's window words only with its unit ("4 weeks"), never alone
        self.cell_nums, self.other_lens, self.win_units, self.day_nums = set(), set(), set(), set()
        vals, wins = [], []

        def walk(o, key=None):
            if isinstance(o, bool) or o is None:
                return
            if isinstance(o, (int, float)):
                v = float(o)
                self.nums.add(round(v, 6))
                if key in _V_DAY_KEYS:
                    self.day_nums.add(round(v, 6))   # a count of days: found unless typed as a count of items
                else:
                    self.cell_nums.add(round(v, 6))
                if 0 <= v <= 1 and isinstance(o, float):
                    self.fracs.append(v * 100)
                if key and re.search(r"pct|percent|change", str(key)):
                    self.pcts.append(v)
                if key == "hour" and v == int(v):
                    self.hours.add(int(v) % 24)
            elif isinstance(o, str):
                strs.append(o)
                if key in ("part", "label") and o.strip():
                    self.labels.add(_low(o))
                if key in _V_THIRD_PARTY:
                    return
                code.append(o)
                if key in _V_VALUE_KEYS:
                    vals.append(o)
                elif key in _V_WINDOW_KEYS:
                    wins.append(o)
                m = _V_ISO.match(o.strip())
                if m:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    self.dates.add((y, mo, d))
                    self.years.add(y)
                    if m.group(4):
                        h = int(m.group(4)) % 12 + (12 if (m.group(6) or "").lower().startswith("p") else 0) \
                            if m.group(6) else int(m.group(4))
                        self.hours.add(h)
                        self.times.add((h, int(m.group(5))))
            elif isinstance(o, dict):
                for k, v in o.items():
                    walk(v, k)
            elif isinstance(o, (list, tuple)):
                self.nums.add(float(len(o)))
                if key not in _V_PROSE_KEYS and (not o or any(isinstance(v, dict) for v in o)):
                    self.cell_nums.add(float(len(o)))   # a list of rows (or an empty one): its length is a count
                else:
                    self.other_lens.add(float(len(o)))   # notes, holds, the days of a tie: not counted as rows
                for v in o:
                    walk(v, key)
        for r in ledger.by_rid.values():
            walk(r.env)
        self.text = "\n".join(strs).lower()
        self.message = " ".join(str(message or "").split()).lower()
        both = "\n".join(code).lower() + "\n" + self.message
        for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)", both):
            self.nums.add(round(float(m.group(1).replace(",", "")), 6))
        self.value_text = "\n".join(vals).lower() + "\n" + self.message
        for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)", self.value_text):
            self.cell_nums.add(round(float(m.group(1).replace(",", "")), 6))
        for w in wins:
            for m in re.finditer(r"(?<![\w.])(\d+)\s+(day|week|month|year|hour|minute)s?\b", w.lower()):
                self.win_units.add((float(m.group(1)), m.group(2)))
        for m in _V_CLOCK.finditer(both):
            h = int(m.group(1)) % 12 + (12 if m.group(3).lower().startswith("p") else 0)
            self.hours.add(h)
            self.times.add((h, int(m.group(2) or 0)))
        for m in re.finditer(r"\b(?:19|20)\d\d\b", both):
            self.nums.add(float(m.group(0)))
            self.years.add(int(m.group(0)))
        self.cell_nums |= {float(y) for y in self.years}
        # dates written in code's own strings: a period's label ("Jul 2026"), a window's words ("5 January 2021 to 30
        # October 2026"), a month with its year ("2026-09")
        for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _V_MONTH + r")\w*\.?(?:,?\s+((?:19|20)\d\d))?\b",
                             both):
            mo = _mon_i(m.group(2))
            if mo and 1 <= int(m.group(1)) <= 31:
                self.dates.add((int(m.group(3)) if m.group(3) else None, mo, int(m.group(1))))
        for m in re.finditer(r"\b(" + _V_MONTH + r")\w*\.?,?\s+((?:19|20)\d\d)\b|\b((?:19|20)\d\d)-(\d\d)\b(?!-)",
                             both):
            if m.group(1):
                self.months.add((int(m.group(2)), _mon_i(m.group(1))))
            elif 1 <= int(m.group(4)) <= 12:
                self.months.add((int(m.group(3)), int(m.group(4))))
        self.code_text = both

    def has_text(self, s):
        s = " ".join(str(s).lower().split())
        if not s:
            return True
        rx = re.compile(r"(?<![\w@])" + re.escape(s) + r"(?![\w])")
        return bool(rx.search(self.text) or rx.search(self.message))

    def has_num(self, n, pct=False, hedged=False, decimals=0, cells=False, unit=None, day_typed=False, noun=None):
        """`cells` (rule "cell_found"): only what a cell holds; `unit`: the time word after the figure, which may match
        a figure of the window words with its unit ("4 weeks"); `noun`: the word after the figure: under `day_typed` a
        count of days (a window's or a row's `days`) is not found when the figure is typed as a count of items."""
        tol = 1.5 if hedged else 0.5
        if pct:   # "114%": a share of the results (x100), a percent-keyed value, or "114%" in code's own text
            return any(abs(f - n) <= tol for f in self.fracs) or any(abs(p_ - n) <= tol for p_ in self.pcts) or \
                bool(re.search(r"(?<![\d.])" + re.escape(f"{n:g}") + r"\s?%",
                               self.value_text if cells else self.code_text))
        nums = self.cell_nums if cells else self.nums
        if round(n, 6) in nums:
            return True
        if cells and round(n, 6) in self.day_nums and not (day_typed and noun and _V_COUNT_NOUN.match(noun)):
            return True
        if cells and unit and (float(n), unit) in self.win_units:
            return True
        if decimals and any(round(v, decimals) == round(n, decimals) for v in nums):
            return True
        tol = 1.5 if hedged else 0.5
        return any(abs(f - n) <= tol for f in self.fracs) if (pct or n <= 100) else False

    def has_date(self, y=None, mo=None, d=None):
        """A date part some date of the results holds (a day; a month: also a period's label; a year: also any
        year written in the results)."""
        if any((y is None or a is None or a == y) and (mo is None or b == mo) and (d is None or c == d)
               for a, b, c in self.dates):
            return True
        if d is None and mo is not None and any((y is None or a == y) and b == mo for a, b in self.months):
            return True
        return d is None and mo is None and y is not None and y in self.years


def _v_code_has(pool, s):
    """The same date words inside code's own strings (window words, labels, notes) or the message."""
    s = " ".join(str(s).lower().split())
    return bool(re.search(r"(?<![\w@])" + re.escape(s) + r"(?![\w])", pool.code_text))


def _values_pool(ledger, turn, cache):
    key = id(ledger)
    if key not in cache:
        cache[key] = _Pool(ledger, (turn.message if turn else "") or "")
    return cache[key]


def _blank(t, a, b):
    return t[:a] + " " * (b - a) + t[b:]


def _row_own_names(row, rest):
    own = {_low(n) for n in _row_names(row, rest)}
    if isinstance(row, dict):
        for k in ("name", "title", "label", "theme", "channel", "area", "handle"):
            v = row.get(k)
            if isinstance(v, str) and v.strip():
                own.add(_low(v))
                own.add(_low(v.lstrip("@")))
    return own


def _title_said_ok(quoted, row):
    """A quoted title before a row marker against the row's own title (the title_quote loosening: a trailing '#n',
    a trailing '...' of a cut title)."""
    t = _low(row.get("title") or "") if isinstance(row, dict) else ""
    q = _low(re.sub(r"(?:\.\.\.|…)\s*$", "", quoted))
    if not t:
        return False
    if q == t or re.sub(r"\s*#\s*\d+\s*$", "", q) == re.sub(r"\s*#\s*\d+\s*$", "", t):
        return True
    return len(q) >= 8 and (t.startswith(q) or q.startswith(t))


def _v_name_claim(pre):
    """The name a row marker is written after when it is not the row's own: from the last capitalised word of the
    clause right before the marker to the marker ("watched Any% speedrun guide[...]": "Any% speedrun guide"). None
    when that clause holds no capitalised word but the plain ones (an opener, YouTube, a month)."""
    tail = re.split(r"[,;:()\[\]]", pre)[-1]
    starts = [m.start() for m in re.finditer(r"(?<![\w'’@-])[A-Z@][\w'’%&.-]*", tail)]
    for a in reversed(starts):
        words = tail[a:].split()
        while words and _v_plain_cap(words[0]):
            words = words[1:]
        if words and len(words) <= 8 and re.match(r"[A-Z@]", words[0]):
            return " ".join(words).rstrip(".…")
    return None


def _v_row_strings(o, key=None):
    """Every string under one row (its title, channel, handle, theme, name, label, a matched line), lower case."""
    if isinstance(o, dict):
        return [s for k, v in o.items() if k != "ref" for s in _v_row_strings(v, k)]
    if isinstance(o, (list, tuple)):
        return [s for v in o for s in _v_row_strings(v, key)]
    return [_low(o)] if isinstance(o, str) and o.strip() else []


def _v_row_holds(row, claim):
    """mvp27: the name written before a row marker is that row's own: some string under the row holds it (a part of
    a title is the row's too), with a cut title's trailing '…' and a trailing '#n' read as in rule (a)."""
    if not isinstance(row, dict):
        return True
    c = _low(re.sub(r"(?:\.\.\.|…)\s*$", "", claim)).strip()
    c2 = re.sub(r"\s*#\s*\d+\s*$", "", c)
    for s in _v_row_strings(row):
        s2 = _low(re.sub(r"(?:\.\.\.|…)\s*$", "", s)).strip()
        for x in (c, c2, c.lstrip("@"), c2.lstrip("@")):
            if x and re.search(r"(?<![\w@])@?" + re.escape(x) + r"(?![\w])", s2):
                return True
        if len(s2) >= 8 and (c.startswith(s2) or c2.startswith(s2)):
            return True   # a cut title ("Sourdough starter day 3: feed 50 g flour…") written whole or longer
    return False


def _values_marked(raw, markers, ledger, turn, nw_refuse, pool=None, cm_rules=None):
    """Rules (a) and (c), and watch_time on a length cell: [(code, detail)] from the markers alone. `cm_rules`: the
    values mode's rules (mvp27: "row_name")."""
    out = []
    r = _typed_weekday(raw)
    if r:   # a weekday written beside a date that is another day of the week (calendar arithmetic)
        out.append(("wrong_value", r[1]))
    names_idx = ledger.all_names()
    prev_end = 0
    for mk in sorted(markers, key=lambda m: m.mstart):
        pre = raw[prev_end:mk.mstart if mk.kind != "calc" else mk.start]
        if mk.kind in ("value", "count"):
            if not mk.said:
                fm = _V_FRACTION_RX.search(raw[prev_end:mk.mstart])
                if fm and mk.kind == "value" and _measure(mk.rest, mk.value)[1] == "share":
                    want = _V_FRACTIONS[fm.group("w").lower()]
                    if nw_refuse and abs(float(mk.value) * 100 - want) > 5.0:
                        out.append(("wrong_value", f"'{fm.group('w')}' is {mk.path} = {_fmt(mk.rest, mk.value)}"))
                elif mk.kind == "value" and _measure(mk.rest, mk.value)[1] == "watch_time":
                    out.append(("watch_time", f"{mk.path} is a length total, never said"))
                prev_end = mk.end
                continue
            r = check_value(mk)
            if r and r[0] in ("wrong_value", "wrong_name", "wrong_measure", "watch_time", "bad_ref"):
                out.append(r)
            elif not r and mk.kind == "value" and _measure(mk.rest, mk.value)[1] == "points":
                pts = _points_of(mk.rest, mk.value)
                if (mk.sign == "+" and pts < 0) or (mk.sign in ("-", "−") and pts > 0):
                    out.append(("wrong_value", f"{mk.path} = {round(pts, 1)} points"))
        elif mk.kind == "row" and not mk.said:
            row = mk.value
            q = re.search(r"[\"“]([^\"”]{2,160})[\"”]\s*$", pre)
            if q and isinstance(row, dict) and row.get("title") is not None:
                if not _title_said_ok(q.group(1), row):
                    out.append(("wrong_name", f"the quoted title before {mk.path} is not that item's title"))
            else:
                own = _row_own_names(row, mk.rest)
                lowp = _low(pre)
                other = next((n for n in sorted(set(names_idx) | {_low(x) for x in turn.names if x} |
                                                (pool.labels if pool is not None else set()), key=len, reverse=True)
                              if len(n) >= 2 and re.search(r"(?<![\w@])" + re.escape(n) + r"\s*$", lowp)), None)
                if other and other not in own and other.lstrip("@") not in own:
                    out.append(("wrong_name", f"the name before {mk.path} is another row's"))
                elif pool is not None and not other:
                    claim = _v_name_claim(pre)
                    if claim and not (pool.has_text(claim) or pool.has_text(re.sub(r"\s*#\s*\d+\s*$", "", claim))):
                        out.append(("unfound_name", f"the name before {mk.path} is no name of this turn's results"))
                    elif claim and cm_rules is not None and "row_name" in cm_rules and not _v_row_holds(row, claim):
                        # mvp27 (run B N038.0): a title some other row holds, written beside this row's marker
                        out.append(("row_name", f"the name before {mk.path} is not that row's own: write the title "
                                                f"or name the row holds, or cite the row it belongs to"))
        elif mk.kind == "calc":
            words = None
            if mk.op == "ratio" and not mk.said:
                wm = _V_RATIO_BEFORE.search(raw[prev_end:mk.mstart])
                words = " ".join(wm.group("w").lower().split()) if wm else None
            r = _values_calc(mk, ledger, words)
            if r:
                out.append(r)
        prev_end = mk.end
    return out


def _values_calc(mk, ledger, words=None):
    """Rule (c): the op computed from the two cells (of any results), the typed number or ratio words against it.
    `words`: a ratio's words written a little before its marker ("twice as many[=ratio(...)]")."""
    (va, ra), (vb, rb) = _cell(ledger, mk.a), _cell(ledger, mk.b)
    if "length" in (_family(ra), _family(rb)):
        return "watch_time", "a length total is never said"
    va, vb = float(va), float(vb)
    op = mk.op
    det = f"{mk.a} = {round(va, 4)}, {mk.b} = {round(vb, 4)}"
    if op == "diff":
        val = va - vb
    elif op == "points":
        val = (va - vb) * 100
    elif vb == 0:
        return "calc", f"{op} over 0; {det}"
    elif op == "pct_change":
        val = (va - vb) / vb * 100
    else:
        val = va / vb
    said = " ".join((mk.said or words or "").lower().split())
    if op == "ratio":
        if mk.num is not None and (mk.unit or "").strip() == "times":
            return None if abs(mk.num - val) <= 0.1 * val else ("calc", f"{mk.a} / {mk.b} = {round(val, 2)}")
        nt = re.match(r"^(?:(?:nearly|almost|about|roughly) )?(\S+) times$", said)
        if nt:
            n = _num_of(nt.group(1))
            return None if n is not None and abs(n - val) <= 0.1 * n else ("calc", f"{mk.a} / {mk.b} = "
                                                                                   f"{round(val, 2)}")
        band = next(((lo, hi) for rx, lo, hi in _RATIO_BANDS if rx.match(said)), None)
        if band is not None and not (band[0] <= val <= band[1]):
            return "calc", f"'{said}' needs {band[0]} to {band[1]}; {mk.a} / {mk.b} = {round(val, 2)}"
        return None
    if mk.num is None:
        return None   # no number written: nothing to compare (a flag)
    tol = 0.0 if op == "diff" else (0.5 if op == "points" else 1.0)
    if mk.hedge:
        tol = max(tol, 1.5 if op == "points" else abs(val) * 0.1)
    if abs(abs(mk.num) - abs(val)) > tol + 1e-9:
        return "calc", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    sign = re.search(r"(?:^|\s)([+\-−])\s*\d", " " + (mk.said or ""))
    if sign and ((sign.group(1) == "+" and val < 0) or (sign.group(1) in ("-", "−") and val > 0)):
        return "calc", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    return None


def _values_unmarked(raw, markers, ledger, turn, pool, nw_refuse, cm_rules=None):
    """Rule (d): what is written with no marker, against what this turn's results hold. -> [(code, detail)].
    `cm_rules`: the values mode's rules (mvp27: "cell_found", a figure is found in a cell, never in code's prose)."""
    out = []
    cells = cm_rules is not None and "cell_found" in cm_rules
    day_typed = cells and "day_typed" in cm_rules
    t = raw
    for mk in markers:
        t = _blank(t, mk.start, mk.end)
    t = re.sub(r"\[[^\]]*\]", lambda m: " " * len(m.group(0)), t)   # a bracket that did not parse (bad_ref)
    # quoted strings (titles, lines of a post): found inside a string of the results
    for m in list(_V_QUOTE.finditer(t)):
        q = re.sub(r"(?:\.\.\.|…)\s*$", "", m.group(1)).strip()
        q2 = re.sub(r"\s*#\s*\d+\s*$", "", q)
        if not (pool.has_text(q) or pool.has_text(q2) or _low(q2) in pool.text):
            out.append(("unfound_name", "a quoted title that no result of this turn holds"))
        t = _blank(t, m.start(), m.end())
    # links are the safety check's; handles are names
    t = re.sub(r"https?://\S+|www\.\S+", lambda m: " " * len(m.group(0)), t)
    for m in list(_V_HANDLE.finditer(t)):
        if not pool.has_text(m.group(0)):
            out.append(("unfound_name", f"'{_clip(m.group(0), 40)}' is named with no marker and no result of this "
                                        "turn holds it"))
        t = _blank(t, m.start(), m.end())
    # dates: ranges of days, day and month, month and day, month and year, a month alone, a year
    for m in list(_V_RANGE.finditer(t)):
        mo, y = _mon_i(m.group(3)), (int(m.group(4)) if m.group(4) else None)
        for d in (int(m.group(1)), int(m.group(2))):
            if not pool.has_date(y, mo, d):
                out.append(("unfound_date", f"'{_clip(m.group(0), 40)}': no result of this turn holds that day"))
                break
        t = _blank(t, m.start(), m.end())
    for rx, order in ((_V_DAYMON, "dmy"), (_V_MONDAY, "mdy")):
        for m in list(rx.finditer(t)):
            if order == "dmy":
                d, mo, y = int(m.group(1)), _mon_i(m.group(2)), (int(m.group(3)) if m.group(3) else None)
            else:
                mo, d, y = _mon_i(m.group(1)), int(m.group(2)), (int(m.group(3)) if m.group(3) else None)
            if not (1 <= d <= 31):
                continue
            if y is None:   # "5 September to 2 October 2026": the year of the day that closes the range
                ny = _V_RANGE_END.match(raw[m.end():m.end() + 40])
                y = int(ny.group(1)) if ny else None
            if not (pool.has_date(y, mo, d) or _v_code_has(pool, m.group(0))):
                out.append(("unfound_date", f"'{_clip(m.group(0), 40)}': no result of this turn holds that day"))
            t = _blank(t, m.start(), m.end())
    for m in list(_V_MONYEAR.finditer(t)):
        mo, y = _mon_i(m.group(1)), int(m.group(2))
        if not (pool.has_date(y, mo) or _v_code_has(pool, m.group(0))):
            out.append(("unfound_date", f"'{_clip(m.group(0), 40)}': no result of this turn holds that month"))
        t = _blank(t, m.start(), m.end())
    for m in list(_V_YEAR.finditer(t)):
        y = int(m.group(1))
        if not (pool.has_date(y) or _v_code_has(pool, m.group(1))):
            out.append(("unfound_date", f"'{y}': no result of this turn holds that year"))
        t = _blank(t, m.start(), m.end())
    for m in list(_V_MONALONE.finditer(t)):
        if m.group(1) in ("may", "march"):
            continue   # the verb, not the month
        mo = _mon_i(m.group(1))
        if not (pool.has_date(None, mo) or _v_code_has(pool, m.group(1))):
            out.append(("unfound_date", f"'{m.group(1)}': no result of this turn holds that month"))
        t = _blank(t, m.start(), m.end())
    # clock times
    for m in list(_V_CLOCK.finditer(t)):
        h = int(m.group(1)) % 12 + (12 if m.group(3).lower().startswith("p") else 0)
        ok = (h, int(m.group(2))) in pool.times if m.group(2) and m.group(2) != "00" else (h in pool.hours)
        if not ok:
            out.append(("unfound_time", f"'{_clip(m.group(0), 20)}': no result of this turn holds that hour"))
        t = _blank(t, m.start(), m.end())
    # figures
    for m in list(_V_FIG.finditer(t)):
        num = m.group("num")
        n = float(num.replace(",", ""))
        dec = len(num.split(".")[1]) if "." in num else 0
        hedged = bool(re.search(r"\b" + _HEDGE_RX + r"\s*$", t[:m.start()], re.I))
        if m.group("ord") and pool.has_date(None, None, int(n)):
            t = _blank(t, m.start(), m.end())
            continue   # "the 30th": a day a date of the results holds
        unit = re.match(r"\s+(day|week|month|year|hour|minute)s?\b", t[m.end():], re.I) if cells else None
        noun = re.match(r"\s+([a-z]+)", t[m.end():], re.I)
        if not pool.has_num(n, pct=bool(m.group("pct")), hedged=hedged, decimals=dec, cells=cells,
                            unit=unit.group(1).lower() if unit else None, day_typed=day_typed,
                            noun=noun.group(1) if noun else None):
            out.append(("unfound_number", f"'{_clip(m.group(0).strip(), 20)}' has no marker and no result of this "
                                          "turn holds it: cite its cell"))
        t = _blank(t, m.start(), m.end())
    # number words (the variant): a ratio word with no ratio marker is a computed value no cell holds; a small count;
    # a fraction as a share
    if nw_refuse:
        for m in list(_V_RATIO_FREE.finditer(t)):
            if _V_COUNT_TWICE.search(t[max(0, m.start() - 25):m.start()]) and m.group(0).lower() == "twice":
                continue   # "opened twice": a count of two, read below as a number word
            out.append(("unfound_number", f"'{m.group(0)}' has no ratio marker: no result of this turn holds a "
                                          "ratio"))
            t = _blank(t, m.start(), m.end())
        t = re.sub(r"\b(?:the\s+)?(?:first|second|other)\s+half\b", lambda m: " " * len(m.group(0)), t, flags=re.I)
        for m in list(_V_NUMWORD_RX.finditer(t)):
            w = m.group("w").lower()
            ok = pool.has_num(float(_V_NUM_WORDS[w]), cells=cells) if w in _V_NUM_WORDS else \
                any(abs(f - _V_FRACTIONS[w]) <= 5.0 for f in pool.fracs)
            if not ok:
                out.append(("unfound_number", f"'{w}' has no marker and no result of this turn holds it"))
            t = _blank(t, m.start(), m.end())
    # names: the library's names (lower case too), then capitalised words
    for a, b, n in _name_spans(t, ledger.all_names(), turn.names):
        if not pool.has_text(n) and not pool.has_text(re.sub(r"(?:es|s)$", "", n)):
            out.append(("unfound_name", f"'{_clip(t[a:b], 40)}' is named with no marker and no result of this turn "
                                        "holds it"))
        t = _blank(t, a, b)
    lead_at = len(t) - len(t.lstrip(" \"“'(‘"))
    for m in _V_CAPS.finditer(t):
        words = m.group(0).split()
        while words and _v_plain_cap(words[0]):
            words = words[1:]
        while words and _v_plain_cap(words[-1]):
            words = words[:-1]
        if not words:
            continue
        run = " ".join(words)
        if m.start() == lead_at and len(m.group(0).split()) == 1 and not re.match(r"\s*[A-Z\"“@]", raw[m.end():]):
            continue   # the sentence's first word, not before another capital: an English capital, not a name
        if not pool.has_text(run):
            out.append(("unfound_name", f"'{_clip(run, 40)}' is named with no marker and no result of this turn "
                                        "holds it"))
    return out


def _v_plain_cap(w):
    w0 = re.split(r"['’]", w.lower())[0].strip("'’")
    return (w0 in OPENERS or w0 in I.ALLOWED_CAPS or w0 in ("of", "and", "the", "de", "&", "a", "an", "shorts", "reels",
                                                            "reel", "youtube's") or w0 in I.WEEKDAYS or
            w0.rstrip("s") in I.WEEKDAYS or any(w0[:3] == x[:3] for x in _MONTHS if len(w0) >= 3) or
            w0 in ("is", "was", "were", "are", "had", "has", "did"))


def _values_hidden_rank(low, markers, res):
    """Step 3.13 as today (the private line under a number of a result that left private items out, or a rank word
    over hidden rows), read for the values mode's own outcome."""
    if res is None:
        return False
    hid = (res.meta or {}).get("hidden") or {}
    if hid.get("rank_hidden_above") and _RANK.search(low):
        return True
    return int(hid.get("sensitive") or 0) > 0 and (
        any(mk.kind in ("value", "count", "calc") and (mk.rid == res.rid or mk.a.startswith(res.rid + "."))
            for mk in markers) or bool(_RANK.search(low)) or
        bool(re.search(r"\b(?:everything|all of|every|only|nothing but)\b", low)))


# mvp27 (rule "motive_you", DESIGN 29): the values mode's motive pattern. Today's _MOTIVE (full and cells, unchanged)
# fires on a bare "because", which a reading of what a number is made of needs ("2024 looks thin because you opened
# 8[...] videos that year"). Here "because" counts only before a motive or a state of mind said of them
_V_STATE = (r"(?:bored|tired|sad|stressed|lonely|anxious|curious|happy|excited|nostalgic|homesick|restless|upset|"
            r"love|loved|like|liked|enjoy|enjoyed|want|wanted|need|needed|miss|missed|crave|craved|wish|wished|hope|"
            r"hoped|try|tried|trying|relax|relaxing|unwind|unwinding|escape|escaping|procrastinat\w*|avoid\w*|"
            r"obsess\w*|addict\w*|hooked|into it|into them|passionate|fascinated|interested|keen)")
_V_MOTIVE = re.compile(r"\bbecause\s+(?:you(?:'re|'ve|'d|\s+are|\s+were|\s+have|\s+had)?|they(?:'re|\s+are|\s+were)?)"
                       r"\s+(?:(?:were|was|are|is|felt|feel|got|get|getting|seem|seemed|must|might|may|probably|likely|"
                       r"clearly|really|just|so|been|be|still|always|often)\s+)*" + _V_STATE + r"\b"
                       r"|\bbecause of (?:your|their) (?:boredom|mood|moods|stress|feelings?|loneliness|curiosity|"
                       r"habits?|interests?|passion|love|job|work|kids?|partner|day)\b"
                       r"|\bbecause (?:it|they|that|this|these) (?:relax|relaxes|calm|calms|help|helps|comfort|comforts|"
                       r"soothe|soothes|entertain|entertains|distract|distracts) (?:you|them)\b"
                       r"|\byou must (?:be|have been|feel|enjoy|like|want|need|love|have)\b"
                       r"|\bto (?:unwind|relax|chill|escape|de-?stress|switch off|wind down|kill time|pass the time|"
                       r"feel better|learn)\b|\bafter (?:a long day|work|school)\b|\bwhen you (?:were|felt|are) "
                       r"(?:bored|tired|sad|stressed|lonely|anxious)\b|\bout of (?:boredom|habit)\b|\bfor fun\b", re.I)


def _values_safety(raw, plain, low, markers, ledger, res, turn, pool, cm_rules=None):
    """The privacy and safety refusals kept (VALUES_SAFETY), each called directly on the sentence."""
    out = []
    motive = _V_MOTIVE if cm_rules is not None and "motive_you" in cm_rules else _MOTIVE
    if _sensitive(plain, turn):
        out.append(("sensitive", None))
    if PSYCH.search(low):
        out.append(("psych", None))
    elif motive.search(low):   # why they opened something (DESIGN 26: no true sentence of any set holds it)
        out.append(("psych", "why they opened something is not in the export"))
    if OUTCOME.search(low):
        out.append(("outcome", None))
    wres = res or next(iter(ledger.by_rid.values()), None)
    if _not_english(plain) and ((wres.sheet.get("lang") if wres is not None else None) or "en") == "en":
        out.append(("language", "the checks read English only"))
    lt = _V_HANDLE.sub(lambda m: " " if pool.has_text(m.group(0)) else m.group(0), plain)
    if I._LINK.search(lt):
        out.append(("link", "no link or web address in a sentence"))
    return out


def check_sentence_values(sentence, ledger, turn=None, where="point", index=0, mode=None, pool_cache=None,
                          too_long=False, with_flags=False):
    """One sentence in values mode -> Outcome: refused only by VALUES_REFUSE. `with_flags` (a sentence checked
    alone): every code of today's full and cells checks of the same sentence goes into `flags` (check_answer_values
    takes them from the whole answer's checks instead)."""
    cm = check_mode(mode) if mode is not None else VALUES
    turn = turn or Turn()
    if not isinstance(ledger, Ledger):
        ledger = Ledger(ledger)
    pool = _values_pool(ledger, turn, pool_cache if pool_cache is not None else {})
    nw = cm.rule("nw_refuse")
    out = Outcome(where, index, sentence)
    raw = " ".join(str(sentence or "").split())
    if not raw:
        out.reasons.append("empty")
        return out
    markers, bad = parse(raw, ledger, CELLS_LOOSE)
    for mk in markers:
        if mk.kind == "calc":
            for p in (mk.a, mk.b):
                try:
                    out.cells[p] = _cell(ledger, p)[0]
                except (KeyError, AttributeError):
                    pass
        elif mk.kind in ("value", "count"):
            out.cells[mk.path] = mk.value
    rids = sorted({mk.rid for mk in markers if mk.rid} | {p.split(".", 1)[0] for mk in markers if mk.kind == "calc"
                                                          for p in (mk.a, mk.b)})
    out.rid = rids[0] if rids else None
    res = ledger.get(out.rid) if out.rid else None
    plain = strip_markers(raw)
    low = plain.lower()
    found = [(b, _bad_detail(raw, ledger)) for b in bad]
    found += _values_marked(raw, markers, ledger, turn, nw, pool, cm.rules)
    found += _values_unmarked(raw, markers, ledger, turn, pool, nw, cm.rules)
    found += _values_safety(raw, plain, low, markers, ledger, res, turn, pool, cm.rules)
    for r, d in found:
        if r not in out.reasons:
            out.reasons.append(r)
        if d and d not in out.details:
            out.details.append(d)
            out.notes.setdefault(r, d)
    out.hidden_rank = _values_hidden_rank(low, markers, res)
    out.layer = "values" if out.reasons else None
    if too_long:
        out.flags.append({"code": "too_long", "mode": "values"})
    if with_flags:
        for name, m_ in (("cells", CELLS), ("full", FULL)):
            for c in check_sentence(sentence, ledger, turn, where, index, mode=m_).reasons:
                out.flags.append({"code": c, "mode": name})
    if not out.reasons:
        out.sent = plain
    return out


def _values_flags(o, others):
    """The codes today's checks give the same sentence (by place), as flags: cells first, then full."""
    seen, fl = set(), list(o.flags)
    for name, v in others:
        x = next((x for x in v.outcomes if (x.where, x.index) == (o.where, o.index)), None)
        for c in (x.reasons if x is not None else []):
            if (c, name) not in seen:
                seen.add((c, name))
                fl.append({"code": c, "mode": name})
    return fl


def check_answer_values(form, ledger, turn=None, mode=None):
    """The form in values mode -> Verdict: today's full and cells verdicts are computed for the flags; a sentence is
    refused only by the values rules and the safety list. The repair (4.5) is due when the lead is refused or more
    than half of the sentences are."""
    cm = check_mode(mode) if mode is not None else VALUES
    turn = turn or Turn()
    if not isinstance(ledger, Ledger):
        ledger = Ledger(ledger)
    try:
        f = form if isinstance(form, AnswerForm) else AnswerForm.model_validate(form)
    except ValidationError as e:
        return Verdict(outcomes=[], form_error=str(e.errors()[0].get("type")), repair=True, check=cm.name)
    vc = check_answer(f, ledger, turn, mode=CELLS)
    vf = check_answer(f, ledger, turn, mode=FULL)
    others = (("cells", vc), ("full", vf))
    cache = {}
    v = Verdict(outcomes=[], check=cm.name)
    lead_s = _split(f.lead)
    if not lead_s:
        v.outcomes.append(Outcome("lead", 0, f.lead or "", reasons=["garbled" if (f.lead or "").strip() else "empty"]))
    else:
        long_lead = len(strip_markers(f.lead)) > LEAD_MAX or len(lead_s) > 2
        for k, s in enumerate(lead_s):
            v.outcomes.append(check_sentence_values(s, ledger, turn, "lead", k, cm, cache,
                                                    too_long=long_lead or len(strip_markers(s)) > SENT_MAX))
    for k, p in enumerate(f.points):
        sents = _split(p)
        text = sents[0] if len(sents) == 1 else " ".join(str(p).split())
        v.outcomes.append(check_sentence_values(text, ledger, turn, "point", k, cm, cache,
                                                too_long=k >= POINTS_MAX or len(sents) != 1 or
                                                len(strip_markers(text)) > SENT_MAX))
    for o in v.outcomes:
        o.flags = _values_flags(o, others)
    v.private_line = any(o.kept and o.hidden_rank for o in v.outcomes)
    rows = _item_rows(ledger)
    for k, it in enumerate(f.items):
        if k >= ITEMS_MAX:   # the cards' cap, as today (not a sentence)
            v.items.append({"ref": it.ref, "note": None, "kept": False, "reasons": ["too_long"], "flags": []})
            continue
        reasons = [] if it.ref in rows else ["not_item"]
        note_o = check_sentence_values(it.note, ledger, turn, "note", k, cm, cache,
                                       too_long=len(it.note) > NOTE_MAX) if it.note else None
        if note_o is not None:
            reasons += note_o.reasons
        fl = [{"code": c, "mode": nm} for nm, vv in others for c in
              ((vv.items[k]["reasons"] if k < len(vv.items) else []) or []) if c not in reasons]
        v.items.append({"ref": it.ref, "note": note_o.sent if note_o and note_o.kept else None,
                        "kept": "not_item" not in reasons, "reasons": reasons, "flags": fl})
    v.outside = vc.outside
    v.chart = vc.chart
    sents = [o for o in v.outcomes if o.where in ("lead", "point")]
    failed = [o for o in sents if not o.kept]
    v.repair = (not v.lead_ok) or (len(sents) > 0 and len(failed) * 2 > len(sents))
    return v


# mvp27 (DESIGN 29): the rules added to the values mode, each measured on the six live runs. "row_name": a name before
# a row marker is that row's own; "cell_found": a figure is found in a cell, never in code's prose; "motive_you": the
# motive pattern reads a motive or a state of mind said of them, not a bare "because"
VALUES_RULES = frozenset({"row_name", "cell_found", "day_typed", "motive_you"})


def values_mode(number_words=None, rules=None):
    """The values CheckMode, with the number-word variant ("refuse" or "flag"; None: VALUES_NUMBER_WORDS) and the
    mvp27 rules (`rules`, a subset of VALUES_RULES; None: all of them; the measures build the others)."""
    nw = (number_words or VALUES_NUMBER_WORDS) == "refuse"
    extra = VALUES_RULES if rules is None else frozenset(rules) & VALUES_RULES
    return CheckMode("values", off=CELLS.off, loose=CELLS_LOOSE, cells=True,
                     rules=frozenset({"values"} | ({"nw_refuse"} if nw else set())) | extra)


VALUES = values_mode()


# ------------------------------------------------------------------ the repair text (4.5)
def repair_message(verdict):
    """The text sent back as the give_answer call's tool_result with is_error: true, or None when no repair is due.
    It names each failed sentence by its place, the reason and the true values of its cells; it quotes no third-party
    text (titles are left out; brackets are neutralised)."""
    if not verdict.repair:
        return None
    if verdict.form_error:
        return f"The answer form did not validate ({verdict.form_error}). Send give_answer again with every field."
    parts = []
    for o in verdict.outcomes:
        if o.kept:
            continue
        where = "lead" if o.where == "lead" else f"point {o.index + 1}"
        if o.where == "lead" and len([x for x in verdict.outcomes if x.where == "lead"]) > 1:
            where = f"lead sentence {o.index + 1}"
        bits = []
        for r in o.reasons:
            # the true values when the step gave them ("'38%' is r1.areas[0].share = 0.356 (36%)"), else the rule
            bits.append(o.notes.get(r) or REASON_TEXT.get(r) or _insight_detail(r))
        seen, uniq = set(), []
        for b in bits:
            b = b if len(b) <= 160 else b[:159] + "…"
            if b not in seen:
                seen.add(b)
                uniq.append(b)
        parts.append(f"{where}: " + "; ".join(uniq))
    head = "These sentences failed the check. Rewrite only these, or drop the points: "
    return head + " ".join(p.rstrip(".") + "." for p in parts)
