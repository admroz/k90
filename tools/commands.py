"""Obsługa komend slash bez LLM."""

from __future__ import annotations

from summary import load_patient_summary, refresh_patient_summary
from .db import create_db_backup, get_conn
from .garmin import (
    get_sync_status as get_garmin_sync_status,
    mark_summary_refreshed as mark_garmin_summary_refreshed,
    sync_garmin_data,
    sync_has_changes as garmin_sync_has_changes,
)
from .libre import (
    get_sync_status as get_libre_sync_status,
    sync_libre_data,
    sync_has_changes as libre_sync_has_changes,
)
from .time_utils import date_days_ago, now_local


def handle_command(text: str) -> str | None:
    """Jeśli tekst jest komendą slash, zwraca gotową odpowiedź. W przeciwnym razie None."""
    cmd = text.strip().lower().split()[0] if text.strip() else ""
    if cmd == "/status":
        return _status()
    if cmd == "/debug":
        return _debug()
    if cmd == "/help":
        return _help()
    if cmd == "/update":
        return _update()
    if cmd == "/summary":
        return _summary()
    if cmd == "/backup":
        return _backup()
    return None


def _format_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size_bytes)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if value < 1024 or candidate == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def _status() -> str:
    conn = get_conn()
    waga = conn.execute("SELECT data, waga_kg FROM waga ORDER BY data DESC LIMIT 1").fetchone()
    wagi_7d = conn.execute("SELECT waga_kg FROM waga ORDER BY data DESC LIMIT 7").fetchall()
    kcal = conn.execute(
        """SELECT data, SUM(kalorie) as kcal FROM posilki
           WHERE data >= ? AND kalorie IS NOT NULL
           GROUP BY data ORDER BY data DESC""",
        (date_days_ago(5),),
    ).fetchall()
    aktywnosc = conn.execute(
        "SELECT data, typ, nazwa, czas_trwania_min FROM aktywnosci ORDER BY data DESC, czas DESC LIMIT 1"
    ).fetchone()
    glucose = conn.execute(
        """SELECT data, czas, glukoza_mg_dl
           FROM glukoza_libre
           ORDER BY timestamp DESC,
                    CASE source_kind WHEN 'latest' THEN 0 ELSE 1 END
           LIMIT 1"""
    ).fetchone()
    conn.close()

    lines = [f"Status na {now_local().strftime('%d.%m.%Y %H:%M')}", ""]

    if waga:
        trend = ""
        if len(wagi_7d) >= 2:
            delta = round(wagi_7d[0]["waga_kg"] - wagi_7d[-1]["waga_kg"], 1)
            trend = f" ({'+' if delta > 0 else ''}{delta} kg / 7 dni)"
        lines.append(f"Waga: {waga['waga_kg']} kg ({waga['data']}){trend}")
    else:
        lines.append("Waga: brak danych")

    if kcal:
        vals = [row["kcal"] for row in kcal if row["kcal"]]
        avg = round(sum(vals) / len(vals)) if vals else 0
        kcal_str = ", ".join(f"{row['data'][-5:]}: {int(row['kcal'])} kcal" for row in kcal)
        lines.append(f"Kcal (5 dni): {kcal_str}")
        lines.append(f"Srednia: {avg} kcal/dzien")
    else:
        lines.append("Kcal: brak danych z ostatnich 5 dni")

    if aktywnosc:
        lines.append(
            f"Ostatnia aktywnosc: {aktywnosc['nazwa']} ({aktywnosc['typ']}, {int(aktywnosc['czas_trwania_min'])} min) — {aktywnosc['data']}"
        )
    else:
        lines.append("Aktywnosc: brak danych")

    if glucose:
        lines.append(f"Glukoza Libre: {int(round(glucose['glukoza_mg_dl']))} mg/dL ({glucose['data']} {glucose['czas']})")
    else:
        lines.append("Glukoza Libre: brak danych")

    return "\n".join(lines)


def _debug() -> str:
    conn = get_conn()
    today = now_local().strftime("%Y-%m-%d")
    usage_today = conn.execute(
        """SELECT COUNT(*) as req, SUM(prompt_tokens) as pt, SUM(completion_tokens) as ct
           FROM usage_stats WHERE date(timestamp) = ?""",
        (today,),
    ).fetchone()
    usage_total = conn.execute(
        """SELECT COUNT(*) as req, SUM(prompt_tokens) as pt, SUM(completion_tokens) as ct
           FROM usage_stats"""
    ).fetchone()
    conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    summary_row = conn.execute(
        "SELECT updated_at, length(content) AS content_len FROM patient_summary WHERE id = 1"
    ).fetchone()
    conn.close()
    sync_rows = [
        ("Garmin", get_garmin_sync_status()),
        ("Libre", get_libre_sync_status()),
    ]

    lines = [f"Debug na {now_local().strftime('%d.%m.%Y %H:%M')}", ""]

    def fmt_usage(row, label):
        if row and row["req"]:
            pt = row["pt"] or 0
            ct = row["ct"] or 0
            return f"{label}: {row['req']} zapytan, {pt} in / {ct} out tokenow"
        return f"{label}: brak danych"

    lines.append(fmt_usage(usage_today, "Dzis"))
    lines.append(fmt_usage(usage_total, "Lacznie"))
    lines.append(f"Historia konwersacji: {conv_count} wiadomosci")
    if summary_row:
        lines.append(f"Summary: {summary_row['updated_at']} ({summary_row['content_len']} znakow)")
    else:
        lines.append("Summary: brak")

    for label, sync_row in sync_rows:
        if sync_row:
            lines.append(
                f"Sync {label}: {sync_row['last_status'] or 'brak'}; sukces {sync_row['last_success_date'] or 'nigdy'}; "
                f"nowe {sync_row['last_inserted'] or 0}, zaktualizowane {sync_row['last_updated'] or 0}"
            )
        else:
            lines.append(f"Sync {label}: brak historii")

    return "\n".join(lines)


def _update() -> str:
    sources = [
        ("Garmin", sync_garmin_data(trigger="slash_update"), garmin_sync_has_changes, mark_garmin_summary_refreshed),
        ("Libre", sync_libre_data(trigger="slash_update"), libre_sync_has_changes, None),
    ]

    changed_sources = []
    summary_sources = []
    body_lines = []
    errors = []

    for label, result, has_changes_fn, mark_fn in sources:
        if "error" in result:
            errors.append(f"{label}: {result['error']}")
            body_lines.append(f"{label}: błąd synchronizacji — {result['error']}")
            continue

        if has_changes_fn(result):
            changed_sources.append(label)
            if label == "Garmin":
                summary_sources.append((label, mark_fn))

        datasets = result.get("datasets", {})
        if not datasets:
            body_lines.append(f"{label}: brak danych o datasetach.")
            continue
        for name, stats in datasets.items():
            body_lines.append(
                f"{label} / {name}: pobrane {stats['fetched']}, nowe {stats['inserted']}, zaktualizowane {stats['updated']}, bez zmian {stats['unchanged']}"
            )

    if summary_sources:
        refresh_patient_summary(trigger="slash_update")
        for _, mark_fn in summary_sources:
            mark_fn()
        labels = ", ".join(label for label, _ in summary_sources)
        refresh_note = f"\nSummary odświeżone po zmianach w danych: {labels}."
    else:
        refresh_note = "\nSummary bez zmian."

    header = "/update: synchronizacja zakończona"
    if errors:
        header = "/update: synchronizacja zakończona z błędami"
    body = "\n".join(body_lines) if body_lines else "Brak danych o datasetach."
    return f"{header}\n{body}{refresh_note}"


def _summary() -> str:
    summary = load_patient_summary().strip()
    if not summary:
        return "Summary: brak danych."
    return summary


def _backup() -> str:
    try:
        backup = create_db_backup()
    except Exception as exc:
        return f"/backup: błąd tworzenia backupu — {exc}"

    lines = ["/backup: snapshot zapisany"]
    lines.append(f"Plik: {backup['filename']}")
    lines.append(f"Katalog: {backup['backup_dir']}")
    lines.append(f"Czas: {backup['created_at']} ({backup['timezone']})")
    lines.append(f"Rozmiar: {_format_size(int(backup['size_bytes']))}")
    lines.append(f"Retencja: {backup['retention_days']} dni")
    if backup['deleted_old']:
        lines.append(f"Usuniete stare backupy: {backup['deleted_old']}")
    return "\n".join(lines)


def _help() -> str:
    return (
        "Dostepne komendy:\n"
        "/status — podsumowanie zdrowotne (waga, kcal, aktywnosc, glukoza)\n"
        "/debug — statystyki uzycia i status syncu\n"
        "/update — synchronizacja Garmin i Libre bez LLM\n"
        "/summary — pokazuje aktualne patient summary\n"
        "/backup — tworzy snapshot SQLite do katalogu backupow\n"
        "/help — ta wiadomosc"
    )
