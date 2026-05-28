import pytest

from app.main import _BodySizeLimitMiddleware


async def _read_body_app(scope, receive, send):
    assert scope["type"] == "http"
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _run_app(app, messages, headers=None):
    sent = []
    pending = list(messages)

    async def receive():
        return pending.pop(0)

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/ingest",
            "headers": headers or [],
        },
        receive,
        send,
    )
    return sent


@pytest.mark.asyncio
async def test_body_size_limit_rejects_content_length_before_reading_body():
    app = _BodySizeLimitMiddleware(_read_body_app, max_body_bytes=4)
    sent = await _run_app(
        app,
        [{"type": "http.request", "body": b"abcde", "more_body": False}],
        headers=[(b"content-length", b"5")],
    )

    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_body_size_limit_rejects_stream_without_content_length():
    app = _BodySizeLimitMiddleware(_read_body_app, max_body_bytes=4)
    sent = await _run_app(
        app,
        [
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"cde", "more_body": False},
        ],
    )

    assert sent[0]["status"] == 413
