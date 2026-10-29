"""Meal mutations: one local transaction per operation, never across inference."""
import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import closing
from datetime import date as Date, time as Time
from decimal import Decimal

from .db import get_conn, rows_to_list
from .time_utils import date_days_ago, now_local

MACROS = ('calories', 'protein_g', 'carbs_g', 'fat_g')


def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS meal_operations (
        operation_id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,
        slot TEXT NOT NULL, fingerprint TEXT NOT NULL, kind TEXT NOT NULL,
        meal_id INTEGER NOT NULL, result TEXT NOT NULL,
        committed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(owner, request_id, slot))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS meal_ingredients (
        meal_id INTEGER PRIMARY KEY, snapshot TEXT NOT NULL)""")
    if 'revision' not in {r[1] for r in conn.execute('PRAGMA table_info(posilki)')}:
        conn.execute('ALTER TABLE posilki ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')

    for column, sql_type in [('quantity', 'REAL'), ('unit', 'TEXT')]:
        if column not in {r[1] for r in conn.execute('PRAGMA table_info(posilki)')}:
            conn.execute(f'ALTER TABLE posilki ADD COLUMN {column} {sql_type}')
    conn.execute("""CREATE TABLE IF NOT EXISTS meal_changes (
        operation_id TEXT PRIMARY KEY, meal_id INTEGER NOT NULL, revision INTEGER NOT NULL,
        actor TEXT NOT NULL, channel TEXT NOT NULL, kind TEXT NOT NULL,
        before_json TEXT NOT NULL, after_json TEXT,
        changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def _nullable_number(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1000000:
        raise ValueError('number must be null or finite JSON number in 0..1000000')
    return value


def _text(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('invalid ' + name)
    return value.strip()


def _macros(values):
    from .food_catalog import _number
    return {k: _number(values.get(k)) for k in MACROS}


def _ingredients(conn, items, remainder):
    from .food_catalog import _record, _version, convert_portion
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError('complete ingredients list required; use [] for estimated meal')
    totals = {k: Decimal(0) for k in MACROS}
    snapshots = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {'product_id', 'version', 'quantity', 'unit'}:
            raise ValueError('invalid ingredient')
        _version(item['product_id']); _version(item['version'])
        row = conn.execute('SELECT * FROM food_products WHERE id=?', (item['product_id'],)).fetchone()
        if row is None or row['status'] != 'confirmed' or row['version'] != item['version']:
            raise ValueError('confirmed current catalog version required')
        product = _record(row)
        calculated, conversion = convert_portion(product, item['quantity'], item['unit'])
        nutrition = {k:calculated[source] for k,source in zip(MACROS, ('kcal','protein','carbs','fat'))}
        for k in MACROS: totals[k] += nutrition[k]
        snapshots.append(dict(item, **conversion, product=product, nutrition={k:float(v) for k,v in nutrition.items()}))
    rest = None
    if remainder is not None:
        if not isinstance(remainder, dict) or set(remainder) != {'description', *MACROS}:
            raise ValueError('explicit estimates for noncatalog remainder required')
        rest = dict(description=_text(remainder['description'], 'remainder'), **_macros(remainder))
        for k in MACROS: totals[k] += Decimal(str(rest[k]))
    if not items and rest is None:
        raise ValueError('meal requires ingredients or estimated noncatalog remainder')
    return {k:float(v) for k,v in totals.items()}, dict(ingredients=snapshots, remainder=rest)


def _perform(kind, args, *, owner, request_id, operation_id, chat):
    meal_id = args.get('meal_id')
    if kind != 'log_meal' and (type(meal_id) is not int or not 1 <= meal_id < 2**63):
        raise ValueError('invalid meal id')
    slot = 'new-meal' if kind == 'log_meal' else f'{kind}:{meal_id}'
    fingerprint = hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    with closing(get_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        prior = conn.execute('SELECT * FROM meal_operations WHERE owner=? AND request_id=? AND slot=?',
                             (owner, request_id, slot)).fetchone()
        if prior:
            if prior['fingerprint'] != fingerprint:
                return dict(success=False, error='operation conflict; ask for clarification in a new message',
                            operation_id=operation_id, meal_id=prior['meal_id'], code=409)
            return dict(json.loads(prior['result']), replayed=True, historical=True,
                        notice='Previously committed effect; current meal state may differ.')
        existing = None
        if kind != 'log_meal':
            existing = conn.execute('SELECT * FROM posilki WHERE id=?', (meal_id,)).fetchone()
            if existing is None:
                return dict(success=False, error='meal not found', status='nie znaleziono',
                            id=meal_id, meal_id=meal_id, operation_id=operation_id, code=404)
            expected = args.get('expected_revision')
            # Legacy direct callers may change only an untouched revision. Chat must
            # read and supply a revision, preventing old context from overwriting WWW.
            if expected is None and not chat:
                expected = 1
            if type(expected) is not int or expected < 1:
                raise ValueError('expected_revision required')
            if expected != existing['revision']:
                return dict(success=False, error='Posiłek został zmieniony. Odczytaj aktualną wersję przed ponowną korektą.', code=409)
        snapshot = None
        if kind != 'delete_meal':
            description = _text(args['description'], 'description')
            now = now_local()
            meal_date = args.get('date') or (existing['data'] if existing else now.strftime('%Y-%m-%d'))
            meal_time = args['time'] if 'time' in args and kind == 'update_meal' and not chat else (args.get('time') or (existing['czas'] if existing and existing['czas'] else now.strftime('%H:%M')))
            if Date.fromisoformat(meal_date).isoformat() != meal_date or (meal_time is not None and Time.fromisoformat(meal_time).strftime('%H:%M') != meal_time):
                raise ValueError('date/time must be YYYY-MM-DD / HH:MM')
            if kind == 'log_meal' and (chat or args.get('ingredients') is not None):
                if args.get('remainder') == '__missing__':
                    raise ValueError('identify estimated noncatalog remainder explicitly, or null if none')
                nutrition, snapshot = _ingredients(conn, args.get('ingredients'), args.get('remainder'))
            else:
                nutrition = ({k: _nullable_number(args[k]) for k in MACROS}
                             if kind == 'update_meal' else _macros(args))
            values = (meal_date, meal_time, description, *(nutrition[k] for k in MACROS))
            if kind == 'log_meal':
                cur = conn.execute("INSERT INTO posilki(data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g,zrodlo) VALUES (?,?,?,?,?,?,?,'manual')", values)
                meal_id = cur.lastrowid
                if snapshot is not None:
                    conn.execute('INSERT INTO meal_ingredients VALUES (?,?)', (meal_id, json.dumps(snapshot, ensure_ascii=False)))
            else:
                quantity = _nullable_number(args.get('quantity', existing['quantity']))
                unit = args.get('unit', existing['unit'])
                if (quantity is None) != (unit is None) or unit not in (None, 'g', 'ml', 'szt'):
                    raise ValueError('quantity and g/ml/szt unit must be supplied together')
                conn.execute('UPDATE posilki SET data=?,czas=?,opis=?,kalorie=?,bialko_g=?,weglowodany_g=?,tluszcze_g=?,revision=revision+1,quantity=?,unit=? WHERE id=? AND revision=?', (*values, quantity, unit, meal_id, expected))
        else:
            conn.execute('DELETE FROM posilki WHERE id=? AND revision=?', (meal_id, expected))
        revision = (existing['revision'] + 1) if existing else 1
        if existing:
            after = conn.execute('SELECT * FROM posilki WHERE id=?', (meal_id,)).fetchone()
            conn.execute('INSERT INTO meal_changes(operation_id,meal_id,revision,actor,channel,kind,before_json,after_json) VALUES (?,?,?,?,?,?,?,?)',
                         (operation_id,meal_id,revision,owner,'chat' if chat else 'web' if request_id.startswith('web-meal:') else 'local',kind,
                          json.dumps(dict(existing)), json.dumps(dict(after)) if after else None))
        result = dict(success=True, revision=revision, id=meal_id, meal_id=meal_id, operation_id=operation_id,
                      status={'log_meal':'zapisano','update_meal':'zaktualizowano','delete_meal':'usunięto'}[kind])
        if kind != 'delete_meal': result.update(data=meal_date, czas=meal_time, nutrition=nutrition)
        conn.execute('INSERT INTO meal_operations(operation_id,owner,request_id,slot,fingerprint,kind,meal_id,result) VALUES (?,?,?,?,?,?,?,?)',
                     (operation_id, owner, request_id, slot, fingerprint, kind, meal_id, json.dumps(result)))
    return result


def _mutate(kind, args):
    from memory_runtime import TURN_CONTEXT
    turn = TURN_CONTEXT.get() or {}
    slot = 'new-meal' if kind == 'log_meal' else f"{kind}:{args.get('meal_id')}"
    owner = turn.get('owner', 'local')
    request_id = turn.get('request_id') or str(uuid.uuid4())
    operation_id = hashlib.sha256(json.dumps([owner, request_id, slot]).encode()).hexdigest()[:32]
    from .food_catalog import MissingPieceSize
    try:
        return _perform(kind, args, owner=owner, request_id=request_id, operation_id=operation_id, chat=bool(turn))
    except MissingPieceSize as exc:
        return dict(success=False, error=str(exc), operation_id=operation_id, meal_id=args.get('meal_id'))
    except (ValueError, TypeError, OverflowError):
        return dict(success=False, error='invalid meal contract, estimates, target or current catalog version',
                    operation_id=operation_id, meal_id=args.get('meal_id'))
    except sqlite3.Error:
        return dict(success=False, error='meal operation failed; check durable operation outcome',
                    operation_id=operation_id, meal_id=args.get('meal_id'))


def log_meal(description, calories=None, protein_g=None, carbs_g=None, fat_g=None,
             notes=None, date=None, time=None, ingredients=None, remainder='__missing__'):
    return _mutate('log_meal', locals())


def update_meal(meal_id, description, calories, protein_g, carbs_g, fat_g, notes=None, date=None, time=None, expected_revision=None, quantity=None, unit=None):
    args = locals().copy()
    if quantity is None and unit is None:
        args.pop("quantity"); args.pop("unit")
    return _mutate('update_meal', args)


def delete_meal(meal_id, expected_revision=None):
    return _mutate('delete_meal', locals())


def committed_operations(owner, request_id, *, conn=None):
    if conn is None:
        with closing(get_conn()) as connection:
            return committed_operations(owner, request_id, conn=connection)
    return [dict(r) for r in conn.execute('SELECT operation_id,kind,meal_id FROM meal_operations WHERE owner=? AND request_id=? ORDER BY committed_at, rowid', (owner, request_id))]


def failure_outcome(owner, request_id, *, conn=None):
    operations = committed_operations(owner, request_id, conn=conn)
    prefix = 'Nie udało się zakończyć odpowiedzi.'
    if not operations:
        return prefix + ' Rejestr operacji posiłków: 0 zatwierdzonych. Inne operacje mogły zostać wykonane.'
    ids = '; '.join(f"{o['kind']}: meal_id={o['meal_id']}, operation_id={o['operation_id']}" for o in operations)
    return prefix + f' Zatwierdzone operacje posiłków ({len(operations)}): ' + ids + '. To wynik historyczny; bieżący stan może się różnić. Inne operacje mogły zostać wykonane.'


def get_recent_meals(days: int = 3) -> list[dict]:
    """Pobiera ostatnio zalogowane posiłki.

    Args:
        days: Liczba dni wstecz (domyślnie 3).

    Returns:
        Lista posiłków: data, czas, opis, kalorie, makroskładniki.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, data, czas, opis, kalorie, bialko_g, weglowodany_g, tluszcze_g, revision, quantity, unit
               FROM posilki
               WHERE data >= ?
               ORDER BY data DESC, czas DESC""",
            (date_days_ago(days),)
        ).fetchall()
    return rows_to_list(rows)
