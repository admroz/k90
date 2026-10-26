"""Synthetic deterministic capture contention; no sleeps or replay of side effects."""
from contextlib import closing
import json
import sqlite3

import pytest

import memory_runtime as runtime
from tools.db import MESSAGE_CONTEXT, get_conn


@pytest.mark.parametrize('capture', ['incoming', 'tool', 'failure', 'pair', 'history'])
def test_capture_reserves_write_before_initialize_reads(temp_db, monkeypatch, capture):
    with closing(get_conn()) as conn, conn:
        runtime.initialize(conn)
    turn = runtime.begin_turn('synthetic-owner', 'Synthetic first')
    original = runtime.initialize
    rivals = []
    blocked = []

    def interleave(conn):
        original(conn)
        rival = get_conn()
        rivals.append(rival)
        rival.execute('PRAGMA busy_timeout=0')
        try:
            rival.execute('BEGIN IMMEDIATE')
            rival.execute("UPDATE memory_settings SET value=value WHERE name='pseudonym_key'")
        except sqlite3.OperationalError as exc:
            assert str(exc) == 'database is locked'
            blocked.append(True)

    monkeypatch.setattr(runtime, 'initialize', interleave)
    turn_token = runtime.TURN_CONTEXT.set(turn if capture in ('tool', 'failure') else None)
    message_token = MESSAGE_CONTEXT.set({'request_id': 'synthetic-capture', 'channel': 'web'})
    try:
        if capture == 'incoming':
            result = runtime.begin_turn('synthetic-owner', 'Synthetic original')
            assert result['request_id'] == 'synthetic-capture'
        elif capture == 'tool':
            runtime.record_tool('synthetic', {'value': 1}, {'value': 2})
        elif capture == 'failure':
            runtime.record_failure('synthetic_failure')
        elif capture == 'pair':
            with closing(get_conn()) as conn, conn:
                runtime.record_pair(conn, 'synthetic-owner', 'Synthetic original', 'Synthetic answer')
        else:
            from agent import save_history
            save_history('synthetic-owner', 'Synthetic original', 'Synthetic answer')
        assert blocked == [True]
    finally:
        MESSAGE_CONTEXT.reset(message_token)
        runtime.TURN_CONTEXT.reset(turn_token)
        for rival in rivals:
            rival.rollback()
            rival.close()
    with closing(get_conn()) as conn:
        payloads = [json.loads(row[0]) for row in conn.execute('SELECT payload FROM agent_events')]
        if capture in ('incoming', 'pair', 'history'):
            assert 'Synthetic original' in payloads
        elif capture == 'tool':
            assert {'name': 'synthetic', 'arguments': {'value': 1}} in payloads
            assert {'name': 'synthetic', 'result': {'value': 2}} in payloads
        else:
            assert {'code': 'synthetic_failure'} in payloads
