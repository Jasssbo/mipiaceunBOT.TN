"""
Storage abstraction layer for webhook-based bot.
Manages user sessions, report state, and temporary data using Redis.
"""

import os
import json
import redis
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class BotStorage:
    """
    Redis-based storage for bot state management.
    Handles serialization, TTL, and connection management.
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis connection with fallback to local Redis."""
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            self.redis.ping()
            logger.info(f"Redis connected successfully to {self.redis_url}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    def _serialize_data(self, data: Any) -> str:
        """Convert Python objects to JSON string, handling datetime objects."""
        def datetime_handler(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        return json.dumps(data, default=datetime_handler, ensure_ascii=False)
    
    def _deserialize_data(self, data: str) -> Any:
        """Convert JSON string back to Python objects."""
        return json.loads(data)
    
    # ========== USER SESSION MANAGEMENT ==========
    
    def get_user_session(self, user_id: int) -> Optional[Dict[Any, Any]]:
        """Get user compilation session data."""
        try:
            data = self.redis.get(f"user_session:{user_id}")
            if data:
                return self._deserialize_data(data)
            return None
        except Exception as e:
            logger.error(f"Error getting user session {user_id}: {e}")
            return None
    
    def set_user_session(self, user_id: int, data: Dict[Any, Any], ttl: int = 1800) -> bool:
        """Set user compilation session with TTL (default 30 minutes)."""
        try:
            serialized = self._serialize_data(data)
            return self.redis.setex(f"user_session:{user_id}", ttl, serialized)
        except Exception as e:
            logger.error(f"Error setting user session {user_id}: {e}")
            return False
    
    def delete_user_session(self, user_id: int) -> bool:
        """Delete user compilation session."""
        try:
            return bool(self.redis.delete(f"user_session:{user_id}"))
        except Exception as e:
            logger.error(f"Error deleting user session {user_id}: {e}")
            return False
    
    def extend_user_session_ttl(self, user_id: int, ttl: int = 1800) -> bool:
        """Extend TTL of existing user session."""
        try:
            return self.redis.expire(f"user_session:{user_id}", ttl)
        except Exception as e:
            logger.error(f"Error extending user session TTL {user_id}: {e}")
            return False
    
    # ========== REPORT STATE MANAGEMENT ==========
    
    def get_report_state(self, user_id: int) -> Optional[Dict[Any, Any]]:
        """Get user report submission state."""
        try:
            data = self.redis.get(f"report_state:{user_id}")
            if data:
                return self._deserialize_data(data)
            return None
        except Exception as e:
            logger.error(f"Error getting report state {user_id}: {e}")
            return None
    
    def set_report_state(self, user_id: int, data: Dict[Any, Any], ttl: int = 300) -> bool:
        """Set user report state with TTL (default 5 minutes)."""
        try:
            serialized = self._serialize_data(data)
            return self.redis.setex(f"report_state:{user_id}", ttl, serialized)
        except Exception as e:
            logger.error(f"Error setting report state {user_id}: {e}")
            return False
    
    def delete_report_state(self, user_id: int) -> bool:
        """Delete user report state."""
        try:
            return bool(self.redis.delete(f"report_state:{user_id}"))
        except Exception as e:
            logger.error(f"Error deleting report state {user_id}: {e}")
            return False
    
    # ========== ANNOUNCEMENT TIMEOUT MANAGEMENT ==========
    
    def get_announce_timeout(self, user_id: int) -> Optional[str]:
        """Get announcement timeout timestamp."""
        try:
            return self.redis.get(f"announce_timeout:{user_id}")
        except Exception as e:
            logger.error(f"Error getting announce timeout {user_id}: {e}")
            return None
    
    def set_announce_timeout(self, user_id: int, timeout_until: datetime, ttl: int = 86400) -> bool:
        """Set announcement timeout until specific datetime."""
        try:
            timeout_str = timeout_until.isoformat()
            return self.redis.setex(f"announce_timeout:{user_id}", ttl, timeout_str)
        except Exception as e:
            logger.error(f"Error setting announce timeout {user_id}: {e}")
            return False
    
    def delete_announce_timeout(self, user_id: int) -> bool:
        """Delete announcement timeout."""
        try:
            return bool(self.redis.delete(f"announce_timeout:{user_id}"))
        except Exception as e:
            logger.error(f"Error deleting announce timeout {user_id}: {e}")
            return False
    
    def is_user_in_timeout(self, user_id: int) -> bool:
        """Check if user is currently in announcement timeout."""
        timeout_str = self.get_announce_timeout(user_id)
        if not timeout_str:
            return False
        
        try:
            timeout_until = datetime.fromisoformat(timeout_str)
            return datetime.now() < timeout_until
        except Exception as e:
            logger.error(f"Error checking timeout for {user_id}: {e}")
            return False
    
    # ========== TEMPORARY DATA MANAGEMENT ==========
    
    def set_temp_data(self, key: str, data: Any, ttl: int = 3600) -> bool:
        """Set temporary data with custom TTL."""
        try:
            serialized = self._serialize_data(data)
            return self.redis.setex(f"temp:{key}", ttl, serialized)
        except Exception as e:
            logger.error(f"Error setting temp data {key}: {e}")
            return False
    
    def get_temp_data(self, key: str) -> Optional[Any]:
        """Get temporary data."""
        try:
            data = self.redis.get(f"temp:{key}")
            if data:
                return self._deserialize_data(data)
            return None
        except Exception as e:
            logger.error(f"Error getting temp data {key}: {e}")
            return None
    
    def delete_temp_data(self, key: str) -> bool:
        """Delete temporary data."""
        try:
            return bool(self.redis.delete(f"temp:{key}"))
        except Exception as e:
            logger.error(f"Error deleting temp data {key}: {e}")
            return False
    
    # ========== UTILITY METHODS ==========
    
    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.redis.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    def get_all_user_sessions(self) -> Dict[str, Dict]:
        """Get all active user sessions (for debugging/admin)."""
        try:
            keys = self.redis.keys("user_session:*")
            sessions = {}
            for key in keys:
                data = self.redis.get(key)
                if data:
                    user_id = key.split(":")[-1]
                    sessions[user_id] = self._deserialize_data(data)
            return sessions
        except Exception as e:
            logger.error(f"Error getting all user sessions: {e}")
            return {}
    
    def cleanup_expired(self) -> int:
        """Manual cleanup of expired keys (Redis handles this automatically but useful for stats)."""
        # Redis handles TTL automatically, this is mainly for monitoring
        try:
            # Count keys that would expire soon
            user_keys = self.redis.keys("user_session:*")
            report_keys = self.redis.keys("report_state:*")
            temp_keys = self.redis.keys("temp:*")
            
            total_keys = len(user_keys) + len(report_keys) + len(temp_keys)
            logger.info(f"Active keys in Redis: {total_keys} (user_sessions: {len(user_keys)}, report_states: {len(report_keys)}, temp: {len(temp_keys)})")
            return total_keys
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0

    @contextmanager
    def transaction(self):
        """Context manager for Redis transactions."""
        pipe = self.redis.pipeline()
        try:
            yield pipe
            pipe.execute()
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            raise


# Global storage instance
storage = None

def init_storage(redis_url: Optional[str] = None) -> BotStorage:
    """Initialize global storage instance."""
    global storage
    storage = BotStorage(redis_url)
    return storage

def get_storage() -> BotStorage:
    """Get global storage instance."""
    global storage
    if storage is None:
        storage = init_storage()
    return storage


# ========== COMPATIBILITY LAYER ==========
# Helper functions that mimic the original user_data/report_state behavior

def get_user_data(user_id: int) -> Dict[Any, Any]:
    """Get user data (compatibility with original user_data dict)."""
    return get_storage().get_user_session(user_id) or {}

def set_user_data(user_id: int, data: Dict[Any, Any]) -> bool:
    """Set user data (compatibility with original user_data dict)."""
    return get_storage().set_user_session(user_id, data)

def delete_user_data(user_id: int) -> bool:
    """Delete user data (compatibility with original user_data dict)."""
    return get_storage().delete_user_session(user_id)

def get_report_data(user_id: int) -> Dict[Any, Any]:
    """Get report state (compatibility with original report_state dict)."""
    return get_storage().get_report_state(user_id) or {}

def set_report_data(user_id: int, data: Dict[Any, Any]) -> bool:
    """Set report state (compatibility with original report_state dict)."""
    return get_storage().set_report_state(user_id, data)

def delete_report_data(user_id: int) -> bool:
    """Delete report state (compatibility with original report_state dict)."""
    return get_storage().delete_report_state(user_id)