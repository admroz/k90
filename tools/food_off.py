"""Read-only OFF backup. Only validated public barcodes leave the application."""
import json
import time
from decimal import Decimal

import requests

from .db import get_conn
from .food_catalog import validate_barcode, search, _number

FIELDS = 'code,product_name,brands,countries_tags,nutrition_data_per,nutriments,product_quantity_unit'
USER_AGENT = 'k90-food-catalog/0.1 (https://github.com/hermesinski/k90)'
LIMIT = 262144


def initialize(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS food_external_cache (
            barcode TEXT PRIMARY KEY, payload TEXT NOT NULL, expires REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS food_external_rate (
            id INTEGER PRIMARY KEY CHECK(id=1), next_at REAL NOT NULL
        );
    ''')


def decode(raw):
    if len(raw) > LIMIT:
        raise ValueError('OFF response too large')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('OFF duplicate JSON key')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('OFF nonfinite JSON')))
    except (ValueError, RecursionError, UnicodeError):
        raise ValueError('OFF invalid JSON') from None
    def walk(item, depth=0):
        if depth > 16:
            raise ValueError('OFF response too deep')
        if isinstance(item, dict):
            for v in item.values(): walk(v, depth+1)
        elif isinstance(item, list):
            for v in item: walk(v, depth+1)
    walk(value)
    return value


def parse(data, code):
    try:
        if data.get('result', {}).get('id') != 'product_found':
            raise ValueError('OFF product not found')
        p = data['product']
        tags = p.get('countries_tags')
        if p.get('code') != code or not isinstance(tags, list) or not all(isinstance(t, str) for t in tags) or 'en:poland' not in tags:
            raise ValueError('OFF barcode/Polish market not verified')
        basis = p.get('nutrition_data_per')
        if basis not in ('100g', '100ml'):
            raise ValueError('OFF ambiguous nutrition basis')
        # Legacy _100g keys also represent liquids. Require an independent ml unit
        # before using that schema for liquids, otherwise ask for the own label.
        if basis == '100ml' and p.get('product_quantity_unit') != 'ml':
            raise ValueError('OFF ambiguous liquid units; use own label')
        name, brand = p.get('product_name'), p.get('brands', '')
        if not isinstance(name, str) or not name.strip() or len(name) > 200 or not isinstance(brand, str) or len(brand) > 200:
            raise ValueError('OFF invalid product identity')
        n = p['nutriments']
        result = dict(name=name, brand=brand, barcode=code, basis=basis,
                      status='unverified', provenance='openfoodfacts',
                      attribution='Open Food Facts — ODbL 1.0 / Database Contents License 1.0',
                      source_url='https://world.openfoodfacts.org/product/'+code,
                      license_url='https://opendatacommons.org/licenses/odbl/1.0/')
        for target, source in [('protein','proteins'),('carbs','carbohydrates'),('fat','fat')]:
            result[target] = _number(n[source+'_100g'])
            if result[target] > 100:
                raise ValueError('OFF invalid macros')
        if n.get('energy-kcal_100g') is not None:
            result['kcal'] = _number(n['energy-kcal_100g'])
        else:
            result['kcal'] = float(Decimal(str(_number(n['energy-kj_100g']))) / Decimal('4.184'))
            result['energy_conversion'] = 'kJ / 4.184'
        return result
    except (KeyError, TypeError, AttributeError):
        raise ValueError('OFF incomplete/invalid product; use own label') from None


def _fetch(code):
    started = time.monotonic()
    with requests.Session() as session:
        session.trust_env = False
        with session.get('https://world.openfoodfacts.org/api/v3/product/'+code,
                         params={'fields':FIELDS}, headers={'User-Agent':USER_AGENT, 'Accept':'application/json', 'Accept-Encoding':'identity'},
                         timeout=(3, 5), allow_redirects=False, stream=True) as r:
            if r.status_code == 429:
                try:
                    delay = min(86400, max(60, int(r.headers.get('Retry-After', '60'))))
                except ValueError:
                    delay = 3600
                with get_conn() as conn:
                    conn.execute('UPDATE food_external_rate SET next_at=? WHERE id=1', (time.time()+delay,))
                raise ValueError('OFF rate limited; retry later; local catalog available')
            if r.status_code != 200:
                raise ValueError('OFF unavailable/not found; local catalog available')
            if r.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise ValueError('OFF unsupported response encoding')
            raw = bytearray()
            # A large buffered chunk can wait forever while a peer drips bytes
            # within the per-read timeout. Check the deadline after each byte.
            for chunk in r.iter_content(1):
                raw.extend(chunk)
                if len(raw) > LIMIT or time.monotonic()-started > 12:
                    raise ValueError('OFF response limit exceeded')
            return decode(raw)


def lookup(barcode):
    code = validate_barcode(barcode)
    if code is None:
        raise ValueError('barcode required')
    local = search(barcode=code)
    if local:
        return local[0]
    now = time.time()
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        cached = conn.execute('SELECT * FROM food_external_cache WHERE barcode=? AND expires>?', (code, now)).fetchone()
        if cached:
            return json.loads(cached['payload'])
        rate = conn.execute('SELECT next_at FROM food_external_rate WHERE id=1').fetchone()
        if rate and rate[0] > now:
            raise ValueError('OFF cooldown; retry later; local catalog available')
        conn.execute('INSERT OR REPLACE INTO food_external_rate VALUES (1,?)', (now+10,))
    try:
        result = parse(_fetch(code), code)
    except requests.RequestException:
        raise ValueError('OFF network unavailable; use local catalog or own label') from None
    with get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO food_external_cache VALUES (?,?,?)',
                     (code, json.dumps(result, ensure_ascii=False), time.time()+86400))
    # A local edit may have arrived during the GET. It always wins.
    local = search(barcode=code)
    return local[0] if local else result
