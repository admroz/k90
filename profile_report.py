"""Bounded, content-free owner report. No database, network or HTTP file selector."""
import ast
from collections import defaultdict, deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat

from profiling import STAGES

MAX_BYTES = 2 * 1024 * 1024  # per file, four current/rotated files
MAX_LINE = 16384
MAX_RECORDS = 12000
HEX = re.compile(r'[0-9a-f]{32}')


def ident(value):
    return value if type(value) is str and HEX.fullmatch(value) else None


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 604800000 else None


def timestamp(value):
    try:
        if type(value) is not str or len(value) > 40:
            return None
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.astimezone(timezone.utc).isoformat() if date.tzinfo else None
    except ValueError:
        return None


def clean(raw, legacy=False):
    if type(raw) is not dict or raw.get('stage') not in STAGES or raw.get('event') not in ('start', 'finish', 'error', 'timeout', 'summary', 'first_event', 'first_text'):
        return None
    request = ident(raw.get('request_id'))
    if not request:
        return None
    scope = raw.get('scope')
    if scope not in ('processing', 'submission', 'delivery', 'background'):
        scope = 'processing' if legacy else None
    if scope is None:
        return None
    result = dict(request_id=request, scope=scope, scope_id=ident(raw.get('scope_id')),
                  clock_id=ident(raw.get('clock_id')), utc=timestamp(raw.get('utc')),
                  channel=raw.get('channel') if raw.get('channel') in ('web', 'telegram', 'cli', 'background') else 'unknown',
                  stage=raw['stage'], event=raw['event'], elapsed_ms=number(raw.get('elapsed_ms')),
                  clock_reset=raw.get('clock_reset') is True, legacy=legacy)
    for key in ('span_id', 'parent_span_id', 'job_id'):
        v = raw.get(key)
        result[key] = v if type(v) is int and 0 < v < 2**53 else None
    return result


def seconds(utc):
    return datetime.fromisoformat(utc).timestamp() if utc else None


def measurement(records):
    starts = [r for r in records if r['event'] == 'start']
    ends = [r for r in records if r['event'] in ('finish', 'error', 'timeout')]
    sample = records[0]
    result = {k: sample[k] for k in ('scope', 'scope_id', 'span_id', 'parent_span_id', 'stage')}
    result.update(utc=sample['utc'], inclusive_ms=None, exclusive_ms=None, outcome='incomplete', incomplete=True)
    if len(starts) != 1 or len(ends) != 1 or len({r['stage'] for r in records}) != 1:
        return result
    a, b = starts[0], ends[0]
    start, end = seconds(a['utc']), seconds(b['utc'])
    valid = (a['scope_id'] is not None and a['clock_id'] is not None and a['clock_id'] == b['clock_id']
             and not any(r['clock_reset'] for r in records) and start is not None and end is not None
             and end >= start and b['elapsed_ms'] is not None
             and abs((end-start)*1000-b['elapsed_ms']) <= 1)
    result.update(outcome=b['event'], utc=a['utc'])
    if valid:
        result.update(inclusive_ms=b['elapsed_ms'], incomplete=False, _start=start, _end=end, _clock=a['clock_id'])
    return result


def build_report(records):
    groups = defaultdict(list)
    for r in records:
        groups[r['request_id']].append(r)
    requests = []
    for request, rows in groups.items():
        spans = defaultdict(list)
        queue = []
        for i, r in enumerate(rows):
            if r['stage'] == 'queue_wait':
                queue.append(r)
            else:
                # Missing scope identity is never merged, including colliding legacy spans.
                key = (r['scope'], r['scope_id'] or ('ambiguous', i), r['span_id'], r['stage'] if r['span_id'] is None else None)
                spans[key].append(r)
        stages = [measurement(v) for v in spans.values() if v[0]['event'] not in ('summary', 'first_event', 'first_text') or any(r['event'] in ('start','finish','error','timeout') for r in v)]
        if queue:
            # Queue is the one intentional cross-scope interval: submission -> processing.
            starts = [r for r in queue if r['event']=='start']
            ends = [r for r in queue if r['event']=='finish']
            if len(starts)==len(ends)==1:
                qrows = [dict(r, scope_id=ends[0]['scope_id']) for r in (starts[0], ends[0])]
                q = measurement(qrows)
            else:
                q = measurement(queue)
            stages.append(q)
        for s in stages:
            children = [c for c in stages if c['scope_id'] == s['scope_id'] and c['scope'] == s['scope'] and c['parent_span_id'] == s['span_id'] and s['span_id'] is not None]
            if s['incomplete'] or any(c['incomplete'] or c.get('_clock') != s.get('_clock') or c['_start'] < s['_start'] or c['_end'] > s['_end'] for c in children):
                continue
            intervals = sorted((c['_start'], c['_end']) for c in children)
            union = 0; end = None
            for a, b in intervals:
                union += max(0, b-max(a, end if end is not None else a)); end = max(b, end if end is not None else b)
            # UTC intervals are accepted only when consistent with monotonic duration.
            s['exclusive_ms'] = max(0, s['inclusive_ms']-union*1000) if s['stage'] != 'begin' else None
        stages.sort(key=lambda s: s['utc'] or '')
        calls = [s for s in stages if s['stage']=='provider_request']
        for n, s in enumerate(calls, 1): s['model_call'] = n
        processing = [s for s in stages if s['scope']=='processing' and s['stage']=='begin']
        queue_stages = [s for s in stages if s['stage']=='queue_wait']
        p = processing[0] if len(processing)==1 else None
        q = queue_stages[0] if len(queue_stages)==1 else None
        total = None
        if p and q and not p['incomplete'] and not q['incomplete'] and p['_clock']==q['_clock'] and q['_end'] <= p['_start']:
            total = p['inclusive_ms'] + q['inclusive_ms']
        failures = [s['stage'] for s in stages if s['outcome'] in ('error','timeout')]
        requests.append(dict(request_id=request, job_id=next((r['job_id'] for r in rows if r['job_id']), None),
            channel=rows[-1]['channel'], utc=min((r['utc'] for r in rows if r['utc']), default=None),
            outcome=p['outcome'] if p else 'incomplete', incomplete=any(s['incomplete'] for s in stages) or not p,
            ambiguous=any(not r['scope_id'] for r in rows), queue_ms=q['inclusive_ms'] if q else None,
            processing_ms=p['inclusive_ms'] if p else None, total_ms=total,
            model_calls=len(calls), delivery_attempts=len({r['scope_id'] for r in rows if r['scope']=='delivery' and r['scope_id']}),
            failure_stages=list(dict.fromkeys(failures)),
            slowest=[s['stage'] for s in sorted(stages, key=lambda s:s['inclusive_ms'] or -1, reverse=True) if s['stage'] not in ('begin','queue_wait')][:3],
            stages=[{k:v for k,v in s.items() if not k.startswith('_')} for s in stages]))
    return sorted(requests, key=lambda r:r['utc'] or '', reverse=True)[:50]


def read_report(directory=None):
    directory = Path(directory) if directory is not None else Path(os.getenv('DATA_DIR', str(Path(__file__).parent/'data'))) / 'logs'
    paths = [directory / ('profiling.jsonl'+suffix) for suffix in ('.3','.2','.1','')]
    # Optional local-only legacy files, explicitly selected by the operator.
    legacy = os.getenv('K90_PROFILE_LEGACY_FILES', '').split(os.pathsep)[:2]
    paths += [Path(p) for p in legacy if p]
    records = deque(maxlen=MAX_RECORDS); skipped = 0; bounded = False; errors = 0
    for index, path in enumerate(paths):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    errors += 1; continue
                if info.st_size > MAX_BYTES:
                    stream.seek(info.st_size-MAX_BYTES); stream.readline(MAX_LINE); bounded = True
                consumed = 0
                while consumed < MAX_BYTES:
                    line = stream.readline(min(MAX_LINE+1, MAX_BYTES-consumed)); consumed += len(line)
                    if not line: break
                    if len(line)>MAX_LINE or not line.endswith(b'\n'):
                        skipped += 1
                        # Never interpret the tail of an overlong/truncated line.
                        if not line.endswith(b'\n'):
                            while consumed < MAX_BYTES:
                                tail = stream.readline(min(MAX_LINE, MAX_BYTES-consumed)); consumed += len(tail)
                                if not tail or tail.endswith(b'\n'): break
                        continue
                    try:
                        text = line.decode('utf-8')
                        if index >= 4:
                            if 'agent.phase' not in text or 'profile=' not in text: continue
                            raw = ast.literal_eval(text.split('profile=',1)[1].strip())
                        else: raw = json.loads(text)
                        r = clean(raw, index>=4)
                        if r:
                            if len(records) == MAX_RECORDS: bounded = True
                            records.append(r)
                        else: skipped += 1
                    except (ValueError, SyntaxError, TypeError, RecursionError): skipped += 1
        except FileNotFoundError: pass
        except OSError: errors += 1
    return dict(enabled=os.getenv('K90_PROFILING_ENABLED','false')=='true', requests=build_report(records),
                skipped=skipped, bounded=bounded, read_errors=errors)
