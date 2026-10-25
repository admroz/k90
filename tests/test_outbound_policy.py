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
