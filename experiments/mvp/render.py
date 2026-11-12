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
    if not shown and extract and pick["item"].platform == "instagram":
        kind = next((k for k in ("ingredients", "steps", "key_points") if k in extract), None)
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
    if extract and pick["item"].platform == "instagram" and set(extract) & {"ingredients", "steps"}:
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
    if result.get("closest"):
        missing = result.get("missing") or []
        if missing:
            cr, ans = missing[0] if isinstance(missing[0], (list, tuple)) else (missing[0], "unknown")
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
    for cr in result.get("unknown_criteria") or []:
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
