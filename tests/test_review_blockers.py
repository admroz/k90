"""Independently reported privacy regressions; synthetic data only."""
from copy import deepcopy
import json

import pytest


def test_numeric_identifiers_are_redacted_in_nested_payloads_and_hs_retain():
    from k90_memory import PrivacyPolicy
    from k90_memory.store import Source
    from k90_memory.worker import outbound_document, Identity
    policy = PrivacyPolicy()
    raw = {'content': json.dumps({'pesel': 90010112345, 'nested': {'phone': 600123456},
                                 'measurements': {'hba1c': 6.2, 'systolic': 120, 'steps': 8000}})}
    clean = policy.sanitize(raw)
    parsed = json.loads(clean['content'])
    assert parsed['pesel'] == '[REDACTED]'
    assert parsed['nested']['phone'] == '[REDACTED]'
    assert parsed['measurements'] == {'hba1c': 6.2, 'systolic': 120, 'steps': 8000}
    source = Source('synthetic-source', 'synthetic-owner', 1, 'user', raw['content'], '2026-10-25T00:00:00Z', 'note', False, False)
    document = outbound_document(source, Identity(b'synthetic-key-32-bytes-long-0000'), policy)
    assert json.loads(document.content) == parsed
    assert '90010112345' in raw['content'] and '600123456' in raw['content']


@pytest.mark.parametrize('accepted', [True, False])
def test_rotated_refresh_survives_jwks_outage_without_unverified_inference(tmp_path, accepted):
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm
    from subscription_auth import TokenStore, CredentialsError, TOKEN_ENDPOINT
    from subscription_api import SubscriptionConversation
    from k90_memory import PrivacyPolicy
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk['kid'] = 'synthetic-key'
    claims = {'iss': 'https://auth.openai.com', 'sub': 'synthetic-user' if accepted else 'wrong-user',
              'aud': 'oaiapp_synthetic', 'iat': int(time.time()), 'exp': int(time.time()) + 300}
    signed = jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'synthetic-key'})
    calls, inference = [], []
    def outage(url, **kwargs):
        calls.append(url)
        if url == TOKEN_ENDPOINT:
            assert kwargs['data']['refresh_token'] == 'synthetic-old-refresh'
            return {'access_token': 'synthetic-new-access', 'refresh_token': 'synthetic-rotated-refresh',
                    'id_token': signed, 'expires_in': 3600, 'token_type': 'Bearer'}
        raise RuntimeError('synthetic-jwks-outage')
    store = TokenStore(tmp_path/'auth', request=outage, clock=lambda: 1000)
    store.install({'client_id': 'oaiapp_synthetic', 'subject': 'synthetic-user',
                   'access_token': 'synthetic-old-access', 'refresh_token': 'synthetic-old-refresh',
                   'scope': 'openid resource.invoke chatgpt.tokens.use.direct', 'token_type': 'Bearer',
                   'expires_at': 1001, 'credits_setting_user_confirmed': True})
    def provider(url, **kwargs):
        inference.append(url)
        assert kwargs['token'] == 'synthetic-new-access'
        if url.endswith('/models'):
            return {'models': [{'slug': 'demo', 'visibility': 'list'}]}
        return {'status': 'completed', 'output': []}
    def convo(tokens):
        return SubscriptionConversation('demo', [], token_store=tokens, policy=PrivacyPolicy(), request=provider)
    with pytest.raises(CredentialsError, match='invalid_refresh_identity'):
        convo(store).complete()
    assert inference == []
    path = tmp_path/'auth'/'credentials.json'
    saved = json.loads(path.read_text())
    assert saved['pending_refresh']['refresh_token'] == 'synthetic-rotated-refresh'
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    def recovery(url, **kwargs):
        calls.append(url)
        assert url != TOKEN_ENDPOINT, 'must revalidate pending identity, not reuse rotated refresh'
        return {'keys': [jwk]}
    restarted = TokenStore(tmp_path/'auth', request=recovery, clock=lambda: 1000)
    path.chmod(0o644)
    with pytest.raises(CredentialsError, match='insecure_credentials'):
        convo(restarted).complete()
    path.chmod(0o600)
    if accepted:
        convo(restarted).complete()
        assert len(inference) == 2
        assert 'pending_refresh' not in json.loads(path.read_text())
        assert restarted.access_token() == 'synthetic-new-access'
    else:
        for _ in range(2):
            with pytest.raises(CredentialsError, match='invalid_refresh_identity'):
                convo(restarted).complete()
        assert inference == []
        revoked = []
        restarted.request = lambda url, **kw: revoked.append(kw['data']['token']) or {}
        assert restarted.logout() is True
        assert revoked == ['synthetic-rotated-refresh']
        assert not path.exists()
    assert calls.count(TOKEN_ENDPOINT) == 1



def test_markdown_answer_does_not_poison_next_turn_and_arguments_fail_closed(temp_db, monkeypatch):
    import agent
    from types import SimpleNamespace
    from k90_memory import PrivacyPolicy, PrivacyError
    answer = '[Plan posilkow](https://example.invalid)'
    received = []
    class Message:
        content = answer
        tool_calls = []
        def model_dump(self, **kwargs):
            return {'role': 'assistant', 'content': self.content}
    def provider(**kwargs):
        received.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=Message())], usage=None)
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(agent, 'MODEL', 'gpt-5.4')
    monkeypatch.setattr(agent.litellm, 'completion', provider)
    assert agent.run_agent('Synthetic initial query', 'markdown-owner')[0] == answer
    assert agent.run_agent('Synthetic followup', 'markdown-owner')[0] == answer
    assert len(received) == 2
    assert any(m.get('content') == answer for m in received[1]['messages'])
    for malformed in ('{"note":', '[missing', 'not JSON'):
        with pytest.raises(PrivacyError):
            PrivacyPolicy().sanitize({'type': 'function_call', 'arguments': malformed})
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize({'arguments': '{"nested":{"api\\u005fkey":"private"}}'})



@pytest.mark.parametrize('adapter', ['api', 'subscription'])
@pytest.mark.parametrize('stage', ['original', 'transport'])
def test_multipart_restrictions_survive_normalization(monkeypatch, adapter, stage):
    from k90_memory import PrivacyError, PrivacyPolicy
    from responses_api import ResponsesConversation
    from subscription_api import SubscriptionConversation
    import responses_api
    calls = []
    class Tokens:
        def access_token(self):
            calls.append('token')
            return 'synthetic-token'
    def forbidden(*args, **kwargs):
        calls.append('transport')
        pytest.fail('restricted content must not reach transport')
    monkeypatch.setattr(responses_api, 'OpenAI', forbidden)
    raw = [{'role': 'user', 'content': [{'type': 'text', 'text': 'SYNTHETIC_LOCAL_ONLY', 'local_only': True}]}]
    before = deepcopy(raw)
    with pytest.raises(PrivacyError):
        messages = raw if stage == 'original' else [{'role': 'user', 'content': 'safe'}]
        if adapter == 'api':
            conversation = ResponsesConversation('gpt-6.1-sol', messages)
        else:
            conversation = SubscriptionConversation('demo-model', messages, token_store=Tokens(),
                                                    policy=PrivacyPolicy(), request=forbidden)
        if stage == 'transport':
            conversation.input = deepcopy(raw)
        conversation.complete()
    assert calls == []
    assert raw == before


def test_multipart_local_only_stays_local_in_worker_and_recall(temp_db, monkeypatch):
    import json
    import memory_runtime as runtime
    from tools.db import get_conn
    from k90_memory import Worker, PrivacyPolicy
    from k90_memory.store import current
    raw = [{'type': 'text', 'text': 'SYNTHETIC_PRIVATE_MILLET', 'local_only': True}]
    turn = runtime.begin_turn('synthetic-owner', raw)
    retained, recalled = [], []
    class Backend:
        def retain(self, doc):
            retained.append(doc)
        def recall(self, *args):
            recalled.append(args)
            return []
    backend = Backend()
    Worker(get_conn, backend, policy=PrivacyPolicy(), pseudonym_key=b'synthetic-key-32-bytes-long-0000').run_once()
    context, stats = runtime.recall_context('synthetic-owner', 'SYNTHETIC_PRIVATE_MILLET')
    monkeypatch.setattr(runtime, 'get_backend', lambda *a, **k: backend)
    direct, direct_stats = runtime.recall_context('synthetic-owner', raw)
    with get_conn() as conn:
        assert json.loads(conn.execute('SELECT payload FROM agent_events WHERE id=?', (turn['user_event_id'],)).fetchone()[0]) == raw
        assert current(conn, 'synthetic-owner', turn['source_id']).local_only is True
    assert retained == []
    assert recalled == []
    assert context == direct == ''
    assert stats['memory_blocked'] >= 1 and direct_stats['memory_blocked'] >= 1
