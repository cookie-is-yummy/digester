"""PROTOTYPE ONLY - round 9, slice U2 (DESIGN.md section 12, "Round 9, slice U2"): a second, stronger judgement of "is
this thing itself one of the kind asked for".

The small model reads each post (names, words, dates: extract.py); code checks and cleans what it read. Then, only for
a request that names a kind of thing and only when 2 or more things are left over all the posts read, ONE call to a
stronger model (config.JUDGE_MODEL; an empty name turns this off) gets the request, the kind on its own line and a
numbered list of the things (name, the post's own words about it cut short, the post's title), as data. It returns a
form: for each number "yes", "no" or "unsure". Code validates the form; a thing counts as the kind only on "yes", a
"no" thing is never counted or shown as the kind, and "unsure" keeps the small model's "fit". A failed call or an
invalid form changes nothing (the answer is today's), and the run records it. The verdicts are cached per post with
the items (the items' key parts plus the judge's prompt, model and effort), so a repeat costs nothing.
"""
import hashlib
import json
import os
import time

from . import config, llm
from .compose import as_data
from .retrieve import norm

VERDICTS = ("yes", "no", "unsure")
PER_POST = 8          # the first things of each post (an answer shows at most 6 of a post)
ABOUT_WORDS = 14      # the post's own words about a thing, cut short
TITLE_WORDS = 9
MIN_THINGS = 2


def prompt():
    return open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_JUDGE}.md"), encoding="utf-8").read()


def on():
    return bool((config.JUDGE_MODEL or "").strip())


def cache_kind(context):
    """The facts table's kind for one request's verdicts: the items' own key (extract.items_cache_kind) plus the
    judge's prompt, model and effort."""
    from .extract import items_cache_kind
    key = json.dumps([items_cache_kind(context), config.PROMPT_JUDGE, config.JUDGE_MODEL, config.JUDGE_EFFORT])
    return "judge:" + hashlib.sha256(key.encode()).hexdigest()[:16]


def _cut(text, n):
    words = " ".join(str(text or "").split()).split(" ")
    return " ".join(words[:n]) + (" …" if len(words) > n else "")


def entries(reads):
    """[(pick, thing)] to judge: the good things (answers.good) of each post read, the first PER_POST of each."""
    from .answers import good
    out = []
    for p in reads:
        got = [x for x in (p.get("facts") or {}).get("items") or [] if good(x)]
        out.extend((p, x) for x in got[:PER_POST])
    return out


def listing(todo):
    """The numbered list the judge reads (data, never instructions)."""
    rows = []
    for i, (p, x) in enumerate(todo, 1):
        row = f"{i}. {x['name']}"
        if x.get("about"):
            row += f": {_cut(x['about'], ABOUT_WORDS)}"
        row += f" (from the post \"{_cut(p.get('title') or '', TITLE_WORDS)}\")"
        rows.append(row)
    return as_data("\n".join(rows))


def parse(raw, n):
    """{number: verdict} from the judge's form, or None when the form is invalid (not an object with "is_kind", or no
    valid entry). A number outside 1..n or a word other than yes, no, unsure is left out (read as unsure)."""
    got = raw.get("is_kind") if isinstance(raw, dict) else None
    if isinstance(got, list):   # [{"n": 1, "is_kind": "yes"}, ...] is read too
        got = {str((r or {}).get("n")): (r or {}).get("is_kind") for r in got if isinstance(r, dict)}
    if not isinstance(got, dict):
        return None
    out = {}
    for k, v in got.items():
        try:
            i = int(str(k).strip().rstrip("."))
        except ValueError:
            continue
        v = str(v or "").strip().lower()
        if 1 <= i <= n and v in VERDICTS:
            out[i] = v
    return out or None


def apply(x, verdict):
    """A thing's verdict: "yes" makes it the kind, "no" never the kind, "unsure" keeps the small model's fit."""
    x["judge"] = verdict
    if verdict == "yes":
        x["fit"] = "yes"
    elif verdict == "no":
        x["fit"] = "no"


def judge_things(reads, kind, context, library, store=None, person=None, extra=None, now=None):
    """Judges the things of the posts read, in place. Returns info for the run's steps: things, yes, no, unsure,
    cached (things whose verdict was read from the cache), calls, cost, seconds, and error ("call" or "invalid") when
    the answer stays today's. {} when the judge is off, the request names no kind or fewer than MIN_THINGS are left."""
    if not on() or not kind:
        return {}
    todo = entries(reads)
    if len(todo) < MIN_THINGS:
        return {}
    t0 = time.time()
    info = {"things": len(todo), "cached": 0, "calls": 0, "cost": 0.0}
    ck = cache_kind(context)
    source = {}
    have = {}
    for p, _ in todo:
        it = p["item"]
        if it.id in have:
            continue
        source[it.id] = "youtube_api" if ((extra or {}).get(it.id) or {}).get("description") else "caption"
        got = store.facts_get(library, it.id, [ck]).get(ck) if store is not None else None
        have[it.id] = dict(got) if isinstance(got, dict) else {}
    verdicts = {}
    need = []
    for p, x in todo:
        v = have[p["item"].id].get(norm(x["name"]))
        if v in VERDICTS:
            verdicts[id(x)] = v
            info["cached"] += 1
        else:
            need.append((p, x))
    if need:
        user = ("Request: " + json.dumps(" ".join(str((context or {}).get("request") or "").split())[:300],
                                         ensure_ascii=False) +
                "\nKind asked for: " + json.dumps(" ".join(str(kind).split())[:80], ensure_ascii=False) +
                "\n\nThings:\n" + listing(need))
        try:
            raw, cost = llm.chat_json(prompt(), user, purpose="mvp_judge", prompt_version=config.PROMPT_JUDGE,
                                      person=person, max_tokens=1200 + 12 * len(need), model=config.JUDGE_MODEL,
                                      reasoning_effort=config.JUDGE_EFFORT or None)
        except Exception as e:  # noqa: BLE001 - a failed judgement never fails the answer: it stays today's
            if llm.budget_stop(e):
                raise
            info.update(error="call", seconds=round(time.time() - t0, 2))
            return info
        info["calls"], info["cost"] = 1, cost
        got = parse(raw, len(need))
        if got is None:
            info.update(error="invalid", seconds=round(time.time() - t0, 2))
            return info
        for i, (p, x) in enumerate(need, 1):
            v = got.get(i, "unsure")
            verdicts[id(x)] = v
            have[p["item"].id][norm(x["name"])] = v
        if store is not None:
            for iid in {p["item"].id for p, _ in need}:
                store.facts_put(library, iid, ck, have[iid], config.PROMPT_JUDGE, source=source[iid], at=now)
    for _, x in todo:
        apply(x, verdicts[id(x)])
    for v in VERDICTS:
        info[v] = sum(1 for _, x in todo if x.get("judge") == v)
    info["seconds"] = round(time.time() - t0, 2)
    return info
