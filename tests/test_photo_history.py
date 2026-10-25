"""Synthetic history projection regressions; originals must remain local."""
import json
from types import SimpleNamespace

import pytest

import agent
from k90_memory import PrivacyError
from tools.db import get_conn


PHOTO = [{'type': 'text', 'text': 'Synthetic millet lunch'},
         {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,c3ludGhldGlj'}}]


@pytest.mark.parametrize('part', [
    None, 123, 'text', [], [PHOTO[0]], {},
    {'type': 'file_url', 'file_url': {'url': 'https://synthetic.invalid/file'}},
    {'type': 'unrecognized_attachment', 'payload': 'synthetic'},
    {'type': 'text', 'text': 123}, {'type': 'text', 'text': None},
    {'type': 'text', 'text': ['nested']}, {'type': 'text'},
    {'type': 'text', 'text': 'safe', 'extra': 'ambiguous'},
    {'type': ['text'], 'text': 'safe'},
    {'type': 'image_url', 'image_url': {'url': 'https://synthetic.invalid/image', 'detail': []}},
])
def test_invalid_history_part_never_reaches_provider(temp_db, monkeypatch, part):
    monkeypatch.setenv('K90_AGENT_AUTH', 'api')
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'local')
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'false')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    original = json.dumps([*PHOTO, part])
    with get_conn() as conn:
        conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)',
                     ('synthetic-owner', 'user', original))
    def forbidden(**payload):
        pytest.fail('Malformed historical part reached provider')
    monkeypatch.setattr(agent.litellm, 'completion', forbidden)
    with pytest.raises(PrivacyError):
        agent.run_agent('Synthetic followup', 'synthetic-owner')
    with get_conn() as conn:
        assert conn.execute('SELECT content FROM conversations ORDER BY id LIMIT 1').fetchone()[0] == original


@pytest.mark.parametrize('consent', ['false', 'true'])
def test_history_projects_photo_without_rewriting_original(temp_db, monkeypatch, consent):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', consent)
    agent.save_history('synthetic-owner', PHOTO, 'Likely millet; what portion?')
    history = agent.load_history('synthetic-owner')
    assert history[0]['content'] == [PHOTO[0], {'type': 'text', 'text': '[Historical image omitted]'}]
    assert history[1]['content'] == 'Likely millet; what portion?'
    with get_conn() as conn:
        assert json.loads(conn.execute('SELECT content FROM conversations ORDER BY id LIMIT 1').fetchone()[0]) == PHOTO


@pytest.mark.parametrize('extra', [
    {'local_only': True}, {'metadata': {'local_only': True}},
    {'metadata': json.dumps({'local_only': True})},
    {'metadata': json.dumps(json.dumps({'password': 'synthetic'}))},
    {'metadata': '[local-only] synthetic'}, {'metadata': 'Bearer synthetic'},
    {'metadata': '{"broken":'}, {'metadata': '{"x":1,"x":2}'},
    {'metadata': {'attachment': 'synthetic'}},
])
def test_image_metadata_cannot_launder_restrictions(temp_db, monkeypatch, extra):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    photo = [PHOTO[0], dict(PHOTO[1], **extra)]
    with get_conn() as conn:
        conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)',
                     ('synthetic-owner', 'user', json.dumps(photo)))
    with pytest.raises(PrivacyError):
        agent.load_history('synthetic-owner')


@pytest.mark.parametrize('raw', [
    '[{"type":"attachment","file":"synthetic"}]',
    '[{"type":"image_url","image_url":null}]',
    '[{"type":"image_url","image_url":{"url":123}}]',
    '[{"type":"image_url","image_url":{"url":"not-an-image-url"}}]',
    '[{"type":"image_url","image_url":{"url":"data:image/png;base64,!!!"}}]',
    '[{"type":"image_url","image_url":{"url":"synthetic","url":"other"}}]',
    '[{"type":"image_url",',
    json.dumps(json.dumps(PHOTO)),
])
def test_ambiguous_or_arbitrary_history_stays_blocked(temp_db, monkeypatch, raw):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    with get_conn() as conn:
        conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)',
                     ('synthetic-owner', 'user', raw))
    with pytest.raises(PrivacyError):
        agent.load_history('synthetic-owner')


@pytest.mark.parametrize('auth', ['api', 'responses', 'chatgpt'])
@pytest.mark.parametrize('memory', ['local', 'hindsight'])
@pytest.mark.parametrize('followup_consent', ['false', 'true'])
def test_real_agent_upload_then_text_followup(temp_db, monkeypatch, auth, memory, followup_consent):
    import memory_runtime as runtime
    import subscription_api
    import subscription_auth
    import responses_api

    monkeypatch.setenv('K90_AGENT_AUTH', 'api' if auth == 'responses' else auth)
    monkeypatch.setenv('K90_MEMORY_BACKEND', memory)
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    monkeypatch.setattr(agent, 'MODEL', 'gpt-6.1-sol' if auth == 'responses' else 'synthetic-vision')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(runtime, 'start_worker', lambda: None)
    sent, hs_sent, indexed = [], [], []
    answer = 'Likely millet; what portion and preparation?'

    def api_request(**payload):
        sent.append(payload)
        message = SimpleNamespace(content=answer, tool_calls=[],
                                  model_dump=lambda **kw: {'role': 'assistant', 'content': answer})
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    def subscription_request(url, **kwargs):
        if url.endswith('/models'):
            return {'models': [{'slug': 'synthetic-vision', 'visibility': 'list'}]}
        sent.append(kwargs['data'])
        return {'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': answer}]}]}

    class SyntheticOpenAI:
        def __init__(self, **kwargs):
            self.responses = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def create(self, **payload):
            sent.append(payload)
            item = SimpleNamespace(type='message', content=[SimpleNamespace(type='output_text', text=answer)],
                                   model_dump=lambda **kw: {'type': 'message', 'role': 'assistant',
                                       'content': [{'type': 'output_text', 'text': answer}]})
            return SimpleNamespace(status='completed', output=[item], usage=None)

    def hs_transport(method, url, body, timeout, max_bytes):
        payload = json.loads(body) if body else None
        hs_sent.append(payload)
        if url.endswith('/recall'):
            return {'results': [{'type': 'world', 'document_id': item['document_id'],
                                 'metadata': item['metadata']} for item in indexed]}
        assert method == 'POST' and url.endswith('/memories')
        indexed.extend(payload['items'])
        return {'success': True, 'async': False, 'items_count': 1, 'bank_id': 'k90-test-photo-history'}

    monkeypatch.setattr(agent.litellm, 'completion', api_request)
    monkeypatch.setattr(responses_api, 'OpenAI', SyntheticOpenAI)
    monkeypatch.setattr(subscription_api, 'request_json', subscription_request)
    monkeypatch.setattr(subscription_auth, 'TokenStore', lambda *a: SimpleNamespace(access_token=lambda: 'synthetic'))
    if memory == 'hindsight':
        monkeypatch.setenv('K90_HINDSIGHT_URL', 'http://synthetic.invalid:8888')
        monkeypatch.setenv('K90_HINDSIGHT_BANK_ID', 'k90-test-photo-history')
        monkeypatch.setenv('K90_HINDSIGHT_ALLOW_INTERNAL_HTTP', 'true')
        monkeypatch.setenv('K90_HINDSIGHT_ALLOW_UNAUTHENTICATED', 'true')
        monkeypatch.setattr(runtime, '_transport', lambda token: hs_transport)

    assert agent.run_agent(PHOTO, 'synthetic-owner') == (answer, False)
    assert 'data:image/png;base64,c3ludGhldGlj' in json.dumps(sent[0])
    if memory == 'hindsight':
        assert runtime.run_pending(limit=20) == 2
        assert indexed
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', followup_consent)
    assert agent.run_agent('Millet lunch: 150 g, steamed', 'synthetic-owner') == (answer, False)
    assert len(sent) == 2
    followup = json.dumps(sent[1])
    assert 'Historical image omitted' in followup and answer in followup
    assert 'Synthetic millet lunch' in followup and '150 g, steamed' in followup
    assert 'image_url' not in followup and 'input_image' not in followup and 'base64' not in followup
    assert 'base64' not in json.dumps(hs_sent) and 'image_url' not in json.dumps(hs_sent)
    with get_conn() as conn:
        assert json.loads(conn.execute('SELECT content FROM conversations ORDER BY id LIMIT 1').fetchone()[0]) == PHOTO
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
        assert json.loads(conn.execute("SELECT payload FROM agent_events WHERE kind='incoming' ORDER BY id LIMIT 1").fetchone()[0]) == PHOTO


@pytest.mark.parametrize('auth', ['api', 'responses', 'chatgpt'])
def test_new_photo_still_requires_consent(temp_db, monkeypatch, auth):
    import subscription_auth
    import responses_api
    monkeypatch.setenv('K90_AGENT_AUTH', 'api' if auth == 'responses' else auth)
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'local')
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'false')
    monkeypatch.setattr(agent, 'MODEL', 'gpt-6.1-sol' if auth == 'responses' else 'synthetic-vision')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    def forbidden(*a, **kw):
        pytest.fail('Rejected image reached provider or token store')
    monkeypatch.setattr(agent.litellm, 'completion', forbidden)
    monkeypatch.setattr(responses_api, 'OpenAI', forbidden)
    monkeypatch.setattr(subscription_auth, 'TokenStore', lambda *a: SimpleNamespace(access_token=forbidden))
    with pytest.raises(PrivacyError):
        agent.run_agent(PHOTO, 'synthetic-owner')
