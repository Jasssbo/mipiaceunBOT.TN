"""
Centralized session management using Redis with automatic in-memory TTL fallback.
Handles user sessions (announcements and reports), automatic cleanup, and rate limiting.
"""
import logging
import json
import os
import time
from typing import Dict, Optional, Any, List, Union, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict, fields
from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError

# Redis configuration
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client: Optional[Redis] = from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
except Exception as e:
    logging.error(f"[REDIS] Configurazione client Redis fallita: {e}")
    redis_client = None


@dataclass
class UserSession:
    """Sessione utente tipizzata per Redis (supporta sia annunci che segnalazioni)."""
    user_id: int
    category: Optional[str] = None
    step: Union[int, str] = 0
    answers: Dict[str, str] = field(default_factory=dict)
    files: Dict[str, List[dict]] = field(default_factory=dict)

    # Message tracking
    messages_to_delete: List[int] = field(default_factory=list)
    user_messages_to_delete: List[int] = field(default_factory=list)
    multi_file_temp_msgs: List[int] = field(default_factory=list)
    preview_msg_id: Optional[Union[int, List[int]]] = None
    confirm_msg_id: Optional[int] = None
    preview_noid_msg_ids: List[int] = field(default_factory=list)
    last_bot_message_id: Optional[int] = None
    allowed: bool = True

    # Single file tracking
    file: Optional[str] = None
    file_type: Optional[str] = None

    # Report flow fields
    reported_username: Optional[str] = None
    reported_user_id: Optional[int] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        val = getattr(self, key, default)
        return default if val is None and default is not None else val


_VALID_SESSION_FIELDS = {f.name for f in fields(UserSession)}


class SessionManager:
    """
    Manages user sessions with Redis primary storage and automatic in-memory TTL fallback.
    Ensures the bot never crashes even if Redis is temporarily unreachable or unconfigured.
    """

    _redis_down_until: float = 0.0
    _fallback_warned: bool = False
    # Shared in-memory fallback store: key -> (value_str, expire_timestamp_or_None)
    _memory_store: Dict[str, Tuple[str, Optional[float]]] = {}

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.redis = redis_client

    def _key(self, user_id: int) -> str:
        return f"{self.prefix}:session:{user_id}"

    def _err_key(self, user_id: int) -> str:
        return f"{self.prefix}:error:{user_id}"

    def _rate_key(self, user_id: int, date_str: str) -> str:
        return f"{self.prefix}:ratelimit:{user_id}:{date_str}"

    def _is_redis_available(self) -> bool:
        return self.redis is not None and time.time() >= SessionManager._redis_down_until

    def _handle_redis_failure(self, exc: Exception) -> None:
        # Avoid log spam: warn once and pause Redis attempts for 60 seconds
        SessionManager._redis_down_until = time.time() + 60.0
        if not SessionManager._fallback_warned:
            logging.warning(
                f"[REDIS] Connessione a Redis non riuscita ({exc}). "
                "Uso fallback in-memory con TTL (imposta REDIS_URL per persistenza distribuita)."
            )
            SessionManager._fallback_warned = True

    # --- Low-level resilient KV operations ---
    def _mem_cleanup_key(self, key: str) -> None:
        entry = SessionManager._memory_store.get(key)
        if entry is not None:
            _, exp = entry
            if exp is not None and time.time() >= exp:
                SessionManager._memory_store.pop(key, None)

    async def _kv_get(self, key: str) -> Optional[str]:
        if self._is_redis_available():
            try:
                val = await self.redis.get(key)
                SessionManager._fallback_warned = False
                return val
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)
        self._mem_cleanup_key(key)
        entry = SessionManager._memory_store.get(key)
        return entry[0] if entry else None

    async def _kv_set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        exp_ts = (time.time() + ex) if ex else None
        # Always mirror to memory store for seamless fallback
        existing = SessionManager._memory_store.get(key)
        if exp_ts is None and existing is not None:
            exp_ts = existing[1]
        SessionManager._memory_store[key] = (value, exp_ts)

        if self._is_redis_available():
            try:
                if ex:
                    await self.redis.set(key, value, ex=ex)
                else:
                    ttl = await self.redis.ttl(key)
                    await self.redis.set(key, value)
                    if ttl and ttl > 0:
                        await self.redis.expire(key, ttl)
                SessionManager._fallback_warned = False
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)

    async def _kv_exists(self, key: str) -> bool:
        if self._is_redis_available():
            try:
                res = await self.redis.exists(key) > 0
                SessionManager._fallback_warned = False
                return res
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)
        self._mem_cleanup_key(key)
        return key in SessionManager._memory_store

    async def _kv_delete(self, key: str) -> None:
        SessionManager._memory_store.pop(key, None)
        if self._is_redis_available():
            try:
                await self.redis.delete(key)
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)

    async def _kv_expire(self, key: str, delay_seconds: int) -> None:
        self._mem_cleanup_key(key)
        if key in SessionManager._memory_store:
            val, _ = SessionManager._memory_store[key]
            SessionManager._memory_store[key] = (val, time.time() + delay_seconds)
        if self._is_redis_available():
            try:
                await self.redis.expire(key, delay_seconds)
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)

    async def _kv_persist(self, key: str) -> None:
        self._mem_cleanup_key(key)
        if key in SessionManager._memory_store:
            val, _ = SessionManager._memory_store[key]
            SessionManager._memory_store[key] = (val, None)
        if self._is_redis_available():
            try:
                await self.redis.persist(key)
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)

    # --- High-level Session API ---
    async def create_session(self, user_id: int, initial_data: Optional[Dict[str, Any]] = None) -> UserSession:
        """Create or reset a session for a user."""
        session = UserSession(user_id=user_id)
        if initial_data:
            for key, value in initial_data.items():
                if key in _VALID_SESSION_FIELDS:
                    setattr(session, key, value)
        await self.save_session(session)
        return session

    async def get_session(self, user_id: int) -> Optional[UserSession]:
        """Get a user's session data."""
        data = await self._kv_get(self._key(user_id))
        if data:
            try:
                parsed = json.loads(data)
                filtered = {k: v for k, v in parsed.items() if k in _VALID_SESSION_FIELDS}
                return UserSession(**filtered)
            except Exception as e:
                logging.error(f"Error parsing session data for {user_id}: {e}")
                return None
        return None

    async def save_session(self, session: UserSession, expire: Optional[int] = None) -> None:
        """Save a UserSession object."""
        key = self._key(session.user_id)
        await self._kv_set(key, json.dumps(asdict(session)), ex=expire)

    async def update_session(self, user_id: int, data: Dict[str, Any]) -> None:
        """Update a user's session data."""
        session = await self.get_session(user_id)
        if not session:
            session = await self.create_session(user_id)
        for key, value in data.items():
            if key in _VALID_SESSION_FIELDS:
                setattr(session, key, value)
        await self.save_session(session)

    async def has_session(self, user_id: int) -> bool:
        """Check if a user has an active session."""
        return await self._kv_exists(self._key(user_id))

    async def delete_session(self, user_id: int) -> None:
        """Delete a user's session immediately."""
        await self._kv_delete(self._key(user_id))

    async def schedule_cleanup(self, user_id: int, delay_seconds: int) -> None:
        """Schedule automatic session cleanup after a delay."""
        await self._kv_expire(self._key(user_id), delay_seconds)

    async def cancel_cleanup(self, user_id: int) -> None:
        """Cancel a scheduled cleanup for a user."""
        await self._kv_persist(self._key(user_id))

    async def get_all_user_ids(self) -> List[int]:
        prefix_match = f"{self.prefix}:session:"
        if self._is_redis_available():
            try:
                keys = await self.redis.keys(f"{prefix_match}*")
                return [int(k.split(":")[-1]) for k in keys]
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)
        for k in list(SessionManager._memory_store.keys()):
            self._mem_cleanup_key(k)
        return [
            int(k.split(":")[-1])
            for k in SessionManager._memory_store
            if k.startswith(prefix_match)
        ]

    async def get_session_count(self) -> int:
        return len(await self.get_all_user_ids())

    async def clear_all(self) -> None:
        prefix_match = f"{self.prefix}:"
        for k in list(SessionManager._memory_store.keys()):
            if k.startswith(prefix_match):
                SessionManager._memory_store.pop(k, None)
        if self._is_redis_available():
            try:
                keys = await self.redis.keys(f"{prefix_match}*")
                if keys:
                    await self.redis.delete(*keys)
            except (RedisError, OSError) as e:
                self._handle_redis_failure(e)

    # --- Ephemeral Error Message Tracking ---
    async def set_error_message(self, user_id: int, msg_id: int) -> None:
        await self._kv_set(self._err_key(user_id), str(msg_id), ex=3600)

    async def get_error_message(self, user_id: int) -> Optional[int]:
        val = await self._kv_get(self._err_key(user_id))
        return int(val) if val else None

    async def clear_error_message(self, user_id: int) -> None:
        await self._kv_delete(self._err_key(user_id))

    # --- Daily Rate Limiting ---
    async def get_daily_count(self, user_id: int) -> int:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        val = await self._kv_get(self._rate_key(user_id, today_str))
        return int(val) if val and val.isdigit() else 0

    async def increment_daily_count(self, user_id: int) -> int:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = self._rate_key(user_id, today_str)
        current = await self.get_daily_count(user_id)
        new_val = current + 1
        await self._kv_set(key, str(new_val), ex=86400)
        return new_val


# Global singleton instances
_announcement_sessions = SessionManager("announcement")
_report_sessions = SessionManager("report")


def get_announcement_sessions() -> SessionManager:
    return _announcement_sessions


def get_report_sessions() -> SessionManager:
    return _report_sessions
