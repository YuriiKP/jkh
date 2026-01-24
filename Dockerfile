FROM pasarguard/panel:latest

RUN pip install --no-cache-dir pymysql==1.1.2

# Устанавливаем утилиты для установки xray-core
ARG XRAY_VERSION

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        unzip \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Копируем и запускаем скрипт установки xray-core
COPY install-xray.sh /usr/local/bin/install-xray.sh
RUN chmod +x /usr/local/bin/install-xray.sh && \
    /usr/local/bin/install-xray.sh

# Копируем папку с шаблонами
# COPY templates/ /var/lib/pasarguard/templates/

###
# Копируем xray_config.json времено в /usr/share/pasarguard/default_xray_config.json 
# Затем запускаем скрипт для переноса конфига в volume /var/lib/pasarguard, если его ещё там нет
###
# COPY xray_config.json /usr/share/pasarguard/default_xray_config.json    ##
# COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh           ## Пока вырубаем 
# RUN chmod +x /usr/local/bin/docker-entrypoint.sh                        ##

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]



CMD ["bash", "-c", "alembic upgrade head; python main.py"]
# COPY main_custom.py /code/main_custom.py
# CMD ["bash", "-c", "alembic upgrade head; python main_custom.py"]