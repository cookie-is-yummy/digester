"""Round 10, slice W (DESIGN.md section 17.W): the screenshot failures, the setup answer that holds a request, and
everyday wording read by code. Synthetic data only: made-up names and example.com addresses; the fake interpreter
answers a marker, so a test sees exactly when a message reached the model."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402
from mvp.tests.test_slice6 import rich  # noqa: E402,F401  (a fixture)

FELL = {"intent": "chat", "reply": "<<FELL-THROUGH>>"}
CHAT = {"intent": "chat", "reply": "unused"}


def replies_of(e, n0):
    return [t for _, _, t in e["ch"].outbox[n0:]]


def calls_since(e, n0):
    return e["calls"][n0:]


@pytest.fixture()
def tester(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "DRAFT_MODEL", False, raising=False)
    for k in ("MVP_SMTP_HOST", "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_OPERATOR"):
        monkeypatch.delenv(k, raising=False)
    env["bot"].max_per_minute = None
    return env


# ======================================= W-a, W1: the email to someone, "email it to me" =======================================
def test_teacher_card(tester):
    """Screenshot (b), a made-up sentence of the same shape: read by code, no model call, the card asks who."""
    e = tester
    n0 = len(e["calls"])
    out = say(e, "can you email my coach that i am not feeling well this morning", FELL)
    assert out == ("Who should it go to? Reply with your coach's email address, or \"blank\" to pick them in your mail "
                   "app.")
    assert calls_since(e, n0) == []


def test_the_old_refusal_never_offers_email_it_to_me():
    from mvp import texts as T
    assert "email it to me" not in T.EMAIL_ONLY_YOU.lower()
    assert T.EMAIL_ONLY_YOU.startswith("Tell me who it's for and what to say")


def _card_waiting_for_to(e):
    say(e, "can you email my coach that i am not feeling well this morning", FELL)
    d = e["bot"].open_draft(H)
    assert d and d["state"]["waiting"] == "to"
    return d


@pytest.mark.parametrize("text", ["email it to me", "Email it to me.", "send it to me", "email me a copy",
                                  "mail me the draft", "can you email it to myself please", "email it to me instead"])
def test_card_open_email_it_to_me_gives_the_link_to_self_and_keeps_the_card(tester, text):
    """Screenshot (c): the draft to themselves as a tap-to-open link; the card stays open, nothing to the coach."""
    e = tester
    d = _card_waiting_for_to(e)
    n0, c0 = len(e["ch"].outbox), len(e["calls"])
    say(e, text, FELL)
    out = "\n".join(replies_of(e, n0))
    assert out.startswith("Here's the draft as an email to yourself (tap to open it in your mail app): mailto:?subject=")
    assert "The draft to your coach is still open. Send me their address when you have it." in out
    assert "not%20feeling%20well%20this%20morning" in out
    assert calls_since(e, c0) == []
    d2 = e["bot"].open_draft(H)
    assert d2 and d2["id"] == d["id"] and d2["state"]["waiting"] == "to" and d2["status"] == "open"
    assert e["bot"].store.q("SELECT count(*) n FROM outbox")[0]["n"] == 0
    # the card goes on: the coach's address still lands on it
    out = say(e, "coach@example.com", FELL)
    assert e["bot"].open_draft(H)["to_addr"] == "coach@example.com"


def test_card_open_email_it_to_me_with_their_own_address_in_to(tester):
    e = tester
    e["bot"].store.set_email(H, "mia@example.com", verified=False)
    _card_waiting_for_to(e)
    out = say(e, "email it to me", FELL)
    assert "mailto:mia@example.com?subject=" in out


def test_card_open_email_it_to_me_with_email_set_up_sends_to_them_only(tester, monkeypatch):
    from mvp.actions import email as em
    e = tester
    monkeypatch.setenv("MVP_SMTP_HOST", "smtp.example.invalid")
    sent = []
    monkeypatch.setattr(em, "_smtp_send", lambda s, m: sent.append((m["To"], m["Subject"], m.get_body(("plain",)).get_content())))
    e["bot"].store.set_email(H, "mia@example.com", verified=True)
    say(e, "email my coach coach@example.com that i am not feeling well this morning", FELL)
    n0 = len(e["ch"].outbox)
    say(e, "email it to me", FELL)
    out = "\n".join(replies_of(e, n0))
    assert out == ("I emailed the draft to you at m•••@example.com, so you can forward it. The draft to your coach is "
                   "still open.")
    assert [s[0] for s in sent] == ["mia@example.com"]          # only to them; never to the coach
    assert "not feeling well this morning" in sent[0][2].lower()
    d = e["bot"].open_draft(H)
    assert d and d["status"] in ("link_shown", "open") and d["to_addr"] == "coach@example.com"


@pytest.mark.parametrize("text", ["email it to me", "send it to me", "Email it to myself please."])
def test_nothing_written_and_nothing_shown_says_so_plainly(tester, text):
    from mvp import texts as T
    e = tester
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert out == T.NOTHING_TO_EMAIL
    assert "didn't catch" not in out and "haven't sent you anything" not in out
    assert calls_since(e, c0) == []


@pytest.mark.parametrize("text", ["email me that", "email me a copy"])
def test_email_me_that_with_nothing_shown_goes_the_old_way_and_says_the_same(tester, text):
    """The rule eval holds "email me that": it stays the interpreter's act_on_last (no new read takes it); the reply
    with nothing to send is the same plain line."""
    from mvp import texts as T
    out = say(tester, text, {"intent": "act_on_last", "actions": ["email.send"]})
    assert out == T.NOTHING_TO_EMAIL


def test_email_it_to_me_after_an_answer_goes_the_old_way(tester):
    """With an answer in view, "email it to me" is the interpreter's act_on_last as before (W-b adds code later)."""
    from mvp import texts as T
    e = tester
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())
    out = say(e, "email it to me", FELL)
    assert out != T.NOTHING_TO_EMAIL


@pytest.mark.parametrize("text", ["cancel it for me", "can you cancel it for me"])
def test_w1_draft_open_cancel_it_for_me_is_not_a_draft_cancel(tester, text):
    e = tester
    say(e, "email sam@example.com that the sink is broken", FELL)
    d = e["bot"].open_draft(H)
    assert d is not None
    say(e, text, FELL)
    d2 = e["bot"].open_draft(H)
    assert d2 is not None and d2["id"] == d["id"]
    assert e["bot"].store.draft(d["id"])["status"] != "cancelled"
    # the near-variant still cancels the draft
    say(e, "cancel it", FELL)
    assert e["bot"].store.draft(d["id"])["status"] == "cancelled"


# ======================================= W2: the time line =======================================
@pytest.mark.parametrize("stored,line,pref", [
    ("not much time usually", "you don't have much time", "doesn't have much time"),
    ("20 minutes a day", "you usually have 20 minutes a day", "usually has 20 minutes a day"),
    ("like 15 min max", "you usually have like 15 min max", "usually has like 15 min max"),
    ("evenings only", "time you have: evenings only", "time they have: evenings only"),
    ("usually about 30 minutes", "you usually have about 30 minutes", "usually has about 30 minutes"),
    ("hardly any time", "you don't have much time", "doesn't have much time"),
    ("half an hour", "you usually have half an hour", "usually has half an hour"),
])
def test_time_line(stored, line, pref):
    from mvp.profile import time_line
    assert time_line(stored) == line
    assert time_line(stored, who="pref") == pref


def test_the_time_line_is_used_where_the_time_is_said(rich):
    from mvp import profile as P
    bot = rich["bot"]
    res = P.apply_merge(bot.store, H, {"kind": "about_me", "time": "not much time usually"},
                        "not much time usually, sorry")
    assert res["changes"] == ["you don't have much time"]
    assert "you don't have much time" in P.show_text(P.get(bot.store, H)).lower()
    assert "Preferences: doesn't have much time." in "\n".join(P.about_lines(bot.store, H))


@pytest.mark.parametrize("note", ["wants YouTube and Instagram exports sent regularly",
                                  "would like you to set up regular exports", "help setting up exports",
                                  "needs you to send the export"])
def test_a_request_shaped_note_is_never_kept(rich, note):
    from mvp import profile as P
    bot = rich["bot"]
    res = P.apply_merge(bot.store, H, {"kind": "about_me", "note": note}, note)
    assert not bot.store.profile_notes(H) and not any(c.startswith("noted:") for c in res["changes"])


def test_a_plain_note_is_still_kept(rich):
    from mvp import profile as P
    bot = rich["bot"]
    P.apply_merge(bot.store, H, {"kind": "about_me", "note": "cooks for two kids"}, "i cook for two kids")
    assert bot.store.profile_notes(H) == ["cooks for two kids"]


# ======================================= W3: the setup answer =======================================
from mvp.tests.test_fixpass2 import _to_the_last_message  # noqa: E402

SETUP_MSG = ("not really, i don't have much time. but can you help me set it up so my youtube and instagram export to "
             "you regularly")
FORMS = {
    "about_me": {"kind": "about_me", "time": "not much time", "note": "wants YouTube and Instagram exports sent regularly"},
    "request": {"kind": "request", "time": "not much time", "note": "wants exports"},
    "both": {"kind": "both", "time": "not much time", "note": "wants YouTube and Instagram exports sent regularly"},
}


@pytest.mark.parametrize("form", list(FORMS))
def test_the_setup_answer_that_asks_for_regular_exports(rich, form):
    """Design B5: reminders started; "you don't have much time", never "usually have not"; no note; no junk reminder;
    at most 1 merge call; 0 interpreter calls."""
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    assert bot.store.pending(H)["kind"] == "confirm_rule"
    st["answers"]["mvp_profile_merge"] = lambda u, f=FORMS[form]: dict(f)
    n0, c0 = len(rich["ch"].outbox), len(rich["calls"])
    say(rich, SETUP_MSG, FELL)
    out = "\n".join(replies_of(rich, n0))
    calls = calls_since(rich, c0)
    assert calls.count("mvp_interpret") == 0 and calls.count("mvp_profile_merge") <= 1, calls
    assert "you don't have much time" in out and "usually have not" not in out
    assert out.startswith("Noted: you don't have much time.\n\nAbout regular exports:"), out
    assert "• YouTube: Google Takeout can repeat your export every 2 months for a year." in out
    assert "• Instagram: I can't confirm a repeating export for your account, so I'll remind you every 4 weeks." in out
    assert "• Each new file goes in the upload box on the test page, and I add it by myself." in out
    assert "Done: next Instagram reminder 10 December, next YouTube one 12 January. Say \"undo\" to stop the reminders." \
        in out
    assert "<<FELL-THROUGH>>" not in out and "what do you know about me" not in out
    assert not bot.store.profile_notes(H)
    rules = bot.store.rules(H)
    assert len(rules) == 2 and all(r["spec"]["content"]["text"].startswith("Time for a fresh") for r in rules)
    assert bot.store.pending(H) is None
    assert P_time(bot) == "not much time"


def P_time(bot):
    from mvp import profile as P
    return P.get(bot.store, H)["prefs"].get("time")


def test_the_setup_answer_on_the_web_page_says_this_page(rich, monkeypatch):
    bot, st = rich["bot"], rich["state"]
    monkeypatch.setattr(bot.channel, "name", "web", raising=False)
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: dict(FORMS["about_me"])
    out = say(rich, SETUP_MSG, FELL)
    assert "• Each new file goes in the upload box on this page, and I add it by myself." in out


@pytest.mark.parametrize("text", [
    "no. but can you set it up so my youtube and instagram export to you regularly",
    "set it up so my youtube and instagram export to you regularly. no",
    "nope, can you help me set it up so my instagram export comes to you regularly",
])
def test_w4_an_export_request_wins_over_a_no_word_in_either_order(rich, text):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me"}
    c0 = len(rich["calls"])
    out = say(rich, text, FELL)
    assert "Done: next Instagram reminder" in out and "OK, no export reminders" not in out
    assert len(bot.store.rules(H)) == 2
    assert "mvp_interpret" not in calls_since(rich, c0)


def test_ok_sure_and_i_have_an_instant_pot_keeps_todays_outcome(rich):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "tools": ["instant pot"]}
    out = say(rich, "ok sure, and i have an instant pot", {"intent": "profile_update"})
    assert out.startswith("Done. Next Instagram reminder") and "an instant pot" in out
    assert len(bot.store.rules(H)) == 2


def test_no_i_have_an_instant_pot_still_declines(rich):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "tools": ["instant pot"]}
    out = say(rich, "no. i have an instant pot", {"intent": "profile_update"})
    assert out.startswith("OK, no export reminders.") and "an instant pot" in out
    assert not bot.store.rules(H) and bot.store.pending(H) is None


@pytest.mark.parametrize("kind", ["about_me", "request", "both"])
def test_the_read_step_answer_with_an_email_request_makes_the_card_and_goes_on(rich, kind):
    from mvp.tests.test_slice6 import start
    bot, st = rich["bot"], rich["state"]
    start(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": kind, "confirm_all": True,
                                                    "note": "wants an email to the landlord"}
    n0, c0 = len(rich["ch"].outbox), len(rich["calls"])
    say(rich, "looks right. can you also email my landlord that the sink is broken", FELL)
    out = replies_of(rich, n0)
    assert any(x.startswith("Who should it go to? Reply with your landlord's email address") for x in out), out
    assert (bot.store.get_state(f"onboard:{H}") or {}).get("step") == "contact"
    assert "mvp_interpret" not in calls_since(rich, c0)
    assert bot.open_draft(H) is not None
    assert not bot.store.profile_notes(H)


def test_a_preference_answer_with_no_request_goes_the_old_way(rich):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "time": "about 20 minutes a day"}
    out = say(rich, "i'm vegetarian and i have about 20 minutes a day", {"intent": "profile_update"})
    assert "you usually have about 20 minutes a day" in out
    assert bot.store.pending(H)["kind"] == "confirm_rule"   # the reminders still wait for a yes


# ======================================= W3: export_reads in the normal path (hook 5a) =======================================
def test_where_do_i_upload_my_new_export_gives_the_steps_by_code(rich):
    c0 = len(rich["calls"])
    out = say(rich, "where do i upload my new export", FELL)
    assert "Instagram, every 4 weeks:" in out or "YouTube, every 2 months:" in out
    assert calls_since(rich, c0) == []


def test_sync_my_saves_automatically_offers_the_reminders_with_one_yes(rich):
    bot = rich["bot"]
    c0 = len(rich["calls"])
    out = say(rich, "i want my saves to sync automatically instead of one export", FELL)
    assert out.startswith("About regular exports:") and out.endswith("Want me to remind you? Say yes.")
    assert calls_since(rich, c0) == []
    assert not bot.store.rules(H)
    out = say(rich, "yes", {"intent": "confirm"})
    assert out.startswith("Done. Next Instagram reminder")
    assert len(bot.store.rules(H)) == 2
    # asked again: they are on
    out = say(rich, "can you keep my saves synced", FELL)
    assert out.startswith("Your export reminders are on: next Instagram one")
    # "steps" right after: the steps, by code
    out = say(rich, "steps", FELL)
    assert "Instagram, every 4 weeks:" in out


def test_steps_alone_is_not_taken_without_the_export_reply(rich):
    out = say(rich, "steps", FELL)
    assert out == "<<FELL-THROUGH>>"


def test_remind_me_every_month_to_send_my_youtube_takeout(rich):
    from mvp.schema import RuleSpec
    bot = rich["bot"]
    out = say(rich, "can you remind me every month to send my youtube takeout", FELL)
    assert out.startswith("I'll remind you every month to send me a new YouTube export, with the steps, starting ")
    assert out.endswith("Want me to? Say yes.")
    say(rich, "yes", {"intent": "confirm"})
    rules = bot.store.rules(H)
    assert len(rules) == 1
    spec = RuleSpec.model_validate(rules[0]["spec"])
    assert spec.when.every_months in (None, 1) and spec.content.text.startswith("Time for a fresh YouTube export")


@pytest.mark.parametrize("text", ["show me the reel about exporting videos from capcut",
                                  "every sunday send me the recipes i saved", "export my data",
                                  "how do i export a blender model", "remind me to call mum every month"])
def test_export_reads_leave_other_messages_alone(rich, text):
    from mvp.refresh import export_kind
    assert export_kind(text) is None


# ======================================= phrasing.py: the near-variant table (design A1, W-1, W-2) =======================================
@pytest.mark.parametrize("text", [
    "just the links", "help", "help me", "send help i have nothing in the fridge", "what did you do for me",
    "show me what you have done for me this week", "no say tuesday not monday", "nvm cancel that",
    "cancel that, i meant workouts", "yes", "ok", "yes more like that", "so tired of pasta, something else",
    "but not spicy", "and another one", "thanks! that's perfect", "i need to cook something fast tonight",
    "can i buy the first one", "cancel it for me", "do it for me", "email it for me"])
def test_normalize_never_strips_these(text):
    from mvp.phrasing import normalize
    assert normalize(text) == text


@pytest.mark.parametrize("text,out", [
    ("chicken and rice recipe, just the ingredients pls", "chicken and rice recipe, just the ingredients"),
    ("perfect send it now pls", "send it now"), ("looks good, send", "send"),
    ("hey can u cancel my hulu thx", "cancel my hulu"),
    ("i need you to email my boss that im late", "email my boss that i'm late"),
    ("could u help me cancel youtube premium", "cancel youtube premium"),
    ("find me pasta for me", "find me pasta")])
def test_normalize_strips_these(text, out):
    from mvp.phrasing import normalize
    assert normalize(text) == out


@pytest.mark.parametrize("text,n", [
    ("cancel my hulu and also email my landlord about the rent", 2),
    ("looks right. can you also email my landlord that the sink is broken", 2),
    ("every sunday put the recipes in ticktick and email me", 1),        # a time word: a rule, never split
    ('email sam "a and b. c" and also cancel netflix', 1),                # quotes
    ("i'm vegetarian and i have an air fryer", 1),
    ("chicken but not spicy", 1),                                       # "not spicy": two words, asks nothing
    ("cancel hulu. email sam about rent. add milk to my list. also book a table", 3)])
def test_clauses(text, n):
    from mvp.phrasing import clauses
    assert len(clauses(text)) == n


def test_clauses_takes_off_the_joining_words():
    from mvp.phrasing import parts
    assert parts("looks right. can you also email my landlord that the sink is broken") == [
        ("looks right.", False), ("can you email my landlord that the sink is broken", True)]


# ======================================= W-b: everyday wording read by code (W4 to W6) =======================================
from mvp.tests.test_round9_postacts import NASA_POST, TACOS, seed  # noqa: E402

POSTS = [("r1", "eats", TACOS, "2026-09-01", "Tacos El Gordo"), NASA_POST,
         ("c4", "venue", "Live concert Dec 12 at the Hall\nTickets at https://example.com/tickets", "2026-10-22",
          "Live concert Dec 12")]


def _draft(e, text="email sam@example.com that the meeting moved to wednesday. my doctor said to rest."):
    say(e, text, FELL)
    d = e["bot"].open_draft(H)
    assert d is not None
    return d


def _todos(e, items=("Email landlord about the sink", "Cancel Netflix", "Buy basil")):
    for t in items:
        e["bot"].store.add_todo(H, t, at=e["clock"][0])
    say(e, "my list", {"intent": "todo_list"})


# ---------- the card's words (draft_reads: never the normalised text, W-2) ----------
@pytest.mark.parametrize("text", ["looks good, send", "perfect send it now pls", "sí, envíalo", "mándalo", "yes send it"])
def test_send_words_in_everyday_shapes(tester, text):
    from mvp import texts as T
    e = tester
    _draft(e)
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert out == T.DRAFT_SEND_LINK and calls_since(e, c0) == []


@pytest.mark.parametrize("text", ["ok go ahead", "go ahead", "yeah go ahead"])
def test_go_ahead_is_the_cards_yes_line_and_never_sends(tester, text):
    from mvp import texts as T
    e = tester
    _draft(e)
    assert say(e, text, FELL) == T.DRAFT_YES


@pytest.mark.parametrize("text", ["go ahead and send it to my boss instead", "send it tomorrow"])
def test_send_near_variants_are_not_the_send_word(tester, text):
    from mvp import texts as T
    e = tester
    _draft(e)
    assert say(e, text, FELL) != T.DRAFT_SEND_LINK


@pytest.mark.parametrize("text", ["dont send yet, keep it in drafts", "keep it in drafts", "just save it as a draft",
                                  "put it in my gmail drafts pls", "save it, i'll send it myself"])
def test_save_as_draft_shapes(tester, text):
    e = tester
    _draft(e)
    out = say(e, text, FELL)
    assert out.startswith("I can't save it in your mail myself.") and "mailto:" in out


def test_say_x_instead_of_y_changes_only_where_the_draft_says_y(tester):
    e = tester
    _draft(e)
    n0 = len(e["ch"].outbox)
    say(e, "no say thursday not wednesday", FELL)
    out = "\n".join(replies_of(e, n0))
    assert "new version" in out.lower(), out
    body = e["bot"].open_draft(H)["body"]
    assert "thursday" in body and "wednesday" not in body.lower()
    # a word the draft doesn't hold: said plainly, nothing changed, never a reminder
    v = e["bot"].open_draft(H)["version"]
    out = say(e, "say tuesday instead of monday", FELL)
    assert out.startswith("The draft doesn't say \"monday\", so I didn't change it.")
    assert e["bot"].open_draft(H)["version"] == v and not e["bot"].store.rules(H)


def test_take_out_the_part_about_drops_that_sentence_only(tester):
    e = tester
    _draft(e)
    say(e, "take out the part about the doctor", FELL)
    body = e["bot"].open_draft(H)["body"]
    assert "doctor" not in body.lower() and "wednesday" in body.lower()


# ---------- email to someone else ----------
@pytest.mark.parametrize("text,whose", [
    ("could u send coach dan an email that i cant make practice tonight", "Dan's"),
    ("can you let my professor know by email that my essay will be a day late", "your professor's"),
    ("shoot sam an email saying thanks for the dinner rec", "Sam's"),
    ("drop sam a line saying thanks for the dinner rec", "Sam's"),
])
def test_email_requests_in_everyday_shapes(tester, text, whose):
    e = tester
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert out.startswith(f"Who should it go to? Reply with {whose} email address"), out
    assert calls_since(e, c0) == []


def test_a_lowercase_title_and_name_before_the_address(tester):
    e = tester
    say(e, "can you email ms rivera (rivera@example.com) that i'll miss class today, feeling sick", FELL)
    d = e["bot"].open_draft(H)
    assert d["to_addr"] == "rivera@example.com" and d["parts"]["greet_name"] == "Ms Rivera"


@pytest.mark.parametrize("text", ["let my mom know i'm on my way", "tell my boss im late", "shoot me an email",
                                  "email me that", "email marketing tips please"])
def test_email_near_variants_are_not_a_card(tester, text):
    e = tester
    say(e, text, FELL)
    assert e["bot"].open_draft(H) is None


def test_the_draft_keeps_the_message_itself_never_its_normalised_form(tester):
    e = tester
    say(e, "hey could u pls email my landlord that the heater is broken again thx", FELL)
    d = e["bot"].open_draft(H)
    assert d["parts"]["text"] == "hey could u pls email my landlord that the heater is broken again thx"


# ---------- email to self with an answer in view (the message itself only) ----------
@pytest.mark.parametrize("text", ["email it to me", "pls email me the list", "mail me the recipe pls",
                                  "can you send me this by email", "send it to my email so i dont lose it"])
def test_email_to_self_after_an_answer_by_code(tester, text):
    from mvp import texts as T
    e = tester
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert "mvp_interpret" not in calls_since(e, c0)
    assert out == T.EMAIL_ASK or "email" in out.lower(), out


@pytest.mark.parametrize("text", ["email me that", "can u email me this one too", "email me these tonight at 8",
                                  "yes but also email it to me", "email me 3 easy pasta recipes"])
def test_rule_eval_email_texts_still_reach_the_interpreter(tester, text):
    e = tester
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())
    c0 = len(e["calls"])
    say(e, text, FELL)
    assert "mvp_interpret" in calls_since(e, c0)


# ---------- cancel ----------
@pytest.mark.parametrize("text,name", [("pls get rid of my hulu subscription", "Hulu"),
                                       ("im paying for apple tv and never watch it, cancel it", "Apple"),
                                       ("how do i stop paying for disney plus", "Disney"),
                                       ("hey can u cancel my hulu thx", "Hulu")])
def test_cancel_in_everyday_shapes(tester, text, name):
    e = tester
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert name in out and calls_since(e, c0) == [], out


@pytest.mark.parametrize("text", ["any videos on how to cancel subscriptions you dont use",
                                  "im thinking of cancelling netflix, did i save anything worth watching on it first",
                                  "show me the reel about cancelling gym memberships", "drop it",
                                  "find the video about how to cancel subscriptions"])
def test_library_questions_are_never_a_cancel(text):
    from mvp import cancel
    assert cancel.request(text) is None


def test_how_do_i_cancel_my_netflix_is_still_a_cancel():
    from mvp import cancel
    assert cancel.request("how do i cancel my netflix")["kind"] == "merchant"


# ---------- apply, book, buy ----------
@pytest.mark.parametrize("text,start", [("can i buy the first one", "I can't buy things for you."),
                                        ("get me tickets for that concert", "I can't book"),
                                        ("reserve a table at that place for 2 on friday", "I can't book tables.")])
def test_post_acts_in_everyday_shapes(env, tmp_path, text, start):
    seed(env, tmp_path, POSTS)
    c0 = len(env["calls"])
    out = say(env, text, FELL)
    assert out.startswith(start) and calls_since(env, c0) == [], out
    assert "NASA" not in out   # "for 2" is how many people, never pick 2


# ---------- connectors and outside apps ----------
@pytest.mark.parametrize("text,start", [
    ("connect my gmail", "I can't connect to Gmail yet."),
    ("can you hook up my google calendar", "I can't connect to Google Calendar yet."),
    ("disconnect notion pls", "I'm not connected to Notion"),
    ("stop using my gmail", "I'm not connected to Gmail"),
])
def test_apps_with_no_connector_get_the_honest_line(tester, text, start):
    e = tester
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert out.startswith(start) and calls_since(e, c0) == [], out


@pytest.mark.parametrize("text", ["is ticktick connected?", "i want to link my todoist", "what apps are you connected to"])
def test_connector_questions_in_everyday_shapes_are_read_by_code(tester, text):
    e = tester
    c0 = len(e["calls"])
    out = say(e, text, FELL)
    assert out != "<<FELL-THROUGH>>" and calls_since(e, c0) == []


@pytest.mark.parametrize("text", ["show me the ticktick setup video", "i use ticktick for everything",
                                  "the notion template reel pls", "what was that video about gmail shortcuts"])
def test_app_names_in_library_questions_are_not_taken(tester, text):
    c0 = len(tester["calls"])
    say(tester, text, FELL)
    assert "mvp_interpret" in calls_since(tester, c0)


def test_add_these_to_my_ticktick_and_save_the_first_one_to_my_notion(tester):
    e = tester
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())
    assert "TickTick" in say(e, "add these to my ticktick", FELL)
    assert "Notion" in say(e, "save the first one to my notion", FELL)


# ---------- what did you do ----------
def test_what_did_you_do_only_when_something_was_done(tester):
    e = tester
    assert say(e, "what did you do", FELL) == "<<FELL-THROUGH>>"
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())
    say(e, "add it to my list", {"intent": "act_on_last", "actions": ["todo.add"]})
    assert say(e, "what did you do", FELL) != "<<FELL-THROUGH>>"
    assert say(e, "show me what you've done for me this week", FELL) != "<<FELL-THROUGH>>"
    assert say(e, "what did u add to my calendar", FELL) != "<<FELL-THROUGH>>"


# ---------- do it ----------
def test_go_ahead_with_the_netflix_one(tester):
    e = tester
    _todos(e)
    n0 = len(e["ch"].outbox)
    say(e, "go ahead with the netflix one", FELL)
    assert "Netflix cancels on its website" in "\n".join(replies_of(e, n0))


def test_do_all_of_them_does_one_and_never_ticks_anything_off(tester):
    e = tester
    _todos(e)
    n0 = len(e["ch"].outbox)
    say(e, "do all of them", FELL)
    out = "\n".join(replies_of(e, n0))
    assert "One at a time: next is \"Cancel Netflix\"" in out
    assert len(e["bot"].store.todos(H)) == 3   # nothing ticked off


def test_a_model_todo_done_without_a_done_word_is_a_do_it(tester):
    """Live harm replayed with a fake form: "do all of them" read as todo_done never ticks off."""
    e = tester
    _todos(e)
    say(e, "please sort them all out", {"intent": "todo_done", "todo_number": 1})
    assert len(e["bot"].store.todos(H)) == 3
    say(e, "done 1", {"intent": "todo_done", "todo_number": 1})
    assert len(e["bot"].store.todos(H)) == 2   # a done word still ticks off


# ---------- what is on screen (screen_guard, W6) ----------
def test_a_draft_change_read_as_a_reminder_makes_no_rule(tester):
    e = tester
    _draft(e)
    say(e, "no say tuesday not monday", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["MON"], "time": "09:00"},
        "content": {"source": "note", "text": "say tuesday not monday"}}})
    assert not e["bot"].store.rules(H)


def test_a_model_confirm_with_the_card_open_gives_the_cards_line(tester):
    from mvp import texts as T
    e = tester
    _draft(e)
    assert say(e, "looks great to me, thank you", {"intent": "confirm"}) == T.DRAFT_YES


def test_a_chat_reply_about_the_bots_insides_is_replaced(tester):
    from mvp import texts as T
    out = say(tester, "what did you do", {"intent": "chat", "reply": "I turned your message into structured JSON."})
    assert out == T.CHAT_INSIDE and "JSON" not in out


def test_a_rule_naming_an_app_says_it_cant_add_there_yet(tester):
    e = tester
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    n0 = len(e["ch"].outbox)
    say(e, "every sunday put the recipes you find in my ticktick", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["SUN"], "time": "09:00"},
        "content": {"source": "library", "goal": "recipes", "searches": ["recipes"]}}})
    out = replies_of(e, n0)
    assert out[0].startswith("I can't add to TickTick on a schedule yet. I can send them to you every Sunday"), out


# ---------- two asks in one message (split_reads, hook 8z) ----------
def test_cancel_and_email_in_one_message_reach_both_helpers(tester):
    e = tester
    n0, c0 = len(e["ch"].outbox), len(e["calls"])
    say(e, "cancel my hulu and also email my landlord about the rent", FELL)
    out = "\n".join(replies_of(e, n0))
    assert "Hulu" in out and "Who should it go to? Reply with your landlord's email address" in out
    assert calls_since(e, c0) == []


def test_a_third_ask_is_said_back(tester):
    e = tester
    n0 = len(e["ch"].outbox)
    say(e, "cancel my hulu. email my landlord about the rent. also book a table", FELL)
    out = "\n".join(replies_of(e, n0))
    assert "You also asked: \"book a table\". Send it on its own and I'll do it." in out


@pytest.mark.parametrize("text", ["put oat milk on my shopping list and find me a smoothie recipe",
                                  "add tortillas to my grocery list and find me a taco recipe",
                                  "every sunday cancel my hulu reminder and email me"])
def test_two_asks_with_no_doing_helper_stay_whole(tester, text):
    e = tester
    c0 = len(e["calls"])
    say(e, text, FELL)
    assert calls_since(e, c0).count("mvp_interpret") == 1
