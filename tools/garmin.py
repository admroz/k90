"""Narzędzie do synchronizacji danych z Garmin Connect."""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent


def sync_garmin_data() -> dict:
    """Pobiera nowe dane z Garmin Connect i aktualizuje bazę danych.

    Uruchamia fetch_garmin.py (tryb przyrostowy: ostatnie 7 dni + bufor),
    a następnie synchronizuje CSV do SQLite.

    Returns:
        Słownik z wynikiem synchronizacji i ewentualnymi błędami.
    """
    results = {}

    # Krok 1: pobierz dane z Garmina
    try:
        proc = subprocess.run(
            [sys.executable, "fetch_garmin.py"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        results["garmin"] = proc.stdout.strip() or "OK"
        if proc.returncode != 0:
            results["garmin_error"] = proc.stderr.strip()[-500:]
            return results
    except subprocess.TimeoutExpired:
        return {"error": "Timeout — Garmin nie odpowiedział w ciągu 2 minut"}
    except Exception as e:
        return {"error": str(e)}

    # Krok 2: zaktualizuj SQLite z nowych CSVków
    try:
        proc = subprocess.run(
            [sys.executable, "migrate_csv_to_sqlite.py"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        results["sqlite"] = proc.stdout.strip().split("\n")[-1] if proc.stdout else "OK"
        if proc.returncode != 0:
            results["sqlite_error"] = proc.stderr.strip()
    except Exception as e:
        results["sqlite_error"] = str(e)

    return results
