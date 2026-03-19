from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
SAMPLE_DIR = ROOT / "sample-output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PoC dla nieoficjalnego dostępu do danych FreeStyle Libre / LibreLinkUp."
    )
    parser.add_argument(
        "--save-sample",
        action="store_true",
        help="Zapisz próbkę odpowiedzi JSON do libre/sample-output/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Jawna ścieżka pliku JSON dla próbki.",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        help="Zanonimizuj zapisany payload przez usunięcie typowych pól identyfikujących.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Dołącz pełne surowe payloady connections i graph do zapisanego raportu.",
    )
    parser.add_argument(
        "--print-client-methods",
        action="store_true",
        help="Wypisz publiczne metody klienta po zalogowaniu, żeby łatwiej znaleźć endpoint historii.",
    )
    return parser.parse_args()


def load_local_env() -> None:
    if ENV_PATH.exists():
        if _load_dotenv is not None:
            _load_dotenv(ENV_PATH)
            return

        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Brak zmiennej {name}. Skopiuj libre/.env.example do libre/.env i uzupełnij dane."
        )
    return value


def import_client():
    try:
        from libre_link_up import LibreLinkUpClient
    except ImportError as exc:
        raise RuntimeError(
            "Brak biblioteki libre-linkup-py. Zainstaluj zależności: pip install -r libre/requirements.txt"
        ) from exc
    return LibreLinkUpClient


def to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain(v) for v in value]
    if hasattr(value, "model_dump"):
        return to_plain(value.model_dump())
    if hasattr(value, "dict") and callable(value.dict):
        return to_plain(value.dict())
    if hasattr(value, "__dict__"):
        return to_plain(vars(value))
    return repr(value)


def redact_payload(data: Any) -> Any:
    sensitive = {
        "email",
        "firstName",
        "first_name",
        "lastName",
        "last_name",
        "patient_id",
        "patientId",
        "userId",
        "user_id",
        "accountId",
        "account_id",
        "sensorSerial",
        "sensor_serial",
    }
    if isinstance(data, dict):
        clean: dict[str, Any] = {}
        for key, value in data.items():
            clean[key] = "<redacted>" if key in sensitive else redact_payload(value)
        return clean
    if isinstance(data, list):
        return [redact_payload(item) for item in data]
    return data


def safe_get(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def summarize_reading(reading: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": safe_get(reading, "Timestamp", "FactoryTimestamp"),
        "factory_timestamp": reading.get("FactoryTimestamp"),
        "glucose": safe_get(reading, "ValueInMgPerDl", "Value"),
        "unit": "mg/dL" if reading.get("ValueInMgPerDl") is not None else safe_get(reading, "Unit"),
        "trend": safe_get(reading, "TrendArrow", "TrendMessage", "Trend"),
        "measurement_color": reading.get("MeasurementColor"),
        "is_high": reading.get("isHigh"),
        "is_low": reading.get("isLow"),
        "type": reading.get("type"),
        "keys": sorted(reading.keys()),
    }


def summarize_latest_from_raw(raw_graph: dict[str, Any]) -> dict[str, Any]:
    connection = raw_graph.get("data", {}).get("connection", {})
    raw_reading = connection.get("glucoseMeasurement") or {}
    return summarize_reading(raw_reading)


def summarize_history_from_raw(raw_graph: dict[str, Any]) -> dict[str, Any]:
    graph_data = raw_graph.get("data", {}).get("graphData") or []
    dict_records = [reading for reading in graph_data if isinstance(reading, dict)]
    examples = [summarize_reading(reading) for reading in dict_records[:3]]
    first_reading = summarize_reading(dict_records[0]) if dict_records else None
    last_reading = summarize_reading(dict_records[-1]) if dict_records else None
    return {
        "method": "get_raw_graph_readings",
        "count": len(dict_records),
        "first": first_reading,
        "last": last_reading,
        "examples": examples,
        "meta": {
            "top_level_keys": sorted(raw_graph.keys()),
            "data_keys": sorted((raw_graph.get("data") or {}).keys()),
        },
        "available": bool(dict_records),
    }


def build_report(client: Any, include_raw: bool = False) -> dict[str, Any]:
    raw_connections = to_plain(client.get_connections())
    raw_graph = to_plain(client.get_raw_graph_readings())
    data = raw_connections.get("data") or []
    first_connection = data[0] if data and isinstance(data[0], dict) else {}
    latest = summarize_latest_from_raw(raw_graph)
    history = summarize_history_from_raw(raw_graph)
    report = {
        "source": "libre-linkup-py",
        "success": True,
        "login": {
            "country": getattr(client, "country", None),
            "connection_count": len(data),
        },
        "connection": {
            "patient_id_present": bool(first_connection.get("patientId")),
            "keys": sorted(first_connection.keys()) if isinstance(first_connection, dict) else [],
        },
        "latest": latest,
        "history": history,
    }
    if include_raw:
        report["raw"] = {
            "connections": raw_connections,
            "graph": raw_graph,
        }
    return report


def save_sample(report: dict[str, Any], args: argparse.Namespace) -> Path:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    path = args.output if args.output else SAMPLE_DIR / f"linkup-sample-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    payload = redact_payload(report) if args.redact else report
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def print_client_methods(client: Any) -> None:
    methods = sorted(
        name for name in dir(client)
        if not name.startswith("_") and callable(getattr(client, name, None))
    )
    print("Public client methods:")
    for name in methods:
        print(f"- {name}")


def main() -> int:
    args = parse_args()
    load_local_env()

    try:
        LibreLinkUpClient = import_client()
        client = LibreLinkUpClient(
            username=require_env("LIBRE_LINK_UP_USERNAME"),
            password=require_env("LIBRE_LINK_UP_PASSWORD"),
            url=require_env("LIBRE_LINK_UP_URL"),
            version=os.getenv("LIBRE_LINK_UP_VERSION", "4.16.0"),
        )
        client.login()
        report = build_report(client, include_raw=args.include_raw)
        print(json.dumps(report, indent=2, ensure_ascii=False))

        if args.print_client_methods:
            print_client_methods(client)

        if args.save_sample or args.output:
            sample_path = save_sample(report, args)
            print(f"Saved sample to: {sample_path}")
        return 0
    except Exception as exc:
        failure = {
            "source": "libre-linkup-py",
            "success": False,
            "error": str(exc),
        }
        print(json.dumps(failure, indent=2, ensure_ascii=False), file=sys.stderr)
        if args.save_sample or args.output:
            sample_path = save_sample(failure, args)
            print(f"Saved failure sample to: {sample_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
