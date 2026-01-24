#!/bin/bash
set -e

# Путь, куда нужно положить конфиг (рабочая папка pasarguard)
TARGET_CONFIG="/var/lib/pasarguard/xray_config.json"
# Путь, где лежит ваш заготовленный шаблон (внутри образа)
SOURCE_CONFIG="/usr/share/pasarguard/default_xray_config.json"

# Проверяем: если целевого файла нет, то копируем
if [ ! -f "$TARGET_CONFIG" ]; then
    echo "xray_config.json not found in $TARGET_CONFIG. Copying default..."
    if [ -f "$SOURCE_CONFIG" ]; then
        cp "$SOURCE_CONFIG" "$TARGET_CONFIG"
    else
        echo "Warning: Default config source not found at $SOURCE_CONFIG"
    fi
else
    echo "xray_config.json already exists. Skipping copy."
fi

# Передаем управление основной команде запуска pasarguard
exec "$@"