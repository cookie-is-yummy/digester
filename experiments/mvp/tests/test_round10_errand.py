"""Round 10, slice W7 (DESIGN.md section 17.W): the errand form. The model is faked (purpose mvp_errand); every test
checks what code does with the form: the checks, the helper it reaches, and that the interpreter's answer stands when
the form is "none" or fails a check. Synthetic data only: made-up names and example.com addresses."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

UNSUP = {"intent": "unsupported", "reply": "I can't do that."}
CHAT = {"intent": "chat", "reply": "Sure thing!"}


@pytest.fixture()
def e(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "DRAFT_MODEL", False, raising=False)
    for k in ("MVP_SMTP_HOST", "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_OPERATOR", "MVP_ERRAND_PER_DAY"):
        monkeypatch.delenv(k, raising=False)
    env["bot"].max_per_minute = None
    env["errand_users"] = []
    return env


def form(e, f):
    """The fake errand model answers `f` (a dict) and records what it was sent."""
    def answer(user):
        e["errand_users"].append(user)
        return dict(f)
    e["state"]["answers"]["mvp_errand"] = answer


def replies(e, n0):
    return [t for _, _, t in e["ch"].outbox[n0:]]


def n_errand(e):
    return e["calls"].count("mvp_errand")


# ---------- when it runs ----------
def test_wanted():
    from mvp.errand import wanted
    from mvp.schema import Interpretation as I
    un = I(intent="unsupported", reply="x")
    assert wanted(un, "escríbele a mi jefe que llego tarde")
    assert not wanted(un, "every friday email my landlord the rent reminder")      # W-3: a rule, never the errand
    assert not wanted(un, "cada domingo pon las recetas en mi ticktick")
    assert not wanted(un, "x" * 401)
    assert not wanted(I(intent="chat", reply="hi"), "thanks")
    assert wanted(I(intent="chat", reply="hi"), "dale, envíalo")
    assert not wanted(I(intent="help"), "help me please")
    assert wanted(I(intent="help"), "qué hiciste?")
    assert not wanted(I(intent="ask", spec={"when": {"type": "now"}, "content": {"goal": "pasta", "searches": ["pasta"]}}),
                      "pasta")


def test_a_message_code_reads_never_reaches_the_errand(e):
    form(e, {"errand": "cancel", "merchant_words": "netflix"})
    say(e, "cancel my netflix", UNSUP)
    assert n_errand(e) == 0


def test_none_leaves_the_interpreters_answer(e):
    from mvp import texts as T
    form(e, {"errand": "none"})
    out = say(e, "can you do my taxes", UNSUP)
    assert n_errand(e) == 1 and out == T.unsupported_reply("can you do my taxes", "I can't do that.")


def test_the_input_is_the_state_word_and_the_message_only(e):
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())
    form(e, {"errand": "none"})
    say(e, "pon el primero en mi todoist", UNSUP)
    u = e["errand_users"][-1]
    assert u == "<state>answer 1</state>\n<message>pon el primero en mi todoist</message>"
    assert "Lemon" not in u and "garlic" not in u


def test_the_daily_cap(e, monkeypatch):
    monkeypatch.setenv("MVP_ERRAND_PER_DAY", "1")
    form(e, {"errand": "none"})
    say(e, "can you do my taxes", UNSUP)
    say(e, "can you walk my dog", UNSUP)
    assert n_errand(e) == 1


def test_the_same_message_is_cached(e):
    form(e, {"errand": "none"})
    say(e, "can you do my taxes", UNSUP)
    say(e, "can you do my taxes", UNSUP)
    assert n_errand(e) == 1


# ---------- email to someone else ----------
def test_spanish_email_to_my_boss_makes_the_card(e):
    form(e, {"errand": "email_other", "to_words": "mi jefe", "say_words": "llego tarde"})
    out = say(e, "escríbele un email a mi jefe que llego tarde", UNSUP)
    assert out.startswith("Who should it go to? Reply with your boss's email address")
    d = e["bot"].open_draft(H)
    assert d and d["parts"]["request"] == "Llego tarde."


@pytest.mark.parametrize("f", [
    {"errand": "email_other", "to_words": "my landlord", "say_words": "the sink is broken"},          # not in the message
    {"errand": "email_other", "to_words": "mi jefe"},
])
def test_an_email_form_with_words_not_in_the_message_is_refused(e, f):
    form(e, f)
    say(e, "escríbele un email a mi jefe que llego tarde", UNSUP)
    assert e["bot"].open_draft(H) is None


def test_an_address_the_message_does_not_hold_is_never_used(e):
    form(e, {"errand": "email_other", "to_words": "mi jefe", "address": "boss@example.com", "say_words": "llego tarde"})
    out = say(e, "escríbele un email a mi jefe que llego tarde", UNSUP)
    d = e["bot"].open_draft(H)
    assert d and d["to_addr"] is None and out.startswith("Who should it go to?")


def test_an_address_typed_in_the_message_is_kept(e):
    form(e, {"errand": "email_other", "to_words": "ana", "address": "ana@example.com", "say_words": "llego tarde"})
    say(e, "manda a ana (ana@example.com) que llego tarde", UNSUP)
    d = e["bot"].open_draft(H)
    assert d and d["to_addr"] == "ana@example.com"


# ---------- the draft ----------
def _draft(e):
    say(e, "email sam@example.com that the meeting moved to wednesday", UNSUP)
    assert e["bot"].open_draft(H)


def test_send_draft_never_sends(e, monkeypatch):
    from mvp import texts as T
    _draft(e)
    form(e, {"errand": "send_draft"})
    out = say(e, "dale, envíalo ya mismo", CHAT)
    assert out == T.DRAFT_SEND_LINK
    assert e["bot"].store.get_state(f"sendhold:{H}") is None
    assert e["bot"].store.q("SELECT count(*) n FROM outbox")[0]["n"] == 0


def test_change_draft_replace_only_where_the_draft_holds_the_words(e):
    _draft(e)
    form(e, {"errand": "change_draft", "change": "replace", "old_words": "wednesday", "new_words": "jueves"})
    say(e, "pon jueves en vez de wednesday", CHAT)
    assert "jueves" in e["bot"].open_draft(H)["body"]


def test_change_draft_with_old_words_not_in_the_draft_is_refused(e):
    _draft(e)
    v = e["bot"].open_draft(H)["version"]
    form(e, {"errand": "change_draft", "change": "replace", "old_words": "friday", "new_words": "jueves"})
    say(e, "pon jueves en vez de friday", CHAT)
    assert e["bot"].open_draft(H)["version"] == v


def test_email_self_draft(e):
    _draft(e)
    form(e, {"errand": "email_self", "what": "draft"})
    out = say(e, "mándamelo a mí", UNSUP)
    assert "email to yourself" in out or "Here's the draft as an email to yourself" in "\n".join(e["ch"].outbox[-1])


# ---------- cancel, to-dos, connections ----------
def test_spanish_cancel_reaches_the_cancel_helper(e):
    form(e, {"errand": "cancel", "merchant_words": "netflix"})
    out = say(e, "quiero cancelar mi suscripción de netflix", UNSUP)
    assert "Netflix" in out


def test_a_merchant_not_in_the_message_is_refused(e):
    form(e, {"errand": "cancel", "merchant_words": "spotify"})
    out = say(e, "quiero cancelar mi suscripción de netflix", UNSUP)
    assert "Spotify" not in out


def test_do_todo_by_number_and_never_ticks_off(e):
    for t in ("Email landlord about the sink", "Cancel Netflix", "Buy basil"):
        e["bot"].store.add_todo(H, t, at=e["clock"][0])
    say(e, "my list", {"intent": "todo_list"})
    form(e, {"errand": "do_todo", "todo": 2})
    n0 = len(e["ch"].outbox)
    say(e, "hazme la segunda", UNSUP)
    assert "Netflix" in "\n".join(replies(e, n0))
    assert len(e["bot"].store.todos(H)) == 3


def test_app_connection(e):
    form(e, {"errand": "app_connection", "op": "connect", "app_words": "google calendar"})
    out = say(e, "conecta mi google calendar", UNSUP)
    assert out.startswith("I can't connect to Google Calendar yet.")


def test_an_app_not_in_the_message_is_refused(e):
    form(e, {"errand": "app_connection", "op": "connect", "app_words": "todoist"})
    out = say(e, "conecta mi google calendar", UNSUP)
    assert "Todoist" not in out


def test_what_did_you_do(e):
    form(e, {"errand": "what_did_you_do"})
    out = say(e, "qué hiciste?", CHAT)
    assert out != "Sure thing!"


def test_a_form_never_makes_a_rule(e):
    form(e, {"errand": "new_rule", "text": "x"})
    say(e, "pon algo raro", UNSUP)
    assert not e["bot"].store.rules(H)


# ---------- a number is used only when the message says it (live: "ese restaurante" read as pick 5) ----------
@pytest.mark.parametrize("n,text,ok", [(2, "la segunda", True), (2, "the 2nd one", True), (2, "number 2", True),
                                       (5, "ese restaurante", False), (1, "the first one", True), (3, "dos", False)])
def test_said_number(n, text, ok):
    from mvp.errand import said_number
    assert said_number(n, text) is ok


def test_a_post_act_pick_the_message_never_said_is_not_used(e, tmp_path):
    from mvp.tests.test_round10_wording import POSTS
    from mvp.tests.test_round9_postacts import seed
    seed(e, tmp_path, POSTS)
    form(e, {"errand": "post_act", "act": "book", "pick": 3})
    out = say(e, "resérvame en ese restaurante para el sábado", UNSUP)
    assert out.startswith("I can't book") and "Tacos El Gordo" in out.split("\n")[0]   # "that one": the restaurant


def test_post_act_target_words_then_the_pointer(e, tmp_path):
    from mvp.tests.test_round10_wording import POSTS
    from mvp.tests.test_round9_postacts import seed
    seed(e, tmp_path, POSTS)
    form(e, {"errand": "post_act", "act": "book", "target_words": "ese restaurante para el sábado"})
    out = say(e, "resérvame en ese restaurante para el sábado", UNSUP)
    assert out.startswith("I can't book") and "Tacos El Gordo" in out.split("\n")[0]


def test_a_chat_about_the_bots_insides_tries_the_errand_first(e):
    form(e, {"errand": "what_did_you_do"})
    out = say(e, "what did you do", {"intent": "chat", "reply": "I turned your message into structured JSON."})
    assert "JSON" not in out and out != "<<x>>"


def test_a_todo_done_clash_reaches_the_errand_and_never_ticks_off(e):
    for t in ("Email landlord about the sink", "Cancel Netflix", "Buy basil"):
        e["bot"].store.add_todo(H, t, at=e["clock"][0])
    say(e, "my list", {"intent": "todo_list"})
    form(e, {"errand": "do_todo", "todo": 2})
    n0 = len(e["ch"].outbox)
    say(e, "haz la segunda", {"intent": "todo_done", "todo_number": 2})
    assert "Netflix" in "\n".join(replies(e, n0)) and len(e["bot"].store.todos(H)) == 3


def test_delete_my_data_removes_the_errand_cache_and_the_export_steps_mark(e):
    form(e, {"errand": "none"})
    say(e, "can you do my taxes", UNSUP)
    say(e, "can you sync my saves", UNSUP)
    keys = [r["key"] for r in e["bot"].store.q("SELECT key FROM state")]
    assert any(k.startswith("errandc:") and k.endswith(":" + H) for k in keys)
    assert f"exportsteps:{H}" in keys
    rows = e["bot"].store.q("SELECT detail FROM action_log WHERE action='errand.form'")
    assert rows and "taxes" not in rows[0]["detail"]   # the name and the state word only, never the message
    say(e, "delete my data", {"intent": "delete_data"})
    e["bot"].on_message(H, "YES")
    keys = [r["key"] for r in e["bot"].store.q("SELECT key FROM state")]
    assert not any(k.endswith(":" + H) and (k.startswith("errandc:") or k.startswith("exportsteps:")) for k in keys)


def test_off_when_the_daily_number_is_zero(e, monkeypatch):
    monkeypatch.setenv("MVP_ERRAND_PER_DAY", "0")
    form(e, {"errand": "cancel", "merchant_words": "netflix"})
    say(e, "quiero cancelar mi suscripción de netflix", UNSUP)
    assert n_errand(e) == 0
