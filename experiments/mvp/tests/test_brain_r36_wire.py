"""mvp36 (DESIGN 35): the chat core behind a switch in the bot, first slice (brainwire.py, the hooks H1 and H2 in
handler.py and history.history_reads). Made-up library (tests/brain_library.py), made-up messages written for these
tests, the fake provider and the fake interpreter only: no model call, no network, no money.

Every rule of the slice's brief has a test here: the switch off is today's bot (replies, store and state compared row
by row); where the chat core is tried and who owns a follow-up; eligibility; the send decision, each way it declines
leaving today's reply and store as with the switch off; the early stop at a search; claimed actions; what a sent
answer writes; the rendering; the threading of two and three turns against the eval's; privacy; money; the consent.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (fixtures)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys  # noqa: E402,F401
from mvp.tests.test_slice2 import H  # noqa: E402

V1 = "mvp-consent-v1+anthropic"
NO_MODEL = {"intent": "chat", "reply": "MODEL WAS CALLED"}
# made-up messages (the made-up library: channels Clip Factory, Pan Theory; the private topic's word "dating")
OCT_Q = "top channels i watched during october?"                     # today's parse takes it (H1)
RECALL_Q = "what was that video i watched about sourdough"           # today's recall read takes it (H1)
OPEN_Q = "anything stand out about october for me?"                  # no parse: the interpreter (H2)
NAMED = "how many dating videos did i open in 2024"                  # names the private topic; no parse (H2)
FOLLOW = "and which month had the most"
FOLLOW2 = "and the newest few"
OCT = {"by": "channel", "window": {"words": "in October", "preset": None, "same_as": None}}
TRUE_LEAD = "In October 2026, Clip Factory[r1.channels[0]] led with 61[r1.channels[0].items] videos."
TRUE_POINT = "Pan Theory[r1.channels[1]] came next with 32[r1.channels[1].items] videos."
PLAIN_LEAD = "Here is what that shows."
SC = {"exclude": [], "how": "opened", "length": "any", "only": [], "platforms": [], "weekday": None}
Y24 = {"words": "in 2024", "preset": None, "same_as": None}
BREAK_TOPIC = {"by": "none", "compare": "none", "order": "most", "top": 5, "window": Y24,
               "scope": dict(SC, only=["dating"])}
MONTHS_TOPIC = {"unit": "month", "window": Y24, "scope": dict(SC, only=["dating"])}
NEWEST_TOPIC = {"limit": 3, "order": "newest", "window": Y24, "scope": dict(SC, only=["dating"])}
ASK = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a look at october",
                                                                       "searches": ["october"], "count": 1}}}


# ---------------------------------------------------------------- helpers
def P():
    from mvp.brain import provider as P_
    return P_


def tu(name, args):
    return P().tool_use(name, args)


def ga(lead, points=(), **kw):
    return P().tool_use("give_answer", dict({"lead": lead, "points": list(points)}, **kw))


def good():
    """One read and an answer that passes the values check."""
    return [[tu("breakdown", OCT)], [ga(TRUE_LEAD, [TRUE_POINT])]]


@pytest.fixture()
def wired(brain, monkeypatch):
    """The switch on for the test person, whose stored consent named Anthropic."""
    monkeypatch.setenv("MVP_BRAIN", "1")
    monkeypatch.setenv("MVP_BRAIN_PEOPLE", H)
    brain["bot"].store.set_consent(H, V1)
    brain["bot"].brain_provider = None
    return brain


def send(e, text, script=None, form=NO_MODEL, bot=None, ch=None):
    """The person sends `text`; the fake provider plays `script` (None: a provider that fails the test when asked).
    -> (what the bot sent, joined; the model purposes called; the wiring's last decision)."""
    bot = bot or e["bot"]
    ch = ch or e["ch"]
    bot.brain_provider = P().FakeProvider([list(s) if isinstance(s, list) else s for s in (script or [])])
    e["state"]["answers"]["mvp_interpret"] = form if callable(form) else (lambda u: form)
    n0, c0 = len(ch.outbox), len(e["calls"])
    bot.on_message(H, text)
    out = "\n".join(str(t) for _, _, t in ch.outbox[n0:])
    return out, e["calls"][c0:], getattr(bot._tl, "brain_last", None)


def requests_sent(bot):
    return len(bot.brain_provider.sent)


ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:\+00:00|Z)?")


def dump(store):
    """Every table's rows, wall-clock values masked (some rows take the real time, not the bot's clock)."""
    db = store.db if hasattr(store, "db") else store
    out = {}
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for t in tables:
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({t})")]
        rows = []
        for r in db.execute(f"SELECT * FROM {t} ORDER BY rowid"):
            d = {}
            for c, v in zip(cols, r):
                if c in ("seconds",):
                    v = "<s>"
                elif isinstance(v, str):
                    v = re.sub(r'"seconds": [0-9.]+', '"seconds": 0', ISO.sub("<t>", v))
                    v = re.sub(r"console-[0-9a-f]+-", "console-<c>-", v)   # each console channel's own prefix
                d[c] = v
            rows.append(d)
        out[t] = rows
    return out


def twin(e, tmp_path, name):
    """A second bot on its own store, the same library, clock, fakes and person (today's bot to compare with)."""
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    from mvp.tests.test_slice6 import AllPool
    ch = ConsoleChannel(printer=None)
    bot = Bot(ch, store=Store(str(tmp_path / f"{name}.sqlite")), pool=AllPool(str(e["lib"])),
              clock=lambda: e["clock"][0])
    bot.load_people(str(tmp_path / "people.json"))
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(e["lib"]), H))
    bot.store.set_consent(H, V1)
    bot.max_per_minute = None
    return bot, ch


def converse(e, bot, ch, steps, monkeypatch, brain_env):
    """`steps`: (text, interpreter form, fake script). The clock moves a minute between messages."""
    for k, v in brain_env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    e["clock"][0] = NOW
    outs = []
    for text, form, script in steps:
        out, _calls, _d = send(e, text, script, form, bot=bot, ch=ch)
        outs.append(out)
        e["clock"][0] = e["clock"][0] + timedelta(minutes=1)
    return outs


W_ASK = ("ask", "chat", "library_stats", "clarify", "unsupported", "confirm")
OFF = {"MVP_BRAIN": None, "MVP_BRAIN_PEOPLE": None}
ON = {"MVP_BRAIN": "1", "MVP_BRAIN_PEOPLE": H}


# ================================================================ rule 1: switch off is today's bot
CONV = [(OCT_Q, NO_MODEL, None), (RECALL_Q, NO_MODEL, None), (OPEN_Q, {"intent": "chat", "reply": "Happy to help."},
                                                              None),
        ("my rules", NO_MODEL, None), ("what leaves this computer", NO_MODEL, None),
        ("thanks!", {"intent": "chat", "reply": "Any time."}, None)]


@pytest.mark.parametrize("mode", ["unset", "zero", "not_named"])
def test_with_the_switch_off_or_the_person_not_named_the_same_messages_give_the_same_replies_and_store(
        brain, tmp_path, monkeypatch, mode):
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "other")
    today = converse(brain, a, cha, CONV, monkeypatch, OFF)
    env_b = {"unset": OFF, "zero": {"MVP_BRAIN": "0", "MVP_BRAIN_PEOPLE": H},
             "not_named": {"MVP_BRAIN": "1", "MVP_BRAIN_PEOPLE": "+15559990000"}}[mode]
    other = converse(brain, b, chb, CONV, monkeypatch, env_b)
    assert today == other and all(today)
    assert dump(a.store) == dump(b.store)
    assert not [k for (k,) in b.store.db.execute("SELECT key FROM state") if k.startswith("brain:")]


def test_with_the_switch_off_no_module_of_the_chat_core_is_imported(tmp_path):
    """A fresh process (pytest's own modules are shared by every test): a history question, a question through the
    interpreter and the consent text, with the switch off; then the same with the switch on for another person."""
    code = r'''
import os, sys, json
sys.path.insert(0, os.environ["EXP"])
from mvp.tests import brain_library as B
from pathlib import Path
from datetime import datetime, timezone
lib = B.write(Path(os.environ["BASE"]) / "lib")
from mvp import config, llm, interpret
from mvp.channels.console import ConsoleChannel
from mvp.core import Bot
from mvp.store import Store
from mvp.tests.test_slice6 import AllPool
llm.chat_json = interpret.llm.chat_json = lambda *a, **k: ({"intent": "chat", "reply": "ok"}, 0.0)
llm.spent_today = lambda h, l: 0.0
llm.spent_total = lambda libs: 0.0
ch = ConsoleChannel(printer=None)
bot = Bot(ch, store=Store(config.DB), pool=AllPool(str(lib)), clock=lambda: datetime(2026, 11, 22, 17, tzinfo=timezone.utc))
bot.max_per_minute = None
bot.store.upsert_person("+15550001", "T", str(lib), "America/New_York")
bot.store.upsert_person("+15550002", "U", str(lib), "America/New_York")
bot.store.set_consent("+15550001", "mvp-consent-v1+anthropic")
bot.on_message("+15550001", "top channels i watched during october?")
bot.on_message("+15550001", "anything stand out about october for me?")
bot.on_message("+15550002", "hi")
print(json.dumps(sorted(m for m in sys.modules if m.startswith("mvp.brain"))))
'''
    for env_ in ({}, {"MVP_BRAIN": "1", "MVP_BRAIN_PEOPLE": "+15559990000"}):
        base = tmp_path / ("b" + str(len(env_)))
        base.mkdir()
        e = dict(os.environ, EXP=EXP, BASE=str(base), MVP_HOME=str(base / "home"), MVP_LEDGER_HOME=str(base / "l"),
                 MVP_DERIVED_HOME=str(base / "d"), MVP_INBOX=str(base / "i"), MVP_INSIGHT="0",
                 PYTHONDONTWRITEBYTECODE="1", **env_)
        for k in ("MVP_BRAIN", "MVP_BRAIN_PEOPLE"):
            if k not in env_:
                e.pop(k, None)
        e.pop("YOUTUBE_API_KEY", None)
        r = subprocess.run([sys.executable, "-B", "-c", code], env=e, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        assert json.loads(r.stdout.strip().splitlines()[-1]) == [], env_


# ================================================================ rule 6: a declined turn is today's, byte for byte
def _search():
    return [[tu("search", {"query": "october"})], [ga(PLAIN_LEAD)]]


def _learned():
    return [[tu("learned", {"topic": "october"})], [ga(PLAIN_LEAD)]]


def _hand_back(words=OCT_Q):
    return [[tu("breakdown", OCT)], [ga(TRUE_LEAD, hand_back={"kind": "reminder", "words": words})]]


DECLINES = {
    "search_or_learned": _search,
    "learned": _learned,
    "provider": lambda: [P().ProviderError("http 529 overloaded_error")],
    "refusal": lambda: [{"blocks": [{"type": "text", "text": "no"}], "stop_reason": "refusal"}],
    "hand_back": _hand_back,
    "plain": lambda: [[{"type": "text", "text": "hm"}], [{"type": "text", "text": "hm"}]],
    "no_result": lambda: [[tu("nothing_here", {})], [ga(PLAIN_LEAD)]],
    "claimed_action": lambda: [[tu("breakdown", OCT)], [ga("I'll send you this list every Sunday.")]],
}


@pytest.mark.parametrize("why", sorted(DECLINES))
@pytest.mark.parametrize("site", ["H1", "H2"])
def test_a_declined_turn_leaves_the_reply_and_the_store_as_with_the_switch_off(brain, tmp_path, monkeypatch, why,
                                                                                site):
    text, form = (OCT_Q, NO_MODEL) if site == "H1" else (OPEN_Q, {"intent": "chat", "reply": "Happy to help."})
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "wired")
    today = converse(brain, a, cha, [(text, form, None)], monkeypatch, OFF)
    script = _hand_back(text) if why == "hand_back" else DECLINES[why]()   # the doing words are the message's own
    wired_ = converse(brain, b, chb, [(text, form, script)], monkeypatch, ON)
    d = b._tl.brain_last
    assert d["decision"] == "declined" and d["site"] == site, d
    assert d["reason"] == {"learned": "search_or_learned", "refusal": "provider"}.get(why, why), d
    assert today == wired_ and today[0] and "Ask me again" not in wired_[0]
    assert dump(a.store) == dump(b.store)


def test_a_turn_that_raises_is_declined_to_todays_bot(brain, tmp_path, monkeypatch):
    from mvp import brainwire as W
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "wired")
    today = converse(brain, a, cha, [(OCT_Q, NO_MODEL, None)], monkeypatch, OFF)

    def boom(*a_, **k):
        raise OSError("the library does not open")
    monkeypatch.setattr(W.BL, "run_turn", boom)
    wired_ = converse(brain, b, chb, [(OCT_Q, NO_MODEL, good())], monkeypatch, ON)
    assert b._tl.brain_last["reason"] == "raised:OSError"
    assert today == wired_ and dump(a.store) == dump(b.store)


def test_a_search_call_ends_the_turn_at_the_next_request(wired):
    out, _c, d = send(wired, OCT_Q, [[tu("search", {"query": "october"})], [ga(PLAIN_LEAD)], [ga(PLAIN_LEAD)]])
    bot = wired["bot"]
    assert requests_sent(bot) == 1 and d["reason"] == "search_or_learned" and d["stopped_at"] is not None
    assert "provider_error" in d["rec"]["events"] and d["rec"]["error"] == "stopped_at_search"
    assert "Clip Factory" in out    # today's history answer


def test_a_search_asked_in_the_repair_request_is_seen_in_the_blocks_and_declines(wired):
    """A read beside give_answer in the one repair request is never run (no call in the record); the request's own
    blocks still show it."""
    bad = "In October 2026, Clip Factory[r1.channels[0]] led with 60[r1.channels[0].items] videos."
    script = [[tu("breakdown", OCT)], [ga(bad)], [tu("search", {"query": "x"}), ga(TRUE_LEAD)]]
    _out, _c, d = send(wired, OCT_Q, script)
    assert "search" not in [c["name"] for c in d["rec"]["calls"]]
    assert d["reason"] == "search_or_learned"


def test_a_no_match_declines_an_ask_at_h2_only(wired):
    from mvp.brain import loop as BL  # noqa: F401  (the switched branch imports it)
    nm = [[tu("find", {"names": ["zqxv"]})], [ga("Nothing in your history goes by that name.")]]
    _o, _c, d = send(wired, OPEN_Q, nm, ASK)
    assert d["site"] == "H2" and d["intent"] == "ask" and d["reason"] == "no_match"
    _o, _c, d = send(wired, OPEN_Q, nm, {"intent": "chat", "reply": "ok"})
    assert d["site"] == "H2" and d["intent"] == "chat" and d["decision"] == "sent", d
    _o, _c, d = send(wired, "what did i watch on 5 october", nm)
    assert d["site"] == "H1" and d["decision"] == "sent", d


# ================================================================ claimed actions
CLAIMED = [
    "I've set up a weekly email of these.", "I sent it to you.", "I'll send you this every Sunday.",
    "I will email you that list tomorrow.", "I'm going to remind you on Friday.", "I'll schedule it for 9am.",
    "I'll set up a rule for that.", "I'll save these for you.", "I will add them to your list.",
    "I'll turn on the weekly digest.", "I'm going to start sending these.", "I'll keep an eye on it for you.",
    "From now on you get these on Mondays.", "It will be sent every week.", "That list will be emailed tonight.",
    "Your summary will be scheduled.", "You'll get one every week.", "You will receive it on Sunday.",
    "I've noted that you like these.", "I have remembered your choice.", "I’ll send it on Monday.", "All set.",
]
TRUE_SENTENCES = [
    "You saved 12 videos in October.", "Most came from Gaming Daily.", "Every week in 2024 you opened a few videos.",
    "Got it, here is October instead.", "I can't see after 30 October.", "You opened Pan Theory 32 times.",
    "That is all your history shows.", "Done Right Cooking led with 5 videos.",
]


@pytest.mark.parametrize("s", CLAIMED)
def test_each_claim_form_is_caught(wired, s):
    from mvp import brainwire as W
    assert W.claims({"lead": s, "points": []}, names=[]) == [s]
    assert W.claims({"lead": "You opened 3 videos.", "points": [s]}, names=[]) == [s]


@pytest.mark.parametrize("s", TRUE_SENTENCES)
def test_true_sentences_are_not_claims(wired, s):
    from mvp import brainwire as W
    names = ["done right cooking"]
    assert W.claims({"lead": s, "points": []}, names=names) == []


def test_a_title_quoted_as_data_is_not_a_claim(wired):
    from mvp import brainwire as W
    title = "from now on i'll send you my best recipes"
    s = "The last one you opened was " + title.capitalize() + ", on 20 October 2026."
    assert W.claims({"lead": s, "points": []}, names=[title]) == []
    assert W.claims({"lead": f"You opened \"I'll send you a surprise\" twice.", "points": []}, names=[]) == []


def test_a_claim_in_a_lead_of_two_sentences_is_read_sentence_by_sentence(wired):
    from mvp import brainwire as W
    assert W.claims({"lead": "You opened 4 videos. All set.", "points": []}, names=[]) == ["All set."]


# ================================================================ where the chat core is tried: H1
def test_h1_a_question_todays_parse_takes_gets_the_chat_cores_answer_with_no_interpreter_call(wired):
    out, calls, d = send(wired, OCT_Q, good())
    assert d["site"] == "H1" and d["decision"] == "sent", d
    assert calls == [] and out.startswith("In October 2026, Clip Factory led with 61 videos.")
    assert "- Pan Theory came next with 32 videos." in out and "[r1" not in out


def test_h1_a_recall_todays_recall_read_takes_goes_to_the_chat_core(wired):
    _o, calls, d = send(wired, RECALL_Q, good())
    assert d["site"] == "H1" and calls == []


def test_h1_todays_own_follow_up_of_its_own_answer_stays_todays(wired):
    """Today's history answer owns the screen (the chat core declined): its follow-up read takes "and in
    September?" as today, and the chat core is not asked."""
    bot = wired["bot"]
    out, _c, d = send(wired, OCT_Q, [P().ProviderError("http 529 overloaded_error")])
    assert d["decision"] == "declined" and "Clip Factory" in out
    from mvp import history as Hm
    assert Hm._fresh_state(bot, H, wired["clock"][0]) is not None
    wired["clock"][0] += timedelta(minutes=1)
    out, calls, d = send(wired, "and in september?", None)
    assert requests_sent(bot) == 0 and calls == [] and out
    assert d is None or d.get("site") != "H1" or d["decision"] == "not_eligible"


def test_a_message_today_reads_before_the_hooks_never_reaches_the_chat_core(wired):
    out, _c, d = send(wired, "what leaves this computer", None)
    assert d is None and "What leaves this computer" in out
    out, _c, d = send(wired, "my rules", None)
    assert d is None


# ================================================================ H2: the intents
@pytest.mark.parametrize("intent", ["ask", "chat", "library_stats", "clarify", "unsupported", "confirm"])
def test_h2_a_talking_intent_is_tried(wired, intent):
    """Through the handler (its guards may read a form again: a clarify with nothing to clarify is unsupported)."""
    form = dict(ASK) if intent == "ask" else {"intent": intent, "reply": "ok", "question": "which one?"}
    _o, calls, d = send(wired, OPEN_Q, good(), form)
    assert d and d["site"] == "H2" and d["intent"] in W_ASK and d["decision"] == "sent", d
    assert set(calls) == {"mvp_interpret"}


@pytest.mark.parametrize("form", [
    {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["SUN"], "time": "09:00"},
                                     "content": {"goal": "a recap", "searches": ["recap"], "count": 1}}},
    {"intent": "set_timezone", "timezone": "America/Chicago"},
    {"intent": "todo_add", "todo_text": "call the framer"},
    {"intent": "more"}, {"intent": "profile_show"}, {"intent": "library_status"}, {"intent": "skip", "rule_number": 1},
    {"intent": "follow_up", "question": "and the second?"}, {"intent": "feedback", "feedback": "up"},
])
def test_h2_a_doing_intent_or_one_not_allowed_is_never_tried(wired, form):
    bot = wired["bot"]
    _o, calls, d = send(wired, OPEN_Q, None, form)
    assert requests_sent(bot) == 0 and calls[:1] == ["mvp_interpret"]
    assert d is None or d["site"] != "H2" or d["decision"] == "not_eligible", d


def test_h2_an_interpretation_with_a_second_intent_is_never_tried(wired):
    """(Read at the site itself: the guards ahead of it may drop a second intent the message does not support.)"""
    from mvp import brainwire as W
    from mvp.schema import Interpretation
    bot = wired["bot"]
    bot.brain_provider = P().FakeProvider([])
    bot._tl.brain_tried = False
    it = Interpretation.model_validate(dict(ASK, also={"intent": "set_timezone", "timezone": "America/Chicago"}))
    assert it.also is not None
    assert W.at_h2(bot, bot.store.person(H), it, OPEN_Q, NOW) is None
    assert requests_sent(bot) == 0 and not getattr(bot._tl, "brain_tried", False)


@pytest.mark.parametrize("intent", ["ask", "chat", "library_stats", "clarify", "unsupported", "confirm"])
def test_h2_at_the_site_every_talking_intent_is_tried(wired, intent):
    from mvp import brainwire as W
    from mvp.schema import Interpretation
    bot = wired["bot"]
    bot.brain_provider = P().FakeProvider(good())
    bot._tl.brain_tried = False
    it = Interpretation.model_validate(dict(ASK) if intent == "ask" else {"intent": intent, "reply": "ok",
                                                                         "question": "which one?",
                                                                         "draft": ASK["spec"]})
    if intent == "clarify":
        # (repair F06) a clarify carries a draft (the schema requires one): it is today's pending question, not tried
        assert W.at_h2(bot, bot.store.person(H), it, OPEN_Q, NOW) is None
        assert bot._tl.brain_last["reason"] == "clarify_draft" and not bot.brain_provider.sent
        return
    assert W.at_h2(bot, bot.store.person(H), it, OPEN_Q, NOW) is not None
    assert bot._tl.brain_last["intent"] == intent and bot._tl.brain_last["decision"] == "sent"


def test_h2_a_follow_up_goes_to_the_chat_core_while_its_answer_owns_the_screen_and_feedback_never_does(wired):
    send(wired, OCT_Q, good())
    wired["clock"][0] += timedelta(minutes=1)
    _o, calls, d = send(wired, "and what about the others", good(),
                        {"intent": "follow_up", "question": "and pan theory?"})
    assert d["site"] == "H2" and d["intent"] == "follow_up" and d["decision"] == "sent", d
    assert calls == ["mvp_interpret"]
    wired["clock"][0] += timedelta(minutes=1)
    _o, calls, d = send(wired, "more of that kind please", good(), {"intent": "feedback", "feedback": "more"})
    assert d is None and requests_sent(wired["bot"]) == 0 and calls[:1] == ["mvp_interpret"]   # (A2-02) today's


def test_on_a_decline_at_h2_the_same_interpretation_goes_on_with_no_second_interpreter_call(wired):
    out, calls, d = send(wired, OPEN_Q, [P().ProviderError("x")], {"intent": "chat", "reply": "Happy to help."})
    assert d["decision"] == "declined" and calls == ["mvp_interpret"] and "Happy to help." in out


def test_the_chat_core_runs_at_most_once_per_message(wired, monkeypatch):
    """Declined at H1, the same message reaching H2 is not tried again."""
    from mvp import history as Hm
    monkeypatch.setattr(Hm, "read", lambda *a, **k: None)
    monkeypatch.setattr(Hm, "read_recall", lambda *a, **k: None)
    from mvp import brainwire as W
    seen = []
    real = W.run

    def counted(*a, **k):
        seen.append(1)
        return real(*a, **k)
    monkeypatch.setattr(W, "run", counted)
    wired["bot"].brain_provider = P().FakeProvider([P().ProviderError("x")])
    wired["bot"]._tl.brain_tried = False
    W.try_turn(wired["bot"], wired["bot"].store.person(H), OPEN_Q, NOW, "H1")   # outside a message: sets the flag
    assert wired["bot"]._tl.brain_tried and len(seen) == 1
    assert W.try_turn(wired["bot"], wired["bot"].store.person(H), OPEN_Q, NOW, "H2") is None and len(seen) == 1
    # a new message resets it
    send(wired, OPEN_Q, good(), {"intent": "chat", "reply": "ok"})
    assert len(seen) == 2


# ================================================================ eligibility
def test_not_eligible_without_the_anthropic_consent(wired):
    wired["bot"].store.set_consent(H, "mvp-consent-v1")
    out, _c, d = send(wired, OCT_Q, None)
    assert d["decision"] == "not_eligible" and d["reason"] == "consent" and "Clip Factory" in out


def test_not_eligible_while_a_preview_waits(wired):
    wired["bot"].store.set_pending(H, "confirm_rule", {"text": "x", "spec": {}, "run_id": None},
                                   at=wired["clock"][0])
    _o, _c, d = send(wired, OCT_Q, None)
    assert d["reason"] == "open"


def test_not_eligible_while_a_setup_step_is_open(wired):
    from mvp.store import now_iso
    wired["bot"].store.set_state(f"onboard:{H}", {"step": "offer", "at": now_iso(wired["clock"][0])})
    _o, _c, d = send(wired, OCT_Q, None)
    assert d is not None and d["reason"] == "open"


@pytest.mark.parametrize("flag", ["in_split", "merged_text", "setup_text", "code_only"])
def test_not_eligible_inside_a_split_a_merged_message_or_the_setup(wired, flag):
    from mvp import brainwire as W
    bot = wired["bot"]
    setattr(bot._tl, flag, True)
    try:
        bot._tl.brain_tried = False
        assert W.not_eligible(bot, bot.store.person(H), NOW) == "open"
    finally:
        setattr(bot._tl, flag, None if flag != "in_split" else False)


def test_not_eligible_over_the_day_cap_or_the_claude_cap_or_with_no_key(wired, monkeypatch):
    from mvp import brainwire as W, config, llm
    bot = wired["bot"]
    p = bot.store.person(H)
    bot._tl.brain_tried = False
    monkeypatch.setattr(llm, "spent_today", lambda h, l: config.DAILY_CAP_USD)
    assert W.not_eligible(bot, p, NOW) == "cap"
    monkeypatch.setattr(llm, "spent_today", lambda h, l: 0.0)
    monkeypatch.setattr(llm, "spent_claude", lambda: config.CLAUDE_CAP_USD)
    assert W.not_eligible(bot, p, NOW) == "claude_cap"
    monkeypatch.setattr(llm, "spent_claude", lambda: 0.0)
    bot.brain_provider = None
    for k in ("DIGESTER_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert W.not_eligible(bot, p, NOW) == "no_key"


def test_over_the_day_cap_a_history_question_gets_todays_answer_never_a_try_again(wired, monkeypatch):
    from mvp import config, llm
    monkeypatch.setattr(llm, "spent_today", lambda h, l: config.DAILY_CAP_USD)
    out, _c, d = send(wired, OCT_Q, None)
    assert d["reason"] == "cap" and "Clip Factory" in out and "Ask me again" not in out


# ================================================================ what a sent answer writes
def test_a_sent_answer_writes_what_todays_follow_up_reads_need(wired):
    bot = wired["bot"]
    bot.store.set_state(f"offers:{H}", {"offers": ["x"], "at": "2026-11-22T16:00:00+00:00"})
    items = {"limit": 3, "order": "newest", "window": {"words": "in October", "preset": None, "same_as": None},
             "scope": SC}
    script = [[tu("items", items)], [ga("Here are your newest from October.", items=[
        {"ref": "r1.items[0]"}, {"ref": "r1.items[1]"}])]]
    out, _c, d = send(wired, OCT_Q, script)
    assert d["decision"] == "sent", d
    run = bot.store.one("SELECT * FROM runs WHERE kind='brain' ORDER BY id DESC")
    steps = json.loads(run["steps"])["brain"]
    assert steps["decision"] == "sent" and steps["site"] == "H1" and steps["tools"] == ["items"]
    assert set(steps) == {"tools", "calls", "results", "lead_source", "events", "seconds", "requests", "check", "cards",
                          "site", "intent", "decision", "reason", "prompt"}
    last = bot.store.last_answer(H)
    assert last["run_id"] == run["id"] and last["goal"] == "history: brain"
    dl = bot.store.q("SELECT item_id, pick_number FROM deliveries WHERE run_id=?", (run["id"],))
    assert len(dl) == steps["cards"] == len(last["items"]) and [x["pick_number"] for x in dl] == list(
        range(1, len(dl) + 1))
    assert bot.store.answer(run["id"]) is not None and bot.store.get_state(f"offers:{H}") is None
    assert bot.store.q("SELECT * FROM sent WHERE run_id=?", (run["id"],))
    assert bot.store.get_state(f"lines:{H}") == {i: [] for i in last["items"]}
    st = bot.store.get_state(f"brain:{H}")
    assert st["run_id"] == run["id"] and set(st) == {"run_id", "at", "screen", "window", "carry"}
    assert "now" not in st["screen"] and st["screen"]["last_answer"]["minutes_ago"] == 1


def test_a_sent_answer_is_in_the_trace(wired):
    bot = wired["bot"]
    bot._tl.trace = {}
    try:
        send(wired, OCT_Q, good())
        tr = dict(bot._tl.trace)
    finally:
        bot._tl.trace = None
    assert tr["intent"] == "brain" and tr["run_id"]


def test_delete_my_data_clears_the_chat_cores_state(wired):
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    assert bot.store.get_state(f"brain:{H}")
    bot.store.delete_person_data(H)
    assert bot.store.get_state(f"brain:{H}") is None


def test_the_chat_cores_screen_goes_stale_after_6_hours_or_a_newer_answer(wired):
    from mvp import brainwire as W
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    now = wired["clock"][0]
    assert W.owns_screen(bot, H, now + timedelta(hours=5, minutes=59))
    assert not W.owns_screen(bot, H, now + timedelta(hours=6, minutes=1))
    run_id = bot.store.add_run(handle=H, kind="ask")
    bot.store.set_last_answer(H, run_id, None, [], "a newer answer")
    assert not W.owns_screen(bot, H, now)
    assert W.screen_for(W.fresh_state(bot, H, now), now, "America/New_York") == {"now": W.now_words(now, "America/New_York")}


# ================================================================ rendering
def test_no_markdown_reaches_a_channel_without_link_parts_and_offers_stay_words(wired):
    bot = wired["bot"]
    items = {"limit": 3, "order": "newest", "window": {"words": "in October", "preset": None, "same_as": None},
             "scope": SC}
    script = [[tu("items", items)], [ga("Here are your newest from October.", items=[{"ref": "r1.items[0]"}],
                                        offers=[{"kind": "by_month"}])]]
    out, _c, d = send(wired, OCT_Q, script)
    assert d["decision"] == "sent", d
    assert "](" not in out and "[" not in out and "By month?" in out
    assert "http" in out and "•" in out
    assert bot.store.get_state(f"offers:{H}") is None   # never a numbered offer: a later "2" runs none
    wired["clock"][0] += timedelta(minutes=1)
    out2, _c, _d = send(wired, "2", None, {"intent": "chat", "reply": "Which one?"})
    assert "By month" not in out2


def test_on_a_channel_with_link_parts_a_card_is_a_link_part_of_its_item(wired):
    from mvp import brainwire as W
    bot = wired["bot"]
    items = {"limit": 3, "order": "newest", "window": {"words": "in October", "preset": None, "same_as": None},
             "scope": SC}
    bot.brain_provider = P().FakeProvider([[tu("items", items)],
                                           [ga("Here are your newest from October.", items=[{"ref": "r1.items[0]"}])]])
    bot._tl.brain_tried = False
    rec, turn, _p, _s, _l = W.run(bot, bot.store.person(H), OCT_Q, NOW, None)
    reply, ids = W.render(bot, bot.store.person(H), rec, turn)
    links = reply.links()
    assert len(links) == 1 == len(ids) and links[0]["url"] == bot.view(str(wired["lib"])).items[ids[0]].url
    alts = [p for p in reply.parts if p.get("card_alt")]
    assert len(alts) == 1 and "[" not in alts[0]["text"]
    # every line of the answer's own text is said (its links as words), in the same order
    plain = rec["answer"]["text"]
    for c in rec["answer"]["cards"]:
        plain = plain.replace(f"[{c['channel']}]({c['url']})", c["channel"])
    assert [x for x in plain.split("\n") if x] == [x for x in "\n".join(p["text"] for p in reply.parts
                                                                        if p["type"] == "text").split("\n") if x]


# ================================================================ threading: two and three turns, against the eval's
def test_two_and_three_turns_thread_the_screen_window_and_carried_topic_as_the_eval_does(wired):
    from mvp import brainwire as W
    from mvp.brain import loop as BL
    bot = wired["bot"]
    ask = {"intent": "ask", "spec": ASK["spec"]}
    fu = {"intent": "follow_up", "question": "which month"}
    _o, _c, d1 = send(wired, NAMED, [[tu("breakdown", BREAK_TOPIC)], [ga(PLAIN_LEAD)]], ask)
    assert d1["decision"] == "sent", d1
    r1, t1 = d1["rec"], d1["turn"]
    assert t1.unlock and BL.unlock_after(t1, r1) == t1.unlock
    turns = [(FOLLOW, MONTHS_TOPIC), (FOLLOW2, NEWEST_TOPIC)]
    prev_r, prev_t, prev_last = r1, t1, None
    for text, args in turns:
        wired["clock"][0] += timedelta(minutes=1)
        now = wired["clock"][0]
        _o, _c, d = send(wired, text, [[tu(args and ("timeline" if "unit" in args else "items"), args)],
                                       [ga(PLAIN_LEAD)]], fu)
        assert d["decision"] == "sent" and d["site"] == "H2", d
        r, t = d["rec"], d["turn"]
        # the eval's threading (eval_brain.live_conversation) from the record before
        assert r["screen"] == BL.screen_after(prev_r, W.now_words(now, "America/New_York"))
        exp_last = BL.last_window(prev_t, prev_r) or prev_last
        assert t.last_window == exp_last and t.last_window is not None
        assert t.carried_unlock == BL.unlock_after(prev_t, prev_r) and t.carried_only
        assert r["unlock_carried"] and r["answer"]["carried_line"]
        prev_r, prev_t, prev_last = r, t, exp_last


# ================================================================ privacy
def test_the_carried_topic_never_reaches_runs_the_trace_or_the_screen_and_no_record_is_written(wired, tmp_path):
    bot = wired["bot"]
    ask = {"intent": "ask", "spec": ASK["spec"]}
    bot._tl.trace = {}
    try:
        _o, _c, d1 = send(wired, NAMED, [[tu("breakdown", BREAK_TOPIC)], [ga(PLAIN_LEAD)]], ask)
        traces = [dict(bot._tl.trace)]
        wired["clock"][0] += timedelta(minutes=1)
        bot._tl.trace = {}
        _o, _c, d2 = send(wired, FOLLOW, [[tu("timeline", MONTHS_TOPIC)], [ga(PLAIN_LEAD)]],
                          {"intent": "follow_up", "question": "which month"})
        traces.append(dict(bot._tl.trace))
    finally:
        bot._tl.trace = None
    topic = d1["turn"].unlock
    assert topic and bot.store.get_state(f"brain:{H}")["carry"] == topic      # only in the one state key
    steps = [r["steps"] for r in bot.store.q("SELECT steps FROM runs WHERE kind='brain'")]
    assert len(steps) == 2 and not any(topic in s or "dating" in s for s in steps)
    assert not any(topic in json.dumps(t, default=str) for t in traces)
    assert topic not in json.dumps(d2["rec"]["screen"])
    sent0 = bot.brain_provider.sent[0][2][0]["content"]
    assert topic not in sent0                                                # the user turn the model read
    # the turn record is written nowhere: no file under the test's folders holds the message
    for root, _dirs, files in os.walk(str(tmp_path)):
        for f in files:
            p = os.path.join(root, f)
            if "lib" in p.split(os.sep):
                continue
            with open(p, "rb") as fh:
                assert NAMED.encode() not in fh.read(), p


# ================================================================ money: the ledger rows name the person, purpose "brain"
def test_every_request_is_logged_with_the_person_and_purpose_brain(wired, monkeypatch):
    from mvp import brainwire as W, llm
    from mvp.tests.fakes.fake_anthropic import sdk_transport

    def msg(content, stop):
        return {"id": "msg_fake", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                "content": content, "stop_reason": stop, "stop_sequence": None,
                "usage": {"input_tokens": 50, "output_tokens": 20, "cache_read_input_tokens": 1000,
                          "cache_creation_input_tokens": 0}}
    full = {"by": "channel", "compare": "none", "order": "most", "top": 5, "window": OCT["window"], "scope": SC}
    answers = [{"status": 200, "json": msg([{"type": "tool_use", "id": "toolu_a", "name": "breakdown",
                                             "input": full}], "tool_use")},
               {"status": 200, "json": msg([{"type": "tool_use", "id": "toolu_b", "name": "give_answer",
                                             "input": {"lead": TRUE_LEAD, "points": [TRUE_POINT]}}], "tool_use")}]
    tr, seen = sdk_transport(answers)
    monkeypatch.setattr(llm.ai, "ANTHROPIC_TRANSPORT", tr)
    monkeypatch.setattr(llm.ai, "ANTHROPIC_CLIENT", None)
    llm.ai._client_cache.clear()
    monkeypatch.setenv("DIGESTER_ANTHROPIC_API_KEY", "made-up-test-key")
    prov = W.new_provider()
    prov.stream = False          # the created request over the fake transport (the body is the same)
    bot = wired["bot"]
    wired["state"]["answers"]["mvp_interpret"] = lambda u: NO_MODEL
    bot.brain_provider = prov
    bot.on_message(H, OCT_Q)
    llm.ai._client_cache.clear()
    d = bot._tl.brain_last
    assert d["decision"] == "sent", (d["rec"]["error"], d["rec"]["events"], d["rec"].get("failed_request"))
    rows = W.ledger_purpose_rows()
    assert len(rows) == 2 == len(seen)
    assert all(r["person"] == llm.person_ref(H) and r["provider"] == "anthropic" and r["prompt_version"] == "brain_v4d"
               and r["model"] == "claude-haiku-5-5" for r in rows)
    assert all(s["body"]["model"] == "claude-haiku-5-5" and "strict" not in json.dumps(s["body"]["tools"])
               for s in seen)
    assert getattr(llm._tl, "person", None) is None                         # restored after the turn


def test_a_budget_refusal_declines_to_todays_bot_with_no_try_again(wired, monkeypatch):
    from mvp import brainwire as W, llm

    def refuse(*a, **k):
        raise RuntimeError("budget stop: anthropic")
    monkeypatch.setattr(llm.ai, "_guard", refuse)
    monkeypatch.setenv("DIGESTER_ANTHROPIC_API_KEY", "made-up-test-key")
    bot = wired["bot"]
    wired["state"]["answers"]["mvp_interpret"] = lambda u: NO_MODEL
    bot.brain_provider = W.new_provider()
    n0 = len(wired["ch"].outbox)
    bot.on_message(H, OCT_Q)
    out = "\n".join(str(t) for _, _, t in wired["ch"].outbox[n0:])
    assert bot._tl.brain_last["reason"] == "provider" and "Clip Factory" in out
    assert "Ask me again" not in out and "limit" not in out.lower()


# ================================================================ consent and "what leaves this computer"
def test_a_switched_on_person_is_shown_anthropic_and_no_training_words_and_agreeing_stores_anthropic(brain,
                                                                                                     monkeypatch):
    from mvp import texts as T, videoask as VA
    monkeypatch.delenv("MVP_BRAIN", raising=False)
    off_consent, off_leaves = T.consent(H), VA.leaves_text(H)
    assert off_consent == T.consent() == T.CONSENT and off_leaves == VA.leaves_text()
    assert T.consent_version(H) == T.consent_version() == T.CONSENT_VERSION
    monkeypatch.setenv("MVP_BRAIN", "1")
    monkeypatch.setenv("MVP_BRAIN_PEOPLE", H)
    c, lv = T.consent(H), VA.leaves_text(H, V1)   # (fix2, A2-10: the line once the consent named Anthropic)
    assert "Anthropic (Claude)" in c and "training" not in c and T.consent_version(H).endswith("+anthropic")
    assert "Anthropic (Claude)" in lv and "training" not in lv.lower() and "watch history and saves" in lv
    assert "your message" in lv and "channel names, dates, counts" in lv and "web" not in lv.lower()
    assert T.consent("+15559990000") == T.CONSENT                          # a person not named: today's text
    # a new person the switch names: the text shown, and "I agree" stores the "+anthropic" version
    bot = brain["bot"]
    bot.store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (H,))
    brain["state"]["answers"]["mvp_interpret"] = lambda u: NO_MODEL
    n0 = len(brain["ch"].outbox)
    bot.on_message(H, "hello")
    shown = "\n".join(str(t) for _, _, t in brain["ch"].outbox[n0:])
    assert "Anthropic (Claude)" in shown and "training" not in shown
    bot.on_message(H, "I agree, I'm over 18")
    assert bot.store.person(H)["consent_version"].endswith("+anthropic")
    # "what leaves this computer", asked through the bot
    n0 = len(brain["ch"].outbox)
    bot.store.set_state(f"onboard:{H}", {"step": "done", "at": "2026-11-22T17:00:00+00:00"})
    bot.on_message(H, "what leaves this computer")
    assert "rows I read from your watch history" in "\n".join(str(t) for _, _, t in brain["ch"].outbox[n0:])
