"""Offline tests for the check of round 9, slice U2 (DESIGN.md section 12, "Round 9, slice U2", its checker's part).
Synthetic posts with made-up names, a fake model, a fake search pool and a fake clock only."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round8_checks import old_and_fresh  # noqa: E402
from mvp.tests.test_round9_judge import judge_on  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

PROGS = "student programs to apply for"


def progs(env, tmp_path, monkeypatch, verdicts, fresh="close", text=PROGS, searches=("student programs",)):
    old_and_fresh(env, tmp_path, fresh_verdict=fresh)
    judge_on(env, monkeypatch, verdicts)
    return say(env, text, ask(text, list(searches)))


# ---------- 1. with the judge, an old round never leads a fresher post (round 7 and round 8 rules) ----------
def test_c2_with_the_judge_an_old_round_never_leads_a_fresher_post(env, tmp_path, monkeypatch):
    """The judge's sort put the composer's verdict before 'old after everything fresher': a 2024 post the composer
    judged clear, whose rounds have probably closed, led a post with two deadlines ahead."""
    msg = progs(env, tmp_path, monkeypatch, {"Cedar Lab": "yes", "Birch Fund": "yes", "Maple Grant": "unsure",
                                             "Aspen Lab": "unsure"})
    assert msg.startswith('Nothing I found is a clear fit for "student programs".\nThese come closest:\n')
    assert msg.index("1. Maple Grant") < msg.index("3. Cedar Lab")
    # near-variant: every verdict unsure, the same order
    msg = progs(env, tmp_path / "b", monkeypatch, {n: "unsure" for n in ("Cedar Lab", "Birch Fund", "Maple Grant",
                                                                        "Aspen Lab")})
    assert msg.index("1. Maple Grant") < msg.index("3. Cedar Lab")
    # near-variant: the fresh post's things are the kind: it is counted and the old one comes close (unchanged)
    msg = progs(env, tmp_path / "c", monkeypatch, {n: "yes" for n in ("Cedar Lab", "Birch Fund", "Maple Grant",
                                                                     "Aspen Lab")})
    assert msg.startswith("I found 2 student programs in your saves, and one post that comes close.\n")
    assert msg.index("1. Maple Grant") < msg.index("Close, but not quite") < msg.index("3. Cedar Lab")


def test_c2_with_the_judge_two_posts_that_count_keep_the_composers_order_when_not_time_sensitive(
        env, tmp_path, monkeypatch):
    # a request that is not time-sensitive: no post is stale, so among the posts that do not count the composer's
    # clear one still comes first (the judge's order of point 3)
    msg = progs(env, tmp_path, monkeypatch, {n: "unsure" for n in ("Cedar Lab", "Birch Fund", "Maple Grant",
                                                                  "Aspen Lab")}, text="student club ideas",
                searches=("student club ideas",))
    assert msg.index("Cedar Lab") < msg.index("Maple Grant")


# ---------- 2. the opening line counts the kind the judge judged ----------
TEX = [("w1", "tex", "Free texture sites\n- Polyvault: free PBR textures for any render\n- Texwell: scanned textures, "
        "free for any use\n- Grainy: a pack of 40 grain overlays", "2026-10-01", "2026-10-02", "instagram")]
TEX_TABLE = {"Free texture sites": {"items": [
    {"name": "Polyvault", "about": "free PBR textures for any render", "fit": "yes"},
    {"name": "Texwell", "about": "scanned textures, free for any use", "fit": "yes"},
    {"name": "Grainy", "about": "a pack of 40 grain overlays", "fit": "yes"}]}}


def tex(env, tmp_path, monkeypatch, verdicts, seen=None, verdict="clear"):
    use_lib(env, tmp_path, TEX, name="tex")
    env["state"]["answers"]["mvp_extract"] = items_fake(TEX_TABLE)
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Free texture sites", verdict, title="Texture sites")]}
    judge_on(env, monkeypatch, verdicts, seen)


def test_c2_the_opening_line_names_the_kind_the_things_were_judged_against(env, tmp_path, monkeypatch):
    """'what websites have free textures for my renders': the judge judged "websites" and the line said 'I found 2
    free textures' (the goal's grammar)."""
    seen = []
    tex(env, tmp_path, monkeypatch, {"Polyvault": "yes", "Texwell": "yes", "Grainy": "no"}, seen)
    msg = say(env, "what websites have free textures for my renders",
              ask("free textures for my renders", ["free textures"]))
    assert 'Kind asked for: "websites"' in seen[0]
    assert msg.startswith("I found 2 websites named in one of your saves.\n")
    assert "Grainy" not in msg
    # near-variant: with nothing clear, the closest line names the same kind
    tex(env, tmp_path / "b", monkeypatch, {"Polyvault": "no", "Texwell": "no", "Grainy": "no"})
    msg = say(env, "what websites have free textures for my renders",
              ask("free textures for my renders", ["free textures"]), )
    assert msg.startswith('Nothing I found is a clear fit for "websites".\n')
    # near-variant (live): a goal that is only the kind, which the word list lacks, said "I found 2 things"
    tex(env, tmp_path / "c", monkeypatch, {"Polyvault": "yes", "Texwell": "yes", "Grainy": "no"})
    msg = say(env, "what are some texture packs i should get", ask("texture packs", ["texture packs"]))
    assert msg.startswith("I found 2 texture packs named in one of your saves.\n")


def test_c2_the_opening_line_is_unchanged_when_the_goal_names_the_kind(env, tmp_path, monkeypatch):
    # the goal names the kind with a word of the list: its own phrase, as before
    tex(env, tmp_path, monkeypatch, {"Polyvault": "yes", "Texwell": "yes", "Grainy": "no"})
    msg = say(env, "what are some free texture websites", ask("free texture websites", ["free textures"]))
    assert msg.startswith("I found 2 free texture websites named in one of your saves.\n")
    # the goal's grammar names the kind the message names too ("games"): the same word
    tex(env, tmp_path / "b", monkeypatch, {"Polyvault": "yes", "Texwell": "yes", "Grainy": "no"})
    msg = say(env, "what games should i play with friends", ask("games to play with friends", ["games"]))
    assert msg.startswith("I found 2 games named in one of your saves.\n")
    # no judge (off): the same noun rule
    from mvp import config
    tex(env, tmp_path / "c", monkeypatch, None)
    monkeypatch.setattr(config, "JUDGE_MODEL", "")
    msg = say(env, "what websites have free textures for my renders",
              ask("free textures for my renders", ["free textures"]))
    assert msg.startswith("I found 3 websites named in one of your saves.\n")


def test_c2_the_noun_rule_reads_the_kind_kept_with_the_answer():
    from types import SimpleNamespace

    from mvp.render import kind_noun
    spec = SimpleNamespace(content=SimpleNamespace(goal="free textures for my renders"))
    assert kind_noun({"kind": "websites"}, spec) == "websites"
    assert kind_noun({}, spec) == "free textures"                    # no kind kept: the goal's grammar as before
    spec.content.goal = "UI/UX libraries for my next project"
    assert kind_noun({"kind": "UI/UX libraries"}, spec) == "UI/UX libraries"
    assert kind_noun({"kind": "tools"}, spec) == "UI/UX libraries"    # the goal's word-list phrase still comes first


# ---------- 3. a verdict the judge's form left out is not cached ----------
def test_c2_a_thing_the_form_left_out_is_judged_again_next_time(env, tmp_path, monkeypatch):
    """A number missing from the form was cached as "unsure", so a repeat never asked again and the small model's
    "yes" stood for good."""
    seen = []
    tex(env, tmp_path, monkeypatch, {"Polyvault": "yes", "Texwell": "yes"}, seen)    # Grainy left out of the form
    first = say(env, "what websites have free textures", ask("websites with free textures", ["free textures"]))
    assert "Grainy" in first    # unsure this time: the small model's fit stands
    judge_on(env, monkeypatch, {"Polyvault": "yes", "Texwell": "yes", "Grainy": "no"}, seen)
    msg = say(env, "what websites have free textures", ask("websites with free textures", ["free textures"]))
    assert env["calls"].count("mvp_judge") == 2 and len(seen) == 2
    body = seen[1].split("<item>", 1)[1].split("</item>", 1)[0]
    assert body.startswith("1. Grainy") and "Polyvault" not in body    # only the one left out is asked again
    assert "Grainy" not in msg
    steps = json.loads(env["bot"].store.q("SELECT steps FROM runs WHERE handle=? ORDER BY id DESC LIMIT 1",
                                          (H,))[0]["steps"])
    assert steps["judge"]["cached"] == 2 and steps["judge"]["calls"] == 1
    # near-variant: every number answered: a repeat costs nothing
    say(env, "what websites have free textures", ask("websites with free textures", ["free textures"]))
    assert env["calls"].count("mvp_judge") == 2
