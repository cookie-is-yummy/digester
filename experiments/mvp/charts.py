"""Charts drawn by code (round 12, pass 7, G3): a chart spec in, an SVG, a PNG, a text chart and a flat list of its
numbers out.

Pure functions, no global state, no model call, no network. Nothing here imports facts, insight or history: code
upstream builds a spec from the fact sheet, calls validate(), and draws only a spec with no reasons.

THE SPEC (a small JSON-serialisable dict)

    {"kind": "per_month",            # by_area | by_theme | by_channel | topics_by_year | per_month | per_year
     "caption": "Videos opened per month:",   # what is counted, and of what (worded by code upstream)
     "unit": "count",                # count | percent (percent values are 0-100, not fractions)
     "lang": "en",                   # en | es: number format (1,094 / 1.094) and the default legend words
     "whole": False,                 # percent only: True when the rows are parts of ONE whole (they add to 100 at
                                     # most); default True for by_area, by_theme, by_channel, else False
     "legend": {"shorts": "Shorts", "long": "Long videos", "unknown": "Length unknown"},   # optional
     "series": ["2026", "2025"],     # optional, at most 2: two shades of one hue, "now" then "before"
     "rows": [{"label": "Jan", "value": 40,
               "parts": {"long": 25, "shorts": 14, "unknown": 1},   # optional; every row or none
               "href": "https://www.youtube.com/@a-channel",        # optional; a link for the label
               "note": "Gaming",                                    # optional; a short word after the value
               "series": 0,                                         # with chart "series" only
               "group": "Gaming"}]}                                 # optional; a gap between groups

  Parts are videos of known length split into Shorts and long ones; videos of unknown length are their own part
  ("unknown"), never folded into another. A row's parts add up to its value exactly for counts, and within rounding
  for percents.

THE CALLS

  validate(spec) -> [reasons]   empty means drawable. Every drawer returns None for a spec with reasons.
  svg(spec, theme, width)       a self-contained SVG string (theme light | dark | auto: auto follows the page's
                                prefers-color-scheme through a scoped <style>).
  png(spec, theme, scale)       PNG bytes, or None when Pillow is missing or anything fails: the caller keeps the text.
  text(spec)                    the text chart (8 whole block cells per row), the fallback and the description.
  describe(spec)                every number the chart shows, flat, with what it is of, for the auditor.
  python3 -m mvp.charts demo --out DIR   every kind, light and dark, SVG and PNG, from made-up specs.

DESIGN (the dataviz method: form first, colour last, validated)

  Form. Rankings and shares (by area, theme, channel; two topics for two years) are horizontal bars: long labels
  read on a phone, one baseline, the value at each bar's tip. Counts over time (per month, per year) are columns
  from one baseline, the value on each cap, the period under it. Columns turn into horizontal bars in time order
  when a value or a period does not fit its slot (a 4-digit count over 12 months at phone width) or when rows carry
  notes: the numbers stay whole, never shrunk to "1.1K". Horizontal bars put each name beside its bar when every
  name fits 42% of the width; otherwise (a long channel name, or rows with notes) each name sits on its own line
  above a bar of the full width, so a channel's name stays whole and a note follows the name ("2023 · Block
  building"). Split by Shorts is a stacked bar (long videos, Shorts,
  unknown, in that fixed order from the baseline) with a legend; "without Shorts" is a single series with no
  legend. Two topics for two years: one hue, two shades (the earlier year lighter), with a legend.
  Every value is printed: a picture in a text channel has no hover and no table, so the numbers ride the marks.

  Colour (validated with the dataviz validator against the chart surface, both modes):
    long videos   light #2a78d6  dark #3987e5   (categorical slot 1, blue)
    Shorts        light #eb6834  dark #d95926   (slot 2, orange): adjacent CVD dE 24.7 light / 26.8 dark,
                                                normal-vision dE 33.6 / 31.8; contrast 3.1:1 light / 4.5:1 dark
    unknown       light #8f8d86  dark #74736c   (a neutral: "no length known" is not an identity; 3.2:1 / 3.7:1;
                                                deutan dE 11.3 / protan 9.0 against orange, all pairs)
    one series    the long-video blue
    two shades    now #2a78d6 / before #86b6ef light; now #3987e5 / before #184f95 dark (ordinal check passes:
                  light end 2.06:1, dark end 2.15:1)
  Text wears ink, never a series colour: primary #0b0b0b / #f0efec, secondary #52514e (7.7:1) / #c3c2b7 (9.7:1).
  Surface #fcfcfb / #1a1a19, a hairline ring #e1e0d9 / #2c2c2a, the baseline #c3c2b7 / #383835.

  Marks. Bars 12 px thick, columns at most 24 px wide; a 4 px rounded data end, square at the baseline; a 2 px
  surface gap between stacked parts (centred on the boundary, so the whole bar keeps its exact length); a part above
  zero is drawn at least 3 px wide, the largest part of that bar giving up the difference (the bar's length stays
  exact, and 2 videos of unknown length beside 900 are still seen); a hairline baseline; no gridlines (every value
  is printed). A value above zero is never thinner than 1 px. The parts' lengths are scaled to add up to the bar's
  own length exactly (percent parts may differ from the value by rounding; the bar is the value, never more). A bar
  too short for the gaps (under 6 px a part) is drawn without them, so 3 videos beside 2,400 are a sliver, not
  nothing.

  Type at the bubble's width (300 px is the chat bubble's content at a 430 px phone): caption 13 px secondary ink,
  wrapped at words onto at most 3 lines; labels 12 px primary ink, cut with "…" at a word where it can, never
  wrapped; values 12 px (10.5 px on column caps); legend 11.5 px, on one line, or one item per line when the items do
  not fit (never broken mid-item); period labels 11 px, 10 px when 11 does not fit (12 months at phone width:
  "May"), before a column chart turns sideways. System sans everywhere. A caption word too long for a line is cut.
  The PNG's real font may be a little wider than the estimate: a label beside the bars may use most of the gap
  before the baseline, then is drawn up to 10% smaller, and only then cut (review: "Gaming 2026" and "Gaming 2025"
  were both drawn "Gaming…", "May" was "M…").

  Width. The default is 300 logical px: the page's bubble at 430 px holds about 300 px of content. The SVG carries a
  viewBox; the web channel sets it to width 100% and height auto so it scales with the bubble.

  The PNG path. Pillow (pillow==12.3.0 in requirements.txt), drawing the same layout the SVG is drawn from, so the
  numbers and the bar lengths are the same by construction. Chosen because it is the lightest thing that looks right
  on a Mac with plain Python 3.12: one wheel (FreeType and libpng inside), no browser, no Cairo, no matplotlib (tens
  of MB and a font cache, and its own look). A pure-Python PNG writer would need its own text rasteriser. Fonts: the
  system's sans (macOS: SF, then Helvetica, then Arial; Linux: Inter, DejaVu, Liberation, FreeSans; MVP_CHART_FONT
  names one), then per-character fallback fonts for scripts the first lacks (Arial Unicode, DejaVu), a colour emoji
  font where there is one (Apple Color Emoji, Noto Color Emoji), and Pillow's own bundled scalable font as the last
  resort, so a PNG is drawn even with no system font. Shapes are drawn at twice the scale and reduced (smooth
  corners). Right-to-left labels: Pillow lays them out with libraqm where it has it; without it (the usual Mac wheel
  without fribidi) a small reordering here puts right-to-left runs in visual order (Hebrew reads right; Arabic
  letters stay unjoined). A character no font has is left out of the PNG's label, never drawn as a box.

  Safety. Every label, caption, note, legend word and href is third-party text: validate() refuses control and bidi
  override characters, invisible format characters (zero-width space, direction marks, soft hyphen, BOM, and tag
  characters outside a flag emoji, which can carry hidden words to a model that reads describe()), and any link
  that is not https on youtube.com, youtu.be or instagram.com (and www/m hosts), or that is a redirect or an account
  action there (/redirect, /attribution_link, /logout, /accounts/..., a "." or ".." segment, an address inside the
  query); links carry rel="noopener noreferrer"; values of a billion or more are refused (their text crushed the
  plot to 1 px bars), and validate() never raises, whatever the spec holds;
  svg() escapes everything for XML; the SVG has no script, no event attribute, no foreignObject, no external
  reference (url() only to its own #ids, scoped by a hash of the spec so two charts on one page never share an id),
  and its <style> only sets colours and fonts.

  Determinism. The same spec, theme and width give the same SVG string and, on one machine, the same PNG bytes
  (fonts differ between machines, so the PNG's text pixels do too; the bar pixels do not).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

KINDS = {"by_area": "bars", "by_theme": "bars", "by_channel": "bars", "topics_by_year": "bars",
         "per_month": "columns", "per_year": "columns"}
ROW_CAP = {"bars": 8, "columns": 12}
UNITS = ("count", "percent")
LANGS = ("en", "es")
PARTS = ("long", "shorts", "unknown")   # the fixed order from the baseline
DEFAULT_LEGEND = {"en": {"long": "Long videos", "shorts": "Shorts", "unknown": "Length unknown"},
                  "es": {"long": "Largos", "shorts": "Shorts", "unknown": "Sin duración"}}
WHOLE_BY_DEFAULT = ("by_area", "by_theme", "by_channel")
LINK_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be",
                        "instagram.com", "www.instagram.com", "m.instagram.com"})
SPEC_KEYS = frozenset({"kind", "caption", "unit", "lang", "whole", "legend", "series", "rows"})
ROW_KEYS = frozenset({"label", "value", "parts", "href", "note", "series", "group", "unit"})
TEXT_MAX = 200          # characters in a label, caption, note or legend word
HREF_MAX = 500
SHARE_SAYS_NOTHING = 90  # a share chart whose top row is this much or more says nothing a sentence does not
BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u061c")
JOINERS = frozenset("\u200c\u200d")   # the only invisible format characters a label may hold (emoji, Persian, Indic)
BLACK_FLAG = "\U0001f3f4"            # tag characters are allowed only in a flag sequence that starts with it
MAX_VALUE = 10 ** 9                  # a count this large is not a person's history; its text would crush the plot
# first path segments that act or send elsewhere: a link in a chart names a channel or a video, nothing else
LINK_REFUSED_SEGMENTS = frozenset({"redirect", "attribution_link", "logout", "signout", "signin", "login", "accounts",
                                   "oauth", "oauth2", "share", ".", ".."})

# the text chart (insight.py's look: 8 whole cells, a label cut at a word with "…")
TEXT_CELLS = 8
TEXT_LABEL_MAX = 18
TEXT_NOTE_MAX = 16
CELL = {"long": "█", "shorts": "▓", "unknown": "▒", None: "█"}
EMPTY_CELL = "░"

# colours by role (see the docstring for the checks they pass)
THEMES = {
    "light": {"surface": "#fcfcfb", "ring": "#e1e0d9", "ink": "#0b0b0b", "ink2": "#52514e", "base": "#c3c2b7",
              "long": "#2a78d6", "shorts": "#eb6834", "unknown": "#8f8d86", "one": "#2a78d6",
              "s0": "#2a78d6", "s1": "#86b6ef"},
    "dark": {"surface": "#1a1a19", "ring": "#2c2c2a", "ink": "#f0efec", "ink2": "#c3c2b7", "base": "#383835",
             "long": "#3987e5", "shorts": "#d95926", "unknown": "#74736c", "one": "#3987e5",
             "s0": "#3987e5", "s1": "#184f95"},
}
ROLES = ("surface", "ring", "ink", "ink2", "base", "long", "shorts", "unknown", "one", "s0", "s1")
FONT_STACK = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# layout, in logical px
DEFAULT_WIDTH = 300
MIN_WIDTH, MAX_WIDTH = 240, 800
PAD = 12
CARD_R = 12
CAP_SIZE, CAP_LH, CAP_LINES = 13, 17, 3
LEGEND_SIZE, LEGEND_LH, SWATCH = 11.5, 17, 9
LABEL_SIZE = 12
VALUE_SIZE = 12
ROW_PITCH, BAR_H = 24, 12
GROUP_GAP = 6
LABEL_SHARE = 0.42      # a label column takes at most this much of the inner width
COL_MAX_W = 24
COL_PLOT_H = 112
COL_VALUE_SIZE = 10.5
TICK_SIZE = 11
TICK_SIZE_SMALL = 10    # 12 months at phone width: "May" needs it, and a year of months stays a column chart
END_R = 4
GAP = 2
MIN_PART = 3        # px: the thinnest part drawn, so the gap never swallows one
EST_SAFETY = 1.06       # the width estimate errs wide: a label must never run into its bar

# em widths of a Helvetica-like sans, for cutting labels without a font (the PNG re-checks with its real font)
_EM = {" ": .278, "!": .278, '"': .355, "#": .556, "$": .556, "%": .889, "&": .667, "'": .191, "(": .333, ")": .333,
       "*": .389, "+": .584, ",": .278, "-": .333, ".": .278, "/": .278, ":": .278, ";": .278, "<": .584, "=": .584,
       ">": .584, "?": .556, "@": 1.015, "[": .278, "\\": .278, "]": .278, "^": .469, "_": .556, "`": .333,
       "{": .334, "|": .26, "}": .334, "~": .584, "…": 1.0, "·": .278, "–": .556, "—": 1.0, "’": .222, "‘": .222,
       "“": .333, "”": .333}
_EM.update({d: .556 for d in "0123456789"})
_EM.update(dict(zip("abcdefghijklmnopqrstuvwxyz",
                    (.556, .556, .5, .556, .556, .278, .556, .556, .222, .222, .5, .222, .833, .556, .556, .556, .556,
                     .333, .5, .278, .556, .5, .722, .5, .5, .5))))
_EM.update(dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                    (.667, .667, .722, .722, .667, .611, .778, .722, .278, .5, .667, .556, .833, .722, .778, .667,
                     .778, .722, .667, .611, .722, .667, .944, .667, .667, .611))))


# ====================================== small helpers ===========================================================
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v):
    """A real, finite number. An int too big for a float is not one (math.isfinite would raise on it)."""
    if not _num(v):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def _drawable(v):
    """A finite number from 0 up to MAX_VALUE."""
    return _finite(v) and 0 <= v < MAX_VALUE


def _bad_text(s):
    """True when a piece of third-party text holds a character a chart must not draw: a control character (a
    newline, a tab), a line or paragraph separator, a bidi override or isolate, a lone surrogate, a noncharacter, or
    an invisible format character (a zero-width space, a direction mark, a soft hyphen, a byte-order mark, tag
    characters that can smuggle hidden words). Allowed: the zero-width joiner and non-joiner, and tag characters inside
    a flag sequence (black flag, tags)."""
    flag = False
    for c in s:
        cp = ord(c)
        cat = unicodedata.category(c)
        if 0xE0020 <= cp <= 0xE007F and flag:   # a subdivision flag: black flag, tag letters, cancel tag
            flag = cp != 0xE007F
            continue
        flag = c == BLACK_FLAG
        if cat in ("Cc", "Cs", "Zl", "Zp") or c in BIDI_CONTROLS:
            return True
        if cat == "Cf" and c not in JOINERS:
            return True
        if 0xFDD0 <= cp <= 0xFDEF or (cp & 0xFFFE) == 0xFFFE:
            return True
    return False


def href_ok(h):
    """True for an https link on youtube.com, youtu.be or instagram.com (and their www and m hosts), with no user,
    no port, and only plain printable ASCII (no quotes, no angle brackets, no spaces)."""
    if not isinstance(h, str) or not h or len(h) > HREF_MAX:
        return False
    if any(ord(c) < 0x21 or ord(c) > 0x7E for c in h) or any(c in h for c in "\"'<>\\`{}|^"):
        return False
    try:
        u = urlsplit(h)
        port = u.port
    except ValueError:
        return False
    if u.scheme != "https" or port is not None or u.username is not None or u.password is not None:
        return False
    host = (u.hostname or "").lower()
    if not (host and u.netloc.lower() == host and host in LINK_HOSTS):
        return False
    segs = [x.lower() for x in u.path.split("/")]
    if any(x in LINK_REFUSED_SEGMENTS for x in segs) or "//" in u.path:
        return False   # a redirect, an account action, or a path that climbs out of itself
    rest = unquote(unquote(u.query + "#" + u.fragment)).lower()
    return "//" not in rest and "http:" not in rest and "https:" not in rest   # no address inside the address


def _form(spec):
    k = spec.get("kind")
    return KINDS.get(k) if isinstance(k, str) else None


def _whole(spec):
    w = spec.get("whole")
    return bool(w) if isinstance(w, bool) else spec.get("kind") in WHOLE_BY_DEFAULT


def fmt_value(v, unit, lang="en"):
    """A value as the chart prints it: "1,094" ("1.094" in Spanish) for a count, "42%" for a percent (rounded the
    way insight.py rounds a share)."""
    if unit == "percent":
        return f"{round(v)}%"
    s = f"{int(v):,}"
    return s.replace(",", ".") if lang == "es" else s


def _legend_words(spec):
    lang = spec.get("lang") if spec.get("lang") in LANGS else "en"
    words = dict(DEFAULT_LEGEND[lang])
    for k, v in (spec.get("legend") or {}).items():
        if k in PARTS and isinstance(v, str) and v.strip():
            words[k] = " ".join(v.split())
    return words


def _parts_used(spec):
    """The parts that any row has above zero, in the fixed order; () when the chart is not split."""
    rows = spec.get("rows") or []
    if not rows or not all(isinstance(r, dict) and isinstance(r.get("parts"), dict) for r in rows):
        return ()
    return tuple(p for p in PARTS if any(_finite(r["parts"].get(p)) and r["parts"].get(p) > 0 for r in rows))


# ====================================== validate =================================================================
def validate(spec):
    """The reasons a spec cannot be drawn, in plain words; an empty list means it can."""
    if not isinstance(spec, dict):
        return ["the spec is not a dict"]
    why = []
    extra = sorted(set(spec) - SPEC_KEYS)
    if extra:
        why.append(f"unknown chart fields: {', '.join(map(str, extra))}")
    form = _form(spec)
    if form is None:
        why.append(f"unknown kind {spec.get('kind')!r} (one of {', '.join(KINDS)})")
    unit = spec.get("unit")
    if unit not in UNITS:
        why.append(f"unknown unit {unit!r} (count or percent)")
    if spec.get("lang", "en") not in LANGS:
        why.append(f"unknown language {spec.get('lang')!r} (en or es)")
    if "whole" in spec and not isinstance(spec["whole"], bool):
        why.append("whole is not true or false")
    cap = spec.get("caption")
    if not isinstance(cap, str) or not cap.strip():
        why.append("no caption (what is counted, and of what)")
    elif _bad_text(cap):
        why.append("the caption holds a control character")
    elif len(cap) > TEXT_MAX:
        why.append(f"the caption is longer than {TEXT_MAX} characters")
    legend = spec.get("legend")
    if legend is not None:
        if not isinstance(legend, dict) or set(legend) - set(PARTS):
            why.append("the legend names something that is not a part (shorts, long, unknown)")
        elif any(not isinstance(v, str) or not v.strip() or _bad_text(v) or len(v) > TEXT_MAX
                 for v in legend.values()):
            why.append("a legend word is empty, too long or holds a control character")
    series = spec.get("series")
    if series is not None:
        if not isinstance(series, list) or not 1 <= len(series) <= 2 or any(
                not isinstance(s, str) or not s.strip() or _bad_text(s) or len(s) > TEXT_MAX for s in series):
            why.append("series is not a list of one or two plain names")
            series = None
    rows = spec.get("rows")
    if not isinstance(rows, list):
        return why + ["no rows"]
    if len(rows) < 2:
        why.append("fewer than 2 rows: one number is a sentence, not a chart")
    if form and len(rows) > ROW_CAP[form]:
        why.append(f"{len(rows)} rows: at most {ROW_CAP[form]} fit a {form} chart")
    split = [isinstance(r, dict) and r.get("parts") is not None for r in rows]
    if any(split) and not all(split):
        why.append("some rows are split into parts and some are not: every row or none")
    if any(split) and series is not None:
        why.append("two measures in one chart: parts and series together")
    values = []
    for i, r in enumerate(rows):
        n = f"row {i + 1}"
        if not isinstance(r, dict):
            why.append(f"{n} is not a dict")
            continue
        extra = sorted(set(r) - ROW_KEYS)
        if extra:
            why.append(f"{n}: unknown fields: {', '.join(map(str, extra))}")
        lab = r.get("label")
        if not isinstance(lab, str) or not lab.strip():
            why.append(f"{n}: no label")
        elif _bad_text(lab):
            why.append(f"{n}: the label holds a control character")
        elif len(lab) > TEXT_MAX:
            why.append(f"{n}: the label is longer than {TEXT_MAX} characters")
        v = r.get("value")
        if _num(v) and (isinstance(v, int) or _finite(v)) and v >= MAX_VALUE:
            why.append(f"{n}: the value is too large to draw (a billion or more)")
            v = None
        elif not _finite(v):
            why.append(f"{n}: the value is not a finite number")
            v = None
        elif v < 0:
            why.append(f"{n}: the value is negative")
            v = None
        elif unit == "count" and v != int(v):
            why.append(f"{n}: a count that is not a whole number")
        if v is not None:
            values.append(v)
        if "unit" in r and r["unit"] != unit:
            why.append(f"two measures in one chart: {n} is in {r['unit']!r}, the chart in {unit!r}")
        parts = r.get("parts")
        if parts is not None:
            if not isinstance(parts, dict) or not parts:
                why.append(f"{n}: parts is not a dict of shorts, long, unknown")
            elif set(parts) - set(PARTS):
                why.append(f"two measures in one chart: {n} has parts that are not shorts, long or unknown: "
                           f"{', '.join(sorted(map(str, set(parts) - set(PARTS))))}")
            elif not all(_drawable(x) for x in parts.values()):
                why.append(f"{n}: a part is not a finite number at zero or above (and under a billion)")
            elif unit == "count" and any(x != int(x) for x in parts.values()):
                why.append(f"{n}: a part that is not a whole number")
            elif v is not None:
                s = sum(parts.values())
                tol = 1e-9 if unit == "count" else 0.5 * (len(parts) + 1) + 1e-9
                if abs(s - v) > tol:
                    why.append(f"{n}: the parts add up to {s:g}, not to the value {v:g}")
        if "href" in r and r["href"] is not None and not href_ok(r["href"]):
            why.append(f"{n}: the link is not https on youtube.com, youtu.be or instagram.com")
        note = r.get("note")
        if note is not None and (not isinstance(note, str) or _bad_text(note) or len(note) > TEXT_MAX):
            why.append(f"{n}: the note is not plain text")
        grp = r.get("group")
        if grp is not None and (not isinstance(grp, str) or _bad_text(grp) or len(grp) > TEXT_MAX):
            why.append(f"{n}: the group is not plain text")
        if "series" in r:
            if series is None:
                why.append(f"{n}: a series index with no series names")
            elif not isinstance(r["series"], int) or isinstance(r["series"], bool) or \
                    not 0 <= r["series"] < len(series):
                why.append(f"{n}: the series index is not one of the series")
    if series is not None and not all(isinstance(r, dict) and "series" in r for r in rows):
        why.append("series names given but not every row says its series")
    if unit == "percent" and values:
        if _whole(spec):
            if sum(values) > 100 + 0.5 * len(values) + 1e-9:
                why.append(f"the shares add up to {sum(values):g}%, over 100% of one whole")
            if max(values) >= SHARE_SAYS_NOTHING:
                why.append(f"the top row is {max(values):g}% of the whole: the chart says nothing a sentence does not")
        elif max(values) > 100 + 0.5:
            why.append(f"a share over 100%: {max(values):g}%")
    if values and len(values) == len(rows) and all(
            fmt_value(v, unit if unit in UNITS else "count", "en") in ("0", "0%") for v in values):
        why.append("every row rounds to 0: the chart says nothing")
    return why


# ====================================== text: clusters, widths, cuts ============================================
def _is_emoji_cp(cp):
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF or cp in (0x00A9, 0x00AE)
            or 0x1F1E6 <= cp <= 0x1F1FF)


def _clusters(s):
    """Grapheme-like clusters: a character with its combining marks, variation selectors, skin tones, tags and
    zero-width-joined followers, and a regional-indicator pair. A cut never splits one."""
    out = []
    for ch in s:
        cp = ord(ch)
        joins = out and (unicodedata.category(ch) in ("Mn", "Me") or cp in (0xFE0E, 0xFE0F, 0x200D)
                         or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F or out[-1].endswith("\u200d"))
        pair = (out and 0x1F1E6 <= cp <= 0x1F1FF and len(out[-1]) == 1 and 0x1F1E6 <= ord(out[-1]) <= 0x1F1FF)
        if joins or pair:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _is_emoji(cl):
    return any(_is_emoji_cp(ord(c)) for c in cl) or "\ufe0f" in cl


def _cw(cl):
    """One cluster's width in em."""
    if _is_emoji(cl):
        return 1.25
    ch = cl[0]
    if ch in _EM:
        return _EM[ch]
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    if unicodedata.category(ch).startswith("M") or ch in "\u200b\u200c\u200d\u200e\u200f":
        return 0.0
    return 0.62


def est(s, size):
    """An estimate of a string's width in px at a font size: errs wide."""
    return sum(_cw(c) for c in _clusters(s)) * size * EST_SAFETY


def _rtl(s):
    """True when the first strong character reads right to left."""
    for c in s:
        b = unicodedata.bidirectional(c)
        if b in ("R", "AL"):
            return True
        if b == "L":
            return False
    return False


def cut(s, maxw, size, measure=None):
    """`s` on one line no wider than `maxw`: whole, or cut with "…" at a word where that keeps most of it, else at a
    cluster. `measure(str) -> px` defaults to the estimate."""
    m = measure or (lambda x: est(x, size))
    s = " ".join(str(s).split())
    if m(s) <= maxw:
        return s
    cls = _clusters(s)
    lo, hi = 0, len(cls)
    while lo < hi:   # the most clusters that fit beside the ellipsis
        mid = (lo + hi + 1) // 2
        if m("".join(cls[:mid]).rstrip() + "…") <= maxw:
            lo = mid
        else:
            hi = mid - 1
    head = "".join(cls[:lo])
    if lo < len(cls) and cls[lo] != " " and " " in head.strip():   # at a word, never inside one (insight.py's
        head = head.rstrip().rsplit(" ", 1)[0]                     # rule since round 12's fix)
    head = head.rstrip(" ,;:-·–—")
    return head + "…" if head else "…"


def _cut_chars(s, n):
    """insight.py's label cut: at most n characters, at a word, with "…"."""
    s = " ".join(str(s or "").split())
    if len(s) <= n:
        return s
    c = s[:n - 1]
    if s[n - 1] != " " and " " in c:
        c = c.rsplit(" ", 1)[0]
    return c.rstrip(" ,;:-") + "…"


def _wrap(s, maxw, size, lines):
    """Words onto at most `lines` lines no wider than `maxw`; the last cut with "…" if the words run over."""
    words = " ".join(s.split()).split(" ")
    out, cur = [], ""
    for i, w in enumerate(words):
        nxt = (cur + " " + w).strip()
        if est(nxt, size) <= maxw or not cur:
            cur = nxt
            continue
        out.append(cur)
        cur = w
        if len(out) == lines - 1:
            cur = " ".join([w] + words[i + 1:])
            break
    out.append(cut(cur, maxw, size))
    out = [x for x in out if x]
    if len(out) == 2 and not out[1].endswith("…"):   # two lines of even length, not one long and a lone word
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wa, wb = est(a, size), est(b, size)
            if wa <= maxw and wb <= maxw and (best is None or max(wa, wb) < best[0]):
                best = (max(wa, wb), [a, b])
        if best:
            out = best[1]
    return [cut(x, maxw, size) for x in out]   # a single word wider than a line is cut too, never run off the card


# ====================================== layout (one geometry for the SVG and the PNG) ============================
def _width(width):
    if not _finite(width):
        return DEFAULT_WIDTH
    return int(max(MIN_WIDTH, min(MAX_WIDTH, round(width))))


def _row_parts(r, parts_used):
    """[(part, value)] of a row in the fixed order, or [(None, value)] for a row that is not split."""
    if not parts_used:
        return [(None, r["value"])]
    return [(p, r["parts"].get(p, 0)) for p in parts_used if (r["parts"].get(p) or 0) > 0]


def _segs(spec, r, parts_used, length):
    """The bar's segments, [{part, role, off, len}], their lengths in proportion to the parts and adding up to
    `length` exactly: the bar is as long as its value whatever the parts add up to (percent parts may differ from the
    value by rounding), so the SVG and the PNG never draw past the value."""
    pv = _row_parts(r, parts_used)
    tot = sum(v for _, v in pv)
    segs, off = [], 0.0
    for part, v in pv:
        ln = length * v / tot if tot > 0 else 0.0
        segs.append({"part": part, "role": _role(spec, r, part), "off": off, "len": ln})
        off += ln
    return segs


def _gaps(segs):
    """True when the bar is long enough for a 2 px surface gap between its parts; a shorter bar is drawn without gaps
    (they would swallow it: 3 videos beside 2,400 were drawn as nothing)."""
    return len(segs) >= 2 and sum(s["len"] for s in segs) >= MIN_PART * len(segs) * 2


def _visible_parts(segs):
    """A part above zero but thinner than MIN_PART px is drawn MIN_PART px (the 2 px gap would swallow it), the
    largest part giving up the difference: the bar's whole length stays exact and a few videos of unknown length
    stay visible beside the rest. Offsets are recomputed in order. A bar too short for gaps is left as it is."""
    if not _gaps(segs):
        return segs
    small = [s for s in segs if 0 < s["len"] < MIN_PART]
    if small:
        big = max(segs, key=lambda s: s["len"])
        for s in small:
            big["len"] -= MIN_PART - s["len"]
            s["len"] = MIN_PART
    off = 0.0
    for s in segs:
        s["off"] = off
        off += s["len"]
    return segs


def _role(spec, r, part):
    if part:
        return part
    if spec.get("series") is not None:
        return f"s{r.get('series', 0)}"
    return "one"


def _legend_items(spec):
    used = _parts_used(spec)
    if used:
        words = _legend_words(spec)
        return [(p, words[p]) for p in used]
    if spec.get("series") is not None:
        return [(f"s{i}", " ".join(s.split())) for i, s in enumerate(spec["series"])]
    return []


def _columns_fit(spec, inner):
    """The period labels' font size when every value and period fits its column's slot, else None (the chart turns
    sideways). The periods drop to TICK_SIZE_SMALL before giving up."""
    rows = spec["rows"]
    slot = inner / len(rows)
    lang = spec.get("lang", "en")
    if any(r.get("note") for r in rows):
        return None
    if any(est(fmt_value(r["value"], spec["unit"], lang), COL_VALUE_SIZE) > slot - 2 for r in rows):
        return None
    for size in (TICK_SIZE, TICK_SIZE_SMALL):
        if all(est(" ".join(r["label"].split()), size) <= slot - 2 for r in rows):
            return size
    return None


def layout(spec, width=DEFAULT_WIDTH):
    """The chart's geometry, theme-free: {"w", "h", "form", "ops"}. Ops are text, bar, line and swatch, in logical
    px; the SVG writes them and the PNG paints them, so the two show the same numbers and the same lengths."""
    W = _width(width)
    inner = W - 2 * PAD
    lang = spec.get("lang", "en")
    unit = spec["unit"]
    rows = spec["rows"]
    ops = []
    y = PAD
    for ln in _wrap(spec["caption"], inner, CAP_SIZE, CAP_LINES):
        y += CAP_LH
        ops.append({"op": "text", "x": PAD, "y": y - 4, "s": ln, "size": CAP_SIZE, "role": "ink2",
                    "anchor": "start", "cls": "cap"})
    y += 6
    items = _legend_items(spec)
    if items:
        widths = [SWATCH + 5 + est(t, LEGEND_SIZE) for _, t in items]
        one_line = sum(widths) + 12 * (len(items) - 1) <= inner
        x = PAD
        for (role, t), w in zip(items, widths):
            if not one_line:
                t = cut(t, inner - SWATCH - 5, LEGEND_SIZE)
            ops.append({"op": "swatch", "x": x, "y": y + (LEGEND_LH - SWATCH) / 2 - 1, "w": SWATCH, "h": SWATCH,
                        "role": role})
            ops.append({"op": "text", "x": x + SWATCH + 5, "y": y + LEGEND_LH - 5, "s": t, "size": LEGEND_SIZE,
                        "role": "ink2", "anchor": "start", "cls": "leg"})
            if one_line:
                x += w + 12
            else:
                y += LEGEND_LH
        if one_line:
            y += LEGEND_LH
        y += 6
    parts_used = _parts_used(spec)
    top = max(r["value"] for r in rows) or 1
    form = _form(spec)
    tick = _columns_fit(spec, inner) if form == "columns" else None
    if tick:
        form = "columns"
        slot = inner / len(rows)
        cw = min(COL_MAX_W, slot * 0.62)
        base = y + COL_VALUE_SIZE + 6 + COL_PLOT_H
        for i, r in enumerate(rows):
            cx = PAD + slot * (i + 0.5)
            h = r["value"] / top * COL_PLOT_H
            if r["value"] > 0:
                h = max(h, 1.0)   # a value too small to see is drawn 1 px tall
            segs = _visible_parts(_segs(spec, r, parts_used, h))
            ops.append({"op": "bar", "dir": "v", "x": cx - cw / 2, "y": base, "w": cw, "h": h, "segs": segs,
                        "row": i, "gaps": _gaps(segs)})
            ops.append({"op": "text", "x": cx, "y": base - h - 4, "s": fmt_value(r["value"], unit, lang),
                        "size": COL_VALUE_SIZE, "role": "ink", "anchor": "middle", "cls": "val"})
            ops.append({"op": "text", "x": cx, "y": base + TICK_SIZE + 4, "s": " ".join(r["label"].split()),
                        "size": tick, "role": "ink2", "anchor": "middle", "cls": "lab", "href": r.get("href"),
                        "rtl": _rtl(r["label"])})
        ops.append({"op": "line", "x1": PAD, "y1": base, "x2": PAD + inner, "y2": base, "role": "base"})
        y = base + TICK_SIZE + 8
    else:
        labels = [" ".join(r["label"].split()) for r in rows]
        vals = [fmt_value(r["value"], unit, lang) for r in rows]
        vw = max(est(v, VALUE_SIZE) for v in vals) + 6
        notes = [" ".join(r["note"].split()) if r.get("note") else "" for r in rows]
        side = max(est(t, LABEL_SIZE) for t in labels) <= inner * LABEL_SHARE and not any(notes)
        form = "bars" if side else "bars_stacked"
        if side:   # short labels: a label column beside the bars, one line per row
            lw = max(est(t, LABEL_SIZE) for t in labels)
            x0 = PAD + lw + 8
            pitch = ROW_PITCH
        else:      # a long label or a note: the name on its own line, the bar under it at full width
            lw = inner
            x0 = PAD
            pitch = ROW_PITCH + LABEL_SIZE + 4
        plot = inner - (x0 - PAD) - vw
        ops_rows = []
        yy = y
        for i, r in enumerate(rows):
            if i and r.get("group") is not None and r.get("group") != rows[i - 1].get("group"):
                yy += GROUP_GAP
            if side:
                by = yy + (ROW_PITCH - BAR_H) / 2
                ly = mid = yy + ROW_PITCH / 2 + LABEL_SIZE * 0.35
            else:
                ly = yy + LABEL_SIZE + 1
                by = yy + LABEL_SIZE + 6
                mid = by + BAR_H / 2 + VALUE_SIZE * 0.35
            w = r["value"] / top * plot
            if r["value"] > 0:
                w = max(w, 1.0)
            segs = _visible_parts(_segs(spec, r, parts_used, w))
            rtl = _rtl(labels[i])
            room = lw if not notes[i] else inner * 0.6
            lab = cut(labels[i], room, LABEL_SIZE)
            # maxw is the room the PNG's real font may use before it cuts again: beside the bars that is the label
            # column and most of the 8 px before the baseline, since the estimate is only an estimate
            ops_rows.append({"op": "text", "x": PAD + lw if rtl else PAD, "y": ly, "s": lab, "size": LABEL_SIZE,
                             "role": "ink", "anchor": "end" if rtl else "start", "cls": "lab", "href": r.get("href"),
                             "rtl": rtl, "maxw": room + (6 if side and not rtl else 0)})
            if notes[i]:   # after the name, in secondary ink (the estimate errs wide, so they never touch)
                nx = PAD + (0 if rtl else est(lab, LABEL_SIZE) + 6)
                nroom = inner - (nx - PAD) - (est(lab, LABEL_SIZE) + 6 if rtl else 0)
                ns = cut("· " + notes[i], nroom, LABEL_SIZE)
                if ns.strip("·… "):   # a note cut down to "…" says nothing: it is left out
                    ops_rows.append({"op": "text", "x": nx, "y": ly, "s": ns, "size": LABEL_SIZE, "role": "ink2",
                                     "anchor": "start", "cls": "note", "rtl": False, "maxw": nroom})
            ops_rows.append({"op": "bar", "dir": "h", "x": x0, "y": by, "w": w, "h": BAR_H, "segs": segs, "row": i,
                             "gaps": _gaps(segs)})
            ops_rows.append({"op": "text", "x": x0 + w + 5, "y": mid, "s": vals[i], "size": VALUE_SIZE, "role": "ink",
                             "anchor": "start", "cls": "val"})
            yy += pitch
        if side:
            ops.append({"op": "line", "x1": x0, "y1": y, "x2": x0, "y2": yy, "role": "base"})
        ops += ops_rows
        y = yy
    return {"w": W, "h": int(math.ceil(y + PAD)), "form": form, "ops": ops, "top": top}


# ====================================== SVG ======================================================================
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("'", "&#39;"))


def _n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _css(theme, sid):
    def rules(t):
        c = THEMES[t]
        return "".join(f"#{sid} .c-{r}{{fill:{c[r]}}}" for r in ROLES) + \
            f"#{sid} .k-base{{stroke:{c['base']}}}#{sid} .k-ring{{stroke:{c['ring']}}}" \
            f"#{sid} .k-gap{{fill:{c['surface']}}}"
    common = (f"#{sid} text{{font-family:{FONT_STACK};}}#{sid} .val{{font-variant-numeric:tabular-nums}}"
              f"#{sid} a text{{text-decoration:underline}}")
    if theme == "auto":
        return common + rules("light") + "@media (prefers-color-scheme: dark){" + rules("dark") + "}"
    return common + rules(theme)


def _spec_id(spec, theme, width):
    h = hashlib.sha1(json.dumps([spec, theme, width], sort_keys=True, ensure_ascii=True, default=str)
                     .encode()).hexdigest()
    return "sdc" + h[:10]


def _desc(spec):
    """The accessible description: the text chart's content in sentences, every number, full labels."""
    lang = spec.get("lang", "en")
    words = _legend_words(spec)
    used = _parts_used(spec)
    lines = []
    for r in spec["rows"]:
        s = f"{' '.join(r['label'].split())}: {fmt_value(r['value'], spec['unit'], lang)}"
        if used:
            s += " (" + ", ".join(f"{words[p]} {fmt_value(r['parts'].get(p, 0), spec['unit'], lang)}"
                                  for p in used) + ")"
        if spec.get("series") is not None:
            s += f" [{spec['series'][r['series']]}]"
        if r.get("note"):
            s += f", {' '.join(r['note'].split())}"
        lines.append(s)
    return "; ".join(lines) + "."


def svg(spec, theme="light", width=DEFAULT_WIDTH):
    """A self-contained SVG of the chart, or None for a spec validate() refuses. theme: light, dark or auto."""
    if validate(spec) or theme not in ("light", "dark", "auto"):
        return None
    W = _width(width)
    L = layout(spec, W)
    sid = _spec_id(spec, theme, W)
    H = L["h"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" id="{sid}" '
           f'width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-labelledby="{sid}-t {sid}-d">',
           f'<title id="{sid}-t">{_esc(" ".join(spec["caption"].split()))}</title>',
           f'<desc id="{sid}-d">{_esc(_desc(spec))}</desc>',
           f"<style>{_css(theme, sid)}</style>",
           f'<rect class="c-surface k-ring" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="{CARD_R}" '
           f'stroke-width="1"/>']
    k = 0
    for op in L["ops"]:
        t = op["op"]
        if t == "text":
            attrs = (f'x="{_n(op["x"])}" y="{_n(op["y"])}" font-size="{_n(op["size"])}" '
                     f'class="c-{op["role"]} {op["cls"]}"')
            anchor = op["anchor"]   # the layout's anchors are physical (left, middle, right of x)
            if op.get("rtl"):       # in a right-to-left text "start" is its right edge
                attrs += ' direction="rtl"'
                anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
            if anchor != "start":
                attrs += f' text-anchor="{anchor}"'
            el = f"<text {attrs}>{_esc(op['s'])}</text>"
            if op.get("href"):
                h = _esc(op["href"])
                el = f'<a href="{h}" xlink:href="{h}" target="_blank" rel="noopener noreferrer">{el}</a>'
            out.append(el)
        elif t == "line":
            out.append(f'<line class="k-{op["role"]}" x1="{_n(op["x1"])}" y1="{_n(op["y1"])}" x2="{_n(op["x2"])}" '
                       f'y2="{_n(op["y2"])}" stroke-width="1"/>')
        elif t == "swatch":
            out.append(f'<rect class="c-{op["role"]}" x="{_n(op["x"])}" y="{_n(op["y"])}" width="{_n(op["w"])}" '
                       f'height="{_n(op["h"])}" rx="2"/>')
        elif t == "bar":
            if op["w"] <= 0 or op["h"] <= 0:
                continue
            cid = f"{sid}-c{k}"
            k += 1
            r = min(END_R, (op["h"] if op["dir"] == "h" else op["w"]) / 2)
            if op["dir"] == "h":
                clip = (f'<rect x="{_n(op["x"] - r)}" y="{_n(op["y"])}" width="{_n(op["w"] + r)}" '
                        f'height="{_n(op["h"])}" rx="{_n(r)}"/>')
            else:
                clip = (f'<rect x="{_n(op["x"])}" y="{_n(op["y"] - op["h"])}" width="{_n(op["w"])}" '
                        f'height="{_n(op["h"] + r)}" rx="{_n(r)}"/>')
            out.append(f'<clipPath id="{cid}">{clip}</clipPath>')
            g = [f'<g clip-path="url(#{cid})" data-row="{op["row"]}">']
            for i, s in enumerate(op["segs"]):
                if s["len"] <= 0:
                    continue
                part = f' data-part="{s["part"]}"' if s["part"] else ""
                if op["dir"] == "h":
                    g.append(f'<rect class="c-{s["role"]} seg"{part} x="{_n(op["x"] + s["off"])}" '
                             f'y="{_n(op["y"])}" width="{_n(s["len"])}" height="{_n(op["h"])}"/>')
                else:
                    g.append(f'<rect class="c-{s["role"]} seg"{part} x="{_n(op["x"])}" '
                             f'y="{_n(op["y"] - s["off"] - s["len"])}" width="{_n(op["w"])}" '
                             f'height="{_n(s["len"])}"/>')
            for s in (op["segs"][1:] if op.get("gaps") else []):   # the 2 px surface gap, centred on each inner
                if op["dir"] == "h":                                      # boundary
                    g.append(f'<rect class="k-gap" x="{_n(op["x"] + s["off"] - GAP / 2)}" y="{_n(op["y"])}" '
                             f'width="{GAP}" height="{_n(op["h"])}"/>')
                else:
                    g.append(f'<rect class="k-gap" x="{_n(op["x"])}" y="{_n(op["y"] - s["off"] - GAP / 2)}" '
                             f'width="{_n(op["w"])}" height="{GAP}"/>')
            out.append("".join(g) + "</g>")
    out.append("</svg>")
    return "\n".join(out)   # no trailing newline: a pre-wrap bubble would draw it as an empty line


# ====================================== PNG (Pillow) =============================================================
REGULAR_FONTS = (
    "/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/freefont/FreeSans.ttf")
FALLBACK_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/ArialHB.ttc", "/System/Library/Fonts/GeezaPro.ttc",
    "C:/Windows/Fonts/seguisym.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")
EMOJI_FONTS = ("/System/Library/Fonts/Apple Color Emoji.ttc", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
               "C:/Windows/Fonts/seguiemj.ttf")
EMOJI_SIZES = (109, 160, 96, 64, 48, 40, 32, 20)   # colour bitmap fonts load only at their own strike sizes
SUPERSAMPLE = 2
SHRINK_MIN = 0.9   # the PNG draws a label up to 10% smaller rather than cut it ("Gaming 2026" and "Gaming 2025" were
                   # both drawn "Gaming…" when the real font was 0.3% wider than the estimate)


class _Fonts:
    """The fonts of one PNG: loaded once per call (no global state), with a glyph check per character."""

    def __init__(self, ImageFont, ss, raqm):
        self.IF = ImageFont
        self.ss = ss
        # without libraqm the labels are put in visual order here, so Pillow must not reorder them again
        self.engine = ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC
        env = os.environ.get("MVP_CHART_FONT")
        self.main = next((p for p in ((env,) if env else ()) + REGULAR_FONTS if p and os.path.isfile(p)), None)
        self.fallbacks = [p for p in FALLBACK_FONTS if os.path.isfile(p) and p != self.main]
        self.emoji_path = next((p for p in EMOJI_FONTS if os.path.isfile(p)), None)
        self._cache, self._has, self._emoji = {}, {}, None

    def get(self, path, size):
        key = (path, round(size * self.ss))
        if key not in self._cache:
            try:
                self._cache[key] = self.IF.truetype(path, key[1], layout_engine=self.engine) if path else \
                    self.IF.load_default(key[1])
            except Exception:
                self._cache[key] = self.IF.load_default(key[1])
        return self._cache[key]

    def has(self, path, ch):
        """True when the font at `path` draws `ch` as something other than its missing-glyph box."""
        key = (path, ch)
        if key not in self._has:
            f = self.get(path, 12)
            try:
                a = f.getmask(ch)
                b = f.getmask("\U0010fffd")
                self._has[key] = not (a.size == b.size and bytes(a) == bytes(b)) and (a.getbbox() is not None
                                                                                       or ch.isspace())
            except Exception:
                self._has[key] = False
        return self._has[key]

    def pick(self, cl):
        """The font path for a cluster ("" for Pillow's own font), "emoji", or None when nothing draws it."""
        if _is_emoji(cl):
            if self.emoji() is not None:
                return "emoji"
            return None
        ch = cl[0]
        if ch in "\u200d\u200c\u200e\u200f\ufe0f\ufe0e":
            return None
        for p in ([self.main] if self.main else []) + self.fallbacks:
            if self.has(p, ch):
                return p
        return "" if ord(ch) < 0x250 else None

    def cover(self, run):
        """The first font that draws every character of `run` (no emoji), or None."""
        cls = _clusters(run)
        if any(_is_emoji(c) for c in cls):
            return None
        for p in ([self.main] if self.main else []) + self.fallbacks:
            if all(c[0].isspace() or self.has(p, c[0]) for c in cls):
                return p
        return None

    def emoji(self):
        if self._emoji is None and self.emoji_path:
            for s in EMOJI_SIZES:
                try:
                    self._emoji = (self.IF.truetype(self.emoji_path, s), s)
                    break
                except Exception:
                    continue
            if self._emoji is None:
                self.emoji_path = None
        return self._emoji[0] if self._emoji else None


def _visual_runs(s, raqm):
    """[(text, rtl)] in visual order, left to right. With libraqm Pillow reorders a right-to-left string itself, so
    a label is one run; without it, a small reordering: runs of one direction (digits and neutrals stay with their
    neighbours), right-to-left runs reversed by cluster, and in a right-to-left label the runs right to left."""
    base_rtl = _rtl(s)
    if raqm:
        return [(s, base_rtl)]
    runs = []
    for cl in _clusters(s):
        b = unicodedata.bidirectional(cl[0])
        d = True if b in ("R", "AL") else False if b in ("L", "EN", "AN") else None
        if d is None and runs:
            d = runs[-1][1]
        if d is None:
            d = base_rtl
        if runs and runs[-1][1] == d:
            runs[-1][0].append(cl)
        else:
            runs.append(([cl], d))
    out = []
    for cls, d in runs:
        if d:
            cls = cls[::-1]
        out.append(("".join(cls), d))
    return out[::-1] if base_rtl else out


def _png_text(img, draw, fonts, op, color, ss, raqm):
    """Draws one text op: runs by font (per-character fallback, emoji as pictures), anchored like the SVG."""
    size = op["size"]
    pieces = []   # [(kind, text, font path or None, rtl)], left to right
    for run, rtl in _visual_runs(op["s"], raqm):
        whole = fonts.cover(run)
        if whole is not None:   # one font draws the whole run: one piece, laid out by Pillow as a whole
            pieces.append(("text", run, whole, rtl))
            continue
        mine = []
        for cl in _clusters(run):
            p = fonts.pick(cl)
            if p is None:
                continue
            if p == "emoji":
                mine.append(("emoji", cl, None, False))
            elif mine and mine[-1][0] == "text" and mine[-1][2] == p:
                mine[-1] = ("text", mine[-1][1] + cl, p, rtl)
            else:
                mine.append(("text", cl, p, rtl))
        pieces += mine[::-1] if (rtl and raqm) else mine   # a logical right-to-left run, drawn right to left

    def width(pcs):
        w = 0.0
        for kind, t, p, rtl in pcs:
            w += size * ss * 1.15 if kind == "emoji" else fonts.get(p, size).getlength(
                t, **({"direction": "rtl"} if (rtl and raqm) else {}))
        return w

    total = width(pieces)
    maxw = op.get("maxw")
    if maxw and total > maxw * ss and total * SHRINK_MIN <= maxw * ss:   # a hair wider than the estimate: a slightly
        return _png_text(img, draw, fonts, dict(op, size=size * maxw * ss / total * 0.995, maxw=None),  # smaller size
                         color, ss, raqm)                                                   # keeps the whole label
    if maxw and total > maxw * ss and op["s"] != "…":   # the real font is much wider than the estimate: cut again
        def m(x):
            return width([("text", x, fonts.main or "", False)]) / ss
        op = dict(op, s=cut(op["s"], maxw, size, measure=m), maxw=None)
        return _png_text(img, draw, fonts, op, color, ss, raqm)
    x = op["x"] * ss
    if op["anchor"] == "middle":
        x -= total / 2
    elif op["anchor"] == "end":
        x -= total
    y = op["y"] * ss
    for kind, t, p, rtl in pieces:
        if kind == "emoji":
            ef = fonts.emoji()
            try:
                bb = ef.getbbox(t, mode="RGBA")
                tile = _emoji_tile(t, ef, bb)
                side = int(round(size * ss * 1.1))
                tile = tile.resize((side, side), resample=1)
                img.paste(tile, (int(round(x)), int(round(y - side * 0.86))), tile)
            except Exception:
                pass
            x += size * ss * 1.15
            continue
        f = fonts.get(p, size)
        kw = {"direction": "rtl"} if (rtl and raqm) else {}
        draw.text((x, y), t, font=f, fill=color, anchor="ls", **kw)
        x += f.getlength(t, **kw)


def _emoji_tile(t, ef, bb):
    from PIL import Image, ImageDraw
    w, h = max(1, bb[2] - bb[0]), max(1, bb[3] - bb[1])
    side = max(w, h)
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(((side - w) / 2 - bb[0], (side - h) / 2 - bb[1]), t, font=ef, embedded_color=True)
    return tile


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _png(spec, theme, scale, width):
    from PIL import Image, ImageDraw, ImageFont, features
    raqm = bool(features.check("raqm"))
    W = _width(width)
    L = layout(spec, W)
    ss = scale * SUPERSAMPLE
    c = {k: _rgb(v) for k, v in THEMES[theme].items()}
    img = Image.new("RGB", (int(round(W * ss)), int(round(L["h"] * ss))), c["surface"])
    draw = ImageDraw.Draw(img)
    fonts = _Fonts(ImageFont, ss, raqm)

    def R(v):
        return int(round(v * ss))
    for op in L["ops"]:
        t = op["op"]
        if t == "line":
            x1, y1, x2, y2 = R(op["x1"]), R(op["y1"]), R(op["x2"]), R(op["y2"])
            lw = max(1, R(1))
            if x1 == x2:
                draw.rectangle([x1 - lw // 2, y1, x1 - lw // 2 + lw - 1, y2 - 1], fill=c[op["role"]])
            else:
                draw.rectangle([x1, y1 - lw // 2, x2 - 1, y1 - lw // 2 + lw - 1], fill=c[op["role"]])
        elif t == "swatch":
            draw.rounded_rectangle([R(op["x"]), R(op["y"]), R(op["x"] + op["w"]) - 1, R(op["y"] + op["h"]) - 1],
                                   radius=R(2), fill=c[op["role"]])
        elif t == "bar":
            if op["w"] <= 0 or op["h"] <= 0:
                continue
            segs = [s for s in op["segs"] if s["len"] > 0]
            for i, s in enumerate(segs):
                last = i == len(segs) - 1
                if op["dir"] == "h":
                    box = [R(op["x"] + s["off"]), R(op["y"]), R(op["x"] + s["off"] + s["len"]) - 1,
                           R(op["y"] + op["h"]) - 1]
                    corners = (False, True, True, False)
                else:
                    box = [R(op["x"]), R(op["y"] - s["off"] - s["len"]), R(op["x"] + op["w"]) - 1,
                           R(op["y"] - s["off"]) - 1]
                    corners = (True, True, False, False)
                if box[2] < box[0] or box[3] < box[1]:
                    continue
                r = min(R(END_R), (box[3] - box[1] + 1) // 2, (box[2] - box[0] + 1) // 2) if last else 0
                if r > 0:
                    draw.rounded_rectangle(box, radius=r, fill=c[s["role"]], corners=corners)
                else:
                    draw.rectangle(box, fill=c[s["role"]])
            for s in (segs[1:] if op.get("gaps") else []):
                if op["dir"] == "h":
                    gx = R(op["x"] + s["off"] - GAP / 2)
                    draw.rectangle([gx, R(op["y"]), gx + R(GAP) - 1, R(op["y"] + op["h"]) - 1], fill=c["surface"])
                else:
                    gy = R(op["y"] - s["off"] - GAP / 2)
                    draw.rectangle([R(op["x"]), gy, R(op["x"] + op["w"]) - 1, gy + R(GAP) - 1], fill=c["surface"])
        elif t == "text":
            _png_text(img, draw, fonts, op, c[op["role"]], ss, raqm)
    if SUPERSAMPLE != 1:
        img = img.resize((int(round(W * scale)), int(round(L["h"] * scale))), resample=Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)   # 9 took half the time for 2-3% fewer bytes
    return buf.getvalue()


def png(spec, theme="light", scale=2, width=DEFAULT_WIDTH):
    """PNG bytes of the chart for a text channel, or None: a spec validate() refuses, a theme that is not light or
    dark, Pillow missing, or any failure while drawing. None means the caller sends the text chart."""
    if validate(spec) or theme not in ("light", "dark") or not _finite(scale) or not 1 <= scale <= 4:
        return None
    try:
        import PIL  # noqa: F401
    except Exception:
        return None
    try:
        return _png(spec, theme, scale, width)
    except Exception:
        return None


# ====================================== text and describe ========================================================
def _cells(r, top, parts_used, cells=TEXT_CELLS):
    """A row's bar of whole cells, `cells` wide: insight.py's rounding (a value above 0 shows at least one cell); a
    split row's cells shared among its parts by largest remainder."""
    v = r["value"]
    if top <= 0:
        return EMPTY_CELL * cells
    n = int(round(max(0.0, min(1.0, v / top)) * cells))
    if v > 0 and n == 0:
        n = 1
    if not parts_used or v <= 0:
        return CELL[None] * n + EMPTY_CELL * (cells - n)
    ps = [(p, r["parts"].get(p, 0) or 0) for p in parts_used]
    tot = sum(x for _, x in ps) or 1
    raw = [(p, x / tot * n) for p, x in ps]
    k = [int(math.floor(x)) for _, x in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i][1] - k[i]), i))
    for i in order[:n - sum(k)]:
        k[i] += 1
    # A part whose share rounds to no cell gets none: one cell is an eighth of the widest bar, so lifting 1 video of
    # 46 to a cell would draw it as a fifth of its bar (tried in review and reverted). The picture shows it (MIN_PART) and the
    # SVG's desc and describe() carry its number.
    return "".join(CELL[p] * m for (p, _), m in zip(ps, k)) + EMPTY_CELL * (cells - n)


def text(spec):
    """The text chart: the caption, a legend line when the bars are split, then one line per row. Bars (by area,
    theme, channel, topic) print "bar value label", as insight.py's chart does; periods print "bar period value".
    None for a spec validate() refuses."""
    if validate(spec):
        return None
    lang = spec.get("lang", "en")
    rows = spec["rows"]
    top = max(r["value"] for r in rows) or 1
    used = _parts_used(spec)
    lines = [" ".join(spec["caption"].split())]
    if used:
        words = _legend_words(spec)
        lines.append(" · ".join(f"{CELL[p]} {words[p]}" for p in used))
    for r in rows:
        bar = _cells(r, top, used)
        val = fmt_value(r["value"], spec["unit"], lang)
        if _form(spec) == "columns":
            ln = f"{bar} {_cut_chars(r['label'], TEXT_LABEL_MAX)} {val}"
        else:
            ln = f"{bar} {val} {_cut_chars(r['label'], TEXT_LABEL_MAX)}"
        if r.get("note"):
            ln += f" · {_cut_chars(r['note'], TEXT_NOTE_MAX)}"
        lines.append(ln.rstrip())
    return "\n".join(lines)


def describe(spec):
    """Every number the chart shows or encodes, flat: one entry per row total and one per part, each with the row's
    label, the part (None for the total), the value, the text the chart prints for it, the unit and what it is of.
    [] for a spec validate() refuses."""
    if validate(spec):
        return []
    lang = spec.get("lang", "en")
    cap = " ".join(spec["caption"].split())
    words = _legend_words(spec)
    used = _parts_used(spec)
    out = []
    for i, r in enumerate(spec["rows"]):
        label = " ".join(r["label"].split())
        base = {"row": i, "label": label, "unit": spec["unit"], "kind": spec["kind"]}
        if spec.get("series") is not None:
            base["series"] = spec["series"][r["series"]]
        if r.get("href"):
            base["href"] = r["href"]
        base["note"] = " ".join(r["note"].split()) if r.get("note") else None
        out.append(dict(base, part=None, value=r["value"], shown=fmt_value(r["value"], spec["unit"], lang),
                        of=cap, printed=True))
        for p in used:
            v = r["parts"].get(p, 0) or 0
            out.append(dict(base, part=p, value=v, shown=fmt_value(v, spec["unit"], lang),
                            of=f"{words[p]} of {label}: {cap}", printed=False))
    return out


# ====================================== demo (made-up specs) =====================================================
def demo_specs():
    """Made-up specs, one per thing worth looking at. No real names."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    split = [(12, 30, 0), (18, 27, 1), (25, 22, 0), (31, 20, 2), (40, 18, 0), (38, 15, 1), (52, 16, 0),
             (47, 12, 0), (61, 14, 3), (58, 9, 0)]
    yt = "https://www.youtube.com/@"
    return {
        "per_month_split": {
            "kind": "per_month", "unit": "count", "lang": "en",
            "caption": "Videos opened per month this year, Shorts and long videos:",
            "rows": [{"label": m, "value": s + lo + u, "parts": {"shorts": s, "long": lo, "unknown": u}}
                     for m, (s, lo, u) in zip(months, split)]},
        "per_month_plain": {
            "kind": "per_month", "unit": "count", "lang": "en", "caption": "Videos opened per month, without Shorts:",
            "rows": [{"label": m, "value": v} for m, v in zip(months, (30, 27, 22, 20, 18, 15, 16, 12, 14, 9, 0, 3))]},
        "per_month_big": {
            "kind": "per_month", "unit": "count", "lang": "es",
            "caption": "Videos abiertos por mes (un video abierto en dos meses cuenta en los dos):",
            "rows": [{"label": m, "value": v, "parts": {"shorts": s, "long": v - s - u, "unknown": u}}
                     for m, v, s, u in zip(["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct",
                                            "nov", "dic"],
                                           (812, 940, 1094, 1203, 990, 870, 1320, 1288, 1010, 760, 640, 905),
                                           (500, 610, 702, 800, 640, 520, 880, 901, 655, 430, 380, 560),
                                           (4, 0, 12, 3, 0, 0, 7, 1, 0, 2, 0, 5))]},
        "by_area": {
            "kind": "by_area", "unit": "percent", "lang": "en", "caption": "Share of what you opened, by area:",
            "rows": [{"label": n, "value": v} for n, v in (("Gaming", 38.4), ("Comedy", 21.2), ("Art and drawing", 14.6),
                                                           ("Science and maths", 9.3), ("Music", 6.1), ("Cooking", 0.4))]},
        "by_theme_split": {
            "kind": "by_theme", "unit": "count", "lang": "en",
            "caption": "Videos opened in the last 4 weeks, by theme, Shorts and long videos:",
            "rows": [{"label": n, "value": s + lo, "parts": {"shorts": s, "long": lo}}
                     for n, s, lo in (("Speedrun challenges", 41, 12), ("Block building tutorials", 8, 31),
                                      ("Watercolor painting for beginners and everyone else", 2, 19),
                                      ("Puzzle game reviews", 11, 6))]},
        "by_channel_links": {
            "kind": "by_channel", "unit": "count", "lang": "en", "caption": "Videos opened in 2025, by channel:",
            "rows": [{"label": n, "value": v, "href": yt + h} for n, v, h in (
                ("Pixel Forge", 212, "pixelforge"), ("The Quiet Builder", 160, "quietbuilder"),
                ("Morning Sketchbook", 97, "morningsketch"), ("Nebula Labs", 64, "nebulalabs"),
                ("A Channel With A Rather Long Name Indeed", 41, "longname"))]},
        "topics_two_years": {
            "kind": "topics_by_year", "unit": "count", "lang": "en", "series": ["2026", "2025"],
            "caption": "Videos opened, gaming and art, this year against last year:",
            "rows": [{"label": "Gaming 2026", "value": 410, "series": 0, "group": "Gaming"},
                     {"label": "Gaming 2025", "value": 530, "series": 1, "group": "Gaming"},
                     {"label": "Art 2026", "value": 190, "series": 0, "group": "Art"},
                     {"label": "Art 2025", "value": 120, "series": 1, "group": "Art"}]},
        "per_year": {
            "kind": "per_year", "unit": "percent", "lang": "en", "caption": "Shorts' share of your YouTube videos, by year:",
            "rows": [{"label": str(y), "value": v} for y, v in ((2020, 4), (2021, 9), (2022, 22), (2023, 35),
                                                              (2024, 48), (2025, 57), (2026, 61))]},
        "per_year_notes": {
            "kind": "per_year", "unit": "count", "lang": "en",
            "caption": "Videos opened per year (the bar) and the main theme:",
            "rows": [{"label": str(y), "value": v, "note": t} for y, v, t in (
                (2021, 1640, "Puzzle games"), (2022, 2210, "Speedrun challenges"), (2023, 2890, "Block building"),
                (2024, 3105, "Watercolor painting"), (2025, 2760, "Science explainers"))]},
        "edge_labels": {
            "kind": "by_theme", "unit": "count", "lang": "en",
            "caption": "Edge cases: a long label, right-to-left, emoji, a zero and one huge value:",
            "rows": [{"label": "Extremely long label that keeps going well past any sensible width", "value": 4},
                     {"label": "בישול ביתי ואפייה", "value": 3},
                     {"label": "Cozy builds 🏡✨", "value": 2},
                     {"label": "Zero this time", "value": 0},
                     {"label": "One huge value", "value": 2400}]},
    }


def demo(out_dir):
    """Writes every demo spec as SVG and PNG, light and dark, and the text charts; returns the paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    texts = []
    for name, spec in demo_specs().items():
        why = validate(spec)
        if why:
            raise SystemExit(f"demo spec {name} is refused: {why}")
        for theme in ("light", "dark"):
            p = os.path.join(out_dir, f"{name}-{theme}.svg")
            with open(p, "w", encoding="utf-8") as f:
                f.write(svg(spec, theme))
            paths.append(p)
            b = png(spec, theme)
            if b is not None:
                p = os.path.join(out_dir, f"{name}-{theme}.png")
                with open(p, "wb") as f:
                    f.write(b)
                paths.append(p)
        texts.append(f"== {name}\n{text(spec)}\n")
    p = os.path.join(out_dir, "text-charts.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(texts))
    paths.append(p)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m mvp.charts", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="write every chart kind, light and dark, SVG and PNG, from made-up specs")
    d.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        paths = demo(a.out)
        pngs = sum(p.endswith(".png") for p in paths)
        print(f"wrote {len(paths)} files to {a.out} ({pngs} PNG{'' if pngs == 1 else 's'})")
        if not pngs:
            print("no PNG: Pillow is not installed (pip install pillow==12.3.0); the SVGs and text charts are there")
    return 0


if __name__ == "__main__":
    sys.exit(main())
