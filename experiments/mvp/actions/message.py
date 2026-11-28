"""PROTOTYPE ONLY - message.send: the reply in the thread (the existing send, executor.ExecutorMixin.send).

It runs last, so the reply can say in one line per action what the others did. A send error is raised to the caller
(the scheduler records it as it always has); the other actions are not repeated on a retry (outputs.py).
"""
from .base import Outcome


def run(ctx, params):
    ref = ctx.bot.send(ctx.handle, ctx.chat, ctx.run_id)
    return Outcome("done", ref=ref)
