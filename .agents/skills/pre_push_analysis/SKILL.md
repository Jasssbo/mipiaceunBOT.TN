---
name: Pre-Push Whitehat Analysis
description: Performs a rigorous security, architectural, static AST, and runtime smoke-test analysis on the Pyrogram bot codebase before pushing to production.
---

# Pre-Push Whitehat Analysis & Automated Audit

You are acting as a Senior DevSecOps Engineer, Python Software Architect, and Pyrogram Expert. When asked to perform a pre-push analysis, audit the repository, or diagnose why the bot fails, follow this workflow.

## Step 1: Run the Automated Codebase Audit Script

Always execute the automated audit script first using the project's virtual environment:

```bash
./.venv/bin/python .agents/skills/pre_push_analysis/scripts/audit_codebase.py
```

The script automatically verifies:
1. **AST Undefined Name & Import Analysis**: Scans every `.py` file in `source/` to detect missing imports (e.g. `RED`, `YELLOW`, `GREEN`), calls to nonexistent functions (e.g. `create_timeout_task`), bare `except:` clauses, and blocking calls (`time.sleep`).
2. **Dependency & C-Extension Verification**: Checks `requirements.txt` and imports `pyrogram`, `tgcrypto`, `sqlalchemy.ext.asyncio`, `greenlet`, `aiosqlite`, and `redis`.
3. **Pyrogram 64-bit Peer ID Patch**: Verifies `pyrogram.utils.MIN_CHANNEL_ID` supports 64-bit supergroup IDs (`-1002461409137`).
4. **SessionManager & UserSession Integrity**: Tests round-trip serialization and Redis-to-memory fallback for both announcement and report flows (`reported_username`, `reported_user_id`, rate limiting).
5. **Async Database & Repository Smoke Test**: Tests `init_db()` and `ReportRepository` queries against an isolated in-memory SQLite database.
6. **Git & Docker Secret Hygiene**: Ensures `.env`, `.session`, and `.db` files are ignored by `.gitignore` and `.dockerignore` and not tracked in Git.

## Step 2: Manual Architectural & Security Review Checklist

1. **Whitehat Security & Leak Prevention (CRITICAL)**
   - **Secrets Management**: Ensure no API keys, Bot tokens, or credentials exist in source files.
   - **Callback Ownership Validation**: Verify callbacks like `delete_`, `confirm_`, and `cancel_` check `callback_query.from_user.id == owner_id`.
   - **Rate Limiting & Abuse**: Verify `FloodWait` handling, `MAX_REPORTS_PER_DAY`, and `MAX_ANNOUNCEMENTS_PER_DAY`.

2. **Data Structure & State Robustness**
   - **Session Schema**: Confirm every key read/written on `announcement_sessions` or `report_sessions` exists on the `UserSession` dataclass in `source/core/session_manager.py`.
   - **Concurrency**: Ensure per-user locks protect concurrent `media_group` updates.

3. **Deployment Readiness (Docker & Render)**
   - **Dockerfile**: Multi-stage `python:3.12-slim` with build-time import verification.
   - **Render Web Service Compatibility**: Background health-check HTTP server on `$PORT` in `source/main.py`.

## Output Format

Present findings in a structured Markdown report:
1. **🚨 CRITICAL SECURITY & RUNTIME RISKS**
2. **🏗️ ARCHITECTURE & STATE FLAWS**
3. **🧪 AUTOMATED AUDIT RESULTS**
4. **✅ ACTIONABLE FIXES APPLIED**
