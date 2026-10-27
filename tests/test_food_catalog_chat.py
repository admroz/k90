"""Synthetic tool/chat flow; never a live vision test."""
import json
import agent
import memory_runtime
from tools import execute_tool
from tools.db import get_conn
from test_food_catalog import label


def test_label_tool_binds_original_event_and_explicit_confirmation(temp_db, monkeypatch):
    message = [{'type':'text','text':'Synthetic nutrition label'},
               {'type':'image_url','image_url':{'url':'data:image/png;base64,iVBORw0KGgo='}}]
    turn = memory_runtime.begin_turn('owner', message)
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        data = label()
        data['provenance'] = 'own_label'
        draft = execute_tool('propose_food_product', {'product':data})
        assert draft['status'] == 'draft'
        assert draft['source_event_id'] == turn['user_event_id']
        assert execute_tool('confirm_food_product', {'product_id':draft['id'], 'version':1}).get('error')
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    monkeypatch.setattr(agent, '_run_agent', lambda *a: (_ for _ in ()).throw(AssertionError('model forbidden for approval')))
    answer, refresh = agent.run_agent(f"/produkt zatwierdz {draft['id']} 1", 'owner')
    assert 'zatwierdzony' in answer and not refresh
    found = execute_tool('find_food_products', {'query':'Synthetic'})
    assert found[0]['status'] == 'confirmed'
    with get_conn() as conn:
        row = conn.execute('SELECT payload FROM agent_events WHERE id=?', (turn['user_event_id'],)).fetchone()
        assert json.loads(row[0]) == message


def test_own_label_requires_current_photo_and_no_model_confirmed_flag(temp_db):
    data = label()
    data['provenance'] = 'own_label'
    assert 'error' in execute_tool('propose_food_product', {'product':data})
    data['provenance'] = 'manual'
    data['status'] = 'confirmed'
    result = execute_tool('propose_food_product', {'product':data})
    assert result['status'] == 'draft'


def test_synthetic_provider_http_photo_review_and_later_reuse(temp_db, monkeypatch):
    from types import SimpleNamespace as NS
    from fastapi.testclient import TestClient
    from webapp import create_app
    from web_runtime import ConversationWorker
    from tools.food_catalog import get
    from test_web import login
    monkeypatch.setenv('WEB_PASSWORD', 'test-password-long')
    monkeypatch.setenv('WEB_COOKIE_SECURE', 'false')
    monkeypatch.setenv('CONVERSATION_USER_ID', 'owner')
    monkeypatch.setenv('K90_AGENT_AUTH', 'api')
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'local')
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    monkeypatch.setenv('K90_SYNC_ENABLED', 'false')
    monkeypatch.setattr(agent, 'MODEL', 'synthetic-vision')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(memory_runtime, 'start_worker', lambda: None)
    label_data = label(); label_data['provenance'] = 'own_label'
    calls = iter([
        ('propose_food_product', {'product':label_data}), None,
        ('find_food_products', {'barcode':'5900531004544'}),
        ('log_meal', {'description':'Synthetic skyr', 'ingredients':[{'product_id':1,'version':2,'quantity':150,'unit':'g'}], 'remainder':None}), None])
    sent = []
    def provider(**payload):
        sent.append(payload)
        call = next(calls)
        if call:
            name, args = call
            tc = dict(id='synthetic-call-'+str(len(sent)), type='function', function={'name':name,'arguments':json.dumps(args)})
            message = NS(content=None, tool_calls=[NS(id=tc['id'], function=NS(**tc['function']))],
                         model_dump=lambda **_: {'role':'assistant','tool_calls':[tc]})
        else:
            answer = 'Synthetic review: /produkt zatwierdz 1 1' if len(sent) == 2 else 'Synthetic portion saved 96 kcal'
            message = NS(content=answer, tool_calls=[], model_dump=lambda **_: {'role':'assistant','content':answer})
        return NS(choices=[NS(message=message)], usage=None)
    monkeypatch.setattr(agent.litellm, 'completion', provider)
    worker = ConversationWorker()
    h = {'X-K90-Request':'1'}
    with TestClient(create_app(start_worker=False)) as client:
        login(client)
        image = 'data:image/png;base64,iVBORw0KGgo='
        assert client.post('/api/messages', json=dict(request_id='web:synthetic-label',text='Synthetic label to catalog',image=image), headers=h).status_code == 202
        assert worker.run_once()
        assert get(1)['status'] == 'draft'
        client.post('/api/messages', json=dict(request_id='web:synthetic-approval',text='/produkt zatwierdz 1 1'), headers=h)
        assert worker.run_once() and get(1)['status'] == 'confirmed'
        monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'false')
        client.post('/api/messages', json=dict(request_id='web:synthetic-portion',text='Synthetic skyr 150g'), headers=h)
        assert worker.run_once()
        assert len(sent) == 5
        assert image in json.dumps(sent[0])
        assert image not in json.dumps(sent[2:])
        with get_conn() as conn:
            assert conn.execute('SELECT kalorie,bialko_g,weglowodany_g,tluszcze_g FROM posilki').fetchone()[:] == (96,18,6.15,0)
            assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 1


def test_retired_portion_writer_and_incomplete_meal_contract_cannot_write(temp_db):
    from tools.food_catalog import propose, confirm
    p = confirm(propose(label())['id'], 1)
    turn = memory_runtime.begin_turn('owner', 'Synthetic portion')
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        args = dict(product_id=p['id'],version=2,quantity=150,unit='g',request_id='model-key1')
        first = execute_tool('log_food_portion', args)
        second = execute_tool('log_food_portion', dict(args,request_id='model-key2'))
        assert second == first and 'error' in first
        assert 'error' in execute_tool('log_meal', dict(description='Synthetic duplicate',calories=96,protein_g=18,carbs_g=6.15,fat_g=0))
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0


def test_text_event_cannot_become_label_provenance(temp_db):
    from tools.food_catalog import propose_from_chat, revise
    import pytest
    turn = memory_runtime.begin_turn('owner', 'Synthetic text only')
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        p = propose_from_chat(label())
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    data = label(); data['provenance'] = 'own_label'
    with pytest.raises(ValueError): revise(p['id'], 1, data)


def test_real_dispatch_approval_does_not_sync_or_call_models(temp_db, monkeypatch):
    import web_runtime
    from tools.food_catalog import propose
    p = propose(label())
    def forbidden(*a, **kw): raise AssertionError('approval must be local')
    calls = []
    monkeypatch.setenv('K90_SYNC_ENABLED', 'true')
    monkeypatch.setenv('K90_PREVIEW', 'false')
    monkeypatch.setattr('tools.garmin.should_auto_sync_today', lambda: calls.append('sync') or False)
    monkeypatch.setattr('tools.libre.should_auto_sync', lambda: calls.append('sync') or False)
    monkeypatch.setattr('summary.refresh_patient_summary', lambda **_: calls.append('summary'))
    monkeypatch.setattr(agent, '_run_agent', forbidden)
    assert 'zatwierdzony' in web_runtime.process_message(f"/produkt zatwierdz {p['id']} 1")
    assert calls == []


def test_retired_portion_writer_never_writes_for_any_identity(temp_db):
    from tools.food_catalog import propose, confirm
    p = confirm(propose(label())['id'], 1)
    turn = memory_runtime.begin_turn('owner', 'Synthetic identity')
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        args = dict(product_id=p['id'],version=2,quantity=150,unit='g',request_id='fixture')
        assert 'error' in execute_tool('log_food_portion', args)
        for bad in ['1', 1.0, True, -1, 2**64]:
            assert 'error' in execute_tool('log_food_portion', dict(args, product_id=bad))
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
