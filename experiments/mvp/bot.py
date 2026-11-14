"""PROTOTYPE ONLY - run the MVP bot.

    python -m mvp.bot --channel web          # a chat page on this computer: test without a phone, move the clock
    python -m mvp.bot --channel console      # type messages as a test person in the terminal
    python -m mvp.bot --channel mac          # iMessage through this Mac's Messages app (founders, build days)
    python -m mvp.bot --channel mac --self-chat +15551234567   # the same, tested alone: text your own number
    python -m mvp.bot --channel sendblue     # Sendblue webhook on 127.0.0.1:8787, behind a tunnel (testers)

Run from experiments/. People come from MVP_HOME/people.json: {"<handle>": {"name", "library", "timezone"}}.
Keys only from the environment. Stop with Ctrl+C.
"""
import argparse
import os
import sys
import threading

from . import config
from .core import Bot
from .runtime import Runtime, report
from .store import Store


def make_channel(name, store, port, host="127.0.0.1", self_chat=None):
    if name == "console":
        from .channels.console import ConsoleChannel
        return ConsoleChannel()
    if name == "web":
        from .channels.web import WebChannel
        return WebChannel(port=port or 8765, host=host)
    if name == "mac":
        from .channels.imessage_mac import MacMessagesChannel
        return MacMessagesChannel(store, self_handle=self_chat)
    if name == "sendblue":
        from .channels.sendblue import SendblueChannel
        return SendblueChannel(port=port or 8787)
    raise SystemExit(f"unknown channel {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="web", choices=["web", "console", "mac", "sendblue"])
    ap.add_argument("--port", type=int, default=None, help="web: 8765 by default; sendblue: 8787")
    ap.add_argument("--host", default="127.0.0.1", help="web only: the address the test page listens on")
    ap.add_argument("--self-chat", default=None, metavar="HANDLE",
                    help="mac only: your own number or Apple Account email; text yourself and the bot answers there")
    ap.add_argument("--as", dest="as_handle", default=None, help="console only: the test person's handle")
    a = ap.parse_args()
    # The test page has its own store: moving its clock must never touch rules that real testers have.
    store = Store(os.path.join(config.HOME, "webtest.sqlite") if a.channel == "web" else config.DB)
    channel = make_channel(a.channel, store, a.port, a.host, a.self_chat)
    bot = Bot(channel, store=store, clock=getattr(channel, "clock", None))
    if hasattr(channel, "attach"):
        channel.attach(bot)
    n = bot.load_people()
    print(f"MVP bot: {n} people, channel {a.channel}, store {store.path}", file=sys.stderr)
    if a.channel == "web":
        print(f"Open http://{a.host}:{channel.port} in a browser on this computer.", file=sys.stderr)
    libs = [r["library"] for r in store.q("SELECT DISTINCT library FROM people")][:bot.pool.max_resident]

    def _load():  # read each library and start its search engine now, so the first reply is not a minute late
        for lib in libs:
            try:
                bot.view(lib)
                bot.pool.get(lib)
            except Exception as e:  # noqa: BLE001
                report(e)
                channel.problem = "A library did not load. Look at the terminal that runs the bot."
        channel.ready = True
        print("A library did not load." if getattr(channel, "problem", None) else "Libraries loaded.", file=sys.stderr)
    threading.Thread(target=_load, daemon=True).start()
    if a.channel == "console":
        rt = Runtime(bot, channel, workers=0)
        rt.recover()
        handle = a.as_handle or next(iter(p["handle"] for p in store.q("SELECT handle FROM people")), None)
        if not handle:
            raise SystemExit("no people in people.json")
        print(f"Talking as {handle}. Type a message; empty line to run due rules; Ctrl+D to quit.", file=sys.stderr)
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line:
                channel.push(handle, line)
            rt.step()
        rt.stop()
        return
    Runtime(bot, channel).run_forever()


if __name__ == "__main__":
    main()
