"""Synthetic model wire captures; the switch never grants HS/image permission."""
import json
from types import SimpleNamespace

import pytest

EMAIL = 'synthetic@example.invalid'


@pytest.mark.parametrize('enabled', ['true', 'false'])
@pytest.mark.parametrize('transport', ['chat', 'responses', 'subscription'])
def test_agent_context_history_tool_and_current_text_follow_switch(temp_db, monkeypatch, caplog, enabled, transport):
    import agent
    import responses_api
    import subscription_api
    import subscription_auth
    from litellm import ModelResponse

    monkeypatch.setenv('K90_TEXT_FILTER_ENABLED', enabled)
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    monkeypatch.setenv('K90_AGENT_AUTH', 'chatgpt' if transport == 'subscription' else 'api')
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'disabled')
    monkeypatch.setattr(agent, 'MODEL', 'gpt-6.1-sol' if transport == 'responses' else 'demo')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('context ' + EMAIL, {}))
    monkeypatch.setattr(agent, 'execute_tool', lambda *a: {'note': 'tool ' + EMAIL})
    agent.save_history('test', 'history ' + EMAIL, 'previous')
    sent = []

    def output():
        if len(sent) == 1:
            return [{'type':'function_call','call_id':'call_test','name':'get_weight_trend','arguments':'{}'}]
        return [{'type':'message','content':[{'type':'output_text','text':'done'}]}]

    class Client:
        def __init__(self, **kw): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def create(self, **kw):
            sent.append(kw)
            values = output()
            items = []
            for value in values:
                item = SimpleNamespace(**value, model_dump=lambda value=value, **kw:value)
                if value['type'] == 'message':
                    item.content = [SimpleNamespace(**part) for part in value['content']]
                items.append(item)
            return SimpleNamespace(status='completed', output=items, usage=None)

    def request(url, **kw):
        if url.endswith('/models'):
            return {'models':[{'slug':'demo','visibility':'list'}]}
        sent.append(kw['data'])
        return {'status':'completed','output':output()}

    def chat(**kw):
        # Capture a deep copy because the agent appends subsequent rounds.
        sent.append(json.loads(json.dumps(kw)))
        message = {'role':'assistant', 'content':'done'}
        if len(sent) == 1:
            message = {'role':'assistant', 'content':None, 'tool_calls':[
                {'id':'call_test','type':'function','function':{'name':'get_weight_trend','arguments':'{}'}}]}
        return ModelResponse(choices=[{'message':message,'finish_reason':'stop'}])

    monkeypatch.setattr(agent.litellm, 'completion', chat)
    monkeypatch.setattr(responses_api, 'OpenAI', Client)
    monkeypatch.setattr(subscription_auth, 'TokenStore', lambda *a: SimpleNamespace(access_token=lambda:'synthetic'))
    monkeypatch.setattr(subscription_api, 'request_json', request)
    with caplog.at_level('INFO'):
        assert agent.run_agent('current ' + EMAIL, 'test') == ('done', False)
    profiles = [json.loads(r.getMessage().split(' profile=', 1)[1])
                for r in caplog.records if ' profile=' in r.getMessage()]
    assert {'history', 'context', 'recall', 'provider', 'tool', 'persistence', 'filtering', 'provider_request'} <= {r['stage'] for r in profiles}
    assert len({r['request_id'] for r in profiles}) == 1
    assert EMAIL not in json.dumps(profiles) and 'test' not in json.dumps(profiles)
    assert len(sent) == 2
    wire = json.dumps(sent)
    for label in ('context', 'history', 'tool', 'current'):
        assert label in wire
    assert (EMAIL in wire) == (enabled == 'false')
    assert ('[REDACTED]' in wire) == (enabled == 'true')
    from tools.db import get_conn
    with get_conn() as conn:
        assert EMAIL in conn.execute("SELECT content FROM conversations WHERE user_id='test' AND role='user' ORDER BY id DESC LIMIT 1").fetchone()[0]


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_summary_documents_obey_model_switch_without_changing_original(temp_db, monkeypatch, enabled):
    import summary
    from patient_documents import write_document, get_document
    monkeypatch.setenv('K90_TEXT_FILTER_ENABLED', enabled)
    write_document('pacjent.md', 'summary ' + EMAIL)
    parts, contents = summary._load_patient_parts()
    assert (EMAIL in '\n'.join(parts)) == (enabled == 'false')
    assert (EMAIL in summary._build_summary_prompt('\n'.join(parts))) == (enabled == 'false')
    assert EMAIL in get_document('pacjent.md')['content']


@pytest.mark.parametrize('action', ['retain', 'recall'])
def test_hindsight_reapplies_baseline_even_with_disabled_model_policy(monkeypatch, action):
    from outbound_policy import model_policy
    from k90_memory import HindsightBackend, PrivacyError
    from k90_memory.backend import MemoryDocument
    monkeypatch.setenv('K90_TEXT_FILTER_ENABLED', 'false')
    sent = []
    def transport(method, url, body, timeout, max_bytes):
        sent.append(json.loads(body))
        return {'results':[]} if action == 'recall' else {'success':True,'async':False,'items_count':1,'bank_id':'k90-synthetic'}
    backend = HindsightBackend('https://synthetic.invalid', 'k90-synthetic', policy=model_policy(), transport=transport)
    def invoke(text):
        if action == 'recall':
            return backend.recall('owner:synthetic', text)
        return backend.retain(MemoryDocument('k90-synthetic-r1','source',1,'owner:synthetic','user',text,'2026-10-26T00:00:00Z'))
    invoke(EMAIL)
    assert EMAIL not in json.dumps(sent) and '[REDACTED]' in json.dumps(sent)
    count = len(sent)
    with pytest.raises(PrivacyError):
        invoke('Bearer synthetic-secret')
    assert len(sent) == count
