"""Memory service with vector embeddings for the homelab agent.


This module provides a memory service that stores memories with vector
embeddings for semantic search. Memories are stored in a SQLite database
with embeddings stored as binary blobs.
"""

import json
import logging
import sqlite3
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Embedding model configuration
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768  # Smaller dimension for efficiency


@dataclass
class Memory:
    """A single memory entry.
    
    """
    
    id: str
    user_id: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert memory to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _embedding_to_bytes(embedding: list[float]) -> bytes:
    """Convert an embedding list to bytes for storage.
    
    Args:
        embedding: List of floats representing the embedding.
        
    Returns:
        Bytes representation of the embedding.
    """
    return struct.pack(f"{len(embedding)}f", *embedding)


def _bytes_to_embedding(data: bytes) -> list[float]:
    """Convert bytes back to an embedding list.
    
    Args:
        data: Bytes representation of the embedding.
        
    Returns:
        List of floats representing the embedding.
    """
    count = len(data) // 4  # 4 bytes per float
    return list(struct.unpack(f"{count}f", data))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector.
        b: Second vector.
        
    Returns:
        Cosine similarity score between -1 and 1.
    """
    if len(a) != len(b):
        return 0.0
    
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = sum(x * x for x in a) ** 0.5
    magnitude_b = sum(x * x for x in b) ** 0.5
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    
    return dot_product / (magnitude_a * magnitude_b)


class MemoryService:
    """Service for managing memories with vector embeddings.
    
    This service provides:
    - Storing memories with automatic embedding generation
    - Semantic search using cosine similarity
    - Tag-based filtering
    - User-specific memory isolation
    
    """
    
    def __init__(
        self,
        db_path: Path,
        api_key: Optional[str] = None,
    ) -> None:
        """Initialize the memory service.
        
        Args:
            db_path: Path to the SQLite database file.
            api_key: Google API key for embeddings. If None, uses GOOGLE_API_KEY env var.
        """
        self.db_path = db_path
        self._api_key = api_key
        self._client: Optional[genai.Client] = None
        
        # Ensure database exists
        self._init_database()
    
    def _get_client(self) -> genai.Client:
        """Get or create the Google GenAI client."""
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client
    
    def _init_database(self) -> None:
        """Initialize the database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Create memories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                embedding BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Create index on user_id for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_id 
            ON memories(user_id)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Memory database initialized at {self.db_path}")
    
    async def _generate_embedding(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        """Generate an embedding for the given text.
        
        Args:
            text: The text to embed.
            task_type: The task type for the embedding:
                - RETRIEVAL_DOCUMENT: For storing documents
                - RETRIEVAL_QUERY: For search queries
                
        Returns:
            The embedding as a list of floats.
        """
        try:
            client = self._get_client()
            
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSION,
                ),
            )
            
            return list(result.embeddings[0].values)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise
    
    async def remember(
        self,
        user_id: str,
        content: str,
        tags: Optional[list[str]] = None,
    ) -> Memory:
        """Store a new memory for a user.
        
        Args:
            user_id: The user ID to associate the memory with.
            content: The content to remember.
            tags: Optional tags to categorize the memory.
            
        Returns:
            The created Memory object.
        """
        import uuid
        
        memory_id = str(uuid.uuid4())
        tags = tags or []
        now = datetime.now().isoformat()
        
        # Generate embedding
        embedding = await self._generate_embedding(content, "RETRIEVAL_DOCUMENT")
        embedding_bytes = _embedding_to_bytes(embedding)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO memories (id, user_id, content, tags, embedding, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            memory_id,
            user_id,
            content,
            json.dumps(tags),
            embedding_bytes,
            now,
            now,
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Memory stored for user {user_id}: {memory_id}")
        
        return Memory(
            id=memory_id,
            user_id=user_id,
            content=content,
            tags=tags,
            created_at=now,
            updated_at=now,
        )
    
    async def recall(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.3,
    ) -> list[tuple[Memory, float]]:
        """Recall memories similar to the query.
        
        Uses semantic search with cosine similarity to find
        the most relevant memories for the user.
        
        Args:
            user_id: The user ID to search memories for.
            query: The search query.
            limit: Maximum number of memories to return.
            min_similarity: Minimum similarity threshold (0-1).
            
        Returns:
            List of (Memory, similarity_score) tuples, sorted by similarity.
        """
        # Generate query embedding
        query_embedding = await self._generate_embedding(query, "RETRIEVAL_QUERY")
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Get all memories for the user with embeddings
        cursor.execute("""
            SELECT id, user_id, content, tags, embedding, created_at, updated_at
            FROM memories
            WHERE user_id = ?
        """, (user_id,))
        
        results: list[tuple[Memory, float]] = []
        
        for row in cursor.fetchall():
            memory_id, mem_user_id, content, tags_json, embedding_bytes, created_at, updated_at = row
            
            if embedding_bytes is None:
                continue
            
            # Calculate similarity
            memory_embedding = _bytes_to_embedding(embedding_bytes)
            similarity = _cosine_similarity(query_embedding, memory_embedding)
            
            if similarity >= min_similarity:
                memory = Memory(
                    id=memory_id,
                    user_id=mem_user_id,
                    content=content,
                    tags=json.loads(tags_json) if tags_json else [],
                    created_at=created_at,
                    updated_at=updated_at,
                )
                results.append((memory, similarity))
        
        conn.close()
        
        # Sort by similarity (descending) and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    async def forget(self, user_id: str, memory_id: str) -> bool:
        """Delete a specific memory.
        
        Args:
            user_id: The user ID (for authorization).
            memory_id: The ID of the memory to delete.
            
        Returns:
            True if the memory was deleted, False if not found.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Only delete if it belongs to the user
        cursor.execute("""
            DELETE FROM memories
            WHERE id = ? AND user_id = ?
        """, (memory_id, user_id))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if deleted:
            logger.info(f"Memory {memory_id} deleted for user {user_id}")
        
        return deleted
    
    async def forget_all(self, user_id: str) -> int:
        """Delete all memories for a user.
        
        Args:
            user_id: The user ID to delete all memories for.
            
        Returns:
            Number of memories deleted.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deleted {deleted} memories for user {user_id}")
        return deleted
    
    def list_memories(
        self,
        user_id: str,
        tags: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """List memories for a user, optionally filtered by tags.
        
        Args:
            user_id: The user ID to list memories for.
            tags: Optional list of tags to filter by (any match).
            limit: Maximum number of memories to return.
            offset: Number of memories to skip.
            
        Returns:
            List of Memory objects.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_id, content, tags, created_at, updated_at
            FROM memories
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """, (user_id, limit, offset))
        
        memories = []
        for row in cursor.fetchall():
            memory_id, mem_user_id, content, tags_json, created_at, updated_at = row
            memory_tags = json.loads(tags_json) if tags_json else []
            
            # Filter by tags if specified
            if tags:
                if not any(tag in memory_tags for tag in tags):
                    continue
            
            memories.append(Memory(
                id=memory_id,
                user_id=mem_user_id,
                content=content,
                tags=memory_tags,
                created_at=created_at,
                updated_at=updated_at,
            ))
        
        conn.close()
        return memories
    
    def search_by_text(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[Memory]:
        """Search memories by text content (simple substring match).
        
        This is a simpler, faster search than recall() when
        you want exact or partial text matches rather than
        semantic similarity.
        
        Args:
            user_id: The user ID to search memories for.
            query: The text to search for (case-insensitive).
            limit: Maximum number of memories to return.
            
        Returns:
            List of matching Memory objects.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_id, content, tags, created_at, updated_at
            FROM memories
            WHERE user_id = ? AND content LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (user_id, f"%{query}%", limit))
        
        memories = []
        for row in cursor.fetchall():
            memory_id, mem_user_id, content, tags_json, created_at, updated_at = row
            memories.append(Memory(
                id=memory_id,
                user_id=mem_user_id,
                content=content,
                tags=json.loads(tags_json) if tags_json else [],
                created_at=created_at,
                updated_at=updated_at,
            ))
        
        conn.close()
        return memories
    
    def get_memory_count(self, user_id: str) -> int:
        """Get the total number of memories for a user.
        
        Args:
            user_id: The user ID to count memories for.
            
        Returns:
            Total memory count.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id = ?",
            (user_id,)
        )
        
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_all_users(self) -> list[str]:
        """Get all user IDs that have memories.
        
        Returns:
            List of user IDs.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT user_id FROM memories ORDER BY user_id")
        
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    
    def update_memory_tags(
        self,
        user_id: str,
        memory_id: str,
        tags: list[str],
    ) -> bool:
        """Update the tags for a memory.
        
        Args:
            user_id: The user ID (for authorization).
            memory_id: The ID of the memory to update.
            tags: The new tags list.
            
        Returns:
            True if updated, False if not found.
        """
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE memories
            SET tags = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (json.dumps(tags), now, memory_id, user_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return updated
