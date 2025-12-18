"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    """The text content of the response."""

    model: str
    """The model that generated the response."""

    usage: dict[str, int] = field(default_factory=dict)
    """Token usage statistics (prompt_tokens, completion_tokens, total_tokens)."""

    raw_response: Optional[Any] = None
    """The raw response object from the provider, if available."""

    finish_reason: Optional[str] = None
    """Why the model stopped generating (stop, length, etc.)."""


@dataclass
class Message:
    """A message in a conversation."""

    role: str
    """The role of the message sender (system, user, assistant)."""

    content: str
    """The content of the message."""


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All LLM providers must implement this interface to ensure
    consistent behavior across different backends.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of the provider.
        
        Returns:
            The provider name (e.g., 'google', 'openai').
        """
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        """Get the current model being used.
        
        Returns:
            The model identifier.
        """
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from a single prompt.
        
        Args:
            prompt: The user prompt to send to the model.
            system_prompt: Optional system prompt to set context.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in the response.
            
        Returns:
            LLMResponse containing the generated text.
            
        Raises:
            LLMError: If generation fails.
        """
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from a conversation history.
        
        Args:
            messages: List of messages in the conversation.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in the response.
            
        Returns:
            LLMResponse containing the generated text.
            
        Raises:
            LLMError: If generation fails.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is healthy and can accept requests.
        
        Returns:
            True if the provider is healthy, False otherwise.
        """
        ...


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is invalid."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limited by the provider."""

    pass


class LLMAuthenticationError(LLMError):
    """Raised when authentication fails."""

    pass
