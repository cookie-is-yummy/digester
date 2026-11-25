"""The code lead (SPEC 4.6): what is said when the model's lead failed its repair, or the deadline is near, from the
results in hand. No model call.

For the first cited result (or the first result of the turn): when its sheet kind is one `insight.code_form` writes
and the result is not ordered by "least" (code_form's words assume "most": on a least-ordered sheet it says the
smallest row "led"), the answer of `insight.code_form(sheet)`, run through today's checks (`insight._check`, the
base words of `scoped`, the gate) and given its window's words (`insight.window_lead`). Otherwise one template per
tool, written with markers and passed through `verify.check_answer` before it is used, then sent with its markers
taken out. When nothing passes: the plain line of SPEC 3.10.

Merge seam (the tools' real results): code_form is not used on a result the tools scoped (meta.filters_said: only,
without, a subject, a weekday, a platform) nor on a length-filtered sheet, because its words would leave the scope
out ("Clip Factory led" of only gaming); the templates say the scope, the base's verb ("you saved"), both windows of
a compare, and a first or a last by the item's day. On the brain library code_form gives no answer for a plain count,
a timeline, a compare or a tool-made first_last sheet (its first/last branch reads facts' own item rows and a topic):
those get a template.
"""
import re

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
    f = sheet.get("filters") or {}
    if V.scope_parts(res) or f.get("without_shorts") or f.get("length") in ("long", "short"):
        # merge seam: a result the tools scoped by a name, a weekday or a platform keeps its scope in meta, not in
        # the sheet's filters, so code_form's words would leave it out ("Clip Factory led" of only gaming); and its
        # lead of a length-filtered sheet ranks without saying "long" ("Pan Theory led" of the long videos only)
        return None
    if ((res.meta or {}).get("base") or "of what you opened") != "of what you opened":
        # mvp20 tune (the live run's I04, I05: "mostly art and design (50% of what you opened), then food and cooking
        # (50%)" of a breakdown of SAVES, a wrongly based lead that went out, and "mostly" on a 50/50 tie): code_form
        # writes "of what you opened" whatever the tools counted; a result of saves, likes or everything gets a
        # template, which says the base's own verb
        return None
    if sheet.get("kind") == "changed" and not all(re.fullmatch(r"(?:19|20)\d\d", str((p or {}).get("label") or ""))
                                                  for p in sheet.get("periods") or [{}]):
        # step 1 fix (the verifier audit's code leads chg and chgy: "gaming has led every year since Oct 2026, at about
        # 51%" of this year by month, where art and design led): code_form's changed answer reads its periods as years;
        # the tools' changes over months get a template
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
    # window_lead opens with the window's bare words ("October 2026 up to 30 October 2026, ..., Clip Factory led"):
    # the fallback says them as a lead does ("In October 2026 up to ...")
    w = ((sheet.get("window") or {}).get("words") or "").strip().rstrip(",")
    cap = w[:1].upper() + w[1:]
    if cap and ans.startswith(cap + ", ") and lead_in(w) != cap + ", ":
        ans = lead_in(w) + ans[len(cap) + 2:]
    return ans if len(ans) <= I.ANSWER_MAX + 120 else None


def _window_words(res):
    w = ((res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or "").strip()
    return w.rstrip(",")


_OWN_PREP = re.compile(r"^(?:in|on|since|from|between|this|last|during|over|across|up to)\b", re.I)
_WEEKDAY = re.compile(r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
VERB = {"of what you opened": ("opened", "videos", "video"), "of what you liked": ("liked", "items", "item"),
        "of what you saved": ("saved", "items", "item"),
        "of everything you opened, liked or saved": ("opened, liked or saved", "items", "item")}
_FORM = re.compile(r" \((?:area|theme|channel|collection)\)$")
_LENGTH_PARTS = ("only videos known to be long", "only Shorts and reels")


def lead_in(w):
    """The window's words as the opening of a lead (merge seam: the tools' window words start with "since", "this
    year", a weekday or "the 4 weeks", not only a month): "In October 2026, ", "Since 1 January 2020 ...", "On Friday
    30 October 2026, ...", "In the 4 weeks up to ..."."""
    if not w:
        return ""
    if _WEEKDAY.match(w):
        return "On " + w + ", "
    if _OWN_PREP.match(w):
        return w[:1].upper() + w[1:] + ", "
    return "In " + w + ", "


def _scope_clause(res):
    """The tools' scope said in the sentence (" (only gaming)", " (without Minecraft builds, on Mondays)"): the length
    lines are said by the noun ("long videos"), first_last's subject by its own template."""
    said = (res.meta or {}).get("filters_said")
    if not isinstance(said, str) or not V.scope_parts(res):
        return ""
    parts = [_FORM.sub("", p.strip()) for p in said.split("; ") if p.strip() and p.strip() not in _LENGTH_PARTS
             and ":" not in p]
    return " (" + ", ".join(parts) + ")" if parts else ""


def _n(n, one, many):
    return one if n == 1 else many


def _day_words(when):
    d = V._as_d(str(when or "")[:10])
    return f"{d.day} {I.MONTHS[d.month - 1].capitalize()} {d.year}" if d else None


def templates(res):
    """Marker-form leads for a result, most specific first (each is verified before use)."""
    rid, sheet, tool = res.rid, res.sheet, res.tool
    w = _window_words(res)
    lead = lead_in(w)
    out = []
    order = (res.meta or {}).get("order") or "most"
    kind = sheet.get("kind")
    verb, noun, noun1 = VERB.get((res.meta or {}).get("base") or "", VERB["of what you opened"])
    scope = _scope_clause(res)
    if res.is_sheet and kind in ("first", "last"):
        # first_last: the item's day (code_form needs facts' own item rows and a topic, which the tool's resolved
        # subject replaces); the window's core words ("In all your history") and the subject in their own words
        said = (res.meta or {}).get("filters_said") or ""
        subj = said.split(":", 1)[0].strip() if ":" in said else ""
        it0 = (sheet.get("items") or [None])[0]
        day = _day_words(it0.get("when")) if isinstance(it0, dict) else None
        core = re.split(r"[(,]", w)[0].strip()
        if subj and day:
            an = "an" if subj[:1].lower() in "aeiou" else "a"
            head = lead_in(core)
            if kind == "first":
                out.append(f"{head}you first {verb} {an} {subj} {noun1} on {day}[{rid}.items[0].when].")
            else:
                out.append(f"{head}the last {subj} {noun1} you {verb} was on {day}[{rid}.items[0].when].")
    if res.is_sheet:
        f = sheet.get("filters") or {}
        long_ = bool(f.get("without_shorts") or f.get("length") == "long")
        noun_ = (f"long {noun}" if long_ else
                 f"{f['topic']} {noun}" if isinstance(f.get("topic"), str) and f.get("topic") else noun)
        noun1_ = (f"long {noun1}" if long_ else
                  f"{f['topic']} {noun1}" if isinstance(f.get("topic"), str) and f.get("topic") else noun1)
        tot = (sheet.get("totals") or {}).get("items")
        total_line = (f"{lead}you {verb} {tot}[{rid}.totals.items] {_n(tot, noun1_, noun_)}{scope}."
                      if isinstance(tot, (int, float)) else None)
        prev = sheet.get("previous") or {}
        ptot, pw = prev.get("items"), (prev.get("words") or "").strip()
        if kind in ("compare_windows", "compare") and isinstance(tot, (int, float)) and \
                isinstance(ptot, (int, float)) and pw:
            # both windows of a compare result in one sentence (each count beside its own window's words)
            pin = pw if _OWN_PREP.match(pw) else "in " + pw
            out.append(f"{lead}you {verb} {tot}[{rid}.totals.items] {_n(tot, noun1_, noun_)}{scope}, and "
                       f"{ptot}[{rid}.previous.items] {pin}.")
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
                out.append(f"{lead}{name}[{rid}.{key}[0]] was the one you {verb} least, with "
                           f"{n}[{rid}.{key}[0].items] {_n(n, noun1_, noun_)}{scope}.")
            else:
                # (mvp20 tune: the base's verb said, "led what you saved", so a lead of saves never reads as opens)
                out.append(f"{lead}{name}[{rid}.{key}[0]] led what you {verb}, with {n}[{rid}.{key}[0].items] "
                           f"{_n(n, noun1_, noun_)}{scope}.")
        if total_line and kind != "count":
            out.append(total_line)
        if w:
            out.append(f"{lead}here is what I counted{scope}.")
    elif tool == "search":
        out.append("Here's what I found in your saves." if (sheet.get("how") or "saved") == "saved" else
                   "Here's what I found.")
    elif tool == "learned":
        out.append("Here is what I found in what you saved.")
    elif tool == "find":
        out.append("Here is what I found in your library.")
    else:
        out.append(lead + "here are the videos." if lead else "Here are the videos.")
    return out


def code_lead(ledger, verdict=None, turn=None, cited=None):
    """{"lead": text with no marker, "how": "code_form" | "template" | "plain", "rid": rid or None,
    "items": [item refs for cards], "private_line": bool}. `private_line` (SPEC 4.3 step 13, as Verdict.private_line):
    the lead ranks while a topic they keep private would have ranked above it, so code's scope line must add
    "Leaving out topics you keep private."."""
    if not isinstance(ledger, V.Ledger):
        ledger = V.Ledger(ledger)
    res = _first_result(ledger, cited or _cited_rid(verdict))
    if res is None:
        return {"lead": PLAIN, "how": "plain", "rid": None, "items": [], "private_line": False}
    items = [f"{res.rid}.items[{i}]" for i, it in enumerate(res.sheet.get("items") or [])
             if isinstance(it, dict)][:V.ITEMS_MAX] if not res.is_sheet or res.sheet.get("kind") in I.ITEM_KINDS \
        else []
    hidden_above = bool(((res.meta or {}).get("hidden") or {}).get("rank_hidden_above"))
    if res.is_sheet:
        a = _from_code_form(res)
        if a:
            # (step 1's close: as the verifier, any number of a result that left private items out asks for the line)
            hidden_n = int((((res.meta or {}).get("hidden") or {}).get("sensitive")) or 0)
            return {"lead": a, "how": "code_form", "rid": res.rid, "items": items,
                    "private_line": (hidden_above and bool(V._RANK.search(a) or V._LEAST.search(a))) or
                    (hidden_n > 0 and bool(re.search(r"\d|\b(?:led|most|top|biggest)\b", a)))}
    for t in templates(res):
        v = V.check_answer({"lead": t, "points": []}, ledger, turn or V.Turn())
        if v.lead_ok:
            return {"lead": " ".join(o.sent for o in v.lead), "how": "template", "rid": res.rid, "items": items,
                    "private_line": v.private_line}
    return {"lead": PLAIN, "how": "plain", "rid": res.rid, "items": [], "private_line": False}


def answer(ledger, verdict, turn=None):
    """SPEC 4.5, row 3: the code lead with the points of the model's answer that passed."""
    lead = code_lead(ledger, verdict, turn)
    pts = verdict.kept_text("point") if verdict is not None and lead["how"] != "plain" else []
    # a kept point that ranks under a hidden topic needs the private line too
    private = lead["private_line"] or bool(verdict is not None and lead["how"] != "plain" and any(
        o.kept and o.hidden_rank for o in verdict.outcomes if o.where == "point"))
    return dict(lead, points=pts, private_line=private)
