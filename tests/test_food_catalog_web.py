"""Synthetic authenticated catalog API acceptance."""
from test_web import web_client, login
from test_food_catalog import label

H = {'X-K90-Request': '1'}


def test_catalog_owner_review_and_meal(web_client):
    c = web_client
    assert c.get('/api/catalog').status_code == 401
    assert c.post('/api/catalog', json=label(), headers=H).status_code == 401
    login(c)
    p = c.post('/api/catalog', json=label(), headers=H)
    assert p.status_code == 200
    p = p.json()
    assert c.get('/api/catalog').json() == [p]
    url = f"/api/catalog/{p['id']}/confirm"
    assert c.post(url, json={'version':1}).status_code == 403
    assert c.post(url, json={'version':1}, headers={**H, 'Origin':'https://evil.invalid'}).status_code == 403
    approved = c.post(url, json={'version':1}, headers=H)
    assert approved.status_code == 200
    assert c.post(url, json={'version':1}, headers=H).status_code == 409
    portion = c.post(f"/api/catalog/{p['id']}/portion", json=dict(version=2, quantity='150', unit='g', request_id='web-fixture'), headers=H)
    assert portion.status_code == 200 and portion.json()['nutrition']['kcal'] == 96
    edit = c.put(f"/api/catalog/{p['id']}", json=dict(version=2, product=label()), headers=H)
    assert edit.status_code == 200 and edit.json()['status'] == 'draft'
    assert c.get('/api/catalog?barcode=../../etc/passwd').status_code == 409


def test_explicit_external_lookup_and_retrievable_label(web_client, monkeypatch):
    import memory_runtime
    from tools import food_catalog, food_off
    from test_food_catalog_off import response, CODE
    from tools import execute_tool
    login(web_client)
    monkeypatch.setattr(food_off, '_fetch', lambda _: response())
    result = web_client.post('/api/catalog/lookup', json={'barcode':CODE}, headers=H)
    assert result.status_code == 200 and result.json()['status'] == 'unverified'
    assert execute_tool('lookup_food_barcode', {'barcode':CODE})['status'] == 'unverified'
    own = label(); own['provenance'] = 'own_label'
    assert web_client.post('/api/catalog', json=own, headers=H).status_code == 409
    image = 'data:image/png;base64,iVBORw0KGgo='
    turn = memory_runtime.begin_turn('owner', [{'type':'image_url','image_url':{'url':image}}])
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        p = food_catalog.propose_from_chat(own)
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    assert web_client.get(f"/api/catalog/{p['id']}/label").json()['image'] == image


def test_invalid_product_structure_and_cross_owner_label_are_rejected(web_client):
    import memory_runtime
    from tools import food_catalog
    login(web_client)
    for bad in [None, [], 'fixture']:
        assert web_client.put('/api/catalog/1', json={'version':1,'product':bad}, headers=H).status_code == 409
    turn = memory_runtime.begin_turn('other-owner', [{'type':'image_url','image_url':{'url':'data:image/png;base64,iVBORw0KGgo='}}])
    token = memory_runtime.TURN_CONTEXT.set(turn)
    try:
        own = label(); own['provenance'] = 'own_label'
        p = food_catalog.propose_from_chat(own)
    finally:
        memory_runtime.TURN_CONTEXT.reset(token)
    assert web_client.get(f"/api/catalog/{p['id']}/label").status_code == 409
