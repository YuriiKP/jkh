#!/usr/bin/env bash
# Дамп всех баз MySQL одним файлом для переноса на другой сервер.
# Запускать на старом сервере: bash /home/backup.sh
set -euo pipefail
cd "$(dirname "$0")"

MYSQL_CONTAINER=${MYSQL_CONTAINER:-mysql}
DUMP="jkh-backup-$(date +%Y%m%d-%H%M%S).sql.gz"
trap 'rm -f "$DUMP"' ERR

die() { echo "❌ $*" >&2; exit 1; }
running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" = true ]; }

command -v docker >/dev/null || die "docker не найден"
running "$MYSQL_CONTAINER" || die "контейнер $MYSQL_CONTAINER не запущен (docker compose up -d mysql)"

# Пароль root берём из окружения контейнера, чтобы не разбирать .env и не светить его в ps
ROOT_PW=$(docker exec "$MYSQL_CONTAINER" printenv MYSQL_ROOT_PASSWORD) \
  || die "не удалось прочитать MYSQL_ROOT_PASSWORD из контейнера $MYSQL_CONTAINER"

# Все пользовательские базы сразу — восстанавливаются одной командой за один проход.
# Пользователей и гранты на новом сервере создаёт сам mysql-контейнер из .env и init.sql
DBS=$(docker exec -e MYSQL_PWD="$ROOT_PW" "$MYSQL_CONTAINER" mysql -uroot -N -e \
  "SELECT schema_name FROM information_schema.schemata
   WHERE schema_name NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY 1")
[ -n "$DBS" ] || die "в MySQL нет пользовательских баз"

echo "🗄️  Дамп баз: $(echo $DBS)"
# --single-transaction: согласованный снимок InnoDB без остановки сервисов
docker exec -e MYSQL_PWD="$ROOT_PW" "$MYSQL_CONTAINER" mysqldump -uroot \
  --databases $DBS \
  --single-transaction --quick --routines --triggers --events \
  --hex-blob --default-character-set=utf8mb4 --set-gtid-purged=OFF --no-tablespaces \
  | gzip -9 > "$DUMP"
gzip -t "$DUMP" || { rm -f "$DUMP"; die "дамп не читается — повторите"; }

echo ""
echo "✅ Готово: $(pwd)/$DUMP ($(du -h "$DUMP" | cut -f1))"
echo "   базы в дампе: $(echo $DBS)"
echo ""
echo "Перенос:   scp \"$(pwd)/$DUMP\" root@НОВЫЙ_СЕРВЕР:/home/"
echo "На новом:  sudo bash /home/restore.sh /home/$DUMP"
