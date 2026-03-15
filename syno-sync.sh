#!/usr/bin/env bash
# Synchronizacja danych między lokalnym środowiskiem a Synology.
#
# Użycie:
#   ./syno-sync.sh push   — wyślij dane + config na Synology
#   ./syno-sync.sh pull   — pobierz dane z Synology (przed lokalnymi testami)

set -e
SYNOLOGY_HOST=$(grep '^SYNOLOGY_HOST=' .env | cut -d= -f2)
SYNOLOGY_USER=$(grep '^SYNOLOGY_USER=' .env | cut -d= -f2)
SYNOLOGY_PATH=$(grep '^SYNOLOGY_PATH=' .env | cut -d= -f2)

HOST="${SYNOLOGY_USER}@${SYNOLOGY_HOST}"
REMOTE="${SYNOLOGY_PATH}"

case "$1" in
  push)
    if [ ! -f .env.synology ]; then
      echo "WARN: .env.synology not found — aborting."
      exit 1
    fi

    echo "==> [PUSH] data/"
    rsync -avz --progress ./data/ "${HOST}:${REMOTE}/data/"

    echo "==> [PUSH] docker-compose.yml"
    rsync -avz docker-compose.yml "${HOST}:${REMOTE}/"

    echo "==> [PUSH] .env"
    rsync -avz .env.synology "${HOST}:${REMOTE}/.env"

    echo ""
    echo "Done. Start agent on Synology:"
    echo "  ssh -p 2222 ${HOST} 'cd ${REMOTE} && docker compose up -d'"
    ;;

  pull)
    echo "==> [PULL] data/"
    rsync -avz --progress "${HOST}:${REMOTE}/data/" ./data/
    echo ""
    echo "Done. You can now start the agent locally."
    ;;

  *)
    echo "Usage: $0 push|pull"
    exit 1
    ;;
esac
