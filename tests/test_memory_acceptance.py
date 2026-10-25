"""Offline acceptance across real HTTP routing, queue, SQLite and local memory.

Only the external model/index receivers are synthetic; no private data is used.
"""
from contextlib import closing
import sqlite3
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

import memory_runtime
import patient_documents
from k90_memory import Worker, rebuild_queue
from tools.db import create_db_backup, get_conn


def test_synthetic_demo_http_queue_memory_and_restart(temp_db, monkeypatch):
    import agent
    from scripts.seed_demo import seed
    from webapp import create_app

    monkeypatch.setenv("WEB_PASSWORD", "synthetic-demo-password")
    monkeypatch.setenv("WEB_COOKIE_SECURE", "false")
    monkeypatch.setenv("K90_PREVIEW", "true")
    monkeypatch.setenv("K90_SYNC_ENABLED", "false")
    monkeypatch.setenv("K90_MEMORY_BACKEND", "local")
    monkeypatch.setenv("CONVERSATION_USER_ID", "synthetic-owner")
    monkeypatch.setattr(agent.litellm, "completion", lambda **kw: (_ for _ in ()).throw(AssertionError("preview called model")))
    seed()
    body = {"request_id": "web:synthetic-demo-acceptance", "text": "Synthetic millet breakfast"}
    headers = {"X-K90-Request": "1"}

    def login(client):
        assert client.post("/api/login", json={"password": "synthetic-demo-password"}, headers=headers).status_code == 200

    app = create_app(start_worker=True)
    with TestClient(app) as client:
        assert client.get("/api/dashboard").status_code == 401
        login(client)
        assert client.get("/api/dashboard").status_code == 200
        document = client.get("/api/documents/pacjent.md")
        assert document.status_code == 200
        assert "fikcyjny" in document.json()["content"]
        response = client.post("/api/messages", json=body, headers=headers)
        assert response.status_code == 202, response.text
        deadline = time.monotonic() + 5
        job = None
        while time.monotonic() < deadline:
            with closing(get_conn()) as conn:
                job = conn.execute("SELECT state FROM chat_jobs WHERE request_id=?", (body["request_id"],)).fetchone()
            assert job is not None
            if job[0] in {"done", "failed"}:
                break
            time.sleep(0.05)
        assert job is not None and job[0] == "done"
        assert client.post("/api/messages", json=body, headers=headers).status_code == 202
        messages = client.get("/api/messages").json()
        assert len(messages) == 2
        assert messages[0]["content"] == {"text": body["text"], "has_image": False}
        assert "model AI nie został wywołany" in messages[1]["content"]["text"]
        context, stats = memory_runtime.recall_context("synthetic-owner", "millet breakfast")
        assert body["text"] in context and stats["memory_sources"] == 1
        assert memory_runtime.recall_context("other-owner", "millet breakfast")[0] == ""
        with closing(get_conn()) as conn:
            assert conn.execute("SELECT count(*) FROM agent_events WHERE request_id=?", (body["request_id"],)).fetchone()[0] == 2
            assert conn.execute("SELECT count(*) FROM memory_outbox WHERE status='done'").fetchone()[0] == 0
    assert not app.state.worker.thread.is_alive()

    restarted = create_app(start_worker=True)
    with TestClient(restarted) as client:
        login(client)
        assert client.get("/api/messages").json() == messages
        assert client.get("/api/jobs").json() == []
        assert client.post("/api/messages", json=body, headers=headers).status_code == 202
        assert len(client.get("/api/messages").json()) == 2
    assert not restarted.state.worker.thread.is_alive()


def test_backup_restore_preserves_ledger_key_and_rebuild_identity(temp_db, tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERSATION_USER_ID", "synthetic-owner")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    for name in patient_documents.DOCUMENT_NAMES:
        patient_documents.write_document(name, "Synthetic " + name)
    memory_runtime.begin_turn("synthetic-owner", "Synthetic millet synthetic@example.invalid")

    class IndexReceiver:
        def __init__(self):
            self.documents = {}
        def retain(self, document):
            self.documents[document.document_id] = document
        def delete(self, document_id):
            self.documents.pop(document_id, None)
        def recall(self, owner_tag, query, limit):
            raise AssertionError("backup test must use local recall")

    index = IndexReceiver()
    with closing(get_conn()) as conn:
        key = memory_runtime._key(conn)
    Worker(get_conn, index, pseudonym_key=key).run_once(limit=100)
    before = dict(index.documents)
    assert len(before) == 6
    assert "synthetic@example.invalid" not in repr(before)
    tables = ("patient_documents", "patient_document_revisions", "agent_events", "memory_sources", "memory_versions", "memory_outbox", "memory_settings", "memory_fts")
    with closing(get_conn()) as conn:
        snapshots = {table: sorted([tuple(row) for row in conn.execute("SELECT * FROM " + table)], key=repr) for table in tables}
    backup = create_db_backup(retention_days=30)
    restored_dir = tmp_path / "restored"
    restored_dir.mkdir()
    restored_db = restored_dir / "k90.db"
    with closing(sqlite3.connect(backup["path"])) as src, closing(sqlite3.connect(restored_db)) as dst:
        src.backup(dst)
    monkeypatch.setenv("DB_PATH", str(restored_db))
    monkeypatch.setenv("DATA_DIR", str(restored_dir))
    assert not list(restored_dir.glob("*.md"))
    with closing(get_conn()) as conn, conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for table in tables:
            assert sorted([tuple(row) for row in conn.execute("SELECT * FROM " + table)], key=repr) == snapshots[table]
        memory_runtime.initialize(conn)
        assert memory_runtime._key(conn) == key
        assert rebuild_queue(conn, "synthetic-owner") == 6
    index.documents.clear()
    Worker(get_conn, index, pseudonym_key=key).run_once(limit=100)
    assert index.documents == before
    context, stats = memory_runtime.recall_context("synthetic-owner", "millet")
    assert stats["memory_sources"] == 1
    assert "synthetic@example.invalid" not in context
    assert "millet" in context


def test_agent_recalls_source_outside_short_history_before_model(temp_db, monkeypatch):
    import agent

    monkeypatch.setenv("K90_AGENT_AUTH", "api")
    monkeypatch.setenv("K90_MEMORY_BACKEND", "local")
    monkeypatch.setattr(agent, "MODEL", "gpt-5.4")
    monkeypatch.setattr(agent, "HISTORY_MESSAGES", 1)
    monkeypatch.setattr(agent, "_build_system_message", lambda: ("Synthetic system", {}))
    old_fact = "Synthetic millet breakfast preference synthetic@example.invalid"
    agent.save_history("synthetic-owner", old_fact, "Synthetic historical answer")
    for i in range(3):
        agent.save_history("synthetic-owner", f"Synthetic unrelated turn {i}", "Synthetic unrelated answer")
    assert old_fact not in str(agent.load_history("synthetic-owner"))
    agent.save_history("other-owner", "Synthetic millet other-owner-hidden", "Synthetic hidden answer")
    captured = []

    class ModelMessage:
        content = "Synthetic grounded answer"
        tool_calls = []
        def model_dump(self, **kwargs):
            return {"role": "assistant", "content": self.content}

    def receive(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=ModelMessage())], usage=None)

    monkeypatch.setattr(agent.litellm, "completion", receive)
    assert agent.run_agent("millet breakfast", "synthetic-owner")[0] == "Synthetic grounded answer"
    assert len(captured) == 1
    payload = str(captured[0]["messages"])
    assert "Synthetic millet breakfast preference" in payload
    assert "source_id" in payload and "occurred_at" in payload and "revision" in payload
    assert "synthetic@example.invalid" not in payload
    assert "other-owner-hidden" not in payload
    with closing(get_conn()) as conn:
        assert old_fact == conn.execute("SELECT content FROM conversations WHERE user_id='synthetic-owner' AND role='user' ORDER BY id LIMIT 1").fetchone()[0]
