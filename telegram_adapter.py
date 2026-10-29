"""Optional Telegram transport. No agent execution or direct database access."""

from __future__ import annotations

import base64
import logging
import os
import time
from profiling import request_scope, span
from logging_setup import configure_logging, event

import requests

from server import TelegramAPI as LegacyTelegramAPI, _image_from_message, split_message
from tools.images import MAX_IMAGE_BYTES, image_mime_type


class ImageTooLarge(ValueError):
    pass


class TelegramAPI(LegacyTelegramAPI):
    def download_file(self, file_id):
        """Bound the actual response stream before accumulating image bytes."""
        info = self.call('getFile', file_id=file_id)
        if info.get('file_size', 0) > MAX_IMAGE_BYTES:
            raise ImageTooLarge()
        path = info.get('file_path')
        if not path:
            raise ValueError('missing_telegram_file')
        with self._session.get(f'{self._file_url}/{path}', timeout=30, stream=True) as response:
            response.raise_for_status()
            if int(response.headers.get('Content-Length', '0')) > MAX_IMAGE_BYTES:
                raise ImageTooLarge()
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=64*1024):
                if len(raw) + len(chunk) > MAX_IMAGE_BYTES:
                    raise ImageTooLarge()
                raw.extend(chunk)
            return bytes(raw), response.headers.get('Content-Type', '')



class BackendClient:
    def __init__(self):
        self.url = os.getenv("K90_BACKEND_URL", "http://127.0.0.1:8000")
        self.session = requests.Session()
        self.session.headers["Authorization"] = (
            "Bearer " + os.environ["K90_INTERNAL_TOKEN"]
        )

    def call(self, method, path, **kwargs):
        response = self.session.request(
            method, self.url + path, timeout=(3, 20), **kwargs
        )
        response.raise_for_status()
        return response.json()


def accept_update(api, backend, update):
    with request_scope('telegram', scope='submission'):
        try:
            return _accept_update(api, backend, update)
        except Exception as exc:
            event('telegram.ingress_failed', component='telegram_adapter', error=exc)
            raise


def _accept_update(api, backend, update):
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if chat.get("type") != "private" or str(sender.get("id")) != os.getenv(
        "TELEGRAM_ALLOWED_USER_ID"
    ):
        return
    if str(chat.get("id")) != str(sender.get("id")):
        return
    text = (message.get("text") or message.get("caption") or "").strip()
    image_info = _image_from_message(message)
    if not text and not image_info:
        return
    body = {
        "request_id": f"telegram:{update['update_id']}",
        "chat_id": chat["id"],
        "text": text,
    }
    album = message.get('media_group_id')
    if album:
        body = {'owner': sender['id'], 'chat_id': chat['id'], 'group_id': str(album),
                'update_id': update['update_id'], 'message_id': message['message_id'], 'text': text}
    if image_info:
        try:
            raw, _ = api.download_file(image_info[0])
        except ImageTooLarge:
            raw = b''
        mime = image_mime_type(raw)
        if mime is None or len(raw) > MAX_IMAGE_BYTES:
            if album:
                body['rejected'] = True
            else:
                body['text'] = 'Użytkownik przesłał obraz w nieobsługiwanym formacie lub większy niż 5 MB. Poproś o JPG, PNG lub WebP do 5 MB. ' + text
        else:
            body['image'] = f'data:{mime};base64,' + base64.b64encode(raw).decode()
    elif album:
        body['rejected'] = True
    accepted = backend.call("POST", "/internal/albums/part" if album else "/internal/messages", json=body)
    if type(accepted) is dict:
        event('telegram.submitted', component='telegram_adapter',
              backend_request_id=accepted.get('profile_id'), backend_job_id=accepted.get('job_id'))


def deliver_pending(api, backend):
    for item in backend.call("GET", "/internal/deliveries"):
        with request_scope('telegram', item.get('profile_id'), item.get('job_id'), scope='delivery'):
            try:
                with span('transport_delivery'):
                    chunks = split_message(item["response"])
                    for index in range(item["delivery_index"], len(chunks)):
                        api.send_text(item["chat_id"], chunks[index])
                        backend.call(
                            "POST",
                            f"/internal/deliveries/{item['request_id']}",
                            json={"index": index + 1, "done": index + 1 == len(chunks)},
                        )
            except Exception as exc:
                event('delivery.failed', component='telegram_adapter', error=exc, delivery_outcome='failed')
                raise
            else:
                event('delivery.completed', component='telegram_adapter', delivery_outcome='completed')


def main():
    configure_logging()
    if os.getenv("TELEGRAM_ENABLED", "true") == "false":
        return
    if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_ALLOWED_USER_ID"):
        event('telegram.disabled', component='telegram_adapter', level=logging.ERROR)
        return
    backend = BackendClient()
    api = TelegramAPI(os.environ["TELEGRAM_BOT_TOKEN"])
    retry = 1
    while True:
        try:
            offset = backend.call("GET", "/internal/offset")["offset"]
            backend.call("POST", "/internal/albums/flush")
            deliver_pending(api, backend)
            params = {"timeout": 3, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            for update in api.call("getUpdates", request_timeout=15, **params):
                accept_update(api, backend, update)
                # Offset advances only after the backend durably accepted the message.
                backend.call(
                    "POST", "/internal/offset", json={"offset": update["update_id"] + 1}
                )
            backend.call("POST", "/internal/albums/flush")
            backend.call("POST", "/internal/status", json={"status": "połączony"})
            retry = 1
        except Exception as exc:
            # Do not log request URLs, tokens or private message bodies.
            with request_scope('telegram', background=True, scope='background'):
                event('telegram.unavailable', component='telegram_adapter', error=exc)
            try:
                backend.call(
                    "POST", "/internal/status", json={"status": "ponawianie połączenia"}
                )
            except Exception:
                pass
            time.sleep(retry)
            retry = min(retry * 2, 30)


if __name__ == "__main__":
    main()
