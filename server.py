"""k90 — Telegram long-polling transport for the health agent."""

from __future__ import annotations

import base64
import logging
import os
import threading
import time
from typing import Any

import requests
from dotenv import load_dotenv

from agent import run_agent
from summary import maybe_refresh_summary, refresh_patient_summary
from tools.commands import handle_command
from tools.db import init_db
from tools.garmin import mark_summary_refreshed, should_auto_sync_today, sync_garmin_data, sync_has_changes
from tools.libre import should_auto_sync as should_auto_sync_libre, sync_libre_data, sync_has_changes as libre_sync_has_changes

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
CONVERSATION_USER_ID = os.getenv("CONVERSATION_USER_ID", "owner")
TELEGRAM_POLL_TIMEOUT = int(os.getenv("TELEGRAM_POLL_TIMEOUT", "30"))
TELEGRAM_MESSAGE_LIMIT = 4096


class TelegramAPIError(RuntimeError):
    """Telegram Bot API error safe to log without exposing the bot token."""


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self._api_url = f"https://api.telegram.org/bot{token}"
        self._file_url = f"https://api.telegram.org/file/bot{token}"
        self._session = requests.Session()

    def call(self, method: str, *, request_timeout: int = 40, **params: Any) -> Any:
        try:
            response = self._session.post(f"{self._api_url}/{method}", json=params, timeout=request_timeout)
        except requests.RequestException as exc:
            raise TelegramAPIError(f"{method}: network error ({type(exc).__name__})") from None

        try:
            payload = response.json()
        except ValueError:
            raise TelegramAPIError(f"{method}: invalid response (HTTP {response.status_code})") from None

        if not response.ok or not payload.get("ok"):
            description = payload.get("description", f"HTTP {response.status_code}")
            raise TelegramAPIError(f"{method}: {description}")
        return payload.get("result")

    def get_updates(self, offset: int | None) -> list[dict]:
        params: dict[str, Any] = {"timeout": TELEGRAM_POLL_TIMEOUT, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", request_timeout=TELEGRAM_POLL_TIMEOUT + 10, **params)

    def send_text(self, chat_id: int, message: str) -> None:
        for chunk in split_message(message):
            self.call("sendMessage", chat_id=chat_id, text=chunk)
            log.info("telegram.sent chat_id=%s chars=%d", chat_id, len(chunk))

    def download_file(self, file_id: str) -> tuple[bytes, str]:
        file_info = self.call("getFile", file_id=file_id)
        file_path = file_info.get("file_path") if isinstance(file_info, dict) else None
        if not file_path:
            raise TelegramAPIError("getFile: missing file_path")
        try:
            response = self._session.get(f"{self._file_url}/{file_path}", timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TelegramAPIError(f"download file: network error ({type(exc).__name__})") from None
        mime_type = response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]
        return response.content, mime_type


def split_message(message: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split a response into Telegram-sized chunks, preferring line boundaries."""
    if not message:
        return ["Przepraszam, nie mam odpowiedzi do wysłania."]
    chunks = []
    remaining = message
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _sync_health_data(api: TelegramAPI, chat_id: int, sender: str) -> tuple[str, str]:
    sync_warning = ""
    sync_notice = ""
    garmin_due = should_auto_sync_today()
    libre_due = should_auto_sync_libre()
    if not (garmin_due or libre_due):
        return sync_warning, sync_notice

    api.send_text(chat_id, "Aktualizuję dane zdrowotne, odpowiem za chwilę.")
    errors = []
    changed_sources = []

    if garmin_due:
        garmin_result = sync_garmin_data(trigger="auto_daily")
        if "error" in garmin_result:
            errors.append("Garmin")
            log.warning("garmin.auto_sync_failed sender=%s error=%s", sender, garmin_result["error"])
        elif sync_has_changes(garmin_result):
            changed_sources.append("Garmin")
            mark_summary_refreshed()
        else:
            log.info("garmin.auto_sync_no_changes sender=%s", sender)

    if libre_due:
        libre_result = sync_libre_data(trigger="auto_stale")
        if "error" in libre_result:
            errors.append("Libre")
            log.warning("libre.auto_sync_failed sender=%s error=%s", sender, libre_result["error"])
        elif libre_sync_has_changes(libre_result):
            changed_sources.append("Libre")
        else:
            log.info("libre.auto_sync_no_changes sender=%s", sender)

    if changed_sources:
        if "Garmin" in changed_sources:
            refresh_patient_summary(trigger="auto_sync")
        sync_notice = f"Mam nowe dane ({', '.join(changed_sources)}) i uwzględniam je w odpowiedzi.\n\n"
    elif errors:
        sync_warning = f"Uwaga: synchronizacja danych ({', '.join(errors)}) nie powiodła się; odpowiedź może bazować na starszych danych.\n\n"
    return sync_warning, sync_notice


def _image_from_message(message: dict) -> tuple[str, str] | None:
    photos = message.get("photo") or []
    if photos:
        return photos[-1]["file_id"], "image/jpeg"
    document = message.get("document") or {}
    mime_type = document.get("mime_type", "")
    if document.get("file_id") and mime_type.startswith("image/"):
        return document["file_id"], mime_type
    return None


def handle_telegram_message(api: TelegramAPI, message: dict) -> None:
    chat = message.get("chat") or {}
    sender_data = message.get("from") or {}
    chat_id = chat.get("id")
    sender_id = sender_data.get("id")
    if chat_id is None or sender_id is None:
        return
    if chat.get("type") != "private":
        log.warning("telegram.reject reason=non_private chat_id=%s user_id=%s", chat_id, sender_id)
        return
    if str(sender_id) != TELEGRAM_ALLOWED_USER_ID:
        log.warning("telegram.reject reason=not_allowed chat_id=%s user_id=%s", chat_id, sender_id)
        return

    text = (message.get("text") or message.get("caption") or "").strip()
    image = _image_from_message(message)
    if not text and not image:
        return
    log.info("telegram.message chat_id=%s user_id=%s text_chars=%d image=%s", chat_id, sender_id, len(text), bool(image))

    command_response = handle_command(text) if text else None
    if command_response is not None:
        api.send_text(chat_id, command_response)
        return

    sender = CONVERSATION_USER_ID or f"telegram:{sender_id}"
    sync_warning, sync_notice = _sync_health_data(api, chat_id, sender)

    content_parts = []
    if text:
        content_parts.append({"type": "text", "text": text})
    elif image:
        content_parts.append({
            "type": "text",
            "text": (
                "Przeanalizuj załączone zdjęcie. Najpierw oceń, czy to wygląda na posiłek, dokument medyczny czy coś innego. "
                "Jeśli to wygląda na posiłek, oszacuj składniki oraz kcal, białko, węglowodany i tłuszcz. "
                "Nie zapisuj posiłku, jeśli z obrazu i kontekstu nie wynika jasno, że został zjedzony. "
                "Jeśli jednak zapiszesz posiłek, podaj potem dokładnie id, datę i godzinę zwrócone przez log_meal."
            ),
        })

    if image:
        file_id, declared_mime_type = image
        try:
            image_bytes, downloaded_mime_type = api.download_file(file_id)
            mime_type = downloaded_mime_type if downloaded_mime_type.startswith("image/") else declared_mime_type
            encoded = base64.b64encode(image_bytes).decode()
            content_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
            log.info("telegram.image mime=%s bytes=%d", mime_type, len(image_bytes))
        except Exception as exc:
            log.error("telegram.image_error error=%s", exc)
            if not text:
                api.send_text(chat_id, "Nie udało mi się pobrać załączonego obrazu. Spróbuj wysłać go ponownie.")
                return

    user_message: str | list[dict]
    if len(content_parts) == 1 and content_parts[0]["type"] == "text":
        user_message = content_parts[0]["text"]
    else:
        user_message = content_parts

    try:
        response, should_refresh = run_agent(user_message, user_id=sender)
    except Exception as exc:
        log.exception("agent.error sender=%s error=%s", sender, exc)
        response = "Przepraszam, wystąpił błąd. Spróbuj ponownie."
        should_refresh = False

    if sync_warning:
        response = sync_warning + response
    elif sync_notice:
        response = sync_notice + response
    api.send_text(chat_id, response)

    if should_refresh:
        log.info("summary.async_refresh trigger=tool_call sender=%s", sender)
        threading.Thread(target=refresh_patient_summary, kwargs={"trigger": "tool_call"}, daemon=True).start()
    log.info("telegram.response chat_id=%s chars=%d refresh=%s", chat_id, len(response), should_refresh)


def run_polling(api: TelegramAPI) -> None:
    offset = None
    retry_delay = 1
    while True:
        try:
            updates = api.get_updates(offset)
            retry_delay = 1
            for update in updates:
                update_id = update.get("update_id")
                try:
                    message = update.get("message")
                    if message:
                        handle_telegram_message(api, message)
                except Exception as exc:
                    log.exception("telegram.update_error update_id=%s error=%s", update_id, exc)
                finally:
                    if isinstance(update_id, int):
                        offset = update_id + 1
        except TelegramAPIError as exc:
            log.error("telegram.poll_error error=%s retry_in=%s", exc, retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if not TELEGRAM_ALLOWED_USER_ID:
        log.warning(
            "telegram.allowed_user_missing; messages will be rejected. "
            "Send a message to the bot, read user_id from the log, set TELEGRAM_ALLOWED_USER_ID and restart."
        )
    init_db()
    try:
        maybe_refresh_summary()
    except Exception as exc:
        log.exception("summary.startup_refresh_failed error=%s", exc)
    api = TelegramAPI(TELEGRAM_BOT_TOKEN)
    bot = api.call("getMe")
    log.info("telegram.connected bot=@%s", bot.get("username", "unknown"))
    try:
        run_polling(api)
    except KeyboardInterrupt:
        log.info("telegram.stopped")


if __name__ == "__main__":
    main()
