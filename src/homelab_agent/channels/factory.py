"""Factory for creating communication channels."""

from homelab_agent.channels.base import (
    BaseCommunicationChannel,
    ChannelConfigurationError,
)
from homelab_agent.config import Config


def create_channel(config: Config) -> BaseCommunicationChannel:
    """Create a communication channel based on configuration.
    
    Args:
        config: The agent configuration.
        
    Returns:
        An initialized communication channel.
        
    Raises:
        ChannelConfigurationError: If the channel is unknown or misconfigured.
    """
    channel_type = config.communication_channel.lower()

    if channel_type == "telegram":
        from homelab_agent.channels.telegram import TelegramChannel

        return TelegramChannel(config)

    elif channel_type == "tui":
        from homelab_agent.channels.tui import TUIChannel

        return TUIChannel(config)

    else:
        raise ChannelConfigurationError(
            f"Unknown communication channel: {channel_type}. "
            f"Supported channels: telegram, tui"
        )
