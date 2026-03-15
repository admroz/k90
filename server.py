"""
Kadencja90 NG — serwer agenta (LiteLLM + Signal WebSocket).
"""

import base64
import json
import logging
import os
import time
import threading
import requests
import websocket
from dotenv import load_dotenv

from agent import run_agent
from tools.db import init_db
from tools.commands import handle_command
from summary import maybe_refresh_summary, refresh_patient_summary

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SIGNAL_API_URL = os.getenv("SIGNAL_CLI_REST_API_URL", "http://signal:8080")
SIGNAL_BOT_NUMBER = os.getenv("SIGNAL_PHONE_NUMBER", "")
ALLOWED_SENDER = os.getenv("SIGNAL_ALLOWED_SENDER", "")


def download_attachment(attachment_id: str) -> tuple[bytes, str]:
    """Pobiera załącznik z signal-cli-rest-api. Zwraca (bytes, mime_type)."""
    resp = requests.get(
        f"{SIGNAL_API_URL}/v1/attachments/{attachment_id}",
        timeout=30,
    )
    resp.raise_for_status()
    mime_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    return resp.content, mime_type


def handle_message(envelope: dict) -> None:
    data_message = envelope.get("dataMessage", {})
    text = (data_message.get("message") or "").strip()
    attachments = data_message.get("attachments", [])

    if not text and not attachments:
        return

    sender_number = envelope.get("sourceNumber")
    sender_uuid = envelope.get("sourceUuid", "")

    if ALLOWED_SENDER and sender_number != ALLOWED_SENDER:
        log.warning("Odrzucono: numer=%s uuid=%s", sender_number, sender_uuid)
        return

    sender = sender_number or sender_uuid
    log.info("Wiadomość od %s (%s): '%s' + %d załącznik(ów)",
             envelope.get("sourceName", "?"), sender, text[:60], len(attachments))

    # Zbuduj content dla LiteLLM
    content_parts = []
    if text:
        content_parts.append({"type": "text", "text": text})
    elif attachments:
        content_parts.append({"type": "text", "text": "Co to za posiłek? Przeanalizuj zdjęcie, oszacuj składniki i kalorie, a następnie zapisz jako mój posiłek."})

    for att in attachments:
        content_type = att.get("contentType", "")
        if not content_type.startswith("image/"):
            continue
        att_id = att.get("id")
        if not att_id:
            continue
        try:
            img_bytes, mime_type = download_attachment(att_id)
            b64 = base64.b64encode(img_bytes).decode()
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            })
            log.info("Załączono zdjęcie: %s (%d B)", mime_type, len(img_bytes))
        except Exception as e:
            log.error("Błąd pobierania załącznika %s: %s", att_id, e)

    if not content_parts:
        return

    # Jeśli tylko tekst — przekaż jako string (szeroka kompatybilność z modelami)
    if len(content_parts) == 1 and content_parts[0]["type"] == "text":
        user_message = content_parts[0]["text"]
    else:
        user_message = content_parts

    command_response = handle_command(text) if text else None
    if command_response is not None:
        send_signal_message(sender, command_response)
        return

    try:
        response, should_refresh = run_agent(user_message, user_id=sender)
    except Exception as e:
        log.error("Błąd agenta: %s", e)
        response = "Przepraszam, wystąpił błąd. Spróbuj ponownie."
        should_refresh = False

    send_signal_message(sender, response)

    if should_refresh:
        log.info("Odświeżanie podsumowania pacjenta (trigger: tool_call)...")
        threading.Thread(
            target=refresh_patient_summary,
            kwargs={"trigger": "tool_call"},
            daemon=True,
        ).start()


def send_signal_message(recipient: str, message: str) -> None:
    url = f"{SIGNAL_API_URL}/v2/send"
    payload = {"message": message, "number": SIGNAL_BOT_NUMBER, "recipients": [recipient]}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        log.info("Wysłano odpowiedź do %s", recipient)
    except requests.HTTPError as e:
        log.error("Błąd wysyłania Signal: %s — %s", e, e.response.text)
    except Exception as e:
        log.error("Błąd wysyłania Signal: %s", e)


def on_message(ws, raw):
    try:
        data = json.loads(raw)
        envelope = data.get("envelope", {})
        if "dataMessage" in envelope:
            threading.Thread(target=handle_message, args=(envelope,), daemon=True).start()
    except Exception as e:
        log.error("Błąd parsowania: %s", e)


def on_error(ws, error):
    log.error("WebSocket błąd: %s", error)


def on_close(ws, code, msg):
    log.warning("WebSocket zamknięty (%s): %s", code, msg)


def on_open(ws):
    log.info("WebSocket połączony — nasłuchuję wiadomości Signal")


def connect_websocket():
    ws_url = SIGNAL_API_URL.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/v1/receive/{SIGNAL_BOT_NUMBER}"
    log.info("Łączę WebSocket: %s", ws_url)
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url, on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            log.error("WebSocket wyjątek: %s", e)
        log.info("Reconnect za 5 sekund...")
        time.sleep(5)


if __name__ == "__main__":
    log.info("Kadencja90 NG startuje (bot: %s)", SIGNAL_BOT_NUMBER)
    init_db()
    maybe_refresh_summary()
    connect_websocket()
