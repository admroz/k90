"""Independent resumed probes, adapted from unchanged review-original-probes.py.
Only synthetic offline fixtures. R1 now MUST raise before the provider boundary.
"""
import json
from types import SimpleNamespace
import pytest
import agent
import memory_runtime
from outbound_policy import project_history
from k90_memory import PrivacyError, PrivacyPolicy
from tools import db
from migrate_csv_to_sqlite import create_schema

@pytest.mark.parametrize('parts', [
    [{'type': 'file_url', 'file_url': {'url': 'https://synthetic.invalid/private.pdf'}}],
    [{'type': 'text', 'text': 123}],
    [None],
    [{'type': 'unrecognized_attachment', 'payload': 'synthetic binary reference'}],
])
def test_malformed_or_unknown_historical_parts_fail_closed(parts, monkeypatch):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    with pytest.raises(PrivacyError):
        project_history(json.dumps(parts))

PHOTO = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,c3ludGhldGlj'}}
BAD_PARTS = [
    {'type': 'file_url', 'file_url': {'url': 'https://synthetic.invalid/private.pdf'}},
    {'type': 'text', 'text': 'safe', 'extra': 'ambiguous'},
    {'type': 'text', 'text': None},
    None,
    {'type': 'image_url', 'image_url': {'url': 'https://synthetic.invalid/image'}, 'metadata': {'local_only': True}},
    {'type': 'image_url', 'image_url': {'url': 'https://synthetic.invalid/image'}, 'metadata': json.dumps(json.dumps({'password': 'synthetic'}))},
    {'type': 'image_url', 'image_url': {'url': 'https://synthetic.invalid/image?password=synthetic'}},
    {'type': 'image_url', 'image_url': {'url': 'https://synthetic.invalid/image', 'detail': 'unknown'}},
    {'type': 'text', 'text': json.dumps(json.dumps({'local_only': True}))},
    {'type': 'text', 'text': '{"x":1,"x":2}'},
]

@pytest.mark.parametrize('consent', ['false', 'true'])
def test_short_history_stable_independent_of_memory(tmp_path, monkeypatch, consent):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'history.db'))
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr(db, '_DB_PATH', str(tmp_path / 'history.db'))
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', consent)
    db.init_db()
    originals = []
    with db.get_conn() as conn:
        for i in range(agent.HISTORY_MESSAGES * 2 + 3):
            role = 'user' if i % 2 == 0 else 'assistant'
            content = json.dumps([{'type': 'text', 'text': 'Synthetic caption ' + str(i)}, PHOTO]) if role == 'user' else 'Synthetic assistant interpretation ' + str(i)
            originals.append((role, content))
            conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)', ('reviewer', role, content))
    observed = []
    for mode in ['local', 'disabled', 'hindsight']:
        monkeypatch.setenv('K90_MEMORY_BACKEND', mode)
        observed.append(agent.load_history('reviewer'))
    assert observed[0] == observed[1] == observed[2]
    assert len(observed[0]) == agent.HISTORY_MESSAGES * 2
    assert [r['role'] for r in observed[0]] == [r[0] for r in originals[-agent.HISTORY_MESSAGES * 2:]]
    assert 'base64' not in json.dumps(observed)
    with db.get_conn() as conn:
        assert [tuple(r) for r in conn.execute('SELECT role,content FROM conversations ORDER BY id')] == originals
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize([PHOTO])

@pytest.mark.parametrize('consent', ['false', 'true'])
@pytest.mark.parametrize('auth', ['api', 'responses', 'chatgpt'])
@pytest.mark.parametrize('bad_part', BAD_PARTS)
def test_adjacent_actual_agent_blocked_before_any_provider(tmp_path, monkeypatch, consent, auth, bad_part):
    import responses_api
    import subscription_auth
    data = tmp_path / 'data'
    data.mkdir()
    monkeypatch.setenv('DATA_DIR', str(data))
    monkeypatch.setenv('DB_PATH', str(data / 'test.db'))
    monkeypatch.setattr(db, '_DB_PATH', str(data / 'test.db'))
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'local')
    monkeypatch.setenv('K90_AGENT_AUTH', 'api' if auth == 'responses' else auth)
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', consent)
    db.init_db()
    original = json.dumps([{'type': 'text', 'text': 'Synthetic meal'}, PHOTO, bad_part])
    with db.get_conn() as conn:
        create_schema(conn)
        conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)', ('reviewer', 'user', original))
    monkeypatch.setattr(agent, 'MODEL', 'gpt-6.1-sol' if auth == 'responses' else 'synthetic')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(memory_runtime, 'start_worker', lambda: None)
    sent = []
    def forbidden(*args, **kwargs):
        sent.append((args, kwargs))
        pytest.fail('Rejected history reached provider or token store')
    monkeypatch.setattr(agent.litellm, 'completion', forbidden)
    monkeypatch.setattr(responses_api, 'OpenAI', forbidden)
    monkeypatch.setattr(subscription_auth, 'TokenStore', forbidden)
    with pytest.raises(PrivacyError):
        agent.run_agent('Synthetic followup', 'reviewer')
    assert not sent
    with db.get_conn() as conn:
        assert conn.execute('SELECT content FROM conversations ORDER BY id LIMIT 1').fetchone()[0] == original
        assert conn.execute('SELECT count(*) FROM conversations').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0

@pytest.mark.parametrize('setting', [None, 'false', 'invalid'])
@pytest.mark.parametrize('auth', ['api', 'responses', 'chatgpt'])
def test_new_upload_default_or_bad_consent_denied(tmp_path, monkeypatch, setting, auth):
    import responses_api
    import subscription_auth
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'new.db'))
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr(db, '_DB_PATH', str(tmp_path / 'new.db'))
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'local')
    monkeypatch.setenv('K90_AGENT_AUTH', 'api' if auth == 'responses' else auth)
    if setting is None:
        monkeypatch.delenv('K90_ALLOW_MODEL_IMAGES', raising=False)
    else:
        monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', setting)
    monkeypatch.setattr(agent, 'MODEL', 'gpt-6.1-sol' if auth == 'responses' else 'synthetic')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(memory_runtime, 'start_worker', lambda: None)
    db.init_db()
    calls = []
    def forbidden(*a, **kw):
        calls.append((a, kw))
        pytest.fail('New image without valid opt-in reached external boundary')
    monkeypatch.setattr(agent.litellm, 'completion', forbidden)
    monkeypatch.setattr(responses_api, 'OpenAI', forbidden)
    monkeypatch.setattr(subscription_auth, 'TokenStore', lambda *a: SimpleNamespace(access_token=forbidden))
    original = [{'type': 'text', 'text': 'Synthetic meal'}, PHOTO]
    with pytest.raises(PrivacyError):
        agent.run_agent(original, 'reviewer')
    assert not calls
    with db.get_conn() as conn:
        assert json.loads(conn.execute("SELECT payload FROM agent_events WHERE kind='incoming'").fetchone()[0]) == original
        assert conn.execute('SELECT count(*) FROM conversations').fetchone()[0] == 0


def test_hs_actual_adapter_never_inherits_model_image_consent(monkeypatch):
    from k90_memory import HindsightBackend, MemoryDocument
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    calls = []
    def forbidden(*args):
        calls.append(args)
        pytest.fail('HS received image data')
    backend = HindsightBackend('https://synthetic.invalid', 'k90-synthetic',
        policy=PrivacyPolicy(allow_images=True), transport=forbidden)
    raw = json.dumps([PHOTO])
    doc = MemoryDocument('synthetic-document', 'synthetic-source', 1, 'owner:synthetic',
        'user', raw, '2026-10-25T12:00:00Z')
    with pytest.raises(PrivacyError):
        backend.retain(doc)
    with pytest.raises(PrivacyError):
        backend.recall('owner:synthetic', raw)
    assert not calls


@pytest.mark.parametrize('consent', ['true', 'false'])
def test_projection_redacts_safe_text_but_never_changes_original(monkeypatch, consent):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', consent)
    monkeypatch.setenv('K90_PRIVACY_REDACT_TERMS', json.dumps(['Synthetic Fullname']))
    raw = json.dumps([{'type': 'text', 'text': 'Synthetic Fullname synthetic@example.invalid'}, PHOTO])
    before = raw
    projected = project_history(raw)
    assert projected == [{'type': 'text', 'text': '[REDACTED] [REDACTED]'},
                         {'type': 'text', 'text': '[Historical image omitted]'}]
    assert raw == before


# Original last reproducer, adapted only to require the correct exception and
# to reach both postconditions after it. Original file remains untouched.
def test_actual_chat_unknown_attachment_must_not_reach_provider(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    monkeypatch.setenv('DATA_DIR', str(data))
    monkeypatch.setenv('DB_PATH', str(data / 'test.db'))
    monkeypatch.setattr(db, '_DB_PATH', str(data / 'test.db'))
    monkeypatch.setenv('K90_MEMORY_BACKEND', 'local')
    monkeypatch.setenv('K90_AGENT_AUTH', 'api')
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'false')
    db.init_db()
    with db.get_conn() as conn:
        create_schema(conn)
        original = json.dumps([
            {'type': 'text', 'text': 'Synthetic meal'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,c3ludGhldGlj'}},
            {'type': 'file_url', 'file_url': {'url': 'https://synthetic.invalid/private.pdf'}},
        ])
        conn.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)', ('reviewer', 'user', original))
    monkeypatch.setattr(agent, 'MODEL', 'synthetic')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(memory_runtime, 'start_worker', lambda: None)
    sent = []
    def completion(**payload):
        sent.append(payload)
        msg = SimpleNamespace(content='Synthetic answer', tool_calls=[], model_dump=lambda **kw: {'role': 'assistant', 'content': 'Synthetic answer'})
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)
    monkeypatch.setattr(agent.litellm, 'completion', completion)
    with pytest.raises(PrivacyError):
        agent.run_agent('Synthetic followup', 'reviewer')
    assert not sent, 'Unknown attachment crossed the provider boundary instead of failing closed'
    with db.get_conn() as conn:
        assert conn.execute('SELECT content FROM conversations ORDER BY id LIMIT 1').fetchone()[0] == original
