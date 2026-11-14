"""Checker, round 8 (DESIGN.md sections 12 and 13): the claims of the answers and rules slices, tried on near-variants.
Each test here failed before the fix it names. Synthetic data, the fake model, the fake search pool and the fake clock
only (New York)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round8_rules import no_model, opps, rules, spec_of, tick_at, tue_todo, u  # noqa: E402


class It:
    """A post as clean_items reads it: its text and its first line."""
    def __init__(self, text):
        self.id, self.raw_caption, self.caption = "x", text, " ".join(text.split())
        self.first_line = next((" ".join(x.split()) for x in text.splitlines() if x.strip()), "")


def names(items):
    return [x["name"] for x in items]


# ---------- finding 93: a real thing written in lower case is still a thing ----------
def test_a_lower_case_name_with_a_slash_or_on_its_own_list_line_is_kept():
    from mvp.extract import clean_items
    text = ("Best UI libraries:\n- shadcn/ui: beautifully designed components you can copy\n"
            "- daisyUI: tailwind components for everyone\n- lucide - clean open icons")
    got, dropped = clean_items([{"name": "shadcn/ui", "about": "beautifully designed components you can copy"},
                                {"name": "daisyUI", "about": "tailwind components for everyone"},
                                {"name": "lucide", "about": "clean open icons"}], It(text))
    assert names(got) == ["shadcn/ui", "daisyUI", "lucide"] and dropped == 0
    # a hyphen inside the name marks it too; a site keeps its name
    got, _ = clean_items([{"name": "react-hook-form", "about": "the forms library i use for every single project"},
                          {"name": "untitledui", "about": "free figma kits and a huge icon set"}],
                         It("Use react-hook-form, the forms library i use for every single project\n"
                            "untitledui.com: free figma kits and a huge icon set"))
    assert names(got) == ["react-hook-form", "untitledui"]
    # near-variants that stay dropped: a kind word, and a lower-case word that only starts a sentence on a list line
    got, _ = clean_items([{"name": "design systems", "about": "a list of the some best design systems"},
                          {"name": "notion", "about": "where i keep them all together"},
                          {"name": "Material UI", "about": "Google's React components, themable"}],
                         It("Design systems\n- a list of the some best design systems\n"
                            "- notion is where i keep them all together\n- Material UI: Google's React components, "
                            "themable"))
    assert names(got) == ["Material UI"]


def test_a_caption_written_without_capitals_cannot_use_the_capital_test():
    from mvp.extract import clean_items, common_noun
    text = ("my fav ui libs for side projects honestly 👇 shadcn, lucide and htmx. lucide has the cleanest open "
            "source icon set around and htmx keeps things simple and fast to ship with")
    got, _ = clean_items([{"name": "lucide", "about": "lucide has the cleanest open source icon set around"},
                          {"name": "htmx", "about": "htmx keeps things simple and fast to ship with"}], It(text))
    assert names(got) == ["lucide", "htmx"]
    # a text with capitals still uses it; a kind after a determiner is still a kind in a lower-case caption
    assert common_noun("htmx", "I use htmx for everything these days. It is simple and Fast and Good.")
    assert common_noun("figma design system", "choosing the right figma design system is crucial for teams who "
                                              "build things together every day")


# ---------- finding 95: one topic with two kind words is one ask ----------
def test_a_bare_kind_word_shares_the_topic_of_the_part_beside_it():
    from mvp.answers import split_asks
    for one in ("tools and resources for designers", "cafes and restaurants in lisbon", "books and podcasts about "
                "startups", "apps, tools and websites for designers", "show me productivity tips and tools",
                "jobs or internships in design", "ui kits and templates", "startup ideas and opportunities",
                "recipes and workouts"):
        assert split_asks(one) is None, one
    # near-variants that still split: every part has words of its own
    assert split_asks("send me startup motivation related reels, opportunities to pursue soon, or things with "
                      "deadlines") == ["startup motivation related reels", "opportunities to pursue soon",
                                       "things with deadlines"]
    assert split_asks("dinner ideas, also some workout videos") == ["dinner ideas", "workout videos"]
    assert split_asks("blender tutorials and some pasta recipes") == ["blender tutorials", "pasta recipes"]


# ---------- finding 97: a question about the app or the person's data is never a search ----------
def test_the_chat_guard_leaves_questions_about_the_app_and_statements_alone():
    from mvp.interpret import chat_guard
    from mvp.schema import Interpretation

    def guard(t):
        return chat_guard(Interpretation(intent="chat", reply="x"), t).intent
    for chat in ("what does the app do with my saves", "is my library private and safe", "where are my saves stored",
                 "can i delete my saves from here", "who can see my saves", "how does this work with my saves",
                 "is there any way to export my saves", "what is the best way to share my saves",
                 "any idea why the search is slow", "what happens to the posts I saved", "did i ever tell it my name",
                 "how many recipes did I save", "why did I save so many recipes", "I saved a lot of reels this "
                 "month huh", "i liked that last one a lot", "ugh i have missed so many deadlines this year"):
        assert guard(chat) == "chat", chat
    # near-variants that are still asks
    for ask in ("what other opportunities might i have missed for 2026, especially winter or next summer",
                "other opportunities i might have missed for 2026, especially winter or next summer",
                "did i save any good pasta recipes last month", "show me other blender tutorials from my saves",
                "what apps do i have saved for budgeting", "what do I have saved about design",
                "any other ui libraries in my saves"):
        assert guard(ask) == "ask", ask


# ---------- BN1: a reminder sent later says how far the date is from the day it is sent ----------
def test_a_fired_deadline_reminder_counts_the_days_from_the_send_not_from_the_answer(env, tmp_path):
    opps(env, tmp_path)
    bot, ch = env["bot"], env["ch"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    n0 = len(ch.outbox)
    env["clock"][0] = u(2026, 11, 27, 14, 1)
    assert bot.tick() == 1
    out = ch.outbox[n0][2]
    assert out.startswith("Reminder: NASA L'SPACE Academy's deadline is 30 November (in 3 days).")
    assert out.endswith("applications close 30 November 2026 (deadline 30 November, in 3 days)")
    assert "16 days" not in out


def test_the_same_across_a_year_end_and_for_a_later_send_the_model_set(env, tmp_path):
    items = [{"name": "Winter Lab", "about": "deadline Jan 5", "when": "Jan 5"},
             {"name": "Spring Camp", "about": "for first years, apply by Jan 2", "when": "Jan 2"}]
    cap = "Programs to apply to:\nWinter Lab: deadline Jan 5\nSpring Camp: for first years, apply by Jan 2"
    opps(env, tmp_path, cap=cap, items=items, posted="2026-12-10", clock=u(2026, 12, 20, 15, 0))
    bot, ch = env["bot"], env["ch"]
    msg = say(env, "remind me a week before winter lab closes", no_model)
    assert "Tuesday 29 December at 9am, a week before its deadline, 5 January 2027 (in 16 days)" in msg
    assert spec_of(rules(bot)[-1])["when"]["date"] == "2026-12-29"
    say(env, "remind me about spring camp on dec 30", {
        "intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}],
        "when": {"type": "once", "date": "2026-12-30", "time": "10:00"}})
    n0 = len(ch.outbox)
    env["clock"][0] = u(2026, 12, 29, 14, 1)
    assert bot.tick() == 1
    assert ch.outbox[n0][2].startswith("Reminder: Winter Lab's deadline is 5 January 2027 (in 7 days).")
    assert ch.outbox[n0][2].endswith("1. Winter Lab: deadline Jan 5 (deadline 5 January 2027, in 7 days)")
    env["clock"][0] = u(2026, 12, 30, 15, 1)
    assert bot.tick() == 1
    assert ch.outbox[-1][2].endswith("(deadline 2 January 2027, in 3 days)")


def test_renew_note_leaves_other_notes_and_says_passed_when_the_day_is_gone():
    from datetime import date
    from mvp.render import renew_note
    x = {"n": 1, "name": "A", "about": "", "note": "from May 2024, so this round has probably closed", "date": None}
    assert renew_note(x, date(2026, 11, 14)) == x
    y = renew_note({"n": 2, "name": "B", "about": "apply soon", "note": "deadline 1 December (in 17 days)",
                    "date": "2026-12-01", "state": "open"}, date(2026, 12, 3))
    assert y["note"] == "its deadline, 1 December 2026, has passed" and y["state"] == "passed"
    assert y["shown"] == "B: apply soon (its deadline, 1 December 2026, has passed)"


# ---------- BN2 (c): one nudge at a time, so "drop it" is about the one asked ----------
def test_two_todos_past_due_are_nudged_one_at_a_time(env):
    bot, ch = env["bot"], env["ch"]
    tue_todo(env)
    tue_todo(env, text="post the letter")
    tick_at(env, u(2026, 11, 17, 23, 1))
    n0 = len(ch.outbox)
    assert tick_at(env, u(2026, 11, 18, 23, 1)) == 1
    assert [m[2] for m in ch.outbox[n0:]] == [
        '"call the bank" was due yesterday. Reply "done 1", "tomorrow" or "drop it".']
    assert tick_at(env, u(2026, 11, 18, 23, 30)) == 0                         # the other waits for the answer
    assert say(env, "drop it", no_model) == 'OK. I took "call the bank" off your list.'
    assert [t["text"] for t in bot.store.todos(H)] == ["post the letter"]
    assert tick_at(env, u(2026, 11, 18, 23, 31)) == 1
    assert last(ch) == '"post the letter" was due yesterday. Reply "done 1", "tomorrow" or "drop it".'
    # with no answer, the next one goes out 12 hours later (and never inside quiet hours)
    tue_todo(env, text="pay rent")
    tue_todo(env, text="water plants")
    tick_at(env, u(2026, 11, 17, 23, 2))
    env["clock"][0] = u(2026, 11, 18, 23, 40)
    bot.tick()
    first = last(ch)
    assert tick_at(env, u(2026, 11, 19, 3, 0)) == 0
    assert tick_at(env, u(2026, 11, 19, 13, 1)) == 1 and last(ch) != first


def test_two_reminders_for_two_things_of_one_post_each_send_their_own_thing(env, tmp_path):
    """The first reminder's send keeps only its thing with that post; the second must still send the second thing
    (it sent the first one again before the fix)."""
    opps(env, tmp_path)
    bot, ch = env["bot"], env["ch"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    say(env, "remind me about design jam on nov 28", {
        "intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}],
        "when": {"type": "once", "date": "2026-11-28", "time": "10:00"}})
    assert spec_of(rules(bot)[-1])["content"]["item_names"] == ["Design Jam"]
    env["clock"][0] = u(2026, 11, 27, 14, 1)
    assert bot.tick() == 1 and "NASA L'SPACE Academy" in last(ch)
    env["clock"][0] = u(2026, 11, 28, 15, 1)
    assert bot.tick() == 1
    assert last(ch).endswith("1. Design Jam: a weekend event for beginners") and "NASA" not in last(ch)


# ---------- finding 94: the opening line and the list score ----------
def test_the_opening_line_drops_every_grading_or_counting_word_before_the_kind():
    from mvp.render import found_noun
    assert found_noun("the best tools") == "tools"
    assert found_noun("top 5 tools") == "tools"
    assert found_noun("any other ui libraries in my saves") == "ui libraries"
    assert found_noun("some UI/UX libraries for my next project") == "UI/UX libraries"   # as before


def test_one_marked_line_or_a_quote_bracket_or_dots_is_not_a_list():
    from mvp.extract import list_score
    for none in ('"quote of the day"\n(not mine)', "...wait for it", "🔥 new video out now",
                 "[ad] my morning routine\nso calm"):
        assert list_score(none) == 0, none
    # emoji bullets and number emoji still count; a list of names on lines still counts
    assert list_score("My stack 👇\n🎨 Figma\n⚡ Framer\n🌐 Webflow") >= 3
    assert list_score("Top tools\n1️⃣ Notion\n2️⃣ Linear\n3️⃣ Raycast") >= 3
    assert list_score("Figma\nFramer\nWebflow\nSpline") >= 1


# ---------- live, 14 Nov: the two phrasings the model did not take ----------
def test_what_are_some_kind_of_thing_read_as_small_talk_is_an_ask():
    """Live: "what are some uiux libraries i should use for my next project" came back as chat (no search word)."""
    from mvp.interpret import chat_guard
    from mvp.schema import Interpretation

    def guard(t):
        return chat_guard(Interpretation(intent="chat", reply="x"), t)
    got = guard("what are some uiux libraries i should use for my next project")
    assert got.intent == "ask" and got.spec.content.goal == "some uiux libraries i should use for my next project"
    for ask in ("What are some UI/UX libraries", "what are the best tools for designers",
                "which ui library should i use for a dashboard", "suggest some productivity apps for me"):
        assert guard(ask).intent == "ask", ask
    # near-variants that stay small talk: a question about a pick, about the bot, or not a kind of thing
    for chat in ("which one should i pick", "which of these should i try first", "what are some things you can do",
                 "can you recommend some fonts for my site", "what is the best way to share my saves"):
        assert guard(chat).intent == "chat", chat


def test_until_ive_done_it_never_reaches_the_model_and_code_still_sets_it(env):
    """Live: with "until I've done it" in the message the model asked a question instead of making the reminder."""
    from mvp.followup import for_interpreter
    assert for_interpreter("remind me every morning at 8 to apply to the internship until I've done it") == \
        "remind me every morning at 8 to apply to the internship"
    assert for_interpreter("remind me daily to send the form until Friday, or until I've done it") == \
        "remind me daily to send the form until Friday"
    assert for_interpreter("every evening remind me to call the bank till I tick it off.") == \
        "every evening remind me to call the bank"
    for same in ("remind me every morning to stretch", "until further notice send me a recipe", "done"):
        assert for_interpreter(same) == same
    seen = []

    def model(user):
        seen.append(user)
        return {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI",
                                                                                   "SAT", "SUN"], "time": "08:00"},
                                               "content": {"source": "note", "text": "apply to the internship"}}}
    msg = say(env, "remind me every morning at 8 to apply to the internship until I've done it", model)
    assert seen and "until I've done it" not in seen[-1] and "apply to the internship" in seen[-1]
    w = spec_of(rules(env["bot"])[-1])["when"]
    assert w["stop_when"] == "done" and "until" not in w and "until you say done" in msg


# ---------- checker, round 8, understanding and integrations (DESIGN.md sections 14 and 15) ----------
from datetime import datetime, timedelta, timezone  # noqa: E402

from mvp.tests.test_round8_understanding import INTERESTS, day, lib8, pasta_asks, send, write_lib  # noqa: E402,F401
from mvp.tests.test_slice6 import AllPool  # noqa: E402

UTC = timezone.utc


def relations(bot):
    return {i["topic"]: i.get("relation") for i in bot.store.profile_data(H)["interests"]}


def test_a_label_lands_on_a_topic_stored_with_another_spelling_of_its_shown_name(lib8):
    """The theme check lists "blender 3D" for a stored "blender 3d"; '1 practise' used to store nothing and say only
    the other topics."""
    from mvp import profile as P
    bot = lib8["bot"]
    ints = [dict(i) for i in INTERESTS]
    ints[0]["topic"] = "blender 3d"
    P.set_interests(bot.store, H, ints)
    assert "1. blender 3D" in send(lib8, "what have I been into lately?")
    msg = send(lib8, "1 practise 2 enjoy")
    assert msg.startswith("Thanks, noted. blender 3D: a skill you're practising; Guitar: just for fun.")
    assert relations(bot)["blender 3d"] == "practise" and relations(bot)["Guitar"] == "enjoy"
    # near-variants: the exact stored name still wins, and a topic that is not stored is not labelled
    P.set_interests(bot.store, H, ints + [{"topic": "Blender 3D", "words": ["blender"], "source": "person"}])
    assert P.set_relations(bot.store, H, [("Blender 3D", "someday")]) == [("Blender 3D", "someday")]
    assert relations(bot)["Blender 3D"] == "someday" and relations(bot)["blender 3d"] is None
    assert P.set_relations(bot.store, H, [("Knitting", "someday")]) == []


def test_a_topic_starting_with_a_digit_can_be_relabelled(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    P.set_interests(bot.store, H, [{"topic": "3D printing", "words": ["printing"], "source": "guess"}])
    assert send(lib8, "3D printing is someday now") == "OK: 3D printing is parked for someday now."
    assert send(lib8, "3d printing is pursue now") == "OK: 3D printing is something you're going for now."
    assert lib8["calls"] == []
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hm."}
    assert send(lib8, "12 is someday now") == "Hm."              # a number alone is not a topic


def test_with_nothing_kept_before_no_topic_is_called_rising(env, tmp_path):
    """A library that starts lately: every topic with 5 posts used to be 'rising' against an empty earlier window."""
    from mvp import profile as P
    rows = [(f"a{k}", "instagram", f"Blender study {k}", {"save": day("2026-09-01", k)}, "none") for k in range(8)]
    rows += [(f"b{k}", "instagram", f"Guitar riff {k}", {"save": day("2026-09-20", k)}, "none") for k in range(6)]
    lib = write_lib(tmp_path / "new", rows)
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = AllPool(str(lib))
    P.set_interests(bot.store, H, [{"topic": "Blender", "words": ["blender"], "source": "guess"},
                                   {"topic": "Guitar", "words": ["guitar"], "source": "guess"}])
    msg = send(env, "what have I been into lately?")
    assert "rising" not in msg and "fading" not in msg
    assert "• Blender: too few to tell (8 posts that mention it lately, 0 before, 0 liked)." in msg
    # near-variant: one post kept before is enough to compare with, and a topic absent before then rises
    from mvp.attention import label
    assert label(8, 0, 14, 0) == "few" and label(8, 0, 14, 1) == "rising" and label(1, 12, 0, 40) == "fading"


def asks(e, goals, days=((0, 0), (0, 2), (1, 1))):
    e["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good.",
                                                                 "verdict": "clear"}]}
    base = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
    for (d, h), g in zip(days, goals):
        e["state"]["answers"]["mvp_interpret"] = lambda u, g=g: {"intent": "ask", "spec": {
            "when": {"type": "now"}, "content": {"goal": g, "searches": [g], "count": 1}}}
        e["clock"][0] = base + timedelta(days=d, hours=h)
        e["bot"].on_message(H, g)
    e["clock"][0] = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
    e["bot"]._arrivals.clear()   # many messages in one real minute: not the flood guard


def test_no_suggestion_from_asks_on_a_personal_topic_or_sharing_only_a_kind_word(env):
    """'dating advice' three times was offered as 'You asked about advice'; 'productivity tools', 'design tools' and
    'AI tools' were offered as one rule about tools."""
    bot = env["bot"]
    for goals in (["dating advice"] * 3, ["keto diet meals"] * 3, ["productivity tools", "design tools", "AI tools"],
                  ["career advice", "study advice", "travel advice"]):
        bot.store.x("DELETE FROM answers")
        bot.store.set_state(f"suggested:{H}", None)
        asks(env, goals)
        assert "You asked about" not in send(env, "recap"), goals
    # near-variants: a topic word is still offered, also when a kind word comes with it
    for goals, word in ((["lisbon cafes", "lisbon restaurants", "things to do in lisbon"], "lisbon"),
                        (["pasta tools", "pasta recipe", "pasta sauce"], "pasta")):
        bot.store.x("DELETE FROM answers")
        bot.store.set_state(f"suggested:{H}", None)
        asks(env, goals)
        assert f"• You asked about {word} 3 times since Thursday 12 November." in send(env, "recap"), goals


def test_the_suggestion_waits_while_a_rule_preview_waits_for_yes(env):
    """The handler reads 'yes' as YES to a waiting preview first: 'yes' to the suggestion used to start that other
    rule."""
    bot = env["bot"]
    pasta_asks(env)
    env["clock"][0] = datetime(2026, 11, 15, 15, 0, tzinfo=UTC)
    say(env, "every monday at 9 send me a workout", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["MON"], "times": ["09:00"]},
        "content": {"goal": "a workout", "searches": ["workout"], "count": 1}}})
    assert bot.store.pending(H)["kind"] == "confirm_rule"
    env["clock"][0] += timedelta(minutes=5)
    assert "You asked about" not in send(env, "recap")
    assert bot.store.get_state(f"suggested:{H}") is None           # not counted as offered: it comes next time
    send(env, "no")
    assert bot.store.rules(H) == [] and bot.store.pending(H) is None
    assert send(env, "recap").endswith("Reply \"yes\" and I'll show you a preview first.")
    assert send(env, "yes").startswith("Here's what that would look like now:")


def test_a_recap_of_posts_or_a_reminder_to_recap_is_not_the_recap_rule(env):
    from mvp.followup import RECAP_RULE
    for t in ("every friday send me a recap of new pasta recipes", "every sunday a recap of my saved recipes",
              "weekly recap of blender tutorials on mondays", "give me a recap of that video"):
        assert not RECAP_RULE.search(t), t
    for t in ("every sunday at 6pm send me a recap", "a recap of my week every monday", "recap of the week on sundays",
              "every week tell me how my rules did", "a weekly recap of my rules on fridays"):
        assert RECAP_RULE.search(t), t
    env["clock"][0] = datetime(2026, 11, 15, 15, 0, tzinfo=UTC)
    msg = say(env, "every sunday at 6pm remind me to recap my week in my journal", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["SUN"], "times": ["18:00"]},
        "content": {"source": "note", "text": "recap my week in my journal"}}})
    assert "recap like this one" not in msg
    stored = [r["spec"]["content"] for r in env["bot"].store.rules(H)]
    pending = (env["bot"].store.pending(H) or {}).get("payload", {}).get("spec", {}).get("content")
    assert all(c.get("source") == "note" for c in stored + ([pending] if pending else [])) and (stored or pending)


def test_my_rules_says_a_trends_rule_sends_with_each_export(lib8):
    """'my rules', the export's rules.json and the agent's my_rules said 'whenever you save something new that fits'."""
    import json as _json
    from mvp import config
    from mvp import export as X
    from mvp.mcp_server import Agent
    from mvp.tests.test_mcp import Pool
    send(lib8, "what have I been into lately")
    send(lib8, "every export")
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "list_rules"}
    want = "1. what you've been into lately: each time a new export of your library comes in"
    assert send(lib8, "my rules").split("\n")[1] == want
    rules, _ = X.rules_json(lib8["bot"].store, H)
    assert _json.loads(rules)[0]["when"] == "each time a new export of your library comes in"
    agent = Agent(H, db=config.DB, pool=Pool(), clock=lambda: lib8["clock"][0])
    assert want in agent.call("my_rules")
    # near-variant: a library rule that runs on new saves keeps its words
    lib8["bot"].store.add_rule(H, "new pasta", {"when": {"type": "new_items"}, "content": {
        "goal": "a pasta recipe", "searches": ["pasta"]}}, "active", None)
    assert "2. a pasta recipe: whenever you save something new that fits" in send(lib8, "my rules")
