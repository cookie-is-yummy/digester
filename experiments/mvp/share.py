"""PROTOTYPE ONLY - "send this to my sister", "share the second one", "forward this": a message the person can forward
themselves (round 8, slice B, I3; vision want 5, "share it with the right person"; DESIGN.md section 15).

The bot never sends to anyone but the person (DESIGN.md sections 6 and 11). It hands them one message that stands alone,
with no bot wording, made only of what the answer already showed and code checked: the post's title and creator, one
line of the post's own words (its first key point, or for a thing of an items answer the thing's own words), and the
link on its own line. Nothing personal goes in it: no kept date, no level, no reason (a reason is written about the
person), no rule footer. Who it is for is never stored or repeated.
"""


def _one_line(s, limit=200):
    s = " ".join(str(s or "").split())
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"


def pick_block(rec):
    """A kept pick (store.answers picks[]) as a forwardable block."""
    head = _one_line(rec.get("title") or "A post", 120) + (f" by {rec['creator']}" if rec.get("creator") else "")
    lines = [head]
    keys = (rec.get("facts") or {}).get("key_points") or []
    if keys and isinstance(keys[0], str):
        lines.append(_one_line(keys[0]))
    if rec.get("url"):
        lines.append(rec["url"])
    return "\n".join(lines)


def item_block(x, source):
    """A thing of an items answer (a kept pick's items[]) and the post it came from."""
    about = _one_line(x.get("about"))
    if about and x.get("stale_from"):
        about += f" (as of {x['stale_from']})"
    lines = [f"{_one_line(x.get('name'), 120)}: {about}" if about else _one_line(x.get("name"), 120)]
    src = _one_line(source.get("title"), 120)
    if src:
        lines.append(f"From \"{src}\"" + (f" by {source['creator']}" if source.get("creator") else ""))
    if source.get("url"):
        lines.append(source["url"])
    return "\n".join(lines)


def share_text(blocks):
    return "\n\n".join(b for b in blocks if b)
