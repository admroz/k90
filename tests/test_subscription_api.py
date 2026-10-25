"""Subscription Responses adapter, network replaced with a synthetic provider."""
import importlib
import json

import pytest


class Tokens:
    def access_token(self):
        return 'synthetic-oauth'


class Policy:
    def sanitize(self, value):
        if isinstance(value, str):
            return value.replace('synthetic@example.invalid', '[EMAIL]')
        if isinstance(value, list):
            return [self.sanitize(v) for v in value]
        if isinstance(value, dict):
            return {k: self.sanitize(v) for k,v in value.items()}
        return value


def test_subscription_preserves_tools_reasoning_and_applies_policy_each_round(monkeypatch):
    adapter = importlib.import_module('subscription_api')
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-paid-key-not-to-use')
    sent = []
    outputs = [
        {'status':'completed','output':[
            {'type':'reasoning','encrypted_content':'synthetic-encrypted'},
            {'type':'function_call','namespace':'k90','name':'demo','call_id':'synthetic-call','arguments':'{}'}],
         'usage':{'input_tokens':12,'output_tokens':3}},
        {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'Done'}]}]},
    ]
    def request(url,**kwargs):
        assert kwargs['token']=='synthetic-oauth'
        if url.endswith('/models'):
            return {'models':[{'slug':'demo-model','visibility':'list'}]}
        assert url=='https://api.openai.com/v1/responses'
        sent.append(kwargs['data'])
        return outputs.pop(0)
    tools=[{'type':'function','function':{'name':'demo','description':'Synthetic tool',
            'parameters':{'type':'object','properties':{}}}}]
    conversation=adapter.SubscriptionConversation('demo-model',[
        {'role':'system','content':'A synthetic@example.invalid test'},
        {'role':'user','content':'Call the tool'}],tools,
        token_store=Tokens(),policy=Policy(),request=request)
    turn=conversation.complete()
    assert turn.calls[0].name=='demo'
    assert turn.input_tokens==12 and turn.output_tokens==3
    assert sent[0]['instructions']=='A [EMAIL] test'
    assert not any(m.get('role')=='system' for m in sent[0]['input'])
    assert sent[0]['tools'][0]['type']=='namespace'
    assert sent[0]['store'] is False and sent[0]['stream'] is True
    assert 'max_output_tokens' not in sent[0]
    conversation.add_tool_result('synthetic-call',{'data':'synthetic@example.invalid'})
    assert conversation.complete().text=='Done'
    assert any(i.get('encrypted_content')=='synthetic-encrypted' for i in sent[1]['input'])
    assert any(i.get('type')=='function_call_output' and '[EMAIL]' in i['output'] for i in sent[1]['input'])
    assert 'synthetic@example.invalid' not in json.dumps(sent)
    assert 'synthetic-paid-key-not-to-use' not in json.dumps(sent)


def test_subscription_rejects_foreign_namespace_before_tool_execution():
    adapter=importlib.import_module('subscription_api')
    def request(url,**kwargs):
        if url.endswith('/models'):
            return {'models':[{'slug':'demo-model','visibility':'list'}]}
        return {'status':'completed','output':[{'type':'function_call','namespace':'foreign',
                 'name':'demo','call_id':'synthetic','arguments':'{}'}]}
    with pytest.raises(adapter.SubscriptionError,match='unexpected_tool'):
        adapter.SubscriptionConversation('demo-model',[],[
            {'type':'function','function':{'name':'demo','parameters':{'type':'object','properties':{}}}}],
            token_store=Tokens(),policy=Policy(),request=request).complete()


def test_subscription_image_parts_and_catalog_allowlist():
    adapter=importlib.import_module('subscription_api')
    requests=[]
    def request(url,**kwargs):
        if url.endswith('/models'):
            return {'models':[{'slug':'demo-model','visibility':'list'}]}
        requests.append(kwargs['data'])
        return {'status':'completed','output':[]}
    convo=adapter.SubscriptionConversation('demo-model',[{'role':'user','content':[
        {'type':'text','text':'Synthetic shapes'},
        {'type':'image_url','image_url':{'url':'data:image/png;base64,c3ludGhldGlj'}}]}],
        token_store=Tokens(),policy=Policy(),request=request)
    convo.complete()
    assert requests[0]['input'][0]['content'][1]['type']=='input_image'
    with pytest.raises(adapter.SubscriptionError,match='model_not_in_account_catalog'):
        adapter.SubscriptionConversation('unknown',[],token_store=Tokens(),policy=Policy(),request=request).complete()
    assert len(requests)==1
