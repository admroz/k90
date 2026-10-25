"""Shared fail-closed model boundary. Local originals are never rewritten."""
from __future__ import annotations

import json
import os

from k90_memory import PrivacyError, PrivacyPolicy


class ModelCallError(RuntimeError):
    """Fixed provider diagnostic without upstream request/response contents."""


def model_policy():
    """Strict local settings. No cloud service is used to sanitize information."""
    try:
        terms=json.loads(os.getenv('K90_PRIVACY_REDACT_TERMS','[]'))
        images=os.getenv('K90_ALLOW_MODEL_IMAGES','false').strip().casefold()
        if images not in ('true','false'):
            raise PrivacyError()
        return PrivacyPolicy(redact_terms=terms,allow_images=images=='true',
                             max_chars=int(os.getenv('K90_OUTBOUND_MAX_CHARS','2000000')))
    except Exception:
        raise PrivacyError() from None


def sanitize_payload(value):
    try:
        return model_policy().sanitize(value)
    except Exception:
        raise PrivacyError() from None


def chat_completion(completion, **payload):
    safe=sanitize_payload(payload)
    try:
        return completion(**safe)
    except PrivacyError:
        raise
    except Exception:
        raise ModelCallError('model_request_failed') from None
