"""Fakes for the round 10 tests and the self-test harness (round 10, slice K; DESIGN.md section 17.K).

All in process: no port, no network, no real account, no real person's data. Each module says how a test turns it on.
  fake_llm       FakeLLM: answers mvp.llm.chat_json by purpose; an unexpected call fails the test
  fake_mcp       FakeMcpServer / FakeTransport: an MCP server with real tool schemas and every knob of design_mcp 3.7
  fake_oauth     fake_oauth_app(): the MCP SDK's OAuth 2.1 server (PRM, metadata, DCR, PKCE, rotation, revoke)
  fake_google    FakeGoogle: Google's device flow and a YouTube Data API subset, as an actions.web OPENER
  fake_merchant  install(context): "Streamly", a made-up merchant with 9 cancel flows, by Playwright routing
"""
