---
name: deployment-diagnostics
description: Diagnose and resolve deployment failures on Render (Web Service / Background Worker) and Docker Compose for the Pyrogram Telegram bot.
---

# Deployment Diagnostics & Troubleshooting Runbook

Use this skill when the user reports deployment errors, container crashes, Render timeouts, Redis connection failures, SQLite session errors, or Telegram peer resolution errors.

## Common Failure Modes & Solutions

### 1. `sqlite3.OperationalError: no such table: version` on Pyrogram Startup
- **Cause**: A 0-byte `job_board_bot.session` file was created (e.g., via `touch job_board_bot.session` in `Dockerfile` or on the host for a Docker bind mount). Pyrogram's `FileStorage.open()` checks `if not path.is_file(): self.create() else: self.update()`. Because the 0-byte file exists, Pyrogram skips `self.create()` and queries `SELECT number FROM version` on an empty database!
- **Fix**:
  - Never run `touch *.session` in `Dockerfile`.
  - Keep the `_safe_file_storage_update` patch in `source/config.py`, which catches `sqlite3.OperationalError` inside `FileStorage.update()` and automatically calls `self.create()` to initialize the SQLite schema in-place.

### 2. `ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed`
- **Cause**: `requirements.txt` specified `sqlalchemy` without `[asyncio]`/`greenlet`, or `Dockerfile` used `alpine` without `g++` and `libstdc++`.
- **Fix**:
  - Ensure `requirements.txt` includes `sqlalchemy[asyncio]>=2.0.0` and `greenlet>=3.0.0`.
  - Ensure `Dockerfile` uses `python:3.12-slim` and runs `python -c "import pyrogram, tgcrypto, sqlalchemy.ext.asyncio, greenlet, aiosqlite, redis"` during build.

### 3. `ValueError: Peer id invalid: -1002...` / `KeyError: 'ID not found: -1002...'`
- **Cause**: Pyrogram 2.0.106 hardcodes `MIN_CHANNEL_ID = -1002147483647` (32-bit). Modern 64-bit supergroups exceed this range and fail `utils.get_peer_type()` when the local SQLite session cache is empty.
- **Fix**:
  - Verify `pyrogram.utils.MIN_CHANNEL_ID = -1009999999999` is set in `source/config.py`.
  - Ensure the bot is a member and administrator of the target `CHAT_ID` supergroup.

### 4. `redis.exceptions.ConnectionError: Connect call failed ('127.0.0.1', 6379)`
- **Cause**: `REDIS_URL` is not configured in the cloud environment (defaulting to `localhost:6379`).
- **Fix**:
  - `SessionManager` in `source/core/session_manager.py` includes an automatic in-memory TTL fallback so the bot continues operating without crashing.
  - For distributed persistence on Render Free Tier, configure an Upstash Redis database and set `REDIS_URL=rediss://default:<password>@<endpoint>:6379` in Render Environment Variables.

### 5. `No open ports detected` / `Port scan timeout reached` on Render
- **Cause**: Render Free Tier only supports **Web Services**, which require an HTTP server listening on `0.0.0.0:$PORT`.
- **Fix**:
  - Verify `start_healthcheck_server()` is called before `bot.run()` in `source/main.py`.
