"""PROTOTYPE ONLY - "what did you do for me": an honest list of what the bot did and what it only prepared (round 9,
W9; DESIGN.md section 16.F).

Read by code, no model call, from the rows the bot already keeps: action_log (emails to the person, calendar links,
Drafts-folder drafts), drafts (emails to other people and cancellation notices), placements (things put in an outside
place: Reminders and Calendar on the Mac, TickTick, Todoist, a webhook), cancellations and to-dos. Last 7 days (or
today), newest first, then what is still waiting and what can still be undone.

The words follow what the bot can see, never more:
  - "I sent" only for an email the mail server took (drafts.status "sent"); "you sent" only when the person said so;
    a link the person opened is "prepared ... I can't see whether you sent it";
  - "added" / "removed" only for things the outside place gave an id for (placements);
  - a calendar link is "gave you", never "added to your calendar";
  - a webhook is "sent to your webhook (I can't see what it did there)";
  - a cancellation never says cancelled; no merchant is named (money stays out of digests, docs/07).
"""
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import texts as T
from .store import now_iso

DAYS = 7
_THANKS = r"(?:[\s,]+(?:please|pls|then|again))?\W*$"
RECEIPTS = re.compile(
    r"^\W*(?:(?:so|ok|okay|hey)[\s,]+)?(?:"
    r"what\s+(?:have|did)\s+you\s+(?:done|do)\s+(?:for\s+me(?:\s+(?:today|this\s+week|lately|recently|so\s+far))?|"
    r"(?:today|this\s+week|lately|recently|so\s+far)(?:\s+for\s+me)?)"
    r"|what\s+(?:did|have)\s+you\s+(?:send|sent)(?:\s+(?:for\s+me|today|this\s+week|lately|recently))+"
    r"|what\s+have\s+you\s+sent"
    r"|(?:show|give)\s+(?:me\s+)?my\s+(?:activity|receipts)"
    r"|my\s+(?:activity|receipts)"
    r"|what(?:'s|\s+is|\s+are)\s+(?:still\s+)?waiting(?:\s+(?:for\s+me|on\s+me))?"
    # ---------- round 10, slice W (W5): "show me what you've done for me this week", "what did you add to my X"
    r"|(?:show|tell)\s+me\s+what\s+you(?:'ve|\s+have)?\s+(?:done|did)(?:\s+for\s+me)?"
    r"(?:\s+(?:today|this\s+week|lately|recently|so\s+far))?"
    r"|what\s+(?:did|have)\s+you\s+(?:add|added|put)\s+(?:to|in|on|into)\s+my\s+[\w ]{2,30}?"
    r"(?:\s+(?:today|this\s+week|lately|recently))?"
    # ---------- checks of round 10 (reading): the same question in more everyday words, a class the held-out set
    # showed (made-up examples here: "show me everything you did", "what have you been doing for me", "did you do
    # anything for me today", "what did you get done today", "list what you've done") ----------
    r"|(?:show|tell|list|give)\s+(?:me\s+)?(?:everything|all|what)\s+(?:(?:that|of\s+what)\s+)?you(?:'ve|\s+have)?\s+"
    r"(?:did|done|have\s+done|handled|sent)(?:\s+for\s+me)?"
    r"|list\s+what\s+you(?:'ve|\s+have)?\s*(?:ve\s+)?(?:did|done)"
    r"|what\s+(?:have|did)\s+you\s+(?:been\s+doing|handled?|taken\s+care\s+of|actually\s+(?:do|done)|get\s+done|got\s+done)"
    r"(?:\s+for\s+me)?"
    r"|(?:did|have)\s+you\s+(?:do|done)\s+anything\s+for\s+me"
    r"|anything\s+you(?:'ve|\s+have)?\s+(?:did|done)\s+for\s+me"
    r"|what\s+(?:stuff|things)\s+(?:did|have)\s+you\s+(?:do|done)(?:\s+for\s+me)?"
    r")(?:\s+(?:today|this\s+week|lately|recently|so\s+far))?" + _THANKS, re.I)
# "what did you do": only when something was done for them in the last 7 days (else the usual path reads it)
RECEIPTS_BARE = re.compile(r"^\W*what\s+(?:did|have)\s+you\s+(?:do|done)\W*$", re.I)
TODAY = re.compile(r"\btoday\b", re.I)
WAITING_ONLY = re.compile(r"\bwaiting\b", re.I)
DID_SEND = re.compile(r"^\W*did\s+you\s+(?:(?:really|already|actually)\s+)?(?:send|email|mail|write)\s+"
                      r"(?:(?:the|my|that|an?)\s+)?(?:(?:e-?mail|mail|message|note|notice|draft)\s+)?(?:to|for)\s+"
                      r"(?P<who>[^?.!]{1,60}?)\W*$", re.I)


def when_words(dt, now, tz):
    """'today at 6:04pm', 'yesterday at 9am', 'on Monday at 6:04pm', 'on 3 Nov at 9am' (a past moment)."""
    z = ZoneInfo(tz)
    local, today = dt.astimezone(z), now.astimezone(z).date()
    clock = local.strftime("%-I:%M%p").lower().replace(":00", "")
    days = (today - local.date()).days
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"yesterday at {clock}"
    if 1 < days < 7:
        return f"on {local:%A} at {clock}"
    return f"on {local:%-d %b} at {clock}"


def day_words(dt, now, tz):
    return when_words(dt, now, tz).rsplit(" at ", 1)[0]


def _t(s):
    return datetime.fromisoformat(s) if s else None


def _parts(row):
    p = row.get("parts")
    if isinstance(p, dict):
        return p
    try:
        return json.loads(p or "{}") or {}
    except ValueError:
        return {}


def who_of(row):
    """Who a draft is to, in the person's own words where the bot still has them: the name they typed, "your
    landlord", the address's domain (kept after the words are cleared), else "someone"."""
    p = _parts(row)
    if row.get("to_name"):
        return row["to_name"]
    if p.get("to_word"):
        return f"your {p['to_word']}"
    if row.get("to_domain"):
        return f"someone at {row['to_domain']}"
    return "someone"


def _what(row, n=1):
    if row.get("kind") == "notice":
        return "cancellation notice" if n == 1 else "cancellation notices"
    return "email" if n == 1 else "emails"


def _n(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


class ReceiptsMixin:
    """The read in answer_normally (hook 8): "what did you do for me", "did you send the email to Maria"."""

    def receipts_reads(self, person, text, now):
        t = " ".join((text or "").split())
        if not t or len(t) > 100:
            return None
        h = person["handle"]
        m = DID_SEND.match(t)
        if m:
            self.note(intent="receipts")
            return self.send(h, self._did_send(person, m.group("who"), now))
        if RECEIPTS_BARE.match(t):   # round 10, slice W (W5)
            if not self._receipt_lines(person, now - timedelta(days=DAYS), now):
                return None
        elif not RECEIPTS.match(t):
            return None
        self.note(intent="receipts")
        today = bool(TODAY.search(t))
        return self.send(h, self.receipts_text(person, now, today=today, waiting_only=bool(WAITING_ONLY.search(t))))

    # ---------- the whole list ----------
    def receipts_text(self, person, now, today=False, waiting_only=False):
        h, tz = person["handle"], person["timezone"]
        z = ZoneInfo(tz)
        if today:
            local = now.astimezone(z)
            since = local.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = now - timedelta(days=DAYS)
        did = [] if waiting_only else self._receipt_lines(person, since, now)
        did.sort(key=lambda r: r[0], reverse=True)   # newest first
        waiting = self._waiting_lines(person, now)
        out = []
        if did:
            out.append(T.RECEIPTS_HEAD_TODAY if today else T.RECEIPTS_HEAD)
            out += [f"• {line}" for _, line in did]
        elif not waiting_only:
            out.append(T.RECEIPTS_NOTHING_TODAY if today else T.RECEIPTS_NOTHING)
        if waiting:
            out.append(T.RECEIPTS_WAITING)
            out += [f"• {line}" for line in waiting]
        elif waiting_only:
            out.append(T.RECEIPTS_NOTHING_WAITING)
        standing = [] if waiting_only else self._standing_lines(h)   # round 10, slice G
        if standing:
            out.append(T.RECEIPT_STANDING)
            out += [f"• {line}" for line in standing]
        lw = self._last_write(h, now)
        if lw and lw["kind"] != "final":
            out.append(T.receipts_undo(lw["say"]))
        if not waiting_only:
            agent = self.store.one("SELECT COUNT(*) AS n FROM action_log WHERE handle=? AND action LIKE 'mcp.%' AND at>=?",
                                   (h, now_iso(since)))
            if agent and agent["n"]:
                out.append(T.receipts_agent(agent["n"]))
        return "\n".join(out)

    def _receipt_lines(self, person, since, now):
        """[(latest moment, line)] for each kind of thing the bot did since `since`."""
        h, tz = person["handle"], person["timezone"]
        s = now_iso(since)
        lines = []
        log = self.store.q("SELECT action, status, detail, at FROM action_log WHERE handle=? AND at>=? ORDER BY id",
                           (h, s))

        def rows(action, *status):
            return [r for r in log if r["action"] == action and (not status or r["status"] in status)]

        # email to the person themselves (email.send: SMTP "done", the outbox here, a link to themselves)
        for status, say in (("done", T.receipt_emailed_you), ("outbox", T.receipt_outbox),
                            ("link", T.receipt_self_link)):
            got = rows("email.send", status)
            if got:
                last = _t(got[-1]["at"])
                lines.append((last, say(len(got), day_words(last, now, tz))))
        # emails and notices to other people (drafts)
        lines += self._draft_receipts(person, s, now)
        # a real draft in the Drafts folder (A5) and one taken out again
        got = rows("mailbox.draft", "done")
        if got:
            gone = len(rows("mailbox.undraft", "done"))
            lines.append((_t(got[-1]["at"]), T.receipt_drafts_folder(len(got), gone)))
        # calendar links (the bot can't see whether they were added)
        got = rows("calendar.add", "done")
        if got:
            lines.append((_t(got[-1]["at"]), T.receipt_calendar_links(len(got))))
        # to-dos on the bot's own lists
        todos = self.store.q("SELECT created_at, done_at, removed_at FROM todos WHERE handle=? AND created_at>=? "
                             "ORDER BY id", (h, s))
        if todos:
            gone = sum(1 for x in todos if x["removed_at"])
            done = sum(1 for x in todos if x["done_at"] and not x["removed_at"])
            lines.append((_t(todos[-1]["created_at"]), T.receipt_todos(len(todos), done, gone)))
        # things put in an outside place (placements: ids only)
        lines += self._placement_receipts(h, s)
        # the live check of 19 Nov (DESIGN.md section 17.L, F2): what the browser did after the person's "yes cancel
        # <merchant>", in the page's own words kept for the run; never the bot's claim that anything ended
        pressed = self._browser_receipts(person, s, now)
        lines += [(at, line) for at, line, _ in pressed]
        done_by_browser = {cid for _, _, cid in pressed if cid}
        # the cancel helper (no merchant named)
        cans = [r for r in self.store.cancellations(h) if (r.get("updated_at") or "") >= s
                and r["id"] not in done_by_browser]
        if cans:
            said = sum(1 for r in cans if r["status"] == "person_says_done")
            # round 10, slice D: "notice_sent" is a notice the bot sent after their "send"
            sent = sum(1 for r in cans if r["status"] in ("person_sent", "notice_sent"))
            # (round 9 checks) a notice the mailbox sent after their "send" is the bot's send, never "you sent"
            mine = sum(1 for r in cans if r["status"] == "notice_sent" or (
                r["status"] == "person_sent" and r.get("draft_id")
                and (self.store.draft(r["draft_id"]) or {}).get("status") == "sent"))
            dropped = sum(1 for r in cans if r["status"] == "dropped")
            lines.append((max(_t(r["updated_at"]) for r in cans),
                          T.receipt_cancellations(len(cans), said, sent - mine, len(cans) - said - sent - dropped,
                                                  mine=mine)))
        return lines

    def _browser_receipts(self, person, since, now):
        """[(moment, line, cancellation id)] for each browser run that pressed the last button since `since` (F2)."""
        h, tz = person["handle"], person["timezone"]
        out = []
        for run in self.store.browser_runs_of(h):
            pressed = run["status"] in ("page_says_cancelled", "page_unclear") or (
                run["status"] == "offer_taken" and run.get("final_name"))
            if not pressed or not run.get("ended_at") or run["ended_at"] < since or not run.get("final_name"):
                continue
            name, practice = run["site_key"] or "the site", False
            try:
                from . import browser
                r = browser.route(run["site_key"])
                if r is not None:
                    name, practice = r["name"], bool(r.get("practice"))
                else:
                    name = name[:1].upper() + name[1:]
            except Exception:  # noqa: BLE001 - the receipts never break on the browser
                pass
            at = _t(run["ended_at"])
            out.append((at, T.receipt_browser(name, run["final_name"], run.get("outcome_quote") or "",
                                              when_words(at, now, tz), run["status"], practice=practice),
                        run.get("cancellation_id")))
        return out

    def _draft_receipts(self, person, since, now):
        h, tz = person["handle"], person["timezone"]
        out = []
        drafts = [d for d in self.store.drafts_of(h)
                  if max(d.get("done_at") or "", d.get("shown_at") or "", d.get("created_at") or "") >= since]
        sender = self._mailbox_sender(h) if hasattr(self, "_mailbox_sender") else None
        for d in reversed(drafts):   # newest first inside the groups too
            at = _t(max(d.get("done_at") or "", d.get("shown_at") or "", d.get("created_at") or ""))
            st, who, what = d["status"], who_of(d), _what(d)
            if st == "sent":   # the mail server took it (W4): the only "I sent"
                out.append((at, T.receipt_sent(what, who, sender, when_words(_t(d["done_at"]) or at, now, tz))))
            elif st == "person_sent":
                out.append((at, T.receipt_person_sent(what, who, day_words(at, now, tz))))
            elif st == "unknown":
                out.append((at, T.receipt_unknown(what, who)))
            elif st == "failed":   # (round 9 checks) the mail server refused it or could not be reached: not sent
                out.append((at, T.receipt_failed(what, who)))
            elif st in ("link_shown", "expired") and d.get("version"):
                out.append((at, T.receipt_prepared(what, who, d.get("route") == "mailbox", day_words(at, now, tz))))
            # open (never shown), held and sending are waiting; cancelled was dropped by the person
        return out

    def _placement_receipts(self, h, since):
        from . import connectors as C
        rows = self.store.placements(h, since=None, open_only=False)
        rows = [r for r in rows if (r["created_at"] or "") >= since or (r.get("removed_at") or "") >= since]
        out = []
        for key, con in C.CONNECTORS.items():
            for action, (one, many) in con.nouns.items():
                got = [r for r in rows if r["connector"] == key and r["action"] == action]
                if not got:
                    continue
                made = [r for r in got if (r["created_at"] or "") >= since]
                gone = sum(1 for r in got if r.get("removed_at"))
                last = max(_t(r.get("removed_at") or r["created_at"]) for r in got)
                line = T.receipt_placed(len(made), gone, one, many, con.where, con.kind)
                # round 10, slice G: how many of them a rule added under its grant ("(4 by rule 3)")
                by = {}
                for r in made:
                    if r.get("rule_id"):
                        by[r["rule_id"]] = by.get(r["rule_id"], 0) + 1
                if by:
                    tail = T.receipt_by_rule(sorted((self.store.rule_number(h, k), c) for k, c in by.items()))
                    line = line.replace(f" {con.where}", f" {con.where}{tail}", 1)
                out.append((last, line))
        return out

    def _standing_lines(self, h):
        """Round 10, slice G: the rules allowed to add to an app on their own (grants not ended)."""
        from .grants import standing
        return [T.receipt_standing(*row) for row in sorted(standing(self.store, h))]

    # ---------- what is still waiting ----------
    def _waiting_lines(self, person, now):
        h, tz = person["handle"], person["timezone"]
        out = []
        hold = self.store.get_state(f"sendhold:{h}")
        held_id = None
        if hold and hold.get("draft_id"):
            row = self.store.draft(hold["draft_id"])
            if row and row["status"] in ("held", "sending"):
                held_id = row["id"]
                due = _t(hold.get("due_at"))
                out.append(T.receipt_held(_what(row), who_of(row), self._receipt_clock(due, tz) if due else None))
        d = self.open_draft(h, now) if hasattr(self, "open_draft") else None
        if d and d["id"] != held_id:
            out.append(T.receipt_open_draft(_what(d), who_of(d)))
        ask = self.store.get_state(f"placeask:{h}")
        if ask and ask.get("plans") and now - datetime.fromisoformat(ask["at"]) <= timedelta(minutes=30):
            out.append(T.RECEIPT_PREVIEW_WAITING)
        return out

    @staticmethod
    def _receipt_clock(dt, tz):
        return dt.astimezone(ZoneInfo(tz)).strftime("%-I:%M%p").lower().replace(":00", "")

    # ---------- "did you send the email to Maria" ----------
    def _did_send(self, person, who, now):
        h, tz = person["handle"], person["timezone"]
        w = " ".join(who.lower().split())
        w = re.sub(r"^(?:my|the|our)\s+", "", w)
        rows = [d for d in reversed(self.store.drafts_of(h)) if d["status"] != "cancelled"]

        def hit(d):
            p = _parts(d)
            names = [d.get("to_name"), p.get("to_word"), d.get("to_addr"), d.get("to_domain")]
            names += [(d.get("to_addr") or "").split("@")[0]]
            return any(n and (w == n.lower() or (len(w) >= 3 and w in n.lower().split())) for n in names)
        d = next((x for x in rows if hit(x)), None)
        if d is None:
            return T.receipt_no_draft(who.strip())
        at = _t(max(d.get("done_at") or "", d.get("shown_at") or "", d.get("created_at") or ""))
        st, name, what = d["status"], who_of(d), _what(d)
        if st == "sent":
            sender = self._mailbox_sender(h) if hasattr(self, "_mailbox_sender") else None
            return T.did_sent(what, name, sender, when_words(_t(d["done_at"]) or at, now, tz))
        if st == "person_sent":
            return T.did_person_sent(what, name, day_words(at, now, tz))
        if st in ("held", "sending"):
            return T.did_held(what, name)
        if st == "unknown":
            return "I " + T.receipt_unknown(what, name) + "."
        if st == "failed":   # (round 9 checks) never "you haven't said send": they did, and it didn't go
            return T.did_failed(what, name)
        if d.get("version") and st in ("link_shown", "expired"):
            return T.did_prepared(what, name, d.get("route") == "mailbox")
        return T.did_not_yet(what, name)
