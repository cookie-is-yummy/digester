"""Round 12, merge (DESIGN.md section 19): a made-up writer for the tests and the dry self-test.

`true_form(sheet)` fills the writer's form (insight_v4's shape) from a fact sheet by code, with sentences built only
from the sheet's own numbers and names, so code's check keeps them: it stands in for the model where a test or the
dry self-test needs the writer's path to run end to end with no model. It is not the writer: it says the obvious
things in fixed words. `fake_insight(user, system=None)` reads the sheet out of the writer's user message.
"""
import json


def sheet_of(user):
    return json.loads(user.split("<sheet>\n", 1)[1].rsplit("\n</sheet>", 1)[0])


def _pct(x):
    return round(float(x) * 100)


def _n(x):
    return f"{int(x):,}"


def true_form(sh):
    kind = sh.get("kind")
    tot = sh.get("totals") or {}
    themes = [t for t in sh.get("themes") or [] if t.get("name")]
    chans = [c for c in sh.get("channels") or [] if c.get("name")]
    topics = [t for t in sh.get("topics") or [] if t.get("name")]
    periods = [p for p in sh.get("periods") or [] if p.get("themes")]
    n = tot.get("items") or 0
    obs = []
    answer = None
    if kind == "compare_topics" and len(topics) == 2:
        a, b = sorted(topics, key=lambda t: -(t.get("items") or 0))
        if a["items"] == b["items"]:
            answer = f"As many {a['name']} as {b['name']}: {_n(a['items'])} videos each."
        else:
            answer = f"More {a['name']}: {_n(a['items'])} videos against {_n(b['items'])} on {b['name']}."
        if a.get("days") and b.get("days") and (a["days"], b["days"]) != (1, 1):
            obs.append({"text": f"You opened {a['name']} on {_n(a['days'])} days, {b['name']} on {_n(b['days'])}.",
                        "uses": ["topics"]})
        for t in (a, b):
            if t.get("channels"):
                c = t["channels"][0]
                obs.append({"text": f"{c['name']} is behind {_n(c['items'])} of the {_n(t['items'])} {t['name']} "
                                    f"videos.", "uses": ["topics"]})
    elif kind == "changed" and len(periods) >= 2:
        p0, p1 = periods[0], periods[-1]
        answer = (f"{p0['themes'][0]['name']} led {p0['label']}, and {p1['themes'][0]['name']} leads "
                  f"{p1['label']}.")
    elif kind == "channels" and len(chans) >= 2:
        answer = f"{chans[0]['name']} led with {_n(chans[0]['items'])} videos, ahead of {chans[1]['name']}."
    elif kind == "count" and topics:
        t = topics[0]
        answer = f"You opened {_n(t['items'])} {t['name']} videos."
        if t.get("days") and t["days"] not in (1, t["items"]):
            obs.append({"text": f"They came on {_n(t['days'])} different days.", "uses": ["topics"]})
        wt = (sh.get("window_totals") or {}).get("items")
        if wt and wt > t["items"]:
            obs.append({"text": f"That is {_n(t['items'])} of the {_n(wt)} videos you opened then.",
                        "uses": ["totals"]})
        if t.get("channels"):
            c = t["channels"][0]
            obs.append({"text": f"{c['name']} is behind " + ("all of them." if c["items"] == t["items"] else
                                                               f"{_n(c['items'])} of them."), "uses": ["topics"]})
    elif kind in ("first", "last") and (sh.get("items") or []) and (sh.get("items")[0].get("at")):
        d = sh["items"][0]["at"][:10]
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"]
        topic = (sh.get("filters") or {}).get("topic") or "these"
        answer = f"You {'first' if kind == 'first' else 'last'} opened a {topic} video on {dd} {months[m - 1]} {y}."
        for p in [p for p in sh.get("periods") or [] if p.get("items")][:2]:
            obs.append({"text": f"You opened {_n(p['items'])} of them in {p['label']}.", "uses": ["periods"]})
    elif themes:
        answer = f"Mostly {themes[0]['name']}, {_pct(themes[0]['share'])}% of what you opened."
    elif n:
        answer = f"You opened {_n(n)} videos."
    if kind == "channels":
        for c in chans[:3]:
            if c.get("days") and c["days"] != c.get("items"):
                obs.append({"text": f"You opened {c['name']} on {_n(c['days'])} different days.",
                            "uses": ["channels"]})
            elif c.get("length_hours") and c["length_hours"] >= 2:
                obs.append({"text": f"{c['name']}'s {_n(c['items'])} videos add up to about "
                                    f"{round(c['length_hours'])} hours.", "uses": ["channels"]})
    if kind == "count" and topics and topics[0].get("length_hours") and topics[0]["length_hours"] >= 2:
        obs.append({"text": f"Together they add up to about {round(topics[0]['length_hours'])} hours of video.",
                    "uses": ["topics"]})
    if kind in ("day", "first", "last") and not themes:
        for c in chans[:2]:
            if n and c.get("items"):
                obs.append({"text": f"{c['name']} is behind {_n(c['items'])} of the {_n(n)} videos.",
                            "uses": ["channels"]})
    for t in themes[:3]:
        cs = [c for c in t.get("channels") or [] if c.get("name")]
        if cs and t.get("items"):
            obs.append({"text": f"{cs[0]['name']} is behind {_n(cs[0]['items'])} of the {_n(t['items'])} "
                                f"{t['name']} videos.", "uses": ["themes"]})
    if tot.get("days_active") and n and kind not in ("day",) and tot["days_active"] not in (1, n):
        obs.append({"text": f"You opened {_n(n)} videos on {_n(tot['days_active'])} different days.",
                    "uses": ["totals"]})
    if tot.get("shorts") and n:
        obs.append({"text": f"{_n(tot['shorts'])} of the {_n(n)} were Shorts.", "uses": ["totals"]})
    so = None
    sv = ((sh.get("library") or {}).get("saved_not_opened") or [])
    if sv and sv[0].get("n"):
        so = f"You saved {_n(sv[0]['n'])} {sv[0]['theme']} videos you never opened; want them as a list?"
    return {"answer": answer, "observations": obs[:4], "so_what": so, "offers": (sh.get("offers") or [])[:2]}


def fake_insight(user, system=None):
    return true_form(sheet_of(user))
