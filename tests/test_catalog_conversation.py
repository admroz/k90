"""Simulated vision only: real HTTP/Telegram adapters, queue and agent/tools."""
import base64
import json
from copy import deepcopy
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from litellm import ModelResponse
import agent
import memory_runtime
from tools import food_catalog as catalog
from tools.db import get_conn
from webapp import create_app
from web_runtime import ConversationWorker
from test_food_catalog import label

PNG = 'data:image/png;base64,iVBORw0KGgo='

@pytest.fixture
def conversation(temp_db, monkeypatch):
    for key, value in {'WEB_PASSWORD':'synthetic-test-password', 'WEB_COOKIE_SECURE':'false',
                       'K90_INTERNAL_TOKEN':'synthetic-token','TELEGRAM_ALLOWED_USER_ID':'123',
                       'K90_ALLOW_MODEL_IMAGES':'true','K90_SYNC_ENABLED':'false',
                       'K90_PREVIEW':'false','K90_AGENT_AUTH':'api'}.items():
        monkeypatch.setenv(key,value)
    monkeypatch.setattr(agent,'MODEL','gpt-5.4')
    monkeypatch.setattr(agent,'_build_system_message',lambda:('synthetic system',{}))
    monkeypatch.setattr(memory_runtime,'start_worker',lambda:None)
    pending=[]; sent=[]
    def provider(**kw):
        sent.append(deepcopy(kw['messages']))
        item=pending.pop(0)
        if isinstance(item,Exception): raise item
        msg={'role':'assistant','content':item} if isinstance(item,str) else {
            'role':'assistant','content':None,'tool_calls':[{'id':'call'+str(len(sent)),
            'type':'function','function':{'name':item[0],'arguments':json.dumps(item[1])}}]}
        return ModelResponse(choices=[{'index':0,'message':msg,'finish_reason':'stop'}])
    monkeypatch.setattr(agent.litellm,'completion',provider)
    with TestClient(create_app(start_worker=False)) as client:
        client.post('/api/login',json={'password':'synthetic-test-password'},headers={'X-K90-Request':'1'})
        class Backend:
            def call(self, method, path, **kwargs):
                r=client.request(method,path,headers={'Authorization':'Bearer synthetic-token'},**kwargs)
                r.raise_for_status(); return r.json()
        api=Mock(); api.download_file.return_value=(base64.b64decode(PNG.split(',')[1]),'image/png')
        worker=ConversationWorker(); serial=iter(range(1,100))
        def send(text,photo=False,channel='web'):
            n=next(serial)
            if channel=='telegram':
                from telegram_adapter import accept_update
                message={'message_id':n,'from':{'id':123},'chat':{'id':123,'type':'private'}}
                message.update({'caption':text,'photo':[{'file_id':'fake'}]} if photo else {'text':text})
                accept_update(api,Backend(),{'update_id':n,'message':message})
            else:
                body={'request_id':'web:conversation-'+str(n),'text':text}
                if photo: body['image']=PNG
                assert client.post('/api/messages',json=body,headers={'X-K90-Request':'1'}).status_code==202
            assert worker.run_once()
            with get_conn() as c: return dict(c.execute('SELECT * FROM chat_jobs ORDER BY seq DESC LIMIT 1').fetchone())
        yield send,pending,sent

@pytest.mark.parametrize('channel',['web','telegram'])
def test_photo_continuation_status_and_ordinary_yes(conversation,channel):
    send,pending,sent=conversation
    pending.extend([('propose_food_product',{'product':dict(label(),barcode=None,provenance='own_label')}),'simulated draft'])
    assert 'Czy zatwierdzasz' in send('Zachowaj etykietę',True,channel)['response']
    pending.extend([('revise_food_product',{'changes':{'barcode':'5900531004544'}}),'simulated updated'])
    response=send('Potwierdzam, dołączam jeszcze zdjęcie kodu',True,channel)
    assert response['state']=='done' and '5900531004544' in response['response']
    assert catalog.get(1)['version']==2 and catalog.get(1)['status']=='draft'
    assert 'Potwierdzam' in json.dumps(sent[2]) and PNG in json.dumps(sent[2])
    status=send('Zapisałeś?',channel=channel)['response']
    assert 'szkic' in status.lower() and 'Czy zatwierdzasz' in status
    assert 'zatwierdzony' in send('ok',channel=channel)['response']
    assert catalog.get(1)['version']==3
    assert 'zatwierdzony' in send('Zapisałeś?',channel=channel)['response']
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM food_product_approvals').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM food_product_versions').fetchone()[0]==3
        assert c.execute('SELECT count(*) FROM posilki').fetchone()[0]==0


def test_partial_text_correction_preserves_fields(conversation):
    send,pending,_=conversation
    data=dict(label(),barcode=None,provenance='own_label',piece_size=125)
    pending.extend([('propose_food_product',{'product':data}),'simulated draft'])
    send('Zachowaj etykietę',True)
    pending.extend([('revise_food_product',{'changes':{'brand':'Synthetic corrected brand','protein':19}}),'simulated correction'])
    answer=send('Popraw białko proszę na 19, a marka to Synthetic corrected brand, reszta bez zmian')['response']
    p=catalog.get(1)
    assert p['version']==2 and p['status']=='draft' and p['protein']==19
    assert p['name']==data['name'] and p['kcal']==float(data['kcal']) and p['piece_size']==125
    assert 'Czy zatwierdzasz' in answer
    assert 'zatwierdzony' in send('tak')['response']


@pytest.mark.parametrize('revision',[False,True])
def test_postwrite_provider_failure_is_catalog_specific_and_recoverable(conversation,revision):
    send,pending,_=conversation
    pending.extend([('propose_food_product',{'product':dict(label(),barcode=None,provenance='own_label')}),
                    'simulated draft' if revision else RuntimeError('simulated provider failure')])
    failed=send('Zachowaj etykietę',True)
    if revision:
        pending.extend([('revise_food_product',{'changes':{'fat':8.5}}),RuntimeError('simulated provider failure')])
        failed=send('Doprecyzuję: tłuszczu jest 8.5',True)
    assert failed['state']=='failed'
    assert 'szkic' in failed['response'].lower() and 'posiłk' not in failed['response'].lower()
    # Recovery reads, never replays tools. Even an unpublished changed draft is not consented.
    assert catalog.get(1)['status']=='draft'
    assert 'zatwierdzony' not in send('ok')['response']
    status=send('Zapisałeś?')['response']
    assert 'Czy zatwierdzasz' in status
    assert 'zatwierdzony' in send('ok')['response']
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM food_product_versions').fetchone()[0]==(3 if revision else 2)
