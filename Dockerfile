# ── Stage 1: builder ─────────────────────────────────────────────────────────
# Compile native C/C++ extensions (tgcrypto, greenlet, etc.) in an isolated
# builder stage so compiler toolchains do not bloat the runtime image.
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc6-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Fail build immediately if any critical C/C++ extension or async driver is missing
RUN python -c "import pyrogram, tgcrypto, sqlalchemy.ext.asyncio, greenlet, aiosqlite, redis"

# Create non-root user for security
RUN groupadd -r botgroup && useradd -r -g botgroup -m -d /app botuser

WORKDIR /app

# Copy application source with proper ownership
COPY --chown=botuser:botgroup . .

# Create backups directory and ensure /app is writable by botuser for SQLite & Pyrogram session creation
# NOTE: Never `touch job_board_bot.session` — a 0-byte file lacks SQLite tables (`version`)!
RUN mkdir -p /app/backups && \
    chown -R botuser:botgroup /app

USER botuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/source

CMD ["python", "source/main.py"]
