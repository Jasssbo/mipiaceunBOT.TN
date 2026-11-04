#!/usr/bin/env python3
"""
Automated Whitehat, Anti-AI-Slop & Markdown Security Audit Script for mipiaceunBOT.TN.
Verifies:
1. Markdown Security & Prompt-Injection Sanitization (invisible Unicode, Bidi overrides, HTML comment injections, RCE pipes)
2. Anti-AI-Slop Detection (cargo-cult `touch *.session`, obsolete `reports.json`, AI meta-comments)
3. AST Static Analysis (undefined names/imports, bare excepts, blocking calls)
4. Dependencies & Native C/C++ Extensions (pyrogram, tgcrypto, sqlalchemy[asyncio], greenlet, aiosqlite, redis)
5. Async Runtime Smoke Tests (Pyrogram 64-bit patch, 0-byte .session self-healing, SessionManager + fallback, SQLite DB)
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
from pathlib import Path
from typing import Set, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[4]
SOURCE_DIR = ROOT_DIR / "source"
sys.path.insert(0, str(SOURCE_DIR))

BUILTIN_NAMES = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__", "__all__"}

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
    re.compile(r"<!--[\s\S]*?(ignore\s+(all\s+)?previous|disregard\s+all|system\s+prompt|you\s+must\s+now|override\s+instructions|curl\s+|wget\s+|eval\s*\(|base64\s+-d)[\s\S]*?-->", re.IGNORECASE),
    re.compile(r"(curl|wget)\s+[^\n|]+\|\s*(ba)?sh\b", re.IGNORECASE),
    re.compile(r"base64\s+(-d|--decode)\s*\|\s*(ba)?sh\b", re.IGNORECASE),
]

AI_SLOP_PATTERNS = [
    (re.compile(r"\b(as an ai language model|here is the updated code|rest of the code remains unchanged)\b", re.IGNORECASE), "AI meta-commentary"),
    (re.compile(r"#\s*TODO:\s*implement\b", re.IGNORECASE), "Unfinished placeholder TODO"),
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
            # Allow BOM only at index 0
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


def check_ai_slop() -> List[str]:
    """Checks Dockerfile, scripts, and Python source for known AI-slop and cargo-cult anti-patterns."""
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

    # 3. Python source files check for AI meta-comments
    for py_file in sorted(SOURCE_DIR.rglob("*.py")):
        rel = py_file.relative_to(ROOT_DIR)
        text = py_file.read_text(encoding="utf-8")
        for pattern, desc in AI_SLOP_PATTERNS:
            if pattern.search(text):
                errors.append(f"[AI SLOP] {rel} contains {desc}")

    return errors


class UndefinedNameVisitor(ast.NodeVisitor):
    """Detects potentially undefined variable/function references in Python AST."""

    def __init__(self):
        self.scopes: List[Set[str]] = [set(BUILTIN_NAMES)]
        self.undefined: List[Tuple[int, str]] = []

    def _define(self, name: str):
        self.scopes[-1].add(name)

    def _is_defined(self, name: str) -> bool:
        return any(name in scope for scope in reversed(self.scopes))

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
        self.scopes.append(set())
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

        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                func_scope.add(child.id)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                func_scope.add(child.name)
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    func_scope.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    if alias.name != "*":
                        func_scope.add(alias.asname or alias.name)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                func_scope.add(child.name)

        self.scopes.append(func_scope)
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
        self._define_target(node.target)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        self._define_target(node.target)
        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        for item in node.items:
            if item.optional_vars:
                self._define_target(item.optional_vars)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith):
        for item in node.items:
            if item.optional_vars:
                self._define_target(item.optional_vars)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.name:
            self._define(node.name)
        self.generic_visit(node)

    def _visit_comprehension(self, node):
        comp_scope: Set[str] = set()
        for gen in node.generators:
            for child in ast.walk(gen.target):
                if isinstance(child, ast.Name):
                    comp_scope.add(child.id)
        self.scopes.append(comp_scope)
        self.generic_visit(node)
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
        lam_scope = {a.arg for a in node.args.args}
        self.scopes.append(lam_scope)
        self.visit(node.body)
        self.scopes.pop()

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if not self._is_defined(node.id):
                self.undefined.append((node.lineno, node.id))


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
    os.environ.setdefault("API_ID", "123456")
    os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
    os.environ.setdefault("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

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
        import modules.core.buttons
        import modules.permissions.user_permissions
        import modules.permissions.topic_permissions
        import modules.user_announcements_interactions.announcement_handler
        import modules.reports.report_user
    except Exception as e:
        errors.append(f"[MODULE / STORAGE ERROR] Failed runtime verification: {e}")

    # Test SessionManager & UserSession (both announcement and report flows + fallback)
    try:
        from core.session_manager import SessionManager
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
        await sm.clear_all()
    except Exception as e:
        errors.append(f"[SESSION MANAGER] Runtime test failed: {e}")

    # Test Database Repository on isolated in-memory SQLite
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from database.models import Base, Report
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

    print("2️⃣  Scanning Codebase & Docker Configs for AI Slop / Anti-Patterns ...")
    slop_errs = check_ai_slop()
    all_errors.extend(slop_errs)
    print("   ✅ Passed!" if not slop_errs else f"   ❌ Found {len(slop_errs)} issue(s)")

    print("3️⃣  Running AST Static Analysis on source/ ...")
    ast_errs = check_ast_all_files()
    all_errors.extend(ast_errs)
    print("   ✅ Passed!" if not ast_errs else f"   ❌ Found {len(ast_errs)} issue(s)")

    print("4️⃣  Checking Dependencies & Native C/C++ Extensions ...")
    dep_errs = check_dependencies()
    all_errors.extend(dep_errs)
    print("   ✅ Passed!" if not dep_errs else f"   ❌ Found {len(dep_errs)} issue(s)")

    print("5️⃣  Running Async Runtime Smoke Tests (64-bit IDs, 0-byte Session, Redis, SQLite) ...")
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
