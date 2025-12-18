"""OpenAI LLM provider implementation."""

import logging
from typing import Optional

from homelab_agent.llm.base import (
    BaseLLMProvider,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMRateLimitError,
    LLMResponse,
    Message,
)

logger = logging.getLogger(__name__)


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI LLM provider.
    
    Uses the openai library to interact with OpenAI's
    GPT models.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
    ) -> None:
        """Initialize the OpenAI LLM provider.
        
        Args:
            api_key: OpenAI API key.
            model: Model to use (default: gpt-4o-mini).
            
        Raises:
            LLMConfigurationError: If API key is not provided.
        """
        if not api_key:
            raise LLMConfigurationError("OpenAI API key is required")

        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        """Get or create the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self._api_key)
            except ImportError:
                raise LLMConfigurationError(
                    "openai package is not installed. "
                    "Install it with: pip install openai"
                )
        return self._client

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "openai"

    @property
    def model(self) -> str:
        """Get the current model."""
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from a single prompt."""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))
        return await self.chat(messages, temperature, max_tokens)

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from a conversation history."""
        try:
            client = self._get_client()

            # Convert messages to OpenAI format
            openai_messages = [
                {"role": msg.role, "content": msg.content} for msg in messages
            ]

            # Build kwargs
            kwargs = {
                "model": self._model,
                "messages": openai_messages,
                "temperature": temperature,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            response = await client.chat.completions.create(**kwargs)

            # Extract response
            choice = response.choices[0]
            content = choice.message.content or ""

            # Build usage dict
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return LLMResponse(
                content=content,
                model=response.model,
                usage=usage,
                raw_response=response,
                finish_reason=choice.finish_reason,
            )

        except Exception as e:
            error_msg = str(e).lower()
            if "api key" in error_msg or "authentication" in error_msg:
                raise LLMAuthenticationError(f"OpenAI API authentication failed: {e}")
            if "rate limit" in error_msg:
                raise LLMRateLimitError(f"OpenAI rate limit exceeded: {e}")
            logger.exception(f"OpenAI LLM error: {e}")
            raise LLMError(f"OpenAI LLM generation failed: {e}")

    async def health_check(self) -> bool:
        """Check if the provider is healthy."""
        try:
            response = await self.generate("Say 'ok'", max_tokens=10)
            return bool(response.content)
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False
