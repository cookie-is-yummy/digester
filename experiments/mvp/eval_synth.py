"""PROTOTYPE ONLY - the synthesis evaluation (round 11, slice M; DESIGN.md section 18.M).

    python3 -m mvp.eval_synth mvp/evalset/synth --mode before|after --out <folder outside git> [--ids s01,s02]
    python3 -m mvp.eval_synth --real <library> --topics-file <file outside git> --out <folder outside git>

from `experiments/`. MVP_HOME must name a new (missing or empty) folder; MVP_TOTAL_CAP_USD and MVP_LEDGER_HOME must be
set (live model calls). Each request is sent through the whole bot as a fresh made-up person (the console channel, the
real search engine on a copy of the made-up library, YouTube descriptions from the set's own file through a fake
videos.list; nothing is fetched from the web).

- before: the read of this slice is off (synth.ON False): the message goes to the interpreter, as on build 84a413a.
- after: the read is on.
- --real: the requests of a file outside git (one JSON object per line, {"id", "message"}) on a real library, read only;
  counts only are printed and kept (never a title, a topic or a reply), the replies go to the out folder.

Scored by code (`score_answer`): the points shown (for "before", the key point lines shown under each pick; for "after",
the numbered points), the points traceable by code to the text of an item they cite (a whole run of its words, or
synth.TRACE_MIN of the point's content words with every number), the items cited by a shown point, how many of them are
among the set's fitting items, and whether 3 or more items are cited. Writes counts.json (numbers only) and
transcript.md (the made-up replies) to --out.
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)


def score_answer(points, texts_of, fit=None):
    """points: [{"text", "ids"}]; texts_of: {id: the item's own text, its description included}; fit: the ids that
    truly fit (or None)."""
    from .compose import line_in_text, numbers_backed
    from .synth import TRACE_MIN, trace_share
    traced, cited = 0, []
    for p in points:
        texts = [texts_of[i] for i in p["ids"] if i in texts_of]
        for i in p["ids"]:
            if i in texts_of and i not in cited:
                cited.append(i)
        if any(line_in_text(p["text"], t) for t in texts) or (
                texts and trace_share(p["text"], texts) >= TRACE_MIN and numbers_backed(p["text"], "\n".join(texts))):
            traced += 1
    out = {"points": len(points), "traceable": traced, "cited": len(cited)}
    if fit is not None:
        out["cited_fit"] = sum(1 for i in cited if i in fit)
        out["cited_unfit"] = len(cited) - out["cited_fit"]
    out["ge3"] = len(cited) >= 3
    return out


def _before_points(bot, handle, reply):
    """The key point lines today's answer showed, each citing its own pick (lines not in the reply are not counted)."""
    last = bot.store.last_answer(handle)
    if not last:
        return []
    kept = bot.store.answer(last["run_id"]) or {}
    out = []
    for p in kept.get("picks") or []:
        for line in p.get("lines") or []:
            if line and line in reply:
                out.append({"text": line, "ids": [p["item_id"]]})
        for x in p.get("items") or []:   # an items answer: each named thing with its words is a point of its post
            shown = x.get("shown") or ""
            if shown and shown in reply:
                out.append({"text": shown, "ids": [p["item_id"]]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="?")
    ap.add_argument("--mode", choices=("before", "after"), default="after")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids")
    ap.add_argument("--real")
    ap.add_argument("--topics-file")
    ap.add_argument("--cap", type=float, default=0.40, help="this run's own spend at most (dollars)")
    a = ap.parse_args(argv)
    home = os.environ.get("MVP_HOME")
    if not home or (os.path.exists(home) and os.listdir(home)):
        sys.exit("MVP_HOME must name a new, empty folder.")
    if not os.environ.get("MVP_TOTAL_CAP_USD") or not os.environ.get("MVP_LEDGER_HOME"):
        sys.exit("Set MVP_TOTAL_CAP_USD and MVP_LEDGER_HOME first (the shared cap must count every call).")
    sys.path.insert(0, EXP)
    from mvp import config, llm, synth, ytinfo
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    os.makedirs(home, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    spent = {"usd": 0.0, "calls": {}}
    real_chat = llm.chat_json

    def counted(system, user, purpose, prompt_version, *x, **kw):
        if spent["usd"] >= a.cap:
            raise RuntimeError("budget stop: this eval's own cap")
        out, cost = real_chat(system, user, purpose, prompt_version, *x, **kw)
        spent["usd"] += cost or 0.0
        spent["calls"][purpose] = spent["calls"].get(purpose, 0) + 1
        return out, cost
    llm.chat_json = counted
    if a.real:
        lib = os.path.abspath(a.real)
        rows = [json.loads(x) for x in open(a.topics_file, encoding="utf-8") if x.strip()]
        fits, desc = {}, None
    else:
        src = os.path.join(os.path.abspath(a.set), "library")
        lib = os.path.join(home, "synthlib")
        shutil.copytree(src, lib)
        sys.path.insert(0, os.path.join(EXP, "demo"))
        import library as LIB

        from mvp import refresh
        LIB.ensure_empty_te_files(lib)
        router = os.path.join(config.REPO, "data", "all", "r7", "router.npz")   # as the self-test does
        if os.path.isfile(router):
            os.makedirs(os.path.join(lib, "r7"), exist_ok=True)
            shutil.copyfile(router, os.path.join(lib, "r7", "router.npz"))
        r = refresh.prepare_library(lib, 0.05)
        if not r["ok"]:
            sys.exit("The made-up library could not be prepared for search.")
        rows = [json.loads(x) for x in open(os.path.join(a.set, "topics.jsonl"), encoding="utf-8") if x.strip()]
        fits = {r["id"]: set(r["fit"]) for r in rows}
        desc = json.load(open(os.path.join(a.set, "descriptions.json"), encoding="utf-8"))
    if a.ids:
        rows = [r for r in rows if r["id"] in a.ids.split(",")]
    synth.ON = a.mode == "after"
    store = Store(config.DB)
    ch = ConsoleChannel(printer=None)
    bot = Bot(ch, store=store)
    bot.max_per_minute = None
    if desc is not None:   # the set's own descriptions; nothing is fetched
        os.environ["MVP_SYNTH_EVAL_KEY"] = "fake"

        def fetch(ids, key, timeout=None):
            return {"items": [{"id": v, "snippet": {"description": desc[v], "publishedAt": "2026-01-02T00:00:00Z"},
                               "contentDetails": {"duration": "PT9M"}} for v in ids if v in desc]}
        bot.yt = ytinfo.YouTubeInfo(store, fetch=fetch, key_env="MVP_SYNTH_EVAL_KEY")
    people = {}
    for r in rows:
        people[f"eval-{r['id']}"] = {"name": "Eval", "library": lib, "timezone": "America/New_York"}
    path = os.path.join(home, "people.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(people, f)
    bot.load_people(path)
    caught = {}
    real_summarize = synth.summarize

    def keep_result(b, person, req, now, last=None):
        res = real_summarize(b, person, req, now, last=last)
        caught[person["handle"]] = res
        return res
    synth.summarize = keep_result
    results, transcript = [], []
    for r in rows:
        h = f"eval-{r['id']}"
        store.set_consent(h, "eval")
        n0, usd0, t0 = len(ch.outbox), spent["usd"], time.time()
        try:
            bot.on_message(h, r["message"])
        except Exception as e:  # noqa: BLE001
            transcript.append(f"## {r['id']}\n\nERROR {type(e).__name__}\n")
            results.append({"id": r["id"], "error": type(e).__name__})
            continue
        reply = "\n".join(t for _, _, t in ch.outbox[n0:])
        view = bot.view(lib)
        if h in caught:
            res = caught[h]
            points = [{"text": p["text"], "ids": p["ids"]} for p in res["points"] if p["text"] in reply]
            extra = res.get("extra") or {}
        else:
            points = _before_points(bot, h, reply)
            extra = bot._youtube().details([view.get(i) for p in points for i in p["ids"] if view.get(i)])
        from mvp.compose import check_text
        texts_of = {i: check_text(view.get(i), extra) for p in points for i in p["ids"] if view.get(i) is not None}
        s = score_answer(points, texts_of, fits.get(r["id"]))
        s.update({"id": r["id"], "usd": round(spent["usd"] - usd0, 5), "seconds": round(time.time() - t0, 1),
                  "dropped": (caught.get(h) or {}).get("dropped") or {},
                  "thin": bool((caught.get(h) or {}).get("thin")),
                  "fit_found": len((caught.get(h) or {}).get("fits") or [])})
        results.append(s)
        if not a.real:
            gone = "\n".join(f"- dropped ({why}): {txt}" for why, txt in (caught.get(h) or {}).get("dropped_text") or [])
            transcript.append(f"## {r['id']} {r['topic']}\n\n> {r['message']}\n\n{reply}\n" + (
                f"\n{gone}\n" if gone else ""))
        else:
            transcript.append(f"## {r['id']}\n\n{reply}\n")
        print(json.dumps({k: v for k, v in s.items()}))
    synth.summarize = real_summarize
    llm.chat_json = real_chat
    ok = [x for x in results if "error" not in x]
    total = {"mode": a.mode if not a.real else "real", "n": len(results), "errors": len(results) - len(ok),
             "points": sum(x["points"] for x in ok), "traceable": sum(x["traceable"] for x in ok),
             "cited": sum(x["cited"] for x in ok), "ge3": sum(1 for x in ok if x["ge3"]),
             "usd": round(spent["usd"], 4), "calls": spent["calls"],
             "seconds": round(sum(x["seconds"] for x in ok), 1)}
    if not a.real:
        total["cited_fit"] = sum(x.get("cited_fit", 0) for x in ok)
        total["cited_unfit"] = sum(x.get("cited_unfit", 0) for x in ok)
    total["dropped"] = {}
    for x in ok:
        for k, v in x["dropped"].items():
            total["dropped"][k] = total["dropped"].get(k, 0) + v
    print(json.dumps(total))
    with open(os.path.join(a.out, "counts.json"), "w", encoding="utf-8") as f:
        json.dump({"total": total, "per_request": results}, f, indent=1)
    with open(os.path.join(a.out, "transcript.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(transcript))
    try:
        bot.pool.stop_all()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
