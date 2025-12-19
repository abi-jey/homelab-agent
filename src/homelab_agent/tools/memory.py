"""Memory tools for the homelab agent.


This module provides tools that allow the agent to remember, recall,
and forget information using vector-based semantic search.
"""

import logging
from typing import Any, Optional

from homelab_agent.memory import MemoryService, Memory

logger = logging.getLogger(__name__)

# Module-level context for memory tools
_memory_context: dict[str, Any] = {}


def set_memory_context(
    memory_service: Optional[MemoryService] = None,
    user_id: Optional[str] = None,
) -> None:
    """Set the context for memory tools.
    
    This must be called before memory tools can be used,
    typically at the start of each message handling.
    
    Args:
        memory_service: The MemoryService instance to use.
        user_id: The current user's ID.
        
    """
    global _memory_context
    _memory_context = {
        "memory_service": memory_service,
        "user_id": user_id,
    }
    logger.debug(f"Memory context set: user_id={user_id}")


def clear_memory_context() -> None:
    """Clear the memory context after message handling.
    
    """
    global _memory_context
    _memory_context = {}


async def remember(
    content: str,
    tags: Optional[list[str]] = None,
) -> str:
    """Remember information for later recall.
    
    Use this tool to store information that you want to remember
    for future conversations with this user. The information is
    stored with embeddings for semantic search.
    
    **When to use:**
    - User explicitly asks you to remember something
    - Important preferences, names, or facts are mentioned
    - You learn something that will be useful in future conversations
    
    Args:
        content: The information to remember. Be specific and include
            relevant context so you can recall it effectively later.
        tags: Optional list of tags to categorize the memory.
            Examples: ["preference", "project", "contact", "fact"]
    
    Returns:
        Confirmation that the memory was stored.
        
    """
    global _memory_context
    
    memory_service = _memory_context.get("memory_service")
    user_id = _memory_context.get("user_id")
    
    if not memory_service:
        return "Error: Memory service is not configured."
    
    if not user_id:
        return "Error: User context is not available."
    
    try:
        memory = await memory_service.remember(user_id, content, tags)
        tag_str = f" (tags: {', '.join(memory.tags)})" if memory.tags else ""
        return f"✅ Remembered: {content[:50]}...{tag_str}"
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        return f"Error: Failed to remember: {e}"


async def recall(
    query: str,
    limit: int = 5,
) -> str:
    """Recall memories similar to the query.
    
    Use this tool to search your memories for information that
    might be relevant to the current conversation. Uses semantic
    search to find the most similar memories.
    
    **When to use:**
    - You need to remember something about the user
    - User asks about something you might have discussed before
    - You need context from previous conversations
    
    Args:
        query: What to search for. Be descriptive about what
            information you're looking for.
        limit: Maximum number of memories to return (1-20).
    
    Returns:
        The most relevant memories found, or a message if none found.
        
    """
    global _memory_context
    
    memory_service = _memory_context.get("memory_service")
    user_id = _memory_context.get("user_id")
    
    if not memory_service:
        return "Error: Memory service is not configured."
    
    if not user_id:
        return "Error: User context is not available."
    
    limit = max(1, min(20, limit))
    
    try:
        results = await memory_service.recall(user_id, query, limit)
        
        if not results:
            return "No memories found matching your query."
        
        memories_text = []
        for memory, similarity in results:
            tag_str = f" [{', '.join(memory.tags)}]" if memory.tags else ""
            score_pct = f"{similarity * 100:.0f}%"
            memories_text.append(
                f"- ({score_pct}) {memory.content}{tag_str}\n"
                f"  ID: {memory.id} | {memory.created_at[:10]}"
            )
        
        return f"Found {len(results)} memories:\n\n" + "\n\n".join(memories_text)
    except Exception as e:
        logger.error(f"Failed to recall memories: {e}")
        return f"Error: Failed to recall: {e}"


async def forget(
    memory_id: str,
) -> str:
    """Forget a specific memory.
    
    Use this tool to delete a specific memory that is no longer
    needed or was stored incorrectly.
    
    **When to use:**
    - User asks you to forget something
    - A memory is outdated or incorrect
    - Information is no longer relevant
    
    Args:
        memory_id: The ID of the memory to delete. Get this from
            the recall or list_memories tools.
    
    Returns:
        Confirmation that the memory was deleted.
        
    """
    global _memory_context
    
    memory_service = _memory_context.get("memory_service")
    user_id = _memory_context.get("user_id")
    
    if not memory_service:
        return "Error: Memory service is not configured."
    
    if not user_id:
        return "Error: User context is not available."
    
    try:
        deleted = await memory_service.forget(user_id, memory_id)
        
        if deleted:
            return f"✅ Memory {memory_id} has been deleted."
        else:
            return f"Memory {memory_id} not found or doesn't belong to you."
    except Exception as e:
        logger.error(f"Failed to forget memory: {e}")
        return f"Error: Failed to forget: {e}"


async def forget_all_memories() -> str:
    """Forget all memories for the current user.
    
    **WARNING**: This permanently deletes ALL your stored memories.
    Only use when the user explicitly requests to delete everything.
    
    Returns:
        Confirmation of how many memories were deleted.
        
    """
    global _memory_context
    
    memory_service = _memory_context.get("memory_service")
    user_id = _memory_context.get("user_id")
    
    if not memory_service:
        return "Error: Memory service is not configured."
    
    if not user_id:
        return "Error: User context is not available."
    
    try:
        count = await memory_service.forget_all(user_id)
        return f"✅ Deleted all {count} memories."
    except Exception as e:
        logger.error(f"Failed to forget all memories: {e}")
        return f"Error: Failed to forget all: {e}"


def list_memories(
    tags: Optional[list[str]] = None,
    limit: int = 10,
) -> str:
    """List stored memories, optionally filtered by tags.
    
    Use this to see what memories are stored for the user.
    Unlike recall, this doesn't do semantic search - it just
    lists memories in chronological order.
    
    **When to use:**
    - User wants to see what you remember about them
    - You need to browse memories by category/tag
    - You need memory IDs for deleting specific memories
    
    Args:
        tags: Optional list of tags to filter by (shows memories
            that have ANY of the specified tags).
        limit: Maximum number of memories to return (1-50).
    
    Returns:
        List of memories with their IDs and tags.
        
    """
    global _memory_context
    
    memory_service = _memory_context.get("memory_service")
    user_id = _memory_context.get("user_id")
    
    if not memory_service:
        return "Error: Memory service is not configured."
    
    if not user_id:
        return "Error: User context is not available."
    
    limit = max(1, min(50, limit))
    
    try:
        memories = memory_service.list_memories(user_id, tags=tags, limit=limit)
        
        if not memories:
            if tags:
                return f"No memories found with tags: {', '.join(tags)}"
            return "No memories stored yet."
        
        memories_text = []
        for memory in memories:
            tag_str = f" [{', '.join(memory.tags)}]" if memory.tags else ""
            memories_text.append(
                f"- {memory.content[:100]}{'...' if len(memory.content) > 100 else ''}{tag_str}\n"
                f"  ID: {memory.id} | {memory.created_at[:10]}"
            )
        
        total = memory_service.get_memory_count(user_id)
        showing = len(memories)
        header = f"Showing {showing} of {total} memories"
        if tags:
            header += f" (filtered by: {', '.join(tags)})"
        
        return f"{header}:\n\n" + "\n\n".join(memories_text)
    except Exception as e:
        logger.error(f"Failed to list memories: {e}")
        return f"Error: Failed to list memories: {e}"


def search_memories(
    query: str,
    limit: int = 10,
) -> str:
    """Search memories by text content (exact match).
    
    Use this for faster, simpler searches when you're looking
    for specific text rather than semantic similarity.
    
    **When to use:**
    - Looking for specific words or phrases
    - Need faster results than semantic search
    - Looking for exact matches
    
    Args:
        query: The text to search for (case-insensitive).
        limit: Maximum number of results (1-50).
    
    Returns:
        Memories containing the search text.
        
    """
    global _memory_context
    
    memory_service = _memory_context.get("memory_service")
    user_id = _memory_context.get("user_id")
    
    if not memory_service:
        return "Error: Memory service is not configured."
    
    if not user_id:
        return "Error: User context is not available."
    
    limit = max(1, min(50, limit))
    
    try:
        memories = memory_service.search_by_text(user_id, query, limit)
        
        if not memories:
            return f"No memories found containing: '{query}'"
        
        memories_text = []
        for memory in memories:
            tag_str = f" [{', '.join(memory.tags)}]" if memory.tags else ""
            memories_text.append(
                f"- {memory.content[:100]}{'...' if len(memory.content) > 100 else ''}{tag_str}\n"
                f"  ID: {memory.id} | {memory.created_at[:10]}"
            )
        
        return f"Found {len(memories)} memories containing '{query}':\n\n" + "\n\n".join(memories_text)
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        return f"Error: Failed to search: {e}"
