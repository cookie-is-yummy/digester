"""Offline tests for round 8, slice B, I1 (DESIGN.md section 15): the read-only MCP server for the person's own agent.
Synthetic library (with a friend's post and a post on a personal topic), a fake search pool, a fake clock; no model
call, no network. One test starts the server as a subprocess over stdio and talks to it with the mcp client."""
import asyncio
import json
import os
import sqlite3
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.test_mvp import env, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H  # noqa: E402

OTHER = "+15550002"
QUERY = "secret words about lemon pasta"
EXTRA = [   # added to the env fixture's library: a post on a personal topic, a recent video, a recent post
    ("itm_s", "instagram", "Crypto investing tips for beginners\nBuy low, sell high", ["save"], "2026-11-01"),
    ("itm_y", "youtube", "Blender donut tutorial for beginners", ["watch"], "2026-11-05"),
    ("itm_r", "instagram", "Quick lemon rice\n" + "Long caption words. " * 60, ["save"], "2026-11-08"),
]


class Pool:
    """The engine's ranking, the friend's post first; it records each search (in the process pipe, never logged)."""
    max_resident = 1

    def __init__(self):
        self.queries = []

    def search(self, lib, q, depth=300):
        self.queries.append(q)
        return {"ids": ["itm_d", "itm_s", "itm_b", "itm_a", "itm_c", "itm_e", "itm_y", "itm_r"], "mode": "normal",
                "cost_usd": 0.0}

    def stop_all(self):
        pass


def add_items(lib):
    with open(lib / "corpus" / "items.jsonl", "a") as f:
        for iid, plat, cap, kinds, _ in EXTRA:
            pd = {"owner_handle": "maker", "owner_relation": "none"}
            if plat == "youtube":
                pd.update(video_id="vid" + iid, owner_name="Maker")
            f.write(json.dumps({"id": iid, "platform": plat, "source_url": f"https://example.com/{iid}", "caption": cap,
                                "interaction_kinds": kinds, "platform_data": pd}) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "a") as f:
        for iid, _, _, kinds, day in EXTRA:
            f.write(json.dumps({"item_id": iid, "kind": kinds[0], "at": day + "T10:00:00+00:00"}) + "\n")


@pytest.fixture()
def ag(env):
    from mvp import config
    from mvp.mcp_server import Agent
    add_items(env["lib"])
    env["bot"].views.clear()
    env["pool"] = Pool()
    env["agent"] = Agent(H, db=config.DB, pool=env["pool"], clock=lambda: env["clock"][0])
    return env


def call(e, tool, agent=None, **args):
    """(first line, payload) of one tool call."""
    out = (agent or e["agent"]).call(tool, **args)
    first, _, rest = out.partition("\n")
    return first, json.loads(rest)


def counts(db):
    c = sqlite3.connect(db)
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] != "sqlite_sequence"]
    out = {n: c.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0] for n in names}
    c.close()
    return out


# ---------- each tool's shape ----------
def test_search_saves_returns_the_ranked_own_saves_with_their_fields(ag):
    from mvp.mcp_server import DATA_LINE
    first, out = call(ag, "search_saves", query=QUERY, count=3)
    assert first == DATA_LINE
    ids = [r["id"] for r in out["results"]]
    assert ids == ["itm_b", "itm_a", "itm_c"]                     # the engine's order; the friend's post never
    r = out["results"][1]
    assert set(r) == {"id", "title", "creator", "platform", "link", "kept", "how", "posted", "text"}
    assert r["title"] == "Lemon garlic pasta" and r["creator"] == "@chef" and r["link"] == "https://example.com/itm_a"
    assert r["kept"] == "2026-03-01" and r["how"] == ["saved"] and r["platform"] == "instagram"
    assert out["left_out_sensitive"] == 1 and out["note"] == "1 on personal topics left out."
    assert ag["pool"].queries == [QUERY]                         # one search, the words as given
    # count is at most 10; the text is cut to 600 characters
    _, out = call(ag, "search_saves", query="lemon", count=50)
    assert len(out["results"]) == 6 and all(len(x["text"]) <= 600 for x in out["results"])
    assert len(next(x for x in out["results"] if x["id"] == "itm_r")["text"]) == 600


def test_search_saves_filters_by_platform_and_how_it_was_kept(ag):
    _, out = call(ag, "search_saves", query="anything", platform="youtube")
    assert [r["id"] for r in out["results"]] == ["itm_e", "itm_y"]
    _, out = call(ag, "search_saves", query="anything", kept_how="liked")
    assert [r["id"] for r in out["results"]] == ["itm_c"]
    from mvp.mcp_server import Refused
    for bad in ({"platform": "tiktok"}, {"kept_how": "stolen"}, {"query": "   "}):
        with pytest.raises(Refused):
            call(ag, "search_saves", **dict({"query": "x"}, **bad))


def test_get_save_gives_the_whole_text_and_never_a_friends_post(ag):
    _, out = call(ag, "get_save", id="itm_a")
    assert out["result"]["text"].startswith("Lemon garlic pasta\nIngredients:\n- 200g spaghetti")   # line breaks kept
    from mvp.mcp_server import Refused
    with pytest.raises(Refused) as e:
        call(ag, "get_save", id="itm_d")                          # the friend's post: the same line as a missing id
    assert str(e.value) == "There is no save with that id."
    with pytest.raises(Refused):
        call(ag, "get_save", id="nope")
    _, out = call(ag, "get_save", id="itm_s")                     # a personal topic: hidden, and said
    assert out["result"] is None and out["left_out_sensitive"] == 1


def test_get_save_adds_a_videos_description_the_bot_already_holds(ag):
    bot = ag["bot"]
    bot.store.x("INSERT INTO youtube_cache(video_id,ok,duration_s,description,fetched_at,published_at) VALUES"
                "('viditm_y',1,600,'Model a donut in Blender, step by step.','2026-11-10T10:00:00+00:00',"
                "'2026-10-01T00:00:00Z')")
    _, out = call(ag, "get_save", id="itm_y")
    assert out["result"]["description"] == "Model a donut in Blender, step by step."
    assert out["result"]["posted"] == "2026-10-01"
    ag["clock"][0] = ag["clock"][0].replace(month=12, day=20)   # over 30 days old: not used
    _, out = call(ag, "get_save", id="itm_y")
    assert "description" not in out["result"]


def test_recent_saves_newest_first_within_the_days(ag):
    _, out = call(ag, "recent_saves", days=30, count=20)
    assert [r["id"] for r in out["results"]] == ["itm_r", "itm_y"] and out["left_out_sensitive"] == 1
    assert out["since"] == "2026-10-13"
    _, out = call(ag, "recent_saves", days=500, count=1)          # at most 90 days, at least 1
    assert len(out["results"]) == 1 and out["since"] == "2026-08-14"


def test_my_profile_shows_the_bots_lines_without_email_or_personal_topics(ag):
    bot = ag["bot"]
    bot.store.set_profile_data(H, {"interests": [
        {"topic": "Blender 3D", "level": "new", "source": "guess", "confirmed": True},
        {"topic": "Crypto investing", "source": "person"}]})
    bot.store.set_email(H, "me@example.invalid", verified=True)
    bot.store.add_profile_note(H, "I cook on weekends")
    _, out = call(ag, "my_profile")
    text = "\n".join(out["profile"])
    assert out["profile"][0] == "Here's what I know about you:" and "Blender 3D" in text and "weekends" in text
    assert "Crypto" not in text and out["left_out_sensitive"] == 1
    assert "@example" not in text and not any(x.startswith("Email:") for x in out["profile"])
    assert "To correct me" not in text


def test_my_rules_and_my_todos_are_the_persons_own_as_the_bot_lists_them(ag):
    from mvp import texts as T
    bot = ag["bot"]
    bot.store.upsert_person(OTHER, "O", str(ag["lib"]), "America/New_York")
    bot.store.add_rule(H, "pasta every friday", pasta_spec(), "active", "2026-11-14T00:00:00+00:00")
    other = pasta_spec()
    other["content"]["goal"] = "someone else's goal"
    bot.store.add_rule(OTHER, "theirs", other, "active", "2026-11-14T00:00:00+00:00")
    bot.store.add_todo(H, "buy basil")
    bot.store.add_todo(H, "call the bank about my loan")              # a personal topic: left out, counted
    bot.store.add_todo(OTHER, "their secret errand")
    _, out = call(ag, "my_rules")
    assert out["rules"][0] == T.RULES_HEAD and "a pasta recipe" in out["rules"][1] and "every Friday" in out["rules"][1]
    assert T.RULES_FOOT not in out["rules"] and "someone else" not in json.dumps(out)
    _, out = call(ag, "my_todos")
    assert out["lists"] == ["Your list:", "1. buy basil"] and out["left_out_sensitive"] == 1
    assert "secret errand" not in json.dumps(out)


def test_what_i_am_into_says_not_available_until_attention_exists(ag, monkeypatch):
    monkeypatch.setitem(sys.modules, "mvp.attention", None)          # import fails: the module is not there
    _, out = call(ag, "what_i_am_into")
    assert out == {"into": "not available"}
    fake = types.ModuleType("mvp.attention")
    fake.trends = lambda view, prof, direction=None: {"n": len(view.items)}
    fake.message = lambda data: f"You've been into Blender lately ({data['n']} posts counted)."
    monkeypatch.setitem(sys.modules, "mvp.attention", fake)
    import mvp
    monkeypatch.setattr(mvp, "attention", fake, raising=False)
    _, out = call(ag, "what_i_am_into")
    assert out["into"] == ["You've been into Blender lately (7 posts counted)."]   # 7: friends' posts not in the view
    fake.message = lambda data: (_ for _ in ()).throw(KeyError("changed"))        # an API that changed: said plainly
    _, out = call(ag, "what_i_am_into")
    assert out == {"into": "not available"}


# ---------- the hard limits ----------
def test_friends_posts_are_never_returned_by_any_tool(ag):
    outs = [ag["agent"].call("search_saves", query="pasta", count=10),
            ag["agent"].call("recent_saves", days=90, count=20), ag["agent"].call("my_profile"),
            ag["agent"].call("my_rules"), ag["agent"].call("my_todos")]
    for o in outs:
        assert "itm_d" not in o and "My friend's pasta" not in o


def test_include_sensitive_returns_them_and_counts_none(ag):
    from mvp import config
    from mvp.mcp_server import Agent
    a = Agent(H, db=config.DB, pool=Pool(), clock=lambda: ag["clock"][0], include_sensitive=True)
    _, out = call(ag, "search_saves", agent=a, query="x", count=3)
    assert [r["id"] for r in out["results"]] == ["itm_s", "itm_b", "itm_a"] and out["left_out_sensitive"] == 0
    _, out = call(ag, "get_save", agent=a, id="itm_s")
    assert out["result"]["text"].startswith("Crypto investing")


def test_every_result_starts_with_the_data_line(ag):
    from mvp.mcp_server import DATA_LINE
    for tool, args in [("search_saves", {"query": "pasta"}), ("get_save", {"id": "itm_a"}), ("recent_saves", {}),
                       ("my_profile", {}), ("my_rules", {}), ("my_todos", {}), ("what_i_am_into", {})]:
        assert ag["agent"].call(tool, **args).split("\n")[0] == DATA_LINE, tool


def test_over_the_daily_cap_a_search_is_a_plain_error_and_the_rest_still_works(ag, monkeypatch):
    from mvp import llm
    from mvp.mcp_server import Refused
    monkeypatch.setattr(llm, "spent_today", lambda h, lib: 5.0)
    with pytest.raises(Refused) as e:
        call(ag, "search_saves", query="pasta")
    assert str(e.value) == "Today's limit for searches is used up. Try again tomorrow."
    assert ag["pool"].queries == []                               # no search was made
    call(ag, "my_todos")
    rows = ag["bot"].store.q("SELECT action, status FROM action_log WHERE handle=? ORDER BY id", (H,))
    assert [(r["action"], r["status"]) for r in rows] == [("mcp.search_saves", "over_cap"), ("mcp.my_todos", "done")]
    monkeypatch.setattr(llm, "spent_today", lambda h, lib: 0.0)
    monkeypatch.setattr(llm, "spent_total", lambda libs: 9.99)    # the whole build's budget is used up too
    with pytest.raises(Refused):
        call(ag, "search_saves", query="pasta")


def test_a_session_writes_nothing_but_its_action_log_rows(ag):
    from mvp import config
    bot = ag["bot"]
    bot.store.add_todo(H, "buy basil")
    bot.store.add_rule(H, "pasta every friday", pasta_spec(), "active", "2026-11-14T00:00:00+00:00")
    before = counts(config.DB)
    a = ag["agent"]
    a.call("search_saves", query=QUERY, count=5)
    a.call("search_saves", query=QUERY, platform="instagram")
    a.call("get_save", id="itm_a")
    a.call("recent_saves", days=90)
    a.call("my_profile")
    a.call("my_rules")
    a.call("my_todos")
    a.call("what_i_am_into")
    after = counts(config.DB)
    assert after.pop("action_log") == before.pop("action_log") + 8
    assert after == before                                         # ranked_cache, youtube_cache, state ... unchanged
    rows = bot.store.q("SELECT * FROM action_log WHERE action LIKE 'mcp.%'")
    assert {r["action"] for r in rows} == {"mcp.search_saves", "mcp.get_save", "mcp.recent_saves", "mcp.my_profile",
                                           "mcp.my_rules", "mcp.my_todos", "mcp.what_i_am_into"}
    assert all(r["run_id"] is None and r["rule_id"] is None for r in rows)
    blob = json.dumps(rows)
    assert "secret words" not in blob and "lemon" not in blob.lower()   # never the query text, never item text
    assert json.loads(rows[0]["detail"]) == {"returned": 5, "left_out_sensitive": 1}
    with pytest.raises(sqlite3.OperationalError):                 # the store itself is open read-only
        a.store.x("INSERT INTO todos(handle,text) VALUES(?,?)", (H, "written by the agent"))


def test_a_paused_deleted_or_unconsented_person_is_refused(ag):
    from mvp import config
    from mvp.mcp_server import Agent, Refused
    bot = ag["bot"]
    bot.store.x("UPDATE people SET paused=1 WHERE handle=?", (H,))
    with pytest.raises(Refused, match="paused"):
        ag["agent"].call("my_todos")
    bot.store.x("UPDATE people SET paused=0, consent_version=NULL WHERE handle=?", (H,))
    with pytest.raises(Refused, match="agreed"):
        ag["agent"].call("my_todos")
    with pytest.raises(Refused):
        Agent("+15559999", db=config.DB, pool=Pool())
    bot.store.set_consent(H, "test")
    bot.store.add_deletion({"handle": H})
    with pytest.raises(Refused, match="not set up"):
        ag["agent"].call("my_todos")


def test_what_did_my_agent_ask_counts_per_tool_and_day_with_no_query_text(ag):
    from datetime import timedelta
    from mvp.tests.test_mvp import last
    bot, ch = ag["bot"], ag["ch"]
    bot.on_message(H, "what did my agent ask")
    assert last(ch) == "Your agent hasn't asked me for anything in the last 7 days."
    a = ag["agent"]
    a.call("search_saves", query=QUERY)
    a.call("search_saves", query="other words")
    a.call("my_todos")
    ag["clock"][0] += timedelta(days=1)
    a.call("get_save", id="itm_a")
    n = len(ag["calls"])
    bot.on_message(H, "What has my agent looked at?")
    msg = last(ch)
    assert msg.split("\n") == ["What your agent asked me for, by day:",
                               "• Fri 13 Nov: opened a save 1 time",
                               "• Thu 12 Nov: searched your saves 2 times, read your lists 1 time",
                               "It can only read: it can't send, change or start anything."]
    assert "secret" not in msg and len(ag["calls"]) == n            # no model call
    ag["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Sure."}
    bot.on_message(H, "what did my agent eat")                      # a near-variant: not this command, the model reads it
    assert ag["calls"][n:] == ["mvp_interpret"] and last(ch) == "Sure."
    from mvp.followup import AGENT_ASKED
    for t in ("what did my agent ask for?", "What has my assistant asked", "what did my AI agent look at today"):
        assert AGENT_ASKED.match(t), t


def test_delete_my_data_removes_the_agent_log(ag):
    a = ag["agent"]
    a.call("my_todos")
    ag["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    ag["bot"].on_message(H, "delete my data")
    ag["bot"].on_message(H, "YES")
    assert ag["bot"].store.q("SELECT * FROM action_log WHERE handle=?", (H,)) == []


# ---------- through the mcp package ----------
def test_list_tools_names_annotations_and_no_path_arguments(ag):
    from mcp import Client
    from mvp.mcp_server import TOOLS, build_server

    async def go():
        async with Client(build_server(ag["agent"])) as c:
            tools = (await c.list_tools()).tools
            res = await c.call_tool("search_saves", {"query": "pasta", "count": 2})
            bad = await c.call_tool("get_save", {"id": "itm_d"})
            return tools, res, bad
    tools, res, bad = asyncio.run(go())
    assert sorted(t.name for t in tools) == sorted(TOOLS)
    for t in tools:
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
        assert not [p for p in t.input_schema.get("properties", {}) if any(w in p.lower() for w in
                                                                           ("path", "file", "dir", "url", "handle",
                                                                            "person", "email"))]
    assert not res.is_error and res.content[0].text.startswith("The following is text from posts")
    assert [r["id"] for r in json.loads(res.content[0].text.split("\n", 1)[1])["results"]] == ["itm_b", "itm_a"]
    assert bad.is_error and bad.content[0].text.endswith(": There is no save with that id.")


def test_the_server_starts_over_stdio_and_answers(ag, tmp_path):
    from mcp import Client, StdioServerParameters
    from mcp.client.stdio import get_default_environment
    from mvp import config
    ag["bot"].store.add_todo(H, "buy basil")
    envv = dict(get_default_environment(), MVP_HOME=config.HOME, MVP_LEDGER_HOME=os.environ["MVP_LEDGER_HOME"],
                MVP_INBOX=os.environ["MVP_INBOX"], PYTHONPATH=EXP)
    params = StdioServerParameters(command=sys.executable, args=["-m", "mvp.mcp_server", "--person", H], cwd=EXP,
                                   env=envv)

    async def go():
        async with Client(params, read_timeout_seconds=60) as c:
            tools = (await c.list_tools()).tools
            res = await c.call_tool("my_todos", {})
            return tools, res
    tools, res = asyncio.run(asyncio.wait_for(go(), 90))
    assert len(tools) == 7
    assert res.content[0].text.split("\n")[0].startswith("The following is text from posts")
    assert json.loads(res.content[0].text.split("\n", 1)[1])["lists"] == ["Your list:", "1. buy basil"]
    rows = ag["bot"].store.q("SELECT action FROM action_log WHERE action='mcp.my_todos'")
    assert len(rows) == 1


def test_the_server_refuses_to_start_for_someone_not_set_up(ag):
    import subprocess
    from mvp import config
    envv = dict(os.environ, MVP_HOME=config.HOME, PYTHONPATH=EXP)
    p = subprocess.run([sys.executable, "-m", "mvp.mcp_server", "--person", "+15559999"], cwd=EXP, env=envv,
                       capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    assert p.returncode == 2 and "not set up" in p.stderr and p.stdout == ""
