"""Local product review acceptance on synthetic SQLite, without a provider."""
import pytest
import agent
import memory_runtime
import web_runtime
from tools import food_catalog as catalog
from tools.db import get_conn
from test_food_catalog import label


def preview(owner='owner', data=None):
    turn = memory_runtime.begin_turn(owner, 'Synthetic proposal request')
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        p = catalog.propose_from_chat(data or label())
        answer = agent.save_history(owner, 'Synthetic proposal request', 'model text')
        assert 'Czy zatwierdzasz' in answer
        return p
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)


def test_preview_local_confirm_and_duplicate(temp_db, monkeypatch):
    p = preview()
    monkeypatch.setenv('K90_SYNC_ENABLED','true')
    def forbidden(*a, **kw): raise AssertionError('must stay local')
    monkeypatch.setattr(agent, '_run_agent', forbidden)
    monkeypatch.setattr('tools.garmin.should_auto_sync_today', forbidden)
    monkeypatch.setattr('tools.libre.should_auto_sync', forbidden)
    token = web_runtime.MESSAGE_CONTEXT.set({'request_id':'synthetic-consent','user_id':'owner'})
    try:
        first = web_runtime.process_message('tak, zapisz ten produkt')
        second = web_runtime.process_message('tak, zapisz ten produkt')
        assert first == second and 'zatwierdzony' in first
    finally:
        web_runtime.MESSAGE_CONTEXT.reset(token)
    assert catalog.get(p['id'])['version'] == 2
    with get_conn() as c:
        assert c.execute("SELECT status FROM food_product_reviews").fetchone()[0] == 'consumed'


@pytest.mark.parametrize('text', ['nie zatwierdzam','"zatwierdzam"','może zatwierdzam','zatwierdzę jutro','zatwierdziłbym','tak, pogoda dobra'])
def test_unsafe_consent_does_not_save(temp_db, monkeypatch, text):
    p = preview()
    monkeypatch.setattr(agent,'_run_agent',lambda *a: ('Synthetic unrelated reply',False))
    agent.run_agent(text,'owner')
    assert catalog.get(p['id'])['status'] == 'draft'


def test_correction_then_separate_consent_and_cancel(temp_db):
    p = preview()
    answer, _ = agent.run_agent('zmień białko na 12 i zatwierdź','owner')
    assert 'Czy zatwierdzasz' in answer
    assert catalog.get(p['id'])['protein'] == 12
    assert catalog.get(p['id'])['status'] == 'draft'
    agent.run_agent('anuluj','owner')
    agent.run_agent('zatwierdzam','owner')
    assert catalog.get(p['id'])['status'] == 'draft'
    with get_conn() as c:
        assert set(r[0] for r in c.execute('SELECT status FROM food_product_reviews')) == {'cancelled'}


def test_wrong_owner_multiple_stale_and_topic(temp_db, monkeypatch):
    p = preview()
    assert 'zatwierdzony' not in agent.run_agent('zatwierdzam','other')[0]
    monkeypatch.setattr(agent,'_run_agent',lambda *a: ('Synthetic other topic',False))
    agent.run_agent('Jak spałem?','owner')
    assert 'zatwierdzony' not in agent.run_agent('tak','owner')[0]
    data = label(); data['barcode'] = None
    preview(data=data)
    assert 'zatwierdzony' not in agent.run_agent('zatwierdzam','owner')[0]
    assert catalog.get(p['id'])['status'] == 'draft'


def test_stale_panel_revision_and_legacy_preview(temp_db):
    p = preview()
    data = label(); data['protein'] = 13
    catalog.revise(p['id'],1,data)
    assert 'zatwierdzony' not in agent.run_agent('zatwierdzam','owner')[0]
    with get_conn() as c:
        c.execute('UPDATE food_products SET owner=NULL WHERE id=?',(p['id'],))
    assert 'zatwierdzony' not in agent.run_agent(f"/produkt zatwierdz {p['id']} 2",'owner')[0]
    answer,_ = agent.run_agent(f"/produkt pokaz {p['id']} 2",'owner')
    assert 'Czy zatwierdzasz' in answer
    assert 'zatwierdzony' in agent.run_agent('tak','owner')[0]


def test_no_review_from_tool_or_model_declaration(temp_db, monkeypatch):
    turn = memory_runtime.begin_turn('owner','Synthetic request')
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        p = catalog.propose_from_chat(label())
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_product_reviews').fetchone()[0] == 0
    monkeypatch.setattr(agent,'_run_agent',lambda *a: ('I confirm everything',False))
    agent.run_agent('Synthetic conversation','owner')
    assert 'zatwierdzony' not in agent.run_agent('tak','owner')[0]
    assert catalog.get(p['id'])['status'] == 'draft'


def test_correction_duplicate_request_and_old_command(temp_db):
    p = preview()
    token = web_runtime.MESSAGE_CONTEXT.set({'request_id':'synthetic-edit','user_id':'owner'})
    try:
        first = agent.run_agent('zmień białko na 12 i zatwierdź','owner')[0]
        assert agent.run_agent('zmień białko na 12 i zatwierdź','owner')[0] == first
    finally:
        web_runtime.MESSAGE_CONTEXT.reset(token)
    assert catalog.get(p['id'])['version'] == 2
    assert 'zatwierdzony' not in agent.run_agent(f"/produkt zatwierdz {p['id']} 1",'owner')[0]
    assert 'zatwierdzony' in agent.run_agent(f"/produkt zatwierdz {p['id']} 2",'owner')[0]
    with get_conn() as c:
        audit = c.execute('SELECT owner,source,source_event_id FROM food_product_approvals').fetchone()
        assert audit['owner'] == 'owner' and audit['source'] == 'chat' and audit['source_event_id']


def test_expired_review_and_wrong_owner_api(temp_db):
    p = preview()
    with pytest.raises(ValueError): catalog.confirm(p['id'],1,owner='other')
    with pytest.raises(ValueError): catalog.revise(p['id'],1,label(),owner='other')
    with get_conn() as c:
        c.execute("UPDATE food_product_reviews SET created_at=datetime('now','-31 minutes')")
    assert 'zatwierdzony' not in agent.run_agent('zatwierdzam','owner')[0]


def test_natural_consent_dispatch_red(temp_db, monkeypatch):
    # Works against the old API as well: this RED reaches the dispatcher, not a new helper.
    turn = memory_runtime.begin_turn('owner','Synthetic proposal')
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        catalog.propose_from_chat(label())
        agent.save_history('owner','Synthetic proposal','Synthetic precise preview. Czy zatwierdzasz?')
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    def forbidden(*a, **kw): raise AssertionError('consent reached sync/model')
    monkeypatch.setenv('K90_SYNC_ENABLED','true')
    monkeypatch.setattr('tools.garmin.should_auto_sync_today',forbidden)
    monkeypatch.setattr('tools.libre.should_auto_sync',forbidden)
    monkeypatch.setattr(agent,'_run_agent',forbidden)
    assert 'zatwierdzony' in web_runtime.process_message('zatwierdzam')


def test_restart_and_sqlite_backup_restore(temp_db, tmp_path):
    import os
    import subprocess
    import sys
    import sqlite3
    p = preview()
    restored = tmp_path/'restored.db'
    with get_conn() as source, sqlite3.connect(restored) as destination:
        source.backup(destination)
    env = dict(os.environ,DB_PATH=str(restored))
    completed = subprocess.run([sys.executable,'-c',
        "from agent import run_agent; assert 'zatwierdzony' in run_agent('tak','owner')[0]"],
        env=env, text=True, capture_output=True, timeout=45)
    assert completed.returncode == 0, completed.stderr
    with sqlite3.connect(restored) as c:
        assert c.execute('SELECT version FROM food_products WHERE id=?',(p['id'],)).fetchone()[0] == 2
        assert c.execute('SELECT status FROM food_product_reviews').fetchone()[0] == 'consumed'
    assert catalog.get(p['id'])['status'] == 'draft'


def test_additive_legacy_migration_does_not_bind_owner(temp_db):
    p = catalog.propose(label())
    with get_conn() as c:
        c.execute('ALTER TABLE food_products DROP COLUMN owner')
        for table in ['food_product_reviews','food_review_actions','food_product_approvals']:
            c.execute('DROP TABLE '+table)
        catalog.initialize(c)
        catalog.initialize(c)
        assert c.execute('SELECT owner FROM food_products').fetchone()[0] is None
        assert c.execute('SELECT count(*) FROM food_product_reviews').fetchone()[0] == 0
    assert 'zatwierdzony' not in agent.run_agent('tak','owner')[0]
    assert catalog.get(p['id'])['version'] == 1


def test_confirm_is_one_transaction_and_panel_chat_race(temp_db):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    p = preview()
    with get_conn() as c:
        c.execute("CREATE TRIGGER synthetic_fail BEFORE INSERT ON food_product_versions BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    with pytest.raises(sqlite3.IntegrityError): agent.run_agent('zatwierdzam','owner')
    assert catalog.get(p['id'])['status'] == 'draft'
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_product_approvals').fetchone()[0] == 0
        assert c.execute('SELECT status FROM food_product_reviews').fetchone()[0] == 'pending'
        c.execute('DROP TRIGGER synthetic_fail')
    barrier = Barrier(2)
    def confirm_chat():
        barrier.wait()
        return agent.run_agent('zatwierdzam','owner')[0]
    def panel_edit():
        barrier.wait()
        data = label(); data['protein'] = 14
        try: return catalog.revise(p['id'],1,data)
        except ValueError: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        chat = pool.submit(confirm_chat); panel = pool.submit(panel_edit)
        chat.result(timeout=30); panel.result(timeout=30)
    assert catalog.get(p['id'])['version'] == 2
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_product_versions').fetchone()[0] == 2
        assert c.execute('SELECT count(*) FROM food_product_approvals').fetchone()[0] <= 1


def test_text_correction_needs_new_consent(temp_db):
    p = preview()
    answer,_ = agent.run_agent('zmień nazwę na Synthetic Yogurt i zatwierdź','owner')
    assert 'Czy zatwierdzasz' in answer
    assert catalog.get(p['id'])['name'] == 'Synthetic Yogurt'
    assert catalog.get(p['id'])['status'] == 'draft'
    assert 'zatwierdzony' in agent.run_agent('tak','owner')[0]


def test_committed_approval_survives_failed_response_and_recovery(temp_db, monkeypatch):
    from tools.db import MESSAGE_CONTEXT
    p = preview()
    web_runtime.init_runtime()
    web_runtime.enqueue('synthetic-committed', 'zatwierdzam')
    original = agent.save_history
    def fail(*a, **kw): raise RuntimeError('synthetic persistence failure')
    monkeypatch.setattr(agent,'save_history',fail)
    worker = web_runtime.ConversationWorker()
    assert worker.run_once()
    assert catalog.get(p['id'])['status'] == 'confirmed'
    with get_conn() as c:
        row = c.execute('SELECT state,response FROM chat_jobs WHERE request_id=?',('synthetic-committed',)).fetchone()
        assert row['state'] == 'failed' and 'zatwierdzony' in row['response']
        c.execute("UPDATE chat_jobs SET state='running',response=NULL WHERE request_id='synthetic-committed'")
    web_runtime.recover_interrupted()
    with get_conn() as c:
        assert 'zatwierdzony' in c.execute("SELECT response FROM chat_jobs WHERE request_id='synthetic-committed'").fetchone()[0]
    monkeypatch.setattr(agent,'save_history',original)
    token = MESSAGE_CONTEXT.set({'request_id':'synthetic-committed','user_id':'owner'})
    try: assert 'zatwierdzony' in agent.run_agent('zatwierdzam','owner')[0]
    finally: MESSAGE_CONTEXT.reset(token)
    assert catalog.get(p['id'])['version'] == 2



def test_cli_topic_command_invalidates_direct_answer(temp_db, monkeypatch):
    p = preview(owner='cli')
    inputs = iter(['/status','tak','exit'])
    monkeypatch.setattr('builtins.input',lambda prompt='':next(inputs))
    monkeypatch.setattr(agent,'handle_command',lambda text:'Synthetic status' if text == '/status' else None)
    monkeypatch.setattr(agent,'_run_agent',lambda *a: (_ for _ in ()).throw(AssertionError('model forbidden')))
    agent.cli()
    assert catalog.get(p['id'])['status'] == 'draft'
