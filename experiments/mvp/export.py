"""PROTOTYPE ONLY - "export my data" and "export my lists" (round 8, slice B, I2; docs/07 › Retention and deletion: "Full
export of a user's data in open formats (JSON, CSV, Markdown)"; DESIGN.md section 15).

Code only, no model call. Everything is read through the store and the library view, so friends' posts never appear.
The files go in one folder under the person's own outbox folder (`MVP_HOME/outbox/<hashed handle>/export-<date>/`,
the same hashed folder as every outbox file, so no number or address is in a path); a second export on the same day
replaces that day's folder. "delete my data" removes every export folder (forget_exports).

- `export my data`: rules.json, todos.csv (title, due date, notes, done: a header a to-do app can import), todos.md,
  profile.json, answers.md (each answer as it was shown, with its links), saves.csv (id, link, platform, kept date,
  how; never a caption: post text is third-party text), README.txt (what each file is).
- `export my lists`: only todos.csv and todos.md, in `lists-<date>/`.
"""
import csv
import io
import json
import os
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from .actions.base import outbox_dir

DATA_FILES = ("rules.json", "todos.csv", "todos.md", "profile.json", "answers.md", "saves.csv", "README.txt")
LIST_FILES = ("todos.csv", "todos.md")
EMAIL_MAX_BYTES = 5 * 1024 * 1024    # saves.csv over this is not emailed (it stays in the folder)
TODO_HEADER = ["title", "due date", "notes", "done"]
SAVES_HEADER = ["id", "link", "platform", "kept date", "how"]

README = """What is in this folder (made {day} at your request):

rules.json    Your rules: their numbers, your own words, whether they are on, paused or finished, and when they send.
todos.csv     Your to-dos as a table a to-do app can import: title, due date, notes (a link, and the list's name when
              it is not your main list), done.
todos.md      The same lists, to read or paste into a notes app.
profile.json  What the bot knows about you: interests and levels, what you're working toward, preferences, email,
              time zone and quiet hours, and things you told it. What each topic is to you, when you said it ("for
              fun", "someday" ...), is with that topic; the topics you said are not you are listed under "not_me".
answers.md    Every answer the bot kept for you, as you were shown it, with its links.
saves.csv     Every post you kept that the bot can see (your own saves, likes, playlists and watches): its id, link,
              platform, the date you kept it and how. No post text, and never your friends' posts.

Saying "delete my data" to the bot removes this folder too.
"""


def _local(at_iso, tz):
    try:
        return datetime.fromisoformat(at_iso).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""


def folder_for(handle, kind, day):
    """The folder for this export (made empty): export-<day> or lists-<day> in the person's outbox folder."""
    d = os.path.join(outbox_dir(handle), f"{kind}-{day}")
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    return d


def todo_rows(store, handle, tz):
    """Open and done to-dos (never removed ones), in the order the bot numbers them."""
    rows = []
    for t in store.all_todos(handle):
        notes = [x for x in (t.get("url"),) if x]
        if (t.get("list") or "todo") != "todo":
            notes.append(f"list: {t['list']}")
        rows.append({"title": t["text"], "due date": _local(t["due_at"], tz) if t.get("due_at") else "",
                     "notes": "; ".join(notes), "done": "yes" if t.get("done_at") else "no",
                     "list": t.get("list") or "todo", "url": t.get("url")})
    return rows


def todos_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(TODO_HEADER)
    for r in rows:
        w.writerow([r[k] for k in TODO_HEADER])
    return buf.getvalue()


def todos_md(rows):
    if not rows:
        return "# Your lists\n\nYour lists are empty.\n"
    out = ["# Your lists"]
    for name in dict.fromkeys(r["list"] for r in rows):
        out += ["", f"## {'To-do' if name == 'todo' else name}"]
        for r in (x for x in rows if x["list"] == name):
            line = f"- [{'x' if r['done'] == 'yes' else ' '}] {r['title']}"
            if r["due date"]:
                line += f" (due {r['due date']})"
            if r["url"]:
                line += f" {r['url']}"
            out.append(line)
    return "\n".join(out) + "\n"


def rules_json(store, handle):
    from .schedule import describe
    from .schema import RuleSpec
    out = []
    for r in store.q("SELECT * FROM rules WHERE handle=? ORDER BY id", (handle,)):
        spec = json.loads(r["spec"])
        try:
            when = describe(RuleSpec.model_validate(spec).when)
        except Exception:  # noqa: BLE001 - an old spec that no longer validates still goes out as stored
            when = None
        out.append({"number": r.get("number"), "your_words": r.get("text"), "status": r["status"], "when": when,
                    "created": r.get("created_at"), "spec": spec})
    return json.dumps(out, ensure_ascii=False, indent=1), len(out)


def profile_json(store, handle):
    """profile.get, plus the topics the person said are not them (merge of round 8: profile.get leaves those markers
    out, so the theme check's labels would otherwise be lost from the export). The other labels ride on each interest
    as `relation` and `relation_at`."""
    from . import profile as P
    prof = P.get(store, handle)
    prof["not_me"] = [{"topic": i["topic"], "relation_at": i.get("relation_at")}
                      for i in P.not_me_markers(store, handle)]
    return json.dumps(prof, ensure_ascii=False, indent=1, default=str)


def answers_md(store, handle, tz):
    rows = store.q("SELECT run_id, goal, kind, parts, at FROM answers WHERE handle=? ORDER BY run_id", (handle,))
    if not rows:
        return "# Answers\n\nNo answers kept yet.\n"
    out = ["# Answers"]
    for r in rows:
        out += ["", f"## {r['goal'] or 'An answer'} ({_local(r['at'], tz)})", ""]
        for p in json.loads(r["parts"] or "[]"):
            if p.get("type") == "link" and p.get("url"):
                out.append(p["url"])
            elif p.get("text"):
                out.append(str(p["text"]).strip())
    return "\n".join(out) + "\n"


def saves_csv(view):
    """One row per kept item the library view holds (friends' posts are not in it). No caption."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(SAVES_HEADER)
    rows = sorted(view.items.values(), key=lambda it: (it.kept_on() or "", it.id), reverse=True)
    for it in rows:
        w.writerow([it.id, it.url or "", it.platform or "", it.kept_on() or "", "; ".join(it.how())])
    return buf.getvalue(), len(rows)


def _write(d, name, text):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def export(bot, person, now, lists_only=False):
    """Writes the export. Returns {"dir", "files": [(name, path)], "saves": n, "todos": n, "rules": n}."""
    h, tz = person["handle"], person["timezone"]
    day = now.astimezone(ZoneInfo(tz)).date().isoformat()
    d = folder_for(h, "lists" if lists_only else "export", day)
    rows = todo_rows(bot.store, h, tz)
    files = [("todos.csv", _write(d, "todos.csv", todos_csv(rows))), ("todos.md", _write(d, "todos.md", todos_md(rows)))]
    out = {"dir": d, "files": files, "todos": len(rows), "saves": None, "rules": None}
    if lists_only:
        return out
    rules, n_rules = rules_json(bot.store, h)
    files.insert(0, ("rules.json", _write(d, "rules.json", rules)))
    files.append(("profile.json", _write(d, "profile.json", profile_json(bot.store, h))))
    files.append(("answers.md", _write(d, "answers.md", answers_md(bot.store, h, tz))))
    text, n = saves_csv(bot.view(person["library"]))
    files.append(("saves.csv", _write(d, "saves.csv", text)))
    files.append(("README.txt", _write(d, "README.txt", README.format(day=day))))
    out.update(saves=n, rules=n_rules)
    return out


def attachments(files):
    """[(filename, path, maintype, subtype)] for an email: every file but one over EMAIL_MAX_BYTES; and the names
    left out."""
    types = {".json": ("application", "json"), ".csv": ("text", "csv"), ".md": ("text", "markdown"),
             ".txt": ("text", "plain")}
    att, left = [], []
    for name, path in files:
        if not os.path.isfile(path):
            continue
        if os.path.getsize(path) > EMAIL_MAX_BYTES:
            left.append(name)
            continue
        main, sub = types.get(os.path.splitext(name)[1], ("application", "octet-stream"))
        att.append((name, path, main, sub))
    return att, left


def forget_exports(handle):
    """'delete my data': every export and lists folder in the person's outbox folder. Returns how many went."""
    base = outbox_dir(handle)
    n = 0
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if os.path.isdir(p) and name.startswith(("export-", "lists-")):
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n
