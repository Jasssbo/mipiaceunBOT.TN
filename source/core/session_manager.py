"""
Centralized session management to replace global user_data dictionary.
Handles user sessions, automatic cleanup, and prevents memory leaks.
"""
import logging
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime


class SessionManager:
    """
    Manages user sessions with automatic cleanup and memory management.
    Replaces the global user_data dictionary pattern.
    """
    
    def __init__(self):
        self._sessions: Dict[int, Dict[str, Any]] = {}
        self._cleanup_tasks: Dict[int, asyncio.Task] = {}
    
    def create_session(self, user_id: int, initial_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create or reset a session for a user."""
        if user_id in self._cleanup_tasks:
            # Cancel any existing cleanup task
            self._cleanup_tasks[user_id].cancel()
            del self._cleanup_tasks[user_id]
        
        session_data = initial_data or {}
        session_data['created_at'] = datetime.now()
        self._sessions[user_id] = session_data
        return session_data
    
    def get_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user's session data."""
        return self._sessions.get(user_id)
    
    def has_session(self, user_id: int) -> bool:
        """Check if a user has an active session."""
        return user_id in self._sessions
    
    def update_session(self, user_id: int, data: Dict[str, Any]) -> None:
        """Update a user's session data."""
        if user_id in self._sessions:
            self._sessions[user_id].update(data)
        else:
            self.create_session(user_id, data)
    
    def delete_session(self, user_id: int) -> None:
        """Delete a user's session immediately."""
        if user_id in self._cleanup_tasks:
            self._cleanup_tasks[user_id].cancel()
            del self._cleanup_tasks[user_id]
        
        self._sessions.pop(user_id, None)
    
    def schedule_cleanup(self, user_id: int, delay_seconds: int, 
                        cleanup_callback=None) -> asyncio.Task:
        """
        Schedule automatic session cleanup after a delay.
        
        Args:
            user_id: User to cleanup
            delay_seconds: Seconds to wait before cleanup
            cleanup_callback: Optional async function to call before cleanup
        
        Returns:
            The cleanup task
        """
        # Cancel any existing cleanup task
        if user_id in self._cleanup_tasks:
            self._cleanup_tasks[user_id].cancel()
        
        async def _cleanup():
            try:
                await asyncio.sleep(delay_seconds)
                if cleanup_callback:
                    await cleanup_callback(user_id)
                self.delete_session(user_id)
            except asyncio.CancelledError:
                # Task was cancelled, this is normal
                pass
            except Exception as e:
                logging.error(f"Error in session cleanup for user {user_id}: {e}")
            finally:
                if user_id in self._cleanup_tasks:
                    del self._cleanup_tasks[user_id]
        
        task = asyncio.create_task(_cleanup())
        self._cleanup_tasks[user_id] = task
        return task
    
    def cancel_cleanup(self, user_id: int) -> None:
        """Cancel a scheduled cleanup for a user."""
        if user_id in self._cleanup_tasks:
            self._cleanup_tasks[user_id].cancel()
            del self._cleanup_tasks[user_id]
    
    def get_all_user_ids(self) -> List[int]:
        """Get all active user IDs."""
        return list(self._sessions.keys())
    
    def get_session_count(self) -> int:
        """Get the count of active sessions."""
        return len(self._sessions)
    
    def clear_all(self) -> None:
        """Clear all sessions (use with caution)."""
        for task in self._cleanup_tasks.values():
            task.cancel()
        self._cleanup_tasks.clear()
        self._sessions.clear()


# Global singleton instances
_announcement_sessions = SessionManager()
_report_sessions = SessionManager()


def get_announcement_sessions() -> SessionManager:
    """Get the global announcement session manager."""
    return _announcement_sessions


def get_report_sessions() -> SessionManager:
    """Get the global report session manager."""
    return _report_sessions
