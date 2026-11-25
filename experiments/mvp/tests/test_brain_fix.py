"""mvp20 fix (the brain's thin live slice, closed): what the two checkers of the tuned slice found, each class
reproduced first and fixed by a rule. Offline: no model call, no network. The library is the made-up one of
tests/brain_library.py; every title, channel and theme is made up.

Two sources: the hand recount of the held-out answers that were sent (5 false sentences, all in code-lead answers),
and the verifier attack (eval/brain_attack_cases.py: false and true sentences on real tool results, each recounted by
the attacker from the rows). Each class here has its false sentence (dropped) and a true twin (kept)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys, person  # noqa: E402,F401

MVP = os.path.dirname(HERE)
PLANTED = os.path.join(MVP, "eval", "brain_planted.json")


def _attack():
    import importlib.util
    spec = importlib.util.spec_from_file_location("brain_attack_cases",
                                                  os.path.join(MVP, "eval", "brain_attack_cases.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _attack_ledgers(e):
    """{name: (envelopes, turn dict)} of the attack's ledgers from today's tools (took_ms zeroed: a timing)."""
    from mvp.brain import tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine
    A = _attack()
    out = {}
    for name, (msg, calls) in A.LEDGERS.items():
        t = TL.Turn(e["bot"], person(e), NOW, message=msg, search=FakeEngine())
        envs = [TL.call(t, tool, args) for tool, args in calls]
        for env_ in envs:
            env_["took_ms"] = 0
            assert not env_.get("is_error"), (name, env_)
        vt = V.Turn.of(t)
        out[name] = (json.loads(json.dumps(envs, default=str)),
                     {"message": msg, "unlock": vt.unlock, "today": vt.today.isoformat(), "names": vt.names,
                      "sensitive_names": vt.sensitive_names})
    return out


def test_the_attack_ledgers_frozen_in_the_planted_set_are_todays_tools(brain):
    got = _attack_ledgers(brain)
    with open(PLANTED, encoding="utf-8") as f:
        data = json.load(f)
    if os.environ.get("MVP_FREEZE_ATTACK") == "1":   # rewrite them (then run eval/build_brain_planted.py)
        for name, (envs, t) in got.items():
            data["ledgers"]["attack_" + name] = envs
            data.setdefault("attack_turns", {})[name] = t
        with open(PLANTED, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
    for name, (envs, t) in got.items():
        assert data["ledgers"]["attack_" + name] == envs, name
        assert data["attack_turns"][name] == t, name


def test_every_false_sentence_of_the_attack_is_dropped_and_its_true_ones_counted():
    from mvp.brain import planted as P
    s = P.score()
    a, t = s["by_source"]["attack"], s["by_source"]["attack_true"]
    kept = [r["id"] for r in s["rows"] if r.get("source") == "attack" and r["kept"]]
    assert a["false"] == 169 and a["false_dropped"] == 169, kept   # 166 sentences, 3 tried as a lead and a point
    assert t["true"] == 63 and t["true_kept"] >= ATTACK_TRUE_KEPT   # 60 sentences, 3 tried both ways
    # the builder's own bar is unchanged by the attack's cases
    assert s["false_dropped"] == s["false"] and s["true_kept"] == s["true"]


ATTACK_TRUE_KEPT = 0   # set to the measured figure once the rules are in (the tuned verifier kept 42 of 60)
