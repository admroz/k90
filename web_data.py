"""Read-only views with explicit table and document allowlists."""

import json
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from tools.db import get_conn, get_data_dir
from tools.patient import ALLOWED_FILES
from tools.time_utils import now_local
from patient_documents import get_document

TABLES = (
    "waga",
    "cisnienie",
    "sen",
    "hrv",
    "body_battery",
    "aktywnosci",
    "metryki_dzienne",
    "kalorie_dzienne",
    "posilki",
    "glukoza_libre",
    "wyniki_lab",
    "conversations",
    "patient_summary",
    "sync_status",
    "usage_stats",
)


def read_table(table, limit=50, offset=0, sort=None, descending=True, search=""):
    if table not in TABLES:
        raise ValueError("Nieznana tabela")
    with closing(get_conn()) as conn:
        conn.execute("PRAGMA query_only = ON")
        columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
        sort = sort or (
            "data"
            if "data" in columns
            else "timestamp"
            if "timestamp" in columns
            else columns[0]
        )
        if sort not in columns:
            raise ValueError("Nieznana kolumna sortowania")
        clause, params = "", []
        if search:
            clause = " WHERE " + " OR ".join(
                f"CAST(\"{col}\" AS TEXT) LIKE ? ESCAPE '\\'" for col in columns
            )
            escaped = (
                search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            params = [f"%{escaped}%"] * len(columns)
        total = conn.execute(
            f'SELECT COUNT(*) FROM "{table}"{clause}', params
        ).fetchone()[0]
        # Bound text sizes in the raw view (legacy conversations can contain base64 images).
        selection = ", ".join(
            f'CASE WHEN typeof("{col}") = \'text\' THEN substr("{col}", 1, 4000) ELSE "{col}" END AS "{col}"'
            for col in columns
        )
        order = f'"{sort}" {"DESC" if descending else "ASC"}, rowid'
        if table == 'posilki' and sort == 'data':
            order = f'data {"DESC" if descending else "ASC"}, CASE WHEN czas IS NULL OR czas = \'\' THEN 1 ELSE 0 END, czas DESC, id DESC'
        rows = conn.execute(
            f'SELECT {selection} FROM "{table}"{clause} ORDER BY {order} LIMIT ? OFFSET ?',
            [*params, limit, offset],
        ).fetchall()
    return {
        "columns": columns,
        "rows": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def document(name):
    if name == "patient_summary":
        with closing(get_conn()) as conn:
            row = conn.execute(
                "SELECT content, updated_at FROM patient_summary WHERE id = 1"
            ).fetchone()
        return {
            "name": name,
            "content": row[0] if row else "",
            "updated_at": row[1] if row else None,
        }
    if name not in ALLOWED_FILES:
        raise ValueError("Nieznany dokument")
    stored = get_document(name, data_dir=get_data_dir())
    return {
        "name": name,
        "content": stored["content"] if stored else "",
        "updated_at": stored["updated_at"] if stored else None,
    }


def history_content(raw):
    if isinstance(raw, list):
        parts = raw
    else:
        try:
            parts = json.loads(raw)
        except (ValueError, TypeError):
            return {"text": str(raw or ""), "has_image": False}
    if not isinstance(parts, list):
        return {"text": str(raw or ""), "has_image": False}
    if not all(isinstance(part, dict) for part in parts):
        return {"text": str(raw), "has_image": False}
    return {
        "text": "\n".join(
            str(part.get("text", "")) for part in parts if part.get("type") == "text"
        ),
        "has_image": any(part.get("type") == "image_url" for part in parts),
    }


def meals_for_day(day: date | None = None):
    today = now_local().date()
    day = day or today
    with closing(get_conn()) as conn:
        rows = [dict(row) for row in conn.execute(
            """SELECT * FROM posilki WHERE data = ?
               ORDER BY CASE WHEN czas IS NULL OR czas = '' THEN 1 ELSE 0 END,
                        czas DESC, id DESC""",
            (day.isoformat(),),
        )]
        energy = conn.execute("SELECT * FROM kalorie_dzienne WHERE data = ?", (day.isoformat(),)).fetchone()
        resting_estimate = None
        if day == today:
            average = conn.execute(
                "SELECT AVG(spoczynkowe_kcal) FROM kalorie_dzienne WHERE data >= ? AND data < ?",
                ((today - timedelta(days=7)).isoformat(), today.isoformat()),
            ).fetchone()[0]
            if average is not None:
                resting_estimate = int((Decimal(str(average)) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) * 100
    totals, missing = {}, {}
    for field in ("kalorie", "bialko_g", "weglowodany_g", "tluszcze_g"):
        values = [row[field] for row in rows if row[field] is not None]
        totals[field] = sum(values) if values else (None if rows else 0)
        missing[field] = len(rows) - len(values)
    energy = dict(energy) if energy else {}
    resting, active = energy.get("spoczynkowe_kcal"), energy.get("aktywne_kcal")
    if day == today:
        resting = resting_estimate
    burned = resting + active if resting is not None and active is not None else None
    # A missing meal or expenditure value cannot turn into a reliable balance.
    balance = totals["kalorie"] - burned if rows and burned is not None and not missing["kalorie"] else None
    return {
        "date": day.isoformat(), "today": today.isoformat(), "meals": rows,
        "totals": totals, "missing_values": missing,
        "energy": {
            "resting_kcal": resting, "active_kcal": active, "burned_kcal": burned,
            "resting_estimated": day == today and resting is not None,
            "balance_kcal": balance, "fetched_at": energy.get("pobrano_at"),
            "day_in_progress": day == today,
        },
        "previous_date": (day - timedelta(days=1)).isoformat() if day > date.min else None,
        "next_date": (day + timedelta(days=1)).isoformat() if day < today else None,
    }


def dashboard(days):
    start = (now_local().date() - timedelta(days=days - 1)).isoformat()
    end = now_local().date().isoformat()
    with closing(get_conn()) as conn:
        result = {}
        for table in (
            "waga",
            "cisnienie",
            "sen",
            "hrv",
            "body_battery",
            "metryki_dzienne",
            "aktywnosci",
            "posilki",
            "kalorie_dzienne",
        ):
            order = "data DESC, CASE WHEN czas IS NULL OR czas = '' THEN 1 ELSE 0 END, czas DESC, id DESC" if table == 'posilki' else 'data, rowid'
            result[table] = [
                dict(row)
                for row in conn.execute(
                    f'SELECT * FROM "{table}" WHERE data BETWEEN ? AND ? ORDER BY {order}',
                    (start, end),
                )
            ]
        result["kalorie"] = [
            dict(row)
            for row in conn.execute(
                "SELECT data, SUM(kalorie) AS kcal, SUM(bialko_g) AS bialko, SUM(weglowodany_g) AS weglowodany, SUM(tluszcze_g) AS tluszcze FROM posilki WHERE data BETWEEN ? AND ? GROUP BY data ORDER BY data",
                (start, end),
            )
        ]
        # Prefer latest over graph for duplicate timestamps. Hourly aggregates keep long ranges small.
        result["glukoza"] = [
            dict(row)
            for row in conn.execute(
                """
            WITH readings AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY timestamp ORDER BY CASE source_kind WHEN 'latest' THEN 0 ELSE 1 END) AS n
                FROM glukoza_libre WHERE data BETWEEN ? AND ?
            ) SELECT substr(data || 'T' || czas, 1, 13) || ':00' AS data, AVG(glukoza_mg_dl) AS glukoza
              FROM readings WHERE n = 1 GROUP BY substr(data || 'T' || czas, 1, 13) ORDER BY data
        """,
                (start, end),
            )
        ]
        result["sync"] = [
            dict(row) for row in conn.execute("SELECT * FROM sync_status")
        ]
        result["latest"] = {}
        for table in ("waga", "sen", "hrv", "cisnienie", "body_battery", "metryki_dzienne"):
            row = conn.execute(
                f'SELECT * FROM "{table}" ORDER BY data DESC, rowid DESC LIMIT 1'
            ).fetchone()
            result["latest"][table] = dict(row) if row else None
        for row in result["kalorie_dzienne"]:
            resting, active = row["spoczynkowe_kcal"], row["aktywne_kcal"]
            row["spalone_kcal"] = resting + active if resting is not None and active is not None else None
    return {**result, "from": start, "to": end, "days": days}
