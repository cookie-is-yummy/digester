"""Round 12, merge (DESIGN.md section 19): a made-up writer for the tests and the dry self-test (round 12, pass 2:
insight_v5's form, sheet paths in braces).

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
    """Round 12, pass 2 (T1): the form of insight_v5, sheet PATHS in braces that code fills ("{themes[0].name}"),
    never a typed number; the sentences read as they did when they were typed out."""
    kind = sh.get("kind")
    tot = sh.get("totals") or {}
    themes = [(k, t) for k, t in enumerate(sh.get("themes") or []) if t.get("name")]
    chans = [(k, c) for k, c in enumerate(sh.get("channels") or []) if c.get("name")]
    topics = [(k, t) for k, t in enumerate(sh.get("topics") or []) if t.get("name")]
    periods = [(k, p) for k, p in enumerate(sh.get("periods") or []) if p.get("themes")]
    n = tot.get("items") or 0
    obs = []
    answer = None
    if kind == "compare_topics" and len(topics) == 2:
        (ka, a), (kb, b) = sorted(topics, key=lambda t: -(t[1].get("items") or 0))
        if a["items"] == b["items"]:
            answer = f"As many {{topics[{ka}].name}} as {{topics[{kb}].name}}: {{topics[{ka}].items}} videos each."
        else:
            answer = (f"More {{topics[{ka}].name}}: {{topics[{ka}].items}} videos against {{topics[{kb}].items}} on "
                      f"{{topics[{kb}].name}}.")
        if a.get("days") and b.get("days") and (a["days"], b["days"]) != (1, 1):
            obs.append({"text": f"You opened {{topics[{ka}].name}} on {{topics[{ka}].days}} days, {{topics[{kb}].name}} "
                                f"on {{topics[{kb}].days}}.", "uses": ["topics"]})
        for k, t in ((ka, a), (kb, b)):
            if t.get("channels"):
                obs.append({"text": f"{{topics[{k}].channels[0].name}} is behind {{topics[{k}].channels[0].items}} of "
                                    f"the {{topics[{k}].items}} {{topics[{k}].name}} videos.", "uses": ["topics"]})
    elif kind == "changed" and len(periods) >= 2:
        (k0, p0), (k1, p1) = periods[0], periods[-1]
        answer = (f"{{periods[{k0}].themes[0].name}} led {{periods[{k0}].label}}, and {{periods[{k1}].themes[0].name}} "
                  f"leads {{periods[{k1}].label}}.")
    elif kind == "channels" and len(chans) >= 2:
        answer = (f"{{channels[{chans[0][0]}].name}} led with {{channels[{chans[0][0]}].items}} videos, ahead of "
                  f"{{channels[{chans[1][0]}].name}}.")
    elif kind == "count" and topics:
        k, t = topics[0]
        answer = f"You opened {{topics[{k}].items}} {{topics[{k}].name}} videos."
        if t.get("days") and t["days"] not in (1, t["items"]):
            obs.append({"text": f"They came on {{topics[{k}].days}} different days.", "uses": ["topics"]})
        wt = (sh.get("window_totals") or {}).get("items")
        if wt and wt > t["items"]:
            obs.append({"text": f"That is {{topics[{k}].items}} of the {{window_totals.items}} videos you opened then.",
                        "uses": ["totals"]})
        if t.get("channels"):
            c = t["channels"][0]
            obs.append({"text": f"{{topics[{k}].channels[0].name}} is behind " +
                        ("all of them." if c["items"] == t["items"] else f"{{topics[{k}].channels[0].items}} of them."),
                        "uses": ["topics"]})
    elif kind in ("first", "last") and (sh.get("items") or []) and (sh.get("items")[0].get("at")):
        topic = (sh.get("filters") or {}).get("topic") or "these"
        answer = f"You {'first' if kind == 'first' else 'last'} opened a {topic} video on {{items[0].at}}."
        for k, p in [(k, p) for k, p in enumerate(sh.get("periods") or []) if p.get("items")][:2]:
            obs.append({"text": f"You opened {{periods[{k}].items}} of them in {{periods[{k}].label}}.",
                        "uses": ["periods"]})
    elif themes and kind == "day":   # round 12, pass 2 (T10): a day's overview says how many
        k = themes[0][0]
        answer = f"You opened {{totals.items}} videos; {{themes[{k}].name}} led, at {{themes[{k}].share}} of them."
    elif themes:
        k = themes[0][0]
        answer = f"{{themes[{k}].name}} led, at {{themes[{k}].share}} of what you opened."
    elif n:
        answer = "You opened {totals.items} videos."
    if kind == "channels":
        for k, c in chans[:3]:
            if c.get("days") and c["days"] != c.get("items"):
                obs.append({"text": f"You opened {{channels[{k}].name}} on {{channels[{k}].days}} different days.",
                            "uses": ["channels"]})
            elif c.get("shorts_share"):
                obs.append({"text": f"{{channels[{k}].shorts_share}} of {{channels[{k}].name}}'s videos were Shorts.",
                            "uses": ["channels"]})
            elif c.get("days") and c.get("theme"):
                obs.append({"text": f"{{channels[{k}].name}}, all {{channels[{k}].theme}}, came on {{channels[{k}].days}} "
                                    f"days.", "uses": ["channels"]})
    if kind in ("day", "first", "last") and not themes:
        for k, c in chans[:2]:
            if n and c.get("items"):
                obs.append({"text": f"{{channels[{k}].name}} is behind {{channels[{k}].items}} of the {{totals.items}} "
                                    f"videos.", "uses": ["channels"]})
    for k, t in themes[:3]:
        cs = [c for c in t.get("channels") or [] if c.get("name")]
        if cs and t.get("items"):
            obs.append({"text": f"{{themes[{k}].channels[0].name}} is behind {{themes[{k}].channels[0].items}} of the "
                                f"{{themes[{k}].items}} {{themes[{k}].name}} videos.", "uses": ["themes"]})
    if tot.get("days_active") and n and kind not in ("day",) and tot["days_active"] not in (1, n):
        obs.append({"text": "You opened {totals.items} videos on {totals.days_active} different days.",
                    "uses": ["totals"]})
    if tot.get("shorts") and n:
        obs.append({"text": "{totals.shorts} of the {totals.items} were Shorts.", "uses": ["totals"]})
    so = None
    cands = [c for c in sh.get("so_what_candidates") or [] if c.get("kind") in ("saved", "lapsed_saves")]
    if cands:
        k = (sh.get("so_what_candidates") or []).index(cands[0])
        so = {"pick": cands[0]["key"], "text": f"You saved {{so_what_candidates[{k}].n}} {{so_what_candidates[{k}].theme}} "
                                              f"videos you never opened; want them as a list?"}
    return {"answer": answer, "observations": obs[:4], "so_what": so, "offers": (sh.get("offers") or [])[:2]}


def fake_insight(user, system=None):
    return true_form(sheet_of(user))
