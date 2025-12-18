"""Web UI for Homelab Agent.

Provides a browser-based chat interface using React.
The static files are built from the frontend/ directory and served via FastAPI.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from homelab_agent.config import Config
from homelab_agent.utils.database import get_sessions_from_db

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
    ) -> None:
        """Initialize the Web UI.
        
        Args:
            config: Application configuration.
            message_handler: Async function to handle messages (user_id, message) -> response.
            forget_handler: Async function to forget sessions (user_id) -> success.
        """
        self.config = config
        self._message_handler = message_handler
        self._forget_handler = forget_handler
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
