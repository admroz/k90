"""Real Docker ignore semantics, using only a disposable synthetic context."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid


PRIVATE_PATHS = tuple(
    prefix + name
    for prefix in ('', 'tools/', 'tools/nested/')
    for name in ('.env', '.env.private', 'credentials.json', 'chatgpt-auth/session.json')
)


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'k90:test'
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@-]*', base):
        raise ValueError('Expected a local image reference')
    image = 'k90-context-smoke:' + uuid.uuid4().hex
    root = Path(__file__).resolve().parents[1]
    # No owner files are copied. Use the real ignore file against fake secrets.
    with tempfile.TemporaryDirectory(prefix='k90-build-context-') as directory:
        context = Path(directory)
        (context / '.dockerignore').write_text((root / '.dockerignore').read_text())
        (context / 'Dockerfile').write_text(f'FROM {base}\nCOPY . /build-context/\n')
        for name in PRIVATE_PATHS:
            path = context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic-private-marker\n')
        (context / 'public-marker.txt').write_text('public\n')
        check = (
            'from pathlib import Path; root=Path("/build-context"); '
            'assert (root/"public-marker.txt").read_text()=="public\\n"; '
            f'assert not [p for p in {json.dumps(PRIVATE_PATHS)} if (root/p).exists()]; '
            'print("Build-context secret exclusions PASS at root and two nested depths")'
        )
        try:
            subprocess.run(['docker', 'build', '--network', 'none', '--pull=false',
                            '-t', image, str(context)], check=True, timeout=120)
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint',
                            'python', image, '-c', check], check=True, timeout=30)
        finally:
            subprocess.run(['docker', 'image', 'rm', '-f', image], check=False, timeout=30)


if __name__ == '__main__':
    main()
