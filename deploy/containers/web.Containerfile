FROM docker.io/library/node:22.17.1-alpine AS builder

ARG VITE_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
ENV VITE_MAP_STYLE_URL=${VITE_MAP_STYLE_URL}

WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build \
    && test -f dist/index.html \
    && rm -rf dist/radar dist/status

FROM docker.io/library/nginx:1.28.0-alpine AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

RUN addgroup -g "${APP_GID}" -S radar \
    && adduser -S -D -H -u "${APP_UID}" -G radar radar \
    && rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /data \
    && chown "${APP_UID}:${APP_GID}" /data

COPY deploy/containers/nginx.conf /etc/nginx/nginx.conf
COPY deploy/containers/security-headers.conf /etc/nginx/security-headers.conf
COPY --from=builder /build/apps/web/dist/ /usr/share/nginx/html/

USER ${APP_UID}:${APP_GID}
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "-", "http://127.0.0.1:8080/healthz"]

ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
