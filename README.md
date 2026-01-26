# Создание базы данных для бота
Для бота нужно создать базу данных и выдать права 
`docker exec -it mysql mysql -u root -p`
`CREATE DATABASE IF NOT EXISTS telegram_db;`

# Создаем нового пользователя
`CREATE USER 'telegram_user'@'%' IDENTIFIED BY 'ваш_пароль';`

# Выдаем права на базу telegram
`GRANT ALL PRIVILEGES ON telegram_user.* TO 'telegram_db'@'%';`

# Применяем изменения
`FLUSH PRIVILEGES;`

# Выход
`EXIT`



# Генерация пары ключей (Private + Public)
`docker exec -it pasarguard xray x25519`

# Генерация ShortId
`docker exec -it pasarguard openssl rand -hex 4`


# Создание сертификата узла
`sudo certbot certonly --standalone -d example.com \
--deploy-hook "mkdir -p /var/lib/pg-node/certs && \
cp /etc/letsencrypt/live/example.com/fullchain.pem /var/lib/pg-node/certs/fullchain.pem && \
cp /etc/letsencrypt/live/example.com/privkey.pem /var/lib/pg-node/certs/privkey.pem && \
chmod 644 /var/lib/pg-node/certs/fullchain.pem && \
chmod 600 /var/lib/pg-node/certs/privkey.pem"`