"""Packaging contract: test source imports as well as the published image."""
import ast
from pathlib import Path
import shlex

from scripts.smoke_container import CHECK

ROOT = Path(__file__).resolve().parents[1]


def test_final_image_copies_every_subscription_runtime_module():
    copied = set()
    for line in (ROOT / 'Dockerfile').read_text().splitlines():
        parts = shlex.split(line)
        if parts and parts[0] == 'COPY':
            copied.update(parts[1:-1])
    required = {p.name for p in ROOT.glob('subscription_*.py')}
    assert required <= copied, f'Missing runtime modules in Dockerfile COPY: {sorted(required - copied)}'


def test_real_container_smoke_imports_subscription_and_summary_paths():
    tree = ast.parse(CHECK)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    required = {'subscription_login', 'subscription_host', 'summary'}
    assert required <= imports, f'Container smoke lacks runtime import checks: {sorted(required - imports)}'
