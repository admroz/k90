import base64
import json
from unittest.mock import Mock

import pytest
import requests

from telegram_adapter import accept_update, deliver_pending
from tools.images import MAX_IMAGE_BYTES
from webapp import TelegramMessage


JPEG = b"\xff\xd8\xffsynthetic-jpeg"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
WEBP = b"RIFF\x0c\x00\x00\x00WEBPsynthetic-webp"


def update():
    return {
        "update_id": 42,
        "message": {
            "from": {"id": 123},
            "chat": {"id": 123, "type": "private"},
            "text": "hello",
        },
    }


def test_update_has_stable_id_and_unauthorized_sender_is_ignored(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    backend, api = Mock(), Mock()
    accept_update(api, backend, update())
    assert backend.call.call_args.kwargs["json"] == {
        "request_id": "telegram:42",
        "chat_id": 123,
        "text": "hello",
    }
    backend.reset_mock()
    message = update()
    message["message"]["from"]["id"] = 456
    accept_update(api, backend, message)
    backend.call.assert_not_called()
    message["message"]["from"]["id"] = 123
    message["message"]["chat"]["type"] = "group"
    accept_update(api, backend, message)
    backend.call.assert_not_called()


def test_delivery_failure_keeps_response_pending_and_never_calls_agent():
    backend, api = Mock(), Mock()
    item = {
        "request_id": "telegram:42",
        "chat_id": 123,
        "response": "saved answer",
        "delivery_index": 0,
    }
    backend.call.return_value = [item]
    api.send_text.side_effect = requests.Timeout()
    with pytest.raises(requests.Timeout):
        deliver_pending(api, backend)
    assert backend.call.call_count == 1
    assert backend.call.call_args.args == ("GET", "/internal/deliveries")
    api.send_text.side_effect = None
    deliver_pending(api, backend)
    assert backend.call.call_args.args == ("POST", "/internal/deliveries/telegram:42")
    assert backend.call.call_args.kwargs["json"] == {"index": 1, "done": True}


def test_long_delivery_resumes_after_acknowledged_chunks():
    backend, api = Mock(), Mock()
    response = "a" * 4096 + "b" * 100
    backend.call.return_value = [
        {
            "request_id": "telegram:42",
            "chat_id": 123,
            "response": response,
            "delivery_index": 1,
        }
    ]
    deliver_pending(api, backend)
    api.send_text.assert_called_once_with(123, "b" * 100)
    assert backend.call.call_args.kwargs["json"] == {"index": 2, "done": True}


def image_update(kind="photo", caption="Zjadłem ten posiłek"):
    result = update()
    message = result["message"]
    message.pop("text")
    message["caption"] = caption
    if kind == "photo":
        message["photo"] = [{"file_id": "small"}, {"file_id": "large"}]
    else:
        message["document"] = {"file_id": "large", "mime_type": "image/jpeg", "file_name": "meal.jpg"}
    return result


@pytest.mark.parametrize("raw, mime", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")])
@pytest.mark.parametrize("kind", ["photo", "document"])
@pytest.mark.parametrize("download_mime", ["application/octet-stream", "image/jpeg"])
def test_image_content_survives_generic_or_wrong_download_mime(monkeypatch, raw, mime, kind, download_mime):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    api, backend = Mock(), Mock()
    api.download_file.return_value = raw, download_mime

    accept_update(api, backend, image_update(kind))

    api.download_file.assert_called_once_with("large")
    body = backend.call.call_args.kwargs["json"]
    assert body["text"] == "Zjadłem ten posiłek"
    assert body["image"] == f"data:{mime};base64," + base64.b64encode(raw).decode()
    # The adapter and backend must agree, otherwise polling would retry forever.
    content = TelegramMessage(**body).content()
    assert content[0]["text"] == body["text"]
    assert content[1]["image_url"]["url"] == body["image"]


@pytest.mark.parametrize("filename, raw, mime", [
    ("meal.JpEg", JPEG, None), ("meal.PNG", PNG, "application/octet-stream"),
    ("meal.webp", WEBP, ""),
])
def test_image_document_without_image_mime_is_recognized_by_filename(monkeypatch, filename, raw, mime):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    message = image_update("document", caption="")
    document = message["message"]["document"]
    document["file_name"] = filename
    if mime is None:
        document.pop("mime_type")
    else:
        document["mime_type"] = mime
    api, backend = Mock(), Mock()
    api.download_file.return_value = raw, "application/octet-stream"

    accept_update(api, backend, message)

    body = backend.call.call_args.kwargs["json"]
    assert TelegramMessage(**body).content()[1]["type"] == "image_url"
    assert base64.b64decode(body["image"].partition(",")[2]) == raw


@pytest.mark.parametrize("raw", [b"", b"GIF89a", b"RIFF1234WAVE", b"not an image"])
def test_invalid_bytes_are_not_forwarded_as_images_even_when_declared_jpeg(monkeypatch, raw):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    api, backend = Mock(), Mock()
    api.download_file.return_value = raw, "image/jpeg"

    accept_update(api, backend, image_update())

    body = backend.call.call_args.kwargs["json"]
    assert "image" not in body
    assert "JPG, PNG lub WebP" in body["text"]
    assert body["text"].endswith("Zjadłem ten posiłek")
    assert TelegramMessage(**body).content() == body["text"]


@pytest.mark.parametrize("extra, accepted", [(0, True), (1, False)])
def test_telegram_image_size_limit_matches_backend(monkeypatch, extra, accepted):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    api, backend = Mock(), Mock()
    raw = JPEG + b"x" * (MAX_IMAGE_BYTES + extra - len(JPEG))
    api.download_file.return_value = raw, "application/octet-stream"

    accept_update(api, backend, image_update())

    body = backend.call.call_args.kwargs["json"]
    assert ("image" in body) is accepted
    TelegramMessage(**body)


def test_download_failure_does_not_enqueue_a_message_without_its_image(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    api, backend = Mock(), Mock()
    api.download_file.side_effect = requests.Timeout()

    with pytest.raises(requests.Timeout):
        accept_update(api, backend, image_update())

    backend.call.assert_not_called()


def test_photo_download_with_octet_stream_reaches_agent_once(monkeypatch, temp_db):
    """Exercise actual download, HTTP validation, durable queue and agent input."""
    from fastapi.testclient import TestClient

    import agent
    from server import TelegramAPI
    from tools.db import get_conn
    from web_runtime import ConversationWorker
    from webapp import create_app

    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setenv("CONVERSATION_USER_ID", "owner")
    monkeypatch.setenv("WEB_PASSWORD", "synthetic-test-password")
    monkeypatch.setenv("K90_INTERNAL_TOKEN", "test-only-internal-token")
    monkeypatch.setenv("K90_PREVIEW", "false")
    monkeypatch.setenv("K90_SYNC_ENABLED", "false")
    captured = []

    def fake_agent(content, user_id):
        captured.append((content, user_id))
        agent.save_history(user_id, content, "Widzę zdjęcie.")
        return "Widzę zdjęcie.", False

    monkeypatch.setattr(agent, "run_agent", fake_agent)
    api = TelegramAPI("fake-test-token")
    monkeypatch.setattr(api, "call", Mock(return_value={"file_path": "photos/meal.jpg"}))
    download = Mock(content=PNG, headers={"Content-Type": "application/octet-stream"})
    monkeypatch.setattr(api._session, "get", Mock(return_value=download))

    with TestClient(create_app(start_worker=False)) as client:
        class Backend:
            def call(self, method, path, **kwargs):
                response = client.request(method, path, headers={"Authorization": "Bearer test-only-internal-token"}, **kwargs)
                response.raise_for_status()
                return response.json()

        backend = Backend()
        accept_update(api, backend, image_update())
        accept_update(api, backend, image_update())
        worker = ConversationWorker()
        assert worker.run_once()
        assert not worker.run_once()

    assert len(captured) == 1
    content, user_id = captured[0]
    assert user_id == "owner"
    assert content[0] == {"type": "text", "text": "Zjadłem ten posiłek"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert base64.b64decode(content[1]["image_url"]["url"].partition(",")[2]) == PNG
    with get_conn() as conn:
        job = conn.execute("SELECT * FROM chat_jobs").fetchone()
        assert (job["state"], job["chat_id"], job["channel"]) == ("done", 123, "telegram")
        assert json.loads(job["payload"])[1] == content[1]
