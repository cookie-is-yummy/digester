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
No model text reaches them but the verified sentences. Chart, items and outside lines are not rendered in this slice.
"""
from . import verify as V

PRIVATE_LINE = "Leaving out topics you keep private."
LIST_WORD = {"channels": "channels", "top": "areas and themes", "count": "totals", "changed": "changes",
             "compare_windows": "two windows", "first": "the first time", "last": "the last time", "day": "one day",
             "timeline": "periods", "items": "items", "search": "your saves", "learned": "your saved items"}
OFFER_TEMPLATES = {"exclude": "Without {label}?", "only": "Only {label}?", "length_long": "Only long videos?",
                   "length_any": "Any length?", "window": "And {window}?", "by_month": "By month?",
                   "examples": "Show some examples?"}
OFFERS_MAX = 2


def _cited_rid(verdict, code, ledger):
    if verdict is not None:
        for o in verdict.outcomes:
            if o.kept and o.rid:
                return o.rid
    if code and code.get("rid"):
        return code["rid"]
    return next(iter(ledger.by_rid), None)


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
    window = (meta.get("window_said") or "").split(",")[0].strip()
    parts = [lst, base] + ([window] if window else [])
    if meta.get("filters_said"):
        parts.append(str(meta["filters_said"]))
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


def build(ledger, verdict=None, code=None, form=None, also=()):
    """The answer that goes out. `verdict`: the verdict whose sentences are sent (the model's), or None when `code`
    (fallback.answer's dict) is sent; `also`: every verdict of the turn (the private line is OR'd over them all).
    -> {lead, points, scope_line, private_line, offers, text, rid, filtered}."""
    if not isinstance(ledger, V.Ledger):
        ledger = V.Ledger(ledger)
    if verdict is not None:
        lead = " ".join(o.sent for o in verdict.lead if o.kept and o.sent)
        points = [s for s in verdict.kept_text("point") if s]
    else:
        lead = (code or {}).get("lead") or ""
        points = list((code or {}).get("points") or [])
    private = bool(verdict is not None and verdict.private_line) or bool((code or {}).get("private_line")) or any(
        v.private_line for v in also if v is not None)
    rid = _cited_rid(verdict, code, ledger)
    res = ledger.get(rid) if rid else None
    filt = filtered(res)
    sline = scope_line(res) if filt else None
    offers = offers_of(form, ledger) if verdict is not None else []
    lines = [lead] if lead else []
    lines += ["- " + p for p in points]
    tail = [x for x in (sline, PRIVATE_LINE if private else None) if x]
    text = "\n".join(lines)
    if tail:
        text += "\n\n" + "\n".join(tail)
    if offers:
        text += "\n\n" + " · ".join(o["label"] for o in offers)
    return {"lead": lead, "points": points, "scope_line": sline, "private_line": private, "offers": offers,
            "text": text, "rid": rid, "filtered": filt}
