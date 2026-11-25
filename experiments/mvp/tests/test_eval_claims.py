"""Round 12, pass 5: the auditor (eval_claims.py) on a made-up library. Every channel, theme, title and number here is
invented. Each planted false claim must be reported with both values; each true one must pass."""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mvp import eval_claims as E  # noqa: E402

NOW = datetime(2026, 11, 22, tzinfo=timezone.utc)
TODAY = date(2026, 11, 22)
FIELDS = [{"id": 0, "name": "Food", "category": "food and cooking"}, {"id": 1, "name": "Games", "category": "gaming"},
          {"id": 2, "name": "Numbers", "category": "math"}, {"id": 3, "name": "Laughs", "category": "comedy"},
          {"id": 4, "name": "Body", "category": "health", "sensitive": True}]
THEMES = [{"id": 0, "name": "Pan recipes", "field": 0, "category": "food and cooking"},
          {"id": 1, "name": "Block building", "field": 1, "category": "gaming"},
          {"id": 2, "name": "Number puzzles", "field": 2, "category": "math"},
          {"id": 3, "name": "Funny clips", "field": 3, "category": "comedy"},
          {"id": 4, "name": "Quiet worries", "field": 4, "category": "health", "sensitive": True},
          {"id": 5, "name": "Block building", "field": 1, "category": "gaming"}]   # one name, two ids: one theme


def make_lib(tmp_path, rows, friends=()):
    """rows: dicts {ch, theme, len, pub, at: [iso, ...], p, cap}; returns (library folder, derived folder)."""
    lib = tmp_path / "lib"
    (lib / "corpus").mkdir(parents=True)
    der = tmp_path / "derived"
    (der / "lengths-v1").mkdir(parents=True)
    tdir = der / "themes-v2" / "madeup0001"
    tdir.mkdir(parents=True)
    items, inter, lens, trows = [], [], [], []
    for k, r in enumerate(list(rows) + list(friends)):
        iid = f"itm_{k:05d}"
        p = r.get("p", "youtube")
        pd = {"owner_name": r["ch"], "owner_handle": r["ch"].lower().replace(" ", ""),
              "owner_relation": "mutual" if r in friends else "none"}
        if p == "youtube":
            pd["video_id"] = f"vid{k:05d}"
            if r.get("len") is not None:
                lens.append({"video_id": pd["video_id"], "length_s": r["len"], "published": r.get("pub"),
                             "refresh_by": "2999-01-01T00:00:00+00:00", "version": "lengths-v1"})
        items.append({"id": iid, "platform": p, "source_url": f"https://example.invalid/{k}",
                      "caption": r.get("cap", f"made up video {k}"), "platform_data": pd})
        for at in r["at"]:
            inter.append({"item_id": iid, "kind": r.get("kind", "watch"), "at": at})
        if r.get("theme") is not None:
            trows.append({"item_id": iid, "field": THEMES[r["theme"]]["field"], "theme": r["theme"],
                          "name": THEMES[r["theme"]]["name"], "version": "themes-v2", "embedding_model": "made-up"})
    for name, data in (("corpus/items.jsonl", items), ("corpus/interactions.jsonl", inter)):
        with open(lib / name, "w") as f:
            f.writelines(json.dumps(x) + "\n" for x in data)
    with open(der / "lengths-v1" / "lengths.jsonl", "w") as f:
        f.writelines(json.dumps(x) + "\n" for x in lens)
    with open(tdir / "themes.jsonl", "w") as f:
        f.writelines(json.dumps(x) + "\n" for x in trows)
    json.dump({"version": "themes-v2", "fields": FIELDS, "themes": THEMES}, open(tdir / "build.json", "w"))
    return str(lib), str(der)


def day(y, m, d, h=15):
    return datetime(y, m, d, h, tzinfo=timezone.utc).isoformat()


def rows_months(spec, year=2025):
    """{month: [(channel, theme, length, n)]} -> rows, each a video opened once on the 10th of that month."""
    out = []
    for m, groups in spec.items():
        for ch, th, ln, n in groups:
            for k in range(n):
                out.append({"ch": ch, "theme": th, "len": ln, "pub": "2025-01-01",
                            "at": [day(year, m, 2 + (k % 27))]})
    return out


def audit(lib, der, text, sheet, spec, sent, tz="America/New_York"):
    L = E.Library(lib, der, tz, now=NOW)
    return E.audit_answer(L, {"id": "t1", "text": text, "window": spec, "sheet": sheet, "sent": sent, "form": None},
                          TODAY), L


def bad(rows, audit_=None, kind=None):
    return [r for r in rows if not r["ok"] and (audit_ is None or r["audit"] == audit_) and
            (kind is None or kind in r["kind"])]


# ---------------------------------------------------------------------------------------------- the record itself
def test_record_reading(tmp_path):
    rows = [{"ch": "Pixel Forge", "theme": 1, "len": 61, "pub": "2023-01-01", "at": [day(2025, 6, 2)]},
            {"ch": "Pixel Forge", "theme": 5, "len": 120, "pub": "2025-02-01", "at": [day(2025, 6, 2)]},
            {"ch": "Pixel Forge", "theme": 1, "len": 120, "pub": "2023-02-01", "at": [day(2025, 6, 2)]},
            {"ch": "Clip Barn", "theme": 3, "len": 120, "pub": None, "cap": "so funny #shorts", "at": [day(2025, 6, 2)]},
            {"ch": "Clip Barn", "theme": 3, "len": None, "at": [day(2025, 6, 2)]},
            {"ch": "Orbit Kitchen", "theme": 0, "len": 600, "pub": "2020-01-01",
             "at": ["2025-06-01T03:00:00+00:00"]},          # 11 pm on 31 May in New York
            {"ch": "Orbit Kitchen", "theme": 4, "len": 600, "pub": "2020-01-01", "at": [day(2025, 6, 3)]}]
    friend = [{"ch": "A Friend", "theme": 3, "len": 30, "pub": "2025-01-01", "at": [day(2025, 6, 2)], "p": "instagram"}]
    lib, der = make_lib(tmp_path, rows, friend)
    L = E.Library(lib, der, "America/New_York", now=NOW)
    assert len(L.items) == 7   # the friend's post is never read
    sh = {i: L.short[i] for i in sorted(L.short)}
    assert list(sh.values()) == [True, True, False, True, None, False, False]
    june = L.scope(date(2025, 6, 1).toordinal(), date(2025, 6, 30).toordinal())
    assert len(june) == 6   # the 03:00 UTC event is 31 May in the person's time zone
    assert L.theme_of["itm_00001"] == L.theme_of["itm_00000"] == "block building"   # one name, one theme
    assert "itm_00006" not in L.theme_of   # a sensitive theme is no theme
    assert L.area_of["itm_00000"] == "gaming"


def test_window_reading():
    class R:
        newest = date(2026, 10, 30).toordinal()
        oldest = date(2019, 1, 1).toordinal()
    for text, kind in (("what have i been watching the most lately", "lately"),
                       ("what was i into in the summer of 2023", "season"),
                       ("what did i watch from 2023 to 2025", "years"),
                       ("what did i watch in 2023 vs 2025", "years"), ("how has what i watch changed since 2020", "since"),
                       ("what have i been into the last 3 months", "last_days"),
                       ("which channels did i watch the most in 2025", "year"), ("what did i watch on october 30", "day"),
                       ("how many videos did i watch this year", "this_year"), ("most watched channels in math", "all")):
        assert E.read_window(text, R, TODAY)["kind"] == kind, text
    a, b, prev = E.resolve({"kind": "lately"}, R, TODAY)
    assert (date.fromordinal(a), date.fromordinal(b)) == (date(2026, 10, 3), date(2026, 10, 30))
    assert date.fromordinal(prev[0]) == date(2026, 9, 5) and date.fromordinal(prev[1]) == date(2026, 10, 2)
    a, b, prev = E.resolve({"kind": "season", "season": "summer", "year": 2023}, R, TODAY)
    assert (date.fromordinal(a), date.fromordinal(b)) == (date(2023, 6, 1), date(2023, 8, 31))
    assert (date.fromordinal(prev[0]), date.fromordinal(prev[1])) == (date(2023, 3, 1), date(2023, 5, 31))
    a, b, prev = E.resolve({"kind": "this_year"}, R, TODAY)
    assert date.fromordinal(b) == date(2026, 10, 30) and date.fromordinal(prev[1]) == date(2025, 10, 30)


# ---------------------------------------------------------------------------------------------- 1. the sheet
def _june_lib(tmp_path):
    rows = rows_months({6: [("Pixel Forge", 1, 30, 30), ("Pixel Forge", 1, 900, 10), ("Orbit Kitchen", 0, 900, 20),
                            ("Clip Barn", 3, 20, 20)],
                        5: [("Orbit Kitchen", 0, 900, 30), ("Clip Barn", 3, 20, 10)]})
    rows += [{"ch": "@igfriend.not", "theme": None, "len": None, "p": "instagram", "at": [day(2025, 6, 5)]}
             for _ in range(20)]
    return make_lib(tmp_path, rows)


def test_sheet_true_and_planted(tmp_path):
    lib, der = _june_lib(tmp_path)
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    true = {"kind": "top", "filters": {}, "window": dict(start="2025-06-01", end="2025-06-30"),
            "totals": {"items": 100, "shorts": 50, "long": 30, "shorts_share": 0.625,
                       "by_platform": {"youtube": 80, "instagram": 20}},
            "themes": [{"name": "Block building", "items": 40, "share": 0.4, "previous_share": 0.0,
                        "previous_items": 0, "change_vs_previous": 0.4},
                       {"name": "Pan recipes", "items": 20, "share": 0.2, "previous_share": 0.75,
                        "previous_items": 30, "change_vs_previous": -0.55}],
            "channels": [{"name": "Pixel Forge", "items": 40, "shorts_share": 0.75},
                         {"name": "Orbit Kitchen", "items": 20}]}
    rows, _ = audit(lib, der, "what was i into in june", true, spec, "")
    assert not bad(rows, "sheet"), bad(rows, "sheet")
    planted = json.loads(json.dumps(true))
    planted["totals"]["items"] = 104
    planted["themes"][0]["share"] = 0.45
    planted["channels"][0]["shorts_share"] = 0.9
    planted["channels"] = planted["channels"][::-1]   # the order of a list
    rows, _ = audit(lib, der, "what was i into in june", planted, spec, "")
    got = {(r["where"], r["said"], r["recount"]) for r in bad(rows, "sheet")}
    assert ("totals.items", 104, 100) in got
    assert ("themes[0].share", 0.45, 0.4) in got
    assert any(w.startswith("channels[0]>=") for w, _, _ in got)


# ---------------------------------------------------------------------------------------------- 2. the bases
def test_base_of_shorts_and_of_everything(tmp_path):
    """(d) of the founder's checks: Shorts are 50 of the 80 YouTube videos, 50 of 70 with a known length, 50 of the 100
    opened in all."""
    rows = rows_months({6: [("Pixel Forge", 1, 30, 50), ("Orbit Kitchen", 0, 900, 20), ("Orbit Kitchen", 0, None, 10)]})
    rows += [{"ch": "@igsome.one", "theme": None, "len": None, "p": "instagram", "at": [day(2025, 6, 5)]}
             for _ in range(20)]
    lib, der = make_lib(tmp_path, rows)
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    sheet = {"kind": "top", "filters": {}, "window": dict(start="2025-06-01", end="2025-06-30"),
             "totals": {"items": 100}}
    for sent, ok in (("Your watching was mostly Shorts at 71%.", False),           # 71% is of the known; of all, 50%
                     ("Shorts were 71% of your YouTube videos.", False),           # of all YouTube videos: 62%
                     ("Shorts were 71% of your YouTube videos with a known length.", True),
                     ("Shorts were 62% of your YouTube videos.", True),
                     ("Shorts made up 50% of what you opened.", True)):
        rows_, _ = audit(lib, der, "what did i watch in june", sheet, spec, sent)
        b = bad(rows_, "base")
        assert (not b) == ok, (sent, b)
        if not ok:
            assert b[0]["said"] == 71.0 and b[0]["recount"] in (50.0, 62.5)


def test_base_of_their_videos_under_a_topic(tmp_path):
    """(b): "A and B are both about T (100% and 99% of their videos)" in a math answer, where it is of their MATH
    videos."""
    rows = rows_months({6: [("Quiet Math", 2, 900, 20), ("Quiet Math", 0, 900, 10), ("Sum Club", 2, 900, 15),
                            ("Sum Club", 0, 900, 15)]})
    for r in rows:
        if r["theme"] == 2:
            r["cap"] = "a math puzzle"
    lib, der = make_lib(tmp_path, rows)
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    sheet = {"kind": "channels", "filters": {"topic": "math", "topic_themes": ["Number puzzles"]},
             "window": dict(start="2025-06-01", end="2025-06-30"),
             "channels": [{"name": "Quiet Math", "items": 20}, {"name": "Sum Club", "items": 15}]}
    false = "Quiet Math and Sum Club are both about Number puzzles (100% and 100% of their videos)."
    rows_, _ = audit(lib, der, "most watched channels in math", sheet, spec, false)
    b = bad(rows_, "base", "their videos")
    assert {(r["said"], r["recount"]) for r in b} == {(100.0, 66.7), (100.0, 50.0)}
    true = "Quiet Math and Sum Club are both about Number puzzles (67% and 50% of their videos)."
    rows_, _ = audit(lib, der, "most watched channels in math", sheet, spec, true)
    assert not bad(rows_, "base")


def test_counts_with_their_base(tmp_path):
    """(c): "You opened 30 long videos and only 31 total videos" on a without-Shorts answer."""
    lib, der = _june_lib(tmp_path)
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    sheet = {"kind": "top", "filters": {"without_shorts": True}, "window": dict(start="2025-06-01", end="2025-06-30")}
    rows_, _ = audit(lib, der, "what did i watch in june without shorts", sheet, spec,
                     "You opened 30 long videos and only 31 total videos.")
    got = {(r["kind"], r["said"], r["recount"]) for r in bad(rows_, "base")}
    # pass 6 (X4): "31 total videos" does not say "long" or "without Shorts", so it is recounted as all 100 opened
    assert ("count (its words drop a filter: without Shorts)", 31, 100) in got
    rows_, _ = audit(lib, der, "what did i watch in june without shorts", sheet, spec,
                     "You opened 30 long videos. Pixel Forge is behind 10 of the 30 videos.")
    assert not bad(rows_, "base")


# ---------------------------------------------------------------------------------------------- 3. the words
def _season_lib(tmp_path, may_bump):
    spec = {}
    for m in range(1, 13):
        n = 12 if (m == 5 and may_bump) else (8 if m in (6, 7, 8) else 2)
        spec[m] = [("Quiet Math", 2, 900, n), ("Pixel Forge", 1, 900, 50 - n)]
    return make_lib(tmp_path, rows_months(spec))


@pytest.mark.parametrize("may_bump, ok", [(True, False), (False, True)])
def test_peaked_against_every_span(tmp_path, may_bump, ok):
    """(a): the summer's 16% is the highest of the calendar seasons, but May to July (28 of 150) is higher."""
    lib, der = _season_lib(tmp_path, may_bump)
    spec = {"kind": "season", "season": "summer", "year": 2025}
    sheet = {"kind": "top", "filters": {}, "window": dict(start="2025-06-01", end="2025-08-31")}
    sent = ("In the summer of 2025 (1 June to 31 August 2025), your Number puzzles watching peaked then, at 16%, "
            "more than in any other three months.")
    rows_, _ = audit(lib, der, "what was i into in the summer of 2025", sheet, spec, sent)
    b = bad(rows_, "word", "peaked")
    assert (not b) == ok
    if not ok:
        assert b[0]["said"] == 16.0 and b[0]["recount"] == 18.7


def test_word_claims(tmp_path):
    rows = rows_months({6: [("Pixel Forge", 1, 900, 30), ("Orbit Kitchen", 0, 900, 50), ("Clip Barn", 3, 20, 20)],
                        5: [("Pixel Forge", 1, 900, 60), ("Orbit Kitchen", 0, 900, 30), ("Clip Barn", 3, 20, 10)]},
                       year=2025)
    rows += rows_months({3: [("Pixel Forge", 1, 900, 40), ("Orbit Kitchen", 0, 900, 10)]}, year=2024)
    lib, der = make_lib(tmp_path, rows)
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    sheet = {"kind": "top", "filters": {}, "window": dict(start="2025-06-01", end="2025-06-30"),
             "channels": [{"name": n} for n in ("Orbit Kitchen", "Pixel Forge", "Clip Barn")]}
    cases = [
        ("Mostly Pixel Forge.", "mostly", False),                       # 30 of 100
        ("Mostly Orbit Kitchen.", "mostly", True),                      # 50 of 100
        ("Pixel Forge led, ahead of Orbit Kitchen.", "led", False),
        ("Orbit Kitchen led, ahead of Pixel Forge and Clip Barn.", "led", True),
        ("Orbit Kitchen led, ahead of Clip Barn and Pixel Forge.", "order", False),
        ("Orbit Kitchen, followed by Clip Barn.", "next place", False),
        ("Orbit Kitchen came first; Pixel Forge came next (30%).", "next place", True),
        ("Much more Orbit Kitchen: about 3 times as many (50 against 30).", "ratio", False),
        ("Much more Orbit Kitchen: about 2 times as many (50 against 25).", "ratio", True),
        ("Block building fell from 60% to 30%.", "direction", True),
        ("Block building grew from 60% to 30%.", "direction", False),
        ("Clip Barn was new.", "new", False),                            # opened in May too
    ]
    for sent, kind, ok in cases:
        rows_, _ = audit(lib, der, "what did i watch in june", sheet, spec, sent)
        b = bad(rows_, "word", kind)
        seen = [r for r in rows_ if r["audit"] == "word" and kind in r["kind"]]
        assert seen, (sent, "not checked")
        assert (not b) == ok, (sent, b)


def test_every_year(tmp_path):
    rows = rows_months({3: [("Pixel Forge", 1, 900, 60), ("Orbit Kitchen", 0, 900, 30)]}, year=2024)
    rows += rows_months({3: [("Pixel Forge", 1, 900, 20), ("Orbit Kitchen", 0, 900, 40)]}, year=2025)
    lib, der = make_lib(tmp_path, rows)
    spec = {"kind": "years", "from": 2024, "to": 2025}
    sheet = {"kind": "changed", "filters": {}}
    rows_, _ = audit(lib, der, "what did i watch in 2024 vs 2025", sheet, spec,
                     "Gaming led every year.")
    b = bad(rows_, "word", "every year")
    assert b and b[0]["recount"] == "2025"
    rows_, _ = audit(lib, der, "what did i watch in 2024 vs 2025", sheet, spec,
                     "From 1 January 2024 to 31 December 2025, gaming fell from 67% in 2024 to 33% in 2025.")
    assert not bad(rows_), bad(rows_)


def test_first_date_channel_shorts_and_a_cut_topic(tmp_path):
    rows = rows_months({5: [("Orbit Kitchen", 0, 900, 3)], 6: [("Orbit Kitchen", 0, 900, 5)]})
    for r in rows:
        r["cap"] = "cooking at home"
    rows += rows_months({6: [("Quiet Math", 2, 30, 10), ("Quiet Math", 0, 900, 10)]})
    for r in rows[-20:-10]:
        r["cap"] = "a math puzzle"
    lib, der = make_lib(tmp_path, rows)
    first = {"kind": "first", "filters": {"topic": "cooking", "topic_themes": ["Pan recipes"]}}
    rows_, _ = audit(lib, der, "when did i first start watching cooking videos", first, {"kind": "all"},
                     "You first opened a cooking video on 10 June 2025.")
    b = bad(rows_, "base", "first or last date")
    assert b and b[0]["said"] == "2025-06-10" and b[0]["recount"] == "2025-05-02"
    rows_, _ = audit(lib, der, "when did i first start watching cooking videos", first, {"kind": "all"},
                     "You first opened a cooking video on 2 May 2025.")
    assert not bad(rows_, "base")
    math = {"kind": "channels", "filters": {"topic": "math", "topic_themes": ["Number puzzles"]},
            "channels": [{"name": "Quiet Math"}]}
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    rows_, _ = audit(lib, der, "most watched channels in math", math, spec,
                     "Quiet Math is a clip channel you grazed (100% Shorts).")
    b = bad(rows_, "base", "Shorts share of a channel")
    assert b and b[0]["recount"] == 50.0 and "own_filt_known" in b[0]["note"]
    cut = {"kind": "count", "filters": {"topic": "cooking", "topic_themes": ["Pan recipes"]}}
    rows_, _ = audit(lib, der, "how many cooking and math videos did i watch in june", cut, spec, "")
    assert bad(rows_, "sheet", "topic read (cut)")


# ---------------------------------------------------------------------------------------------- 4. the summary
def test_summary_prints_codes_only(tmp_path, capsys):
    lib, der = _june_lib(tmp_path)
    out = tmp_path / "answers"
    out.mkdir()
    sheet = {"kind": "top", "filters": {}, "window": dict(start="2025-06-01", end="2025-06-30"),
             "totals": {"items": 99}, "channels": [{"name": "Pixel Forge"}, {"name": "Orbit Kitchen"}]}
    rec = {"id": "q1", "text": "what did i watch in june", "sent": "Mostly Pixel Forge, ahead of Orbit Kitchen.",
           "sheet": sheet, "form": {"answer": "{totals.items} videos"}, "library": lib, "timezone": "America/New_York",
           "today": TODAY.isoformat(), "window": dict(kind="range", start="2025-06-01", end="2025-06-30")}
    json.dump(rec, open(out / "a_q1.json", "w"))
    os.environ["MVP_DERIVED_HOME"] = der
    try:
        summ, rows = E.audit_folder(str(out), json_out=str(tmp_path / "audit.json"))
    finally:
        os.environ.pop("MVP_DERIVED_HOME", None)
    printed = capsys.readouterr().out
    assert summ["answers"] == 1 and summ["mismatches"] >= 2
    assert summ["sheet_used_mismatches"] == 1   # totals.items, a path the form used
    for name in ("Pixel Forge", "Orbit Kitchen", "Block building", "gaming"):
        assert name not in printed and name not in json.dumps(summ)
    assert E.paths_of({"answer": "{themes[0].name} at {themes[0].share}"}) == {"themes[0].name", "themes[0].share"}


# ---------------------------------------------------------------------------------------------- 6. pass 6
def test_the_auditor_imports_none_of_the_answer_s_code():
    src = open(E.__file__, encoding="utf-8").read()
    for mod in ("facts", "insight", "history", "themes"):
        assert not re.search(r"^\s*(?:from \S*\b" + mod + r"\b|import \S*\b" + mod + r"\b|from \. import .*\b" + mod
                             + r"\b)", src, re.M), mod


PLANTED_RESULTS = {}


def _planted():
    if not PLANTED_RESULTS:
        for c, b in E.run_planted():
            PLANTED_RESULTS[c["id"]] = (c, b)
    return PLANTED_RESULTS


@pytest.mark.parametrize("cid", [c["id"] for c in json.load(open(E.PLANTED, encoding="utf-8"))["cases"]])
def test_the_planted_set(cid):
    """A5: every defect of the hand check, planted in a made-up answer, is flagged with its kind; its clean twin is
    flagged with nothing at all."""
    c, b = _planted()[cid]
    if c["defect"]:
        assert any(c["expect"] in r["kind"] for r in b), (cid, [r["kind"] for r in b])
    else:
        assert not b, (cid, [(r["kind"], r["said"], r["recount"]) for r in b])


def test_planted_values():
    """The flags carry both values, as a hand count of the made-up record gives them."""
    P = _planted()
    got = lambda cid, kind: [(r["said"], r["recount"]) for r in P[cid][1] if kind in r["kind"]]   # noqa: E731
    assert got("x2_defect", "inside a record") == [(21.0, 62.5)]            # 25 of the 40 gaming videos
    assert got("x4_defect", "drop a filter") == [(20, 64)]                   # every long video of June
    assert got("x6_defect", "share") == [(19.0, 15.6)]                       # 10 of the 64 known to be long
    assert got("x7_defect", "usual day") == [(67.0, 50.0)]                   # 2 of 4 YouTube videos a usual day
    assert got("x8_defect", "saved") == [(4, 6)]                             # 6 saved, 4 of them never opened
    assert got("x1_defect", "cards in order") == [("1/2", "2/1")]
    assert got("x13_defect", "chart share") == [(19.0, 18.3)]               # 22 of 120, rounded once
    assert ("2 points", ">= 3 points") in got("x14_defect", "under 3 points")
    rep = E.planted_report([P[k] for k in P])
    assert rep["missed"] == [] and rep["false_flags"] == [] and rep["caught"] == rep["defects"] >= 12


def test_a_calendar_month_and_its_month_before():
    class R:
        newest = date(2026, 10, 30).toordinal()
        oldest = date(2019, 1, 1).toordinal()
    sp = E.read_window("what was i into in march 2024", R, TODAY)
    assert sp == {"kind": "month", "month": 3, "year": 2024}
    a, b, prev = E.resolve(sp, R, TODAY)
    assert (date.fromordinal(a), date.fromordinal(b)) == (date(2024, 3, 1), date(2024, 3, 31))
    assert (date.fromordinal(prev[0]), date.fromordinal(prev[1])) == (date(2024, 2, 1), date(2024, 2, 29))
    a, b, prev = E.resolve({"kind": "range", "start": "2024-03-01", "end": "2024-03-31"}, R, TODAY)
    assert date.fromordinal(prev[0]) == date(2024, 2, 1)
    assert E.read_window("what did i watch in october", R, TODAY) == {"kind": "month", "month": 10, "year": 2026}
    assert E.read_window("what did i watch on october 30", R, TODAY)["kind"] == "day"


def test_a_follow_up_keeps_the_window_of_its_chain():
    ans = [{"id": "q.0", "text": "what did i watch the most in 2024", "follow": False},
           {"id": "q.1", "text": "without shorts", "follow": True, "parent_text": "what did i watch the most in 2024"},
           {"id": "q.2", "text": "only music", "follow": True, "parent_text": "what did i watch the most in 2024"}]
    E.link_follow_ups(ans)
    assert ans[2]["chain"] == ["what did i watch the most in 2024", "without shorts"]

    class R:
        newest = date(2026, 10, 30).toordinal()
        oldest = date(2019, 1, 1).toordinal()
        said_themes = {}
    ctx = E.Ctx(R, dict(ans[2], sheet={}), TODAY)
    assert ctx.spec == {"kind": "year", "year": 2024}


def test_a_topic_row_cut_at_four_reads_its_top_themes():
    row = {"name": "blocks", "themes": ["A", "B", "C", "D"], "matched_by": "themes and words",
           "top_themes": [{"name": "E", "items": 9}, {"name": "A", "items": 5}]}
    assert E.row_themes(row) == ["A", "B", "C", "D", "E"]
    words = {"name": "folds", "themes": [], "matched_by": "words", "top_themes": [{"name": "Z", "items": 9}]}
    assert E.row_themes(words) == []   # a row found by its words has no themes: its top themes are not its own


def test_new_and_a_count_bind_to_their_own_clause(tmp_path):
    rows = rows_months({6: [("Pixel Forge", 1, 900, 30), ("Orbit Kitchen", 0, 900, 50)],
                        5: [("Pixel Forge", 1, 900, 20), ("Orbit Kitchen", 0, 900, 20)]})
    rows += [{"ch": "Clip Barn", "theme": 3, "len": 20, "pub": "2025-01-01", "at": [day(2025, 6, 9)]},
             {"ch": "Dot Lane", "theme": 3, "len": 20, "pub": "2025-01-01", "at": [day(2025, 6, 9)]}]
    lib, der = make_lib(tmp_path, rows)
    spec = dict(kind="range", start="2025-06-01", end="2025-06-30")
    sheet = {"kind": "top", "filters": {}, "window": dict(start="2025-06-01", end="2025-06-30"),
             "channels": [{"name": n} for n in ("Orbit Kitchen", "Pixel Forge", "Clip Barn", "Dot Lane")]}
    rows_, _ = audit(lib, der, "what did i watch in june", sheet, spec,
                     "Orbit Kitchen and Pixel Forge each supplied many, while 2 channels were new.")
    assert not bad(rows_), bad(rows_)
    assert [r for r in rows_ if r["kind"] == "new channels (count)" and r["ok"]]
    rows_, _ = audit(lib, der, "what did i watch in june", sheet, spec, "Pixel Forge had 30 videos.")
    assert [r for r in rows_ if r["kind"] == "count of a record's videos" and r["ok"]]
    rows_, _ = audit(lib, der, "what did i watch in june", sheet, spec, "Pixel Forge had 82 videos.")
    assert bad(rows_, "base", "count of a record")


def test_allowed_cases_are_marked_not_dropped():
    allow = E.load_allow()
    assert allow, "eval_claims_allow.json is read"
    F = E.Findings("x", "top")
    for s in ("Grid Works was mostly Block building, with 76% of its videos in that theme.", "Mostly Block building."):
        F.sentence = s
        F.add("word", "mostly (half)", False, ">=50%", 2.0, severity=1.0)
    rows = F.rows
    E.mark_allowed(rows, allow)
    assert rows[0].get("allowed") == 0 and rows[1].get("allowed") is None
    summ = E.summarise(rows, [{}])
    assert summ["mismatches"] == 1 and summ["allowed"] == 1


# ---------------------------------------------------------------------------------------------- 5. against the product
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, person, mods, no_real_keys  # noqa: E402,F401  (fixtures)
from mvp.tests.test_round12_merge import QS  # noqa: E402


@pytest.mark.parametrize("key", sorted(QS))
def test_the_auditor_agrees_with_the_sheets_of_the_made_up_library(r12, key):
    """The brief's eight questions on the round 12 made-up library: every number the auditor can recount on the sheet
    as the writer is shown it is the product's own (two readings of DESIGN 19 that share no code agree)."""
    Hm, F, _L, _T = mods()
    from mvp import insight as I
    q = Hm.read(QS[key], TODAY)
    s = F.build(r12["bot"], person(r12), q, r12["clock"][0], text=QS[key])
    s["themes"] = [dict(t, change_vs_previous=round(t["change_vs_previous"] / 100, 4))
                   if isinstance(t.get("change_vs_previous"), (int, float)) else t for t in s.get("themes") or []]
    shown = json.loads(json.dumps(I.shown(s), default=str))
    L = E.Library(str(r12["lib"]), None, "America/New_York", now=NOW)
    rows = E.audit_answer(L, {"id": key, "text": QS[key], "sheet": shown, "sent": "", "form": None}, TODAY)
    assert len([r for r in rows if r["audit"] == "sheet"]) >= 10, key
    assert not bad(rows, "sheet"), [(r["where"], r["said"], r["recount"]) for r in bad(rows, "sheet")]
