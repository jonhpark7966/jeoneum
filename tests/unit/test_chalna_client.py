"""chalna client lifecycle — health check + conditional auto-start (mocked httpx)."""
from __future__ import annotations

import httpx
import pytest

from jeoneum import chalna_client
from jeoneum.chalna_client import ChalnaClient


class _Resp:
    def __init__(self, code):
        self.status_code = code


def test_is_up_true_only_on_200(monkeypatch):
    monkeypatch.setattr(chalna_client.httpx, "get", lambda *a, **k: _Resp(200))
    assert ChalnaClient(base_url="http://x").is_up() is True


def test_is_up_false_on_404(monkeypatch):
    # regression: `< 500` wrongly treated 404 as healthy
    monkeypatch.setattr(chalna_client.httpx, "get", lambda *a, **k: _Resp(404))
    assert ChalnaClient(base_url="http://x").is_up() is False


def test_is_up_false_on_connection_error(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(chalna_client.httpx, "get", boom)
    assert ChalnaClient(base_url="http://x").is_up() is False


def test_ensure_up_noop_when_already_up(monkeypatch):
    monkeypatch.setattr(ChalnaClient, "is_up", lambda self: True)
    called = []
    monkeypatch.setattr(chalna_client.subprocess, "run", lambda *a, **k: called.append(a))
    ChalnaClient().ensure_up()
    assert called == []                              # did NOT try to start chalna


def test_ensure_up_raises_when_down_and_autostart_disabled(monkeypatch):
    monkeypatch.setattr(ChalnaClient, "is_up", lambda self: False)
    with pytest.raises(RuntimeError):
        ChalnaClient(auto_start=False).ensure_up()
