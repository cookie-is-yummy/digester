"""PROTOTYPE ONLY - turn checked picks into what the person reads (render v2, DESIGN.md section 3).

The shape: a first line; one recommended pick with its reason in a sentence and where it came from in plain words;
its link as a part of its own (a channel that shows link previews sends it as its own message); its details; then
"Alternatively, try these:" with one line each, and for an ask "Or here's a wider selection:". When nothing is a clear
fit, the closest is shown as the closest. Every count and the "top N" line are computed here, from the checked lines.
No "Why:" label.

A reply is a list of parts: {"type": "text", "text"} and {"type": "link", "url", "title", "platform", "video_id"}.
`Reply` joins with plain strings (`head + reply + tail`), so callers that add a line keep working.
"""
import re
from datetime import datetime

from . import lang as L

LABEL = {"ingredients": "Ingredients", "steps": "Steps", "key_points": "Key points"}
KIND_PLURAL = {"ingredients": "The ingredients", "steps": "The steps", "key_points": "The key points"}
# a clause that can follow "because": it starts with a subject (finding 8); anything else follows a colon
SUBJECT = re.compile(r"^(?:it|it's|it’s|its|you|you'll|you're|you’re|your|the|this|these|there|they|all|both|each|"
                     r"every|he|she|we)\b", re.I)   # not "one": "one pot and 15 minutes" is not a clause
_ENDED = re.compile(r"[.!?…][\"'”’)\]]*$")
HOW = {"save": "saved", "collection": "put in a collection", "share_self": "sent to yourself",
       "playlist": "added to a playlist", "like": "liked", "watch": "watched", "view": "viewed"}
HOW_ORDER = ["share_self", "save", "collection", "playlist", "like", "watch", "view"]
IN_VIDEO = {"ingredients": "The recipe is in the video, not written in the post.",
            "steps": "The steps are in the video, not written in the post.",
            "key_points": "The tips are in the video, not written in the post."}


class Reply:
    """A message made of parts. str(reply) and reply.text() join them for channels without link previews."""

    def __init__(self, parts=None):
        self.parts = [dict(p) for p in (parts or []) if p.get("type") == "link" or (p.get("text") or "").strip()]

    @staticmethod
    def of(x):
        return x if isinstance(x, Reply) else Reply([{"type": "text", "text": str(x)}])

    def __add__(self, other):
        if isinstance(other, Reply):
            return Reply(self.parts + other.parts)
        other = str(other)
        if not other:
            return Reply(self.parts)
        parts = [dict(p) for p in self.parts]
        if parts and parts[-1]["type"] == "text":
            parts[-1]["text"] += other
        else:
            parts.append({"type": "text", "text": other})
        return Reply(parts)

    def __radd__(self, other):
        other = str(other)
        if not other:
            return Reply(self.parts)
        parts = [dict(p) for p in self.parts]
        if parts and parts[0]["type"] == "text":
            parts[0]["text"] = other + parts[0]["text"]
        else:
            parts.insert(0, {"type": "text", "text": other})
        return Reply(parts)

    def split(self):
        """The parts as separate messages: text parts trimmed, empty ones left out, each link as its bare URL."""
        out = []
        for p in self.parts:
            if p["type"] == "link":
                out.append(p)
            elif p["text"].strip():
                out.append({"type": "text", "text": p["text"].strip(), **({"card_alt": True} if p.get("card_alt")
                                                                           else {})})
        return out

    def text(self):
        return "\n".join(p["url"] if p["type"] == "link" else p["text"] for p in self.split())

    def links(self):
        return [p for p in self.parts if p["type"] == "link"]

    def __str__(self):
        return self.text()

    def __contains__(self, s):
        return s in self.text()

    def __eq__(self, other):
        return self.text() == (other.text() if isinstance(other, Reply) else other)

    def __hash__(self):
        return hash(self.text())

    def strip(self):
        return self.text().strip()


def joined(x):
    return x.text() if isinstance(x, Reply) else str(x)


# ---------- words ----------
def when_kept(it, now=None, lang=None):
    """'which you sent to yourself in July', 'which you saved in March 2025': the strongest way they kept it."""
    t = L.table(lang)
    kind = next((k for k in HOW_ORDER if k in it.kinds), None)
    if not kind:
        return ""
    day = it.dates.get(kind) or it.kept_on()
    try:
        d = datetime.fromisoformat(str(day)[:10])
    except (TypeError, ValueError):
        return t["kept_plain"].format(how=t["how"][kind])
    this_year = (now or datetime.now()).year == d.year
    return t["kept"].format(how=t["how"][kind], when=L.month(d, lang, not this_year))


def by(it, lang=None):
    return L.table(lang)["by"].format(creator=it.creator) if it.creator else ""


def link_part(it, title):
    return {"type": "link", "url": it.url, "title": title, "platform": it.platform,
            "video_id": getattr(it, "video_id", None)}


def in_video(pick, extract):
    """The kind to say "is in the video" about, or None. Said only for Instagram, only when the details step read the
    post and found none of it, and never when the post's text looks like it holds a list (then the step missed it, and
    saying "not written in the post" would be wrong)."""
    it, facts = pick["item"], pick.get("facts") or {}
    if not extract or it.platform != "instagram":
        return None
    asked = [k for k in ("ingredients", "steps", "key_points") if k in extract]
    if not asked or any(facts.get(k) for k in facts) or not all(k in facts for k in asked + [k for k in ("items",)
                                                                                           if k in extract]):
        return None
    from .extract import list_like
    if list_like(getattr(it, "raw_caption", "") or it.caption):
        return None
    return asked[0]


def end_sentence(s):
    """A full stop unless the sentence already ends with one (also before a closing quote: finding 9)."""
    s = s.rstrip()
    return s if _ENDED.search(s) else s + "."


def kind_lines(kind, lines, label=True, lang=None, pick=None):
    out = [f"{L.table(lang)['label'][kind]} ({len(lines)}):"] if label else []
    if kind == "steps":
        out.extend(f"{i}. {line}" for i, line in enumerate(lines, 1))
    else:
        out.extend(f"• {stale_suffix(pick, line, lang) if pick and kind == 'key_points' else line}" for line in lines)
    return out


def details_lines(pick, extract, asked=None, lang=None):
    """The checked lines under their labels, counted here; for Instagram with nothing written, one plain line; for
    YouTube with nothing written, nothing (the video may well show it). Ingredients only for a food request, and a
    line is never shown under two labels (finding 12). A kind the person asked for that the post does not write out
    while another kind is: one honest line (finding 16)."""
    t = L.table(lang)
    out = []
    facts = pick.get("facts") or {}
    food = "ingredients" in (extract or [])
    shown, seen = False, set()
    for kind in [k for k in ("ingredients", "steps", "key_points") if k in facts or k in (extract or [])]:
        if kind == "ingredients" and not food:
            continue
        lines = [x for x in facts.get(kind) or [] if x not in seen]
        seen.update(lines)
        if not lines:
            continue
        shown = True
        out.extend(kind_lines(kind, lines, lang=lang, pick=pick))
    if not shown and pick.get("lines"):   # lines found before (a follow-up), kind unknown
        out.append(f"{t['label']['details']} ({len(pick['lines'])}):")
        out.extend(f"• {line}" for line in pick["lines"])
        shown = True
    kind = None if shown else in_video(pick, extract)
    if kind and list(extract or []) == ["items", "key_points"]:
        # round 7: the default details for a request that asks for things: the plain line only then (a request that
        # asks for nothing in particular keeps the answer it had)
        kind = "items" if pick.get("things") else None
    if kind:
        out.append(t["in_video"][kind])
    elif shown and pick["item"].platform == "instagram":
        for k in asked or []:
            if k in facts and not facts.get(k) and (k != "ingredients" or food):
                out.append(t["not_written"][k])
    return out


def stale_suffix(pick, line, lang=None):
    """Round 7, finding 91: a line that speaks of now ("applications are open") from a post older than 60 days gets
    the post's month after it, so it never reads as true today."""
    from .dates import STALE_DAYS, days_old, month_year, STALE
    today = pick.get("today")
    if not today or not pick.get("age_from") or L.code(lang):
        return line
    n = days_old(pick["age_from"], today)
    if n is None or n <= STALE_DAYS or not STALE.search(line or ""):
        return line
    return f"{line.rstrip()} (as of {month_year(pick['age_from'])})"


def alt_note(pick, extract, lang=None):
    """The one line after an alternative: what is written out (counted from checked lines), else its reason. Round 7:
    with the default details (items, then key points) an alternative says what is in it, its first key point."""
    t = L.table(lang)
    facts = pick.get("facts") or {}
    ing, steps, keys = facts.get("ingredients") or [], facts.get("steps") or [], facts.get("key_points") or []
    if keys and list(extract or []) == ["items", "key_points"]:
        return stale_suffix(pick, keys[0], lang)
    if ing and "ingredients" in (extract or []):
        amounts = sum(any(ch.isdigit() for ch in line) for line in ing) * 2 >= len(ing)
        return (t["alt_ing_steps"] if steps else t["alt_ing"]) + (t["amounts"] if amounts else "")
    if steps:
        return t["alt_steps"]
    if keys:
        return t["alt_keys"]
    if in_video(pick, extract) in ("ingredients", "steps"):
        return t["alt_video"]
    return pick["because"] if pick.get("because_backed") and pick.get("because") else ""


def code_reason(pick, extract, lang=None):
    """Fix pass 5, finding 84 (5): a reason code can stand behind, from what it read in the pick's own text and shows
    under it ("the ingredients are written out, with amounts"); '' when no details are shown."""
    p = dict(pick, because=None, because_backed=False)
    note = alt_note(p, extract, lang)
    t = L.table(lang)
    return note if note and note != t["alt_video"] else ""


def pick_sentence(lead, p, now=None, lang=None, colon=False):
    """'I recommend One Pot Pasta by @chef (9 minutes), which you saved in March, because it takes 15 minutes.' The
    reason only when it is backed (finding 10); after "because" only a full clause, else after a colon (finding 8)."""
    t = L.table(lang)
    it = p["item"]
    kept = when_kept(it, now, lang)
    length = L.length(p.get("length_text"), lang)
    s = f"{lead} {p['title']}{by(it, lang)}" + (f" ({length})" if length else "")
    if kept:
        s += f", {kept}"
    b = p["because"] if p.get("because_backed") and p.get("because") else None
    fit = p.get("fit") if not colon else None   # finding 54: the person's kit or level, backed by the pick's text
    if fit:
        b = f"{b}, and {fit}" if b else fit
    if b:
        subject = SUBJECT.match(b) or L.code(lang) is not None   # the subject words are English ones
        if colon:   # a follow-up names a pick already shown: "It's X, which you saved in May: it has no cream."
            subject = False
        s += ((f", {t['because']} " if kept else f" {t['because']} ") + b) if subject else (": " + b)
    return end_sentence(s)


def criterion_phrase(cr, lang=None, no=False):
    """A must-have as it reads in a sentence about the picks (finding 11)."""
    t = L.table(lang)
    low = cr.lower()
    if re.search(r"\b(dish|eat|meal|recipe)\b", low) and re.search(r"finish|end|whole|full|complete", low):
        return t["ph_recipe"]
    if re.search(r"\b(routine|workout)\b", low) and re.search(r"finish|end|whole|full|complete", low):
        return t["ph_routine"]
    if re.search(r"start to finish|finished|ends? with|whole project|complete project", low):
        return t["ph_project"]
    m = re.match(r"suits (?:an? )?(beginner|kids|intermediate level|advanced level)$", low)
    if m and not L.code(lang):   # finding 58: the level must-have, in a sentence
        return {"beginner": "is made for a beginner", "kids": "is made for kids",
                "intermediate level": "is made for an intermediate level",
                "advanced level": "is made for an advanced level"}[m.group(1)]
    m = re.match(r"under (\d+) minutes$", low)
    if m:
        return t["ph_under"].format(n=m.group(1))
    return t["ph_fits_no" if no else "ph_fits"].format(cr=cr)


INTRO_GOAL_WORDS = 6   # round 7, rule 7: a longer goal is never echoed in the opening line code builds


def intro_line(result, spec, lang=None):
    """The opening line: the composer's, when it passed the checks, else one built here (finding 37). A changed
    request's line is built by code from the merged request (round 7, finding 92). A goal longer than a few words is
    not echoed back (round 7): "Here's what I found in your saves."."""
    t = L.table(lang)
    if result.get("intro_code"):
        return end_sentence(result["intro_code"])
    if result.get("intro"):
        return end_sentence(result["intro"])
    goal = (spec.content.goal or "").strip()
    if len(goal.split()) > INTRO_GOAL_WORDS:
        return t["intro_plain"]
    if re.match(r"^(a|an|some)\s", goal, re.I):
        return t["intro_a"].format(goal=goal)
    return t["intro_plain"] if not goal else t["intro_for"].format(goal=goal)


def date_words(p, result, lang=None):
    """Round 7, finding 91: the few words about a pick's date for a time-sensitive request ("its deadline, 14
    February 2025, has passed"), worked out by code; '' otherwise (and in a language without these phrases)."""
    if not result.get("ts") or L.code(lang) or not result.get("today"):
        return ""
    from .dates import date_note
    return date_note(p.get("date_state"), result["today"])


def date_sentence(p, result, lang=None):
    w = date_words(p, result, lang)
    if not w:
        return ""
    if w.startswith("its "):
        return end_sentence("I" + w[1:])
    if w.startswith("from "):
        return end_sentence("It's " + w)
    return end_sentence(w[0].upper() + w[1:])


def _item_line(x, lang=None):
    """'3. Name: what the post says about it (deadline 1 December (in 17 days)).'"""
    s = f"{x['n']}. {x['name']}"
    about = x.get("about") or ""
    if about and x.get("stale_from") and not L.code(lang):
        about = f"{about.rstrip()} (as of {x['stale_from']})"
    if about:
        s += f": {about}"
    # checker: inside the item's own brackets, "deadline 1 December, in 19 days" (never brackets in brackets)
    when = re.sub(r" \(((?:in |about )[^()]+|today|tomorrow)\)$", r", \1", x.get("note") or "")
    if not when and x.get("when") and not (about and x["when"] in about):
        when = x["when"]
    if when:
        s += f" ({when})"
    return s


def source_head(p, now=None, lang=None):
    """'From "Best design systems" by @creator (posted May 2024, saved July 2023):'."""
    t = L.table(lang)
    it = p["item"]
    when = []
    if p.get("posted"):
        try:
            d = datetime.fromisoformat(str(p["posted"])[:10])
            when.append(t["posted"].format(when=L.month(d, lang, True)))
        except ValueError:
            pass
    kind = next((k for k in HOW_ORDER if k in it.kinds), None)
    day = (it.dates.get(kind) if kind else None) or it.kept_on()
    if kind and day:
        try:
            d = datetime.fromisoformat(str(day)[:10])
            when.append(t["kept_head"].format(how=t["how"][kind], when=L.month(d, lang, True)))
        except ValueError:
            pass
    return t["items_from"].format(title=p["title"], by=by(it, lang)) + (f" ({', '.join(when)})" if when else "") + ":"


FOUND_NOUN_WORDS = 4   # round 8, finding 94: the goal's noun phrase in "I found 9 UI/UX libraries named in ..."


def found_noun(goal):
    """The goal's noun phrase up to its kind of thing, when it is short ("UI/UX libraries for my next project": "UI/UX
    libraries"; "opportunities to pursue soon": "opportunities"); None otherwise (then "things")."""
    from .extract import THINGS
    g = re.sub(r"^\s*(?:some|a few|any|the|good|great|other|more)\s+", "", (goal or "").strip(), flags=re.I)
    ends = [m for m in THINGS.finditer(g) if m.group(0).lower().endswith("s") and " " not in m.group(0)]
    if not ends:
        return None
    phrase = g[:ends[-1].end()].strip()
    if len(phrase.split()) > FOUND_NOUN_WORDS or re.search(r"[^\w\s/&'-]", phrase):
        return None
    return phrase


def items_intro(result, spec, lang=None):
    """Round 8, finding 94: 'I found 9 UI/UX libraries named in 3 of your saves.', counted by code; a changed
    request keeps its own line (round 7)."""
    if result.get("intro_code"):
        return end_sentence(result["intro_code"])
    t = L.table(lang)
    srcs = result["items_answer"]
    n, k = sum(len(its) for _, its, _ in srcs), len(srcs)
    noun = (found_noun(spec.content.goal) if not L.code(lang) else None) or t["items_things"]
    return t["items_found_one" if k == 1 else "items_found"].format(n=n, noun=noun, k=k)


def items_message(result, spec, footer=None, now=None, lang=None):
    """Round 7, finding 90: the answer is the things the posts name, each under the post it came from, with that
    post's link alone after its list. Up to 3 posts, up to 6 things each ("and 2 more in the post"). Picks with no
    named things follow in one line each. Round 8 (findings 93 and 94): the opening line says what was found, with
    counts; the next posts with things are named under "More in your saves:"; a pick whose title promises a list its
    text does not hold says the names are in its slides."""
    t = L.table(lang)
    parts, text = [], [items_intro(result, spec, lang)]
    if result.get("level_note"):
        text.append(result["level_note"])
    srcs = result["items_answer"]
    used = set()
    for p, its, more in srcs:
        used.add(id(p))
        text.append("")
        text.append(source_head(p, now, lang))
        text.extend(_item_line(x, lang) for x in its)
        if more:
            text.append(t["and_more"].format(n=more))
        parts.append({"type": "text", "text": "\n".join(text).strip("\n")})
        text = []
        if p["item"].url:
            parts.append(link_part(p["item"], p["title"]))
    more = result.get("items_more") or []
    if more:
        text.append("")
        text.append(t["items_more"])
        for p, n in more:
            used.add(id(p))
            line = t["items_more_line_one" if n == 1 else "items_more_line"].format(title=p["title"],
                                                                                    by=by(p["item"], lang), n=n)
            text.append(f"• {line}" + (f" {p['item'].url}" if p["item"].url else ""))
    rest = [p for p in result["picks"] if id(p) not in used]
    if rest:
        text.append("")
        text.append(t["items_also"])
        for p in rest:
            if p.get("things") and promises_slides(p):
                text.append(f"• {p['title']}{by(p['item'], lang)}: {t['in_slides']}" +
                            (f" {p['item'].url}" if p["item"].url else ""))
                continue
            note = alt_note(p, result.get("extract"), lang)
            dn = date_words(p, result, lang)
            if dn:
                note = f"{note.rstrip(' .')}; {dn}" if note else dn
            text.append(f"• {p['title']}{by(p['item'], lang)}" + (f": {end_sentence(note)}" if note else "") +
                        (f" {p['item'].url}" if p["item"].url else ""))
    if footer:
        text.append("")
        text.append(footer)
    if text:
        parts.append({"type": "text", "text": "\n".join(text).strip("\n")})
    return Reply(parts)


def promises_slides(p):
    """Round 8, finding 93 (rule 5): the post's title or first line promises a list ("4 free programs for students",
    "best design systems") and the details step read it and no named thing of it is shown."""
    from .extract import promises_list
    facts = p.get("facts") or {}
    return "items" in facts and not p.get("shown_items") and \
        promises_list(p.get("title") or "", getattr(p["item"], "first_line", "") or "")


def picks_message(result, spec, footer=None, now=None, extract=None, lang=None, follow_up=False):
    """The answer. `lang`: the person's language when the phrase table holds it (lang.py); else English.
    follow_up: an answer to a question about picks already shown ("is the second one vegetarian?"): never "I
    recommend", and no opening line built from the question; the composer's own line when it passed the checks."""
    t = L.table(lang)
    lang = lang if L.supported(lang) else None
    if result.get("items_answer") and not follow_up:
        return items_message(result, spec, footer=footer, now=now, lang=lang)
    c = spec.content
    extract = list(c.extract if extract is None else extract)
    picks, wider = result["picks"], result.get("wider") or []
    parts = []
    text = []

    def flush():
        if text:
            parts.append({"type": "text", "text": "\n".join(text).strip("\n")})
            text.clear()

    first = picks[0]
    it = first["item"]
    unknown = list(result.get("unknown_criteria") or [])
    if result.get("closest"):
        missing = result.get("missing") or []
        if missing:
            cr, ans = missing[0] if isinstance(missing[0], (list, tuple)) else (missing[0], "unknown")
            if cr in unknown:   # said once, here
                unknown.remove(cr)
            phrase = criterion_phrase(cr, lang, no=(ans == "no"))
            lead = t["lead_no" if ans == "no" else "lead_unknown"].format(phrase=phrase)
            text.append(pick_sentence(lead, first, now, lang))
        else:
            text.append(t["no_clear"].format(goal=c.goal))
            text.append("")
            text.append(pick_sentence(t["closest"], first, now, lang))
    elif follow_up:
        if result.get("intro"):
            text.append(end_sentence(result["intro"]))
            text.append("")
        text.append(pick_sentence(t["its"], first, now, lang, colon=True))
    else:
        text.append(intro_line(result, spec, lang))
        text.append("")
        text.append(pick_sentence(t["recommend"], first, now, lang))
    if result.get("level_note"):   # slice 6: once per topic while the level is a guess
        text.append(result["level_note"])
    lead_date = date_sentence(first, result, lang)
    if lead_date:   # round 7, finding 91: "Its deadline, 14 February 2025, has passed."
        text.append(lead_date)
    flush()
    if it.url:
        parts.append(link_part(it, first["title"]))
    text.extend(details_lines(first, extract, asked=c.extract, lang=lang))
    if result.get("closest"):
        groups = [(t["or_close"], picks[1:])]
    else:   # fix pass 5, finding 84 (3): close ones after a clear lead come under their own heading, never mixed
        groups = [(t["or_try"], [p for p in picks[1:] if p.get("verdict", "clear") == "clear"]),
                  (t["or_close"], [p for p in picks[1:] if p.get("verdict", "clear") != "clear"])]
    for head, group in groups:
        if not group:
            continue
        text.append("")
        text.append(head)
        for p in group:
            note = alt_note(p, extract, lang)
            dn = date_words(p, result, lang)
            if dn:
                note = f"{note.rstrip(' .')}; {dn}" if note else dn
            length = L.length(p.get("length_text"), lang)
            text.append(f"• {p['title']}{by(p['item'], lang)}" + (f" ({length})" if length else "") +
                        (f": {end_sentence(note)}" if note else "") + (f" {p['item'].url}" if p["item"].url else ""))
    if wider:
        text.append("")
        text.append(t["wider"])
        for p in wider:
            text.append(f"• {p['title']}" + (f": {p['item'].url}" if p["item"].url else ""))
    for cr in unknown:
        text.append("")
        text.append(t["cant_check"].format(cr=cr))
    if c.asked_count and c.asked_count > c.count:
        text.append("")
        text.append(t["top_n"].format(asked=c.asked_count, n=c.count))
    if footer:
        text.append("")
        text.append(footer)
    flush()
    return Reply(parts)


def none_message(result, spec, scheduled=False, lang=None):
    """Nothing to show. The reason is always a sentence code chose (finding 5), never the model's words."""
    t = L.table(lang)
    reason = result.get("none_reason") or t["none_default"]
    if t is not L.EN:   # the reasons code builds, in the person's language
        m = re.match(r"nothing you kept since (\S+) matched$", reason)
        reason = t["none_lib"] if reason == L.EN["none_lib"] else \
            (t["none_since"].format(date=m.group(1)) if m else reason)
    if scheduled and spec.when.type == "once":
        return f"Nothing good for \"{spec.content.goal}\" right now: {reason.rstrip('.')}. Ask me again any time."
    if scheduled:
        return f"Nothing new for \"{spec.content.goal}\" this time: {reason.rstrip('.')}. I'd rather skip than send something weak."
    return t["none"].format(reason=reason.rstrip("."))


# ---------- slice 4: a pick on its own, and an answer as an email (DESIGN.md sections 3 and 6) ----------
def pick_record(p):
    """What is kept of a checked pick (store.answers): its checked title, its link and its checked details."""
    it = p["item"]
    facts = p.get("facts") or {}
    kinds = [k for k in ("ingredients", "steps", "key_points") if facts.get(k)]
    rec = {"item_id": it.id, "title": p["title"], "url": it.url, "platform": it.platform,
           "video_id": getattr(it, "video_id", None), "creator": it.creator, "facts": facts,
           "lines": list(p.get("lines") or []), "line_kinds": kinds if p.get("lines") and not p.get("lines_reused") else None}
    if p.get("shown_items"):   # round 7: the things an items answer showed from this post, as it showed them
        rec["items"] = [{k: x.get(k) for k in ("n", "name", "about", "when", "note", "date", "state", "stale_from")}
                        for x in p["shown_items"]]
        for x in rec["items"]:
            x["shown"] = _item_line(x)[len(f"{x['n']}. "):]
    if p.get("posted"):
        rec["posted"] = p["posted"]
    return rec


def pick_parts(rec, lead=""):
    """One kept pick as parts: its title (and creator), its link alone, and its checked details."""
    head = f"{lead}{rec['title']}" + (f" by {rec['creator']}" if rec.get("creator") else "") + "."
    parts = [{"type": "text", "text": head}]
    if rec.get("url"):
        parts.append({"type": "link", "url": rec["url"], "title": rec["title"], "platform": rec.get("platform"),
                      "video_id": rec.get("video_id")})
    lines = []
    facts = rec.get("facts") or {}
    for x in rec.get("items") or []:   # round 7: the things an items answer showed from this post
        lines.append(f"{x.get('n') or len(lines) + 1}. {x.get('shown') or x.get('name')}")
    for kind in ("ingredients", "steps", "key_points"):
        got = facts.get(kind) or []
        if got:
            lines.append(f"{LABEL[kind]} ({len(got)}):")
            lines.extend(f"{i}. {x}" if kind == "steps" else f"• {x}" for i, x in enumerate(got, 1))
    if not lines and rec.get("lines"):
        lines.append(f"Details ({len(rec['lines'])}):")
        lines.extend(f"• {x}" for x in rec["lines"])
    if lines:
        parts.append({"type": "text", "text": "\n".join(lines)})
    return parts


def _esc(s):
    import html
    return html.escape(str(s), quote=True)


def _linkify(line):
    import re
    out, last = [], 0
    for m in re.finditer(r"https?://[^\s<>\"]+", line):
        out.append(_esc(line[last:m.start()]))
        url = m.group(0).rstrip(".,)")
        out.append(f'<a href="{_esc(url)}">{_esc(url)}</a>' + _esc(m.group(0)[len(url):]))
        last = m.end()
    out.append(_esc(line[last:]))
    return "".join(out)


def _link_html(p):
    import re
    url, title = p.get("url") or "", p.get("title") or p.get("url") or ""
    if not re.match(r"^https?://", url, re.I):
        return f"<p>{_esc(url)}</p>"
    vid = p.get("video_id") if p.get("platform") == "youtube" else None
    if vid and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", str(vid)):
        # the thumbnail by its public URL, linked to the video, with YouTube named as the source; nothing is fetched
        return (f'<p><a href="{_esc(url)}"><img src="https://i.ytimg.com/vi/{vid}/hqdefault.jpg" width="320" '
                f'height="180" alt="{_esc(title)}" style="display:block;border:0;border-radius:8px"></a>'
                f'<span style="color:#ff0000;font-weight:bold">YouTube</span> <a href="{_esc(url)}">{_esc(title)}</a></p>')
    label = {"instagram": " (Instagram)", "youtube": " (YouTube)"}.get(p.get("platform"), "")
    return f'<p><a href="{_esc(url)}">{_esc(title)}</a>{label}</p>'


def email_bodies(parts, links=(), footer=""):
    """(plain text, simple HTML) of an answer's parts, plus links such as "Add to Google Calendar". Links in text are
    made clickable; a YouTube pick shows its thumbnail by URL; an Instagram pick is a linked title (email runs no
    embed script)."""
    rep = Reply(parts)
    text = rep.text()
    html = []
    for p in rep.split():
        if p["type"] == "link":
            html.append(_link_html(p))
            continue
        for para in p["text"].split("\n\n"):
            html.append("<p>" + "<br>".join(_linkify(x) for x in para.split("\n")) + "</p>")
    for label, url in links:
        text += f"\n\n{label}: {url}"
        html.append(f'<p><a href="{_esc(url)}">{_esc(label)}</a></p>')
    if footer:
        text += "\n\n" + footer
        html.append(f'<p style="color:#666;font-size:12px">{_esc(footer)}</p>')
    body = ('<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
            'font-size:15px;line-height:1.45;color:#16161a;max-width:560px">' + "\n".join(html) + "</body></html>")
    return text, body
