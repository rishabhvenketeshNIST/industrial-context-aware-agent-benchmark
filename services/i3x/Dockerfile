# Private ICAB i3X server: CESMII's own OPC UA -> i3X reference wrapper
# (https://github.com/cesmii/OPCUA-i3X), built from a pinned commit so the
# image is reproducible even though upstream has not tagged a release yet.
#
# This wraps ICAB's own TEP-backed OPC UA server (services/opcua/, see
# icab.context.opcua.TEPOPCUAServer) rather than the public i3X conformance
# server -- see docs/architecture/i3x-private-server.md.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Pin the exact upstream commit for a reproducible build.
ARG OPCUA_I3X_COMMIT=7df7478bebfedc083b2244428ac9f75e83505166

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /src
RUN git clone https://github.com/cesmii/OPCUA-i3X.git . \
 && git checkout "${OPCUA_I3X_COMMIT}"

WORKDIR /app
RUN cp /src/pyproject.toml /src/uv.lock /src/README.md /src/LICENSE . \
 && cp -r /src/src ./src \
 && rm -rf /src

RUN uv sync --frozen --no-dev --no-install-project
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --home-dir /home/app --create-home app \
 && chown -R app:app /app /home/app
USER app

ENV UV_CACHE_DIR=/home/app/.cache/uv \
    UV_PROJECT_ENVIRONMENT=/app/.venv

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).status == 200 else 1)" \
  || exit 1

ENTRYPOINT ["uv", "run", "--no-dev", "--frozen", "i3xua"]
CMD ["--config", "/config/config.yaml"]
