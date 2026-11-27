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
from . import results as R
from . import verify as V

PLAIN = "I couldn't check an answer to that in time. Ask me again?"
# mvp28 prep repair: the plain line of a turn that ended out of rounds with every call refused (event no_result)
NO_RESULT = "I couldn't get a result for that this time. Ask me again, maybe in other words?"
CODE_FORM_KINDS = ("top", "channels", "count", "changed", "compare_windows", "compare_topics", "first", "last", "day",
                   "timeline")
LIST_OF = {"channels": "channels", "top": "themes", "count": None, "changed": "themes", "compare_windows": "themes",
           "timeline": "periods"}


def _first_result(ledger, cited=None):
    if cited and ledger.get(cited):
        return ledger.get(cited)
    # mvp28 prep repair: never a lookup that found nothing ("Here is what I found in your library." over no match)
    # while a later result holds an answer
    return next((r for r in ledger.by_rid.values() if R.answers(r.env)), None) or \
        next(iter(ledger.by_rid.values()), None)


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
    for key in ("areas", "themes", "channels"):
        rows = sheet.get(key)
        nm = (rows[0].get("name") if _tied_top(rows) else None) if isinstance(rows, list) else None
        if isinstance(nm, str) and nm and nm in ans and re.search(r"\b(?:led|leads|most|top|biggest|first)\b", ans):
            return None   # code_form ranks a row over a tie: a template instead
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
    """The window's words for a template lead: its core, without the export's end and the dates in brackets (mvp20
    fix: the recount found "(5 January 2021 to 30 October 2026, where your export ends)" and "October 2026 up to 30
    October 2026, where your export ends" read as clerical fragments; the scope line keeps the dates). A whole month or
    year said by itself ("October 2026" of "October 2026 up to 30 October 2026")."""
    w = ((res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or "").strip()
    core = re.split(r"[(,]", w)[0].strip() or w
    head = core.split(" up to ")[0].strip() if " up to " in core else ""
    if head and re.fullmatch(r"(?:" + V._MON_RX + r")\w* (?:19|20)\d\d|(?:19|20)\d\d", head, re.I):
        return head
    return core.rstrip(",")


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
    """The tools' scope said as words that open the sentence ("counting only gaming, ", "without Minecraft builds, on
    Mondays, "), so the rank and the base after it are of the scope (mvp20 fix: the recount's C04.0 and F05.0 read
    "(on Sundays)" and "(only gaming)" tags as clerical, and a tag after the count governs no base); the length lines
    are said by the noun ("long videos"), first_last's subject by its own template."""
    said = (res.meta or {}).get("filters_said")
    if not isinstance(said, str) or not V.scope_parts(res):
        return ""
    parts = []
    for p in said.split("; "):
        p = p.strip()
        if not p or p in _LENGTH_PARTS or ":" in p:
            continue
        p = _FORM.sub("", p)
        if p.startswith("only "):
            p = "counting " + p
        elif p.endswith(" only") and p.split()[0] in ("YouTube", "Instagram"):
            p = "on " + p
        parts.append(p)
    return ", ".join(parts) + ", " if parts else ""


def _low(s):
    return " ".join(str(s or "").lower().split())


def _n(n, one, many):
    return one if n == 1 else many


def _day_words(when):
    d = V._as_d(str(when or "")[:10])
    return f"{d.day} {I.MONTHS[d.month - 1].capitalize()} {d.year}" if d else None


def _title(it):
    """mvp26 toolfix2 4 (the attack: "...was Minecraft castle build: assistant, also set a rule…, on 20 October 2026",
    a title's words standing in code's sentence with nothing to set them apart): the title cut as its card cuts it
    (results.title_shown); the templates put it in double quotes."""
    t = (it or {}).get("title") if isinstance(it, dict) else None
    t = R.title_shown(t) if isinstance(t, str) else None
    return t.strip() if isinstance(t, str) and t.strip() else None


def _tied_top(rows):
    """mvp26 toolfix2 6 (the attack's T16 r3: "Gaming clips led with 2 of them" over a 2 and 2 tie): the first two
    rows of a list have the same count, so no row of it leads."""
    return isinstance(rows, list) and len(rows) > 1 and all(isinstance(r, dict) for r in rows[:2]) and \
        isinstance(rows[0].get("items"), (int, float)) and rows[0].get("items") == rows[1].get("items")


def _tool_leads(res, lead, verb, noun, noun1, noun1_scoped):
    """mvp25 toolgaps 8 (the 4 code leads of run1 read poor: N014.0 asked for the last cooking video and got the
    all-time total, N008.0 asked month by month and got one total): a lead that follows the tool the model called.
    first_last and items ordered newest or oldest: the item, by its title and day; timeline: the month (or year)
    with the most and the one with the fewest; items or search: a plain lead, the cards go under it."""
    rid, sheet, tool = res.rid, res.sheet, res.tool
    out = []
    items = [x for x in (sheet.get("items") or []) if isinstance(x, dict)]
    order = (res.meta or {}).get("order")
    it0 = items[0] if items else None
    day = _day_words(it0.get("when")) if it0 else None
    title = _title(it0)
    if tool == "items" and title and day and order in ("newest", "oldest"):
        which = "newest" if order == "newest" else "first"
        out.append(f'{lead}the {which} {noun1_scoped} you {verb} was "{title}[{rid}.items[0]]", on '
                   f"{day}[{rid}.items[0].when].")
    f = sheet.get("filters") or {}
    scoped = bool(_scope_clause(res) or f.get("without_shorts") or f.get("length") in ("long", "short")
                  or f.get("topic"))
    if tool == "timeline" and not scoped:   # a scoped timeline keeps the counts' templates, which say the scope
        ps = [(k, p) for k, p in enumerate(sheet.get("periods") or []) if isinstance(p, dict)
              and isinstance(p.get("items"), int) and p.get("label")]
        if len(ps) >= 2:
            hi = max(ps, key=lambda x: (x[1]["items"], -x[0]))
            lo = min(ps, key=lambda x: (x[1]["items"], x[0]))
            if hi[1]["items"] > lo[1]["items"]:
                # the period with the most and the one with the fewest, each count beside its own period's words (the
                # checker reads a window's dates beside a period's count as a number with no marker, so the window
                # is said by its head words only: "This year", not "This year up to 30 October 2026")
                w = _window_words(res)
                head = w.split(" up to ")[0].strip() if " up to " in w else w
                h = lead_in(head) if head else "In all, "
                tot = (sheet.get("totals") or {}).get("items")
                if isinstance(tot, int):
                    out.append(f"{h}you {verb} {tot}[{rid}.totals.items] {_n(tot, noun1, noun)}: "
                               f"{hi[1]['items']}[{rid}.periods[{hi[0]}].items] in {hi[1]['label']} and "
                               f"{lo[1]['items']}[{rid}.periods[{lo[0]}].items] in {lo[1]['label']}.")
                out.append(f"{h}you {verb} {hi[1]['items']}[{rid}.periods[{hi[0]}].items] "
                           f"{_n(hi[1]['items'], noun1, noun)} in {hi[1]['label']} and "
                           f"{lo[1]['items']}[{rid}.periods[{lo[0]}].items] in {lo[1]['label']}.")
    if tool == "items" and items:
        # the cards go under it (answer.build renders them from the rows)
        out.append(f"{lead}here are some of the {noun} you {verb}." if lead else f"Here are some of the {noun} you "
                   f"{verb}.")
    return out


def templates(res, prefer=None):
    """Marker-form leads for a result, most specific first (each is verified before use). `prefer`: the list the
    model's own lead cited (areas, themes, channels), tried first."""
    rid, sheet, tool = res.rid, res.sheet, res.tool
    w = _window_words(res)
    lead = lead_in(w)
    out = []
    order = (res.meta or {}).get("order") or "most"
    kind = sheet.get("kind")
    verb, noun, noun1 = VERB.get((res.meta or {}).get("base") or "", VERB["of what you opened"])
    scope = ", ".join(p for p in _scope_clause(res).rstrip(", ").split(", ") if p and _low(p) not in _low(w))
    scope = scope + ", " if scope else ""
    lead = lead + scope if lead else (scope[:1].upper() + scope[1:] if scope else "")
    if res.is_sheet and kind in ("first", "last"):
        # first_last: the item's day (code_form needs facts' own item rows and a topic, which the tool's resolved
        # subject replaces); the window's core words ("In all your history") and the subject in their own words
        said = (res.meta or {}).get("filters_said") or ""
        subj = said.split(":", 1)[0].strip() if ":" in said else ""
        it0 = (sheet.get("items") or [None])[0]
        day = _day_words(it0.get("when")) if isinstance(it0, dict) else None
        core = re.split(r"[(,]", w)[0].strip()
        title = _title(it0)
        if subj and day and title:
            # mvp25 toolgaps 8: the item itself, by its title, beside its day
            head = lead_in(core)
            which = "first" if kind == "first" else "last"
            out.append(f'{head}the {which} {subj} {noun1} you {verb} was "{title}[{rid}.items[0]]", on '
                       f"{day}[{rid}.items[0].when].")
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
        # mvp25 toolgaps 8: the tool's own lead first (an item, a month), then the counts
        out += _tool_leads(res, lead, verb, noun_, noun1_, noun1_)
        tot = (sheet.get("totals") or {}).get("items")
        total_line = (f"{lead}you {verb} {tot}[{rid}.totals.items] {_n(tot, noun1_, noun_)}."
                      if isinstance(tot, (int, float)) else None)
        prev = sheet.get("previous") or {}
        ptot, pw = prev.get("items"), (prev.get("words") or "").strip()
        if kind in ("compare_windows", "compare") and isinstance(tot, (int, float)) and \
                isinstance(ptot, (int, float)) and pw:
            # both windows of a compare result in one sentence (each count beside its own window's words)
            pin = pw if _OWN_PREP.match(pw) else "in " + pw
            out.append(f"{lead}you {verb} {tot}[{rid}.totals.items] {_n(tot, noun1_, noun_)}, and "
                       f"{ptot}[{rid}.previous.items] {pin}.")
        if kind == "count" and total_line:
            out.append(total_line)
        lst = LIST_OF.get(kind, "themes")
        keys = ([lst] if lst else []) + ["channels", "themes", "areas"]
        if prefer in keys:
            # mvp20 fix (the recount's C04.0: the model's lead named an AREA first, the template a THEME, and a kept
            # point's "came next" then read after the wrong row): the list the model's own lead cited comes first
            keys = [prefer] + [k for k in keys if k != prefer]
        for key in keys:
            rows = sheet.get(key)
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
                continue
            nk = I._record_name_key(rows[0])
            if not nk or not isinstance(rows[0].get("items"), (int, float)) or _tied_top(rows):
                continue
            name, n = rows[0][nk], rows[0]["items"]
            if order == "least":
                out.append(f"{lead}{name}[{rid}.{key}[0]] was the one you {verb} least, with "
                           f"{n}[{rid}.{key}[0].items] {_n(n, noun1_, noun_)}.")
            elif noun_ != noun:
                # mvp20 fix (the recount's B03.0: "Home cooking led what you opened, with 30 long videos" of the long
                # videos only ranked on everything they opened): the rank's base says the length or topic itself
                out.append(f"{lead}{name}[{rid}.{key}[0]] led the {noun_} you {verb}, with "
                           f"{n}[{rid}.{key}[0].items].")
            else:
                # (mvp20 tune: the base's verb said, "led what you saved", so a lead of saves never reads as opens)
                out.append(f"{lead}{name}[{rid}.{key}[0]] led what you {verb}, with {n}[{rid}.{key}[0].items] "
                           f"{_n(n, noun1_, noun_)}.")
        if total_line and kind != "count":
            out.append(total_line)
        if w:
            out.append(f"{lead}here is what I counted.")
    elif tool == "search":
        out.append("Here's what I found in your saves." if (sheet.get("how") or "saved") == "saved" else
                   "Here's what I found.")
    elif tool == "learned":
        out.append("Here is what I found in what you saved.")
    elif tool == "find":
        if R.answers(res.env):   # (mvp28 prep repair: never over a lookup that found nothing)
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
        or res.tool == "items" else []   # mvp25 toolgaps 8: an items result's cards go under the code lead too
    hidden_above = bool(((res.meta or {}).get("hidden") or {}).get("rank_hidden_above"))
    if res.is_sheet:
        a = _from_code_form(res)
        if a:
            # (step 1's close: as the verifier, any number of a result that left private items out asks for the line)
            hidden_n = int((((res.meta or {}).get("hidden") or {}).get("sensitive")) or 0)
            return {"lead": a, "how": "code_form", "rid": res.rid, "items": items,
                    "list": LIST_OF.get(res.sheet_k.get("kind"), "themes"),
                    "private_line": (hidden_above and bool(V._RANK.search(a) or V._LEAST.search(a))) or
                    (hidden_n > 0 and bool(re.search(r"\d|\b(?:led|most|top|biggest)\b", a)))}
    for t in templates(res, _preferred_list(verdict, res.rid)):
        # (mvp24: code's own template is checked with every rule, "full", whatever mode the model's answer was checked
        # in: code words it, and B03.0 was a false code lead)
        v = V.check_answer({"lead": t, "points": []}, ledger, turn or V.Turn(), mode="full")
        if v.lead_ok:
            return {"lead": " ".join(o.sent for o in v.lead), "how": "template", "rid": res.rid, "items": items,
                    "private_line": v.private_line, "marked": t}
    return {"lead": PLAIN, "how": "plain", "rid": res.rid, "items": [], "private_line": False}


def _preferred_list(verdict, rid):
    """The list (areas, themes, channels) the model's own lead cited first, on that result, or None."""
    if verdict is None:
        return None
    for o in verdict.outcomes:
        if o.where != "lead":
            continue
        m = re.search(r"\[" + re.escape(rid or "") + r"\.(areas|themes|channels)\[\d+\]", o.text or "")
        if m:
            return m.group(1)
    return None


# a point that points back at what the model's own lead said ("That is 8 fewer videos", "its theme", "the other 651",
# "also opened"): under a code lead it points at a sentence that is not sent
_BACK_REF = re.compile(r"^\s*(?:that|this|it|its|they|their|these|those|he|she)\b|\b(?:its|their)\s+(?:own\s+)?"
                       r"(?:theme|area|channel|share|count|videos?)\b|\bthe other\b|\bthe rest\b|\balso\b|"
                       r"\bas well\b|\btoo\b|\binstead\b", re.I)


def _points_under(ledger, verdict, lead, turn, mode=None):
    """mvp20 fix (the recount's C04.0 and I02.0: points kept under the model's failed lead went out under a code lead
    they did not fit: "art and design came next" after a THEME, the code lead said again as a point): the model's
    kept points are checked again with the code lead in their lead's place (the template in marker form), and only
    what passes there goes out. A point kept only because the model's lead said its scope (the scope waiver) never
    rides on a code lead. A code_form lead has no markers: a point that places itself after the lead's row ('came
    next') is not sent under it."""
    kept = [o for o in verdict.outcomes if o.where == "point" and o.kept and "scope_waived" not in (o.notes or {})]
    # mvp20 fix, after the final live runs (the held-out second look's E04.0: "That is 8 fewer videos, and its theme
    # Watercolor painting fell ..." went out under a code lead about another channel): a point that refers back to the
    # model's own lead is not sent under a code lead
    kept = [o for o in kept if not _BACK_REF.search(V.strip_markers(o.text))]
    if not kept:
        return []
    texts = [o.text for o in kept]
    if lead.get("marked"):
        v = V.check_answer({"lead": lead["marked"], "points": texts}, ledger, turn or V.Turn(), mode=mode)
        return [o.sent for o in v.outcomes if o.where == "point" and o.kept and o.sent and
                "scope_waived" not in (o.notes or {})]
    out = []
    for o in kept:
        if not o.sent:
            continue
        if V._NEXT.search(V.strip_markers(o.text)):
            # under a code_form lead, a 'came next' row follows the lead's first row only in the lead's own list
            m = re.search(r"\[" + re.escape(lead.get("rid") or "") + r"\.(\w+)\[(\d+)\]", o.text)
            if not m or m.group(1) != lead.get("list") or int(m.group(2)) < 1:
                continue
        out.append(o.sent)
    return out


def no_result(code=None):
    """The code lead of a turn that ended with no result in hand (loop event no_result): the plain line NO_RESULT, with
    `no_result` set so the answer carries the turn's limit lines (answer.build); never a template over a lookup that
    found nothing."""
    return {"lead": NO_RESULT, "how": "plain", "rid": (code or {}).get("rid"), "items": [], "private_line": False,
            "points": [], "no_result": True}


OTHERS_MAX = V.POINTS_MAX   # the points of an answer


def scope_said(res):
    """mvp30 repair (the attack: a result scoped to one private topic went out under a code lead with no scope line,
    so its count read as one of all their history): True when the templates say every part of the result's scope. A
    part the full check reads (scope_parts) is said by the scope clause; a length part by the noun ("long videos"); any
    other part (the helper form of a private topic's scope) no template says, and the scope line is then the only
    place that says it."""
    said = (res.meta or {}).get("filters_said") if res is not None else None
    if not isinstance(said, str) or not said.strip():
        return True
    parts = [p.strip() for p in said.split("; ") if p.strip() and p.strip() not in _LENGTH_PARTS]
    return len(V.scope_parts(res)) >= len(parts)


def other_points(ledger, lead, turn=None):
    """mvp30 (a turn that ran out of time with several results in hand sent the first result's sentence alone, and the
    other parts of the question went unanswered): one sentence per OTHER result in
    hand, in call order, each the first of its own templates that passes the full check as a lead of its own (so it
    says its own window and scope), never one that repeats a sentence already said; at most OTHERS_MAX.
    -> ([sentence], private_line)."""
    out, private, said = [], False, {lead.get("lead")}
    for res in ledger.by_rid.values():
        if len(out) >= OTHERS_MAX:
            break
        if res.rid == lead.get("rid") or not R.answers(res.env) or not scope_said(res):
            continue   # (a result whose scope no template says goes out only with its own scope line)
        for t in templates(res):
            v = V.check_answer({"lead": t, "points": []}, ledger, turn or V.Turn(), mode="full")
            if not v.lead_ok:
                continue
            s = " ".join(o.sent for o in v.lead)
            if s and s not in said and not s.endswith("here is what I counted."):
                out.append(s)
                said.add(s)
                private = private or bool(v.private_line)
            break
    return out, private


def answer(ledger, verdict, turn=None, mode=None, others=False):
    """SPEC 4.5, row 3: the code lead with the points of the model's answer that passed (checked again under it).
    mvp24, cells mode: a code lead never carries a model's points, and no model point is read again under a lead it
    was not written for (the points are not re-checked under the code lead: there are none).
    mvp30, `others` (the loop sets it when no answer form came back at all: a provider timeout, the hard stop, no call
    after the nudge): the points are one sentence of each other result in hand (other_points), and `mixed` is set so
    the scope line, which names one result, is left out."""
    if not isinstance(ledger, V.Ledger):
        ledger = V.Ledger(ledger)
    cm = V.check_mode(mode)
    lead = code_lead(ledger, verdict, turn)
    if others and verdict is None and lead["how"] != "plain" and scope_said(ledger.get(lead.get("rid"))):
        # (mvp30 repair: `mixed` leaves the lead's scope line out, so a lead whose scope no template says keeps it)
        pts, priv = other_points(ledger, lead, turn)
        if pts:
            return dict(lead, points=pts, private_line=bool(lead["private_line"] or priv), mixed=True)
    pts = _points_under(ledger, verdict, lead, turn, cm) if verdict is not None and lead["how"] != "plain" and \
        not cm.cells else []
    if lead["how"] == "template" and not pts and lead.get("marked", "").endswith("here is what I counted."):
        # mvp20 fix (the recount's D04.1: "here is what I counted (Instagram only)." with nothing after it): a lead
        # that only says a count was made, with no point under it, says nothing: the plain line instead
        return {"lead": PLAIN, "how": "plain", "rid": lead["rid"], "items": [], "private_line": False, "points": []}
    # a kept point that ranks under a hidden topic needs the private line too
    # (cells mode: no model point goes out under the code lead, so none asks for the line here)
    private = lead["private_line"] or bool(not cm.cells and verdict is not None and lead["how"] != "plain" and any(
        o.kept and o.hidden_rank for o in verdict.outcomes if o.where == "point"))
    return dict(lead, points=pts, private_line=private)
