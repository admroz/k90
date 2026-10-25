"""Crash-recoverable bounded outbox. No SQLite transaction spans backend I/O.

Document IDs are stable PER SOURCE REVISION (not merely per source). Hindsight
has no conditional/fenced replace; revision-specific IDs prevent a delayed old
request from overwriting a newer document. Old revisions have durable delete
jobs, and hydration always rejects stale refs even before remote cleanup.
"""
from dataclasses import asdict
import hashlib
import hmac
import json
import math
import time
import uuid

from .backend import BackendProtocol, MemoryDocument
from .privacy import PrivacyError, PrivacyPolicy
from .store import current, hydrate, search_local


class Identity:
    def __init__(self, key):
        if type(key) is not bytes or len(key) < 16:
            raise ValueError('memory pseudonym key required (at least 16 bytes)')
        self.key = key

    def _digest(self, *values):
        raw = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()
        # Letters-only encoding avoids identifier redaction interpreting hash runs
        # as telephone/PESEL. HMAC separates pseudonyms from a guessable owner name.
        return hmac.new(self.key, raw, hashlib.sha256).hexdigest().translate(str.maketrans('0123456789', 'ghijklmnop'))

    def owner_tag(self, owner):
        return 'owner:' + self._digest('owner', owner)

    def document_id(self, owner, source_id, revision):
        return 'k90-' + self._digest('source', owner, source_id) + '-r' + str(revision)


def outbound_document(source, identity, policy):
    """One shared, fail-closed boundary before even a replacement backend."""
    try:
        if source.local_only or source.kind not in ('conversation', 'document', 'note'):
            raise PrivacyError()
        document = MemoryDocument(identity.document_id(source.owner, source.source_id, source.revision),
                                  source.source_id, source.revision, identity.owner_tag(source.owner),
                                  source.role, source.content, source.occurred_at, source.kind)
        values = asdict(document)
        clean = PrivacyPolicy().sanitize(policy.sanitize(values))
        if type(clean) is not dict or any(clean.get(k) != v for k, v in values.items() if k != 'content'):
            raise PrivacyError()
        if type(clean.get('content')) is not str:
            raise PrivacyError()
        # The baseline policy never grants image consent to the index.
        return MemoryDocument(**clean)
    except Exception:
        raise PrivacyError() from None


class Worker:
    def __init__(self, get_conn, backend: BackendProtocol, *, pseudonym_key,
                 policy=None, clock=time.time, lease_seconds=60, retry_seconds=5):
        if (not math.isfinite(lease_seconds) or not 0 < lease_seconds <= 3600
                or not math.isfinite(retry_seconds) or not 0 < retry_seconds <= 3600):
            raise ValueError('invalid worker timing')
        self.get_conn = get_conn
        self.backend = backend
        self.identity = Identity(pseudonym_key)
        self.policy = policy if policy is not None else PrivacyPolicy()
        self.clock = clock
        self.lease_seconds = lease_seconds
        self.retry_seconds = retry_seconds

    def _claim(self):
        conn = self.get_conn()
        try:
            if conn.in_transaction:
                raise ValueError('worker factory must return a fresh connection')
            conn.execute('BEGIN IMMEDIATE')
            now = self.clock()
            row = conn.execute('''SELECT id,owner,source_id,revision,operation,attempts
                FROM memory_outbox WHERE
                (status IN ('pending','retry') AND available_at<=?) OR
                (status='processing' AND lease_until<=?) ORDER BY id LIMIT 1''', (now, now)).fetchone()
            if row is None:
                conn.commit()
                return None
            job = dict(zip(('id', 'owner', 'source_id', 'revision', 'operation', 'attempts'), row))
            job['token'] = uuid.uuid4().hex
            conn.execute("UPDATE memory_outbox SET status='processing',attempts=attempts+1,lease_until=?,token=?,error=NULL WHERE id=?",
                         (now + self.lease_seconds, job['token'], job['id']))
            source = current(conn, job['owner'], job['source_id'])
            conn.commit()
            return job, source
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _finish(self, job, status, error=None):
        conn = self.get_conn()
        try:
            delay = min(3600, self.retry_seconds * 2 ** min(job['attempts'], 10)) if status == 'retry' else 0
            conn.execute('''UPDATE memory_outbox SET status=?,error=?,available_at=?,lease_until=0,token=NULL
                WHERE id=? AND token=? AND status='processing' ''',
                         (status, error, self.clock() + delay, job['id'], job['token']))
            conn.commit()
        finally:
            conn.close()

    def _after_retain(self, job):
        conn = self.get_conn()
        try:
            # Persist cleanup BEFORE acknowledging a stale in-flight write. If the
            # process crashes here, lease recovery repeats this stale branch.
            conn.execute('BEGIN IMMEDIATE')
            source = current(conn, job['owner'], job['source_id'])
            if source is None or source.deleted or source.revision != job['revision']:
                conn.execute("INSERT INTO memory_outbox(owner,source_id,revision,operation) VALUES (?,?,?,'delete')",
                             (job['owner'], job['source_id'], job['revision']))
                conn.commit()
                return 'superseded'
            conn.commit()
            return 'done'
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def run_once(self, limit=20):
        """Process at most limit jobs (capped at 100); caller schedules next tick.

        Returns number claimed, not number successfully indexed. Generic error
        codes only are persisted. BaseException intentionally leaves a lease for
        restart recovery; regular backend exceptions retry with capped backoff.
        """
        count = 0
        for _ in range(max(0, min(int(limit), 100))):
            claimed = self._claim()
            if claimed is None:
                break
            job, source = claimed
            count += 1
            doc_id = self.identity.document_id(job['owner'], job['source_id'], job['revision'])
            try:
                stale = source is None or source.deleted or source.revision != job['revision']
                if job['operation'] == 'delete' or stale:
                    self.backend.delete(doc_id)
                    status = 'superseded' if stale and job['operation'] == 'retain' else 'done'
                else:
                    document = outbound_document(source, self.identity, self.policy)
                    self.backend.retain(document)
                    status = self._after_retain(job)
            except PrivacyError:
                self._finish(job, 'blocked', 'privacy_blocked')
            except Exception:
                self._finish(job, 'retry', 'backend_unavailable')
            else:
                self._finish(job, status)
        return count


def retrieve(conn, owner, query, *, backend=None, pseudonym_key=None, policy=None, limit=20):
    """Return LOCAL ORIGINALS for caller use; sanitize again before any LLM call.

    Optional semantic lookup is bounded by the backend timeout. Any outage,
    malformed response or policy failure falls back to owner-scoped local search;
    local-only results are deliberately still local and are NOT safe to forward.
    """
    limit = max(0, min(int(limit), 100))
    if backend is not None and limit:
        try:
            identity = Identity(pseudonym_key)
            active_policy = policy if policy is not None else PrivacyPolicy()
            clean = PrivacyPolicy().sanitize_text(active_policy.sanitize_text(query))
            if type(clean) is not str:
                raise PrivacyError()
            refs = backend.recall(identity.owner_tag(owner), clean, limit)
            found = hydrate(conn, owner, refs, limit)
            if found:
                return found
        except Exception:
            pass
    return search_local(conn, owner, query, limit)
