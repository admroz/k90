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
        CREATE TABLE IF NOT EXISTS food_draft_requests (
            request_id TEXT PRIMARY KEY, payload TEXT NOT NULL, product_id INTEGER NOT NULL
        );
    """)

    from .product_review import initialize as initialize_review
    initialize_review(conn)


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


# Physical amounts have their own explicit bound, independent of nutrition limits.
# At most one million native g/ml per recorded portion or one piece.
MAX_NATIVE_AMOUNT = Decimal('1000000')


def _positive_amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError('positive finite amount required')
    try:
        amount = Decimal(str(value).replace(',', '.'))
    except InvalidOperation:
        raise ValueError('invalid amount') from None
    if not amount.is_finite() or not 0 < amount <= MAX_NATIVE_AMOUNT or float(amount) == 0:
        raise ValueError('amount outside positive finite limit')
    return amount


class MissingPieceSize(ValueError):
    """The caller must ask for the converter or a native quantity."""


def convert_portion(product, quantity, unit):
    """Shared Decimal calculation; preserve submitted units in additive snapshots."""
    amount = _positive_amount(quantity)
    native = 'g' if product['basis'] == '100g' else 'ml'
    size = None
    if unit == 'szt':
        if product.get('piece_size') is None:
            raise MissingPieceSize('Brak rozmiaru jednej sztuki; podaj masę/objętość lub ilość w ' + native)
        size = _positive_amount(product['piece_size'])
        normalized = amount * size
    elif unit == native:
        normalized = amount
    else:
        raise ValueError('unit does not match product basis')
    if not 0 < normalized <= MAX_NATIVE_AMOUNT or float(normalized) == 0:
        raise ValueError('normalized amount exceeds limit')
    nutrition = {k: Decimal(str(product[k])) * normalized / 100
                 for k in ('kcal', 'protein', 'carbs', 'fat')}
    snapshot = dict(normalized_quantity=float(normalized), normalized_unit=native,
                    piece_size=float(size) if size is not None else None,
                    piece_unit=native if size is not None else None)
    return nutrition, snapshot


def _validated(data):
    if not isinstance(data, dict):
        raise ValueError('product must be an object')
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
        if result[field] > (1000 if field == 'kcal' else 100):
            raise ValueError('nutrition exceeds per100 limit')
    if 'piece_size' in data:
        result['piece_size'] = (None if data['piece_size'] is None
                                else float(_positive_amount(data['piece_size'])))
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


def propose(data, *, source_event_id=None, request_id=None, owner=None):
    from .product_review import owner as configured_owner
    owner = configured_owner() if owner is None else owner
    record = _validated(data)
    if record['provenance'] == 'own_label' and source_event_id is None:
        raise ValueError('own_label requires submitted photo; use manual entry otherwise')
    if source_event_id is not None:
        record['source_event_id'] = source_event_id
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False)
    if request_id is not None and (not isinstance(request_id, str) or not 1 <= len(request_id) <= 100):
        raise ValueError('invalid request id')
    try:
        with get_conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if source_event_id is not None:
                source = conn.execute("SELECT payload FROM agent_events WHERE id=? AND owner=? AND role='user'",
                                      (source_event_id, owner)).fetchone()
                content = json.loads(source[0]) if source else []
                photos = [p for p in content if isinstance(p, dict) and p.get('type') == 'image_url'] if isinstance(content, list) else []
                if len(photos) > 1:
                    prior = conn.execute("SELECT * FROM food_products WHERE owner=? AND json_extract(payload,'$.source_event_id')=? ORDER BY id LIMIT 1",
                                         (owner, source_event_id)).fetchone()
                    if prior:
                        if prior['payload'] != payload:
                            raise ValueError('Jedna paczka zdjęć może mieć tylko jedną propozycję. Sprzeczne produkty lub wartości wymagają wyjaśnienia; nie twórz kolejnego szkicu.')
                        return _record(prior)
            if request_id:
                previous = conn.execute('SELECT * FROM food_draft_requests WHERE request_id=?', (request_id,)).fetchone()
                if previous:
                    bound = conn.execute('SELECT owner FROM food_products WHERE id=?', (previous['product_id'],)).fetchone()
                    if previous['payload'] != payload or bound['owner'] != owner:
                        raise ValueError('request id conflict')
                    return _record(conn.execute('SELECT * FROM food_products WHERE id=?', (previous['product_id'],)).fetchone())
            cur = conn.execute("INSERT INTO food_products(barcode,version,status,payload,owner) VALUES (?,1,'draft',?,?)",
                               (record["barcode"], payload, owner))
            product_id = cur.lastrowid
            conn.execute("INSERT INTO food_product_versions(product_id,version,status,payload) VALUES (?,1,'draft',?)",
                         (product_id, payload))
            if request_id:
                conn.execute('INSERT INTO food_draft_requests VALUES (?,?,?)', (request_id, payload, product_id))
            result = _record(conn.execute('SELECT * FROM food_products WHERE id=?', (product_id,)).fetchone())
    except sqlite3.IntegrityError:
        raise ValueError("barcode already exists; select existing product") from None
    return result


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
    import hashlib
    key = ('event:' + str(event_id) + ':' + hashlib.sha256(json.dumps(_validated(product), sort_keys=True).encode()).hexdigest()[:32]) if event_id else None
    from .product_review import _context_products, _closed_context
    with get_conn() as conn:
        replay = conn.execute('SELECT 1 FROM food_draft_requests WHERE request_id=?', (key,)).fetchone()
        if turn and not replay and any(p['status'] == 'draft' and not _closed_context(conn, turn, p['id'])
                                      for p in _context_products(conn, turn)):
            raise ValueError('Istnieje bieżący szkic: użyj revise_food_product z samymi zmienionymi polami lub wyjaśnij cel.')
    draft = propose(product, source_event_id=event_id, request_id=key, owner=turn.get('owner'))
    from .product_review import queue_preview
    queue_preview(draft)
    draft['review_instruction'] = 'Backend pokaże pełny podgląd. Wymagana osobna zgoda użytkownika.'
    return draft



CATALOG_PROMPT = """Katalog produktów: własna etykieta i korekty właściciela są źródłem prawdy.
Zdjęcie posiłku nadal obsługuj jako posiłek; nie jest etykietą produktu.
Gdy użytkownik chce zachować etykietę, odczytaj WSZYSTKIE bieżące zdjęcia łącznie jako jeden produkt i użyj propose_food_product najwyżej raz:
Zdjęcia kodu, nazwy/logo i makr to wspólne dowody, nie osobne produkty.
Przed szkicem zapytaj o wyjaśnienie, gdy zdjęcia przedstawiają różne produkty, sprzeczne kody/nazwy,
nieczytelne dane lub niejasną podstawę 100g vs 100ml, porcję vs opakowanie czy rozmiar zbiorczy.
Nie sumuj makr z etykiet. Masa opakowania nie oznacza ilości spożytej ani podstawy makr.
podaj nazwę, markę, opcjonalny kod, podstawę 100g lub 100ml, kcal, protein, carbs, fat oraz provenance own_label.
Brakujące lub nieczytelne wartości wyjaśnij z użytkownikiem; nigdy nie zgaduj ani nie zastępuj zerem.
Backend pokazuje pełny podgląd i obsługuje zgodę, korektę oraz anulowanie lokalnie.
Kontynuacja rozmowy (kolejne zdjęcie, doprecyzowanie nazwy, marki, makr, podstawy lub sztuki):
użyj revise_food_product z samymi zmienionymi polami, NIE propose_food_product i nie twórz duplikatu.
Odczytaj tekst i wszystkie bieżące zdjęcia łącznie. Zachowaj pominięte pola; nie zgaduj brakujących.
Niejasność lub sprzeczne dane wyjaśnij pytaniem. Pytanie o zapis/stan: review_food_product.
Każda korekta wymaga nowego podglądu i osobnego tak/ok; zgoda razem ze zmianą nie zatwierdza nowej wersji.
Nie udzielaj zgody w imieniu użytkownika. Nie twierdź, że szkic jest zatwierdzony.
Korekty można wprowadzić w panelu Katalog; wpis ręczny ma provenance manual.
Przy ponownym użyciu najpierw find_food_products po kodzie, potem nazwie; wybierz dokładny potwierdzony produkt i wersję.
Użyj jednego log_meal dla całego logicznego posiłku: pełne ingredients (product_id, version, quantity, unit g dla100g lub ml dla100ml albo szt).
Opcjonalne piece_size to znana masa/objętość JEDNEJ sztuki w g/ml zgodnie z podstawą.
Nie wyliczaj jej z opakowania, liczby sztuk ani gęstości. Dla szt (także ułamkowych) bez piece_size dopytaj o rozmiar sztuki lub ilość w jednostce natywnej.
Nie obliczaj makr ani konwersji samodzielnie; robi to serwer.
remainder zawiera opis i komplet oszacowań WYŁĄCZNIE części spoza katalogu (np. owoce); null oznacza brak reszty.
Dla całkowicie szacowanego posiłku ingredients=[] i remainder obejmuje cały posiłek. Nie doliczaj katalogowych makr do reszty.
Nie używaj log_food_portion w rozmowie. Jeden nowy posiłek na wiadomość; przy kilku niejednoznacznych posiłkach lub brakujących ilościach/oszacowaniach dopytaj.
Makra katalogu oblicza serwer; po sukcesie podaj zwrócone meal_id, datę i czas. Replay to wynik historyczny; bieżący stan może się różnić.
Gdy brak lokalnego kodu, lookup_food_barcode używa OFF tylko jako zapasowego źródła: wynik unverified nie jest etykietą właściciela ani produktem do logowania.
Nie importuj wartości OFF jako manual/own_label. Poproś o własną etykietę lub ręczne sprawdzone wartości.
"""


def label_image(product_id):
    import os
    product = get(product_id)
    with get_conn() as conn:
        row = conn.execute("SELECT payload FROM agent_events WHERE id=? AND owner=? AND role='user'",
                           (product.get('source_event_id'), os.getenv('CONVERSATION_USER_ID', 'owner'))).fetchone()
    content = json.loads(row['payload']) if row else []
    images = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, dict) and part.get('type') == 'image_url':
            url = part.get('image_url', {}).get('url', '')
            if isinstance(url, str) and url.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
                images.append(url)
    if images:
        return {'image':images[0], 'images':images}
    raise ValueError('label photo unavailable')


def confirm(product_id, version, *, owner=None, source_event_id=None):
    """Trusted panel/command only. Models have no confirmation tool."""
    from .product_review import owner as configured_owner, _confirm
    owner = configured_owner() if owner is None else owner
    _version(version)
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM food_products WHERE id=?', (product_id,)).fetchone()
        if row is None or owner != configured_owner():
            raise ValueError('owner or version mismatch')
        _confirm(conn, row, version, owner, source_event_id)
        return _record(conn.execute('SELECT * FROM food_products WHERE id=?', (product_id,)).fetchone())


def search(query="", barcode=None):
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("invalid query")
    with get_conn() as conn:
        conn.create_function('catalog_fold', 1, lambda s: s.casefold())
        if barcode is not None:
            rows = conn.execute("SELECT * FROM food_products WHERE barcode=?", (validate_barcode(barcode),)).fetchall()
        else:
            # instr is literal: wildcard characters never broaden a query.
            rows = conn.execute("SELECT * FROM food_products WHERE instr(catalog_fold(json_extract(payload,'$.name') || ' ' || json_extract(payload,'$.brand')),catalog_fold(?))>0 ORDER BY id DESC LIMIT 30", (query,)).fetchall()
        return [_record(row) for row in rows]


def panel_preview(product_id, version, *, owner=None):
    """Explicit current-version preview, including legacy unowned panel products.

    Like /produkt pokaz, only the configured owner may bind an unowned record.
    Listing/getting, revising and confirming never implicitly claim ownership.
    """
    from .product_review import owner as configured_owner
    owner = configured_owner() if owner is None else owner
    _version(version)
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM food_products WHERE id=?', (product_id,)).fetchone()
        if (owner != configured_owner() or row is None or row['version'] != version
                or row['owner'] not in (None, owner)):
            raise ValueError('owner or version mismatch; preview required')
        if row['owner'] is None:
            conn.execute('UPDATE food_products SET owner=? WHERE id=? AND version=? AND owner IS NULL',
                         (owner, product_id, version))
        return _record(row)


def _revise(conn, old, version, data, owner):
    _version(version)
    if old is None or old['version'] != version or old['owner'] != owner:
        raise ValueError('owner or version mismatch; preview required')
    if not isinstance(data, dict):
        raise ValueError('product must be an object')
    original = json.loads(old['payload'])
    if (data.get('basis', original['basis']) != original['basis']
            and original.get('piece_size') is not None and 'piece_size' not in data):
        raise ValueError('basis change requires explicit new piece_size or null')
    record = _validated(dict(original, **data))
    if original.get('source_event_id') is not None:
        record['source_event_id'] = original['source_event_id']
    if record['provenance'] == 'own_label':
        evidence = conn.execute("SELECT payload FROM agent_events WHERE id=? AND owner=? AND role='user'", (record.get('source_event_id'),owner)).fetchone()
        content = json.loads(evidence[0]) if evidence else None
        if not isinstance(content, list) or not any(isinstance(p, dict) and p.get('type') == 'image_url' for p in content):
            raise ValueError('own_label requires original photo')
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False)
    cur = conn.execute("UPDATE food_products SET version=version+1,status='draft',barcode=?,payload=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=? AND owner=?",
                       (record['barcode'], payload, old['id'], version, owner))
    if cur.rowcount != 1:
        raise ValueError('stale version')
    conn.execute("INSERT INTO food_product_versions(product_id,version,status,payload) VALUES (?,?,'draft',?)",(old['id'],version+1,payload))
    conn.execute("UPDATE food_product_reviews SET status='cancelled',reason='revised' WHERE product_id=? AND status='pending'",(old['id'],))
    return _record(conn.execute('SELECT * FROM food_products WHERE id=?',(old['id'],)).fetchone())


def revise(product_id, version, data, *, owner=None):
    from .product_review import owner as configured_owner
    owner = configured_owner() if owner is None else owner
    if owner != configured_owner():
        raise ValueError('owner mismatch')
    try:
        with get_conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT * FROM food_products WHERE id=?',(product_id,)).fetchone()
            return _revise(conn,old,version,data,owner)
    except sqlite3.IntegrityError:
        raise ValueError('barcode already exists') from None


def log_portion(product_id, version, quantity, unit, request_id):
    _version(product_id)
    _version(version)
    amount = float(_positive_amount(quantity))
    if unit not in ('g', 'ml', 'szt'):
        raise ValueError('explicit g/ml/szt required')
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
        calculated, conversion = convert_portion(product, quantity, unit)
        nutrition = {k:float(v) for k,v in calculated.items()}
        now = now_local()
        cur = conn.execute("INSERT INTO posilki(data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g,zrodlo) VALUES (?,?,?,?,?,?,?,'catalog')",
                           (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
                            f"{product['name']} — {amount:g} {unit}", nutrition['kcal'], nutrition['protein'], nutrition['carbs'], nutrition['fat']))
        result = dict(meal_id=cur.lastrowid, product=product, quantity=amount, unit=unit, nutrition=nutrition, **conversion)
        conn.execute('INSERT INTO food_portions VALUES (?,?,?,?)',
                     (request_id, fingerprint, json.dumps(result, ensure_ascii=False), cur.lastrowid))
        return result


def _version(value):
    if type(value) is not int or not 1 <= value < 2**63 - 1:
        raise ValueError('invalid version')


def log_portion_from_chat(product_id, version, quantity, unit, request_id):
    _version(product_id)
    from memory_runtime import TURN_CONTEXT
    import hashlib
    turn = TURN_CONTEXT.get()
    if not turn:
        raise ValueError('portion tool requires active conversation turn')
    identity = json.dumps([turn['owner'], turn['request_id'], product_id, version, _number(quantity), unit])
    trusted_key = 'chat:' + hashlib.sha256(identity.encode()).hexdigest()
    return log_portion(product_id, version, quantity, unit, trusted_key)
