"""Synthetic receiver regressions: originals stay local, not evidence of real services."""
import json
import sqlite3
from types import SimpleNamespace

import pytest
from k90_memory import PrivacyError, PrivacyPolicy, Worker
from k90_memory.store import current

MARKER = 'SYNTHETIC_COMPOSITION_PRIVATE'
BOUNDARIES = ['responses', 'subscription', 'chat', 'hs_retain', 'hs_recall']


def dispatch(monkeypatch, boundary, text):
    import responses_api
    from subscription_api import SubscriptionConversation
    from outbound_policy import chat_completion
    from k90_memory.backend import HindsightBackend, MemoryDocument
    calls = []
    class Client:
        def __init__(self, **kw):
            calls.append('client'); self.responses = self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def create(self, **kw):
            calls.append(kw)
            return SimpleNamespace(status='completed', output=[], usage=None)
    class Tokens:
        def access_token(self):
            calls.append('token'); return 'synthetic-token'
    def request(url, **kw):
        calls.append(kw)
        if url.endswith('/models'): return {'models': [{'slug': 'demo', 'visibility': 'list'}]}
        return {'status': 'completed', 'output': []}
    def transport(method, url, body, timeout, max_bytes):
        calls.append(json.loads(body))
        if url.endswith('/recall'): return {'results': []}
        return {'success': True, 'async': False, 'items_count': 1, 'bank_id': 'k90-synthetic'}
    monkeypatch.setattr(responses_api, 'OpenAI', Client)
    messages = [{'role': 'user', 'content': text}]
    original = json.dumps(messages)
    denied = False
    try:
        if boundary == 'responses': responses_api.ResponsesConversation('gpt-6.1-sol', messages).complete()
        elif boundary == 'subscription': SubscriptionConversation('demo', messages, token_store=Tokens(), policy=PrivacyPolicy(), request=request).complete()
        elif boundary == 'chat': chat_completion(lambda **kw: calls.append(kw), model='demo', messages=messages)
        else:
            backend = HindsightBackend('https://synthetic.invalid', 'k90-synthetic', transport=transport)
            if boundary == 'hs_retain': backend.retain(MemoryDocument('k90-synthetic-r1', 'source', 1, 'owner:synthetic', 'user', text, '2026-10-25T00:00:00Z'))
            else: backend.recall('owner:synthetic', text)
    except PrivacyError:
        denied = True
    assert json.dumps(messages) == original
    return denied, calls


@pytest.mark.parametrize('boundary', BOUNDARIES)
@pytest.mark.parametrize('key', [
    '{"api\\u005fkey":"' + MARKER + '"}',
    json.dumps({'local_only': True, 'text': MARKER}),
    json.dumps('{"local\\u005fonly":true,"text":"'+MARKER+'"}'),
    '{broken,"api\\u005fkey":"'+MARKER+'"}',
])
def test_encoded_mapping_key_denied(monkeypatch, boundary, key):
    denied, calls = dispatch(monkeypatch, boundary, json.dumps({key: 'ordinary'}))
    assert denied and calls == []


@pytest.mark.parametrize('boundary', BOUNDARIES)
@pytest.mark.parametrize('key,value', [
    ('"api\\u005fkey"', MARKER),
    ('"local\\u005fonly"', True),
    ('"image\\u005furl"', 'https://example.invalid/image'),
    ('"ph\\u006fne"', 10112348),
])
def test_encoded_scalar_semantic_key_denied(monkeypatch, boundary, key, value):
    denied, calls = dispatch(monkeypatch, boundary, json.dumps({key: value}))
    assert denied and calls == []


@pytest.mark.parametrize('text', ['[Plan](https://example.invalid)', '[x] ordinary task', 'Ordinary **Markdown**', '{"bp":120,"hba1c":6.2}'])
@pytest.mark.parametrize('boundary', BOUNDARIES)
def test_normal_content_reaches_receivers(monkeypatch, boundary, text):
    denied, calls = dispatch(monkeypatch, boundary, text)
    assert not denied and calls


def test_mapping_key_limits_and_protocol_preservation():
    value = {'role': 'user', 'type': 'text', 'content': 'ordinary', '{"bp":120}': 1}
    assert PrivacyPolicy().sanitize(value) == value
    deep = 'ordinary'
    for _ in range(8): deep = json.dumps(deep)
    with pytest.raises(PrivacyError): PrivacyPolicy(max_depth=4).sanitize({deep: 1})
    key = json.dumps({'note': 'x'*40})
    with pytest.raises(PrivacyError): PrivacyPolicy(max_chars=len(key)+5).sanitize({key: 1})


DUPLICATES = [
    '{"local_only":true,"text":"'+MARKER+'","local_only":false}',
    '{"local_only":true,"text":"'+MARKER+'","local\\u005fonly":false}',
    '{"text":"'+MARKER+'","text":"ordinary"}',
    json.dumps('{"local_only":true,"text":"'+MARKER+'","local_only":false}'),
]


@pytest.mark.parametrize('boundary', BOUNDARIES)
@pytest.mark.parametrize('text', DUPLICATES)
def test_duplicate_json_denied(monkeypatch, boundary, text):
    denied, calls = dispatch(monkeypatch, boundary, text)
    assert denied and calls == []


@pytest.mark.parametrize('text', DUPLICATES[:2] + [json.dumps({json.dumps({'local_only': True, 'text': MARKER}): 'ordinary'})])
@pytest.mark.parametrize('ingestion', ['incoming', 'multipart', 'backfill'])
def test_local_ingestion_worker_keeps_original_and_restriction(monkeypatch, tmp_path, text, ingestion):
    import memory_runtime as runtime
    import memory_admin
    db = tmp_path / 'synthetic.db'
    def conn():
        c = sqlite3.connect(db); c.row_factory = sqlite3.Row; return c
    monkeypatch.setattr(runtime, 'get_conn', conn)
    monkeypatch.setattr(memory_admin, 'get_conn', conn)
    monkeypatch.setattr(memory_admin, 'get_db_path', lambda: str(db))
    raw = [{'type': 'text', 'text': 'ordinary'}, {'type': 'text', 'text': text}] if ingestion == 'multipart' else text
    if ingestion == 'backfill':
        with conn() as c:
            c.execute('CREATE TABLE conversations (id INTEGER PRIMARY KEY,user_id TEXT,role TEXT,content TEXT,timestamp TEXT)')
            c.execute('INSERT INTO conversations VALUES (1,?,?,?,?)', ('synthetic-owner', 'user', text, '2026-10-25'))
        assert memory_admin.main(['--owner', 'synthetic-owner', 'backfill', '--apply']) == 0
        source_id = 'conversation:1'
    else:
        turn = runtime.begin_turn('synthetic-owner', raw)
        source_id = turn['source_id']
    retained = []
    class Receiver:
        def retain(self, document): retained.append(document)
        def delete(self, document_id): pass
        def recall(self, owner_tag, query, limit): return []
    assert Worker(conn, Receiver(), policy=PrivacyPolicy(), pseudonym_key=b'synthetic-composition-key').run_once(1) == 1
    with conn() as c:
        source = current(c, 'synthetic-owner', source_id)
        assert source is not None and source.local_only
        assert c.execute('SELECT status FROM memory_outbox').fetchone()[0] == 'blocked'
        if ingestion == 'backfill': assert c.execute('SELECT content FROM conversations').fetchone()[0] == text
        else: assert json.loads(c.execute('SELECT payload FROM agent_events').fetchone()[0]) == raw
    assert retained == []


PRIVATE_DOCUMENT = json.dumps({'local_only': True, 'text': MARKER})


@pytest.mark.parametrize('boundary', ['responses', 'subscription', 'chat'])
def test_summary_sources_checked_before_headings(monkeypatch, boundary):
    import summary
    import patient_documents
    monkeypatch.setattr(patient_documents, 'get_document', lambda name, **kw: {'content': PRIVATE_DOCUMENT} if name == 'pacjent.md' else None)
    denied, calls = False, []
    try:
        parts, _ = summary._load_patient_parts()
        denied, calls = dispatch(monkeypatch, boundary, summary._build_summary_prompt('\n\n'.join(parts)))
    except PrivacyError:
        denied = True
    assert denied and calls == []


def test_actual_summary_refresh_preserves_sqlite_original(temp_db, monkeypatch):
    import summary
    from patient_documents import write_document, get_document
    from tools.db import get_conn
    monkeypatch.setattr(summary, 'DATA_DIR', temp_db.parent / 'data')
    write_document('pacjent.md', PRIVATE_DOCUMENT)
    monkeypatch.setattr(summary, 'SUMMARY_MODEL', 'synthetic-chat')
    monkeypatch.setenv('K90_SUMMARY_AUTH', 'api')
    calls = []
    def receiver(**kw):
        calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='\n'.join(label+' ordinary' for label in summary.SUMMARY_LABELS)))])
    monkeypatch.setattr(summary.litellm, 'completion', receiver)
    with pytest.raises(PrivacyError): summary.refresh_patient_summary('synthetic')
    assert calls == []
    document = get_document('pacjent.md')
    assert document is not None and document['content'] == PRIVATE_DOCUMENT
    with get_conn() as c: assert c.execute('SELECT count(*) FROM patient_summary').fetchone()[0] == 0


@pytest.mark.parametrize('part', ['prompt', 'summary', 'operational'])
def test_system_sources_checked_before_prefix(monkeypatch, part):
    import agent
    import summary
    monkeypatch.setattr(agent, 'SYSTEM_PROMPT', PRIVATE_DOCUMENT if part == 'prompt' else 'Ordinary system')
    monkeypatch.setattr(summary, 'load_patient_summary', lambda: PRIVATE_DOCUMENT if part == 'summary' else '')
    monkeypatch.setattr(agent, 'build_operational_context', lambda: (PRIVATE_DOCUMENT if part == 'operational' else '', {}))
    with pytest.raises(PrivacyError): agent._build_system_message()


def test_operational_raw_row_checked_before_formatting(temp_db):
    from tools.db import get_conn
    from tools.context import build_operational_context
    from tools.time_utils import today_local
    with get_conn() as c:
        c.execute('INSERT INTO posilki(data,opis) VALUES (?,?)', (today_local(), PRIVATE_DOCUMENT))
    with pytest.raises(PrivacyError): build_operational_context()


def test_history_duplicate_multipart_checked_before_decode(temp_db):
    import agent
    from tools.db import get_conn
    raw = '[{"type":"text","local_only":true,"text":"'+MARKER+'","local_only":false}]'
    with get_conn() as c:
        c.execute('INSERT INTO conversations(user_id,role,content) VALUES (?,?,?)', ('synthetic', 'user', raw))
    with pytest.raises(PrivacyError): agent.load_history('synthetic')
    with get_conn() as c: assert c.execute('SELECT content FROM conversations').fetchone()[0] == raw


def test_recall_metadata_checked_before_serialization(temp_db, monkeypatch):
    import memory_runtime as runtime
    source = SimpleNamespace(source_id=PRIVATE_DOCUMENT, revision=1, role='user', occurred_at='2026-10-25', content='ordinary', local_only=False)
    monkeypatch.setattr(runtime, 'retrieve', lambda *a, **kw: [source])
    context, stats = runtime.recall_context('synthetic', 'ordinary')
    assert context == '' and stats['memory_blocked'] == 1


def test_document_snapshot_carries_source_restriction(temp_db):
    from patient_documents import write_document
    from tools.db import get_conn
    write_document('pacjent.md', PRIVATE_DOCUMENT)
    with get_conn() as c:
        source = current(c, 'owner', 'document:pacjent.md')
        assert source is not None and source.local_only


@pytest.mark.parametrize('boundary', ['responses', 'subscription', 'chat'])
def test_tool_document_result_keeps_restriction_to_receiver(temp_db, monkeypatch, boundary):
    from patient_documents import write_document
    from tools.patient import read_patient_file
    write_document('pacjent.md', PRIVATE_DOCUMENT)
    result = read_patient_file('pacjent.md')
    denied, calls = dispatch(monkeypatch, boundary, json.dumps(result))
    assert denied and calls == []
    assert result['content'] == PRIVATE_DOCUMENT


def test_summary_markdown_redaction_fallback_uses_safe_copies(temp_db, monkeypatch):
    import summary
    from patient_documents import write_document, get_document
    original = '[Plan](https://example.invalid)\n\nContact synthetic@example.invalid'
    monkeypatch.setattr(summary, 'DATA_DIR', temp_db.parent / 'data')
    write_document('pacjent.md', original)
    parts, contents = summary._load_patient_parts()
    assert '[Plan](https://example.invalid)' in parts[0]
    assert 'synthetic@example.invalid' not in '\n'.join(parts)
    fallback = summary._fallback_summary(contents)
    assert 'synthetic@example.invalid' not in fallback and '[REDACTED]' in fallback
    document = get_document('pacjent.md')
    assert document is not None and document['content'] == original


def test_duplicate_tool_arguments_rejected_before_execution(monkeypatch):
    import agent
    monkeypatch.setattr(agent, 'load_history', lambda owner: [])
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('ordinary', {}))
    monkeypatch.setattr(agent.memory_runtime, 'recall_context', lambda *a, **kw: ('', {}))
    monkeypatch.setattr(agent, 'MODEL', 'synthetic-chat')
    monkeypatch.setenv('K90_AGENT_AUTH', 'api')
    args = DUPLICATES[0]
    call = SimpleNamespace(id='synthetic-call', function=SimpleNamespace(name='update_patient_file', arguments=args))
    message = SimpleNamespace(tool_calls=[call], content='', model_dump=lambda **kw: {
        'role': 'assistant', 'content': '', 'tool_calls': [{'id': call.id, 'type': 'function',
            'function': {'name': call.function.name, 'arguments': args}}]})
    monkeypatch.setattr(agent.litellm, 'completion', lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None))
    executed = []
    monkeypatch.setattr(agent, 'execute_tool', lambda *a: executed.append(a) or {'ok': True})
    with pytest.raises(PrivacyError): agent._run_agent('ordinary', 'synthetic')
    assert executed == []
