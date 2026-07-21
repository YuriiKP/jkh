root@legalchocolate:/home# vi xray_last_download.sh
#!/bin/bash

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

# 4. Распаковываем архив
echo "Распаковываем архив..."
unzip -o xray.zip

# 5. Делаем файл исполняемым и очищаем мусор
chmod +x xray
rm xray.zip geoip.dat geosite.dat

echo "Готово! Файл xray успешно скачан и распакован."
./xray version
