"""PROTOTYPE ONLY - one webhook the operator made in an automation tool (IFTTT, Make, Zapier, n8n) (round 9, E;
DESIGN.md section 16.E; amendment A-014, Proposed).

Action `webhook.post` (registry): one small JSON POST to MVP_WEBHOOK_URL (https only), only after the person's yes to
exactly what will be sent; the preview says before the yes that the bot can't see or undo what the automation does.
There is no undo: what the automation did is out of the bot's reach. The address works like a password: it comes from
the environment only and is never logged, stored, shown or put in an error.

The JSON, fixed by code: {"kind": "todo", "title", "text", "link", "due", "list"}. title: the one thing's title (or,
for several, the list's name); text: the titles one a line when there are several; link: the post's link when every
item has the same one; due: a local time with its offset; list: the list's name. Nothing else (no caption, no
friend's post, no person's name).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from ..connectors import ConnectorError
from . import _tasks, web
from .base import Outcome

APP = "your webhook"


def settings():
    url = _tasks.env("MVP_WEBHOOK_URL")
    return {"url": url} if url and url.lower().startswith("https://") else None


def reachable():
    return settings() is not None


def yes_token(ctx, params):
    return _tasks.yes_token("webhook", ctx, params)


def payload(params, tz):
    items = params.items
    links = {i.notes for i in items}
    link = next(iter(links)) if len(links) == 1 and next(iter(links)).startswith("https://") else None
    dues = {i.due for i in items}
    due = None
    if len(dues) == 1 and items[0].due:
        due = datetime.strptime(items[0].due, "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo(tz)).isoformat()
    if len(items) == 1:
        title, text = items[0].title, ""
    else:
        title, text = params.list or f"{len(items)} things", "\n".join(i.title for i in items)
    return {"kind": "todo", "title": title, "text": text, "link": link, "due": due, "list": params.list}


def run(ctx, params):
    s = settings()
    if s is None:
        raise ConnectorError("unreachable", APP)
    web.call("POST", s["url"], None, payload(params, _tasks.tz_of(ctx)), app=APP)
    return Outcome("done", detail={"placed": [{"action": "webhook.post", "remote_id": "sent"}],
                                   "count": len(params.items)})


def remove(rows):
    """Nothing can be taken back from an automation."""
    return {"removed": [], "failed": [r["id"] for r in rows]}


def check():
    """No request at all: "check my webhook" only checks that an https address is set (sending a test would reach the
    automation without the person's yes)."""
    if settings() is None:
        raise ConnectorError("unreachable", APP)
    return {"ok": True}
