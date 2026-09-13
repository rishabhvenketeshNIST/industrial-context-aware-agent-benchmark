# ICAB's own TEP-backed OPC UA server, containerized so the private i3X
# stack (services/i3x/) is fully reproducible via `docker compose up -d`
# without a manually-run host process. See scripts/run_tep_opcua_server.py
# and icab.context.opcua.TEPOPCUAServer.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY scripts ./scripts

RUN uv sync --frozen --no-dev

EXPOSE 4841

ENTRYPOINT ["uv", "run", "--no-dev", "--frozen", "python", "scripts/run_tep_opcua_server.py"]
CMD ["--endpoint", "opc.tcp://0.0.0.0:4841/icab/tep/", "--seed", "42", "--step-seconds", "2.0"]
