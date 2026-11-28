"""PROTOTYPE ONLY - links the person taps to do something only they can do (round 10, slice Y5; DESIGN.md section 17.Y;
amendment A-015, Proposed).

No outside write and no registry entry: these build a link from what code holds (a creator's handle from the person's
own export, a video or channel id from their own library or from YouTube's answer), never from a caption, a title or
anything a model wrote. Instagram lets no app follow, unfollow, mute or save for a personal account, and the bot never
signs in as the person, so it sends the link and the taps to make. "done" after a link is logged as `link.tap` in
action_log (the app and the verb; never the handle).
"""
import re

_IG = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_VID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CH = re.compile(r"^UC[A-Za-z0-9_-]{10,40}$")

YT_CHANNELS = "https://www.youtube.com/feed/channels"
YT_HISTORY = "https://www.youtube.com/feed/history"
YT_WATCH_LATER = "https://www.youtube.com/playlist?list=WL"
YT_PREMIUM = "https://www.youtube.com/paid_memberships"


def instagram_handle(creator):
    """'@made_up_cook' or 'made_up_cook' -> 'made_up_cook'; None when it is not a plain Instagram handle."""
    h = (creator or "").strip().lstrip("@")
    return h if _IG.match(h) and not h.startswith(".") and ".." not in h else None


def instagram_profile(handle):
    h = instagram_handle(handle)
    return f"https://www.instagram.com/{h}/" if h else None


def youtube_video(video_id):
    return f"https://www.youtube.com/watch?v={video_id}" if video_id and _VID.match(video_id) else None


def youtube_channel(channel_id):
    """The channel's own page when its id is known (Subscribed › Unsubscribe; ⋮ › Don't recommend); else the list of
    the person's channels."""
    return f"https://www.youtube.com/channel/{channel_id}" if channel_id and _CH.match(channel_id) else YT_CHANNELS


def tap(store, handle, app, verb, now):
    """The person said "done" after a link: logged as a tap (no outside write was made by the bot)."""
    store.log_action(handle, None, None, "link.tap", "done", detail={"app": app, "verb": verb}, at=now)
