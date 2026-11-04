# AGENTS.md — Architectural & Engineering Standards for mipiaceunBOT.TN

This document defines mandatory engineering, security, and deployment standards for agents working on **mipiaceunBOT.TN**.

---

## 1. Architecture & Directory Structure

- **`source/main.py`**: Entrypoint. Starts the Render HTTP health-check server (when `PORT` is set), initializes SQLite tables via `init_db()` on `bot.loop`, and runs the Pyrogram client.
- **`source/config.py`**: Central configuration, environment variable validation, Pyrogram 64-bit channel ID patch (`pyrogram.utils.MIN_CHANNEL_ID = -1009999999999`), and `Client` initialization.
- **`source/core/`**:
  - `session_manager.py`: `UserSession` dataclass and `SessionManager` (Redis primary store with automatic in-memory TTL fallback and daily rate-limiting counters).
  - `ui_components.py`: Reusable `InlineKeyboardMarkup` builders.
- **`source/database/`**:
  - `models.py`: SQLAlchemy 2.0 declarative models (`Report` with 64-bit `BigInteger` user IDs).
  - `repository.py`: Async SQLAlchemy engine (`sqlite+aiosqlite`), `init_db()`, and `ReportRepository`.
- **`source/middleware/permissions.py`**: `@require_group_member` decorator with `TTLCache`.
- **`source/modules/`**:
  - `core/`: `/start` command handler and inline callback dispatcher (`buttons.py`).
  - `permissions/`: Group member verification (`user_permissions.py`) and forum topic moderation (`topic_permissions.py`).
  - `user_announcements_interactions/`: Multi-step wizard for creating, previewing, publishing, and deleting community announcements (`announcement_handler.py`).
  - `reports/`: User reporting flow, auto-ban threshold logic, admin moderation commands, and GDPR `/my_data` & `/erase_my_data` handlers (`report_user.py`).
- **`source/services/`**: `MessageService` (with `tenacity` retry/FloodWait handling) and `ValidationService`.

---

## 2. Critical Technical Invariants (MUST NEVER BE VIOLATED)

1. **Pyrogram 64-Bit Channel IDs**:
   - Pyrogram 2.0.106 hardcodes `MIN_CHANNEL_ID = -1002147483647` (32-bit limit). Modern Telegram supergroups have 64-bit IDs (e.g., `-1002461409137`).
   - `pyrogram.utils.MIN_CHANNEL_ID = -1009999999999` MUST remain patched in `source/config.py` before any peer resolution occurs.

2. **SQLAlchemy Asyncio & `greenlet`**:
   - `sqlalchemy.ext.asyncio` requires `greenlet` (a native C++ extension).
   - `requirements.txt` MUST always declare `sqlalchemy[asyncio]>=2.0.0` and `greenlet>=3.0.0`.
   - `Dockerfile` MUST use `python:3.12-slim` (glibc) with a build-time smoke test (`python -c "import pyrogram, tgcrypto, sqlalchemy.ext.asyncio, greenlet, aiosqlite, redis"`). Avoid bare Alpine images without `g++` and `libstdc++`.

3. **Session Schema Consistency (`UserSession`)**:
   - Both `announcement_sessions` and `report_sessions` serialize/deserialize through `UserSession` in `source/core/session_manager.py`.
   - Any new session key added to either flow MUST be declared as a field on `UserSession`. Never pass undeclared keys to `create_session()` or `update_session()`.

4. **Redis Resilience (Zero-Crash Guarantee)**:
   - `SessionManager` MUST catch `(RedisError, OSError)` on all Redis operations and transparently fall back to its in-memory TTL store so the bot never crashes if Redis is unconfigured or temporarily unreachable.

5. **Async Concurrency & Non-Blocking Execution**:
   - Never use synchronous blocking calls (`time.sleep`, `requests`, synchronous `sqlite3`) inside async handlers. Always use `asyncio.sleep` and `aiosqlite`.
   - Protect multi-message handlers (such as `media_group` photo uploads in `collect_data_handler`) with per-user `asyncio.Lock` to prevent race conditions on session state.

6. **Security, GDPR & Git Hygiene**:
   - Never hardcode secrets (`API_ID`, `API_HASH`, `BOT_TOKEN`).
   - Never commit `*.env`, `*.session`, `*.db`, or `reports.json` to Git.
   - Always run `.agents/skills/pre_push_analysis/scripts/audit_codebase.py` after making code changes to verify zero undefined symbols, valid imports, and passing unit/smoke checks.
