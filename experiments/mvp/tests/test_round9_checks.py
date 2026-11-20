"""Offline tests for the check of round 9, slice U (DESIGN.md section 12, "Round 9, slice U", the checker's part):
what the checker found wrong in the slice and fixed. Synthetic posts with made-up names, a fake model, a fake search
pool and a fake clock (today is 12 Nov 2026 in New York)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round8_live import NOW, ROUNDUP, ROWS98, TABLE98, TABLE99, compose98  # noqa: E402
from mvp.tests.test_slice2 import say  # noqa: E402


# ---------- the read order: a title that names the request's year stays first among the candidates ----------
def year_lib(env, tmp_path, year_text, name="libyear"):
    rows = [("m1", "chances", NOW, "2026-08-20", "2026-08-21", "instagram")] + \
        [(f"r{n}", f"lists{n}", ROUNDUP.format(n=n), "2026-08-01", "2026-08-02", "instagram") for n in range(1, 7)] + \
        [("q1", "summerlist", year_text, "2026-07-02", "2026-07-03", "instagram")]
    use_lib(env, tmp_path, rows, name=name)
    seen = []
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE99, seen)
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Student programmes worth a look", title="Student programmes")]}
    return seen


def read_texts(seen):
    return [u.split("<item>", 1)[-1] for u in seen]


def test_c1_a_year_title_without_the_kind_word_is_still_read_before_lists_that_name_the_kind(env, tmp_path):
    # six lists say "opportunities" (the kind's word); the year post does not: before the fix it was never read
    seen = year_lib(env, tmp_path, "Summer 2027 job list\nfor students, by @someone")
    say(env, "opportunities for next summer", ask("opportunities for next summer", ["summer opportunities"]))
    texts = read_texts(seen)
    assert len(texts) == 6 and any("Summer 2027 job list" in t for t in texts)


def test_c1_near_variants_keep_their_read_order(env, tmp_path):
    # with the kind word in its text, as in round 8 (finding 102)
    seen = year_lib(env, tmp_path, "Summer 2027 job list\nopportunities for students, by @someone")
    say(env, "opportunities for next summer", ask("opportunities for next summer", ["summer opportunities"]))
    assert any("Summer 2027 job list" in t for t in read_texts(seen))
    # a request with no year or season: the year post is not read before the lists
    seen.clear()
    say(env, "other opportunities", ask("other opportunities", ["opportunities"]))
    assert not any("Summer 2027 job list" in t for t in read_texts(seen))
    # a title naming another year is not first either
    seen = year_lib(env, tmp_path, "Summer 2024 job list\nfor students, by @someone", name="libyear2")
    say(env, "opportunities for next summer", ask("opportunities for next summer", ["summer opportunities"]))
    assert not any("Summer 2024 job list" in t for t in read_texts(seen))


# ---------- one of a kind: each kind in "places or cafes" takes the singular ----------
def test_c2_a_count_of_one_takes_the_singular_of_each_kind():
    from mvp.render import one_of
    assert one_of("places or cafes") == "place or cafe"
    assert one_of("tools and resources") == "tool and resource"
    assert one_of("Places & Cafes") == "Place & Cafe"
    # near-variants: one kind, and a part before the last one that is not a kind word
    assert one_of("UI/UX libraries") == "UI/UX library" and one_of("fonts") == "font" and one_of("boxes") == "box"
    assert one_of("rice and beans recipes") == "rice and beans recipe"


def test_c2_the_opening_line_says_one_place_or_cafe(env, tmp_path):
    use_lib(env, tmp_path, ROWS98, name="libc2")
    env["state"]["answers"]["mvp_compose"] = compose98
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE98)
    msg = say(env, "places or cafes i could go to", ask("places or cafes i could go to", ["places", "cafes"]))
    assert msg.startswith("I found 1 place or cafe in your saves, and 2 posts that come close.\n")
    assert "places or cafe " not in msg


# ---------- the chat guard: "what <kind> should I ..." needs the kind right after "what"; its asking words go ----------
def guard(t):
    from mvp.interpret import chat_guard
    from mvp.schema import Interpretation
    return chat_guard(Interpretation(intent="chat", reply="Which phone do you use?"), t)


def test_c4_what_day_should_i_is_a_question_not_a_search():
    for t in ("what day should i post my reels", "what song should i post with my reel",
              "what color should i paint my room", "what time should i post my videos"):
        assert guard(t).intent == "chat", t


def test_c4_the_goal_leaves_out_every_asking_verb():
    assert guard("what courses can i take for free").spec.content.goal == "courses for free"
    assert guard("what workout should i do today").spec.content.goal == "workout today"
    assert guard("what podcasts could i listen to on long drives").spec.content.goal == "podcasts on long drives"
    # near-variants kept from slice U and round 8
    assert guard("what apps should i use to edit photos on my phone").spec.content.goal == \
        "apps to edit photos on my phone"
    assert guard("what productivity apps should i try").spec.content.goal == "productivity apps"
    assert guard("which tools should i use for video editing").spec.content.goal == "tools for video editing"
    for t in ("what should i cook tonight", "what kind of apps should i use", "what apps should i delete from my phone"):
        assert guard(t).intent == "chat", t
