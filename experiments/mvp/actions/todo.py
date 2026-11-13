"""PROTOTYPE ONLY - todo.add (DESIGN.md sections 2 and 11): picks of an answer go on one of the person's lists.

"what": "pick" adds each pick's checked title and its link; "what": "ingredients" adds each checked ingredient line of
the pick (lines the details step verified against the item's own text, kept apart from the steps). Nothing is written
unless everything asked for can be added. This is the one implementation: a rule's or an ask's `do`, "add the first
one to my list" (act_on_last) and "add its ingredients to my grocery list" (todo_add) all come here.
"""
from .. import texts as T
from ..schedule import say_time
from ..schema import list_name
from .base import Outcome


def rows_for(picks, what="pick", due=None):
    """[(text, item_id, url, due)] for the picks, or (None, reason) when one pick has no ingredient lines of its own."""
    rows = []
    for p in picks:
        if what == "ingredients":
            ing = (p.get("facts") or {}).get("ingredients")
            if not ing:   # lines found before the details step kept kinds apart: only if they are ingredients alone
                if p.get("line_kinds") == ["ingredients"] and p.get("lines"):
                    ing = p["lines"]
                else:
                    return None, "no_ingredients"
            rows += [(line, p["item_id"], None, None) for line in ing]
        else:
            rows.append((p["title"], p["item_id"], p.get("url"), due))
    return rows, None


def add(bot, person, picks, what="pick", name="todo", due=None, undoable=True):
    """Writes the to-dos, records the write for "undo" (for a timed send, undoable=False, apart from the person's own
    writes: review fix S4), and returns the Outcome with the line that says what was added and where."""
    h = person["handle"]
    rows, problem = rows_for(picks, what, due)
    if problem:
        return Outcome("skipped", line=T.NO_INGREDIENTS)
    if not rows:
        return Outcome("skipped", line=T.NO_PICK_TO_ADD)
    now = bot.clock()
    ids = [bot.store.add_todo(h, text, name, item_id=iid, url=url, due_at=d, at=now) for text, iid, url, d in rows]
    bot._wrote(h, "todo_add", f"added {len(ids)} to-do{'s' if len(ids) > 1 else ''} to the list \"{name}\"",
               {"ids": ids}, timed=not undoable)
    due_text = say_time(due, now, person["timezone"]) if due else None
    return Outcome("done", line=T.todos_added([r[0] for r in rows], name, due_text), ref=",".join(map(str, ids)),
                   detail={"ids": ids, "list": name})


def run(ctx, params):
    if not ctx.picks:   # a reminder or a list has no picks to add
        return Outcome("skipped")
    name = list_name(params.list) or "todo"
    picks = ctx.picks
    if params.what == "ingredients" and ctx.kind != "act_on_last":
        picks = picks[:1]   # a rule's or an ask's do: the recommended pick's ingredients
    return add(ctx.bot, ctx.person, picks, params.what, name, undoable=ctx.kind != "scheduled")
