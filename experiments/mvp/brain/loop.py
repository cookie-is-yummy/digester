"""PROTOTYPE ONLY - the brain loop, the thin live slice of step 2 (design/brain_v1/SPEC.md 3.4, 3.10, 4.5).

`run_turn(provider, turn, message, screen)`: the model answers one message by calling the processor's read tools
(brain/tools.py, through `tools.call`) in rounds, then filling `give_answer` (verify.AnswerForm as its schema). Code
verifies every sentence (verify.check_answer); a failed lead, or more than half of the sentences failed, gets ONE
repair request (the failures as the is_error result of that give_answer call, verify.repair_message); a lead that still
fails becomes the code lead (fallback.answer) with the points that passed. brain/answer.py assembles what goes out.

Rounds and deadlines (SPEC 3.4): at most ROUNDS tool rounds; past the soft deadline (SOFT_S; DEEP_S once `learned`
was called or a third round started) or out of rounds, every read call gets one is_error "time is up" and the next
response must be give_answer; a hard stop (HARD_S) ends the turn with the code lead. A response with only text gets one
nudge. give_answer beside read calls is refused (is_error) while the read calls run. Read calls run in call order
(rids follow it).

Nothing here is wired into the message path: the eval (eval_brain.py run) and the tests call it.

The tool_result text the model reads is `present(envelope)`: the envelope of SPEC 2.3 with the sheet's keys lifted to
the top beside rid, tool and meta, so a cell's path is literally the result id plus its JSON path (r1.totals.items),
the shape that removes "r1.sheet." by construction. The ledger keeps the envelope untouched.
"""
import json
import os
import re
import time

from . import answer as A
from . import fallback as FB
from . import tools as TL
from . import verify as V

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_VERSION = os.environ.get("MVP_BRAIN_PROMPT", "brain_v3")   # mvp20 fix: v3 (v1, v2 kept for reference)
PROMPT_PATH = os.path.join(os.path.dirname(HERE), "prompts", f"{PROMPT_VERSION}.md")
GIVE_ANSWER = "give_answer"
ROUNDS = int(os.environ.get("MVP_BRAIN_ROUNDS", "3"))
# mvp25 toolgaps 9: the speed bars are now 8 s at the median and 11 s at the slow end (they were 6 and 10). A read round
# that starts at the soft deadline still needs the answer request after it (4.2 s at the median in mvp24's run1), so
# the soft deadline is the slow-end bar less that: 11 - 4.2, about 7 (it was 6, the old median bar; 3 turns of run1
# were refused at 6.2 to 6.7 s). A deep round (a third round, or after `learned`) is refused past the slow-end bar
# itself, 11 (it was 12). The hard stop stays at 15: it is a stop, not a bar.
SOFT_S = float(os.environ.get("MVP_BRAIN_SOFT_S", "7"))
DEEP_S = float(os.environ.get("MVP_BRAIN_DEEP_S", "11"))
HARD_S = float(os.environ.get("MVP_BRAIN_HARD_S", "15"))
CALLS_MAX = 12
TIME_UP = "Time is up for this question. Call give_answer now with the results you already have."
ALONE = "call give_answer alone, after the results come back"
LIMIT = "limit for this question reached"
NUDGE = "(code) Finish by calling give_answer with that answer."
REPAIR_ONLY = "only give_answer is open now: rewrite the failed sentences"
GIVE_ANSWER_DESC = ("Your answer to their message: the lead, up to 3 points and offers, every number and name with "
                    "its marker. Code checks each sentence before anything is sent. Call it alone, after the results "
                    "come back.")


def system_text():
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def give_answer_schema():
    return TL._sorted(TL._strict(V.AnswerForm.model_json_schema(by_alias=True)))


def tool_list():
    """The nine read tools (sorted, byte-stable) and give_answer last."""
    return TL.schemas() + [{"name": GIVE_ANSWER, "description": GIVE_ANSWER_DESC,
                            "input_schema": give_answer_schema()}]


def present(env):
    """The tool_result text of one result: {"rid", "tool", "meta", <the sheet's keys>} (a sheet key that would clash
    with those three keeps the sheet nested under "sheet"); an error result as it is."""
    if not isinstance(env, dict) or "sheet" not in env:
        return json.dumps(env, ensure_ascii=False, sort_keys=True)
    sheet = env.get("sheet") or {}
    head = {"rid": env.get("rid"), "tool": env.get("tool"), "meta": env.get("meta")}
    if not isinstance(sheet, dict) or any(k in head for k in sheet):
        body = dict(head, sheet=sheet)
    else:
        body = dict(head, **sheet)
    return json.dumps(body, ensure_ascii=False, sort_keys=False)


def user_text(message, screen):
    scr = json.dumps(screen or {}, ensure_ascii=False, sort_keys=True)
    return f"<screen>\n{scr}\n</screen>\n<message>\n{message}\n</message>"


def _err(id_, text):
    return {"type": "tool_result", "tool_use_id": id_, "content": text, "is_error": True}


def _sentences_of(verdict):
    return [o for o in (verdict.outcomes if verdict else []) if o.where in ("lead", "point")]


def outcome_json(o):
    return {"where": o.where, "index": o.index, "text": o.text, "sent": o.sent, "kept": o.kept,
            "reasons": list(o.reasons), "details": list(o.details), "cells": {k: v for k, v in o.cells.items()},
            "rid": o.rid, "layer": o.layer, "hidden_rank": o.hidden_rank}


def verdict_json(v):
    if v is None:
        return None
    return {"outcomes": [outcome_json(o) for o in v.outcomes], "items": v.items, "outside": v.outside,
            "chart": v.chart, "form_error": v.form_error, "private_line": v.private_line, "repair": v.repair,
            "lead_ok": v.lead_ok, "version": v.version}


def run_turn(provider, turn, message=None, screen=None, now=time.monotonic, rounds=ROUNDS, soft_s=SOFT_S,
             deep_s=DEEP_S, hard_s=HARD_S, system=None, tools=None, check=None):
    """One message through the brain. `turn`: a tools.Turn for this message (its search / learned backends set);
    `screen`: the code-written screen (a dict); `check`: the checker's mode ("full", "cells"; None: MVP_BRAIN_CHECK,
    else "full"), resolved once for the whole turn. -> the turn record (see the module docstring and eval_brain run)."""
    cm = V.check_mode(check)
    message = turn.message if message is None else message
    screen = screen or {}
    if not turn.screen:
        turn.screen = json.dumps(screen, ensure_ascii=False, sort_keys=True)
    system = system if system is not None else system_text()
    tools = tools if tools is not None else tool_list()
    t0 = now()
    rec = {"message": message, "screen": screen, "calls": [], "forms": [], "verdicts": [], "repair_message": None,
           "requests": [], "events": [], "lead_source": None, "error": None, "answer": None, "check": cm.name,
           # mvp25 toolgaps 5: the topic this turn unlocked (code's, from their message or carried from the answer
           # before), so an offline re-read of the record reads the same rows
           "unlock": turn.unlock, "unlock_carried": bool(turn.carried_unlock and turn.unlock == turn.carried_unlock)}
    messages = [{"role": "user", "content": user_text(message, screen)}]
    vturn = V.Turn.of(turn)
    tool_rounds, calls_made, deep = 0, 0, False
    time_up_sent = nudged = repair_used = False
    verdicts, forms = [], []

    def elapsed():
        return now() - t0

    def send(max_tokens=None):
        left = max(1.0, hard_s - elapsed())
        r = provider.send(system, tools, messages, max_tokens=max_tokens, timeout=left)
        rec["requests"].append({"stop_reason": r.stop_reason, "usage": r.usage, "seconds": r.seconds,
                                "cost_usd": r.cost_usd, "retries": r.retries, "blocks": r.blocks})
        return r

    while True:
        if elapsed() >= hard_s:
            rec["events"].append("hard_stop")
            break
        try:
            r = send()
            if r.stop_reason == "max_tokens":
                rec["events"].append("max_tokens")
                r = send(max_tokens=2 * (getattr(provider, "max_tokens", 4000) or 4000))
        except Exception as e:  # noqa: BLE001 - a provider failure ends the turn with what is in hand
            rec["error"] = getattr(e, "kind", None) or type(e).__name__
            rec["events"].append("provider_error")
            break
        if r.stop_reason in ("refusal", "max_tokens"):
            rec["events"].append(r.stop_reason)
            break
        messages.append({"role": "assistant", "content": r.raw})
        uses = r.tool_uses()
        if not uses:
            if nudged or repair_used:
                rec["events"].append("no_call_after_nudge")
                break
            nudged = True
            rec["events"].append("nudge")
            messages.append({"role": "user", "content": NUDGE})
            continue
        ga = [u for u in uses if u.get("name") == GIVE_ANSWER]
        reads = [u for u in uses if u.get("name") != GIVE_ANSWER]
        results = []
        if repair_used:
            # the one repair request: only give_answer is open; anything else ends the turn after this answer
            for u in reads:
                results.append(_err(u["id"], REPAIR_ONLY))
            if ga:
                form = _take_form(ga[0], rec)
                forms.append(form)
                v = V.check_answer(form, turn.results, vturn, mode=cm)
                verdicts.append(v)
            else:
                rec["events"].append("repair_without_answer")
            break
        if ga and not reads:
            form = _take_form(ga[0], rec)
            forms.append(form)
            v = V.check_answer(form, turn.results, vturn, mode=cm)
            verdicts.append(v)
            if not v.repair:
                break
            if elapsed() >= hard_s - 3.0:
                rec["events"].append("no_time_for_repair")
                break
            repair_used = True
            msg = _form_error_text(form) if v.form_error else V.repair_message(v)
            rec["repair_message"] = msg
            results.append(_err(ga[0]["id"], msg))
            for u in ga[1:]:
                results.append(_err(u["id"], "one give_answer per response"))
            messages.append({"role": "user", "content": results})
            continue
        for u in ga:
            results.append(_err(u["id"], ALONE))
        limit = deep_s if deep else soft_s
        if tool_rounds >= rounds or elapsed() >= limit:
            if time_up_sent:
                rec["events"].append("tools_after_time_up")
                break
            time_up_sent = True
            rec["events"].append("time_up")
            for u in reads:
                results.append(_err(u["id"], TIME_UP))
            messages.append({"role": "user", "content": _ordered(uses, results)})
            continue
        tool_rounds += 1
        if tool_rounds >= 3:
            deep = True
        for u in reads:
            args = u.get("input") or {}
            if calls_made >= CALLS_MAX:
                env = {"is_error": True, "error": LIMIT, "tool": u.get("name")}
            else:
                calls_made += 1
                env = TL.call(turn, u.get("name"), args)
            if u.get("name") == "learned":
                deep = True
            rec["calls"].append({"round": tool_rounds, "id": u["id"], "name": u.get("name"), "args": args,
                                 "rid": env.get("rid"), "result": env})
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": present(env),
                            **({"is_error": True} if env.get("is_error") else {})})
        messages.append({"role": "user", "content": _ordered(uses, results)})

    rec["forms"] = forms
    rec["verdicts"] = [verdict_json(v) for v in verdicts]
    rec["rounds"] = tool_rounds
    _finish(rec, turn, vturn, verdicts, cm)
    rec["seconds"] = round(elapsed(), 2)
    rec["tokens"] = {k: sum(q["usage"].get(k, 0) for q in rec["requests"])
                     for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                               "cache_creation_input_tokens")}
    rec["cost_usd"] = round(sum(q["cost_usd"] for q in rec["requests"]), 6)
    rec["n_requests"] = len(rec["requests"])
    return rec


FORM_FIELDS = frozenset(V.AnswerForm.model_fields) | frozenset(
    f.alias for f in V.AnswerForm.model_fields.values() if f.alias)


def clean_form(form):
    """(form, dropped keys): the give_answer input with its unknown TOP-LEVEL keys left out before it is checked.
    give_answer is sent without strict (all ten tools strict is a grammar the API refuses), and the live run showed the
    model adding keys of its own ("understood_note": "x", "lead_fix": null) to an otherwise good form; one such key made
    the whole form fail validation and spent the one repair on it. What a dropped key held is never read or sent; keys
    inside the fields are still validated as before (an unknown key in an offer or an item still fails)."""
    if not isinstance(form, dict):
        return form, []
    extra = sorted(k for k in form if k not in FORM_FIELDS)
    return {k: v for k, v in form.items() if k in FORM_FIELDS}, extra


def _take_form(use, rec):
    """The give_answer input of a tool_use, cleaned (clean_form); dropped keys are recorded, never their values."""
    form, extra = clean_form(use.get("input") or {})
    if extra:
        rec["events"].append("form_keys_dropped")
        rec.setdefault("dropped_keys", []).append(extra[:12])
    return form


def _form_error_text(form):
    """The repair text of a form that did not validate, naming the fields (the verifier's own text gives only the
    error's type): an extra key, a missing or wrong field."""
    try:
        V.AnswerForm.model_validate(form)
        return V.repair_message(V.Verdict(outcomes=[], form_error="?", repair=True))
    except Exception as e:  # noqa: BLE001 - a pydantic ValidationError
        errs = getattr(e, "errors", lambda: [])()[:4]
        bits = []
        for er in errs:
            loc = ".".join(str(x) for x in er.get("loc") or ()) or "the form"
            bits.append(f"'{loc[:60]}': {'not a field of give_answer' if er.get('type') == 'extra_forbidden' else er.get('msg', '')[:80]}")
        return ("The answer form did not validate (" + "; ".join(bits) + "). Send give_answer again with only its "
                "fields: understood, lead, points, items, chart, outside, ask_back, offers, setup, corrects_previous, "
                "hand_back.")


def form_sentences(form):
    """Sentences the model wrote in a form, counted as the verifier counts them (lead sentences + points), also for a
    form that did not validate."""
    if not isinstance(form, dict):
        return 0
    lead = form.get("lead") if isinstance(form.get("lead"), str) else ""
    pts = form.get("points") if isinstance(form.get("points"), list) else []
    return len(V._split(lead)) + len(pts)


def _ordered(uses, results):
    """Every tool_use gets exactly one tool_result, in the order of the calls."""
    by = {x["tool_use_id"]: x for x in results}
    return [by[u["id"]] for u in uses if u["id"] in by]


def _finish(rec, turn, vturn, verdicts, cm=None):
    """Which answer goes out, and its sentence counts."""
    cm = cm or V.FULL
    ledger = V.Ledger(turn.results)
    v1 = verdicts[0] if verdicts else None
    v2 = verdicts[1] if len(verdicts) > 1 else None
    sent_v, source, code = None, None, None
    if v1 is not None and not v1.repair:
        sent_v, source = v1, "model"
    elif v2 is not None and v2.lead_ok:
        sent_v, source = v2, "model_after_repair"
    elif v1 is not None and v1.lead_ok:
        sent_v, source = v1, "model"          # the repair (for the points) failed; the first lead stands
    if sent_v is None:
        base_v = v2 or v1
        code = FB.answer(ledger, base_v, vturn, mode=cm)
        source = "plain" if code["how"] == "plain" else "code"
    form = None
    if sent_v is not None:
        form = rec["forms"][verdicts.index(sent_v)]
    elif code is not None and code.get("how") != "plain" and base_v is not None and base_v in verdicts and \
            verdicts.index(base_v) < len(rec["forms"]):
        # mvp20 fix: the offers the model picked go out under a code lead too (their labels are code's)
        form = rec["forms"][verdicts.index(base_v)]
    out = A.build(ledger, verdict=sent_v, code=code, form=form, also=[v for v in verdicts if v is not None], mode=cm,
                  links=_links(turn), limits=list(getattr(turn, "limits", None) or []))
    rec["answer"] = out
    rec["lead_source"] = source
    rec["code_lead"] = code
    written = len(_sentences_of(v1)) if (v1 is not None and not v1.form_error) else \
        (form_sentences(rec["forms"][0]) if rec["forms"] else 0)
    first_kept = sum(1 for o in _sentences_of(v1) if o.kept)
    if source in ("model", "model_after_repair"):
        final = sum(1 for o in _sentences_of(sent_v) if o.kept)
    else:
        final = len(code["points"]) if code else 0
    rec["sentences"] = {"written": written, "kept_first_pass": first_kept, "kept_sent": min(final, written)}


def _links(turn):
    """item id -> its link, from the library the tools read (the cards' channel link; mvp25 toolgaps 7)."""
    lib = getattr(turn, "_lib", None)
    view = getattr(lib, "view", None)
    if view is None:
        return None
    return lambda iid: getattr(view.items.get(iid), "url", None)


def screen_after(rec, now_words=None):
    """The screen for their next message (SPEC 3.3, the part this slice needs): the last answer's scope line and plan
    (tool, args, the window and scope code resolved), written by code from the record; no model text."""
    plan = []
    for c in rec.get("calls") or []:
        env = c.get("result") or {}
        if env.get("is_error") or not env.get("rid"):
            continue
        meta = env.get("meta") or {}
        plan.append({"rid": env["rid"], "tool": c["name"], "args": c["args"],
                     "window_said": meta.get("window_said"), "filters_said": meta.get("filters_said")})
    out = {"last_answer": {"minutes_ago": 1, "plan": plan,
                           "scope_line": ((rec.get("answer") or {}).get("scope_line"))}}
    if now_words:
        out["now"] = now_words
    return out


def unlock_after(turn, rec):
    """mvp25 toolgaps 5: the topic to carry into the next message: the one this turn unlocked, when one of its results
    resolved a name to it (meta.resolved, or a find row's match); else None. Code's, never the model's: the next Turn
    takes it as `carried_unlock`, and it never goes on the screen the model reads."""
    if not turn.unlock:
        return None
    for c in rec.get("calls") or []:
        env = c.get("result") or {}
        if env.get("is_error"):
            continue
        if any(str(v).startswith("topic:") for v in ((env.get("meta") or {}).get("resolved") or {}).values()):
            return turn.unlock
        for row in (env.get("sheet") or {}).get("names") or []:
            if any(str((m or {}).get("ref", "")).startswith("topic:") for m in row.get("matches") or []):
                return turn.unlock
    return None


def last_window(turn, rec):
    """The window of the last answer's first counted result (for window.same_as "last" next time)."""
    for c in rec.get("calls") or []:
        rid = (c.get("result") or {}).get("rid")
        if rid and rid in turn.windows:
            return turn.windows[rid]
    return None


def strip_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()
