from unittest.mock import Mock

import pytest
import requests

from telegram_adapter import accept_update, deliver_pending


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
