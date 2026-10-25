"""Local-only launcher: isolated data, Telegram and source sync disabled."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DOCUMENTS = (
    "pacjent.md",
    "wywiad.md",
    "analiza.md",
    "dieta.md",
    "tydzien.md",
    "system_prompt.md",
)


def clone_snapshot(source: Path, destination: Path):
    source = source.resolve()
    if not (source / "k90.db").is_file():
        raise ValueError("Snapshot musi zawierać k90.db.")
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(0o700)
    with (
        closing(
            sqlite3.connect((source / "k90.db").as_uri() + "?mode=ro", uri=True)
        ) as src,
        closing(sqlite3.connect(destination / "k90.db")) as dst,
    ):
        src.backup(dst)
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Kopia bazy nie przeszła kontroli integralności.")
    (destination / "k90.db").chmod(0o600)
    for name in DOCUMENTS:
        path = source / name
        if path.is_file() and not path.is_symlink():
            shutil.copy2(path, destination / name)
            (destination / name).chmod(0o600)
    # Imported Telegram jobs must never be replayed in a local copy.
    with closing(sqlite3.connect(destination / "k90.db")) as conn, conn:
        conn.execute("DROP TABLE IF EXISTS chat_jobs")
        conn.execute("DROP TABLE IF EXISTS transport_state")
        from patient_documents import import_markdown

        import_markdown(conn, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Folder ze snapshotem; uruchomienie tworzy nową kopię roboczą",
    )
    parser.add_argument(
        "--live-agent",
        action="store_true",
        help="Włącz płatne zapytania do modelu z .env na lokalnej kopii",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    local_root = ROOT / "data" / "local"
    if args.snapshot:
        stamp = datetime.now(ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Warsaw")))
        data = local_root / ("snapshot-" + stamp.strftime("%Y%m%d-%H%M%S-%f"))
        clone_snapshot(args.snapshot, data)
    else:
        data = local_root / "demo"
        data.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "DB_PATH": str(data / "k90.db"),
            "DATA_DIR": str(data),
            "BACKUP_DIR": str(data / "backups"),
            "K90_LOCAL": "true",
            "K90_PREVIEW": "false" if args.live_agent else "true",
            "K90_SYNC_ENABLED": "false",
            "TELEGRAM_ENABLED": "false",
            "WEB_COOKIE_SECURE": "false",
            "WEB_PASSWORD": os.getenv("K90_LOCAL_PASSWORD", "k90-local-preview"),
        }
    )
    if not args.snapshot:
        from scripts.seed_demo import seed

        seed()
    print(
        f"k90: http://127.0.0.1:{args.port}\nDane robocze: {data}\nHasło: wartość K90_LOCAL_PASSWORD lub domyślne k90-local-preview",
        flush=True,
    )
    import uvicorn

    uvicorn.run("webapp:app", host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
