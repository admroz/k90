"""Provide a per-container private transport credential before starting Supervisor."""

import os
import secrets

os.environ.setdefault("K90_INTERNAL_TOKEN", secrets.token_urlsafe(48))
os.execvp("supervisord", ["supervisord", "-c", "/app/supervisord.conf"])
