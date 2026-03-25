"""k90 — serwer agenta (LiteLLM + Signal WebSocket)."""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time

import requests
import websocket
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

SIGNAL_API_URL = os.getenv("SIGNAL_CLI_REST_API_URL", "http://signal:8080")
SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_PHONE_NUMBER", "")
ALLOWED_SENDER = os.getenv("SIGNAL_ALLOWED_SENDER", "")


def download_attachment(attachment_id: str) -> tuple[bytes, str]:
    """Pobiera załącznik z signal-cli-rest-api. Zwraca (bytes, mime_type)."""
    response = requests.get(f"{SIGNAL_API_URL}/v1/attachments/{attachment_id}", timeout=30)
    response.raise_for_status()
    mime_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
    return response.content, mime_type


def handle_message(envelope: dict) -> None:
    data_message = envelope.get("dataMessage", {})
    text = (data_message.get("message") or "").strip()
    attachments = data_message.get("attachments", [])

    if not text and not attachments:
        return

    sender_number = envelope.get("sourceNumber")
    sender_uuid = envelope.get("sourceUuid", "")

    if ALLOWED_SENDER and sender_number != ALLOWED_SENDER:
        log.warning("signal.reject sender=%s uuid=%s", sender_number, sender_uuid)
        return

    sender = sender_number or sender_uuid
    log.info(
        "signal.message sender=%s text_chars=%d attachments=%d",
        sender,
        len(text),
        len(attachments),
    )

    command_response = handle_command(text) if text else None
    if command_response is not None:
        send_signal_message(sender, command_response)
        return

    sync_warning = ""
    sync_notice = ""
    garmin_due = should_auto_sync_today()
    libre_due = should_auto_sync_libre()
    if garmin_due or libre_due:
        send_signal_message(sender, "Aktualizuję dane zdrowotne, odpowiem za chwilę.")

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
                log.info("garmin.auto_sync_refreshed sender=%s", sender)
            else:
                log.info("garmin.auto_sync_no_changes sender=%s", sender)

        if libre_due:
            libre_result = sync_libre_data(trigger="auto_stale")
            if "error" in libre_result:
                errors.append("Libre")
                log.warning("libre.auto_sync_failed sender=%s error=%s", sender, libre_result["error"])
            elif libre_sync_has_changes(libre_result):
                changed_sources.append("Libre")
                log.info("libre.auto_sync_refreshed sender=%s", sender)
            else:
                log.info("libre.auto_sync_no_changes sender=%s", sender)

        if changed_sources:
            if "Garmin" in changed_sources:
                refresh_patient_summary(trigger="auto_sync")
            sync_notice = f"Mam nowe dane ({', '.join(changed_sources)}) i uwzględniam je w odpowiedzi.\n\n"
        elif errors:
            sync_warning = f"Uwaga: synchronizacja danych ({', '.join(errors)}) nie powiodła się; odpowiedź może bazować na starszych danych.\n\n"

    content_parts = []
    if text:
        content_parts.append({"type": "text", "text": text})
    elif attachments:
        content_parts.append({
            "type": "text",
            "text": (
                "Przeanalizuj załączone zdjęcie. Najpierw oceń, czy to wygląda na posiłek, dokument medyczny czy coś innego. "
                "Jeśli to wygląda na posiłek, oszacuj składniki oraz kcal, białko, węglowodany i tłuszcz. "
                "Nie zapisuj posiłku, jeśli z obrazu i kontekstu nie wynika jasno, że został zjedzony. "
                "Jeśli jednak zapiszesz posiłek, podaj potem dokładnie id, datę i godzinę zwrócone przez log_meal."
            ),
        })

    image_count = 0
    for attachment in attachments:
        content_type = attachment.get("contentType", "")
        if not content_type.startswith("image/"):
            log.info("signal.attachment skipped content_type=%s", content_type)
            continue
        attachment_id = attachment.get("id")
        if not attachment_id:
            continue
        try:
            image_bytes, mime_type = download_attachment(attachment_id)
            encoded = base64.b64encode(image_bytes).decode()
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
            })
            image_count += 1
            log.info("signal.attachment image mime=%s bytes=%d", mime_type, len(image_bytes))
        except Exception as exc:
            log.error("signal.attachment_error id=%s error=%s", attachment_id, exc)

    if not content_parts:
        return

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

    send_signal_message(sender, response)

    if should_refresh:
        log.info("summary.async_refresh trigger=tool_call sender=%s", sender)
        threading.Thread(
            target=refresh_patient_summary,
            kwargs={"trigger": "tool_call"},
            daemon=True,
        ).start()

    log.info("signal.response sender=%s chars=%d images=%d refresh=%s", sender, len(response), image_count, should_refresh)


def send_signal_message(recipient: str, message: str) -> None:
    url = f"{SIGNAL_API_URL}/v2/send"
    payload = {"message": message, "number": SIGNAL_BOT_NUMBER, "recipients": [recipient]}
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        log.info("signal.sent recipient=%s chars=%d", recipient, len(message))
    except requests.HTTPError as exc:
        log.error("signal.send_http_error recipient=%s error=%s body=%s", recipient, exc, exc.response.text)
    except Exception as exc:
        log.error("signal.send_error recipient=%s error=%s", recipient, exc)


def on_message(ws, raw):
    try:
        data = json.loads(raw)
        envelope = data.get("envelope", {})
        if "dataMessage" in envelope:
            threading.Thread(target=handle_message, args=(envelope,), daemon=True).start()
    except Exception as exc:
        log.error("signal.parse_error error=%s", exc)


def on_error(ws, error):
    log.error("signal.websocket_error error=%s", error)


def on_close(ws, code, msg):
    log.warning("signal.websocket_closed code=%s msg=%s", code, msg)


def on_open(ws):
    log.info("signal.websocket_connected")


def connect_websocket() -> None:
    ws_url = SIGNAL_API_URL.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/v1/receive/{SIGNAL_BOT_NUMBER}"
    log.info("signal.websocket_connect url=%s", ws_url)
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as exc:
            log.error("signal.websocket_exception error=%s", exc)
        log.info("signal.websocket_reconnect_in seconds=5")
        time.sleep(5)


if __name__ == "__main__":
    log.info("server.start bot=%s", SIGNAL_BOT_NUMBER)
    init_db()
    maybe_refresh_summary()
    connect_websocket()
