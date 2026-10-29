"""Deterministic, owner-bound product review. Never exposed as model authority."""
import json
import os
import re
from .db import get_conn

CLARIFY = 'Pokaż konkretny aktualny podgląd: /produkt pokaz ID WERSJA. Następnie potwierdź osobną wiadomością.'


def owner():
    return os.getenv('CONVERSATION_USER_ID', 'owner')


def initialize(conn):
    if 'owner' not in {r[1] for r in conn.execute('PRAGMA table_info(food_products)')}:
        conn.execute('ALTER TABLE food_products ADD COLUMN owner TEXT')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS food_product_reviews (
            id INTEGER PRIMARY KEY, owner TEXT NOT NULL, product_id INTEGER NOT NULL,
            version INTEGER NOT NULL, review_event_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', direct INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            consent_event_id INTEGER, reason TEXT,
            UNIQUE(owner,product_id,version,review_event_id)
        );
        CREATE TABLE IF NOT EXISTS food_product_approvals (
            product_id INTEGER NOT NULL, version INTEGER NOT NULL, owner TEXT NOT NULL,
            source TEXT NOT NULL, source_event_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(product_id,version)
        );
        CREATE TABLE IF NOT EXISTS food_review_actions (
            owner TEXT NOT NULL, request_id TEXT NOT NULL, message TEXT NOT NULL,
            answer TEXT NOT NULL, previews TEXT NOT NULL, PRIMARY KEY(owner,request_id)
        );
    ''')


def intent(message):
    if not isinstance(message, str):
        return None
    text = ' '.join(message.casefold().strip().rstrip('.!').split())
    if text in ('zatwierdzam', 'tak, zapisz ten produkt', 'zapisz ten produkt', 'tak'):
        return ('confirm', text)
    if text in ('anuluj', 'anuluj produkt', 'anuluj tę propozycję'):
        return ('cancel', text)
    m = re.fullmatch(r'(?:zmień|popraw) (?:masę|mase|objętość|objetosc|rozmiar) sztuki na\s*(\d+(?:[.,]\d+)?)\s*(g|ml)(?: i zatwierdź)?', text)
    if m:
        return ('piece_correct', m.groups())
    if text in ('usuń rozmiar sztuki', 'usuń masę sztuki', 'usuń objętość sztuki', 'wyczyść rozmiar sztuki'):
        return ('piece_clear', None)
    if re.search(r'(?:sztuki|sztukę)', text) and re.search(r'zmień|popraw|usuń|wyczyść', text):
        return ('unclear', None)
    m = re.fullmatch(r'(?:zmień|popraw) (białko|bialko|węglowodany|weglowodany|tłuszcz|tluszcz|kcal) na (\d+(?:[.,]\d+)?)(?: i zatwierdź)?', text)
    if m:
        return ('correct', m.groups())
    m = re.fullmatch(r'(?:zmień|popraw) (nazwę|markę|podstawę) na (.+?)(?: i zatwierdź)?[.!]?', message.strip(), re.IGNORECASE)
    if m:
        return ('text_correct', (m[1].casefold(), m[2]))
    m = re.fullmatch(r'/produkt(?:y)? (pokaz|pokaż|zatwierdz) ([0-9]+) ([0-9]+)', text)
    if m:
        if len(m[2]) > 18 or len(m[3]) > 18:
            return ('unclear', None)
        return ('show' if m[1] in ('pokaz','pokaż') else 'explicit', (int(m[2]),int(m[3])))
    # Unclear review language stays local and never becomes model permission.
    if re.search(r'zatwier|zapisz ten produkt|anuluj|\btak\b|(?:zmień|popraw) (?:białko|bialko|kcal|tłuszcz|węglowodany|nazwę|markę|podstawę)', text) or text.startswith(('/produkt ', '/produkty ')):
        return ('unclear', None)
    return None


def interrupt(owner_id):
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='food_product_reviews'").fetchone():
            return
        conn.execute('UPDATE food_product_reviews SET direct=0 WHERE owner=? AND status=\'pending\'', (owner_id,))


def queue_preview(product):
    from memory_runtime import TURN_CONTEXT
    turn = TURN_CONTEXT.get()
    if turn:
        turn.setdefault('catalog_previews', {})[product['id']] = product['version']


def preview_text(p):
    return (f"Produkt {p['id']}, wersja {p['version']}: {p['name']} · {p['brand']} · "
            f"kod {p.get('barcode') or 'brak'} · {p['basis']}: {p['kcal']} kcal / "
            f"B {p['protein']} / W {p['carbs']} / T {p['fat']}.\n"
            + (f"Jedna sztuka: {p['piece_size']} {'g' if p['basis'] == '100g' else 'ml'}.\n"
               if p.get('piece_size') is not None else 'Rozmiar sztuki: brak.\n') +
            'Czy zatwierdzasz zapis tego produktu w tej wersji? Odpowiedz „zatwierdzam” albo „anuluj”.')


def publish(conn, turn, answer):
    """Called only while persisting the actual assistant preview, never by a tool."""
    from .food_catalog import _record
    previews = turn.pop('catalog_previews', {})
    if not previews:
        return answer
    texts = []
    for pid, version in previews.items():
        row = conn.execute('SELECT * FROM food_products WHERE id=? AND version=? AND owner=? AND status=\'draft\'',
                           (pid,version,turn['owner'])).fetchone()
        if row is None:
            texts.append(CLARIFY)
            continue
        conn.execute('INSERT OR IGNORE INTO food_product_reviews(owner,product_id,version,review_event_id) VALUES (?,?,?,?)',
                     (turn['owner'],pid,version,turn['user_event_id']))
        texts.append(preview_text(_record(row)))
    return '\n\n'.join(texts)


def _pending(conn, owner_id):
    rows = conn.execute("SELECT * FROM food_product_reviews WHERE owner=? AND status='pending' ORDER BY id DESC", (owner_id,)).fetchall()
    # Repeated showing of the same version is one proposal, multiple products are ambiguous.
    unique = {(r['product_id'],r['version']):r for r in reversed(rows)}
    if len(unique) != 1:
        raise ValueError('ambiguous review')
    r = next(iter(unique.values()))
    fresh = conn.execute("SELECT ? >= datetime('now','-30 minutes')", (r['created_at'],)).fetchone()[0]
    if not r['direct'] or not fresh:
        raise ValueError('review context expired')
    p = conn.execute('SELECT * FROM food_products WHERE id=? AND version=? AND owner=? AND status=\'draft\'',
                     (r['product_id'],r['version'],owner_id)).fetchone()
    if p is None:
        raise ValueError('stale review')
    return r, p


def resolve(message, turn):
    from . import food_catalog as catalog
    action = intent(message)
    if action is None:
        interrupt(turn['owner'])
        return None
    kind, arg = action
    owner_id = turn['owner']
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT * FROM food_review_actions WHERE owner=? AND request_id=?', (owner_id,turn['request_id'])).fetchone()
        if previous:
            if previous['message'] != message:
                return CLARIFY
            turn['catalog_previews'] = {int(k):v for k,v in json.loads(previous['previews']).items()
                if not conn.execute('SELECT 1 FROM food_product_reviews WHERE owner=? AND product_id=? AND version=? AND review_event_id=?',
                                    (owner_id,int(k),v,turn['user_event_id'])).fetchone()}
            return previous['answer']
        conn.execute('SAVEPOINT review_action')
        try:
            if kind in ('show', 'explicit'):
                pid, version = arg
                row = conn.execute('SELECT * FROM food_products WHERE id=? AND version=? AND status=\'draft\'',(pid,version)).fetchone()
                if row is None or row['owner'] not in (None,owner_id) or (row['owner'] is None and owner_id != owner()):
                    raise ValueError('owner or version mismatch')
                if kind == 'show':
                    conn.execute('UPDATE food_products SET owner=? WHERE id=?',(owner_id,pid))
                    conn.execute("UPDATE food_product_reviews SET status='cancelled',reason='selected_preview' WHERE owner=? AND status='pending'",(owner_id,))
                    queue_preview(catalog._record(row))
                    answer = preview_text(catalog._record(row))
                else:
                    # Explicit command retains its target but must have a bound owner.
                    if row['owner'] is None:
                        raise ValueError('preview required')
                    answer = _confirm(conn, row, version, owner_id, turn['user_event_id'])
            elif kind == 'unclear':
                raise ValueError('unclear consent')
            else:
                review, row = _pending(conn,owner_id)
                if kind == 'cancel':
                    conn.execute("UPDATE food_product_reviews SET status='cancelled',reason='owner_cancel',consent_event_id=? WHERE owner=? AND product_id=? AND status='pending'",(turn['user_event_id'],owner_id,row['id']))
                    answer = 'Anulowano propozycję produktu.'
                elif kind in ('correct', 'text_correct', 'piece_correct', 'piece_clear'):
                    # Extraction is deliberately small/local; no model can select a target.
                    fields = {'białko':'protein','bialko':'protein','węglowodany':'carbs','weglowodany':'carbs','tłuszcz':'fat','tluszcz':'fat','kcal':'kcal','nazwę':'name','markę':'brand','podstawę':'basis'}
                    data = json.loads(row['payload'])
                    if kind == 'piece_clear':
                        data['piece_size'] = None
                    elif kind == 'piece_correct':
                        if arg[1] != ('g' if data['basis'] == '100g' else 'ml'):
                            raise ValueError('piece unit mismatch')
                        data['piece_size'] = arg[0]
                    else:
                        data[fields[arg[0]]] = arg[1]
                        # Keep omission explicit when changing basis; _revise guards old size.
                        if fields[arg[0]] == 'basis':
                            data.pop('piece_size', None)
                    revised = catalog._revise(conn,row,review['version'],data,owner_id)
                    queue_preview(revised)
                    answer = preview_text(revised)
                else:
                    answer = _confirm(conn,row,review['version'],owner_id,turn['user_event_id'])
        except ValueError:
            conn.execute('ROLLBACK TO review_action')
            turn.pop('catalog_previews', None)
            conn.execute("UPDATE food_product_reviews SET direct=0 WHERE owner=? AND status='pending'",(owner_id,))
            answer = CLARIFY
        conn.execute('RELEASE review_action')
        conn.execute('INSERT INTO food_review_actions VALUES (?,?,?,?,?)',(owner_id,turn['request_id'],message,answer,json.dumps(turn.get('catalog_previews', {}))))
        return answer


def _confirm(conn,row,version,owner_id,event_id):
    from .food_catalog import _record
    if row['owner'] != owner_id or row['version'] != version or row['status'] != 'draft':
        raise ValueError('owner or version mismatch')
    conn.execute('INSERT INTO food_product_approvals(product_id,version,owner,source,source_event_id) VALUES (?,?,?,?,?)',
                 (row['id'],version,owner_id,'chat' if event_id is not None else 'panel',event_id))
    conn.execute("UPDATE food_products SET version=version+1,status='confirmed',updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=?",(row['id'],version))
    conn.execute("INSERT INTO food_product_versions(product_id,version,status,payload) VALUES (?,?,'confirmed',?)",(row['id'],version+1,row['payload']))
    conn.execute("UPDATE food_product_reviews SET status='consumed',consent_event_id=?,reason='confirmed' WHERE product_id=? AND owner=? AND status='pending'",(event_id,row['id'],owner_id))
    p = _record(conn.execute('SELECT * FROM food_products WHERE id=?',(row['id'],)).fetchone())
    return f"Produkt {p['id']} zatwierdzony: {p['name']}, {p['basis']}: {p['kcal']} kcal / B {p['protein']} / W {p['carbs']} / T {p['fat']}."


def known_outcome(owner_id, request_id, *, conn):
    """Recover only backend-recorded results, including a commit before response failure."""
    row = conn.execute('SELECT answer,previews FROM food_review_actions WHERE owner=? AND request_id=?',
                       (owner_id,request_id)).fetchone()
    if row is None:
        return None
    if json.loads(row['previews']):
        return 'Szkic nie jest zatwierdzony. ' + CLARIFY
    return row['answer']
