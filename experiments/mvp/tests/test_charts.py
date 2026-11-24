"""Round 12, pass 7, G3: the chart drawing module (mvp/charts.py): a spec in; an SVG, a PNG, a text chart and the
flat list of its numbers out.

Made-up specs only (every label, channel and link here is invented). No model call, no network."""
import copy
import io
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp import charts  # noqa: E402

SVGNS = "{http://www.w3.org/2000/svg}"
HAS_PIL = True
try:
    from PIL import Image  # noqa: F401
except Exception:   # pragma: no cover
    HAS_PIL = False
needs_pil = pytest.mark.skipif(not HAS_PIL, reason="Pillow is not installed")


def bars_spec(**kw):
    s = {"kind": "by_theme", "unit": "count", "lang": "en", "caption": "Videos opened, by theme:",
         "rows": [{"label": "Puzzle games", "value": 40}, {"label": "Block building", "value": 25},
                  {"label": "Sketching", "value": 10}, {"label": "Space news", "value": 0}]}
    s.update(kw)
    return s


def split_spec(**kw):
    s = {"kind": "per_month", "unit": "count", "lang": "en", "caption": "Videos opened per month:",
         "rows": [{"label": m, "value": a + b + c, "parts": {"shorts": a, "long": b, "unknown": c}}
                  for m, (a, b, c) in zip(["Jan", "Feb", "Mar", "Apr", "May"],
                                          [(10, 20, 0), (30, 12, 3), (5, 5, 0), (0, 18, 1), (22, 0, 0)])]}
    s.update(kw)
    return s


def share_spec(**kw):
    s = {"kind": "by_area", "unit": "percent", "lang": "en", "caption": "Share of what you opened, by area:",
         "rows": [{"label": "Gaming", "value": 41.6}, {"label": "Comedy", "value": 22.2},
                  {"label": "Music", "value": 9.5}]}
    s.update(kw)
    return s


def with_row(spec, i, **kw):
    s = copy.deepcopy(spec)
    s["rows"][i].update(kw)
    return s


# ====================================== validate: every refusal, one by one ======================================
def test_demo_specs_are_all_drawable():
    for name, spec in charts.demo_specs().items():
        assert charts.validate(spec) == [], name


def test_good_specs_pass():
    for s in (bars_spec(), split_spec(), share_spec()):
        assert charts.validate(s) == []


REFUSALS = [
    ("not a dict", lambda: [1, 2], "not a dict"),
    ("unknown kind", lambda: bars_spec(kind="pie"), "unknown kind"),
    ("unknown unit", lambda: bars_spec(unit="hours"), "unknown unit"),
    ("unknown language", lambda: bars_spec(lang="fr"), "unknown language"),
    ("unknown chart field", lambda: bars_spec(colour="red"), "unknown chart fields"),
    ("unknown row field", lambda: with_row(bars_spec(), 0, onclick="x"), "unknown fields"),
    ("no caption", lambda: bars_spec(caption=" "), "no caption"),
    ("value NaN", lambda: with_row(bars_spec(), 1, value=float("nan")), "not a finite number"),
    ("value infinite", lambda: with_row(bars_spec(), 1, value=float("inf")), "not a finite number"),
    ("value a string", lambda: with_row(bars_spec(), 1, value="25"), "not a finite number"),
    ("value a bool", lambda: with_row(bars_spec(), 1, value=True), "not a finite number"),
    ("value negative", lambda: with_row(bars_spec(), 1, value=-3), "negative"),
    ("count not whole", lambda: with_row(bars_spec(), 1, value=2.5), "not a whole number"),
    ("parts off by one", lambda: with_row(split_spec(), 1, value=46), "the parts add up to 45, not to the value 46"),
    ("parts not parts", lambda: with_row(split_spec(), 0, parts={"shorts": 10, "minutes": 20}), "two measures"),
    ("parts negative", lambda: with_row(split_spec(), 0, parts={"shorts": 40, "long": -10}), "a part is not"),
    ("some rows split, some not", lambda: with_row(split_spec(), 2, parts=None), "every row or none"),
    ("one row", lambda: bars_spec(rows=[{"label": "A", "value": 3}]), "fewer than 2 rows"),
    ("nine bars", lambda: bars_spec(rows=[{"label": f"T{i}", "value": i + 1} for i in range(9)]),
     "at most 8 fit a bars chart"),
    ("thirteen columns", lambda: split_spec(rows=[{"label": f"M{i}", "value": i + 1} for i in range(13)]),
     "at most 12 fit a columns chart"),
    ("a row in another unit", lambda: with_row(bars_spec(), 0, unit="percent"), "two measures in one chart"),
    ("parts and series", lambda: split_spec(series=["2026", "2025"]), "two measures in one chart"),
    ("shares over 100 of one whole", lambda: share_spec(rows=[{"label": "A", "value": 60}, {"label": "B", "value": 50}]),
     "over 100% of one whole"),
    ("a share over 100", lambda: share_spec(kind="per_year", rows=[{"label": "2025", "value": 101},
                                                                   {"label": "2026", "value": 50}]), "over 100%"),
    ("the top share says it all", lambda: share_spec(rows=[{"label": "A", "value": 90}, {"label": "B", "value": 6}]),
     "says nothing"),
    ("all round to 0 (percent)", lambda: share_spec(rows=[{"label": "A", "value": 0.3}, {"label": "B", "value": 0.4}]),
     "every row rounds to 0"),
    ("all zero (count)", lambda: bars_spec(rows=[{"label": "A", "value": 0}, {"label": "B", "value": 0}]),
     "every row rounds to 0"),
    ("label with a newline", lambda: with_row(bars_spec(), 0, label="Puzzle\ngames"), "control character"),
    ("label with a tab", lambda: with_row(bars_spec(), 0, label="Puzzle\tgames"), "control character"),
    ("label with NUL", lambda: with_row(bars_spec(), 0, label="Puzzle\x00"), "control character"),
    ("label with a bidi override", lambda: with_row(bars_spec(), 0, label="abc‮def"), "control character"),
    ("label with a line separator", lambda: with_row(bars_spec(), 0, label="abc def"), "control character"),
    ("caption with a control", lambda: bars_spec(caption="Videos\x1b[31m"), "caption holds a control"),
    ("note with a control", lambda: with_row(bars_spec(), 0, note="a\nb"), "note is not plain text"),
    ("legend with a control", lambda: split_spec(legend={"shorts": "Sh\norts"}), "legend word"),
    ("legend names a stranger", lambda: split_spec(legend={"minutes": "Minutes"}), "not a part"),
    ("series index with no series", lambda: with_row(bars_spec(), 0, series=0), "no series names"),
    ("series index out of range", lambda: bars_spec(series=["2026", "2025"], rows=[
        {"label": "A 2026", "value": 3, "series": 0}, {"label": "A 2025", "value": 2, "series": 2}]),
     "not one of the series"),
    ("a label too long", lambda: with_row(bars_spec(), 0, label="x" * 201), "longer than 200"),
]


@pytest.mark.parametrize("name,make,why", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_validate_refuses(name, make, why):
    reasons = charts.validate(make())
    assert any(why in r for r in reasons), reasons


def test_percent_parts_within_rounding_pass_and_beyond_fail():
    s = share_spec(kind="per_year", rows=[
        {"label": "2025", "value": 40, "parts": {"shorts": 20.4, "long": 19.4}},
        {"label": "2026", "value": 30, "parts": {"shorts": 15, "long": 15}}])
    assert charts.validate(s) == []
    s["rows"][0]["parts"] = {"shorts": 25, "long": 19}
    assert any("add up to 44" in r for r in charts.validate(s))


def test_share_top_row_just_under_90_is_drawn():
    assert charts.validate(share_spec(rows=[{"label": "A", "value": 89.4}, {"label": "B", "value": 6}])) == []


GOOD_HREFS = ["https://www.youtube.com/@a-made-up-channel", "https://youtube.com/channel/UCmadeup",
              "https://m.youtube.com/@x", "https://youtu.be/abcDEF12345", "https://www.instagram.com/made.up/",
              "https://instagram.com/made_up", "https://m.instagram.com/made_up", "https://WWW.YouTube.com/@x"]
BAD_HREFS = ["http://www.youtube.com/@x", "javascript:alert(1)", "JavaScript:alert(1)",
             "data:text/html;base64,PHNjcmlwdD4=", "ftp://youtube.com/x", "https://evil.example/@x",
             "https://youtube.com.evil.example/x", "https://evilyoutube.com/x", "https://user@youtube.com/x",
             "https://youtube.com:8443/x", 'https://youtube.com/x"onmouseover="alert(1)', "https://youtube.com/a b",
             "https://youtube.com/a\nb", "https://youtube.com/<x>", "//youtube.com/x", "https:youtube.com/x",
             "https://youtube.com\\@evil.example/", "https://xn--yutube-wqa.com/x", "", "https://"]


@pytest.mark.parametrize("h", GOOD_HREFS)
def test_href_allowed(h):
    assert charts.href_ok(h)
    assert charts.validate(with_row(bars_spec(kind="by_channel"), 0, href=h)) == []


@pytest.mark.parametrize("h", BAD_HREFS)
def test_href_refused(h):
    assert not charts.href_ok(h)
    s = with_row(bars_spec(kind="by_channel"), 0, href=h)
    assert any("link" in r for r in charts.validate(s))
    assert charts.svg(s) is None and charts.png(s) is None and charts.text(s) is None and charts.describe(s) == []


# ====================================== geometry read back from the SVG =========================================
def seg_lengths(svg_text):
    """{row: [(part, length), ...]} in drawing order."""
    root = ET.fromstring(svg_text)
    out = {}
    for g in root.iter(SVGNS + "g"):
        if g.get("data-row") is None:
            continue
        segs = []
        for r in g.iter(SVGNS + "rect"):
            if "seg" in (r.get("class") or "").split():
                segs.append((r.get("data-part"), float(r.get("width")), float(r.get("height"))))
        out[int(g.get("data-row"))] = segs
    return out


def lengths(spec, svg_text):
    L = charts.layout(spec)
    horizontal = L["form"] != "columns"
    return {row: [(p, w if horizontal else h) for p, w, h in segs] for row, segs in seg_lengths(svg_text).items()}


@pytest.mark.parametrize("make", [bars_spec, split_spec, share_spec,
                                  lambda: charts.demo_specs()["per_month_big"],
                                  lambda: charts.demo_specs()["topics_two_years"],
                                  lambda: charts.demo_specs()["per_year"],
                                  lambda: charts.demo_specs()["by_channel_links"]])
def test_svg_bar_lengths_are_proportional_to_the_values(make):
    spec = make()
    for theme in ("light", "dark", "auto"):
        s = charts.svg(spec, theme)
        ls = lengths(spec, s)
        ratios = []
        for i, r in enumerate(spec["rows"]):
            total = sum(x for _, x in ls.get(i, []))
            if r["value"] == 0:
                assert i not in ls   # a zero draws no bar
                continue
            ratios.append(total / r["value"])
        top = max(r["value"] for r in spec["rows"])
        for i, r in enumerate(spec["rows"]):
            if r["value"] and i in ls:
                want = r["value"] * max(ratios)
                got = sum(x for _, x in ls[i])
                assert abs(got - max(want, 1.0)) <= 0.02 + (1.0 if want < 1 else 0), (i, got, want)
        assert max(ratios) * top > 100   # a real length, not a sliver chart


def test_equal_values_draw_equal_bars_and_bars_start_at_one_baseline():
    spec = bars_spec(rows=[{"label": "A", "value": 7}, {"label": "B", "value": 7}, {"label": "Ccc", "value": 3}])
    root = ET.fromstring(charts.svg(spec))
    xs, ws = [], []
    for g in root.iter(SVGNS + "g"):
        if g.get("data-row") is not None:
            r = next(x for x in g.iter(SVGNS + "rect") if "seg" in x.get("class"))
            xs.append(float(r.get("x")))
            ws.append(float(r.get("width")))
    assert len(set(xs)) == 1 and ws[0] == ws[1] and abs(ws[2] / ws[0] - 3 / 7) < 1e-3


def test_parts_sum_to_the_bar_and_each_part_is_proportional():
    spec = split_spec()
    ls = lengths(spec, charts.svg(spec))
    unit = max(sum(x for _, x in ls[i]) / r["value"] for i, r in enumerate(spec["rows"]))
    boosted = 0
    for i, r in enumerate(spec["rows"]):
        segs = dict(ls[i])
        assert abs(sum(segs.values()) - r["value"] * unit) <= 0.03   # the whole bar is exact
        want = {p: v * unit for p, v in r["parts"].items() if v}
        assert set(segs) == set(want)   # a zero part draws nothing; every other part is drawn
        lift = sum(charts.MIN_PART - w for w in want.values() if w < charts.MIN_PART)
        biggest = max(want, key=want.get)
        for p, w in want.items():
            if w < charts.MIN_PART:   # a thin part is drawn at the minimum, taken from the biggest part
                assert abs(segs[p] - charts.MIN_PART) <= 0.02
                boosted += 1
            elif p == biggest:
                assert abs(segs[p] - (w - lift)) <= 0.03, (i, p)
            else:
                assert abs(segs[p] - w) <= 0.02, (i, p)
    assert boosted >= 1   # the made-up data has one 1-video part of unknown length


def test_split_order_is_long_then_shorts_then_unknown_and_unknown_is_never_folded():
    spec = split_spec()
    segs = seg_lengths(charts.svg(spec))
    assert [p for p, _, _ in segs[1]] == ["long", "shorts", "unknown"]
    assert [p for p, _, _ in segs[3]] == ["long", "unknown"]
    leg = charts.text(spec).splitlines()[1]
    assert leg == "█ Long videos · ▓ Shorts · ▒ Length unknown"


def test_without_shorts_has_no_legend_and_one_colour():
    s = charts.svg(bars_spec())
    assert "leg" not in re.findall(r'class="c-\w+ (\w+)"', s)
    assert set(re.findall(r'class="c-(\w+) seg"', s)) == {"one"}


def test_two_series_get_a_legend_and_two_shades():
    spec = charts.demo_specs()["topics_two_years"]
    s = charts.svg(spec)
    assert set(re.findall(r'class="c-(\w+) seg"', s)) == {"s0", "s1"}
    assert re.findall(r'class="c-ink2 leg">([^<]+)<', s) == ["2026", "2025"]


def test_columns_turn_sideways_when_values_do_not_fit_and_stay_columns_when_they_do():
    assert charts.layout(charts.demo_specs()["per_month_big"])["form"] == "bars"
    assert charts.layout(charts.demo_specs()["per_month_split"])["form"] == "columns"
    assert charts.layout(charts.demo_specs()["per_year"])["form"] == "columns"
    assert charts.layout(charts.demo_specs()["per_year_notes"])["form"] == "bars_stacked"


def test_labels_are_cut_with_an_ellipsis_and_never_wrapped():
    spec = with_row(bars_spec(), 0, label="An extremely long made up label that runs on and on past the edge")
    root = ET.fromstring(charts.svg(spec))
    labs = [t.text for t in root.iter(SVGNS + "text") if "lab" in t.get("class")]
    assert labs[0].endswith("…") and "\n" not in labs[0]
    assert labs[0].startswith("An extremely long")
    assert all(not t.endswith("…") for t in labs[1:])
    W = charts.DEFAULT_WIDTH
    for t in root.iter(SVGNS + "text"):
        assert charts.est(t.text, float(t.get("font-size"))) <= W   # nothing runs off the card


def test_legend_on_one_line_or_one_item_per_line():
    one = charts.layout(split_spec())
    leg = [o for o in one["ops"] if o.get("cls") == "leg"]
    assert len({o["y"] for o in leg}) == 1
    narrow = charts.layout(split_spec(legend={"long": "Long videos of every kind",
                                              "shorts": "Shorts of every kind",
                                              "unknown": "Videos whose length is unknown"}))
    leg = [o for o in narrow["ops"] if o.get("cls") == "leg"]
    assert len({o["y"] for o in leg}) == 3 and len({o["x"] for o in leg}) == 1


# ====================================== the PNG, measured from its pixels =========================================
def _dist(a, b):
    return max(abs(x - y) for x, y in zip(a[:3], b[:3]))


def png_lengths(spec, theme="light", scale=2):
    from PIL import Image
    im = Image.open(io.BytesIO(charts.png(spec, theme, scale=scale))).convert("RGB")
    px = im.load()
    surface = charts._rgb(charts.THEMES[theme]["surface"])
    L = charts.layout(spec)
    out = {}
    for op in L["ops"]:
        if op["op"] != "bar" or op["w"] <= 0 or op["h"] <= 0:
            continue
        if op["dir"] == "h":
            y = int((op["y"] + op["h"] / 2) * scale)
            x0 = int(round(op["x"] * scale))
            stop = int((op["x"] + op["w"] + 4) * scale)   # before the value printed at the tip
            last = max((x for x in range(x0, stop) if _dist(px[x, y], surface) > 60), default=x0 - 1)
            out[op["row"]] = (last + 1 - x0) / scale
        else:
            x = int((op["x"] + op["w"] / 2) * scale)
            base = int(round(op["y"] * scale))
            stop = int((op["y"] - op["h"] - 3) * scale)
            first = min((y for y in range(stop, base) if _dist(px[x, y], surface) > 60), default=base)
            out[op["row"]] = (base - first) / scale
    return out, L


@needs_pil
@pytest.mark.parametrize("make", [bars_spec, split_spec, share_spec,
                                  lambda: charts.demo_specs()["per_month_big"],
                                  lambda: charts.demo_specs()["per_year"],
                                  lambda: charts.demo_specs()["topics_two_years"]])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_png_bar_lengths_match_the_svg_to_the_pixel(make, theme):
    spec = make()
    got, L = png_lengths(spec, theme)
    svg_len = {row: sum(x for _, x in segs) for row, segs in lengths(spec, charts.svg(spec, theme)).items()}
    for i, r in enumerate(spec["rows"]):
        if r["value"] == 0:
            assert i not in svg_len
            continue
        assert abs(got[i] - svg_len[i]) <= 1.0, (i, got[i], svg_len[i])
    top = max(r["value"] for r in spec["rows"])
    big = [i for i, r in enumerate(spec["rows"]) if r["value"] >= top * 0.2]
    ratios = [got[i] / spec["rows"][i]["value"] for i in big]
    assert max(ratios) / min(ratios) < 1.02   # proportional, within a pixel's rounding


@needs_pil
def test_png_is_a_png_of_the_layout_size_and_scales():
    spec = split_spec()
    from PIL import Image
    L = charts.layout(spec)
    for scale in (1, 2, 3):
        im = Image.open(io.BytesIO(charts.png(spec, "light", scale=scale)))
        assert im.format == "PNG" and im.size == (round(L["w"] * scale), round(L["h"] * scale))
    assert charts.png(spec, "auto") is None and charts.png(spec, "light", scale=9) is None


@needs_pil
def test_png_draws_without_libraqm_and_with_an_rtl_and_emoji_label(monkeypatch):
    import PIL.features as F
    spec = charts.demo_specs()["edge_labels"]
    a = charts.png(spec, "light")
    orig = F.check
    monkeypatch.setattr(F, "check", lambda name: False if name == "raqm" else orig(name))
    b = charts.png(spec, "light")
    assert a and b and a[:8] == b[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_is_none_when_pillow_is_missing(monkeypatch):
    for name in [m for m in list(sys.modules) if m == "PIL" or m.startswith("PIL.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "PIL", None)
    spec = split_spec()
    assert charts.png(spec) is None
    assert charts.svg(spec) and charts.text(spec) and charts.describe(spec)   # the rest does not need it


def test_png_is_none_when_drawing_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("a broken font")
    monkeypatch.setattr(charts, "_png", boom)
    assert charts.png(split_spec()) is None


# ====================================== escaping: third-party text stays text ===================================
NASTY = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "it's & <b>bold</b>",
         "]]><!--", '<foreignObject><iframe src="https://evil.example"/></foreignObject>',
         "url(https://evil.example/x.png)", "@import 'https://evil.example/a.css';"]


@pytest.mark.parametrize("theme", ["light", "dark", "auto"])
def test_svg_escapes_every_label_caption_note_and_legend(theme):
    spec = {"kind": "by_channel", "unit": "count", "lang": "en", "caption": "Counted <b>&</b> \"quoted\" 'x'",
            "legend": {"shorts": "<Shorts>", "long": "long & 'odd'"},
            "rows": [{"label": t, "value": 10 - i, "note": t, "parts": {"shorts": 5 - i if i < 5 else 0,
                                                                         "long": 5 if i < 5 else 10 - i}}
                     for i, t in enumerate(NASTY)]}
    spec["rows"][0]["href"] = "https://www.youtube.com/@made-up?x=1&y=2"
    assert charts.validate(spec) == []
    s = charts.svg(spec, theme)
    root = ET.fromstring(s)   # well-formed XML
    assert "<script" not in s.lower() and "<foreignobject" not in s.lower() and "<iframe" not in s.lower()
    assert not re.search(r"\son\w+\s*=", s.replace("onerror=alert", ""))   # no event attribute on any element
    for el in root.iter():
        for k in el.attrib:
            assert not k.lower().startswith("on"), k
        assert el.tag.split("}")[-1] in {"svg", "title", "desc", "style", "rect", "text", "line", "a", "g",
                                         "clipPath"}, el.tag
    for el in root.iter():   # a url() only in an attribute, and only to the chart's own ids
        for v in el.attrib.values():
            assert "url(" not in v or re.fullmatch(r"url\(#sdc[0-9a-f]+-c\d+\)", v), v
    style = root.find(SVGNS + "style").text
    assert "url(" not in style and "@import" not in style and "http" not in style
    texts = [t.text for t in root.iter(SVGNS + "text")]
    assert any(t and t.startswith("<script>") for t in texts)   # drawn as text, not run
    hrefs = [a.get("href") for a in root.iter(SVGNS + "a")]
    assert hrefs == ["https://www.youtube.com/@made-up?x=1&y=2"]
    assert root.find(SVGNS + "title").text == "Counted <b>&</b> \"quoted\" 'x'"
    assert "&lt;script&gt;" in root.find(SVGNS + "desc").text.replace("<", "&lt;").replace(">", "&gt;")


def test_svg_has_no_external_reference():
    for spec in charts.demo_specs().values():
        s = charts.svg(spec, "auto")
        refs = re.findall(r'(?:href|src)="([^"]*)"', s)
        assert all(charts.href_ok(r) for r in refs)
        for u in re.findall(r"https?://[^\"'\s<)]+", s):
            assert u.startswith(("http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink")) or charts.href_ok(u)


def test_ids_are_unique_per_chart_so_two_charts_share_a_page():
    a = charts.svg(bars_spec())
    b = charts.svg(split_spec())
    ia = set(re.findall(r'id="([^"]+)"', a))
    ib = set(re.findall(r'id="([^"]+)"', b))
    assert ia and ib and not ia & ib
    assert all(i.startswith("sdc") for i in ia | ib)
    css = ET.fromstring(a).find(SVGNS + "style").text
    rules = [r for r in re.split(r"[{}]", css) if r.strip().startswith(("#", ".", "text"))]
    assert all(r.strip().startswith("#" + sorted(ia)[0][:13]) for r in rules if r.strip().startswith(("#", ".")))


def test_auto_theme_follows_the_page():
    s = charts.svg(split_spec(), "auto")
    assert "@media (prefers-color-scheme: dark)" in s
    assert charts.THEMES["light"]["shorts"] in s and charts.THEMES["dark"]["shorts"] in s
    assert charts.THEMES["dark"]["shorts"] not in charts.svg(split_spec(), "light")


def test_accessible_title_and_desc_say_what_the_text_chart_says():
    spec = split_spec()
    root = ET.fromstring(charts.svg(spec))
    assert root.get("role") == "img"
    t, d = root.find(SVGNS + "title").text, root.find(SVGNS + "desc").text
    assert t == spec["caption"]
    for r in spec["rows"]:
        assert f"{r['label']}: {r['value']}" in d
    assert "Shorts 30" in d and "Long videos 12" in d and "Length unknown 3" in d


# ====================================== the same numbers everywhere ==============================================
NUM = re.compile(r"\d[\d,.]*%?")


@pytest.mark.parametrize("name", list(charts.demo_specs()))
def test_the_same_numbers_in_svg_png_text_and_describe(name):
    spec = charts.demo_specs()[name]
    root = ET.fromstring(charts.svg(spec))
    vals_svg = [t.text for t in root.iter(SVGNS + "text") if "val" in t.get("class")]
    printed = [d["shown"] for d in charts.describe(spec) if d["printed"]]
    assert vals_svg == printed
    lines = charts.text(spec).splitlines()[1:]
    if charts._parts_used(spec):
        assert lines[0].startswith("█ ") and "·" in lines[0]   # the legend line
        lines = lines[1:]
    assert len(lines) == len(spec["rows"])
    for ln, shown in zip(lines, printed):
        assert shown in NUM.findall(ln), (ln, shown)
    # the PNG paints the same layout ops the SVG writes: the same strings at the same places
    L = charts.layout(spec)
    assert [o["s"] for o in L["ops"] if o.get("cls") == "val"] == vals_svg
    parts = [d for d in charts.describe(spec) if d["part"]]
    for i, r in enumerate(spec["rows"]):
        mine = [d["value"] for d in parts if d["row"] == i]
        if mine:
            assert sum(mine) == r["value"]


def test_describe_lists_every_number_with_what_it_is_of():
    spec = split_spec()
    d = charts.describe(spec)
    assert len(d) == len(spec["rows"]) * 4   # a total and three parts per row
    feb = [x for x in d if x["label"] == "Feb"]
    assert [(x["part"], x["value"]) for x in feb] == [(None, 45), ("long", 12), ("shorts", 30), ("unknown", 3)]
    assert feb[0]["of"] == spec["caption"] and feb[2]["of"].startswith("Shorts of Feb")
    assert all(x["unit"] == "count" and x["kind"] == "per_month" for x in d)
    ch = charts.describe(charts.demo_specs()["by_channel_links"])
    assert ch[0]["href"].startswith("https://www.youtube.com/@")


def test_percent_values_print_as_insight_rounds_them():
    spec = share_spec()
    assert [d["shown"] for d in charts.describe(spec)] == ["42%", "22%", "10%"]
    assert charts.fmt_value(1094, "count", "es") == "1.094" and charts.fmt_value(1094, "count", "en") == "1,094"


# ====================================== the text chart matches insight.py's ======================================
def test_text_chart_matches_insight_bars_and_labels():
    from mvp import insight
    spec = {"kind": "by_theme", "unit": "percent", "lang": "en", "caption": "Share of what you opened, by theme:",
            "rows": [{"label": n, "value": v * 100} for n, v in
                     (("Speedrun challenges", .31), ("Watercolor painting for beginners", .18), ("Puzzle games", .07),
                      ("Space news", .004))]}
    lines = charts.text(spec).splitlines()
    assert lines[0] == spec["caption"]
    top = max(r["value"] for r in spec["rows"])
    for ln, r in zip(lines[1:], spec["rows"]):
        want = f"{insight.bar(r['value'], top)} {round(r['value'])}% {insight._label(r['label'])}"
        assert ln == want
    per = {"kind": "per_month", "unit": "count", "lang": "en", "caption": "Videos opened per month:",
           "rows": [{"label": m, "value": v} for m, v in (("Jan", 12), ("Feb", 0), ("Mar", 30))]}
    for ln, r in zip(charts.text(per).splitlines()[1:], per["rows"]):
        assert ln == f"{insight.bar(r['value'], 30)} {r['label']} {insight._fmt(r['value'], 'en')}"


def test_text_chart_split_cells_add_up_to_the_plain_bar():
    spec = split_spec()
    plain = copy.deepcopy(spec)
    for r in plain["rows"]:
        r.pop("parts")
    for a, b in zip(charts.text(spec).splitlines()[2:], charts.text(plain).splitlines()[1:]):
        cells_a, cells_b = a.split(" ")[0], b.split(" ")[0]
        assert len(cells_a) == len(cells_b) == 8
        assert cells_a.count("░") == cells_b.count("░")


# ====================================== determinism and the demo command =========================================
def test_same_spec_same_bytes():
    spec = charts.demo_specs()["per_month_split"]
    assert charts.svg(spec) == charts.svg(copy.deepcopy(spec))
    assert charts.svg(spec, "dark") != charts.svg(spec, "light")
    if HAS_PIL:
        assert charts.png(spec) == charts.png(copy.deepcopy(spec))
    assert charts.text(spec) == charts.text(copy.deepcopy(spec))


def test_width_is_clamped_and_drawers_refuse_bad_input():
    spec = bars_spec()
    assert 'width="240"' in charts.svg(spec, width=10)
    assert 'width="800"' in charts.svg(spec, width=5000)
    assert 'width="300"' in charts.svg(spec, width=float("nan"))
    assert charts.svg(spec, theme="neon") is None
    bad = with_row(spec, 0, value=-1)
    assert charts.svg(bad) is None and charts.text(bad) is None and charts.describe(bad) == []


def test_demo_command_writes_every_kind_light_and_dark(tmp_path):
    assert charts.main(["demo", "--out", str(tmp_path)]) == 0
    names = set(os.listdir(tmp_path))
    for kind in charts.demo_specs():
        for theme in ("light", "dark"):
            assert f"{kind}-{theme}.svg" in names
            if HAS_PIL:
                assert f"{kind}-{theme}.png" in names
    assert "text-charts.txt" in names
    for n in names:
        if n.endswith(".svg"):
            ET.parse(os.path.join(tmp_path, n))   # each SVG stands alone as a file


def test_demo_covers_what_the_brief_asks_to_look_at():
    d = charts.demo_specs()
    kinds = {s["kind"] for s in d.values()}
    assert kinds == set(charts.KINDS)
    assert any(r.get("parts") for r in d["per_month_split"]["rows"])
    assert all(r.get("href") for r in d["by_channel_links"]["rows"])
    labels = [r["label"] for r in d["edge_labels"]["rows"]]
    assert any(charts._rtl(x) for x in labels) and any(charts._is_emoji(c) for x in labels
                                                       for c in charts._clusters(x))
    vals = [r["value"] for r in d["edge_labels"]["rows"]]
    assert 0 in vals and max(vals) > 100 * min(v for v in vals if v)
    assert any(len(x) > 40 for x in labels)


def test_estimate_errs_wide_of_a_real_font():
    pytest.importorskip("PIL")
    from PIL import ImageFont
    path = next((p for p in charts.REGULAR_FONTS if os.path.isfile(p)), None)
    if not path:
        pytest.skip("no system sans here")
    f = ImageFont.truetype(path, 120)
    for s in ("Videos opened per month", "Watercolor painting", "1,094", "Speedrun challenges", "WWW MMM"):
        assert charts.est(s, 120) >= f.getlength(s) * 0.97, s
    assert math.isclose(charts.est("", 12), 0)
