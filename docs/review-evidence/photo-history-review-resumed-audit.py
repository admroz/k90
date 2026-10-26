"""Read-only audit of reviewed Git source and actual independent test XML."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path('/opt/data/projects/k90-photo-history')
TASK = Path('/opt/data/jobs/k90-photo-history')
TESTED = 'b8091b7a03ac2de7010d7a1408eb44a3f09d24d9'
BASE = '17beba2353cbc1e1a2d39d71bc9b5a78f11a2ed4'
HEAD = '422ff9e56286e93699b268d849818f51099310bb'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)
def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert git('rev-parse', 'HEAD').strip() == HEAD
assert git('status', '--porcelain') == ''
post_tested = git('diff', '--name-only', TESTED, HEAD).splitlines()
assert all(p.startswith('docs/') for p in post_tested)
source_paths = [p for p in git('ls-files').splitlines() if not p.startswith('docs/')]
assert git('diff', TESTED, HEAD, '--', *source_paths) == ''
original = TASK / 'review-original-probes.py'
preserved = ROOT / 'docs/review-evidence/photo-history-original-reviewer-probes.py'
assert original.read_bytes() == preserved.read_bytes()
assert "result = agent.run_agent('Synthetic followup', 'reviewer')" in original.read_text()

def xml_report(name):
    suites = ET.parse(TASK / name).getroot()
    cases = suites.findall('.//testcase')
    counts = Counter()
    by_module = {}
    selected = []
    for c in cases:
        status = 'failed' if c.find('failure') is not None else 'error' if c.find('error') is not None else 'skipped' if c.find('skipped') is not None else 'passed'
        counts[status] += 1
        module = c.attrib['classname']
        by_module.setdefault(module, Counter())[status] += 1
        if 'real_agent_upload_then_text_followup' in c.attrib['name']:
            selected.append({'name': c.attrib['name'], 'status': status})
    assert counts['failed'] == counts['error'] == 0
    return {'cases': len(cases), 'counts': dict(counts), 'modules': by_module, 'actual_agent_matrix': selected}

# Read every changed documentation/evidence file, retaining historical logs
# verbatim on disk and printing their terminal outcome lines, not treating them
# as fresh test results.
doc_audit = []
for p in git('diff', '--name-only', BASE, HEAD).splitlines():
    if p.startswith('docs/') or p == 'README.md':
        path = ROOT / p
        text = path.read_text()
        doc_audit.append({'path': p, 'sha256': hash_file(path), 'lines': len(text.splitlines()),
            'historical_outcomes': [line for line in text.splitlines() if (' passed' in line or ' failed' in line or ' skipped' in line)][-3:]})
full = xml_report('review-resumed-full.xml')
assert full['counts'] == {'passed': 482, 'skipped': 1}
assert len(full['actual_agent_matrix']) == 12
probes = xml_report('review-resumed-probes-final.xml')
assert probes['counts'] == {'passed': 79}
print(json.dumps({'head': HEAD, 'tested_source': TESTED, 'base': BASE, 'clean_worktree': True,
    'source_equivalent_to_tested': True, 'post_tested_changes': post_tested,
    'original_probe_sha256': hash_file(original), 'original_probe_equals_committed_preserved_copy': True,
    'offline_guard_sha256': hash_file(Path('/opt/data/cache/scratch/k90-verification-20261025/sitecustomize.py')),
    'full': full, 'probes_final': probes, 'documentation_audit': doc_audit}, indent=2))
