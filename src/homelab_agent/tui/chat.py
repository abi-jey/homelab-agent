"""TUI Chat interface for Homelab Agent using Textual."""

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Awaitable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown, Static, Button, Label
from textual.message import Message as TextualMessage
from textual.screen import ModalScreen

from homelab_agent.api.client import AgentAPIClient, AgentAPIError
from homelab_agent.config import Config
from homelab_agent.utils.database import SessionInfo, get_sessions_from_db

# Type alias for message handlers
AsyncMessageHandler = Callable[[str], Awaitable[str]]


class UserButton(Button):
    """Button representing a user session."""
    
    def __init__(self, session: SessionInfo) -> None:
        self.session = session
        super().__init__(str(session), id=f"user-{session.user_id}")


class UserSelectorScreen(ModalScreen[str]):
    """Modal screen for selecting a user/session."""
    
    CSS = """
    UserSelectorScreen {
        align: center middle;
    }
    
    #user-selector-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    #user-selector-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    #user-list {
        height: auto;
        max-height: 15;
        margin-bottom: 1;
    }
    
    UserButton {
        width: 100%;
        margin-bottom: 1;
    }
    
    #new-user-input {
        width: 100%;
        margin-bottom: 1;
    }
    
    #button-row {
        height: auto;
        align: center middle;
    }
    
    #cancel-button {
        margin-right: 2;
    }
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, sessions: list[SessionInfo], current_user: str) -> None:
        super().__init__()
        self.sessions = sessions
        self.current_user = current_user
    
    def compose(self) -> ComposeResult:
        with Container(id="user-selector-container"):
            yield Label("Select or Enter User ID", id="user-selector-title")
            
            with VerticalScroll(id="user-list"):
                for session in self.sessions:
                    yield UserButton(session)
            
            yield Input(
                placeholder="Or enter new user ID...",
                value=self.current_user,
                id="new-user-input",
            )
            
            with Horizontal(id="button-row"):
                yield Button("Cancel", variant="default", id="cancel-button")
                yield Button("Select", variant="primary", id="select-button")
    
    @on(UserButton.Pressed)
    def on_user_button(self, event: UserButton.Pressed) -> None:
        """Handle user button click."""
        if isinstance(event.button, UserButton):
            self.dismiss(event.button.session.user_id)
    
    @on(Button.Pressed, "#select-button")
    def on_select(self) -> None:
        """Handle select button click."""
        user_input = self.query_one("#new-user-input", Input)
        user_id = user_input.value.strip()
        if user_id:
            self.dismiss(user_id)
    
    @on(Button.Pressed, "#cancel-button")
    def on_cancel(self) -> None:
        """Handle cancel button click."""
        self.dismiss(self.current_user)
    
    def action_cancel(self) -> None:
        """Cancel selection."""
        self.dismiss(self.current_user)


class ChatMessage(Static):
    """A single chat message widget."""

    def __init__(
        self,
        content: str,
        sender: str = "user",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Initialize the chat message.
        
        Args:
            content: The message content.
            sender: Either "user" or "assistant".
            timestamp: Message timestamp, defaults to now.
        """
        self.sender = sender
        self.timestamp = timestamp or datetime.now()
        super().__init__()
        self.content = content

    def compose(self) -> ComposeResult:
        time_str = self.timestamp.strftime("%H:%M")
        if self.sender == "user":
            yield Static(
                f"[bold cyan]You[/bold cyan] [dim]{time_str}[/dim]\n{self.content}",
                classes="user-message",
            )
        else:
            yield Static(
                f"[bold green]HAL[/bold green] [dim]{time_str}[/dim]\n{self.content}",
                classes="assistant-message",
            )


class ChatInput(Input):
    """Custom input widget for chat."""

    class Submitted(TextualMessage):
        """Message sent when user submits input."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def action_submit(self) -> None:
        """Handle submit action."""
        if self.value.strip():
            self.post_message(self.Submitted(self.value))
            self.value = ""


class ChatView(VerticalScroll):
    """Scrollable container for chat messages."""

    def add_message(self, content: str, sender: str = "user") -> None:
        """Add a message to the chat view.
        
        Args:
            content: Message content.
            sender: Either "user" or "assistant".
        """
        message = ChatMessage(content, sender)
        self.mount(message)
        self.scroll_end(animate=False)


class HalTuiApp(App):
    """Main TUI application for HAL chat interface."""

    TITLE = "HAL - Homelab Agent"
    SUB_TITLE = "AI-Powered Automation"

    CSS = """
    Screen {
        background: $surface;
    }

    #chat-container {
        height: 1fr;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }

    ChatView {
        height: 1fr;
        scrollbar-gutter: stable;
    }

    ChatMessage {
        margin-bottom: 1;
        padding: 0 1;
    }

    .user-message {
        background: $primary-darken-2;
        border-left: thick $primary;
        padding-left: 1;
        margin-left: 4;
    }

    .assistant-message {
        background: $success-darken-3;
        border-left: thick $success;
        padding-left: 1;
        margin-right: 4;
    }

    #input-container {
        height: auto;
        margin: 0 1 1 1;
        padding: 0 1;
    }

    #chat-input {
        width: 100%;
    }

    #status-bar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #thinking-indicator {
        text-style: italic;
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear chat"),
        Binding("ctrl+f", "forget", "Forget session"),
        Binding("ctrl+u", "select_user", "Switch user"),
        Binding("escape", "quit", "Quit"),
    ]

    def __init__(
        self,
        config: Optional[Config] = None,
        message_handler: Optional[AsyncMessageHandler] = None,
    ) -> None:
        """Initialize the TUI app.
        
        Args:
            config: Optional configuration. If None, loads from default location.
            message_handler: Optional async function to process messages.
        """
        super().__init__()
        self.config = config
        self._message_handler = message_handler
        self._thinking = False
        self._api_client: Optional[AgentAPIClient] = None
        self._llm_provider = None  # Fallback for standalone mode
        self._user_id = "tui_user"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            ChatView(id="chat-view"),
            id="chat-container",
        )
        yield Horizontal(
            ChatInput(
                placeholder="Type your message... (Enter to send, Ctrl+C to quit)",
                id="chat-input",
            ),
            id="input-container",
        )
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app when mounted."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(
            "Hello! I'm HAL, your homelab assistant. How can I help you today?",
            sender="assistant",
        )
        # Focus the input
        self.query_one("#chat-input", ChatInput).focus()
        
        # Load config if not provided
        if self.config is None:
            try:
                self.config = Config.load()
            except FileNotFoundError:
                self._update_status("No config found - run 'hal init' first")
                return

        # Try to connect to the daemon via HTTP API
        self._try_connect_to_daemon()

    def _try_connect_to_daemon(self) -> None:
        """Try to connect to the running daemon via HTTP API."""
        if not self.config:
            return
            
        self._api_client = AgentAPIClient(
            host="127.0.0.1",
            port=self.config.http_port,
        )
        
        # Schedule async health check
        self.call_later(self._check_daemon_connection)

    async def _check_daemon_connection(self) -> None:
        """Check if daemon is reachable and update status."""
        if not self._api_client:
            return
            
        try:
            health = await self._api_client.health()
            if health.get("status") == "ok":
                self._update_status("Connected to daemon")
                return
        except AgentAPIError:
            pass
        except Exception:
            pass
        
        # Daemon not available, fall back to standalone mode
        self._api_client = None
        self._init_standalone_mode()

    def _init_standalone_mode(self) -> None:
        """Initialize LLM provider directly for standalone mode."""
        if not self._message_handler and self.config:
            try:
                from homelab_agent.llm import create_llm_provider
                self._llm_provider = create_llm_provider(self.config)
                self._update_status(
                    f"Standalone: {self._llm_provider.name} ({self._llm_provider.model})"
                )
            except Exception as e:
                self._update_status(f"LLM init failed: {e}")
        else:
            if self.config:
                self._update_status(f"Standalone: {self.config.llm_provider}")

    def _update_status(self, message: str) -> None:
        """Update the status bar."""
        status = self.query_one("#status-bar", Static)
        status.update(f"[dim]{message}[/dim]")

    def _set_thinking(self, thinking: bool) -> None:
        """Set the thinking indicator."""
        self._thinking = thinking
        if thinking:
            self._update_status("HAL is thinking...")
        else:
            if self.config:
                self._update_status(f"Connected: {self.config.llm_provider}")
            else:
                self._update_status("Ready")

    @on(ChatInput.Submitted)
    async def on_chat_submit(self, event: ChatInput.Submitted) -> None:
        """Handle chat message submission."""
        user_message = event.value.strip()
        if not user_message:
            return

        chat_view = self.query_one("#chat-view", ChatView)
        
        # Add user message
        chat_view.add_message(user_message, sender="user")
        
        # Show thinking indicator
        self._set_thinking(True)
        
        # Process the message (placeholder for actual LLM integration)
        response = await self._process_message(user_message)
        
        # Hide thinking indicator
        self._set_thinking(False)
        
        # Add assistant response
        chat_view.add_message(response, sender="assistant")

    async def _process_message(self, message: str) -> str:
        """Process a user message and get a response.
        
        Args:
            message: User's message.
            
        Returns:
            Assistant's response.
        """
        # Use custom handler if provided
        if self._message_handler:
            try:
                return await self._message_handler(message)
            except Exception as e:
                return f"Error: {e}"

        # Use API client if connected to daemon
        if self._api_client:
            try:
                response = await self._api_client.chat(
                    message=message,
                    user_id=self._user_id,
                )
                return response.get("response", "No response received")
            except AgentAPIError as e:
                return f"Daemon error: {e}"
            except Exception as e:
                return f"Connection error: {e}"

        # Use LLM provider if available (standalone mode)
        if self._llm_provider:
            try:
                from homelab_agent.llm.google_adk import GoogleADKProvider
                
                # Use session-based chat for ADK
                if isinstance(self._llm_provider, GoogleADKProvider):
                    return await self._llm_provider.chat_with_session(
                        user_id=self._user_id,
                        message=message,
                    )
                
                # Use simple generate for other providers
                from homelab_agent.llm.base import Message
                
                response = await self._llm_provider.generate(
                    prompt=message,
                    system_prompt=(
                        "You are HAL, a helpful homelab assistant. "
                        "Be concise and helpful."
                    ),
                    temperature=0.7,
                )
                return response.content
            except Exception as e:
                return f"LLM Error: {e}"
        
        # Fallback responses
        if self.config is None:
            return (
                "I'm not fully configured yet. Please run `hal init` to set up "
                "your LLM provider and other settings."
            )
        
        # Placeholder responses
        message_lower = message.lower()
        if "hello" in message_lower or "hi" in message_lower:
            return "Hello! How can I help you manage your homelab today?"
        elif "status" in message_lower:
            return (
                f"**Current Configuration:**\n"
                f"- LLM Provider: {self.config.llm_provider}\n"
                f"- Communication: {self.config.communication_channel}\n"
                f"- Runtime Dir: {self.config.runtime_dir}"
            )
        elif "help" in message_lower:
            return (
                "I can help you with:\n"
                "- **status** - Show current configuration\n"
                "- **services** - List running services\n"
                "- **logs** - View service logs\n"
                "- Any other homelab management tasks!"
            )
        else:
            return (
                f"I received your message: *{message}*\n\n"
                "LLM is not configured. Run `hal init` to set up your API keys."
            )

    def action_clear(self) -> None:
        """Clear the chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.remove_children()
        chat_view.add_message(
            "Chat cleared. How can I help you?",
            sender="assistant",
        )

    async def action_forget(self) -> None:
        """Forget the session (clear backend memory)."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.remove_children()
        
        # Forget on the daemon if connected
        if self._api_client:
            try:
                await self._api_client.forget(self._user_id)
                chat_view.add_message(
                    "Session forgotten. Starting fresh!",
                    sender="assistant",
                )
            except Exception as e:
                chat_view.add_message(
                    f"Failed to forget session: {e}",
                    sender="assistant",
                )
        # Forget on standalone ADK provider
        elif self._llm_provider:
            try:
                from homelab_agent.llm.google_adk import GoogleADKProvider
                if isinstance(self._llm_provider, GoogleADKProvider):
                    await self._llm_provider.forget_session(self._user_id)
                chat_view.add_message(
                    "Session forgotten. Starting fresh!",
                    sender="assistant",
                )
            except Exception as e:
                chat_view.add_message(
                    f"Failed to forget session: {e}",
                    sender="assistant",
                )
        else:
            chat_view.add_message(
                "Chat cleared. How can I help you?",
                sender="assistant",
            )

    async def action_select_user(self) -> None:
        """Open user/session selector dialog."""
        # Get sessions from database
        sessions = []
        if self.config:
            db_path = self.config.database_path
            sessions = get_sessions_from_db(db_path)
        
        # Show selector screen
        def on_user_selected(user_id: str) -> None:
            if user_id != self._user_id:
                self._user_id = user_id
                chat_view = self.query_one("#chat-view", ChatView)
                chat_view.remove_children()
                chat_view.add_message(
                    f"Switched to user: **{user_id}**\n\nContinuing previous conversation...",
                    sender="assistant",
                )
                self._update_status(f"User: {user_id}")
        
        def on_user_selected_wrapper(user_id: str | None) -> None:
            if user_id is not None:
                on_user_selected(user_id)
        
        self.push_screen(
            UserSelectorScreen(sessions, self._user_id),
            on_user_selected_wrapper,
        )

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()


def run_tui(config: Optional[Config] = None) -> None:
    """Run the HAL TUI application.
    
    Args:
        config: Optional configuration to use.
    """
    app = HalTuiApp(config)
    app.run()
