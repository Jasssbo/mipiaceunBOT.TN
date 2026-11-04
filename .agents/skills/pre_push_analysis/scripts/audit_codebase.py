#!/usr/bin/env python3
"""
Automated Whitehat, Anti-AI-Slop, Memory & Markdown Security Audit Script for mipiaceunBOT.TN.
Runs 100% hermetically (zero network calls to production Redis, zero disk artifacts).

Verifies:
1. Markdown Security & Prompt-Injection Sanitization (invisible Unicode, Bidi overrides, HTML comment injections, RCE pipes)
2. Anti-AI-Slop & Hardcoded Secret Detection (cargo-cult `touch *.session`, obsolete `reports.json`, leaked tokens/URLs)
3. AST Static Analysis & OWASP Access Control (accurate lexical scoping, bare excepts, blocking calls, handler auth checks)
4. Dependencies & Native C/C++ Extensions (pyrogram, tgcrypto, sqlalchemy[asyncio], greenlet, aiosqlite, redis)
5. Hermetic Async Runtime Smoke Tests (64-bit IDs, 0-byte .session self-healing, HMAC callback signing, bounded memory, SQLite)
6. Git & Docker Secret Hygiene
"""
import ast
import asyncio
import builtins
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Set, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[4]
SOURCE_DIR = ROOT_DIR / "source"
sys.path.insert(0, str(SOURCE_DIR))

BUILTIN_NAMES = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__", "__all__"}

# Handlers that are intentionally accessible to all users per GDPR Art. 15 & Art. 17
GDPR_PUBLIC_HANDLERS = {
    "privacy_command_handler",
    "terms_command_handler",
    "my_data_handler",
    "erase_my_data_handler",
}

# Steganographic / invisible / bidirectional Unicode code points used in compromised .md attacks
DANGEROUS_UNICODE_RANGES = [
    (0x200B, 0x200F, "Zero-Width / Direction Mark"),
    (0x202A, 0x202E, "Bidirectional Text Override (Trojan Source)"),
    (0x2060, 0x2064, "Invisible Word Joiner / Operator"),
    (0x2066, 0x2069, "Bidirectional Isolate"),
    (0xFEFF, 0xFEFF, "Zero-Width No-Break Space (BOM inside text)"),
    (0xE0000, 0xE007F, "Unicode Tag Characters (Invisible Prompt Injection)"),
]

PROMPT_INJECTION_PATTERNS = [
    re.compile(
        r"<!--[\s\S]*?(ignore\s+(all\s+)?previous|disregard\s+all|system\s+prompt|you\s+must\s+now|override\s+instructions|curl\s+|wget\s+|eval\s*\(|base64\s+-d)[\s\S]*?-->",
        re.IGNORECASE,
    ),
    re.compile(r"(curl|wget)\s+[^\n|]+\|\s*(ba)?sh\b", re.IGNORECASE),
    re.compile(r"base64\s+(-d|--decode)\s*\|\s*(ba)?sh\b", re.IGNORECASE),
]

AI_SLOP_PATTERNS = [
    (
        re.compile(r"\b(as an ai language model|here is the updated code|rest of the code remains unchanged)\b", re.IGNORECASE),
        "AI meta-commentary",
    ),
    (re.compile(r"#\s*TODO:\s*implement\b", re.IGNORECASE), "Unfinished placeholder TODO"),
]

# Patterns for accidentally hardcoded live credentials in source code
SECRET_LEAK_PATTERNS = [
    (re.compile(r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b"), "Hardcoded Telegram BOT_TOKEN"),
    (re.compile(r"rediss?://[^:\s]+:[^@\s]{10,}@[^\s\"']+"), "Hardcoded Redis URL with password"),
]


def _is_dangerous_char(ch: str) -> str:
    cp = ord(ch)
    for start, end, desc in DANGEROUS_UNICODE_RANGES:
        if start <= cp <= end:
            return f"U+{cp:04X} ({desc})"
    return ""


def check_markdown_security(sanitize: bool = False) -> List[str]:
    """Scans all .md files for invisible Unicode steganography, prompt injection, and RCE shell pipes."""
    errors = []
    md_files = [
        p for p in ROOT_DIR.rglob("*.md")
        if ".venv" not in p.parts and ".git" not in p.parts
    ]

    for md_file in sorted(md_files):
        rel = md_file.relative_to(ROOT_DIR)
        raw_text = md_file.read_text(encoding="utf-8")

        # 1. Check for invisible / steganographic Unicode characters
        bad_chars = []
        cleaned_chars = []
        for idx, ch in enumerate(raw_text):
            if idx == 0 and ord(ch) == 0xFEFF:
                cleaned_chars.append(ch)
                continue
            reason = _is_dangerous_char(ch)
            if reason:
                bad_chars.append(reason)
            else:
                cleaned_chars.append(ch)

        if bad_chars:
            unique_reasons = ", ".join(sorted(set(bad_chars)))
            if sanitize:
                md_file.write_text("".join(cleaned_chars), encoding="utf-8")
                print(f"   🧹 Sanitized {len(bad_chars)} hidden Unicode char(s) in {rel}: {unique_reasons}")
            else:
                errors.append(
                    f"[MD SECURITY] {rel} contains {len(bad_chars)} hidden/steganographic Unicode char(s): {unique_reasons} (run with --sanitize)"
                )

        # 2. Check for hidden HTML prompt injections or RCE pipes
        for pattern in PROMPT_INJECTION_PATTERNS:
            match = pattern.search(raw_text)
            if match:
                snippet = match.group(0)[:80].replace("\n", " ")
                errors.append(f"[MD PROMPT INJECTION / RCE] {rel} contains suspicious payload: '{snippet}...'")

    return errors


def check_ai_slop_and_secrets() -> List[str]:
    """Checks Dockerfile, scripts, and Python source for AI-slop, cargo-cult anti-patterns, and hardcoded secrets."""
    errors = []

    # 1. Dockerfile must never `touch *.session` (causes 0-byte SQLite OperationalError: no such table: version)
    dockerfile = ROOT_DIR / "Dockerfile"
    if dockerfile.exists():
        for lineno, line in enumerate(dockerfile.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith("#") and re.search(r"\btouch\b.*\.session\b", stripped):
                errors.append(
                    f"[AI SLOP] Dockerfile:{lineno} uses 'touch *.session' which creates a 0-byte file that crashes Pyrogram FileStorage!"
                )

    # 2. backup.sh must not reference obsolete reports.json
    backup_sh = ROOT_DIR / "backup.sh"
    if backup_sh.exists():
        b_text = backup_sh.read_text(encoding="utf-8")
        if 'SOURCE_FILE="reports.json"' in b_text:
            errors.append("[AI SLOP] backup.sh still targets obsolete 'reports.json' instead of 'users_data.db'")

    # 3. Python source files check for AI meta-comments and hardcoded credentials
    for py_file in sorted(SOURCE_DIR.rglob("*.py")):
        rel = py_file.relative_to(ROOT_DIR)
        text = py_file.read_text(encoding="utf-8")
        for pattern, desc in AI_SLOP_PATTERNS:
            if pattern.search(text):
                errors.append(f"[AI SLOP] {rel} contains {desc}")
        for pattern, desc in SECRET_LEAK_PATTERNS:
            if pattern.search(text):
                errors.append(f"[SECRET LEAK] {rel} contains {desc}")

    return errors


def _collect_func_locals(node: ast.AST, out: Set[str]) -> None:
    """Collects local variable names bound inside a function body without descending into nested scopes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(child.name)
            # Do NOT descend into nested function/class bodies
            continue
        if isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Lambda)):
            # Do NOT leak comprehension/lambda variables into outer function scope
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            out.add(child.id)
        elif isinstance(child, ast.Import):
            for alias in child.names:
                out.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(child, ast.ImportFrom):
            for alias in child.names:
                if alias.name != "*":
                    out.add(alias.asname or alias.name)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            out.add(child.name)
        _collect_func_locals(child, out)


class UndefinedNameVisitor(ast.NodeVisitor):
    """Detects undefined variable/function references in Python AST respecting Python lexical scoping rules."""

    def __init__(self):
        # Each tuple is (scope_set, is_class_scope). Class scopes are not visible to nested functions!
        self.scopes: List[Tuple[Set[str], bool]] = [(set(BUILTIN_NAMES), False)]
        self.undefined: List[Tuple[int, str]] = []

    def _define(self, name: str):
        self.scopes[-1][0].add(name)

    def _is_defined(self, name: str) -> bool:
        for idx in range(len(self.scopes) - 1, -1, -1):
            scope_set, is_class_scope = self.scopes[idx]
            # A class body scope is only visible at the top of the stack (inside the class body itself),
            # never inside methods defined within the class.
            if is_class_scope and idx != len(self.scopes) - 1:
                continue
            if name in scope_set:
                return True
        return False

    def _define_target(self, target: ast.AST):
        if isinstance(target, ast.Name):
            self._define(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._define_target(elt)
        elif isinstance(target, ast.Starred):
            self._define_target(target.value)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self._define(name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            if alias.name == "*":
                continue
            name = alias.asname or alias.name
            self._define(name)

    def visit_ClassDef(self, node: ast.ClassDef):
        self._define(node.name)
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        self.scopes.append((set(), True))
        for stmt in node.body:
            self.visit(stmt)
        self.scopes.pop()

    def _visit_func(self, node):
        self._define(node.name)
        for dec in node.decorator_list:
            self.visit(dec)
        for default in node.args.defaults + node.args.kw_defaults:
            if default:
                self.visit(default)
        func_scope: Set[str] = set()
        for arg in (
            node.args.posonlyargs
            + node.args.args
            + node.args.kwonlyargs
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        ):
            func_scope.add(arg.arg)

        _collect_func_locals(node, func_scope)

        self.scopes.append((func_scope, False))
        for stmt in node.body:
            self.visit(stmt)
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_func(node)

    def visit_Assign(self, node: ast.Assign):
        self.visit(node.value)
        for t in node.targets:
            self._define_target(t)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.value:
            self.visit(node.value)
        self._define_target(node.target)

    def visit_For(self, node: ast.For):
        self.visit(node.iter)
        self._define_target(node.target)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        self.visit(node.iter)
        self._define_target(node.target)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._define_target(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_AsyncWith(self, node: ast.AsyncWith):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._define_target(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.type:
            self.visit(node.type)
        if node.name:
            self._define(node.name)
        for stmt in node.body:
            self.visit(stmt)

    def _visit_comprehension(self, node):
        # In Python, the first generator's iter is evaluated in the outer scope!
        first_gen = node.generators[0]
        self.visit(first_gen.iter)

        comp_scope: Set[str] = set()
        self.scopes.append((comp_scope, False))
        self._define_target(first_gen.target)
        for if_clause in first_gen.ifs:
            self.visit(if_clause)

        for gen in node.generators[1:]:
            self.visit(gen.iter)
            self._define_target(gen.target)
            for if_clause in gen.ifs:
                self.visit(if_clause)

        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.scopes.pop()

    def visit_ListComp(self, node: ast.ListComp):
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp):
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp):
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        self._visit_comprehension(node)

    def visit_Lambda(self, node: ast.Lambda):
        for default in node.args.defaults + node.args.kw_defaults:
            if default:
                self.visit(default)
        lam_scope = {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
        if node.args.vararg:
            lam_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            lam_scope.add(node.args.kwarg.arg)
        self.scopes.append((lam_scope, False))
        self.visit(node.body)
        self.scopes.pop()

    def visit_NamedExpr(self, node: ast.NamedExpr):
        self.visit(node.value)
        self._define_target(node.target)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if not self._is_defined(node.id):
                self.undefined.append((node.lineno, node.id))


def _check_handler_access_control(tree: ast.Module, rel: Path) -> List[str]:
    """Verifies that every Pyrogram @bot.on_message / @bot.on_callback_query handler enforces access control."""
    errors = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_bot_handler = False
        has_group_member_decorator = False
        for dec in node.decorator_list:
            dec_src = ast.unparse(dec)
            if "bot.on_message" in dec_src or "bot.on_callback_query" in dec_src:
                is_bot_handler = True
            if "require_group_member" in dec_src:
                has_group_member_decorator = True

        if not is_bot_handler:
            continue
        if has_group_member_decorator or node.name in GDPR_PUBLIC_HANDLERS:
            continue

        body_src = ast.unparse(node)
        if "ADMIN_IDS" in body_src or "CHAT_ID" in body_src:
            continue

        errors.append(
            f"[OWASP A01 ACCESS CONTROL] {rel}:{node.lineno} -> Handler '{node.name}' lacks @require_group_member or ADMIN_IDS/CHAT_ID check"
        )
    return errors


def check_ast_all_files() -> List[str]:
    errors = []
    for py_file in sorted(SOURCE_DIR.rglob("*.py")):
        rel = py_file.relative_to(ROOT_DIR)
        source_code = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source_code, filename=str(rel))
        except SyntaxError as e:
            errors.append(f"[SYNTAX ERROR] {rel}:{e.lineno}: {e.msg}")
            continue

        visitor = UndefinedNameVisitor()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visitor._define(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    visitor._define_target(t)
            elif isinstance(node, ast.AnnAssign):
                visitor._define_target(node.target)

        visitor.visit(tree)
        for lineno, name in visitor.undefined:
            errors.append(f"[UNDEFINED NAME] {rel}:{lineno} -> '{name}' is not defined/imported")

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                errors.append(f"[BARE EXCEPT] {rel}:{node.lineno} -> Use 'except Exception:' instead of bare 'except:'")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "time" and node.func.attr == "sleep":
                    errors.append(f"[BLOCKING CALL] {rel}:{node.lineno} -> Blocking 'time.sleep()' in async codebase")

        errors.extend(_check_handler_access_control(tree, rel))

    return errors


def check_dependencies() -> List[str]:
    errors = []
    req_file = ROOT_DIR / "requirements.txt"
    req_text = req_file.read_text(encoding="utf-8").lower()
    if "greenlet" not in req_text or "sqlalchemy[asyncio]" not in req_text:
        errors.append("[REQUIREMENTS] Both 'greenlet' and 'sqlalchemy[asyncio]' must be in requirements.txt")

    for mod in ["pyrogram", "tgcrypto", "sqlalchemy.ext.asyncio", "greenlet", "aiosqlite", "redis", "tenacity", "cachetools"]:
        try:
            __import__(mod)
        except Exception as e:
            errors.append(f"[IMPORT ERROR] Failed to import required library '{mod}': {e}")
    return errors


async def check_runtime_components() -> List[str]:
    errors = []
    # Force hermetic in-memory environment BEFORE importing project modules so load_dotenv()
    # never connects to production Redis or creates SQLite files on disk during the audit.
    os.environ["API_ID"] = "123456"
    os.environ["API_HASH"] = "0123456789abcdef0123456789abcdef"
    os.environ["BOT_TOKEN"] = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    os.environ["REDIS_URL"] = "memory://"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    try:
        import config
        import pyrogram.utils as utils
        from pyrogram.storage.file_storage import FileStorage

        if utils.MIN_CHANNEL_ID > -1002461409137:
            errors.append(f"[PYROGRAM PATCH] MIN_CHANNEL_ID ({utils.MIN_CHANNEL_ID}) does not cover 64-bit ID -1002461409137")
        if utils.get_peer_type(-1002461409137) != "channel":
            errors.append("[PYROGRAM PATCH] utils.get_peer_type(-1002461409137) did not return 'channel'")

        # Test 0-byte .session file self-healing (prevents sqlite3.OperationalError: no such table: version)
        with tempfile.TemporaryDirectory() as tmpdir:
            zero_session = Path(tmpdir) / "zero_test.session"
            zero_session.touch()
            fs = FileStorage("zero_test", Path(tmpdir))
            await fs.open()
            if fs.version() != FileStorage.VERSION:
                errors.append(f"[FILESTORAGE PATCH] Expected schema version {FileStorage.VERSION}, got {fs.version()}")
            await fs.close()

        # Verify all bot modules and handlers import cleanly
        import modules.core.start
        import modules.core.buttons as buttons_mod
        import modules.permissions.user_permissions
        import modules.permissions.topic_permissions
        import modules.user_announcements_interactions.announcement_handler
        import modules.reports.report_user

        # Test OWASP A08 HMAC callback signature & 64-byte Telegram limit for 10-photo album
        sample_ids = list(range(100001, 100011))
        cb_data = buttons_mod.sign_delete_callback(5000000001, sample_ids)
        if len(cb_data.encode("utf-8")) > 64:
            errors.append(f"[OWASP CALLBACK] delete_ callback exceeds 64-byte Telegram limit ({len(cb_data)} bytes): {cb_data}")
        parts = cb_data.split("_")
        if not buttons_mod.verify_delete_callback(int(parts[1]), parts[2], parts[3]):
            errors.append("[OWASP CALLBACK] Valid HMAC signature rejected by verify_delete_callback")
        if buttons_mod.verify_delete_callback(int(parts[1]), "463,466,467", parts[3]):
            errors.append("[OWASP CALLBACK] Tampered message IDs accepted by verify_delete_callback!")
        if buttons_mod.decode_msg_ids(parts[2]) != sample_ids:
            errors.append("[OWASP CALLBACK] decode_msg_ids did not round-trip contiguous album IDs")
    except Exception as e:
        errors.append(f"[MODULE / STORAGE ERROR] Failed runtime verification: {e}")

    # Test SessionManager & UserSession (both announcement and report flows + memory bounds & TTL eviction)
    try:
        from cachetools import TTLCache
        from core.session_manager import SessionManager
        from modules.user_announcements_interactions.announcement_handler import _user_locks
        from services.message_service import get_message_service

        if not isinstance(_user_locks, TTLCache):
            errors.append("[MEMORY MANAGEMENT] announcement_handler._user_locks must be a bounded TTLCache")
        if not isinstance(get_message_service()._user_messages, TTLCache):
            errors.append("[MEMORY MANAGEMENT] MessageService._user_messages must be a bounded TTLCache")

        sm = SessionManager("audit_test")
        await sm.create_session(999001, {"category": "job", "step": 0})
        await sm.update_session(999001, {
            "step": "awaiting_reason",
            "reported_username": "bad_actor",
            "reported_user_id": 888001,
        })
        sess = await sm.get_session(999001)
        if not sess or sess.reported_username != "bad_actor" or sess.reported_user_id != 888001:
            errors.append(f"[SESSION SCHEMA] UserSession lost report fields: {sess}")
        count = await sm.increment_daily_count(999001)
        if count != 1:
            errors.append(f"[RATE LIMIT] Expected daily count 1, got {count}")

        # Verify expired key eviction in _memory_store
        SessionManager._memory_store["audit_test:expired"] = ("val", time.time() - 10)
        SessionManager._ops_counter = 49
        sm._mem_periodic_sweep()
        if "audit_test:expired" in SessionManager._memory_store:
            errors.append("[MEMORY MANAGEMENT] SessionManager._mem_periodic_sweep failed to evict expired key")

        await sm.clear_all()
    except Exception as e:
        errors.append(f"[SESSION MANAGER] Runtime test failed: {e}")

    # Test Database Repository on isolated in-memory SQLite (zero disk artifacts)
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from database.models import Base, Report
        import database.repository as repo_mod
        from database.repository import ReportRepository

        test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        test_session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with test_session_maker() as session:
            repo = ReportRepository(session)
            await repo.add(Report(
                reported_username="spammer",
                reported_user_id=5000000001,
                reporter_username="alice",
                reporter_user_id=5000000002,
                reason="Test report reason >= 10 chars",
            ))
            unique = await repo.count_unique_reporters_for_user(5000000001)
            if unique != 1:
                errors.append(f"[DATABASE] Expected 1 unique reporter, got {unique}")
            erased = await repo.erase_user_data(5000000002)
            if erased != 1:
                errors.append(f"[DATABASE] GDPR erase expected 1 deleted row, got {erased}")
        await test_engine.dispose()
        await repo_mod.engine.dispose()
    except Exception as e:
        errors.append(f"[DATABASE] Async SQLAlchemy smoke test failed: {e}")

    return errors


def check_git_hygiene() -> List[str]:
    errors = []
    gitignore_text = (ROOT_DIR / ".gitignore").read_text(encoding="utf-8")
    for pattern in ["*.env", "*.session", "*.db"]:
        if pattern not in gitignore_text:
            errors.append(f"[GIT HYGIENE] Pattern '{pattern}' missing from .gitignore")

    dockerignore_path = ROOT_DIR / ".dockerignore"
    if not dockerignore_path.exists():
        errors.append("[DOCKER HYGIENE] Missing .dockerignore file")
    else:
        di_text = dockerignore_path.read_text(encoding="utf-8")
        for pattern in ["*.env", "*.session", "*.db", ".venv"]:
            if pattern not in di_text:
                errors.append(f"[DOCKER HYGIENE] Pattern '{pattern}' missing from .dockerignore")

    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=ROOT_DIR, text=True)
        tracked = out.splitlines()
        for f in tracked:
            if f.endswith((".env", ".session")) or f == "reports.json":
                errors.append(f"[GIT HYGIENE] Secret/session file is tracked in Git: {f}")
            elif f.endswith(".db"):
                print(f"   ⚠️  Note: '{f}' is still in Git index (run 'git rm --cached {f}' before committing)")
    except Exception as e:
        errors.append(f"[GIT CHECK] Could not run git ls-files: {e}")
    return errors


def main():
    sanitize_flag = "--sanitize" in sys.argv
    print("=" * 72)
    print("🔍 mipiaceunBOT.TN — Whitehat, Anti-Slop & Markdown Security Audit")
    print("=" * 72)

    all_errors: List[str] = []

    print("1️⃣  Scanning .md files for Prompt Injections & Hidden Unicode ...")
    md_errs = check_markdown_security(sanitize=sanitize_flag)
    all_errors.extend(md_errs)
    print("   ✅ Passed!" if not md_errs else f"   ❌ Found {len(md_errs)} issue(s)")

    print("2️⃣  Scanning Codebase & Docker Configs for AI Slop / Leaked Secrets ...")
    slop_errs = check_ai_slop_and_secrets()
    all_errors.extend(slop_errs)
    print("   ✅ Passed!" if not slop_errs else f"   ❌ Found {len(slop_errs)} issue(s)")

    print("3️⃣  Running AST Static & OWASP Access Control Analysis on source/ ...")
    ast_errs = check_ast_all_files()
    all_errors.extend(ast_errs)
    print("   ✅ Passed!" if not ast_errs else f"   ❌ Found {len(ast_errs)} issue(s)")

    print("4️⃣  Checking Dependencies & Native C/C++ Extensions ...")
    dep_errs = check_dependencies()
    all_errors.extend(dep_errs)
    print("   ✅ Passed!" if not dep_errs else f"   ❌ Found {len(dep_errs)} issue(s)")

    print("5️⃣  Running Hermetic Async Runtime Smoke Tests (64-bit IDs, HMAC, Memory, DB) ...")
    rt_errs = asyncio.run(check_runtime_components())
    all_errors.extend(rt_errs)
    print("   ✅ Passed!" if not rt_errs else f"   ❌ Found {len(rt_errs)} issue(s)")

    print("6️⃣  Checking Git & Docker Secret Hygiene ...")
    git_errs = check_git_hygiene()
    all_errors.extend(git_errs)
    print("   ✅ Passed!" if not git_errs else f"   ❌ Found {len(git_errs)} issue(s)")

    print("=" * 72)
    if all_errors:
        print(f"🚨 AUDIT FAILED WITH {len(all_errors)} ISSUE(S):")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("✅ ALL 6 AUDIT LAYERS PASSED! Repository is sanitized and production-ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
