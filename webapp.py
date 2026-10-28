"""Single-owner LAN web API. Run one Uvicorn worker per database."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager, closing
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Literal
from datetime import time as MealTime

import web_data
from tools.db import get_conn, get_db_path
from tools.images import MAX_IMAGE_BYTES, image_mime_type
from tools.patient import ALLOWED_FILES
from tools.time_utils import APP_TIMEZONE
from web_runtime import (
    ConversationWorker,
    enqueue,
    get_transport,
    init_runtime,
    set_transport,
)

STATIC = Path(__file__).parent / "web"


class BodyLimitMiddleware:
    """Enforce the actual body limit, including requests using chunked encoding."""

    def __init__(self, app, limit=7_100_000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.limit:
                return await JSONResponse(
                    {"detail": "Żądanie jest za duże."}, status_code=413
                )(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(messages)

        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        await self.app(scope, replay, send)


class Message(BaseModel):
    request_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9:_-]+$")
    text: str = Field(default="", max_length=16000)
    image: str | None = Field(default=None, max_length=7_000_000)

    @model_validator(mode="after")
    def valid_content(self):
        if not self.text.strip() and not self.image:
            raise ValueError("Wpisz wiadomość lub dodaj zdjęcie.")
        if self.image:
            header, _, encoded = self.image.partition(",")
            if header not in (
                "data:image/jpeg;base64",
                "data:image/png;base64",
                "data:image/webp;base64",
            ):
                raise ValueError("Obsługujemy JPG, PNG i WebP.")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except ValueError:
                raise ValueError("Nieprawidłowy obraz.") from None
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError("Zdjęcie może mieć maksymalnie 5 MB.")
            declared_mime = header.removeprefix("data:").removesuffix(";base64")
            if image_mime_type(raw) != declared_mime:
                raise ValueError("Zawartość pliku nie odpowiada formatowi zdjęcia.")
        return self

    def content(self):
        if not self.image:
            return self.text.strip()
        return [
            {
                "type": "text",
                "text": self.text.strip()
                or "Przeanalizuj załączone zdjęcie. Nie zapisuj posiłku bez potwierdzenia, że został zjedzony.",
            },
            {"type": "image_url", "image_url": {"url": self.image}},
        ]


class MealOperation(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9:_-]+$")


class MealEdit(MealOperation):
    description: str = Field(min_length=1, max_length=2000)
    calories: float | None = Field(ge=0, le=1000000)
    protein_g: float | None = Field(ge=0, le=1000000)
    carbs_g: float | None = Field(ge=0, le=1000000)
    fat_g: float | None = Field(ge=0, le=1000000)
    quantity: float | None = Field(ge=0, le=1000000)
    unit: Literal['g', 'ml', 'szt'] | None
    date: str
    time: str | None

    @model_validator(mode='after')
    def valid_meal(self):
        if not self.description.strip():
            raise ValueError('Opis nie może być pusty.')
        if (self.quantity is None) != (self.unit is None):
            raise ValueError('Podaj ilość i jednostkę razem albo pozostaw oba puste.')
        if date.fromisoformat(self.date).isoformat() != self.date:
            raise ValueError('Data: YYYY-MM-DD.')
        if self.time is not None and MealTime.fromisoformat(self.time).strftime('%H:%M') != self.time:
            raise ValueError('Godzina: HH:MM lub null dla nieznanej.')
        return self


class TelegramMessage(Message):
    chat_id: int


class Login(BaseModel):
    password: str = Field(max_length=1024)


class SyncRequest(BaseModel):
    request_id: str = Field(min_length=5, max_length=120, pattern=r"^web:[a-zA-Z0-9:_-]+$")


class Delivery(BaseModel):
    index: int = Field(ge=0)
    done: bool = False


class TransportStatus(BaseModel):
    status: str = Field(max_length=80)


class Offset(BaseModel):
    offset: int = Field(ge=0)


def create_app(*, start_worker=True, processor=None):
    from logging_setup import configure_logging
    configure_logging()
    sessions = {}
    login_attempts = deque()

    @asynccontextmanager
    async def lifespan(app):
        if not os.getenv("WEB_PASSWORD") or len(os.environ["WEB_PASSWORD"]) < 12:
            raise RuntimeError("Ustaw WEB_PASSWORD (co najmniej 12 znaków).")
        lock_path = Path(get_db_path()).with_suffix(".web.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(
                    "Ta baza ma już uruchomiony backend. Użyj jednego workera."
                ) from None
            init_runtime()
            import memory_runtime
            worker = ConversationWorker(processor)
            app.state.worker = worker
            if start_worker:
                memory_runtime.start_worker()
                worker.start()
            try:
                yield
            finally:
                worker.stop.set()
                if start_worker:
                    worker.thread.join(timeout=5)
                    memory_runtime.stop_worker()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def meal_validation_error(request, exc):
        if request.url.path.startswith('/api/meals/'):
            # Do not echo private fields or non-JSON NaN/Infinity in an error response.
            return JSONResponse({'detail': 'Sprawdź opis, liczby (0–1000000), datę, godzinę i jednostkę.'}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        # JSON-only mutating endpoints plus a custom header prevent cross-site form requests.
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 7_100_000:
            return JSONResponse({"detail": "Żądanie jest za duże."}, status_code=413)
        if request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ) and not request.url.path.startswith("/internal/"):
            origin = request.headers.get("origin")
            if request.headers.get("x-k90-request") != "1" or (
                origin and urlsplit(origin).netloc != request.headers.get("host")
            ):
                return JSONResponse(
                    {"detail": "Niedozwolone źródło żądania."}, status_code=403
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    async def authenticated(request: Request):
        token = request.cookies.get("k90_session", "")
        expires = sessions.get(token, 0)
        if expires <= time.time():
            sessions.pop(token, None)
            raise HTTPException(401, "Zaloguj się, aby uzyskać dostęp.")

    def internal(request: Request):
        expected = os.getenv("K90_INTERNAL_TOKEN", "")
        actual = request.headers.get("authorization", "")
        if not expected or not hmac.compare_digest(
            actual.encode(), f"Bearer {expected}".encode()
        ):
            raise HTTPException(401, "Brak dostępu.")

    def submit(message, channel, chat_id=None):
        try:
            job = enqueue(message.request_id, message.content(), channel, chat_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        except OverflowError as exc:
            raise HTTPException(429, str(exc)) from None
        result = {"request_id": job["request_id"], "state": job["state"]}
        if channel == "telegram":
            result.update(profile_id=job["profile_id"], job_id=job["seq"])
        return result

    @app.get("/healthz")
    def health():
        with closing(get_conn()) as conn:
            conn.execute("SELECT 1").fetchone()
        healthy = not start_worker or app.state.worker.thread.is_alive()
        return JSONResponse({"ok": healthy}, status_code=200 if healthy else 503)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return RedirectResponse("/static/favicon.svg")

    @app.post("/api/login")
    async def login(body: Login, response: Response):
        now = time.time()
        while login_attempts and login_attempts[0] < now - 60:
            login_attempts.popleft()
        if len(login_attempts) >= 10:
            raise HTTPException(429, "Zbyt wiele prób. Spróbuj za minutę.")
        login_attempts.append(now)
        expected = hashlib.sha256(os.environ["WEB_PASSWORD"].encode()).digest()
        if not hmac.compare_digest(
            hashlib.sha256(body.password.encode()).digest(), expected
        ):
            raise HTTPException(401, "Nieprawidłowe hasło.")
        for token, expiry in list(sessions.items()):
            if expiry <= now:
                sessions.pop(token, None)
        if len(sessions) >= 20:
            sessions.pop(next(iter(sessions)))
        token = secrets.token_urlsafe(32)
        sessions[token] = now + 12 * 3600
        response.set_cookie(
            "k90_session",
            token,
            httponly=True,
            samesite="strict",
            secure=os.getenv("WEB_COOKIE_SECURE", "true") != "false",
            max_age=12 * 3600,
        )
        return {"ok": True}

    @app.post("/api/logout", dependencies=[Depends(authenticated)])
    async def logout(request: Request, response: Response):
        sessions.pop(request.cookies.get("k90_session"), None)
        response.delete_cookie("k90_session")
        return {"ok": True}

    @app.get("/api/session", dependencies=[Depends(authenticated)])
    def session():
        return {
            "preview": os.getenv("K90_PREVIEW") == "true",
            "local": os.getenv("K90_LOCAL") == "true",
            "timezone": APP_TIMEZONE,
            "sync_enabled": os.getenv("K90_SYNC_ENABLED", "true") != "false",
            "telegram_enabled": os.getenv("TELEGRAM_ENABLED", "true") != "false",
            "telegram": get_transport(
                "telegram_status", {"status": "brak połączenia", "at": 0}
            ),
        }

    from tools import food_catalog

    def catalog_action(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, TypeError, OverflowError) as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get('/api/catalog', dependencies=[Depends(authenticated)])
    def catalog_list(query: str = Query('', max_length=200), barcode: str | None = None):
        return catalog_action(food_catalog.search, query, barcode)

    @app.post('/api/catalog', dependencies=[Depends(authenticated)])
    def catalog_create(body: dict):
        return catalog_action(food_catalog.propose, body, request_id=body.get('request_id'),
                              owner=os.getenv('CONVERSATION_USER_ID', 'owner'))

    @app.post('/api/catalog/lookup', dependencies=[Depends(authenticated)])
    def catalog_lookup(body: dict):
        from tools.food_off import lookup
        return catalog_action(lookup, body.get('barcode'))

    @app.get('/api/catalog/{product_id}/label', dependencies=[Depends(authenticated)])
    def catalog_label(product_id: int):
        return catalog_action(food_catalog.label_image, product_id)

    @app.put('/api/catalog/{product_id}', dependencies=[Depends(authenticated)])
    def catalog_edit(product_id: int, body: dict):
        return catalog_action(food_catalog.revise, product_id, body.get('version'), body.get('product', {}),
                              owner=os.getenv('CONVERSATION_USER_ID', 'owner'))

    @app.post('/api/catalog/{product_id}/confirm', dependencies=[Depends(authenticated)])
    def catalog_confirm(product_id: int, body: dict):
        return catalog_action(food_catalog.confirm, product_id, body.get('version'),
                              owner=os.getenv('CONVERSATION_USER_ID', 'owner'))

    @app.post('/api/catalog/{product_id}/portion', dependencies=[Depends(authenticated)])
    def catalog_portion(product_id: int, body: dict):
        return catalog_action(food_catalog.log_portion, product_id, body.get('version'),
                              body.get('quantity'), body.get('unit'), body.get('request_id'))

    @app.get("/api/dashboard", dependencies=[Depends(authenticated)])
    def dashboard(days: int = Query(30, ge=1, le=366)):
        return web_data.dashboard(days)

    def mutate_meal(meal_id, body, kind):
        from tools.diet import _perform
        args = body.model_dump()
        request_id = 'web-meal:' + args.pop('request_id')
        args['meal_id'] = meal_id
        owner = os.getenv('CONVERSATION_USER_ID', 'owner')
        operation_id = hashlib.sha256(json.dumps([owner, request_id, kind, meal_id]).encode()).hexdigest()[:32]
        try:
            result = _perform(kind, args, owner=owner, request_id=request_id,
                              operation_id=operation_id, chat=False)
        except (ValueError, TypeError, OverflowError):
            raise HTTPException(422, 'Sprawdź opis, liczby, datę, godzinę i jednostkę.') from None
        if not result.get('success'):
            raise HTTPException(result.get('code', 409), result['error'])
        return result

    @app.put('/api/meals/{meal_id}', dependencies=[Depends(authenticated)])
    def edit_meal(meal_id: int, body: MealEdit):
        return mutate_meal(meal_id, body, 'update_meal')

    @app.delete('/api/meals/{meal_id}', dependencies=[Depends(authenticated)])
    def remove_meal(meal_id: int, body: MealOperation):
        return mutate_meal(meal_id, body, 'delete_meal')

    @app.get("/api/meals", dependencies=[Depends(authenticated)])
    def meals(day: date | None = Query(None, alias="date")):
        return web_data.meals_for_day(day)

    @app.post("/api/sync/garmin", status_code=202, dependencies=[Depends(authenticated)])
    def sync_garmin(body: SyncRequest):
        if os.getenv("K90_SYNC_ENABLED", "true").lower() == "false":
            raise HTTPException(409, "Synchronizacja jest wyłączona w lokalnej kopii danych.")
        try:
            job = enqueue(body.request_id, "", kind="garmin_sync")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        except OverflowError as exc:
            raise HTTPException(429, str(exc)) from None
        return {"request_id": job["request_id"], "state": job["state"]}

    @app.get("/api/sync/garmin", dependencies=[Depends(authenticated)])
    def garmin_sync_status():
        with closing(get_conn()) as conn:
            row = conn.execute("SELECT request_id, state, response, created_at, finished_at FROM chat_jobs WHERE kind = 'garmin_sync' ORDER BY seq DESC LIMIT 1").fetchone()
            through = conn.execute("SELECT MAX(data) FROM kalorie_dzienne").fetchone()[0]
        return {**dict(row), "calories_through": through} if row else None

    @app.get("/api/tables", dependencies=[Depends(authenticated)])
    def tables():
        return list(web_data.TABLES)

    @app.get("/api/tables/{table}", dependencies=[Depends(authenticated)])
    def table(
        table: str,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        sort: str | None = None,
        descending: bool = True,
        search: str = Query("", max_length=200),
    ):
        try:
            return web_data.read_table(table, limit, offset, sort, descending, search)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/documents", dependencies=[Depends(authenticated)])
    def documents():
        return [*sorted(ALLOWED_FILES), "patient_summary"]

    @app.get("/api/documents/{name}", dependencies=[Depends(authenticated)])
    def document(name: str):
        try:
            return web_data.document(name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/messages", dependencies=[Depends(authenticated)])
    def messages(
        before: int | None = Query(None, ge=1, le=2**63 - 1),
        limit: int = Query(50, ge=1, le=100),
    ):
        from web_runtime import timeline
        from profiling import request_scope, span
        rows = timeline(os.getenv("CONVERSATION_USER_ID", "owner"), before, limit)
        result = []
        for row in rows:
            with request_scope(row['channel'], row['profile_id'], row['job_id'], scope='delivery'):
                with span('transport_delivery'):
                    result.append({**row, 'content': web_data.history_content(row['content'])})
        return result

    @app.get("/api/jobs", dependencies=[Depends(authenticated)])
    def jobs():
        with closing(get_conn()) as conn:
            rows = conn.execute(
                "SELECT request_id, channel, payload, state, response, created_at FROM chat_jobs WHERE state != 'done' AND kind = 'message' AND user_id = ? ORDER BY seq DESC LIMIT 100",
                (os.getenv("CONVERSATION_USER_ID", "owner"),),
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": web_data.history_content(json.loads(row["payload"])),
            }
            for row in reversed(rows)
        ]

    @app.post("/api/messages", status_code=202, dependencies=[Depends(authenticated)])
    def message(body: Message):
        if not body.request_id.startswith("web:"):
            raise HTTPException(400, "Nieprawidłowy identyfikator wiadomości.")
        return submit(body, "web")

    @app.post("/internal/messages", status_code=202, dependencies=[Depends(internal)])
    def telegram_message(body: TelegramMessage):
        if not body.request_id.startswith("telegram:"):
            raise HTTPException(400, "Nieprawidłowy identyfikator.")
        return submit(body, "telegram", body.chat_id)

    @app.get("/internal/offset", dependencies=[Depends(internal)])
    def offset():
        return {"offset": get_transport("telegram_offset")}

    @app.post("/internal/offset", dependencies=[Depends(internal)])
    def save_offset(body: Offset):
        set_transport("telegram_offset", body.offset)
        return {"ok": True}

    @app.post("/internal/status", dependencies=[Depends(internal)])
    def status(body: TransportStatus):
        set_transport("telegram_status", {"status": body.status, "at": time.time()})
        return {"ok": True}

    @app.get("/internal/deliveries", dependencies=[Depends(internal)])
    def deliveries():
        with closing(get_conn()) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT request_id, chat_id, response, delivery_index, profile_id, seq AS job_id FROM chat_jobs WHERE channel = 'telegram' AND delivered = 0 AND state IN ('done', 'failed', 'interrupted') ORDER BY seq LIMIT 10"
                )
            ]

    @app.post("/internal/deliveries/{request_id}", dependencies=[Depends(internal)])
    def delivered(request_id: str, body: Delivery):
        with closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE chat_jobs SET delivery_index = MAX(delivery_index, ?), delivered = MAX(delivered, ?) WHERE request_id = ? AND channel = 'telegram'",
                (body.index, int(body.done), request_id),
            )
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
