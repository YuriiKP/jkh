CREATE DATABASE IF NOT EXISTS telegram_db;
CREATE USER 'telegram_user'@'%' IDENTIFIED BY 'Hj34gfjHgj9gloTwR34wcx';
GRANT ALL PRIVILEGES ON telegram_db.* TO 'telegram_user'@'%';