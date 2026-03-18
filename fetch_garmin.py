#!/usr/bin/env python3
"""
Garmin Connect data fetcher — projekt k90
Pobiera: wagę, ciśnienie krwi, aktywności fizyczne, sen, tętno spoczynkowe, stres, oddech
Scala waga_garmin.csv + vitalia_waga.json → waga.csv

Instalacja:
    pip install garminconnect python-dotenv

Użycie:
    python fetch_garmin.py          # aktualizacja od ostatniego wpisu
    python fetch_garmin.py --full   # pełne pobranie od 2022-01-01
"""

import csv
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("Brak python-dotenv. Uruchom: pip install python-dotenv")

try:
    import garminconnect
except ImportError:
    sys.exit("Brak garminconnect. Uruchom: pip install garminconnect")


# ── Konfiguracja ──────────────────────────────────────────────────────────────

load_dotenv()

EMAIL      = os.getenv("GARMIN_EMAIL")
PASSWORD   = os.getenv("GARMIN_PASSWORD")
END_DATE   = os.getenv("GARMIN_END_DATE", str(date.today()))
DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
TOKENSTORE = DATA_DIR / ".garmin_tokens"

OUT_WAGA        = DATA_DIR / "waga_garmin.csv"
OUT_CISNIENIE   = DATA_DIR / "cisnienie.csv"
OUT_AKTYWNOSCI  = DATA_DIR / "aktywnosci.csv"
OUT_WAGA_FINAL  = DATA_DIR / "waga.csv"
OUT_SEN         = DATA_DIR / "sen.csv"
OUT_METRYKI     = DATA_DIR / "metryki_dzienne.csv"
OUT_HRV         = DATA_DIR / "hrv.csv"
OUT_BATERIA     = DATA_DIR / "body_battery.csv"
VITALIA_JSON    = DATA_DIR / "vitalia_waga.json"
HEIGHT_M        = 1.86
FULL_START      = "2022-01-01"


# ── Wyznacz datę startu (tryb przyrostowy) ────────────────────────────────────

def last_date_in_csv(filepath: Path, date_col: str = "data") -> str | None:
    """Zwraca ostatnią datę z istniejącego CSV lub None."""
    if not filepath.exists():
        return None
    last = None
    with open(filepath, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row.get(date_col, "")
            if d and (last is None or d > last):
                last = d
    return last


def start_date_for(filepath: Path, fallback: str = FULL_START) -> str:
    """Data startu = dzień po ostatnim wpisie (lub fallback przy pierwszym uruchomieniu)."""
    last = last_date_in_csv(filepath)
    if not last:
        return fallback
    # Cofnij się o 7 dni dla bezpieczeństwa (wpisy mogą być dodawane z opóźnieniem)
    d = datetime.strptime(last, "%Y-%m-%d").date() - timedelta(days=7)
    return str(d)


# ── Autentykacja ──────────────────────────────────────────────────────────────

def get_mfa() -> str:
    return input("Kod MFA (pozostaw puste jeśli brak): ").strip()


def login() -> garminconnect.Garmin:
    client = garminconnect.Garmin(
        email=EMAIL,
        password=PASSWORD,
        is_cn=False,
        prompt_mfa=get_mfa,
    )
    if TOKENSTORE.exists():
        print("Wczytuję tokeny z cache...")
        try:
            client.login(tokenstore=str(TOKENSTORE))
            print(f"Zalogowano jako: {client.display_name}")
            return client
        except Exception as e:
            print(f"Cache tokenów nieważny ({e.__class__.__name__}: {e})")
            print("Loguję ponownie (może wymagać MFA)...")
    else:
        print("Brak tokenów — pierwsze logowanie (może wymagać MFA)...")
    client.login()
    TOKENSTORE.mkdir(exist_ok=True)
    client.garth.dump(str(TOKENSTORE))
    print(f"Tokeny zapisane w {TOKENSTORE}/")
    print(f"Zalogowano jako: {client.display_name}")
    return client


# ── Pobieranie danych ─────────────────────────────────────────────────────────

def date_chunks(start: str, end: str, chunk_days: int = 180):
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end,   "%Y-%m-%d").date()
    while s <= e:
        yield str(s), str(min(s + timedelta(days=chunk_days - 1), e))
        s += timedelta(days=chunk_days)


def fetch_weight(client, start: str, end: str) -> list[dict]:
    records = []
    for s, e in date_chunks(start, end):
        print(f"  Waga: {s} → {e}", end="  ")
        try:
            data = client.get_weigh_ins(s, e)
            n = 0
            for day in (data or {}).get("dailyWeightSummaries", []):
                for m in day.get("allWeightMetrics", []):
                    w = _val(m, "weight", 1000)
                    records.append({
                        "data":           m.get("calendarDate", ""),
                        "waga_kg":        w,
                        "bmi":            m.get("bmi") or (round(w / HEIGHT_M**2, 2) if w else None),
                        "tkanka_tluszcz": m.get("bodyFat"),
                        "masa_miesni_kg": _val(m, "muscleMass", 1000),
                        "masa_kostna_kg": _val(m, "boneMass", 1000),
                        "woda_pct":       m.get("bodyWater"),
                        "zrodlo":         m.get("sourceType", ""),
                    })
                    n += 1
            print(f"({n} pomiarów)")
        except Exception as exc:
            print(f"BŁĄD: {exc}")
    return sorted(records, key=lambda r: r["data"])


def fetch_blood_pressure(client, start: str, end: str) -> list[dict]:
    records = []
    for s, e in date_chunks(start, end, chunk_days=365):
        print(f"  Ciśnienie: {s} → {e}", end="  ")
        try:
            data = client.get_blood_pressure(s, e)
            days = (data or {}).get("measurementSummaries", [])
            for day in days:
                for m in day.get("measurements", []):
                    ts = m.get("measurementTimestampLocal", "")
                    records.append({
                        "data":        ts[:10] if ts else day.get("startDate", ""),
                        "czas":        ts[11:19] if ts else "",
                        "skurczowe":   m.get("systolic"),
                        "rozkurczowe": m.get("diastolic"),
                        "puls":        m.get("pulse"),
                        "kategoria":   m.get("categoryName", ""),
                        "zrodlo":      m.get("sourceType", ""),
                        "uwagi":       m.get("notes", ""),
                    })
            print(f"({len(days)} dni z pomiarami)")
        except Exception as exc:
            print(f"BŁĄD: {exc}")
    return sorted(records, key=lambda r: (r["data"], r["czas"]))


def fetch_activities(client, start: str, end: str) -> list[dict]:
    print(f"  Aktywności: {start} → {end}", end="  ")
    records = []
    try:
        for a in (client.get_activities_by_date(start, end) or []):
            ts = a.get("startTimeLocal", "")
            records.append({
                "data":             ts[:10],
                "czas":             ts[11:16],
                "typ":              a.get("activityType", {}).get("typeKey", ""),
                "nazwa":            a.get("activityName", ""),
                "czas_trwania_min": round((a.get("duration") or 0) / 60, 1),
                "dystans_km":       round((a.get("distance") or 0) / 1000, 2),
                "kalorie":          a.get("calories"),
                "sr_tetno":         a.get("averageHR"),
                "max_tetno":        a.get("maxHR"),
                "kroki":            a.get("steps"),
            })
        print(f"({len(records)} aktywności)")
    except Exception as exc:
        print(f"BŁĄD: {exc}")
    return sorted(records, key=lambda r: (r["data"], r["czas"]))


# ── Pobieranie danych dziennych (pętla po dniach) ────────────────────────────

def date_range(start: str, end: str):
    """Generator dat dzień po dniu od start do end włącznie."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end,   "%Y-%m-%d").date()
    while s <= e:
        yield str(s)
        s += timedelta(days=1)


def fetch_sleep(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    print(f"  Sen: {start} → {end} ({total} dni)")
    ok = 0
    for i, d in enumerate(dates):
        if i % 30 == 0:
            print(f"    sen {d}  ({i+1}/{total})", flush=True)
        try:
            data = client.get_sleep_data(d)
            dto = (data or {}).get("dailySleepDTO") or {}
            if not dto:
                continue

            secs = dto.get("sleepTimeSeconds") or 0
            deep  = dto.get("deepSleepSeconds") or 0
            light = dto.get("lightSleepSeconds") or 0
            rem   = dto.get("remSleepSeconds") or 0
            awake = dto.get("awakeSleepSeconds") or 0

            def _ts(key):
                ms = dto.get(key)
                if ms:
                    from datetime import timezone
                    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%H:%M")
                return ""

            score_obj = (dto.get("sleepScores") or {}).get("overall") or {}
            records.append({
                "data":             d,
                "total_sleep_min":  round(secs / 60, 1) if secs else "",
                "deep_min":         round(deep  / 60, 1) if deep  else "",
                "light_min":        round(light / 60, 1) if light else "",
                "rem_min":          round(rem   / 60, 1) if rem   else "",
                "awake_min":        round(awake / 60, 1) if awake else "",
                "sleep_score":      score_obj.get("value", ""),
                "spo2_avg":         dto.get("averageSpO2Value", ""),
                "start_gmt":        _ts("sleepStartTimestampGMT"),
                "end_gmt":          _ts("sleepEndTimestampGMT"),
            })
            ok += 1
        except Exception:
            pass
        if i % 30 == 29:
            time.sleep(0.2)
    print(f"  → Sen: {ok}/{total} nocy z danymi")
    return sorted(records, key=lambda r: r["data"])


def fetch_daily_metrics(client, start: str, end: str) -> list[dict]:
    """Tętno spoczynkowe + stres + oddech — po jednym wierszu na dzień."""
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    print(f"  Metryki dzienne (RHR/stres/oddech): {start} → {end} ({total} dni)")
    ok = 0
    for i, d in enumerate(dates):
        if i % 30 == 0:
            print(f"    metryki {d}  ({i+1}/{total})", flush=True)
        row = {"data": d, "rhr": "", "avg_stres": "", "max_stres": "",
               "avg_oddech": "", "min_oddech": "", "max_oddech": ""}
        any_data = False
        try:
            rhr_data = client.get_rhr_day(d)
            metrics_map = ((rhr_data or {})
                           .get("allMetrics", {})
                           .get("metricsMap", {}))
            rhr_list = metrics_map.get("WELLNESS_RESTING_HEART_RATE", [])
            if rhr_list:
                row["rhr"] = rhr_list[0].get("value", "")
                any_data = True
        except Exception:
            pass
        try:
            stress = client.get_stress_data(d) or {}
            if stress.get("avgStressLevel") is not None:
                row["avg_stres"] = stress.get("avgStressLevel", "")
                row["max_stres"] = stress.get("maxStressLevel", "")
                any_data = True
        except Exception:
            pass
        try:
            resp = client.get_respiration_data(d) or {}
            if resp.get("avgWakingRespirationValue") is not None:
                row["avg_oddech"] = resp.get("avgWakingRespirationValue", "")
                row["min_oddech"] = resp.get("lowestRespirationValue", "")
                row["max_oddech"] = resp.get("highestRespirationValue", "")
                any_data = True
        except Exception:
            pass
        if any_data:
            records.append(row)
            ok += 1
        if i % 30 == 29:
            time.sleep(0.2)
    print(f"  → Metryki: {ok}/{total} dni z danymi")
    return sorted(records, key=lambda r: r["data"])


def fetch_hrv(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    print(f"  HRV: {start} → {end} ({total} dni)")
    ok = 0
    for i, d in enumerate(dates):
        if i % 30 == 0:
            print(f"    hrv {d}  ({i+1}/{total})", flush=True)
        try:
            data = client.get_hrv_data(d)
            s = (data or {}).get("hrvSummary") or {}
            if not s or s.get("lastNightAvg") is None:
                continue
            baseline = s.get("baseline") or {}
            records.append({
                "data":           d,
                "hrv_noc":        s.get("lastNightAvg", ""),
                "hrv_5min_max":   s.get("lastNight5MinHigh", ""),
                "hrv_tyg_avg":    s.get("weeklyAvg", ""),
                "hrv_status":     s.get("status", ""),
                "baseline_low":   baseline.get("balancedLow", ""),
                "baseline_high":  baseline.get("balancedUpper", ""),
            })
            ok += 1
        except Exception:
            pass
        if i % 30 == 29:
            time.sleep(0.2)
    print(f"  → HRV: {ok}/{total} nocy z danymi")
    return sorted(records, key=lambda r: r["data"])


def fetch_body_battery(client, start: str, end: str) -> list[dict]:
    records = []
    dates = list(date_range(start, end))
    total = len(dates)
    print(f"  Body Battery: {start} → {end} ({total} dni)")
    ok = 0
    for i, d in enumerate(dates):
        if i % 30 == 0:
            print(f"    body battery {d}  ({i+1}/{total})", flush=True)
        try:
            s = client.get_stats(d) or {}
            charged = s.get("bodyBatteryChargedValue")
            if charged is None:
                continue
            records.append({
                "data":        d,
                "naladowanie": charged,
                "zuzycie":     s.get("bodyBatteryDrainedValue", ""),
                "max_bateria": s.get("bodyBatteryHighestValue", ""),
                "min_bateria": s.get("bodyBatteryLowestValue", ""),
            })
            ok += 1
        except Exception:
            pass
        if i % 30 == 29:
            time.sleep(0.2)
    print(f"  → Body Battery: {ok}/{total} dni z danymi")
    return sorted(records, key=lambda r: r["data"])


# ── Scalanie CSV (tryb przyrostowy) ───────────────────────────────────────────

def merge_csv(existing: Path, new_records: list[dict], key_cols: list[str]) -> list[dict]:
    """Wczytuje istniejący CSV i dodaje nowe rekordy (bez duplikatów po kluczu)."""
    existing_rows: dict[tuple, dict] = {}
    if existing.exists():
        with open(existing, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                k = tuple(row[c] for c in key_cols)
                existing_rows[k] = row
    for row in new_records:
        k = tuple(str(row.get(c, "")) for c in key_cols)
        existing_rows[k] = {str(fk): str(fv) if fv is not None else "" for fk, fv in row.items()}
    return sorted(existing_rows.values(), key=lambda r: tuple(r[c] for c in key_cols))


def save_csv(records: list[dict], filepath: Path, label: str) -> None:
    if not records:
        print(f"  Brak nowych danych: {label}")
        return
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"  Zapisano {len(records)} rekordów → {filepath}")


# ── Budowanie waga.csv (Garmin + Vitalia + punkt 2012) ────────────────────────

def build_waga_csv() -> None:
    print("\n── Scalanie waga.csv ──")

    # Garmin (źródło główne)
    garmin: dict[str, dict] = {}
    if OUT_WAGA.exists():
        with open(OUT_WAGA, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                garmin[row["data"]] = {
                    "data":    row["data"],
                    "waga_kg": float(row["waga_kg"]),
                    "bmi":     float(row["bmi"]) if row["bmi"] else None,
                    "zrodlo":  "garmin",
                }

    # Vitalia (uzupełnienie starszej historii)
    vitalia: dict[str, dict] = {}
    if VITALIA_JSON.exists():
        with open(VITALIA_JSON, encoding="utf-8") as f:
            for r in json.load(f):
                d = r["measurement_date"]
                w = float(r["current_weight"]) if r.get("current_weight") else None
                if w and d not in vitalia:
                    vitalia[d] = {
                        "data":    d,
                        "waga_kg": w,
                        "bmi":     round(w / HEIGHT_M**2, 2),
                        "zrodlo":  "vitalia",
                    }

    # Scal: Garmin ma pierwszeństwo
    merged = {**vitalia, **garmin}

    # Punkt startowy 2012
    merged.setdefault("2012-07-01", {
        "data": "2012-07-01", "waga_kg": 109.0,
        "bmi": round(109.0 / HEIGHT_M**2, 2), "zrodlo": "manual",
    })

    rows = sorted(merged.values(), key=lambda r: r["data"])
    save_csv(rows, OUT_WAGA_FINAL, "waga.csv")
    n_g = sum(1 for r in rows if r["zrodlo"] == "garmin")
    n_v = sum(1 for r in rows if r["zrodlo"] == "vitalia")
    print(f"  ({n_g} Garmin + {n_v} Vitalia + 1 manual = {len(rows)} łącznie)")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _val(d: dict, key: str, divisor: float = 1.0):
    v = d.get(key)
    return round(v / divisor, 2) if v is not None else None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not EMAIL or not PASSWORD:
        sys.exit("Brak kredencjałów — uzupełnij plik .env")

    full_mode = "--full" in sys.argv

    # Wyznacz zakresy dat (przyrostowo lub pełne)
    if full_mode:
        w_start = bp_start = act_start = sleep_start = daily_start = hrv_start = bat_start = FULL_START
        print("\n  Tryb: PEŁNE pobranie od", FULL_START)
    else:
        w_start      = start_date_for(OUT_WAGA,       FULL_START)
        bp_start     = start_date_for(OUT_CISNIENIE,  FULL_START)
        act_start    = start_date_for(OUT_AKTYWNOSCI, FULL_START)
        sleep_start  = start_date_for(OUT_SEN,        FULL_START)
        daily_start  = start_date_for(OUT_METRYKI,    FULL_START)
        hrv_start    = start_date_for(OUT_HRV,        FULL_START)
        bat_start    = start_date_for(OUT_BATERIA,    FULL_START)
        print("\n  Tryb: PRZYROSTOWY (od ostatniego wpisu)")

    print(f"\n{'='*55}")
    print(f"  Garmin Connect fetch — do {END_DATE}")
    print(f"{'='*55}\n")

    client = login()
    print()

    # Waga
    print("── Waga i skład ciała ──")
    new_weight = fetch_weight(client, w_start, END_DATE)
    merged_weight = merge_csv(OUT_WAGA, new_weight, ["data"])
    save_csv(merged_weight, OUT_WAGA, "waga_garmin")

    # Ciśnienie
    print("\n── Ciśnienie krwi ──")
    new_bp = fetch_blood_pressure(client, bp_start, END_DATE)
    merged_bp = merge_csv(OUT_CISNIENIE, new_bp, ["data", "czas"])
    save_csv(merged_bp, OUT_CISNIENIE, "ciśnienie")

    # Aktywności
    print("\n── Aktywności fizyczne ──")
    new_act = fetch_activities(client, act_start, END_DATE)
    merged_act = merge_csv(OUT_AKTYWNOSCI, new_act, ["data", "czas"])
    save_csv(merged_act, OUT_AKTYWNOSCI, "aktywności")

    # Sen
    print("\n── Sen ──")
    new_sleep = fetch_sleep(client, sleep_start, END_DATE)
    merged_sleep = merge_csv(OUT_SEN, new_sleep, ["data"])
    save_csv(merged_sleep, OUT_SEN, "sen")

    # Tętno spoczynkowe / stres / oddech
    print("\n── Metryki dzienne (RHR, stres, oddech) ──")
    new_daily = fetch_daily_metrics(client, daily_start, END_DATE)
    merged_daily = merge_csv(OUT_METRYKI, new_daily, ["data"])
    save_csv(merged_daily, OUT_METRYKI, "metryki dzienne")

    # HRV
    print("\n── HRV (zmienność rytmu serca) ──")
    new_hrv = fetch_hrv(client, hrv_start, END_DATE)
    merged_hrv = merge_csv(OUT_HRV, new_hrv, ["data"])
    save_csv(merged_hrv, OUT_HRV, "HRV")

    # Body Battery
    print("\n── Body Battery ──")
    new_bat = fetch_body_battery(client, bat_start, END_DATE)
    merged_bat = merge_csv(OUT_BATERIA, new_bat, ["data"])
    save_csv(merged_bat, OUT_BATERIA, "body battery")

    # Scal waga.csv
    build_waga_csv()

    print(f"\n{'='*55}")
    print("  Gotowe!")
    print(f"  {OUT_WAGA_FINAL} ({len(merged_weight)} wag, w tym historia z Vitalia)")
    print(f"  {OUT_CISNIENIE} ({len(merged_bp)} pomiarów ciśnienia)")
    print(f"  {OUT_AKTYWNOSCI} ({len(merged_act)} aktywności)")
    print(f"  {OUT_SEN} ({len(merged_sleep)} nocy)")
    print(f"  {OUT_METRYKI} ({len(merged_daily)} dni)")
    print(f"  {OUT_HRV} ({len(merged_hrv)} nocy)")
    print(f"  {OUT_BATERIA} ({len(merged_bat)} dni)")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
