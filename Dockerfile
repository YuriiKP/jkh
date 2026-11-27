FROM pasarguard/panel:latest

WORKDIR /code

# Копируем папку с шаблонами.
# В docker-compose.yaml ./templates ещё и монтируется в /var/lib/pasarguard/templates:
# bind-mount /var/lib/pasarguard перекрывает этот слой, так что на сервере работают файлы из репозитория.
COPY templates/ /var/lib/pasarguard/templates/

# Перезаписываем оригинальный share.py нашим патчем
COPY app/subscription/share.py /code/app/subscription/share.py

# asyncmy больше не ставим вручную: панель (>= 5.4.0) уже содержит его в зависимостях.
# Запуск обеспечивает ENTRYPOINT образа (/code/start.sh):
# alembic upgrade head && python main.py
