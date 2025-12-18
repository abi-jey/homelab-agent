"""TUI communication channel implementation."""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from homelab_agent.channels.base import (
    BaseCommunicationChannel,
    ChannelError,
    IncomingMessage,
    MessageHandler,
    OutgoingMessage,
)
from homelab_agent.config import Config

if TYPE_CHECKING:
    from homelab_agent.tui.chat import ChatView

logger = logging.getLogger(__name__)


class TUIChannel(BaseCommunicationChannel):
    """TUI (Terminal User Interface) communication channel.
    
    Provides an interactive chat interface in the terminal
    using the Textual library.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the TUI channel.
        
        Args:
            config: The agent configuration.
        """
        self._config = config
        self._message_handler: Optional[MessageHandler] = None
        self._is_running = False
        self._app = None
        self._pending_messages: list[OutgoingMessage] = []

    @property
    def name(self) -> str:
        """Get the channel name."""
        return "tui"

    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._is_running

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the handler for incoming messages."""
        self._message_handler = handler

    async def start(self) -> None:
        """Start the TUI channel.
        
        Note: The TUI is blocking and should be run in the main thread.
        Use run_blocking() for the main TUI loop.
        """
        self._is_running = True
        logger.info("TUI channel marked as ready")

    async def stop(self) -> None:
        """Stop the TUI channel."""
        self._is_running = False
        if self._app:
            self._app.exit()
        logger.info("TUI channel stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message through the TUI.
        
        Note: This queues messages to be displayed in the TUI.
        """
        if not self._is_running:
            logger.warning("Cannot send message: TUI channel is not running")
            return False

        self._pending_messages.append(message)
        
        # If app is running, display immediately
        if self._app:
            try:
                from homelab_agent.tui.chat import ChatView
                chat_view: ChatView = self._app.query_one("#chat-view")  # type: ignore
                chat_view.add_message(message.content, sender="assistant")
                return True
            except Exception as e:
                logger.error(f"Failed to display message in TUI: {e}")
                return False

        return True

    def run_blocking(self) -> None:
        """Run the TUI in blocking mode.
        
        This should be called from the main thread and will block
        until the user exits the TUI.
        """
        from homelab_agent.tui.chat import HalTuiApp

        # Create a custom app with message handler integration
        app = _TUIAppWithHandler(
            config=self._config,
            message_handler=self._message_handler,
        )
        self._app = app
        self._is_running = True

        try:
            app.run()
        finally:
            self._is_running = False
            self._app = None


class _TUIAppWithHandler:
    """Wrapper that integrates HalTuiApp with the message handler."""

    def __init__(
        self,
        config: Config,
        message_handler: Optional[MessageHandler] = None,
    ) -> None:
        """Initialize the TUI app wrapper.
        
        Args:
            config: The agent configuration.
            message_handler: Optional message handler for processing messages.
        """
        self._config = config
        self._message_handler = message_handler
        self._app = None

    def run(self) -> None:
        """Run the TUI application."""
        from homelab_agent.tui.chat import HalTuiApp

        # Create app with config
        self._app = HalTuiApp(self._config)

        # Override the message processing if we have a handler
        if self._message_handler:
            original_process = self._app._process_message

            async def enhanced_process(message: str) -> str:
                if self._message_handler:
                    incoming = IncomingMessage(
                        channel="tui",
                        user_id="local",
                        username="local_user",
                        content=message,
                    )
                    try:
                        return await self._message_handler(incoming)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        return f"Error processing message: {e}"
                return await original_process(message)

            self._app._process_message = enhanced_process

        self._app.run()

    def query_one(self, selector: str):
        """Query the app for a widget."""
        if self._app:
            return self._app.query_one(selector)
        raise RuntimeError("App is not running")

    def exit(self) -> None:
        """Exit the app."""
        if self._app:
            self._app.exit()
