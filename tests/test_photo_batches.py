import base64
import pytest
from webapp import Message

@pytest.fixture(autouse=True)
def trusted_owner(monkeypatch):
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_ID','123')


PNG = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nsynthetic').decode()

def test_three_photos_one_content():
    message = Message(request_id='web:batch', text='Jeden produkt', images=[PNG]*3)
    assert [p['image_url']['url'] for p in message.content() if p['type']=='image_url'] == [PNG]*3

@pytest.mark.parametrize('kwargs', [dict(image=PNG, images=[PNG]), dict(images=[PNG]*5), dict(images=[]), dict(images=['data:image/png;base64,%%%']), dict(images=[PNG.replace('png','jpeg')])])
def test_reject_whole_invalid_batch(kwargs):
    with pytest.raises(ValueError):
        Message(request_id='web:batch', text='produkt', **kwargs)

import json
from tools.db import get_conn
from web_runtime import init_runtime, accept_album_part, flush_albums


def part(n, **extra):
    return dict(owner=123, chat_id=123, group_id='group', update_id=n, message_id=n, text=f'caption{n}', image=PNG, **extra)


def test_durable_ordered_album_duplicate_restart_late(temp_db):
    init_runtime()
    for n in (3,1,2,2):
        accept_album_part(**part(n), now=100)
    with get_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM chat_jobs').fetchone()[0] == 0
    init_runtime()  # Restart preserves the inbox and dedup state.
    flush_albums(now=101.9)
    with get_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM chat_jobs').fetchone()[0] == 0
    flush_albums(now=102)
    flush_albums(now=103)
    accept_album_part(**part(2), now=104)  # Retry of known element is not late.
    accept_album_part(**part(4), now=104)
    accept_album_part(**part(4), now=105)
    with get_conn() as conn:
        jobs = conn.execute('SELECT * FROM chat_jobs ORDER BY seq').fetchall()
        assert len(jobs) == 2
        assert jobs[0]['kind'] == 'message'
        content = json.loads(jobs[0]['payload'])
        assert content[0]['text'] == 'caption1\ncaption2\ncaption3'
        assert len(content) == 4
        assert jobs[1]['kind'] == 'transport_notice'
        assert conn.execute('SELECT COUNT(*) FROM telegram_album_parts WHERE image IS NOT NULL').fetchone()[0] == 0


def test_fifth_photo_rejects_entire_album_and_retention(temp_db):
    init_runtime()
    for n in range(1,7):
        accept_album_part(**part(n), now=100)
    flush_albums(now=120)
    with get_conn() as conn:
        jobs = conn.execute('SELECT * FROM chat_jobs').fetchall()
        assert len(jobs) == 1 and jobs[0]['kind'] == 'transport_notice'
        assert conn.execute('SELECT state FROM telegram_albums').fetchone()[0] == 'rejected'
    flush_albums(now=100+8*86400)
    with get_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM telegram_albums').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM telegram_album_parts').fetchone()[0] == 0


@pytest.mark.parametrize('sizes,valid', [([5_000_000,5_000_000],True),([5_000_001],False),([4_000_000,4_000_000,2_000_001],False)])
def test_decoded_limits(sizes,valid):
    images = ['data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'x'*(n-8)).decode() for n in sizes]
    if valid:
        assert len(Message(request_id='web:size',images=images).content()) == 3
    else:
        with pytest.raises(ValueError): Message(request_id='web:size',images=images)


def test_one_batch_one_draft_and_all_evidence(temp_db):
    import memory_runtime
    from tools import execute_tool
    from tools.food_catalog import label_image
    from test_food_catalog import label
    content = Message(request_id='web:batch',images=[PNG]*3).content()
    turn = memory_runtime.begin_turn('owner',content)
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        product = dict(label(),provenance='own_label')
        draft = execute_tool('propose_food_product',{'product':product})
        assert draft['status']=='draft'
        assert execute_tool('propose_food_product',{'product':product})['id']==draft['id']
        other = dict(product,name='Different product',barcode=None)
        for _ in range(3):
            assert 'error' in execute_tool('propose_food_product',{'product':other})
        assert label_image(draft['id']) == {'image':PNG,'images':[PNG]*3}
        with get_conn() as conn:
            assert conn.execute('SELECT COUNT(*) FROM food_products').fetchone()[0] == 1
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)


def test_http_album_adapter_durable_before_ack_and_worker(temp_db,monkeypatch):
    from fastapi.testclient import TestClient
    from unittest.mock import Mock
    import agent
    from telegram_adapter import accept_update
    from webapp import create_app
    from web_runtime import ConversationWorker
    monkeypatch.setenv('WEB_PASSWORD','synthetic-test-password')
    monkeypatch.setenv('K90_INTERNAL_TOKEN','synthetic-token')
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_ID','123')
    monkeypatch.setenv('K90_SYNC_ENABLED','false')
    seen=[]
    monkeypatch.setattr(agent,'run_agent',lambda content,user_id:(seen.append(content) or 'ok',False))
    with TestClient(create_app(start_worker=False)) as client:
        class Backend:
            def call(self,method,path,**kwargs):
                response=client.request(method,path,headers={'Authorization':'Bearer synthetic-token'},**kwargs)
                response.raise_for_status()
                return response.json()
        api=Mock(); api.download_file.return_value=(base64.b64decode(PNG.split(',')[1]),'image/png')
        backend=Backend()
        for n in (3,1,2,2):
            update={'update_id':n,'message':{'message_id':n,'media_group_id':'album','from':{'id':123},'chat':{'id':123,'type':'private'},'caption':str(n),'photo':[{'file_id':'small'},{'file_id':'large'}]}}
            accept_update(api,backend,update)
            with get_conn() as conn:
                assert conn.execute('SELECT COUNT(*) FROM telegram_album_parts').fetchone()[0] >= 1
            backend.call('POST','/internal/offset',json={'offset':n+1})
        assert not ConversationWorker().run_once()
        flush_albums(now=__import__('time').time()+3)
        assert ConversationWorker().run_once()
        assert not ConversationWorker().run_once()
        assert len(seen)==1 and len(seen[0])==4
        bad=part(99);bad['chat_id']=456
        assert client.post('/internal/albums/part',json=bad,headers={'Authorization':'Bearer synthetic-token'}).status_code==403


def test_seal_and_enqueue_rollback_together(temp_db,monkeypatch):
    import web_runtime
    init_runtime()
    accept_album_part(**part(1),now=100)
    original=web_runtime._enqueue
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('synthetic crash before seal commit')
    monkeypatch.setattr(web_runtime,'_enqueue',fail)
    with pytest.raises(RuntimeError): flush_albums(now=103)
    with get_conn() as conn:
        assert conn.execute('SELECT state FROM telegram_albums').fetchone()[0]=='pending'
        assert conn.execute('SELECT COUNT(*) FROM chat_jobs').fetchone()[0]==0
        assert conn.execute('SELECT image FROM telegram_album_parts').fetchone()[0]==PNG
    monkeypatch.setattr(web_runtime,'_enqueue',original)
    flush_albums(now=103)
    with get_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM chat_jobs').fetchone()[0]==1


def test_stream_download_stops_before_full_allocation():
    from unittest.mock import Mock
    from telegram_adapter import TelegramAPI,ImageTooLarge
    api=TelegramAPI('synthetic-token')
    api.call=Mock(return_value={'file_path':'synthetic.png'})
    response=Mock(headers={})
    response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
    response.iter_content.return_value=iter([b'x'*1_000_000]*6)
    api._session.get=Mock(return_value=response)
    with pytest.raises(ImageTooLarge): api.download_file('fake')
    assert api._session.get.call_args.kwargs['stream'] is True


def test_batch_filter_and_next_text_turn_omit_all_photos(temp_db,monkeypatch):
    import agent
    from outbound_policy import model_policy
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES','true')
    content=Message(request_id='web:joint',images=[PNG]*3).content()
    assert model_policy().sanitize(content)==content
    agent.save_history('owner',content,'synthetic answer')
    history=agent.load_history('owner')
    assert 'data:image/' not in json.dumps(history)
    assert sum(p.get('text')=='[Historical image omitted]' for p in history[0]['content'])==3


def test_http_three_photos_one_turn_draft_consent_preview(temp_db,monkeypatch):
    from fastapi.testclient import TestClient
    from litellm import ModelResponse
    import agent
    from webapp import create_app
    from web_runtime import ConversationWorker
    from test_food_catalog import label
    from copy import deepcopy
    monkeypatch.setenv('WEB_PASSWORD','synthetic-test-password')
    monkeypatch.setenv('WEB_COOKIE_SECURE','false')
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES','true')
    monkeypatch.setenv('K90_SYNC_ENABLED','false')
    monkeypatch.setenv('K90_PREVIEW','false')
    monkeypatch.setattr(agent,'MODEL','gpt-5.4')
    monkeypatch.setattr(agent,'_build_system_message',lambda:('synthetic system',{}))
    product=dict(label(),provenance='own_label')
    pending=[{'role':'assistant','content':None,'tool_calls':[{'id':'call1','type':'function','function':{'name':'propose_food_product','arguments':json.dumps({'product':product})}}]},
             {'role':'assistant','content':'Sprawdź wspólną propozycję.'}, {'role':'assistant','content':'Dalszy tekst.'}]
    sent=[]
    def completion(**kwargs):
        sent.append(deepcopy(kwargs['messages']))
        return ModelResponse(choices=[{'index':0,'message':pending.pop(0),'finish_reason':'stop'}],usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
    monkeypatch.setattr(agent.litellm,'completion',completion)
    with TestClient(create_app(start_worker=False)) as client:
        client.post('/api/login',json={'password':'synthetic-test-password'},headers={'X-K90-Request':'1'})
        headers={'X-K90-Request':'1'}
        body={'request_id':'web:joint','text':'Zachowaj jeden produkt','images':[PNG]*3}
        assert client.post('/api/messages',json=body,headers=headers).status_code==202
        assert client.post('/api/messages',json=body,headers=headers).status_code==202
        assert ConversationWorker().run_once()
        with get_conn() as conn:
            draft=conn.execute('SELECT * FROM food_products').fetchone()
            assert draft and draft['status']=='draft'
            assert conn.execute('SELECT COUNT(*) FROM agent_events WHERE role="user"').fetchone()[0]==1
        assert client.get(f"/api/catalog/{draft['id']}/label").json()['images']==[PNG]*3
        assert len([p for p in sent[0][-1]['content'] if p['type']=='image_url'])==3
        assert client.post('/api/messages',json={'request_id':'web:consent','text':'zatwierdzam'},headers=headers).status_code==202
        assert ConversationWorker().run_once()
        with get_conn() as conn:
            assert conn.execute('SELECT status FROM food_products').fetchone()[0]=='confirmed'
            assert conn.execute('SELECT COUNT(*) FROM food_products').fetchone()[0]==1
        assert len(sent)==2  # Consent is local, no inference.
        agent.run_agent('Dalszy tekst','owner')
        assert 'data:image/' not in json.dumps(sent[-1])


@pytest.mark.parametrize('ambiguity',['różne produkty i kody','100g czy 100ml','opakowanie czy porcja','nieczytelne makra'])
def test_synthetic_clarification_has_no_catalog_writes(temp_db,monkeypatch,ambiguity):
    import agent
    from litellm import ModelResponse
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES','true')
    monkeypatch.setattr(agent,'MODEL','gpt-5.4')
    monkeypatch.setattr(agent,'_build_system_message',lambda:('synthetic system',{}))
    # This exercises a clarification response, not recognition of these synthetic pixels.
    monkeypatch.setattr(agent.litellm,'completion',lambda **kw:ModelResponse(choices=[{'index':0,'message':{'role':'assistant','content':'Wyjaśnij: '+ambiguity},'finish_reason':'stop'}],usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}))
    answer,_=agent.run_agent(Message(request_id='web:conflict',images=[PNG]*3).content(),'owner')
    assert 'Wyjaśnij' in answer
    with get_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM food_products').fetchone()[0]==0
