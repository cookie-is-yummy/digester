"""A fake Gemini for asking a video (round 11, slice Q; videoask.py). No network, no money.

    from mvp.tests.fakes.fake_gemini import FakeGemini
    fake = FakeGemini({"answered": True, "points": [{"at": "01:05", "says": "Set the shutter to 1/50."}]})
    fake.install(monkeypatch)
    ... fake.requests -> each GenerateContentRequest body sent; fake.models; fake.people

`answer` is the parsed form (a dict), None (the model gave nothing usable: a refusal or a blocked candidate), a
callable(request) returning either, or an exception instance to raise (an HTTP 400 for a private video, a 429, a
time-out). Each call reports `cost_per_call`, as the real call does. GEMINI_API_KEY is set to a dummy value for the test
(the real key is never read: nothing here reaches the network).
"""


class FakeGemini:
    def __init__(self, answer=None, cost_per_call=0.004):
        self.answer = answer
        self.cost_per_call = cost_per_call
        self.requests, self.models, self.people, self.est_tokens = [], [], [], []

    def call(self, mdl, request, est_tokens, person):
        self.requests.append(request)
        self.models.append(mdl)
        self.people.append(person)
        self.est_tokens.append(est_tokens)
        a = self.answer
        if isinstance(a, BaseException):
            raise a
        out = a(request) if callable(a) else a
        return (dict(out) if isinstance(out, dict) else out), self.cost_per_call, ""

    def install(self, monkeypatch):
        from mvp import videoask
        monkeypatch.setattr(videoask, "call_model", self.call)
        monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-key")
        return self

    # what reached Google, read back from a request body
    @staticmethod
    def sent_url(request):
        part = request["contents"][0]["parts"][0]
        return part["file_data"]["file_uri"]

    @staticmethod
    def sent_text(request):
        return " ".join(p.get("text", "") for p in request["contents"][0]["parts"][1:])
