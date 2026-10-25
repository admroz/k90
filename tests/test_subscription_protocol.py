"""OAuth/transport regressions reused from the validated standalone probe (synthetic only)."""
from pathlib import Path
import io
import json
import unittest
HERE = Path(__file__).resolve().parent
def load_probe():
    import subscription_protocol
    return subscription_protocol

class StreamChecks(unittest.TestCase):
    def test_only_completed_response_is_success(self):
        probe = load_probe()
        self.assertTrue(hasattr(probe, 'read_stream'), 'SSE validation is not implemented')
        response = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]}
        event = {'type': 'response.completed', 'response': response}
        wire = ('data: ' + json.dumps(event) + '\n\n').encode()
        self.assertEqual(probe.read_stream(io.BytesIO(wire)), response)
        with self.assertRaises(probe.ProbeError):
            probe.read_stream(io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"looks OK"}\n\n'))
        for kind in ['response.failed', 'response.incomplete', 'error']:
            bad = ('data: ' + json.dumps({'type': kind, 'response': {'error': {'code': 'subscription_sharing_usage_limit_exceeded'}}}) + '\n\n').encode()
            with self.assertRaises(probe.ProbeError):
                probe.read_stream(io.BytesIO(bad))

class CallbackChecks(unittest.TestCase):
    def test_callback_validates_path_state_duplicates_and_client(self):
        probe = load_probe()
        self.assertTrue(hasattr(probe, 'validate_callback'), 'OAuth callback validation is not implemented')
        good = '/auth/callback?state=state1&code=demo-code&client_id=oaiapp_demo'
        self.assertEqual(probe.validate_callback(good, 'state1'), ('demo-code', 'oaiapp_demo'))
        for path in [good.replace('state1', 'wrong'), good + '&state=state1', good.replace('/auth/callback', '/other'), good.replace('demo-code', ''), good.replace('oaiapp_demo', 'dynamic_agent_client')]:
            with self.assertRaises(probe.ProbeError):
                probe.validate_callback(path, 'state1')
        with self.assertRaises(probe.ProbeError):
            probe.validate_callback(good, 'state1', 'oaiapp_other')
        with self.assertRaises(probe.ProbeError):
            probe.validate_callback('/auth/callback?state=state1&error=access_denied', 'state1')

class IdentityChecks(unittest.TestCase):
    def test_signed_identity_nonce_audience_and_grant_are_required(self):
        probe = load_probe()
        self.assertTrue(hasattr(probe, 'validate_identity'), 'OIDC validation is not implemented')
        import jwt
        import time
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        from jwt.algorithms import RSAAlgorithm
        jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        jwk['kid'] = 'demo'
        claims = {'iss': 'https://auth.openai.com', 'sub': 'synthetic-user', 'aud': 'oaiapp_demo', 'iat': int(time.time()), 'exp': int(time.time()) + 300, 'nonce': 'nonce1'}
        signed = jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'demo'})
        tokens = {'id_token': signed, 'access_token': 'synthetic-not-a-live-token', 'token_type': 'Bearer', 'scope': 'resource.invoke chatgpt.tokens.use.direct'}
        self.assertEqual(probe.validate_identity(tokens, 'oaiapp_demo', 'nonce1', {'keys': [jwk]}), 'synthetic-user')
        for client, nonce in [('other', 'nonce1'), ('oaiapp_demo', 'wrong')]:
            with self.assertRaises(probe.ProbeError):
                probe.validate_identity(tokens, client, nonce, {'keys': [jwk]})
        with self.assertRaises(probe.ProbeError):
            probe.validate_identity({**tokens, 'scope': 'openid'}, 'oaiapp_demo', 'nonce1', {'keys': [jwk]})

class AuthorizationChecks(unittest.TestCase):
    def test_real_loopback_callback_and_signature_checks_keep_tokens_out_of_files(self):
        probe = load_probe()
        self.assertTrue(hasattr(probe, 'authorize'), 'interactive authorization is not implemented')
        import tempfile
        import time
        from urllib.parse import urlsplit, parse_qs, urlencode
        from urllib.request import urlopen
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        from jwt.algorithms import RSAAlgorithm
        jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        jwk['kid'] = 'demo'
        pending = {}
        def browser(url):
            q = parse_qs(urlsplit(url).query)
            self.assertEqual(q['code_challenge_method'], ['S256'])
            self.assertIn('chatgpt.tokens.use.direct', q['scope'][0].split())
            self.assertEqual(urlsplit(q['redirect_uri'][0]).hostname, '127.0.0.1')
            pending.update({k: v[0] for k,v in q.items()})
            callback = q['redirect_uri'][0] + '?' + urlencode({'state': q['state'][0], 'code': 'demo-code', 'client_id': 'oaiapp_demo'})
            with urlopen(callback, timeout=5) as result:
                self.assertEqual(result.status, 200)
        def request(url, **kwargs):
            if url.endswith('/.well-known/openid-configuration'):
                return {'issuer': 'https://auth.openai.com', 'authorization_endpoint': 'https://auth.openai.com/api/accounts/authorize', 'token_endpoint': 'https://auth.openai.com/api/accounts/oauth/token', 'jwks_uri': 'https://auth.openai.com/.well-known/jwks.json'}
            if url.endswith('/.well-known/jwks.json'):
                return {'keys': [jwk]}
            if url.endswith('/oauth/token'):
                data = kwargs['data']
                self.assertEqual(data['client_id'], 'oaiapp_demo')
                self.assertEqual(data['redirect_uri'], pending['redirect_uri'])
                claims = {'iss': 'https://auth.openai.com', 'sub': 'synthetic-user', 'aud': 'oaiapp_demo', 'iat': int(time.time()), 'exp': int(time.time()) + 300, 'nonce': pending['nonce']}
                return {'access_token': 'synthetic-access-token-never-real', 'refresh_token': 'synthetic-refresh-token-never-real', 'token_type': 'Bearer', 'scope': 'resource.invoke chatgpt.tokens.use.direct', 'id_token': jwt.encode(claims, key, algorithm='RS256', headers={'kid':'demo'})}
            self.fail('Unexpected endpoint')
        with tempfile.TemporaryDirectory() as tmp:
            tokens, client = probe.authorize(Path(tmp), open_browser=browser, request=request)
            self.assertEqual(client, 'oaiapp_demo')
            self.assertTrue(tokens['access_token'].startswith('synthetic-'))
            saved = ''.join(p.read_text() for p in Path(tmp).glob('*.json'))
            self.assertNotIn('synthetic-access-token', saved)
            self.assertNotIn('synthetic-refresh-token', saved)
            self.assertNotIn('id_token', saved)
            self.assertEqual((Path(tmp)/'registration.json').stat().st_mode & 0o777, 0o600)

class TransportChecks(unittest.TestCase):
    def test_no_key_fallback_and_no_credential_redirects(self):
        probe = load_probe()
        self.assertTrue(hasattr(probe, 'request_json'), 'restricted transport is not implemented')
        from unittest.mock import Mock, patch
        import os
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-paid-api-key'}):
            with self.assertRaises(probe.ProbeError):
                probe.request_json('https://api.openai.com/v1/models')
        with self.assertRaises(probe.ProbeError):
            probe.request_json('https://example.com/v1/models', token='synthetic-oauth-token')
        connection = Mock()
        response = Mock()
        response.status = 302
        response.read.return_value = b''
        connection.getresponse.return_value = response
        with patch('http.client.HTTPSConnection', return_value=connection) as factory:
            with self.assertRaises(probe.ProbeError):
                probe.request_json('https://api.openai.com/v1/models', token='synthetic-oauth-token')
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(connection.request.call_args.args[:2], ('GET', '/v1/models'))
        self.assertTrue(connection.close.called)
