"""PROTOTYPE ONLY - every prompt's evaluation on a list of models, side by side (DESIGN.md section 20).

    python3 -m mvp.eval_models --models claude-haiku-5-5,gpt-5.4-mini --out <folder outside git>
                               [--evals insight,drafts,synth,selftest,rules] [--library <library>] [--max-usd 3]
                               [--judge-model same|<id>] [--quick] [--dry]
    python3 -m mvp.eval_models --list                    # every prompt the bot sends, with its evaluation

from `experiments/`. Each evaluation runs in its own process with MVP_MODEL (and MVP_JUDGE_MODEL: "same" = the model
under test, the default) set to the model, a new MVP_HOME, and its own folder <out>/<model>/<eval>/, so runs of two
models never overwrite each other. Per model it records the evaluation's own quality numbers, the model calls'
latency (median and worst, from the ledger rows the run tagged with MVP_RUN_TAG), and the cost; it stops a model's
evaluations once --max-usd has been spent on it (MVP_RUN_MAX_USD refuses the call that would pass it, mid-evaluation
too). One table for all: <out>/comparison.md and <out>/comparison.json.

A live run needs MVP_LEDGER_HOME (the shared ledger, so the caps count every call) and MVP_TOTAL_CAP_USD set, and a
key for every model named: with a claude- model and no DIGESTER_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY it stops at
once with that error, before anything is sent. --dry runs the same processes on fakes (tests/fakes/fake_anthropic.py
for Claude, fake OpenAI and Gemini answers and vectors): no network, $0; it tests this harness, not a model.

Evaluations that need a real library (--library; the founder's own, under data/) are skipped without one: kinds
(eval_kinds). The audit of history answers (eval_claims) and the theme names (themes build) are not run from here;
--list says how to run them on one model.
"""
import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
sys.path.insert(0, EXP)

# ---------- every prompt the bot sends (purpose, version, where, its evaluation and the command) ----------
PROMPTS = [
    ("interpret", "config.PROMPT_INTERPRET (interpret_v5)", "interpret.py", "rules, selftest",
     "python3 -m mvp.eval_rules mvp/evalset/rules_dev_timing.jsonl --out F (also _content, _extra)"),
    ("compose", "config.PROMPT_COMPOSE (compose_v5)", "compose.py", "kinds (library), selftest",
     "python3 -m mvp.eval_kinds mvp/evalset/kinds_dev.jsonl <library> --out DIR"),
    ("extract", "config.PROMPT_EXTRACT (extract_v4)", "extract.py", "kinds (library), selftest",
     "python3 -m mvp.eval_kinds mvp/evalset/kinds_dev.jsonl <library> --out DIR"),
    ("judge", "config.PROMPT_JUDGE (judge_kind_v2), on MVP_JUDGE_MODEL", "judge.py", "kinds (library)",
     "python3 -m mvp.eval_kinds mvp/evalset/kinds_dev.jsonl <library> --out DIR"),
    ("draft", "config.PROMPT_DRAFT (draft_v2)", "drafts.py", "drafts", "python3 -m mvp.eval_drafts --out DIR"),
    ("errand", "errand.PROMPT_VERSION (errand_v2), on MVP_ERRAND_MODEL or MVP_MODEL", "errand.py",
     "selftest (no scored set of its own in the repo)", "python3 -m mvp.selftest"),
    ("profile_guess", "config.PROMPT_PROFILE_GUESS (profile_guess_v3)", "profile.py",
     "selftest (no scored set of its own in the repo)", "python3 -m mvp.selftest"),
    ("profile_merge", "config.PROMPT_PROFILE_MERGE (profile_merge_v3)", "profile.py",
     "selftest; rules has profile cases (the interpreter's side)", "python3 -m mvp.selftest"),
    ("first_requests", "config.PROMPT_FIRST_REQUESTS (first_requests_v1)", "onboarding.py",
     "selftest (no scored set of its own in the repo)", "python3 -m mvp.selftest"),
    ("synth", "synth.PROMPT_VERSION (synth_v5)", "synth.py", "synth",
     "python3 -m mvp.eval_synth mvp/evalset/synth --mode after --out DIR"),
    ("insight", "insight.PROMPT_VERSION (insight_v5)", "insight.py",
     "insight (made-up sheets; its planted-falsehood sets test the code check, not the model); claims (library)",
     "python3 -m mvp.eval_insight --mode live --out F"),
    ("theme_name", "themes.PROMPT_VERSION (theme_name_v2)", "themes.py",
     "none scored: names were read by hand (DESIGN 19.D); run on one model, read the names",
     "MVP_MODEL=<model> python3 -m mvp.themes build <library>  (writes a new derived version beside the old)"),
    ("video_ask", "videoask.PROMPT_VERSION (video_ask_v2), Gemini only", "videoask.py",
     "videoask (stays on Gemini: Claude does not watch YouTube videos)",
     "python3 -m mvp.eval_videoask --list FILE --prompt video_ask_v2 --out F"),
    ("smoke", "smoke_v1", "llm.py", "it is the check", "python3 -m mvp.llm smoke [model]"),
]
# the history audit runs the insight writer on a real library; it is another builder's file this round
MANUAL = {"claims": "MVP_MODEL=<model> python3 -m mvp.eval_claims capture QUESTIONS.jsonl --out DIR --live N, "
                    "then python3 -m mvp.eval_claims audit DIR --json OUT"}

ORDER = ("insight", "drafts", "synth", "selftest", "rules", "kinds")   # cheapest first: a ceiling stops the dearest
# synth and the self-test build their made-up library's search with the real library's router (as the self-test does)
ROUTER = os.path.join(os.path.dirname(EXP), "data", "all", "r7", "router.npz")
# what an evaluation prints when a ceiling refused a call (MVP_RUN_MAX_USD, its own --max-usd / --cap, the self-test's)
STOP_WORDS = ("budget stop (run)", "eval budget used up", "this eval's own cap", "budget stop")
SECRETS = ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "DIGESTER_ANTHROPIC_API_KEY", "YOUTUBE_API_KEY",
           "ANTHROPIC_AUTH_TOKEN")   # a --dry run's processes get none of these: a call that escaped the fakes fails


def _rules_files():
    return [os.path.join("mvp", "evalset", f"rules_dev_{k}.jsonl") for k in ("timing", "content", "extra")]


def plan(name, d, quick, library, remaining, router=ROUTER):
    """([(argv, needs_new_home)], None) for one evaluation into folder d, or (None, why) when it cannot run here."""
    usd = f"{max(remaining, 0.0):.4f}"
    if name in ("synth", "selftest") and not os.path.isfile(router):
        return None, "skipped: needs data/all/r7/router.npz (the search router of a real library)"
    if name == "kinds" and not library:
        return None, "skipped: needs --library"
    return _plan(name, d, quick, library, usd), None


def _plan(name, d, quick, library, usd):
    if name == "insight":
        return [(["-m", "mvp.eval_insight", "--mode", "live", "--out", os.path.join(d, "rows.jsonl")]
                 + (["--cases", "top_lately,top_summer"] if quick else []), False)]
    if name == "drafts":
        return [(["-m", "mvp.eval_drafts", "--out", d, "--max-usd", usd] + (["--only", "d-dev-01"] if quick else []),
                 False)]
    if name == "synth":
        return [(["-m", "mvp.eval_synth", os.path.join("mvp", "evalset", "synth"), "--mode", "after", "--out", d,
                  "--cap", usd] + (["--ids", "s01"] if quick else []), True)]
    if name == "selftest":
        return [(["-m", "mvp.selftest", "--quiet", "--counts", os.path.join(d, "counts.jsonl")]
                 + (["--only", "c02"] if quick else []), True)]
    if name == "rules":
        return [(["-m", "mvp.eval_rules", f, "--out", os.path.join(d, os.path.basename(f).replace(".jsonl", ".json")),
                  "--workers", "4"] + (["--limit", "3"] if quick else []), False) for f in _rules_files()]
    if name == "kinds":
        return [(["-m", "mvp.eval_kinds", os.path.join("mvp", "evalset", "kinds_dev.jsonl"), library, "--out", d]
                 + (["--only", "1,2"] if quick else []), True)]
    raise SystemExit(f"unknown evaluation: {name}")


def last_json(text):
    """The last JSON object a run printed (one line, or an indented block starting with a line "{")."""
    lines = (text or "").splitlines()
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s.startswith("{"):
            continue
        for chunk in (s, "\n".join(lines[i:])):
            try:
                v = json.loads(chunk)
                if isinstance(v, dict):
                    return v
            except ValueError:
                pass
    return None


def quality(name, d, outs):
    """(headline, details) from what the evaluation wrote or printed."""
    try:
        if name == "insight":
            s = last_json(outs[0]) or {}
            return (f"{s.get('answers', 0)}/{s.get('cases', 0)} answered",
                    {k: s.get(k) for k in ("cases", "answers", "violations", "used", "kept", "dropped", "so_what",
                                           "run_of_counts")})
        if name == "drafts":
            s = last_json(outs[0]) or {}
            return (f"{s.get('passed', 0)}/{s.get('cases', 0)} passed",
                    {k: s.get(k) for k in ("cases", "passed", "first_try", "fell_back", "must_missing",
                                           "must_not_hits", "two_to_five_sentences")})
        if name == "synth":
            t = json.load(open(os.path.join(d, "counts.json")))["total"]
            return (f"{t.get('traceable', 0)}/{t.get('points', 0)} points traceable",
                    {k: t.get(k) for k in ("n", "errors", "points", "traceable", "cited", "ge3", "cited_fit",
                                           "cited_unfit")})
        if name == "selftest":
            s = last_json(outs[0]) or {}
            return (f"{s.get('steps_ok', 0)}/{s.get('steps', 0)} steps ok",
                    {k: s.get(k) for k in ("conversations", "ran", "steps", "steps_ok", "stopped")}
                    | {"failed": len(s.get("failed") or [])})
        if name == "rules":
            per, p, n = {}, 0, 0
            for f in _rules_files():
                path = os.path.join(d, os.path.basename(f).replace(".jsonl", ".json"))
                if not os.path.exists(path):   # stopped at the ceiling before this file
                    per[os.path.basename(f)] = "not run"
                    continue
                j = json.load(open(path))
                per[os.path.basename(f)] = f"{j['passed']}/{j['cases']}"
                p, n = p + j["passed"], n + j["cases"]
            return f"{p}/{n} passed" + (" (partial)" if "not run" in per.values() else ""), per
        if name == "kinds":
            rows = json.load(open(os.path.join(d, "counts.json")))["rows"]
            shown = sum(len(r.get("things_shown") or []) for r in rows)
            judged = [r.get("judge") or {} for r in rows]
            return (f"{len(rows)} requests, {shown} things shown",
                    {"requests": len(rows), "things_shown": shown, "judge_yes": sum(j.get("yes", 0) for j in judged),
                     "judge_no": sum(j.get("no", 0) for j in judged)})
    except (OSError, ValueError, KeyError, TypeError) as e:
        return f"no score ({type(e).__name__})", {}
    return "no score", {}


def ledger_rows(ledger, tag):
    if not os.path.exists(ledger):
        return []
    out = []
    with open(ledger, encoding="utf-8") as f:
        for line in f:
            if tag in line:
                r = json.loads(line)
                if r.get("run") == tag:
                    out.append(r)
    return out


def call_numbers(rows, model):
    """Calls, errors, latency (median and worst) of the model's own calls; cost of everything the run logged."""
    mine = [r for r in rows if r.get("model") == model]
    secs = [r["seconds"] for r in mine if isinstance(r.get("seconds"), (int, float)) and not r.get("estimated")]
    return {"calls": len(mine), "estimated_rows": sum(1 for r in mine if r.get("estimated")),
            "median_s": round(statistics.median(secs), 2) if secs else None,
            "worst_s": round(max(secs), 2) if secs else None,
            "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 6),
            "model_cost_usd": round(sum(r.get("cost_usd") or 0 for r in mine), 6)}


def key_problem(models, environ):
    """Fail fast: the error a live run would meet first (a missing key), or None."""
    from mvp import config   # config only: nothing is sent, no key is read but by name
    sys.path.insert(0, os.path.join(EXP, "lib"))
    import ai
    if any(config.is_claude(m) for m in models):
        try:
            ai.anthropic_key()
        except ai.MissingKey as e:
            return str(e)
    if any(not config.is_claude(m) for m in models) and not environ.get("OPENAI_API_KEY"):
        return "no OpenAI key: set OPENAI_API_KEY to run a non-Claude model; nothing was sent"
    for need in ("MVP_LEDGER_HOME", "MVP_TOTAL_CAP_USD"):
        if not environ.get(need):
            return f"Set {need} first (the shared caps must count every call)."
    return None


def safe(model):
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in model)


def run_all(a, out=print):
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    evals = [e for e in ORDER if e in [x.strip() for x in a.evals.split(",")]] if a.evals else list(ORDER)
    os.makedirs(a.out, exist_ok=True)
    env0 = dict(os.environ)
    if a.dry:
        env0["MVP_LEDGER_HOME"] = os.path.join(os.path.abspath(a.out), "dry_ledger")
        env0.setdefault("MVP_TOTAL_CAP_USD", "1")
        env0["MVP_EVAL_DRY"] = "1"
        for k in SECRETS:
            env0.pop(k, None)
        env0["DIGESTER_ANTHROPIC_API_KEY"] = "dry-run-not-a-key"   # the fake client is built with it; never sent
    else:
        why = key_problem(models, env0)
        if why:
            out(why)
            return 2, None
    ledger = os.path.join(env0["MVP_LEDGER_HOME"], "ai_runs.jsonl")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    table = {"at": stamp, "dry": bool(a.dry), "max_usd_per_model": a.max_usd, "models": models, "evals": evals,
             "rows": []}
    for m in models:
        spent = 0.0
        for e in evals:
            d = os.path.join(os.path.abspath(a.out), safe(m), e)
            room = a.max_usd - spent
            row = {"model": m, "eval": e, "dir": d}
            steps, why = plan(e, d, a.quick, a.library, room)
            if steps is None:
                row.update(status=why, headline="", details={})
                table["rows"].append(row)
                continue
            if room <= 0:
                row.update(status=f"stopped: ${a.max_usd:.2f} spent on this model", headline="", details={})
                table["rows"].append(row)
                continue
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d)
            tag = f"eval_models:{stamp}:{safe(m)}:{e}"
            env = dict(env0, MVP_MODEL=m, MVP_RUN_TAG=tag, MVP_RUN_MAX_USD=f"{room:.6f}",
                       MVP_SELFTEST_CAP_USD=f"{room:.6f}", MVP_JUDGE_MODEL=m if a.judge_model == "same" else
                       a.judge_model)
            env.pop("MVP_ERRAND_MODEL", None)
            outs, rcs, t0, hit = [], [], time.time(), False
            for i, (argv, new_home) in enumerate(steps):
                # the room left for this step: what earlier steps of this evaluation spent is counted (rules has 3)
                step_room = room - sum(r.get("cost_usd") or 0 for r in ledger_rows(ledger, tag))
                if step_room <= 0:
                    outs.append("")
                    rcs.append("ceiling")
                    continue
                env.update(MVP_RUN_MAX_USD=f"{step_room:.6f}", MVP_SELFTEST_CAP_USD=f"{step_room:.6f}")
                env["MVP_HOME"] = os.path.join(d, f"home{i}")
                env["MVP_RUN_STOP_FILE"] = os.path.join(d, "ceiling_refusals.txt")
                if not new_home:
                    os.makedirs(env["MVP_HOME"], exist_ok=True)
                cmd = [sys.executable, "-m", "mvp.eval_models", "--child", "--"] + argv[1:] if a.dry else \
                    [sys.executable] + argv
                p = subprocess.run(cmd, cwd=EXP, env=dict(env), capture_output=True, text=True, timeout=a.timeout)
                outs.append(p.stdout)
                hit = hit or any(w in p.stdout + p.stderr for w in STOP_WORDS)
                rcs.append(p.returncode)
                with open(os.path.join(d, f"stdout{i}.txt"), "w", encoding="utf-8") as f:
                    f.write(p.stdout)
                with open(os.path.join(d, f"stderr{i}.txt"), "w", encoding="utf-8") as f:
                    f.write(p.stderr[-20000:])
            head, details = quality(e, d, outs)
            nums = call_numbers(ledger_rows(ledger, tag), m)
            spent += nums["cost_usd"]
            status = "ok" if all(rc == 0 for rc in rcs) else f"exit {','.join(str(rc) for rc in rcs)}"
            hit = hit or os.path.exists(os.path.join(d, "ceiling_refusals.txt"))
            if spent >= a.max_usd or hit or "ceiling" in rcs:
                status += "; ceiling reached"
            row.update(status=status, headline=head, details=details, wall_s=round(time.time() - t0, 1), **nums)
            table["rows"].append(row)
            out(f"{m} {e}: {head} | {nums['calls']} calls, median {nums['median_s']} s, worst {nums['worst_s']} s, "
                f"${nums['cost_usd']:.4f} | {status}")
    write_table(table, a.out)
    return 0, table


def write_table(table, out):
    with open(os.path.join(out, "comparison.json"), "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1)
    lines = [f"# Prompts on {', '.join(table['models'])} ({table['at']}{', dry run on fakes' if table['dry'] else ''})",
             "", f"Ceiling ${table['max_usd_per_model']:.2f} per model. Latency is per model call (the ledger rows of "
             "the run); cost is everything the run logged (search embeddings included).", "",
             "| eval | model | quality | calls | median s | worst s | cost $ | status |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in sorted(table["rows"], key=lambda r: (ORDER.index(r["eval"]), table["models"].index(r["model"]))):
        lines.append(f"| {r['eval']} | {r['model']} | {r.get('headline') or ''} | {r.get('calls', '')} | "
                     f"{r.get('median_s') if r.get('median_s') is not None else ''} | "
                     f"{r.get('worst_s') if r.get('worst_s') is not None else ''} | "
                     f"{r.get('cost_usd', '') if 'cost_usd' in r else ''} | {r['status']} |")
    lines += ["", "Details per row are in comparison.json; each run's own files are in <model>/<eval>/."]
    with open(os.path.join(out, "comparison.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------- --dry: the child process on fakes ----------
def _fake_vector(text, dims):
    h = hashlib.sha256((text or "").encode()).digest()
    v = [((h[i % 32] + i * 37) % 255) / 127.0 - 1.0 for i in range(dims or 1024)]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def child(argv):
    """Runs one evaluation module in this process with fake model clients (MVP_EVAL_DRY=1 only)."""
    if os.environ.get("MVP_EVAL_DRY") != "1":
        raise SystemExit("--child is for --dry runs only")
    import runpy
    from mvp import llm
    from mvp.tests.fakes.fake_anthropic import FakeAnthropic, reply
    ai = llm.ai

    def answer(body):
        n = sum(len(str(x.get("content", ""))) for x in body.get("messages", [])) + len(body.get("system", ""))
        return reply("{}", input_tokens=max(1, n // 4), output_tokens=5)
    ai.ANTHROPIC_CLIENT = FakeAnthropic(default=answer)

    def fake_chat(model, system, user, max_tokens=400, purpose="", prompt_version="", **extra):
        ai._guard("openai", model, (len(system) + len(user)) / 3.5, max_tokens)
        ai._log({"provider": "openai", "model": model, "purpose": purpose, "prompt_version": prompt_version, "n": 1,
                 "in_tokens": (len(system) + len(user)) // 4, "out_tokens": 5, "cost_usd": 0.0, "seconds": 0.0})
        return {}, {}

    def fake_embed(texts, model="text-embedding-3-small", dimensions=None, purpose=""):
        ai._log({"provider": "openai", "model": model, "purpose": purpose, "n": len(texts), "in_tokens": 0,
                 "out_tokens": 0, "cost_usd": 0.0, "seconds": 0.0})
        return [_fake_vector(t, dimensions) for t in texts]

    ai.openai_chat_json = fake_chat
    ai.openai_embed = fake_embed
    ai.gemini_json = lambda *a, **k: ({}, {})
    ai.gemini_embed = lambda texts, model, dimensions=None, **k: [_fake_vector(t, dimensions) for t in texts]
    mod = argv[1] if argv[:1] == ["-m"] else argv[0]
    rest = argv[2:] if argv[:1] == ["-m"] else argv[1:]
    sys.argv = [mod] + rest
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--child"]:
        rest = argv[2:] if argv[1:2] == ["--"] else argv[1:]
        try:
            child(["-m"] + rest)
        except SystemExit as e:
            if e.code is not None and not isinstance(e.code, int):
                print(e.code, file=sys.stderr)
            return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--evals", default="", help=f"a subset of {','.join(ORDER)}")
    ap.add_argument("--library", default="", help="a real library (kinds); without it, kinds is skipped")
    ap.add_argument("--max-usd", type=float, default=3.0, help="spend ceiling per model")
    ap.add_argument("--judge-model", default="same", help="MVP_JUDGE_MODEL for the runs ('same': the model)")
    ap.add_argument("--quick", action="store_true", help="a few cases of each (a check of the harness)")
    ap.add_argument("--dry", action="store_true", help="fake model clients: no network, $0")
    ap.add_argument("--timeout", type=float, default=3600.0, help="seconds per evaluation process")
    ap.add_argument("--list", action="store_true", help="every prompt the bot sends and its evaluation")
    a = ap.parse_args(argv)
    if a.list:
        for name, ver, where, ev, cmd in PROMPTS:
            print(f"{name}: {ver}; {where}; eval: {ev}\n    {cmd}")
        for name, cmd in MANUAL.items():
            print(f"(not run from here) {name}: {cmd}")
        return 0
    if not a.models or not a.out:
        ap.error("--models and --out are needed")
    rc, _ = run_all(a)
    return rc


if __name__ == "__main__":
    sys.exit(main())
