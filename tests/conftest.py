from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrate_csv_to_sqlite import create_schema
from tools import db as db_module


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setattr(db_module, "_DB_PATH", str(db_path), raising=False)

    db_module.init_db()
    with db_module.get_conn() as conn:
        create_schema(conn)
        conn.commit()

    return db_path
