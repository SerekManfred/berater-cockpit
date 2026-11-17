# Word → PDF für die Vorschau im Schnellweg INIT (Phase 2h). Nur im internen Netz, ohne Port und ohne Internet.
# Schriften: Liberation Sans ist maßgleich zu Arial (Schrift der Berichte); fontconfig ordnet Arial → Liberation Sans zu.
FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 HOME=/tmp PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-liberation fonts-liberation2 fontconfig python3 \
 && rm -rf /var/lib/apt/lists/* \
 && fc-cache -f \
 && fc-match Arial | grep -q "Liberation Sans" \
 && useradd --system --uid 10001 --home-dir /tmp pdf
COPY server.py /srv/server.py
COPY test_server.py /srv/test_server.py
RUN python3 /srv/test_server.py
USER pdf
EXPOSE 3100
CMD ["python3", "/srv/server.py"]
