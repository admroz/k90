"""
Kadencja90 NG — agent medyczny.

Uruchomienie (CLI):
    python agent.py

Wymagane zmienne środowiskowe (.env):
    AGENT_MODEL=claude-haiku-4-5-20251001  # lub inny model obsługiwany przez LiteLLM
    ANTHROPIC_API_KEY=...
"""

import json
import os
from datetime import datetime
from dotenv import load_dotenv
import litellm

from system_prompt import SYSTEM_PROMPT
from tools import TOOLS, execute_tool
from tools.db import get_conn, init_db

load_dotenv()

MODEL = os.getenv("AGENT_MODEL", "claude-haiku-4-5-20251001")
HISTORY_MESSAGES = int(os.getenv("HISTORY_MESSAGES", "10"))
MAX_TOOL_ROUNDS = 10

# Narzędzia których wywołanie wyzwala odświeżenie podsumowania pacjenta
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
    for r in reversed(rows):
        content = r["content"]
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                content = parsed
        except (json.JSONDecodeError, TypeError):
            pass
        result.append({"role": r["role"], "content": content})
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


def run_agent(
    user_message: "str | list",
    user_id: str = "cli",
) -> tuple[str, bool]:
    """Uruchamia agenta i zwraca (odpowiedź, czy_odświeżyć_podsumowanie).

    Args:
        user_message: Tekst lub lista content parts (dla obrazów w formacie LiteLLM).
        user_id: Identyfikator użytkownika (do historii w SQLite).

    Returns:
        (odpowiedź tekstowa, czy wywołano narzędzie wymagające odświeżenia podsumowania)
    """
    from summary import load_patient_summary

    history = load_history(user_id)
    patient_summary = load_patient_summary()

    now = datetime.now()
    date_context = f"Dzisiaj jest {now.strftime('%A, %d.%m.%Y')}, godzina {now.strftime('%H:%M')}."

    if patient_summary:
        system = f"{SYSTEM_PROMPT}\n\n{date_context}\n\nPodsumowanie kluczowych danych pacjenta:\n{patient_summary}"
    else:
        system = f"{SYSTEM_PROMPT}\n\n{date_context}"

    messages = [{"role": "system", "content": system}] + history
    messages.append({"role": "user", "content": user_message})

    should_refresh = False

    for _ in range(MAX_TOOL_ROUNDS):
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

        if not msg.tool_calls:
            answer = msg.content or ""
            save_history(user_id, user_message, answer)
            return answer, should_refresh

        for tc in msg.tool_calls:
            if tc.function.name in SUMMARY_REFRESH_TRIGGERS:
                should_refresh = True
            args = json.loads(tc.function.arguments or "{}")
            result = execute_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    answer = "Przepraszam, nie mogłem przetworzyć Twojego zapytania."
    save_history(user_id, user_message, answer)
    return answer, should_refresh


def cli():
    """Interaktywna pętla CLI do testowania agenta."""
    init_db()
    print(f"Kadencja90 NG — Agent medyczny (model: {MODEL})")
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

        try:
            response, should_refresh = run_agent(user_input, user_id="cli")
            print(f"\nAgent: {response}\n")
            if should_refresh:
                print("[Auto-odświeżanie podsumowania pacjenta...]")
                from summary import refresh_patient_summary
                refresh_patient_summary(trigger="tool_call_cli")
        except Exception as e:
            print(f"\n[Błąd]: {e}\n")


if __name__ == "__main__":
    cli()
