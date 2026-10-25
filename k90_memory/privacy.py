"""Conservative local outbound filter, NOT a guarantee of anonymization.

Health context is allowed. Direct identifiers are masked; configured terms must
cover names/addresses not recognizable by generic rules. Never log rejected input.
"""
from dataclasses import dataclass
import json
import math
import re


class PrivacyError(ValueError):
    def __init__(self):
        super().__init__('outbound content blocked')


_SECRET = re.compile(r'(?i)\bbearer\s+\S+|\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret)[\"\x27]?\s*[=:]\s*\S+|\bsk-[\w-]{16,}|-----BEGIN [^-]*PRIVATE KEY-----')
_EMAIL = re.compile(r'(?i)[\w.!#$%&\x27*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+')
_PESEL = re.compile(r'(?<!\d)\d{11}(?!\d)')
_PHONE = re.compile(r'(?<!\w)(?:\+?48[ .-]?)?(?:\(?\d{3}\)?[ .-]?){2}\d{3}(?!\w)')
_PHONE_INTL = re.compile(r'(?<!\w)\+\d{1,3}[ .-]?(?:\(?\d\)?[ .-]?){6,14}(?!\w)')
_PHONE_US = re.compile(r'(?<!\w)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\w)')
_LOCAL_ONLY = re.compile(r'(?i)(?:\[|<)local[_ -]only(?:\]|>)')
_SECRET_KEYS = {'authorization', 'proxyauthorization', 'apikey', 'password', 'passwd', 'secret', 'clientsecret', 'accesstoken', 'refreshtoken', 'privatekey', 'cookie', 'setcookie'}
_IDENTIFIER_KEYS = {'pesel', 'phone', 'phonenumber', 'telephone', 'telephonenumber', 'mobile', 'mobilenumber', 'nationalid', 'nationalidentifier', 'ssn', 'socialsecuritynumber'}
_IMAGE_KEYS = {'image', 'imageurl', 'inputimage', 'imagedata', 'file', 'filedata', 'inputfile', 'attachment', 'attachments', 'audio', 'inputaudio', 'video', 'inputvideo', 'document', 'pdf', 'base64'}


def _key(key):
    return re.sub(r'[^a-z0-9]', '', key.casefold())


def strict_json_loads(raw):
    """Decode without discarding ambiguous pairs (including escaped-equal keys).

    Privacy callers bound the input and decoded walk separately. Syntax errors
    remain ValueError; duplicate/non-finite input is a fixed PrivacyError.
    """
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PrivacyError()
            result[key] = value
        return result
    def constant(_):
        raise PrivacyError()
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


@dataclass(frozen=True)
class PrivacyPolicy:
    redact_terms: tuple[str, ...] = ()
    allow_images: bool = False
    max_chars: int = 1_000_000
    max_depth: int = 40

    def __post_init__(self):
        if (type(self.redact_terms) not in (tuple, list)
                or any(type(t) is not str or not t.strip() or len(t) > 1000 for t in self.redact_terms)
                or len(self.redact_terms) > 1000 or type(self.allow_images) is not bool
                or type(self.max_chars) is not int or not 1 <= self.max_chars <= 10_000_000
                or type(self.max_depth) is not int or not 1 <= self.max_depth <= 100):
            raise PrivacyError()
        object.__setattr__(self, 'redact_terms', tuple(self.redact_terms))

    def _text(self, text):
        if type(text) is not str or len(text) > self.max_chars:
            raise PrivacyError()
        if _SECRET.search(text) or _LOCAL_ONLY.search(text):
            raise PrivacyError()
        if not self.allow_images and re.search(r'(?i)data:(?:image|audio|video|application)/', text):
            raise PrivacyError()
        for term in sorted(self.redact_terms, key=len, reverse=True):
            text = re.sub(re.escape(term), '[REDACTED]', text, flags=re.IGNORECASE)
        for pattern in (_EMAIL, _PHONE_INTL, _PESEL, _PHONE_US, _PHONE):
            text = pattern.sub('[REDACTED]', text)
        return text

    def sanitize_text(self, text):
        """Also inspect JSON-encoded arguments, including keys and escaped strings."""
        clean = self.sanitize(text)
        if type(clean) is not str:
            raise PrivacyError()
        return clean

    def sanitize(self, value):
        """Return a fresh JSON-compatible tree; block unknown/binary objects.

        Keys are filtered as well as values. Protocol keys remain unchanged unless
        explicitly matched by a redact term; collisions are rejected, never merged.
        Images/files are rejected anywhere by default. Image consent is solely for
        a model boundary, NEVER permission for the memory backend to index images.
        """
        budget = [0, 0]
        def walk(obj, depth, required_json=False, preserve_json=False):
            budget[0] += 1
            if depth > self.max_depth or budget[0] > 100_000:
                raise PrivacyError()
            if type(obj) is str:
                budget[1] += len(obj)
                if budget[1] > self.max_chars:
                    raise PrivacyError()
                stripped = obj.lstrip()
                if required_json or stripped.startswith(('{', '[', '"')):
                    try:
                        parsed = strict_json_loads(obj)
                    except PrivacyError:
                        raise
                    except (ValueError, RecursionError):
                        # Object-like and quoted encodings are always fail-closed.
                        # Only a complete, plain Markdown label can disambiguate
                        # a leading '[' from a malformed JSON array. Do not infer
                        # safety from an unrecognized/broken JSON key prefix.
                        label, closed, _ = stripped[1:].partition(']')
                        markdown = (stripped.startswith('[') and closed and label
                                    and not any(c in label for c in '{}["\'\\,:')
                                    and (not label.strip() or
                                         (label.lstrip()[0].isalpha() and
                                          label.strip() not in ('true', 'false', 'null'))))
                        if required_json or not markdown:
                            raise PrivacyError() from None
                        return self._text(obj)
                    # Reuse this walk's depth/node/character budgets for every
                    # decoded layer, and retain the original number of encodings.
                    clean = walk(parsed, depth + 1)
                    if preserve_json:
                        # Names cannot be canonicalized or partially redacted:
                        # that could rename a protocol field or create a collision.
                        # A decoded scalar name has no enclosing value here, so
                        # it cannot safely inherit field-specific restrictions.
                        # Reject encoded reserved names rather than accepting
                        # escaped aliases of e.g. api_key/local_only/type/phone.
                        reserved = (_SECRET_KEYS | _IDENTIFIER_KEYS | _IMAGE_KEYS |
                                    {'localonly', 'type', 'role', 'mimetype', 'mediatype',
                                     'arguments', 'toolcallid', 'callid'})
                        if type(parsed) is str and _key(parsed) in reserved:
                            raise PrivacyError()
                        if clean != parsed:
                            raise PrivacyError()
                        return obj
                    return json.dumps(clean, ensure_ascii=False, separators=(',', ':'))
                return self._text(obj)
            if obj is None or type(obj) is bool:
                return obj
            if type(obj) is int or (type(obj) is float and math.isfinite(obj)):
                # JSON numbers must not bypass the same identifier rules used
                # for strings. Preserve the numeric type of ordinary metrics.
                text = str(int(obj)) if type(obj) is float and obj.is_integer() else str(obj)
                clean = self._text(text)
                return clean if clean != text else obj
            if type(obj) in (list, tuple):
                return [walk(item, depth + 1) for item in obj]
            if type(obj) is dict:
                out = {}
                for key, item in obj.items():
                    if type(key) is not str:
                        raise PrivacyError()
                    canonical = _key(key)
                    if canonical in _SECRET_KEYS:
                        raise PrivacyError()
                    if canonical == 'localonly' and item is not False:
                        raise PrivacyError()
                    if not self.allow_images and (canonical in _IMAGE_KEYS or
                            (canonical == 'type' and type(item) is str and _key(item) in _IMAGE_KEYS) or
                            (canonical in ('mimetype', 'mediatype') and type(item) is str and re.match(r'(?i)(?:image|video|audio|application)/', item))):
                        raise PrivacyError()
                    clean_key = walk(key, depth + 1, preserve_json=True)
                    if clean_key in out or budget[1] > self.max_chars:
                        raise PrivacyError()
                    clean_item = walk(item, depth + 1, required_json=canonical == 'arguments')
                    if canonical in _IDENTIFIER_KEYS and type(item) in (int, float):
                        # Numeric JSON has already discarded any leading zeroes;
                        # semantic identifier fields cannot use a length heuristic.
                        clean_item = '[REDACTED]'
                    if canonical in ('role', 'type', 'toolcallid', 'callid') and (clean_key != key or clean_item != item):
                        raise PrivacyError()
                    out[clean_key] = clean_item
                return out
            raise PrivacyError()
        try:
            return walk(value, 0)
        except Exception:
            raise PrivacyError() from None
