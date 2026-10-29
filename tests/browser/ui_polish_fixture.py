"""Real-API browser fixture. Refuses existing/non-synthetic data directories."""
import os
from pathlib import Path
from datetime import datetime

_data = Path(os.environ['DATA_DIR']).resolve()
_db = Path(os.environ['DB_PATH']).resolve()
if (os.getenv('K90_UI_SYNTHETIC') != 'true' or _db.name != 'synthetic-ui.db'
        or _db.parent != _data or _db.exists() or any(_data.iterdir())):
    raise RuntimeError('UI acceptance requires an empty synthetic data directory and fresh synthetic-ui.db')

from tools.db import init_db, get_conn
from tools import food_catalog as catalog
from webapp import create_app
import web_data

web_data.now_local = lambda: datetime(2026, 10, 29, 18)
init_db()
product = catalog.propose(dict(name='Synthetic legacy piece', brand='Fixture',
    basis='100g', provenance='manual', kcal=64, protein=12, carbs=4.1, fat=0, piece_size=90))
catalog.confirm(product['id'], 1)
with get_conn() as conn:
    # Reproduce the pre-owner-column migration without reading any real database.
    conn.execute('UPDATE food_products SET owner=NULL WHERE id=?', (product['id'],))
    for day, value in [('2026-10-21',9000), ('2026-10-22',1850), ('2026-10-28',2050), ('2026-10-29',777)]:
        conn.execute('INSERT INTO kalorie_dzienne VALUES (?,?,100,NULL,CURRENT_TIMESTAMP)', (day,value))
    for time, description in [('08:00','Synthetic early'), (None,'Synthetic untimed'), ('20:00','Synthetic late')]:
        conn.execute("INSERT INTO posilki(data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g) VALUES ('2026-10-29',?,?,100,5,10,4)", (time,description))
    for day, value in [('2026-10-02',83), ('2026-10-03',82), ('2026-10-29',80)]:
        conn.execute('INSERT INTO waga(data,waga_kg) VALUES (?,?)', (day,value))
    conn.execute("INSERT INTO sen(data,total_sleep_min) VALUES ('2026-10-28',450)")


def forbidden(*args, **kwargs):
    raise AssertionError('No model in UI browser acceptance')


app = create_app(processor=forbidden)
