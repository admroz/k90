"""Small deterministic synthetic dataset; no patient data or external calls."""

import math
from contextlib import closing
from datetime import timedelta

from tools.db import get_conn, get_data_dir, init_db
from tools.time_utils import now_local
from patient_documents import get_document, import_markdown, write_document


def seed():
    init_db()
    with closing(get_conn()) as conn, conn:
        import_markdown(conn, get_data_dir())
        if conn.execute("SELECT COUNT(*) FROM waga").fetchone()[0]:
            return
        for i in range(90):
            day = (now_local().date() - timedelta(days=89 - i)).isoformat()
            conn.execute(
                "INSERT INTO waga VALUES (?, ?, ?, ?)",
                (day, round(84 - i * 0.023 + math.sin(i) * 0.17, 1), 25.1, "demo"),
            )
            conn.execute(
                "INSERT INTO sen (data,total_sleep_min,deep_min,light_min,rem_min,sleep_score) VALUES (?, ?, 85, 230, 90, ?)",
                (day, 425 + math.sin(i * 0.9) * 35, round(78 + math.sin(i) * 8)),
            )
            conn.execute(
                "INSERT INTO hrv (data,hrv_noc,hrv_status) VALUES (?, ?, 'BALANCED')",
                (day, round(43 + math.sin(i * 0.6) * 6 + i * 0.06)),
            )
            conn.execute(
                "INSERT INTO body_battery (data,max_bateria,min_bateria) VALUES (?, ?, 18)",
                (day, round(75 + math.sin(i) * 12)),
            )
            conn.execute(
                "INSERT INTO cisnienie (data,czas,skurczowe,rozkurczowe,puls,zrodlo) VALUES (?, '08:00', ?, ?, 63, 'demo')",
                (day, round(121 + math.sin(i) * 5), round(78 + math.cos(i) * 3)),
            )
            for hour, description, kcal in (
                (8, "Owsianka z jogurtem i owocami", 480),
                (13, "Kasza, warzywa i pieczony kurczak", 650),
                (19, "Kanapki z twarogiem i warzywami", 510),
            ):
                conn.execute(
                    "INSERT INTO posilki (data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g,zrodlo) VALUES (?, ?, ?, ?, 30, 55, 18, 'demo')",
                    (
                        day,
                        f"{hour:02d}:00",
                        description,
                        kcal + round(math.sin(i) * 45),
                    ),
                )
            if i % 3 == 0:
                conn.execute(
                    "INSERT INTO aktywnosci (data,czas,typ,nazwa,czas_trwania_min,dystans_km) VALUES (?, '17:00', 'walking', 'Spacer po okolicy', ?, 4.5)",
                    (day, round(50 + math.sin(i) * 10)),
                )
            if i >= 76:
                for hour in range(24):
                    timestamp = f"{day}T{hour:02d}:00:00+02:00"
                    conn.execute(
                        "INSERT INTO glukoza_libre (timestamp,source_kind,data,czas,glukoza_mg_dl,zrodlo) VALUES (?, 'graph', ?, ?, ?, 'demo')",
                        (
                            timestamp,
                            day,
                            f"{hour:02d}:00",
                            round(100 + math.sin(hour + i) * 14),
                        ),
                    )
        conn.execute(
            "INSERT INTO patient_summary (id,content,trigger) VALUES (1, ?, 'demo')",
            (
                "Dane demonstracyjne, całkowicie fikcyjne. Cel: obejrzeć interfejs i przetestować wspólną rozmowę.",
            ),
        )
        conn.execute(
            "INSERT INTO sync_status (source,last_success_at,last_status) VALUES ('demo', ?, 'dane demonstracyjne')",
            (now_local().isoformat(),),
        )
    if get_document("pacjent.md") is None:
        write_document(
            "pacjent.md",
            "# Profil demonstracyjny\n\nTo fikcyjny zestaw danych do przeglądania aplikacji.\n\n## Cele\n\n- Regularny ruch\n- Obserwacja snu i regeneracji\n- Spokojna rozmowa o trendach\n\n**Żadna z tych wartości nie opisuje rzeczywistego pacjenta.**\n",
        )
    if get_document("analiza.md") is None:
        write_document(
            "analiza.md",
            "# Obserwacje\n\nDane służą do sprawdzenia wykresów, tabel i dokumentów.\n\n## Co można sprawdzić\n\n- Zmiana okresu wykresu\n- Przejście z wykresu do rozmowy\n- Podgląd surowych rekordów\n",
        )
