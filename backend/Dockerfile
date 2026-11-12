FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Tests laufen beim Bauen (gegen eine Wegwerf-SQLite-Datenbank): Fehler werden gar nicht erst ausgeliefert
RUN python -m pytest -q -p no:cacheprovider && rm -rf /tmp/cockpit-test-*
# Datei-Volume: leeres Volume übernimmt beim ersten Einbinden Besitzer und Rechte dieses Ordners
RUN mkdir -p /daten && chown nobody:nogroup /daten && chmod 700 /daten
USER nobody
# Beim Start zuerst die Migrationen, dann die API
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
