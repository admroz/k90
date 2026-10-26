"""Owner-approved opaque image scope; text still uses the basic privacy filter."""
import json

import pytest

from k90_memory import PrivacyError, PrivacyPolicy
from outbound_policy import chat_completion, project_history


# Valid base64 with digit runs that the text phone/PESEL rules would replace.
URI = 'data:image/png;base64,iVBORw0KGgoA' + '12345678901/' * 32


def part(uri=URI):
    return {'type': 'image_url', 'image_url': {'url': uri, 'detail': 'auto'}}


@pytest.mark.parametrize('encoded', [0, 1, 2])
def test_recognized_bytes_never_enter_text_filter(monkeypatch, encoded):
    original = PrivacyPolicy._text
    def guarded(self, text):
        assert URI not in text and '12345678901' not in text
        return original(self, text)
    monkeypatch.setattr(PrivacyPolicy, '_text', guarded)
    value = part()
    for _ in range(encoded):
        value = json.dumps(value)
    clean = PrivacyPolicy(allow_images=True, redact_terms=('12345678901',)).sanitize(value)
    for _ in range(encoded):
        clean = json.loads(clean)
    assert clean == part()


def test_provider_gets_original_bytes_and_filtered_text(monkeypatch):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    monkeypatch.setenv('K90_PRIVACY_REDACT_TERMS', '["12345678901", "Synthetic Name"]')
    payload = {'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'Synthetic Name a@example.invalid +48 600 123 456'}, part()]}],
        'metadata': {'note': 'a@example.invalid'}}
    sent = []
    chat_completion(lambda **kw: sent.append(kw), **payload)
    assert sent[0]['messages'][0]['content'][1] == part()
    assert 'example.invalid' not in json.dumps(sent)
    assert payload['messages'][0]['content'][1] == part()


def test_history_inspects_structure_without_scanning_bytes(monkeypatch):
    original = PrivacyPolicy._text
    def guarded(self, text):
        assert '12345678901' not in text
        return original(self, text)
    monkeypatch.setattr(PrivacyPolicy, '_text', guarded)
    assert project_history(json.dumps([part()])) == [
        {'type': 'text', 'text': '[Historical image omitted]'}]


@pytest.mark.parametrize('value', [
    part('data:image/png;base64,!!!'), part('data:image/png;base64,abc'),
    part('data:application/pdf;base64,YQ=='), part('not-a-url'),
    dict(part(), metadata={'password': 'synthetic'}),
    dict(part(), local_only=True), dict(part(), metadata='a@example.invalid'),
    {'type': 'file', 'data': 'YQ=='}, {'arbitrary': {'base64': 'YQ=='}},
    {'type': 'input_image', 'image_url': URI, 'extra': 'unknown'},
])
def test_unsupported_or_secret_envelope_blocks_transport(monkeypatch, value):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    sent = []
    with pytest.raises(PrivacyError):
        chat_completion(lambda **kw: sent.append(kw), messages=[value])
    assert sent == []


def test_opaque_budget_consent_and_hs_default():
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize(part())
    # Budget contract B1/B2: validated bytes no longer consume text chars.
    policy = PrivacyPolicy(allow_images=True, max_chars=100)
    assert policy.sanitize(part()) == part()
    with pytest.raises(PrivacyError):
        policy.sanitize({'text': 'x' * 101, 'photo': part()})
    # A URI in prose remains textual and cannot inherit opaque treatment.
    assert '12345678901' not in PrivacyPolicy(allow_images=True,
        redact_terms=('12345678901',)).sanitize('meal ' + URI)


def test_responses_envelope_preserves_bytes():
    value = {'type': 'input_image', 'image_url': URI, 'detail': 'high'}
    assert PrivacyPolicy(allow_images=True).sanitize(value) == value


@pytest.mark.parametrize('value', [
    part('https://synthetic.invalid/image?password=synthetic'),
    part('https://synthetic:password@synthetic.invalid/image'),
    {'note': 'password=synthetic', 'photo': part()},
    {'note': '[local-only] synthetic', 'photo': part()},
    {'metadata': json.dumps(json.dumps({'local_only': True})), 'photo': part()},
    {'metadata': '{"broken":', 'photo': part()},
    '{"type":"image_url","image_url":{"url":"' + URI + '","url":"other"}}',
    {'type': 'image_url', 'image_url': {'url': URI, 'password': 'synthetic'}},
    {'type': 'image_url', 'image_url': {'url': URI, 'detail': '[local-only]'}},
    part('data:image/png;base64,YR=='),  # Non-canonical padding bits.
])
@pytest.mark.parametrize('encoded', [False, True])
def test_opaque_scope_keeps_structural_and_text_restrictions(value, encoded):
    if encoded:
        value = json.dumps(value)
    with pytest.raises(PrivacyError):
        PrivacyPolicy(allow_images=True).sanitize(value)


def test_remote_url_and_free_text_are_filtered_not_opaque():
    policy = PrivacyPolicy(allow_images=True, redact_terms=('synthetic-private',))
    remote = part('https://synthetic.invalid/synthetic-private/image')
    assert 'synthetic-private' not in json.dumps(policy.sanitize(remote))
    assert policy.sanitize('HbA1c 6.2%; lunch 150 g; BP 120/80') == 'HbA1c 6.2%; lunch 150 g; BP 120/80'
    for text in ('password=synthetic ' + URI, '[local-only] ' + URI):
        with pytest.raises(PrivacyError):
            policy.sanitize(text)


def test_opaque_nodes_obey_depth_and_total_character_budgets():
    with pytest.raises(PrivacyError):
        PrivacyPolicy(allow_images=True, max_depth=1).sanitize(part())
    policy = PrivacyPolicy(allow_images=True, max_chars=100)
    assert policy.sanitize([part(), part()]) == [part(), part()]
    # Envelope keys/detail still count, cumulatively, as actual text.
    with pytest.raises(PrivacyError):
        policy.sanitize([part()] * 4)


@pytest.mark.parametrize('uri', [
    'data:image/png;base64,cGFzc3dvcmQ9c3ludGhldGlj',
    'data:image/unknown;base64,iVBORw0KGgo=',
    'data:image/jpeg;base64,iVBORw0KGgo=',
])
def test_text_claiming_image_or_wrong_format_is_not_opaque(uri):
    with pytest.raises(PrivacyError):
        PrivacyPolicy(allow_images=True).sanitize(part(uri))


def test_decoded_image_size_limit_blocks_before_transport(monkeypatch):
    import tools.images
    monkeypatch.setattr(tools.images, 'MAX_IMAGE_BYTES', 8)
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    sent = []
    with pytest.raises(PrivacyError):
        chat_completion(lambda **kw: sent.append(kw), messages=[part()])
    assert sent == []
