"""
k90 — agent medyczny.

Uruchomienie (CLI):
    python agent.py

Wymagane zmienne środowiskowe (.env):
    AGENT_MODEL=gpt-4o  # lub inny model obsługiwany przez LiteLLM
    OPENAI_API_KEY=...
"""

from __future__ import annotations

import json
import logging
import os
import litellm
from dotenv import load_dotenv

from system_prompt import SYSTEM_PROMPT
from tools import TOOLS, execute_tool
from tools.commands import handle_command
from tools.context import build_operational_context
from tools.db import get_conn, init_db
from tools.garmin import mark_summary_refreshed, should_auto_sync_today, sync_garmin_data, sync_has_changes
from tools.time_utils import now_local

load_dotenv()

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL = os.getenv("AGENT_MODEL", "gpt-4o")
HISTORY_MESSAGES = int(os.getenv("HISTORY_MESSAGES", "10"))
MAX_TOOL_ROUNDS = 10

SUMMARY_REFRESH_TRIGGERS = {"sync_garmin_data", "update_patient_file", "refresh_patient_summary"}


def _save_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO usage_stats (model, prompt_tokens, completion_tokens) VALUES (?, ?, ?)",
        (model, prompt_tokens, completion_tokens),
    )
    conn.commit()
    conn.close()


def load_history(user_id: str) -> list[dict]:
    """Ładuje ostatnie HISTORY_MESSAGES par wiadomości z historii rozmów."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, HISTORY_MESSAGES * 2),
    ).fetchall()
    conn.close()
    result = []
    for row in reversed(rows):
        content = row["content"]
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                content = parsed
        except (json.JSONDecodeError, TypeError):
            pass
        result.append({"role": row["role"], "content": content})
    return result


def save_history(user_id: str, user_content, assistant_content: str) -> None:
    """Zapisuje wiadomość użytkownika i odpowiedź asystenta do historii."""
    if isinstance(user_content, list):
        user_text = json.dumps(user_content, ensure_ascii=False)
    else:
        user_text = user_content
    conn = get_conn()
    conn.execute(
        "INSERT INTO conversations (user_id, role, content) VALUES (?, 'user', ?)",
        (user_id, user_text),
    )
    conn.execute(
        "INSERT INTO conversations (user_id, role, content) VALUES (?, 'assistant', ?)",
        (user_id, assistant_content),
    )
    conn.commit()
    conn.close()


def _build_system_message() -> tuple[str, dict]:
    from summary import load_patient_summary

    patient_summary = load_patient_summary()
    operational_context, context_stats = build_operational_context()

    now = now_local()
    date_context = f"Dzisiaj jest {now.strftime('%A, %d.%m.%Y')}, godzina {now.strftime('%H:%M')}."

    parts = [SYSTEM_PROMPT, date_context]
    if patient_summary:
        parts.append(f"Trwała pamięć pacjenta:\n{patient_summary}")
    if operational_context:
        parts.append(f"Bieżący kontekst operacyjny:\n{operational_context}")

    context_stats["summary_chars"] = len(patient_summary)
    return "\n\n".join(parts), context_stats


def _message_kind(user_message: str | list) -> str:
    if isinstance(user_message, list):
        kinds = [part.get("type", "unknown") for part in user_message if isinstance(part, dict)]
        return ",".join(kinds) or "multipart"
    return "text"


def run_agent(user_message: str | list, user_id: str = "cli") -> tuple[str, bool]:
    """Uruchamia agenta i zwraca (odpowiedź, czy_odświeżyć_podsumowanie)."""
    history = load_history(user_id)
    system, context_stats = _build_system_message()

    messages = [{"role": "system", "content": system}] + history
    messages.append({"role": "user", "content": user_message})

    log.info(
        "agent.start user=%s model=%s input=%s history_records=%d context_sections=%d context_chars=%d summary_chars=%d",
        user_id,
        MODEL,
        _message_kind(user_message),
        len(history),
        context_stats.get("sections", 0),
        context_stats.get("chars", 0),
        context_stats.get("summary_chars", 0),
    )

    should_refresh = False

    for round_index in range(1, MAX_TOOL_ROUNDS + 1):
        response = litellm.completion(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if response.usage:
            _save_usage(MODEL, response.usage.prompt_tokens, response.usage.completion_tokens)
            log.info(
                "agent.usage user=%s round=%d prompt_tokens=%s completion_tokens=%s",
                user_id,
                round_index,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )

        if not msg.tool_calls:
            answer = msg.content or ""
            save_history(user_id, user_message, answer)
            log.info(
                "agent.finish user=%s round=%d response_chars=%d refresh=%s",
                user_id,
                round_index,
                len(answer),
                should_refresh,
            )
            return answer, should_refresh

        tool_names = [tool_call.function.name for tool_call in msg.tool_calls]
        log.info("agent.tools user=%s round=%d tool_calls=%s", user_id, round_index, ",".join(tool_names))

        for tool_call in msg.tool_calls:
            if tool_call.function.name in SUMMARY_REFRESH_TRIGGERS:
                should_refresh = True
            args = json.loads(tool_call.function.arguments or "{}")
            result = execute_tool(tool_call.function.name, args)
            log.info(
                "agent.tool_result user=%s tool=%s ok=%s",
                user_id,
                tool_call.function.name,
                "error" not in result,
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    answer = "Przepraszam, nie mogłem przetworzyć Twojego zapytania."
    save_history(user_id, user_message, answer)
    log.warning("agent.max_rounds user=%s rounds=%d", user_id, MAX_TOOL_ROUNDS)
    return answer, should_refresh


def cli() -> None:
    """Interaktywna pętla CLI do testowania agenta."""
    init_db()
    print(f"k90 — Agent medyczny (model: {MODEL})")
    print("Wpisz 'quit' lub 'exit' aby zakończyć.\n")

    while True:
        try:
            user_input = input("Ty: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDo widzenia.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Do widzenia.")
            break

        command_response = handle_command(user_input)
        if command_response is not None:
            print(f"\nAgent: {command_response}\n")
            continue

        sync_prefix = ""
        if should_auto_sync_today():
            print("\nAgent: Aktualizuję dane zdrowotne, odpowiem za chwilę.\n")
            sync_result = sync_garmin_data(trigger="auto_daily_cli")
            if "error" in sync_result:
                sync_prefix = "Uwaga: dzisiejsza synchronizacja danych nie powiodła się; odpowiedź może bazować na starszych danych.\n\n"
            elif sync_has_changes(sync_result):
                from summary import refresh_patient_summary

                refresh_patient_summary(trigger="auto_daily_sync_cli")
                mark_summary_refreshed()
                sync_prefix = "Mam nowe dane i uwzględniam je w odpowiedzi.\n\n"

        try:
            response, should_refresh = run_agent(user_input, user_id="cli")
            if sync_prefix:
                response = sync_prefix + response
            print(f"\nAgent: {response}\n")
            if should_refresh:
                print("[Auto-odświeżanie podsumowania pacjenta...]")
                from summary import refresh_patient_summary

                refresh_patient_summary(trigger="tool_call_cli")
        except Exception as exc:  # pragma: no cover - CLI path
            print(f"\n[Błąd]: {exc}\n")


if __name__ == "__main__":
    cli()
