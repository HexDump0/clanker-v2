FROM python:3.13-slim

WORKDIR /app

# Typst (PDF reports) + fonts for the report template
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils \
        fonts-noto-core fonts-liberation fonts-dejavu-core && \
    curl -fsSL https://github.com/typst/typst/releases/download/v0.15.0/typst-x86_64-unknown-linux-musl.tar.xz \
    | tar -xJ -C /tmp && \
    mv /tmp/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst && \
    rm -rf /tmp/typst-* && \
    apt-get purge -y curl xz-utils && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependencies first for layer caching (locked, no dev group)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# Watcher state + generated PDFs persist here (mount a volume)
RUN mkdir -p /app/data/pdfs

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "--no-sync", "clanker", "run"]
