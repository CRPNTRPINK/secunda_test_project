#!/usr/bin/env bash
set -euo pipefail

# Миграции накатывает api-сервис; consumer только ждёт готовности схемы.
echo "Starting consumer (payment processor + outbox relay)..."
exec python -m app.worker
