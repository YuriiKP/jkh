#!/bin/bash
set -e

# ------------------------------------------------------------------
### Установка ядра xray ###
# ------------------------------------------------------------------
echo "Installing latest Xray-core..."

# Определяем архитектуру
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)
        XRAY_FILE="Xray-linux-64.zip"
        ;;
    aarch64|arm64)
        XRAY_FILE="Xray-linux-arm64-v8a.zip"
        ;;
    armv7l|armv6l)
        XRAY_FILE="Xray-linux-arm32-v7a.zip"
        ;;
    *)
        XRAY_FILE="Xray-linux-64.zip"
        ;;
esac

# Получаем последнюю версию
# XRAY_VERSION_TEST=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')

# if [ -z "$XRAY_VERSION" ]; then
#     echo "Error: Could not determine latest version"
#     exit 1
# fi

INSTALL_DIR="/var/lib/pasarguard"

echo "Latest version: $XRAY_VERSION"
echo "Installing to: $INSTALL_DIR"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Скачиваем и распаковываем
DOWNLOAD_URL="https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/${XRAY_FILE}"
wget -q "$DOWNLOAD_URL" -O xray.zip || curl -L -o xray.zip "$DOWNLOAD_URL"
unzip -o xray.zip
rm -f xray.zip
chmod +x xray

echo "Xray-core installed successfully to $INSTALL_DIR/xray"


# ------------------------------------------------------------------
# Установка конфига
# ------------------------------------------------------------------
# # Путь, куда нужно положить конфиг (рабочая папка pasarguard)
# TARGET_CONFIG="/var/lib/pasarguard/xray_config.json"
# # Путь, где лежит ваш заготовленный шаблон (внутри образа)
# SOURCE_CONFIG="/usr/share/pasarguard/default_xray_config.json"

# # Проверяем: если целевого файла нет, то копируем
# if [ ! -f "$TARGET_CONFIG" ]; then
#     echo "xray_config.json not found in $TARGET_CONFIG. Copying default..."
#     if [ -f "$SOURCE_CONFIG" ]; then
#         cp "$SOURCE_CONFIG" "$TARGET_CONFIG"
#     else
#         echo "Warning: Default config source not found at $SOURCE_CONFIG"
#     fi
# else
#     echo "xray_config.json already exists. Skipping copy."
# fi



# Передаем управление основной команде запуска pasarguard
exec "$@"