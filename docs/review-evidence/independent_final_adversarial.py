"""Independent synthetic receiver matrix for final source. No external I/O."""
import copy
import json
import sqlite3
from types import SimpleNamespace
import pytest
from k90_memory import PrivacyPolicy, PrivacyError

MARKER='SYNTHETIC_FINAL_PRIVATE_ZEBRA'

def encoded(v, n):
    for _ in range(n): v=json.dumps(v)
    return v

DENIED=[
    {'LOCAL - ONLY':True,'text':MARKER},
    {'pAss-word':MARKER},
    {'Authorization':MARKER},
    {'local_only':None,'text':MARKER},
    {'local_only':0,'text':MARKER},
    {'local_only':'false','text':MARKER},
    {'note':encoded({'private_key':MARKER},3)},
    {'note':encoded({'local_only':True,'text':MARKER},4)},
    {'"local\\u005fonly"':True,'text':MARKER},
    {'"api\\u005fkey"':MARKER},
    {'note': [{'x': {'input_file':MARKER}}]},
    '{"note":"'+MARKER+'","bad":1e10000}',
    '{"local_only":false,"local\\u005fonly":true,"text":"'+MARKER+'"}',
    '{"note":"'+MARKER+'"}\n{}',
    '["'+MARKER+'", {"local_only":true}]',
    {'note':'[local-only] '+MARKER},
    {'note':'<local_only> '+MARKER},
]

def receiver(monkeypatch,boundary,value, calls=None):
    import responses_api
    from outbound_policy import chat_completion
    from subscription_api import SubscriptionConversation
    from k90_memory.backend import HindsightBackend, MemoryDocument
    calls=[] if calls is None else calls
    class Client:
        def __init__(self,**kw): self.responses=self
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def create(self,**kw):
            calls.append(kw)
            return SimpleNamespace(status='completed',output=[],usage=None)
    class Token:
        def access_token(self):
            calls.append('TOKEN_ACCESSED'); return 'synthetic'
    def request(url,**kw):
        if url.endswith('/models'): return {'models':[{'slug':'demo','visibility':'list'}]}
        calls.append(kw['data']); return {'status':'completed','output':[]}
    def transport(method,url,body,*a):
        calls.append(json.loads(body))
        return {'results':[]} if url.endswith('/recall') else {'success':True,'async':False,'items_count':1,'bank_id':'k90-final'}
    monkeypatch.setattr(responses_api,'OpenAI',Client)
    text=json.dumps(value) if not isinstance(value,str) else value
    messages=[{'role':'user','content':text}]
    if boundary=='chat': chat_completion(lambda **kw:calls.append(kw),model='demo',messages=messages)
    elif boundary=='responses': responses_api.ResponsesConversation('gpt-6.1-sol',messages).complete()
    elif boundary=='subscription': SubscriptionConversation('demo',messages,token_store=Token(),policy=PrivacyPolicy(),request=request).complete()
    else:
        backend=HindsightBackend('https://synthetic.invalid','k90-final',transport=transport)
        if boundary=='hs_retain': backend.retain(MemoryDocument('k90-doc-r1','event:1',1,'owner:synthetic','user',text,'2026-10-25T00:00:00Z'))
        else: backend.recall('owner:synthetic',text)
    return calls

@pytest.mark.parametrize('boundary',['chat','responses','subscription','hs_retain','hs_recall'])
@pytest.mark.parametrize('value',DENIED)
def test_new_receiver_restrictions(monkeypatch,boundary,value):
    before=copy.deepcopy(value)
    calls=[]
    with pytest.raises(PrivacyError): receiver(monkeypatch,boundary,value,calls)
    assert calls == []
    assert value==before

@pytest.mark.parametrize('boundary',['chat','responses','subscription','hs_retain','hs_recall'])
@pytest.mark.parametrize('value',[
    'Contact synthetic.final@example.invalid',
    {'phone':10112348,'metric':6.2},
    {'nested':{'national_id':1234567,'bp':120}},
    {'note':encoded({'email':'synthetic.final@example.invalid'},3)},
])
def test_new_receiver_redactions(monkeypatch,boundary,value):
    calls=receiver(monkeypatch,boundary,value)
    assert calls
    serialized=json.dumps(calls)
    assert 'synthetic.final@example.invalid' not in serialized
    assert '10112348' not in serialized and '1234567' not in serialized
    assert '[REDACTED]' in serialized

@pytest.mark.parametrize('boundary',['chat','responses','subscription','hs_retain','hs_recall'])
def test_control_normal_markdown_and_measurements(monkeypatch,boundary):
    calls=receiver(monkeypatch,boundary,'[Plan](https://example.invalid)\nBP 120/80; HbA1c 6.2')
    assert calls and '120/80' in json.dumps(calls)


def test_malicious_hs_refs_never_hydrate_other_owner_stale_or_deleted(tmp_path):
    from k90_memory import initialize,upsert_source
    from k90_memory.store import SourceRef,delete_source
    from k90_memory.worker import retrieve
    c=sqlite3.connect(tmp_path/'ledger.db')
    initialize(c)
    upsert_source(c,'shared','owner-a','user','visible apple','2026-10-25')
    upsert_source(c,'shared','owner-b','user',MARKER,'2026-10-25')
    upsert_source(c,'stale','owner-a','user','old '+MARKER,'2026-10-24')
    upsert_source(c,'stale','owner-a','user','current orange','2026-10-25')
    upsert_source(c,'deleted','owner-a','user',MARKER,'2026-10-25')
    delete_source(c,'deleted','owner-a'); c.commit()
    class Malicious:
        def recall(self,*a): return [SourceRef('stale',1),SourceRef('deleted',1),SourceRef('unknown',1),SourceRef('shared',1)]
    results=retrieve(c,'owner-a','apple',backend=Malicious(),pseudonym_key=b'synthetic-final-test-key')
    assert [s.content for s in results]==['visible apple']
    c.close()


def test_subscription_rejects_limit_without_api_fallback(monkeypatch):
    import subscription_api
    import responses_api
    import litellm
    from subscription_protocol import ProbeError
    def paid(*a,**kw): pytest.fail('forbidden paid fallback')
    monkeypatch.setattr(litellm,'completion',paid)
    monkeypatch.setattr(responses_api,'OpenAI',paid)
    calls=[]
    def request(url,**kw):
        calls.append(url)
        if url.endswith('/models'):return {'models':[{'slug':'demo','visibility':'list'}]}
        raise ProbeError('http_429')
    conv=subscription_api.SubscriptionConversation('demo',[{'role':'user','content':'ordinary'}],token_store=SimpleNamespace(access_token=lambda:'synthetic'),policy=PrivacyPolicy(),request=request)
    with pytest.raises(subscription_api.SubscriptionError,match='http_429'):conv.complete()
    assert len(calls)==2
