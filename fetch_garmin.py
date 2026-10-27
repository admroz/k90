#!/usr/bin/env python3
"""
Garmin Connect data fetcher — projekt k90.

Domyślny tryb pracy synchronizuje dane bezpośrednio do SQLite.
CSV nie są już częścią standardowego flow synchronizacji.
"""

from __future__ import annotations

import logging
from logging_setup import configure_logging
configure_logging()
log = logging.getLogger('fetch_garmin')

import os
import math
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("Brak python-dotenv. Uruchom: pip install python-dotenv")

try:
    import garminconnect
except ImportError:
    sys.exit("Brak garminconnect. Uruchom: pip install garminconnect")

from migrate_csv_to_sqlite import create_schema

load_dotenv()

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Warsaw")
GARMIN_END_DATE = os.getenv("GARMIN_END_DATE")
HEIGHT_M = 1.86
FULL_START = "2022-01-01"


def get_data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))


def get_db_path() -> Path:
    return Path(os.getenv("DB_PATH", get_data_dir() / "k90.db"))


def get_tokenstore() -> Path:
    return get_data_dir() / ".garmin_tokens"


def ensure_agent_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS patient_summary (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            content TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            trigger TEXT
        );
        CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER
        );
    """)
TABLE_CONFIG = {
    "waga": {
        "key_cols": ["data"],
        "columns": ["data", "waga_kg", "bmi", "zrodlo"],
    },
    "cisnienie": {
        "key_cols": ["data", "czas"],
        "columns": ["data", "czas", "skurczowe", "rozkurczowe", "puls", "kategoria", "zrodlo", "uwagi"],
    },
    "aktywnosci": {
        "key_cols": ["data", "czas"],
        "columns": [
            "data", "czas", "typ", "nazwa", "czas_trwania_min", "dystans_km", "kalorie", "sr_tetno", "max_tetno", "kroki"
        ],
    },
    "sen": {
        "key_cols": ["data"],
        "columns": ["data", "total_sleep_min", "deep_min", "light_min", "rem_min", "awake_min", "sleep_score", "spo2_avg", "start_gmt", "end_gmt"],
    },
    "metryki_dzienne": {
        "key_cols": ["data"],
        "columns": ["data", "rhr", "avg_stres", "max_stres", "avg_oddech", "min_oddech", "max_oddech"],
    },
    "kalorie_dzienne": {
        "key_cols": ["data"],
        "columns": ["data", "spoczynkowe_kcal", "aktywne_kcal", "calkowite_kcal", "pobrano_at"],
        "compare_columns": ["data", "spoczynkowe_kcal", "aktywne_kcal", "calkowite_kcal"],
    },
    "hrv": {
        "key_cols": ["data"],
        "columns": ["data", "hrv_noc", "hrv_5min_max", "hrv_tyg_avg", "hrv_status", "baseline_low", "baseline_high"],
    },
    "body_battery": {
        "key_cols": ["data"],
        "columns": ["data", "naladowanie", "zuzycie", "max_bateria", "min_bateria"],
    },
}


def get_mfa() -> str:
    return input("Kod MFA (pozostaw puste jeśli brak): ").strip()


def login() -> garminconnect.Garmin:
    client = garminconnect.Garmin(
        email=EMAIL,
        password=PASSWORD,
        is_cn=False,
        prompt_mfa=get_mfa,
    )
    tokenstore = get_tokenstore()
    if tokenstore.exists():
        log.info('garmin.sync.progress')
        try:
            client.login(tokenstore=str(tokenstore))
            log.info('garmin.sync.progress')
            return client
        except Exception:
            log.warning('garmin.login_failed', exc_info=True)
    else:
        log.info('garmin.sync.progress')
    client.login()
    tokenstore.mkdir(exist_ok=True)
    client.garth.dump(str(tokenstore))
    log.info('garmin.sync.progress')
    return client


def date_chunks(start: str, end: str, chunk_days: int = 180):
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    while start_date <= end_date:
        yield str(start_date), str(min(start_date + timedelta(days=chunk_days - 1), end_date))
        start_date += timedelta(days=chunk_days)


def date_range(start: str, end: str):
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    while start_date <= end_date:
        yield str(start_date)
        start_date += timedelta(days=1)


def _default_end_date() -> str:
    if GARMIN_END_DATE:
        return GARMIN_END_DATE
    return datetime.now(ZoneInfo(APP_TIMEZONE)).date().isoformat()


def _val(data: dict, key: str, divisor: float = 1.0):
    value = data.get(key)
    return round(value / divisor, 2) if value is not None else None


def _normalize_record(record: dict, columns: list[str]) -> dict:
    normalized = {}
    for column in columns:
        value = record.get(column)
        if value == "":
            value = None
        normalized[column] = value
    return normalized


def _last_date_in_db(conn: sqlite3.Connection, table: str) -> str | None:
    row = conn.execute(f"SELECT MAX(data) AS max_date FROM {table}").fetchone()
    return row[0] if row and row[0] else None


def _start_date_for_table(conn: sqlite3.Connection, table: str, fallback: str = FULL_START) -> str:
    last = _last_date_in_db(conn, table)
    if not last:
        return fallback
    buffered = datetime.strptime(last, "%Y-%m-%d").date() - timedelta(days=7)
    return str(buffered)


def _compare_rows(existing: sqlite3.Row, incoming: dict, columns: list[str]) -> bool:
    return all(existing[column] == incoming[column] for column in columns)


def _insert_or_update_many(conn: sqlite3.Connection, table: str, records: list[dict]) -> dict:
    config = TABLE_CONFIG[table]
    key_cols = config["key_cols"]
    columns = config["columns"]
    stats = {"fetched": len(records), "inserted": 0, "updated": 0, "unchanged": 0}
    if not records:
        return stats

    select_sql = f"SELECT {', '.join(columns)} FROM {table} WHERE " + " AND ".join(f"{col} = ?" for col in key_cols)
    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    update_cols = [col for col in columns if col not in key_cols]
    update_sql = f"UPDATE {table} SET " + ", ".join(f"{col} = ?" for col in update_cols) + " WHERE " + " AND ".join(f"{col} = ?" for col in key_cols)

    for record in records:
        normalized = _normalize_record(record, columns)
        key_values = [normalized[col] for col in key_cols]
        existing = conn.execute(select_sql, key_values).fetchone()
        if existing is None:
            conn.execute(insert_sql, [normalized[col] for col in columns])
            stats["inserted"] += 1
            continue
        if _compare_rows(existing, normalized, config.get("compare_columns", columns)):
            if table == "kalorie_dzienne":
                # Refresh freshness without claiming the calorie values changed.
                conn.execute("UPDATE kalorie_dzienne SET pobrano_at = ? WHERE data = ?", (normalized["pobrano_at"], normalized["data"]))
            stats["unchanged"] += 1
            continue
        conn.execute(update_sql, [normalized[col] for col in update_cols] + key_values)
        stats["updated"] += 1

    return stats


def fetch_weight(client, start: str, end: str) -> list[dict]:
    records = []
    for chunk_start, chunk_end in date_chunks(start, end):
        log.info('garmin.sync.progress')
        try:
            data = client.get_weigh_ins(chunk_start, chunk_end)
            count = 0
            for day in (data or {}).get("dailyWeightSummaries", []):
                for metric in day.get("allWeightMetrics", []):
                    weight = _val(metric, "weight", 1000)
                    records.append({
                        "data": metric.get("calendarDate", ""),
                        "waga_kg": weight,
                        "bmi": metric.get("bmi") or (round(weight / HEIGHT_M**2, 2) if weight else None),
                        "zrodlo": metric.get("sourceType", "garmin") or "garmin",
                    })
                    count += 1
            log.info('garmin.sync.progress')
        except Exception:
            log.exception('garmin.fetch_failed')
    return sorted(records, key=lambda row: row["data"])


def fetch_blood_pressure(client, start: str, end: str) -> list[dict]:
    records = []
    for chunk_start, chunk_end in date_chunks(start, end, chunk_days=365):
        log.info('garmin.sync.progress')
        try:
            data = client.get_blood_pressure(chunk_start, chunk_end)
            days = (data or {}).get("measurementSummaries", [])
            for day in days:
                for measurement in day.get("measurements", []):
                    timestamp = measurement.get("measurementTimestampLocal", "")
                    records.append({
                        "data": timestamp[:10] if timestamp else day.get("startDate", ""),
                        "czas": timestamp[11:19] if timestamp else "",
                        "skurczowe": measurement.get("systolic"),
                        "rozkurczowe": measurement.get("diastolic"),
                        "puls": measurement.get("pulse"),
                        "kategoria": measurement.get("categoryName", ""),
                        "zrodlo": measurement.get("sourceType", "garmin") or "garmin",
                        "uwagi": measurement.get("notes", ""),
                    })
            log.info('garmin.sync.progress')
        except Exception:
            log.exception('garmin.fetch_failed')
    return sorted(records, key=lambda row: (row["data"], row["czas"]))


def fetch_activities(client, start: str, end: str) -> list[dict]:
    log.info('garmin.sync.progress')
    records = []
    try:
        for activity in client.get_activities_by_date(start, end) or []:
            timestamp = activity.get("startTimeLocal", "")
            records.append({
                "data": timestamp[:10],
                "czas": timestamp[11:16],
                "typ": activity.get("activityType", {}).get("typeKey", ""),
                "nazwa": activity.get("activityName", ""),
                "czas_trwania_min": round((activity.get("duration") or 0) / 60, 1),
                "dystans_km": round((activity.get("distance") or 0) / 1000, 2),
                "kalorie": activity.get("calories"),
                "sr_tetno": activity.get("averageHR"),
                "max_tetno": activity.get("maxHR"),
                "kroki": activity.get("steps"),
            })
        log.info('garmin.sync.progress')
    except Exception:
        log.exception('garmin.fetch_failed')
    return sorted(records, key=lambda row: (row["data"], row["czas"]))


def fetch_sleep(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    log.info('garmin.sync.progress')
    ok = 0
    for index, day in enumerate(dates):
        if index % 30 == 0:
            log.info('garmin.sync.progress')
        try:
            data = client.get_sleep_data(day)
            dto = (data or {}).get("dailySleepDTO") or {}
            if not dto:
                continue

            secs = dto.get("sleepTimeSeconds") or 0
            deep = dto.get("deepSleepSeconds") or 0
            light = dto.get("lightSleepSeconds") or 0
            rem = dto.get("remSleepSeconds") or 0
            awake = dto.get("awakeSleepSeconds") or 0

            def _ts(key):
                value = dto.get(key)
                if value:
                    from datetime import timezone

                    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%H:%M")
                return ""

            score_obj = (dto.get("sleepScores") or {}).get("overall") or {}
            records.append({
                "data": day,
                "total_sleep_min": round(secs / 60, 1) if secs else None,
                "deep_min": round(deep / 60, 1) if deep else None,
                "light_min": round(light / 60, 1) if light else None,
                "rem_min": round(rem / 60, 1) if rem else None,
                "awake_min": round(awake / 60, 1) if awake else None,
                "sleep_score": score_obj.get("value"),
                "spo2_avg": dto.get("averageSpO2Value"),
                "start_gmt": _ts("sleepStartTimestampGMT"),
                "end_gmt": _ts("sleepEndTimestampGMT"),
            })
            ok += 1
        except Exception:
            pass
        if index % 30 == 29:
            time.sleep(0.2)
    log.info('garmin.sync.progress')
    return sorted(records, key=lambda row: row["data"])


def fetch_daily_metrics(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    log.info('garmin.sync.progress')
    ok = 0
    for index, day in enumerate(dates):
        if index % 30 == 0:
            log.info('garmin.sync.progress')
        row = {"data": day, "rhr": None, "avg_stres": None, "max_stres": None, "avg_oddech": None, "min_oddech": None, "max_oddech": None}
        any_data = False
        try:
            rhr_data = client.get_rhr_day(day)
            metrics_map = ((rhr_data or {}).get("allMetrics", {}).get("metricsMap", {}))
            rhr_list = metrics_map.get("WELLNESS_RESTING_HEART_RATE", [])
            if rhr_list:
                row["rhr"] = rhr_list[0].get("value")
                any_data = True
        except Exception:
            pass
        try:
            stress = client.get_stress_data(day) or {}
            if stress.get("avgStressLevel") is not None:
                row["avg_stres"] = stress.get("avgStressLevel")
                row["max_stres"] = stress.get("maxStressLevel")
                any_data = True
        except Exception:
            pass
        try:
            respiration = client.get_respiration_data(day) or {}
            if respiration.get("avgWakingRespirationValue") is not None:
                row["avg_oddech"] = respiration.get("avgWakingRespirationValue")
                row["min_oddech"] = respiration.get("lowestRespirationValue")
                row["max_oddech"] = respiration.get("highestRespirationValue")
                any_data = True
        except Exception:
            pass
        if any_data:
            records.append(row)
            ok += 1
        if index % 30 == 29:
            time.sleep(0.2)
    log.info('garmin.sync.progress')
    return sorted(records, key=lambda row: row["data"])


def fetch_daily_calories(client, start: str, end: str) -> list[dict]:
    records = []
    for day in date_range(start, end):
        try:
            data = client.get_stats(day) or {}
        except garminconnect.GarminConnectConnectionError as exc:
            # The client uses this exact error for an empty, successful summary.
            # Do not treat authentication, rate limiting or network failures as gaps.
            if str(exc) != "No data received from server":
                raise
            data = {}
        if data.get("calendarDate") not in (None, day):
            raise ValueError("Garmin returned calorie data for a different date")

        def value(key):
            raw = data.get(key)
            if raw is None or isinstance(raw, bool):
                return None
            try:
                number = float(raw)
            except (TypeError, ValueError):
                return None
            return number if math.isfinite(number) and number >= 0 else None

        # Unknown values remain NULL. A successful empty response also records
        # the queried day, so a historical backfill can resume after a restart.
        records.append({
            "data": day,
            "spoczynkowe_kcal": value("bmrKilocalories"),
            "aktywne_kcal": value("activeKilocalories"),
            "calkowite_kcal": value("totalKilocalories"),
            "pobrano_at": datetime.now(ZoneInfo(APP_TIMEZONE)).isoformat(),
        })
        time.sleep(0.1)
    return records


def fetch_hrv(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    log.info('garmin.sync.progress')
    ok = 0
    for index, day in enumerate(dates):
        if index % 30 == 0:
            log.info('garmin.sync.progress')
        try:
            data = client.get_hrv_data(day)
            summary = (data or {}).get("hrvSummary") or {}
            if not summary or summary.get("lastNightAvg") is None:
                continue
            baseline = summary.get("baseline") or {}
            records.append({
                "data": day,
                "hrv_noc": summary.get("lastNightAvg"),
                "hrv_5min_max": summary.get("lastNight5MinHigh"),
                "hrv_tyg_avg": summary.get("weeklyAvg"),
                "hrv_status": summary.get("status"),
                "baseline_low": baseline.get("balancedLow"),
                "baseline_high": baseline.get("balancedUpper"),
            })
            ok += 1
        except Exception:
            pass
        if index % 30 == 29:
            time.sleep(0.2)
    log.info('garmin.sync.progress')
    return sorted(records, key=lambda row: row["data"])


def fetch_body_battery(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    log.info('garmin.sync.progress')
    ok = 0
    for index, day in enumerate(dates):
        if index % 30 == 0:
            log.info('garmin.sync.progress')
        try:
            stats = client.get_stats(day) or {}
            charged = stats.get("bodyBatteryChargedValue")
            if charged is None:
                continue
            records.append({
                "data": day,
                "naladowanie": charged,
                "zuzycie": stats.get("bodyBatteryDrainedValue"),
                "max_bateria": stats.get("bodyBatteryHighestValue"),
                "min_bateria": stats.get("bodyBatteryLowestValue"),
            })
            ok += 1
        except Exception:
            pass
        if index % 30 == 29:
            time.sleep(0.2)
    log.info('garmin.sync.progress')
    return sorted(records, key=lambda row: row["data"])


def sync_garmin_to_db(client=None, full_mode: bool = False, end_date: str | None = None, start_dates: dict[str, str] | None = None) -> dict:
    if not EMAIL or not PASSWORD:
        return {"error": "Brak kredencjałów — uzupełnij plik .env"}

    target_end = end_date or _default_end_date()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    create_schema(conn)
    ensure_agent_tables(conn)
    conn.commit()

    starts = start_dates or {
        "waga": FULL_START if full_mode else _start_date_for_table(conn, "waga"),
        "cisnienie": FULL_START if full_mode else _start_date_for_table(conn, "cisnienie"),
        "aktywnosci": FULL_START if full_mode else _start_date_for_table(conn, "aktywnosci"),
        "sen": FULL_START if full_mode else _start_date_for_table(conn, "sen"),
        "metryki_dzienne": FULL_START if full_mode else _start_date_for_table(conn, "metryki_dzienne"),
        "hrv": FULL_START if full_mode else _start_date_for_table(conn, "hrv"),
        "body_battery": FULL_START if full_mode else _start_date_for_table(conn, "body_battery"),
        "kalorie_dzienne": FULL_START if full_mode else _start_date_for_table(conn, "kalorie_dzienne"),
    }

    log.info('garmin.sync.progress')
    log.info('garmin.sync.progress')

    own_client = client is None
    if own_client:
        client = login()

    dataset_fetchers = [
        ("waga", fetch_weight),
        ("cisnienie", fetch_blood_pressure),
        ("aktywnosci", fetch_activities),
        ("sen", fetch_sleep),
        ("metryki_dzienne", fetch_daily_metrics),
        ("hrv", fetch_hrv),
        ("body_battery", fetch_body_battery),
        ("kalorie_dzienne", fetch_daily_calories),
    ]

    results = {"ok": True, "datasets": {}, "end_date": target_end}
    try:
        for table, fetcher in dataset_fetchers:
            log.info('garmin.sync.progress')
            start = starts.get(table, FULL_START)
            chunks = date_chunks(start, target_end, chunk_days=30) if table == "kalorie_dzienne" else [(start, target_end)]
            stats = {"fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0}
            for batch_start, batch_end in chunks:
                records = fetcher(client, batch_start, batch_end)
                batch = _insert_or_update_many(conn, table, records)
                conn.commit()
                for key in stats:
                    stats[key] += batch[key]
                if table == "kalorie_dzienne":
                    log.info('garmin.sync.progress')
            results["datasets"][table] = stats
            log.info('garmin.sync.progress')
    except Exception as exc:
        results = {"error": str(exc)}
    finally:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass
        conn.close()

    return results


def main() -> None:
    full_mode = "--full" in sys.argv
    result = sync_garmin_to_db(full_mode=full_mode)
    if "error" in result:
        log.error('garmin.fetch_failed')
        raise SystemExit(1)

    log.info('garmin.sync.progress')
    for name, stats in result.get("datasets", {}).items():
        log.info('garmin.sync.progress')


if __name__ == "__main__":
    main()
