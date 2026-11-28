"""PROTOTYPE ONLY - shared text helpers for experiments (information gate, stopwords)."""
import re
import unicodedata

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

GENERIC = {"fyp", "viral", "reels", "explore", "explorepage", "foryou", "foryoupage", "trending", "reelsinstagram",
           "viralreels", "instagood", "reel", "fy", "fypage", "fypシ", "foryourpage", "explorer", "reelitfeelit",
           "instadaily", "love", "follow", "like", "instagram", "tiktok", "video", "videos", "funny", "meme", "memes"}
STOP = GENERIC | {"comment", "share", "save", "link", "bio", "check", "new", "day", "make", "just", "don", "get",
                  "want", "time", "like", "know", "people", "really", "got", "going", "thing", "things", "way",
                  "one", "follow", "credit", "dm", "removal", "owner", "rights", "reserved", "please", "thank",
                  "thanks", "today", "first", "best", "good", "see", "let", "need", "use", "can", "will", "also",
                  "would", "start", "made", "years", "part", "how", "what", "this", "that"} | set(ENGLISH_STOP_WORDS)


def strip_tags(cap):
    return re.sub(r"(#\S+|@\S+|https?://\S+)", " ", cap or "")


def letters(s):
    latin = other = 0
    for ch in s:
        if ch.isalpha():
            if "LATIN" in unicodedata.name(ch, ""):
                latin += 1
            else:
                other += 1
    return latin, other


def info_class(item):
    """'ok' = enough topical signal; 'low' = too little text; 'non_english' = mostly non-Latin script."""
    text = strip_tags(item.get("caption", ""))
    latin, other = letters(text)
    tags = [h.lower() for h in (item["platform_data"].get("hashtags") or [])]
    topical = [t for t in tags if t not in GENERIC and letters(t)[0] >= 3]
    if other > latin and other >= 10:
        return "non_english"
    if latin >= 40 or len(topical) >= 3:
        return "ok"
    return "low"
