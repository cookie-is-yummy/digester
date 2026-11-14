"""Offline tests for round 7, slice A (findings 90, 91 and 92; DESIGN.md section 12): answers that are the things the
posts name, with their post cited; the date of today and of each post; a follow-up that changes the request is a new
search. Synthetic data, a fake model, a fake search pool and a fake clock only (today is 12 Nov 2026 in New York)."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice6 import AllPool, number_of  # noqa: E402

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def code_for(day, seq=1):
    """An Instagram shortcode whose media id encodes `day` (noon UTC): (ms since 1314220021721) << 23, base 64."""
    ms = int(datetime.fromisoformat(day + "T12:00:00+00:00").timestamp() * 1000) - 1314220021721
    n = (ms << 23) | seq
    out = ""
    while n:
        n, r = divmod(n, 64)
        out = ALPHABET[r] + out
    return out


def ig(day, seq=1):
    return f"https://www.instagram.com/p/{code_for(day, seq)}/"


def write_lib(path, rows):
    """rows: (id, creator, caption, posted day or None, kept day, platform)."""
    (path / "corpus").mkdir(parents=True)
    with open(path / "corpus" / "items.jsonl", "w") as f:
        for i, (iid, who, cap, posted, kept, plat) in enumerate(rows, 1):
            url = ig(posted, i) if posted and plat == "instagram" else f"https://example.com/{iid}"
            pd = {"owner_handle": who, "owner_relation": "none"}
            if plat == "youtube":
                pd.update(video_id=f"vid{iid}", owner_name=who)
                url = f"https://www.youtube.com/watch?v=vid{iid}"
            f.write(json.dumps({"id": iid, "platform": plat, "source_url": url, "caption": cap,
                                "interaction_kinds": ["save"], "platform_data": pd}) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        for iid, _, _, _, kept, _ in rows:
            f.write(json.dumps({"item_id": iid, "kind": "save", "at": kept + "T10:00:00+00:00"}) + "\n")
    return path


def use_lib(env, tmp_path, rows, name="lib7"):
    lib = write_lib(tmp_path / name, rows)
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = AllPool(str(lib))
    env["lib"] = lib
    return env


def ask(goal, searches=None, **content):
    return {"intent": "ask", "spec": {"when": {"type": "now"}, "content": dict(
        {"goal": goal, "searches": searches or [goal], "count": 3}, **content)}}


def num(u, needle):
    """The candidate number of the item whose text (over several lines, for a video's description) holds `needle`."""
    import re
    for m in re.finditer(r"^(\d+)\. [^\n]*\n<item>(.*?)</item>", u, re.M | re.S):
        if needle.lower() in m.group(2).lower():
            return int(m.group(1))
    return number_of(u, needle)


def pick(u, needle, verdict="clear", title=None, **kw):
    return dict({"n": num(u, needle), "verdict": verdict, "title": title or needle}, **kw)


def items_fake(table, seen=None):
    """The details call: {needle in the post's text: {"items": [...], "key_points": [...]}}."""
    def answer(user):
        if seen is not None:
            seen.append(user)
        body = user.split("<item>", 1)[-1]
        for needle, out in table.items():
            if needle in body:
                kinds = json.loads(user.split("\n")[0][len("Kinds wanted: "):])
                return {k: v for k, v in out.items() if k in kinds}
        return {}
    return answer


# ---------- the UI/UX library request (finding 90) ----------
DS = ("Best design systems for UI/UX designers\n1. Material UI - Google's design system with React components\n"
      "2. Ant Design: an enterprise-class UI design language\n3. Chakra UI, simple and accessible components\n"
      "Save this for your next project")
ICONS = "High-quality icon sites\n- Iconoir: free open source icons\n- Lucide: beautiful consistent icons"
VIBES = "Design vibes and inspiration for a calm workspace"
UI_ROWS = [("d1", "designer", DS, "2023-06-20", "2023-07-02", "instagram"),
           ("d2", "iconfan", ICONS, "2022-09-01", "2022-09-15", "instagram"),
           ("d3", "vibes", VIBES, "2024-01-10", "2024-02-01", "instagram")]
UI_ITEMS = {
    "Best design systems": {"items": [
        {"name": "Material UI", "about": "Google's design system with React components", "when": "", "fit": "yes"},
        {"name": "Ant Design", "about": "an enterprise-class UI design language", "when": "", "fit": "unknown"},
        {"name": "Invented Kit", "about": "a library the post never names", "when": "", "fit": "yes"},
        {"name": "Chakra UI", "about": "simple and accessible components", "when": "", "fit": "unknown"}],
        "key_points": []},
    "High-quality icon sites": {"items": [
        {"name": "Iconoir", "about": "free open source icons", "when": "", "fit": "yes"},
        {"name": "lucide.com", "about": "beautiful consistent icons", "when": "", "fit": "yes"}], "key_points": []},
}
UI_ASK = "what are some uiux libraries i should use for my next project"


def ui_compose(u):
    return {"picks": [pick(u, "Best design systems", title="Best design systems",
                           because="it curates several design systems", facts=[{"label": "list",
                                                                                "quote": "Best design systems"}]),
                      pick(u, "High-quality icon sites", title="High-quality icon sites"),
                      pick(u, "Design vibes", "close", title="Design vibes")],
            "intro": "Here are the UI/UX libraries in your saves."}


@pytest.fixture()
def ui(env, tmp_path):
    use_lib(env, tmp_path, UI_ROWS)
    env["state"]["answers"]["mvp_compose"] = ui_compose
    env["seen_extract"] = []
    env["state"]["answers"]["mvp_extract"] = items_fake(UI_ITEMS, env["seen_extract"])
    return env


def test_90_a_question_for_things_is_answered_with_the_things_each_under_its_post(ui):
    msg = say(ui, UI_ASK, ask("UI/UX libraries", ["ui ux libraries", "design systems"]))
    assert "I recommend" not in msg and "because" not in msg
    assert msg.startswith("Here are the UI/UX libraries in your saves.")
    assert 'From "Best design systems" by @designer (posted June 2023, saved July 2023):' in msg
    assert "1. Material UI: Google's design system with React components" in msg
    assert "2. Ant Design: an enterprise-class UI design language" in msg
    assert "3. Chakra UI: simple and accessible components" in msg
    assert "Invented Kit" not in msg                             # a name the post's text does not hold is dropped
    assert 'From "High-quality icon sites" by @iconfan (posted September 2022, saved September 2022):' in msg
    assert "4. Iconoir: free open source icons" in msg
    assert "5. lucide: beautiful consistent icons" in msg and "lucide.com" not in msg   # a site by its name
    # every source is cited: its link goes alone after its list
    lines = msg.split("\n")
    assert lines.index(ig("2023-06-20", 1)) > lines.index("3. Chakra UI: simple and accessible components")
    assert lines.index(ig("2022-09-01", 2)) > lines.index("5. lucide: beautiful consistent icons")
    # the post with no named things is one line after them
    assert "Also in your saves:" in msg and "• Design vibes by @vibes" in msg
    # the details call got the request and today's date (and the post's date) and ran on the top 3 picks
    first = next(u for u in ui["seen_extract"] if "Best design systems" in u)
    assert '"items"' in first.split("\n")[0] and "Request: " in first and "Today: 2026-11-12" in first
    assert "Posted: 2023-06-20" in first
    assert sum(1 for c in ui["calls"] if c == "mvp_extract") == 3


def test_90_the_items_are_kept_with_the_answer_and_acted_on_by_number_and_by_name(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    run = bot.store.last_answer(H)["run_id"]
    kept = bot.store.answer(run)["picks"]
    assert [x["name"] for x in kept[0]["items"]] == ["Material UI", "Ant Design", "Chakra UI"]
    assert kept[0]["items"][1]["shown"] == "Ant Design: an enterprise-class UI design language"
    msg = say(ui, "add the second one to my to-do list", {"intent": "todo_add", "pick_number": 2})
    todos = bot.store.todos(H)
    assert todos[-1]["text"] == "Ant Design" and todos[-1]["url"] == ig("2023-06-20", 1)
    assert "Ant Design" in msg
    say(ui, "add iconoir to my list", {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {}}]})
    assert bot.store.todos(H)[-1]["text"] == "Iconoir" and bot.store.todos(H)[-1]["url"] == ig("2022-09-01", 2)
    msg = say(ui, "add the ninth one to my list", {"intent": "todo_add", "pick_number": 9})
    assert "listed 5 things" in msg


def test_90_email_it_to_me_after_an_items_answer_sends_the_whole_answer(ui, monkeypatch):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    bot.store.set_email(H, "me@example.com", verified=True)
    say(ui, "email it to me", {"intent": "act_on_last", "actions": [{"action": "email.send", "params": {}}]})
    row = bot.store.one("SELECT path FROM outbox WHERE handle=? AND kind='email' ORDER BY id DESC LIMIT 1", (H,))
    body = open(row["path"], encoding="utf-8").read()
    assert "Material UI: Google" in body and "Iconoir: free open source icons" in body


def test_90_a_rules_timed_send_is_an_items_answer_too(env, tmp_path):
    fonts = "Free fonts for designers\n- Inter: a clean sans serif\n- Lora: a calm serif for body text"
    use_lib(env, tmp_path, UI_ROWS + [("d4", "typo", fonts, "2026-08-01", "2026-08-03", "instagram")])
    table = dict(UI_ITEMS, **{"Free fonts": {"items": [{"name": "Inter", "about": "a clean sans serif"},
                                                       {"name": "Lora", "about": "a calm serif for body text"}]}})
    env["state"]["answers"]["mvp_extract"] = items_fake(table)

    def compose(u):   # whichever lists are still candidates, in this order
        return {"picks": [pick(u, k, title=k) for k in ("Best design systems", "High-quality icon sites",
                                                        "Free fonts for designers") if k in u][:2]}
    env["state"]["answers"]["mvp_compose"] = compose
    bot, clock = env["bot"], env["clock"]
    msg = say(env, "send me ui libraries every friday at 7pm", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["FRI"], "time": "19:00"},
        "content": {"goal": "UI/UX libraries", "searches": ["ui libraries"], "count": 2}}})
    assert "1. Material UI" in msg and "Reply YES" in msg
    say(env, "yes", {"intent": "confirm"})
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 1
    msg = last(env["ch"])
    assert 'From "Free fonts for designers" by @typo' in msg and "1. Inter: a clean sans serif" in msg
    assert "I recommend" not in msg and "\"pause 1\"" in msg


def test_90_an_item_reminder_later_sends_that_thing_alone(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot, clock = ui["bot"], ui["clock"]
    msg = say(ui, "remind me about chakra ui tomorrow at 9am", {
        "intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}],
        "when": {"type": "once", "date": "2026-11-13", "time": "09:00"}})
    assert "Chakra UI" in msg
    clock[0] = datetime(2026, 11, 13, 14, 1, tzinfo=timezone.utc)
    bot.tick()
    sent = last(ui["ch"])
    assert "Chakra UI: simple and accessible components" in sent and "Material UI" not in sent


def test_90_spanish_answers_still_work_with_items(ui):
    form = ask("librerías de UI/UX")
    form["lang"] = "es"
    ui["state"]["answers"]["mvp_compose"] = lambda u: dict(ui_compose(u), intro="")
    msg = say(ui, "¿qué librerías de ui ux debería usar?", form)
    assert 'De "Best design systems" de @designer' in msg and "1. Material UI" in msg
    assert "Also in your saves" not in msg and "posted" not in msg


def test_90_a_post_whose_text_names_nothing_keeps_the_present_answer(env, tmp_path):
    rows = [("m1", "coach", "Startup motivation: keep going when it gets hard", None, "2026-10-01", "instagram"),
            ("m2", "coach2", "Founder motivation reel, watch this when you doubt yourself", None, "2026-10-02",
             "instagram")]
    use_lib(env, tmp_path, rows)
    env["state"]["answers"]["mvp_compose"] = lambda u: {
        "picks": [pick(u, "Startup motivation", title="Startup motivation", because="it says to keep going",
                       facts=[{"label": "msg", "quote": "keep going when it gets hard"}]),
                  pick(u, "Founder motivation", title="Founder motivation reel")]}
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    form = ask("startup motivation reels")
    new = say(env, "send me startup motivation reels", form)
    # the same request with the details step of before (none for a request that is not a recipe or a tutorial)
    from mvp import executor
    import mvp.extract as X
    orig = executor.default_extract
    executor.default_extract = lambda spec, *t: []
    try:
        old = say(env, "send me startup motivation reels", form)
    finally:
        executor.default_extract = orig
    assert new == old and "I recommend Startup motivation" in new and "slides or video" not in new
    # a request that asks for things, with posts whose text names none: the plain line
    msg = say(env, "what tools should i use", ask("tools for founders"))
    assert "The details are in the post's slides or video, not in its text." in msg
    assert X.asks_for_things("what tools should i use")


def test_90_a_recipe_request_still_gets_ingredients_and_steps_and_a_reason(env, tmp_path):
    cap = ("One pot chicken and rice\nIngredients:\n- 2 cups rice\n- 1 lb chicken\nSteps:\n1. Brown the chicken.\n"
           "2. Add the rice and cook 20 minutes.")
    use_lib(env, tmp_path, [("r1", "cook", cap, "2025-01-05", "2025-02-01", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(
        u, "One pot chicken", title="One pot chicken and rice", because="it cooks in one pot",
        facts=[{"label": "pot", "quote": "One pot chicken and rice"}])]}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["2 cups rice", "1 lb chicken"],
                                                        "steps": ["Brown the chicken.", "Add the rice and cook 20 minutes."]}
    msg = say(env, "convenient chicken and rice recipes", ask("chicken and rice recipes"))
    assert "I recommend One pot chicken and rice by @cook, which you saved in February 2025, because it cooks in " \
           "one pot." in msg
    assert "Ingredients (2):" in msg and "Steps (2):" in msg and "From \"" not in msg


def test_90_the_item_checks():
    from mvp.extract import verify_items
    text = ("Programs for students:\nNASA L'SPACE Academy: a free program. NASA explicitly says prior experience is "
            "not required. Apply by December 1.\nGoogle STEP internship for first and second year students")
    items, dropped = verify_items([
        {"name": "NASA L'SPACE Academy", "about": "NASA explicitly says prior experience is not required.",
         "when": "December 1", "fit": "yes"},
        {"name": "Google STEP", "about": "internship for first and second year students", "fit": "unknown"},
        {"name": "Made Up Program", "about": "a free program", "fit": "yes"},          # not in the text
        {"name": "#students", "about": "", "fit": "yes"},                              # a hashtag is not a name
        {"name": "Google STEP", "about": "again"},                                     # once each
        {"name": "Old one", "fit": "no"},                                              # the text says it does not fit
        {"name": "NASA L'SPACE Academy 2"}, "a bare string"], text)
    assert [x["name"] for x in items] == ["NASA L'SPACE Academy", "Google STEP"]
    assert items[0]["about"] == "NASA explicitly says prior experience is not required." and \
        items[0]["when"] == "December 1"
    bad, _ = verify_items([{"name": "Google STEP", "about": "a paid program in Paris", "when": "May 5"}], text)
    assert bad == [{"name": "Google STEP", "about": "", "when": "", "fit": "unknown"}]   # never words it does not have
    assert verify_items("nonsense", text) == ([], 0)


# ---------- dates (finding 91) ----------
def test_91_the_instagram_shortcode_gives_the_posted_date():
    from mvp.dates import instagram_posted, shortcode_time
    for day in ("2014-03-02", "2019-11-30", "2024-05-17", "2026-11-01"):
        assert instagram_posted(ig(day)) == day
        assert instagram_posted(f"https://www.instagram.com/reel/{code_for(day)}/?igsh=abc") == day
    assert instagram_posted("https://example.com/p/abc") is None and shortcode_time("!!") is None
    long_code = code_for("2023-04-04") + "AbCdEfGhIjKlMnOpQrStUvWxYz012345678"    # a private link's long code
    assert instagram_posted(f"https://www.instagram.com/p/{long_code}/") == "2023-04-04"


def test_91_youtube_keeps_the_published_date():
    from mvp.ytinfo import parse
    got = parse({"items": [{"id": "v1", "snippet": {"description": "d", "publishedAt": "2024-02-03T10:00:00Z"},
                            "contentDetails": {"duration": "PT5M"}}]}, ["v1", "v2"])
    assert got["v1"] == (1, 300, "d", "2024-02-03T10:00:00Z") and got["v2"] == (0, None, "", None)


def test_91_dates_in_the_text_are_read_and_said_with_how_far_they_are():
    from datetime import date
    from mvp.dates import date_note, deadline_in, find_dates, state_of, time_sensitive
    today = date(2026, 11, 14)
    assert deadline_in("Applications close February 14, 2025.", "2024-12-01") == (date(2025, 2, 14), True)
    assert deadline_in("Apply by Jan 15", "2026-09-10") == (date(2027, 1, 15), True)   # the year after the post
    assert [d for d, _, _ in find_dates("Event on 3rd March 2026 and 2026-04-01")] == [date(2026, 3, 3),
                                                                                         date(2026, 4, 1)]
    st = state_of("Deadline: December 1", "2026-10-01", None, today)
    assert st["state"] == "open" and date_note(st, today) == "deadline 1 December (in 17 days)"
    st = state_of("applications close February 14, 2025", "2024-12-01", None, today)
    assert date_note(st, today) == "its deadline, 14 February 2025, has passed"
    st = state_of("Applications now open!", "2024-05-02", None, today)
    assert st["state"] == "old" and date_note(st, today).startswith("from May 2024, so this round has probably closed")
    assert state_of("Applications now open!", "2026-10-02", None, today)["state"] is None   # fresh: no note
    assert state_of("A calm morning routine", "2020-01-01", None, today)["state"] is None    # no date clue
    assert time_sensitive("what other opportunities might i have missed for 2026")
    assert time_sensitive("things with deadlines") and not time_sensitive("convenient chicken and rice recipes")


OPP = [("o1", "awards", "Design award 2025: applications close February 14, 2025", "2024-12-01", "2025-02-01",
        "instagram"),
       ("o2", "labs", "Summer research program for students: apply by December 1, 2026", "2026-10-01", "2026-10-05",
        "instagram"),
       ("o3", "grants", "Startup grant for founders, applications now open! Apply now", "2024-05-02", "2024-05-20",
        "instagram"),
       ("o4", "fellows", "Founder fellowship: applications open until January 15", "2026-09-10", "2026-09-12",
        "instagram")]


@pytest.fixture()
def opp(env, tmp_path):
    use_lib(env, tmp_path, OPP)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    return env


def test_91_a_passed_deadline_never_leads_and_a_fresh_one_does(opp):
    opp["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Design award", title="Design award 2025"), pick(u, "Summer research", title="Summer research program")]}
    msg = say(opp, "opportunities to apply for soon", ask("opportunities to apply for"))
    assert "I recommend Summer research program by @labs" in msg
    assert "Deadline 1 December (in 19 days)." in msg
    assert "Design award" not in msg          # passed, while something not passed fits
    # alone, it is shown, and says it has passed
    opp["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Design award", title="Design award 2025")]}
    msg = say(opp, "opportunities with deadlines", ask("opportunities with deadlines"))
    assert "Design award 2025" in msg and "Its deadline, 14 February 2025, has passed." in msg


def test_91_an_old_now_open_post_comes_last_with_its_date(opp):
    opp["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Startup grant", title="Startup grant for founders"),
        pick(u, "Founder fellowship", title="Founder fellowship")]}
    msg = say(opp, "startup opportunities to pursue soon", ask("startup opportunities"))
    assert "I recommend Founder fellowship by @fellows" in msg
    assert "Deadline 15 January 2027 (in 64 days)" not in msg and "15 January 2027" in msg
    assert "• Startup grant for founders by @grants: from May 2024, so this round has probably closed; check " \
           "whether it runs again." in msg


def test_91_a_year_in_the_request_prefers_posts_that_name_it(env, tmp_path):
    rows = [("y1", "hack", "Hackathon 2024 edition, sign up", "2023-01-05", "2023-01-06", "instagram"),
            ("y2", "hack2", "Hackathon 2026 edition, sign up", "2023-01-07", "2023-01-08", "instagram")]
    use_lib(env, tmp_path, rows)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Hackathon 2024", title="Hackathon 2024"),
                                                                  pick(u, "Hackathon 2026", title="Hackathon 2026")]}
    msg = say(env, "hackathons for 2026", ask("hackathons for 2026"))
    assert "I recommend Hackathon 2026" in msg


def test_91_a_reason_that_says_now_open_from_an_old_post_is_trimmed(opp):
    opp["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(
        u, "Startup grant", title="Startup grant for founders",
        because="it lists a startup grant for founders, and applications are now open",
        facts=[{"label": "grant", "quote": "Startup grant for founders"}])]}
    msg = say(opp, "startup grants", ask("startup grants"))
    assert "because it lists a startup grant for founders." in msg and "are now open" not in msg
    assert "It's from May 2024, so this round has probably closed; check whether it runs again." in msg
    # not time-sensitive, the same: a stale claim is never stated as current
    from mvp.answers import stale_reason
    from datetime import date
    assert stale_reason({"because": "it is new this week", "because_backed": True, "age_from": "2026-01-01"},
                        date(2026, 11, 12))
    assert not stale_reason({"because": "it is new this week", "because_backed": True, "age_from": "2026-11-01"},
                            date(2026, 11, 12))


def test_91_a_post_with_no_date_clue_keeps_the_composers_order(env, tmp_path):
    rows = [("n1", "a", "Internship tips for your resume", None, "2026-01-01", "instagram"),
            ("n2", "b", "Internship interview guide", None, "2026-02-01", "instagram")]
    use_lib(env, tmp_path, rows)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Internship tips", title="Internship tips", because="it has resume tips",
             facts=[{"label": "t", "quote": "tips for your resume"}]),
        pick(u, "Internship interview", "close", title="Internship interview guide")]}
    msg = say(env, "internship advice", ask("internship advice"))
    assert msg.index("Internship tips") < msg.index("Internship interview guide")
    assert "has passed" not in msg and "probably closed" not in msg and "Deadline" not in msg


def test_91_a_request_that_is_not_time_sensitive_is_unchanged_by_the_date_logic(env, tmp_path, monkeypatch):
    cap = "Rice cooker chicken and rice, new and ready in 30 minutes\nIngredients:\n- 2 cups rice\n- 1 lb chicken"
    use_lib(env, tmp_path, [("r1", "cook", cap, "2024-01-05", "2024-02-01", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(
        u, "Rice cooker chicken", title="Rice cooker chicken and rice", because="it is ready in 30 minutes",
        facts=[{"label": "time", "quote": "ready in 30 minutes"}])], "intro": "I found some chicken and rice recipes."}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["2 cups rice", "1 lb chicken"], "steps": []}
    msg = say(env, "convenient chicken and rice recipes", ask("chicken and rice recipes"))
    import mvp.answers as A
    import mvp.executor as X
    monkeypatch.setattr(A, "post_dates", lambda *a, **k: None)
    monkeypatch.setattr(X, "stale", lambda *a, **k: False)
    assert say(env, "convenient chicken and rice recipes", ask("chicken and rice recipes")) == msg
    assert "I recommend Rice cooker chicken and rice by @cook, which you saved in February 2024, because it is " \
           "ready in 30 minutes." in msg


def test_91_the_composer_is_told_today_and_each_candidates_dates(opp):
    seen = []
    opp["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    say(opp, "opportunities", ask("opportunities"))
    assert '"today": "2026-11-12"' in seen[0]
    assert "(kept 2026-10-05); posted 2026-10-01" in seen[0]


def test_91_items_of_an_old_list_say_their_dates(env, tmp_path):
    cap = ("Programs for students to apply to:\nNASA L'SPACE Academy: prior experience is not required, apply by "
           "December 1\nCity Lab summer fellowship: applications close March 3\nOld Grant: applications now open")
    use_lib(env, tmp_path, [("p1", "progs", cap, "2026-02-10", "2026-02-11", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Programs for students",
                                                                       title="Programs for students")]}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"items": [
        {"name": "City Lab summer fellowship", "about": "applications close March 3", "when": "March 3"},
        {"name": "NASA L'SPACE Academy", "about": "prior experience is not required", "when": "December 1"},
        {"name": "Old Grant", "about": "applications now open"}]}
    msg = say(env, "what opportunities might i have missed for 2026", ask("opportunities for 2026"))
    assert "1. NASA L'SPACE Academy: prior experience is not required (deadline 1 December, in 19 days)" in msg
    assert "City Lab" not in msg                       # 3 March 2026 has passed, and others have not
    assert "2. Old Grant: applications now open (as of February 2026)" in msg


# ---------- a follow-up that changes the request (finding 92) ----------
BLENDER = [("b1", "Blender Guru", "Beginner Blender 4.0 Tutorial", None, "2025-11-01", "youtube"),
           ("b2", "CG Cookie", "BLENDER BASICS 1 - Learn Blender", None, "2025-10-01", "youtube"),
           ("b3", "Blender Guru", "Blender 3.0 Beginner Tutorial - Part 1", None, "2025-09-01", "youtube"),
           ("b4", "polyfan", "Low poly island in Blender for beginners, a full tutorial", None, "2025-08-01",
            "instagram"),
           ("b5", "Grant Abbitt", "Blender beginner sword modelling tutorial", None, "2025-07-01", "youtube")]
DESC = {"vidb1": ("Part 1 of the donut series: we model a donut from start to finish", "PT17M57S"),
        "vidb2": ("Learn the interface and the basics", "PT7M18S"),
        "vidb3": ("Part 1 of making a donut in Blender 3.0", "PT25M"),
        "vidb5": ("Model a low poly sword", "PT24M")}


@pytest.fixture()
def blender(env, tmp_path, monkeypatch):
    use_lib(env, tmp_path, BLENDER)
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key-not-real")
    from mvp import ytinfo

    def fetch(ids, key, timeout=None):
        return {"items": [{"id": v, "snippet": {"description": DESC[v][0], "publishedAt": "2024-01-01T00:00:00Z"},
                           "contentDetails": {"duration": DESC[v][1]}} for v in ids if v in DESC]}
    monkeypatch.setattr(ytinfo, "fetch_batch", fetch)
    import mvp.config as C
    monkeypatch.setattr(C, "OUTSIDE_ON", False)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    env["seen"] = []

    def compose(u):   # the beginner videos first, whichever are candidates
        env["seen"].append(u)
        order = ["Beginner Blender 4.0", "BLENDER BASICS", "Blender 3.0 Beginner", "Low poly island", "sword"]
        return {"picks": [pick(u, k, title=k) for k in order if k in u.split("Candidates:")[-1]][:3],
                "intro": "I found some basic Blender tutorials in your saves."}
    env["state"]["answers"]["mvp_compose"] = compose
    say(env, "could you find me some basic blender tutorials", ask("basic Blender tutorials", ["blender basics"]))
    return env


def shown_ids(env):
    return env["bot"].store.last_answer(H)["items"]


def test_92_a_follow_up_that_rules_something_out_is_a_new_search(blender):
    assert shown_ids(blender)[:3] == ["b1", "b2", "b4"]   # (b3 is the lead's own kind of video: last, left out)
    n_runs = blender["bot"].store.one("SELECT COUNT(*) n FROM runs WHERE kind='ask'")["n"]
    msg = say(blender, "what about something that isnt a donut.",
              {"intent": "follow_up", "question": "What about something that isn't a donut?", "avoid": ["donut"]})
    assert blender["bot"].store.one("SELECT COUNT(*) n FROM runs WHERE kind='ask'")["n"] == n_runs + 1   # a search
    assert msg.startswith("Here's what else I found in your saves for basic Blender tutorials, leaving out anything "
                          "about donut.")
    assert "isn't a donut" not in msg and "isnt a donut" not in msg   # never the message quoted back
    ids = shown_ids(blender)
    assert "b1" not in ids and "b3" not in ids and ids[0] == "b2"   # the donut videos, by their descriptions
    view = blender["bot"].view(str(blender["lib"]))
    from mvp.compose import own_text
    extra = blender["bot"]._youtube().details([view.get(i) for i in ids])
    assert not any("donut" in own_text(view.get(i), extra).lower() for i in ids)
    assert "donut" not in blender["seen"][-1].split("Candidates:")[-1].lower()   # never reached the composer


def test_92_the_question_reader_and_the_avoid_words():
    from mvp.followup import avoid_words, request_change
    from mvp.schema import Interpretation
    q = Interpretation(intent="follow_up", question="x")
    assert request_change(q, "how long is the second one?") is None
    assert request_change(q, "which is easiest?") is None
    assert request_change(q, "does it need an oven?") is None
    assert avoid_words("what about something that isnt a donut.") == ["donut"]
    assert avoid_words("something without any cheese") == ["cheese"]
    ch = request_change(q, "not from that creator")
    assert ch["creator"] and not ch["avoid"]
    assert request_change(q, "something shorter")["shorter"]
    assert request_change(q, "anything else?")["others"]
    assert request_change(q, "more recent ones")["newest"]
    assert request_change(q, "on instagram instead")["platform"] == "instagram"
    assert request_change(Interpretation(intent="follow_up", question="x", avoid=["cream"]), "any without cream?")


def test_92_how_long_is_the_second_one_stays_a_question_about_the_picks_shown(blender):
    n_runs = blender["bot"].store.one("SELECT COUNT(*) n FROM runs WHERE kind='ask'")["n"]
    say(blender, "how long is the second one?", {"intent": "follow_up", "question": "how long is the second one?",
                                                  "pick_number": 2})
    assert blender["bot"].store.one("SELECT COUNT(*) n FROM runs WHERE kind='ask'")["n"] == n_runs
    assert blender["bot"].store.one("SELECT kind FROM runs ORDER BY id DESC LIMIT 1")["kind"] == "follow_up"


def test_92_not_from_that_creator_leaves_the_creator_out(blender):
    msg = say(blender, "not from that creator", {"intent": "follow_up", "question": "not from that creator"})
    ids = shown_ids(blender)
    assert "b1" not in ids and "b3" not in ids                 # both by the lead's creator
    assert "not from Blender Guru" in msg


def test_92_something_shorter_bounds_the_length(blender):
    msg = say(blender, "something shorter", {"intent": "follow_up", "question": "something shorter"})
    ids = shown_ids(blender)
    assert ids[0] == "b2"                                       # 7 minutes; the 17- and 25-minute ones are not clear
    assert "shorter ones" in msg.split("\n")[0]


def test_92_anything_else_leaves_out_what_was_shown(blender):
    before = set(shown_ids(blender))
    say(blender, "anything else?", {"intent": "follow_up", "question": "anything else?"})
    ids = shown_ids(blender)
    assert ids and not set(ids) & before


def test_92_a_change_with_nothing_left_says_so_and_never_shows_a_rejected_pick(blender):
    msg = say(blender, "what about something with no donut, no basics, no island and no sword",
              {"intent": "follow_up", "question": "something else", "avoid": ["donut", "basics", "island", "sword"]})
    assert msg.startswith("I found nothing else in your saves for basic Blender tutorials, leaving out anything "
                          "about donut, basics, island and sword.")
    assert "youtube.com" not in msg and "I recommend" not in msg


# ---------- the short opening line, and dates in timed sends ----------
def test_round7_the_fallback_opening_line_never_echoes_a_long_request(opp):
    opp["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Summer research", title="Summer research")]}
    long_goal = "startup motivation related reels, opportunities to pursue soon, or things with deadlines"
    msg = say(opp, "send me " + long_goal, ask(long_goal))
    assert msg.startswith("Here's what I found in your saves.\n") and long_goal not in msg
    msg = say(opp, "research programs", ask("research programs"))
    assert msg.startswith("Here's what I found in your saves for research programs.")


def test_91_a_rules_timed_send_never_leads_with_a_passed_deadline(opp):
    bot, clock = opp["bot"], opp["clock"]

    def compose(u):
        return {"picks": [pick(u, k, title=k) for k in ("Design award", "Summer research") if k in u][:1] +
                [pick(u, k, title=k) for k in ("Design award", "Summer research") if k in u][1:2]}
    opp["state"]["answers"]["mvp_compose"] = compose
    say(opp, "every friday send me opportunities with deadlines", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["FRI"], "time": "19:00"},
        "content": {"goal": "opportunities with deadlines", "searches": ["opportunities"], "count": 1}}})
    preview = last(opp["ch"])
    assert "Summer research" in preview and "Design award" not in preview
    assert "Deadline 1 December (in 19 days)." in preview
