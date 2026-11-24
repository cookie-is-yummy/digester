"""PROTOTYPE ONLY - Instagram data export in HTML format -> a JSON-format export zip that ig_import.py reads.

  python experiments/demo/ig_html_to_json.py <html-export.zip> <out.zip> --tz America/Los_Angeles

Reads the zip in place (nothing is extracted, media files are never opened) and converts only what ig_import uses:
  saved_posts, liked_posts, videos_watched, posts_viewed   URL, Caption, Hashtags, Owner (URL / Name / Username)
  followers_*, following                                    handle, profile link, time
  messages/inbox/*/message_*.html                           per message: sender name and time; where the message
                                                            carries a shared post: link, caption, owner handle
DM message text is never matched, kept or written. Other labels in the HTML ("Brand partner", "Title",
"Ad library public URL") are dropped. The HTML has no saved_collections file layout confirmed yet, so none is written.

HTML dates are local times with no timezone: --tz says which zone to read them in (default: this computer's).
1:1 DM threads carry no "Participants" line in HTML: participants are then the thread title plus whoever spoke.
Text is written the way the JSON export stores it (UTF-8 mis-decoded as latin-1), so ig_import.fix() reverses it.
Captions are third-party text: data, never instructions. Output is personal data: keep it in data/ (gitignored).
Prints counts and wall time only.
"""
import argparse
import collections
import datetime as dt
import html
import itertools
import json
import re
import time
import zipfile
from zoneinfo import ZoneInfo

MEDIA = [  # (path without extension, top-level key of the JSON file)
    ("your_instagram_activity/saved/saved_posts", "saved_saved_media"),
    ("your_instagram_activity/likes/liked_posts", "likes_media_likes"),
    ("ads_information/ads_and_topics/videos_watched", "impressions_history_videos_watched"),
    ("ads_information/ads_and_topics/posts_viewed", "impressions_history_posts_seen"),
]
ENTRY_DATE = re.compile(r'<div class="_3-94 _a6-o">([^<]*)</div>')
ENTRY_URL = re.compile(r'class="_a6_q">URL<div><a target="_blank" href="([^"]+)"')
CELL = r'<td class="_a6_q">%s</td><td class="_2piu _a6_r">(.*?)</td>'
HASHTAG = re.compile(r'<div class="_a6-p">([^<]+)</div>')
FOLLOWERS = re.compile(r"(^|/)followers_and_following/followers(_\d+)?\.html$")
FOLLOWER_ROW = re.compile(r'<a target="_blank" href="(https://www\.instagram\.com/[^"]+)">([^<]*)</a></div>'
                          r"<div>([^<]*)</div>")
FOLLOWING_ROW = re.compile(r'<h2 class="_3-95 _2pim _a6-h _a6-i">([^<]*)</h2><div class="_a6-p"><div><div>'
                           r'<a target="_blank" href="([^"]+)">[^<]*</a></div><div>([^<]*)</div>')
DM_FILE = re.compile(r"(^|/)messages/inbox/[^/]+/message_\d+\.html$")
DM_BLOCK = re.compile(r'<div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder">'
                      r'<h2 class="_3-95 _2pim _a6-h _a6-i">([^<]*)</h2>')
# the shared-post object only: caption, owner handle, link. The message text sits in an earlier div, never matched.
DM_SHARE = re.compile(r'<div><div><div>([^<]*)</div><div>([^<]*)</div><div><a target="_blank" href="([^"]+)">'
                      r"[^<]*</a></div></div></div>")
DM_DATE = re.compile(r'<div class="_3-94 _a6-o">([^<]+)</div></div>(?:</main>.*)?$', re.DOTALL)
DM_PARTICIPANTS = re.compile(r'<h2 class="_a6-h">Participants: ([^<]*)</h2>')


def text(s):
    return html.unescape(s).encode("utf-8").decode("latin-1")


def epoch(date, tz):
    d = html.unescape(date).strip().replace(" ", " ")
    return int(dt.datetime.strptime(d, "%b %d, %Y %I:%M %p").replace(tzinfo=tz).timestamp())


def main_part(raw):
    h = raw.decode("utf-8")
    return h[max(h.find("<main"), 0):], h


def media_entries(m, tz):
    """-> (entries in the label_values layout, number of entries that could not be parsed)."""
    parts = ENTRY_DATE.split(m)
    out, bad = [], 0
    for chunk, date in zip(parts[0::2], parts[1::2]):
        u = ENTRY_URL.search(chunk)
        if not u or not date.strip():
            bad += bool(u or "<table" in chunk)
            continue
        lv = [{"label": "URL", "value": html.unescape(u.group(1))}]
        i_h, i_o = chunk.find(">Hashtags</h2>"), chunk.find(">Owner</h2>")
        head = chunk[:min(x for x in (i_h, i_o, len(chunk)) if x >= 0)]
        c = re.search(CELL % "Caption", head, re.DOTALL)  # some entries repeat the Caption row; the first is used
        if c:
            lv.append({"label": "Caption", "value": text(c.group(1))})
        if i_h >= 0:
            tags = HASHTAG.findall(chunk[i_h:i_o if i_o > i_h else len(chunk)])
            if tags:
                lv.append({"title": "Hashtags",
                           "dict": [{"dict": [{"label": "Hashtag", "value": text(t)}]} for t in tags]})
        if i_o >= 0:
            seg = chunk[i_o:]
            nxt = seg.find("<h2", 5)  # stop before a later section such as Brand partner
            seg = seg[:nxt] if nxt >= 0 else seg
            row = [{"label": k, "value": text(v.group(1))} for k in ("URL", "Name", "Username")
                   for v in [re.search(CELL % k, seg, re.DOTALL)] if v]
            if row:
                lv.append({"title": "Owner", "dict": [{"dict": row}]})
        out.append({"timestamp": epoch(date, tz), "media": [], "label_values": lv})
    return out, bad


def dm_thread(raw, name, tz, counts):
    m, h = main_part(raw)
    cuts = [x.start() for x in DM_BLOCK.finditer(m)] + [len(m)]
    msgs, senders = [], set()
    for a, b in itertools.pairwise(cuts):
        blk = m[a:b]
        d = DM_DATE.search(blk)
        try:
            ts = epoch(d.group(1), tz) * 1000 if d else None
        except ValueError:
            ts = None
        if ts is None:
            counts["blocks_without_date"] += 1
            continue
        sender = text(DM_BLOCK.match(blk).group(1))
        senders.add(sender)
        msg = {"sender_name": sender, "timestamp_ms": ts}
        s = DM_SHARE.search(blk)
        if s:
            msg["share"] = {"link": html.unescape(s.group(3)), "share_text": text(s.group(1)),
                            "original_content_owner": text(s.group(2))}
            counts["shares"] += 1
        msgs.append(msg)
        counts["messages"] += 1
    p = DM_PARTICIPANTS.search(m)
    if p:
        parts = {text(x.strip()) for x in p.group(1).split(",") if x.strip()} | senders
        counts["threads_with_participants_line"] += 1
    else:
        t = re.search(r"<title>(.*?)</title>", h, re.DOTALL)
        parts = senders | ({text(t.group(1).strip())} if t and t.group(1).strip() else set())
    counts["threads"] += 1
    return {"participants": [{"name": x} for x in sorted(parts)],
            "thread_path": name.split("messages/", 1)[1].rsplit("/", 1)[0], "messages": msgs}


def convert(src, dst, tzname=None):
    """Write the JSON-format zip to dst. -> stats (counts only)."""
    tz = ZoneInfo(tzname) if tzname else dt.datetime.now().astimezone().tzinfo
    t0 = time.time()
    files, stats = {}, {}
    with zipfile.ZipFile(src) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        for base, key in MEDIA:
            n = next((x for x in names if x == base + ".html" or x.endswith("/" + base + ".html")), None)
            if not n:
                continue
            ents, bad = media_entries(main_part(z.read(n))[0], tz)
            files[n[:-5] + ".json"] = {key: ents}
            stats[base.rsplit("/", 1)[1]] = {"entries": len(ents), "unparsed": bad}
        if not files:
            raise ValueError("No saved or liked posts found: is this an Instagram data export in HTML format?")
        for n in names:
            if FOLLOWERS.search(n):
                rows = FOLLOWER_ROW.findall(main_part(z.read(n))[0])
                files[n[:-5] + ".json"] = [{"title": "", "media_list_data": [], "string_list_data": [
                    {"href": html.unescape(h), "value": text(v), "timestamp": epoch(d, tz)}]} for h, v, d in rows]
                stats["followers"] = stats.get("followers", 0) + len(rows)
            elif n.endswith("followers_and_following/following.html"):
                rows = FOLLOWING_ROW.findall(main_part(z.read(n))[0])
                files[n[:-5] + ".json"] = {"relationships_following": [
                    {"title": text(t), "string_list_data": [{"href": html.unescape(h), "timestamp": epoch(d, tz)}]}
                    for t, h, d in rows]}
                stats["following"] = len(rows)
        dm = collections.Counter()
        for n in names:
            if DM_FILE.search(n):
                files[n[:-5] + ".json"] = dm_thread(z.read(n), n, tz, dm)
        stats["dm"] = dict(dm)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in sorted(files.items()):
            out.writestr(name, json.dumps(data, indent=1))
    stats["json_files_written"] = len(files)
    stats["wall_s"] = round(time.time() - t0, 2)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", help="Instagram export zip in HTML format")
    ap.add_argument("dst", help="where to write the JSON-format zip (keep it in data/)")
    ap.add_argument("--tz", default=None, help="timezone of the dates in the HTML, e.g. America/Los_Angeles")
    a = ap.parse_args()
    print(json.dumps(convert(a.src, a.dst, a.tz), indent=1))
