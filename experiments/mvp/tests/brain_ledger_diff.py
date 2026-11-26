"""The planted set's frozen ledgers against today's tools (scratchpad mvp22, the read tools' fixes).

The planted sentences were labelled true or false against the cells of the ledgers frozen in eval/brain_planted.json.
The tools' fixes of mvp22 (tests/test_brain_toolfix.py) change some of those cells, so the frozen ledgers are left as
they are (re-freezing would change what the labels mean without anyone reading them again), and the freeze tests pin
exactly how today's tools differ from them: the list in eval/brain_toolfix_ledger_diff.json. Any other change of a
tool's result still fails them. MVP_FREEZE_TOOLFIX_DIFF=1 rewrites the list (read it before you commit it)."""
import json
import os

MVP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIFF = os.path.join(MVP, "eval", "brain_toolfix_ledger_diff.json")


def diff(a, b, path=""):
    """[[kind, path, frozen, today]] of every difference: a key added or removed, a list's length, a value."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append(["added", p, None, b[k]])
            elif k not in b:
                out.append(["removed", p, a[k], None])
            else:
                out += diff(a[k], b[k], p)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(["list_len", path, len(a), len(b)])
        for n, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{n}]")
    elif a != b:
        out.append(["changed", path, a, b])
    return out


def check(prefix, got, data):
    """Assert today's ledgers (`got`: {name: (envelopes, turn)}) differ from the frozen ones exactly as pinned."""
    with open(DIFF, encoding="utf-8") as f:
        pinned = json.load(f)
    mine = {}
    for name, (envs, t) in got.items():
        d = diff(data["ledgers"][prefix + name], envs)
        if d:
            mine[prefix + name] = json.loads(json.dumps(d, default=str))
        assert data[prefix + "turns"][name] == t, name
    if os.environ.get("MVP_FREEZE_TOOLFIX_DIFF") == "1":
        pinned = {k: v for k, v in pinned.items() if not k.startswith(prefix)}
        pinned.update(mine)
        with open(DIFF, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(pinned.items())), f, indent=1, ensure_ascii=False)
            f.write("\n")
    want = {k: v for k, v in pinned.items() if k.startswith(prefix)}
    assert sorted(mine) == sorted(want)
    for k in mine:
        assert mine[k] == want[k], k
