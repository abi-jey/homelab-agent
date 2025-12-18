"""Abstract base class for communication channels."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Awaitable, List


@dataclass
class MessagePart:
    """A single message within a bundled message."""
    
    content: str
    """The message content."""
    
    sender: Optional[str] = None
    """Sender username or display name."""
    
    timestamp: Optional[datetime] = None
    """When this message was sent."""
    
    def format(self) -> str:
        """Format this message part for display.
        
        Returns:
            Formatted string with sender and timestamp if available.
        """
        parts = []
        if self.timestamp:
            parts.append(f"[{self.timestamp.strftime('%H:%M:%S')}]")
        if self.sender:
            parts.append(f"@{self.sender}:")
        parts.append(self.content)
        return " ".join(parts)


@dataclass
class IncomingMessage:
    """An incoming message from a communication channel."""

    channel: str
    """The channel the message came from (telegram, tui, etc.)."""

    user_id: str
    """Unique identifier for the user who sent the message."""

    username: Optional[str]
    """Optional username or display name."""

    content: str
    """The message content (or combined content if bundled)."""

    chat_id: Optional[str] = None
    """Channel-specific chat/conversation ID for replies."""

    raw_data: Optional[dict] = None
    """Raw message data from the channel, if available."""
    
    bundled_messages: List[MessagePart] = field(default_factory=list)
    """List of individual messages if this is a bundled message."""
    
    is_bundled: bool = False
    """Whether this message contains multiple bundled messages."""
    
    def get_formatted_content(self) -> str:
        """Get the message content, formatted if bundled.
        
        Returns:
            The content string, with bundled messages formatted with
            sender and timestamp information.
        """
        if not self.is_bundled or not self.bundled_messages:
            return self.content
        
        # Format each bundled message
        formatted_parts = [msg.format() for msg in self.bundled_messages]
        return "\n".join(formatted_parts)


@dataclass
class OutgoingMessage:
    """An outgoing message to send through a communication channel."""

    content: str
    """The message content."""

    chat_id: Optional[str] = None
    """Target chat/conversation ID for the message."""

    user_id: Optional[str] = None
    """Target user ID (for directed messages)."""

    parse_mode: Optional[str] = None
    """Parse mode for formatting (markdown, html, etc.)."""


# Type alias for message handlers
MessageHandler = Callable[[IncomingMessage], Awaitable[str]]


class BaseCommunicationChannel(ABC):
    """Abstract base class for communication channels.
    
    All communication channels must implement this interface to ensure
    consistent behavior across different backends (Telegram, TUI, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of the channel.
        
        Returns:
            The channel name (e.g., 'telegram', 'tui').
        """
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the channel is currently running.
        
        Returns:
            True if the channel is running, False otherwise.
        """
        ...

    @abstractmethod
    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the handler for incoming messages.
        
        The handler will be called for each incoming message and should
        return the response string to send back.
        
        Args:
            handler: Async function that takes an IncomingMessage and returns a response string.
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the communication channel.
        
        This should initialize connections and begin listening for messages.
        
        Raises:
            ChannelError: If the channel fails to start.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the communication channel.
        
        This should gracefully close connections and stop listening.
        """
        ...

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message through the channel.
        
        Args:
            message: The message to send.
            
        Returns:
            True if the message was sent successfully, False otherwise.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the channel is healthy.
        
        Returns:
            True if the channel is healthy, False otherwise.
        """
        return self.is_running


class ChannelError(Exception):
    """Base exception for channel-related errors."""

    pass


class ChannelConfigurationError(ChannelError):
    """Raised when channel configuration is invalid."""

    pass


class ChannelConnectionError(ChannelError):
    """Raised when connection to the channel fails."""

    pass


class ChannelAuthorizationError(ChannelError):
    """Raised when a user is not authorized."""

    pass
