"""Synthetic owner catalog tests; no provider or public network."""
import pytest

from tools import food_catalog as catalog
from tools.db import get_conn, init_db, create_db_backup


def label(**overrides):
    return dict(name="Synthetic skyr", brand="Fixture", barcode="5900531004544",
                basis="100g", kcal="64", protein="12", carbs="4,1", fat="0",
                provenance="manual", **overrides)


def test_draft_confirmation_version_and_backup(temp_db):
    draft = catalog.propose(label())
    assert draft["status"] == "draft"
    assert draft["carbs"] == 4.1 and draft["fat"] == 0
    init_db()
    assert catalog.get(draft["id"]) == draft
    confirmed = catalog.confirm(draft["id"], draft["version"])
    assert confirmed["status"] == "confirmed"
    with pytest.raises(ValueError, match="version"):
        catalog.confirm(draft["id"], draft["version"])
    import sqlite3
    backup = create_db_backup()
    with sqlite3.connect(backup["path"]) as conn:
        assert conn.execute("SELECT count(*) FROM food_product_versions").fetchone()[0] == 2


@pytest.mark.parametrize("field,value", [("barcode", "5900531004545"),
    ("barcode", 5900531004544), ("barcode", " 5900531004544"),
    ("basis", "g"), ("kcal", None), ("protein", "NaN"),
    ("carbs", -1), ("fat", True), ("provenance", "external"), ("name", "")])
def test_invalid_draft_rejected_without_writes(temp_db, field, value):
    data = label()
    data[field] = value
    with pytest.raises(ValueError):
        catalog.propose(data)
    with get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM food_products").fetchone()[0] == 0


def test_barcode_optional_and_duplicates_rejected(temp_db):
    data = label()
    data["barcode"] = None
    assert catalog.propose(data)["barcode"] is None
    catalog.propose(label())
    with pytest.raises(ValueError, match="barcode"):
        catalog.propose(label())
