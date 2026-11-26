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


LEVEL_OF = {"areas": "area", "themes": "theme", "channels": "channel"}


def levels(sheet):
    """mvp25 toolgaps 6 (N067.0: "Clip Factory led with 61" then "Digital drawing came next at 29", a channel's rank
    and a theme's set side by side): each row of a ranked list says its level (area, theme, channel), at the top of
    the sheet and in its new and stopped lists; a rank is within one level."""
    if not isinstance(sheet, dict):
        return sheet
    lists = [sheet] + [sheet[k] for k in ("new", "stopped") if isinstance(sheet.get(k), dict)]
    for holder in lists:
        for k, lv in LEVEL_OF.items():
            for row in holder.get(k) or []:
                if isinstance(row, dict):
                    row.setdefault("level", lv)
    return sheet


def size(o):
    return len(json.dumps(o, ensure_ascii=False, default=str))


def title_shown(text, limit=TITLE_MAX):
    """mvp26 toolfix2 4: a title as code puts it in its own lines (a card, a code lead): neutralised, its double quotes
    made single (so a quoted title stays one quotation), clipped to 90 characters. The same cut for every line."""
    if not isinstance(text, str):
        return text
    return neutral(" ".join(text.replace('"', "'").split()), limit)


# mvp26 toolfix2 5 (the timeline of run1 N001.1 held the latest 47 of 69 periods where it held 52 before the cells of
# mvp25 were added, and new themes on ranked sheets lost their first days): the cells added for insight are measured
# outside the size cap, so every list is cut exactly as before they were added; they ride on top up to EXTRA_CHARS
# (about 250 tokens), and only past that do they go (the parts of the day first, unless the sheet is a totals' sheet,
# where they are the answer)
EXTRA_CHARS = 1000


def _hold_extras(sheet):
    """Take the added cells out of the sheet: [(holder, key, value, kind)] to put back."""
    held = []
    new = sheet.get("new") if isinstance(sheet.get("new"), dict) else None
    for k in ("themes", "channels"):
        for row in (new or {}).get(k) or []:
            if isinstance(row, dict) and "first_watched" in row:
                held.append((row, "first_watched", row.pop("first_watched"), "first"))
    if new is not None and "small_channels" in new:
        held.append((new, "small_channels", new.pop("small_channels"), "small"))
    when = sheet.get("when") if isinstance(sheet.get("when"), dict) else None
    for k in ("parts_of_day", "busiest_weekdays", "busiest_weekday_opens"):
        if when is not None and k in when:
            held.append((when, k, when.pop(k), "parts" if k == "parts_of_day" else "weekday"))
    return held


def _put_back(sheet, held, chars):
    """The added cells back, then out again in order while the sheet is over `chars`. True when any went."""
    for holder, k, v, _kind in held:
        holder[k] = v
    if size(sheet) <= chars:
        return False
    order = ("parts", "first", "small", "weekday") if sheet.get("kind") != "count" else \
        ("first", "small", "parts", "weekday")
    went = False
    for kind in order:
        for holder, k, _v, kk in held:
            if kk == kind and k in holder:
                holder.pop(k)
                went = True
        if size(sheet) <= chars:
            break
    return went


def cut_to_size(sheet, chars=RESULT_CHARS, keep=None, newest=False):
    """Cut until the sheet is about 1,500 tokens: first the lists inside rows (a theme's channels, an area's themes),
    then the other rankings (longest first), the ranking asked for (`keep`) last. True when anything was cut. Rows
    are cut from the end, so what is left is the top of each list, its refs unchanged. `newest` (toolfix 9: a month
    timeline of all history kept January 2021 to December 2022 and lost October 2026): the list asked for is in time
    order, so it is cut from its start, and its rows' refs are made again (a ref is the row's own path). The cells
    added for insight are measured apart (mvp26 toolfix2 5: `_hold_extras`), so they never cost a row."""
    held = _hold_extras(sheet)
    cut = _cut_rows(sheet, chars, keep, newest)
    return _put_back(sheet, held, chars + EXTRA_CHARS) or cut


def _cut_rows(sheet, chars, keep, newest):
    cut = False
    for inner_max in (2, 1, 0):
        if size(sheet) <= chars:
            return cut
        for k in CUT_ORDER:
            for row in sheet.get(k) or []:
                if isinstance(row, dict):
                    for kk, v in list(row.items()):
                        if isinstance(v, list) and len(v) > inner_max:
                            if newest and not inner_max:
                                # toolfix 9: a period's list cut to nothing is taken out (absent: not shown; an
                                # empty list would say "none"), so more periods fit
                                row.pop(kk)
                            else:
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
        if newest and k == keep:
            sheet[k] = sheet[k][1:]
            head = str((sheet[k][0] or {}).get("ref", "")).split(".", 1)[0] if sheet[k] else ""
            if head:
                _refs({k: sheet[k]}, head)
        else:
            sheet[k] = sheet[k][:-1]
        cut = True
    return cut


def drop_extras(sheet, chars=RESULT_CHARS):
    """mvp25 toolgaps 6: the cells this round added for insight (a new row's first day, the parts of the day) never cost
    a row: on a sheet over its size they go first, so its rows are cut exactly as before; but a totals' sheet ("count")
    keeps its parts of the day, which cost its ranked lists a row or two. True when any went."""
    if size(sheet) <= chars:
        return False
    went = False
    for k in ("themes", "channels"):
        for row in ((sheet.get("new") or {}).get(k) or []) if isinstance(sheet.get("new"), dict) else []:
            if isinstance(row, dict) and row.pop("first_watched", None) is not None:
                went = True
    if size(sheet) > chars and sheet.get("kind") != "count" and isinstance(sheet.get("when"), dict) and \
            sheet["when"].pop("parts_of_day", None) is not None:
        # (a totals' sheet keeps them: there the parts of the day are the answer and its ranked lists are extra)
        went = True
    return went


def envelope(rid, tool, meta, sheet, cost_usd=0.0, took_ms=0, keep=None, newest=False):
    meta = dict(meta)
    if sheet is not None:
        meta["truncated"] = bool(meta.get("truncated")) or cut_to_size(sheet, keep=keep, newest=newest)
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


def answers(env):
    """mvp28 prep repair: a result there is an answer in: any result but an error, and but a name that found nothing (a
    find whose every name came back with no match, or a counting tool's result for a name of its scope that matched
    nothing, tools._unresolved; either with no option and no item holding its words). An ambiguous name's options are
    an answer (they ask back), as is a count of zero of what was asked."""
    if not isinstance(env, dict) or env.get("is_error"):
        return False

    def found(r):
        return not isinstance(r, dict) or r.get("status", r.get("error")) != "no_match" or bool(r.get("options")) or \
            bool(r.get("items_with_words") or 0)
    if "sheet" not in env and env.get("error") == "no_match":
        return found(env)   # a counting tool's unresolved name: no rows, only what the name matched
    if env.get("tool") != "find":
        return True
    rows = (env.get("sheet") or {}).get("names") or []
    return not rows or any(found(r) for r in rows)


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
    nw = sheet.get("new") if isinstance(sheet.get("new"), dict) else {}
    left = nw.pop("small_channels_left_out", None)
    if left:
        # mvp26 toolfix2 6: the channels under the floor are listed up to 5; how many more there are is said
        notes.append(f"new.small_channels lists 5 of them; {left} more channels were first opened in this window under "
                     "the floor and are not listed.")
    if isinstance(nw.get("channels"), list) and len(nw["channels"]) >= 5:
        notes.append("new.channels lists at most 5 channels: there may be more.")
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
