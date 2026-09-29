# Production web: the built React app behind Caddy, which also proxies the API.
FROM node:20-alpine AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
# A demo stand for the jury shows one-click demo logins; set to false for a real company.
ARG SHOW_DEMO_LOGINS=true
RUN VITE_SHOW_DEMO_LOGINS=$SHOW_DEMO_LOGINS npm run build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
