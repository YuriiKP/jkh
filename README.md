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
`docker exec -it marzban xray x25519`

# Генерация ShortId
`docker exec -it marzban openssl rand -hex 4`