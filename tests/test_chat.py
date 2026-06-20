from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer gw_sk_demo123"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_completion_mock():
    r = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hello there"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"].startswith("[mock]")
    assert r.headers["x-cache"] == "MISS"
    assert r.headers["x-provider"] == "mock"


def test_requires_auth():
    r = client.post(
        "/v1/chat/completions",
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


def test_rejects_bad_key():
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer nope"},
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


def test_streaming_mock():
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "stream please"}],
            "stream": True,
        },
    ) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes())
    assert b"data:" in body
    assert b"[DONE]" in body
