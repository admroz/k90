"""One policy immediately before every model-provider call."""
import importlib
import json

import pytest


def test_provider_receives_only_filtered_payload_and_original_stays_local(monkeypatch):
    boundary=importlib.import_module('outbound_policy')
    monkeypatch.setenv('K90_PRIVACY_REDACT_TERMS',json.dumps(['Synthetic Fullname']))
    captured=[]
    payload={'model':'demo','messages':[{'role':'user','content':'Synthetic Fullname synthetic@example.invalid'}]}
    result=boundary.chat_completion(lambda **kwargs:captured.append(kwargs) or 'synthetic-ok',**payload)
    assert result=='synthetic-ok'
    assert 'Synthetic Fullname' not in json.dumps(captured)
    assert 'synthetic@example.invalid' not in json.dumps(captured)
    assert 'Synthetic Fullname' in payload['messages'][0]['content']


def test_bad_filter_config_or_secret_blocks_before_any_provider_call(monkeypatch):
    boundary=importlib.import_module('outbound_policy')
    calls=[]
    invoke=lambda **kw:calls.append(kw)
    monkeypatch.setenv('K90_PRIVACY_REDACT_TERMS','not-valid-json')
    with pytest.raises(boundary.PrivacyError):
        boundary.chat_completion(invoke,model='demo',messages=[])
    monkeypatch.setenv('K90_PRIVACY_REDACT_TERMS','[]')
    with pytest.raises(boundary.PrivacyError):
        boundary.chat_completion(invoke,model='demo',messages=[{'role':'user','content':'Bearer synthetic-secret'}])
    assert calls==[]


def test_vendor_exceptions_never_escape_with_body_or_token():
    boundary=importlib.import_module('outbound_policy')
    def broken(**kw):
        raise RuntimeError('synthetic-private-response and synthetic-secret')
    with pytest.raises(boundary.ModelCallError) as exc:
        boundary.chat_completion(broken,model='demo',messages=[])
    assert str(exc.value)=='model_request_failed'
    assert exc.value.__cause__ is None


def test_disabled_text_filter_keeps_explicit_terms_and_hindsight_baseline(monkeypatch):
    from outbound_policy import sanitize_payload
    from k90_memory import PrivacyPolicy, PrivacyError

    monkeypatch.setenv('K90_TEXT_FILTER_ENABLED', 'false')
    monkeypatch.setenv('K90_PRIVACY_REDACT_TERMS', '["Synthetic Name"]')
    original = {'messages': [{'role': 'user', 'content':
        'Synthetic Name synthetic@example.invalid Bearer synthetic-secret'}]}
    safe = sanitize_payload(original)
    assert safe['messages'][0]['content'] == '[REDACTED] synthetic@example.invalid Bearer synthetic-secret'
    assert 'Synthetic Name' in original['messages'][0]['content']
    with pytest.raises(PrivacyError):
        PrivacyPolicy().sanitize(safe)
    with pytest.raises(PrivacyError):
        sanitize_payload({'messages': [{'role':'user', 'content':'[local-only] synthetic'}]})


@pytest.mark.parametrize('setting', [None, 'true', 'false', 'yes', '1', '', 'TRUE'])
def test_text_filter_configuration_is_strict_and_default_enabled(monkeypatch, setting):
    from outbound_policy import sanitize_payload, PrivacyError
    monkeypatch.delenv('K90_TEXT_FILTER_ENABLED', raising=False)
    if setting is not None:
        monkeypatch.setenv('K90_TEXT_FILTER_ENABLED', setting)
    if setting not in (None, 'true', 'false'):
        with pytest.raises(PrivacyError):
            sanitize_payload('ordinary text')
    else:
        assert sanitize_payload('synthetic@example.invalid') == (
            'synthetic@example.invalid' if setting == 'false' else '[REDACTED]')


@pytest.mark.parametrize('value', [object(), {'password': 'synthetic'}, {'local_only': True},
    {'type':'image_url','image_url':{'url':'https://example.invalid/image.png'}},
    {'arguments':'{"local_only":true}'}, ['x' * 100, 'y' * 100]])
def test_disabled_filter_retains_structure_consent_and_aggregate_limits(monkeypatch, value):
    from outbound_policy import sanitize_payload, PrivacyError
    monkeypatch.setenv('K90_TEXT_FILTER_ENABLED', 'false')
    monkeypatch.setenv('K90_OUTBOUND_MAX_CHARS', '150')
    with pytest.raises(PrivacyError):
        sanitize_payload(value)
