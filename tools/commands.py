"""Obsługa komend slash (/status, /debug, /help) — bez LLM."""

from datetime import datetime
from .db import get_conn


def handle_command(text: str) -> str | None:
    """Jeśli tekst jest komendą slash, zwraca gotową odpowiedź. W przeciwnym razie None."""
    cmd = text.strip().lower().split()[0] if text.strip() else ""
    if cmd == "/status":
        return _status()
    if cmd == "/debug":
        return _debug()
    if cmd == "/help":
        return _help()
    return None


def _status() -> str:
    conn = get_conn()

    # Ostatnia waga
    waga = conn.execute(
        "SELECT data, waga_kg FROM waga ORDER BY data DESC LIMIT 1"
    ).fetchone()

    # Trend wagi (7 dni)
    wagi_7d = conn.execute(
        "SELECT waga_kg FROM waga ORDER BY data DESC LIMIT 7"
    ).fetchall()

    # Kcal z ostatnich 5 dni
    kcal = conn.execute(
        """SELECT data, SUM(kalorie) as kcal FROM posilki
           WHERE data >= date('now', '-5 days') AND kalorie IS NOT NULL
           GROUP BY data ORDER BY data DESC"""
    ).fetchall()

    # Ostatnia aktywność
    aktywnosc = conn.execute(
        "SELECT data, typ, nazwa, czas_trwania_min FROM aktywnosci ORDER BY data DESC, czas DESC LIMIT 1"
    ).fetchone()

    conn.close()

    lines = [f"Status na {datetime.now().strftime('%d.%m.%Y %H:%M')}"]
    lines.append("")

    if waga:
        trend = ""
        if len(wagi_7d) >= 2:
            delta = round(wagi_7d[0]["waga_kg"] - wagi_7d[-1]["waga_kg"], 1)
            trend = f" ({'+' if delta > 0 else ''}{delta} kg / 7 dni)"
        lines.append(f"Waga: {waga['waga_kg']} kg ({waga['data']}){trend}")
    else:
        lines.append("Waga: brak danych")

    if kcal:
        vals = [r["kcal"] for r in kcal if r["kcal"]]
        avg = round(sum(vals) / len(vals)) if vals else 0
        kcal_str = ", ".join(f"{r['data'][-5:]}: {int(r['kcal'])} kcal" for r in kcal)
        lines.append(f"Kcal (5 dni): {kcal_str}")
        lines.append(f"Srednia: {avg} kcal/dzien")
    else:
        lines.append("Kcal: brak danych z ostatnich 5 dni")

    if aktywnosc:
        lines.append(f"Ostatnia aktywnosc: {aktywnosc['nazwa']} ({aktywnosc['typ']}, {int(aktywnosc['czas_trwania_min'])} min) — {aktywnosc['data']}")
    else:
        lines.append("Aktywnosc: brak danych")

    return "\n".join(lines)


def _debug() -> str:
    conn = get_conn()

    # Statystyki użycia tokenów
    today = datetime.now().strftime("%Y-%m-%d")
    usage_today = conn.execute(
        """SELECT COUNT(*) as req, SUM(prompt_tokens) as pt, SUM(completion_tokens) as ct
           FROM usage_stats WHERE date(timestamp) = ?""",
        (today,)
    ).fetchone()
    usage_total = conn.execute(
        """SELECT COUNT(*) as req, SUM(prompt_tokens) as pt, SUM(completion_tokens) as ct
           FROM usage_stats"""
    ).fetchone()

    # Liczba konwersacji
    conv_count = conn.execute(
        "SELECT COUNT(*) FROM conversations"
    ).fetchone()[0]

    conn.close()

    lines = [f"Debug na {datetime.now().strftime('%d.%m.%Y %H:%M')}"]
    lines.append("")

    def fmt_usage(row, label):
        if row and row["req"]:
            pt = row["pt"] or 0
            ct = row["ct"] or 0
            # Haiku pricing: $0.80/1M input, $4.00/1M output (claude-haiku-4-5)
            cost = (pt * 0.0000008) + (ct * 0.000004)
            return f"{label}: {row['req']} zapytan, {pt} in / {ct} out tokenow (~${cost:.4f})"
        return f"{label}: brak danych"

    lines.append(fmt_usage(usage_today, "Dzis"))
    lines.append(fmt_usage(usage_total, "Lacznie"))
    lines.append(f"Historia konwersacji: {conv_count} wiadomosci")

    return "\n".join(lines)


def _help() -> str:
    return (
        "Dostepne komendy:\n"
        "/status — podsumowanie zdrowotne (waga, kcal, aktywnosc)\n"
        "/debug — statystyki uzycia (tokeny, zapytania, koszty)\n"
        "/help — ta wiadomosc"
    )
