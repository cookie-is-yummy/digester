"""PROTOTYPE ONLY - TickTick by a personal API token (round 9, E; DESIGN.md section 16.E; amendment A-014, Proposed).

Action `ticktick.add` (registry): tasks in the operator's TickTick, only after the person's yes to the exact rows shown
(places.py makes the preview and the yes token; actions.perform checks it). Settings from the environment only:
MVP_TICKTICK_TOKEN (TickTick web app: avatar › Settings › Account › API Token) and MVP_TICKTICK_PROJECT (a project id;
default "inbox"). The token is sent only in the Authorization header and never logged, stored or shown.

Request shapes checked on developer.ticktick.com/docs/openapi.md on 17 Nov 2026: POST /open/v1/task with title,
projectId, content, dueDate ("yyyy-MM-dd'T'HH:mm:ssZ"), timeZone, isAllDay; the answer's id and projectId; DELETE
/open/v1/project/{projectId}/task/{taskId}; GET /open/v1/project; "Authorization: Bearer <token>". Not confirmed there:
"inbox" as a projectId for creating a task (the page documents it for searching), and any rate limit.
"""
from ..connectors import ConnectorError
from . import _tasks, web
from .base import Outcome

API = "https://api.ticktick.com/open/v1"
APP = "TickTick"


def settings():
    token = _tasks.env("MVP_TICKTICK_TOKEN")
    return {"token": token, "project": _tasks.env("MVP_TICKTICK_PROJECT") or "inbox"} if token else None


def reachable():
    return settings() is not None


def yes_token(ctx, params):
    return _tasks.yes_token("ticktick", ctx, params)


def _s():
    s = settings()
    if s is None:
        raise ConnectorError("unreachable", APP)
    return s


def body_for(item, project, tz):
    b = {"title": item.title, "projectId": project}
    if item.notes:
        b["content"] = item.notes
    if item.due:
        b["dueDate"] = _tasks.utc_of(item.due, tz).strftime("%Y-%m-%dT%H:%M:%S+0000")
        b["timeZone"] = tz
        b["isAllDay"] = False
    return b


def run(ctx, params):
    s = _s()
    tz = _tasks.tz_of(ctx)

    def add(it):
        got = web.call("POST", f"{API}/task", s["token"], body_for(it, s["project"], tz), app=APP)
        if not got.get("id"):
            raise ConnectorError("failed", APP)
        return f"{got.get('projectId') or s['project']}/{got['id']}"
    ids = _tasks.add_all(params.items, add, _delete, APP)
    return Outcome("done", detail={"placed": [{"action": "ticktick.add", "remote_id": i} for i in ids],
                                   "count": len(ids)})


def _delete(remote_id):
    project, _, task = str(remote_id).partition("/")
    web.call("DELETE", f"{API}/project/{project}/task/{task}", _s()["token"], app=APP)


def remove(rows):
    return _tasks.remove_rows(rows, _delete)


def check():
    """A harmless read: the projects list (only that it answered is kept)."""
    web.call("GET", f"{API}/project", _s()["token"], app=APP)
    return {"ok": True}
