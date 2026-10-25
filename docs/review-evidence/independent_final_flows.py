"""Actual source-to-model paths with independent fixtures, all synthetic."""
import json
from types import SimpleNamespace
import pytest
from k90_memory import PrivacyError

PRIVATE=json.dumps({'notes':json.dumps({'local_only':True,'text':'SYNTHETIC_FINAL_FLOW_PRIVATE'})})

@pytest.fixture
def database(tmp_path,monkeypatch):
    from tools import db
    data=tmp_path/'data';data.mkdir()
    monkeypatch.setenv('DB_PATH',str(data/'synthetic.db'))
    monkeypatch.setenv('DATA_DIR',str(data))
    monkeypatch.setenv('K90_MEMORY_BACKEND','local')
    monkeypatch.setenv('K90_CHATGPT_STATE_DIR',str(tmp_path/'auth'))
    db.init_db()
    return data

@pytest.mark.parametrize('mode',['chat','responses','subscription'])
@pytest.mark.parametrize('source',['incoming','history','profile','meal','tool','summary_document'])
def test_actual_source_composition_no_receiver_escape(database,monkeypatch,mode,source):
    import agent,summary,responses_api,subscription_api,subscription_auth
    from tools.db import get_conn
    from tools.time_utils import today_local
    from patient_documents import write_document,get_document
    from tools.patient import read_patient_file
    calls=[]
    def forbidden(*a,**kw):
        calls.append((a,kw));pytest.fail('restricted original reached receiver')
    monkeypatch.setattr(agent,'SYSTEM_PROMPT','Ordinary synthetic system')
    monkeypatch.setattr(agent,'MODEL','gpt-6.1-sol' if mode=='responses' else 'demo-chat')
    monkeypatch.setattr(summary,'SUMMARY_MODEL','gpt-6.1-sol' if mode=='responses' else 'demo-chat')
    monkeypatch.setattr(summary,'DATA_DIR',database)
    monkeypatch.setenv('K90_AGENT_AUTH','chatgpt' if mode=='subscription' else 'api')
    monkeypatch.setenv('K90_SUMMARY_AUTH','chatgpt' if mode=='subscription' else 'api')
    monkeypatch.setattr(responses_api,'OpenAI',forbidden)
    monkeypatch.setattr(subscription_auth.TokenStore,'access_token',forbidden)
    monkeypatch.setattr(agent.litellm,'completion',forbidden)
    incoming='Ordinary question'
    if source=='incoming': incoming=PRIVATE
    elif source=='history':
        with get_conn() as c:c.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)',('synthetic','assistant',PRIVATE))
    elif source=='profile':
        with get_conn() as c:c.execute('INSERT INTO patient_summary(id,content) VALUES (1,?)',(PRIVATE,))
    elif source=='meal':
        with get_conn() as c:c.execute('INSERT INTO posilki(data,opis) VALUES (?,?)',(today_local(),PRIVATE))
    elif source in ('tool','summary_document'):write_document('pacjent.md',PRIVATE)
    with pytest.raises(PrivacyError):
        if source=='summary_document':summary.refresh_patient_summary('synthetic')
        elif source=='tool':
            result=read_patient_file('pacjent.md')
            if mode=='responses':
                conv=responses_api.ResponsesConversation('gpt-6.1-sol',[{'role':'user','content':incoming}])
                conv.add_tool_result('synthetic-call',result);conv.complete()
            elif mode=='subscription':
                from outbound_policy import model_policy
                conv=subscription_api.SubscriptionConversation('demo-chat',[{'role':'user','content':incoming}],token_store=SimpleNamespace(access_token=forbidden),policy=model_policy(),request=forbidden)
                conv.add_tool_result('synthetic-call',result);conv.complete()
            else:
                from outbound_policy import chat_completion
                chat_completion(forbidden,model='demo-chat',messages=[{'role':'tool','tool_call_id':'synthetic-call','content':json.dumps(result)}])
        else:agent.run_agent(incoming,'synthetic')
    assert calls==[]
    if source in ('tool','summary_document'):assert get_document('pacjent.md')['content']==PRIVATE
    if source=='incoming':
        with get_conn() as c:
            assert json.loads(c.execute("SELECT payload FROM agent_events WHERE kind='incoming'").fetchone()[0])==PRIVATE
            assert c.execute('SELECT local_only FROM memory_sources').fetchone()[0]==1
