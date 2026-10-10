"""Real MCP ASGI requests and signed OAuth JWTs, without public network."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest
from services.collaboration.exchange import BRANCH
from services.collaboration.server import JWTVerifier, Settings, SCOPE, create_server


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path, tmp_path / "state", "https://exchange.example.org/mcp",
                    "https://auth.example.org/", "https://auth.example.org/jwks", frozenset({"owner"}))


@pytest.fixture
def keys():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(settings, keys, **overrides):
    claims = dict(iss=settings.issuer, aud=settings.public_url, sub="owner", scope=SCOPE,
                  iat=int(time.time()) - 1, exp=int(time.time()) + 600)
    claims.update(overrides)
    return jwt.encode(claims, keys, algorithm="RS256", headers={"kid": "test"})


@pytest.mark.parametrize("change", [{}, {"aud": "https://other.example.org/mcp"}, {"iss": "wrong"},
    {"sub": "other"}, {"scope": "read"}, {"exp": 1}, {"scope": [SCOPE]}, {"iat": int(time.time()) + 6000}])
def test_oauth_claims(settings, keys, change, monkeypatch):
    verifier = JWTVerifier(settings)
    monkeypatch.setattr(verifier.keys, "get_signing_key_from_jwt", lambda _: SimpleNamespace(key=keys.public_key()))
    accepted = verifier.verify(token(settings, keys, **change))
    assert (accepted is not None) == (not change)


def test_invalid_signatures_and_missing_claims(settings, keys, monkeypatch):
    verifier = JWTVerifier(settings)
    monkeypatch.setattr(verifier.keys, "get_signing_key_from_jwt", lambda _: SimpleNamespace(key=keys.public_key()))
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert verifier.verify(token(settings, other)) is None
    assert verifier.verify(jwt.encode({"sub": "owner"}, keys, algorithm="RS256")) is None
    assert verifier.verify("malformed") is None


@pytest.mark.parametrize("change", [{"public_url": "http://example.org/mcp"}, {"subjects": frozenset()},
                                      {"issuer": "https://user:secret@example.org"},
                                      {"public_url": "https://example.org/other"}])
def test_invalid_configuration(settings, change):
    with pytest.raises(ValueError):
        replace(settings, **change)


class FakeExchange:
    def __init__(self):
        self.writes = []
        self.events = []
    def read_gpt_message(self):
        return {"message": "GPT demande", "commit": "abc"}
    def get_exchange_status(self):
        return {"ready": True, "commit": "abc"}
    def write_claude_message(self, message):
        self.writes.append(message)
        return {"published": True, "commit": "def"}
    def audit(self, event, **fields):
        self.events.append((event, fields))


def test_mcp_http_auth_discovery_and_exact_tools(settings, keys, monkeypatch):
    async def run():
        monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt", lambda self, _: SimpleNamespace(key=keys.public_key()))
        exchange = FakeExchange()
        server = create_server(settings, exchange)
        app = server.streamable_http_app()
        async with server.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://exchange.example.org") as client:
                headers = {"Accept": "application/json, text/event-stream"}
                request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
                denied = await client.post("/mcp", headers=headers, json=request)
                assert denied.status_code == 401
                assert "resource_metadata=" in denied.headers["www-authenticate"]
                for metadata_path in (
                    "/.well-known/oauth-protected-resource/mcp",
                    "/.well-known/oauth-protected-resource",
                ):
                    metadata = await client.get(metadata_path)
                    assert metadata.status_code == 200
                    assert metadata.json()["authorization_servers"] == [settings.issuer]
                    assert metadata.json()["resource"] == settings.public_url
                headers["Authorization"] = "Bearer " + token(settings, keys)
                response = await client.post("/mcp", headers=headers, json=request)
                assert response.status_code == 200, response.text
                assert response.json()["result"]["serverInfo"]["name"] == "Eidolon Collaboration"
                response = await client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                tools = response.json()["result"]["tools"]
                assert {x["name"] for x in tools} == {"read_gpt_message", "write_claude_message", "get_exchange_status"}
                for name, arguments in [("read_gpt_message", {}), ("get_exchange_status", {}), ("write_claude_message", {"message": "Claude réponse"})]:
                    response = await client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
                    assert not response.json()["result"].get("isError"), response.text
                assert exchange.writes == ["Claude réponse"]
                assert all(fields["subject"] == "owner" for _, fields in exchange.events)
                headers["Authorization"] = "Bearer " + token(settings, keys, sub="unauthorized")
                response = await client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "write_claude_message", "arguments": {"message": "attack"}}})
                assert response.status_code == 401
                assert exchange.writes == ["Claude réponse"]
    asyncio.run(run())

# Reuse a real bare-Git fixture for a client/server/commit/push round trip.
from tests.test_collaboration_exchange import setup


def test_official_mcp_client_over_loopback_with_real_git(settings, keys, setup, monkeypatch):
    import socket
    import threading
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    exchange, _, remote = setup
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt", lambda self, _: SimpleNamespace(key=keys.public_key()))
    server = create_server(settings, exchange)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    runner = uvicorn.Server(uvicorn.Config(server.streamable_http_app(), log_level="error"))
    thread = threading.Thread(target=runner.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not runner.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runner.started

        async def run():
            async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token(settings, keys), "Host": "exchange.example.org"}) as http:
                async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        listed = await client.list_tools()
                        assert len(listed.tools) == 3
                        read_result = await client.call_tool("read_gpt_message", {})
                        assert not read_result.isError
                        assert json.loads(read_result.content[0].text)["message"] == "GPT demande é\n"
                        result = await client.call_tool("write_claude_message", {"message": "Réponse via MCP réel 🙂"})
                        assert not result.isError
                        assert json.loads(result.content[0].text)["published"]
                        status = await client.call_tool("get_exchange_status", {})
                        assert json.loads(status.content[0].text)["ready"]
        asyncio.run(run())
        from tests.test_collaboration_exchange import git
        assert git(remote, "show", f"{BRANCH}:collaboration/CLAUDE-TO-GPT.md") == "Réponse via MCP réel 🙂"
    finally:
        runner.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()
