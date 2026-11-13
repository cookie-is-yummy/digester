"""PROTOTYPE ONLY - the run loop around the bot: who handles what, in which order, and what is written down.

- Every message received is first written to the store's inbound journal (channel reference, person, time; the text is
  kept only until the message has been handled). A reference seen before is dropped, so a webhook retry or a restart
  never answers a message twice; a message that was received but not handled when the bot stopped is handled at the
  next start if it is under 10 minutes old.
- Messages are handled by a small pool of workers, one person at a time per person: a slow search for one person does
  not hold up the others, and one person's messages stay in order.
- Texts a person sends in quick succession ("send me pasta recipes" then "every friday") are joined into one request.
- The scheduler runs on its own thread every 30 seconds, and takes the same per-person lock as message handling.
- Errors are reported as an exception type and a file and line, never with message text or a handle.
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .channels.base import Inbound
from .store import now_iso

TICK_SECONDS = 30
REPLAY_MAX_AGE = timedelta(minutes=10)
SORRY = "Something went wrong on my side. Please try again in a bit."


def report(e):
    tb = e.__traceback__
    while tb and tb.tb_next:
        tb = tb.tb_next
    where = f"{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno}" if tb else "?"
    print(f"error: {type(e).__name__} at {where}", file=sys.stderr)


class Runtime:
    def __init__(self, bot, channel, workers=4, join_seconds=None):
        self.bot, self.channel, self.store = bot, channel, bot.store
        self.join_seconds = channel.join_seconds if join_seconds is None else join_seconds
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="msg") if workers else None
        self.buffers = {}       # handle -> [(inbound id, Inbound)] waiting to be joined and handled
        self.last_arrival = {}  # handle -> real time of the newest buffered message
        self.arrived = {}       # handle -> real time the oldest buffered message arrived
        self.in_flight = set()  # handles with a batch being handled: their next batch waits, to keep order
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.tick_now = threading.Event()

    # ---------- start-up ----------
    def recover(self):
        """Runs once at start. Unfinished sends are never repeated; unfinished messages are handled if still fresh."""
        self.bot.recover()
        now = datetime.now(timezone.utc)
        replayed = dropped = 0
        for row in self.store.inbound_unfinished():
            if row["channel"] != self.channel.name:
                continue
            fresh = now - datetime.fromisoformat(row["received_at"]) <= REPLAY_MAX_AGE
            if fresh and (row["text"] or row["tapback"]):
                msg = Inbound(handle=row["handle"], text=row["text"] or "", tapback=row["tapback"],
                              tapback_ref=row["tapback_ref"], ref=row["ref"])
                self._buffer(row["id"], msg)
                replayed += 1
            else:
                self.store.inbound_done(row["id"], "dropped", error="not handled before a restart")
                dropped += 1
        if replayed or dropped:
            print(f"After the restart: {replayed} unanswered messages handled now, {dropped} too old and dropped.",
                  file=sys.stderr)

    # ---------- messages in ----------
    def _buffer(self, inbound_id, msg):
        with self.lock:
            self.buffers.setdefault(msg.handle, []).append((inbound_id, msg))
            self.last_arrival[msg.handle] = time.time()
            self.arrived.setdefault(msg.handle, datetime.now(timezone.utc))  # when this batch began to arrive

    def poll(self):
        """Take new messages from the channel into the journal and the buffers."""
        for msg in self.channel.receive():
            inbound_id = self.store.inbound_add(self.channel.name, msg, at=self.bot.clock())
            if inbound_id is None:  # this reference was already received: not answered again, but written down
                self.store.inbound_duplicate(self.channel.name, msg, at=self.bot.clock())
                self.channel.done(msg)
                continue
            self._buffer(inbound_id, msg)
        if self.channel.wants_tick():
            self.tick_now.set()

    def dispatch(self, wait=True):
        """Hand each person's buffered messages to a worker once they have been quiet for join_seconds."""
        now = time.time()
        ready = []
        with self.lock:
            for handle, batch in list(self.buffers.items()):
                if not batch or handle in self.in_flight:
                    continue
                if wait and now - self.last_arrival.get(handle, 0) < self.join_seconds:
                    continue
                self.in_flight.add(handle)
                ready.append((handle, self.buffers.pop(handle), self.arrived.pop(handle, None)))
        for handle, batch, received in ready:
            if self.pool:
                self.pool.submit(self._handle, handle, batch, received)
            else:
                self._handle(handle, batch, received)

    def _handle(self, handle, batch, received=None):
        t0 = time.time()
        trace = self.bot._tl.trace = {}
        status, error = "done", None
        try:
            for unit in _join(batch):
                self.bot.on_message(handle, unit.text, tapback=unit.tapback, tapback_ref=unit.tapback_ref,
                                    received=received)
        except Exception as e:  # noqa: BLE001 - type and place only: messages can hold numbers and text
            report(e)
            status, error = "error", type(e).__name__
            if any(m.text for _, m in batch):  # never leave a person without an answer
                try:
                    self.bot.send(handle, SORRY)
                except Exception as e2:  # noqa: BLE001
                    report(e2)
        finally:
            self.bot._tl.trace = None
            seconds = round(time.time() - t0, 2)
            for inbound_id, msg in batch:
                self.store.inbound_done(inbound_id, status, intent=trace.get("intent"), run_id=trace.get("run_id"),
                                        reply_ref=trace.get("reply_ref"), error=error, seconds=seconds)
                self.channel.done(msg)
            with self.lock:
                self.in_flight.discard(handle)

    # ---------- the scheduler ----------
    def tick(self):
        try:
            soon = self.bot.clock() + timedelta(minutes=3)
            for r in self.store.q("SELECT DISTINCT p.library FROM rules r JOIN people p ON p.handle=r.handle "
                                  "WHERE r.status='active' AND r.next_run_at<=?", (now_iso(soon),)):
                self.bot.pool.warm(r["library"])  # load the engine before the send is due
            return self.bot.tick()
        except Exception as e:  # noqa: BLE001
            report(e)
            return 0

    def _scheduler(self):
        while not self.stop_flag.is_set():
            self.tick_now.wait(TICK_SECONDS)
            self.tick_now.clear()
            if not self.stop_flag.is_set():
                self.tick()

    # ---------- running ----------
    def step(self):
        """One synchronous turn, for tests and the terminal: everything waiting is handled, then due rules run."""
        self.poll()
        self.dispatch(wait=False)
        self.tick_now.clear()
        return self.tick()

    def run_forever(self):
        self.recover()
        threading.Thread(target=self._scheduler, daemon=True, name="scheduler").start()
        try:
            while not self.stop_flag.is_set():
                try:
                    self.poll()
                    self.dispatch()
                except Exception as e:  # noqa: BLE001
                    report(e)
                time.sleep(self.channel.poll_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self.stop_flag.set()
        self.tick_now.set()
        if self.pool:
            self.pool.shutdown(wait=True, cancel_futures=False)
        self.channel.close()
        self.bot.pool.stop_all()


def _join(batch):
    """Consecutive texts become one message (joined with a line break); a tapback stays its own unit, in order."""
    units, texts = [], []
    for _, m in batch:
        if m.tapback:
            if texts:
                units.append(Inbound(handle=m.handle, text="\n".join(texts)))
                texts = []
            units.append(m)
        elif m.text:
            texts.append(m.text)
    if texts:
        units.append(Inbound(handle=batch[0][1].handle, text="\n".join(texts)))
    return units
