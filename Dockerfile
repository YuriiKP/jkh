FROM pasarguard/panel:latest

WORKDIR /code

# 2. asyncmy — Cython/C-расширение, поэтому нужен компилятор, затем убираем его
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && ./.venv/bin/python -m pip install --no-cache-dir asyncmy==0.2.11 \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. Прокидываем пути, чтобы команды alembic и python были доступны без полных путей
ENV PATH="/code/.venv/bin:$PATH"


# Копируем папку с шаблонами
COPY templates/ /var/lib/pasarguard/templates/

# Перезаписываем оригинальный share.py нашим патчем
COPY app/subscription/share.py /code/app/subscription/share.py


CMD ["bash", "-c", "alembic upgrade head && python main.py"]
