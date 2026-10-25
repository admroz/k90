"""Real loopback HTTP receivers. No cloud calls or real credentials."""
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import json
import threading
from types import SimpleNamespace
import pytest
from k90_memory import PrivacyPolicy,PrivacyError

@contextmanager
def server():
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):self.reply()
        def do_POST(self):self.reply()
        def reply(self):
            length=int(self.headers.get('Content-Length',0))
            body=self.rfile.read(length)
            received.append({'path':self.path,'body':body.decode(),'authorization':self.headers.get('Authorization')})
            if self.path.endswith('/models'):
                data={'models':[{'slug':'demo','visibility':'list'}]}
            elif self.path.endswith('/memories/recall'):data={'results':[]}
            elif self.path.endswith('/memories'):data={'success':True,'async':False,'items_count':1,'bank_id':'k90-final'}
            elif self.path.endswith('/chat/completions'):
                data={'id':'synthetic','object':'chat.completion','created':1,'model':'demo','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'ordinary'}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
            else:data={'status':'completed','output':[],'usage':None}
            stream=self.headers.get('Accept')=='text/event-stream'
            raw=('data: '+json.dumps({'type':'response.completed','response':data})+'\n\n').encode() if stream else json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream' if stream else 'application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    try:yield srv.server_port,received
    finally:srv.shutdown();srv.server_close();thread.join()

@pytest.mark.parametrize('boundary',['chat','responses','subscription','hs_stdlib','hs_runtime'])
@pytest.mark.parametrize('private',[False,True])
def test_wire_receiver(monkeypatch,boundary,private):
    import responses_api
    from openai import OpenAI
    from outbound_policy import chat_completion
    from subscription_api import SubscriptionConversation
    from k90_memory.backend import HindsightBackend,MemoryDocument
    import memory_runtime
    import litellm
    marker='SYNTHETIC_WIRE_PRIVATE'
    text=json.dumps({'local_only':True,'text':marker}) if private else 'Contact synthetic.wire@example.invalid; BP 120/80'
    with server() as (port,received):
        url=f'http://127.0.0.1:{port}'
        def invoke():
            if boundary=='chat':
                completion=partial(litellm.completion,api_base=url+'/v1',api_key='synthetic-wire-token',num_retries=0)
                chat_completion(completion,model='openai/demo',messages=[{'role':'user','content':text}])
            elif boundary=='responses':
                monkeypatch.setattr(responses_api,'OpenAI',partial(OpenAI,base_url=url+'/v1',api_key='synthetic-wire-token'))
                responses_api.ResponsesConversation('gpt-6.1-sol',[{'role':'user','content':text}]).complete()
            elif boundary=='subscription':
                class LocalHTTPS(http.client.HTTPConnection):
                    def __init__(self,host,**kw):
                        assert host=='api.openai.com'
                        super().__init__('127.0.0.1',port=port,**kw)
                monkeypatch.setattr(http.client,'HTTPSConnection',LocalHTTPS)
                SubscriptionConversation('demo',[{'role':'user','content':text}],token_store=SimpleNamespace(access_token=lambda:'synthetic-wire-token'),policy=PrivacyPolicy()).complete()
            else:
                backend=HindsightBackend(url,'k90-final',allow_internal_http=True,transport=memory_runtime._transport('synthetic-wire-token') if boundary=='hs_runtime' else None)
                backend.retain(MemoryDocument('k90-doc-r1','event:1',1,'owner:synthetic','user',text,'2026-10-25T00:00:00Z'))
                backend.recall('owner:synthetic',text)
        if private:
            with pytest.raises(PrivacyError):invoke()
            assert received==[]
        else:
            invoke()
            assert received
            bodies='\n'.join(r['body'] for r in received)
            assert 'synthetic.wire@example.invalid' not in bodies
            assert '[REDACTED]' in bodies and '120/80' in bodies
            print('WIRE',boundary,'requests',len(received),'redaction_verified')
