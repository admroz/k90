import json
import pytest


class Transport:
    def __init__(self, response=None):
        self.calls = []
        self.response = response

    def __call__(self, method, url, body, timeout, max_bytes):
        self.calls.append((method, url, json.loads(body) if body else None, timeout, max_bytes))
        return self.response


def document(**kwargs):
    from k90_memory import MemoryDocument
    values = dict(document_id='k90-doc-r1', source_id='s1', revision=1,
                  owner_tag='owner:opaque', role='assistant', content='Plan spaceru test@example.invalid',
                  occurred_at='2026-01-01T12:00:00Z', kind='conversation')
    values.update(kwargs)
    return MemoryDocument(**values)


def backend(transport, **kwargs):
    from k90_memory import HindsightBackend
    return HindsightBackend('http://hindsight:8888', 'bank/a?b', allow_internal_http=True,
                            transport=transport, **kwargs)


def test_backend_retain_exact_sync_contract_and_privacy():
    t = Transport({'success': True, 'bank_id': 'bank/a?b', 'items_count': 1, 'async': False})
    b = backend(t)
    b.retain(document())
    method, url, payload, timeout, bound = t.calls[0]
    assert method == 'POST' and url.endswith('/banks/bank%2Fa%3Fb/memories')
    assert payload['async'] is False
    item = payload['items'][0]
    assert item['metadata'] == {'source_id': 's1', 'revision': '1', 'role': 'assistant', 'kind': 'conversation'}
    assert 'example.invalid' not in json.dumps(payload)
    assert item['document_id'] == 'k90-doc-r1' and item['update_mode'] == 'replace'
    assert item['tags'] == ['owner:opaque'] and item['timestamp'] == '2026-01-01T12:00:00Z'
    assert 'assistant' in item['context'] and 0 < timeout <= 30 and bound <= 2_000_000
    b.retain(document())
    assert t.calls[0][2] == t.calls[1][2]


@pytest.mark.parametrize('response', [None, {}, {'success': True, 'async': True},
    {'success': False, 'async': False, 'items_count': 1, 'bank_id': 'bank/a?b'},
    {'success': True, 'async': False, 'items_count': 0, 'bank_id': 'bank/a?b'}])
def test_backend_rejects_incomplete_ack(response):
    from k90_memory import BackendError
    with pytest.raises(BackendError):
        backend(Transport(response)).retain(document())


def test_backend_recall_scope_and_untrusted_results():
    from k90_memory import SourceRef
    t = Transport({'results': [
        {'type': 'world', 'document_id': 'doc', 'metadata': {'source_id': 's1', 'revision': '2'}},
        {'type': 'observation', 'metadata': {'source_id': 's2', 'revision': '2'}},
        {'type': 'experience', 'document_id': 'other', 'metadata': {'source_id': 's2', 'revision': 'bad'}},
        {'text': 'unattributed'}]})
    assert backend(t).recall('owner:opaque', 'test@example.invalid spacer', 3) == [SourceRef('s1', 2)]
    payload = t.calls[0][2]
    assert payload['tags'] == ['owner:opaque'] and payload['tags_match'] == 'all_strict'
    assert payload['types'] == ['world', 'experience']
    assert payload['budget'] == 'low' and payload['max_tokens'] <= 2048
    assert 'example.invalid' not in payload['query']


def test_backend_recall_rejects_noncanonical_metadata_revision():
    t = Transport({'results': [
        {'type': 'world', 'document_id': 'doc', 'metadata': {'source_id': 's', 'revision': rev}}
        for rev in (True, 1.9, '01', '+1', ' 1', '1e0', 1)
    ]})
    assert backend(t).recall('owner:opaque', 'spacer', 20) == []


def test_transport_configuration_forbidden_payload_and_safe_errors():
    from k90_memory import HindsightBackend, BackendError, PrivacyError
    for url in ('http://example.invalid', 'https://u:p@example.invalid', 'https://example.invalid/?x=1', 'file:///tmp/a'):
        with pytest.raises(BackendError):
            HindsightBackend(url, 'bank')
    t = Transport({})
    with pytest.raises(PrivacyError):
        backend(t).retain(document(content='Bearer supersecret'))
    with pytest.raises(PrivacyError):
        backend(t).retain(document(kind='image'))
    with pytest.raises(PrivacyError):
        backend(t).recall('owner:opaque', 'api_key=secret', 2)
    assert t.calls == []
    def broken(*args):
        raise TimeoutError('raw patient secret body')
    with pytest.raises(BackendError) as exc:
        backend(broken).retain(document())
    assert str(exc.value) == 'memory backend unavailable' and exc.value.__cause__ is None


def test_stdlib_transport_blocks_redirects_and_bounds_without_network(monkeypatch):
    from k90_memory.backend import StdlibTransport, NoRedirect
    from urllib.request import Request
    assert NoRedirect().redirect_request(Request('https://example.invalid'), None, 302, '', {}, 'https://evil.invalid') is None
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, count):
            assert count == 11
            return b'x' * count
    class Opener:
        def open(self, request, timeout):
            assert timeout == 2
            return Response()
    monkeypatch.setattr('k90_memory.backend.build_opener', lambda *args: Opener())
    from k90_memory import BackendError
    with pytest.raises(BackendError):
        StdlibTransport()('POST', 'https://example.invalid', b'{}', 2, 10)
