"""Offline tests for the privacy review fixes (PRIV-1 to PRIV-11). Synthetic data and fakes only: no model calls, no
network, no real library."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.test_mvp import env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice5 import drop, fake_prepare, fresh, yt  # noqa: E402,F401


def _lib(d, items, inter):
    os.makedirs(os.path.join(d, "corpus"), exist_ok=True)
    with open(os.path.join(d, "corpus", "items.jsonl"), "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    with open(os.path.join(d, "corpus", "interactions.jsonl"), "w") as f:
        for r in inter:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(d, "library.json"), "w") as f:
        json.dump({"counts": {}}, f)


def _ig(iid, owner, rel, kinds=("save",)):
    return {"id": iid, "platform": "instagram", "source_url": f"https://example.com/{iid}", "caption": f"post {iid}",
            "interaction_kinds": list(kinds), "platform_data": {"owner_handle": owner, "owner_relation": rel}}


# ---------- PRIV-1: a share whose owner became a friend never comes back ----------
def test_priv1_a_carried_share_whose_owner_is_now_mutual_is_left_out(env, tmp_path):
    from mvp import refresh
    from mvp.libview import LibraryView
    old, new = str(tmp_path / "old"), str(tmp_path / "new")
    _lib(old, [_ig("s1", "pal", "following", ["share_self"]), _ig("s2", "baker", "following", ["share_self"])],
         [{"item_id": "s1", "kind": "share_self", "at": "2026-01-01T00:00:00+00:00"},
          {"item_id": "s2", "kind": "share_self", "at": "2026-01-02T00:00:00+00:00"}])
    _lib(new, [_ig("n1", "pal", "mutual")], [{"item_id": "n1", "kind": "save", "at": "2026-02-01T00:00:00+00:00"}])
    got = refresh.carry_over(old, new, {"instagram"})
    assert got["shares"] == 1                       # only @baker's share comes over
    view = LibraryView(new)
    assert "s1" not in view.items and "s2" in view.items
    # with the new export's lists: @baker is now a friend too, @pal is only followed
    _lib(new, [], [])
    got = refresh.carry_over(old, new, {"instagram"}, graph=({"baker"}, {"baker", "pal"}))
    rows = [json.loads(x) for x in open(os.path.join(new, "corpus", "items.jsonl"))]
    assert [r["id"] for r in rows] == ["s1"] and rows[0]["platform_data"]["owner_relation"] == "following"
    inter = [json.loads(x) for x in open(os.path.join(new, "corpus", "interactions.jsonl"))]
    assert [r["item_id"] for r in inter] == ["s1"]


def test_priv1_an_import_uses_the_new_exports_followers_lists(fresh, tmp_path):
    """The synthetic export lists sample_pal as a follower and followed (a friend). An old share of theirs, marked
    'following' in the old library, is not carried into the new one."""
    bot = fresh["bot"]
    lib = fresh["lib"]
    with open(lib / "corpus" / "items.jsonl", "a") as f:
        f.write(json.dumps(_ig("old_share", "sample_pal", "following", ["share_self"])) + "\n")
        f.write(json.dumps(_ig("old_share2", "synthetic_baker", "none", ["share_self"])) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "a") as f:
        f.write(json.dumps({"item_id": "old_share", "kind": "share_self", "at": "2026-01-01T00:00:00+00:00"}) + "\n")
        f.write(json.dumps({"item_id": "old_share2", "kind": "share_self", "at": "2026-01-01T00:00:00+00:00"}) + "\n")
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    new = bot.store.person(H)["library"]
    assert new != str(lib)
    rows = {json.loads(x)["id"]: json.loads(x) for x in open(os.path.join(new, "corpus", "items.jsonl"))}
    assert "old_share" not in rows
    assert rows["old_share2"]["platform_data"]["owner_relation"] == "following"   # set again from the new lists


# ---------- PRIV-4: religious observances, named conditions and gender words are never inferred or searched ----------
SENSITIVE_TOPICS = ["Ramadan iftar recipes", "Halal street food", "Kosher baking", "Shabbat dinners", "Eid outfits",
                    "Diwali sweets", "PCOS-friendly meals", "Menopause workouts", "Endometriosis recipes",
                    "HIV awareness", "Bipolar journaling", "OCD tips", "PTSD recovery", "IBS-friendly dinners",
                    "Celiac baking", "Nonbinary fashion", "Non-binary style"]
HARMLESS_TOPICS = ["Quick dinners", "Blender 3D", "Lentil soup", "Gluten-free baking", "Street food", "Fashion",
                   "Desserts", "Journaling", "Home workouts", "Ocean photography"]


def test_priv4_the_profile_check_removes_observances_conditions_and_gender_words(env):
    from mvp import profile
    for t in SENSITIVE_TOPICS:
        assert profile.sensitive(t), t
    for t in HARMLESS_TOPICS:
        assert not profile.sensitive(t), t


def test_priv4_a_guessed_sensitive_topic_is_not_kept_for_the_read(env):
    from mvp import profile
    from mvp.libview import LibraryView
    view = LibraryView(str(env["lib"]))
    items = [it for it in view.items.values() if it.platform == "instagram"]
    raw = {"topics": [{"topic": "Ramadan iftar recipes", "items": ["S1", "S2"], "words": ["pasta"]},
                      {"topic": "PCOS-friendly meals", "items": ["S1", "S2"], "words": ["pasta"]}]}
    interests, removed = profile.check_guess(raw, items, [], view)
    assert interests == [] and removed == 2


def test_priv4_the_outside_search_stops_for_the_same_words(env):
    from mvp import outside
    for q in ["pcos meal prep", "ramadan recipes", "iftar ideas", "eid outfits", "endometriosis friendly dinners",
              "kosher desserts", "halal recipes", "non-binary fashion", "celiac baking", "ibs dinners"]:
        assert outside.sensitive_topic([q]), q
    for q in ["lentil soup", "quick dinners", "gluten free baking", "street food", "blender donut"]:
        assert outside.sensitive_topic([q]) is None, q


# ---------- PRIV-5: "delete my data" leaves no export, no unnamed library and no handle-keyed traces ----------
def test_priv5_delete_removes_the_inbox_names_every_library_and_clears_traces(fresh):
    from mvp import config, llm
    bot, st = fresh["bot"], fresh["bot"].store
    old_lib = st.person(H)["library"]
    bot.refresher.prepare = fake_prepare(ok=False)          # a failed build: the export goes to .failed
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    assert os.listdir(os.path.join(fresh["inbox"], ".failed"))
    bot.refresher.prepare = fake_prepare()
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    new_lib = st.person(H)["library"]
    assert new_lib != old_lib
    rid = st.add_rule(H, "pasta every friday at 7pm", pasta_spec(), "active", None)
    st.set_state(f"outside_auto:{H}", {"day": "2026-11-12", "topics": [["sourdough", "starter"]]})
    st.set_state(f"retry:{rid}", 2)
    st.set_state(f"hold:{rid}", {"x": 1})
    st.set_state(f"something_new:{H}", 1)
    st.facts_put(new_lib, "x1", "steps", ["a line"], "extract_v1")
    st.facts_put(old_lib, "x2", "steps", ["a line"], "extract_v1")
    st.cache_put("ranked_cache", "k", ["x1"], library=new_lib, mode="normal")
    st.x("INSERT INTO profile_guess(key,library,result,at) VALUES('g1',?,'{}','2026-11-12')", (old_lib,))
    with open(llm.ai.LEDGER, "a") as f:   # a row from before the ledger used a hashed ref
        f.write(json.dumps({"purpose": "mvp_compose", "person": H, "cost_usd": 0.001}) + "\n")
    os.makedirs(os.path.join(fresh["inbox"], ".working", "x"), exist_ok=True)
    say(fresh, "delete my data", {"intent": "delete_data"})
    say(fresh, "yes", {"intent": "confirm"})
    assert st.person(H) is None
    assert not os.path.exists(fresh["inbox"])                                   # the raw exports, .failed included
    for key in (f"outside_auto:{H}", f"retry:{rid}", f"hold:{rid}", f"something_new:{H}"):
        assert st.get_state(key) is None, key
    for t in ("facts", "ranked_cache", "profile_guess"):
        assert st.one(f"SELECT COUNT(*) n FROM {t}")["n"] == 0, t
    marks = [json.loads(x) for x in open(os.path.join(config.HOME, "deletions.jsonl"))]
    assert len(marks) == 1 and set(marks[0]["libraries"]) == {os.path.abspath(new_lib), os.path.abspath(old_lib)}
    assert marks[0]["ledger_rows_with_handle"] == 1
    # every row the MVP itself wrote names a hashed ref, never the handle
    rows = [json.loads(x) for x in open(llm.ai.LEDGER)]
    assert sum(1 for r in rows if r.get("person") == H) == 1                     # only the old row above
    assert any(r.get("person") == llm.person_ref(H) for r in rows)
    assert llm.person_ref(H) != H and llm.person_ref(H) == llm.person_ref(H)


def test_priv5_the_daily_cap_still_counts_hashed_and_old_rows(tmp_path, monkeypatch):
    from datetime import datetime
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp import llm                       # not stubbed here: the real spent_today
    day = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    os.makedirs(llm.LEDGER_HOME, exist_ok=True)
    with open(llm.ai.LEDGER, "a") as f:
        f.write(json.dumps({"at": day, "person": H, "cost_usd": 0.25}) + "\n")
        f.write(json.dumps({"at": day, "person": llm.person_ref(H), "cost_usd": 0.5}) + "\n")
        f.write(json.dumps({"at": day, "person": llm.person_ref("+15559999"), "cost_usd": 9}) + "\n")
    assert abs(llm.spent_today(H, str(tmp_path / "nolib")) - 0.75) < 1e-9
    assert llm.person_ref(H).startswith("p-") and "5550001" not in llm.person_ref(H)


# ---------- PRIV-3: a deletion on the test page never marks the real bot's person as deleted ----------
def test_priv3_each_store_keeps_its_own_deletion_list(env):
    from mvp import config
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    bot = env["bot"]
    bot.store.add_rule(H, "pasta every friday", pasta_spec(), "active", None)
    web = Bot(ConsoleChannel(printer=None), store=Store(os.path.join(config.HOME, "webtest.sqlite")), pool=bot.pool,
              clock=bot.clock)
    web.load_people(bot.people_path)
    web.store.set_consent(H, "test")
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    web.on_message(H, "delete my data")
    web.on_message(H, "yes")
    assert web.store.person(H) is None
    assert not os.path.exists(os.path.join(config.HOME, "deletions.jsonl"))
    assert [json.loads(x)["handle"] for x in open(os.path.join(config.HOME, "deletions-webtest.jsonl"))] == [H]
    assert web.load_people(bot.people_path) == 0                  # the test page's person stays deleted there
    real = Bot(ConsoleChannel(printer=None), store=Store(config.DB), pool=bot.pool, clock=bot.clock)
    assert real.load_people(bot.people_path) == 1 and real.store.rules(H)   # the real bot is untouched


# ---------- PRIV-6: a deletion during an import: nothing is sent, kept or moved to .failed ----------

@pytest.mark.parametrize("ok", [False, True])
def test_priv6_deleted_during_the_build(fresh, ok):
    bot, ch = fresh["bot"], fresh["ch"]
    fresh["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    inner = fake_prepare(ok=ok)
    seen = {}

    def prep(lib, cap):
        bot.on_message(H, "delete my data")
        bot.on_message(H, "yes")
        seen["n"], seen["lib"] = len(ch.outbox), lib
        return inner(lib, cap)
    bot.refresher.prepare = prep
    drop(fresh, fresh["ig_zip"])
    assert bot.refresher.poll(force=True) == 1
    assert bot.store.person(H) is None
    assert ch.outbox[seen["n"]:] == []                                         # nothing sent after the deletion
    assert bot.store.one("SELECT COUNT(*) n FROM sent WHERE handle=?", (H,))["n"] == 0
    assert bot.store.one("SELECT COUNT(*) n FROM imports WHERE handle=?", (H,))["n"] == 0
    assert not os.path.exists(seen["lib"])                                     # the library built from their export
    assert not os.path.exists(fresh["inbox"])                                  # no .failed copy, no .working copy


# ---------- PRIV-7: the outside search never uses words the setup's model wrote ----------
def _offer(env, outside="none"):
    from mvp.store import now_iso
    spec = {"when": {"type": "now"}, "content": {"goal": "a pasta dish you can cook tonight", "outside": outside,
            "searches": ["easy pasta dinner"], "count": 1, "criteria": ["ends with a dish you can eat"]}}
    req = "An easy pasta dinner that ends with a dish you can eat"          # written by the first-requests model
    env["bot"].store.set_state(f"onboard:{H}", {"step": "offer", "at": now_iso(env["clock"][0]),
                                                "requests": [{"text": req, "spec": spec, "hits": 3}]})
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Lemon garlic pasta",
                                                                    "verdict": "close"}]}


def test_priv7_a_first_request_run_by_number_sends_no_model_words_to_youtube(yt):
    _offer(yt)
    yt["bot"].on_message(H, "1")
    assert "the closest I have is" in last(yt["ch"])                     # the library answer is given
    assert yt["yt"].searches() == []
    _offer(yt, outside="some")
    yt["bot"].on_message(H, "1")
    assert yt["yt"].searches() == []


def test_priv7_the_morning_rule_keeps_the_persons_words_and_searches_with_none_of_the_models(yt):
    _offer(yt, outside="some")
    yt["bot"].on_message(H, "every morning")
    assert yt["yt"].searches() == []
    yt["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "confirm"}
    yt["bot"].on_message(H, "yes")
    rule = yt["bot"].store.rules(H)[0]
    assert rule["text"] == "every morning"
    yt["clock"][0] = yt["clock"][0] + __import__("datetime").timedelta(days=1)
    yt["bot"].tick()
    assert yt["yt"].searches() == []
    # a rule stored before the fix, with the setup's sentence as its text: its sends use none of those words
    yt["bot"].store.update_rule(rule["id"], text="every morning at 8: An easy pasta dinner that ends with a dish")
    yt["bot"].run(yt["bot"].store.person(H), __import__("mvp.schema", fromlist=["x"]).RuleSpec.model_validate(
        rule["spec"]), "manual", rule_id=rule["id"], request_text="every morning at 8: An easy pasta dinner")
    assert yt["yt"].searches() == []
