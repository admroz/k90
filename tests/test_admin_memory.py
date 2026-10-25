"""Explicit bounded old-history import; never a startup side effect."""
import importlib
import json

from tools.db import get_conn


def test_backfill_is_dry_run_by_default_and_apply_is_idempotent(temp_db,capsys):
    admin=importlib.import_module('memory_admin')
    with get_conn() as conn:
        conn.execute("INSERT INTO conversations(user_id,role,content) VALUES ('owner','user','Synthetic legacy millet synthetic@example.invalid')")
        conn.execute("INSERT INTO conversations(user_id,role,content) VALUES ('other','user','Do not import other owner')")
    assert admin.main(['backfill','--limit','10'])==0
    dry=json.loads(capsys.readouterr().out)
    assert dry['selected_rows']==1 and dry['applied'] is False
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM memory_sources').fetchone()[0]==0
    assert admin.main(['backfill','--limit','10','--apply'])==0
    assert admin.main(['backfill','--limit','10','--apply'])==0
    output=capsys.readouterr().out
    assert 'synthetic@example.invalid' not in output
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM memory_sources').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM memory_versions').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM memory_outbox').fetchone()[0]==1


def test_status_and_rebuild_never_contact_backend(temp_db,monkeypatch,capsys):
    admin=importlib.import_module('memory_admin')
    import memory_runtime
    memory_runtime.begin_turn('owner','Synthetic grain preference')
    monkeypatch.setattr(memory_runtime,'get_backend',lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden')))
    assert admin.main(['status'])==0
    assert json.loads(capsys.readouterr().out)['active_sources']==1
    assert admin.main(['rebuild'])==0
    assert json.loads(capsys.readouterr().out)['queued_sources']==1
