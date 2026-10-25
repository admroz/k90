"""Static COPY-manifest check, not a substitute for a Docker image build."""
from pathlib import Path
import shlex


def test_dockerfile_includes_new_runtime_modules():
    root=Path(__file__).resolve().parent.parent
    sources=[]
    for line in (root/'Dockerfile').read_text().splitlines():
        tokens=shlex.split(line)
        if tokens and tokens[0]=='COPY':
            sources.extend(tokens[1:-1])
    required={'patient_documents.py','memory_runtime.py','memory_admin.py','outbound_policy.py',
              'subscription_auth.py','subscription_protocol.py','subscription_api.py','subscription_login.py',
              'k90_memory/'}
    assert required<=set(sources), 'new runtime imports would be missing from the Docker image'
    assert all((root/path).exists() for path in required)
