#!/bin/bash
set -e # Останавливать скрипт при любой ошибке

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
  echo "Пожалуйста, запускайте скрипт от имени root или через sudo"
  exit 1
fi

echo "🚀 Начало настройки сервера для Pasargard Node..."

# # 1. Обновление системы и синхронизация времени
# echo "⏳ Обновление пакетов и синхронизация времени..."
# apt update && apt upgrade -y
# timedatectl set-ntp true

# 1. Обновление системы и синхронизация времени
echo " Обновление пакетов и синхронизация времени..."
export DEBIAN_FRONTEND=noninteractive
apt update
apt -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade -y
timedatectl set-ntp true

# 2. Смена порта SSH на 1122
echo "🔒 Смена порта SSH на 1122..."
# Заменяем Port 22 (или раскомментируем #Port 22) на Port 1122
sed -i 's/^#*Port .*/Port 1122/' /etc/ssh/sshd_config
# sed 's/#Port 22/Port 1122/' /etc/ssh/sshd_config
# Перезапускаем SSH (daemon-reload не нужен для простого изменения конфига sshd)
systemctl daemon-reload
systemctl restart ssh
echo "✅ Порт SSH изменен на 1122. НЕ ЗАКРЫВАЙТЕ текущую сессию, пока не проверите вход в новом окне!"

# 3. Настройка UFW и безопасное отключение пинга
echo "🛡️ Настройка UFW и защита от пинга..."
ufw --force enable
ufw allow 1122/tcp
ufw allow 443
ufw allow 80
ufw allow 8443
ufw allow 62050

# Безопасное отключение пинга (блокируем только echo-request и echo-reply, оставляем fragmentation-needed для PMTUD/Xray)
sed -i '/-A ufw-before-input -p icmp --icmp-type echo-request -j ACCEPT/c\-A ufw-before-input -p icmp --icmp-type echo-request -j DROP' /etc/ufw/before.rules
sed -i '/-A ufw-before-output -p icmp --icmp-type echo-reply -j ACCEPT/c\-A ufw-before-output -p icmp --icmp-type echo-reply -j DROP' /etc/ufw/before.rules

ufw reload
echo "✅ UFW настроен. Разрешен только порт 1122/tcp."

# # 4. Установка Fail2Ban (Защита от брутфорса)
# echo "👮 Установка Fail2Ban..."
# apt install -y fail2ban
# systemctl enable fail2ban
# systemctl start fail2ban
# echo "✅ Fail2Ban активирован."

# 5. Установка Docker (Официальный репозиторий)
sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc | cut -f1)

# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# # Добавляем текущего пользователя в группу docker (если скрипт запущен через sudo)
# if [ -n "$SUDO_USER" ]; then
#     usermod -aG docker $SUDO_USER
#     echo "✅ Пользователь $SUDO_USER добавлен в группу docker. Перезайдите в SSH, чтобы изменения вступили в силу."
# fi

# 6. Установка Certbot
echo "🔑 Установка Certbot..."
apt install -y certbot
echo "✅ Certbot установлен."


# 7 Установка ядра Xray
echo "🔧 Установка ядра Xray..."

apt install unzip

INSTALL_DIR="/home/xray_core"


# 8 BBR
cat >/etc/sysctl.d/99-remnawave-xhttp.conf <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.ipv4.ip_forward=1
fs.file-max=1048576
EOF
sysctl --system


# 9 swap 2G
swapoff -a && rm -f /swapfile && sed -i '/\/swapfile/d' /etc/fstab && fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >>/etc/fstab


#**********************************************
# 1. Определяем архитектуру процессора
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  XRAY_ARCH="linux-64" ;;
    aarch64) XRAY_ARCH="linux-arm64-v8a" ;;
    armv7l)  XRAY_ARCH="linux-arm32-v7a" ;;
    *) echo "Ошибка: Неподдерживаемая архитектура ($ARCH)."; exit 1 ;;
esac
echo "Обнаружена архитектура: $ARCH -> Будет скачана сборка: $XRAY_ARCH"

# 2. Получаем тег САМОЙ ПОСЛЕДНЕЙ версии (включая pre-release)
echo "Проверяем последнюю сборку на GitHub (включая pre-release)..."
# Запрашиваем список релизов и берем первый (самый свежий)
LATEST_VERSION=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases | grep 'tag_name' | head -n 1 | cut -d\" -f4)

if [ -z "$LATEST_VERSION" ]; then
    echo "Ошибка: Не удалось получить номер версии."
    exit 1
fi
echo "Целевая версия: $LATEST_VERSION"

# 3. Формируем ссылку и скачиваем архив
DOWNLOAD_URL="https://github.com/XTLS/Xray-core/releases/download/${LATEST_VERSION}/Xray-${XRAY_ARCH}.zip"
echo "Скачиваем: $DOWNLOAD_URL"
wget -q --show-progress "$DOWNLOAD_URL" -O xray.zip

# 4. Создаём целевой каталог и распаковываем архив
echo "Создаём каталог $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
echo "Распаковываем архив..."
unzip -o xray.zip -d "$INSTALL_DIR"

# 5. Делаем файл исполняемым и очищаем мусор
chmod +x "$INSTALL_DIR/xray"
rm -f xray.zip

echo "Готово! Файл xray успешно установлен в $INSTALL_DIR."
"$INSTALL_DIR/xray" version

echo "✅ Ядро Xray установлено."


# 8. Финальные инструкции
echo ""
echo "========================================================================="
echo "✅ НАСТРОЙКА СЕРВЕРА ЗАВЕРШЕНА УСПЕШНО!"
echo "========================================================================="
echo "⚠️  ВАЖНО: Для следующего подключения используйте порт 1122:"
echo "   ssh -p 1122 user@your_server_ip"
echo ""
echo "📝 СЛЕДУЮЩИЕ ШАГИ (выполните вручную):"
echo ""
echo "1. Получите SSL-сертификат для вашего домена (замените example.com):"
echo "   certbot certonly --standalone -d example.com"
echo ""
echo "2. Сгенерируйте уникальный ключ (UUID) для ноды Pasargard:"
UUID_VAL=$(uuidgen)
echo "   Ваш ключ ноды: $UUID_VAL"
echo "   (Скопируйте его и сохраните в настройках панели Pasargard)"
echo ""
echo "3. Не забудьте открыть порты для Xray (например, 443/tcp и 443/udp) в UFW,"
echo "   когда будете готовы запускать контейнеры:"
echo "   ufw allow 443/tcp && ufw allow 443/udp"
echo "========================================================================="
