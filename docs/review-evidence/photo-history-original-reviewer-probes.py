"""Independent synthetic offline probes; no repository source modifications."""
import json
from types import SimpleNamespace
import pytest
import agent
import memory_runtime
from outbound_policy import project_history
from k90_memory import PrivacyError
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
    result = agent.run_agent('Synthetic followup', 'reviewer')
    with db.get_conn() as conn:
        assert conn.execute('SELECT content FROM conversations ORDER BY id LIMIT 1').fetchone()[0] == original
    print('Observed result:', result)
    print('Intercepted outbound historical content:', json.dumps(sent[0]['messages'][1]['content']))
    assert not sent, 'Unknown attachment crossed the provider boundary instead of failing closed'
