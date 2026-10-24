from tools import health
from tools.db import get_conn


def test_daily_metrics_exposes_garmin_energy_with_and_without_other_metrics(temp_db, monkeypatch):
    monkeypatch.setattr(health, "date_days_ago", lambda days: "2026-10-01")
    with get_conn() as conn:
        conn.executemany("INSERT INTO metryki_dzienne (data,rhr,avg_stres) VALUES (?,?,?)", [
            ("2026-10-24", 55, 23), ("2026-10-22", 58, 31),
        ])
        conn.executemany("INSERT INTO kalorie_dzienne VALUES (?,?,?,?,?)", [
            ("2026-10-24", 1900, 500, 2400, "now"),
            ("2026-10-23", 1900, 0, 1900, "yesterday"),
            ("2026-10-21", 1900, None, 2400, "partial"),
            ("2026-10-20", None, None, None, "no data"),
            ("2026-09-30", 1900, 100, 2000, "outside range"),
        ])
        conn.execute("INSERT INTO aktywnosci (data,kalorie) VALUES ('2026-10-24',800)")
        conn.commit()
    rows = health.get_daily_metrics()
    assert [row["data"] for row in rows] == ["2026-10-24", "2026-10-23", "2026-10-22", "2026-10-21"]
    assert rows[0]["rhr"] == 55 and rows[0]["spalone_kcal"] == 2400
    assert rows[0]["kalorie_pobrano_at"] == "now"
    assert rows[1]["rhr"] is None and rows[1]["aktywne_kcal"] == 0
    assert rows[1]["spalone_kcal"] == 1900
    assert rows[2]["rhr"] == 58 and rows[2]["spalone_kcal"] is None
    assert rows[3]["spalone_kcal"] is None
