"""Offline provider boundaries; real agent, dispatcher, SQLite and queue.

These synthetic fixtures diagnose local replay only, never a production cause.
"""
from copy import deepcopy
from types import SimpleNamespace as NS
import http.client
import json

import httpx
from openai import OpenAI
import pytest

import agent
import memory_runtime
import responses_api
from tools.db import get_conn, MESSAGE_CONTEXT
from tools.diet import log_meal
from web_runtime import init_runtime, enqueue, ConversationWorker, recover_interrupted
from test_responses_api import call, response, message


@pytest.mark.parametrize('adapter,mode,fail_second',
    [(a,m,f) for a in ('chat','responses','subscription') for m in ('read','update','multi') for f in ('','status')] +
    [(a,'update',f) for a in ('chat','responses','subscription') for f in ('timeout','filter')] +
    [('responses','update','incomplete'),('subscription','update','stream')])
def test_real_tool_second_request(temp_db, monkeypatch, adapter, mode, fail_second):
    monkeypatch.setenv('K90_AGENT_AUTH', 'chatgpt' if adapter == 'subscription' else 'api')
    monkeypatch.setenv('K90_PREVIEW','false')
    monkeypatch.setenv('K90_SYNC_ENABLED','false')
    monkeypatch.setenv('CONVERSATION_USER_ID','owner')
    monkeypatch.setattr(agent,'MODEL','synthetic-chat' if adapter == 'chat' else 'gpt-6.1-sol')
    monkeypatch.setattr(agent,'_build_system_message',lambda: ('Synthetic system', {}))
    monkeypatch.setattr(memory_runtime,'start_worker',lambda: None)
    meal = log_meal('Synthetic original', 50, 0, 12, 0)
    edit = dict(meal_id=meal['meal_id'],description='Synthetic corrected synthetic@example.invalid',
                calories=75,protein_g=1,carbs_g=16,fat_g=1)
    calls = []
    if mode in ('read','multi'): calls.append(call('get_recent_meals', '{}', 'read-id'))
    if mode in ('update','multi'): calls.append(call('update_meal', json.dumps(edit), 'update-id'))
    if mode == 'multi': calls.append(call('delete_meal', '{"meal_id":999999}', 'missing-id'))
    reasoning = {'id':'rs_synthetic','type':'reasoning','summary':[], 'encrypted_content':'synthetic-encrypted'}
    output = [reasoning, *calls]
    sent = []

    def next_response(payload):
        sent.append(deepcopy(payload))
        if len(sent) == 1:
            return response(output)
        if fail_second == 'timeout':
            raise TimeoutError('synthetic boundary timeout')
        if fail_second == 'incomplete':
            return response([],status='incomplete')
        if fail_second == 'status':
            raise RuntimeError('synthetic boundary failure')
        return response([message('Synthetic completed')])

    if adapter == 'chat':
        def completion(**payload):
            result = next_response(payload)
            if len(sent) == 1:
                tool_calls = [dict(id=c['call_id'],type='function',function=dict(name=c['name'],arguments=c['arguments'])) for c in calls]
                raw = dict(role='assistant',content=None,tool_calls=tool_calls)
                msg = NS(content=None, tool_calls=[NS(id=c['id'],function=NS(**c['function'])) for c in tool_calls],model_dump=lambda **_:raw)
            else:
                msg = NS(content='Synthetic completed',tool_calls=[],model_dump=lambda **_:dict(role='assistant',content='Synthetic completed'))
            return NS(choices=[NS(message=msg)],usage=None)
        monkeypatch.setattr(agent.litellm,'completion',completion)
    elif adapter == 'responses':
        def handle(request):
            try:
                reply = next_response(json.loads(request.content))
            except TimeoutError:
                raise httpx.ReadTimeout('synthetic timeout',request=request)
            except RuntimeError:
                return httpx.Response(400,json={'error':{'message':'synthetic failure','type':'invalid_request_error'}})
            return httpx.Response(200,json=reply)
        def client(**options):
            options['max_retries'] = 0  # One deterministic fixture attempt; production settings untouched.
            return OpenAI(api_key='synthetic-only',base_url='http://model.test/v1',
                          http_client=httpx.Client(transport=httpx.MockTransport(handle)), **options)
        monkeypatch.setattr(responses_api,'OpenAI',client)
    else:
        # Mock only HTTP and token access, retaining actual SSE parsing/namespace/policy.
        import subscription_auth
        monkeypatch.setattr(subscription_auth.TokenStore,'access_token',lambda _: 'synthetic-only')
        for c in calls: c['namespace'] = 'k90'
        class Connection:
            def __init__(self,*a,**kw): pass
            def request(self, method, path, body=None, headers=None):
                self.path = path; self.body = body
            def getresponse(self):
                if self.path.endswith('/models'):
                    return NS(status=200,read=lambda _:json.dumps({'models':[{'slug':'gpt-6.1-sol','visibility':'list'}]}).encode())
                try:
                    reply = next_response(json.loads(self.body))
                except RuntimeError:
                    return NS(status=400)
                event = json.dumps({'type':'response.completed','response':reply}).encode()
                class Stream:
                    status = 200
                    def __iter__(self):
                        if fail_second == 'stream' and len(sent) == 2: return iter([])
                        return iter([b'data: '+event+b'\n',b'\n'])
                return Stream()
            def close(self): pass
        monkeypatch.setattr(http.client,'HTTPSConnection',Connection)

    if fail_second == 'filter':
        original = agent.execute_tool
        def filtered_after_write(name, args):
            return dict(original(name,args), secret='synthetic-blocked-fixture')
        monkeypatch.setattr(agent,'execute_tool',filtered_after_write)
    init_runtime()
    enqueue('web:synthetic-adapter', 'Synthetic correction request')
    worker = ConversationWorker()
    assert worker.run_once()
    assert len(sent) == (1 if fail_second == 'filter' else 2)
    if fail_second != 'filter' and adapter == 'chat':
        outputs = [dict(call_id=m['tool_call_id'],output=m['content']) for m in sent[1]['messages'] if m.get('role') == 'tool']
    elif fail_second != 'filter':
        outputs = [i for i in sent[1]['input'] if i.get('type') == 'function_call_output']
        assert reasoning in sent[1]['input']
        from outbound_policy import sanitize_payload
        assert all(c in sent[1]['input'] for c in sanitize_payload(calls))
        if adapter == 'subscription':
            assert sent[1]['tools'][0]['name'] == 'k90'
    if fail_second == 'filter': outputs = []
    assert [o['call_id'] for o in outputs] == ([c['call_id'] for c in calls] if fail_second != 'filter' else [])
    decoded = [json.loads(o['output']) for o in outputs]
    if mode == 'multi': assert decoded[-1]['error'] and decoded[-1]['success'] is False
    assert 'synthetic@example.invalid' not in json.dumps(outputs)
    with get_conn() as conn:
        job = conn.execute('SELECT * FROM chat_jobs').fetchone()
        stored = conn.execute('SELECT kalorie FROM posilki WHERE id=?',(meal['meal_id'],)).fetchone()[0]
        assert stored == (50 if mode == 'read' else 75)
        assert job['state'] == ('failed' if fail_second else 'done')
        if fail_second:
            assert 'synthetic boundary failure' not in job['response']
            if mode != 'read':
                assert f"meal_id={meal['meal_id']}" in job['response'] and 'operation_id=' in job['response']
            else: assert '0 zatwierdzonych' in job['response']
    # Queue/request/delivery retries and restart recovery cannot replay writes.
    enqueue('web:synthetic-adapter', 'Synthetic correction request')
    recover_interrupted()
    assert not worker.run_once() and len(sent) == (1 if fail_second == 'filter' else 2)
    with get_conn() as conn:
        assert conn.execute('SELECT revision FROM posilki').fetchone()[0] == (1 if mode == 'read' else 2)
        assert conn.execute("SELECT count(*) FROM meal_operations WHERE kind='update_meal'").fetchone()[0] == (0 if mode == 'read' else 1)
