"""Timezone helpers for application-local time calculations."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Warsaw")


def now_local() -> datetime:
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def today_local() -> str:
    return now_local().date().isoformat()


def date_days_ago(days: int) -> str:
    return (now_local().date() - timedelta(days=days)).isoformat()
