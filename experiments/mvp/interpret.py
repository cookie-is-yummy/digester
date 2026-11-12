"""PROTOTYPE ONLY - one message in, one validated Interpretation out. The model fills the form; this code validates it,
retries once on an invalid form, and works out dates (saved_after from since_days). The person's message is passed as
their request; nothing it says can call an action directly (AGENTS.md rule 6)."""
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from . import config, llm
from .schema import Interpretation, RuleSpec
from .schedule import describe, resolve_relative

PROMPT = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_INTERPRET}.md"), encoding="utf-8").read()


def _context(person, rules, pending, last, now):
    tz = ZoneInfo(person["timezone"])
    local = now.astimezone(tz)
    lines = [f"Today is {local.strftime('%A %Y-%m-%d')}, local time {local.strftime('%H:%M')} ({person['timezone']})."]
    if rules:
        lines.append("Their rules, as numbered to them:")
        for i, r in enumerate(rules, 1):
            spec = RuleSpec.model_validate(r["spec"])
            lines.append(f"  {i}. {spec.content.goal} - {describe(spec.when)} ({r['status']}) spec={json.dumps(r['spec'])}")
    else:
        lines.append("They have no rules yet.")
    if pending and pending["kind"] == "confirm_rule":
        lines.append("The bot just showed a preview of a NEW rule and asked them to reply YES to start it. If their message "
                     "changes that rule (with or without a yes), return intent new_rule with the whole changed spec and "
                     "edits_pending true. A different, unrelated request is a new_rule with edits_pending false. "
                     f"Pending spec={json.dumps(pending['payload']['spec'])}")
    elif pending and pending["kind"] == "confirm_delete":
        lines.append("The bot just asked them to confirm deleting all their data.")
    if last:
        lines.append(f"The bot's last answer was about: {last['goal']} ({len(last['items'])} picks, numbered 1 to "
                     f"{len(last['items'])}).")
    return "\n".join(lines)


def finish(spec: RuleSpec, now, tzname):
    """Code-side completion of a spec. A period ('recently', since_days) stays relative: retrieve turns it into a date
    at each run, so a recurring rule's window moves with time. A relative time ('in two hours') becomes a date and a
    time here, from the moment the message arrived."""
    resolve_relative(spec.when, now, tzname)
    return spec


def interpret(text, person, rules, pending, last, now):
    """Returns (Interpretation, cost_usd)."""
    user = _context(person, rules, pending, last, now) + "\n\nTheir message:\n" + text.strip()[:1000]
    cost = 0.0
    err = None
    for attempt in range(2):
        prompt = user if err is None else user + f"\n\nYour last form was invalid ({err}). Return a valid form."
        raw, c = llm.chat_json(PROMPT, prompt, purpose="mvp_interpret", prompt_version=config.PROMPT_INTERPRET,
                               person=person["handle"], max_tokens=900)
        cost += c
        try:
            it = Interpretation.model_validate(raw)
            if it.spec is not None:
                finish(it.spec, now, person["timezone"])
            return it, cost
        except ValidationError as e:
            err = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:4])
    return Interpretation(intent="unsupported", reply="Sorry, I didn't catch that. Could you say it another way?"), cost


def now_local(now, tzname):
    return now.astimezone(ZoneInfo(tzname))


def parse_iso(s):
    return datetime.fromisoformat(s) if s else None
