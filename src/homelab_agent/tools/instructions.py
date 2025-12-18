"""Instruction management tool for the homelab agent.

This module provides tools that allow the agent to update its own
system instructions at runtime. Instructions are persisted to a JSON file.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class InstructionUpdate(BaseModel):
    """A record of an instruction update."""
    
    timestamp: datetime = Field(default_factory=datetime.now)
    previous_instruction: Optional[str] = None
    new_instruction: str
    reason: Optional[str] = None


class InstructionData(BaseModel):
    """Persisted instruction data."""
    
    current_instruction: str = Field(..., description="The current system instruction")
    default_instruction: str = Field(..., description="The original default instruction")
    last_updated: Optional[datetime] = None
    update_history: list[InstructionUpdate] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class InstructionManager:
    """Manages agent instructions with persistence.
    
    Stores instructions in a JSON file and maintains update history.
    """
    
    def __init__(self, data_path: Path, default_instruction: str) -> None:
        """Initialize the instruction manager.
        
        Args:
            data_path: Path to the JSON file for storing instructions.
            default_instruction: The default system instruction to use.
        """
        self._data_path = data_path
        self._default_instruction = default_instruction
        self._data: Optional[InstructionData] = None
    
    def _load(self) -> InstructionData:
        """Load instruction data from disk."""
        if self._data is not None:
            return self._data
        
        if self._data_path.exists():
            try:
                with open(self._data_path) as f:
                    raw_data = json.load(f)
                self._data = InstructionData.model_validate(raw_data)
                logger.info("Loaded instructions from disk")
            except Exception as e:
                logger.error(f"Failed to load instructions: {e}")
                self._data = InstructionData(
                    current_instruction=self._default_instruction,
                    default_instruction=self._default_instruction,
                )
        else:
            self._data = InstructionData(
                current_instruction=self._default_instruction,
                default_instruction=self._default_instruction,
            )
        
        return self._data
    
    def _save(self) -> None:
        """Save instruction data to disk."""
        if self._data is None:
            return
        
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._data_path, "w") as f:
            json.dump(self._data.model_dump(mode="json"), f, indent=2, default=str)
        logger.info("Saved instructions to disk")
    
    def get_instruction(self) -> str:
        """Get the current instruction."""
        data = self._load()
        return data.current_instruction
    
    def update_instruction(self, new_instruction: str, reason: Optional[str] = None) -> None:
        """Update the current instruction.
        
        Args:
            new_instruction: The new instruction to set.
            reason: Optional reason for the update.
        """
        data = self._load()
        
        update = InstructionUpdate(
            previous_instruction=data.current_instruction,
            new_instruction=new_instruction,
            reason=reason,
        )
        
        data.current_instruction = new_instruction
        data.last_updated = datetime.now()
        data.update_history.append(update)
        
        # Keep only last 10 updates
        if len(data.update_history) > 10:
            data.update_history = data.update_history[-10:]
        
        self._save()
        logger.info(f"Updated instruction (reason: {reason})")
    
    def reset_instruction(self) -> None:
        """Reset instruction to the default."""
        data = self._load()
        
        update = InstructionUpdate(
            previous_instruction=data.current_instruction,
            new_instruction=data.default_instruction,
            reason="Reset to default",
        )
        
        data.current_instruction = data.default_instruction
        data.last_updated = datetime.now()
        data.update_history.append(update)
        
        self._save()
        logger.info("Reset instruction to default")
    
    def get_history(self) -> list[InstructionUpdate]:
        """Get the update history."""
        data = self._load()
        return data.update_history


# Tool context for instruction management
class InstructionToolContext:
    """Context for instruction tools."""
    
    manager: Optional[InstructionManager] = None


_tool_context = InstructionToolContext()


def set_instruction_context(manager: InstructionManager) -> None:
    """Set the instruction manager for tools."""
    _tool_context.manager = manager


def update_my_instructions(
    new_instruction: str,
    reason: Optional[str] = None,
) -> dict:
    """Update the agent's system instructions.
    
    Use this tool when you need to modify your own behavior, personality,
    or capabilities. The new instruction will persist across restarts.
    
    Be careful: This changes how you behave for ALL future conversations.
    Only use this when the user explicitly asks you to change your behavior
    or when you need to add new capabilities.
    
    Args:
        new_instruction: The complete new system instruction. This should be
            a comprehensive description of who you are and how you should behave.
            It replaces your current instruction entirely.
        reason: Why you are updating your instructions. This is logged for
            audit purposes.
    
    Returns:
        A dictionary with:
        - status: "success" or "error"
        - message: Confirmation or error message
        - instruction_preview: First 200 chars of the new instruction
    """
    if _tool_context.manager is None:
        return {
            "status": "error",
            "message": "Instruction manager is not configured.",
        }
    
    if not new_instruction or len(new_instruction.strip()) < 50:
        return {
            "status": "error",
            "message": "Instruction must be at least 50 characters long.",
        }
    
    try:
        _tool_context.manager.update_instruction(new_instruction.strip(), reason)
        return {
            "status": "success",
            "message": "Instructions updated successfully. Changes will take effect on next conversation.",
            "instruction_preview": new_instruction[:200] + "..." if len(new_instruction) > 200 else new_instruction,
            "reason": reason,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update instructions: {e}",
        }


def get_my_instructions() -> dict:
    """Get the current system instructions.
    
    Use this to see what your current instructions are before modifying them.
    
    Returns:
        A dictionary with:
        - status: "success" or "error"
        - current_instruction: Your current system instruction
        - last_updated: When instructions were last modified
    """
    if _tool_context.manager is None:
        return {
            "status": "error",
            "message": "Instruction manager is not configured.",
        }
    
    try:
        data = _tool_context.manager._load()
        return {
            "status": "success",
            "current_instruction": data.current_instruction,
            "default_instruction": data.default_instruction,
            "last_updated": data.last_updated.isoformat() if data.last_updated else None,
            "is_modified": data.current_instruction != data.default_instruction,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get instructions: {e}",
        }


def reset_my_instructions() -> dict:
    """Reset instructions to the default.
    
    Use this to undo all instruction changes and return to the original
    default behavior.
    
    Returns:
        A dictionary with:
        - status: "success" or "error"
        - message: Confirmation message
    """
    if _tool_context.manager is None:
        return {
            "status": "error",
            "message": "Instruction manager is not configured.",
        }
    
    try:
        _tool_context.manager.reset_instruction()
        return {
            "status": "success",
            "message": "Instructions reset to default. Changes will take effect on next conversation.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to reset instructions: {e}",
        }
