#!/usr/bin/env bash
# Перенос на новый сервер: базы из дампа + сертификаты, которые уже выпустил местный Caddy.
# Порядок: один раз поднять стек (MySQL сделает init, Caddy выпустит сертификаты),
# остановить его, затем: sudo bash /home/restore.sh /home/jkh-backup-*.sql.gz
set -euo pipefail

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
MYSQL_CONTAINER=${MYSQL_CONTAINER:-mysql}
CADDY_CONTAINER=${CADDY_CONTAINER:-caddy}
CERTS_DIR=${CERTS_DIR:-/var/lib/pg-node/certs}
ARCHIVE=${1:-}
ASSUME_YES=${2:-}

die() { echo "❌ $*" >&2; exit 1; }

[ -n "$ARCHIVE" ] || ARCHIVE=$(ls -t "$SELF_DIR"/jkh-backup-*.sql.gz 2>/dev/null | head -n1 || true)
[ -n "$ARCHIVE" ] || die "использование: sudo bash restore.sh <дамп.sql.gz> [--yes]"
[ -f "$ARCHIVE" ] || die "файл не найден: $ARCHIVE"
ARCHIVE=$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")
[ "$EUID" -eq 0 ] || die "нужен root (пишем в $CERTS_DIR): sudo bash restore.sh $ARCHIVE"

# Проект с docker-compose.yaml ищем рядом и в типовых местах; можно задать руками
PROJECT_DIR=${PROJECT_DIR:-}
if [ -z "$PROJECT_DIR" ]; then
  for d in "$PWD" /home/jkh /home /root/jkh /root /opt/jkh; do
    [ -f "$d/docker-compose.yaml" ] && { PROJECT_DIR=$d; break; }
  done
fi
[ -n "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/docker-compose.yaml" ] \
  || die "не нашёл docker-compose.yaml — задайте PROJECT_DIR=/путь/к/проекту"
cd "$PROJECT_DIR"
[ -f .env ] || die "нет .env в $PROJECT_DIR — скопируйте со старого сервера и поправьте домен/пароли"

if [ "$ASSUME_YES" != "--yes" ]; then
  echo "⚠️  Базы MySQL в $PROJECT_DIR и $CERTS_DIR будут перезаписаны данными из $ARCHIVE."
  answer=""
  read -r -p "Продолжить? [y/N] " answer || true
  case "$answer" in y|Y|yes) ;; *) echo "Отменено."; exit 1 ;; esac
fi

# Приложение не должно писать в базы во время импорта
docker compose stop telegram pasarguard node caddy >/dev/null 2>&1 || true

echo "⏳ Запуск MySQL..."
docker compose up -d mysql
for _ in $(seq 1 120); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' "$MYSQL_CONTAINER" 2>/dev/null)" = healthy ]; then
    break
  fi
  sleep 2
done
[ "$(docker inspect -f '{{.State.Health.Status}}' "$MYSQL_CONTAINER" 2>/dev/null)" = healthy ] \
  || { docker compose logs --tail 50 mysql; die "MySQL не поднялся за 3 минуты"; }

ROOT_PW=$(docker exec "$MYSQL_CONTAINER" printenv MYSQL_ROOT_PASSWORD) \
  || die "не удалось прочитать MYSQL_ROOT_PASSWORD из контейнера"

# Имя базы в .env нового сервера должно совпадать с той, что в дампе (частая причина «пустой» панели)
dump_stream() { if [ "${ARCHIVE##*.}" = gz ]; then gzip -dc "$ARCHIVE"; else cat "$ARCHIVE"; fi; }
DB=$(sed -n 's/^MYSQL_DATABASE[[:space:]]*=[[:space:]]*//p' .env | head -n1 | tr -d '" ')
if [ -n "$DB" ] && ! grep -q "USE \`$DB\`" < <(dump_stream); then
  echo "⚠️  В .env MYSQL_DATABASE=$DB, но такой базы в дампе нет — панель поднимется с пустой базой."
fi

echo "📥 Импорт $ARCHIVE..."
if [ "${ARCHIVE##*.}" = gz ]; then
  gzip -dc "$ARCHIVE" | docker exec -i -e MYSQL_PWD="$ROOT_PW" "$MYSQL_CONTAINER" \
    mysql -uroot --default-character-set=utf8mb4
else
  docker exec -i -e MYSQL_PWD="$ROOT_PW" "$MYSQL_CONTAINER" \
    mysql -uroot --default-character-set=utf8mb4 < "$ARCHIVE"
fi

DOMAIN=$(sed -n 's/^PASARGUARD_BASE_URL[[:space:]]*=[[:space:]]*//p' .env | head -n1 \
  | sed 's/^"//; s/"$//; s|.*://||; s|[:/].*||')

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# Сертификаты берём из того, что Caddy уже выпустил; docker cp работает и с остановленным контейнером
certs_from_caddy() {
  rm -rf "$TMP/certificates"
  docker cp "$CADDY_CONTAINER:/data/caddy/certificates" "$TMP/" >/dev/null 2>&1 || return 1
  local d
  d=$(find "$TMP/certificates" -maxdepth 2 -type d -name "$DOMAIN" 2>/dev/null | head -n1)
  [ -n "$d" ] || d=$(dirname "$(find "$TMP/certificates" -maxdepth 3 -name fullchain.pem 2>/dev/null | head -n1)")
  [ -s "$d/fullchain.pem" ] && [ -s "$d/privkey.pem" ] || return 1
  echo "$d"
}

SRC=$(certs_from_caddy || true)
if [ -z "$SRC" ]; then
  echo "🔐 Caddy ещё не выпускал сертификат для $DOMAIN — запускаю его и жду до минуты..."
  docker compose up -d --no-deps caddy
  for _ in $(seq 1 30); do
    SRC=$(certs_from_caddy || true)
    if [ -n "$SRC" ]; then break; fi
    sleep 2
  done
fi

if [ -n "$SRC" ]; then
  install -d -m 700 "$CERTS_DIR"
  install -m 644 "$SRC/fullchain.pem" "$CERTS_DIR/fullchain.pem"
  install -m 600 "$SRC/privkey.pem" "$CERTS_DIR/privkey.pem"
  echo "🔐 Сертификаты $DOMAIN скопированы в $CERTS_DIR"
else
  echo "⚠️  Сертификат для $DOMAIN не найден. База уже восстановлена: поднимите стек один раз,"
  echo "    дождитесь выдачи сертификата и запустите restore.sh снова (повторный импорт безопасен)."
fi

echo "🚀 Запуск стека..."
docker compose up -d
docker compose ps

echo ""
echo "📊 Таблиц на базу после восстановления:"
docker exec -e MYSQL_PWD="$ROOT_PW" "$MYSQL_CONTAINER" mysql -uroot -N -e \
  "SELECT table_schema, COUNT(*) FROM information_schema.tables
   WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys')
   GROUP BY 1 ORDER BY 1"

echo ""
echo "✅ Готово. Проверьте: сайт панели, вход в /dashvrot/, бота в Telegram, подключение ноды."
