"""A fake model for tests and the self-test's --dry mode (round 10, slice K). No network, no money.

    from mvp.tests.fakes.fake_llm import FakeLLM
    fake = FakeLLM({"mvp_interpret": {"intent": "chat", "reply": "OK."}})   # purpose -> dict, or callable(user, system)
    fake.install(monkeypatch)            # in a test; or `undo = fake.install()` in a harness, then undo()
    ... fake.calls -> [(purpose, prompt_version)]; fake.cost -> what the fake said it spent

A call for a purpose with no answer raises FakeLLMMissing, so a test that promises 0 model calls fails on the first
one (`FakeLLM()` with no answers is that promise). `strict=False` answers {} instead. Each answer reports
`cost_per_call` (default $0.001), as the real wrapper does, so cost logging paths run.
"""


class FakeLLMMissing(AssertionError):
    """A model call the test did not expect."""


class FakeLLM:
    def __init__(self, answers=None, strict=True, cost_per_call=0.001):
        self.answers = dict(answers or {})
        self.strict = strict
        self.cost_per_call = cost_per_call
        self.calls = []        # (purpose, prompt_version)
        self.users = []        # the user text of each call (tests check what reached a prompt)
        self.cost = 0.0

    def answer(self, purpose, out):
        self.answers[purpose] = out
        return self

    def chat_json(self, system, user, purpose, prompt_version, person=None, max_tokens=1200, temperature=None,
                  seed=None, model=None, reasoning_effort=None):
        self.calls.append((purpose, prompt_version))
        self.users.append(user)
        if purpose not in self.answers:
            if self.strict:
                raise FakeLLMMissing(f"unexpected model call: {purpose}")
            return {}, 0.0
        a = self.answers[purpose]
        out = a(user, system) if callable(a) else a
        self.cost += self.cost_per_call
        return (dict(out) if isinstance(out, dict) else out), self.cost_per_call

    def install(self, monkeypatch=None):
        """Replaces mvp.llm.chat_json (every module reaches the model through it) and makes the spend readers see 0.
        With pytest's monkeypatch the test undoes it; without, the returned function undoes it."""
        from mvp import llm
        swaps = {"chat_json": self.chat_json, "spent_today": lambda h, lib: 0.0, "spent_total": lambda libs: 0.0}
        if monkeypatch is not None:
            for k, v in swaps.items():
                monkeypatch.setattr(llm, k, v)
            return lambda: None
        old = {k: getattr(llm, k) for k in swaps}
        for k, v in swaps.items():
            setattr(llm, k, v)

        def undo():
            for k, v in old.items():
                setattr(llm, k, v)
        return undo
