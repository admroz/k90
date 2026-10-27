"""Safe diagnostics before real fetcher boundaries reduce errors to strings."""
import json

import pytest
import requests


@pytest.mark.parametrize('source', ['libre', 'garmin'])
@pytest.mark.parametrize('timing', ['false', 'true'])
def test_client_http_failure_keeps_metadata_and_result(temp_db, tmp_path, monkeypatch, capfd, source, timing):
    import fetch_garmin
    import fetch_libre
    import profiling
    import tools.garmin as garmin
    import tools.libre as libre

    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_SYNC_ENABLED', 'true')
    monkeypatch.setenv('K90_PROFILING_ENABLED', timing)
    response = requests.Response()
    response.status_code = 503
    response.url = 'https://CANARY_FETCH_PRIVATE.invalid'
    failure = requests.HTTPError('CANARY_FETCH_PRIVATE token base64 body', response=response)

    class Client:
        def get_raw_graph_readings(self):
            raise failure

        def get_stats(self, day):
            raise failure

    if source == 'libre':
        monkeypatch.setattr(libre, 'is_enabled', lambda: True)
        monkeypatch.setattr(fetch_libre, 'USERNAME', 'fixture-user')
        monkeypatch.setattr(fetch_libre, 'PASSWORD', 'fixture-password')
        monkeypatch.setattr(fetch_libre, 'DB_PATH', str(temp_db))
        monkeypatch.setattr(fetch_libre, 'login', Client)
        sync = libre.sync_libre_data
    else:
        monkeypatch.setattr(fetch_garmin, 'EMAIL', 'fixture@example.invalid')
        monkeypatch.setattr(fetch_garmin, 'PASSWORD', 'fixture-password')
        monkeypatch.setattr(fetch_garmin, 'login', Client)
        monkeypatch.setattr(fetch_garmin, '_default_end_date', lambda: '2022-01-01')
        # Reach the real calorie client path without fetching unrelated datasets.
        for name in ('fetch_weight', 'fetch_blood_pressure', 'fetch_activities',
                     'fetch_sleep', 'fetch_daily_metrics', 'fetch_hrv', 'fetch_body_battery'):
            monkeypatch.setattr(fetch_garmin, name, lambda *args: [])
        sync = garmin.sync_garmin_data

    with profiling.request_scope('background', 'a'*32):
        assert sync() == {'error': str(failure)}
    rows = [json.loads(line) for line in (tmp_path/'logs/errors.log').read_text().splitlines()]
    row = next((r for r in rows if r['event'] == source+'.fetch_failed'), None)
    assert row is not None, 'diagnostics must be captured before the exception becomes a string'
    assert row['component'] == 'fetch_'+source and row['level'] == 'ERROR'
    assert row['http_status'] == 503 and row['exception_category'] == 'http'
    assert row['error_code'] == 'runtime_failure' and row['request_id'] == 'a'*32
    app = [json.loads(line) for line in (tmp_path/'logs/app.log').read_text().splitlines()]
    assert row in app
    content = ''.join(p.read_text() for p in (tmp_path/'logs').iterdir()) + capfd.readouterr().err
    assert 'CANARY_FETCH_PRIVATE' not in content and 'Traceback' not in content
