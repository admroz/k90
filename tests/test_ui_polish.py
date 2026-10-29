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


def test_meals_newest_first_with_missing_times_last_and_stable_ties(temp_db, monkeypatch):
    from tools import diet
    monkeypatch.setattr(web_data, 'now_local', lambda: datetime(2026, 10, 29, 18))
    monkeypatch.setattr(diet, 'date_days_ago', lambda _: '2026-10-01')
    with get_conn() as conn:
        for day, time, desc in [('2026-10-28','23:00','old'), ('2026-10-29',None,'null'), ('2026-10-29','08:00','early'), ('2026-10-29','','empty'), ('2026-10-29','20:00','late1'), ('2026-10-29','20:00','late2')]:
            conn.execute('INSERT INTO posilki(data,czas,opis) VALUES (?,?,?)', (day,time,desc))
    expected = ['late2','late1','early','empty','null']
    assert [r['opis'] for r in web_data.meals_for_day()['meals']] == expected
    assert [r['opis'] for r in web_data.dashboard(7)['posilki']] == expected + ['old']
    assert [r['opis'] for r in web_data.read_table('posilki')['rows']] == expected + ['old']
    assert [r['opis'] for r in diet.get_recent_meals()] == expected + ['old']


@pytest.mark.parametrize('confirmed', [False, True])
def test_legacy_piece_edit_requires_explicit_current_panel_preview(web_client, confirmed):
    from tools import food_catalog as c
    login(web_client)
    p = c.propose(dict(label(), piece_size=90))
    if confirmed:
        p = c.confirm(p['id'], p['version'])
    with get_conn() as conn:
        conn.execute('UPDATE food_products SET owner=NULL WHERE id=?', (p['id'],))
    url = f"/api/catalog/{p['id']}"
    update = {'version':p['version'], 'product':{'piece_size':100}}
    rejected = web_client.put(url, json=update, headers=H)
    assert rejected.status_code == 409
    assert rejected.json()['detail'] == 'owner or version mismatch; preview required'
    # Showing a specific current version may claim ONLY unowned legacy records.
    preview = web_client.post(url+'/preview', json={'version':p['version']}, headers=H)
    assert preview.status_code == 200
    assert preview.json()['piece_size'] == 90 and preview.json()['version'] == p['version']
    revised = web_client.put(url, json=update, headers=H)
    assert revised.status_code == 200
    assert revised.json()['piece_size'] == 100 and revised.json()['status'] == 'draft'
    assert web_client.put(url, json=update, headers=H).status_code == 409
    assert web_client.post(url+'/confirm', json={'version':p['version']}, headers=H).status_code == 409
    with get_conn() as conn:
        assert conn.execute('SELECT owner FROM food_products WHERE id=?', (p['id'],)).fetchone()[0] == 'owner'
        assert conn.execute('SELECT count(*) FROM food_product_approvals WHERE product_id=? AND version=?', (p['id'],p['version']+1)).fetchone()[0] == 0


def test_panel_preview_does_not_claim_foreign_or_stale_versions(web_client):
    from tools import food_catalog as c
    login(web_client)
    p = c.propose(label(), owner='other-owner')
    url = f"/api/catalog/{p['id']}/preview"
    assert web_client.post(url, json={'version':1}, headers=H).status_code == 409
    with get_conn() as conn:
        conn.execute('UPDATE food_products SET owner=NULL WHERE id=?', (p['id'],))
    assert web_client.post(url, json={'version':2}, headers=H).status_code == 409
    assert web_client.post(url, json={'version':True}, headers=H).status_code == 409
    assert web_client.post(url, json={'version':1}).status_code == 403
    with get_conn() as conn:
        assert conn.execute('SELECT owner FROM food_products WHERE id=?', (p['id'],)).fetchone()[0] is None
