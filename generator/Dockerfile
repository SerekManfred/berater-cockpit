FROM node:20-alpine
WORKDIR /srv
COPY package*.json ./
RUN npm install
COPY . .
# Tests beim Bauen: ein fehlerhafter Generator wird nicht ausgeliefert
RUN npm test && npm prune --omit=dev
USER node
EXPOSE 3000
CMD ["node", "src/server.js"]
