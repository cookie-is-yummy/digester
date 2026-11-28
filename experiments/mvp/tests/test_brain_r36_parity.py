"""mvp36 (DESIGN 35): the switch, and the measured configuration pinned in the wiring (brainwire.py), compared with the
eval's way of building the same turn (eval_brain run: MVP_BRAIN_PROMPT=brain_v4d, MVP_BRAIN_STRICT=0, --check values,
--loose give_answer). Both sides are built in one process and compared as plain data. Made-up library
(tests/brain_library.py) and made-up messages only; the fake provider only (no model call, no network, no money).
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mvp.tests.test_mvp import env  # noqa: E402,F401  (fixtures)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys, person  # noqa: E402,F401

TZ = "America/New_York"
NOW_WORDS = "Sun 22 Nov 2026 12:00, America/New_York"
MEASURED_ENV = {"MVP_BRAIN_PROMPT": "brain_v4d", "MVP_BRAIN_STRICT": "0", "MVP_BRAIN_CHECK": "values"}
KNOBS = ("MVP_BRAIN_PROMPT", "MVP_BRAIN_STRICT", "MVP_BRAIN_CHECK", "MVP_BRAIN_VALUES_RULES", "MVP_BRAIN_MODEL",
         "MVP_BRAIN_EFFORT", "MVP_BRAIN_THINKING", "MVP_BRAIN_MAX_TOKENS", "MVP_BRAIN_STREAM", "MVP_BRAIN_ROUNDS",
         "MVP_BRAIN_SOFT_S", "MVP_BRAIN_DEEP_S", "MVP_BRAIN_HARD_S")
OCT = {"by": "channel", "window": {"words": "in October", "preset": None, "same_as": None}}
TRUE_LEAD = "In October 2026, Clip Factory[r1.channels[0]] led with 61[r1.channels[0].items] videos."
TRUE_POINT = "Pan Theory[r1.channels[1]] came next with 32[r1.channels[1].items] videos."
MESSAGE = "top channels i watched during october?"


def _purge():
    for m in [m for m in sys.modules if m.startswith("mvp") and not m.startswith("mvp.tests")]:
        del sys.modules[m]


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _plain(system, tools, prov, cm, loop_numbers, screen):
    """The resolved objects of one side, as plain data."""
    from mvp.brain import loop as BL, provider as P, verify as V
    body = prov.body(system, tools, [{"role": "user", "content": "x"}])
    body.pop("messages")
    body.pop("tools")
    body.pop("system")
    return {"system_sha": _sha(system),
            "tools": json.dumps(P.tool_defs(tools, prov.strict, prov.loose), sort_keys=True),
            "tool_list_sha": _sha(json.dumps(tools, sort_keys=True)),
            "body": json.dumps(body, sort_keys=True), "settings": prov.settings(),
            "check": {"name": cm.name, "rules": sorted(cm.rules), "off": sorted(cm.off), "loose": sorted(cm.loose),
                      "cells": cm.cells, "insight": cm.insight,
                      "values_rules": sorted(cm.rules & V.VALUES_RULES_ALL)},
            "loop": list(loop_numbers), "user": BL.user_text(MESSAGE, screen)}


def _clean_env(monkeypatch):
    for k in KNOBS:
        monkeypatch.delenv(k, raising=False)


def test_the_switch_needs_mvp_brain_1_and_the_person_listed_and_is_read_per_message(monkeypatch):
    _clean_env(monkeypatch)
    _purge()
    from mvp import config
    for k in ("MVP_BRAIN", "MVP_BRAIN_PEOPLE"):
        monkeypatch.delenv(k, raising=False)
    assert not config.brain_on("+15550001")
    monkeypatch.setenv("MVP_BRAIN_PEOPLE", "+15550001")
    assert not config.brain_on("+15550001")                       # MVP_BRAIN unset
    for v in ("0", "", "true", "yes", "2"):
        monkeypatch.setenv("MVP_BRAIN", v)
        assert not config.brain_on("+15550001"), v
    monkeypatch.setenv("MVP_BRAIN", "1")                          # read per call, not at import
    assert config.brain_on("+15550001")
    assert config.brain_on("5550001") is False                    # not the same handle
    monkeypatch.setenv("MVP_BRAIN_PEOPLE", " (555) 555-0101 , Sam@Example.com ")
    assert config.brain_on("+15555550101") and config.brain_on("sam@example.com")   # the bot's own spelling
    assert not config.brain_on("+15550001") and not config.brain_on("") and not config.brain_on(None)
    # no default person: the operator is not implied, also on the test page with MVP_OPERATOR unset
    monkeypatch.setenv("MVP_BRAIN_PEOPLE", "")
    monkeypatch.setattr(config, "OPERATOR", None)
    monkeypatch.setattr(config, "PAGE_OPERATOR", True)
    assert config.is_operator("+15550001") and not config.brain_on("+15550001")


def test_the_wiring_pins_the_measured_configuration_and_the_modules_defaults_stay_as_they_were(monkeypatch, tmp_path):
    """Both sides in one process: the handler's way with no brain setting in the environment, then the eval's way
    under the measured run's settings (a fresh import, as a run starts). The resolved objects are equal."""
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    _clean_env(monkeypatch)
    _purge()
    from mvp import brainwire as W
    from mvp.brain import loop as BL, provider as P, verify as V
    # the modules' own import-time defaults are not the measured ones, and are not changed
    assert BL.PROMPT_VERSION == "brain_v3" and P.STRICT is True and V.check_mode(None).name == "full"
    assert (BL.ROUNDS, BL.SOFT_S, BL.DEEP_S, BL.HARD_S) == (3, 7.0, 11.0, 15.0)
    hand = _plain(W.system_text(), W.tool_list(), W.new_provider(), W.CHECK,
                  (W.ROUNDS, W.SOFT_S, W.DEEP_S, W.HARD_S), W.screen_for(None, NOW, TZ))
    hand_purpose = W.new_provider().purpose
    for k, v in MEASURED_ENV.items():
        monkeypatch.setenv(k, v)
    _purge()
    from mvp.brain import loop as BL2, provider as P2, verify as V2
    assert BL2.PROMPT_VERSION == "brain_v4d" and P2.STRICT is False
    prov = P2.AnthropicProvider(prompt_version=BL2.PROMPT_VERSION, loose=("give_answer",))
    ev = _plain(BL2.system_text(), BL2.tool_list(), prov, V2.check_mode(V2.check_mode(None).name),
                (BL2.ROUNDS, BL2.SOFT_S, BL2.DEEP_S, BL2.HARD_S), {"now": NOW_WORDS})
    assert hand == ev
    # the expected values (read_core section 7): the prompt file, ten tools, no `strict`, the measured settings
    assert hand["system_sha"].startswith("e577a8a1a8046f7f") and hand["tool_list_sha"].startswith("757522dde0178ce0")
    assert '"strict"' not in hand["tools"] and len(json.loads(hand["tools"])) == 10
    assert hand["settings"] == {"model": "claude-haiku-5-5", "thinking": {"type": "adaptive"}, "effort": "low",
                                "max_tokens": 4000, "tool_choice": "auto", "strict": False,
                                "strict_off_for": ["give_answer"], "cache": "5m on the system block + automatic tail",
                                "fallbacks": None, "sampling": None, "stream": True}
    assert hand["check"]["name"] == "values" and len(hand["check"]["values_rules"]) == 20
    assert set(hand["check"]["rules"]) == set(hand["check"]["values_rules"]) | {"values", "nw_refuse"}
    assert hand["loop"] == [3, 7.0, 11.0, 15.0]
    assert hand_purpose == "brain" and prov.purpose == "brain_eval"   # the ledger tells the bot's rows from the eval's


def test_a_values_rule_set_in_the_environment_does_not_reach_the_wired_check(monkeypatch, tmp_path):
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    _clean_env(monkeypatch)
    _purge()
    from mvp.brain import verify as V
    extra = sorted(V.VALUES_RULES_SWITCHED - V.VALUES_DEFAULT_RULES)[0]   # a rule only the environment switches on
    monkeypatch.setenv("MVP_BRAIN_VALUES_RULES", extra)
    monkeypatch.setenv("MVP_BRAIN_PROMPT", "brain_v1")
    monkeypatch.setenv("MVP_BRAIN_STRICT", "1")
    _purge()
    from mvp import brainwire as W
    from mvp.brain import verify as V2
    assert extra in V2.VALUES.rules and extra not in W.CHECK.rules
    assert W.system_text() != open(os.path.join(os.path.dirname(W.PROMPT_PATH), "brain_v1.md")).read()
    assert W.new_provider().strict is False


@pytest.fixture()
def measured(monkeypatch):
    """The measured run's settings in the environment before the bot's modules are imported (env purges them)."""
    _clean_env(monkeypatch)
    for k, v in MEASURED_ENV.items():
        monkeypatch.setenv(k, v)


def _ga(lead, points=()):
    from mvp.brain import provider as P
    return P.tool_use("give_answer", {"lead": lead, "points": list(points)}, id_="toolu_ga")


def _bd():
    from mvp.brain import provider as P
    return P.tool_use("breakdown", OCT, id_="toolu_bd")


def _no_seconds(x):
    """The record but for its seconds (and a tool's own milliseconds)."""
    if isinstance(x, dict):
        return {k: _no_seconds(v) for k, v in x.items() if k not in ("seconds", "took_ms")}
    if isinstance(x, list):
        return [_no_seconds(v) for v in x]
    return x


def _ms(sent):
    import re
    return re.sub(r'\\?"took_ms\\?": \d+', "took_ms", json.dumps(sent, sort_keys=True, default=str))


def test_one_fake_script_through_the_eval_and_through_the_wiring_gives_the_same_record(measured, brain):
    from mvp import brainwire as W
    from mvp import eval_brain as E
    from mvp.brain import loop as BL, provider as P
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    h = E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                  now=NOW)
    script = [[_bd()], [_ga(TRUE_LEAD, [TRUE_POINT])]]
    p1 = P.FakeProvider([list(s) for s in script])
    t1 = h.turn(MESSAGE, screen="", last_window=None, search=FakeEngine(), learned=fake_learned, carried_unlock=None)
    r1 = BL.run_turn(p1, t1, MESSAGE, {"now": E.NOW_WORDS}, check="values")   # as run_live passes --check values
    bot = brain["bot"]
    bot.brain_provider = P.FakeProvider([list(s) for s in script])
    r2, t2, prov, screen, _last = W.run(bot, dict(person(brain)), MESSAGE, NOW, None)
    assert screen == {"now": E.NOW_WORDS}
    assert _no_seconds(r1) == _no_seconds(r2) and r2["lead_source"] == "model"
    # what each request sent is the same (but for a tool's own milliseconds), and the proxy stopped nothing
    assert _ms(p1.sent) == _ms(bot.brain_provider.sent) and len(p1.sent) == 2 and prov.stopped_at is None
    # threading, for the next message, as the eval does it
    assert BL.screen_after(r2, E.NOW_WORDS) == BL.screen_after(r1, E.NOW_WORDS)
    assert BL.last_window(t2, r2) == BL.last_window(t1, r1) and BL.unlock_after(t2, r2) == BL.unlock_after(t1, r1)


def test_the_screens_now_is_codes_words_in_the_eval_format_and_minutes_ago_is_the_real_gap(measured, brain):
    from mvp import brainwire as W
    assert W.now_words(NOW, TZ) == NOW_WORDS
    assert W.now_words(datetime(2026, 11, 5, 14, 7, tzinfo=timezone.utc), TZ) == "Thu 5 Nov 2026 09:07, America/New_York"
    st = {"at": NOW.isoformat(), "screen": {"last_answer": {"minutes_ago": 1, "plan": [], "scope_line": None}}}
    later = NOW + timedelta(minutes=47, seconds=30)
    scr = W.screen_for(st, later, TZ)
    assert scr["last_answer"]["minutes_ago"] == 47 and scr["now"] == W.now_words(later, TZ)
    assert st["screen"]["last_answer"]["minutes_ago"] == 1           # the stored screen is not changed


@pytest.fixture()
def unset_knobs(monkeypatch):
    """No brain setting in the environment before the bot's modules are imported (the bot's own case)."""
    _clean_env(monkeypatch)


def test_what_the_wiring_passes_to_run_turn_is_the_evals_resolved_configuration(unset_knobs, brain, monkeypatch):
    """(repair F07) The arguments W.run itself hands to loop.run_turn, read by wrapping run_turn while it runs with no
    MVP_BRAIN_* variable set, against what the eval's run resolves under the measured settings (a fresh import): the
    loop numbers, the system text, the tools and the check with its rules. Every one is passed (none is left to the
    loop's environment defaults)."""
    from mvp import brainwire as W
    from mvp.brain import loop as BL, provider as P, verify as V
    assert BL.PROMPT_VERSION == "brain_v3" and V.check_mode(None).name == "full"   # the defaults are not the measured
    seen = []
    real = BL.run_turn

    def wrapped(*a, **k):
        seen.append(k)
        return real(*a, **k)
    monkeypatch.setattr(BL, "run_turn", wrapped)
    bot = brain["bot"]
    bot.brain_provider = P.FakeProvider([[_bd()], [_ga(TRUE_LEAD, [TRUE_POINT])]])
    rec, _t, _p, _s, _l = W.run(bot, dict(person(brain)), MESSAGE, NOW, None)
    assert len(seen) == 1 and rec["lead_source"] == "model"
    k = seen[0]
    assert {"rounds", "soft_s", "deep_s", "hard_s", "system", "tools", "check"} <= set(k)
    cm = V.check_mode(k["check"])
    hand = {"loop": [k["rounds"], k["soft_s"], k["deep_s"], k["hard_s"]], "system_sha": _sha(k["system"]),
            "tools": json.dumps(k["tools"], sort_keys=True), "check": cm.name, "rules": sorted(cm.rules),
            "off": sorted(cm.off), "loose": sorted(cm.loose)}
    for key, v in MEASURED_ENV.items():
        monkeypatch.setenv(key, v)
    _purge()
    from mvp.brain import loop as BL2, verify as V2
    cm2 = V2.check_mode("values")   # as run_live passes --check values
    ev = {"loop": [BL2.ROUNDS, BL2.SOFT_S, BL2.DEEP_S, BL2.HARD_S], "system_sha": _sha(BL2.system_text()),
          "tools": json.dumps(BL2.tool_list(), sort_keys=True), "check": cm2.name, "rules": sorted(cm2.rules),
          "off": sorted(cm2.off), "loose": sorted(cm2.loose)}
    assert hand == ev
    assert hand["loop"] == [3, 7.0, 11.0, 15.0] and hand["system_sha"].startswith("e577a8a1a8046f7f")
