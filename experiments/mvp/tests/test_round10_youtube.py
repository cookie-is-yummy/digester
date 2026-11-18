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

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
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
    assert tell(yt, "connect youtube").startswith("YouTube isn't set up here yet")
    show(yt, "yt_1")
    assert tell(yt, "unsubscribe me from that channel").startswith("YouTube isn't set up here yet")
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
    from mvp import config, connectors as C
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
