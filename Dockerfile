FROM python:3.12-slim AS base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS app

COPY agent.py server.py system_prompt.py system_prompt.md summary.py responses_api.py fetch_garmin.py fetch_libre.py migrate_csv_to_sqlite.py ./
COPY tools/ ./tools/
COPY patient_documents.py memory_runtime.py memory_admin.py outbound_policy.py subscription_auth.py subscription_protocol.py subscription_api.py subscription_login.py subscription_host.py ./
COPY k90_memory/ ./k90_memory/
COPY webapp.py web_data.py web_runtime.py telegram_adapter.py container_start.py supervisord.conf ./
COPY profiling.py ./
COPY web/ ./web/

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/k90.db
ENV DATA_DIR=/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" || exit 1
CMD ["python", "container_start.py"]
