"""Round 10, slice Y (DESIGN.md section 17.Y): the person's YouTube through Google's own API, and Instagram links.

Everything runs against the in-process fake Google (tests/fakes/fake_google.py) set as actions.web.OPENER: the device
flow, subscriptions, playlists, quota and errors. Made-up channels, videos and handles only; no model call where none is
promised, no network, no port."""
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H  # noqa: E402

UTC = timezone.utc
CHAT = {"intent": "chat", "reply": "OK."}
# made-up library items: three YouTube videos from two channels, one Instagram reel
VIDS = {"yt_1": ("vidAAAAAAA1", "Kitchen Lab", "One-pan miso pasta"),
        "yt_2": ("vidBBBBBBB2", "Garden Hour", "Tomatoes in pots"),
        "yt_3": ("vidCCCCCCC3", "Kitchen Lab", "Lemon orzo")}
CHANNELS = {"UCkitchen0001": "Kitchen Lab", "UCgarden00002": "Garden Hour", "UCbikes000003": "Bike Fix",
            "UCchess000004": "Chess Corner", "UCknits000005": "Knit Night"}


def _key():
    return base64.b64encode(os.urandom(32)).decode()


def _add_items(lib, watched="2026-11-01T10:00:00+00:00", vids=None, dates=None):
    """YouTube items (watched on `watched`, or on dates[item id]) and one Instagram reel, added to the env library."""
    vids = vids or VIDS
    with open(lib / "corpus" / "items.jsonl", "a") as f:
        for iid, (vid, ch, title) in vids.items():
            f.write(json.dumps({"id": iid, "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={vid}",
                                "caption": title, "interaction_kinds": ["watch"],
                                "platform_data": {"video_id": vid, "owner_name": ch, "owner_relation": "none"}}) + "\n")
        f.write(json.dumps({"id": "ig_1", "platform": "instagram", "source_url": "https://www.instagram.com/reel/x1/",
                            "caption": "Crispy rice salad", "interaction_kinds": ["save"],
                            "platform_data": {"owner_handle": "made_up_cook", "owner_relation": "following"}}) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "a") as f:
        for iid in vids:
            f.write(json.dumps({"item_id": iid, "kind": "watch", "at": (dates or {}).get(iid, watched)}) + "\n")
        f.write(json.dumps({"item_id": "ig_1", "kind": "save", "at": watched}) + "\n")


@pytest.fixture()
def yt(env, monkeypatch):
    """The bot of `env`, a fake Google, a client id and secret, a sealing key, and YouTube picks in the library."""
    monkeypatch.setenv("MVP_TOKEN_KEY", _key())
    monkeypatch.setenv("MVP_YT_CLIENT_ID", "made-up-client.example.com")
    monkeypatch.setenv("MVP_YT_CLIENT_SECRET", "made-up-client-secret")
    monkeypatch.delenv("MVP_OPERATOR", raising=False)
    monkeypatch.delenv("MVP_YT_UNITS_PER_DAY", raising=False)
    from mvp.actions import web
    from mvp.tests.fakes.fake_google import FakeGoogle
    g = FakeGoogle()
    g.add_channels(list(CHANNELS), CHANNELS)
    for vid, ch in (("vidAAAAAAA1", "UCkitchen0001"), ("vidBBBBBBB2", "UCgarden00002"),
                    ("vidCCCCCCC3", "UCkitchen0001")):
        g.add_video(vid, ch)
    monkeypatch.setattr(web, "OPENER", g)
    _add_items(env["lib"])
    env["state"]["answers"]["mvp_interpret"] = lambda u: CHAT
    env["bot"].max_per_minute = None
    env["g"] = g
    return env


def tell(e, text):
    """The person sends `text`; the bot's last reply to it (None: no reply)."""
    e["clock"][0] += timedelta(seconds=20)
    n = len(e["ch"].outbox)
    e["bot"].on_message(H, text)
    out = e["ch"].outbox[n:]
    return out[-1][2] if out else None


def show(e, *ids):
    """An answer with these picks is the last thing shown."""
    e["bot"].store.set_last_answer(H, None, None, list(ids), "test")


def connect(e):
    r = tell(e, "connect youtube")
    assert "google.com/device" in r and "ABCD-" in r
    e["g"].approve()
    return tell(e, "done")


def outbox_text(e):
    return "\n".join(m[2] for m in e["ch"].outbox)


def db_text(e):
    """Every value in the store, as text (to check nothing secret or third-party is kept there)."""
    st = e["bot"].store
    out = []
    for t in [r["name"] for r in st.q("SELECT name FROM sqlite_master WHERE type='table'")]:
        out += [json.dumps(r, default=str) for r in st.q(f"SELECT * FROM {t}")]
    return "\n".join(out)


def actions(e, name=None):
    rows = e["bot"].store.q("SELECT action, status, detail FROM action_log ORDER BY id")
    return [r for r in rows if name is None or r["action"] == name]


# ---------- Y2: connect by a code (the device flow) ----------
def test_connect_by_a_code_then_the_connected_line_and_nothing_secret_kept(yt):
    from mvp import tokens
    from mvp.tests.fakes.fake_google import SCOPE_RW
    r = tell(yt, "connect youtube")
    code = next(iter(yt["g"].device.values()))["user_code"]
    assert r == (f"To let me manage your YouTube, open google.com/device on any phone or computer and type {code}. "
                 "Google will warn that the app isn't verified yet; that's expected for this test. I'll only change "
                 "something on YouTube after you say yes to the exact change. The code works for 30 minutes.")
    assert [d["scopes"] for d in yt["g"].device.values()] == [[SCOPE_RW]]   # the one scope, never force-ssl
    assert tell(yt, "done").startswith(f"I haven't heard from Google yet. Open google.com/device, type {code} ")
    assert tell(yt, "connect youtube").startswith("I haven't heard from Google yet")   # the same code, not a new one
    assert len(yt["g"].device) == 1
    yt["g"].approve()
    assert tell(yt, "done") == ('YouTube is connected. You follow 5 channels and have 0 playlists. Say "disconnect '
                                'youtube" any time.')
    assert tokens.exists(H, "youtube") and not tokens.exists(H, "youtube_device")
    assert tell(yt, "is youtube connected") == 'YouTube is connected. Say "disconnect youtube" to end it.'
    assert tell(yt, "connect my youtube") == 'YouTube is already connected. Say "disconnect youtube" to end it.'
    # no token, no device code and no client secret in any reply or store row
    kept = db_text(yt) + outbox_text(yt)
    for secret in list(yt["g"].tokens) + list(yt["g"].refresh) + list(yt["g"].device) + ["made-up-client-secret"]:
        assert secret not in kept
    assert "mvp_interpret" not in yt["calls"]   # read by code, no model call


def test_the_scheduler_tick_asks_google_while_a_code_is_open(yt):
    bot, g = yt["bot"], yt["g"]
    tell(yt, "connect youtube")
    n = len(yt["ch"].outbox)
    bot.tick()
    assert len(yt["ch"].outbox) == n                       # not before the interval
    yt["clock"][0] += timedelta(seconds=6)
    g.slow_down = True
    bot.tick()                                              # slow_down: the gap grows by 5 seconds
    st = bot.store.get_state(f"ytdevice:{H}")
    assert st["interval"] == 10 and len(yt["ch"].outbox) == n
    g.approve()
    yt["clock"][0] += timedelta(seconds=11)
    bot.tick()
    assert yt["ch"].outbox[-1][2].startswith("YouTube is connected. You follow 5 channels")
    assert bot.store.get_state(f"ytdevice:{H}") is None
    yt["clock"][0] += timedelta(seconds=30)
    n = len(yt["ch"].outbox)
    bot.tick()
    assert len(yt["ch"].outbox) == n                       # said once


@pytest.mark.parametrize("how, line", [
    ("deny", 'Google says you didn\'t allow it, so YouTube isn\'t connected. Say "connect youtube" to try again.'),
    ("expire", 'The code ran out before Google heard from you, so YouTube isn\'t connected. Say "connect youtube" '
               'for a new one.')])
def test_a_code_denied_or_expired_says_so_and_keeps_nothing(yt, how, line):
    from mvp import tokens
    tell(yt, "connect youtube")
    getattr(yt["g"], {"deny": "deny", "expire": "expire_device"}[how])()
    assert tell(yt, "done") == line
    assert not tokens.exists(H, "youtube") and not tokens.exists(H, "youtube_device")
    assert yt["bot"].store.get_state(f"ytdevice:{H}") is None


def test_a_code_left_open_runs_out_after_30_minutes_on_the_tick(yt):
    tell(yt, "connect youtube")
    yt["clock"][0] += timedelta(minutes=31)
    yt["bot"].tick()
    assert yt["ch"].outbox[-1][2].startswith("The code ran out before Google heard from you")


def test_a_wider_grant_than_youtube_is_refused_and_ended_at_google(yt):
    """The device flow never keeps youtube.force-ssl (or any scope but `youtube`), even if Google grants it."""
    from mvp import tokens
    from mvp.tests.fakes.fake_google import SCOPE_RW
    tell(yt, "connect youtube")
    for d in yt["g"].device.values():
        d["scopes"] = [SCOPE_RW, "https://www.googleapis.com/auth/youtube.force-ssl"]
    yt["g"].approve()
    assert tell(yt, "done").startswith("Google gave me a different permission than the one I asked for")
    assert not tokens.exists(H, "youtube") and yt["g"].revoked == [True]
    # near variant: read-only is refused too (every change would fail)
    tell(yt, "connect youtube")
    for d in yt["g"].device.values():
        if d["state"] == "pending":
            d["scopes"] = ["https://www.googleapis.com/auth/youtube.readonly"]
    yt["g"].approve()
    assert tell(yt, "done").startswith("Google gave me a different permission")
    assert not tokens.exists(H, "youtube")


def test_the_scope_asked_is_youtube_only():
    from mvp import yt_auth
    assert yt_auth.SCOPE == "https://www.googleapis.com/auth/youtube"
    src = open(yt_auth.__file__, encoding="utf-8").read() + open(
        os.path.join(os.path.dirname(yt_auth.__file__), "actions", "youtube.py"), encoding="utf-8").read()
    assert "auth/youtube.force-ssl" not in src


def test_not_set_up_and_no_key_lines(yt, monkeypatch):
    monkeypatch.delenv("MVP_YT_CLIENT_SECRET")
    assert tell(yt, "connect youtube").startswith("YouTube isn't set up on this bot yet")
    show(yt, "yt_1")
    assert tell(yt, "unsubscribe me from that channel").startswith("YouTube isn't set up on this bot yet")
    monkeypatch.setenv("MVP_YT_CLIENT_SECRET", "made-up-client-secret")
    monkeypatch.delenv("MVP_TOKEN_KEY")
    monkeypatch.setenv("MVP_TOKEN_KEY_AUTO", "0")
    assert tell(yt, "connect youtube") == ("I can't keep sign-ins safely yet: the person who runs me needs to set a "
                                           "key first.")
    assert yt["g"].device == {}   # Google was not even asked


def test_disconnect_ends_access_at_google_deletes_the_sign_in_and_the_lists(yt):
    from mvp import tokens
    connect(yt)
    store = yt["bot"].store
    gid = store.add_grant(H, 1, "youtube", "youtube.playlist_add", "Dinners", 3, 10, "x")
    r = tell(yt, "disconnect youtube")
    assert r == "YouTube is disconnected, and I deleted my sign-in. What I changed there stays as it is."
    assert yt["g"].revoked == [True] and not tokens.exists(H, "youtube")
    assert store.grant(gid)["status"] == "ended" and store.get_state(f"ytsubs:{H}") is None
    assert tell(yt, "disconnect youtube") == "YouTube isn't connected, so there's nothing to disconnect."
    assert tell(yt, "is youtube connected") == 'YouTube isn\'t connected. Say "connect youtube" to connect it.'


def test_a_tester_can_connect_and_act_but_the_other_routes_stay_the_operators(yt):
    """M-4: the new branch of connectors.unavailable is for kind "oauth" only."""
    from mvp import config
    from mvp import connectors as C
    from mvp.actions import REGISTRY
    store = yt["bot"].store
    assert not config.is_operator(H)
    assert C.unavailable(store, H, "youtube") == "not_connected"
    connect(yt)
    assert C.unavailable(store, H, "youtube") is None
    for key in ("mac", "ticktick", "todoist", "webhook"):
        assert C.unavailable(store, H, key) == "operator", key
    assert REGISTRY["mailbox.send"].who == "operator" and REGISTRY["mailbox.draft"].who == "operator"
    assert all(REGISTRY[n].who == "anyone" and not REGISTRY[n].from_model and not REGISTRY[n].in_rules
               and REGISTRY[n].confirm == "send_word" for n in REGISTRY if n.startswith("youtube."))
    show(yt, "yt_2")
    assert tell(yt, "unsubscribe me from that channel").startswith('Unsubscribe from "Garden Hour" on YouTube?')
    assert tell(yt, "yes").startswith('Unsubscribed from "Garden Hour" on YouTube.')


# ---------- Y1: routing ----------
def test_not_connected_the_channel_request_says_how_and_gives_the_page(yt):
    show(yt, "yt_1")
    for text in ("unsubscribe me from that channel", "unsubscribe from this channel", "Unsubscribe from the channel.",
                 "can you unsubscribe me from that channel for me", "unsubscribe from kitchen lab"):
        assert tell(yt, text) == ('I can do that on YouTube once you connect it: say "connect youtube". Or do it '
                                  'yourself here: https://www.youtube.com/feed/channels'), text
    assert yt["g"].calls == []


@pytest.mark.parametrize("text", ["unsubscribe from netflix", "unsubscribe me from netflix",
                                  "unsubscribe from youtube premium", "unsubscribe from my youtube music"])
@pytest.mark.parametrize("connected", [False, True])
def test_a_paid_service_still_goes_to_the_cancel_helper(yt, text, connected):
    if connected:
        connect(yt)
    show(yt, "yt_1")
    tell(yt, text)
    assert [r["status"] for r in actions(yt, "cancel.help")] == ["done"], text
    assert not any(r["action"].startswith("youtube.") for r in actions(yt))


def test_a_name_that_is_both_a_channel_and_a_paid_service_asks_which(yt):
    yt["g"].add_channels(["UCnetflix0007"], {"UCnetflix0007": "Netflix"})
    connect(yt)
    assert tell(yt, "unsubscribe from netflix") == "Do you mean the YouTube channel or a paid subscription?"
    assert tell(yt, "the youtube channel") == ('Unsubscribe from "Netflix" on YouTube? Reply "yes" to unsubscribe, or '
                                              '"no" to keep it.')
    assert tell(yt, "no") == "OK, I left it as it is on YouTube."
    assert tell(yt, "unsubscribe from netflix") == "Do you mean the YouTube channel or a paid subscription?"
    tell(yt, "the paid subscription")
    assert [r["status"] for r in actions(yt, "cancel.help")] == ["done"]
    assert ("DELETE", "subscriptions") not in yt["g"].calls
    # near variant: "the netflix channel" says which, so there is no question
    assert tell(yt, "unsubscribe from the netflix channel").startswith('Unsubscribe from "Netflix" on YouTube?')


def test_two_channels_in_view_ask_which_and_a_name_answers(yt):
    connect(yt)
    show(yt, "yt_1", "ig_1", "yt_2")
    assert tell(yt, "unsubscribe me from that channel") == ('Which channel?\n1. "Kitchen Lab"\n2. "Garden Hour"\n'
                                                            'Say "unsubscribe from" and its name.')
    assert tell(yt, "unsubscribe from garden hour").startswith('Unsubscribe from "Garden Hour" on YouTube?')


@pytest.mark.parametrize("text", ["can you unsub me from kitchen lab",
                                  "remove kitchen lab from my youtube subscriptions",
                                  "remove that channel from my subscriptions", "stop following kitchen lab",
                                  "unsubscribe from this guy", "take the kitchen lab channel off my subscriptions",
                                  "remove kitchen lab from my subscriptions",
                                  # the wordings the live interpreter read as "unsupported" (DESIGN 17.Y, measured)
                                  "get rid of the kitchen lab channel", "take me off kitchen lab's channel",
                                  "delete the kitchen lab subscription on youtube"])
def test_everyday_wordings_reach_the_one_channel_question(yt, text):
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, text) == ('Unsubscribe from "Kitchen Lab" on YouTube? Reply "yes" to unsubscribe, or "no" to keep '
                              'it.'), text
    assert tell(yt, "no") == "OK, I left it as it is on YouTube."


def test_everyday_wordings_for_links_disconnect_and_a_playlist(yt):
    assert "Following › Unfollow" in tell(yt, "stop following @made_up_cook")
    connect(yt)
    show(yt, "yt_1", "yt_3")
    assert tell(yt, "make a playlist of these").startswith("What should the playlist be called?")
    assert tell(yt, "make me a youtube playlist called pasta night with these").startswith(
        'I\'ll make a private YouTube playlist "Pasta night" and add these 2 videos to it')
    tell(yt, "no")
    assert tell(yt, "unsub 2") is not None and ("DELETE", "subscriptions") not in yt["g"].calls   # nothing waiting
    for text in ("save these videos to youtube", "add this to my youtube"):
        show(yt, "yt_1", "yt_3")
        assert tell(yt, text).startswith("What should the playlist be called?"), text
    for text in ("clean up my youtube subscriptions", "which channels do i never watch"):
        assert tell(yt, text).startswith("Since when? Say, for example,"), text
    assert "schedule_frequency=ONCE_A_WEEK" in tell(yt, "make my instagram export happen every week")
    assert tell(yt, "log out of youtube").startswith("YouTube is disconnected")
    # near variant: a paid service named the same way is not taken
    for text in ("remove netflix from my subscriptions", "delete my netflix subscription",
                 "get rid of the netflix subscription"):
        tell(yt, text)
        assert yt["bot"].store.get_state(f"ytask:{H}") is None, text
    assert not [r for r in actions(yt) if r["action"].startswith("youtube.")]


def test_words_that_are_not_a_youtube_request_are_left_alone(yt):
    connect(yt)
    show(yt, "yt_1")
    for text in ("unsubscribe from the newsletter", "unsubscribe from my rules", "unsubscribe from texts",
                 "stop my reminders", "unfollow the plan", "mute the reminders", "put it on my list",
                 "add these to my shopping list", "unsubscribe from it"):
        tell(yt, text)
    assert not any(r["action"].startswith(("youtube.", "link.")) for r in actions(yt))
    assert yt["bot"].store.get_state(f"ytask:{H}") is None
    assert ("DELETE", "subscriptions") not in yt["g"].calls


# ---------- Y3: one-off writes (design test 27) ----------
def test_27_unsubscribe_from_the_picks_channel_then_undo(yt):
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, "unsubscribe me from that channel") == ('Unsubscribe from "Kitchen Lab" on YouTube? Reply "yes" '
                                                            'to unsubscribe, or "no" to keep it.')
    assert "UCkitchen0001" in yt["g"].subs.values()
    assert tell(yt, "yes") == ('Unsubscribed from "Kitchen Lab" on YouTube. Say "undo" in the next 7 days to '
                               'subscribe again.')
    assert "UCkitchen0001" not in yt["g"].subs.values()
    row = actions(yt, "youtube.unsubscribe")[-1]
    d = json.loads(row["detail"])
    assert row["status"] == "done" and d["count"] == 1 and d["units"] == 51 and d["route"] == "youtube_api"
    pl = yt["bot"].store.placements(H, connector="youtube")
    assert [(p["action"], p["remote_id"], p["route"]) for p in pl] == [("youtube.unsubscribe", "UCkitchen0001",
                                                                       "youtube_api")]
    yt["clock"][0] += timedelta(days=6)
    assert tell(yt, "undo") == 'I subscribed you again to "Kitchen Lab" on YouTube.'
    assert "UCkitchen0001" in yt["g"].subs.values()
    assert yt["bot"].store.placements(H, connector="youtube") == []


def test_undo_after_7_days_does_not_reach_youtube(yt):
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    tell(yt, "yes")
    yt["clock"][0] += timedelta(days=7, minutes=5)
    tell(yt, "undo")
    assert "UCkitchen0001" not in yt["g"].subs.values()


def test_the_persons_own_newer_write_is_undone_first(yt):
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    tell(yt, "yes")
    yt["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "todo_add", "todo_text": "buy basil"}
    tell(yt, "add buy basil to my list")
    yt["state"]["answers"]["mvp_interpret"] = lambda u: CHAT
    assert len(yt["bot"].store.todos(H)) == 1
    tell(yt, "undo")
    assert "UCkitchen0001" not in yt["g"].subs.values()   # the to-do went, YouTube was not touched
    tell(yt, "undo")
    assert "UCkitchen0001" in yt["g"].subs.values()


def test_not_subscribed_says_so_and_changes_nothing(yt):
    yt["g"].subs = {k: v for k, v in yt["g"].subs.items() if v != "UCgarden00002"}
    connect(yt)
    show(yt, "yt_2")
    assert tell(yt, "unsubscribe me from that channel") == 'You\'re not subscribed to "Garden Hour" on YouTube.'
    assert yt["bot"].store.get_state(f"ytask:{H}") is None


def test_a_yes_after_the_question_went_stale_or_another_message_changes_nothing(yt):
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    tell(yt, "what's the weather")            # the question is for the next message only
    tell(yt, "yes")
    assert "UCkitchen0001" in yt["g"].subs.values()
    tell(yt, "unsubscribe me from that channel")
    yt["clock"][0] += timedelta(minutes=31)
    tell(yt, "yes")
    assert "UCkitchen0001" in yt["g"].subs.values()


# ---------- design test 28: channels not watched since, with the M-15 guard ----------
OLD = {"old_1": ("vidDDDDDDD4", "Bike Fix", "Chain on"), "old_2": ("vidEEEEEEE5", "Chess Corner", "Openings"),
       "old_3": ("vidFFFFFFF6", "Fly Fishing", "Knots")}


def _idle_setup(e):
    """Five channels watched: two recently (Kitchen Lab, Garden Hour), three last in 2024 or before; Knit Night has
    no record in the history (left out, counted)."""
    e["g"].add_channels(["UCflyfish0006"], {"UCflyfish0006": "Fly Fishing"})
    _add_items(e["lib"], vids=OLD, dates={"old_1": "2024-06-01T10:00:00+00:00", "old_2": "2023-01-05T10:00:00+00:00",
                                          "old_3": "2024-02-01T10:00:00+00:00"})
    connect(e)


def test_28_idle_list_keep_re_previews_and_the_count_must_match(yt):
    _idle_setup(yt)
    r = tell(yt, "unsubscribe from channels I haven't watched since 2024")
    assert r == ("You're subscribed to 6 channels on YouTube. 3 have nothing in your watch history since 1 Jan 2025 "
                 "(your history here ends on 1 Nov 2026; 1 channel I can't match to your history is left out).\n"
                 "1. Bike Fix\n2. Chess Corner\n3. Fly Fishing\n"
                 "Reply \"unsubscribe 3\" to remove them all on YouTube, or \"keep 4, 9\" first.")
    first = yt["bot"].store.get_state(f"ytask:{H}")["token"]
    r = tell(yt, "keep 2")
    assert r.endswith("1. Bike Fix\n2. Fly Fishing\nReply \"unsubscribe 2\" to remove them all on YouTube, or "
                      "\"keep 4, 9\" first.") and "You're keeping 1." in r
    assert yt["bot"].store.get_state(f"ytask:{H}")["token"] != first           # a new list, a new yes
    assert tell(yt, "unsubscribe 3") == ('That list has 2 channels. Reply "unsubscribe 2" to remove them all on '
                                         'YouTube, or "keep 4, 9" first.')
    assert tell(yt, "yes").startswith("That list has 2 channels.")                 # a bare yes is not enough for 2
    assert ("DELETE", "subscriptions") not in yt["g"].calls
    assert tell(yt, "unsubscribe 2") == ('Unsubscribed from 2 channels on YouTube. Say "undo" in the next 7 days to '
                                         'subscribe again.')
    left = set(yt["g"].subs.values())
    assert "UCbikes000003" not in left and "UCflyfish0006" not in left and "UCchess000004" in left
    assert "UCknits000005" in left                                                 # unmatched: never guessed
    assert tell(yt, "undo") == "I subscribed you again to 2 channels on YouTube."
    assert {"UCbikes000003", "UCflyfish0006"} <= set(yt["g"].subs.values())


def test_28_a_stale_yes_after_the_list_changed_deletes_nothing(yt):
    _idle_setup(yt)
    tell(yt, "unsubscribe from channels I haven't watched since 2024")
    g = yt["g"]
    sid = next(s for s, c in g.subs.items() if c == "UCchess000004")
    del g.subs[sid]                                   # the person unsubscribed from one on YouTube meanwhile
    assert tell(yt, "unsubscribe 3") == ("Your YouTube subscriptions changed since I showed you that list, so I didn't "
                                         "change anything. Ask again and I'll show you the new list.")
    assert ("DELETE", "subscriptions") not in g.calls
    # near variant: a title that changed is another list too
    tell(yt, "unsubscribe from channels I haven't watched since 2024")
    g.channels["UCbikes000003"] = "Bike Fix (new name)"
    assert tell(yt, "unsubscribe 2").startswith("Your YouTube subscriptions changed")
    assert ("DELETE", "subscriptions") not in g.calls


@pytest.mark.parametrize("when, since", [("since 2024", "1 Jan 2025"), ("in a year", "12 Nov 2025"),
                                         ("since march 2025", "1 Apr 2025"), ("in 6 months", "16 May 2026")])
def test_28_the_time_words(yt, when, since):
    _idle_setup(yt)
    r = tell(yt, f"unsubscribe from channels I haven't watched {when}")
    assert f"since {since} (" in r, r


def test_m15_no_watch_history_or_an_old_one_refuses(yt, tmp_path):
    connect(yt)
    view = yt["bot"].view(str(yt["lib"]))
    for it in view.items.values():
        it.dates.pop("watch", None)
    assert tell(yt, "unsubscribe from channels I haven't watched since 2024") == (
        "I don't have your YouTube watch history, so I can't tell which channels you've stopped watching. It's in your "
        "Google Takeout (YouTube, history); send me a new one and ask again.")
    for it in view.items.values():
        if it.platform == "youtube":
            it.dates["watch"] = "2026-06-01T10:00:00+00:00"            # 164 days before the clock
    assert tell(yt, "unsubscribe from channels I haven't watched since 2024") == (
        "Your newest YouTube watch history here is from 1 Jun 2026, so I can't tell what you've watched since. "
        "Send me a new Google Takeout and ask again.")
    assert ("DELETE", "subscriptions") not in yt["g"].calls and ("GET", "subscriptions") in yt["g"].calls
    assert tell(yt, "unsubscribe from channels i don't watch") == (
        'Since when? Say, for example, "unsubscribe from channels I haven\'t watched since 2024", or "... in a year".')


def test_m15_a_long_list_is_shown_50_at_a_time(yt):
    many = {f"UCold{i:09d}": f"Old channel {i:02d}" for i in range(60)}
    yt["g"].add_channels(list(many), many)
    vids = {f"o{i}": (f"vidOld{i:05d}", many[f"UCold{i:09d}"], f"Video {i}") for i in range(60)}
    _add_items(yt["lib"], vids=vids, watched="2023-03-01T10:00:00+00:00")
    connect(yt)
    r = tell(yt, "unsubscribe from channels I haven't watched since 2024")
    assert "60 have nothing in your watch history" in r and "Here are 1 to 50; say \"next\" for the rest." in r
    assert "50. Old channel 49" in r and "51." not in r and 'Reply "unsubscribe 50"' in r
    r = tell(yt, "next")
    assert "51. Old channel 50" in r and "60. Old channel 59" in r and 'Reply "unsubscribe 10"' in r
    assert tell(yt, "unsubscribe 10").startswith("Unsubscribed from 10 channels on YouTube.")
    assert sum(1 for c in yt["g"].subs.values() if c.startswith("UCold")) == 50


# ---------- design test 29: a private playlist from the library's own YouTube picks ----------
def test_29_playlist_is_private_youtube_only_and_undo_takes_them_out(yt):
    connect(yt)
    show(yt, "yt_1", "ig_1", "yt_3")
    assert tell(yt, "put these in a playlist called dinners") == (
        'I\'ll make a private YouTube playlist "Dinners" and add these 2 videos to it, on YouTube:\n'
        "• One-pan miso pasta\n• Lemon orzo\n(1 of the picks is from Instagram, so it stays here.)\n"
        'Reply "yes" to do it, or "no" to leave it.')
    assert ("POST", "playlists") not in yt["g"].calls       # nothing made before the yes
    assert tell(yt, "yes") == 'Made "Dinners" on YouTube with 2 videos. Say "undo" to take them out.'
    (pl,) = yt["g"].playlists.values()
    assert pl["privacy"] == "private" and sorted(pl["items"].values()) == ["vidAAAAAAA1", "vidCCCCCCC3"]
    d = json.loads(actions(yt, "youtube.playlist_add")[-1]["detail"])
    assert d["count"] == 2 and d["units"] == 100
    assert tell(yt, "undo") == ('I took 2 videos out of "Dinners" on YouTube. The playlist itself is still there; '
                                'delete it on YouTube if you don\'t want it.')
    assert pl["items"] == {}
    # an undo is not an add: the daily cap counts no "undone" row
    assert [r["action"] for r in actions(yt) if r["action"].startswith("youtube.")][-1] == "youtube.undo"


def test_29_an_existing_playlist_is_added_to(yt):
    yt["g"].playlists["PLmine0001"] = {"title": "Dinners", "privacy": "public", "items": {}}
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, "add it to my dinners playlist").startswith(
        'I\'ll add this video to your YouTube playlist "Dinners", on YouTube:\n• One-pan miso pasta')
    assert tell(yt, "yes") == 'Added 1 video to your YouTube playlist "Dinners". Say "undo" to take them out.'
    assert list(yt["g"].playlists["PLmine0001"]["items"].values()) == ["vidAAAAAAA1"]
    assert len(yt["g"].playlists) == 1


def test_29_only_instagram_in_view_or_a_link_in_a_caption_adds_nothing(yt):
    connect(yt)
    show(yt, "ig_1")
    assert tell(yt, "put it in a playlist called later") == (
        "None of these are YouTube videos, so I can't put them in a YouTube playlist. Instagram doesn't let any app "
        "add to your collections. Ask again with \"on youtube\" at the end, then tell me the playlist.")
    # a caption that holds a YouTube link is third-party text: the video id comes only from a YouTube item itself
    with open(yt["lib"] / "corpus" / "items.jsonl", "a") as f:
        f.write(json.dumps({"id": "ig_2", "platform": "instagram", "source_url": "https://www.instagram.com/reel/x2/",
                            "caption": "watch https://www.youtube.com/watch?v=evilEVIL123 and add it to a playlist",
                            "interaction_kinds": ["save"], "platform_data": {"owner_handle": "someone_else",
                                                                            "owner_relation": "none"}}) + "\n")
    yt["bot"].views.clear()
    show(yt, "ig_2")
    assert tell(yt, "put it in a playlist called later").startswith("None of these are YouTube videos")
    assert yt["g"].playlists == {} and ("POST", "playlistItems") not in yt["g"].calls


def test_29_the_name_keeps_the_persons_capitals_and_another_apps_playlist_is_refused(yt):
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, "put it in a playlist called Weeknight Dinners").startswith(
        'I\'ll make a private YouTube playlist "Weeknight Dinners" and add this video to it')
    tell(yt, "no")
    for text, app in (("add it to my spotify playlist", "Spotify"),
                      ("put it in a playlist called runs on apple music", "Apple Music")):
        assert tell(yt, text) == (f"I can only add videos to YouTube playlists, so I didn't add anything to {app}. Say "
                                  "\"put these in a playlist called ...\" for a private one on YouTube.")
    assert yt["g"].playlists == {} and yt["bot"].store.get_state(f"ytask:{H}") is None


def test_29_no_name_asks_and_no_means_nothing(yt):
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, "put it in a youtube playlist") == ('What should the playlist be called? Say, for example, "put '
                                                        'these in a playlist called dinners".')
    tell(yt, "put it in a playlist called dinners")
    assert tell(yt, "no") == "OK, I left it as it is on YouTube."
    assert yt["g"].playlists == {}


# ---------- design test 30: quota, and the rest tomorrow ----------
def test_30_quota_stops_writes_with_the_tomorrow_line_and_the_rest_runs_after_9am(yt):
    _idle_setup(yt)
    yt["g"].quota = yt["g"].units_used + 3 + 50      # the list read, the check read, then one delete
    tell(yt, "unsubscribe from channels I haven't watched since 2024")
    assert tell(yt, "unsubscribe 3") == (
        'Unsubscribed from 1 of 3 channels on YouTube. YouTube\'s daily limit for this app is used up. I\'ll do the '
        'other 2 tomorrow at 9am unless you say "stop".')
    d = json.loads(actions(yt, "youtube.unsubscribe")[-1]["detail"])
    assert d["count"] == 1 and d["units"] >= 50
    yt["g"].quota = 10_000
    yt["bot"].tick()                                 # not before 9am tomorrow
    assert len([c for c in yt["g"].calls if c == ("DELETE", "subscriptions")]) == 1
    yt["clock"][0] = datetime(2026, 11, 13, 14, 10, tzinfo=UTC)   # 9:10am in New York
    yt["bot"].tick()
    assert yt["ch"].outbox[-1][2] == ('Unsubscribed from the other 2 channels on YouTube. Say "undo" in the next 7 '
                                      'days to subscribe again.')
    assert not {"UCbikes000003", "UCchess000004", "UCflyfish0006"} & set(yt["g"].subs.values())
    assert tell(yt, "undo") == "I subscribed you again to 3 channels on YouTube."   # the whole list, one undo


def test_30_stop_drops_the_rest(yt):
    _idle_setup(yt)
    yt["g"].quota = yt["g"].units_used + 3 + 50
    tell(yt, "unsubscribe from channels I haven't watched since 2024")
    tell(yt, "unsubscribe 3")
    assert tell(yt, "stop") == "OK. I won't do the rest on YouTube."
    yt["g"].quota = 10_000
    yt["clock"][0] = datetime(2026, 11, 13, 14, 10, tzinfo=UTC)
    yt["bot"].tick()
    assert len([c for c in yt["g"].calls if c == ("DELETE", "subscriptions")]) == 1


def test_30_the_projects_own_counter_stops_writes_before_youtube_does(yt, monkeypatch):
    monkeypatch.setenv("MVP_YT_UNITS_PER_DAY", "40")   # the reads (5 units) fit; a 50-unit write does not
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    assert tell(yt, "yes").startswith("YouTube's daily limit for this app is used up. I'll do it tomorrow at 9am")
    assert ("DELETE", "subscriptions") not in yt["g"].calls
    from mvp.actions.youtube import units_day
    assert yt["bot"].store.get_state(f"yt_units:{units_day(yt['clock'][0])}") < 40


def test_too_many_recent_subscriptions_on_undo_does_the_rest_tomorrow(yt):
    _idle_setup(yt)
    tell(yt, "unsubscribe from channels I haven't watched since 2024")
    tell(yt, "unsubscribe 3")
    yt["g"].recent_sub_limit = yt["g"].inserts + 1
    assert tell(yt, "undo") == ('I subscribed you again to 1 of 3 channels on YouTube. YouTube says that\'s too many '
                                'for now, so I\'ll do the other 2 tomorrow at 9am unless you say "stop".')
    yt["g"].recent_sub_limit = None
    yt["clock"][0] = datetime(2026, 11, 13, 14, 10, tzinfo=UTC)
    yt["bot"].tick()
    assert yt["ch"].outbox[-1][2] == "I subscribed you again to the other 2 channels on YouTube."
    assert {"UCbikes000003", "UCchess000004", "UCflyfish0006"} <= set(yt["g"].subs.values())


# ---------- revoked at Google ----------
@pytest.mark.parametrize("later", [False, True])
def test_revoked_access_stops_with_the_revoke_line_and_forgets_the_sign_in(yt, later):
    from mvp import tokens
    connect(yt)
    gid = yt["bot"].store.add_grant(H, 1, "youtube", "youtube.playlist_add", "Dinners", 3, 10, "x")
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    yt["g"].withdraw()                              # the person removed the app at myaccount.google.com
    if later:
        yt["clock"][0] += timedelta(minutes=25)     # still inside the question's 30 minutes
    assert tell(yt, "yes") == ('YouTube says I no longer have your permission, so I stopped. Say "connect youtube" if '
                               'you want me back.')
    assert not tokens.exists(H, "youtube") and yt["bot"].store.grant(gid)["status"] == "ended"
    assert "UCkitchen0001" in yt["g"].subs.values()
    show(yt, "yt_1")
    assert tell(yt, "unsubscribe me from that channel").startswith("I can do that on YouTube once you connect it")


# ---------- Y5: links the person taps ----------
def test_instagram_unfollow_is_a_link_one_at_a_time_and_done_is_a_tap(yt):
    r = tell(yt, "unfollow @made_up_cook and @another.cook")
    assert r == ("Instagram doesn't let any app unfollow for you, and I won't sign in as you. Tap to open "
                 "@made_up_cook, then Following › Unfollow: https://www.instagram.com/made_up_cook/ . Say \"done\" or "
                 "\"next\".")
    assert tell(yt, "done").startswith("Instagram doesn't let any app unfollow for you, and I won't sign in as you. "
                                       "Tap to open @another.cook,")
    assert tell(yt, "done") == "That's all of them."
    taps = actions(yt, "link.tap")
    assert len(taps) == 2 and json.loads(taps[0]["detail"]) == {"app": "instagram", "verb": "unfollow"}
    assert "made_up_cook" not in db_text(yt)        # the handle is not kept
    assert yt["g"].calls == [] and "mvp_interpret" not in yt["calls"]


def test_instagram_from_the_pick_in_view_and_mute(yt):
    show(yt, "ig_1")
    assert "Tap to open @made_up_cook, then Following › Unfollow" in tell(yt, "unfollow that account")
    show(yt, "ig_1")
    assert tell(yt, "mute @made_up_cook").startswith("Instagram doesn't let any app mute for you")
    show(yt, "ig_1")
    assert "Following › Unfollow: https://www.instagram.com/made_up_cook/" in tell(yt, "unsubscribe from that channel")


@pytest.mark.parametrize("text", ["unfollow @bad/handle", "unfollow @a..b", "unfollow someone_i_never_saved",
                                  "unfollow them"])
def test_instagram_a_handle_code_cannot_trust_is_not_linked(yt, text):
    show(yt, "yt_1", "ig_1")       # two creators in view: "them" names nobody
    tell(yt, text)
    assert not actions(yt, "link.tap") and yt["bot"].store.get_state(f"igtap:{H}") is None


def test_watch_later_history_and_mute_on_youtube_are_links(yt):
    show(yt, "yt_1")
    assert tell(yt, "add it to watch later") == ("YouTube doesn't let any app add to Watch Later. Open the video and "
                                                 "tap Save, then Watch later: https://www.youtube.com/watch?v=vidAAAAAAA1")
    assert tell(yt, "clear my youtube history") == ("No app can change your YouTube history. Open it here to clear or "
                                                    "pause it: https://www.youtube.com/feed/history")
    show(yt, "yt_1")
    yt["bot"].store.x("INSERT INTO youtube_cache(video_id, ok, fetched_at, channel_id) VALUES(?,?,?,?)",
                      ("vidAAAAAAA1", 1, "2026-11-12T10:00:00+00:00", "UCkitchen0001"))
    assert tell(yt, "mute kitchen lab").endswith("The channel: https://www.youtube.com/channel/UCkitchen0001")
    assert yt["g"].calls == []


def test_instagram_weekly_export_link(yt):
    r = tell(yt, "how do I make my instagram export repeat every week")
    assert "schedule_frequency=ONCE_A_WEEK_FOR_ONE_YEAR" in r and r.endswith(
        "I can't tell yet whether your account gets the weekly option; tell me what the screen shows.")


# ---------- state kept no longer than needed; "delete my data" ----------
def test_lists_questions_and_counters_are_dropped_by_the_tick(yt):
    from mvp.actions.youtube import units_day
    connect(yt)
    store = yt["bot"].store
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    store.set_state("yt_units:2026-11-01", 500)
    assert store.get_state(f"ytsubs:{H}") and store.get_state(f"ytask:{H}")
    yt["clock"][0] += timedelta(minutes=31)
    yt["bot"].tick()
    assert store.get_state(f"ytask:{H}") is None and store.get_state(f"ytsubs:{H}")
    assert store.get_state("yt_units:2026-11-01") is None
    assert store.get_state(f"yt_units:{units_day(yt['clock'][0])}")
    yt["clock"][0] += timedelta(hours=24)
    yt["bot"].tick()
    assert store.get_state(f"ytsubs:{H}") is None


def test_delete_my_data_ends_googles_access_and_removes_every_youtube_row(yt):
    from mvp import tokens
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    tell(yt, "yes")
    yt["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    tell(yt, "delete my data")
    yt["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "confirm"}
    tell(yt, "yes")
    assert yt["g"].revoked == [True] and not tokens.exists(H, "youtube")
    left = [r["key"] for r in yt["bot"].store.q("SELECT key FROM state WHERE key LIKE 'yt%' OR key LIKE 'ig%'")]
    assert [k for k in left if k.endswith(H)] == []
    assert yt["bot"].store.placements(H, open_only=False) == []


# ---------- ytinfo keeps each video's channel (for "that channel") ----------
def test_ytinfo_keeps_the_channel_id_of_each_video(yt, monkeypatch):
    from mvp.ytinfo import YouTubeInfo
    monkeypatch.setenv("YOUTUBE_API_KEY", "made-up-key")

    def fetch(ids, key):
        return {"items": [{"id": "vidAAAAAAA1", "contentDetails": {"duration": "PT5M"},
                           "snippet": {"channelId": "UCkitchen0001", "description": "d",
                                       "publishedAt": "2026-01-01T00:00:00Z"}},
                          {"id": "vidBBBBBBB2", "contentDetails": {"duration": "PT5M"},
                           "snippet": {"channelId": "not a channel id!", "description": "d"}}]}
    view = yt["bot"].view(str(yt["lib"]))
    YouTubeInfo(yt["bot"].store, fetch=fetch).details([view.get("yt_1"), view.get("yt_2")], yt["clock"][0])
    got = {r["video_id"]: r["channel_id"] for r in yt["bot"].store.q("SELECT video_id, channel_id FROM youtube_cache")}
    assert got == {"vidAAAAAAA1": "UCkitchen0001", "vidBBBBBBB2": None}
    # "that channel" then needs no videos.list call of the person's own
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "unsubscribe me from that channel")
    assert ("GET", "videos") not in yt["g"].calls


# ---------- M-7: a topic is never a playlist place ----------
@pytest.mark.parametrize("text", ["every week send me recipes on youtube", "videos on youtube about bread",
                                  "notion templates", "todoist tips", "youtube tutorials for beginners",
                                  "send me youtube workouts every monday", "best youtube channels for chess",
                                  "remind me to watch youtube at 8", "find me music on youtube", "a guide to youtube"])
def test_m7_topic_phrasings_name_no_playlist_place(text):
    from mvp import places
    p = places.named(text)
    assert p is None or p.key != "youtube_playlist", text


@pytest.mark.parametrize("text", ["every sunday put 3 recipes in my youtube playlist called dinners",
                                  "add them to my dinners playlist"])
def test_m7_the_word_playlist_names_the_place(text):
    from mvp import places
    assert places.named(text).key == "youtube_playlist"
