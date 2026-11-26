"""mvp28 args: with strict tool grammar off (MVP_BRAIN_STRICT=0) the server no longer holds the model's tool arguments
to the schema, so code does: a model's call (tools.call(..., sent=True), as loop.run_turn makes it) is checked against
the very schema sent to the model before its argument model runs. An unknown key, a missing key, a wrong type (a bool
or a whole float for an integer), a value outside an enum, a string where a list is due: each is refused with an error
that names the argument and what it allows, so the model can call again. Nothing is defaulted, coerced or dropped.
A call inside the schema runs exactly as before; code's own calls (hand plans, tests) keep the argument models'
defaults. Also: the eval counts tool errors by kind and survives an auditor that raises; and what the tools do with
friends' posts (in no row; a counted result says how many it left out).

Made-up library and made-up messages only; no model call.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys, person  # noqa: E402,F401
from mvp.tests.test_brain_evaltools import OCT, harness, made_up_fresh  # noqa: E402,F401  (harness is a fixture)

# (the fixtures drop every mvp module between tests, so each test imports the brain's modules itself)

W = {"preset": None, "same_as": None, "words": "in October"}
SC = {"exclude": [], "how": "opened", "length": "any", "only": [], "platforms": [], "weekday": None}
FULL = {   # every read tool's arguments as strict grammar makes the model send them: every key, each of its type
    "find": {"kinds": [], "names": ["Home cooking"]},
    "breakdown": {"by": "theme", "compare": "previous", "order": "most", "scope": SC, "top": 8, "window": W},
    "timeline": {"scope": SC, "unit": "month", "window": dict(W, words="2024")},
    "changes": {"against": "previous", "level": "theme", "scope": SC, "window": dict(W, words="2024")},
    "compare": {"a": dict(W, words="2024"), "b": dict(W, words="2023"), "by": "none", "scope": SC},
    "first_last": {"scope": SC, "subject": "Home cooking", "which": "first"},
    "items": {"limit": 5, "offset": 0, "order": "most_opened", "scope": SC, "window": W},
    "search": {"how": "saved", "limit": 5, "query": "sourdough bread", "window": None},
    "learned": {"scope": SC, "topic": "sourdough"},
}
MSG = "what did i watch in october and in 2024, and how did 2023 compare?"


def _turn(e, message=MSG):
    from mvp.brain import tools as TL
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    return TL.Turn(e["bot"], person(e), NOW, message=message, search=FakeEngine(), learned=fake_learned)


def _call(e, name, args, sent=True, message=MSG):
    from mvp.brain import tools as TL
    env_ = dict(TL.call(_turn(e, message), name, copy.deepcopy(args), sent=sent))
    env_.pop("took_ms", None)
    return env_


def _with(args, path, value, drop=False):
    a = copy.deepcopy(args)
    cur = a
    for k in path[:-1]:
        cur = cur[k]
    if drop:
        cur.pop(path[-1])
    else:
        cur[path[-1]] = value
    return a


# ================================================================ 1. inside the schema: exactly as before
def test_every_full_call_is_inside_the_schema_and_runs_as_before(brain):
    from mvp.brain import tools as TL
    assert sorted(FULL) == sorted(n for n in TL.REGISTRY if TL.REGISTRY[n].run is not None)
    for name, args in FULL.items():
        assert TL.sent_problems(name, args) == [], name
        assert _call(brain, name, args, sent=True) == _call(brain, name, args, sent=False), name


def test_code_own_calls_keep_the_defaults(brain):
    # a hand plan writes only what it needs; the argument models fill the rest, as before
    got = _call(brain, "breakdown", {"by": "channel", "window": {"words": "in October"}}, sent=False)
    assert not got.get("is_error") and got["meta"]["order"] == "most"


# ================================================================ 2. outside the schema: refused, named, with what is allowed
def _refused(e, name, args):
    got = _call(e, name, args)
    assert got.get("is_error") and got.get("outside_schema"), got
    assert got["error"].startswith(f"Arguments outside the schema of {name}: ")
    assert got["next"].startswith(f"call {name} again")
    return got


def test_a_missing_key_is_refused_never_defaulted(brain):
    # the class of case: a ranking key left out of a totals-only breakdown still orders the lists inside the result
    got = _refused(brain, "breakdown", _with(FULL["breakdown"], ["order"], None, drop=True))
    assert got["outside_schema"] == ["order"] and "'most', 'least'" in got["error"]
    got = _refused(brain, "items", _with(FULL["items"], ["scope"], None, drop=True))
    assert got["outside_schema"] == ["scope"] and "exclude, how, length, only, platforms, weekday" in got["error"]
    got = _refused(brain, "breakdown", _with(FULL["breakdown"], ["window"], {"words": "in October"}))
    assert sorted(got["outside_schema"]) == ["window.preset", "window.same_as"]


def test_a_bool_or_a_whole_float_or_a_numeric_string_is_no_integer(brain):
    # weekday true used to be read as 1 (Tuesday), top true as 1, a numeric string as its number
    for path, v in ((["scope", "weekday"], True), (["scope", "weekday"], 3.0), (["scope", "weekday"], "3"),
                    (["top"], True), (["top"], 8.0), (["top"], "8")):
        got = _refused(brain, "breakdown", _with(FULL["breakdown"], path, v))
        assert got["outside_schema"] == [".".join(path)], (path, v)
    assert "`scope.weekday` must be an integer or null (got true)" in _call(
        brain, "items", _with(FULL["items"], ["scope", "weekday"], True))["error"]


def test_an_unknown_key_names_the_keys_that_exist(brain):
    # (the prep repair: the unknown key itself is never said back; the model wrote it, and it can hold a title's
    # text, a marker or an instruction; the object that holds it and the keys that exist are said)
    got = _refused(brain, "breakdown", _with(FULL["breakdown"], ["scope", "platform"], "youtube"))
    assert "`scope` has a key that is not an argument (the keys of scope are exclude, how, length, only, platforms, " \
           "weekday)" in got["error"] and "platform`" not in got["error"]
    got = _refused(brain, "breakdown", _with(FULL["breakdown"], ["made_up"], 1))
    assert got["outside_schema"] == ["*"] and "made_up" not in got["error"]
    # inside an optional window (an object or null): the wrong key of the object is named, not only "object or null"
    got = _refused(brain, "search", _with(FULL["search"], ["window"], {"word": "October"}))
    assert "window.*" in got["outside_schema"] and "`window` has a key that is not an argument" in got["error"]


def test_an_enum_value_or_a_type_outside_the_schema_lists_what_it_allows(brain):
    got = _refused(brain, "breakdown", _with(FULL["breakdown"], ["scope", "how"], "watched"))
    assert "`scope.how` must be one of 'opened', 'liked', 'saved', 'any' (got a string of 7 characters)" in got["error"]
    got = _refused(brain, "items", _with(FULL["items"], ["window", "preset"], "yesterday"))
    assert "window.preset" in got["outside_schema"]
    got = _refused(brain, "compare", _with(FULL["compare"], ["scope", "only"], "Home cooking"))
    assert "`scope.only` must be a list of strings" in got["error"]
    got = _refused(brain, "find", _with(FULL["find"], ["kinds"], ["topic"]))
    assert got["outside_schema"] == ["kinds[0]"]
    got = _refused(brain, "first_last", [FULL["first_last"]])
    assert got["outside_schema"] == ["arguments"]


def test_every_problem_is_said_in_one_error(brain):
    # each refusal costs a round: one retry must be enough
    args = _with(_with(FULL["breakdown"], ["order"], None, drop=True), ["scope", "how"], "watched")
    got = _refused(brain, "breakdown", args)
    assert sorted(got["outside_schema"]) == ["order", "scope.how"]


def test_inside_the_schema_the_argument_models_still_check_bounds_and_windows(brain):
    for args in (_with(FULL["breakdown"], ["top"], 500), _with(FULL["breakdown"], ["window", "preset"], "lately"),
                 _with(FULL["breakdown"], ["window", "words"], "the blursday period")):
        got = _call(brain, "breakdown", args)
        assert got.get("is_error") and "outside_schema" not in got, args


# ================================================================ 3. the loop: a refused call, then the corrected one
def test_a_provider_with_strict_on_is_held_too(brain):
    # a run with --loose sends the read tools without strict while `strict` reads true: held all the same
    from mvp.brain import loop as BL, provider as P
    prov = P.FakeProvider([[P.tool_use("breakdown", {"by": "channel", "window": {"words": "in October"}})], []])
    prov.strict = True
    rec = BL.run_turn(prov, _turn(brain), MSG, {})
    assert rec["calls"][0]["result"].get("outside_schema")


def test_the_offline_fakes_keep_their_short_calls(brain):
    from mvp.brain import loop as BL, provider as P
    prov = P.FakeProvider([[P.tool_use("breakdown", {"by": "channel", "window": {"words": "in October"}})], []])
    rec = BL.run_turn(prov, _turn(brain), MSG, {})
    assert not rec["calls"][0]["result"].get("is_error")



def test_the_loop_holds_the_models_calls_to_the_schema_and_the_model_can_call_again(brain):
    from mvp.brain import loop as BL, provider as P
    bad = _with(FULL["breakdown"], ["order"], None, drop=True)
    form = {"understood": "their October", "lead": "Here is what you opened in October.", "points": [], "items": [],
            "chart": None, "outside": [], "ask_back": None, "offers": [], "setup": None, "corrects_previous": False,
            "hand_back": None}
    prov = P.FakeProvider([[P.tool_use("breakdown", bad)], [P.tool_use("breakdown", FULL["breakdown"])],
                           [P.tool_use("give_answer", form)]])
    prov.strict = False   # a provider that says its grammar: strict off, as MVP_BRAIN_STRICT=0 sends it
    rec = BL.run_turn(prov, _turn(brain), MSG, {})
    first, second = rec["calls"]
    assert first["result"]["is_error"] and first["result"]["outside_schema"] == ["order"]
    assert not second["result"].get("is_error") and second["rid"] == "r1"
    # what the model read back is the error, naming the argument
    sent_back = prov.sent[1][2][-1]["content"][0]
    assert sent_back["is_error"] and "`order` is missing" in sent_back["content"]


# ================================================================ 4. the eval: tool errors by kind, the auditor guarded
def test_tool_error_kinds_and_the_runs_counts(env):
    from mvp import eval_brain as E
    recs = [{"key": "X1.0", "strict": False, "events": ["time_up"], "verdicts": [{"form_error": "missing"}, {}],
             "calls": [{"result": {"is_error": True, "error": "Arguments outside the schema of items: ...",
                                   "outside_schema": ["order"]}},
                       {"result": {"is_error": True, "error": "scope.how: Input should be 'opened'"}},
                       {"result": {"is_error": True, "error": "window words not understood: 'x'."}},
                       {"result": {"is_error": True, "error": "Their export holds no likes: ..."}},
                       {"result": {"rid": "r1", "sheet": {}}}]},
            {"key": "X2.0", "strict": False, "events": [], "verdicts": [], "calls": [], "audit_error": "KeyError: 'x'"}]
    one = E.tool_args_of(recs[0])
    assert one["tool_errors"] == {"outside_schema": 1, "arguments": 1, "window": 1, "not_in_export": 1}
    assert one["arg_errors"] == 2 and one["form_errors"] == 1 and one["time_up"] == 1
    s = E.tool_args_summary(recs, {"strict": False})
    assert s["strict"] is False and s["arg_errors"] == 2 and s["tool_errors"] == 4
    assert s["messages_with_arg_errors"] == ["X1.0"] and s["arg_error_then_time_up"] == ["X1.0"]
    assert s["audit_errors"] == ["X2.0"] and E._audit_exit({"tool_args": s}) == 1
    assert E._audit_exit({"tool_args": dict(s, audit_errors=[])}) == 0


def test_strict_is_read_for_the_read_tools():
    from mvp import eval_brain as E
    assert E.strict_reads({"strict": True, "strict_off_for": ["give_answer"]}) is True
    assert E.strict_reads({"strict": False, "strict_off_for": ["give_answer"]}) is False
    assert E.strict_reads({"strict": True, "strict_off_for": ["breakdown", "give_answer"]}) is False
    assert E.strict_reads({"model": "fake"}) is None and E.strict_reads(None) is None


def test_an_auditor_that_raises_in_a_live_conversation_keeps_the_record_and_fails_the_run(harness, tmp_path,
                                                                                            monkeypatch):
    import json
    from mvp import eval_brain as E
    from mvp.brain import provider as P
    path = str(tmp_path / "fresh.jsonl")
    made_up_fresh(path)
    (p, core), = E.run_set("a", set_name="fresh", path=path)

    def boom(*a, **k):
        raise ValueError("could not convert string to float: '2026-10-12'")
    monkeypatch.setattr(E, "audit_sent", boom)
    lead = "In October 2026, gaming[r1.areas[0]] led what you opened."
    script = [[P.tool_use("breakdown", {"by": "area", "window": OCT})],
              [P.tool_use("give_answer", {"lead": lead, "points": []})],
              [P.tool_use("breakdown", {"by": "area", "window": OCT})],
              [P.tool_use("give_answer", {"lead": lead, "points": []})]]
    out = tmp_path / "run"
    out.mkdir()
    recs = E.live_conversation(harness, P.FakeProvider(script), p, core, out_dir=str(out), log=lambda s: None,
                               set_name="fresh")
    assert recs and all(r["audit_error"].startswith("ValueError: could not convert") for r in recs)
    for r in recs:
        saved = json.load(open(out / f"{r['key']}.json"))
        assert saved["audit_error"] == r["audit_error"] and saved["audit"] == {"checked": 0, "findings": []}
        assert saved["strict"] is None and saved["tool_args"]["arg_errors"] == 0
    s = E.summarize(recs, {"set": "fresh"})
    assert s["tool_args"]["audit_errors"] == sorted(r["key"] for r in recs) and E._audit_exit(s) == 1


def test_an_auditor_that_raises_never_loses_the_record(env, monkeypatch):
    from mvp import eval_brain as E

    def boom(*a, **k):
        raise ValueError("could not convert string to float: '2026-10-12'")
    monkeypatch.setattr(E, "audit_sent", boom)
    bad, checked, err = E.guarded_audit(None, {}, None, {}, "q")
    assert (bad, checked) == ([], 0) and err.startswith("ValueError: could not convert")
    monkeypatch.setattr(E, "audit_sent", lambda *a, **k: (["hint"], 3))
    assert E.guarded_audit(None, {}, None, {}, "q") == (["hint"], 3, None)


# ================================================================ 5. what the tools do with friends' posts
# (the note's words stay: tests/test_brain_tools.py pins "Posts from friends are not counted." byte for byte)
def test_a_friends_post_is_in_no_row_and_a_counted_result_says_how_many_it_left_out(brain):
    from mvp.brain import tools as TL
    msg = "what did my friends send me that i saved, all time?"
    args = _with(_with(FULL["items"], ["scope", "how"], "saved"), ["window"], {"preset": "all", "same_as": None,
                                                                                "words": None})
    t = _turn(brain, msg)
    got = TL.call(t, "items", args, sent=True)
    assert got["sheet"]["left_out"]["friends"] >= 1 and got["meta"]["hidden"]["friends"] >= 1
    assert all(t.lib.is_visible(r["item_id"]) for r in got["sheet"]["items"])
    assert TL.FRIENDS_LINE in got["meta"]["notes"]
