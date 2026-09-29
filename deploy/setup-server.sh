#!/usr/bin/env sh
# HelpFlow on a fresh Ubuntu/Debian server, in one command from the repository root:
#   sh deploy/setup-server.sh helpflow.example.ru          # domain: HTTPS from Let's Encrypt
#   sh deploy/setup-server.sh 203.0.113.10                 # IP only: plain HTTP
#   sh deploy/setup-server.sh helpflow.example.ru --demo   # demo stand for the jury
# --demo adds demo accounts with the PUBLIC password DemoPass123 (including the support lead)
# and one-click logins: anyone with the address can sign in as admin. Only for a demo.
# Without --demo no accounts are created: set ADMIN_EMAIL and ADMIN_PASSWORD in .env.
# Safe to re-run: keeps the existing .env and database, rebuilds, re-seeds only what is missing.
set -eu

ADDRESS="${1:?Укажите домен или IP сервера: sh deploy/setup-server.sh helpflow.example.ru [--demo]}"
DEMO=false
[ "${2:-}" = "--demo" ] && DEMO=true
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "Устанавливаю Docker..."
  curl -fsSL https://get.docker.com | sh
fi

case "$ADDRESS" in
  *[a-zA-Z]*) SITE="$ADDRESS"; URL="https://$ADDRESS"; SECURE=true ;;
  *) SITE=":80"; URL="http://$ADDRESS"; SECURE=false ;;
esac

if [ ! -f .env ]; then
  DB_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
  cat > .env <<ENV
PUBLIC_URL=$URL
SITE_ADDRESS=$SITE
COOKIE_SECURE=$SECURE
AI_PROVIDER=rules
POSTGRES_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql+psycopg://helpflow:$DB_PASSWORD@db:5432/helpflow
ENV
  echo "Создан .env (пароль базы сгенерирован)."
fi
# The mode follows the latest run: --demo turns demo logins on, a run without it turns them off.
grep -v '^SHOW_DEMO_LOGINS=' .env > .env.tmp && mv .env.tmp .env
echo "SHOW_DEMO_LOGINS=$DEMO" >> .env

$COMPOSE up -d --build

printf "Жду API"
for _ in $(seq 1 60); do
  if $COMPOSE exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" >/dev/null 2>&1; then
    break
  fi
  printf "."; sleep 3
done
echo

if [ "$DEMO" = true ]; then
  $COMPOSE exec -T api python -m app.seed_demo
  echo
  echo "Готово: $URL"
  echo "ВНИМАНИЕ: демо-режим. Пароль всех аккаунтов DemoPass123 известен всем, включая руководителя."
  echo "Не храните здесь настоящие данные; после проверки: docker compose ... down -v"
else
  echo
  echo "Готово: $URL"
  echo "Демо-аккаунты не создавались. Первый руководитель: ADMIN_EMAIL и ADMIN_PASSWORD в .env, затем повторите запуск."
fi
