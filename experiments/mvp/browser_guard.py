"""PROTOTYPE ONLY - what the browser may press, what is the last step, what a page is (round 10, slice V1; DESIGN.md
section 17.V; amendment A-016, Proposed). Pure functions: no browser, no model, no network.

Ported from the do-for-you prototype's guard (36 of 36 checks on the practice merchant), with the critic's and the
addendum's additions: sites the bot never drives whatever the settings say (`DENIED_SITES`), and what may be quoted
from a merchant's page (only the sentences that state the effects or the outcome, links and addresses removed, never a
sentence aimed at an assistant). The page is third-party data: nothing on it can choose an element, a link or a route.

    snap = page.evaluate(SNAPSHOT_JS)            # {elements, frames, text, url, title, h1, hidden}
    page_state(snap, domains, final_names)     # off_site | captcha | otp | login_wall | kept | outcome_ok |
                                               # final_step | normal
    allowed(el, "click" | "confirmed_click", domains, snap, final_names) -> (ok, reason)
    el_hash(snap, el)                          # what the person's "yes cancel <merchant>" binds to
"""
import hashlib
import re
from urllib.parse import urlparse

SNAPSHOT_JS = r"""
() => {
  const out = []; let n = 0;
  document.querySelectorAll('[data-sd-id]').forEach(e => e.removeAttribute('data-sd-id'));
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const region = e => { const r = e.closest('section,form,fieldset,aside,dialog,[role=dialog],[role=region],li');
    return r ? r.innerText.trim().replace(/\s+/g,' ').slice(0,160) : ''; };
  for (const e of document.querySelectorAll('a,button,input,select,textarea,[role=button],[role=link]')) {
    if (!vis(e)) continue;
    const id = 'e' + (++n); e.setAttribute('data-sd-id', id);
    let name = e.getAttribute('aria-label') || '';
    if (!name && e.labels && e.labels.length) name = e.labels[0].innerText;
    if (!name) name = e.innerText || e.value || e.getAttribute('placeholder') || '';
    out.push({id, tag: e.tagName.toLowerCase(), type: (e.getAttribute('type')||'').toLowerCase(),
      name: name.trim().replace(/\s+/g,' ').slice(0,80), href: e.href || null, disabled: !!e.disabled,
      autocomplete: (e.getAttribute('autocomplete')||'').toLowerCase(), field: (e.getAttribute('name')||'').toLowerCase(),
      ctx: region(e)});
  }
  let hidden = 0;
  for (const e of document.querySelectorAll('body *')) {
    const s = getComputedStyle(e); const fs = parseFloat(s.fontSize);
    if (e.children.length === 0 && e.textContent.trim() && (fs < 3 || s.color === s.backgroundColor ||
        s.color === 'rgb(255, 255, 255)' && getComputedStyle(document.body).backgroundColor !== 'rgb(0, 0, 0)'))
      hidden += 1;
  }
  const frames = [...document.querySelectorAll('iframe')].map(f => f.src);
  const h1 = (document.querySelector('h1')||{}).innerText || '';
  return {elements: out, frames, text: document.body ? document.body.innerText.slice(0, 4000) : '', url: location.href,
          title: document.title, h1: h1.slice(0,120), hidden};
}"""

# ---------- sites the bot never drives, whatever MVP_BROWSER_MERCHANTS says (addendum V5) ----------
# Social media (their terms forbid automated access even when the person is signed in; docs/07) and Google's own
# pages (YouTube has an official connector, slice Y; Google sign-in refuses an automated browser).
DENIED_SITES = ("instagram.com", "cdninstagram.com", "facebook.com", "fb.com", "messenger.com", "threads.net",
                "threads.com", "tiktok.com", "x.com", "twitter.com", "snapchat.com", "reddit.com", "youtube.com",
                "youtu.be", "accounts.google.com")

REFUSE = re.compile(
    r"\b(?:accept|claim|get \d+ ?% off|\d+ ?% off|upgrade|subscribe|buy|purchase|pay|join|start|resume|"
    r"keep (?:my )?(?:plan|membership|subscription)|stay|switch|redeem|add|reactivate|restart|yes,? i want|"
    r"pause|snooze|take a break|put .{0,20} on hold|hold my|downgrade|change (?:my )?plan|cheaper plan|"
    r"special offer|deal|save \d+|free months?|gift|try .{0,15} free|unlock)\b", re.I)
GENERIC = re.compile(r"^(?:confirm|continue|yes|ok|okay|next|submit|done|i agree|agree|got it|proceed|go|sure)\W*$",
                     re.I)
OFFER_CTX = re.compile(r"\$\s?\d|\d+ ?%|/ ?mo\b|per month|\bfree\b|\boffer\b|\bdeal\b|\bdiscount\b|\bpause\b|"
                       r"\bupgrade\b|\bsave\b", re.I)
TO_BOT = re.compile(r"\b(?:ai|a\.i\.|assistant|agent|bot|llm|gpt|claude|automated)\b", re.I)
FINAL = re.compile(r"\b(?:finish cancell?(?:ation|ing)|confirm cancell?ation|complete cancell?ation|yes,? cancel|"
                   r"cancel (?:my )?(?:membership|subscription|plan) now|end (?:my )?membership|turn off auto-?renew)\b",
                   re.I)
SECRET_FIELD = re.compile(r"password|passcode|cc-|card|cvv|cvc|iban|account.?number|one-time-code|otp|ssn", re.I)
SOFT_FINAL = re.compile(r"\b(?:cancel|end|confirm|finish|terminate|deactivate|yes)\b", re.I)
EFFECTS = re.compile(r"\b(?:ends? on|will end|won'?t be charged|will not be charged|access until|lose access|"
                     r"you can (?:watch|use|listen) until)\b", re.I)
CAPTCHA_HOSTS = ("google.com/recaptcha", "hcaptcha.com", "challenges.cloudflare.com", "arkoselabs.com")
CAPTCHA_TEXT = re.compile(r"verify you are (?:a )?human|are you a robot|press and hold|complete the security check", re.I)
OTP_TEXT = re.compile(r"enter the code|verification code|we sent (?:you )?a code|two-step|2-step", re.I)
OK_OUTCOME = re.compile(r"(?:membership|subscription|plan) (?:has been|was|is) cancell?ed|cancell?ation (?:is )?confirmed|"
                        r"won't renew|will not renew|we've cancell?ed", re.I)
KEPT = re.compile(r"discount is applied|plan continues|welcome back|you're still a member|is paused|paused until|"
                  r"you've upgraded|welcome to ultra|offer (?:is )?applied", re.I)
INSTRUCTIONS = re.compile(r"\b(?:ai assistants?|assistants?|agents?|llms?|bots?)\b.{0,80}\b(?:click|press|type|visit|"
                          r"ignore|agreed|do not ask|don'?t ask)\b", re.I)
REASON_OK = ("prefer not to say", "other", "i don't use it", "i dont use it", "not using it", "too expensive")
WALLS = ("login_wall", "captcha", "otp", "off_site")
_LINKISH = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+|\b[\w-]+\.(?:com|net|org|io|co|example)\b\S*", re.I)
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def host(u):
    return (urlparse(u).hostname or "").lower() if u else ""


def denied(url_or_host):
    """True for a page on a site the bot never drives (DENIED_SITES), given a URL or a bare host."""
    h = host(url_or_host) if "/" in str(url_or_host or "") else str(url_or_host or "").lower().strip(".")
    return any(h == d or h.endswith("." + d) for d in DENIED_SITES)


def text_hash(snap):
    return hashlib.sha256(snap["text"].encode()).hexdigest()


def el_hash(snap, el):
    """What the person's yes binds to: the page address, the button's name and tag, and the page's whole text."""
    return hashlib.sha256("|".join([snap["url"], el["name"], el["tag"], text_hash(snap)]).encode()).hexdigest()


def offer_around(el):
    return bool(OFFER_CTX.search(el.get("ctx") or "")) and (el.get("ctx") or "").strip() != ""


def is_final(el, snap, final_names=()):
    """The last step: the merchant's own final button name (route file), a known final wording, or any cancel-like
    button on a page that states the effects. Never a button inside an offer or one that speaks to the bot."""
    n = el["name"]
    if REFUSE.search(n) or TO_BOT.search(n):
        return False
    return bool(n.lower() in {x.lower() for x in final_names} or FINAL.search(n)
                or (SOFT_FINAL.search(n) and EFFECTS.search(snap["text"])))


def page_state(snap, domains, final_names=()):
    els, text = snap["elements"], snap["text"]
    if host(snap["url"]) not in domains or denied(snap["url"]):
        return "off_site"
    if any(any(h in f for h in CAPTCHA_HOSTS) for f in snap["frames"]) or CAPTCHA_TEXT.search(text):
        return "captcha"
    if any(e["autocomplete"] == "one-time-code" for e in els) or OTP_TEXT.search(text):
        return "otp"
    if any(e["type"] == "password" for e in els):
        return "login_wall"
    if KEPT.search(text):
        return "kept"
    if OK_OUTCOME.search(text):
        return "outcome_ok"
    if any(is_final(e, snap, final_names) and allowed(e, "confirmed_click", domains, snap, final_names)[0]
           for e in els):
        return "final_step"
    return "normal"


def allowed(el, action, domains, snap, final_names=()):
    """(ok, reason). Only "click" and "confirmed_click" exist; code decides, a label from anywhere never allows."""
    n = el["name"]
    if action not in ("click", "confirmed_click"):
        return False, "only presses: the bot never types"
    if el.get("disabled"):
        return False, "disabled"
    if el["tag"] in ("input", "textarea", "select"):
        if el["tag"] == "input" and el["type"] == "radio":
            if n.lower().strip(" .") not in REASON_OK:
                return False, "only a neutral reason may be picked"
        else:
            return False, "a field or a box: the bot never fills or ticks"
    if SECRET_FIELD.search((el.get("autocomplete") or "") + " " + (el.get("field") or "")):
        return False, "a secret field"
    if el.get("href") and (host(el["href"]) not in domains or denied(el["href"])):
        return False, "leaves the merchant's site"
    if TO_BOT.search(n):
        return False, "the button speaks to the bot"
    if REFUSE.search(n):
        return False, "buys, upgrades, pauses or accepts an offer"
    if GENERIC.match(n) and offer_around(el):
        return False, "a generic button inside an offer"
    if is_final(el, snap, final_names) and action != "confirmed_click":
        return False, "the last step: needs the person's yes"
    return True, "ok"


def flagged(snap):
    """True when the page carries words aimed at an assistant or hidden text (noted in the run's counts; a page can
    never steer the runner, which follows names from the merchant's own help page)."""
    return bool(INSTRUCTIONS.search(snap.get("text") or "")) or int(snap.get("hidden") or 0) > 0


def _clean(sentence):
    s = _LINKISH.sub("", sentence)
    return " ".join(s.split()).strip()


def quote(text, rx, limit=200):
    """The merchant's own words to show the person: the sentences of the first line of the page that `rx` matches,
    links and addresses removed, never a sentence aimed at an assistant or the bot, at most `limit` characters. ""
    when there is none. Only this ever leaves the page (D-10)."""
    for line in (text or "").split("\n"):
        if not rx.search(line):
            continue
        keep = []
        for m in _SENTENCE.finditer(line):
            s = _clean(m.group(0))
            if not s or not rx.search(s) or INSTRUCTIONS.search(s) or TO_BOT.search(s) or '"' in s:
                continue
            if len(" ".join(keep + [s])) > limit:
                break
            keep.append(s)
        if keep:
            return " ".join(keep)
    return ""


def effects_quote(text):
    """What the last page says will happen ("Your membership ends on 1 Dec 2026. You won't be charged again.")."""
    return quote(text, EFFECTS)


def outcome_quote(text, phrases=()):
    """What the page says after the press ("Your membership has been cancelled. You can watch until 1 Dec 2026.")."""
    extra = [re.escape(p) for p in phrases or () if p]
    rx = re.compile("|".join([OK_OUTCOME.pattern, EFFECTS.pattern] + extra), re.I)
    return quote(text, rx)


def end_date(sentence, today):
    """The first full date in the merchant's sentence (a datetime.date), or None."""
    from .dates import find_dates
    found = find_dates(sentence or "", year_hint=today.isoformat())
    return found[0][0] if found else None
