# Production web: the built React app behind Caddy, which also proxies the API.
FROM node:20-alpine AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
# One-click demo logins (known password) only for a demo stand: deploy/setup-server.sh --demo.
ARG SHOW_DEMO_LOGINS=false
RUN VITE_SHOW_DEMO_LOGINS=$SHOW_DEMO_LOGINS npm run build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
