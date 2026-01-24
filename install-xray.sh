#!/bin/bash
set -e

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

INSTALL_DIR="/var/lib/marzban_xray"

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