# Создание базы данных для бота
Для бота нужно создать базу данных и выдать права 
`docker exec -it mysql mysql -u root -p`
`CREATE DATABASE IF NOT EXISTS telegram_db;`

# Создаем нового пользователя
`CREATE USER 'telegram_user'@'%' IDENTIFIED BY 'ваш_пароль';`

# Выдаем права на базу telegram
`GRANT ALL PRIVILEGES ON telegram_db.* TO 'telegram_user'@'%';`

# Применяем изменения
`FLUSH PRIVILEGES;`

# Выход
`EXIT`



# Генерация пары ключей (Private + Public)
`docker exec -it pasarguard xray x25519`

# Генерация ShortId
`openssl rand -hex 4`


# Установка certbot
`sudo apt-get install certbot -y`

# Создание сертификата узла
`sudo certbot certonly --standalone -d example.com \
--deploy-hook "mkdir -p /var/lib/pg-node/certs && \
cp /etc/letsencrypt/live/example.com/fullchain.pem /var/lib/pg-node/certs/fullchain.pem && \
cp /etc/letsencrypt/live/example.com/privkey.pem /var/lib/pg-node/certs/privkey.pem && \
chmod 644 /var/lib/pg-node/certs/fullchain.pem && \
chmod 600 /var/lib/pg-node/certs/privkey.pem" && \
docker restart node`

# Перенос бэкапа базы данных 
`docker exec mysql mysqldump -u root -p'ПАРОЛЬ' ИМЯ_БАЗЫ > backup.sql`
`docker exec mysql mysqldump -u root -p'ПАРОЛЬ' --all-databases > dump.sql`


`docker exec -i mysql mysql -u root -p'ПАРОЛЬ' ИМЯ_БАЗЫ < backup.sql`


## Telegram bot: webhook / long-polling

Бот умеет работать в двух режимах:

- **Webhook (aiohttp)**: если в `.env` задан `WEBHOOK_PATH`, бот поднимает `aiohttp`-сервер на `WEB_SERVER_HOST:WEB_SERVER_PORT` и вызывает `setWebhook` на URL `PASARGUARD_BASE_URL + WEBHOOK_PATH` с `WEBHOOK_SECRET`.
- **Long-polling**: если `WEBHOOK_PATH` не задан, бот стартует через `start_polling` (как раньше).

Переменные окружения:

- **WEB_SERVER_HOST**: хост для `aiohttp` (по умолчанию `0.0.0.0`)
- **WEB_SERVER_PORT**: порт для `aiohttp` (по умолчанию `8080`)
- **WEBHOOK_PATH**: путь вебхука (например, `/tg/webhook`)
- **WEBHOOK_SECRET**: `secret_token` для Telegram webhook