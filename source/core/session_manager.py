"""
Centralized session management using Redis.
Handles user sessions, automatic cleanup, and prevents memory leaks.
"""
import logging
import asyncio
import json
import os
from typing import Dict, Optional, Any, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from redis.asyncio import Redis, from_url

# Redis instance
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = from_url(redis_url, decode_responses=True)
except Exception as e:
    logging.error(f"Failed to connect to Redis: {e}")
    redis_client = None

@dataclass
class UserSession:
    """Sessione utente tipizzata per Redis"""
    user_id: int
    category: Optional[str] = None
    step: int = 0
    answers: Dict[str, str] = field(default_factory=dict)
    files: Dict[str, List[dict]] = field(default_factory=dict)
    
    # Message tracking
    messages_to_delete: List[int] = field(default_factory=list)
    user_messages_to_delete: List[int] = field(default_factory=list)
    multi_file_temp_msgs: List[int] = field(default_factory=list)
    preview_msg_id: Optional[int] = None
    confirm_msg_id: Optional[int] = None
    preview_noid_msg_ids: List[int] = field(default_factory=list)
    
    # Old tracking (file and file_type)
    file: Optional[str] = None
    file_type: Optional[str] = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def __getitem__(self, key):
        return getattr(self, key)
        
    def __setitem__(self, key, value):
        setattr(self, key, value)
        
    def __contains__(self, key):
        return hasattr(self, key)
        
    def get(self, key, default=None):
        return getattr(self, key, default)

class SessionManager:
    """
    Manages user sessions with automatic cleanup and memory management using Redis.
    Replaces the global user_data dictionary pattern.
    """
    
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.redis = redis_client
        
    def _key(self, user_id: int) -> str:
        return f"{self.prefix}:session:{user_id}"

    async def create_session(self, user_id: int, initial_data: Optional[Dict[str, Any]] = None) -> UserSession:
        """Create or reset a session for a user."""
        session = UserSession(user_id=user_id)
        if initial_data:
            for key, value in initial_data.items():
                if hasattr(session, key):
                    setattr(session, key, value)
        await self.save_session(session)
        return session
    
    async def get_session(self, user_id: int) -> Optional[UserSession]:
        """Get a user's session data."""
        if not self.redis:
            return None
        data = await self.redis.get(self._key(user_id))
        if data:
            try:
                parsed = json.loads(data)
                # Remove keys that are not in the dataclass to avoid TypeError
                # in case of old data formats
                return UserSession(**parsed)
            except Exception as e:
                logging.error(f"Error parsing session data for {user_id}: {e}")
                return None
        return None
    
    async def save_session(self, session: UserSession, expire: Optional[int] = None) -> None:
        """Save a UserSession object to Redis."""
        if not self.redis:
            return
        key = self._key(session.user_id)
        await self.redis.set(key, json.dumps(asdict(session)))
        if expire:
            await self.redis.expire(key, expire)

    async def update_session(self, user_id: int, data: Dict[str, Any]) -> None:
        """Update a user's session data."""
        session = await self.get_session(user_id)
        if not session:
            session = await self.create_session(user_id)
        for key, value in data.items():
            if hasattr(session, key):
                setattr(session, key, value)
        await self.save_session(session)
    
    async def has_session(self, user_id: int) -> bool:
        """Check if a user has an active session."""
        if not self.redis:
            return False
        return await self.redis.exists(self._key(user_id)) > 0
    
    async def delete_session(self, user_id: int) -> None:
        """Delete a user's session immediately."""
        if self.redis:
            await self.redis.delete(self._key(user_id))
    
    async def schedule_cleanup(self, user_id: int, delay_seconds: int) -> None:
        """
        Schedule automatic session cleanup after a delay using Redis EXPIRE.
        """
        if self.redis:
            await self.redis.expire(self._key(user_id), delay_seconds)
    
    async def cancel_cleanup(self, user_id: int) -> None:
        """Cancel a scheduled cleanup for a user."""
        if self.redis:
            await self.redis.persist(self._key(user_id))
    
    async def get_all_user_ids(self) -> List[int]:
        if not self.redis:
            return []
        keys = await self.redis.keys(f"{self.prefix}:session:*")
        return [int(k.split(":")[-1]) for k in keys]
    
    async def get_session_count(self) -> int:
        if not self.redis:
            return 0
        keys = await self.redis.keys(f"{self.prefix}:session:*")
        return len(keys)
    
    async def clear_all(self) -> None:
        if not self.redis:
            return
        keys = await self.redis.keys(f"{self.prefix}:*")
        if keys:
            await self.redis.delete(*keys)
            
    # --- EPHEMERAL STATE TRACKING (e.g. error messages) ---
    def _err_key(self, user_id: int) -> str:
        return f"{self.prefix}:error:{user_id}"

    async def set_error_message(self, user_id: int, msg_id: int) -> None:
        if self.redis:
            await self.redis.set(self._err_key(user_id), msg_id, ex=3600)

    async def get_error_message(self, user_id: int) -> Optional[int]:
        if not self.redis:
            return None
        val = await self.redis.get(self._err_key(user_id))
        return int(val) if val else None

    async def clear_error_message(self, user_id: int) -> None:
        if self.redis:
            await self.redis.delete(self._err_key(user_id))

# Global singleton instances
_announcement_sessions = SessionManager("announcement")
_report_sessions = SessionManager("report")

def get_announcement_sessions() -> SessionManager:
    return _announcement_sessions

def get_report_sessions() -> SessionManager:
    return _report_sessions
