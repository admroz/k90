import json
from pathlib import Path


def test_absent_report(tmp_path):
    from profile_report import read_report
    assert read_report(tmp_path)['requests'] == []

from datetime import datetime, timedelta, timezone
import pytest
from profile_report import clean, build_report

RID='a'*32
SID='b'*32
CLOCK='c'*32

def event(stage='begin', kind='start', t=0, elapsed=None, span=None, parent=None, scope='processing', sid=SID, clock=CLOCK, **extra):
    return dict(request_id=RID, scope=scope, scope_id=sid, clock_id=clock, channel='web', job_id=7,
                utc=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=t)).isoformat(),
                stage=stage, event=kind, elapsed_ms=elapsed, span_id=span, parent_span_id=parent, **extra)

def pair(stage, start, duration, **kwargs):
    return [event(stage,'start',start,**kwargs), event(stage,'finish',start+duration,duration,**kwargs)]

def report(rows):
    return build_report([clean(r) for r in rows])[0]

def test_nested_overlap_and_model_markers_delivery():
    rows=pair('begin',0,100)+pair('processing',0,100,span=1)
    rows+=pair('provider_request',10,60,span=2,parent=1)+pair('tool',40,50,span=3,parent=1)
    rows += [event('provider_request','first_text',20,10,span=2,parent=1), event('provider_request','first_event',15,5,span=2,parent=1)]
    for sid in ('d'*32,'e'*32): rows+=pair('begin',110,5,scope='delivery',sid=sid)+pair('transport_delivery',110,5,scope='delivery',sid=sid,span=1)
    r=report(rows)
    assert r['processing_ms']==100 and r['model_calls']==1 and r['delivery_attempts']==2
    assert next(s for s in r['stages'] if s['stage']=='processing')['exclusive_ms']==pytest.approx(20,abs=.001)
    assert len([s for s in r['stages'] if s['stage']=='provider_request'])==1

@pytest.mark.parametrize('change', ['missing_start','missing_end','reset','clock','backwards'])
def test_incomplete_clock(change):
    rows=pair('begin',0,100)
    if change=='missing_start': rows.pop(0)
    if change=='missing_end': rows.pop()
    if change=='reset': rows[1]['clock_reset']=True
    if change=='clock': rows[1]['clock_id']='d'*32
    if change=='backwards': rows[1]['utc']=event(t=-1)['utc']
    r=report(rows)
    assert r['incomplete'] and r['processing_ms'] is None and r['total_ms'] is None

def test_complete_disjoint_queue_and_missing_child():
    rows=pair('begin',100,100)+pair('processing',100,100,span=1)
    rows += [event('queue_wait','start',0,scope='submission',sid='d'*32),event('queue_wait','finish',100,100)]
    r=report(rows)
    assert r['total_ms']==200
    rows += [event('tool','start',110,span=2,parent=1)]
    r=report(rows)
    assert next(s for s in r['stages'] if s['stage']=='processing')['exclusive_ms'] is None
    rows[-2]['utc']=event(t=101)['utc']
    assert report(rows)['total_ms'] is None

def test_bounded_rotation_privacy_truncation_legacy(tmp_path,monkeypatch):
    import profile_report as mod
    monkeypatch.setattr(mod,'MAX_BYTES',4096)
    (tmp_path/'profiling.jsonl.1').write_text('x'*5000+'\n'+json.dumps(event())+'\n')
    (tmp_path/'profiling.jsonl').write_text(json.dumps(event(kind='finish',t=100,elapsed=100,secret='private meal <svg onload=alert(1)>'))+'\n'+ '{"broken":')
    result=mod.read_report(tmp_path)
    assert result['bounded'] and result['skipped']>=1
    assert 'private' not in json.dumps(result) and 'secret' not in json.dumps(result)
    legacy=tmp_path/'old.txt'
    rows=[dict(event(),scope_id=None),dict(event(kind='finish',t=100,elapsed=100),scope_id=None)]
    legacy.write_text(''.join('agent.phase profile='+repr(r)+'\n' for r in rows))
    monkeypatch.setenv('K90_PROFILE_LEGACY_FILES',str(legacy))
    result=mod.read_report(tmp_path)
    assert result['requests'][0]['ambiguous'] and result['requests'][0]['incomplete']
    assert result['requests'][0]['model_calls'] is None
    assert all(s['exclusive_ms'] is None for s in result['requests'][0]['stages'])

def test_fixed_50_and_identity():
    rows=[]
    for n in range(60):
        rows += [dict(r,request_id=f'{n:032x}') for r in pair('begin',n*100,50)]
    assert len(build_report([clean(r) for r in rows]))==50
    r=report(pair('begin',0,100)+pair('provider_request',0,60,span=1)+pair('provider_request',101,60,span=1,sid='d'*32))
    assert r['model_calls']==2

def test_container_copies_report():
    assert 'COPY profiling.py logging_setup.py profile_report.py ./' in Path('Dockerfile').read_text()


def test_only_fixed_rotations_no_symlink_and_record_cap(tmp_path,monkeypatch):
    import profile_report as mod
    monkeypatch.setattr(mod,'MAX_RECORDS',3)
    (tmp_path/'profiling.jsonl.4').write_text(json.dumps(event())+'\n')
    assert mod.read_report(tmp_path)['requests']==[]
    (tmp_path/'profiling.jsonl').write_text(''.join(json.dumps(event(span=n,stage='tool'))+'\n' for n in range(1,6)))
    r=mod.read_report(tmp_path)
    assert r['bounded'] and len(r['requests'][0]['stages'])==3
    (tmp_path/'profiling.jsonl.1').symlink_to(tmp_path/'profiling.jsonl')
    assert mod.read_report(tmp_path)['read_errors']==1
