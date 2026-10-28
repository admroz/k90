"""Durable, serial conversation queue shared by HTTP and Telegram.

Only one backend process may own a database. An interrupted job is never
automatically replayed: a tool may already have performed its side effect.
"""

from __future__ import annotations

import sys
import json
import logging
import os
import threading
import time
from uuid import uuid4
from contextlib import closing
import profiling
from logging_setup import configure_logging, event

from tools.db import MESSAGE_CONTEXT, get_conn, init_db

INTERRUPTED = "Przetwarzanie przerwano podczas restartu. Sprawdź historię i dane przed ponowieniem wiadomości."


def init_runtime():
    configure_logging()
    profiling.enabled()  # Reject invalid configuration before starting the worker.
    init_db()
    with closing(get_conn()) as conn, conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_jobs (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                channel TEXT NOT NULL,
                payload TEXT NOT NULL,
                chat_id INTEGER,
                state TEXT NOT NULL DEFAULT 'queued',
                response TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                delivery_index INTEGER NOT NULL DEFAULT 0,
                delivered INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS transport_state (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_jobs)")}
        if "kind" not in columns:
            conn.execute("ALTER TABLE chat_jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'message'")
        if "user_id" not in columns:
            conn.execute("ALTER TABLE chat_jobs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'owner'")
            for job in conn.execute('SELECT seq, request_id FROM chat_jobs').fetchall():
                owners = {row[0] for row in conn.execute(
                    'SELECT DISTINCT user_id FROM conversations WHERE request_id=?', (job['request_id'],))}
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='agent_events'").fetchone():
                    owners.update(row[0] for row in conn.execute(
                        'SELECT DISTINCT owner FROM agent_events WHERE request_id=?', (job['request_id'],)))
                owner = next(iter(owners)) if len(owners) == 1 else (
                    '__ambiguous_legacy_owner__' if owners else os.getenv('CONVERSATION_USER_ID', 'owner'))
                conn.execute('UPDATE chat_jobs SET user_id=? WHERE seq=?', (owner, job['seq']))
        for name, kind in (('profile_id', 'TEXT'), ('queued_monotonic', 'REAL'), ('queue_clock_id', 'TEXT')):
            if name not in columns:
                conn.execute(f"ALTER TABLE chat_jobs ADD COLUMN {name} {kind}")
        for row in conn.execute("SELECT seq FROM chat_jobs WHERE profile_id IS NULL").fetchall():
            conn.execute("UPDATE chat_jobs SET profile_id=? WHERE seq=?", (uuid4().hex, row[0]))
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, identity TEXT NOT NULL, role TEXT NOT NULL,
            conversation_id INTEGER, job_seq INTEGER,
            UNIQUE(user_id, identity, role)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS chat_timeline_job ON chat_timeline(job_seq)")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS telegram_albums (
                album_key TEXT PRIMARY KEY, owner TEXT NOT NULL, chat_id INTEGER NOT NULL,
                first_at REAL NOT NULL, last_at REAL NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', error INTEGER NOT NULL DEFAULT 0,
                late_notified INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS telegram_album_parts (
                album_key TEXT NOT NULL, update_id INTEGER NOT NULL UNIQUE,
                message_id INTEGER NOT NULL, caption TEXT NOT NULL, image TEXT,
                PRIMARY KEY(album_key, message_id)
            );
        """)
        _index_timeline(conn)


def _index_timeline(conn):
    # Identity, never content or timestamps, joins the two persistence paths.
    candidates = []
    for row in conn.execute("""SELECT c.id, c.user_id, c.request_id, c.role, c.timestamp
        FROM conversations c LEFT JOIN chat_timeline t ON t.user_id=c.user_id
        AND t.role=c.role AND t.identity=CASE WHEN length(c.request_id)>0
            THEN 'request:' || c.request_id ELSE 'legacy:' || c.id END
        WHERE t.conversation_id IS NOT c.id ORDER BY c.id"""):
        identity = "request:" + row["request_id"] if row["request_id"] else "legacy:" + str(row["id"])
        candidates.append((row["timestamp"], 1, row["id"], row["user_id"], identity,
                           row["role"], row["id"], None))
    for row in conn.execute("""SELECT j.seq, j.user_id, j.request_id, j.created_at
        FROM chat_jobs j WHERE j.kind='message' AND
        (SELECT COUNT(*) FROM chat_timeline t WHERE t.job_seq=j.seq) < 2 ORDER BY j.seq"""):
        for role in ("user", "assistant"):
            candidates.append((row["created_at"], 0, row["seq"], row["user_id"],
                               "request:" + row["request_id"], role, None, row["seq"]))
    for _, _, _, owner, identity, role, conversation, job in sorted(candidates, key=lambda c: c[:3]):
        conn.execute("""INSERT INTO chat_timeline
            (user_id, identity, role, conversation_id, job_seq) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, identity, role) DO UPDATE SET
            conversation_id = COALESCE(excluded.conversation_id, conversation_id),
            job_seq = COALESCE(excluded.job_seq, job_seq)""",
            (owner, identity, role, conversation, job))


@profiling.profiled('projection')
def timeline(user_id, before=None, limit=50):
    with closing(get_conn()) as conn, conn:
        _index_timeline(conn)
        rows = conn.execute("""SELECT t.id, t.role, t.user_id,
            COALESCE(j.request_id, c.request_id) AS request_id,
            COALESCE(j.channel, c.channel) AS channel,
            COALESCE(j.created_at, c.timestamp) AS timestamp,
            j.profile_id, j.seq AS job_id,
            j.state, CASE WHEN t.role = 'user' THEN COALESCE(j.payload, c.content)
                WHEN j.state IN ('failed', 'interrupted') THEN COALESCE(j.response, '')
                ELSE COALESCE(c.content, j.response, '') END AS content
            FROM chat_timeline t
            LEFT JOIN conversations c ON c.id = t.conversation_id AND c.user_id = t.user_id
            LEFT JOIN chat_jobs j ON j.seq = t.job_seq AND j.user_id = t.user_id
            WHERE t.user_id = ? AND t.id < ? ORDER BY t.id DESC LIMIT ?""",
            (user_id, before or 2**63 - 1, limit)).fetchall()
    result = [dict(row) for row in reversed(rows)]
    for row in result:
        if row['role'] == 'user' and row['state'] is not None:
            row['content'] = json.loads(row['content'])
    return result


def set_transport(name, value):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO transport_state VALUES (?, ?, ?)",
            (name, json.dumps(value), time.time()),
        )


def get_transport(name, default=None):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT value FROM transport_state WHERE name = ?", (name,)
        ).fetchone()
    return json.loads(row[0]) if row else default


def enqueue(request_id, content, channel="web", chat_id=None, *, kind="message"):
    if kind not in ("message", "garmin_sync"):
        raise ValueError("Nieznany rodzaj operacji")
    with closing(get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        return _enqueue(conn, request_id, content, channel, chat_id, kind=kind)


def _enqueue(conn, request_id, content, channel="web", chat_id=None, *, kind="message"):
    payload = json.dumps(content, ensure_ascii=False)
    _index_timeline(conn)
    existing = conn.execute(
        "SELECT * FROM chat_jobs WHERE request_id = ?", (request_id,)
    ).fetchone()
    if existing:
        if (existing["payload"], existing["channel"], existing["chat_id"], existing["kind"], existing["user_id"]) != (
            payload,
            channel,
            chat_id,
            kind,
            os.getenv("CONVERSATION_USER_ID", "owner"),
        ):
            raise ValueError("Ten identyfikator wiadomości ma już inną treść.")
        return dict(existing)
    if kind == "garmin_sync":
        active = conn.execute("SELECT * FROM chat_jobs WHERE kind = 'garmin_sync' AND state IN ('queued', 'running') ORDER BY seq LIMIT 1").fetchone()
        if active:
            return dict(active)
    count = conn.execute(
        "SELECT COUNT(*) FROM chat_jobs WHERE state IN ('queued', 'running')"
    ).fetchone()[0]
    if count >= 100:
        raise OverflowError(
            "Kolejka jest pełna. Poczekaj na zakończenie poprzednich wiadomości."
        )
    conn.execute(
        "INSERT INTO chat_jobs (request_id, channel, payload, chat_id, kind, user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (request_id, channel, payload, chat_id, kind, os.getenv("CONVERSATION_USER_ID", "owner")),
    )
    _index_timeline(conn)
    job = dict(
        conn.execute(
            "SELECT * FROM chat_jobs WHERE request_id = ?", (request_id,)
        ).fetchone()
    )
    profile_id = uuid4().hex
    queued = profiling.perf_counter() if profiling.enabled() else None
    conn.execute("UPDATE chat_jobs SET profile_id=?, queued_monotonic=?, queue_clock_id=? WHERE seq=?",
                 (profile_id, queued, profiling.CLOCK_ID, job['seq']))
    job.update(profile_id=profile_id, queued_monotonic=queued, queue_clock_id=profiling.CLOCK_ID)
    with profiling.request_scope(channel, profile_id, job['seq'], scope='submission'):
        profiling.queue_event('start', queued, profiling.CLOCK_ID)
    return job



def recover_interrupted():
    from tools.diet import failure_outcome
    from tools.product_review import known_outcome
    with closing(get_conn()) as conn, conn:
        for row in conn.execute(
            "SELECT request_id, user_id FROM chat_jobs WHERE state = 'running'"
        ).fetchall():
            saved = conn.execute(
                "SELECT content FROM conversations WHERE request_id = ? AND user_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
                (row[0], row[1]),
            ).fetchone()
            conn.execute(
                "UPDATE chat_jobs SET state = ?, response = ?, finished_at = CURRENT_TIMESTAMP WHERE request_id = ?",
                (
                    "done" if saved else "interrupted",
                    saved[0] if saved else (known_outcome(row[1], row[0], conn=conn) or failure_outcome(row[1], row[0], conn=conn)),
                    row[0],
                ),
            )


def process_message(content):
    # Imports happen after local-mode environment variables have been set.
    from agent import run_agent, save_history
    from summary import refresh_patient_summary
    from tools.commands import handle_command
    from tools.garmin import (
        mark_summary_refreshed,
        should_auto_sync_today,
        sync_garmin_data,
        sync_has_changes,
    )
    from tools.libre import should_auto_sync, sync_libre_data

    user_id = MESSAGE_CONTEXT.get().get('user_id', os.getenv("CONVERSATION_USER_ID", "owner"))
    text = content if isinstance(content, str) else ""
    from tools.product_review import intent, interrupt
    if intent(content) is not None:
        # run_agent captures the original and executes only the exact local
        # approval command, before sync/summary or any model work.
        return run_agent(content, user_id=user_id)[0]
    interrupt(user_id)
    if (
        text.strip().lower().split()[:1] == ["/update"]
        and os.getenv("K90_SYNC_ENABLED", "true") == "false"
    ):
        answer = (
            "To lokalna kopia danych. Synchronizacja z Garmin i Libre jest wyłączona."
        )
    elif os.getenv("K90_PREVIEW", "false") == "true":
        if text.strip() in ("/help", "/status", "/debug", "/summary"):
            answer = handle_command(text)
        else:
            answer = "Wiadomość dotarła do wspólnej historii. To tryb podglądu — model AI nie został wywołany. Uruchom lokalnie z --live-agent, aby rozmawiać z agentem na tej kopii danych."
    else:
        answer = handle_command(text) if text else None
        if answer is None:
            warnings = []
            garmin_changed = False
            if os.getenv("K90_SYNC_ENABLED", "true") != "false":
                for name, due, sync in (
                    ("Garmin", should_auto_sync_today, sync_garmin_data),
                    ("Libre", should_auto_sync, sync_libre_data),
                ):
                    try:
                        if not due():
                            continue
                        result = sync(trigger="conversation")
                        if "error" in result:
                            warnings.append(name)
                        elif name == "Garmin" and sync_has_changes(result):
                            garmin_changed = True
                    except Exception:
                        event('conversation.sync_failed', component='web_runtime', level=logging.ERROR, error=sys.exception())
                        warnings.append(name)
            if garmin_changed:
                try:
                    refresh_patient_summary(trigger="auto_sync")
                    mark_summary_refreshed()
                except Exception:
                    event('summary.auto_sync_refresh_failed', component='web_runtime', level=logging.ERROR, error=sys.exception())
            answer, refresh = run_agent(content, user_id=user_id)
            if refresh:
                try:
                    refresh_patient_summary(trigger="conversation")
                except Exception:
                    event('summary.refresh_failed', component='web_runtime', level=logging.ERROR, error=sys.exception())
            if warnings:
                # Store the notice in the same answer seen by both channels.
                answer = (
                    f"Nie udało się odświeżyć danych: {', '.join(warnings)}.\n\n"
                    + answer
                )
                with closing(get_conn()) as conn, conn:
                    conn.execute(
                        "UPDATE conversations SET content = ? WHERE request_id = ? AND role = 'assistant'",
                        (answer, MESSAGE_CONTEXT.get().get("request_id")),
                    )
            return answer
    save_history(user_id, content, answer)
    return answer


class ConversationWorker:
    def __init__(self, processor=None):
        self.refresh_on_start = processor is None
        self.processor = processor or process_message
        self.stop = threading.Event()
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="conversation-worker"
        )

    def start(self):
        recover_interrupted()
        self.thread.start()

    def run_once(self):
        with closing(get_conn()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            job = conn.execute(
                "SELECT * FROM chat_jobs WHERE state = 'queued' ORDER BY seq LIMIT 1"
            ).fetchone()
            if not job:
                return False
            conn.execute(
                "UPDATE chat_jobs SET state = 'running' WHERE seq = ?", (job["seq"],)
            )
        with profiling.request_scope(job['channel'], job['profile_id'], job['seq']):
            profiling.queue_event('finish', job['queued_monotonic'], job['queue_clock_id'])
            return self._run_claimed(job)

    def _run_claimed(self, job):
        event('conversation.claim', component='web_runtime')
        token = MESSAGE_CONTEXT.set(
            {"channel": job["channel"], "request_id": job["request_id"], 'user_id': job['user_id']}
        )
        try:
            if job["kind"] == "garmin_sync":
                # Intentionally bypass agent, slash commands and LLM summaries.
                from tools.garmin import sync_garmin_data

                result = sync_garmin_data(trigger="web_button")
                if "error" in result:
                    raise RuntimeError("Garmin synchronization failed")
                response = "Dane Garmin zostały pobrane."
            else:
                with profiling.span('processing'):
                    response = self.processor(json.loads(job["payload"]))
            state = "done"
        except Exception as exc:
            profiling.failure(exc)
            event('conversation.failed', component='web_runtime', level=logging.ERROR)
            from tools.diet import failure_outcome
            from tools.product_review import known_outcome
            with closing(get_conn()) as conn:
                response = known_outcome(job['user_id'], job['request_id'], conn=conn)
            response = response or failure_outcome(job['user_id'], job['request_id'])
            if job["kind"] == "garmin_sync":
                response = "Nie udało się pobrać danych Garmin. Sprawdź połączenie i konfigurację w logach kontenera."
            state = "failed"
        finally:
            MESSAGE_CONTEXT.reset(token)
        with profiling.span('persistence'), closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE chat_jobs SET state = ?, response = ?, finished_at = CURRENT_TIMESTAMP WHERE seq = ?",
                (state, response, job["seq"]),
            )
        event('job.completed' if state == 'done' else 'job.failed', component='web_runtime',
              response_outcome='completed' if state == 'done' else 'failed',
              delivery_outcome='pending', mutation_outcome='unknown')
        return True

    def run(self):
        if self.refresh_on_start and os.getenv("K90_PREVIEW", "false") != "true":
            try:
                from summary import maybe_refresh_summary

                maybe_refresh_summary()
            except Exception:
                event('summary.startup_refresh_failed', component='web_runtime', level=logging.ERROR, error=sys.exception())
        while not self.stop.is_set():
            try:
                if not self.run_once():
                    self.stop.wait(0.25)
            except Exception:
                event('conversation.worker_error', component='web_runtime', level=logging.ERROR, error=sys.exception())
                self.stop.wait(2)


ALBUM_REJECTED = 'Album odrzucony: maksymalnie 4 zdjęcia JPG/PNG/WebP, każde do 5 MB i łącznie do 10 MB. Wyślij ponownie całą paczkę.'
ALBUM_LATE = 'Album mógł być niekompletny: zdjęcie dotarło po zamknięciu paczki. Sprawdź propozycję i wyślij ponownie wszystkie zdjęcia razem.'


def _album_notice(conn, key, chat_id, text):
    # Transport-only response: no model, draft or partial-photo inference.
    if not conn.execute('SELECT 1 FROM chat_jobs WHERE request_id=?', (key,)).fetchone():
        conn.execute("""INSERT INTO chat_jobs
            (request_id,channel,payload,chat_id,state,response,finished_at,kind,user_id,profile_id)
            VALUES (?,'telegram','""',?,'done',?,CURRENT_TIMESTAMP,'transport_notice',?,?)""",
            (key, chat_id, text, os.getenv('CONVERSATION_USER_ID', 'owner'), uuid4().hex))


def accept_album_part(*, owner, chat_id, group_id, update_id, message_id, text='', image=None, rejected=False, now=None):
    """Durable acceptance precedes adapter offset ack; identity comes from trusted intake."""
    import hashlib
    from tools.images import validate_batch
    now = time.time() if now is None else now
    if image is not None:
        validate_batch([image])
    flush_albums(now=now)
    key = 'telegram:album:' + hashlib.sha256(json.dumps([owner, chat_id, group_id]).encode()).hexdigest()
    with closing(get_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        _cleanup_albums(conn, now)
        row = conn.execute('SELECT * FROM telegram_albums WHERE album_key=?', (key,)).fetchone()
        duplicate = conn.execute('SELECT 1 FROM telegram_album_parts WHERE update_id=? OR (album_key=? AND message_id=?)',
                                 (update_id, key, message_id)).fetchone()
        if duplicate:
            return {'accepted': True}
        if row and row['state'] != 'pending':
            if row['state'] == 'sealed' and not row['late_notified']:
                _album_notice(conn, key+':late', chat_id, ALBUM_LATE)
                conn.execute('UPDATE telegram_albums SET late_notified=1 WHERE album_key=?', (key,))
            return {'accepted': True}
        if not row:
            if conn.execute('SELECT COUNT(*) FROM telegram_albums').fetchone()[0] >= 1000 or conn.execute("SELECT COUNT(*) FROM telegram_albums WHERE state='pending'").fetchone()[0] >= 32:
                raise OverflowError('Inbox albumów jest pełny; ponów później.')
            conn.execute('INSERT INTO telegram_albums(album_key,owner,chat_id,first_at,last_at) VALUES (?,?,?,?,?)',
                         (key,owner,chat_id,now,now))
        photos = [r[0] for r in conn.execute('SELECT image FROM telegram_album_parts WHERE album_key=? AND image IS NOT NULL', (key,))]
        photos += [image] if image else []
        invalid = rejected or not image
        try:
            validate_batch(photos)
        except ValueError:
            invalid = True
        conn.execute('INSERT INTO telegram_album_parts VALUES (?,?,?,?,?)', (key,update_id,message_id,text,image if not invalid else None))
        conn.execute('UPDATE telegram_albums SET last_at=?, error=MAX(error,?) WHERE album_key=?', (now,int(invalid),key))
        if invalid:
            _album_notice(conn, key+':rejected', chat_id, ALBUM_REJECTED)
            conn.execute("UPDATE telegram_albums SET state='rejected' WHERE album_key=?", (key,))
            conn.execute("UPDATE telegram_album_parts SET image=NULL,caption='' WHERE album_key=?", (key,))
    return {'accepted': True}


def _cleanup_albums(conn, now):
    # Keep dedup/seal tombstones seven days, discard private inbox payload on seal.
    expired = [r[0] for r in conn.execute("SELECT album_key FROM telegram_albums WHERE state!='pending' AND last_at<?", (now-7*86400,))]
    for key in expired:
        conn.execute('DELETE FROM telegram_album_parts WHERE album_key=?', (key,))
        conn.execute('DELETE FROM telegram_albums WHERE album_key=?', (key,))


def flush_albums(*, now=None):
    now = time.time() if now is None else now
    with closing(get_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        _cleanup_albums(conn, now)
        rows = conn.execute("SELECT * FROM telegram_albums WHERE state='pending' AND (last_at<=? OR first_at<=?) ORDER BY first_at", (now-2,now-10)).fetchall()
        for row in rows:
            parts = conn.execute('SELECT * FROM telegram_album_parts WHERE album_key=? ORDER BY message_id', (row['album_key'],)).fetchall()
            text = '\n'.join(p['caption'] for p in parts if p['caption']) or 'Przeanalizuj zdjęcia łącznie. Nie zapisuj posiłku bez potwierdzenia, że został zjedzony.'
            content = [{'type':'text','text':text}, *[{'type':'image_url','image_url':{'url':p['image']}} for p in parts]]
            try:
                _enqueue(conn, row['album_key'], content, 'telegram', row['chat_id'])
            except OverflowError:
                continue  # Keep durable pending data until queue capacity is available.
            conn.execute("UPDATE telegram_albums SET state='sealed' WHERE album_key=?", (row['album_key'],))
            conn.execute("UPDATE telegram_album_parts SET image=NULL,caption='' WHERE album_key=?", (row['album_key'],))
    return {'flushed': len(rows)}
