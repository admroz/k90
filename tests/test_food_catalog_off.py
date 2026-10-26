"""Synthetic OFF wire fixtures; public live GET evidence is recorded separately."""
import json
import pytest
from tools import food_off as off
from tools import food_catalog as catalog
from test_food_catalog import label

CODE = '5900531004544'


def response():
    return dict(status='success', result={'id':'product_found'}, product=dict(
        code=CODE, product_name='Synthetic Polish fixture', brands='Fixture',
        countries_tags=['en:poland'], nutrition_data_per='100g',
        nutriments={'energy-kcal_100g':64,'proteins_100g':12,'carbohydrates_100g':4.1,'fat_100g':0}))


def test_external_cache_local_priority_and_no_promotion(temp_db, monkeypatch):
    calls = []
    monkeypatch.setattr(off, '_fetch', lambda code: calls.append(code) or response())
    found = off.lookup(CODE)
    assert found['status'] == 'unverified' and found['provenance'] == 'openfoodfacts'
    assert found['fat'] == 0 and found['basis'] == '100g'
    assert 'ODbL' in found['attribution']
    assert off.lookup(CODE) == found and calls == [CODE]
    draft = catalog.propose(label())
    confirmed = catalog.confirm(draft['id'], 1)
    assert off.lookup(CODE) == confirmed
    assert calls == [CODE]
    with pytest.raises(ValueError):
        off.lookup('https://127.0.0.1/private')


@pytest.mark.parametrize('change', ['null','missing','foreign','basis','ml_ambiguous','code','nan','not_found'])
def test_reject_incomplete_or_inconsistent_public_records(change):
    data = response()
    p = data['product']
    if change == 'null': p['nutriments']['fat_100g'] = None
    if change == 'missing': del p['nutriments']['proteins_100g']
    if change == 'foreign': p['countries_tags'] = ['en:france']
    if change == 'basis': p['nutrition_data_per'] = 'serving'
    if change == 'ml_ambiguous': p['nutrition_data_per'] = '100ml'
    if change == 'code': p['code'] = '00000000'
    if change == 'nan': p['nutriments']['fat_100g'] = float('nan')
    if change == 'not_found': data['result']['id'] = 'product_not_found'
    with pytest.raises(ValueError): off.parse(data, CODE)


def test_depth_size_invalid_json_and_kj_explicit():
    for raw in [b'x', b' '*262145, b'['*40 + b'0' + b']'*40, b'{"a":NaN}']:
        with pytest.raises(ValueError): off.decode(raw)
    data = response()
    n = data['product']['nutriments']
    del n['energy-kcal_100g']
    n['energy-kj_100g'] = 267.776
    parsed = off.parse(data, CODE)
    assert parsed['kcal'] == 64 and parsed['energy_conversion'] == 'kJ / 4.184'


def test_fixed_host_no_redirect_bounded_transport_and_cooldown(temp_db, monkeypatch):
    import requests
    class Reply:
        status_code = 200
        headers = {}
        chunks = [json.dumps(response()).encode()]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size):
            assert size == 1
            yield from self.chunks
    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert self.trust_env is False
            assert url == 'https://world.openfoodfacts.org/api/v3/product/'+CODE
            assert kwargs['allow_redirects'] is False and kwargs['timeout'] == (3,5)
            assert set(kwargs['params']) == {'fields'}
            assert 'k90-food-catalog' in kwargs['headers']['User-Agent']
            return Reply()
    monkeypatch.setattr(off.requests, 'Session', Session)
    assert off._fetch(CODE)['product']['code'] == CODE
    Reply.status_code = 302
    with pytest.raises(ValueError): off._fetch(CODE)
    Reply.status_code = 429; Reply.headers = {'Retry-After':'120'}
    # initialize rate slot using an ordinary failed attempt
    monkeypatch.setattr(off, '_fetch', lambda _: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(ValueError, match='network'): off.lookup(CODE)
    with pytest.raises(ValueError, match='cooldown'): off.lookup(CODE)


def test_explicit_liquid_basis_is_preserved_and_zero_is_valid():
    data = response()
    data['product']['nutrition_data_per'] = '100ml'
    data['product']['product_quantity_unit'] = 'ml'
    result = off.parse(data, CODE)
    assert result['basis'] == '100ml' and result['fat'] == 0


def test_country_tag_must_be_exact_list():
    for tags in ['not-en:poland', {'en:poland':True}, ['not-en:poland'], ['en:poland',1]]:
        data = response(); data['product']['countries_tags'] = tags
        with pytest.raises(ValueError): off.parse(data, CODE)


def test_slow_drip_is_stopped_before_large_buffer_accumulates(monkeypatch):
    state = {'clock':0, 'bytes':0}
    class Reply:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, size):
            for _ in range(100):
                state['bytes'] += size
                state['clock'] += size * .25
                yield b'x' * size
    class Session:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, *a, **kw): return Reply()
    monkeypatch.setattr(off.requests, 'Session', Session)
    monkeypatch.setattr(off.time, 'monotonic', lambda:state['clock'])
    with pytest.raises(ValueError): off._fetch(CODE)
    assert state['bytes'] <= 64


def test_compressed_responses_are_rejected_before_stream_read(monkeypatch):
    class Reply:
        status_code = 200
        headers = {'Content-Encoding':'gzip'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, size):
            raise AssertionError('compressed stream must never be read')
    class Session:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, *a, **kw): return Reply()
    monkeypatch.setattr(off.requests, 'Session', Session)
    with pytest.raises(ValueError, match='encoding'): off._fetch(CODE)


@pytest.mark.parametrize('source,value', [
    ('kcal', 10000), ('kj', 4184.004184),
])
@pytest.mark.parametrize('path', ['parse', 'lookup'])
def test_excessive_energy_is_rejected_before_cache(temp_db, monkeypatch, source, value, path):
    data = response()
    n = data['product']['nutriments']
    del n['energy-kcal_100g']
    n['energy-'+source+'_100g'] = value
    monkeypatch.setattr(off, '_fetch', lambda _: data)
    try:
        with pytest.raises(ValueError):
            if path == 'parse':
                off.parse(data, CODE)
            else:
                off.lookup(CODE)
    finally:
        with off.get_conn() as conn:
            assert conn.execute('SELECT count(*) FROM food_external_cache').fetchone()[0] == 0


@pytest.mark.parametrize('source', ['kcal', 'kj'])
@pytest.mark.parametrize('value', [None, -1, float('nan'), float('inf'), 'missing'])
def test_invalid_energy_is_rejected(source, value):
    data = response()
    n = data['product']['nutriments']
    del n['energy-kcal_100g']
    if value != 'missing':
        n['energy-'+source+'_100g'] = value
    with pytest.raises(ValueError):
        off.parse(data, CODE)


@pytest.mark.parametrize('source,multiplier', [('kcal', 1), ('kj', 4.184)])
@pytest.mark.parametrize('kcal', [0, 1000])
def test_energy_per100_boundaries_are_valid(temp_db, monkeypatch, source, multiplier, kcal):
    data = response()
    n = data['product']['nutriments']
    del n['energy-kcal_100g']
    n['energy-'+source+'_100g'] = kcal * multiplier
    monkeypatch.setattr(off, '_fetch', lambda _: data)
    assert off.parse(data, CODE)['kcal'] == kcal
    assert off.lookup(CODE)['kcal'] == kcal
    with off.get_conn() as conn:
        assert json.loads(conn.execute('SELECT payload FROM food_external_cache').fetchone()[0])['kcal'] == kcal
