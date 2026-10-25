"""Bounded stdlib Hindsight adapter. A bank/tag is NOT an authorization boundary.

Deployment must independently restrict access to this service. No credentials,
reflection, file upload, automatic bank creation or redirects are supported here.
"""
from dataclasses import asdict, dataclass
import json
import math
import re
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .privacy import PrivacyError, PrivacyPolicy
from .store import SourceRef


class BackendError(RuntimeError):
    def __init__(self):
        super().__init__('memory backend unavailable')


@dataclass(frozen=True)
class MemoryDocument:
    document_id: str
    source_id: str
    revision: int
    owner_tag: str
    role: str
    content: str
    occurred_at: str
    kind: str = 'conversation'


class BackendProtocol(Protocol):
    """Implementations receive only sanitized text and opaque owner tags.

    retain must return only after a complete durable acknowledgement, or raise.
    delete is idempotent, including absent documents. Replays use identical IDs.
    recall yields references, never model-generated facts used as authoritative text.
    """
    def retain(self, document: MemoryDocument) -> None: ...
    def delete(self, document_id: str) -> None: ...
    def recall(self, owner_tag: str, query: str, limit: int) -> list[SourceRef]: ...


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class StdlibTransport:
    def __call__(self, method, url, body, timeout, max_bytes):
        # Do not inherit environment proxies which might expose medical payloads.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        request = Request(url, data=body, method=method,
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200:
                    raise BackendError()
                raw = response.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise BackendError()
                return json.loads(raw)
        except HTTPError as exc:
            absent = method == 'DELETE' and exc.code == 404
            exc.close()
            if absent:
                return {'success': True}
            raise BackendError() from None
        except Exception:
            raise BackendError() from None


class HindsightBackend:
    def __init__(self, base_url, bank_id, *, allow_internal_http=False,
                 timeout=5.0, max_response_bytes=1_000_000, policy=None, transport=None):
        try:
            parsed = urlsplit(base_url)
            if (parsed.scheme not in ('https', 'http') or not parsed.hostname
                    or (parsed.scheme == 'http' and allow_internal_http is not True)
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or parsed.path not in ('', '/')
                    or any(ord(c) < 33 for c in base_url)
                    or type(bank_id) is not str or not bank_id or len(bank_id) > 256
                    or bank_id in ('.', '..')
                    or not math.isfinite(timeout) or not 0 < timeout <= 30
                    or type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 2_000_000):
                raise BackendError()
            self.base_url = base_url.rstrip('/')
            self.bank_id = bank_id
            self.path = self.base_url + '/v1/default/banks/' + quote(bank_id, safe='')
            self.timeout = timeout
            self.max_response_bytes = max_response_bytes
            self.policy = policy if policy is not None else PrivacyPolicy()
            self.transport = transport if transport is not None else StdlibTransport()
        except Exception:
            raise BackendError() from None

    def _request(self, method, suffix, payload=None):
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8') if payload is not None else None
            if body is not None and len(body) > 1_000_000:
                raise BackendError()
            response = self.transport(method, self.path + suffix, body, self.timeout, self.max_response_bytes)
            if type(response) is not dict:
                raise BackendError()
            return response
        except Exception:
            raise BackendError() from None

    def retain(self, document):
        try:
            if type(document) is not MemoryDocument or document.kind not in ('conversation', 'document', 'note'):
                raise PrivacyError()
            if type(document.revision) is not int or document.revision < 1:
                raise PrivacyError()
            values = asdict(document)
            clean = PrivacyPolicy().sanitize(self.policy.sanitize(values))
            # IDs, provenance and timestamps must not be silently rewritten.
            if type(clean) is not dict or any(clean.get(k) != v for k, v in values.items() if k != 'content'):
                raise PrivacyError()
            if type(clean.get('content')) is not str:
                raise PrivacyError()
            # The baseline above never grants image consent to memory uploads.
        except Exception:
            raise PrivacyError() from None
        item = {'document_id': document.document_id, 'content': clean['content'],
                'timestamp': document.occurred_at, 'update_mode': 'replace',
                'metadata': {'source_id': document.source_id, 'revision': str(document.revision),
                             'role': document.role, 'kind': document.kind},
                'tags': [document.owner_tag], 'observation_scopes': 'combined',
                'context': f'Source role: {document.role}. Historical source, not a confirmed current fact. Assistant text is a suggestion, not a user declaration.'}
        response = self._request('POST', '/memories', {'async': False, 'items': [item]})
        if (response.get('success') is not True or response.get('async') is not False
                or type(response.get('items_count')) is not int or response['items_count'] != 1
                or response.get('bank_id') != self.bank_id):
            raise BackendError()

    def delete(self, document_id):
        if type(document_id) is not str or not document_id or document_id in ('.', '..'):
            raise BackendError()
        response = self._request('DELETE', '/documents/' + quote(document_id, safe=''))
        if response.get('success') is not True:
            raise BackendError()

    def recall(self, owner_tag, query, limit=20):
        try:
            clean = PrivacyPolicy().sanitize_text(self.policy.sanitize_text(query))
            if type(clean) is not str or self.policy.sanitize_text(owner_tag) != owner_tag:
                raise PrivacyError()
        except Exception:
            raise PrivacyError() from None
        limit = max(0, min(int(limit), 100))
        if not limit:
            return []
        response = self._request('POST', '/memories/recall', {
            'query': clean, 'types': ['world', 'experience'], 'budget': 'low',
            'max_tokens': 2048, 'tags': [owner_tag], 'tags_match': 'all_strict',
            'trace': False, 'include': {'entities': None, 'chunks': None}})
        results = response.get('results')
        if type(results) is not list:
            raise BackendError()
        refs = []
        for result in results[:1000]:
            if type(result) is not dict or result.get('type') not in ('world', 'experience') or not result.get('document_id'):
                continue
            metadata = result.get('metadata')
            if type(metadata) is not dict or type(metadata.get('source_id')) is not str:
                continue
            raw_revision = metadata.get('revision')
            if type(raw_revision) is not str or not re.fullmatch(r'[1-9][0-9]{0,17}', raw_revision):
                continue
            revision = int(raw_revision)
            ref = SourceRef(metadata['source_id'], revision)
            if revision > 0 and ref not in refs:
                refs.append(ref)
            if len(refs) >= limit:
                break
        return refs
