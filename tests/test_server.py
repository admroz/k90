from __future__ import annotations

import server


class FakeAPI:
    def __init__(self, image: bytes = b"image"):
        self.sent = []
        self.image = image

    def send_text(self, chat_id: int, message: str) -> None:
        self.sent.append((chat_id, message))

    def download_file(self, file_id: str):
        assert file_id
        return self.image, "image/jpeg"


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {"ok": True, "result": []}


def private_message(text: str = "hello", *, user_id: int = 123) -> dict:
    return {
        "message_id": 1,
        "from": {"id": user_id},
        "chat": {"id": user_id, "type": "private"},
        "text": text,
    }


def test_help_bypasses_agent(monkeypatch):
    api = FakeAPI()
    monkeypatch.setattr(server, "TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setattr(
        server,
        "run_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("agent should not run")),
    )

    server.handle_telegram_message(api, private_message("/help"))

    assert len(api.sent) == 1
    assert "/help" in api.sent[0][1]


def test_text_message_reaches_agent_with_stable_user_id(monkeypatch):
    api = FakeAPI()
    calls = []
    monkeypatch.setattr(server, "TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setattr(server, "CONVERSATION_USER_ID", "owner")
    monkeypatch.setattr(server, "should_auto_sync_today", lambda: False)
    monkeypatch.setattr(server, "should_auto_sync_libre", lambda: False)
    monkeypatch.setattr(
        server,
        "run_agent",
        lambda message, user_id: (calls.append((message, user_id)) or ("Odpowiedź", False)),
    )

    server.handle_telegram_message(api, private_message("Jak się mam?"))

    assert calls == [("Jak się mam?", "owner")]
    assert api.sent == [(123, "Odpowiedź")]


def test_unknown_or_group_sender_is_rejected(monkeypatch):
    api = FakeAPI()
    monkeypatch.setattr(server, "TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setattr(
        server,
        "run_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("agent should not run")),
    )

    server.handle_telegram_message(api, private_message(user_id=456))
    group = private_message(user_id=123)
    group["chat"] = {"id": -1001, "type": "group"}
    server.handle_telegram_message(api, group)

    assert api.sent == []


def test_photo_is_downloaded_and_passed_as_multimodal_input(monkeypatch):
    api = FakeAPI(image=b"abc")
    captured = []
    monkeypatch.setattr(server, "TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setattr(server, "should_auto_sync_today", lambda: False)
    monkeypatch.setattr(server, "should_auto_sync_libre", lambda: False)
    monkeypatch.setattr(
        server,
        "run_agent",
        lambda message, user_id: (captured.append(message) or ("Widzę zdjęcie", False)),
    )
    message = private_message("")
    message.pop("text")
    message["photo"] = [{"file_id": "small"}, {"file_id": "large"}]

    server.handle_telegram_message(api, message)

    assert captured[0][-1]["type"] == "image_url"
    assert captured[0][-1]["image_url"]["url"] == "data:image/jpeg;base64,YWJj"
    assert api.sent == [(123, "Widzę zdjęcie")]


def test_long_response_is_split_within_telegram_limit():
    chunks = server.split_message(("word " * 1200).strip(), limit=100)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 100 for chunk in chunks)
    assert " ".join(chunks) == ("word " * 1200).strip()


def test_get_updates_keeps_telegram_and_http_timeouts_separate(monkeypatch):
    api = server.TelegramAPI("secret-token")
    calls = []
    monkeypatch.setattr(server, "TELEGRAM_POLL_TIMEOUT", 30)
    monkeypatch.setattr(
        api._session,
        "post",
        lambda url, json, timeout: (calls.append((url, json, timeout)) or FakeResponse()),
    )

    assert api.get_updates(offset=42) == []
    assert calls[0][1]["timeout"] == 30
    assert calls[0][1]["offset"] == 42
    assert calls[0][2] == 40
