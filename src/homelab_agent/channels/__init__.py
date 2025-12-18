"""Communication channels for Homelab Agent."""

from homelab_agent.channels.base import (
    BaseCommunicationChannel,
    ChannelAuthorizationError,
    ChannelConfigurationError,
    ChannelConnectionError,
    ChannelError,
    IncomingMessage,
    MessageHandler,
    OutgoingMessage,
)
from homelab_agent.channels.factory import create_channel

__all__ = [
    "BaseCommunicationChannel",
    "ChannelAuthorizationError",
    "ChannelConfigurationError",
    "ChannelConnectionError",
    "ChannelError",
    "IncomingMessage",
    "MessageHandler",
    "OutgoingMessage",
    "create_channel",
]
