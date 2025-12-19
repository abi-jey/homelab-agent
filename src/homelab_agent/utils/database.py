"""Database utilities for the homelab agent.

This module provides functions to query the ADK sessions database
for session and message history information.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class SessionInfo:
    """Information about a user session."""
    
    user_id: str
    session_count: int
    last_update: str
    
    def __str__(self) -> str:
        return f"{self.user_id} ({self.session_count} sessions, last: {self.last_update})"


@dataclass
class SessionDetail:
    """Detailed information about a specific session.
    
    """
    
    id: str
    user_id: str
    app_name: str
    create_time: str
    update_time: str
    message_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "app_name": self.app_name,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "message_count": self.message_count,
        }


@dataclass
class MessageEvent:
    """A single message event from the database.
    
    """
    
    id: str
    session_id: str
    author: str
    content: Optional[str]
    timestamp: str
    role: Optional[str] = None
    text: Optional[str] = None
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    is_tool_response: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "author": self.author,
            "content": self.content,
            "timestamp": self.timestamp,
            "role": self.role,
            "text": self.text,
            "is_tool_call": self.is_tool_call,
            "tool_name": self.tool_name,
            "is_tool_response": self.is_tool_response,
        }


def get_sessions_from_db(db_path: Path) -> list[SessionInfo]:
    """Get unique users/sessions from the ADK sessions database.
    
    Args:
        db_path: Path to the SQLite sessions database.
        
    Returns:
        List of SessionInfo objects.
    """
    sessions = []
    if not db_path.exists():
        return sessions
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                user_id, 
                COUNT(*) as session_count,
                MAX(update_time) as last_update
            FROM sessions 
            WHERE app_name = 'homelab-agent'
            GROUP BY user_id
            ORDER BY last_update DESC
        """)
        
        for row in cursor.fetchall():
            sessions.append(SessionInfo(
                user_id=row[0],
                session_count=row[1],
                last_update=row[2][:16] if row[2] else "unknown",
            ))
        
        conn.close()
    except Exception:
        pass
    
    return sessions


def get_user_sessions(db_path: Path, user_id: str) -> list[SessionDetail]:
    """Get all sessions for a specific user.
    
    Args:
        db_path: Path to the SQLite sessions database.
        user_id: The user ID to get sessions for.
        
    Returns:
        List of SessionDetail objects.
        
    """
    sessions = []
    if not db_path.exists():
        return sessions
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Get sessions for the user
        cursor.execute("""
            SELECT 
                s.id,
                s.user_id,
                s.app_name,
                s.create_time,
                s.update_time,
                COUNT(e.id) as message_count
            FROM sessions s
            LEFT JOIN events e ON s.id = e.session_id 
                AND s.app_name = e.app_name 
                AND s.user_id = e.user_id
            WHERE s.app_name = 'homelab-agent' AND s.user_id = ?
            GROUP BY s.id, s.user_id, s.app_name, s.create_time, s.update_time
            ORDER BY s.update_time DESC
        """, (user_id,))
        
        for row in cursor.fetchall():
            sessions.append(SessionDetail(
                id=row[0],
                user_id=row[1],
                app_name=row[2],
                create_time=row[3][:19] if row[3] else "unknown",
                update_time=row[4][:19] if row[4] else "unknown",
                message_count=row[5] or 0,
            ))
        
        conn.close()
    except Exception:
        pass
    
    return sessions


def get_session_messages(
    db_path: Path, 
    session_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[MessageEvent]:
    """Get messages/events for a specific session.
    
    Args:
        db_path: Path to the SQLite sessions database.
        session_id: The session ID to get messages for.
        limit: Maximum number of messages to return.
        offset: Number of messages to skip.
        
    Returns:
        List of MessageEvent objects.
        
    """
    messages = []
    if not db_path.exists():
        return messages
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id,
                session_id,
                author,
                content,
                timestamp
            FROM events
            WHERE session_id = ?
            ORDER BY timestamp ASC
            LIMIT ? OFFSET ?
        """, (session_id, limit, offset))
        
        for row in cursor.fetchall():
            event_id = row[0]
            session_id = row[1]
            author = row[2]
            content_raw = row[3]
            timestamp = row[4][:19] if row[4] else "unknown"
            
            # Parse the content JSON to extract useful info
            role = None
            text = None
            is_tool_call = False
            tool_name = None
            is_tool_response = False
            
            if content_raw:
                try:
                    content_json = json.loads(content_raw)
                    role = content_json.get("role")
                    parts = content_json.get("parts", [])
                    
                    text_parts = []
                    for part in parts:
                        if isinstance(part, dict):
                            if "text" in part:
                                text_parts.append(part["text"])
                            elif "function_call" in part:
                                is_tool_call = True
                                fc = part["function_call"]
                                tool_name = fc.get("name", "unknown")
                                text_parts.append(f"[Tool Call: {tool_name}]")
                            elif "function_response" in part:
                                is_tool_response = True
                                fr = part["function_response"]
                                tool_name = fr.get("name", "unknown")
                                text_parts.append(f"[Tool Response: {tool_name}]")
                    
                    text = "\n".join(text_parts) if text_parts else None
                    
                except (json.JSONDecodeError, TypeError):
                    text = content_raw
            
            messages.append(MessageEvent(
                id=event_id,
                session_id=session_id,
                author=author,
                content=content_raw,
                timestamp=timestamp,
                role=role,
                text=text,
                is_tool_call=is_tool_call,
                tool_name=tool_name,
                is_tool_response=is_tool_response,
            ))
        
        conn.close()
    except Exception:
        pass
    
    return messages


def get_session_message_count(db_path: Path, session_id: str) -> int:
    """Get the total number of messages in a session.
    
    Args:
        db_path: Path to the SQLite sessions database.
        session_id: The session ID to count messages for.
        
    Returns:
        Total message count.
        
    """
    if not db_path.exists():
        return 0
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?",
            (session_id,)
        )
        
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0
