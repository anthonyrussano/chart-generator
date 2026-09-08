# syntax=docker/dockerfile:1.7
#
# The reproducible execution environment for chart-gen.
#
# Deliberately small: the chart renderer is pure Python and writes SVG itself,
# so the only native dependency is librsvg, and only for PNG export. Nothing
# here needs a browser, a headless Chromium, or a JavaScript toolchain.

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.29

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="chart-gen"
LABEL org.opencontainers.image.description="Deterministic chart generation toolchain for agents"

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_CERTS=true \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        fontconfig \
        fonts-dejavu-core \
        librsvg2-bin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer first, so source edits do not invalidate the install.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=secret,id=ca-bundle \
    if [ -f /run/secrets/ca-bundle ]; then \
        export SSL_CERT_FILE=/run/secrets/ca-bundle; \
    fi; \
    uv sync --frozen --extra dev

# The workspace is mounted at runtime; outputs land there, not in the image.
WORKDIR /workspace

ENTRYPOINT ["chart-gen"]
CMD ["--help"]
