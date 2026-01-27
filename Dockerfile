FROM pasarguard/panel:latest

WORKDIR /code

# 2. Устанавливаем через python -m pip
RUN ./.venv/bin/python -m pip install --no-cache-dir aiomysql==0.3.2

# 3. Прокидываем пути, чтобы команды alembic и python были доступны без полных путей
ENV PATH="/code/.venv/bin:$PATH"


# Копируем папку с шаблонами
# COPY templates/ /var/lib/pasarguard/templates/


CMD ["bash", "-c", "alembic upgrade head && python main.py"]