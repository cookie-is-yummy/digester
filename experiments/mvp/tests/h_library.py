"""Round 11, slice H (DESIGN.md section 18.H): a planted, made-up watch history for the history-question tests.

Every title, channel and handle here is invented. The clock of the tests is Thursday 19 November 2026 (New York);
the YouTube record ends on Friday 30 October 2026 (local time: the last watch is 31 October 02:30 UTC), Instagram's
on 15 October 2026.

    October 2026, YouTube watched: 16 videos (Pixel Forge 6, Kettle & Cast 4, Chord Garden 3, Grade Lab 2,
                                   Loose Wires 1); "blender" in 6 titles, "cooking" in 3.
    September 2026: 10 videos (Kettle & Cast 5, Chord Garden 3, Pixel Forge 2); one Pixel Forge video is watched on
                    3 September, 2 October and 20 October (one video, three watches).
    2025: 11 videos (Kettle & Cast 6, Chord Garden 4, Pixel Forge 1).
    2024: 6 videos; the first video on 5 January 2024 (Loose Wires); the first cooking video on 10 February 2024.
    Instagram: 4 saved in October 2026, 3 liked, a friend's post saved (never counted), 2 Instagram videos watched.
"""
import json

YT_START = "2024-01-05"


def _yt(rows, iid, title, channel, watches, extra=None):
    rows.append({"id": iid, "platform": "youtube", "caption": title, "channel": channel,
                 "events": [("watch", w) for w in watches] + list(extra or [])})


def rows():
    out = []
    n = [0]

    def nid(p):
        n[0] += 1
        return f"{p}{n[0]:03d}"
    # ---- October 2026 (16 videos) ----
    blender_oct = ["Blender donut, the easy way", "Blender lighting basics", "Blender geometry nodes intro",
                   "Blender sculpting for beginners", "Blender camera tricks"]
    days = ["2026-10-01T14:00:00+00:00", "2026-10-05T15:00:00+00:00", "2026-10-09T16:00:00+00:00",
            "2026-10-14T17:00:00+00:00", "2026-10-30T13:00:00+00:00"]
    for t, d in zip(blender_oct, days):
        _yt(out, nid("y"), t, "Pixel Forge", [d])
    # the one video watched three times (September and twice in October): counted once in October
    _yt(out, "y_rewatch", "Blender render settings explained", "Pixel Forge",
        ["2026-09-03T12:00:00+00:00", "2026-10-02T12:00:00+00:00", "2026-10-20T12:00:00+00:00"])
    cook_oct = [("Cooking rice in one pot", "2026-10-03T18:00:00+00:00"),
                ("Weeknight cooking: lentil soup", "2026-10-11T18:00:00+00:00"),
                ("Knife skills for cooking fast", "2026-10-22T18:00:00+00:00"),
                ("Sunday bread bake", "2026-10-30T15:00:00+00:00")]
    for t, d in cook_oct:
        _yt(out, nid("y"), t, "Kettle & Cast", [d])
    for t, d in [("Three chords, a hundred songs", "2026-10-06T20:00:00+00:00"),
                 ("Fingerstyle warmups", "2026-10-16T20:00:00+00:00"),
                 ("Strumming patterns", "2026-10-26T20:00:00+00:00")]:
        _yt(out, nid("y"), t, "Chord Garden", [d])
    for t, d in [("Color grading a night scene", "2026-10-08T21:00:00+00:00"),
                 ("Color grading: matching two cameras", "2026-10-31T02:30:00+00:00")]:   # 30 Oct, 22:30 New York
        _yt(out, nid("y"), t, "Grade Lab", [d])
    _yt(out, nid("y"), "Soldering a tiny radio", "Loose Wires", ["2026-10-12T10:00:00+00:00"],
        extra=[("like", "2026-10-12T10:20:00+00:00")])
    # ---- September 2026 (10 videos, the rewatch above among them) ----
    for i in range(5):
        _yt(out, nid("y"), f"Cooking pasta sauce part {i + 1}" if i < 2 else f"Pan sauce lesson {i + 1}",
            "Kettle & Cast", [f"2026-09-{5 + i * 4:02d}T18:00:00+00:00"])
    for i in range(3):
        _yt(out, nid("y"), f"Chord shapes lesson {i + 1}", "Chord Garden", [f"2026-09-{6 + i * 5:02d}T20:00:00+00:00"])
    _yt(out, nid("y"), "Blender materials in ten minutes", "Pixel Forge", ["2026-09-21T14:00:00+00:00"],
        extra=[("like", "2026-09-21T14:30:00+00:00")])
    # ---- 2025 (11 videos) ----
    for i in range(6):
        _yt(out, nid("y"), f"Cooking for one, episode {i + 1}", "Kettle & Cast",
            [f"2025-{2 + i:02d}-14T18:00:00+00:00"])
    for i in range(4):
        _yt(out, nid("y"), f"Barre chords, week {i + 1}", "Chord Garden", [f"2025-{3 + i * 2:02d}-02T20:00:00+00:00"])
    _yt(out, nid("y"), "Blender first steps 2025", "Pixel Forge", ["2025-11-20T14:00:00+00:00"],
        extra=[("playlist", "2025-11-20T14:05:00+00:00")])
    # ---- 2024 (6 videos) ----
    _yt(out, "y_first", "A beginner multimeter guide", "Loose Wires", [YT_START + "T15:00:00+00:00"])
    _yt(out, "y_firstcook", "Cooking rice the easy way", "Kettle & Cast", ["2024-02-10T18:00:00+00:00"])
    _yt(out, nid("y"), "Cooking eggs three ways", "Kettle & Cast", ["2024-03-02T18:00:00+00:00"])
    _yt(out, nid("y"), "Cooking with cast iron", "Kettle & Cast", ["2024-03-09T18:00:00+00:00"])
    _yt(out, nid("y"), "Open chords for total beginners", "Chord Garden", ["2024-05-01T20:00:00+00:00"])
    _yt(out, nid("y"), "Hum-free guitar cables", "Loose Wires", ["2024-07-04T15:00:00+00:00"])
    # ---- Instagram ----
    ig = [("Blender shortcut cheat sheet", "pixelforge.ig", [("save", "2026-10-02T12:00:00+00:00")]),
          ("Slow cooking ragu recipe", "kettle.cast", [("save", "2026-10-07T12:00:00+00:00")]),
          ("Guitar pedal board tour", "chord.garden", [("collection", "2026-10-10T12:00:00+00:00")]),
          ("Studio desk setup", "deskdaily", [("share_self", "2026-10-15T12:00:00+00:00")]),
          ("Funny cat reel", "catclips", [("like", "2026-10-04T12:00:00+00:00")]),
          ("Latte art in slow motion", "milkfoam", [("like", "2026-10-09T12:00:00+00:00")]),
          ("Cooking hack with a fork", "kettle.cast", [("like", "2026-09-12T12:00:00+00:00")]),
          ("Blender speed sculpt reel", "pixelforge.ig", [("watch", "2026-10-13T12:00:00+00:00")]),
          ("Paper plane fold", "foldit", [("watch", "2026-08-01T12:00:00+00:00")])]
    for cap, handle, ev in ig:
        out.append({"id": nid("i"), "platform": "instagram", "caption": cap, "handle": handle, "events": ev})
    # a friend's posts: never counted (rule 8), not even its watch
    out.append({"id": "i_friend", "platform": "instagram", "caption": "Blender cooking party at mine", "handle": "pal",
                "relation": "mutual", "events": [("save", "2026-10-08T12:00:00+00:00"),
                                                 ("watch", "2026-10-08T12:00:00+00:00")]})
    return out


def write(path, extra_rows=()):
    """Writes the planted library under `path` (a pathlib.Path); returns the path."""
    (path / "corpus").mkdir(parents=True, exist_ok=True)
    rs = rows() + list(extra_rows)
    with open(path / "corpus" / "items.jsonl", "w") as f:
        for r in rs:
            pd = {"owner_relation": r.get("relation", "none")}
            if r["platform"] == "youtube":
                vid = "v" + r["id"]
                pd.update(video_id=vid, owner_name=r["channel"], owner_handle="", duration_s=600,
                          watch_count=sum(1 for k, _ in r["events"] if k == "watch"), media_kind="video")
                url = f"https://www.youtube.com/watch?v={vid}"
            else:
                pd.update(owner_handle=r["handle"], media_kind="reel")
                url = f"https://www.instagram.com/reel/C{r['id']}/"
            f.write(json.dumps({"id": r["id"], "platform": r["platform"], "source_url": url, "caption": r["caption"],
                                "interaction_kinds": sorted({k for k, _ in r["events"]}), "platform_data": pd}) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        for r in rs:
            for k, at in r["events"]:
                f.write(json.dumps({"item_id": r["id"], "kind": k, "at": at}) + "\n")
    return path
