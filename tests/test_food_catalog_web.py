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
