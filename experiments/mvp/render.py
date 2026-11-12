"""PROTOTYPE ONLY - turn checked picks into one plain-text message. Counts come from code (the matched lines)."""
from datetime import datetime

LABEL = {"ingredients": "Ingredients", "steps": "Steps", "key_points": "Key points"}
EMOJI = {"instagram": "📸", "youtube": "▶️"}


def _month(iso):
    try:
        return datetime.fromisoformat(iso[:10]).strftime("%b %Y")
    except (TypeError, ValueError):
        return None


def picks_message(result, spec, footer=None):
    c = spec.content
    picks = result["picks"]
    out = []
    if result.get("intro"):
        out.append(result["intro"])
    for i, p in enumerate(picks, 1):
        it = p["item"]
        how = it.how()
        kept = _month(it.kept_on() or "")
        source = " · ".join(x for x in [it.creator, (how[0] if how else None) and (how[0] + (f" in {kept}" if kept else ""))] if x)
        num = f"{i}. " if len(picks) > 1 else ""
        out.append(f"{num}{EMOJI.get(it.platform, '')} {p['title']}" + (f" ({source})" if source else ""))
        out.append(f"Why: {p['why']}")
        if c.extract:
            kind = c.extract[0] if len(c.extract) == 1 else "details"   # render v1: one label for the lines
            if p["lines"]:
                label = LABEL.get(kind, "Details")
                noun = label.lower()
                n = len(p["lines"])
                if n == 1:
                    noun = {"ingredients": "ingredient", "steps": "step", "key points": "key point",
                            "details": "detail"}[noun]
                out.append(f"{label} from the post ({n} {noun} listed):")
                out.extend(f"• {line}" for line in p["lines"])
            elif set(c.extract) & {"ingredients", "steps"}:
                what = " and ".join(x for x in c.extract if x in ("ingredients", "steps"))
                out.append(f"I couldn't find the {what} written in the post. They may be in the video.")
        if it.url:
            out.append(it.url)
        out.append("")
    if footer:
        out.append(footer)
    return "\n".join(out).strip()


def none_message(result, spec, scheduled=False):
    reason = result.get("none_reason") or "nothing in your library fits well"
    if scheduled and spec.when.type == "once":
        return f"Nothing good for \"{spec.content.goal}\" right now: {reason.rstrip('.')}. Ask me again any time."
    if scheduled:
        return f"Nothing new for \"{spec.content.goal}\" this time: {reason.rstrip('.')}. I'd rather skip than send something weak."
    return f"I didn't find a good match: {reason.rstrip('.')}."
