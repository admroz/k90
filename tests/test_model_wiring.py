"""Exercise real app entry points with synthetic model receivers only."""
import json
from types import SimpleNamespace

import pytest

import agent
from k90_memory import PrivacyError
from tools.db import get_conn


class Message:
    content='Synthetic answer'
    tool_calls=[]
    def model_dump(self,**kwargs):
        return {'role':'assistant','content':self.content}


def context(monkeypatch):
    monkeypatch.setattr(agent,'MODEL','gpt-5.4')
    monkeypatch.setattr(agent,'_build_system_message',lambda:('Synthetic system',{}))
    monkeypatch.setenv('K90_AGENT_AUTH','api')
    monkeypatch.setenv('K90_MEMORY_BACKEND','local')


def test_agent_blocks_secret_before_model_but_keeps_original_locally(temp_db,monkeypatch):
    context(monkeypatch)
    calls=[]
    monkeypatch.setattr(agent.litellm,'completion',lambda **kw:calls.append(kw) or SimpleNamespace(
        choices=[SimpleNamespace(message=Message())],usage=None))
    with pytest.raises(PrivacyError):
        agent.run_agent('Bearer synthetic-private-secret','synthetic-owner')
    assert calls==[]
    with get_conn() as conn:
        incoming=conn.execute("SELECT payload FROM agent_events WHERE kind='incoming'").fetchone()
        assert json.loads(incoming[0])=='Bearer synthetic-private-secret'
        assert conn.execute('SELECT count(*) FROM conversations').fetchone()[0]==0


def test_agent_filters_model_payload_and_keeps_canonical_raw_pair(temp_db,monkeypatch):
    context(monkeypatch)
    captured=[]
    monkeypatch.setattr(agent.litellm,'completion',lambda **kw:captured.append(kw) or SimpleNamespace(
        choices=[SimpleNamespace(message=Message())],usage=None))
    assert agent.run_agent('Synthetic contact synthetic@example.invalid','synthetic-owner')[0]=='Synthetic answer'
    assert 'synthetic@example.invalid' not in json.dumps(captured)
    with get_conn() as conn:
        assert conn.execute("SELECT content FROM conversations WHERE role='user'").fetchone()[0]=='Synthetic contact synthetic@example.invalid'
        assert conn.execute("SELECT count(*) FROM agent_events WHERE kind IN ('incoming','assistant')").fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM memory_outbox').fetchone()[0]==2


def test_summary_provider_uses_shared_filter(monkeypatch):
    import summary
    monkeypatch.setattr(summary,'SUMMARY_MODEL','gpt-5.4')
    monkeypatch.setenv('K90_SUMMARY_AUTH','api')
    captured=[]
    text='\n'.join(label+' Synthetic' for label in summary.SUMMARY_LABELS)
    monkeypatch.setattr(summary.litellm,'completion',lambda **kw:captured.append(kw) or SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text),finish_reason='stop')]))
    assert summary._generate_summary('Synthetic contact synthetic@example.invalid')[0]==text
    assert 'synthetic@example.invalid' not in json.dumps(captured)


def test_summary_subscription_never_uses_paid_api(monkeypatch):
    import summary,subscription_api
    from responses_api import Turn
    monkeypatch.setattr(summary,'SUMMARY_MODEL','gpt-6.1-sol')
    monkeypatch.setenv('K90_SUMMARY_AUTH','chatgpt')
    text='\n'.join(label+' Synthetic' for label in summary.SUMMARY_LABELS)
    captured=[]
    class Fake:
        def __init__(self,*args,**kwargs):
            captured.append(args)
        def complete(self):
            return Turn(text)
    monkeypatch.setattr(subscription_api,'SubscriptionConversation',Fake)
    monkeypatch.setattr(summary.litellm,'completion',lambda **kw:pytest.fail('paid summary fallback'))
    monkeypatch.setattr(summary,'ResponsesConversation',lambda *a,**k:pytest.fail('API-key Responses path'))
    assert summary._generate_summary('Synthetic profile')[0]==text
    assert captured


def test_responses_api_key_transport_filters_before_sdk_call(monkeypatch):
    import responses_api
    captured=[]
    class Client:
        def __init__(self):
            self.responses=SimpleNamespace(create=self.create)
        def __enter__(self):
            return self
        def __exit__(self,*args):
            return False
        def create(self,**kw):
            captured.append(kw)
            return SimpleNamespace(status='completed',output=[],usage=None)
    monkeypatch.setattr(responses_api,'OpenAI',lambda **kw:Client())
    responses_api.ResponsesConversation('gpt-6.1-sol',[{'role':'user','content':'synthetic@example.invalid'}]).complete()
    assert 'synthetic@example.invalid' not in json.dumps(captured)


def test_images_are_blocked_without_explicit_model_consent(monkeypatch):
    import responses_api
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES','false')
    monkeypatch.setattr(responses_api,'OpenAI',lambda **kw:pytest.fail('blocked image reached SDK'))
    image=[{'type':'image_url','image_url':{'url':'data:image/png;base64,c3ludGhldGlj'}}]
    with pytest.raises(PrivacyError):
        responses_api.ResponsesConversation('gpt-6.1-sol',[{'role':'user','content':image}]).complete()


def test_subscription_mode_routes_other_catalog_models_without_api_fallback(temp_db,monkeypatch):
    context(monkeypatch)
    monkeypatch.setenv('K90_AGENT_AUTH','chatgpt')
    monkeypatch.setattr(agent,'MODEL','gpt-6-astra')
    import subscription_api
    from responses_api import Turn
    captured=[]
    class FakeConversation:
        def __init__(self,*args,**kwargs):
            captured.append((args,kwargs))
        def complete(self):
            return Turn('Synthetic plan answer')
    monkeypatch.setattr(subscription_api,'SubscriptionConversation',FakeConversation)
    monkeypatch.setattr(agent.litellm,'completion',lambda **kw:pytest.fail('paid API fallback forbidden'))
    assert agent.run_agent('Synthetic question','synthetic-owner')[0]=='Synthetic plan answer'
    assert captured[0][0][0]=='gpt-6-astra'
    assert captured[0][1]['policy'] is not None
