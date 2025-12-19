"""Web UI for Homelab Agent.

Provides a browser-based chat interface using React.
The static files are built from the frontend/ directory and served via FastAPI.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from homelab_agent.config import Config
from homelab_agent.memory import MemoryService
from homelab_agent.utils.database import (
    get_sessions_from_db,
    get_user_sessions,
    get_session_messages,
    get_session_message_count,
)

logger = logging.getLogger(__name__)

# Path to static files (React build output)
STATIC_DIR = Path(__file__).parent / "static"

# Type alias for message handlers
AsyncMessageHandler = Callable[[str, str], Awaitable[str]]


class WebUI:
    """Web-based chat interface for HAL.
    
    Serves the React-based frontend and handles WebSocket connections
    for real-time chat functionality.
    """
    
    def __init__(
        self,
        config: Config,
        message_handler: Optional[AsyncMessageHandler] = None,
        forget_handler: Optional[Callable[[str], Awaitable[bool]]] = None,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        """Initialize the Web UI.
        
        Args:
            config: Application configuration.
            message_handler: Async function to handle messages (user_id, message) -> response.
            forget_handler: Async function to forget sessions (user_id) -> success.
            memory_service: Optional MemoryService for memory API endpoints.
        """
        self.config = config
        self._message_handler = message_handler
        self._forget_handler = forget_handler
        self._memory_service = memory_service
        self._app = FastAPI(title="HAL - Homelab Agent")
        self._connections: dict[str, WebSocket] = {}
        
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """Set up FastAPI routes."""
        
        # WebSocket endpoint for real-time chat
        @self._app.websocket("/ws/{user_id}")
        async def websocket_endpoint(websocket: WebSocket, user_id: str):
            await websocket.accept()
            self._connections[user_id] = websocket
            logger.info(f"WebSocket connected: {user_id}")
            
            try:
                # Send welcome message
                await websocket.send_json({
                    "type": "message",
                    "sender": "assistant",
                    "content": "Hello! I'm HAL, your homelab assistant. How can I help you today?",
                    "timestamp": datetime.now().isoformat(),
                })
                
                while True:
                    data = await websocket.receive_json()
                    
                    if data.get("type") == "message":
                        content = data.get("content", "").strip()
                        if not content:
                            continue
                        
                        # Echo user message back
                        await websocket.send_json({
                            "type": "message",
                            "sender": "user",
                            "content": content,
                            "timestamp": datetime.now().isoformat(),
                        })
                        
                        # Show typing indicator
                        await websocket.send_json({
                            "type": "typing",
                            "typing": True,
                        })
                        
                        # Process message
                        if self._message_handler:
                            try:
                                response = await self._message_handler(user_id, content)
                            except Exception as e:
                                logger.error(f"Error handling message: {e}")
                                response = f"Error: {e}"
                        else:
                            response = "Message handler not configured."
                        
                        # Hide typing and send response
                        await websocket.send_json({
                            "type": "typing",
                            "typing": False,
                        })
                        
                        await websocket.send_json({
                            "type": "message",
                            "sender": "assistant",
                            "content": response,
                            "timestamp": datetime.now().isoformat(),
                        })
                    
                    elif data.get("type") == "forget":
                        if self._forget_handler:
                            try:
                                success = await self._forget_handler(user_id)
                                await websocket.send_json({
                                    "type": "message",
                                    "sender": "system",
                                    "content": "🗑️ Session cleared!" if success else "No session to clear.",
                                    "timestamp": datetime.now().isoformat(),
                                })
                            except Exception as e:
                                logger.error(f"Error in forget handler: {e}")
                                await websocket.send_json({
                                    "type": "message",
                                    "sender": "system",
                                    "content": f"Failed to clear session: {e}",
                                    "timestamp": datetime.now().isoformat(),
                                })
                        
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: {user_id}")
            finally:
                if user_id in self._connections:
                    del self._connections[user_id]
        
        # API endpoint to get available sessions
        @self._app.get("/api/sessions")
        async def get_sessions():
            db_path = self.config.database_path
            sessions = get_sessions_from_db(db_path)
            return {
                "sessions": [
                    {
                        "user_id": s.user_id,
                        "session_count": s.session_count,
                        "last_update": s.last_update,
                    }
                    for s in sessions
                ]
            }
        
        # API endpoint to get sessions for a specific user
        @self._app.get("/api/users/{user_id}/sessions")
        async def get_user_sessions_api(user_id: str):
            db_path = self.config.database_path
            sessions = get_user_sessions(db_path, user_id)
            return {
                "user_id": user_id,
                "sessions": [s.to_dict() for s in sessions],
            }
        
        # API endpoint to get messages for a specific session
        @self._app.get("/api/sessions/{session_id}/messages")
        async def get_session_messages_api(
            session_id: str,
            limit: int = 100,
            offset: int = 0,
        ):
            db_path = self.config.database_path
            messages = get_session_messages(db_path, session_id, limit, offset)
            total = get_session_message_count(db_path, session_id)
            return {
                "session_id": session_id,
                "messages": [m.to_dict() for m in messages],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        
        # API endpoint to delete a session
        @self._app.delete("/api/sessions/{session_id}")
        async def delete_session_api(session_id: str):
            db_path = self.config.database_path
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                # Delete events for the session
                cursor.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
                events_deleted = cursor.rowcount
                
                # Delete the session
                cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                session_deleted = cursor.rowcount > 0
                
                conn.commit()
                conn.close()
                
                if session_deleted:
                    return {
                        "success": True,
                        "session_id": session_id,
                        "events_deleted": events_deleted,
                    }
                else:
                    raise HTTPException(status_code=404, detail="Session not found")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to delete session: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Memory API endpoints
        
        @self._app.get("/api/memories/users")
        async def get_memory_users():
            """Get all users that have memories."""
            if not self._memory_service:
                raise HTTPException(status_code=503, detail="Memory service not available")
            users = self._memory_service.get_all_users()
            return {"users": users}
        
        @self._app.get("/api/memories/{user_id}")
        async def get_user_memories(
            user_id: str,
            limit: int = 100,
            offset: int = 0,
        ):
            """Get memories for a specific user."""
            if not self._memory_service:
                raise HTTPException(status_code=503, detail="Memory service not available")
            memories = self._memory_service.list_memories(user_id, limit=limit, offset=offset)
            total = self._memory_service.get_memory_count(user_id)
            return {
                "user_id": user_id,
                "memories": [m.to_dict() for m in memories],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        
        @self._app.delete("/api/memories/{user_id}/{memory_id}")
        async def delete_memory_api(user_id: str, memory_id: str):
            """Delete a specific memory."""
            if not self._memory_service:
                raise HTTPException(status_code=503, detail="Memory service not available")
            deleted = await self._memory_service.forget(user_id, memory_id)
            if deleted:
                return {"success": True, "memory_id": memory_id}
            raise HTTPException(status_code=404, detail="Memory not found")
        
        @self._app.delete("/api/memories/{user_id}")
        async def delete_all_user_memories(user_id: str):
            """Delete all memories for a user."""
            if not self._memory_service:
                raise HTTPException(status_code=503, detail="Memory service not available")
            count = await self._memory_service.forget_all(user_id)
            return {"success": True, "user_id": user_id, "deleted": count}
        
        # Serve index.html for the root path
        @self._app.get("/")
        async def serve_index():
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return {"error": "Frontend not built. Run 'npm run build' in webui/frontend/"}
        
        # Mount static files for assets (JS, CSS, etc.)
        if STATIC_DIR.exists():
            self._app.mount(
                "/assets",
                StaticFiles(directory=STATIC_DIR / "assets"),
                name="assets"
            )
    
    @property
    def app(self) -> FastAPI:
        """Get the FastAPI application."""
        return self._app
    
    async def send_to_user(self, user_id: str, message: str) -> bool:
        """Send a message to a specific user if connected.
        
        Args:
            user_id: The user ID.
            message: The message to send.
            
        Returns:
            True if sent, False if user not connected.
        """
        if user_id in self._connections:
            try:
                await self._connections[user_id].send_json({
                    "type": "message",
                    "sender": "assistant",
                    "content": message,
                    "timestamp": datetime.now().isoformat(),
                })
                return True
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")
        return False
