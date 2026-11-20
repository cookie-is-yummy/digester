"""PROTOTYPE ONLY - Todoist by a personal API token (round 9, E; DESIGN.md section 16.E; amendment A-014, Proposed).

Action `todoist.add` (registry): tasks in the operator's Todoist, only after the person's yes to the exact rows shown
(places.py). Settings from the environment only: MVP_TODOIST_TOKEN (Todoist: Settings › Integrations › Developer ›
API token) and MVP_TODOIST_PROJECT (a project id; default: the Inbox). The token is sent only in the Authorization
header and never logged, stored or shown.

Request shapes checked on developer.todoist.com/api/v1 on 17 Nov 2026: POST /api/v1/tasks with content (required),
description, project_id ("If omitted or null, the task will be added to the user's Inbox"), due_datetime (example
"2025-02-12T12:00:00Z"); the answer's id; DELETE /api/v1/tasks/{task_id}; GET /api/v1/projects; "Authorization:
Bearer $token". due_string is never sent, so Todoist never reads the person's words its own way. Not confirmed there:
a rate limit for these calls (the page states limits for the sync endpoint only).
"""
from ..connectors import ConnectorError
from . import _tasks, web
from .base import Outcome

API = "https://api.todoist.com/api/v1"
APP = "Todoist"


def settings():
    token = _tasks.env("MVP_TODOIST_TOKEN")
    return {"token": token, "project": _tasks.env("MVP_TODOIST_PROJECT")} if token else None


def reachable():
    return settings() is not None


def yes_token(ctx, params):
    return _tasks.yes_token("todoist", ctx, params)


def _s():
    s = settings()
    if s is None:
        raise ConnectorError("unreachable", APP)
    return s


def body_for(item, project, tz):
    b = {"content": item.title}
    if item.notes:
        b["description"] = item.notes
    if project:
        b["project_id"] = project
    if item.due:
        b["due_datetime"] = _tasks.utc_of(item.due, tz).strftime("%Y-%m-%dT%H:%M:%SZ")
    return b


def run(ctx, params):
    s = _s()
    tz = _tasks.tz_of(ctx)

    def add(it):
        got = web.call("POST", f"{API}/tasks", s["token"], body_for(it, s["project"], tz), app=APP)
        if not got.get("id"):
            raise ConnectorError("failed", APP)
        return str(got["id"])
    ids = _tasks.add_all(params.items, add, _delete, APP)
    return Outcome("done", detail={"placed": [{"action": "todoist.add", "remote_id": i} for i in ids],
                                   "count": len(ids)})


def _delete(remote_id):
    web.call("DELETE", f"{API}/tasks/{remote_id}", _s()["token"], app=APP)


def remove(rows):
    return _tasks.remove_rows(rows, _delete)


def check():
    web.call("GET", f"{API}/projects", _s()["token"], app=APP)
    return {"ok": True}
