"""Synthetic receiver-level regressions for the leading JSON text contract."""
import json
from types import SimpleNamespace

import pytest

from k90_memory import PrivacyError, PrivacyPolicy


def encoded(value, layers):
    for _ in range(layers):
        value = json.dumps(value)
    return value


@pytest.mark.parametrize('adapter', ['api', 'subscription'])
@pytest.mark.parametrize('text', [
    '{broken,"api\\u005fkey":"SYNTHETIC_BOUNDARY_SECRET"}',
    '{/*comment*/"api\\u005fkey":"SYNTHETIC_BOUNDARY_SECRET"}',
    '[broken,"api\\u005fkey":"SYNTHETIC_BOUNDARY_SECRET"]',
    encoded('{"api\\u005fkey":"SYNTHETIC_BOUNDARY_SECRET"}', 1),
    encoded('{"api\\u005fkey":"SYNTHETIC_BOUNDARY_SECRET"}', 3),
    encoded('{"local\\u005fonly":true,"text":"SYNTHETIC_BOUNDARY_SECRET"}', 2),
])
def test_leading_json_restrictions_block_before_receivers(monkeypatch, adapter, text):
    import responses_api
    from subscription_api import SubscriptionConversation

    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append('client')
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
            calls.append('token')
            return 'synthetic-token'

    def receiver(url, **kwargs):
        calls.append(kwargs)
        if url.endswith('/models'):
            return {'models': [{'slug': 'demo', 'visibility': 'list'}]}
        return {'status': 'completed', 'output': []}

    monkeypatch.setattr(responses_api, 'OpenAI', Client)
    messages = [{'role': 'user', 'content': text}]
    before = json.dumps(messages)
    with pytest.raises(PrivacyError, match='^outbound content blocked$'):
        if adapter == 'api':
            conversation = responses_api.ResponsesConversation('gpt-6.1-sol', messages)
        else:
            conversation = SubscriptionConversation('demo', messages, token_store=Tokens(),
                                                    policy=PrivacyPolicy(), request=receiver)
        conversation.complete()
    assert calls == []
    assert json.dumps(messages) == before


@pytest.mark.parametrize('text', [
    '[Plan](https://example.invalid)', '[A longer plan](https://example.invalid/path)',
    '[Plan] ordinary Markdown', '[ ] unchecked task', '[x] checked task',
    '[REDACTED] ordinary continuation', 'Ordinary measurements: 120, 6.2',
])
def test_ordinary_bracketed_markdown_remains_unchanged(text):
    assert PrivacyPolicy().sanitize_text(text) == text


def test_decoding_uses_shared_limits_and_preserves_encoding_layers():
    raw = encoded('{"note":"synthetic@example.invalid","bp":120}', 2)
    clean = PrivacyPolicy().sanitize_text(raw)
    assert json.loads(json.loads(json.loads(clean))) == {'note': '[REDACTED]', 'bp': 120}
    assert PrivacyPolicy().sanitize_text(clean) == clean
    for policy in (PrivacyPolicy(max_depth=2), PrivacyPolicy(max_chars=len(raw))):
        with pytest.raises(PrivacyError):
            policy.sanitize_text(raw)
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize({'arguments': '[Plan](https://example.invalid)'})
