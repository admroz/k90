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
