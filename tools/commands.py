"""Obsługa komend slash bez LLM."""

from __future__ import annotations

from summary import load_patient_summary, refresh_patient_summary
from .db import get_conn
from .garmin import get_sync_status, mark_summary_refreshed, sync_garmin_data, sync_has_changes
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
    return None


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
    sync_row = get_sync_status()

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
    if sync_row:
        lines.append(
            f"Sync danych: {sync_row['last_status'] or 'brak'}; sukces {sync_row['last_success_date'] or 'nigdy'}; "
            f"nowe {sync_row['last_inserted'] or 0}, zaktualizowane {sync_row['last_updated'] or 0}"
        )
    else:
        lines.append("Sync danych: brak historii")

    return "\n".join(lines)


def _update() -> str:
    result = sync_garmin_data(trigger="slash_update")
    if "error" in result:
        return f"/update: błąd synchronizacji\n{result['error']}"

    refresh_note = ""
    if sync_has_changes(result):
        refresh_patient_summary(trigger="slash_update")
        mark_summary_refreshed()
        refresh_note = "\nSummary odświeżone po zmianach w danych Garmin."
    else:
        refresh_note = "\nBrak nowych zmian z Garmin, summary bez zmian."

    datasets = []
    for name, stats in result.get("datasets", {}).items():
        datasets.append(
            f"{name}: pobrane {stats['fetched']}, nowe {stats['inserted']}, zaktualizowane {stats['updated']}, bez zmian {stats['unchanged']}"
        )
    body = "\n".join(datasets) if datasets else "Brak danych o datasetach."
    return f"/update: synchronizacja zakończona\n{body}{refresh_note}"


def _summary() -> str:
    summary = load_patient_summary().strip()
    if not summary:
        return "Summary: brak danych."
    return summary


def _help() -> str:
    return (
        "Dostepne komendy:\n"
        "/status — podsumowanie zdrowotne (waga, kcal, aktywnosc)\n"
        "/debug — statystyki uzycia i summary\n"
        "/update — synchronizacja Garmin bez LLM\n"
        "/summary — pokazuje aktualne patient summary\n"
        "/help — ta wiadomosc"
    )
