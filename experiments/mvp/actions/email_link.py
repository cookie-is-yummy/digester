"""PROTOTYPE ONLY - email.draft_link (round 9, slice A, W2; DESIGN.md section 16.A).

The link that opens one draft card's email in the person's own mail app (a mailto: link, RFC 6068). Nothing is sent:
the person checks it there and presses Send themselves. Only the bot's own code runs it (from_model=False), never in
a rule or a later action (in_rules=False), at most 20 a day per person (the registry entry). The link is built from
the draft row as it is now, so it is always the version the card shows.
"""
from .base import Outcome


def run(ctx, params):
    from ..drafts import mailto
    row = ctx.store.draft(params.draft_id)
    if row is None or row["handle"] != ctx.handle:
        return Outcome("failed", detail={"error": "NoDraft"})
    url = mailto(row.get("to_addr") or "", row.get("subject") or "", row.get("body") or "", params.cut_note)
    return Outcome("done", detail={"url": url})
