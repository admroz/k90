from contextlib import closing

import pytest
from fastapi.testclient import TestClient

import web_data
from tools.db import get_conn
from tools.time_utils import today_local
from webapp import create_app


@pytest.fixture
def web_client(temp_db, monkeypatch):
    monkeypatch.setenv("WEB_PASSWORD", "test-password-long")
    monkeypatch.setenv("WEB_COOKIE_SECURE", "false")
    monkeypatch.setenv("K90_INTERNAL_TOKEN", "test-internal-token")
    monkeypatch.setenv("CONVERSATION_USER_ID", "owner")
    monkeypatch.setenv("K90_PREVIEW", "true")
    monkeypatch.setenv("K90_SYNC_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    with TestClient(create_app(start_worker=False)) as client:
        yield client


def login(client):
    response = client.post(
        "/api/login",
        json={"password": "test-password-long"},
        headers={"X-K90-Request": "1"},
    )
    assert response.status_code == 200
    return response


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard",
        "/api/meals",
        "/api/tables",
        "/api/tables/waga",
        "/api/documents/pacjent.md",
        "/api/messages",
        "/api/jobs",
    ],
)
def test_private_data_requires_login(web_client, path):
    response = web_client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_login_logout_and_session_cookie(web_client):
    response = login(web_client)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert web_client.get("/api/session").json()["preview"] is True
    assert (
        web_client.post("/api/logout", headers={"X-K90-Request": "1"}).status_code
        == 200
    )
    assert web_client.get("/api/messages").status_code == 401


def test_default_cookie_requires_https(web_client, monkeypatch):
    monkeypatch.delenv("WEB_COOKIE_SECURE")
    assert "Secure" in login(web_client).headers["set-cookie"]


def test_daily_meals_default_to_application_date_and_include_all_meals(web_client, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # In UTC it is still yesterday. Use the application's calendar date.
    monkeypatch.setattr(web_data, "now_local", lambda: datetime(2026, 10, 23, 0, 30, tzinfo=ZoneInfo("Europe/Warsaw")))
    with get_conn() as conn:
        for hour in (20, 7, 16, 10, 13, 22):
            conn.execute(
                "INSERT INTO posilki (data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g) VALUES (?,?,?,?,?,?,?)",
                ("2026-10-23", f"{hour:02}:00", f"Posiłek {hour}", 100, 5, 10, 4),
            )
        conn.execute("INSERT INTO posilki (data,kalorie) VALUES ('2026-10-22', 999)")
        conn.commit()
    login(web_client)
    data = web_client.get("/api/meals").json()
    assert data["date"] == data["today"] == "2026-10-23"
    assert data["previous_date"] == "2026-10-22"
    assert data["next_date"] is None
    assert [row["czas"] for row in data["meals"]] == ["07:00", "10:00", "13:00", "16:00", "20:00", "22:00"]
    assert data["totals"] == {"kalorie": 600, "bialko_g": 30, "weglowodany_g": 60, "tluszcze_g": 24}
    assert all(count == 0 for count in data["missing_values"].values())


def test_daily_meals_can_read_older_days_independently_of_chart_period(web_client, monkeypatch):
    from datetime import datetime

    monkeypatch.setattr(web_data, "now_local", lambda: datetime(2026, 10, 23, 12))
    with get_conn() as conn:
        conn.execute("INSERT INTO posilki (data,czas,opis,kalorie,bialko_g,weglowodany_g,tluszcze_g) VALUES ('2024-02-29','12:30','Starszy posiłek',450,20,50,12)")
        conn.commit()
    login(web_client)
    data = web_client.get("/api/meals?date=2024-02-29").json()
    assert data["date"] == "2024-02-29"
    assert data["previous_date"] == "2024-02-28"
    assert data["next_date"] == "2024-03-01"
    assert data["meals"][0]["opis"] == "Starszy posiłek"
    assert data["totals"]["kalorie"] == 450
    assert web_client.get("/api/dashboard?days=7").json()["posilki"] == []


def test_empty_meal_day_has_zero_totals(web_client):
    login(web_client)
    data = web_client.get("/api/meals?date=2020-01-01").json()
    assert data["meals"] == []
    assert all(value == 0 for value in data["totals"].values())
    assert all(count == 0 for count in data["missing_values"].values())


def test_daily_totals_distinguish_missing_values_from_real_zero(web_client):
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO posilki (data,kalorie,bialko_g,weglowodany_g,tluszcze_g) VALUES ('2026-10-22',?,?,?,?)",
            [(500, 20, None, 10), (None, None, None, 0), (0, 0, None, None)],
        )
        conn.commit()
    login(web_client)
    data = web_client.get("/api/meals?date=2026-10-22").json()
    assert data["totals"] == {"kalorie": 500, "bialko_g": 20, "weglowodany_g": None, "tluszcze_g": 10}
    assert data["missing_values"] == {"kalorie": 1, "bialko_g": 1, "weglowodany_g": 3, "tluszcze_g": 1}
    assert data["meals"][2]["kalorie"] == 0


@pytest.mark.parametrize("day", ["2026-02-30", "not-a-date", "2026-10-23' OR 1=1--"])
def test_meal_day_is_validated(web_client, day):
    login(web_client)
    assert web_client.get("/api/meals", params={"date": day}).status_code == 422


def test_cross_origin_post_and_missing_header_rejected(web_client):
    body = {"password": "test-password-long"}
    assert web_client.post("/api/login", json=body).status_code == 403
    assert (
        web_client.post(
            "/api/login",
            json=body,
            headers={"X-K90-Request": "1", "Origin": "https://other.example"},
        ).status_code
        == 403
    )


def test_login_rate_limit(web_client):
    for _ in range(10):
        assert (
            web_client.post(
                "/api/login", json={"password": "wrong"}, headers={"X-K90-Request": "1"}
            ).status_code
            == 401
        )
    assert (
        web_client.post(
            "/api/login", json={"password": "wrong"}, headers={"X-K90-Request": "1"}
        ).status_code
        == 429
    )


def test_internal_transport_is_not_accessible_with_browser_cookie(web_client):
    login(web_client)
    assert web_client.get("/internal/deliveries").status_code == 401
    assert (
        web_client.get(
            "/internal/deliveries",
            headers={"Authorization": "Bearer test-internal-token"},
        ).status_code
        == 200
    )


def test_health_and_static_files_work_without_telegram(web_client):
    assert web_client.get("/healthz").json() == {"ok": True}
    assert web_client.get("/").status_code == 200
    assert "script-src 'self'" in web_client.get("/").headers["content-security-policy"]
    assert "use strict" in web_client.get("/static/app.js").text


def test_message_idempotency_conflicting_retry_and_pending_refresh(web_client):
    login(web_client)
    body = {"request_id": "web:abc", "text": "Test"}
    headers = {"X-K90-Request": "1"}
    assert (
        web_client.post("/api/messages", json=body, headers=headers).status_code == 202
    )
    assert (
        web_client.post("/api/messages", json=body, headers=headers).status_code == 202
    )
    assert (
        web_client.post(
            "/api/messages", json={**body, "text": "Other"}, headers=headers
        ).status_code
        == 409
    )
    jobs = web_client.get("/api/jobs").json()
    assert len(jobs) == 1 and jobs[0]["payload"]["text"] == "Test"
    # A new browser session still sees the durable pending message.
    web_client.cookies.clear()
    login(web_client)
    assert web_client.get("/api/jobs").json() == jobs


@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "web:empty", "text": "  "},
        {"request_id": "web:bad", "image": "data:image/svg+xml;base64,PHN2Zz4="},
        {"request_id": "web:bad", "image": "data:image/png;base64,YWJj"},
        {"request_id": "web:bad", "image": "data:image/png;base64,!"},
    ],
)
def test_invalid_message_and_image_rejected(web_client, body):
    login(web_client)
    assert (
        web_client.post(
            "/api/messages", json=body, headers={"X-K90-Request": "1"}
        ).status_code
        == 422
    )
    assert web_client.get("/api/jobs").json() == []


def test_web_cannot_impersonate_telegram(web_client):
    login(web_client)
    assert (
        web_client.post(
            "/api/messages",
            json={"request_id": "telegram:123", "text": "test"},
            headers={"X-K90-Request": "1"},
        ).status_code
        == 400
    )


def test_table_pagination_sort_literal_search_and_sql_injection(web_client):
    login(web_client)
    with closing(get_conn()) as conn, conn:
        for i in range(65):
            conn.execute(
                "INSERT INTO posilki (data,opis,kalorie) VALUES ('2026-09-20', ?, ?)",
                (f"Posiłek {i}", i),
            )
        conn.execute(
            "INSERT INTO posilki (data,opis) VALUES ('2026-09-20', 'Jogurt 2%')"
        )
    page = web_client.get(
        "/api/tables/posilki", params={"sort": "kalorie", "limit": 20, "offset": 20}
    ).json()
    assert page["total"] == 66 and len(page["rows"]) == 20
    assert page["rows"][0]["kalorie"] == 44
    matches = web_client.get("/api/tables/posilki", params={"search": "%"}).json()
    assert matches["total"] == 1
    assert (
        web_client.get(
            "/api/tables/posilki", params={"sort": "id; DROP TABLE posilki"}
        ).status_code
        == 400
    )
    assert web_client.get("/api/tables/chat_jobs").status_code == 400
    assert (
        web_client.get("/api/tables/posilki", params={"search": "' OR 1=1 --"}).json()[
            "total"
        ]
        == 0
    )
    assert (
        web_client.get("/api/tables/posilki", params={"limit": 10000}).status_code
        == 422
    )


def test_document_allowlist_and_symlinks(web_client, tmp_path):
    from tools.db import get_data_dir

    login(web_client)
    (get_data_dir() / "pacjent.md").write_text("# Example\n\n<script>alert(1)</script>")
    assert "<script>" in web_client.get("/api/documents/pacjent.md").json()["content"]
    assert web_client.get("/api/documents/system_prompt.md").status_code == 400
    assert web_client.get("/api/documents/.env").status_code == 400
    private = tmp_path / "secret"
    private.write_text("secret")
    (get_data_dir() / "analiza.md").symlink_to(private)
    assert web_client.get("/api/documents/analiza.md").status_code == 400


def test_history_is_shared_by_channel_but_scoped_to_owner(web_client):
    login(web_client)
    with closing(get_conn()) as conn, conn:
        for channel in ("web", "telegram"):
            conn.execute(
                "INSERT INTO conversations (user_id,role,content,channel) VALUES ('owner', 'user', ?, ?)",
                (channel, channel),
            )
        conn.execute(
            "INSERT INTO conversations (user_id,role,content) VALUES ('other', 'user', 'private')"
        )
    rows = web_client.get("/api/messages").json()
    assert [r["content"]["text"] for r in rows] == ["web", "telegram"]
    assert (
        len(web_client.get("/api/messages", params={"before": rows[-1]["id"]}).json())
        == 1
    )
    assert (
        web_client.get("/api/messages?before=999999999999999999999999").status_code
        == 422
    )


def test_dashboard_deduplicates_glucose_and_does_not_turn_missing_into_zero(web_client):
    login(web_client)
    day = today_local()
    with closing(get_conn()) as conn, conn:
        for source, value in (("graph", 100), ("latest", 120)):
            conn.execute(
                "INSERT INTO glukoza_libre (timestamp,source_kind,data,czas,glukoza_mg_dl) VALUES (?, ?, ?, '12:00', ?)",
                (day + "T12:00", source, day, value),
            )
        conn.execute(
            "INSERT INTO posilki (data,opis) VALUES (?, 'Unknown calories')", (day,)
        )
    data = web_client.get("/api/dashboard?days=1").json()
    assert data["from"] == day == data["to"]
    assert data["glukoza"][0]["glukoza"] == 120
    assert data["kalorie"][0]["kcal"] is None
    assert data["latest"]["waga"] is None


def test_chunked_body_size_is_enforced(web_client):
    response = web_client.post(
        "/api/login",
        content=iter([b"x" * 4_000_000, b"x" * 4_000_000]),
        headers={"Content-Type": "application/json", "X-K90-Request": "1"},
    )
    assert response.status_code == 413


def test_worker_processes_without_blocking_api(temp_db, monkeypatch):
    import threading

    monkeypatch.setenv("WEB_PASSWORD", "test-password-long")
    monkeypatch.setenv("WEB_COOKIE_SECURE", "false")
    entered, release = threading.Event(), threading.Event()

    def slow_processor(content):
        entered.set()
        assert release.wait(5)
        return "done"

    with TestClient(create_app(processor=slow_processor)) as client:
        login(client)
        client.post(
            "/api/messages",
            json={"request_id": "web:slow", "text": "hi"},
            headers={"X-K90-Request": "1"},
        )
        try:
            assert entered.wait(2)
            assert client.get("/healthz").json()["ok"]
            assert client.get("/api/dashboard").status_code == 200
            assert client.get("/api/jobs").json()[0]["state"] == "running"
        finally:
            release.set()


def test_second_backend_cannot_own_same_database(web_client):
    with pytest.raises(RuntimeError, match="już uruchomiony backend"):
        with TestClient(create_app(start_worker=False)):
            pass


def test_legacy_non_multimodal_json_does_not_break_history():
    assert web_data.history_content('["abc", 123]')["has_image"] is False
    assert web_data.history_content("[bad json")["text"] == "[bad json"


def test_telegram_delivery_outage_does_not_block_shared_web_conversation(web_client):
    from unittest.mock import Mock

    import requests

    from telegram_adapter import deliver_pending

    internal_headers = {"Authorization": "Bearer test-internal-token"}

    class Backend:
        def call(self, method, path, **kwargs):
            response = web_client.request(
                method, path, headers=internal_headers, **kwargs
            )
            response.raise_for_status()
            return response.json()

    backend = Backend()
    backend.call(
        "POST",
        "/internal/messages",
        json={"request_id": "telegram:outage", "text": "phone", "chat_id": 123},
    )
    web_client.app.state.worker.run_once()
    telegram = Mock()
    telegram.send_text.side_effect = requests.Timeout()
    with pytest.raises(requests.Timeout):
        deliver_pending(telegram, backend)
    login(web_client)
    response = web_client.post(
        "/api/messages",
        json={"request_id": "web:during-outage", "text": "browser"},
        headers={"X-K90-Request": "1"},
    )
    assert response.status_code == 202
    web_client.app.state.worker.run_once()
    rows = web_client.get("/api/messages").json()
    assert [row["channel"] for row in rows] == ["telegram", "telegram", "web", "web"]
    assert web_client.get("/healthz").json()["ok"]
    telegram.send_text.side_effect = None
    deliver_pending(telegram, backend)
    assert backend.call("GET", "/internal/deliveries") == []
    assert len(web_client.get("/api/messages").json()) == 4
