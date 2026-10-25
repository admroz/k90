"""Synthetic independent boundary probes, not repository changes."""
import json
from types import SimpleNamespace
import pytest

PAYLOADS = {
    'malformed_unquoted_prefix': '{broken,"api\\u005fkey":"SYNTHETIC_ESCAPED_SECRET"}',
    'malformed_comment_prefix': '{/*comment*/"api\\u005fkey":"SYNTHETIC_ESCAPED_SECRET"}',
    'json_string_encoded': json.dumps('{"api\\u005fkey":"SYNTHETIC_ESCAPED_SECRET"}'),
}

@pytest.mark.parametrize('adapter', ['api', 'subscription'])
@pytest.mark.parametrize('variant', list(PAYLOADS))
def test_denied_text_never_reaches_actual_model_receiver(monkeypatch, adapter, variant):
    from k90_memory import PrivacyPolicy, PrivacyError
    import responses_api
    from subscription_api import SubscriptionConversation
    calls = []
    text = PAYLOADS[variant]
    class Client:
        def __init__(self, **kwargs):
            self.responses = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def create(self, **payload):
            calls.append(payload)
            return SimpleNamespace(status='completed', output=[], usage=None)
    class Tokens:
        def access_token(self):
            return 'synthetic-token'
    def receiver(url, **kwargs):
        if url.endswith('/models'):
            return {'models': [{'slug':'demo','visibility':'list'}]}
        calls.append(kwargs['data'])
        return {'status':'completed', 'output':[]}
    monkeypatch.setattr(responses_api, 'OpenAI', Client)
    try:
        messages = [{'role':'user','content':text}]
        if adapter == 'api':
            conv = responses_api.ResponsesConversation('gpt-6.1-sol', messages)
        else:
            conv = SubscriptionConversation('demo', messages, token_store=Tokens(), policy=PrivacyPolicy(), request=receiver)
        conv.complete()
    except PrivacyError:
        pass
    escaped = any('SYNTHETIC_ESCAPED_SECRET' in json.dumps(payload) for payload in calls)
    assert not escaped, f'{adapter}/{variant}: synthetic escaped-key secret reached model receiver'


def test_markdown_and_numeric_allow_deny_pairs():
    from k90_memory import PrivacyPolicy, PrivacyError
    p = PrivacyPolicy()
    for prose in ['[Plan](https://example.invalid)', '[A longer plan](https://example.invalid/path)', 'Ordinary measurements: 120, 6.2']:
        assert p.sanitize_text(prose) == prose
    raw = {'national_id': int('00010112348'), 'SSN': 12345, 'mobile_number': 12345, 'measurements': {'bp':120,'hba1c':6.2,'steps':8000}}
    clean = p.sanitize(raw)
    assert all(clean[k] == '[REDACTED]' for k in ('national_id','SSN','mobile_number'))
    assert clean['measurements'] == raw['measurements']
    for denied in ['{"api\\u005fkey":"synthetic",', '{"local_only":true} trailing', '[{"api\\u005fkey":"synthetic"}] suffix']:
        with pytest.raises(PrivacyError):
            p.sanitize_text(denied)


@pytest.mark.parametrize('restricted_first', [True, False])
def test_backfill_upgrade_and_live_encoded_parts_stay_local(tmp_path, monkeypatch, capsys, restricted_first):
    import sqlite3
    import memory_admin
    import memory_runtime as runtime
    from k90_memory import PrivacyPolicy, Worker, upsert_source
    from k90_memory.store import current
    db = tmp_path / 'synthetic.db'
    def conn():
        result = sqlite3.connect(db)
        result.row_factory = sqlite3.Row
        return result
    monkeypatch.setattr(memory_admin, 'get_conn', conn)
    monkeypatch.setattr(memory_admin, 'get_db_path', lambda: str(db))
    monkeypatch.setattr(runtime, 'get_conn', conn)
    private = {'type':'text', 'text':json.dumps({'local_only':True, 'text':'SYNTHETIC_RESTRICTED'})}
    plain = {'type':'text', 'text':'Ordinary continuation'}
    parts = [private, plain] if restricted_first else [plain, private]
    with conn() as c:
        c.execute('CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id TEXT, role TEXT, content TEXT, timestamp TEXT)')
        c.execute('INSERT INTO conversations VALUES (1,?,?,?,?)', ('owner','user',json.dumps(parts),'2026-10-25T00:00:00Z'))
        runtime.initialize(c)
        upsert_source(c,'conversation:1','owner','user',runtime._text(parts),'unset')
    assert memory_admin.main(['backfill','--apply']) == 0
    capsys.readouterr()
    with conn() as c:
        assert current(c,'owner','conversation:1').local_only is True
    assert memory_admin.main(['backfill','--apply']) == 0
    assert json.loads(capsys.readouterr().out)['queued_sources'] == 0
    turn = runtime.begin_turn('owner',parts)
    with conn() as c:
        assert current(c,'owner',turn['source_id']).local_only is True
    class Receiver:
        retained = []
        recalled = []
        def retain(self, doc):
            self.retained.append(doc)
        def delete(self, doc_id):
            pass
        def recall(self, *args):
            self.recalled.append(args)
            return []
    receiver = Receiver()
    Worker(conn, receiver, policy=PrivacyPolicy(), pseudonym_key=b'synthetic-independent-key').run_once(10)
    monkeypatch.setattr(runtime,'get_backend',lambda *a,**k: receiver)
    assert runtime.recall_context('owner',parts)[0] == ''
    assert receiver.retained == receiver.recalled == []
    # An unrestricted search string may reach semantic search; restricted sources must not return.
    assert runtime.recall_context('owner','SYNTHETIC_RESTRICTED')[0] == ''
    assert receiver.retained == [] and len(receiver.recalled) == 1


@pytest.mark.parametrize('rejection', [{'scope':'openid'}, {'id_token':None}, {'id_token':''}, {'id_token':'***'}])
def test_rotated_rejected_credentials_fail_closed_and_revoke_latest(tmp_path, rejection):
    from subscription_auth import TokenStore, CredentialsError
    directory = tmp_path / 'synthetic-auth'
    requests = []
    def rotate(url, **kwargs):
        requests.append(kwargs['data'])
        return {'access_token':'synthetic-access-new','refresh_token':'synthetic-refresh-new', 'expires_in':3600, **rejection}
    store = TokenStore(directory, request=rotate, clock=lambda:1000)
    store.install({'client_id':'trusted-synthetic-client','subject':'synthetic-subject','access_token':'synthetic-access-old', 'refresh_token':'synthetic-refresh-old','scope':'openid resource.invoke chatgpt.tokens.use.direct','token_type':'Bearer','expires_at':1001,'credits_setting_user_confirmed':True})
    with pytest.raises(CredentialsError):
        store.access_token()
    saved = json.loads(store.path.read_text())
    assert saved['pending_refresh']['refresh_token'] == 'synthetic-refresh-new'
    def forbid(*args, **kwargs):
        pytest.fail('recovery must not reuse old refresh or reach provider')
    restarted = TokenStore(directory, request=forbid, clock=lambda:1000)
    with pytest.raises(CredentialsError):
        restarted.access_token()
    # Even corrupt candidate client metadata cannot control logout client_id.
    saved['pending_refresh']['client_id'] = 'untrusted-synthetic-client'
    store.path.write_text(json.dumps(saved))
    revoked = []
    restarted.request = lambda url, **kw: revoked.append(kw['data']) or {}
    assert restarted.logout() is True
    assert revoked == [{'client_id':'trusted-synthetic-client','token':'synthetic-refresh-new','token_type_hint':'refresh_token'}]
    assert len(requests) == 1 and not store.path.exists()
