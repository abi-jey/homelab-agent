"""Database utilities for the homelab agent."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SessionInfo:
    """Information about a user session."""
    
    user_id: str
    session_count: int
    last_update: str
    
    def __str__(self) -> str:
        return f"{self.user_id} ({self.session_count} sessions, last: {self.last_update})"


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
