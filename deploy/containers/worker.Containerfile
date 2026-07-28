FROM docker.io/library/python:3.13.5-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /build
COPY apps/worker/requirements-prod.lock apps/worker/requirements-prod.lock
RUN python -m pip install \
      setuptools==83.0.0 \
      wheel==0.47.0 \
      packaging==26.2 \
      --requirement apps/worker/requirements-prod.lock

COPY apps/worker apps/worker
RUN python -m pip install \
      --no-deps \
      --no-build-isolation \
      apps/worker \
    && python -m pip uninstall --yes \
      pip \
      setuptools \
      wheel \
      packaging

FROM docker.io/library/python:3.13.5-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROJ_NETWORK=OFF

RUN groupadd --gid "${APP_GID}" radar \
    && useradd \
      --uid "${APP_UID}" \
      --gid "${APP_GID}" \
      --no-create-home \
      --shell /usr/sbin/nologin \
      radar \
    && install -d -o "${APP_UID}" -g "${APP_GID}" /app /data

COPY --from=builder /opt/venv /opt/venv
COPY config /app/config
COPY deploy/containers/worker-healthcheck.py /usr/local/bin/worker-healthcheck.py
RUN chmod 0555 /usr/local/bin/worker-healthcheck.py

WORKDIR /app
USER ${APP_UID}:${APP_GID}

HEALTHCHECK --interval=60s --timeout=5s --start-period=15m --retries=3 \
  CMD ["python", "/usr/local/bin/worker-healthcheck.py"]

ENTRYPOINT ["aemet-radar"]
CMD ["run", "--data-dir", "/data"]
