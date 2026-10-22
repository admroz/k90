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


def enqueue(request_id, content, channel="web", chat_id=None):
    payload = json.dumps(content, ensure_ascii=False)
    with closing(get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM chat_jobs WHERE request_id = ?", (request_id,)
        ).fetchone()
        if existing:
            if (existing["payload"], existing["channel"], existing["chat_id"]) != (
                payload,
                channel,
                chat_id,
            ):
                raise ValueError("Ten identyfikator wiadomości ma już inną treść.")
            return dict(existing)
        count = conn.execute(
            "SELECT COUNT(*) FROM chat_jobs WHERE state IN ('queued', 'running')"
        ).fetchone()[0]
        if count >= 100:
            raise OverflowError(
                "Kolejka jest pełna. Poczekaj na zakończenie poprzednich wiadomości."
            )
        conn.execute(
            "INSERT INTO chat_jobs (request_id, channel, payload, chat_id) VALUES (?, ?, ?, ?)",
            (request_id, channel, payload, chat_id),
        )
        return dict(
            conn.execute(
                "SELECT * FROM chat_jobs WHERE request_id = ?", (request_id,)
            ).fetchone()
        )


def recover_interrupted():
    with closing(get_conn()) as conn, conn:
        for row in conn.execute(
            "SELECT request_id FROM chat_jobs WHERE state = 'running'"
        ).fetchall():
            saved = conn.execute(
                "SELECT content FROM conversations WHERE request_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
                (row[0],),
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
        token = MESSAGE_CONTEXT.set(
            {"channel": job["channel"], "request_id": job["request_id"]}
        )
        try:
            response = self.processor(json.loads(job["payload"]))
            state = "done"
        except Exception:
            log.exception("conversation.failed request_id=%s", job["request_id"])
            response = "Nie udało się zakończyć odpowiedzi. Sprawdź dane przed ponowieniem — część operacji mogła zostać wykonana."
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
