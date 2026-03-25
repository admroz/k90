"""Narzędzia do logowania i pobierania danych o posiłkach."""

from .db import checkpoint_wal, get_conn, rows_to_list
from .time_utils import date_days_ago, now_local


def log_meal(
    description: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    notes: str = None,
    date: str = None,
    time: str = None,
) -> dict:
    """Zapisuje informację o spożytym posiłku do bazy danych.

    Args:
        description: Opis posiłku (np. 'owsianka z jagodami i orzechami').
        calories: Szacowana liczba kalorii.
        protein_g: Białko w gramach.
        carbs_g: Węglowodany w gramach.
        fat_g: Tłuszcze w gramach.
        notes: Dodatkowe uwagi (opcjonalne).

    Returns:
        Słownik z id zapisanego posiłku i potwierdzeniem.
    """
    now = now_local()
    meal_date = date or now.strftime("%Y-%m-%d")
    meal_time = time or now.strftime("%H:%M")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO posilki (data, czas, opis, kalorie, bialko_g, weglowodany_g, tluszcze_g, zrodlo)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')""",
            (meal_date, meal_time, description, calories, protein_g, carbs_g, fat_g)
        )
        meal_id = cur.lastrowid
        conn.commit()
        checkpoint_wal(conn)
    return {"id": meal_id, "status": "zapisano", "data": meal_date, "czas": meal_time}


def update_meal(
    meal_id: int,
    description: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    notes: str = None,
    date: str = None,
    time: str = None,
) -> dict:
    """Aktualizuje istniejący wpis posiłku w bazie danych."""
    with get_conn() as conn:
        existing = conn.execute(
            """SELECT id, data, czas
               FROM posilki
               WHERE id = ?""",
            (meal_id,),
        ).fetchone()
        if existing is None:
            return {"status": "nie znaleziono", "id": meal_id}

        meal_date = date or existing["data"]
        meal_time = time or existing["czas"] or now_local().strftime("%H:%M")
        conn.execute(
            """UPDATE posilki
               SET data = ?, czas = ?, opis = ?, kalorie = ?, bialko_g = ?, weglowodany_g = ?, tluszcze_g = ?
               WHERE id = ?""",
            (meal_date, meal_time, description, calories, protein_g, carbs_g, fat_g, meal_id),
        )
        conn.commit()
        checkpoint_wal(conn)
    return {"id": meal_id, "status": "zaktualizowano", "data": meal_date, "czas": meal_time}


def delete_meal(meal_id: int) -> dict:
    """Usuwa posiłek z bazy danych na podstawie jego ID.

    Args:
        meal_id: ID posiłku do usunięcia (widoczne w get_recent_meals).

    Returns:
        Słownik z potwierdzeniem usunięcia lub błędem jeśli nie znaleziono.
    """
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM posilki WHERE id = ?", (meal_id,))
        conn.commit()
        checkpoint_wal(conn)
    if cur.rowcount:
        return {"status": "usunięto", "id": meal_id}
    return {"status": "nie znaleziono", "id": meal_id}


def get_recent_meals(days: int = 3) -> list[dict]:
    """Pobiera ostatnio zalogowane posiłki.

    Args:
        days: Liczba dni wstecz (domyślnie 3).

    Returns:
        Lista posiłków: data, czas, opis, kalorie, makroskładniki.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, data, czas, opis, kalorie, bialko_g, weglowodany_g, tluszcze_g
               FROM posilki
               WHERE data >= ?
               ORDER BY data DESC, czas DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)
