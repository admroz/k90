from __future__ import annotations

from datetime import datetime
from pathlib import Path

import summary
from tools.db import get_conn


def test_is_summary_complete_detects_valid_and_invalid_summary():
    valid = "\n".join(
        [
            "Dane demograficzne: 48 lat, M.",
            "Główne rozpoznania: hipoglikemia reaktywna.",
            "Leki: Candepres 8 mg.",
            "Ważne wyniki z datami: glukoza 43 mg/dl (2026-03-10).",
            "Trendy zdrowotne: spadek masy ciała.",
            "Dieta i ograniczenia: low-IG.",
            "Otwarte kwestie: poprawa glikemii.",
        ]
    )
    invalid = "Dane demograficzne: tylko jedna linia"

    assert summary._is_summary_complete(valid, finish_reason="stop") is True
    assert summary._is_summary_complete(valid, finish_reason="length") is False
    assert summary._is_summary_complete(invalid, finish_reason="stop") is False


def test_refresh_patient_summary_falls_back_and_saves(monkeypatch, temp_db, tmp_path: Path):
    monkeypatch.setattr(summary, "DATA_DIR", tmp_path)
    monkeypatch.setattr(summary, "_load_patient_parts", lambda: (["=== pacjent.md ===\nPacjent testowy"], {"pacjent.md": "Pacjent testowy"}))
    monkeypatch.setattr(summary, "_generate_summary", lambda combined: ("", "length", 2))
    monkeypatch.setattr(summary, "now_local", lambda: datetime(2026, 3, 18, 16, 0, 0))

    result = summary.refresh_patient_summary(trigger="test")

    assert result.startswith("Dane demograficzne:")
    assert "Otwarte kwestie:" in result

    with get_conn() as conn:
        row = conn.execute("SELECT content, trigger, updated_at FROM patient_summary WHERE id = 1").fetchone()

    assert row["content"] == result
    assert row["trigger"] == "test"
    assert row["updated_at"] == "2026-03-18T16:00:00"
