"""PROTOTYPE ONLY - tests for the YouTube Takeout importer and API enricher, on synthetic fixtures only.

run: .venv/bin/python -m pytest experiments/youtube/test_youtube.py -q
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import api_enrich as A  # noqa: E402
import takeout_import as T  # noqa: E402

FX = os.path.join(HERE, "fixtures")
CURRENT = os.path.join(FX, "takeout_current")
LEGACY = os.path.join(FX, "takeout_legacy")
RESPONSE = os.path.join(FX, "videos_list_response.json")


@pytest.fixture(scope="module")
def current():
    items, inter, searches, subs, stats = T.build(CURRENT)
    return {"items": {it["platform_data"]["video_id"]: it for it in items}, "item_list": items,
            "inter": inter, "searches": searches, "subs": subs, "stats": stats}


def inter_of(c, vid):
    iid = c["items"][vid]["id"]
    return [x for x in c["inter"] if x["item_id"] == iid]


# ---------------- import ----------------
def test_item_shape_matches_instagram_corpus(current):
    must = {"id", "platform", "source_url", "dedup_key", "first_seen_at", "caption", "platform_data", "importance",
            "processing_depth", "interaction_kinds"}
    for it in current["item_list"]:
        assert must <= set(it)
        assert it["platform"] == "youtube"
        assert it["dedup_key"] == "youtube:" + it["platform_data"]["video_id"]
        assert it["id"].startswith("itm_") and len(it["id"]) == 16
        assert isinstance(it["caption"], str)
        allowed = {"v", "video_id", "channel_id", "channel_title", "duration_s", "playlist_id", "chapters",
                   "watch_count"}  # docs/03 platform_data.youtube
        assert set(it["platform_data"]) <= allowed
    for x in current["inter"]:
        assert {"item_id", "kind", "at", "capture_method", "weight"} <= set(x)


def test_expected_items(current):
    assert set(current["items"]) == {"SYNvid00001", "SYNvid00002", "SYNvid00003", "SYNvid00004", "SYNvid00005",
                                     "SYNvid00009", "SYNshort001"}
    assert "SYNad000001" not in current["items"]  # ads skipped
    assert current["stats"]["watch_skipped_ads"] == 1
    assert current["stats"]["watch_skipped_not_video"] == 1  # community post


def test_dedup_and_watch_count(current):
    it = current["items"]["SYNvid00001"]
    watches = [x for x in inter_of(current, "SYNvid00001") if x["kind"] == "watch"]
    assert len(watches) == 2  # three records, one exact duplicate
    assert current["stats"]["watch_duplicates"] == 1
    assert it["platform_data"]["watch_count"] == 2
    assert len([i for i in current["item_list"] if i["dedup_key"] == "youtube:SYNvid00001"]) == 1
    assert it["caption"] == "Synthetic Sourdough Shaping Walkthrough"  # latest title wins
    assert it["first_seen_at"].startswith("2025-03-04T18:20:11")


def test_interaction_weights_and_importance(current):
    w = {x["kind"]: x["weight"] for x in current["inter"]}
    assert w == {"watch": 0.1, "like": 0.3, "playlist": 0.8, "share_self": 1.0}
    assert current["items"]["SYNvid00004"]["importance"] == 0.1
    assert current["items"]["SYNvid00004"]["processing_depth"] == "count_only"
    assert current["items"]["SYNvid00003"]["importance"] == 0.4  # watch + like
    assert current["items"]["SYNvid00003"]["processing_depth"] == "light"
    assert current["items"]["SYNvid00001"]["importance"] == 1.0  # capped
    assert current["items"]["SYNvid00002"]["interaction_kinds"] == ["share_self", "watch"]  # Scroll Digest playlist
    assert current["items"]["SYNvid00005"]["processing_depth"] == "full"
    pl = [x for x in inter_of(current, "SYNvid00001") if x["kind"] == "playlist"]
    assert pl[0]["collection_name"] == "Synthetic Recipes"
    assert current["items"]["SYNvid00001"]["platform_data"]["playlist_id"] == "PLsynthetic00000000000000000000001"
    wl = [x for x in inter_of(current, "SYNshort001") if x["kind"] == "playlist"]
    assert wl[0]["collection_name"] == "Watch later"


def test_removed_and_untitled_videos(current):
    assert current["stats"]["watch_removed_no_url"] == 1  # no URL: counted, never an item
    it = current["items"]["SYNvid00009"]  # private: Takeout shows the URL as the title
    assert it["caption"] == "" and it["creator"] is None
    assert current["items"]["SYNvid00005"]["caption"] == ""  # playlist CSV has no title
    assert current["stats"]["items_without_title"] == 2


def test_subscriptions_set_creator_relation(current):
    assert {s["channel_id"] for s in current["subs"]} == {"UCsynthetic0000000000001", "UCsynthetic0000000000003"}
    assert current["items"]["SYNvid00002"]["creator_relation"] == "following"
    assert current["items"]["SYNvid00003"]["creator_relation"] == "none"


def test_search_history_is_not_an_item(current):
    qs = {s["query"] for s in current["searches"]}
    assert qs == {"synthetic sourdough shaping", "synthetic paella & rice"}  # localized title parsed via URL; ad skipped
    assert all(s["id"].startswith("srch_") for s in current["searches"])
    assert not any("search" in it["source_url"] for it in current["item_list"])


def test_url_parsing():
    assert T.video_id_from_url("https://www.youtube.com/watch?v=SYNvid00001&t=30s") == "SYNvid00001"
    assert T.video_id_from_url("https://music.youtube.com/watch?v=SYNvid00004") == "SYNvid00004"
    assert T.video_id_from_url("https://youtu.be/SYNvid00004") == "SYNvid00004"
    assert T.video_id_from_url("https://www.youtube.com/shorts/SYNshort001") == "SYNshort001"
    assert T.video_id_from_url("https://www.youtube.com/channel/UCsynthetic0000000000001") is None
    assert T.video_id_from_url(None) is None
    assert T.parse_time("2021-05-03 19:22:11 UTC") == "2021-05-03T19:22:11+00:00"
    assert T.parse_time("2025-03-04T18:20:11.123Z") == "2025-03-04T18:20:11.123000+00:00"


def test_legacy_csv_variant():
    items, _inter, searches, _subs, stats = T.build(LEGACY)
    by = {it["platform_data"]["video_id"]: it for it in items}
    assert set(by) == {"SYNvid00006", "SYNvid00007"}
    assert by["SYNvid00007"]["interaction_kinds"] == ["like"]
    assert by["SYNvid00007"]["first_seen_at"] == "2021-04-01T08:00:00+00:00"
    assert by["SYNvid00006"]["creator_relation"] == "following"  # BOM + "Channel Id" header
    assert searches == [] and stats["watch_removed_no_url"] == 1


def test_main_writes_files(tmp_path):
    T.main([CURRENT, "--out", str(tmp_path)])
    for name in ["items.jsonl", "interactions.jsonl", "searches.jsonl", "subscriptions.jsonl", "import_stats.json"]:
        assert (tmp_path / name).exists()
    stats = json.loads((tmp_path / "import_stats.json").read_text())
    assert stats["items"] == 7 and "wall_s" in stats


# ---------------- enricher ----------------
@pytest.mark.parametrize("s,want", [("PT15M33S", 933), ("PT1H2M3S", 3723), ("PT10M", 600), ("PT45S", 45),
                                    ("P1DT2H", 93600), ("P0D", 0), ("PT0S", 0), ("", None), ("PT", None),
                                    ("garbage", None), (None, None)])
def test_parse_duration(s, want):
    assert A.parse_duration(s) == want


def test_parse_chapters_leading_and_trailing():
    d = "Intro text\n0:00 Intro\n00:45 - Pre-shaping\n3:10 Bench rest\n1:02:03 Late part\nhttps://example.com"
    ch = A.parse_chapters(d)
    assert ch == [{"start_s": 0, "title": "Intro"}, {"start_s": 45, "title": "Pre-shaping"},
                  {"start_s": 190, "title": "Bench rest"}, {"start_s": 3723, "title": "Late part"}]
    assert [c["start_s"] for c in A.parse_chapters("Intro 00:00\nMiddle 01:15\nEnd 04:40")] == [0, 75, 280]
    assert A.parse_chapters("(0:00) A\n[1:00] B\n2:00 | C")[2] == {"start_s": 120, "title": "C"}


@pytest.mark.parametrize("d", [
    "0:30 A\n1:00 B\n2:00 C",          # first is not 0:00
    "0:00 A\n1:00 B",                  # fewer than three
    "0:00 A\n0:05 B\n1:00 C",          # chapter shorter than 10 s
    "0:00 A\n2:00 B\n1:00 C",          # not ascending
    "",
])
def test_parse_chapters_rejects_invalid(d):
    assert A.parse_chapters(d) == []


def test_parse_chapters_drops_past_duration():
    assert A.parse_chapters("0:00 A\n1:00 B\n2:00 C\n9:00 D", duration_s=300) == [
        {"start_s": 0, "title": "A"}, {"start_s": 60, "title": "B"}, {"start_s": 120, "title": "C"}]


def test_parse_response():
    resp = json.load(open(RESPONSE))
    rows = A.parse_response(resp, ["SYNvid00001", "SYNvid00002", "SYNvid00004", "SYNvid00005", "SYNvid00009"],
                            fetched_at="2026-10-30T00:00:00+00:00")
    r = rows["SYNvid00001"]
    assert r["ok"] and r["provider"] == "youtube_api" and r["tier"] == 0
    assert r["duration_s"] == 725
    assert [c["start_s"] for c in r["chapters"]] == [0, 45, 190, 450]
    assert r["thumbnail_url"] == "https://i.ytimg.com/vi/SYNvid00001/maxresdefault.jpg"  # as returned, best size
    assert r["hashtags"] == ["sourdough", "bread shaping", "synthetic baking"]
    assert r["topic_categories"] == ["Food", "Hobby"]
    assert r["creator"]["id"] == "UCsynthetic0000000000001"
    assert r["refresh_by"] == "2026-11-29T00:00:00+00:00"  # 30 days
    assert rows["SYNvid00002"]["chapters"] == [] and rows["SYNvid00002"]["duration_s"] == 3723
    assert rows["SYNvid00004"]["duration_s"] is None and rows["SYNvid00004"]["live"] == "live"  # P0D live
    assert [c["start_s"] for c in rows["SYNvid00005"]["chapters"]] == [0, 75, 280, 545]
    assert rows["SYNvid00005"]["thumbnail_url"].endswith("mqdefault.jpg")
    assert rows["SYNvid00009"] == {**rows["SYNvid00009"], "ok": False, "status": "unavailable"}
    patch = A.platform_data_patch(r)
    assert set(patch) == {"channel_id", "channel_title", "duration_s", "chapters"}
    assert A.platform_data_patch(rows["SYNvid00009"]) == {}


def test_tier0_text(current):
    rows = A.parse_response(json.load(open(RESPONSE)), ["SYNvid00001"])
    it = current["items"]["SYNvid00001"]
    t = A.tier0_text(it, rows["SYNvid00001"])
    for part in ["Synthetic Sourdough Shaping Walkthrough", "by Synthetic Channel 1", "#sourdough",
                 "chapters: Intro · Pre-shaping the dough", "topics: Food"]:
        assert part in t
    assert "https://" not in t and "0:45" not in t
    assert A.tier0_text(current["items"]["SYNvid00003"]) == "Synthetic Weekend Trip Planning by Synthetic Channel 2"
    assert A.tier0_text(current["items"]["SYNvid00009"]) == ""


def test_batches_of_50(monkeypatch):
    calls = []

    def fake(ids, key, timeout=30):
        calls.append(list(ids))
        return {"items": [{"id": i, "snippet": {"title": "t"}, "contentDetails": {"duration": "PT1M"}} for i in ids]}

    monkeypatch.setattr(A, "fetch_batch", fake)
    ids = [f"SYN{n:08d}" for n in range(120)]
    rows, units = A.fetch_all(ids, "not-a-real-key", raw_dir=None, sleep_s=0)
    assert [len(c) for c in calls] == [50, 50, 20] and units == 3 and len(rows) == 120


def test_quota_estimate():
    q = A.quota_estimate(20_000)
    assert q["calls"] == 400 and q["units"] == 400 and q["share_of_daily_quota"] == 0.04
    assert q["users_backfilled_per_day_at_default_quota"] == 25


def test_no_key_skips_live_call(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(A, "fetch_batch", lambda *a, **k: pytest.fail("live call without a key"))
    T.main([CURRENT, "--out", str(tmp_path)])
    stats = A.main(["--items", str(tmp_path / "items.jsonl"), "--out", str(tmp_path / "enr")])
    assert stats["mode"] == "takeout only" and stats["quota_units_used"] == 0
    text = json.loads((tmp_path / "enr" / "text.json").read_text())
    assert set(text) == {"SYNvid00001", "SYNvid00002", "SYNvid00003", "SYNvid00004", "SYNvid00005", "SYNvid00009",
                         "SYNshort001"}
    assert "skipping" in capsys.readouterr().err


def test_eval_example_shapes():
    qs = [json.loads(l) for l in open(os.path.join(FX, "queries_example.jsonl"))]
    ans = {a["id"]: a for a in (json.loads(l) for l in open(os.path.join(FX, "answers_example.jsonl")))}
    for q in qs:
        assert set(q) == {"id", "query", "kinds", "examples", "filters"}  # Instagram method-side keys
        a = ans[q["id"]]
        assert {"relevant", "hard_negatives", "judged_not_relevant"} <= set(a)
        if "moment" in q["kinds"]:
            assert a["moments"] and set(a["moments"]) <= set(a["relevant"])
            for spans in a["moments"].values():
                for s in spans:
                    assert 0 <= s["start_s"] < s["end_s"] and s["grade"] in (1, 2)
