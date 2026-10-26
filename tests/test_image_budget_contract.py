"""Supported intake must survive actual photo -> text, without image replay."""
import base64
import json
import random
import struct
import zlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from k90_memory import PrivacyError, PrivacyPolicy
from outbound_policy import sanitize_payload, project_history


def png(target):
    # Exact independent-review fixture, including its legal padding chunk.
    n = {1179648: 295000, 1572864: 393000, 4999000: 1249000}.get(target, 1)
    def chunk(k, d):
        return struct.pack('>I', len(d)) + k + d + struct.pack('>I', zlib.crc32(k+d) & 0xffffffff)
    pixels = random.Random(90).randbytes(n * 3)
    scan = b''.join(b'\0' + pixels[i:i+3] for i in range(0, len(pixels), 3))
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, n, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b''))
    data = data[:-12] + chunk(b'npAd', b'x' * (target-len(data)-12)) + data[-12:]
    assert len(data) == target
    return data


def part(data):
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(data).decode()}}


@pytest.mark.parametrize('size', [1179648, 1572864, 4999000])
def test_accepted_photo_then_text_real_agent(temp_db, monkeypatch, size):
    import agent
    from webapp import Message
    from tools.db import get_conn
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    monkeypatch.setenv('K90_AGENT_AUTH', 'api')
    image = part(png(size))
    uri = image['image_url']['url']
    assert Message(request_id='web:budget', text='Synthetic millet', image=uri).image == uri
    photo = [{'type': 'text', 'text': 'Synthetic millet'}, image]
    sent = []
    def complete(**kw):
        sent.append(kw)
        msg = SimpleNamespace(content='Synthetic answer', tool_calls=[],
                              model_dump=lambda **kw: {'role': 'assistant', 'content': 'Synthetic answer'})
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)
    with patch.object(agent, 'MODEL', 'synthetic'), patch.object(agent, '_build_system_message', lambda: ('Synthetic system', {})), patch('memory_runtime.start_worker', lambda: None), patch.object(agent.litellm, 'completion', complete):
        agent.run_agent(photo, 'budget-owner')
        assert sent[0]['messages'][-1]['content'][1] == image
        with get_conn() as conn:
            original = conn.execute("SELECT content FROM conversations WHERE role='user'").fetchone()[0]
            events = [tuple(r) for r in conn.execute('SELECT id,payload FROM agent_events')]
        monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'false')
        agent.run_agent('150 g, steamed', 'budget-owner')
    assert len(sent) == 2
    followup = json.dumps(sent[1])
    assert 'Historical image omitted' in followup
    assert 'base64' not in followup and uri not in followup
    with get_conn() as conn:
        assert conn.execute("SELECT content FROM conversations WHERE role='user' ORDER BY id LIMIT 1").fetchone()[0] == original
        assert json.loads(original) == photo
        assert [tuple(r) for r in conn.execute('SELECT id,payload FROM agent_events WHERE id<=?', (events[-1][0],))] == events


def test_separate_text_image_and_parse_limits(monkeypatch):
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    policy = PrivacyPolicy(allow_images=True, max_chars=2000000)
    image = part(png(4999000))
    assert policy.sanitize([image, image]) == [image, image]
    for value in ([image] * 3, part(png(5000001)), 'x' * 2000001,
                  {'text': 'x' * 2000001, 'photo': image},
                  json.dumps({'text': 'x' * 1100000, 'photo': image}),
                  json.dumps({'local_only': True, 'photo': image}),
                  json.dumps({'password': 'synthetic', 'photo': image}),
                  json.dumps({'text': 'x' * 16000000}),
                  '{"broken":"' + 'x' * 16000000):
        with pytest.raises(PrivacyError):
            policy.sanitize(value)
    nested = json.dumps(image)
    for _ in range(4):
        nested = json.dumps(nested)
    with pytest.raises(PrivacyError):
        policy.sanitize(nested)
    with pytest.raises(PrivacyError):
        policy.sanitize([None] * 100001)
    with pytest.raises(PrivacyError):
        PrivacyPolicy(allow_images=True, max_depth=1).sanitize(image)


def test_bounds_precede_json_allocation_and_binary_decode(monkeypatch):
    import k90_memory.privacy as privacy
    policy = PrivacyPolicy(allow_images=True, max_chars=2000000)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('Unbounded input reached allocating parser/decoder')
    with patch.object(privacy, 'strict_json_loads', forbidden):
        with pytest.raises(PrivacyError):
            policy.sanitize('{"text":"' + 'x' * 16000000 + '"}')
    assert calls == []
    with patch.object(privacy.base64, 'b64decode', forbidden):
        with pytest.raises(PrivacyError):
            policy.sanitize({'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + 'A' * 7000000}})
    assert calls == []


def test_exact_decimal_intake_limit_and_encoded_history(monkeypatch):
    from webapp import Message
    monkeypatch.setenv('K90_ALLOW_MODEL_IMAGES', 'true')
    image = part(png(5000000))
    uri = image['image_url']['url']
    assert Message(request_id='web:exact-limit', text='Synthetic meal', image=uri).image == uri
    assert sanitize_payload([image]) == [image]
    raw = json.dumps([image])
    assert project_history(raw) == [{'type': 'text', 'text': '[Historical image omitted]'}]
    # Large image doesn't exempt remote URL/prose or encoded text from text rules.
    policy = PrivacyPolicy(allow_images=True, max_chars=2000000)
    for value in ('meal ' + uri, {'type': 'image_url', 'image_url': {'url': 'https://synthetic.invalid/' + 'x' * 2000000}},
                  json.dumps({'metadata': json.dumps({'local_only': True}), 'photo': image})):
        with pytest.raises(PrivacyError):
            policy.sanitize(value)
