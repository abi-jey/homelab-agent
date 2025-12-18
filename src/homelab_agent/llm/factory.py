"""Factory for creating LLM providers."""

from typing import Any, Callable, Optional

from homelab_agent.config import Config
from homelab_agent.llm.base import BaseLLMProvider, LLMConfigurationError


def create_llm_provider(
    config: Config,
    model: Optional[str] = None,
    tools: Optional[list[Callable[..., Any]]] = None,
) -> BaseLLMProvider:
    """Create an LLM provider based on configuration.
    
    Args:
        config: The agent configuration.
        model: Optional model override.
        tools: Optional list of tool functions for the agent.
        
    Returns:
        An initialized LLM provider.
        
    Raises:
        LLMConfigurationError: If the provider is unknown or misconfigured.
    """
    provider = config.llm_provider.lower()
    model_to_use = model or config.llm_model

    if provider == "google":
        from homelab_agent.llm.google_adk import GoogleADKProvider

        if not config.google_api_key:
            raise LLMConfigurationError(
                "Google API key is required. Set it in the configuration."
            )
        return GoogleADKProvider(
            api_key=config.google_api_key,
            model=model_to_use,
            database_path=config.database_path,
            app_name="homelab-agent",
            tools=tools,
        )

    elif provider == "openai":
        from homelab_agent.llm.openai import OpenAILLMProvider

        if not config.openai_api_key:
            raise LLMConfigurationError(
                "OpenAI API key is required. Set it in the configuration."
            )
        return OpenAILLMProvider(
            api_key=config.openai_api_key,
            model=model_to_use,
        )

    else:
        raise LLMConfigurationError(
            f"Unknown LLM provider: {provider}. "
            f"Supported providers: google, openai"
        )
