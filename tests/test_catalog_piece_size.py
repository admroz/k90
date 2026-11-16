"""One-piece conversion on existing per100 products, synthetic data only."""
import json
import pytest
from tools import food_catalog as c, execute_tool
from tools.db import get_conn
from test_food_catalog import label
from test_logical_meal import turn

@pytest.mark.parametrize('basis,native', [('100g','g'),('100ml','ml')])
def test_piece_both_writes_and_history(temp_db, basis, native):
    data = label(); data.update(basis=basis, piece_size=90)
    p = c.confirm(c.propose(data)['id'],1)
    first = c.log_portion(p['id'],2,0.5,'szt','piece')
    assert first['nutrition']['kcal'] == 28.8
    assert first['normalized_quantity'] == 45 and first['normalized_unit'] == native
    assert first['piece_size'] == 90 and first['quantity'] == 0.5
    args = dict(description='Synthetic mixed meal', ingredients=[dict(product_id=p['id'],version=2,quantity=2.5,unit='szt')], remainder=dict(description='Fruit',calories=10,protein_g=0,carbs_g=2,fat_g=0))
    with turn('piece-meal'):
        result = execute_tool('log_meal',args)
        assert result['nutrition']['calories'] == 154
        assert execute_tool('log_meal',args)['replayed']
        assert execute_tool('log_meal',dict(args,remainder=None))['error']
    with get_conn() as conn:
        snapshot = conn.execute('SELECT snapshot FROM meal_ingredients').fetchone()[0]
        assert json.loads(snapshot)['ingredients'][0]['normalized_quantity'] == 225
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 2
    revised = c.revise(p['id'],2,dict(data,piece_size=100,kcal=80))
    c.confirm(p['id'],revised['version'])
    assert c.log_portion(p['id'],2,.5,'szt','piece') == first
    with get_conn() as conn:
        assert conn.execute('SELECT snapshot FROM meal_ingredients').fetchone()[0] == snapshot
    with pytest.raises(ValueError,match='conflict'): c.log_portion(p['id'],2,.5,native,'piece')


def test_independent_edits_and_basis(temp_db):
    data=label(); data['piece_size']=90
    p=c.propose(data)
    p=c.revise(p['id'],1,dict(label(),kcal=80))
    assert p['piece_size']==90
    p=c.revise(p['id'],2,{'piece_size':45})
    assert p['kcal']==80 and p['protein']==12
    with pytest.raises(ValueError): c.revise(p['id'],3,dict(label(),basis='100ml'))
    p=c.revise(p['id'],3,{'piece_size':None})
    assert p['piece_size'] is None and p['kcal']==80
    with pytest.raises(ValueError): c.log_portion(p['id'],4,1,'szt','draft')
    p=c.confirm(p['id'],4)
    with pytest.raises(ValueError): c.log_portion(p['id'],5,1,'szt','missing')
    assert c.log_portion(p['id'],5,10,'g','native')['nutrition']['kcal']==8

@pytest.mark.parametrize('value',[True,0,-1,'NaN','Infinity',float('inf'),'1e999','1e-999', ''])
def test_invalid_converter(temp_db,value):
    with pytest.raises(ValueError): c.propose(dict(label(),piece_size=value))

@pytest.mark.parametrize('quantity,unit',[(True,'szt'),(0,'szt'),(-1,'szt'),('NaN','szt'),('Infinity','szt'),(1,'ml'),(1000000,'szt')])
def test_invalid_portions_both_routes(temp_db,quantity,unit):
    p=c.confirm(c.propose(dict(label(),piece_size=90))['id'],1)
    with pytest.raises(ValueError): c.log_portion(p['id'],2,quantity,unit,'bad')
    with turn('bad'):
        assert execute_tool('log_meal',dict(description='Synthetic',ingredients=[dict(product_id=p['id'],version=2,quantity=quantity,unit=unit)],remainder=None))['error']
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0]==0


from test_catalog_conversation import conversation


def test_natural_size_macro_clear_separate_consent(conversation):
    send,pending,_=conversation
    pending.extend([('propose_food_product',{'product':dict(label(),piece_size=50)}),'Preview'])
    send('Zachowaj produkt')
    pending.extend([('revise_food_product',{'changes':{'piece_size':90}}),'Updated'])
    answer=send('zmień masę sztuki na90g i zatwierdź')['response']
    assert 'Jedna sztuka: 90.0 g' in answer and 'Czy zatwierdzasz' in answer
    p=c.get(1); assert p['status']=='draft' and p['protein']==12
    pending.extend([('revise_food_product',{'changes':{'protein':15}}),'Updated'])
    send('zmień białko na 15')
    p=c.get(1); assert p['piece_size']==90 and p['protein']==15
    pending.extend([('revise_food_product',{'changes':{'piece_size':None}}),'Updated'])
    send('usuń rozmiar sztuki')
    p=c.get(1); assert p['piece_size'] is None and p['protein']==15 and p['status']=='draft'
    pending.extend([('confirm_food_product',{'product_id':1,'version':4}),'Confirmed'])
    send('zatwierdzam')
    assert c.get(1)['status']=='confirmed'


def test_piece_unit_mismatch_asks_for_clarification(conversation):
    send,pending,_=conversation
    pending.extend([('propose_food_product',{'product':dict(label(),piece_size=50)}),'Preview'])
    send('Zachowaj produkt')
    pending.append('Podstawa to 100g. Podaj masę jednej sztuki w gramach.')
    send('zmień masę sztuki na 90 ml')
    assert c.get(1)['piece_size']==50 and c.get(1)['version']==1


def test_missing_converter_requests_native_amount_without_write(temp_db):
    p=c.confirm(c.propose(label())['id'],1)
    with turn('missing-converter'):
        result=execute_tool('log_meal',dict(description='Synthetic',ingredients=[dict(product_id=p['id'],version=2,quantity=.5,unit='szt')],remainder=None))
    assert 'sztuki' in result['error'] and 'g' in result['error']
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0]==0
