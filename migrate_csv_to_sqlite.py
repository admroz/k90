"""
Jednorazowy skrypt migracji danych z CSV do SQLite (kadencja90.db).
Uruchom raz: python migrate_csv_to_sqlite.py
"""

import csv
import sqlite3
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "kadencja90.db"))


def float_or_none(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def int_or_none(val):
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def str_or_none(val):
    if val is None or val == "":
        return None
    return val


def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS waga (
            data        TEXT PRIMARY KEY,
            waga_kg     REAL,
            bmi         REAL,
            zrodlo      TEXT
        );

        CREATE TABLE IF NOT EXISTS cisnienie (
            data        TEXT,
            czas        TEXT,
            skurczowe   INTEGER,
            rozkurczowe INTEGER,
            puls        INTEGER,
            kategoria   TEXT,
            zrodlo      TEXT,
            uwagi       TEXT,
            PRIMARY KEY (data, czas)
        );

        CREATE TABLE IF NOT EXISTS aktywnosci (
            data              TEXT,
            czas              TEXT,
            typ               TEXT,
            nazwa             TEXT,
            czas_trwania_min  REAL,
            dystans_km        REAL,
            kalorie           REAL,
            sr_tetno          REAL,
            max_tetno         REAL,
            kroki             INTEGER,
            PRIMARY KEY (data, czas)
        );

        CREATE TABLE IF NOT EXISTS sen (
            data            TEXT PRIMARY KEY,
            total_sleep_min REAL,
            deep_min        REAL,
            light_min       REAL,
            rem_min         REAL,
            awake_min       REAL,
            sleep_score     REAL,
            spo2_avg        REAL,
            start_gmt       TEXT,
            end_gmt         TEXT
        );

        CREATE TABLE IF NOT EXISTS metryki_dzienne (
            data        TEXT PRIMARY KEY,
            rhr         REAL,
            avg_stres   REAL,
            max_stres   REAL,
            avg_oddech  REAL,
            min_oddech  REAL,
            max_oddech  REAL
        );

        CREATE TABLE IF NOT EXISTS hrv (
            data          TEXT PRIMARY KEY,
            hrv_noc       REAL,
            hrv_5min_max  REAL,
            hrv_tyg_avg   REAL,
            hrv_status    TEXT,
            baseline_low  REAL,
            baseline_high REAL
        );

        CREATE TABLE IF NOT EXISTS body_battery (
            data        TEXT PRIMARY KEY,
            naladowanie REAL,
            zuzycie     REAL,
            max_bateria REAL,
            min_bateria REAL
        );

        CREATE TABLE IF NOT EXISTS wyniki_lab (
            data        TEXT,
            kategoria   TEXT,
            badanie     TEXT,
            wynik       REAL,
            jednostka   TEXT,
            norma_min   REAL,
            norma_max   REAL,
            ocena       TEXT,
            uwagi       TEXT,
            PRIMARY KEY (data, badanie)
        );

        CREATE TABLE IF NOT EXISTS sesje (
            sender         TEXT PRIMARY KEY,
            historia       TEXT NOT NULL DEFAULT '[]',
            zaktualizowano TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS posilki (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data        TEXT NOT NULL,
            czas        TEXT,
            opis        TEXT,
            kalorie     REAL,
            bialko_g    REAL,
            weglowodany_g REAL,
            tluszcze_g  REAL,
            zrodlo      TEXT DEFAULT 'manual'
        );
    """)
    conn.commit()


def migrate_waga(conn):
    path = DATA_DIR / "waga.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO waga VALUES (?,?,?,?)",
                (row["data"], float_or_none(row["waga_kg"]),
                 float_or_none(row["bmi"]), str_or_none(row["zrodlo"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_cisnienie(conn):
    path = DATA_DIR / "cisnienie.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO cisnienie VALUES (?,?,?,?,?,?,?,?)",
                (row["data"], str_or_none(row["czas"]),
                 int_or_none(row["skurczowe"]), int_or_none(row["rozkurczowe"]),
                 int_or_none(row["puls"]), str_or_none(row["kategoria"]),
                 str_or_none(row["zrodlo"]), str_or_none(row["uwagi"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_aktywnosci(conn):
    path = DATA_DIR / "aktywnosci.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO aktywnosci VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row["data"], str_or_none(row["czas"]),
                 str_or_none(row["typ"]), str_or_none(row["nazwa"]),
                 float_or_none(row["czas_trwania_min"]),
                 float_or_none(row["dystans_km"]),
                 float_or_none(row["kalorie"]),
                 float_or_none(row["sr_tetno"]),
                 float_or_none(row["max_tetno"]),
                 int_or_none(row["kroki"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_sen(conn):
    path = DATA_DIR / "sen.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO sen VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row["data"],
                 float_or_none(row["total_sleep_min"]),
                 float_or_none(row["deep_min"]),
                 float_or_none(row["light_min"]),
                 float_or_none(row["rem_min"]),
                 float_or_none(row["awake_min"]),
                 float_or_none(row["sleep_score"]),
                 float_or_none(row["spo2_avg"]),
                 str_or_none(row["start_gmt"]),
                 str_or_none(row["end_gmt"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_metryki(conn):
    path = DATA_DIR / "metryki_dzienne.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO metryki_dzienne VALUES (?,?,?,?,?,?,?)",
                (row["data"],
                 float_or_none(row["rhr"]),
                 float_or_none(row["avg_stres"]),
                 float_or_none(row["max_stres"]),
                 float_or_none(row["avg_oddech"]),
                 float_or_none(row["min_oddech"]),
                 float_or_none(row["max_oddech"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_hrv(conn):
    path = DATA_DIR / "hrv.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO hrv VALUES (?,?,?,?,?,?,?)",
                (row["data"],
                 float_or_none(row["hrv_noc"]),
                 float_or_none(row["hrv_5min_max"]),
                 float_or_none(row["hrv_tyg_avg"]),
                 str_or_none(row["hrv_status"]),
                 float_or_none(row["baseline_low"]),
                 float_or_none(row["baseline_high"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_body_battery(conn):
    path = DATA_DIR / "body_battery.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO body_battery VALUES (?,?,?,?,?)",
                (row["data"],
                 float_or_none(row["naladowanie"]),
                 float_or_none(row["zuzycie"]),
                 float_or_none(row["max_bateria"]),
                 float_or_none(row["min_bateria"]))
            )
            count += 1
    conn.commit()
    return count


def migrate_wyniki_lab(conn):
    path = DATA_DIR / "wyniki_lab.csv"
    if not path.exists():
        print(f"  Pominięto: {path.name} (brak pliku)")
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO wyniki_lab VALUES (?,?,?,?,?,?,?,?,?)",
                (row["data"],
                 str_or_none(row["kategoria"]),
                 str_or_none(row["badanie"]),
                 float_or_none(row["wynik"]),
                 str_or_none(row["jednostka"]),
                 float_or_none(row["norma_min"]),
                 float_or_none(row["norma_max"]),
                 str_or_none(row["ocena"]),
                 str_or_none(row["uwagi"]))
            )
            count += 1
    conn.commit()
    return count


def main():
    print(f"Tworzę bazę: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    print("Tworzę schemat...")
    create_schema(conn)

    migrations = [
        ("waga",            migrate_waga),
        ("cisnienie",       migrate_cisnienie),
        ("aktywnosci",      migrate_aktywnosci),
        ("sen",             migrate_sen),
        ("metryki_dzienne", migrate_metryki),
        ("hrv",             migrate_hrv),
        ("body_battery",    migrate_body_battery),
        ("wyniki_lab",      migrate_wyniki_lab),
    ]

    total = 0
    for name, fn in migrations:
        n = fn(conn)
        print(f"  {name}: {n} wierszy")
        total += n

    conn.close()
    size_kb = DB_PATH.stat().st_size // 1024
    print(f"\nGotowe. Łącznie: {total} wierszy → {DB_PATH.name} ({size_kb} KB)")


if __name__ == "__main__":
    main()
