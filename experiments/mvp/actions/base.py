"""PROTOTYPE ONLY - what every action gets and gives back (DESIGN.md sections 6 and 11, slice 4).

An action is a plain function `run(ctx, params) -> Outcome` in its own module. `ctx` holds the answer it acts on (as
the executor kept it: rendered parts without chat footers, and each pick's checked title, link and details), the
person, the run, and what the actions before it did (calendar.add's file is attached to the email that follows). The
Outcome is one short line for the thread (and, for a calendar entry, its link as a part of its own), and a record for
the action log. Nothing in an Outcome is written by a model: titles and lines come from the checked answer.
"""
import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from .. import config


@dataclass
class Outcome:
    status: str                      # done | outbox (written, not sent) | waiting (needs an email) | skipped | failed
    line: str = ""                   # one short line for the thread
    link: Optional[dict] = None      # a link part placed right after the line (calendar.add)
    ref: Optional[str] = None        # an outbox file, a channel reference, to-do ids
    attach: list = field(default_factory=list)       # [(filename, path, maintype, subtype)] for an email after it
    email_links: list = field(default_factory=list)  # [(label, url)] for an email after it
    detail: Optional[dict] = None    # kept in the action log


@dataclass
class Ctx:
    bot: object
    person: dict
    answer: dict                     # {"kind": picks|note|todos, "goal", "parts", "picks": [...]} (store.answers)
    picks: list                      # the picks this action is about (main picks, or the one the person named)
    whole: bool = True               # True: the action is about the whole answer; False: only `picks`
    run_id: Optional[int] = None
    rule_id: Optional[int] = None
    kind: str = "ask"                # ask | more | manual | scheduled | act_on_last
    now: object = None
    tz: str = "America/New_York"
    request_text: str = ""
    slot_at: object = None           # a timed send: the moment it was due (an event at that time is today's)
    params_of: dict = field(default_factory=dict)   # action name -> its params (validated)
    done: list = field(default_factory=list)        # [(name, Outcome)] of the actions run before this one
    chat: object = None              # message.send: the Reply to send in the thread

    @property
    def handle(self):
        return self.person["handle"]

    @property
    def store(self):
        return self.bot.store


def outbox_dir(handle):
    """One folder per person under MVP_HOME/outbox, named by a hash so no number or address is in a path."""
    d = os.path.join(config.OUTBOX, hashlib.sha256(str(handle).encode()).hexdigest()[:12])
    os.makedirs(d, exist_ok=True)
    return d


def write_outbox(handle, stem, ext, data, now):
    """Writes one file to the person's outbox folder; returns its path."""
    stem = re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-")[:40] or "item"
    base = os.path.join(outbox_dir(handle), f"{now.strftime('%Y%m%d-%H%M%S')}-{stem}")
    path, n = f"{base}.{ext}", 1
    while os.path.exists(path):
        n += 1
        path = f"{base}-{n}.{ext}"
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def where_outbox(bot):
    """Where an unsent email is, in the reply: the test page has an Outbox panel."""
    return getattr(bot.channel, "outbox_place", None) or "in the bot's outbox folder"
