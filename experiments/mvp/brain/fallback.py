"""The code lead (SPEC 4.6): what is said when the model's lead failed its repair, or the deadline is near, from the
results in hand. No model call.

For the first cited result (or the first result of the turn): when its sheet kind is one `insight.code_form` writes
and the result is not ordered by "least" (code_form's words assume "most": on a least-ordered sheet it says the
smallest row "led"), the answer of `insight.code_form(sheet)`, run through today's checks (`insight._check`, the
base words of `scoped`, the gate) and given its window's words (`insight.window_lead`). Otherwise one template per
tool, written with markers and passed through `verify.check_answer` before it is used, then sent with its markers
taken out. When nothing passes: the plain line of SPEC 3.10.
"""
from .. import insight as I
from . import verify as V

PLAIN = "I couldn't check an answer to that in time. Ask me again?"
CODE_FORM_KINDS = ("top", "channels", "count", "changed", "compare_windows", "compare_topics", "first", "last", "day",
                   "timeline")
LIST_OF = {"channels": "channels", "top": "themes", "count": None, "changed": "themes", "compare_windows": "themes",
           "timeline": "periods"}


def _first_result(ledger, cited=None):
    if cited and ledger.get(cited):
        return ledger.get(cited)
    return next(iter(ledger.by_rid.values()), None)


def _cited_rid(verdict):
    if verdict is None:
        return None
    for o in verdict.outcomes:
        if o.rid:
            return o.rid
    return None


def _from_code_form(res):
    """The code_form answer of a sheet, checked by today's checks, with its window's words; or None."""
    sheet = res.sheet_k
    if sheet.get("kind") not in CODE_FORM_KINDS or (res.meta or {}).get("order") == "least":
        return None
    try:
        form = I.code_form(sheet)
    except Exception:   # noqa: BLE001  (a sheet code_form cannot read gets a template)
        return None
    ans = form.get("answer") if isinstance(form, dict) else None
    if not isinstance(ans, str) or not ans.strip():
        return None
    facts = I.Facts(sheet)
    why, _n = I._check(ans, facts, maxlen=I.ANSWER_MAX)
    if why:
        return None
    ans = I.scoped(ans, sheet, answer=True)
    names, state, out = I._gate_names(sheet), {}, []
    for s in I._sentences(ans):
        g, gwhy = I.gate_sentence(s, sheet, names, state)
        if gwhy:
            return None
        out.append(g)
    ans = I.window_lead(" ".join(out), sheet)
    return ans if len(ans) <= I.ANSWER_MAX + 120 else None


def _window_words(res):
    w = ((res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or "").strip()
    return w.rstrip(",")


def templates(res):
    """Marker-form leads for a result, most specific first (each is verified before use)."""
    rid, sheet, tool = res.rid, res.sheet, res.tool
    w = _window_words(res)
    lead_in = (f"In {w}, " if w and not w.lower().startswith(("in ", "across ", "all ")) else
               (w[:1].upper() + w[1:] + ", " if w else ""))
    out = []
    order = (res.meta or {}).get("order") or "most"
    kind = sheet.get("kind")
    if res.is_sheet:
        f = sheet.get("filters") or {}
        noun = "long videos" if (f.get("without_shorts") or f.get("length") == "long") else (
            f"{f['topic']} videos" if isinstance(f.get("topic"), str) and f.get("topic") else "videos")
        tot = (sheet.get("totals") or {}).get("items")
        total_line = f"{lead_in}you opened {tot}[{rid}.totals.items] {noun}." if isinstance(tot, (int, float)) \
            else None
        if kind == "count" and total_line:
            out.append(total_line)
        lst = LIST_OF.get(kind, "themes")
        for key in ([lst] if lst else []) + ["channels", "themes", "areas"]:
            rows = sheet.get(key)
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
                continue
            nk = I._record_name_key(rows[0])
            if not nk or not isinstance(rows[0].get("items"), (int, float)):
                continue
            name, n = rows[0][nk], rows[0]["items"]
            if order == "least":
                out.append(f"{lead_in}{name}[{rid}.{key}[0]] was the one you opened least, with "
                           f"{n}[{rid}.{key}[0].items] {noun}.")
            else:
                out.append(f"{lead_in}{name}[{rid}.{key}[0]] led, with {n}[{rid}.{key}[0].items] {noun}.")
        if total_line and kind != "count":
            out.append(total_line)
        if w:
            out.append(f"{lead_in}here is what I counted.")
    elif tool == "search":
        out.append("Here's what I found in your saves.")
    elif tool == "learned":
        out.append("Here is what I found in what you saved.")
    elif tool == "find":
        out.append("Here is what I found in your library.")
    else:
        out.append((lead_in or "") + "here are the videos." if lead_in else "Here are the videos.")
    return out


def code_lead(ledger, verdict=None, turn=None, cited=None):
    """{"lead": text with no marker, "how": "code_form" | "template" | "plain", "rid": rid or None,
    "items": [item refs for cards]}."""
    if not isinstance(ledger, V.Ledger):
        ledger = V.Ledger(ledger)
    res = _first_result(ledger, cited or _cited_rid(verdict))
    if res is None:
        return {"lead": PLAIN, "how": "plain", "rid": None, "items": []}
    items = [f"{res.rid}.items[{i}]" for i, it in enumerate(res.sheet.get("items") or [])
             if isinstance(it, dict)][:V.ITEMS_MAX] if not res.is_sheet or res.sheet.get("kind") in I.ITEM_KINDS \
        else []
    if res.is_sheet:
        a = _from_code_form(res)
        if a:
            return {"lead": a, "how": "code_form", "rid": res.rid, "items": items}
    for t in templates(res):
        v = V.check_answer({"lead": t, "points": []}, ledger, turn or V.Turn())
        if v.lead_ok:
            return {"lead": " ".join(o.sent for o in v.lead), "how": "template", "rid": res.rid, "items": items}
    return {"lead": PLAIN, "how": "plain", "rid": res.rid, "items": []}


def answer(ledger, verdict, turn=None):
    """SPEC 4.5, row 3: the code lead with the points of the model's answer that passed."""
    lead = code_lead(ledger, verdict, turn)
    pts = verdict.kept_text("point") if verdict is not None and lead["how"] != "plain" else []
    return dict(lead, points=pts)
