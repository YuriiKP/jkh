FROM pasarguard/panel:latest

WORKDIR /code

# Копируем папку с шаблонами
COPY templates/ /var/lib/pasarguard/templates/

# Перезаписываем оригинальный share.py нашим патчем
COPY app/subscription/share.py /code/app/subscription/share.py

# asyncmy больше не ставим вручную: панель (>= 5.4.0) уже содержит его в зависимостях.
# Запуск обеспечивает ENTRYPOINT образа (/code/start.sh):
# alembic upgrade head && python main.py
