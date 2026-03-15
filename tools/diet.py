"""Narzędzia do logowania i pobierania danych o posiłkach."""

from datetime import date, datetime
from .db import get_conn, rows_to_list


def log_meal(
    description: str,
    calories: float = None,
    protein_g: float = None,
    carbs_g: float = None,
    fat_g: float = None,
    notes: str = None,
    date: str = None,
    time: str = None,
) -> dict:
    """Zapisuje informację o spożytym posiłku do bazy danych.

    Args:
        description: Opis posiłku (np. 'owsianka z jagodami i orzechami').
        calories: Szacowana liczba kalorii (opcjonalne).
        protein_g: Białko w gramach (opcjonalne).
        carbs_g: Węglowodany w gramach (opcjonalne).
        fat_g: Tłuszcze w gramach (opcjonalne).
        notes: Dodatkowe uwagi (opcjonalne).

    Returns:
        Słownik z id zapisanego posiłku i potwierdzeniem.
    """
    now = datetime.now()
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
    return {"id": meal_id, "status": "zapisano", "data": meal_date, "czas": meal_time}


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
               WHERE data >= date('now', ? || ' days')
               ORDER BY data DESC, czas DESC""",
            (f"-{days}",)
        ).fetchall()
    return rows_to_list(rows)
