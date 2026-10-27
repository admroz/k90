"""
k90 — agent medyczny.

Uruchomienie (CLI):
    python agent.py

Wymagane zmienne środowiskowe (.env):
    AGENT_MODEL=gpt-5.4  # lub inny model obsługiwany przez LiteLLM
    OPENAI_API_KEY=...
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import closing
from profiling import span as _phase, profiled, profiled_request
from logging_setup import configure_logging, event
import profiling
configure_logging()
import litellm
from dotenv import load_dotenv

from responses_api import FunctionCall, ResponsesConversation, uses_responses
import memory_runtime
from k90_memory.privacy import strict_json_loads
from outbound_policy import chat_completion, model_policy, project_history

from system_prompt import SYSTEM_PROMPT
from tools import TOOLS, execute_tool
from tools.commands import handle_command
from tools.context import build_operational_context
from tools.db import MESSAGE_CONTEXT, get_conn, init_db
from tools.garmin import mark_summary_refreshed, should_auto_sync_today, sync_garmin_data, sync_has_changes
from tools.libre import should_auto_sync as should_auto_sync_libre, sync_libre_data, sync_has_changes as libre_sync_has_changes
from tools.time_utils import now_local

load_dotenv()

log = logging.getLogger('agent')

MODEL = os.getenv("AGENT_MODEL", "gpt-5.4")
HISTORY_MESSAGES = int(os.getenv("HISTORY_MESSAGES", "10"))
MAX_TOOL_ROUNDS = 10

SUMMARY_REFRESH_TRIGGERS = {"sync_garmin_data", "update_patient_file", "refresh_patient_summary"}


def _completion_options(model: str) -> dict:
    """Return endpoint-compatible options for the configured chat model."""
    model_name = model.rsplit("/", 1)[-1]
    if model_name.startswith("gpt-5.6"):
        # GPT-5.6 function tools with reasoning require the Responses API.
        # This agent still uses Chat Completions, so preserve tool calling by
        # explicitly using the non-reasoning mode.
        return {"reasoning_effort": "none"}
    return {}


def _save_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO usage_stats (model, prompt_tokens, completion_tokens) VALUES (?, ?, ?)",
        (model, prompt_tokens, completion_tokens),
    )
    conn.commit()
    conn.close()


@profiled('history')
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
        content = project_history(row["content"])
        result.append({"role": row["role"], "content": content})
    return result


@profiled('persistence')
def save_history(user_id: str, user_content, assistant_content: str) -> None:
    """Zapisuje wiadomość użytkownika i odpowiedź asystenta do historii."""
    if isinstance(user_content, list):
        user_text = json.dumps(user_content, ensure_ascii=False)
    else:
        user_text = user_content
    context = MESSAGE_CONTEXT.get()
    turn = memory_runtime.TURN_CONTEXT.get() or {}
    request_id = context.get("request_id") or turn.get("request_id")
    with closing(get_conn()) as conn, conn:
        user_row = conn.execute(
            "INSERT INTO conversations (user_id, role, content, channel, request_id) VALUES (?, 'user', ?, ?, ?)",
            (user_id, user_text, context.get("channel"), request_id),
        )
        assistant_row = conn.execute(
            "INSERT INTO conversations (user_id, role, content, channel, request_id) VALUES (?, 'assistant', ?, ?, ?)",
            (user_id, assistant_content, context.get("channel"), request_id),
        )
        memory_runtime.record_pair(conn, user_id, user_content, assistant_content,
                                   user_conversation_id=user_row.lastrowid,
                                   assistant_conversation_id=assistant_row.lastrowid)


def _build_system_message() -> tuple[str, dict]:
    from summary import load_patient_summary

    patient_summary = load_patient_summary()
    operational_context, context_stats = build_operational_context()
    prompt, patient_summary, operational_context = model_policy().sanitize(
        [SYSTEM_PROMPT, patient_summary, operational_context])

    now = now_local()
    date_context = f"Dzisiaj jest {now.strftime('%A, %d.%m.%Y')}, godzina {now.strftime('%H:%M')}."

    parts = [prompt, date_context]
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


@profiled_request
def run_agent(user_message: str | list, user_id: str = "cli") -> tuple[str, bool]:
    """Capture originals durably before any outbound work, even if a provider fails."""
    with _phase("capture"):
        turn = memory_runtime.begin_turn(user_id, user_message)
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        from tools.food_catalog import approval_command
        approval = approval_command(user_message)
        if approval is not None:
            save_history(user_id, user_message, approval)
            return approval, False
        memory_runtime.start_worker()
        result = _run_agent(user_message, user_id)
        event('response.completed', response_outcome='completed', delivery_outcome='pending', mutation_outcome='unknown')
        return result
    except BaseException as exc:
        event('response.failed', error=exc, response_outcome='failed', delivery_outcome='pending', mutation_outcome='unknown')
        try:
            memory_runtime.record_failure(type(exc).__name__)
        except Exception:
            log.warning("agent.failure_record.unavailable")
        raise
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)


def _run_agent(user_message: str | list, user_id: str = "cli") -> tuple[str, bool]:
    """Uruchamia agenta i zwraca (odpowiedź, czy_odświeżyć_podsumowanie)."""
    history = load_history(user_id)
    with _phase("context"):
        system, context_stats = _build_system_message()
    from tools.food_catalog import CATALOG_PROMPT
    system += '\n\n' + CATALOG_PROMPT
    turn = memory_runtime.TURN_CONTEXT.get() or {}
    recalled, memory_stats = memory_runtime.recall_context(user_id, user_message,
                                                        exclude=[turn.get('source_id')])
    context_stats.update(memory_stats)
    if recalled:
        system += "\n\n" + recalled
    log_user = "event:" + str(turn.get('user_event_id', 'unknown'))

    messages = [{"role": "system", "content": system}] + history
    messages.append({"role": "user", "content": user_message})

    completion_options = _completion_options(MODEL)
    log.info(
        "agent.start user=%s model=%s reasoning_effort=%s input=%s history_records=%d context_sections=%d context_chars=%d summary_chars=%d",
        log_user,
        MODEL,
        (os.getenv("AGENT_REASONING_EFFORT", "low") if uses_responses(MODEL)
         else completion_options.get("reasoning_effort", "default")),
        _message_kind(user_message),
        len(history),
        context_stats.get("sections", 0),
        context_stats.get("chars", 0),
        context_stats.get("summary_chars", 0),
    )

    should_refresh = False
    responses = None
    auth_mode = os.getenv('K90_AGENT_AUTH', 'api').strip().casefold()
    if auth_mode == 'chatgpt':
        from subscription_api import SubscriptionConversation
        from subscription_auth import TokenStore
        from subscription_login import default_state_directory
        responses = SubscriptionConversation(MODEL, messages, TOOLS,
            token_store=TokenStore(default_state_directory()), policy=model_policy(),
            reasoning_effort=os.getenv('AGENT_REASONING_EFFORT', 'low'))
    elif auth_mode != 'api':
        raise ValueError('invalid_agent_auth_mode')
    elif uses_responses(MODEL):
        responses = ResponsesConversation(
            MODEL, messages, TOOLS,
            reasoning_effort=os.getenv("AGENT_REASONING_EFFORT", "low"),
            max_output_tokens=int(os.getenv("AGENT_MAX_OUTPUT_TOKENS", "8192")),
        )

    for round_index in range(1, MAX_TOOL_ROUNDS + 1):
        profiling.indices(round_index)
        with _phase("provider"):
            if responses is not None:
                turn = responses.complete()
                # A truncated response may contain partial arguments. Never run its tools.
                if not turn.complete:
                    _save_usage(MODEL, turn.input_tokens, turn.output_tokens)
                    raise RuntimeError("Odpowiedź modelu została przerwana przez limit tokenów; zwiększ AGENT_MAX_OUTPUT_TOKENS.")
                calls, answer = turn.calls, turn.text
                prompt_tokens, completion_tokens = turn.input_tokens, turn.output_tokens
            else:
                response = chat_completion(litellm.completion,
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    **completion_options,
                )
                msg = response.choices[0].message
                messages.append(msg.model_dump(exclude_none=True))
                calls = [FunctionCall(call.id, call.function.name, call.function.arguments)
                         for call in (msg.tool_calls or [])]
                answer = msg.content or ""
                usage = getattr(response, "usage", None)
                prompt_tokens = usage.prompt_tokens if usage else 0
                completion_tokens = usage.completion_tokens if usage else 0
        if prompt_tokens or completion_tokens:
            _save_usage(MODEL, prompt_tokens, completion_tokens)
            log.info(
                "agent.usage user=%s round=%d prompt_tokens=%s completion_tokens=%s",
                log_user,
                round_index,
                prompt_tokens,
                completion_tokens,
            )

        if not calls:
            if responses is not None and not answer.strip():
                raise RuntimeError("Model nie zwrócił tekstu odpowiedzi.")
            save_history(user_id, user_message, answer)
            log.info(
                "agent.finish user=%s round=%d response_chars=%d refresh=%s",
                log_user,
                round_index,
                len(answer),
                should_refresh,
            )
            return answer, should_refresh

        tool_names = [tool_call.name for tool_call in calls]
        log.info("agent.tools user=%s round=%d tool_calls=%s", log_user, round_index, ",".join(tool_names))

        for tool_index, tool_call in enumerate(calls, 1):
            profiling.indices(round_index, tool_index)
            if tool_call.name in SUMMARY_REFRESH_TRIGGERS:
                should_refresh = True
            args = strict_json_loads(tool_call.arguments or "{}")
            with _phase('tool') as failed:
                result = execute_tool(tool_call.name, args)
                if failed is not None and isinstance(result, dict) and 'error' in result:
                    failed[0] = True
            event('tool.completed', mutation_outcome='unknown',
                  tool_outcome='error' if 'error' in result else 'returned')
            memory_runtime.record_tool(tool_call.name, args, result)
            log.info(
                "agent.tool_result user=%s tool=%s ok=%s",
                log_user,
                tool_call.name,
                "error" not in result,
            )
            if responses is not None:
                responses.add_tool_result(tool_call.call_id, result)
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.call_id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

    answer = "Przepraszam, nie mogłem przetworzyć Twojego zapytania."
    save_history(user_id, user_message, answer)
    log.warning("agent.max_rounds user=%s rounds=%d", log_user, MAX_TOOL_ROUNDS)
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

        with profiling.request_scope('cli'):
            command_response = handle_command(user_input)
            if command_response is not None:
                print(f"\nAgent: {command_response}\n")
                continue

            sync_prefix = ""
            garmin_due = should_auto_sync_today()
            libre_due = should_auto_sync_libre()
            if garmin_due or libre_due:
                print("\nAgent: Aktualizuję dane zdrowotne, odpowiem za chwilę.\n")

                errors = []
                changed_sources = []

                if garmin_due:
                    garmin_result = sync_garmin_data(trigger="auto_daily_cli")
                    if "error" in garmin_result:
                        errors.append("Garmin")
                    elif sync_has_changes(garmin_result):
                        changed_sources.append("Garmin")
                        mark_summary_refreshed()

                if libre_due:
                    libre_result = sync_libre_data(trigger="auto_stale_cli")
                    if "error" in libre_result:
                        errors.append("Libre")
                    elif libre_sync_has_changes(libre_result):
                        changed_sources.append("Libre")

                if changed_sources:
                    if "Garmin" in changed_sources:
                        from summary import refresh_patient_summary

                        refresh_patient_summary(trigger="auto_sync_cli")
                    sync_prefix = f"Mam nowe dane ({', '.join(changed_sources)}) i uwzględniam je w odpowiedzi.\n\n"
                elif errors:
                    sync_prefix = f"Uwaga: synchronizacja danych ({', '.join(errors)}) nie powiodła się; odpowiedź może bazować na starszych danych.\n\n"

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
                event('response.failed', error=exc, response_outcome='failed')
                print("\n[Błąd]: Nie udało się zakończyć odpowiedzi. Sprawdź bezpieczne logi.\n")


if __name__ == "__main__":
    cli()
