"""Offline tests for the independent k90 ChatGPT credential store."""
import importlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


def module():
    return importlib.import_module('subscription_auth')


def record(**extra):
    return {'client_id': 'oaiapp_synthetic', 'subject': 'synthetic-user',
            'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
            'id_token': 'synthetic-id', 'token_type': 'Bearer',
            'scope': 'openid resource.invoke chatgpt.tokens.use.direct',
            'credits_setting_user_confirmed': True,
            'expires_at': 2000.0, **extra}


def test_store_keeps_private_permissions_and_does_not_refresh_valid_access(tmp_path):
    auth = module()
    def forbidden(*args, **kwargs):
        pytest.fail('valid access must not invoke token endpoint')
    store = auth.TokenStore(tmp_path/'auth', request=forbidden, clock=lambda: 1000)
    store.install(record())
    assert store.access_token() == 'synthetic-access'
    assert (tmp_path/'auth').stat().st_mode & 0o777 == 0o700
    assert (tmp_path/'auth'/'credentials.json').stat().st_mode & 0o777 == 0o600


def test_rotating_refresh_is_serialized_and_saved_before_other_callers(tmp_path):
    auth = module()
    calls = []
    lock = threading.Lock()
    def request(url, **kwargs):
        with lock:
            calls.append(kwargs)
        assert url == 'https://auth.openai.com/api/accounts/oauth/token'
        assert kwargs['form'] is True
        assert kwargs['data'] == {'grant_type': 'refresh_token', 'client_id': 'oaiapp_synthetic',
                                  'refresh_token': 'synthetic-refresh', 'resource': 'https://api.openai.com/v1'}
        return {'access_token': 'synthetic-new-access', 'refresh_token': 'synthetic-new-refresh',
                'token_type': 'Bearer', 'expires_in': 3600}
    store = auth.TokenStore(tmp_path/'auth', request=request, clock=lambda: 1000)
    store.install(record(expires_at=1001))
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(lambda _: store.access_token(), range(4)))
    assert tokens == ['synthetic-new-access']*4
    assert len(calls) == 1
    saved = json.loads((tmp_path/'auth'/'credentials.json').read_text())
    assert saved['refresh_token'] == 'synthetic-new-refresh'
    assert saved['expires_at'] == 4600


def test_refresh_failure_never_uses_api_key_or_leaks_response(tmp_path, monkeypatch):
    auth = module()
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-paid-key')
    def broken(*args, **kwargs):
        raise RuntimeError('synthetic-refresh-secret and private response body')
    store = auth.TokenStore(tmp_path/'auth', request=broken, clock=lambda: 1000)
    store.install(record(expires_at=1001))
    with pytest.raises(auth.CredentialsError) as exc:
        store.access_token()
    assert str(exc.value) == 'refresh_failed'
    assert exc.value.__cause__ is None


def test_mapping_is_not_silently_overwritten_and_symlinks_are_refused(tmp_path):
    auth = module()
    store = auth.TokenStore(tmp_path/'auth', request=lambda *a, **k: {}, clock=lambda: 1000)
    store.install(record())
    with pytest.raises(auth.CredentialsError, match='account_mismatch'):
        store.install(record(subject='another-synthetic-user'))
    assert store.access_token() == 'synthetic-access'
    token_file = tmp_path/'auth'/'credentials.json'
    elsewhere = tmp_path/'elsewhere'
    token_file.rename(elsewhere)
    token_file.symlink_to(elsewhere)
    with pytest.raises(auth.CredentialsError):
        store.access_token()


@pytest.mark.parametrize('access', [None, '', 42])
def test_refresh_must_supply_a_new_access_token(tmp_path, access):
    auth = module()
    response = {'expires_in': 3600, 'token_type': 'Bearer'}
    if access is not None:
        response['access_token'] = access
    store = auth.TokenStore(tmp_path/'auth', request=lambda *a, **k: response, clock=lambda: 1000)
    store.install(record(expires_at=1001))
    with pytest.raises(auth.CredentialsError, match='invalid_refresh_response'):
        store.access_token()


def test_unconfirmed_extra_credit_setting_blocks_even_valid_access(tmp_path):
    auth = module()
    store = auth.TokenStore(tmp_path/'auth', request=lambda *a, **k: pytest.fail('network forbidden'), clock=lambda: 1000)
    store.install(record(credits_setting_user_confirmed=False))
    with pytest.raises(auth.CredentialsError, match='credits_confirmation_required'):
        store.access_token()


@pytest.mark.parametrize('fails', [False, True])
def test_logout_revokes_latest_session_and_clears_local_tokens_on_failure(tmp_path, fails):
    auth = module()
    calls=[]
    def request(url, **kwargs):
        calls.append((url, kwargs))
        if fails:
            raise RuntimeError('synthetic-private-provider-error')
        return {}
    store=auth.TokenStore(tmp_path/'auth', request=request, clock=lambda:1000)
    store.install(record())
    registration=tmp_path/'auth'/'registration.json'
    registration.write_text('{"host_id":"synthetic-host"}')
    assert store.logout() is (not fails)
    assert not (tmp_path/'auth'/'credentials.json').exists()
    assert registration.exists()
    assert calls[0][0]=='https://auth.openai.com/api/accounts/oauth/revoke'
    assert calls[0][1]['data']['token']=='synthetic-refresh'
    assert calls[0][1]['data']['client_id']=='oaiapp_synthetic'


def test_missing_plan_scope_on_refresh_is_not_accepted(tmp_path):
    auth = module()
    response = {'access_token': 'synthetic-new', 'refresh_token': 'synthetic-new-refresh',
                'expires_in': 3600, 'token_type': 'Bearer', 'scope': 'openid'}
    store = auth.TokenStore(tmp_path/'auth', request=lambda *a, **k: response, clock=lambda: 1000)
    store.install(record(expires_at=1001))
    with pytest.raises(auth.CredentialsError, match='plan_permission_missing'):
        store.access_token()
