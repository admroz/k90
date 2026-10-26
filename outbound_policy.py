"""Shared fail-closed model boundary. Local originals are never rewritten."""
from __future__ import annotations

import json
import os
import base64
import re
from dataclasses import replace
from urllib.parse import urlsplit

from k90_memory import PrivacyError, PrivacyPolicy
from k90_memory.privacy import strict_json_loads


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


def project_history(raw):
    """Validate originals before omitting recognized historical image parts.

    Image permission during the first walk only permits inspection of image
    fields; all other restrictions and encoded JSON checks still apply. The
    second walk always forbids images, independently of live-upload consent.
    Never mutate the stored original or infer an image's contents.
    """
    policy = replace(model_policy(), allow_images=False)
    inspected = replace(policy, allow_images=True).sanitize_text(raw)
    try:
        parsed = strict_json_loads(raw)
    except PrivacyError:
        raise
    except (ValueError, TypeError):
        return policy.sanitize_text(inspected)
    if not isinstance(parsed, list):
        return policy.sanitize_text(inspected)
    projected = []
    for part in parsed:
        if type(part) is not dict:
            raise PrivacyError()
        if part.get('type') == 'text':
            if set(part) != {'type', 'text'} or type(part['text']) is not str:
                raise PrivacyError()
            projected.append(part)
        elif part.get('type') == 'image_url':
            image = part.get('image_url')
            if (set(part) != {'type', 'image_url'} or type(image) is not dict
                    or not {'url'} <= set(image) <= {'url', 'detail'}
                    or type(image['url']) is not str or not image['url']
                    or ('detail' in image and image['detail'] not in ('auto', 'low', 'high'))):
                raise PrivacyError()
            _validate_historical_image_url(image['url'])
            projected.append({'type': 'text', 'text': '[Historical image omitted]'})
        else:
            raise PrivacyError()
    return policy.sanitize(projected)


def _validate_historical_image_url(url):
    """Accept the supported URL envelope, without fetching or decoding an image."""
    try:
        if url.startswith('data:'):
            match = re.fullmatch(r'data:image/[A-Za-z0-9.+-]+;base64,([A-Za-z0-9+/]+={0,2})', url)
            if not match:
                raise PrivacyError()
            base64.b64decode(match[1], validate=True)
        else:
            parsed = urlsplit(url)
            if (parsed.scheme not in ('https', 'http') or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or any(c.isspace() or ord(c) < 32 for c in url)):
                raise PrivacyError()
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
