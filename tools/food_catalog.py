"""Owner-authored nutrition records. No network or model authority here."""
from decimal import Decimal, InvalidOperation
import json
import sqlite3

from .db import get_conn


def initialize(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS food_products (
            id INTEGER PRIMARY KEY,
            barcode TEXT UNIQUE,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS food_product_versions (
            product_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(product_id, version)
        );
    """)


def validate_barcode(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) not in (8, 12, 13, 14) or not value.isascii() or not value.isdigit():
        raise ValueError("barcode format")
    total = sum(int(d) * (3 if i % 2 == 0 else 1)
                for i, d in enumerate(reversed(value[:-1])))
    if (10 - total % 10) % 10 != int(value[-1]):
        raise ValueError("barcode check digit")
    return value


def _number(value):
    if value is None or isinstance(value, bool):
        raise ValueError("nutrition required")
    try:
        number = Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        raise ValueError("invalid nutrition") from None
    if not number.is_finite() or not 0 <= number <= 10000:
        raise ValueError("invalid nutrition range")
    return float(number)


def _validated(data):
    result = {}
    for field in ("name", "brand"):
        value = data.get(field, "")
        if not isinstance(value, str) or len(value) > 200 or (field == "name" and not value.strip()):
            raise ValueError("invalid " + field)
        result[field] = value.strip()
    result["barcode"] = validate_barcode(data.get("barcode"))
    if data.get("basis") not in ("100g", "100ml"):
        raise ValueError("basis must be 100g or 100ml")
    result["basis"] = data["basis"]
    if data.get("provenance") not in ("manual", "own_label"):
        raise ValueError("invalid provenance")
    result["provenance"] = data["provenance"]
    for field in ("kcal", "protein", "carbs", "fat"):
        result[field] = _number(data.get(field))
    return result


def _record(row):
    return dict(json.loads(row["payload"]), id=row["id"], version=row["version"],
                status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"])


def get(product_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM food_products WHERE id=?", (product_id,)).fetchone()
        if row is None:
            raise ValueError("product not found")
        return _record(row)


def propose(data):
    record = _validated(data)
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False)
    try:
        with get_conn() as conn:
            cur = conn.execute("INSERT INTO food_products(barcode,version,status,payload) VALUES (?,1,'draft',?)",
                               (record["barcode"], payload))
            product_id = cur.lastrowid
            conn.execute("INSERT INTO food_product_versions(product_id,version,status,payload) VALUES (?,1,'draft',?)",
                         (product_id, payload))
    except sqlite3.IntegrityError:
        raise ValueError("barcode already exists; select existing product") from None
    return get(product_id)


def confirm(product_id, version):
    """Only trusted explicit owner action may call this; never expose as model authority."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM food_products WHERE id=?", (product_id,)).fetchone()
        if row is None or row["version"] != version or row["status"] != "draft":
            raise ValueError("stale version or non-draft product")
        conn.execute("UPDATE food_products SET version=version+1,status='confirmed',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (product_id,))
        conn.execute("INSERT INTO food_product_versions(product_id,version,status,payload) VALUES (?,?,'confirmed',?)",
                     (product_id, version + 1, row["payload"]))
    return get(product_id)
