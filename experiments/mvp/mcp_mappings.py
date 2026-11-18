"""PROTOTYPE ONLY - which MCP servers the bot may call, and how one bot action becomes one server tool (round 10,
slice C; DESIGN.md section 17.C; amendment A-015, Proposed).

SERVERS is code: a server's address is never taken from a chat message, a caption, a result or a tool description.
A Mapping turns the bot's own checked params (actions.PlaceTodoParams: the titles and links the person saw in the
preview) into the server's arguments, reads the remote ids from the result, and names the one tool that undoes it.
The model never chooses a tool or writes an argument.

Todoist (`todoist.mcp_add`): `add-tasks` with `content` = the title shown, `description` = the post's own link (or
nothing), at most 25 tasks a call; NO `dueString` (verdict M-6: how Todoist reads a date string made by code is not
verified, so a due time never goes this way; places.py keeps a to-do with a time on the bot's list instead). Undo:
`delete-object {"type": "task", "id"}` on an id the bot recorded in placements. Schemas: @todoist/mcp 16.1.0's types
(tests/fakes/fake_mcp.py holds them). Not in this round (verdict M-1, M-5): TickTick, Notion, Gmail, Calendar.
"""
from collections.abc import Callable
from dataclasses import dataclass

from .mcp_client import McpError, an_id, structured

TODOIST_MAX = 25   # Todoist's own MAX_TASKS_PER_OPERATION for add-tasks

# key -> the server's fixed address, the issuer its sign-in must come from, how the bot registers, what it asks for
SERVERS = {
    "todoist": {"key": "todoist", "app": "Todoist", "url": "https://ai.todoist.net/mcp",
                "issuer": "https://todoist.com", "registration": "cimd_or_dcr", "scope": "data:read_write",
                "testers": False},
}


@dataclass(frozen=True)
class Mapping:
    key: str                     # "<bot action>@mcp"
    action: str                  # the registry action it serves
    server: str                  # a key of SERVERS
    tool: str                    # the one tool it creates with
    build: Callable              # (params, ctx) -> [arguments dict, ...] (one per tools/call)
    read: Callable               # (result dict) -> [remote id, ...]; raises McpError
    undo_tool: str | None = None
    undo_args: Callable | None = None   # remote id -> arguments
    needed: tuple = ()           # other tools it needs pinned

    def tools(self):
        return (self.tool,) + ((self.undo_tool,) if self.undo_tool else ()) + tuple(self.needed)


def todoist_build(params, ctx=None):
    """PlaceTodoParams -> add-tasks arguments: the title and the link only (never a caption, never a due time)."""
    tasks = []
    for it in params.items:
        t = {"content": it.title}
        if it.notes:
            t["description"] = it.notes
        tasks.append(t)
    return [{"tasks": tasks[i:i + TODOIST_MAX]} for i in range(0, len(tasks), TODOIST_MAX)]


def todoist_read(res):
    """add-tasks' answer -> the new task ids. A `failures` list means part of the call was not done: the ids that
    were made travel with the error, so the caller deletes them again (all or nothing)."""
    d = structured(res)
    tasks = d.get("tasks")
    if not isinstance(tasks, list):
        raise McpError("bad_result")
    ids = [an_id(t.get("id") if isinstance(t, dict) else None) for t in tasks]
    if d.get("failures"):
        raise McpError("tool_error", made=ids)
    if not ids:
        raise McpError("bad_result")
    return ids


MAPPINGS = {
    "todoist.mcp_add": Mapping("todoist.add@mcp", "todoist.mcp_add", "todoist", "add-tasks", todoist_build,
                               todoist_read, "delete-object", lambda rid: {"type": "task", "id": rid}),
}
# connector key -> the MCP action that adds a to-do there (connectors.route_for)
TODO_ACTION = {"todoist": "todoist.mcp_add"}
