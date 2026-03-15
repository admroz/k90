#!/usr/bin/env bash
# Synchronizacja danych między lokalnym środowiskiem a Synology.
#
# Użycie:
#   ./syno-sync.sh push   — zatrzymaj agenta na syno, wyślij dane + config
#   ./syno-sync.sh pull   — pobierz dane z syno (np. przed lokalnymi testami)

set -e
source .env

HOST="${SYNOLOGY_USER}@${SYNOLOGY_HOST}"
REMOTE="${SYNOLOGY_PATH}"

case "$1" in
  push)
    echo "==> [PUSH] Sending data/ to ${HOST}:${REMOTE}/data/"
    rsync -avz --progress --exclude='signal/' ./data/ "${HOST}:${REMOTE}/data/"

    echo ""
    if [ ! -f .env.synology ]; then
      echo "WARN: .env.synology not found — skipping .env upload."
      echo "      Create .env.synology with Synology-specific settings."
    else
      echo "==> Copying .env.synology as .env to ${HOST}:${REMOTE}/.env"
      scp .env.synology "${HOST}:${REMOTE}/.env"
    fi

    echo ""
    echo "==> Copying docker-compose.yml to ${HOST}:${REMOTE}/docker-compose.yml"
    scp docker-compose.yml "${HOST}:${REMOTE}/docker-compose.yml"

    echo ""
    echo "Done. Start agent on Synology:"
    echo "  ssh ${HOST} 'cd ${REMOTE} && docker compose up -d'"
    ;;

  pull)
    echo "==> [PULL] Fetching data/ from ${HOST}:${REMOTE}/data/"
    rsync -avz --progress --exclude='signal/' "${HOST}:${REMOTE}/data/" ./data/
    echo ""
    echo "Done. You can now start the agent locally."
    ;;

  *)
    echo "Usage: $0 push|pull"
    exit 1
    ;;
esac
