"""Bounded offline reproductions; scripted extraction is not real image inference."""
import json
import pytest
from test_catalog_conversation import conversation, PNG
from tools.db import get_conn
from tools.food_catalog import get
from test_web import web_client, login


PRODUCT = dict(name='Synthetic BIO kefir naturalny', brand='Synthetic dairy',
               barcode='5900512980119', basis='100g', kcal=50, protein=3.3,
               carbs=4.7, fat=2, provenance='own_label')


@pytest.mark.parametrize('followup_channel', ['web', 'telegram'])
def test_no_draft_album_description_then_delayed_catalog_save(conversation, followup_channel):
    send, pending, sent = conversation
    pending.append('Trzy zdjęcia tego samego produktu. 50 kcal, B 3.3, W 4.7, T 2 na 100g. Przygotować wpis?')
    first = send('Etykieta produktu', photo=True, channel='telegram', album=True)
    assert first['state'] == 'done'
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0] == 0
        source = c.execute("SELECT id,payload FROM agent_events WHERE role='user'").fetchone()
        assert len([p for p in json.loads(source['payload']) if p['type']=='image_url']) == 3
    pending.extend([('propose_food_product', {'product':PRODUCT}), 'Sprawdź propozycję.'])
    second = send('zapisz do katalogu', channel=followup_channel)
    assert second['state'] == 'done'
    with get_conn() as c:
        rows = c.execute('SELECT id FROM food_products').fetchall()
        assert len(rows) == 1, 'recent owner album must support creation without resending photos'
        assert c.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
    product = get(rows[0]['id'])
    assert product['status'] == 'draft' and product['source_event_id'] == source['id']
    assert all(product[k] == v for k,v in PRODUCT.items())
    assert 'Czy zatwierdzasz' in second['response']
    assert 'data:image/' not in json.dumps(sent[1:])


@pytest.mark.parametrize('failure', ['none', 'before_write', 'after_write'])
def test_fresh_album_caption_catalog_outcome_and_delivery(conversation, failure):
    send, pending, sent = conversation
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0] == 0
    if failure == 'before_write':
        pending.append(RuntimeError('synthetic failure before tool'))
    else:
        pending.extend([('propose_food_product', {'product':PRODUCT}),
                        RuntimeError('synthetic failure after tool') if failure=='after_write' else 'Sprawdź propozycję.'])
    result = send('dodaj do katalogu', photo=True, channel='telegram', album=True)
    assert result['state'] == ('done' if failure=='none' else 'failed')
    assert len([p for p in sent[0][-1]['content'] if p['type']=='image_url']) == 3
    assert sent[0][-1]['content'][0]['text'] == 'dodaj do katalogu'
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0] == (0 if failure=='before_write' else 1)
        assert c.execute('SELECT count(*) FROM posilki').fetchone()[0] == 0
    if failure=='before_write':
        assert 'katalog' in result['response'].lower(), 'catalog attempt needs its own durable outcome, not meal ledger 0'
        assert 'posiłk' not in result['response'].lower()
    else:
        assert get(1)['status'] == 'draft'
        assert ('Czy zatwierdzasz' if failure=='none' else 'szkic') in result['response']
    assert not pending  # No automatic retry or duplicate tool execution.


def test_seven_day_cookie_and_server_expiry_boundary(web_client, monkeypatch):
    import webapp
    now = webapp.time.time()
    clock = [now]
    monkeypatch.setattr(webapp.time, 'time', lambda: clock[0])
    response = login(web_client)
    from http.cookies import SimpleCookie
    parsed = SimpleCookie()
    parsed.load(response.headers['set-cookie'])
    duration = parsed['k90_session']['max-age']
    assert duration == '604800'
    cookie = web_client.cookies.get('k90_session')
    for offset, expected in [(12*3600+1,200),(7*86400-1,200),(7*86400,401)]:
        clock[0] = now + offset
        # Send even an expired browser cookie: this also proves server expiry.
        assert web_client.get('/api/session', headers={'Cookie':'k90_session='+cookie}).status_code == expected
