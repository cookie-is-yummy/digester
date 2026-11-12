"""PROTOTYPE ONLY - turn checked picks into what the person reads (render v2, DESIGN.md section 3).

The shape: a first line; one recommended pick with its reason in a sentence and where it came from in plain words;
its link as a part of its own (a channel that shows link previews sends it as its own message); its details; then
"Alternatively, try these:" with one line each, and for an ask "Or here's a wider selection:". When nothing is a clear
fit, the closest is shown as the closest. Every count and the "top N" line are computed here, from the checked lines.
No "Why:" label.

A reply is a list of parts: {"type": "text", "text"} and {"type": "link", "url", "title", "platform", "video_id"}.
`Reply` joins with plain strings (`head + reply + tail`), so callers that add a line keep working.
"""
from datetime import datetime

LABEL = {"ingredients": "Ingredients", "steps": "Steps", "key_points": "Key points"}
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
def when_kept(it, now=None):
    """'which you sent to yourself in July', 'which you saved in March 2025': the strongest way they kept it."""
    kind = next((k for k in HOW_ORDER if k in it.kinds), None)
    if not kind:
        return ""
    day = it.dates.get(kind) or it.kept_on()
    try:
        d = datetime.fromisoformat(str(day)[:10])
    except (TypeError, ValueError):
        return f"which you {HOW[kind]}"
    this_year = (now or datetime.now()).year == d.year
    return f"which you {HOW[kind]} in {d.strftime('%B') if this_year else d.strftime('%B %Y')}"


def by(it):
    return f" by {it.creator}" if it.creator else ""


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


def details_lines(pick, extract):
    """The checked lines under their labels, counted here; for Instagram with nothing written, one plain line; for
    YouTube with nothing written, nothing (the video may well show it)."""
    out = []
    facts = pick.get("facts") or {}
    shown = False
    for kind in [k for k in ("ingredients", "steps", "key_points") if k in facts or k in (extract or [])]:
        lines = facts.get(kind) or []
        if not lines:
            continue
        shown = True
        out.append(f"{LABEL[kind]} ({len(lines)}):")
        if kind == "steps":
            out.extend(f"{i}. {line}" for i, line in enumerate(lines, 1))
        else:
            out.extend(f"• {line}" for line in lines)
    if not shown and pick.get("lines"):   # lines found before (a follow-up), kind unknown
        out.append(f"Details ({len(pick['lines'])}):")
        out.extend(f"• {line}" for line in pick["lines"])
        shown = True
    kind = None if shown else in_video(pick, extract)
    if kind:
        out.append(IN_VIDEO[kind])
    return out


def alt_note(pick, extract):
    """The one line after an alternative: what is written out (counted from checked lines), else its reason."""
    facts = pick.get("facts") or {}
    ing, steps, keys = facts.get("ingredients") or [], facts.get("steps") or [], facts.get("key_points") or []
    if ing:
        amounts = sum(any(ch.isdigit() for ch in line) for line in ing) * 2 >= len(ing)
        what = "the ingredients and steps are" if steps else "the ingredients are"
        return f"{what} written out" + (", with amounts" if amounts else "")
    if steps:
        return "the steps are written out"
    if keys:
        return "the tips are written out"
    if in_video(pick, extract) in ("ingredients", "steps"):
        return "the recipe is in the video"
    return pick["because"] if pick.get("because_backed") else ""


def picks_message(result, spec, footer=None, now=None):
    c = spec.content
    picks, wider = result["picks"], result.get("wider") or []
    parts = []
    text = []

    def flush():
        if text:
            parts.append({"type": "text", "text": "\n".join(text).strip("\n")})
            text.clear()

    first = picks[0]
    it = first["item"]
    kept = when_kept(it, now)
    where = f"{by(it)}, {kept}," if kept else f"{by(it)},"
    because = first["because"]
    if not first.get("because_backed") and kept:   # the plain clause; how they kept it is already in the sentence
        because = because.split(", and you ")[0]
    unknown = list(result.get("unknown_criteria") or [])
    if result.get("closest"):
        missing = result.get("missing") or []
        if missing:
            cr, ans = missing[0] if isinstance(missing[0], (list, tuple)) else (missing[0], "unknown")
            if cr in unknown:   # said once, here, with the reason
                unknown.remove(cr)
                text.append(f"None of what I found clearly meets \"{cr}\": the posts don't say.")
            else:
                text.append(f"None of what I found {'meets' if ans == 'no' else 'clearly meets'} \"{cr}\".")
        else:
            text.append(f"Nothing I found is a clear fit for \"{c.goal}\".")
        text.append("")
        text.append(f"The closest I have is {first['title']}{where} because {because}.")
    else:
        if result.get("intro"):
            text.append(result["intro"])
            text.append("")
        text.append(f"I recommend {first['title']}{where} because {because}.")
    flush()
    if it.url:
        parts.append(link_part(it, first["title"]))
    text.extend(details_lines(first, c.extract))
    if len(picks) > 1:
        text.append("")
        text.append("Alternatively, try these:")
        for p in picks[1:]:
            note = alt_note(p, c.extract)
            text.append(f"• {p['title']}{by(p['item'])}" + (f": {note}." if note else "") +
                        (f" {p['item'].url}" if p["item"].url else ""))
    if wider:
        text.append("")
        text.append("Or here's a wider selection:")
        for p in wider:
            text.append(f"• {p['title']}" + (f": {p['item'].url}" if p["item"].url else ""))
    for cr in unknown:
        text.append("")
        text.append(f"I couldn't check \"{cr}\" for any of these: the posts don't say.")
    if c.asked_count and c.asked_count > c.count:
        text.append("")
        text.append(f"You asked for {c.asked_count}, so here are the top {c.count}.")
    if footer:
        text.append("")
        text.append(footer)
    flush()
    return Reply(parts)


def none_message(result, spec, scheduled=False):
    reason = result.get("none_reason") or "nothing in your library fits well"
    if scheduled and spec.when.type == "once":
        return f"Nothing good for \"{spec.content.goal}\" right now: {reason.rstrip('.')}. Ask me again any time."
    if scheduled:
        return f"Nothing new for \"{spec.content.goal}\" this time: {reason.rstrip('.')}. I'd rather skip than send something weak."
    return f"I didn't find a good match: {reason.rstrip('.')}."


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
