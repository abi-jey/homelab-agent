"""Memory module for the homelab agent.


This module provides a vector-based memory system that allows the agent
to remember, recall, and forget information, with support for semantic
search using embeddings.
"""

from homelab_agent.memory.service import MemoryService, Memory

__all__ = [
    "MemoryService",
    "Memory",
]
