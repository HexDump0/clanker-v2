FROM python:3.13-slim

WORKDIR /app

# Typst (PDF reports) + ffmpeg (review-video encoding) + fonts for the templates
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils \
        ffmpeg fonts-noto-core fonts-liberation fonts-dejavu-core && \
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

# Headless Chromium for demo page renders (review_render_page / packet pre-render)
RUN uv run --no-sync playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# Runtime state (watcher_state.json, chat_memory.json, generated PDFs/videos) lives
# here. Declaring it a volume keeps the data across container restarts; for durable
# persistence across redeploys, mount a named volume at /app/data (in Coolify: add a
# Persistent Storage entry with mount path /app/data).
RUN mkdir -p /app/data/pdfs
VOLUME ["/app/data"]

# The browser-extension API (EXTENSION_API_ENABLED=true) listens here; point your reverse proxy at it.
EXPOSE 8765

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "--no-sync", "clanker", "run"]
