"""PROTOTYPE ONLY - run the MVP bot.

    python -m mvp.bot --channel console      # type messages as a test person (development)
    python -m mvp.bot --channel mac          # iMessage through this Mac's Messages app (founders, build days)
    python -m mvp.bot --channel sendblue     # Sendblue webhook on 127.0.0.1:8787, behind a tunnel (testers)

Run from experiments/. People come from MVP_HOME/people.json: {"<handle>": {"name", "library", "timezone"}}.
Keys only from the environment. Stop with Ctrl+C.
"""
import argparse
import os
import sys
import time
from datetime import timedelta

from . import config
from .core import Bot
from .store import Store, now_iso


def _report(e):
    tb = e.__traceback__
    while tb and tb.tb_next:
        tb = tb.tb_next
    where = f"{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno}" if tb else "?"
    print(f"error: {type(e).__name__} at {where}", file=sys.stderr)


def make_channel(name, store, port):
    if name == "console":
        from .channels.console import ConsoleChannel
        return ConsoleChannel()
    if name == "mac":
        from .channels.imessage_mac import MacMessagesChannel
        return MacMessagesChannel(store)
    if name == "sendblue":
        from .channels.sendblue import SendblueChannel
        return SendblueChannel(port=port)
    raise SystemExit(f"unknown channel {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="console", choices=["console", "mac", "sendblue"])
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--as", dest="as_handle", default=None, help="console only: the test person's handle")
    a = ap.parse_args()
    store = Store(config.DB)
    channel = make_channel(a.channel, store, a.port)
    bot = Bot(channel, store=store)
    n = bot.load_people()
    print(f"MVP bot: {n} people, channel {a.channel}, store {config.DB}", file=sys.stderr)
    for r in store.q("SELECT DISTINCT library FROM people")[:bot.pool.max_resident]:
        bot.pool.warm(r["library"])  # load search engines now, so the first reply is not a minute late
    if a.channel == "console":
        handle = a.as_handle or next(iter(p["handle"] for p in store.q("SELECT handle FROM people")), None)
        if not handle:
            raise SystemExit("no people in people.json")
        print(f"Talking as {handle}. Type a message; empty line to run due rules; Ctrl+D to quit.", file=sys.stderr)
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line:
                bot.on_message(handle, line)
            bot.tick()
        return
    last_tick = 0.0
    try:
        while True:
            for msg in channel.receive():
                try:
                    bot.on_message(msg.handle, msg.text, tapback=msg.tapback, tapback_ref=msg.tapback_ref)
                except Exception as e:  # noqa: BLE001 - type and place only: messages can hold numbers and text
                    _report(e)
            if time.time() - last_tick > 30:
                last_tick = time.time()
                try:
                    soon = bot.clock() + timedelta(minutes=3)
                    for r in store.q("SELECT DISTINCT p.library FROM rules r JOIN people p ON p.handle=r.handle "
                                     "WHERE r.status='active' AND r.next_run_at<=?", (now_iso(soon),)):
                        bot.pool.warm(r["library"])
                    bot.tick()
                except Exception as e:  # noqa: BLE001
                    _report(e)
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        channel.close()
        bot.pool.stop_all()


if __name__ == "__main__":
    main()
