"""PROTOTYPE ONLY - the brain's result envelope (design/brain_v1/SPEC.md 2.1, 2.3), step 1.

Every read tool returns one envelope: {"rid", "tool", "meta", "sheet", "cost_usd", "took_ms"}. `sheet` is a fact sheet
as the model reads it (insight.shown, so the checks of round 12 read it unchanged) with code's so-whats and offers
removed, every list row carrying its `ref` (the path of the row: "r1.channels[0]"), every area row its `change_pts`,
and every string neutralised: third-party text (titles, captions, channel names) can never forge a marker, a slot or a
tag, nor carry a link or an address. Code only: no model, no network.
"""
import json
import re

from .. import insight

# what the model never sees of a sheet: code's old so-whats (never parroted), the offers, and the parts meta carries
DROPPED = ("so_what_candidates", "offers", "ranked", "hidden", "built_s", "versions")
TITLE_MAX, TEXT_MAX, NAME_MAX = 90, 200, 90
RESULT_CHARS = 6000          # about 1,500 tokens (4 characters a token): rows are cut beyond it
CUT_ORDER = ("items", "channels", "themes", "periods", "areas", "topics", "fields", "names", "points")
_SWAP = str.maketrans({"[": "(", "]": ")", "{": "(", "}": ")", "<": "‹", ">": "›"})
URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[a-z0-9.-]+\.(?:com|net|org|io|ly|be|co|tv|me|gg|app)/\S*")
EMAIL = re.compile(r"(?i)\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PATH_KEYS = ("ref",)         # code-made paths (they hold brackets on purpose)


def neutral(text, limit=None):
    """Third-party text made safe to show a model: links and addresses out, brackets and braces swapped for round
    ones, angle brackets for look-alikes, clipped. "Hack {channels[0].items} [r1.totals.items]" -> "Hack
    (channels(0).items) (r1.totals.items)"."""
    if not isinstance(text, str):
        return text
    t = URL.sub("(link)", text)
    t = EMAIL.sub("(address)", t)
    t = t.translate(_SWAP)
    if limit and len(t) > limit:
        t = t[:limit - 1].rstrip() + "…"
    return t


def _limit(key):
    return TITLE_MAX if key == "title" else TEXT_MAX if key == "text" else None


def clean(o, key=None):
    """Every string leaf neutralised (titles clipped to 90 characters, `text` to 200), except code's own paths."""
    if isinstance(o, dict):
        return {k: (v if k in PATH_KEYS else clean(v, k)) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v, key) for v in o]
    if isinstance(o, str):
        return neutral(o, _limit(key))
    return o


def holds_third_party(o, key=None):
    """True when a sheet holds a title or a text field (the envelope says so: `third_party_text`)."""
    if isinstance(o, dict):
        return any(holds_third_party(v, k) for k, v in o.items())
    if isinstance(o, list):
        return any(holds_third_party(v, key) for v in o)
    return key in ("title", "text") and isinstance(o, str) and bool(o)


def shown(raw, limits=None):
    """insight.shown(raw), with lists longer than insight's own caps when `limits` asks ({"channels": 25}): the rows
    past a cap are trimmed by insight.shown too, a cap's worth at a time, so each row reads exactly as it would."""
    s = insight.shown(raw)
    for k, n in (limits or {}).items():
        if not isinstance(s.get(k), list):
            continue
        rows = raw.get(k) if isinstance(raw.get(k), list) else []
        cap = insight.SHOW.get(k)
        if cap and n > cap and len(rows) > cap:
            out = list(s[k])
            i = cap
            while i < min(len(rows), n):
                part = insight.shown(dict(raw, **{k: rows[i:i + cap]})).get(k)
                out += part if isinstance(part, list) else []
                i += cap
            s[k] = out
        s[k] = s[k][:n]
    return s


def _refs(o, path):
    """Each dict in a list gets its own path as `ref` ("r1.areas[0]", "r1.areas[0].themes[1]")."""
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, list):
                for n, row in enumerate(v):
                    if isinstance(row, dict):
                        here = f"{path}.{k}[{n}]"
                        _refs(row, here)
                        row["ref"] = here
            elif isinstance(v, dict) and k != "ref":
                _refs(v, f"{path}.{k}")
    return o


def change_pts(sheet):
    """Area rows carry their change as a fraction (facts._area_rows); `change_pts` says it in points, one decimal."""
    for r in sheet.get("areas") or []:
        if isinstance(r, dict) and isinstance(r.get("change_vs_previous"), (int, float)):
            r["change_pts"] = round(r["change_vs_previous"] * 100, 1)
    return sheet


def present(raw, rid, limits=None, drop=()):
    """The sheet as a tool returns it: shown, without code's so-whats and offers (and the keys in `drop`), each row
    with its ref, area rows with change_pts, every string neutralised."""
    s = shown(raw or {}, limits)
    # step 1 fix (the tools audit, B24, P02, F04, B30: new.channels [] where facts found new channels): insight.shown
    # empties some lists for its writer's style (new channels of a year or more are filler there); to the brain an
    # empty list says "none", so a list shown empty that facts filled is taken out (absent: not shown)
    for k in ("new", "stopped"):
        if isinstance(s.get(k), dict) and isinstance((raw or {}).get(k), dict):
            for kk, v in list(s[k].items()):
                if isinstance(v, list) and not v and (raw[k].get(kk) or []):
                    s[k].pop(kk)
    for k in tuple(DROPPED) + tuple(drop):
        s.pop(k, None)
    s = clean(s)
    change_pts(s)
    return _refs(s, rid)


def size(o):
    return len(json.dumps(o, ensure_ascii=False, default=str))


def cut_to_size(sheet, chars=RESULT_CHARS, keep=None):
    """Cut until the sheet is about 1,500 tokens: first the lists inside rows (a theme's channels, an area's themes),
    then the other rankings (longest first), the ranking asked for (`keep`) last. True when anything was cut. Rows
    are cut from the end, so what is left is the top of each list, its refs unchanged."""
    cut = False
    for inner_max in (2, 1, 0):
        if size(sheet) <= chars:
            return cut
        for k in CUT_ORDER:
            for row in sheet.get(k) or []:
                if isinstance(row, dict):
                    for kk, v in list(row.items()):
                        if isinstance(v, list) and len(v) > inner_max:
                            row[kk] = v[:inner_max]
                            cut = True
    while size(sheet) > chars:
        lists = [(len(sheet[k]), k) for k in CUT_ORDER if k != keep and isinstance(sheet.get(k), list)
                 and len(sheet[k]) > 1]
        if not lists and isinstance(sheet.get(keep), list) and len(sheet[keep]) > 1:
            lists = [(len(sheet[keep]), keep)]
        if not lists:
            break
        _n, k = max(lists)
        sheet[k] = sheet[k][:-1]
        cut = True
    return cut


def envelope(rid, tool, meta, sheet, cost_usd=0.0, took_ms=0, keep=None):
    meta = dict(meta)
    if sheet is not None:
        meta["truncated"] = bool(meta.get("truncated")) or cut_to_size(sheet, keep=keep)
        meta["third_party_text"] = holds_third_party(sheet)
    return {"rid": rid, "tool": tool, "meta": meta, "sheet": sheet, "cost_usd": round(float(cost_usd or 0.0), 6),
            "took_ms": int(took_ms)}


def error(message, tool=None, **extra):
    """A failed call, sent back to the model as a tool_result with is_error: the reason in code's words."""
    out = {"is_error": True, "error": message}
    if tool:
        out["tool"] = tool
    out.update(extra)
    return out


def has_url(o):
    """True when any string in `o` holds a link (a test's and a check's question)."""
    return bool(URL.search(json.dumps(o, ensure_ascii=False, default=str)))


# ================================================================ step 1 fixes of the tools audit
from .. import facts as _F  # noqa: E402

NO_BEFORE_NOTE = "No window before this one: new and stopped are not computed here."
NEW_NOTE = (f"New: at least {_F.NEW_MIN_ITEMS} items and {int(_F.NEW_MIN_SHARE * 100)}% of the window, with at most "
            f"{_F.NEW_PREV_MAX} before; a channel new in the window: first opened in it, {_F.NEW_CHANNEL_MIN} items or "
            f"more on {_F.NEW_CHANNEL_DAYS} days or more; stopped: the reverse.")


def honest(sheet, how="opened"):
    """Step 1 fixes of the tools audit, on every sheet result (the tools' presentation only; facts.sheet is
    unchanged): `new` and `stopped` of a sheet with no window before are not computed, so they are taken out rather
    than shown as empty lists ("nothing is new"); a channel's `first_watched` on a base of saves or likes is the first
    save (or like), so it is taken out there; and the floors that make a row "new" are said."""
    notes = []
    if not isinstance(sheet, dict) or not sheet.get("kind"):
        return notes
    if "new" in sheet or "stopped" in sheet:
        if not sheet.get("previous") and sheet.get("kind") not in ("compare_windows",):
            sheet.pop("new", None)
            sheet.pop("stopped", None)
            notes.append(NO_BEFORE_NOTE)
        else:
            notes.append(NEW_NOTE)
    fl = sheet.get("fields")
    if isinstance(fl, list) and len({(r or {}).get("name") for r in fl if isinstance(r, dict)}) < len(fl):
        # step 1 fix (the tools audit: two rows named "Gaming", 66 and 6): fields of one shown name are one row here
        # (a sentence citing "Gaming" means all of it); counts and shares of one base add up
        merged = {}
        for r in fl:
            if not isinstance(r, dict):
                continue
            m = merged.setdefault(r.get("name"), {k: v for k, v in r.items() if k != "ref"})
            if m is not r and m.get("_seen"):
                m["items"] = int(m.get("items", 0)) + int(r.get("items", 0))
                if isinstance(m.get("share"), (int, float)) and isinstance(r.get("share"), (int, float)):
                    m["share"] = round(m["share"] + r["share"], 4)
            m["_seen"] = True
        rows = sorted(merged.values(), key=lambda x: -int(x.get("items", 0)))
        rid = str((fl[0] or {}).get("ref", "r?.")).split(".", 1)[0]
        sheet["fields"] = [dict({k: v for k, v in r.items() if k != "_seen"}, ref=f"{rid}.fields[{k}]")
                           for k, r in enumerate(rows)]
    if how != "opened":
        def walk(o):
            if isinstance(o, dict):
                o.pop("first_watched", None)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(sheet)
    return notes
