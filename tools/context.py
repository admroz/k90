"""Builds a compact operational context block from recent health data."""

from __future__ import annotations

from .db import get_conn
from .time_utils import date_days_ago

MEAL_DAYS = 3
ACTIVITY_DAYS = 3
WEIGHT_DAYS = 7
BP_DAYS = 7
SLEEP_DAYS = 3
RECOVERY_DAYS = 3


def _fmt_num(value, decimals: int = 1) -> str:
    if value is None:
        return "brak"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return str(value)


def _fmt_minutes(value) -> str:
    if value is None:
        return "brak"
    return f"{int(round(float(value)))} min"


def _section(title: str, items: list[str]) -> str | None:
    clean = [item for item in items if item]
    if not clean:
        return None
    return f"{title}: " + " | ".join(clean)


def build_operational_context() -> tuple[str, dict]:
    with get_conn() as conn:
        meals = conn.execute(
            """SELECT data, czas, opis, kalorie, bialko_g, weglowodany_g, tluszcze_g
               FROM posilki
               WHERE data >= ?
               ORDER BY data DESC, czas DESC
               LIMIT 6""",
            (date_days_ago(MEAL_DAYS),),
        ).fetchall()

        activities = conn.execute(
            """SELECT data, czas, typ, nazwa, czas_trwania_min, dystans_km, kalorie
               FROM aktywnosci
               WHERE data >= ?
               ORDER BY data DESC, czas DESC
               LIMIT 5""",
            (date_days_ago(ACTIVITY_DAYS),),
        ).fetchall()

        weights = conn.execute(
            """SELECT data, waga_kg
               FROM waga
               WHERE data >= ? AND waga_kg IS NOT NULL
               ORDER BY data DESC
               LIMIT 4""",
            (date_days_ago(WEIGHT_DAYS),),
        ).fetchall()

        blood_pressure = conn.execute(
            """SELECT data, czas, skurczowe, rozkurczowe, puls
               FROM cisnienie
               WHERE data >= ?
               ORDER BY data DESC, czas DESC
               LIMIT 4""",
            (date_days_ago(BP_DAYS),),
        ).fetchall()

        sleep = conn.execute(
            """SELECT data, total_sleep_min, sleep_score, spo2_avg
               FROM sen
               WHERE data >= ? AND total_sleep_min IS NOT NULL
               ORDER BY data DESC
               LIMIT 3""",
            (date_days_ago(SLEEP_DAYS),),
        ).fetchall()

        recovery = conn.execute(
            """SELECT m.data, m.rhr, m.avg_stres, m.avg_oddech,
                      h.hrv_noc, b.max_bateria, b.min_bateria
               FROM metryki_dzienne m
               LEFT JOIN hrv h ON h.data = m.data
               LEFT JOIN body_battery b ON b.data = m.data
               WHERE m.data >= ?
               ORDER BY m.data DESC
               LIMIT 3""",
            (date_days_ago(RECOVERY_DAYS),),
        ).fetchall()

    sections: list[str] = []
    stats = {
        "meals": len(meals),
        "activities": len(activities),
        "weights": len(weights),
        "blood_pressure": len(blood_pressure),
        "sleep": len(sleep),
        "recovery": len(recovery),
    }

    meal_items = []
    for row in meals:
        macros = []
        if row["bialko_g"] is not None:
            macros.append(f"B {_fmt_num(row['bialko_g'])} g")
        if row["weglowodany_g"] is not None:
            macros.append(f"W {_fmt_num(row['weglowodany_g'])} g")
        if row["tluszcze_g"] is not None:
            macros.append(f"T {_fmt_num(row['tluszcze_g'])} g")
        extras = []
        if row["kalorie"] is not None:
            extras.append(f"{int(round(row['kalorie']))} kcal")
        if macros:
            extras.append(", ".join(macros))
        suffix = f" ({'; '.join(extras)})" if extras else ""
        meal_items.append(f"{row['data']} {row['czas'] or '--:--'} {row['opis']}{suffix}")
    section = _section("Posiłki z ostatnich dni", meal_items)
    if section:
        sections.append(section)

    activity_items = []
    for row in activities:
        bits = [row["nazwa"] or row["typ"] or "aktywność"]
        details = []
        if row["czas_trwania_min"] is not None:
            details.append(_fmt_minutes(row["czas_trwania_min"]))
        if row["dystans_km"] is not None:
            details.append(f"{_fmt_num(row['dystans_km'], 2)} km")
        if row["kalorie"] is not None:
            details.append(f"{int(round(row['kalorie']))} kcal")
        suffix = f" ({', '.join(details)})" if details else ""
        activity_items.append(f"{row['data']} {row['czas'] or '--:--'} {' '.join(bits)}{suffix}")
    section = _section("Aktywności z ostatnich dni", activity_items)
    if section:
        sections.append(section)

    if weights:
        weight_items = [f"{row['data']}: {_fmt_num(row['waga_kg'])} kg" for row in weights[:3]]
        if len(weights) >= 2 and weights[0]["waga_kg"] is not None and weights[-1]["waga_kg"] is not None:
            delta = round(weights[0]["waga_kg"] - weights[-1]["waga_kg"], 1)
            weight_items.append(f"zmiana {WEIGHT_DAYS} dni: {delta:+.1f} kg")
        sections.append(_section("Waga", weight_items))

    bp_items = []
    for row in blood_pressure:
        bp = f"{row['skurczowe']}/{row['rozkurczowe']}"
        pulse = f", puls {row['puls']}" if row["puls"] is not None else ""
        bp_items.append(f"{row['data']} {row['czas'] or '--:--'} {bp}{pulse}")
    section = _section("Ciśnienie", bp_items)
    if section:
        sections.append(section)

    sleep_items = []
    for row in sleep:
        extras = []
        if row["sleep_score"] is not None:
            extras.append(f"score {int(round(row['sleep_score']))}")
        if row["spo2_avg"] is not None:
            extras.append(f"SpO2 {_fmt_num(row['spo2_avg'])}")
        suffix = f" ({', '.join(extras)})" if extras else ""
        sleep_items.append(f"{row['data']}: {_fmt_minutes(row['total_sleep_min'])}{suffix}")
    section = _section("Sen", sleep_items)
    if section:
        sections.append(section)

    recovery_items = []
    for row in recovery:
        details = []
        if row["hrv_noc"] is not None:
            details.append(f"HRV {_fmt_num(row['hrv_noc'])}")
        if row["rhr"] is not None:
            details.append(f"RHR {_fmt_num(row['rhr'])}")
        if row["avg_stres"] is not None:
            details.append(f"stres {_fmt_num(row['avg_stres'])}")
        if row["avg_oddech"] is not None:
            details.append(f"oddech {_fmt_num(row['avg_oddech'])}")
        if row["max_bateria"] is not None or row["min_bateria"] is not None:
            details.append(f"Body Battery {_fmt_num(row['min_bateria'])}-{_fmt_num(row['max_bateria'])}")
        recovery_items.append(f"{row['data']}: {', '.join(details) if details else 'brak danych'}")
    section = _section("Regeneracja i metryki", recovery_items)
    if section:
        sections.append(section)

    context = "\n".join(section for section in sections if section)
    stats["chars"] = len(context)
    stats["sections"] = len(sections)
    return context, stats
