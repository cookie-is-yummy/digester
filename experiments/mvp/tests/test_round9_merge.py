"""Checks on the merged round 9 tree (DESIGN.md section 16, "hook order"): the hooks run in the order the verdict's
map gives, and no round 9 read takes a message that went another way before, end to end through the bot.

Each round 9 hook on the bot is wrapped to record when it answers a message (returns something other than None). The
159 rule-eval texts and every rule-changing phrasing in the earlier test files are then sent as a tester and as the
operator (with a mailbox and a Mac set up), with no answer kept and after an answer. Only the rule eval's t-dev-040
("buy the ingredients for the first one", slice C) may be answered by a round 9 read. Synthetic data only; the fake
interpreter answers "chat" so nothing else runs."""
import ast
import glob
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

MVP = os.path.dirname(HERE)
BOT_HOOKS = ("draft_reads", "offer_reads", "_cancel_answer", "email_reads", "cancel_reads", "postact_reads",
             "cancel_stop_guard", "receipts_reads", "do_it", "_doit_answer", "secret_reads")
PLACE_HOOKS = ("place_reads", "asked_reads")
# round 10, slice W: hook 5a (refresh.export_reads) and the bot's new reads
W_MODULE_HOOKS = ("export_reads",)
W_BOT_HOOKS = ("split_reads", "self_email_reads")
# ---------- round 10, slice S: its two reads are checked the same way (hook 0 and hook 4b) ----------
BOT_HOOKS += ("fit_reads", "_mismatch_answer")
BOT_HOOKS += ("browser_reads",)   # second merge of round 10: slice V's read (only while a run is open)
# ---------- end round 10, slice S ----------
ALLOWED = {"buy the ingredients for the first one"}   # the rule eval's t-dev-040: slice C puts them on the list
CHAT = {"intent": "chat", "reply": "OK."}


def eval_texts():
    out = []
    for path in sorted(glob.glob(os.path.join(MVP, "evalset", "rules_dev_*.jsonl"))):
        out += [json.loads(line)["text"] for line in open(path, encoding="utf-8") if line.strip()]
    return out


RULE_WORDS = re.compile(r"\b(?:stop|stopped|pause|paused|resume|restart|unpause|cancel|end|quit|turn off|change|"
                        r"move|edit|switch|instead|make it|delete rule|remove rule|unsubscribe)\b", re.I)


def rule_phrasings():
    """Every short string in the test files from before round 9 that stops, pauses or changes something."""
    out = set()
    for path in glob.glob(os.path.join(HERE, "test_*.py")):
        if os.path.basename(path).startswith(("test_round9_", "test_round10_",
                                              "test_round11_", "test_round12_", "test_brain_")):   # round 10, slice K:
            # the set stays the round 9 one (round 12: its test files are left out as round 10's and 11's are; the
            # brain's step-1 test files too: their rule-like strings are tool arguments and eval lines, not phrasings
            # today's reads must leave alone)
            continue
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and 2 <= len(node.value) <= 120 \
                    and "\n" not in node.value and RULE_WORDS.search(node.value) and not node.value.startswith("mvp"):
                out.add(node.value)
    return sorted(out)


@pytest.fixture()
def rec(env, monkeypatch):
    """The env bot with every round 9 hook wrapped: env["claimed"] lists (hook, text) for each one that answered."""
    from mvp import places
    from mvp.core import Bot
    claimed = []
    env["claimed"] = claimed
    env["bot"].max_per_minute = None

    def wrap(name, f, text_at):
        def w(*a, **kw):
            out = f(*a, **kw)
            if out is not None and out is not False and out != (False, None):
                claimed.append((name, a[text_at]))
            return out
        return w
    for name in BOT_HOOKS:
        monkeypatch.setattr(Bot, name, wrap(name, getattr(Bot, name), 2))
    for name in PLACE_HOOKS:
        monkeypatch.setattr(places, name, wrap(name, getattr(places, name), 2))
    # ---------- round 10, slice W: the new reads are checked the same way ----------
    from mvp import refresh
    for name in W_MODULE_HOOKS:
        monkeypatch.setattr(refresh, name, wrap(name, getattr(refresh, name), 2))
    for name in W_BOT_HOOKS:
        if hasattr(Bot, name):
            monkeypatch.setattr(Bot, name, wrap(name, getattr(Bot, name), 2))
    # ---------- end round 10, slice W ----------
    # ---------- round 10, slice G: hook 8a ("stop adding to X", "use X for rule N", "undo rule N") ----------
    from mvp import grants
    monkeypatch.setattr(grants, "grant_reads", wrap("grant_reads", grants.grant_reads, 2))
    # ---------- end round 10, slice G ----------
    # ---------- round 10, slice Y: hook 5b (youtube_reads) and 4a (youtube_answer) ----------
    from mvp import ytreads
    for name in ("youtube_reads", "youtube_answer"):
        monkeypatch.setattr(ytreads, name, wrap(name, getattr(ytreads, name), 2))
    # ---------- end round 10, slice Y ----------
    return env


def operator(env, monkeypatch):
    from mvp import config
    from mvp.actions import mac
    from mvp.tests.test_round9_mac import FakeRunner
    r = FakeRunner()
    r.mac = mac
    monkeypatch.setattr(mac, "RUNNER", r)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "me@example.com")
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", "fake-app-pass-1234")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("MVP_MAILBOX_IMAP_HOST", "imap.example.invalid")
    # round 9, E: TickTick, Todoist and a webhook set up too (a fake opener: no network)
    from mvp.actions import web
    from mvp.tests.test_round9_tokens import FakeOpener
    monkeypatch.setattr(web, "OPENER", FakeOpener())
    monkeypatch.setenv("MVP_TICKTICK_TOKEN", "tt-fake-merge-0000000000000000")
    monkeypatch.setenv("MVP_TODOIST_TOKEN", "td-fake-merge-0000000000000000")
    monkeypatch.setenv("MVP_WEBHOOK_URL", "https://hooks.example.com/catch/fake")
    say(env, "check my mac", CHAT)


def send_all(env, texts, after_answer):
    bot = env["bot"]
    for t in texts:
        if after_answer:
            env["state"]["answers"]["mvp_compose"] = lemon_pick()
            say(env, "pasta, no cream", ask_pasta())
        bot.store.clear_pending(H)
        say(env, t, CHAT)
        bot.store.clear_pending(H)


@pytest.mark.parametrize("who", ["tester", "operator"])
@pytest.mark.parametrize("after_answer", [False, True])
def test_no_rule_eval_text_is_taken_by_a_round9_hook_but_t_dev_040(rec, monkeypatch, who, after_answer):
    texts = eval_texts()
    assert len(texts) == 159
    if who == "operator":
        operator(rec, monkeypatch)
    rec["claimed"].clear()
    send_all(rec, texts, after_answer)
    taken = sorted({t for _, t in rec["claimed"] if t in texts})
    assert set(taken) <= ALLOWED, taken
    if after_answer:   # the wrappers see what they should: slice C takes t-dev-040 after an answer
        assert ("postact_reads", "buy the ingredients for the first one") in rec["claimed"]


@pytest.mark.parametrize("who", ["tester", "operator"])
def test_every_rule_phrasing_from_before_round_9_still_goes_the_old_way(rec, monkeypatch, who):
    """Each stop, pause, resume or change phrasing the earlier tests use (with rules in place) is answered by no
    round 9 hook, so it still stops, pauses or changes a rule exactly as those tests check."""
    texts = rule_phrasings()
    assert len(texts) > 100
    if who == "operator":
        operator(rec, monkeypatch)
    for words, days in (("stretch", ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]), ("water the plants", ["MON"])):
        say(rec, f"remind me to {words}", {"intent": "new_rule", "spec": {
            "when": {"type": "schedule", "days": days, "time": "07:00"}, "content": {"source": "note", "text": words}}})
        rec["bot"].store.clear_pending(H)
    assert len(rec["bot"].store.rules(H)) == 2
    rec["claimed"].clear()
    for t in texts:
        rec["bot"].store.clear_pending(H)
        say(rec, t, CHAT)
    taken = sorted({t for _, t in rec["claimed"] if t in texts})
    assert taken == [], taken
    # the wrappers see what they should: each round 9 request read answers its own phrasing
    for text, hook in (("cancel my netflix", "cancel_reads"), ("what are you connected to", "place_reads"),
                       ("email sam@example.com that the sink is broken", "email_reads"),
                       ("what did you do for me", "receipts_reads"), ("do it for me", "do_it"),
                       ("connect my ticktick", "place_reads"), ("MVP_TODOIST_TOKEN=x", "secret_reads")):
        rec["claimed"].clear()
        say(rec, text, CHAT)
        assert [h for h, _ in rec["claimed"]][-1:] == [hook], (text, rec["claimed"])


def test_the_hooks_run_in_the_order_of_the_map():
    """handler.py: the card reads (draft, then offer) right after confirm_delete; the next-message reads (cancel,
    then the Mac's yes/no and REMOVE/KEEP) after _overdue_reply; the request reads (email, cancel, postact, place)
    after _rule_reads and before integration_reads; the stop guard before the pending row is cleared."""
    src = open(os.path.join(MVP, "handler.py"), encoding="utf-8").read()

    def order(*needles):
        at = [src.index(n) for n in needles]
        assert at == sorted(at), needles
    order('pending["kind"] == "confirm_delete"', "self.draft_reads(", "self.offer_reads(",
          'pending["kind"] == "confirm_rule" and YES.match(text)', "self._email_text(")
    order("self._overdue_reply(person, text, now)", "self._cancel_answer(", "place_answer(self, person, text, now)")
    order("ref = self._rule_reads(person, text, now)", "self.email_reads(", "self.cancel_reads(",
          "self.postact_reads(", "ref = place_reads(self, person, text, now)", "self.receipts_reads(", "self.do_it(",
          "self.integration_reads(")
    order("place_answer(self, person, text, now)", "self._doit_answer(")
    order("self.secret_reads(person, text, now)", "self._asked_reads(person, text, now)", "self.onboard_step(")
    order("self.cancel_stop_guard(", "self._manage(")
    # ---------- round 10, slice S ----------
    order('pending["kind"] == "confirm_delete"', "ref = self.fit_reads(person, text, now)", "self.draft_reads(")
    order("place_answer(self, person, text, now)", "self._mismatch_answer(person, text, now, ask)", "self._doit_answer(")
    # ---------- end round 10, slice S ----------
    # round 10, slice G: hook 8a right after place_reads (8), before receipts_reads
    order("ref = place_reads(self, person, text, now)", "ref = grant_reads(self, person, text, now)",
          "self.receipts_reads(")
    # round 10, slice Y: 5b after email_reads and before cancel_reads; 4a after the places' yes/no answer
    order("self.email_reads(", "ref = ytreads.youtube_reads(self, person, text, now)", "self.cancel_reads(")
    order("place_answer(self, person, text, now)", "ref = ytreads.youtube_answer(self, person, text, now)",
          "self._mismatch_answer(person, text, now, ask)")
