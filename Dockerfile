# ── Stage 1: builder ─────────────────────────────────────────────────────────
# Install C build tools and compile every dependency that has a native extension
# (tgcrypto, aiosqlite, etc.) here so the final image stays lean.
FROM python:3.12-alpine AS builder

# Build-time deps: gcc / musl-dev for C extensions, libffi for cryptography
RUN apk add --no-cache \
        gcc \
        musl-dev \
        libffi-dev \
        openssl-dev \
        python3-dev

WORKDIR /build

# Upgrade pip first, then install wheels into an isolated prefix
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-alpine

# Runtime-only C libs needed by installed packages (libffi, openssl)
RUN apk add --no-cache \
        libffi \
        openssl \
        tzdata

# Copy compiled site-packages from the builder stage
COPY --from=builder /install /usr/local

# Non-root user — Alpine uses adduser/addgroup, NOT useradd
RUN addgroup -S botgroup && adduser -S -G botgroup botuser

WORKDIR /app

# Copy application source (chown in same layer to save a layer)
COPY --chown=botuser:botgroup . .

# Pre-create the session file so Docker never turns it into a directory.
# If a volume-mounted file doesn't exist on the host, Docker creates a
# directory instead — which crashes Pyrogram on startup.
RUN touch job_board_bot.session && \
    chown botuser:botgroup job_board_bot.session

USER botuser

# Unbuffered output so logs are visible immediately in "docker logs"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "source/main.py"]
