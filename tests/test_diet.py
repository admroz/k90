from __future__ import annotations

import pytest

from tools.db import get_conn
from tools.diet import get_recent_meals, log_meal, update_meal


def test_log_meal_stores_required_macros(temp_db):
    result = log_meal(
        description="Kurczak z ryzem",
        calories=650,
        protein_g=45,
        carbs_g=70,
        fat_g=18,
    )

    assert result["status"] == "zapisano"

    meals = get_recent_meals(days=1)
    assert len(meals) == 1
    assert meals[0]["kalorie"] == 650
    assert meals[0]["bialko_g"] == 45
    assert meals[0]["weglowodany_g"] == 70
    assert meals[0]["tluszcze_g"] == 18


def test_update_meal_updates_existing_entry(temp_db):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO posilki (data, czas, opis, kalorie, bialko_g, weglowodany_g, tluszcze_g, zrodlo)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')""",
            ("2026-03-25", "13:00", "Stary obiad", 500, 20, 50, 15),
        )
        meal_id = cur.lastrowid
        conn.commit()

    result = update_meal(
        meal_id=meal_id,
        description="Nowy obiad",
        calories=720,
        protein_g=55,
        carbs_g=68,
        fat_g=26,
        date="2026-03-25",
        time="13:15",
    )

    assert result == {"id": meal_id, "status": "zaktualizowano", "data": "2026-03-25", "czas": "13:15"}

    meals = get_recent_meals(days=7)
    assert meals[0]["opis"] == "Nowy obiad"
    assert meals[0]["kalorie"] == 720
    assert meals[0]["bialko_g"] == 55
    assert meals[0]["weglowodany_g"] == 68
    assert meals[0]["tluszcze_g"] == 26


def test_update_meal_returns_not_found_for_missing_id(temp_db):
    result = update_meal(
        meal_id=999,
        description="Nie istnieje",
        calories=500,
        protein_g=30,
        carbs_g=40,
        fat_g=20,
    )

    assert result == {"status": "nie znaleziono", "id": 999}


def test_log_meal_requires_all_macros():
    with pytest.raises(TypeError):
        log_meal(description="Niepelny wpis", calories=500, protein_g=30, carbs_g=40)
