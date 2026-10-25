"""Independent k90 ChatGPT credentials. Never reads API keys or other agents' sessions."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile
import time

TOKEN_ENDPOINT = 'https://auth.openai.com/api/accounts/oauth/token'
PLAN_SCOPES = {'resource.invoke', 'chatgpt.tokens.use.direct'}


class CredentialsError(RuntimeError):
    """Only fixed, content-free codes may leave this module."""


def _validate_record(value):
    if not isinstance(value, dict):
        raise CredentialsError('invalid_credentials')
    for key in ('client_id', 'subject', 'access_token', 'refresh_token', 'scope'):
        if not isinstance(value.get(key), str) or not value[key]:
            raise CredentialsError('invalid_credentials')
    if value['client_id'] == 'dynamic_agent_client':
        raise CredentialsError('invalid_credentials')
    if not PLAN_SCOPES <= set(value['scope'].split()):
        raise CredentialsError('plan_permission_missing')
    if str(value.get('token_type', '')).casefold() != 'bearer':
        raise CredentialsError('invalid_credentials')
    expiry = value.get('expires_at')
    if not isinstance(expiry, (int, float)) or isinstance(expiry, bool) or not math.isfinite(expiry) or expiry <= 0:
        raise CredentialsError('invalid_credentials')
    return value


class TokenStore:
    """POSIX lock serializes rotating refresh tokens across threads/processes.

    install() is an internal API: its caller must first verify login identity/grant.
    Permission checks protect other OS users, not root or another process of our UID.
    """
    def __init__(self, directory, *, request=None, clock=time.time):
        self.directory = Path(directory)
        self.path = self.directory/'credentials.json'
        self.request = request
        self.clock = clock

    @contextmanager
    def _locked(self):
        try:
            if self.directory.is_symlink():
                raise CredentialsError('insecure_credential_directory')
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.directory.stat().st_uid != os.getuid():
                raise CredentialsError('insecure_credential_directory')
            self.directory.chmod(0o700)
            fd = os.open(self.directory/'credentials.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
            try:
                os.fchmod(fd, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)
        except OSError:
            raise CredentialsError('credential_storage_error') from None

    def _read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd) as stream:
                info = os.fstat(stream.fileno())
                if info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 65536:
                    raise CredentialsError('insecure_credentials')
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise CredentialsError('invalid_credentials')
            return _validate_record(json.loads(raw))
        except FileNotFoundError:
            raise CredentialsError('login_required') from None
        except (OSError, ValueError, TypeError):
            raise CredentialsError('invalid_credentials') from None

    def _write(self, value):
        value = _validate_record(value)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='.credentials-', dir=self.directory)
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY|os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (OSError, ValueError, TypeError):
            raise CredentialsError('credential_storage_error') from None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def install(self, value):
        """Store a previously verified login, without overwriting another identity."""
        value = _validate_record(dict(value))
        with self._locked():
            if self.path.exists() or self.path.is_symlink():
                old = self._read()
                if (old['client_id'], old['subject']) != (value['client_id'], value['subject']):
                    raise CredentialsError('account_mismatch')
            self._write(value)

    def _call(self, url, **kwargs):
        request = self.request
        if request is None:
            from subscription_protocol import request_json
            request = request_json
        return request(url, **kwargs)

    def _verify_refresh_identity(self, response, old):
        if 'id_token' not in response:
            return
        try:
            import jwt
            token = response['id_token']
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256':
                raise ValueError('algorithm')
            jwks = self._call('https://auth.openai.com/.well-known/jwks.json')
            keys = [j for j in jwks['keys'] if j.get('kid') == header.get('kid')]
            if len(keys) != 1:
                raise ValueError('key')
            key = jwt.PyJWK.from_dict(keys[0], algorithm='RS256').key
            claims = jwt.decode(token, key, algorithms=['RS256'], audience=old['client_id'],
                                issuer='https://auth.openai.com',
                                options={'require': ['exp','iat','iss','aud','sub']})
            if claims['sub'] != old['subject']:
                raise ValueError('subject')
            if 'nonce' in claims and old.get('nonce') and claims['nonce'] != old['nonce']:
                raise ValueError('nonce')
        except Exception:
            raise CredentialsError('invalid_refresh_identity') from None

    def _pending_candidate(self, old):
        candidate = _validate_record(old['pending_refresh'])
        if ('pending_refresh' in candidate
                or any(candidate.get(key) != old.get(key) for key in
                       ('client_id', 'subject', 'nonce', 'credits_setting_user_confirmed'))):
            raise CredentialsError('invalid_refresh_response')
        return candidate

    def logout(self):
        """Clear local tokens even if remote revocation cannot be confirmed."""
        with self._locked():
            try:
                old = self._read()
            except CredentialsError as exc:
                if str(exc) == 'login_required':
                    return True
                raise
            revoked = False
            try:
                # Revocation needs the latest rotated token, not verified access.
                latest = old.get('pending_refresh', old)
                token = latest.get('refresh_token') if isinstance(latest, dict) else None
                if not isinstance(token, str) or not token:
                    raise CredentialsError('invalid_refresh_response')
                self._call('https://auth.openai.com/api/accounts/oauth/revoke', form=True, data={
                    'client_id': old['client_id'], 'token': token,
                    'token_type_hint': 'refresh_token',
                })
                revoked = True
            except BaseException:
                pass
            finally:
                self.path.unlink(missing_ok=True)
            return revoked

    def access_token(self):
        with self._locked():
            old = self._read()
            if old.get('credits_setting_user_confirmed') is not True:
                raise CredentialsError('credits_confirmation_required')
            if 'pending_refresh' in old:
                # A prior rotation succeeded but identity validation did not.
                # Revalidate it under the same lock, never return its access
                # token or reuse the invalidated old refresh token beforehand.
                fresh = self._pending_candidate(old)
                self._verify_refresh_identity(fresh, old)
                self._write(fresh)
                old = fresh
            if old['expires_at'] > self.clock() + 60:
                return old['access_token']
            try:
                response = self._call(TOKEN_ENDPOINT, form=True, data={
                    'grant_type': 'refresh_token', 'client_id': old['client_id'],
                    'refresh_token': old['refresh_token'], 'resource': 'https://api.openai.com/v1',
                })
            except Exception:
                raise CredentialsError('refresh_failed') from None
            if (not isinstance(response, dict) or
                    not isinstance(response.get('access_token'), str) or not response['access_token']):
                raise CredentialsError('invalid_refresh_response')
            expiry = response.get('expires_in')
            if not isinstance(expiry, (int, float)) or isinstance(expiry, bool) or not math.isfinite(expiry) or expiry <= 0:
                raise CredentialsError('invalid_refresh_response')
            fresh = {**old, **{key: response[key] for key in
                ('access_token','refresh_token','id_token','scope','token_type') if key in response},
                'expires_at': self.clock() + expiry}
            if 'id_token' not in response:
                fresh.pop('id_token', None)
            # A successful rotation may narrow scope or provide an invalid ID
            # token. Keep its refresh token for revocation before authorization
            # checks, without ever authorizing the pending access token.
            if isinstance(fresh.get('refresh_token'), str) and fresh['refresh_token']:
                self._write({**old, 'pending_refresh': fresh})
            _validate_record(fresh)
            self._verify_refresh_identity(response, old)
            self._write(fresh)
            return fresh['access_token']
