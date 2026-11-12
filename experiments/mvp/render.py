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
                     r"every|one|he|she|we)\b", re.I)
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
                out.append({"type": "text", "text": p["text"].strip()})
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
    if not asked or any(facts.get(k) for k in facts) or not all(k in facts for k in asked):
        return None
    from .extract import list_like
    if list_like(getattr(it, "raw_caption", "") or it.caption):
        return None
    return asked[0]


def end_sentence(s):
    """A full stop unless the sentence already ends with one (also before a closing quote: finding 9)."""
    s = s.rstrip()
    return s if _ENDED.search(s) else s + "."


def kind_lines(kind, lines, label=True, lang=None):
    out = [f"{L.table(lang)['label'][kind]} ({len(lines)}):"] if label else []
    if kind == "steps":
        out.extend(f"{i}. {line}" for i, line in enumerate(lines, 1))
    else:
        out.extend(f"• {line}" for line in lines)
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
        out.extend(kind_lines(kind, lines, lang=lang))
    if not shown and pick.get("lines"):   # lines found before (a follow-up), kind unknown
        out.append(f"{t['label']['details']} ({len(pick['lines'])}):")
        out.extend(f"• {line}" for line in pick["lines"])
        shown = True
    kind = None if shown else in_video(pick, extract)
    if kind:
        out.append(t["in_video"][kind])
    elif shown and pick["item"].platform == "instagram":
        for k in asked or []:
            if k in facts and not facts.get(k) and (k != "ingredients" or food):
                out.append(t["not_written"][k])
    return out


def alt_note(pick, extract, lang=None):
    """The one line after an alternative: what is written out (counted from checked lines), else its reason."""
    t = L.table(lang)
    facts = pick.get("facts") or {}
    ing, steps, keys = facts.get("ingredients") or [], facts.get("steps") or [], facts.get("key_points") or []
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


def pick_sentence(lead, p, now=None, lang=None):
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
    if b:
        subject = SUBJECT.match(b) or L.code(lang) is not None   # the subject words are English ones
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
    m = re.match(r"under (\d+) minutes$", low)
    if m:
        return t["ph_under"].format(n=m.group(1))
    return t["ph_fits_no" if no else "ph_fits"].format(cr=cr)


def intro_line(result, spec, lang=None):
    """The opening line: the composer's, when it passed the checks, else one built here (finding 37)."""
    t = L.table(lang)
    if result.get("intro"):
        return end_sentence(result["intro"])
    goal = (spec.content.goal or "").strip()
    if re.match(r"^(a|an|some)\s", goal, re.I):
        return t["intro_a"].format(goal=goal)
    return t["intro_plain"] if not goal else t["intro_for"].format(goal=goal)


def picks_message(result, spec, footer=None, now=None, extract=None, lang=None):
    """The answer. `lang`: the person's language when the phrase table holds it (lang.py); else English."""
    t = L.table(lang)
    lang = lang if L.supported(lang) else None
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
    else:
        text.append(intro_line(result, spec, lang))
        text.append("")
        text.append(pick_sentence(t["recommend"], first, now, lang))
    if result.get("level_note"):   # slice 6: once per topic while the level is a guess
        text.append(result["level_note"])
    flush()
    if it.url:
        parts.append(link_part(it, first["title"]))
    text.extend(details_lines(first, extract, asked=c.extract, lang=lang))
    if len(picks) > 1:
        text.append("")
        text.append(t["or_close"] if result.get("closest") else t["or_try"])
        for p in picks[1:]:
            note = alt_note(p, extract, lang)
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
    return {"item_id": it.id, "title": p["title"], "url": it.url, "platform": it.platform,
            "video_id": getattr(it, "video_id", None), "creator": it.creator, "facts": facts,
            "lines": list(p.get("lines") or []), "line_kinds": kinds if p.get("lines") and not p.get("lines_reused") else None}


def pick_parts(rec, lead=""):
    """One kept pick as parts: its title (and creator), its link alone, and its checked details."""
    head = f"{lead}{rec['title']}" + (f" by {rec['creator']}" if rec.get("creator") else "") + "."
    parts = [{"type": "text", "text": head}]
    if rec.get("url"):
        parts.append({"type": "link", "url": rec["url"], "title": rec["title"], "platform": rec.get("platform"),
                      "video_id": rec.get("video_id")})
    lines = []
    facts = rec.get("facts") or {}
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
