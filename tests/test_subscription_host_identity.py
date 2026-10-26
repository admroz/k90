"""Synthetic regression for OpenAI SIWC host identifier contract."""
import json
import uuid

import pytest

from subscription_login import initialize_host


def test_new_host_uses_stable_uuid4_urn(tmp_path):
    path = tmp_path / 'auth'
    first = initialize_host(path)
    assert first['host_id'].startswith('urn:uuid:')
    assert uuid.UUID(first['host_id'][9:]).version == 4
    assert initialize_host(path) == first


def test_unregistered_legacy_bare_uuid_is_upgraded_without_rotating_uuid(tmp_path):
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    identifier = '9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c'
    (path / 'registration.json').write_text(json.dumps({'host_id': identifier}))
    assert initialize_host(path)['host_id'] == 'urn:uuid:' + identifier
    assert json.loads((path / 'registration.json').read_text())['host_id'] == 'urn:uuid:' + identifier


@pytest.mark.parametrize('bound', [{'client_id': 'oaiapp_synthetic'}, {'subject': 'synthetic-user'}])
def test_bound_registration_is_never_silently_migrated(tmp_path, bound):
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    original = {'host_id': '9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c', **bound}
    target = path / 'registration.json'
    target.write_text(json.dumps(original))
    try:
        initialize_host(path)
    except Exception:
        pass
    assert json.loads(target.read_text()) == original


def test_already_valid_host_remains_byte_for_byte_stable(tmp_path):
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    original = {'host_id': 'urn:uuid:9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c'}
    target = path / 'registration.json'
    target.write_text(json.dumps(original))
    before = target.read_bytes()
    assert initialize_host(path) == original
    assert target.read_bytes() == before


@pytest.mark.parametrize('kind', ['file', 'symlink', 'dangling_symlink'])
def test_credentials_block_migration_without_being_read(tmp_path, kind, monkeypatch):
    from pathlib import Path
    from subscription_auth import CredentialsError
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    target = path / 'registration.json'
    target.write_text(json.dumps({'host_id': '9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c'}))
    credentials = path / 'credentials.json'
    if kind == 'file':
        credentials.write_text('synthetic unreadable credentials')
    else:
        destination = tmp_path / 'synthetic-secret'
        if kind == 'symlink':
            destination.write_text('synthetic secret')
        credentials.symlink_to(destination)
    before = target.read_bytes()
    original_read = Path.read_text
    def guarded_read(self, *args, **kwargs):
        assert self not in (credentials, tmp_path / 'synthetic-secret')
        return original_read(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', guarded_read)
    with pytest.raises(CredentialsError, match='host_identity_bound'):
        initialize_host(path)
    assert target.read_bytes() == before


@pytest.mark.parametrize('binding', ['client_id', 'subject', 'access_token', 'refresh_token', 'id_token', 'verified', 'credentials'])
def test_even_empty_binding_metadata_blocks_migration(tmp_path, binding):
    from subscription_auth import CredentialsError
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    target = path / 'registration.json'
    target.write_text(json.dumps({'host_id': '9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c', binding: ''}))
    before = target.read_bytes()
    with pytest.raises(CredentialsError, match='host_identity_bound'):
        initialize_host(path)
    assert target.read_bytes() == before


@pytest.mark.parametrize('identifier', [
    'urn:ietf:params:oauth:jwk-thumbprint:sha-256:' + 'a' * 43,
    'did:key:z6MkrJVnaZkeFzdQyMZuHBp3hM6Z4TMH1vFhKx4VAr6U2W8w',
    '9CC7A9D1-9C71-4CE8-920B-A7D2FE45287C',
    '9cc7a9d1-9c71-1ce8-920b-a7d2fe45287c',
])
def test_other_existing_identifiers_are_not_rewritten(tmp_path, identifier):
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    target = path / 'registration.json'
    target.write_text(json.dumps({'host_id': identifier}))
    before = target.read_bytes()
    assert initialize_host(path)['host_id'] == identifier
    assert target.read_bytes() == before


def test_registration_symlink_is_rejected(tmp_path):
    from subscription_auth import CredentialsError
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    target = tmp_path / 'external.json'
    target.write_text('{"host_id":"9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c"}')
    before = target.read_bytes()
    (path / 'registration.json').symlink_to(target)
    with pytest.raises(CredentialsError, match='insecure_registration'):
        initialize_host(path)
    assert target.read_bytes() == before


def test_migration_is_idempotent_and_private(tmp_path):
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    target = path / 'registration.json'
    target.write_text('{"host_id":"9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c"}')
    first = initialize_host(path)
    before = target.read_bytes()
    assert initialize_host(path) == first
    assert target.read_bytes() == before
    assert target.stat().st_mode & 0o777 == 0o600


def test_missing_registration_with_credentials_does_not_create_identity(tmp_path):
    from subscription_auth import CredentialsError
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    (path / 'credentials.json').write_text('synthetic credentials')
    with pytest.raises(CredentialsError, match='host_identity_bound'):
        initialize_host(path)
    assert not (path / 'registration.json').exists()


@pytest.mark.parametrize('identifier', [None,
    '9cc7a9d1-9c71-4ce8-920b-a7d2fe45287c',
    'urn:ietf:params:oauth:jwk-thumbprint:sha-256:' + 'a' * 43,
    'did:key:z6MkrJVnaZkeFzdQyMZuHBp3hM6Z4TMH1vFhKx4VAr6U2W8w',
])
def test_authorize_sends_the_same_initialized_host_id(tmp_path, identifier):
    from urllib.parse import parse_qs, urlsplit
    from subscription_protocol import authorize
    path = tmp_path / 'auth'
    path.mkdir(mode=0o700)
    if identifier:
        (path / 'registration.json').write_text(json.dumps({'host_id': identifier}))
    class BrowserIntercepted(Exception):
        pass
    observed = []
    def browser(url):
        observed.append(parse_qs(urlsplit(url).query)['ext_agent_host_id'][0])
        raise BrowserIntercepted
    def request(url, **kwargs):
        assert url == 'https://auth.openai.com/.well-known/openid-configuration'
        return {'issuer': 'https://auth.openai.com',
                'authorization_endpoint': 'https://auth.openai.com/api/accounts/authorize',
                'token_endpoint': 'https://auth.openai.com/api/accounts/oauth/token',
                'jwks_uri': 'https://auth.openai.com/.well-known/jwks.json'}
    with pytest.raises(BrowserIntercepted):
        authorize(path, open_browser=browser, request=request)
    saved = initialize_host(path)['host_id']
    assert observed == [saved]
    if identifier is None or identifier.startswith('9cc7'):
        assert saved.startswith('urn:uuid:')
    else:
        assert saved == identifier
