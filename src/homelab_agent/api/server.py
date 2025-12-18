"""HTTP API server for TUI-daemon communication using FastAPI.

This provides a lightweight HTTP API that allows the TUI to communicate
with the running daemon without requiring root privileges.
"""

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from homelab_agent.channels.base import IncomingMessage
from homelab_agent.config import Config

logger = logging.getLogger(__name__)

# Type for agent message handler (takes IncomingMessage, returns str)
AgentMessageHandler = Callable[[IncomingMessage], Awaitable[str]]
# Type for forget handler
ForgetHandlerType = Callable[[str], Awaitable[bool]]


# Pydantic models for request/response
class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    message: str
    user_id: str = "tui_user"


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""
    response: str
    user_id: str


class ForgetRequest(BaseModel):
    """Request body for forget endpoint."""
    user_id: str = "tui_user"


class ForgetResponse(BaseModel):
    """Response body for forget endpoint."""
    success: bool
    user_id: str


class HealthResponse(BaseModel):
    """Response body for health endpoint."""
    status: str
    service: str = "homelab-agent"


class StatusResponse(BaseModel):
    """Response body for status endpoint."""
    status: str
    llm_provider: str
    llm_model: str


class APIServer:
    """HTTP API server for TUI-daemon communication using FastAPI."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        """Initialize the API server.
        
        Args:
            host: Host to bind to (default: localhost only).
            port: Port to bind to.
        """
        self._host = host
        self._port = port
        self._app: Optional[FastAPI] = None
        self._server: Optional[uvicorn.Server] = None
        self._server_task: Optional[asyncio.Task] = None
        
        # Handlers (simple signature: user_id, message -> response)
        self._message_handler: Optional[Callable[[str, str], Awaitable[str]]] = None
        self._forget_handler: Optional[ForgetHandlerType] = None
        
        # Status info
        self._llm_provider: str = "unknown"
        self._llm_model: str = "unknown"
        self._is_running = False

    def set_message_handler(
        self, handler: Callable[[str, str], Awaitable[str]]
    ) -> None:
        """Set the message handler.
        
        Args:
            handler: Async function that takes (user_id, message) and returns response.
        """
        self._message_handler = handler

    def set_forget_handler(self, handler: ForgetHandlerType) -> None:
        """Set the forget session handler.
        
        Args:
            handler: Async function that takes user_id and returns success boolean.
        """
        self._forget_handler = handler

    def set_status_info(self, provider: str, model: str) -> None:
        """Set status info for the status endpoint.
        
        Args:
            provider: LLM provider name.
            model: LLM model name.
        """
        self._llm_provider = provider
        self._llm_model = model

    def _build_app(self) -> FastAPI:
        """Build the FastAPI application."""
        from homelab_agent.version import __version__
        
        self._app = FastAPI(
            title="Homelab Agent API",
            description="HTTP API for TUI-daemon communication",
            version=__version__,
        )
        
        @self._app.get("/health", response_model=HealthResponse)
        async def health() -> HealthResponse:
            """Health check endpoint."""
            return HealthResponse(status="ok")

        @self._app.get("/status", response_model=StatusResponse)
        async def status() -> StatusResponse:
            """Get agent status."""
            return StatusResponse(
                status="running",
                llm_provider=self._llm_provider,
                llm_model=self._llm_model,
            )

        @self._app.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest) -> ChatResponse:
            """Send a message and get a response."""
            if not self._message_handler:
                raise HTTPException(
                    status_code=503,
                    detail="Message handler not configured",
                )

            if not request.message:
                raise HTTPException(
                    status_code=400,
                    detail="Message is required",
                )

            try:
                response = await self._message_handler(
                    request.user_id,
                    request.message,
                )
                return ChatResponse(
                    response=response,
                    user_id=request.user_id,
                )
            except Exception as e:
                logger.exception(f"Error handling chat request: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self._app.post("/forget", response_model=ForgetResponse)
        async def forget(request: ForgetRequest) -> ForgetResponse:
            """Forget session for a user."""
            if not self._forget_handler:
                raise HTTPException(
                    status_code=503,
                    detail="Forget handler not configured",
                )

            try:
                success = await self._forget_handler(request.user_id)
                return ForgetResponse(
                    success=success,
                    user_id=request.user_id,
                )
            except Exception as e:
                logger.exception(f"Error handling forget request: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        return self._app

    async def start(self) -> None:
        """Start the API server."""
        if self._is_running:
            logger.warning("API server is already running")
            return

        if not self._app:
            self._build_app()
        
        if not self._app:
            raise RuntimeError("Failed to build API application")

        config = uvicorn.Config(
            app=self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        
        # Run server in background task
        self._server_task = asyncio.create_task(self._server.serve())
        self._is_running = True
        logger.info(f"API server started on http://{self._host}:{self._port}")

    async def stop(self) -> None:
        """Stop the API server."""
        if not self._is_running:
            return

        if self._server:
            self._server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._server_task.cancel()
                    try:
                        await self._server_task
                    except asyncio.CancelledError:
                        pass
        
        self._is_running = False
        logger.info("API server stopped")

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._is_running

    @property
    def url(self) -> str:
        """Get the server URL."""
        return f"http://{self._host}:{self._port}"


class AgentAPIServer:
    """Wrapper around APIServer that integrates with the agent.
    
    This adapts the agent's IncomingMessage-based handlers to the
    simpler (user_id, message) signature used by the API server.
    """

    def __init__(
        self,
        config: Config,
        message_handler: AgentMessageHandler,
        forget_handler: ForgetHandlerType,
    ) -> None:
        """Initialize the agent API server.
        
        Args:
            config: Agent configuration.
            message_handler: Handler that takes IncomingMessage.
            forget_handler: Handler that takes user_id.
        """
        self._config = config
        self._agent_message_handler = message_handler
        self._forget_handler = forget_handler
        
        # Create the underlying API server
        self._server = APIServer(
            host="127.0.0.1",
            port=config.http_port,
        )
        
        # Set up handlers with adapters
        self._server.set_message_handler(self._handle_message)
        self._server.set_forget_handler(forget_handler)
        self._server.set_status_info(
            provider=config.llm_provider,
            model=config.llm_model,
        )

    async def _handle_message(self, user_id: str, message: str) -> str:
        """Adapt API message to IncomingMessage for the agent handler."""
        incoming = IncomingMessage(
            channel="api",
            user_id=user_id,
            username=None,
            content=message,
            raw_data={"user_id": user_id, "message": message},
        )
        return await self._agent_message_handler(incoming)

    async def start(self) -> None:
        """Start the API server."""
        await self._server.start()

    async def stop(self) -> None:
        """Stop the API server."""
        await self._server.stop()

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._server.is_running

    @property
    def url(self) -> str:
        """Get the server URL."""
        return self._server.url
