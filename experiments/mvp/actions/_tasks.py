"""PROTOTYPE ONLY - what the two task apps by token share (round 9, E; DESIGN.md section 16.E): the yes token of the
exact rows shown, a local due time turned into UTC, and "all or nothing" for a batch (a task app that took only part
of it has that part deleted again, so the person's list is never half there)."""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..connectors import ConnectorError


def env(name):
    """A setting from the environment, stripped; None when unset or empty. Never logged, never stored."""
    v = (os.environ.get(name) or "").strip()
    return v or None


def yes_token(key, ctx, params):
    from . import make_yes_token, text_hash
    canon = json.dumps(params.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return make_yes_token(ctx.handle, key, text_hash(canon))


def tz_of(ctx):
    return ((getattr(ctx, "person", None) or {}).get("timezone") or getattr(ctx, "tz", None) or "America/New_York")


def utc_of(local, tz):
    """'YYYY-MM-DDTHH:MM' wall time in `tz` -> an aware UTC datetime."""
    return datetime.strptime(local, "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def add_all(items, add_one, delete_one, app):
    """Adds each item with add_one(item) -> remote id. On a failure the ones already added are deleted again with
    delete_one(remote id); the error is raised with code "partial" when one of those could not be deleted."""
    made = []
    for it in items:
        try:
            made.append(add_one(it))
        except ConnectorError as e:
            left = False
            for rid in made:
                try:
                    delete_one(rid)
                except ConnectorError as d:
                    left = left or d.code != "gone"
            raise ConnectorError("partial" if left else e.code, app) from None
    return made


def remove_rows(rows, delete_one):
    """{"removed": [placement ids], "failed": [...]}; a task already gone (404) counts as removed."""
    out = {"removed": [], "failed": []}
    for r in rows:
        try:
            delete_one(r["remote_id"])
            out["removed"].append(r["id"])
        except ConnectorError as e:
            out["removed" if e.code == "gone" else "failed"].append(r["id"])
    return out
