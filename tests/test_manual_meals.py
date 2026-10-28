"""Whole-meal manual mutations on real SQLite and authenticated HTTP."""
import json
import pytest
from test_web import web_client, login
from tools.db import get_conn
from tools.diet import log_meal, update_meal

HEAD = {'X-K90-Request': '1'}

def seed():
    return log_meal('Synthetic <img src=x onerror=alert(1)>', 100, 2, 20, 1, date='2026-01-01', time='08:00')['id']

def payload(**kw):
    return dict(description='Synthetic corrected', calories=0, protein_g=None, carbs_g=10.5, fat_g=0,
                quantity=125.5, unit='g', date='2026-01-02', time='09:45', expected_revision=1,
                request_id='edit-1', **kw)

def test_edit_move_delete_and_replay(web_client):
    mid=seed(); login(web_client)
    with get_conn() as c:
        c.execute('INSERT INTO meal_ingredients VALUES (?,?)',(mid,'{"original":true}'))
    body=payload()
    r=web_client.put(f'/api/meals/{mid}',json=body,headers=HEAD)
    assert r.status_code==200, r.text
    assert r.json()['revision']==2
    assert web_client.get('/api/meals?date=2026-01-01').json()['totals']['kalorie']==0
    new=web_client.get('/api/meals?date=2026-01-02').json()
    assert new['meals'][0]['quantity']==125.5 and new['meals'][0]['bialko_g'] is None
    assert new['totals']['kalorie']==0
    assert web_client.put(f'/api/meals/{mid}',json=body,headers=HEAD).json()['replayed']
    stale=dict(body,request_id='stale')
    assert web_client.put(f'/api/meals/{mid}',json=stale,headers=HEAD).status_code==409
    assert not update_meal(mid,'stale chat',50,1,1,1,expected_revision=1)['success']
    d={'expected_revision':2,'request_id':'delete-1'}
    assert web_client.request('DELETE',f'/api/meals/{mid}',json=d,headers=HEAD).status_code==200
    assert web_client.request('DELETE',f'/api/meals/{mid}',json=d,headers=HEAD).json()['replayed']
    assert web_client.get('/api/meals?date=2026-01-02').json()['meals']==[]
    assert web_client.put(f'/api/meals/{mid}',json=dict(body,request_id='missing'),headers=HEAD).status_code==404
    with get_conn() as c:
        changes=c.execute('SELECT * FROM meal_changes ORDER BY rowid').fetchall()
        assert len(changes)==2
        assert json.loads(changes[0]['before_json'])['revision']==1
        assert json.loads(changes[1]['before_json'])['revision']==2
        assert changes[1]['after_json'] is None and changes[1]['revision']==3
        assert c.execute('SELECT snapshot FROM meal_ingredients').fetchone()[0]=='{"original":true}'

@pytest.mark.parametrize('field,value', [('calories',True),('calories',-1),('calories','1,5'),('calories','NaN'),('quantity',-1),('unit','kg'),('date','2026-02-30'),('date',''),('time','25:00'),('time',''),('expected_revision',True)])
def test_invalid_preserves_state(web_client,field,value):
    mid=seed(); login(web_client); body=payload(); body[field]=value
    assert web_client.put(f'/api/meals/{mid}',json=body,headers=HEAD).status_code==422
    with get_conn() as c:
        assert c.execute('SELECT revision FROM posilki').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM meal_changes').fetchone()[0]==0

def test_actual_guards(web_client):
    mid=seed(); path=f'/api/meals/{mid}'
    assert web_client.put(path,json=payload(),headers=HEAD).status_code==401
    login(web_client)
    assert web_client.put(path,json=payload()).status_code==403
    assert web_client.put(path,json=payload(),headers=dict(HEAD,Origin='https://evil.invalid')).status_code==403

@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_nonfinite_json(web_client, token):
    mid=seed(); login(web_client)
    raw=json.dumps(payload()).replace('"calories": 0', '"calories": '+token)
    r=web_client.put(f'/api/meals/{mid}', content=raw, headers=HEAD)
    assert r.status_code==422, r.text


def test_chat_cas_and_backup_legacy(temp_db, tmp_path, monkeypatch):
    from tools.db import init_db
    import sqlite3
    import memory_runtime
    mid=seed()
    with get_conn() as c:
        c.execute('ALTER TABLE posilki DROP COLUMN quantity')
        c.execute('ALTER TABLE posilki DROP COLUMN unit')
    init_db(); init_db()
    with get_conn() as c:
        row=c.execute('SELECT * FROM posilki').fetchone()
        assert row['quantity'] is None and row['unit'] is None
    token=memory_runtime.TURN_CONTEXT.set({'owner':'owner','request_id':'chat-edit'})
    try:
        assert update_meal(mid,'chat corrected',0,None,0,0,expected_revision=1)['revision']==2
        assert not update_meal(mid,'missing revision',1,1,1,1)['success']
    finally: memory_runtime.TURN_CONTEXT.reset(token)
    backup=tmp_path/'restore.db'
    with get_conn() as src, sqlite3.connect(backup) as dst: src.backup(dst)
    monkeypatch.setenv('DB_PATH',str(backup)); init_db()
    with get_conn() as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('SELECT revision FROM posilki').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM meal_changes').fetchone()[0]==1
