"""A test helper: a fact sheet wrapped in the result envelope of SPEC 2.3 (brain/results.py is built on another
branch; this is the shape it writes, for the verifier's tests and eval/convert_insight_cases.py). Made-up data only."""
import copy
import re

from mvp import insight as I

_NEUTRAL = str.maketrans({"[": "(", "]": ")", "{": "(", "}": ")", "<": "‹", ">": "›"})
TITLE_MAX, TEXT_MAX = 90, 200


def _refs(o, rid, path=""):
    """Every list row gets its ref; area rows get change_pts; third-party text is clipped and neutralised."""
    third = False
    if isinstance(o, dict):
        for k, v in list(o.items()):
            p = (path + "." if path else "") + k
            if k in ("title", "text") and isinstance(v, str):
                n = TITLE_MAX if k == "title" else TEXT_MAX
                o[k] = v.translate(_NEUTRAL)[:n]
                third = True
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    if isinstance(x, dict):
                        x["ref"] = f"{rid}.{p}[{i}]"
                        if k in ("areas", "top_areas") and isinstance(x.get("change_vs_previous"), (int, float)):
                            x["change_pts"] = round(float(x["change_vs_previous"]) * 100, 1)
                        third |= _refs(x, rid, f"{p}[{i}]")
            elif isinstance(v, dict):
                third |= _refs(v, rid, p)
    return third


def meta_of(sheet, **over):
    b = I.bases(sheet)
    f = sheet.get("filters") or {}
    said = []
    if f.get("topic"):
        said.append(f"only {f['topic']}")
    if f.get("without_shorts"):
        said.append("without Shorts (only long videos)")
    m = {"window_said": (sheet.get("window") or {}).get("words") or "",
         "base": "of " + (b["opened"] if b else "what you opened"),
         "filters_said": ", ".join(said), "resolved": {}, "order": "most", "complete": True,
         "rows_total": len(sheet.get("channels") or sheet.get("themes") or []),
         "hidden": {"sensitive": 0, "friends": 0, "rank_hidden_above": False},
         "notes": [], "third_party_text": False}
    m.update(over)
    return m


def envelope(rid, tool, sheet, shown=True, **meta):
    """`sheet` as a tool returns it: insight.shown(sheet) minus so_what_candidates and offers, each row with its ref."""
    s = I.shown(sheet) if shown else copy.deepcopy(sheet)
    s = {k: copy.deepcopy(v) for k, v in s.items() if k not in ("so_what_candidates", "offers")}
    third = _refs(s, rid)
    m = meta_of(s, **meta)
    m["third_party_text"] = bool(third)
    return {"rid": rid, "tool": tool, "meta": m, "sheet": s, "cost_usd": 0.0, "took_ms": 1}


def items_envelope(rid, tool, rows, **meta):
    """A result that is not a sheet (search, an item list): rows of items."""
    s = {"items": copy.deepcopy(rows)}
    third = _refs(s, rid)
    m = {"window_said": meta.pop("window_said", ""), "base": "", "filters_said": "", "resolved": {}, "order": "most",
         "complete": True, "rows_total": len(rows), "hidden": {"sensitive": 0, "friends": 0,
                                                              "rank_hidden_above": False},
         "notes": [], "third_party_text": bool(third)}
    m.update(meta)
    return {"rid": rid, "tool": tool, "meta": m, "sheet": s, "cost_usd": 0.0, "took_ms": 1}


def tool_of(sheet):
    k = sheet.get("kind")
    return {"top": "breakdown", "channels": "breakdown", "count": "breakdown", "changed": "changes",
            "compare_windows": "compare", "compare": "compare", "first": "first_last", "last": "first_last",
            "day": "items", "timeline": "timeline", "compare_topics": "breakdown"}.get(k, "breakdown")


def neutral(s):
    return re.sub(r"\s+", " ", str(s).translate(_NEUTRAL))
