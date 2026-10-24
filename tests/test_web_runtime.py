from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from tools.db import MESSAGE_CONTEXT, get_conn
from web_runtime import ConversationWorker, enqueue, init_runtime, recover_interrupted


@pytest.fixture
def runtime(temp_db, monkeypatch):
    monkeypatch.setenv("CONVERSATION_USER_ID", "owner")
    monkeypatch.setenv("K90_PREVIEW", "true")
    monkeypatch.setenv("K90_SYNC_ENABLED", "false")
    init_runtime()


def test_concurrent_retries_enqueue_once(runtime):
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = list(pool.map(lambda _: enqueue("web:same", "hello"), range(12)))
    assert len({j["seq"] for j in jobs}) == 1
    with closing(get_conn()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_jobs").fetchone()[0] == 1


def test_channels_processed_in_order_and_share_context(runtime):
    from agent import load_history

    enqueue("telegram:1", "from phone", "telegram", 123)
    enqueue("web:2", "from browser")
    worker = ConversationWorker()
    assert worker.run_once() and worker.run_once()
    assert not worker.run_once()
    rows = load_history("owner")
    assert [r["content"] for r in rows if r["role"] == "user"] == [
        "from phone",
        "from browser",
    ]
    with closing(get_conn()) as conn:
        channels = [
            r[0] for r in conn.execute("SELECT channel FROM conversations ORDER BY id")
        ]
    assert channels == ["telegram", "telegram", "web", "web"]
    assert MESSAGE_CONTEXT.get() == {}


def test_interrupted_job_not_replayed_but_queued_job_survives(runtime):
    enqueue("web:started", "possibly changed data")
    enqueue("web:queued", "still waiting")
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE chat_jobs SET state = 'running' WHERE request_id = 'web:started'"
        )
    recover_interrupted()
    calls = []
    worker = ConversationWorker(lambda content: calls.append(content) or "done")
    assert worker.run_once()
    assert not worker.run_once()
    assert calls == ["still waiting"]
    with closing(get_conn()) as conn:
        assert (
            conn.execute(
                "SELECT state FROM chat_jobs WHERE request_id = 'web:started'"
            ).fetchone()[0]
            == "interrupted"
        )


def test_recovery_uses_already_saved_answer_without_running_agent(runtime):
    enqueue("telegram:1", "hello", "telegram", 123)
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE chat_jobs SET state = 'running'")
        conn.execute(
            "INSERT INTO conversations (user_id,role,content,request_id) VALUES ('owner', 'assistant', 'Saved answer', 'telegram:1')"
        )
    recover_interrupted()
    with closing(get_conn()) as conn:
        job = conn.execute("SELECT * FROM chat_jobs").fetchone()
    assert job["state"] == "done" and job["response"] == "Saved answer"
    assert job["delivered"] == 0


def test_processor_failure_does_not_poison_following_messages(runtime):
    enqueue("web:bad", "bad")
    enqueue("web:good", "good")

    def processor(content):
        if content == "bad":
            raise RuntimeError("fake provider outage")
        return "answer"

    worker = ConversationWorker(processor)
    worker.run_once()
    worker.run_once()
    with closing(get_conn()) as conn:
        assert [
            r[0] for r in conn.execute("SELECT state FROM chat_jobs ORDER BY seq")
        ] == ["failed", "done"]


def test_local_sync_guards_prevent_external_access(runtime, monkeypatch):
    import tools.garmin as garmin
    import tools.libre as libre

    def forbidden(*args, **kwargs):
        pytest.fail("External source must not be contacted")

    monkeypatch.setattr(garmin, "sync_garmin_to_db", forbidden)
    monkeypatch.setattr(libre, "sync_libre_to_db", forbidden)
    assert "error" in garmin.sync_garmin_data()
    assert "error" in libre.sync_libre_data()
    enqueue("web:sync", "/update")
    ConversationWorker().run_once()
    with closing(get_conn()) as conn:
        assert (
            "lokalna kopia"
            in conn.execute("SELECT response FROM chat_jobs").fetchone()[0]
        )


def test_queue_is_bounded_but_duplicate_retries_still_work(runtime):
    for i in range(100):
        enqueue(f"web:{i}", "test")
    assert enqueue("web:0", "test")["state"] == "queued"
    with pytest.raises(OverflowError):
        enqueue("web:overflow", "new")


def test_garmin_sync_runs_serially_between_messages_without_agent(runtime, monkeypatch):
    import tools.garmin as garmin

    calls = []
    monkeypatch.setattr(garmin, "sync_garmin_data", lambda **kwargs: calls.append("sync") or {"ok": True})
    enqueue("web:first", "first")
    enqueue("web:sync", "", kind="garmin_sync")
    enqueue("web:last", "last")
    worker = ConversationWorker(lambda content: calls.append(content) or "answer")
    assert all(worker.run_once() for _ in range(3))
    assert not worker.run_once()
    assert calls == ["first", "sync", "last"]


def test_existing_queue_records_migrate_as_messages(runtime):
    enqueue("web:legacy", "legacy content")
    with closing(get_conn()) as conn, conn:
        conn.execute("ALTER TABLE chat_jobs DROP COLUMN kind")
    init_runtime()
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT kind, payload FROM chat_jobs").fetchone()
    assert row["kind"] == "message"
    assert row["payload"] == '"legacy content"'


def test_failed_garmin_sync_has_a_terminal_state_and_does_not_block_chat(runtime, monkeypatch):
    import tools.garmin as garmin

    monkeypatch.setattr(garmin, "sync_garmin_data", lambda **kwargs: {"error": "synthetic outage"})
    enqueue("web:sync", "", kind="garmin_sync")
    enqueue("web:next", "next")
    worker = ConversationWorker(lambda content: "answer")
    assert worker.run_once() and worker.run_once()
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT state, response FROM chat_jobs ORDER BY seq").fetchall()
    assert rows[0]["state"] == "failed"
    assert "Garmin" in rows[0]["response"]
    assert rows[1]["state"] == "done"


def test_unexpected_sync_exception_still_allows_answer(runtime, monkeypatch):
    import agent
    import tools.garmin as garmin
    import tools.libre as libre

    monkeypatch.setenv("K90_PREVIEW", "false")
    monkeypatch.setenv("K90_SYNC_ENABLED", "true")
    monkeypatch.setattr(garmin, "should_auto_sync_today", lambda: True)
    monkeypatch.setattr(libre, "should_auto_sync", lambda: False)

    def broken_sync(**kwargs):
        raise RuntimeError("source unavailable")

    def fake_agent(content, user_id):
        agent.save_history(user_id, content, "Answer from stored data")
        return "Answer from stored data", False

    monkeypatch.setattr(garmin, "sync_garmin_data", broken_sync)
    monkeypatch.setattr(agent, "run_agent", fake_agent)
    enqueue("web:sync-outage", "hello")
    ConversationWorker().run_once()
    with closing(get_conn()) as conn:
        job = conn.execute("SELECT * FROM chat_jobs").fetchone()
        saved = conn.execute(
            "SELECT content FROM conversations WHERE role = 'assistant'"
        ).fetchone()[0]
    assert job["state"] == "done"
    assert "Garmin" in job["response"] and "Answer from stored data" in job["response"]
    assert saved == job["response"]
