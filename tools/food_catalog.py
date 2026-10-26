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
        CREATE TABLE IF NOT EXISTS food_portions (
            request_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            meal_id INTEGER NOT NULL
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


def propose(data, *, source_event_id=None):
    record = _validated(data)
    if source_event_id is not None:
        record['source_event_id'] = source_event_id
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


def propose_from_chat(product):
    from memory_runtime import TURN_CONTEXT
    turn = TURN_CONTEXT.get() or {}
    event_id = turn.get('user_event_id')
    if product.get('provenance') == 'own_label':
        with get_conn() as conn:
            row = conn.execute("SELECT payload FROM agent_events WHERE id=? AND owner=? AND role='user'",
                               (event_id, turn.get('owner'))).fetchone()
        content = json.loads(row['payload']) if row else None
        if not isinstance(content, list) or not any(isinstance(p, dict) and p.get('type') == 'image_url' for p in content):
            raise ValueError('own_label requires current submitted photo')
    draft = propose(product, source_event_id=event_id)
    draft['review_instruction'] = f"Sprawdź nazwę, podstawę i kcal/B/W/T. Zatwierdź dokładnie: /produkt zatwierdz {draft['id']} {draft['version']} albo popraw w panelu Katalog."
    return draft


def approval_command(message):
    if not isinstance(message, str) or not message.startswith('/produkt zatwierdz '):
        return None
    parts = message.split()
    if len(parts) != 4 or not parts[2].isascii() or not parts[2].isdigit() or not parts[3].isascii() or not parts[3].isdigit():
        return 'Użyj: /produkt zatwierdz ID WERSJA'
    try:
        p = confirm(int(parts[2]), int(parts[3]))
    except ValueError as exc:
        return 'Nie zatwierdzono: ' + str(exc)
    return f"Produkt {p['id']} zatwierdzony: {p['name']}, {p['basis']}: {p['kcal']} kcal / B {p['protein']} / W {p['carbs']} / T {p['fat']}."


CATALOG_PROMPT = """Katalog produktów: własna etykieta i korekty właściciela są źródłem prawdy.
Zdjęcie posiłku nadal obsługuj jako posiłek; nie jest etykietą produktu.
Gdy użytkownik chce zachować etykietę, odczytaj bieżące zdjęcie i użyj propose_food_product:
podaj nazwę, markę, opcjonalny kod, podstawę 100g lub 100ml, kcal, protein, carbs, fat oraz provenance own_label.
Brakujące lub nieczytelne wartości wyjaśnij z użytkownikiem; nigdy nie zgaduj ani nie zastępuj zerem.
Pokaż wszystkie wartości i jednostkę do kontroli oraz dokładną komendę /produkt zatwierdz ID WERSJA z wyniku narzędzia.
Tylko ta jawna komenda użytkownika lub przycisk panelu potwierdza wersję. Nie twierdź, że szkic jest zatwierdzony.
Korekty można wprowadzić w panelu Katalog; wpis ręczny ma provenance manual.
Przy ponownym użyciu najpierw find_food_products po kodzie, potem nazwie; wybierz dokładny potwierdzony produkt i wersję.
log_food_portion oblicza i zapisuje porcję deterministycznie: ilość g dla100g lub ml dla100ml.
Nie zapisuj tej samej porcji ponownie przez log_meal. Przekaż stały unikalny request_id dla powtórzenia tej samej operacji.
"""


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


def search(query="", barcode=None):
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("invalid query")
    with get_conn() as conn:
        if barcode is not None:
            rows = conn.execute("SELECT * FROM food_products WHERE barcode=?", (validate_barcode(barcode),)).fetchall()
        else:
            # instr is literal: wildcard characters never broaden a query.
            rows = conn.execute("SELECT * FROM food_products WHERE instr(lower(json_extract(payload,'$.name') || ' ' || json_extract(payload,'$.brand')),lower(?))>0 ORDER BY id DESC LIMIT 30", (query,)).fetchall()
        return [_record(row) for row in rows]


def revise(product_id, version, data):
    record = _validated(data)
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False)
    try:
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("UPDATE food_products SET version=version+1,status='draft',barcode=?,payload=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=?",
                               (record['barcode'], payload, product_id, version))
            if cur.rowcount != 1:
                raise ValueError("stale version")
            conn.execute("INSERT INTO food_product_versions(product_id,version,status,payload) VALUES (?,?,'draft',?)",
                         (product_id, version + 1, payload))
    except sqlite3.IntegrityError:
        raise ValueError("barcode already exists") from None
    return get(product_id)


def log_portion(product_id, version, quantity, unit, request_id):
    amount = _number(quantity)
    if amount <= 0 or unit not in ('g', 'ml'):
        raise ValueError("positive quantity and explicit g/ml required")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
        raise ValueError("request id required")
    fingerprint = json.dumps([product_id, version, amount, unit])
    from .time_utils import now_local
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT * FROM food_portions WHERE request_id=?', (request_id,)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise ValueError('request id conflict')
            return json.loads(previous['snapshot'])
        row = conn.execute('SELECT * FROM food_products WHERE id=?', (product_id,)).fetchone()
        if row is None or row['status'] != 'confirmed' or row['version'] != version:
            raise ValueError('confirmed current version required')
        product = _record(row)
        if product['basis'] != '100' + unit:
            raise ValueError('unit does not match product basis')
        nutrition = {key: float(Decimal(str(product[key])) * Decimal(str(amount)) / 100)
                     for key in ('kcal', 'protein', 'carbs', 'fat')}
        now = now_local()
        cur = conn.execute("INSERT INTO posilki(data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g,zrodlo) VALUES (?,?,?,?,?,?,?,'catalog')",
                           (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
                            f"{product['name']} — {amount:g} {unit}", nutrition['kcal'], nutrition['protein'], nutrition['carbs'], nutrition['fat']))
        result = dict(meal_id=cur.lastrowid, product=product, quantity=amount, unit=unit, nutrition=nutrition)
        conn.execute('INSERT INTO food_portions VALUES (?,?,?,?)',
                     (request_id, fingerprint, json.dumps(result, ensure_ascii=False), cur.lastrowid))
        return result
