"""Offline tests for the round 9 live fix pass, group A (DESIGN.md section 16.H): findings 104 to 108 from the main
agent's live check of the merged build. Synthetic data only (made-up names, example.com addresses), the fakes of
test_mvp (model, search pool, clock: Thursday 12 Nov 2026, New York), a fake draft model and a fake IMAP server."""
import json
import os
import sys
from email import message_from_bytes, policy

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round9_drafts import (CHAT, GOOD, HEAD, NEW, card, d, draft_calls, draft_row,  # noqa: E402,F401
                                          link_of, m, model, one_pick, parse_mailto)
from mvp.tests.test_round9_mailbox import FakeIMAP, appended, box, op  # noqa: E402,F401
from mvp.tests.test_round9_postacts import seed, tell  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402


def boom(u):
    raise AssertionError("the model was called")


def calls(e):
    return len(e["calls"])


def outbox_since(e, n):
    return [t for _, _, t in e["ch"].outbox[n:]]


# =====================================================================================================================
# 104: an address the person typed right after the role word (or the name) is the recipient
# =====================================================================================================================
@pytest.mark.parametrize("text,to,word,name", [
    ("email my friend maya@example.com that i can't make it on saturday", "maya@example.com", "friend", None),
    ("email maya@example.com that i can't make it on saturday", "maya@example.com", None, None),
    ("email my landlord (bob@example.com) that the heating is broken", "bob@example.com", "landlord", None),
    ("email my landlord <bob@example.com> that the heating is broken", "bob@example.com", "landlord", None),
    ("email my sister, ana@example.com, that dinner is at 7", "ana@example.com", "sister", None),
    ("email my friend Maya at maya@example.com that i'm late", "maya@example.com", "friend", "Maya"),
    ("email my friend maya at maya@example.com that i'm late", "maya@example.com", "friend", "Maya"),
    ("email my friend Maya maya@example.com that i'm late", "maya@example.com", "friend", "Maya"),
    ("email Maya (maya@example.com) that i'm late", "maya@example.com", None, "Maya"),
    ("send maya@example.com an email saying i'm late", "maya@example.com", None, None),
    ("send my landlord bob@example.com an email that the heating is broken", "bob@example.com", "landlord", None),
    ("please shoot my coach an email about practice", None, "coach", None),
])
def test_104_the_typed_address_after_the_role_word_is_read(text, to, word, name):
    from mvp.drafts import email_request
    r = email_request(text)
    assert r is not None and (r["to"], r.get("word"), r.get("name")) == (to, word, name)


@pytest.mark.parametrize("text", [
    "email my friend that maya@example.com is her new address",   # an address inside the words is not the recipient
    "email my friend about maya@example.com",
])
def test_104_an_address_inside_the_words_is_never_the_recipient(text):
    from mvp.drafts import email_request
    r = email_request(text)
    assert r is not None and r["to"] is None and r["word"] == "friend"


@pytest.mark.parametrize("text", ["send them an email saying hi", "send my mom an email with the recipe",
                                  "send the pasta an email", "send it to me as an email"])
def test_104_send_x_an_email_is_read_only_with_a_recipient_and_its_words(text):
    from mvp.drafts import email_request
    assert email_request(text) is None


def test_104_the_founders_case_is_a_card_with_the_typed_address_and_no_question(d):
    n = calls(d)
    say(d, "email my friend maya@example.com that i can't make it on saturday and ask if sunday works", boom)
    c = card(d)
    assert calls(d) == n and not any("Who should it go to" in x for x in c)
    assert c[0] == f"{HEAD}\nTo: maya@example.com\nSubject: I can't make it on saturday"
    # the statement, then the question as a question, in the person's own words (code-built, no model here)
    assert c[1] == "Hi,\n\nI can't make it on saturday. Can you let me know if sunday works?\n\nThanks,\nT"
    assert parse_mailto(link_of(c[2]))[0] == "maya@example.com"
    assert draft_row(d)["to_addr"] == "maya@example.com"


@pytest.mark.parametrize("text,to,greet", [
    ("email my landlord (bob@example.com) that the heating is broken", "bob@example.com", "Hi,"),
    ("email my friend Maya at maya@example.com that i'm running late", "maya@example.com", "Hi Maya,"),
    ("email my friend maya at maya@example.com that i'm running late", "maya@example.com", "Hi Maya,"),
    ("send maya@example.com an email saying i'm running late", "maya@example.com", "Hi,"),
])
def test_104_near_variants_end_to_end(d, text, to, greet):
    n = calls(d)
    say(d, text, boom)
    c = card(d)
    assert calls(d) == n and c[0].split("\n")[1] == f"To: {to}" and c[1].startswith(greet + "\n\n")


def test_104_email_this_to_my_sister_with_her_address(d):
    one_pick(d)
    n = calls(d)
    say(d, "email this to my sister ana@example.com", boom)
    c = card(d)
    assert calls(d) == n and c[0].split("\n")[1] == "To: ana@example.com" and "Lemon garlic pasta" in c[1]


def test_104_the_ask_and_split_keeps_the_old_shapes():
    from mvp.drafts import clause_paragraph
    assert clause_paragraph("that the sink is broken")[0] == "The sink is broken."
    assert clause_paragraph("and ask if she can come on Tuesday")[0] == "Can you let me know if you can come on Tuesday?"
    assert clause_paragraph("that the heating is broken again and ask when it can be fixed")[0] == \
        "The heating is broken again. Can you let me know when it can be fixed?"
    # "and" without an ask stays one sentence
    assert clause_paragraph("that the sink is broken and the tap leaks")[0] == "The sink is broken and the tap leaks."


def test_104_a_lone_role_word_still_asks_for_the_address(d):
    say(d, "email my landlord that the heating is broken", boom)
    assert last(d["ch"]).startswith("Who should it go to? Reply with your landlord's email address")


# =====================================================================================================================
# 105: a rewrite that comes back the same is said plainly, and is not a new version
# =====================================================================================================================
INTRO = {"subject": "Lemon garlic pasta", "greeting": "Hi,", "closing": "Thanks,",
         "body": "I saw this and thought of you."}


def _passed_on_post(m):
    one_pick(m)
    say(m, "email it to sam@example.com", CHAT)
    return draft_row(m)


@pytest.mark.parametrize("again", [
    INTRO,                                                        # the very same words
    dict(INTRO, body="I saw this and   thought of you.\n"),       # spacing aside, the same
])
def test_105_make_it_friendlier_with_the_same_words_is_not_a_new_version(m, again):
    model(m, INTRO, again)
    before = _passed_on_post(m)
    n = len(m["ch"].outbox)
    msg = say(m, "make it friendlier", CHAT)
    assert msg == ("I couldn't make it friendlier without adding things you didn't say, so the email is the same as "
                   "before. Tell me the words to use, like: say \"hope you're well\", or instead say ...")
    assert len(m["ch"].outbox) == n + 1 and not msg.startswith(NEW)          # one line, no card
    after = draft_row(m)
    assert (after["version"], after["text_hash"]) == (before["version"], before["text_hash"])
    assert json.loads(after["parts"]).get("changes", 0) == json.loads(before["parts"]).get("changes", 0)
    assert draft_calls(m) == 2


def test_105_a_rewrite_that_fails_its_checks_twice_says_so_in_the_tone_s_words(m):
    model(m, INTRO, dict(INTRO, body="I saw this and thought of you, Jordan."))
    before = _passed_on_post(m)
    msg = say(m, "make it more formal", CHAT)
    assert msg.startswith("I couldn't make it more formal without adding things you didn't say")
    assert draft_row(m)["version"] == before["version"] and draft_calls(m) == 3


def test_105_in_spanish_that_comes_back_the_same_says_put_it_in_spanish(m):
    model(m, INTRO, INTRO)
    _passed_on_post(m)
    assert say(m, "put it in spanish", CHAT).startswith("I couldn't put it in Spanish without adding things")


def test_105_a_failed_call_says_it_couldnt_just_now(m):
    model(m, INTRO, RuntimeError("timeout"))
    before = _passed_on_post(m)
    assert say(m, "make it friendlier", CHAT).startswith("I couldn't rewrite it just now, so the email is the same")
    assert draft_row(m)["version"] == before["version"]


def test_105_a_real_rewrite_is_still_the_new_version(m):
    model(m, INTRO, dict(INTRO, body="I saw this and thought of you. Hope you like it!"))
    before = _passed_on_post(m)
    say(m, "make it friendlier", CHAT)
    c = card(m)
    assert c[0].startswith(NEW) and "Hope you like it!" in c[1]
    assert draft_row(m)["version"] == before["version"] + 1


def test_105_with_the_model_off_the_fixed_line_stays(d):
    one_pick(d)
    say(d, "email it to sam@example.com", CHAT)
    assert say(d, "make it friendlier", CHAT).startswith("I can't rewrite it in a new tone yet.")


@pytest.mark.parametrize("body,kept", [
    ("Thanks for watering my plants.", "Thanks for watering my plants."),
    ("Thank you so much for everything you did.", "Thank you so much for everything you did."),
    ("I saw this and thought of you.\n\nThanks so much!", "I saw this and thought of you."),
    ("The sink is broken.\n\nBest wishes,", "The sink is broken."),
    ("Hi Sam,\nThe sink is broken.\nThanks,", "The sink is broken."),
])
def test_105_a_sentence_that_starts_with_thanks_is_the_email_not_a_sign_off(body, kept):
    # (found by the draft evaluation of this pass: "Thanks for watering my plants." was cut as a sign-off, and the
    # card showed an empty email)
    from mvp.drafts import clean_form
    assert clean_form({"body": body})["body"] == kept


def test_105_a_form_that_is_only_a_sign_off_is_retried_then_falls_back(m):
    seen = model(m, dict(GOOD, body="Thanks!"))
    say(m, "email maria@example.com that the kitchen sink is broken", CHAT)
    assert draft_calls(m) == 2 and "only a greeting or a sign-off" in seen[1]
    assert card(m)[1] == "Hi,\n\nThe kitchen sink is broken.\n\nThanks,\nT"


def test_105_a_thank_you_email_keeps_its_words(m):
    model(m, {"subject": "Thank you", "greeting": "Hi Sam,", "closing": "Best,",
              "body": "Thanks for watering my plants. I really appreciate it."})
    say(m, "email my neighbor Sam at sam@example.com to say thanks for watering my plants", CHAT)
    assert card(m)[1] == "Hi Sam,\n\nThanks for watering my plants. I really appreciate it.\n\nBest,\nT"


@pytest.mark.parametrize("first,second", [
    ("remove the link", "remove the link"),
    ("subject: Dinner", "subject: Dinner"),
    ("don't sign it", "don't sign it"),
])
def test_105_a_code_change_that_changes_nothing_is_not_a_new_version(d, first, second):
    one_pick(d)
    say(d, "email it to sam@example.com", CHAT)
    say(d, first, CHAT)
    assert card(d)[0].startswith(NEW)
    row = draft_row(d)
    n = len(d["ch"].outbox)
    assert say(d, second, CHAT) == "That's already how the email reads, so nothing changed."
    assert len(d["ch"].outbox) == n + 1
    again = draft_row(d)
    assert (again["version"], again["text_hash"]) == (row["version"], row["text_hash"])
    assert json.loads(again["parts"])["changes"] == json.loads(row["parts"])["changes"]


# =====================================================================================================================
# 106: draft_v2 writes a complete email; the checks are the same or stricter
# =====================================================================================================================
def test_106_config_points_at_draft_v2_and_v1_stays():
    from mvp import config, drafts
    assert config.PROMPT_DRAFT == "draft_v2"
    for v in ("draft_v1", "draft_v2"):
        assert os.path.exists(os.path.join(config.HERE, "prompts", f"{v}.md"))
    drafts._PROMPT.clear()
    text = drafts.PROMPT_TEXT()
    assert "2 to 5 short sentences" in text and "<post>" in text and "JSON only." in text


def test_106_the_model_call_is_logged_under_draft_v2(m):
    from mvp import llm
    seen = []
    real = llm.chat_json

    def spy(system, user, purpose, prompt_version, **kw):
        seen.append((purpose, prompt_version))
        return real(system, user, purpose, prompt_version, **kw)
    llm.chat_json = spy
    try:
        model(m, GOOD)
        say(m, "email maria@example.com that the kitchen sink is broken", CHAT)
    finally:
        llm.chat_json = real
    assert ("draft", "draft_v2") in seen


@pytest.mark.parametrize("greeting,name,bad", [
    ("Dear,", "", True), ("Querida,", "", True), ("Dear Maria,", "Maria", False), ("Hello,", "", False),
    ("Hi,", "", False), ("Dear Professor,", "", True), ("Hola,", "", False),
])
def test_106_dear_with_no_name_is_refused_by_the_checks(greeting, name, bad):
    from mvp.drafts import grounded
    srcs = ["email my landlord that the sink is broken", name, "T"]
    got = grounded({"subject": "Sink", "greeting": greeting, "closing": "Thanks,",
                    "body": "I'm writing to let you know that the sink is broken."}, srcs, name=name)
    assert bool(got) is bad


@pytest.mark.parametrize("body", [
    "I'm writing to let you know that the heating is broken again. Could you let me know when it can be fixed?",
    "I'm writing to let you know that the kitchen sink is broken. Could you take a look at it? Thank you for your help.",
])
def test_106_the_complete_shape_passes_the_checks(body):
    from mvp.drafts import grounded
    srcs = ["email my landlord that the heating is broken again and ask when it can be fixed", "", "landlord", "T"]
    subject = "Heating"
    if "sink" in body:
        srcs[0], subject = "email my landlord that the kitchen sink is broken", "Kitchen sink"
    assert grounded({"subject": subject, "greeting": "Hello,", "closing": "Best,", "body": body}, srcs, name="") == []


@pytest.mark.parametrize("body", [
    "I'm writing to let you know that the heating is broken again. It has been cold since Monday.",
    "I'm writing to let you know that the heating is broken again. I already called a plumber.",
    "I'm writing to let you know that the heating is broken again. I've paid for the repair.",
    "I'm writing to let you know that the heating broke three days ago.",
])
def test_106_the_checks_still_refuse_an_invented_fact(body):
    from mvp.drafts import grounded
    srcs = ["email my landlord that the heating is broken again and ask when it can be fixed", "", "landlord", "T"]
    assert grounded({"subject": "Heating", "greeting": "Hello,", "closing": "Best,", "body": body}, srcs, name="")


def test_106_the_eval_counts_sentences():
    from mvp.eval_drafts import sentences
    assert sentences("I'm writing about the sink. Could you take a look?\n\nThank you for your help.") == 3
    assert sentences("Le escribo. ¿Puede echarle un vistazo?") == 2
    assert sentences("I saw this. https://example.com/p/1") == 1
    assert sentences("") == 0


# =====================================================================================================================
# 107: with a draft card open, "put this in my email" means the card
# =====================================================================================================================
SAVE_LINE = ("I can't save it in your mail myself. This link opens it as a new message in your mail app; close it there "
             "without sending, and your mail app keeps it as a draft (some ask you first):\n")


@pytest.mark.parametrize("text", ["put this in my email", "put it in my drafts", "save it as a draft",
                                  "save this email as a draft", "can you put it in my gmail", "stick it in my inbox",
                                  "put it in my mail app"])
def test_107_with_a_card_open_the_save_words_mean_the_card(d, text):
    say(d, "email maria@example.com that the kitchen sink is broken", CHAT)
    c = card(d)
    n = calls(d)
    msg = say(d, text, boom)
    assert calls(d) == n and msg == SAVE_LINE + link_of(c[2])
    assert "your email address" not in msg.lower() and "code" not in msg.lower()
    assert d["bot"].open_draft(H) is not None and draft_row(d)["status"] == "link_shown"
    assert say(d, "send", CHAT).startswith("I can't send from your address.")   # the card is still the open thing


def test_107_the_link_is_the_version_last_shown(d):
    say(d, "email maria@example.com that the kitchen sink is broken", CHAT)
    say(d, "subject: Sink", CHAT)
    c = card(d)
    msg = say(d, "put this in my email", boom)
    assert msg.endswith(link_of(c[2])) and parse_mailto(link_of(c[2]))[1] == "Sink"


def test_107_before_the_card_is_ready_the_question_stands(d):
    say(d, "email my landlord that the kitchen sink is broken", CHAT)
    assert say(d, "put this in my email", boom).startswith("The email isn't finished yet.")


def test_107_with_a_placeholder_left_no_link(d):
    bot = d["bot"]
    bot.draft_start(bot.store.person(H), "notice", to="help@gym.example", subject="Cancel",
                    paragraphs=["Please cancel my membership.", "Member number: (fill this in)"],
                    placeholders=["member number"])
    msg = say(d, "put it in my drafts", boom)
    assert msg.startswith("Fill in the member number first") and "mailto:" not in msg


def test_107_with_no_card_nothing_changes(d):
    one_pick(d)
    n = len(d["ch"].outbox)
    say(d, "put this in my email", {"intent": "act_on_last", "actions": ["email.send"]})
    assert not any(x.startswith("I can't save it in your mail myself") for x in outbox_since(d, n))


def test_107_the_operator_with_a_mailbox_saves_the_card_itself(box):
    one_pick(box)
    say(box, "email maria@example.com that the kitchen sink is broken", CHAT)
    c = card(box)
    msg = say(box, "put this in my email", CHAT)
    assert msg.startswith("I saved it in your Drafts folder (maria@example.com is filled in). Nothing has been sent.")
    got = message_from_bytes(appended()[0], policy=policy.default)
    assert got["To"] == "maria@example.com" and got.get_content().replace("\r\n", "\n").rstrip("\n") == c[1]


# =====================================================================================================================
# 108: "apply to the first one" on a thing with no date still offers what the bot can do now
# =====================================================================================================================
PLAIN = ("h1", "harborclub", "Harbor Youth Fellowship\nA summer programme for students who love the sea.", "2026-10-05",
         "Harbor Youth Fellowship")
WITH_LIST = ("h1", "harborclub", "Harbor Youth Fellowship\nRequirements:\n- transcript\n- short essay\n\nGood luck!",
             "2026-10-05", "Harbor Youth Fellowship")
ASK_DATE = "The post doesn't say when it closes. Tell me the date, like \"dec 5\", and I'll set a reminder too."


def test_108_no_date_and_no_checklist_offers_the_to_do_and_a_bare_1_takes_it(env, tmp_path):
    seed(env, tmp_path, [PLAIN])
    msg = tell(env, "apply to the first one")
    assert "1. \"Apply to Harbor Youth Fellowship\" on your to-do list, with the post's link." in msg
    assert msg.endswith("Reply 1, or \"none\".\n" + ASK_DATE)
    msg = tell(env, "1")
    assert "Added \"Apply to Harbor Youth Fellowship\" to your list." in msg
    assert "I don't have anything waiting for a yes" not in msg and "I didn't apply for you" in msg
    rows = env["bot"].store.todos(H)
    assert [(r["text"], r["item_id"], bool(r["url"])) for r in rows] == [("Apply to Harbor Youth Fellowship", "h1",
                                                                            True)]
    assert tell(env, "undo").startswith("Undone")
    assert env["bot"].store.todos(H) == []


@pytest.mark.parametrize("choice", ["yes", "do 1", "the first one", "all"])
def test_108_other_ways_to_take_the_one_offer(env, tmp_path, choice):
    seed(env, tmp_path, [PLAIN])
    tell(env, "apply to it")
    tell(env, choice)
    assert [r["text"] for r in env["bot"].store.todos(H)] == ["Apply to Harbor Youth Fellowship"]


def test_108_the_date_still_answers_after_the_menu_and_after_the_choice(env, tmp_path):
    seed(env, tmp_path, [PLAIN])
    tell(env, "apply to it")
    tell(env, "1")
    msg = tell(env, "dec 5")
    assert msg.startswith("OK. I'll remind you about Harbor Youth Fellowship on Wednesday 2 December at 9am")


def test_108_with_a_checklist_the_to_do_is_first_and_the_date_question_last(env, tmp_path):
    seed(env, tmp_path, [WITH_LIST])
    msg = tell(env, "apply to the first one")
    assert "1. \"Apply to Harbor Youth Fellowship\" on your to-do list" in msg
    assert "2. A checklist from the post's own words: transcript, short essay." in msg
    assert msg.endswith('Reply 1, 2, "all", or "none".\n' + ASK_DATE)
    tell(env, "all")
    texts = [r["text"] for r in env["bot"].store.todos(H)]
    assert "Apply to Harbor Youth Fellowship" in texts and "transcript" in texts


def test_108_none_ends_the_menu(env, tmp_path):
    seed(env, tmp_path, [PLAIN])
    tell(env, "apply to it")
    assert tell(env, "none").startswith("OK.")
    assert env["bot"].store.todos(H) == []


def test_108_a_title_that_already_says_apply_is_not_said_twice():
    from mvp import texts as T
    assert T.apply_todo_text("Apply now: Harbor Youth Fellowship") == "Apply now: Harbor Youth Fellowship"
    assert T.apply_todo_text("Harbor Youth Fellowship") == "Apply to Harbor Youth Fellowship"


def test_108_an_apply_to_do_already_on_the_list_is_not_offered_again(env, tmp_path):
    seed(env, tmp_path, [PLAIN])
    env["bot"].store.add_todo(H, "Apply to Harbor Youth Fellowship", item_id="h1", at=env["clock"][0])
    msg = tell(env, "apply to it")
    assert "on your to-do list" not in msg and msg.startswith("I can't fill in or send the application myself.")


def test_108_a_dated_post_is_unchanged(env, tmp_path):
    cap = "Harbor Youth Fellowship\nApplications close 30 November 2026."
    seed(env, tmp_path, [("h1", "harborclub", cap, "2026-10-05", "Harbor Youth Fellowship")])
    msg = tell(env, "apply to it")
    assert "1. Its deadline, 30 November" in msg and "to-do list" not in msg and ASK_DATE not in msg
