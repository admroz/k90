"""Generowanie i zarządzanie podsumowaniem pacjenta w SQLite."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import litellm

from tools.db import get_conn
from tools.time_utils import APP_TIMEZONE, now_local

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "gpt-5.4")
SUMMARY_MAX_AGE_DAYS = int(os.getenv("SUMMARY_MAX_AGE_DAYS", "7"))
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "600"))
PATIENT_FILES = ["pacjent.md", "wywiad.md", "analiza.md", "dieta.md", "tydzien.md"]
SUMMARY_LABELS = [
    "Dane demograficzne:",
    "Główne rozpoznania:",
    "Leki:",
    "Ważne wyniki z datami:",
    "Trendy zdrowotne:",
    "Dieta i ograniczenia:",
    "Otwarte kwestie:",
]


def load_patient_summary() -> str:
    """Wczytuje podsumowanie pacjenta z SQLite. Zwraca pusty string jeśli brak."""
    conn = get_conn()
    row = conn.execute("SELECT content FROM patient_summary WHERE id = 1").fetchone()
    conn.close()
    return row["content"] if row else ""


def _collapse_text(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text.replace("#", " ")).strip(" -:\n")
    if len(clean) <= limit:
        return clean
    trimmed = clean[:limit].rsplit(" ", 1)[0].rstrip(",;:-")
    return trimmed + "..."


def _load_patient_parts() -> tuple[list[str], dict[str, str]]:
    parts: list[str] = []
    contents: dict[str, str] = {}
    for fname in PATIENT_FILES:
        path = DATA_DIR / fname
        if path.exists():
            text = path.read_text(encoding="utf-8")
            contents[fname] = text
            parts.append(f"=== {fname} ===\n{text}")
    return parts, contents


def _build_summary_prompt(combined: str, compact: bool = False) -> str:
    style = (
        "Każda linia ma mieć maksymalnie około 160 znaków. Pisz bardzo skrótowo, bez markdownu, bez wstępów, bez zakończeń."
        if compact
        else "Pisz zwięźle, po polsku, bez markdownu, bez wstępów, bez zakończeń."
    )
    labels = "\n".join(SUMMARY_LABELS)
    return (
        "Na podstawie poniższych plików medycznych stwórz krótki rekord faktów medycznych pacjenta. "
        "Zwróć dokładnie 7 linii i nic więcej. Każda linia ma zaczynać się dokładnie od jednej z etykiet:\n"
        f"{labels}\n\n"
        "Uwzględnij tylko najważniejsze fakty: wiek/płeć/wzrost/waga, główne schorzenia, leki i suplementy, "
        "najważniejsze wyniki z datami, aktualne trendy, zasady diety oraz otwarte kwestie. "
        "Priorytety treści: w linii 'Główne rozpoznania' odróżnij problemy stabilne od obecnego głównego tematu zdrowotnego; "
        "w linii 'Leki' wypisz wszystkie aktualne leki i suplementy z dawkami, niczego nie pomijaj; "
        "w linii 'Trendy zdrowotne' uwzględnij aktywność fizyczną, trend masy ciała oraz najważniejsze bieżące zmiany stylu życia; "
        "w linii 'Otwarte kwestie' nazwij aktualny główny cel lub problem, nad którym pacjent teraz pracuje. "
        "Zasady krytyczne: dane szybkozmienne, takie jak masa ciała, opisuj jako trend albo zawsze z datą; "
        "jeśli interwencja jest świeża, napisz to wprost jako nową lub ostatnią zmianę; "
        "nie dopisuj relacji przyczynowych, poprawy ani pogorszenia, jeśli źródła nie mówią tego wprost; "
        "nie przedstawiaj historycznej wartości jako obecnego stanu bez daty. "
        f"{style}\n\n{combined}"
    )


def _is_summary_complete(summary: str, finish_reason: str | None) -> bool:
    if not summary.strip():
        return False
    if finish_reason == "length":
        return False
    lines = [line.strip() for line in summary.splitlines() if line.strip()]
    if len(lines) != len(SUMMARY_LABELS):
        return False
    return all(line.startswith(label) for line, label in zip(lines, SUMMARY_LABELS))


def _fallback_summary(contents: dict[str, str]) -> str:
    pacjent = _collapse_text(contents.get("pacjent.md", "brak danych"), 200)
    wywiad = _collapse_text(contents.get("wywiad.md", "brak danych"), 200)
    analiza = _collapse_text(contents.get("analiza.md", "brak danych"), 200)
    dieta = _collapse_text((contents.get("dieta.md", "") + " " + contents.get("tydzien.md", "")).strip() or "brak danych", 200)
    fallback_lines = [
        f"Dane demograficzne: {pacjent}",
        f"Główne rozpoznania: {wywiad}",
        f"Leki: {pacjent}",
        f"Ważne wyniki z datami: {analiza}",
        f"Trendy zdrowotne: {analiza}",
        f"Dieta i ograniczenia: {dieta}",
        "Otwarte kwestie: Jeśli potrzebne są szczegóły, sprawdź źródłowe pliki pacjenta.",
    ]
    return "\n".join(fallback_lines)


def _generate_summary(combined: str) -> tuple[str, str | None, int]:
    last_finish_reason = None
    for attempt, compact in enumerate((False, True), start=1):
        response = litellm.completion(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": _build_summary_prompt(combined, compact=compact)}],
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        summary = (choice.message.content or "").strip()
        log.info(
            "summary.attempt model=%s attempt=%d finish_reason=%s chars=%d",
            SUMMARY_MODEL,
            attempt,
            finish_reason,
            len(summary),
        )
        if _is_summary_complete(summary, finish_reason):
            return summary, finish_reason, attempt
        last_finish_reason = finish_reason
    return "", last_finish_reason, 2


def refresh_patient_summary(trigger: str = "manual") -> str:
    """Generuje nowe podsumowanie pacjenta z plików .md i zapisuje w SQLite."""
    parts, contents = _load_patient_parts()
    if not parts:
        return "Brak plików pacjenta do podsumowania."

    combined = "\n\n".join(parts)
    log.info("summary.refresh trigger=%s input_chars=%d files=%d", trigger, len(combined), len(parts))

    summary, finish_reason, attempts = _generate_summary(combined)
    if not summary:
        log.warning("summary.fallback trigger=%s finish_reason=%s", trigger, finish_reason)
        summary = _fallback_summary(contents)

    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO patient_summary (id, content, updated_at, trigger) VALUES (1, ?, ?, ?)",
        (summary, now_local().isoformat(), trigger),
    )
    conn.commit()
    conn.close()

    log.info(
        "summary.saved trigger=%s chars=%d attempts=%d",
        trigger,
        len(summary),
        attempts,
    )
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
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=now_local().tzinfo)
    if now_local() - updated > timedelta(days=SUMMARY_MAX_AGE_DAYS):
        refresh_patient_summary(trigger="startup_aged")
