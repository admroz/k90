"""Static contract; real Compose validation is a separate integration gate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_passes_configuration_without_allowlist():
    text = (ROOT / 'docker-compose.yml').read_text()
    assert '    env_file:\n      - .env\n' in text
    environment = text.split('    environment:\n', 1)[1].split('    volumes:', 1)[0]
    keys = {line.strip().removeprefix('- ').split('=', 1)[0]
            for line in environment.splitlines() if line.strip()}
    assert keys == {'WEB_PASSWORD', 'DATA_DIR', 'DB_PATH', 'TZ'}
    assert 'WEB_PASSWORD=${WEB_PASSWORD:?' in environment
    assert 'TZ=${TZ:-${APP_TIMEZONE:-Europe/Warsaw}}' in environment
    assert '${DATA_PATH:-./data}:/data' in text.split('    volumes:', 1)[1]


def test_private_environment_variants_are_ignored():
    for name in ('.gitignore', '.dockerignore'):
        lines = (ROOT / name).read_text().splitlines()
        assert '.env' in lines
        assert '.env.*' in lines
        assert 'chatgpt-auth/' in lines
        assert 'credentials.json' in lines
    assert '!.env.example' in (ROOT / '.gitignore').read_text().splitlines()


def test_docker_excludes_private_files_at_arbitrary_depth():
    lines = (ROOT / '.dockerignore').read_text().splitlines()
    assert {'**/.env', '**/.env.*', '**/chatgpt-auth/', '**/credentials.json'} <= set(lines)
