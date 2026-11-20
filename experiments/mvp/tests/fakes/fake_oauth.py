"""A fake MCP server with its own OAuth 2.1 authorization server, in process (round 10, slice K; port of the design's
prototype). It approves every sign-in at once (test only). Made-up data; no port: tests reach it through an ASGI
client (starlette's TestClient), never a socket.

    from mvp.tests.fakes.fake_oauth import fake_oauth_app
    srv = fake_oauth_app()                       # srv.base = "https://fake-auth.example", srv.provider, srv.asgi
    from starlette.testclient import TestClient
    with TestClient(srv.asgi, base_url=srv.base) as http:
        http.get("/.well-known/oauth-protected-resource/mcp")     # PRM (RFC 9728)
        http.get("/.well-known/oauth-authorization-server")       # AS metadata (RFC 8414)
        http.post("/register", json={...})                        # DCR (RFC 7591)
        http.get("/authorize", params={... PKCE S256 ...}, follow_redirects=False)   # 302 to redirect_uri?code=&state=
        http.post("/token", data={"grant_type": "authorization_code", ...})
        http.post("/token", data={"grant_type": "refresh_token", ...})   # rotation: the old refresh token dies
        http.post("/revoke", data={"token": ..., "client_id": ...})   # a public client revokes with its id alone

Knobs on srv.provider: access_ttl (seconds, default 3, so tests see expiry), withdraw() (forget every token, as if the
person removed the app's access), approve (False: /authorize redirects with error=access_denied), issued (count).
A tool `create_task` and a tool `withdraw_consent` are served at /mcp for a round trip with a Bearer token.
"""
import secrets
import time
from types import SimpleNamespace

BASE = "https://fake-auth.example"


class Provider:
    """The SDK's OAuthAuthorizationServerProvider protocol, in memory."""

    def __init__(self, access_ttl=3):
        self.clients, self.codes, self.refresh, self.access = {}, {}, {}, {}
        self.access_ttl = access_ttl
        self.approve = True
        self.issued = 0

    async def get_client(self, client_id):
        return self.clients.get(client_id)

    async def register_client(self, info):
        self.clients[info.client_id] = info

    async def authorize(self, client, params):
        from mcp.server.auth.provider import AuthorizationCode, construct_redirect_uri
        if not self.approve:
            return construct_redirect_uri(str(params.redirect_uri), error="access_denied", state=params.state)
        code = secrets.token_urlsafe(16)
        self.codes[code] = AuthorizationCode(
            code=code, scopes=params.scopes or ["tasks"], expires_at=time.time() + 60, client_id=client.client_id,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly, resource=params.resource)
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client, code):
        return self.codes.get(code)

    def _issue(self, client_id, scopes, resource):
        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthToken
        at, rt = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
        self.issued += 1
        self.access[at] = AccessToken(token=at, client_id=client_id, scopes=scopes,
                                      expires_at=int(time.time()) + self.access_ttl, resource=resource)
        self.refresh[rt] = RefreshToken(token=rt, client_id=client_id, scopes=scopes, resource=resource)
        return OAuthToken(access_token=at, token_type="Bearer", expires_in=self.access_ttl, refresh_token=rt,
                          scope=" ".join(scopes))

    async def exchange_authorization_code(self, client, code):
        self.codes.pop(code.code, None)
        return self._issue(client.client_id, code.scopes, code.resource)

    async def load_refresh_token(self, client, token):
        return self.refresh.get(token)

    async def exchange_refresh_token(self, client, rt, scopes):
        self.refresh.pop(rt.token, None)   # rotation: the old refresh token dies (OAuth 2.1 public clients)
        return self._issue(client.client_id, scopes or rt.scopes, rt.resource)

    async def load_access_token(self, token):
        t = self.access.get(token)
        return t if t and (t.expires_at or 0) > time.time() else None

    async def revoke_token(self, token):
        self.access.pop(getattr(token, "token", ""), None)
        self.refresh.pop(getattr(token, "token", ""), None)

    def withdraw(self):
        self.access.clear()
        self.refresh.clear()


def fake_oauth_app(access_ttl=3, base=BASE):
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from mcp.server.mcpserver import MCPServer
    p = Provider(access_ttl)
    app = MCPServer("fake-oauth-tasks", auth_server_provider=p, auth=AuthSettings(
        issuer_url=base, resource_server_url=f"{base}/mcp", required_scopes=["tasks"],
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["tasks"],
                                                              default_scopes=["tasks"]),
        revocation_options=RevocationOptions(enabled=True), validate_token_resource=True))
    made = {}

    @app.tool()
    def create_task(task: dict) -> dict:
        """Create a task."""
        tid = secrets.token_hex(6)
        made[tid] = task
        return {"id": tid, "projectId": "inbox"}

    @app.tool()
    def withdraw_consent() -> str:
        """Test hook: forget every token, as if the person removed the app's access."""
        p.withdraw()
        return "all tokens forgotten"
    return SimpleNamespace(app=app, provider=p, base=base, asgi=_public_revoke(app.streamable_http_app(), p),
                           made=made)


def _public_revoke(asgi, provider):
    """RFC 7009 lets a public client (token_endpoint_auth_method "none", PKCE) revoke with its client_id alone; the
    SDK's /revoke asks every client for a secret. This wrapper answers /revoke for public clients itself (200, the
    token forgotten, as the RFC says even for an unknown token) and passes everything else to the SDK's app."""
    import urllib.parse

    async def app(scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/revoke" or scope.get("method") != "POST":
            return await asgi(scope, receive, send)
        chunks, more = [], True
        while more:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)
        form = dict(urllib.parse.parse_qsl(body.decode("utf-8", "replace")))
        client = provider.clients.get(form.get("client_id"))
        if client is not None and getattr(client, "token_endpoint_auth_method", None) == "none":
            await provider.revoke_token(SimpleNamespace(token=form.get("token") or ""))
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-length", b"0")]})
            return await send({"type": "http.response.body", "body": b""})
        sent = False

        async def again():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await asgi(scope, again, send)
    return app
