FROM python:3.12-slim AS base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS app

COPY agent.py server.py system_prompt.py system_prompt.md summary.py fetch_garmin.py fetch_libre.py migrate_csv_to_sqlite.py ./
COPY tools/ ./tools/

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/k90.db
ENV DATA_DIR=/data

CMD ["python", "server.py"]
