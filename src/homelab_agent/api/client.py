"""HTTP API client for TUI to communicate with daemon using httpx."""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class AgentAPIError(Exception):
    """Error from the agent API."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        """Initialize the error.
        
        Args:
            message: Error message.
            status_code: HTTP status code.
        """
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AgentAPIClient:
    """HTTP client for TUI-daemon communication using httpx."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the API client.
        
        Args:
            host: Daemon host.
            port: Daemon port.
            timeout: Request timeout in seconds.
        """
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "AgentAPIClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def health_check(self) -> bool:
        """Check if the daemon is healthy.
        
        Returns:
            True if healthy, False otherwise.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == "ok"
            return False
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    async def health(self) -> dict[str, Any]:
        """Get health status as a dict.
        
        Returns:
            Health status dict.
            
        Raises:
            AgentAPIError: If request fails.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            if resp.status_code == 200:
                return resp.json()
            raise AgentAPIError("Health request failed", resp.status_code)
        except httpx.RequestError as e:
            raise AgentAPIError(f"Cannot connect to daemon: {e}")

    async def get_status(self) -> dict[str, Any]:
        """Get daemon status.
        
        Returns:
            Status dict with provider, model info.
            
        Raises:
            AgentAPIError: If cannot connect to daemon.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/status")
            if resp.status_code == 200:
                return resp.json()
            raise AgentAPIError("Status request failed", resp.status_code)
        except httpx.RequestError as e:
            raise AgentAPIError(f"Cannot connect to daemon: {e}")

    async def chat(
        self,
        message: str,
        user_id: str = "tui_user",
    ) -> dict[str, Any]:
        """Send a message and get a response.
        
        Args:
            message: The message to send.
            user_id: User identifier (for session tracking).
            
        Returns:
            Response dict with 'response' key.
            
        Raises:
            AgentAPIError: If cannot connect or request fails.
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                "/chat",
                json={"message": message, "user_id": user_id},
            )
            data = resp.json()
            
            if resp.status_code == 200:
                return data
            else:
                error = data.get("detail", "Unknown error")
                raise AgentAPIError(str(error), resp.status_code)
                
        except httpx.RequestError as e:
            raise AgentAPIError(f"Cannot connect to daemon: {e}")

    async def forget(self, user_id: str = "tui_user") -> bool:
        """Forget session for a user.
        
        Args:
            user_id: User identifier.
            
        Returns:
            True if successful, False otherwise.
            
        Raises:
            AgentAPIError: If cannot connect to daemon.
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                "/forget",
                json={"user_id": user_id},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("success", False)
            return False
                
        except httpx.RequestError as e:
            raise AgentAPIError(f"Cannot connect to daemon: {e}")


def get_client(port: int = 8765) -> AgentAPIClient:
    """Create an API client with default settings.
    
    Args:
        port: The daemon port.
        
    Returns:
        An AgentAPIClient instance.
    """
    return AgentAPIClient(port=port)


# Alias for backwards compatibility
APIClient = AgentAPIClient
