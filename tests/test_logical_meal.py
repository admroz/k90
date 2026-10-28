"""Real dispatcher and synthetic SQLite integrity checks."""
import pytest
import memory_runtime
from tools import execute_tool
from tools.db import get_conn
from tools.food_catalog import propose, confirm
from test_food_catalog import label

@pytest.mark.parametrize('reverse', [False, True])
def test_one_breakfast_across_rounds(temp_db, reverse):
    products = []
    for n in range(4):
        data = label(); data['barcode'] = None; data['name'] = f'Synthetic {n}'
        products.append(confirm(propose(data)['id'], 1))
    token = memory_runtime.TURN_CONTEXT.set(memory_runtime.begin_turn('owner', 'Synthetic breakfast'))
    meal = dict(description='Synthetic breakfast with fruit', calories=50, protein_g=0, carbs_g=12, fat_g=0,
                ingredients=[dict(product_id=p['id'],version=2,quantity=100,unit='g') for p in products],
                remainder=dict(description='Fruit only', calories=50,protein_g=0,carbs_g=12,fat_g=0))
    try:
        if reverse: result = execute_tool('log_meal', meal)
        old_results = []
        for p in products:
            old = execute_tool('log_food_portion', dict(product_id=p['id'],version=2,quantity=100,unit='g',request_id=f"old-{p['id']}"))
            old_results.append(old)
        if not reverse: result = execute_tool('log_meal', meal)
        with get_conn() as conn:
            observed = [tuple(r) for r in conn.execute('SELECT id,kalorie FROM posilki')]
        assert all('error' in r for r in old_results), (old_results, result, observed)
        assert 'error' not in result
        with get_conn() as conn:
            rows = conn.execute('SELECT kalorie FROM posilki').fetchall()
            assert len(rows) == 1
            assert rows[0][0] == pytest.approx(4 * products[0]['kcal'] + 50)
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)

from contextlib import contextmanager

@contextmanager
def turn(request='synthetic:one', owner='owner'):
    token = memory_runtime.TURN_CONTEXT.set(dict(owner=owner, request_id=request))
    try:
        yield
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)


def estimated(calories=50):
    return dict(description='Synthetic breakfast', ingredients=[], remainder=dict(
        description='Estimated fruit only',calories=calories,protein_g=0,carbs_g=12,fat_g=0))


def test_operation_replay_conflict_and_new_message(temp_db):
    with turn():
        first = execute_tool('log_meal', estimated())
        replay = execute_tool('log_meal', estimated())
        assert replay['operation_id'] == first['operation_id'] and replay['historical']
        assert execute_tool('log_meal', estimated(70))['error']
    with turn('synthetic:two'):
        second = execute_tool('log_meal', estimated())
        assert first['meal_id'] != second['meal_id']
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM meal_operations').fetchone()[0] == 2


def test_atomic_invalid_ingredient_remainder_and_duplicate_list(temp_db):
    p = confirm(propose(label())['id'], 1)
    item = dict(product_id=p['id'],version=2,quantity=100,unit='g')
    with turn():
        for bad in [dict(item, version=1),dict(item,unit='ml'),dict(item,quantity=-1)]:
            assert execute_tool('log_meal',dict(description='Synthetic',ingredients=[item,bad],remainder=None))['error']
        assert execute_tool('log_meal',dict(description='Synthetic',ingredients=[item]))['error']
        assert execute_tool('log_meal',dict(description='Synthetic',ingredients=[item],remainder={'description':'Fruit'}))['error']
        with get_conn() as conn:
            assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
            assert conn.execute('SELECT count(*) FROM meal_operations').fetchone()[0] == 0
        result = execute_tool('log_meal',dict(description='Synthetic',ingredients=[item,item],remainder=None))
        assert result['nutrition']['calories'] == 2*p['kcal']
        assert execute_tool('log_meal',dict(description='Synthetic',ingredients=[item,item],remainder=None))['replayed']
    with get_conn() as conn:
        snapshot = json.loads(conn.execute('SELECT snapshot FROM meal_ingredients').fetchone()[0])
        assert len(snapshot['ingredients']) == 2
        assert snapshot['remainder'] is None


import json

def test_update_delete_replays_never_restore_or_reapply(temp_db):
    with turn():
        meal = execute_tool('log_meal',estimated())
    args = dict(expected_revision=1,meal_id=meal['meal_id'],description='Synthetic corrected',calories=100,protein_g=2,carbs_g=20,fat_g=1)
    with turn('synthetic:edit'):
        update = execute_tool('update_meal',args)
        assert update['success']
    with turn('synthetic:delete'):
        deleted = execute_tool('delete_meal',{'meal_id':meal['meal_id'],'expected_revision':2})
        assert deleted['success']
    with turn('synthetic:edit'):
        assert execute_tool('update_meal',args)['historical']
    with turn():
        assert execute_tool('log_meal',estimated())['historical']
    with turn('synthetic:delete'):
        assert execute_tool('delete_meal',{'meal_id':meal['meal_id'],'expected_revision':2})['historical']
    with turn('synthetic:missing'):
        for name, payload in [('delete_meal',{'meal_id':999}),('update_meal',dict(args,meal_id=999))]:
            result = execute_tool(name,payload)
            assert result['success'] is False and result['error'] and result['operation_id']
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM meal_operations').fetchone()[0] == 3


def test_before_commit_failure_rolls_back_meal_and_snapshot(temp_db):
    with get_conn() as conn:
        conn.execute("CREATE TRIGGER synthetic_fail BEFORE INSERT ON meal_operations BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    with turn():
        assert execute_tool('log_meal',estimated())['error']
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM meal_ingredients').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM meal_operations').fetchone()[0] == 0


def test_legacy_init_twice_and_sqlite_backup_restore(temp_db, tmp_path, monkeypatch):
    from tools.db import init_db
    init_db(); init_db()
    with turn():
        first = execute_tool('log_meal',estimated())
    backup = tmp_path/'restored.db'
    import sqlite3
    with get_conn() as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    monkeypatch.setenv('DB_PATH',str(backup))
    init_db(); init_db()
    with turn():
        replay = execute_tool('log_meal',estimated())
    assert replay['operation_id'] == first['operation_id'] and replay['historical']
    with get_conn() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 1

@pytest.mark.parametrize('crash', [False, True])
def test_committed_outcome_survives_event_failure_and_crash(temp_db, monkeypatch, crash):
    import agent
    from web_runtime import init_runtime, enqueue, ConversationWorker, recover_interrupted
    monkeypatch.setenv('CONVERSATION_USER_ID','owner')
    monkeypatch.setenv('K90_PREVIEW','false')
    monkeypatch.setenv('K90_SYNC_ENABLED','false')
    init_runtime()
    job = enqueue('web:synthetic-committed','Synthetic request')
    def event_failure(*a):
        if crash: raise SystemExit('synthetic crash')
        raise RuntimeError('synthetic private event failure')
    monkeypatch.setattr(memory_runtime,'record_tool',event_failure)
    def run(*a):
        result = execute_tool('log_meal',estimated())
        assert result['success']
        memory_runtime.record_tool('log_meal',estimated(),result)
    monkeypatch.setattr(agent,'_run_agent',run)
    worker = ConversationWorker()
    if crash:
        with pytest.raises(SystemExit): worker.run_once()
        recover_interrupted()
    else:
        assert worker.run_once()
    enqueue('web:synthetic-committed','Synthetic request')
    assert not worker.run_once()
    with get_conn() as conn:
        row = conn.execute('SELECT state,response FROM chat_jobs').fetchone()
        assert row['state'] == ('interrupted' if crash else 'failed')
        assert 'meal_id=1' in row['response'] and 'operation_id=' in row['response']
        assert 'synthetic private' not in row['response'] and 'Synthetic breakfast' not in row['response']
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM meal_operations').fetchone()[0] == 1


def test_actual_legacy_schema_upgrade_twice(temp_db):
    from tools.db import init_db
    with get_conn() as conn:
        conn.execute('DROP TABLE meal_operations')
        conn.execute('DROP TABLE meal_ingredients')
        conn.execute('ALTER TABLE posilki DROP COLUMN revision')
        conn.execute("INSERT INTO posilki(data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g,zrodlo) VALUES ('2026-01-01','08:00','Synthetic legacy',50,0,12,0,'manual')")
    init_db(); init_db()
    with get_conn() as conn:
        assert conn.execute('SELECT opis,revision FROM posilki').fetchone()[:] == ('Synthetic legacy',1)
    with turn():
        assert execute_tool('log_meal',estimated())['meal_id'] == 2


def test_active_chat_schema_has_only_complete_meal_writer():
    from tools import TOOLS
    functions = {t['function']['name']: t['function'] for t in TOOLS}
    assert 'log_food_portion' not in functions
    schema = functions['log_meal']['parameters']
    assert set(schema['required']) == {'description','ingredients','remainder'}
    assert 'calories' not in schema['properties']
