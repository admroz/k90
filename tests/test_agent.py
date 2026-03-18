from __future__ import annotations

import agent
from tools.db import get_conn


def test_load_history_limits_message_pairs_and_parses_json(monkeypatch, temp_db):
    monkeypatch.setattr(agent, "HISTORY_MESSAGES", 2)

    with get_conn() as conn:
        for idx in range(1, 5):
            conn.execute(
                "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                ("u1", "user", f"user-{idx}"),
            )
            content = '[{"type":"text","text":"hello"}]' if idx == 4 else f"assistant-{idx}"
            conn.execute(
                "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                ("u1", "assistant", content),
            )
        conn.commit()

    history = agent.load_history("u1")

    assert len(history) == 4
    assert history[0]["content"] == "user-3"
    assert isinstance(history[-1]["content"], list)
    assert history[-1]["content"][0]["text"] == "hello"


def test_cli_slash_command_bypasses_run_agent(monkeypatch, capsys):
    inputs = iter(["/status", "exit"])
    monkeypatch.setattr(agent, "init_db", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(agent, "handle_command", lambda text: "STATUS" if text == "/status" else None)
    monkeypatch.setattr(agent, "run_agent", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_agent should not be called")))

    agent.cli()

    out = capsys.readouterr().out
    assert "Agent: STATUS" in out
