"""
Robust message service with retry logic and batch operations.
Handles message deletion, sending, and tracking across user sessions.
"""
import logging
import asyncio
from typing import List, Optional, Dict, Set
from pyrogram import errors, Client
from pyrogram.types import InlineKeyboardMarkup, Message
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    RetryError
)


class MessageService:
    """
    Centralized service for handling Telegram messages with retry logic.
    Tracks messages per user and provides batch operations.
    """
    
    def __init__(self):
        # Track messages per user for batch operations
        self._user_messages: Dict[int, Set[int]] = {}
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)),
        reraise=True
    )
    async def delete_message(self, client: Client, chat_id: int, message_id: int) -> bool:
        """
        Delete a single message with retry logic.
        
        Args:
            client: Pyrogram client
            chat_id: Chat/user ID
            message_id: Message ID to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            await client.delete_messages(chat_id, message_id)
            return True
        except errors.MessageDeleteForbidden:
            # Cannot delete this message (e.g., too old, not ours)
            logging.debug(f"Cannot delete message {message_id} in chat {chat_id}: forbidden")
            return False
        except errors.FloodWait as e:
            # Let tenacity handle the retry
            logging.warning(f"FloodWait {e.value}s when deleting message {message_id}")
            raise
        except errors.RPCError as e:
            # Let tenacity handle the retry
            logging.warning(f"RPCError when deleting message {message_id}: {e}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error deleting message {message_id}: {e}")
            return False
    
    async def delete_messages_batch(self, client: Client, chat_id: int, 
                                   message_ids: List[int]) -> int:
        """
        Delete multiple messages, handling errors gracefully.
        
        Args:
            client: Pyrogram client
            chat_id: Chat/user ID
            message_ids: List of message IDs to delete
            
        Returns:
            Number of successfully deleted messages
        """
        if not message_ids:
            return 0
        
        deleted_count = 0
        for msg_id in message_ids:
            try:
                if await self.delete_message(client, chat_id, msg_id):
                    deleted_count += 1
            except RetryError:
                # All retries exhausted
                logging.error(f"Failed to delete message {msg_id} after all retries")
            except Exception as e:
                logging.error(f"Error deleting message {msg_id}: {e}")
        
        return deleted_count
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)),
        reraise=True
    )
    async def send_message(self, client: Client, chat_id: int, text: str,
                          reply_markup: Optional[InlineKeyboardMarkup] = None) -> Optional[Message]:
        """
        Send a message with retry logic.
        
        Args:
            client: Pyrogram client
            chat_id: Chat/user ID
            text: Message text
            reply_markup: Optional inline keyboard
            
        Returns:
            Sent Message object or None on failure
        """
        try:
            msg = await client.send_message(chat_id, text, reply_markup=reply_markup)
            return msg
        except errors.FloodWait as e:
            logging.warning(f"FloodWait {e.value}s when sending message")
            raise
        except errors.RPCError as e:
            logging.warning(f"RPCError when sending message: {e}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error sending message: {e}")
            return None
    
    def track_message(self, user_id: int, message_id: int) -> None:
        """Track a message for a user for later batch operations."""
        if user_id not in self._user_messages:
            self._user_messages[user_id] = set()
        self._user_messages[user_id].add(message_id)
    
    def track_messages(self, user_id: int, message_ids: List[int]) -> None:
        """Track multiple messages for a user."""
        if user_id not in self._user_messages:
            self._user_messages[user_id] = set()
        self._user_messages[user_id].update(message_ids)
    
    def get_tracked_messages(self, user_id: int) -> List[int]:
        """Get all tracked messages for a user."""
        return list(self._user_messages.get(user_id, set()))
    
    def clear_tracked_messages(self, user_id: int) -> None:
        """Clear tracked messages for a user."""
        self._user_messages.pop(user_id, None)
    
    async def delete_tracked_messages(self, client: Client, user_id: int) -> int:
        """
        Delete all tracked messages for a user.
        
        Args:
            client: Pyrogram client
            user_id: User ID
            
        Returns:
            Number of successfully deleted messages
        """
        message_ids = self.get_tracked_messages(user_id)
        deleted = await self.delete_messages_batch(client, user_id, message_ids)
        self.clear_tracked_messages(user_id)
        return deleted
    
    async def send_and_track(self, client: Client, user_id: int, text: str,
                           reply_markup: Optional[InlineKeyboardMarkup] = None,
                           auto_track: bool = True) -> Optional[Message]:
        """
        Send a message and optionally track it for later deletion.
        
        Args:
            client: Pyrogram client
            user_id: User ID
            text: Message text
            reply_markup: Optional inline keyboard
            auto_track: If True, automatically track this message
            
        Returns:
            Sent Message object or None on failure
        """
        try:
            msg = await self.send_message(client, user_id, text, reply_markup)
            if msg and auto_track:
                self.track_message(user_id, msg.id)
            return msg
        except RetryError:
            logging.error(f"Failed to send message after all retries")
            return None


# Global singleton instance
_message_service = MessageService()


def get_message_service() -> MessageService:
    """Get the global message service instance."""
    return _message_service
