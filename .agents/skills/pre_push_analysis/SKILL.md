---
name: pre-push-whitehat-analysis
description: Performs a rigorous security, architectural, anti-AI-slop, Markdown prompt-injection sanitization, static AST, and runtime smoke-test analysis on the Pyrogram bot codebase before pushing to production.
---

# Pre-Push Whitehat, Anti-Slop & Markdown Security Analysis

You are acting as a Senior DevSecOps Engineer, Python Software Architect, and Pyrogram Expert. When asked to perform a pre-push analysis, audit the repository, sanitize `.md` files, or diagnose why the bot fails, follow this workflow.

## Step 1: Run the Automated Codebase & Markdown Security Audit Script

Always execute the automated audit script first using the project's virtual environment:

```bash
# Standard audit (fails with exit code 1 on any violation)
./.venv/bin/python .agents/skills/pre_push_analysis/scripts/audit_codebase.py

# Audit + automatic sanitization of invisible/steganographic Unicode in .md files
./.venv/bin/python .agents/skills/pre_push_analysis/scripts/audit_codebase.py --sanitize
```

The script automatically verifies 6 critical layers:
1. **Markdown Security & Prompt-Injection Sanitization**:
   - Scans every `.md` file in the repository (`AGENTS.md`, `README.md`, `TERMS_OF_SERVICE.md`, `.agents/**/*.md`) for:
     - Invisible/steganographic Unicode characters (Zero-Width joiners, Bidi overrides `U+202A`–`U+202E`, Unicode Tag block `U+E0000`–`U+E007F`).
     - Prompt-injection payloads hidden inside HTML comments (`<!-- ... -->`) or text (`ignore previous instructions`, `system override`, etc.).
     - Malicious shell execution traps (piping `curl`/`wget` or decoded `base64` payloads directly into `sh`/`bash`).
2. **Anti-AI-Slop & Cargo-Cult Pattern Detection**:
   - Detects AI slop such as `touch *.session` in `Dockerfile` (which causes `sqlite3.OperationalError: no such table: version`), placeholder comments (`# rest of code here`, `# as an ai`), and obsolete `reports.json` references in operational scripts.
3. **AST Static Analysis**:
   - Scans every `.py` file in `source/` to detect undefined names/missing imports (`NameError`), bare `except:` clauses, and blocking calls (`time.sleep`).
4. **Dependency & Native C/C++ Extension Verification**:
   - Checks `requirements.txt` and imports `pyrogram`, `tgcrypto`, `sqlalchemy.ext.asyncio`, `greenlet`, `aiosqlite`, and `redis`.
5. **Async Runtime Smoke Tests**:
   - Verifies Pyrogram 64-bit peer ID patch (`-1002461409137`).
   - Verifies Pyrogram `FileStorage` self-healing on a **0-byte `.session` file** (preventing `no such table: version`).
   - Verifies `SessionManager` & `UserSession` round-trip serialization + fallback.
   - Verifies `ReportRepository` async CRUD and GDPR erasure on an in-memory SQLite database.
6. **Git & Docker Secret Hygiene**:
   - Verifies `.gitignore` and `.dockerignore` protect `.env`, `.session`, and `.db` files.

## Step 2: Manual Architectural & Security Review Checklist

1. **Whitehat Security & Leak Prevention (CRITICAL)**
   - Ensure no secrets exist in source files.
   - Verify callback ownership checks (`callback_query.from_user.id == owner_id`).
   - Verify rate limiting (`FloodWait`, `MAX_REPORTS_PER_DAY`, `MAX_ANNOUNCEMENTS_PER_DAY`).

2. **Data Structure & State Robustness**
   - Confirm all session keys exist on `UserSession` in `source/core/session_manager.py`.
   - Confirm per-user `asyncio.Lock` protects concurrent `media_group` updates.

3. **Deployment Readiness (Docker & Render)**
   - Multi-stage `python:3.12-slim` `Dockerfile` without `touch *.session`.
   - Background health-check HTTP server on `$PORT` in `source/main.py`.

## Output Format

Present findings in a structured Markdown report:
1. **🚨 CRITICAL SECURITY & PROMPT-INJECTION RISKS**
2. **🧹 ANTI-AI-SLOP & ARCHITECTURAL FINDINGS**
3. **🧪 AUTOMATED AUDIT RESULTS**
4. **✅ ACTIONABLE FIXES APPLIED**
