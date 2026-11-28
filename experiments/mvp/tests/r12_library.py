"""Round 12, D (DESIGN.md section 19.D): a made-up watch history with KNOWN themes, for the fact sheet's tests.

Every title, channel and handle here is invented. The clock is Sunday 22 November 2026 (New York); the YouTube record
ends on Friday 30 October 2026, Instagram's on 15 October 2026.

Themes (field / theme), each with its own made-up channel(s) and a made-up 24-dimension vector direction:
    gaming / minecraft builds   "Brick Realm"     2021 to 2022 heavy, a little in 2026
    gaming / speedruns          "Frame Perfect"   2021 to 2023
    gaming / clips              "Clip Factory"    Shorts (30 to 50 seconds, published 2025), October 2026
    art    / watercolor         "Wet Paper"       rising: 2025 and 2026
    art    / digital drawing    "Pixel Pencil"    2026, many in October 2026
    math   / calculus           "Limit Lane"      the summer of 2023, a few in 2026
    math   / number puzzles     "Odd Prime"       the summer of 2023
    cooking                     "Pan Theory"      every year, a little
    dating advice (SENSITIVE)   "Heart Notes"     2024: its name must never be shown
Saved and never watched: 3 watercolor videos in a playlist. Lengths: every video 600 seconds except the clips (30 to
50 s) and the drawing videos (1,500 s); 2 calculus videos have no answer (deleted).
"""
import json
from datetime import datetime, timedelta, timezone

DIM = 24
THEMES = {   # key: (field index, theme index, channel, title words, length_s)
    "mc": (0, 0, "Brick Realm", ["Minecraft castle build", "Minecraft redstone door", "Minecraft village makeover",
                                 "Minecraft survival base", "Minecraft tower build"], 600),
    "sr": (0, 1, "Frame Perfect", ["Speedrun world record attempt", "Any% speedrun route", "Speedrun glitch explained",
                                   "Speedrun race finals"], 600),
    "cl": (0, 2, "Clip Factory", ["Gaming clutch moment", "Funniest gaming fail", "Gaming clip of the day"], 40),
    "wc": (1, 0, "Wet Paper", ["Watercolor sunset painting", "Watercolor wet on wet", "Watercolor trees easy",
                               "Watercolor sky washes"], 600),
    "dd": (1, 1, "Pixel Pencil", ["Digital drawing hands", "Digital art shading", "Procreate portrait sketch",
                                  "Digital drawing lineart"], 1500),
    "ca": (2, 0, "Limit Lane", ["Calculus limits intro", "Calculus derivatives fast", "Integrals by parts",
                                "Calculus chain rule"], 600),
    "np": (2, 1, "Odd Prime", ["Number puzzle of primes", "A tricky number puzzle", "Prime spiral puzzle",
                               "Puzzle with magic squares"], 600),
    "co": (3, 0, "Pan Theory", ["Weeknight cooking pasta", "Cooking crispy rice", "Cooking tofu three ways"], 600),
    "da": (4, 0, "Heart Notes", ["Dating advice first date", "Relationship advice texting", "Dating mistakes"], 600),
}
TRUE_FIELD = {0: "gaming", 1: "art", 2: "math", 3: "cooking", 4: "dating"}


def _plan():
    """(theme key, ISO watch time) rows: how many videos of each theme in each stretch."""
    out = []

    def spread(key, n, start, days, hour=20):
        d0 = datetime.fromisoformat(start)
        for k in range(n):
            at = d0 + timedelta(days=(k * days) // max(n, 1), hours=(k % 3))
            out.append((key, at.replace(hour=(hour + k % 4) % 24, tzinfo=timezone.utc).isoformat()))
    spread("mc", 150, "2021-01-05T00:00:00", 600)
    spread("sr", 90, "2021-03-01T00:00:00", 800)
    spread("co", 40, "2021-02-01T00:00:00", 1800)
    spread("ca", 75, "2023-06-03T00:00:00", 85)
    spread("np", 60, "2023-06-05T00:00:00", 80)
    spread("da", 50, "2024-02-01T00:00:00", 200)
    spread("wc", 90, "2025-01-10T00:00:00", 600)
    spread("dd", 90, "2026-08-01T00:00:00", 88)
    spread("cl", 60, "2026-10-01T00:00:00", 29)
    spread("mc", 12, "2026-09-02T00:00:00", 50)
    spread("ca", 10, "2026-09-10T00:00:00", 40)
    spread("co", 30, "2026-10-02T00:00:00", 25)
    return out


def rows():
    out = []
    n = {}
    for key, at in _plan():
        f, t, ch, titles, length = THEMES[key]
        n[key] = n.get(key, 0) + 1
        k = n[key]
        iid = f"r{key}{k:03d}"
        title = f"{titles[k % len(titles)]} #{k}"
        out.append({"id": iid, "platform": "youtube", "caption": title, "channel": ch, "theme": key,
                    "length": None if (key == "ca" and k in (3, 7)) else length,
                    "published": "2025-03-01" if key == "cl" else "2020-01-01",
                    "events": [("watch", at)]})
    # the 30th of October 2026 (New York): two drawing videos, a clip and a cooking video watched that day
    day = [("dd", "Digital drawing on the 30th", "2026-10-30T14:00:00+00:00"),
           ("dd", "Digital art colour on the 30th", "2026-10-30T23:30:00+00:00"),
           ("cl", "Gaming clip on the 30th", "2026-10-30T16:00:00+00:00"),
           ("co", "Cooking soup on the 30th", "2026-10-31T01:00:00+00:00")]   # 30 Oct, 21:00 New York
    for k, (key, title, at) in enumerate(day, 1):
        f, t, ch, titles, length = THEMES[key]
        out.append({"id": f"rday{k}", "platform": "youtube", "caption": title, "channel": ch, "theme": key,
                    "length": length, "published": "2025-03-01" if key == "cl" else "2020-01-01",
                    "events": [("watch", at)]})
    # saved in a playlist and never watched
    for k in range(3):
        out.append({"id": f"rsave{k}", "platform": "youtube", "caption": f"Watercolor portrait lesson {k + 1}",
                    "channel": "Wet Paper", "theme": "wc", "length": 900, "published": "2020-01-01",
                    "events": [("playlist", f"2026-10-0{k + 3}T12:00:00+00:00")]})
    # Instagram: a few watched reels and saves (they end on 15 October 2026)
    for k in range(4):
        out.append({"id": f"rig{k}", "platform": "instagram", "caption": f"Watercolor reel {k + 1}",
                    "handle": "wetpaper.ig", "theme": "wc", "length": None, "published": None,
                    "events": [("watch", f"2026-10-1{k + 2}T12:00:00+00:00")]})
    return out


def vector(key, iid):
    """A made-up vector: the field's direction, the theme's, and a little noise (fixed by the id)."""
    import numpy as np
    f, t = THEMES[key][0], THEMES[key][1]
    import zlib
    rng = np.random.default_rng(zlib.crc32(iid.encode()))
    v = rng.normal(0, 0.12, DIM)
    v[f] += 1.0
    v[5 + f * 3 + t] += 0.7
    return v


def write(path, extra_rows=()):
    """The made-up library under `path` (a pathlib.Path), with its item vectors; returns the path."""
    import numpy as np
    (path / "corpus").mkdir(parents=True, exist_ok=True)
    rs = rows() + list(extra_rows)
    with open(path / "corpus" / "items.jsonl", "w") as f:
        for r in rs:
            pd = {"owner_relation": "none"}
            if r["platform"] == "youtube":
                vid = "v" + r["id"]
                pd.update(video_id=vid, owner_name=r["channel"], owner_handle="", media_kind="video",
                          watch_count=sum(1 for k, _ in r["events"] if k == "watch"))
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
    d = path / "corpus" / "emb" / "oai3l_1024"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ids.json").write_text(json.dumps([r["id"] for r in rs]))
    np.save(d / "emb.npy", np.asarray([vector(r["theme"], r["id"]) for r in rs], dtype=np.float16))
    return path


def fake_videos_list(rs=None):
    """A fake videos.list: the made-up lengths (an id with no length is not returned, like a deleted video)."""
    by = {"v" + r["id"]: r for r in (rs or rows()) if r["platform"] == "youtube"}
    calls = []

    def fetch(ids, key):
        calls.append(list(ids))
        items = []
        for v in ids:
            r = by.get(v)
            if r and r["length"]:
                m, s = divmod(r["length"], 60)
                items.append({"id": v, "contentDetails": {"duration": f"PT{m}M{s}S" if m else f"PT{s}S"},
                              "snippet": {"publishedAt": r["published"] + "T00:00:00Z"}})
        return {"items": items}
    fetch.calls = calls
    return fetch


NAMES = {"minecraft": ("Minecraft builds", ["gaming", "minecraft", "building"]),
         "speedrun": ("Speedruns", ["gaming", "speedrun"]),
         "gaming": ("Gaming clips", ["gaming", "clips"]),
         "watercolor": ("Watercolor painting", ["art", "painting", "watercolor"]),
         "digital": ("Digital drawing", ["art", "drawing", "digital art"]),
         "drawing": ("Digital drawing", ["art", "drawing", "digital art"]),
         "calculus": ("Calculus lessons", ["math", "calculus"]),
         "puzzle": ("Number puzzles", ["math", "puzzles"]),
         "cooking": ("Home cooking", ["cooking", "food"]),
         "dating": ("Dating advice", ["dating", "relationships"])}
FIELD_NAMES = {"minecraft": ("Gaming", ["gaming", "video games"]), "speedrun": ("Gaming", ["gaming"]),
               "gaming": ("Gaming", ["gaming"]), "watercolor": ("Art", ["art"]), "digital": ("Art", ["art"]),
               "drawing": ("Art", ["art"]), "calculus": ("Math", ["math"]), "puzzle": ("Math", ["math"]),
               "number": ("Math", ["math"]), "cooking": ("Cooking", ["cooking"]), "dating": ("Dating", ["dating"])}


CATEGORY = {"Minecraft builds": "gaming", "Speedruns": "gaming", "Gaming clips": "gaming", "Gaming": "gaming",
            "Watercolor painting": "art and design", "Digital drawing": "art and design", "Art": "art and design",
            "Calculus lessons": "math", "Number puzzles": "math", "Math": "math", "Home cooking": "food and cooking",
            "Cooking": "food and cooking", "Dating advice": "relationships", "Dating": "relationships"}


def fake_namer(calls=None):
    """A fake of the naming call: names each block by the first known word among its titles' words."""
    import re

    def pick(block, table):
        low = block.lower()
        best = None
        for w in table:
            c = len(re.findall(r"\b" + w, low))
            if c and (best is None or c > best[0]):
                best = (c, w)
        return table[best[1]] if best else ("Other things", [])

    def chat(system, user, purpose, prompt_version, person=None, **kw):
        if calls is not None:
            calls.append(purpose)
        blocks = re.split(r"\n\n(?=SUB-GROUP \d+)", user)
        fname, fwords = pick(blocks[0], FIELD_NAMES)
        groups = []
        for n, b in enumerate(blocks[1:], 1):
            name, words = pick(b, NAMES)
            groups.append({"n": n, "name": name, "words": words, "mixed": False, "category": CATEGORY.get(name, "other"),
                           "sensitive": name == "Dating advice"})
        return {"field": {"name": fname, "words": fwords, "mixed": False, "sensitive": False,
                          "category": CATEGORY.get(fname, "other")}, "groups": groups}, 0.0
    return chat
