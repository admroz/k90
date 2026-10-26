"""Large synthetic images must not pin a conversation in text filtering."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("size", [131072, 524288])
def test_historical_image_projection_is_bounded_for_realistic_base64(size):
    program = '''import json
from outbound_policy import project_history
raw = json.dumps([{"type":"text","text":"Synthetic meal"}, {"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgoA" + "A" * 131072}}])
result = project_history(raw)
assert result == [{"type":"text","text":"Synthetic meal"}, {"type":"text","text":"[Historical image omitted]"}]
'''
    program = program.replace("131072", str(size))
    try:
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=3)
    except subprocess.TimeoutExpired:
        raise AssertionError(f'Historical image projection exceeded 3s for {size} synthetic base64 characters') from None
    assert result.returncode == 0, result.stderr


def test_email_redaction_matches_original_semantics():
    import itertools
    import re
    from k90_memory.privacy import PrivacyPolicy
    original = re.compile(r"(?i)[\w.!#$%&\x27*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
    samples = ['a@b.c+x@y.z', 'ą.foo+tag@domena.invalid', 'a@b..c',
               'a@b.c.d-', 'x@@a@b.c', 'a@b.c!d@e.f', '@domain.invalid']
    samples += [''.join(s) for n in range(6) for s in itertools.product('a@.+ ', repeat=n)]
    policy = PrivacyPolicy()
    for sample in samples:
        assert policy._text(sample) == original.sub('[REDACTED]', sample), repr(sample)


def test_long_email_tokens_are_bounded_with_and_without_at():
    program = '''from k90_memory.privacy import PrivacyPolicy
p = PrivacyPolicy()
n = 524288
for s, expected in [("A"*n, "A"*n), ("A"*n+"@x", "A"*n+"@x"),
                    ("a@"+"x"*n, "a@"+"x"*n),
                    ("A"*n+"@x.invalid", "[REDACTED]"),
                    ("a@"+"x."*(n//2)+"!", "[REDACTED].!")]:
    assert p._text(s) == expected
'''
    result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                            capture_output=True, text=True, timeout=4)
    assert result.returncode == 0, result.stderr
