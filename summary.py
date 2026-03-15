"""Generowanie i zarządzanie podsumowaniem pacjenta w SQLite."""

import os
import litellm
from datetime import datetime, timedelta
from pathlib import Path

from tools.db import get_conn

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "claude-sonnet-4-6")
SUMMARY_MAX_AGE_DAYS = int(os.getenv("SUMMARY_MAX_AGE_DAYS", "7"))

PATIENT_FILES = ["pacjent.md", "wywiad.md", "analiza.md", "dieta.md", "tydzien.md"]


def load_patient_summary() -> str:
    """Wczytuje podsumowanie pacjenta z SQLite. Zwraca pusty string jeśli brak."""
    conn = get_conn()
    row = conn.execute("SELECT content FROM patient_summary WHERE id = 1").fetchone()
    conn.close()
    return row["content"] if row else ""


def refresh_patient_summary(trigger: str = "manual") -> str:
    """Generuje nowe podsumowanie pacjenta z plików .md i zapisuje w SQLite.

    Używa SUMMARY_MODEL (domyślnie sonnet) do generowania zwięzłego podsumowania ~500 tokenów.
    Zwraca wygenerowane podsumowanie.
    """
    parts = []
    for fname in PATIENT_FILES:
        path = DATA_DIR / fname
        if path.exists():
            parts.append(f"=== {fname} ===\n{path.read_text(encoding='utf-8')}")

    if not parts:
        return "Brak plików pacjenta do podsumowania."

    combined = "\n\n".join(parts)

    response = litellm.completion(
        model=SUMMARY_MODEL,
        messages=[{
            "role": "user",
            "content": (
                "Na podstawie poniższych plików medycznych stwórz zwięzłe podsumowanie "
                "kluczowych faktów medycznych pacjenta (maksymalnie 500 tokenów). "
                "Uwzględnij: dane demograficzne, główne schorzenia i diagnozy, aktualne leki, "
                "kluczowe wyniki badań z datami, trendy zdrowotne, zasady diety i ograniczenia. "
                "Pomiń szczegóły mało istotne. Pisz po polsku, zwięźle, w punktach.\n\n"
                f"{combined}"
            ),
        }],
    )

    summary = response.choices[0].message.content or ""

    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO patient_summary (id, content, updated_at, trigger) VALUES (1, ?, ?, ?)",
        (summary, datetime.now().isoformat(), trigger),
    )
    conn.commit()
    conn.close()

    return summary


def maybe_refresh_summary() -> None:
    """Odświeża podsumowanie przy starcie jeśli brak lub starsze niż SUMMARY_MAX_AGE_DAYS."""
    conn = get_conn()
    row = conn.execute("SELECT updated_at FROM patient_summary WHERE id = 1").fetchone()
    conn.close()

    if row is None:
        refresh_patient_summary(trigger="startup_initial")
        return

    updated = datetime.fromisoformat(row["updated_at"])
    if datetime.now() - updated > timedelta(days=SUMMARY_MAX_AGE_DAYS):
        refresh_patient_summary(trigger="startup_aged")
