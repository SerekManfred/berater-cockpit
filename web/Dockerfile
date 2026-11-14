# Stufe 1: Oberfläche bauen
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
# Frontend-Tests (vitest) laufen beim Bauen – schlägt einer fehl, entsteht kein Image
RUN npm test
RUN npm run build

# Stufe 2: Caddy liefert die Oberfläche aus und leitet /api an das Backend weiter
FROM caddy:2-alpine
COPY web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
