"""Narzędzia do pobierania danych zdrowotnych z bazy SQLite."""

from .db import get_conn, rows_to_list
from .time_utils import date_days_ago


def get_blood_pressure(days: int = 30) -> list[dict]:
    """Pobiera pomiary ciśnienia krwi z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 30).

    Returns:
        Lista pomiarów: data, czas, skurczowe, rozkurczowe, puls, kategoria.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT data, czas, skurczowe, rozkurczowe, puls, kategoria
               FROM cisnienie
               WHERE data >= ?
               ORDER BY data DESC, czas DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)


def get_weight_trend(days: int = 90) -> list[dict]:
    """Pobiera historię wagi z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 90).

    Returns:
        Lista rekordów: data, waga_kg, bmi.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT data, waga_kg, bmi
               FROM waga
               WHERE data >= ?
               ORDER BY data DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)


def get_sleep_stats(days: int = 14) -> list[dict]:
    """Pobiera dane dotyczące snu z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 14).

    Returns:
        Lista rekordów snu: data, łączny czas snu, fazy, sleep score, SpO2.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT data, total_sleep_min, deep_min, light_min, rem_min,
                      awake_min, sleep_score, spo2_avg
               FROM sen
               WHERE data >= ?
                 AND total_sleep_min IS NOT NULL
               ORDER BY data DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)


def get_activities(days: int = 14, activity_type: str = None) -> list[dict]:
    """Pobiera aktywności fizyczne z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 14).
        activity_type: Opcjonalny filtr typu aktywności (np. 'cycling', 'hiking').

    Returns:
        Lista aktywności: data, typ, nazwa, czas trwania, dystans, kalorie, tętno.
    """
    with get_conn() as conn:
        if activity_type:
            rows = conn.execute(
                """SELECT data, czas, typ, nazwa, czas_trwania_min,
                          dystans_km, kalorie, sr_tetno, max_tetno, kroki
                   FROM aktywnosci
                   WHERE data >= ? AND typ = ?
                   ORDER BY data DESC, czas DESC""",
                (date_days_ago(days), activity_type)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT data, czas, typ, nazwa, czas_trwania_min,
                          dystans_km, kalorie, sr_tetno, max_tetno, kroki
                   FROM aktywnosci
                   WHERE data >= ?
                   ORDER BY data DESC, czas DESC""",
                (date_days_ago(days),)
            ).fetchall()
    return rows_to_list(rows)


def get_hrv(days: int = 14) -> list[dict]:
    """Pobiera dane HRV (zmienność rytmu serca) z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 14).

    Returns:
        Lista rekordów HRV: data, hrv_noc, hrv_5min_max, status, baseline.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT data, hrv_noc, hrv_5min_max, hrv_tyg_avg,
                      hrv_status, baseline_low, baseline_high
               FROM hrv
               WHERE data >= ?
                 AND hrv_noc IS NOT NULL
               ORDER BY data DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)


def get_body_battery(days: int = 7) -> list[dict]:
    """Pobiera dane Body Battery z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 7).

    Returns:
        Lista rekordów: data, naładowanie, zużycie, max, min baterii.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT data, naladowanie, zuzycie, max_bateria, min_bateria
               FROM body_battery
               WHERE data >= ?
               ORDER BY data DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)


def get_daily_metrics(days: int = 14) -> list[dict]:
    """Pobiera dzienne metryki zdrowotne z ostatnich N dni.

    Args:
        days: Liczba dni wstecz (domyślnie 14).

    Returns:
        Lista rekordów: data, RHR, stres, oddech.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT data, rhr, avg_stres, max_stres, avg_oddech
               FROM metryki_dzienne
               WHERE data >= ?
                 AND rhr IS NOT NULL
               ORDER BY data DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)
