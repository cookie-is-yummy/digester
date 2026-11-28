"""Offline tests for round 9, C1 (DESIGN.md section 16.D): the registry fields every outward action needs, with
today's behaviour as the default; validate_action's `by` and `where`; perform's yes token, operator check and daily
cap counted from action_log on the person's local day; config.OPERATOR and is_operator; the stub entry points other
slices import. Synthetic data only; fake actions are registered for each test and removed after it; no model call."""
import importlib
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

UTC = timezone.utc
TEXT = "Hi Sam,\n\nThe kitchen sink is broken.\n\nThanks"


def _fake_module(name, ran, yes=None):
    m = types.ModuleType(f"mvp.actions.{name}")

    def run(ctx, params):
        from mvp.actions.base import Outcome
        ran.append((name, ctx.now))
        return Outcome("done", line=f"{name} ran")
    m.run = run
    if yes is not None:
        m.yes_token = yes
    return m


def _send_yes(ctx, params):
    """What a send_word module does: the token of the exact text it is about to send."""
    from mvp.actions import make_yes_token, text_hash
    return make_yes_token("draft-1", 1, text_hash(ctx.request_text))


@pytest.fixture()
def fakes(monkeypatch):
    """Fake actions in the live registry (whatever mvp.actions is loaded now), removed after the test."""
    A = importlib.import_module("mvp.actions")
    from mvp.actions import ActionDef, NoParams
    ran = []
    defs = {
        "fake.plain": dict(),
        "fake.code_only": dict(from_model=False),
        "fake.no_rules": dict(in_rules=False),
        "fake.capped": dict(max_per_day=2),
        "fake.out_a": dict(outside=True),
        "fake.out_b": dict(outside=True),
        "fake.send": dict(confirm="send_word", outside=True, undo="hold", in_rules=False, from_model=False),
        "fake.send_nomod": dict(confirm="send_word"),
        "fake.mine": dict(who="operator"),
    }
    for i, (name, kw) in enumerate(defs.items()):
        mod = name.replace(".", "_")
        yes = _send_yes if name == "fake.send" else None
        monkeypatch.setitem(sys.modules, f"mvp.actions.{mod}", _fake_module(name, ran, yes))
        monkeypatch.setitem(A.REGISTRY, name, ActionDef(name=name, params=NoParams, module=mod, order=50 + i,
                                                        does="a test action", **kw))
    return {"A": A, "ran": ran}


def ctx_for(env, now, handle=H, request=""):
    from mvp.actions.base import Ctx
    person = env["bot"].store.person(handle)
    return Ctx(bot=env["bot"], person=person, answer={"kind": "picks", "goal": "x", "parts": [], "picks": []},
               picks=[], run_id=None, now=now, tz=person["timezone"], request_text=request)


def run_logged(env, ctx, name, **kw):
    """perform, then log the outcome the way every caller does (outputs._perform does the same)."""
    from mvp.actions import perform
    o = perform(name, ctx, **kw)
    env["bot"].store.log_action(ctx.handle, None, None, name, o.status, detail={"line": o.line}, at=ctx.now)
    return o


# ---------- the fields, with today's behaviour as the default ----------
def test_existing_actions_keep_todays_behaviour():
    from mvp.actions import REGISTRY
    assert set(REGISTRY) >= {"message.send", "email.send", "calendar.add", "todo.add"}
    for name in ("message.send", "email.send", "calendar.add", "todo.add"):
        d = REGISTRY[name]
        assert (d.outside, d.undo, d.confirm, d.max_per_day, d.in_rules, d.who, d.from_model, d.connector,
                d.fallback) == (False, "none", "never", None, True, "anyone", True, None, None), name


def test_the_fields_only_take_the_listed_values():
    from pydantic import ValidationError
    from mvp.actions import ActionDef, NoParams
    base = dict(name="x.y", params=NoParams, module="x", order=1, does="x")
    for bad in (dict(undo="later"), dict(confirm="yes"), dict(who="everyone"), dict(max_per_day=0)):
        with pytest.raises(ValidationError):
            ActionDef(**base, **bad)
    ok = ActionDef(**base, outside=True, undo="hold", confirm="send_word", max_per_day=5, in_rules=False,
                   who="operator", from_model=False, connector="mailbox", fallback="email.send")
    assert ok.connector == "mailbox" and ok.fallback == "email.send"


# ---------- validate_action: who names it and where ----------
def test_a_code_only_action_fails_a_model_form_and_passes_a_code_call(fakes):
    from pydantic import ValidationError
    from mvp.actions import validate_action
    from mvp.schema import Action, Interpretation, RuleSpec
    with pytest.raises(ValidationError):
        Action.model_validate({"action": "fake.code_only"})
    with pytest.raises(ValidationError):
        Action.model_validate("fake.code_only")                       # a bare name is the same form
    with pytest.raises(ValidationError):
        RuleSpec.model_validate({**pasta_spec(), "do": ["fake.code_only"]})
    with pytest.raises(ValidationError):
        Interpretation.model_validate({"intent": "act_on_last", "pick_number": 1, "actions": ["fake.code_only"]})
    with pytest.raises(ValueError):
        validate_action("fake.code_only")                             # the default is a model form
    assert validate_action("fake.code_only", {}, by="code") == ("fake.code_only", {})
    # near-variant: an action with the default fields passes everywhere
    assert Action.model_validate("fake.plain").action == "fake.plain"
    assert [a.action for a in RuleSpec.model_validate({**pasta_spec(), "do": ["fake.plain"]}).do] == ["fake.plain"]
    i = Interpretation.model_validate({"intent": "act_on_last", "pick_number": 1, "actions": ["fake.plain"]})
    assert [a.action for a in i.actions] == ["fake.plain"]


def test_an_action_kept_out_of_rules_is_refused_in_a_rule_and_in_act_on_last(fakes):
    from pydantic import ValidationError
    from mvp.actions import validate_action
    from mvp.schema import Action, Interpretation, RuleSpec
    assert Action.model_validate("fake.no_rules").action == "fake.no_rules"     # a form of its own: fine
    with pytest.raises(ValidationError):
        RuleSpec.model_validate({**pasta_spec(), "do": ["fake.no_rules"]})
    with pytest.raises(ValidationError):
        RuleSpec.model_validate({**pasta_spec(), "do": ["message.send", {"action": "fake.no_rules"}]})
    with pytest.raises(ValidationError):
        Interpretation.model_validate({"intent": "act_on_last", "pick_number": 1,
                                       "actions": ["todo.add", "fake.no_rules"]})
    with pytest.raises(ValidationError):   # a rule inside a new_rule form is the same rule
        Interpretation.model_validate({"intent": "new_rule", "spec": {**pasta_spec(), "do": ["fake.no_rules"]}})
    for where in ("rule", "act"):
        with pytest.raises(ValueError):
            validate_action("fake.no_rules", by="code", where=where)     # code can't put it in a rule either
    assert validate_action("fake.no_rules", by="code", where="form")[0] == "fake.no_rules"


def test_validate_action_refuses_an_unknown_who_or_where(fakes):
    from mvp.actions import validate_action
    for kw in (dict(by="agent"), dict(where="mcp"), dict(by="")):
        with pytest.raises(ValueError):
            validate_action("fake.plain", **kw)
    with pytest.raises(ValueError):
        validate_action("fake.nothing", by="code")


def test_a_model_form_naming_a_code_only_action_runs_nothing(env, fakes):
    """End to end: the interpreter's form names it (in act_on_last, and in a new rule); nothing runs or is stored."""
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "a pasta recipe", ask_pasta())
    for name in ("fake.code_only", "fake.send", "fake.no_rules"):
        say(env, "do that with it", {"intent": "act_on_last", "pick_number": 1, "actions": [name]})
        say(env, "every friday send me pasta", {"intent": "new_rule", "spec": {**pasta_spec(), "do": [name]}})
        say(env, "yes", {"intent": "chat"})
    assert fakes["ran"] == []
    store = env["bot"].store
    assert not store.q("SELECT * FROM action_log WHERE action LIKE 'fake.%'")
    assert all("fake." not in (r.get("spec") or "") for r in store.q("SELECT spec FROM rules"))


# ---------- the daily cap, counted from action_log on the person's local day ----------
def test_the_third_run_in_one_local_day_is_skipped_with_the_cap_line(env, fakes):
    from mvp import texts as T
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)                    # 9 am in New York
    assert run_logged(env, ctx_for(env, t0), "fake.capped").status == "done"
    assert run_logged(env, ctx_for(env, t0 + timedelta(hours=3)), "fake.capped").status == "done"
    o = run_logged(env, ctx_for(env, t0 + timedelta(hours=4)), "fake.capped")
    assert (o.status, o.line) == ("skipped", T.over_action_cap(None, 2))
    assert o.line == "I've reached my limit for this today (2 a day). I can do it again tomorrow."
    assert len(fakes["ran"]) == 2
    # 11:59 pm in New York is still the same day (04:59 UTC the next day)
    assert run_logged(env, ctx_for(env, datetime(2026, 11, 13, 4, 59, tzinfo=UTC)), "fake.capped").status == "skipped"
    # 12:01 am in New York is the next day: it runs again
    assert run_logged(env, ctx_for(env, datetime(2026, 11, 13, 5, 1, tzinfo=UTC)), "fake.capped").status == "done"
    assert len(fakes["ran"]) == 3


def test_a_label_names_what_was_capped(env, fakes, monkeypatch):
    from mvp import texts as T
    monkeypatch.setitem(T.ACTION_CAP_LABEL, "fake.capped", "emails")
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
    for _ in range(2):
        run_logged(env, ctx_for(env, t0), "fake.capped")
    o = run_logged(env, ctx_for(env, t0), "fake.capped")
    assert o.line == "I've reached my limit of 2 emails a day for you. I can do more tomorrow."


def test_the_day_follows_the_persons_time_zone(env, fakes):
    store = env["bot"].store
    store.set_timezone(H, "Asia/Tokyo")
    # 14:00 and 16:00 UTC on 12 Nov are 11 pm on the 12th and 1 am on the 13th in Tokyo: two different days
    t1, t2 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC), datetime(2026, 11, 12, 16, 0, tzinfo=UTC)
    run_logged(env, ctx_for(env, t1), "fake.capped")
    run_logged(env, ctx_for(env, t1), "fake.capped")
    assert run_logged(env, ctx_for(env, t1), "fake.capped").status == "skipped"
    assert run_logged(env, ctx_for(env, t2), "fake.capped").status == "done"
    # near-variant: in New York both are the 12th, so the second time is still capped
    store.set_timezone(H, "America/New_York")
    assert run_logged(env, ctx_for(env, t2), "fake.capped").status == "skipped"


def test_skipped_failed_other_people_and_other_actions_do_not_count(env, fakes):
    store = env["bot"].store
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
    for status in ("skipped", "failed", "skipped"):
        store.log_action(H, None, None, "fake.capped", status, at=t0)
    store.log_action("+15550002", None, None, "fake.capped", "done", at=t0)
    store.log_action("+15550002", None, None, "fake.capped", "done", at=t0)
    store.log_action(H, None, None, "fake.plain", "done", at=t0)
    store.log_action(H, None, None, "fake.plain", "done", at=t0)
    store.log_action(H, None, None, "fake.capped", "done", at=t0 - timedelta(days=1))   # yesterday
    store.log_action(H, None, None, "fake.capped", "done", at=t0 - timedelta(days=1))
    assert run_logged(env, ctx_for(env, t0), "fake.capped").status == "done"
    # a row the action waits on ("waiting", "outbox", "held") counts: it is what was done or is being done
    store.log_action(H, None, None, "fake.capped", "held", at=t0)
    assert run_logged(env, ctx_for(env, t0), "fake.capped").status == "skipped"


def test_the_cap_works_through_the_executors_perform(env, fakes):
    """outputs._perform logs each run, so a capped action stops on its own there too, and the line is the reply's."""
    from mvp import texts as T
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
    got = [env["bot"]._perform(ctx_for(env, t0 + timedelta(minutes=i)), [("fake.capped", {})])[0][1]
           for i in range(3)]
    assert [o.status for o in got] == ["done", "done", "skipped"] and got[2].line == T.over_action_cap(None, 2)
    rows = env["bot"].store.q("SELECT status FROM action_log WHERE action='fake.capped' ORDER BY id")
    assert [r["status"] for r in rows] == ["done", "done", "skipped"]


def test_all_outside_actions_together_stop_at_the_outside_cap(env, fakes, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OUTSIDE_WRITES_PER_DAY", 3)
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
    assert [run_logged(env, ctx_for(env, t0), n).status for n in ("fake.out_a", "fake.out_b", "fake.out_a")] == \
        ["done"] * 3
    assert run_logged(env, ctx_for(env, t0), "fake.out_b").status == "skipped"
    assert run_logged(env, ctx_for(env, t0), "fake.plain").status == "done"         # not an outside action
    assert run_logged(env, ctx_for(env, t0 + timedelta(days=1)), "fake.out_b").status == "done"
    assert config.OUTSIDE_WRITES_PER_DAY == 3 and importlib.import_module("mvp.config").OUTSIDE_WRITES_PER_DAY == 3


def test_an_action_with_no_cap_never_reads_the_log(env, fakes, monkeypatch):
    """Today's actions (and any with no cap and not outside) run exactly as before: no count is read."""
    store = env["bot"].store

    def boom(*a, **k):
        raise AssertionError("the cap was read")
    monkeypatch.setattr(store, "actions_in", boom)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    a = ask_pasta()
    a["spec"]["do"] = ["todo.add", "calendar.add"]
    say(env, "a pasta recipe on my list", a)
    acts = {r["action"]: r["status"] for r in store.q("SELECT action, status FROM action_log")}
    assert acts.get("todo.add") == "done" and "calendar.add" in acts
    assert run_logged(env, ctx_for(env, datetime(2026, 11, 12, 14, 0, tzinfo=UTC)), "fake.plain").status == "done"


# ---------- the yes token of the exact text ----------
def test_a_send_word_action_runs_only_with_the_token_of_the_exact_text(env, fakes):
    from mvp.actions import Refused, make_yes_token, perform, text_hash
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
    ctx = ctx_for(env, t0, request=TEXT)
    with pytest.raises(Refused):
        perform("fake.send", ctx)                                         # no token
    with pytest.raises(Refused):
        perform("fake.send", ctx, yes_token="")                           # an empty one
    with pytest.raises(Refused):
        perform("fake.send", ctx, yes_token="abc")                        # a wrong one
    with pytest.raises(Refused):                                          # the token of a version one comma apart
        perform("fake.send", ctx, yes_token=make_yes_token("draft-1", 1, text_hash(TEXT.replace(",", ""))))
    with pytest.raises(Refused):                                          # of an earlier version
        perform("fake.send", ctx, yes_token=make_yes_token("draft-1", 0, text_hash(TEXT)))
    assert fakes["ran"] == []
    o = perform("fake.send", ctx, yes_token=make_yes_token("draft-1", 1, text_hash(TEXT)))
    assert o.status == "done" and len(fakes["ran"]) == 1
    # a send_word action whose module cannot make the token never runs, whatever token is given
    with pytest.raises(Refused):
        perform("fake.send_nomod", ctx, yes_token=make_yes_token("draft-1", 1, text_hash(TEXT)))
    assert len(fakes["ran"]) == 1


def test_a_refused_send_through_the_executor_is_a_failure_and_sends_nothing(env, fakes):
    t0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
    (name, o), = env["bot"]._perform(ctx_for(env, t0, request=TEXT), [("fake.send", {})])
    assert name == "fake.send" and o.status == "failed" and fakes["ran"] == []
    assert o.detail == {"error": "Refused"}


def test_the_token_changes_with_any_part():
    from mvp.actions import make_yes_token, text_hash
    t = make_yes_token("d", 1, text_hash("a"))
    assert t == make_yes_token("d", 1, text_hash("a")) and len(t) == 64
    assert len({t, make_yes_token("d", 2, text_hash("a")), make_yes_token("e", 1, text_hash("a")),
                make_yes_token("d", 1, text_hash("a ")), make_yes_token("d1", "", text_hash("a"))}) == 5
    assert make_yes_token("ab", "c") != make_yes_token("a", "bc")          # parts are kept apart


# ---------- the operator ----------
def test_no_operator_when_the_setting_is_unset(env, fakes, monkeypatch):
    from mvp import config
    from mvp.actions import Refused, perform
    monkeypatch.setattr(config, "OPERATOR", None)
    for h in (H, "+15550002", "me@example.com", "", None, "None"):
        assert config.is_operator(h) is False
    with pytest.raises(Refused):
        perform("fake.mine", ctx_for(env, datetime(2026, 11, 12, 14, 0, tzinfo=UTC)))
    monkeypatch.setattr(config, "OPERATOR", "")
    assert config.is_operator(H) is False and config.is_operator("") is False
    assert fakes["ran"] == []


def test_the_operator_setting_names_one_handle_in_any_spelling(env, fakes, monkeypatch):
    from mvp import config
    from mvp.actions import Refused, perform
    monkeypatch.setattr(config, "OPERATOR", H)
    assert config.is_operator(H) and not config.is_operator("+15550002")
    assert perform("fake.mine", ctx_for(env, datetime(2026, 11, 12, 14, 0, tzinfo=UTC))).status == "done"
    monkeypatch.setattr(config, "OPERATOR", "(415) 555-0100")
    assert config.is_operator("+14155550100") and config.is_operator("4155550100")
    assert not config.is_operator("+14155550101")
    with pytest.raises(Refused):
        perform("fake.mine", ctx_for(env, datetime(2026, 11, 12, 14, 0, tzinfo=UTC)))
    monkeypatch.setattr(config, "OPERATOR", "Me@Example.com")
    assert config.is_operator("me@example.com") and not config.is_operator("you@example.com")


def test_the_operator_comes_from_the_environment(monkeypatch):
    import mvp.config as config
    try:
        monkeypatch.setenv("MVP_OPERATOR", "+14155550100")
        importlib.reload(config)
        assert config.OPERATOR == "+14155550100" and config.is_operator("+14155550100")
        monkeypatch.setenv("MVP_OPERATOR", "")
        importlib.reload(config)
        assert config.OPERATOR is None and not config.is_operator("+14155550100")
        monkeypatch.delenv("MVP_OPERATOR")
        importlib.reload(config)
        assert config.OPERATOR is None and config.OUTSIDE_WRITES_PER_DAY == 40
    finally:
        monkeypatch.delenv("MVP_OPERATOR", raising=False)
        importlib.reload(config)


# ---------- the stubs other slices import before their owners merge ----------
def test_the_published_entry_points_import_and_do_nothing():
    from mvp import cancel, drafts
    # round 9, slice A replaced the drafts stub: the entry points take the bot first (tests/test_round9_drafts.py)
    assert callable(drafts.start) and callable(drafts.open_draft) and callable(drafts.from_todo)
    # slice B built cancel.from_todo (test_round9_cancel.py): a to-do that is not a cancel is still not handled there
    assert cancel.from_todo({"handle": H}, {"text": "Buy milk"}, None) is None


# ---------- the round 9 merge: importing mvp/llm.py again never chains its ledger wrapper ----------
def test_importing_llm_again_wraps_ai_log_once_and_writes_one_row(tmp_path, monkeypatch):
    import mvp.llm  # noqa: F401 - the module as the rest of the suite holds it
    ai = sys.modules["ai"]
    for name in ("_log", "DATA", "LEDGER", "TIMEOUT"):   # put back after the test
        monkeypatch.setattr(ai, name, getattr(ai, name))
    monkeypatch.setitem(sys.modules, "mvp.llm", sys.modules["mvp.llm"])
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path))
    for _ in range(5):
        del sys.modules["mvp.llm"]
        llm = importlib.import_module("mvp.llm")
    assert ai._log is llm._log
    under = llm._orig_log
    assert getattr(under, "__module__", None) == "ai" and not hasattr(under, "_mvp_orig")
    ai._log({"provider": "test", "purpose": "merge", "cost_usd": 0.0})
    rows = (tmp_path / "ai_runs.jsonl").read_text().splitlines()
    assert len(rows) == 1
