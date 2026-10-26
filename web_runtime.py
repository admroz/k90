"""Durable, serial conversation queue shared by HTTP and Telegram.

Only one backend process may own a database. An interrupted job is never
automatically replayed: a tool may already have performed its side effect.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import closing

from tools.db import MESSAGE_CONTEXT, get_conn, init_db

log = logging.getLogger(__name__)
INTERRUPTED = "Przetwarzanie przerwano podczas restartu. Sprawdź historię i dane przed ponowieniem wiadomości."


def init_runtime():
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
            conn.execute("UPDATE chat_jobs SET user_id = ?", (os.getenv("CONVERSATION_USER_ID", "owner"),))
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, identity TEXT NOT NULL, role TEXT NOT NULL,
            conversation_id INTEGER, job_seq INTEGER,
            UNIQUE(user_id, identity, role)
        )""")
        _index_timeline(conn)


def _index_timeline(conn):
    # Identity, never content or timestamps, joins the two persistence paths.
    candidates = []
    for row in conn.execute("SELECT * FROM conversations ORDER BY id"):
        identity = "request:" + row["request_id"] if row["request_id"] else "legacy:" + str(row["id"])
        candidates.append((row["timestamp"], 1, row["id"], row["user_id"], identity,
                           row["role"], row["id"], None))
    for row in conn.execute("SELECT * FROM chat_jobs WHERE kind = 'message' ORDER BY seq"):
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


def timeline(user_id, before=None, limit=50):
    with closing(get_conn()) as conn, conn:
        _index_timeline(conn)
        rows = conn.execute("""SELECT t.id, t.role, t.user_id,
            COALESCE(j.request_id, c.request_id) AS request_id,
            COALESCE(j.channel, c.channel) AS channel,
            COALESCE(j.created_at, c.timestamp) AS timestamp,
            j.state, CASE WHEN t.role = 'user' THEN COALESCE(j.payload, c.content)
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
    payload = json.dumps(content, ensure_ascii=False)
    with closing(get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
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
        return dict(
            conn.execute(
                "SELECT * FROM chat_jobs WHERE request_id = ?", (request_id,)
            ).fetchone()
        )


def recover_interrupted():
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
                    saved[0] if saved else INTERRUPTED,
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

    user_id = os.getenv("CONVERSATION_USER_ID", "owner")
    text = content if isinstance(content, str) else ""
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
                        log.exception("conversation.sync_failed source=%s", name)
                        warnings.append(name)
            if garmin_changed:
                try:
                    refresh_patient_summary(trigger="auto_sync")
                    mark_summary_refreshed()
                except Exception:
                    log.exception("summary.auto_sync_refresh_failed")
            answer, refresh = run_agent(content, user_id=user_id)
            if refresh:
                try:
                    refresh_patient_summary(trigger="conversation")
                except Exception:
                    log.exception("summary.refresh_failed")
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
        log.info("conversation.claim seq=%d channel=%s", job["seq"], job["channel"])
        token = MESSAGE_CONTEXT.set(
            {"channel": job["channel"], "request_id": job["request_id"]}
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
                response = self.processor(json.loads(job["payload"]))
            state = "done"
        except Exception:
            log.exception("conversation.failed request_id=%s", job["request_id"])
            response = "Nie udało się zakończyć odpowiedzi. Sprawdź dane przed ponowieniem — część operacji mogła zostać wykonana."
            if job["kind"] == "garmin_sync":
                response = "Nie udało się pobrać danych Garmin. Sprawdź połączenie i konfigurację w logach kontenera."
            state = "failed"
        finally:
            MESSAGE_CONTEXT.reset(token)
        with closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE chat_jobs SET state = ?, response = ?, finished_at = CURRENT_TIMESTAMP WHERE seq = ?",
                (state, response, job["seq"]),
            )
        return True

    def run(self):
        if self.refresh_on_start and os.getenv("K90_PREVIEW", "false") != "true":
            try:
                from summary import maybe_refresh_summary

                maybe_refresh_summary()
            except Exception:
                log.exception("summary.startup_refresh_failed")
        while not self.stop.is_set():
            try:
                if not self.run_once():
                    self.stop.wait(0.25)
            except Exception:
                log.exception("conversation.worker_error")
                self.stop.wait(2)
