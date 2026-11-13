"""The CLI/TUI gateway dial must not ping a loopback owner (#154910).

The owner answers WebSocket pings on the same event loop that runs the agent turn,
so a busy turn can leave a ping unanswered for longer than the websockets default
20 s timeout. The client then closes a healthy loopback socket with 1011
"keepalive ping timeout" and reports the turn outcome as unknown. The dashboard
server already disables keepalive on loopback binds for the same reason; the
client side must match, while a non-loopback owner keeps the library default.
"""
import asyncio

import pytest

from hermes_cli import gateway_client
from hermes_cli.gateway_client import GatewayClientError, connect_gateway


def _dial_kwargs(monkeypatch, url):
    captured = {}

    def fake_connect(dial_url, **kwargs):
        captured["url"] = dial_url
        captured.update(kwargs)
        raise OSError("dial refused by test")

    monkeypatch.setattr("websockets.asyncio.client.connect", fake_connect)
    monkeypatch.setenv("HERMES_TUI_GATEWAY_URL", url)

    async def dial():
        async with connect_gateway():
            pass

    with pytest.raises(GatewayClientError):
        asyncio.run(dial())
    assert captured["url"] == url
    return captured


@pytest.mark.parametrize(
    "url",
    [
        "ws://127.0.0.1:8642/api/ws",
        "ws://localhost:8642/api/ws",
        "ws://[::1]:8642/api/ws",
        "ws://127.0.0.2:8642/api/ws",
    ],
)
def test_loopback_owner_is_dialed_without_keepalive_ping(monkeypatch, url):
    kwargs = _dial_kwargs(monkeypatch, url)
    assert kwargs["ping_interval"] is None
    assert kwargs["ping_timeout"] is None
    assert kwargs["proxy"] is None


@pytest.mark.parametrize(
    "url", ["wss://gateway.example.com/api/ws", "ws://192.168.1.20:8642/api/ws"]
)
def test_non_loopback_owner_keeps_the_default_keepalive(monkeypatch, url):
    kwargs = _dial_kwargs(monkeypatch, url)
    assert "ping_interval" not in kwargs
    assert "ping_timeout" not in kwargs


def test_is_loopback_ws_url_rejects_unparseable_hosts():
    assert gateway_client._is_loopback_ws_url("ws://127.0.0.1:1/api/ws") is True
    assert gateway_client._is_loopback_ws_url("ws://example.com/api/ws") is False
    assert gateway_client._is_loopback_ws_url("not a url") is False
