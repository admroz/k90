import json
import pytest


def test_policy_masks_pii_keys_and_nested_arguments_without_mutating():
    from k90_memory import PrivacyPolicy
    policy = PrivacyPolicy(redact_terms=('Kowalski', 'ul. Testowa 7'))
    raw = {'role': 'user', 'content': 'HbA1c 6.2%, Kowalski, ul. Testowa 7; 90010112345; +48 600 123 456; test@example.invalid',
           'tool_calls': [{'id': 'call_123', 'function': {'name': 'lookup', 'arguments': json.dumps({'test@example.invalid': 'Kowalski', 'extra': {'note': '600-123-456'}})}}]}
    before = json.dumps(raw)
    clean = policy.sanitize(raw)
    encoded = json.dumps(clean)
    for forbidden in ('Kowalski', 'Testowa', '90010112345', '600', 'example.invalid'):
        assert forbidden not in encoded
    assert clean['role'] == 'user' and 'HbA1c 6.2%' in clean['content']
    args = json.loads(clean['tool_calls'][0]['function']['arguments'])
    assert '[REDACTED]' in args
    assert json.dumps(raw) == before


@pytest.mark.parametrize('value', [
    'Bearer top-secret-value', 'api_key=really-secret', 'sk-proj-abcdefghijklmnopqrstuv',
    {'extra_args': {'Authorization': 'anything'}},
    {'user-defined': {'password': 'secret'}}, {'local_only': True, 'content': 'private'},
    {'extra': {'type': 'image_url', 'image_url': {'url': 'https://example.invalid/a.png'}}},
    {'content': 'data:image/png;base64,aGVsbG8='}, b'bytes',
])
def test_policy_forbidden_values_fail_closed(value):
    from k90_memory import PrivacyPolicy, PrivacyError
    with pytest.raises(PrivacyError) as exc:
        PrivacyPolicy().sanitize(value)
    assert str(exc.value) == 'outbound content blocked'
    assert exc.value.__cause__ is None


def test_redaction_is_idempotent_and_nested_protocol_secrets_never_bypass():
    from k90_memory import PrivacyPolicy, PrivacyError
    p = PrivacyPolicy()
    clean = p.sanitize_text('test@example.invalid spacer')
    assert p.sanitize_text(clean) == clean
    for value in (
        '[REDACTED] {"api_key": "private"}',
        '{"x": {"api\\u005fkey": "private"}}',
        {'type': 'document', 'source': {'type': 'base64', 'data': 'encoded'}},
        {'arbitrary': {'mime_type': 'image/png', 'data': 'encoded'}},
        {'content': [{'type': 'text', 'text': 'safe'}, {'type': 'video', 'data': 'encoded'}]},
    ):
        with pytest.raises(PrivacyError):
            p.sanitize(value)


def test_phone_formats_and_explicit_local_only_markers():
    from k90_memory import PrivacyPolicy, PrivacyError
    p = PrivacyPolicy()
    for phone in ('+1 (202) 555-0100', '(415) 555-1212', '2025550100', '+44 20 7946 0958', '+48 600 123 456'):
        assert not any(c.isdigit() for c in p.sanitize_text(phone))
    for marker in ('[LOCAL_ONLY] private', '<local-only>private</local-only>'):
        with pytest.raises(PrivacyError):
            p.sanitize_text(marker)
    assert p.sanitize_text('2026-01-01T12:00:00Z HbA1c 6.2% BP 120/80') == '2026-01-01T12:00:00Z HbA1c 6.2% BP 120/80'


def test_protocol_control_fields_cannot_be_silently_rewritten():
    from k90_memory import PrivacyPolicy, PrivacyError
    for terms, value in (
        (('assistant',), {'role': 'assistant', 'content': 'text'}),
        (('call_abc',), {'tool_call_id': 'call_abc', 'content': 'text'}),
        (('role',), {'role': 'user', 'content': 'text'}),
    ):
        with pytest.raises(PrivacyError):
            PrivacyPolicy(redact_terms=terms).sanitize(value)


def test_policy_configuration_depth_cycles_collision_and_image_consent():
    from k90_memory import PrivacyPolicy, PrivacyError
    for terms in ('wrong', ('',), (42,)):
        with pytest.raises(PrivacyError):
            PrivacyPolicy(redact_terms=terms)
    p = PrivacyPolicy(redact_terms=('Alice', 'Bob'))
    with pytest.raises(PrivacyError):
        p.sanitize({'Alice': 1, 'Bob': 2})
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(PrivacyError):
        p.sanitize(cyclic)
    image = {'type': 'image_url', 'image_url': {'url': 'https://example.invalid/a.png'}}
    assert PrivacyPolicy(allow_images=True).sanitize(image) == image
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize(float('nan'))
