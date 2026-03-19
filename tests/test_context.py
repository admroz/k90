from __future__ import annotations

from tools.context import build_operational_context
from tools.db import get_conn


def test_build_operational_context_includes_recent_sections(monkeypatch, temp_db):
    monkeypatch.setattr("tools.context.date_days_ago", lambda days: "2026-03-10")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO posilki (data, czas, opis, kalorie, bialko_g, weglowodany_g, tluszcze_g, zrodlo) VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')",
            ("2026-03-18", "08:15", "Owsianka", 500, 25, 60, 12),
        )
        conn.execute(
            "INSERT INTO aktywnosci (data, czas, typ, nazwa, czas_trwania_min, dystans_km, kalorie) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-03-17", "10:00", "cycling", "MTB", 90, 31.2, 850),
        )
        conn.execute("INSERT INTO waga (data, waga_kg) VALUES (?, ?)", ("2026-03-18", 89.2))
        conn.execute("INSERT INTO waga (data, waga_kg) VALUES (?, ?)", ("2026-03-12", 91.0))
        conn.execute(
            "INSERT INTO cisnienie (data, czas, skurczowe, rozkurczowe, puls) VALUES (?, ?, ?, ?, ?)",
            ("2026-03-18", "07:00", 118, 76, 58),
        )
        conn.execute(
            "INSERT INTO sen (data, total_sleep_min, sleep_score, spo2_avg) VALUES (?, ?, ?, ?)",
            ("2026-03-18", 440, 82, 96.0),
        )
        conn.execute(
            "INSERT INTO metryki_dzienne (data, rhr, avg_stres, avg_oddech) VALUES (?, ?, ?, ?)",
            ("2026-03-18", 52, 24, 13.5),
        )
        conn.execute("INSERT INTO hrv (data, hrv_noc) VALUES (?, ?)", ("2026-03-18", 41.2))
        conn.execute(
            "INSERT INTO body_battery (data, max_bateria, min_bateria) VALUES (?, ?, ?)",
            ("2026-03-18", 82, 35),
        )
        conn.execute(
            "INSERT INTO glukoza_libre (timestamp, source_kind, factory_timestamp, data, czas, glukoza_mg_dl, trend_arrow, measurement_color, is_high, is_low, typ, zrodlo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-03-18T08:15:00", "latest", "2026-03-18T07:15:00", "2026-03-18", "08:15:00", 107, 3, 1, 0, 0, 0, "librelinkup"),
        )
        conn.execute(
            "INSERT INTO glukoza_libre (timestamp, source_kind, factory_timestamp, data, czas, glukoza_mg_dl, measurement_color, is_high, is_low, typ, zrodlo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-03-18T08:00:00", "graph", "2026-03-18T07:00:00", "2026-03-18", "08:00:00", 103, 1, 0, 0, 0, "librelinkup"),
        )
        conn.commit()

    context, stats = build_operational_context()

    assert "Posiłki z ostatnich dni:" in context
    assert "Owsianka (500 kcal; B 25 g, W 60 g, T 12 g)" in context
    assert "Aktywności z ostatnich dni:" in context
    assert "MTB (90 min, 31.2 km, 850 kcal)" in context
    assert "Waga:" in context
    assert "zmiana 7 dni: -1.8 kg" in context
    assert "Ciśnienie:" in context
    assert "Sen:" in context
    assert "Regeneracja i metryki:" in context
    assert "Glukoza Libre:" in context
    assert stats["sections"] == 7
    assert stats["meals"] == 1
    assert stats["activities"] == 1
    assert stats["glucose"] == 1
