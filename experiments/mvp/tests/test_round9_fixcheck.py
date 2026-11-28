"""Offline tests for the check of the round 9 live fix pass (DESIGN.md section 12, "Round 9, live fix (kinds)", its
check; section 16.H, its check): each test below failed on the merged tree before its fix; the near-variants hold
either way. Synthetic posts with made-up names, example.com addresses, the fakes of test_mvp (model, search pool,
clock), a fake draft model and fake SMTP and IMAP servers."""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round9_drafts import CHAT, card, d, draft_row, link_of, m, model, one_pick  # noqa: E402,F401
from mvp.tests.test_round9_mailbox import FakeIMAP, FakeMailSMTP, box, draft, op, sends, tick_at  # noqa: E402,F401
from mvp.tests.test_round9_postacts import seed, tell  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402


def runs(e):
    return e["bot"].store.q("SELECT * FROM runs WHERE handle=? ORDER BY id", (H,))


# =====================================================================================================================
# 103, check 1: a Spanish request for a kind of thing. The interpreter keeps the person's language in the goal and the
# searches ("herramientas de IA para un proyecto"), so the English word list found no kind: no search of the kind
# phrase, and a purpose stayed a must-have
# =====================================================================================================================
@pytest.mark.parametrize("goal,text,kind", [
    ("herramientas de IA para un proyecto", "cuáles son algunas herramientas de IA que debería usar para mi próximo "
                                            "proyecto", "herramientas de IA"),
    ("herramientas de IA", "cuáles son algunas herramientas de IA", "herramientas de IA"),
    ("librerías de uiux", "qué librerías de uiux debería usar para mi próximo proyecto", "librerías de UI/UX"),
    ("cursos de diseño gratis", "cursos de diseño gratis", "cursos de diseño"),
    ("canales de gamedev", "qué canales de gamedev debería seguir", "canales de gamedev"),
])
def test_fx_a_spanish_kind_request_has_its_kind(goal, text, kind):
    from mvp.extract import kind_request
    assert kind_request(goal, text) == kind


@pytest.mark.parametrize("goal,text", [
    ("recetas de pollo", "recetas de pollo fáciles"),
    ("rutinas de ejercicio", "rutinas de ejercicio para principiantes"),
    ("tutoriales de blender", "tutoriales de blender"),
    ("apps de recetas", "apps de recetas"),               # a recipe word: never a kind request, as "recipe apps"
    ("ejercicios de yoga", "qué ejercicios de yoga guardé"),
])
def test_fx_near_variant_a_spanish_recipe_workout_or_tutorial_is_never_a_kind_request(goal, text):
    from mvp.extract import kind_request
    assert kind_request(goal, text) is None


def test_fx_near_variant_english_kind_requests_read_as_before():
    from mvp.extract import kind_request
    assert kind_request("uiux libraries", "what are some uiux libraries i should use for my next project") == \
        "UI/UX libraries"
    assert kind_request("design tools", "what design tools should i use for my portfolio") == "design tools"
    assert kind_request("chicken recipes", "what are some chicken recipes") is None
    assert kind_request("recipe apps", "recipe apps i saved") is None
    assert kind_request("python tutorials", "what are some good python tutorials") is None


@pytest.mark.parametrize("criterion", ["para mi próximo proyecto", "para un proyecto", "para principiantes",
                                       "que debería usar", "que debería usar para mi próximo proyecto",
                                       "i should read", "i could follow", "that i should watch for my next project"])
def test_fx_a_purpose_in_spanish_or_with_another_verb_is_a_purpose(criterion):
    from mvp.extract import purpose_only
    assert purpose_only(criterion)


@pytest.mark.parametrize("criterion", ["para android", "gratis", "para niños", "en español", "for kids",
                                       "i should read before bed", "con modo oscuro"])
def test_fx_near_variant_a_real_must_have_stays(criterion):
    from mvp.extract import purpose_only
    assert not purpose_only(criterion)


TOOLS = "Mis herramientas de IA favoritas\n1. Lumo - escribe por ti\n2. Pindo - resume videos\n3. Tarra - hace slides"
NOTES = "Notas de clase\nMi forma de estudiar\n- repasar\n- resumir"
ES_ROWS = [("t1", "iafan", TOOLS, "2026-09-01", "2026-09-02", "instagram"),
           ("n1", "studyfan", NOTES, "2026-08-01", "2026-08-02", "instagram")]


@pytest.fixture()
def es_lib(env, tmp_path):
    use_lib(env, tmp_path, ES_ROWS, name="libfxes")
    env["state"]["composed"] = []

    def compose(u):
        env["state"]["composed"].append(u)
        return {"picks": [pick(u, "Mis herramientas de IA", title="Herramientas de IA")]}
    env["state"]["answers"]["mvp_compose"] = compose
    env["state"]["answers"]["mvp_extract"] = items_fake({"Mis herramientas de IA": {"items": [
        {"name": n, "about": "", "fit": "yes"} for n in ("Lumo", "Pindo", "Tarra")]}})
    return env


def test_fx_a_spanish_long_wording_searches_the_kind_and_leaves_its_purpose_out(es_lib):
    say(es_lib, "cuáles son algunas herramientas de IA que debería usar para mi próximo proyecto",
        ask("herramientas de IA para un proyecto", ["herramientas de IA para proyecto", "IA para mi próximo proyecto"],
            criteria=["para mi próximo proyecto"]))
    assert es_lib["bot"].pool.queries[-1] == "herramientas de IA"
    steps = json.loads(runs(es_lib)[-1]["steps"])
    assert steps["kind_search"] == 1 and steps["purpose_left_out"] == 1
    assert '"para mi próximo proyecto"' not in es_lib["state"]["composed"][-1]


def test_fx_near_variant_a_spanish_short_wording_that_says_the_kind_adds_no_search(es_lib):
    n = len(es_lib["bot"].pool.queries)
    say(es_lib, "cuáles son algunas herramientas de IA", ask("herramientas de IA", ["herramientas de IA", "IA tools"]))
    assert es_lib["bot"].pool.queries[n:] == ["herramientas de IA", "IA tools"]
    assert "kind_search" not in json.loads(runs(es_lib)[-1]["steps"])


def test_fx_near_variant_a_spanish_recipe_request_keeps_its_searches_and_must_haves(es_lib):
    n = len(es_lib["bot"].pool.queries)
    say(es_lib, "recetas de pollo para principiantes", ask("recetas de pollo", ["recetas de pollo fáciles"],
                                                           criteria=["para principiantes"]))
    assert es_lib["bot"].pool.queries[n:] == ["recetas de pollo fáciles"]
    assert "purpose_left_out" not in json.loads(runs(es_lib)[-1]["steps"])


# =====================================================================================================================
# 103, check 2: the read step's run-together spelling knew only UI/UX (render.spelled). "gamedev channels" left a
# list that says "Game dev channels" unread, the same way "uiux" did before the fix ("channels" is not a topic word)
# =====================================================================================================================
GAME = "Game dev channels to follow\n1. Pixelforge - engine deep dives\n2. Tilesmith - level design\n3. Bytecraft"
PICKS = "Good habits for creators\n1. Post daily\n2. Reply to comments"
VIBES = "Studio vibes for a cosy desk\nSave this for later"
GAME_ROWS = [("p1", "habits", PICKS, "2026-09-01", "2026-09-02", "instagram"),
             ("v1", "vibes", VIBES, "2026-08-01", "2026-08-02", "instagram"),
             ("g1", "gamefan", GAME, "2026-07-01", "2026-07-02", "instagram")]


def _game(env, tmp_path, name):
    use_lib(env, tmp_path, GAME_ROWS, name=name)
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Good habits", title="Good habits"),
                                                                  pick(u, "Studio vibes", "close", title="Vibes")]}
    env["state"]["answers"]["mvp_extract"] = items_fake({
        "Good habits": {"items": [{"name": "Post daily", "about": "", "fit": "no"}]},
        "Game dev channels": {"items": [{"name": n, "about": "", "fit": "yes"}
                                        for n in ("Pixelforge", "Tilesmith", "Bytecraft")]}}, seen)
    return seen


def test_fx_a_run_together_word_of_any_topic_reads_the_post_that_spells_it_apart(env, tmp_path):
    seen = _game(env, tmp_path, "libfxg")
    msg = say(env, "what are some gamedev channels i should follow", ask("gamedev channels", ["gamedev channels"]))
    assert any("Game dev channels" in u for u in seen)
    assert "Pixelforge" in msg


@pytest.mark.parametrize("text,goal", [("what are some nocode channels", "nocode channels"),
                                       ("what are some cooking channels", "cooking channels")])
def test_fx_near_variant_a_post_on_another_topic_is_still_not_read(env, tmp_path, text, goal):
    seen = _game(env, tmp_path, "libfxg2")
    say(env, text, ask(goal, [goal]))
    assert not any("Game dev channels" in u for u in seen)


# =====================================================================================================================
# 104, check: the typed address after a title, a full name, or a lowercase name in brackets was not read: the address
# stayed in the email's words, To was empty, and the bot asked "Who should it go to?"
# =====================================================================================================================
@pytest.mark.parametrize("text,to,word,name", [
    ("email my boss Mr Smith at smith@example.com that i'm late", "smith@example.com", "boss", "Mr Smith"),
    ("email my boss mr. smith at smith@example.com that i'm late", "smith@example.com", "boss", "Mr. Smith"),
    ("email my teacher Ms Lee (lee@example.com) that i'm late", "lee@example.com", "teacher", "Ms Lee"),
    ("email my friend Maya Lopez maya@example.com that i'm late", "maya@example.com", "friend", "Maya Lopez"),
    ("email my friend maya lopez at maya@example.com that i'm late", "maya@example.com", "friend", "Maya Lopez"),
    ("email my friend maya (maya@example.com) that i'm late", "maya@example.com", "friend", "Maya"),
    ("email my friend: maya@example.com, that i'm late", "maya@example.com", "friend", None),
    ("email Dr. Ruiz at ruiz@example.com that i'm late", "ruiz@example.com", None, "Dr. Ruiz"),
])
def test_fx_the_typed_address_after_a_title_or_a_full_name_is_read(text, to, word, name):
    from mvp.drafts import email_request
    r = email_request(text)
    assert (r["to"], r.get("word"), r.get("name"), r["request"]) == (to, word, name, "I'm late.")


@pytest.mark.parametrize("text,words", [
    ("email my friend that maya@example.com is her new address", "Maya@example.com is her new address."),
    ("email my friend that i saw bob at bob@example.com", "I saw bob at bob@example.com."),
    ("email my friend Maya Saturday maya@example.com x", None),   # a day is never a second name
])
def test_fx_near_variant_an_address_inside_the_words_is_still_never_the_recipient(text, words):
    from mvp.drafts import email_request
    r = email_request(text)
    assert r["to"] is None and r["word"] == "friend"
    if words:
        assert r["request"] == words


def test_fx_the_founders_shape_with_a_full_name_is_a_card_end_to_end(d):
    say(d, "email my friend Maya Lopez maya@example.com that i can't make it on saturday and ask if sunday works", CHAT)
    c = card(d)
    assert c[0].split("\n")[1] == "To: maya@example.com" and c[1].startswith("Hi Maya Lopez,\n\n")
    assert "maya@example.com" not in c[1]


# =====================================================================================================================
# 105, check: a rewrite that came back the same while a send of those words waits in its hold kept the hold (right),
# but the reply said only "the email is the same as before": the person who asked for a change was not told that the
# same words still go at the set time
# =====================================================================================================================
SINK = {"subject": "The kitchen sink is broken", "greeting": "Hi,", "closing": "Thanks,",
        "body": "The kitchen sink is broken."}


def _held(op, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "DRAFT_MODEL", True)
    model(op, SINK)
    draft(op)
    say(op, "send", CHAT)
    return op["bot"].store.get_state(f"sendhold:{H}")


def test_fx_an_unchanged_rewrite_during_a_hold_says_the_send_still_waits(op, monkeypatch):
    hold = _held(op, monkeypatch)
    msg = say(op, "make it friendlier", CHAT)
    assert msg.startswith("I couldn't make it friendlier without adding things you didn't say")
    assert msg.endswith("It's already waiting to go at 1:02 pm. Reply \"undo\" to stop it.")
    assert op["bot"].store.get_state(f"sendhold:{H}") == hold          # the hold is kept: the words did not change
    tick_at(op, 3)
    assert len(sends()) == 1


def test_fx_an_unchanged_code_change_during_a_hold_says_so_too(op, monkeypatch):
    hold = _held(op, monkeypatch)
    msg = say(op, "say the kitchen sink is broken instead", CHAT)
    assert msg == ("That's already how the email reads, so nothing changed. It's already waiting to go at 1:02 pm. "
                   "Reply \"undo\" to stop it.")
    assert op["bot"].store.get_state(f"sendhold:{H}") == hold


def test_fx_near_variant_without_a_hold_the_line_is_unchanged(m):
    model(m, SINK, SINK)
    say(m, "email maria@example.com that the kitchen sink is broken", CHAT)
    msg = say(m, "make it friendlier", CHAT)
    assert msg.endswith("Tell me the words to use, like: say \"hope you're well\", or instead say ...")


def test_fx_near_variant_a_real_change_during_a_hold_still_stops_it(op, monkeypatch):
    _held(op, monkeypatch)
    model(op, dict(SINK, body="The kitchen sink is broken. Could you take a look at it?"))
    n = len(op["ch"].outbox)
    say(op, "make it more formal", CHAT)
    assert op["ch"].outbox[n][2].startswith("That stopped the send I had waiting.")
    assert op["bot"].store.get_state(f"sendhold:{H}") is None


# =====================================================================================================================
# 107, check: with a card still open but a newer answer shown after it, "put this in my email" gave the old card's
# link; "this" is the newest thing shown (before finding 107's fix it went the answer's way, as here)
# =====================================================================================================================
SAVE_LINE = "I can't save it in your mail myself."


def test_fx_put_this_in_my_email_after_a_newer_answer_is_not_the_old_card(d):
    say(d, "email maria@example.com that the kitchen sink is broken", CHAT)
    one_pick(d)
    n = len(d["ch"].outbox)
    say(d, "put this in my email", {"intent": "act_on_last", "actions": ["email.send"]})
    assert not any(t.startswith(SAVE_LINE) for _, _, t in d["ch"].outbox[n:])
    assert any(c == "mvp_interpret" for c in d["calls"][-3:])


@pytest.mark.parametrize("text", ["put this in my email", "put it in my drafts"])
def test_fx_near_variant_with_the_card_newest_it_is_the_card(d, text):
    say(d, "email maria@example.com that the kitchen sink is broken", CHAT)
    assert say(d, text, CHAT).startswith(SAVE_LINE)


def test_fx_near_variant_the_word_draft_still_means_the_card_after_a_newer_answer(d):
    say(d, "email maria@example.com that the kitchen sink is broken", CHAT)
    one_pick(d)
    assert say(d, "save it as a draft", CHAT).startswith(SAVE_LINE)


# =====================================================================================================================
# 108, check: the apply menu's last line asks for the date, but "none", a number past the list or one already done
# ended the date question: "dec 5" next went to the model
# =====================================================================================================================
PLAIN = ("h1", "harborclub", "Harbor Youth Fellowship\nA summer programme for students who love the sea.", "2026-10-05",
         "Harbor Youth Fellowship")
WITH_LIST = ("h1", "harborclub", "Harbor Youth Fellowship\nRequirements:\n- transcript\n- short essay\n\nGood luck!",
             "2026-10-05", "Harbor Youth Fellowship")
REMINDED = "OK. I'll remind you about Harbor Youth Fellowship on Wednesday 2 December at 9am"


@pytest.mark.parametrize("post,first", [(PLAIN, "none"), (WITH_LIST, "no thanks"), (PLAIN, "2"), (WITH_LIST, "3")])
def test_fx_after_none_or_a_number_past_the_menu_the_date_still_answers(env, tmp_path, post, first):
    seed(env, tmp_path, [post])
    tell(env, "apply to the first one")
    tell(env, first)
    assert tell(env, "dec 5").startswith(REMINDED)
    assert len(env["bot"].store.rules(H)) == 1


def test_fx_after_a_number_already_done_the_date_still_answers(env, tmp_path):
    seed(env, tmp_path, [WITH_LIST])
    tell(env, "apply to the first one")
    tell(env, "1")
    assert tell(env, "1") == "I've done that one already. Tell me what else you'd like."
    assert tell(env, "dec 5").startswith(REMINDED)


def test_fx_near_variant_after_none_another_message_ends_the_question(env, tmp_path):
    seed(env, tmp_path, [PLAIN])
    tell(env, "apply to the first one")
    tell(env, "none")
    say(env, "whats on my list", {"intent": "todo_list"})
    n = len(env["calls"])
    say(env, "dec 5", CHAT)
    assert len(env["calls"]) == n + 1 and env["bot"].store.rules(H) == []   # the model's, not the date question's


def test_fx_near_variant_a_dated_post_has_no_date_question_to_keep(env, tmp_path):
    cap = "Harbor Youth Fellowship\nApplications close 30 November 2026."
    seed(env, tmp_path, [("h1", "harborclub", cap, "2026-10-05", "Harbor Youth Fellowship")])
    tell(env, "apply to it")
    tell(env, "none")
    assert env["bot"].store.get_state(f"deadline_ask:{H}") is None


# =====================================================================================================================
# 106, check: a brief that says its own claim is untrue. draft_v2 wrote "the report is done. I sent it yesterday." for
# "email my boss that the report is done even though it isn't, say i sent it yesterday" (live, 1 of 3 lie briefs; the
# other two left the made-up parts out, as the prompt asks). Code now writes no card for it
# =====================================================================================================================
NOT_TRUE = ("I can't write something you've told me isn't true, so I didn't write this one. Tell me what you'd like to "
            "say instead, like: email my boss that I need one more day.")


@pytest.mark.parametrize("text", [
    "email my boss that the report is done even though it isn't, say i sent it yesterday",
    "email my boss at boss@example.com that i finished even though i didn't",
    "email my teacher and pretend i was sick",
    "email sam@example.com that the rent was paid even though it wasn't.",
])
def test_fx_a_brief_that_says_its_claim_is_untrue_gets_no_card(m, text):
    model(m, {"subject": "Report", "greeting": "Hello,", "closing": "Best,", "body": "The report is done."})
    n = len(m["ch"].outbox)
    assert say(m, text, CHAT) == NOT_TRUE
    assert len(m["ch"].outbox) == n + 1 and draft_row(m) is None
    assert not any(c == "draft" for c in m["calls"])


@pytest.mark.parametrize("text", [
    "email my landlord at bob@example.com that the heater broke even though it wasn't my fault",
    "email my friend at sam@example.com that even though it isn't sunny we should go",
    "email my professor at lin@example.com and make up a good excuse for missing class",   # the prompt leaves it out
    "email my friend at sam@example.com that we should pretend we're pirates at the party",
])
def test_fx_near_variant_a_real_statement_still_gets_its_card(d, text):
    say(d, text, CHAT)
    assert card(d)[0].startswith("Here's the email. Nothing has been sent.")
