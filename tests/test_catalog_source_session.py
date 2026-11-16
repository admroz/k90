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
    pending.append('Trzy zdjęcia tego samego produktu: Synthetic BIO kefir naturalny, kod 5900512980119. 50 kcal, B 3.3, W 4.7, T 2 na 100g. Przygotować wpis?')
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


@pytest.mark.parametrize('guard', ['foreign', 'stale', 'ambiguous', 'unrelated', 'local_only', 'mismatch'])
def test_delayed_source_requires_recent_unambiguous_related_owner_evidence(conversation, guard):
    send, pending, _ = conversation
    pending.append('Synthetic BIO kefir naturalny, kod 5900512980119, 50 kcal na 100g.')
    send('Etykieta', photo=True, channel='telegram', album=True)
    with get_conn() as c:
        if guard == 'foreign': c.execute("UPDATE agent_events SET owner='other' WHERE role='user'")
        elif guard == 'stale': c.execute("UPDATE agent_events SET occurred_at=datetime('now','-31 minutes')")
        elif guard == 'local_only':
            c.execute("UPDATE memory_sources SET local_only=1")
        elif guard == 'mismatch':
            c.execute("UPDATE agent_events SET payload=? WHERE role='assistant'", (json.dumps('Inny produkt.'),))
    if guard == 'ambiguous':
        pending.append('Inny produkt, inna etykieta.')
        send('Inna etykieta', photo=True)
    elif guard == 'unrelated':
        pending.append('Rozmawiamy o spacerze.')
        send('Jak zaplanować spacer?')
    pending.extend([('propose_food_product', {'product':PRODUCT}), 'Który produkt masz na myśli?'])
    send('Zapisz wcześniejszy produkt')
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0] == 0


def test_natural_confirmation_and_correction_use_model_tools(conversation):
    send, pending, sent = conversation
    pending.extend([('propose_food_product', {'product':PRODUCT}), 'Propozycja.'])
    send('Zapamiętaj produkt', photo=True)
    pending.extend([('revise_food_product', {'changes':{'fat':2.5}}), 'Poprawione.'])
    send('Tam jest jednak dwa i pół grama tłuszczu, zapamiętaj już poprawną wersję')
    assert get(1)['version'] == 2 and get(1)['status'] == 'draft'
    pending.extend([('confirm_food_product', {'product_id':1, 'version':2}), 'Zatwierdzono.'])
    response = send('Zgadza się wszystko po poprawce, możesz zachować ten produkt')
    assert response['state'] == 'done'
    assert get(1)['version'] == 3 and get(1)['status'] == 'confirmed'
    with get_conn() as c:
        row = c.execute('SELECT * FROM food_product_approvals').fetchone()
        assert row['version'] == 2 and row['owner'] == 'owner'
        event = c.execute('SELECT request_id FROM agent_events WHERE id=?', (row['source_event_id'],)).fetchone()
        assert event['request_id'] == response['request_id']
    assert not pending and len(sent) == 6


@pytest.mark.parametrize('guard', ['transport', 'version', 'owner', 'expired', 'unpublished', 'same_turn'])
def test_model_confirmation_requires_separate_current_owner_preview(conversation, guard):
    send, pending, _ = conversation
    pending.extend([('propose_food_product', {'product':PRODUCT}),
                    ('confirm_food_product', {'product_id':1, 'version':1}) if guard=='same_turn' else
                    RuntimeError('synthetic postwrite') if guard=='unpublished' else 'Propozycja.'])
    if guard=='same_turn': pending.append('Sprawdź dane.')
    send('Zapamiętaj produkt', photo=True)
    if guard != 'same_turn':
        with get_conn() as c:
            if guard=='owner': c.execute("UPDATE food_products SET owner='other'")
            elif guard=='version': c.execute('UPDATE food_products SET version=2')
            elif guard=='expired': c.execute("UPDATE food_product_reviews SET created_at=datetime('now','-31 minutes')")
        pending.extend([('confirm_food_product', {'product_id':1, 'version':1}), 'Potrzebny podgląd.'])
        send('To mi odpowiada, zachowaj', channel='telegram' if guard=='transport' else 'web')
    assert get(1)['status'] == 'draft'
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_product_approvals').fetchone()[0] == 0


def test_delayed_write_failure_is_bound_to_mutation_request(conversation):
    send, pending, _ = conversation
    pending.append('Synthetic BIO kefir naturalny, kod 5900512980119, 50 kcal na 100g.')
    first = send('Etykieta', photo=True, channel='telegram', album=True)
    pending.extend([('propose_food_product', {'product':PRODUCT}), RuntimeError('synthetic postwrite')])
    second = send('Zachowaj w katalogu')
    assert second['state'] == 'failed' and 'szkic' in second['response'].lower()
    from tools.product_review import known_outcome
    with get_conn() as c:
        assert known_outcome('owner', second['request_id'], conn=c)
        assert known_outcome('owner', first['request_id'], conn=c) is None


@pytest.mark.parametrize('text,operation', [
    ('Zjadłem całe opakowanie; zapisz posiłek', 'meal'),
    ('Na talerzu jest produkt do katalogu, a nie mój posiłek; czego brakuje?', 'clarify'),
])
def test_image_intent_guidance_keeps_explicit_text_authoritative(conversation, text, operation):
    send, pending, sent = conversation
    if operation=='meal':
        pending.extend([('log_meal', dict(description='Synthetic meal', ingredients=[],
                         remainder=dict(description='Synthetic estimate', calories=100, protein_g=5, carbs_g=10, fat_g=4))),
                        'Zapisano posiłek.'])
    else:
        pending.append('Podaj nazwę i etykietę z wartościami na 100g lub 100ml; sam talerz nie wystarcza.')
    result=send(text, photo=True)
    assert result['state']=='done' and not pending
    prompt=sent[0][0]['content']
    assert 'Etykieta, makra, kod kreskowy lub opakowanie zwykle wskazują katalog' in prompt
    assert 'Talerz lub porcja zwykle wskazują posiłek' in prompt
    assert 'Jawny tekst użytkownika ma pierwszeństwo' in prompt
    assert 'Opakowanie nie dowodzi spożycia' in prompt
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM posilki').fetchone()[0] == (1 if operation=='meal' else 0)
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0] == 0


def test_legacy_explicit_command_cannot_approve_unseen_version(conversation):
    from tools.food_catalog import propose
    send, pending, _ = conversation
    p=propose(dict(PRODUCT, provenance='manual'))
    result=send(f"/produkt zatwierdz {p['id']} 1")
    assert result['state']=='done' and get(p['id'])['status']=='draft'
    assert not pending


def test_catalog_tool_replays_do_not_duplicate_draft_or_approval(conversation):
    send, pending, _=conversation
    proposal=('propose_food_product', {'product':PRODUCT})
    pending.extend([proposal,proposal,'Podgląd.'])
    send('Zapamiętaj produkt',photo=True)
    confirmation=('confirm_food_product', {'product_id':1,'version':1})
    pending.extend([confirmation,confirmation,'Zapisano.'])
    send('Dane się zgadzają, zachowaj proszę')
    assert get(1)['status']=='confirmed' and get(1)['version']==2
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM food_product_approvals').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM catalog_creations').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM posilki').fetchone()[0]==0


def test_source_clarification_can_select_recent_identified_label_without_resending(conversation):
    send,pending,sent=conversation
    pending.append('Synthetic BIO kefir naturalny, kod 5900512980119, 50 kcal na 100g.')
    first=send('Etykieta',photo=True,channel='telegram',album=True)
    pending.append('Inny produkt: Synthetic second product.')
    send('Druga etykieta',photo=True)
    pending.extend([('propose_food_product',{'product':PRODUCT}),'Który produkt chcesz zachować?'])
    send('Zapisz produkt')
    with get_conn() as c:
        assert c.execute('SELECT count(*) FROM food_products').fetchone()[0]==0
        source=c.execute("SELECT id FROM agent_events WHERE request_id=? AND role='user'",(first['request_id'],)).fetchone()[0]
    pending.extend([('propose_food_product',{'product':PRODUCT}),'Sprawdź dane.'])
    send('Chodzi mi o kefir z kodem 5900512980119, zachowaj go')
    assert get(1)['source_event_id']==source and get(1)['status']=='draft'
    assert 'data:image/' not in json.dumps(sent[2:])
