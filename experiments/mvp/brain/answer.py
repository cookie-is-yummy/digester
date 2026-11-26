"""PROTOTYPE ONLY - the answer that goes out (design/brain_v1/SPEC.md 3.6, 4.4, 4.5, 4.6; DECISIONS 3 and 4): a minimal
renderer for the thin live slice of step 2.

From a verdict that passed (the model's sentences, kept ones only, markers stripped by the verifier) or from the code
lead (brain/fallback.answer): the lead, the points, then code's own lines:
- the scope line, whenever the cited result was filtered (meta.filters_said: a name, a weekday, a platform or a length;
  or the sheet's without-Shorts filter): "Counted: channels · what you opened · October 2026 ... · without gaming
  (area)" (decision 3: only when something was guessed, filtered or clipped; this slice says it when filtered);
- the private line "Leaving out topics you keep private." whenever any verdict of the turn or the code lead asks for it
  (Verdict.private_line: any kept number of a result that left private items out; decision 4);
- the offers, each label from a fixed template (code writes them; the model only picks the kind and a ref).
No model text reaches them but the verified sentences. Chart and outside lines are not rendered in this slice.

mvp25 toolgaps 7 (N041.1, N044.1 and N049.0 named nothing: the item cards the model chose were not rendered): the
cards go out as the channel shows them, a short list of item lines built by code from the cited rows (title, channel
as a link to the item, the event and its day), never a model sentence; an ask-back goes out as code's question over
the cards of the result it is about. Code's limit line (mvp25 toolgaps 2): the export's watch-time line when a cited
result carries it, and, under a code lead only, what a refused call found the export does not hold.
"""
import re

from . import results as R
from . import verify as V

PRIVATE_LINE = "Leaving out topics you keep private."
LIST_WORD = {"channels": "channels", "top": "areas and themes", "count": "totals", "changed": "changes",
             "compare_windows": "two windows", "first": "the first time", "last": "the last time", "day": "one day",
             "timeline": "periods", "items": "items", "search": "your saves", "learned": "your saved items"}
OFFER_TEMPLATES = {"exclude": "Without {label}?", "only": "Only {label}?", "length_long": "Only long videos?",
                   "length_any": "Any length?", "window": "And {window}?", "by_month": "By month?",
                   "examples": "Show some examples?"}
OFFERS_MAX = 2
CARDS_MAX = 5
ASK_LINE = "Which one do you mean?"


def _cited_rid(verdict, code, ledger, cards=()):
    """The result the answer cites: a kept sentence's, else the code lead's, else the one result all the cards are of;
    else none (mvp26 toolfix2 2: the scope line fell back to the turn's first result, and Wet Paper cards went out
    under "Counted: ... Brick Realm: Brick Realm (channel)")."""
    if verdict is not None:
        for o in verdict.outcomes:
            if o.kept and o.rid:
                return o.rid
    if code and code.get("rid"):
        return code["rid"]
    rids = {str(c["ref"]).split(".", 1)[0] for c in cards}
    if len(rids) == 1:
        return rids.pop()
    if not cards and len(ledger.by_rid) == 1:
        # a turn with one result: the answer can be about no other (look2 D04.1, "Your Instagram areas for 2022 have
        # no rows to show.", keeps "Counted: ... 2022 · Instagram only")
        return next(iter(ledger.by_rid))
    return None


_ITEM_REF = re.compile(r"^(r\d+\.items\[\d+\])(?:\.\w+)?$")


def _cited_items(verdict):
    """The item rows the kept sentences cite ("r1.items[0]" of "r1.items[0].when"), in order."""
    out = []
    for o in (verdict.outcomes if verdict is not None else []):
        if not o.kept:
            continue
        for path in o.cells or {}:
            m = _ITEM_REF.match(str(path))
            if m and m.group(1) not in out:
                out.append(m.group(1))
    return out


def _between(form, ledger):
    """The item refs an ask-back is between (`ask_back.between`), those that name an item row of this turn; a question
    or a name written there is not a ref and gives no card."""
    ab = (form or {}).get("ask_back") if isinstance(form, dict) else None
    out = []
    for x in ((ab or {}).get("between") or []) if isinstance(ab, dict) else []:
        x = str(x).strip()
        if _ITEM_REF.match(x) and card(ledger, x) is not None and x not in out:
            out.append(x)
    return out


def filtered(res):
    """The result counted a scope: a name, weekday, platform or length line in meta, or the without-Shorts filter."""
    if res is None:
        return False
    meta = res.meta or {}
    f = (res.sheet.get("filters") or {}) if isinstance(res.sheet, dict) else {}
    return bool(meta.get("filters_said")) or bool(f.get("without_shorts")) or f.get("length") in ("long", "short")


def scope_line(res):
    """"Counted: <list> · <base> · <window> · <scope>" of one result (code's words only)."""
    meta = res.meta or {}
    kind = res.sheet.get("kind") if isinstance(res.sheet, dict) else None
    lst = LIST_WORD.get(kind or res.tool or "", res.tool or "results")
    base = (meta.get("base") or "of what you opened")
    base = base[3:] if base.startswith("of ") else base
    # (mvp20 fix: the recount found "all your history (5 January 2021 to 30 October 2026 · only gaming" with its
    # bracket left open, and "on Sundays · on Sundays": the export's end is cut out whole and a part is said once)
    import re
    window = re.sub(r",?\s*where your (?:youtube |instagram )?export ends", "", meta.get("window_said") or "").strip()
    window = window.split(", ")[0].strip() if "(" not in window else window
    if window.count("(") > window.count(")"):
        window += ")"
    parts = [lst, base] + ([window] if window else [])
    if meta.get("filters_said"):
        for p in str(meta["filters_said"]).split("; "):
            if p.strip() and p.strip().lower() not in window.lower():
                parts.append(p.strip())
    elif (res.sheet.get("filters") or {}).get("without_shorts"):
        parts.append("only videos known to be long")
    return "Counted: " + " · ".join(parts)


def _row_label(ledger, ref):
    if not ref or "." not in ref:
        return None
    rid, rest = ref.split(".", 1)
    r = ledger.get(rid)
    if r is None:
        return None
    try:
        row = V._resolve(r.sheet, rest)
    except (KeyError, AttributeError, IndexError, TypeError):
        return None
    if isinstance(row, dict):
        for k in ("name", "label", "title"):
            if isinstance(row.get(k), str) and row[k].strip():
                return row[k].strip()
    return None


def offers_of(form, ledger):
    """[{kind, ref, label}] from the form's offers: a label code writes, or the offer is dropped (a ref that names no
    row, window words that are missing)."""
    out = []
    for o in ((form or {}).get("offers") or [])[:3]:
        if not isinstance(o, dict):
            continue
        kind = o.get("kind")
        tpl = OFFER_TEMPLATES.get(kind)
        if not tpl:
            continue
        label = None
        if kind in ("exclude", "only"):
            label = _row_label(ledger, o.get("ref"))
            if not label:
                continue
            text = tpl.format(label=label)
        elif kind == "window":
            w = " ".join(str(o.get("window_words") or "").split())
            if not w or len(w) > 40 or any(c in w for c in "[]{}<>"):
                continue
            text = tpl.format(window=w)
        else:
            text = tpl
        if any(x["label"] == text for x in out):
            continue
        out.append({"kind": kind, "ref": o.get("ref"), "label": text})
        if len(out) >= OFFERS_MAX:
            break
    return out


def _learned_point(ledger, text):
    """SPEC 4.3 step 4: a kept point that is exactly a learned result's point marker ("[r1.points[0]]") goes out as that
    point's text, which the tool already traced to their own items (synth.check_points); anything else: None."""
    import re
    m = re.fullmatch(r"\s*\[(r\d+)\.points\[(\d+)\]\]\s*\.?\s*", text or "")
    if not m:
        return None
    r = ledger.get(m.group(1))
    if r is None or r.tool != "learned":
        return None
    pts = r.sheet.get("points") if isinstance(r.sheet, dict) else None
    k = int(m.group(2))
    if not isinstance(pts, list) or k >= len(pts) or not isinstance(pts[k], dict):
        return None
    t = " ".join(str(pts[k].get("text") or "").split())
    return t or None


def _row(ledger, ref):
    if not ref or "." not in ref:
        return None
    rid, rest = ref.split(".", 1)
    r = ledger.get(rid)
    if r is None:
        return None
    try:
        row = V._resolve(r.sheet, rest)
    except (KeyError, AttributeError, IndexError, TypeError):
        return None
    return row if isinstance(row, dict) else None


def card(ledger, ref, links=None):
    """One item line, built by code from the row a ref names: "Title · [Channel](link) · saved on 5 October 2026"."""
    from datetime import date
    from .. import history as Hm
    row = _row(ledger, ref)
    title = R.title_shown((row or {}).get("title"))
    if not isinstance(title, str) or not title.strip() or "." not in str(ref) or \
            not str(ref).split(".", 1)[1].startswith("items["):
        return None
    day = None
    try:
        day = Hm.day_words(date.fromisoformat(str(row.get("when") or "")[:10]))
    except ValueError:
        pass
    ev = row.get("how") if isinstance(row.get("how"), str) else None
    when = f"{ev} on {day}" if ev and day else f"on {day}" if day else ""
    ch = row.get("channel") if isinstance(row.get("channel"), str) else None
    url = links(row.get("item_id")) if (links and row.get("item_id")) else None
    chs = f"[{ch}]({url})" if ch and url else (ch or "")
    line = " · ".join(x for x in (title.strip(), chs, when) if x)
    return {"ref": ref, "title": title.strip(), "channel": ch, "url": url, "event": ev, "when": row.get("when"),
            "line": line}


def _cards(ledger, refs, links=None):
    out = []
    for ref in refs:
        c = card(ledger, ref, links)
        if c and all(x["ref"] != c["ref"] for x in out):
            out.append(c)
        if len(out) >= CARDS_MAX:
            break
    return out


def limit_lines(ledger, rid, code=None, limits=()):
    """Code's own limit lines: the watch-time line of a cited result (the prompt leaves it to code), and under a code
    lead what the turn's refused calls found the export does not hold (`limits`, tools.Turn.limits)."""
    from . import tools as TL
    out = []
    res = ledger.get(rid) if rid else None
    if res is not None and TL.WATCH_TIME_LINE in ((res.meta or {}).get("notes") or []):
        out.append(TL.WATCH_TIME_LINE)
    if code is not None and code.get("how") != "plain":
        out += [x for x in limits if isinstance(x, str) and x not in out]
    return out


def build(ledger, verdict=None, code=None, form=None, also=(), mode=None, links=None, limits=()):
    """The answer that goes out. `verdict`: the verdict whose sentences are sent (the model's), or None when `code`
    (fallback.answer's dict) is sent; `also`: every verdict of the turn (the private line is OR'd over them all);
    `mode`: the checker's mode (mvp24: in "cells" a code lead goes out with no point of the model's).
    `links`: item id -> its link (the cards' channel link); `limits`: the turn's limit lines (tools.Turn.limits).
    -> {lead, points, scope_line, private_line, offers, text, rid, filtered, cards, ask, limits}."""
    if not isinstance(ledger, V.Ledger):
        ledger = V.Ledger(ledger)
    cells = V.check_mode(mode).cells
    if verdict is not None:
        lead = " ".join(o.sent for o in verdict.lead if o.kept and o.sent)
        points = [s for s in (o.sent or _learned_point(ledger, o.text) for o in verdict.outcomes
                              if o.where == "point" and o.kept) if s]
    else:
        lead = (code or {}).get("lead") or ""
        # (mvp24, cells mode: the model's points were written for its own lead; under code's lead none goes out)
        points = [] if cells else list((code or {}).get("points") or [])
    private = bool(verdict is not None and verdict.private_line) or bool((code or {}).get("private_line")) or any(
        v.private_line for v in also if v is not None)
    # (mvp20 fix: the plain line counted nothing, so no scope line goes under it)
    plain = verdict is None and bool(code) and code.get("how") == "plain"
    # (mvp20 fix: a code lead keeps the offers the model picked; code writes every label)
    offers = offers_of(form, ledger) if (verdict is not None or code) else []
    # mvp25 toolgaps 7: the item cards (the model's picks, or the code lead's items) and an ask-back over them
    if verdict is not None:
        refs = [it.get("ref") for it in (verdict.items or []) if isinstance(it, dict) and it.get("kept")]
    else:
        refs = list((code or {}).get("items") or []) if not plain else []
    ask = bool((form or {}).get("ask_back")) and (verdict is not None or not plain)
    if ask:
        # mvp26 toolfix2 2 (the attack: an ask-back rendered every item of the cited result, or of the turn's first
        # result when the lead cited nothing, and never read `between`: 6 of 8 builds showed another result's cards):
        # the items it is between, else the answer's picks, else the items its kept sentences cite; else none
        refs = _between(form, ledger) or refs or (_cited_items(verdict) if verdict is not None else [])
    cards = _cards(ledger, refs, links)
    rid = _cited_rid(verdict, code, ledger, cards)
    res = ledger.get(rid) if rid else None
    filt = filtered(res)
    # (mvp26 toolfix2 2: the scope line says what the cited result counted; over cards of another result it would
    # read as theirs, so it goes out only when every card is of that result)
    own = all(str(c["ref"]).split(".", 1)[0] == rid for c in cards)
    sline = scope_line(res) if filt and not plain and own else None
    lim = limit_lines(ledger, rid, code if verdict is None else None, limits) if not plain else []
    lines = [lead] if lead else []
    lines += ["- " + p for p in points]
    lines += lim
    if cards:
        lines += ([ASK_LINE] if ask else []) + ["• " + c["line"] for c in cards]
    tail = [x for x in (sline, PRIVATE_LINE if private else None) if x]
    text = "\n".join(lines)
    if tail:
        text += "\n\n" + "\n".join(tail)
    if offers:
        text += "\n\n" + " · ".join(o["label"] for o in offers)
    return {"lead": lead, "points": points, "scope_line": sline, "private_line": private, "offers": offers,
            "text": text, "rid": rid, "filtered": filt, "cards": cards, "ask": bool(ask and cards), "limits": lim}
