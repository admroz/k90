"""Owner UI scope: synthetic calendar-day energy and consistent meal ordering."""
from datetime import date, datetime
import pytest
import web_data
from tools.db import get_conn
from test_web import web_client, login
from test_food_catalog import label

H = {'X-K90-Request': '1'}


def test_today_resting_uses_previous_seven_calendar_days_available_only(temp_db, monkeypatch):
    monkeypatch.setattr(web_data, 'now_local', lambda: datetime(2026, 10, 29, 18))
    with get_conn() as conn:
        for day, value in [('2026-10-21', 9000), ('2026-10-22', 1850), ('2026-10-24', None), ('2026-10-28', 2050), ('2026-10-29', 777)]:
            conn.execute('INSERT INTO kalorie_dzienne VALUES (?,?,100,NULL,CURRENT_TIMESTAMP)', (day, value))
    energy = web_data.meals_for_day()['energy']
    assert energy['resting_kcal'] == 2000  # 1950, half up to the nearest 100
    assert energy['resting_estimated'] is True
    assert energy['burned_kcal'] == 2100
    past = web_data.meals_for_day(date(2026, 10, 28))['energy']
    assert past['resting_kcal'] == 2050 and past['resting_estimated'] is False


@pytest.mark.parametrize('measurements,expected', [([], None), ([None], None), ([0], 0), ([1849, 1850], 1800)])
def test_today_missing_is_not_zero_and_estimate_does_not_need_today_row(temp_db, monkeypatch, measurements, expected):
    monkeypatch.setattr(web_data, 'now_local', lambda: datetime(2026, 10, 29, 18))
    with get_conn() as conn:
        for i, value in enumerate(measurements):
            conn.execute('INSERT INTO kalorie_dzienne VALUES (?,?,NULL,NULL,CURRENT_TIMESTAMP)', (f'2026-10-{28-i}', value))
    energy = web_data.meals_for_day()['energy']
    assert energy['resting_kcal'] == expected
    assert energy['resting_estimated'] is (expected is not None)
    assert energy['burned_kcal'] is None
