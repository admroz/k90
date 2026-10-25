"""Final review regression cases; synthetic data and external receivers only."""
import json

import pytest


@pytest.mark.parametrize('preexisting', [False, True])
def test_backfill_preserves_multipart_restriction_and_repairs_old_source(temp_db, capsys, preexisting):
    import memory_admin
    import memory_runtime
    from tools.db import get_conn
    from k90_memory import PrivacyPolicy, Worker, upsert_source
    from k90_memory.store import current
    text = 'SYNTHETIC_BACKFILL_PRIVATE'
    raw = [{'type': 'text', 'text': text, 'local_only': True}]
    with get_conn() as conn:
        row_id = conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)',
                              ('owner', 'user', json.dumps(raw))).lastrowid
        source_id = 'conversation:' + str(row_id)
        if preexisting:
            memory_runtime.initialize(conn)
            upsert_source(conn, source_id, 'owner', 'user', text, 'unset')
    assert memory_admin.main(['backfill', '--apply']) == 0
    capsys.readouterr()
    with get_conn() as conn:
        source = current(conn, 'owner', source_id)
        assert source is not None
        assert source.local_only is True
        revision = source.revision
    assert memory_admin.main(['backfill', '--apply']) == 0
    assert json.loads(capsys.readouterr().out)['queued_sources'] == 0
    retained = []
    class Backend:
        def retain(self, document):
            retained.append(document)
        def delete(self, document_id):
            pass
        def recall(self, owner_tag, query, limit):
            return []
    Worker(get_conn, Backend(), policy=PrivacyPolicy(), pseudonym_key=b'synthetic-final-key').run_once(limit=10)
    assert retained == []
    assert memory_runtime.recall_context('owner', text)[0] == ''
    with get_conn() as conn:
        unchanged = current(conn, 'owner', source_id)
        assert unchanged is not None and unchanged.revision == revision
        assert conn.execute("SELECT status FROM memory_outbox WHERE source_id=? AND revision=? AND operation='retain'",
                            (source_id, revision)).fetchone()[0] == 'blocked'


@pytest.mark.parametrize('adapter', ['api', 'subscription'])
@pytest.mark.parametrize('text', [
    '{"api\\u005fkey":"synthetic-private",',
    '{"local_only":true,"text":"SYNTHETIC_TRAILING"} ordinary suffix',
    '[{"api\\u005fkey":"synthetic-private"}] trailing text',
])
def test_malformed_structured_text_is_blocked_before_model_transport(monkeypatch, adapter, text):
    import responses_api
    from responses_api import ResponsesConversation
    from subscription_api import SubscriptionConversation
    from k90_memory import PrivacyPolicy, PrivacyError
    calls = []
    class Tokens:
        def access_token(self):
            calls.append('token')
            return 'synthetic-token'
    def forbidden(*args, **kwargs):
        calls.append('transport')
        pytest.fail('structured private text escaped outbound policy')
    monkeypatch.setattr(responses_api, 'OpenAI', forbidden)
    with pytest.raises(PrivacyError):
        messages = [{'role': 'user', 'content': text}]
        if adapter == 'api':
            conversation = ResponsesConversation('gpt-6.1-sol', messages)
        else:
            conversation = SubscriptionConversation('demo', messages, policy=PrivacyPolicy(),
                                                    token_store=Tokens(), request=forbidden)
        conversation.complete()
    assert calls == []
    assert PrivacyPolicy().sanitize_text('[Plan](https://example.invalid)') == '[Plan](https://example.invalid)'


@pytest.mark.parametrize('private_first', [True, False])
def test_individually_encoded_local_only_part_stays_local(temp_db, monkeypatch, private_first):
    import memory_runtime as runtime
    from k90_memory import PrivacyPolicy, PrivacyError, Worker
    from k90_memory.store import current
    from tools.db import get_conn
    private = {'type': 'text', 'text': json.dumps({'local_only': True, 'text': 'SYNTHETIC_MULTIPART_PRIVATE'})}
    ordinary = {'type': 'text', 'text': 'Ordinary synthetic continuation'}
    raw = [private, ordinary] if private_first else [ordinary, private]
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize(raw)
    turn = runtime.begin_turn('owner', raw)
    retained, recalled = [], []
    class Backend:
        def retain(self, doc):
            retained.append(doc)
        def recall(self, *args):
            recalled.append(args)
            return []
    backend = Backend()
    with get_conn() as conn:
        source = current(conn, 'owner', turn['source_id'])
        assert source is not None and source.local_only is True
    Worker(get_conn, backend, policy=PrivacyPolicy(), pseudonym_key=b'synthetic-final-key').run_once()
    assert retained == []
    assert runtime.recall_context('owner', 'SYNTHETIC_MULTIPART_PRIVATE')[0] == ''
    monkeypatch.setattr(runtime, 'get_backend', lambda *a, **kw: backend)
    assert runtime.recall_context('owner', raw)[0] == ''
    assert recalled == []


@pytest.mark.parametrize('encoded', [False, True])
def test_semantic_numeric_identifiers_redact_without_leading_zeroes(encoded):
    from k90_memory import PrivacyPolicy
    raw = {'pesel': 10112348, 'nested': {'phone_number': 12345678, 'PESEL': 1},
           'measurements': {'hba1c': 6.2, 'systolic': 120, 'steps': 8000, 'fraction': 0.5}}
    value = json.dumps(raw) if encoded else raw
    clean = PrivacyPolicy().sanitize(value)
    if encoded:
        clean = json.loads(clean)
    assert clean['pesel'] == '[REDACTED]'
    assert clean['nested'] == {'phone_number': '[REDACTED]', 'PESEL': '[REDACTED]'}
    assert clean['measurements'] == raw['measurements']
    assert {k: type(v) for k, v in clean['measurements'].items()} == {k: type(v) for k, v in raw['measurements'].items()}


@pytest.mark.parametrize('rejected', [
    {'scope': 'openid'}, {'id_token': ''}, {'id_token': None}, {'id_token': '***'},
])
def test_rejected_refresh_keeps_latest_token_for_logout_and_blocks_recovery(tmp_path, rejected):
    from subscription_auth import TokenStore, CredentialsError, TOKEN_ENDPOINT
    from subscription_api import SubscriptionConversation
    from k90_memory import PrivacyPolicy
    refreshes, inference, revoked = [], [], []
    def refresh(url, **kwargs):
        refreshes.append(url)
        assert url == TOKEN_ENDPOINT
        return {'access_token': 'synthetic-new-access', 'refresh_token': 'synthetic-new-refresh',
                'expires_in': 3600, 'token_type': 'Bearer', 'client_id': 'untrusted-client', **rejected}
    directory = tmp_path / 'auth'
    store = TokenStore(directory, request=refresh, clock=lambda: 1000)
    store.install({'client_id': 'oaiapp_synthetic', 'subject': 'synthetic-user',
                   'access_token': 'synthetic-old-access', 'refresh_token': 'synthetic-old-refresh',
                   'scope': 'openid resource.invoke chatgpt.tokens.use.direct', 'token_type': 'Bearer',
                   'expires_at': 1001, 'credits_setting_user_confirmed': True})
    def provider(*args, **kwargs):
        inference.append(args)
        pytest.fail('rejected refresh cannot authorize inference')
    def complete(tokens):
        return SubscriptionConversation('demo', [], token_store=tokens, policy=PrivacyPolicy(), request=provider).complete()
    with pytest.raises(CredentialsError):
        complete(store)
    saved = json.loads(store.path.read_text())
    assert saved['pending_refresh']['refresh_token'] == 'synthetic-new-refresh'
    assert saved['pending_refresh']['client_id'] == 'oaiapp_synthetic'
    def offline(url, **kwargs):
        pytest.fail('invalid pending credentials must not refresh old token or fetch keys')
    restarted = TokenStore(directory, request=offline, clock=lambda: 1000)
    for _ in range(2):
        with pytest.raises(CredentialsError):
            complete(restarted)
    assert inference == [] and refreshes == [TOKEN_ENDPOINT]
    def revoke(url, **kwargs):
        assert url.endswith('/revoke')
        revoked.append(kwargs['data'])
        return {}
    restarted.request = revoke
    assert restarted.logout() is True
    assert revoked == [{'client_id': 'oaiapp_synthetic', 'token': 'synthetic-new-refresh',
                        'token_type_hint': 'refresh_token'}]
    assert not restarted.path.exists()
