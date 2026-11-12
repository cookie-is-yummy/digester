"""PROTOTYPE ONLY - a channel for development and tests: messages come from a list or stdin, replies are printed
and kept in .outbox."""
import itertools
import queue

from .base import Channel, Inbound


class ConsoleChannel(Channel):
    name = "console"
    join_seconds = 0.0

    def __init__(self, printer=print):
        self.inbox = queue.Queue()
        self.outbox = []   # (ref, handle, text)
        self.printer = printer
        self._ids = itertools.count(1)

    def push(self, handle, text="", tapback=None, tapback_ref=None):
        self.inbox.put(Inbound(handle=handle, text=text, tapback=tapback, tapback_ref=tapback_ref))

    def receive(self):
        out = []
        while not self.inbox.empty():
            out.append(self.inbox.get())
        return out

    def send(self, handle, text):
        ref = f"console-{next(self._ids)}"
        self.outbox.append((ref, handle, text))
        if self.printer:
            self.printer(f"\n--- to {handle} [{ref}] ---\n{text}\n")
        return ref
