"""Tool call logging with Pydantic models.


This module provides structured logging of tool calls to a JSON file
for analysis, debugging, and auditing purposes.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolCallRecord(BaseModel):
    """Record of a single tool call."""
    
    id: str = Field(description="Unique identifier for this tool call")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the tool was called")
    tool_name: str = Field(description="Name of the tool that was called")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool")
    result: Optional[Any] = Field(default=None, description="Result returned by the tool")
    success: bool = Field(default=True, description="Whether the tool call succeeded")
    error: Optional[str] = Field(default=None, description="Error message if the call failed")
    duration_ms: Optional[float] = Field(default=None, description="Duration of the call in milliseconds")
    user_id: Optional[str] = Field(default=None, description="User who triggered the call")
    session_id: Optional[str] = Field(default=None, description="Session ID for the conversation")
    channel: Optional[str] = Field(default=None, description="Communication channel used")
    chat_id: Optional[str] = Field(default=None, description="Chat/conversation ID")
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        }
    }


class ToolCallLog(BaseModel):
    """Container for multiple tool call records."""
    
    version: str = Field(default="1.0", description="Log format version")
    created: datetime = Field(default_factory=datetime.now, description="When the log was created")
    updated: datetime = Field(default_factory=datetime.now, description="When the log was last updated")
    records: list[ToolCallRecord] = Field(default_factory=list, description="List of tool call records")
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        }
    }


class ToolCallLogger:
    """Logger for tool calls that persists to a JSON file.
    
    This class provides structured logging of all tool calls made by the agent,
    storing them in a JSON file for later analysis.
    
    The log file is rotated when it exceeds max_records, keeping only the
    most recent records.
    """
    
    def __init__(
        self,
        log_path: Path,
        max_records: int = 10000,
    ) -> None:
        """Initialize the tool call logger.
        
        Args:
            log_path: Path to the JSON log file.
            max_records: Maximum number of records to keep (oldest are removed).
        """
        self._log_path = log_path
        self._max_records = max_records
        self._log: Optional[ToolCallLog] = None
        self._call_counter = 0
        
        # Ensure directory exists
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing log or create new
        self._load()
    
    def _load(self) -> None:
        """Load the log from disk or create a new one."""
        if self._log_path.exists():
            try:
                with open(self._log_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._log = ToolCallLog.model_validate(data)
                self._call_counter = len(self._log.records)
                logger.debug(f"Loaded {len(self._log.records)} tool call records")
            except Exception as e:
                logger.warning(f"Could not load tool call log, creating new: {e}")
                self._log = ToolCallLog()
        else:
            self._log = ToolCallLog()
    
    def _save(self) -> None:
        """Save the log to disk."""
        if not self._log:
            return
        
        try:
            self._log.updated = datetime.now()
            
            with open(self._log_path, "w", encoding="utf-8") as f:
                json.dump(self._log.model_dump(mode="json"), f, indent=2, default=str)
            
            logger.debug(f"Saved {len(self._log.records)} tool call records")
        except Exception as e:
            logger.error(f"Failed to save tool call log: {e}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID for a tool call record."""
        self._call_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"tc_{timestamp}_{self._call_counter:06d}"
    
    def log_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Optional[Any] = None,
        success: bool = True,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> ToolCallRecord:
        """Log a tool call.
        
        Args:
            tool_name: Name of the tool.
            args: Arguments passed to the tool.
            result: Result returned by the tool (will be truncated if large).
            success: Whether the call succeeded.
            error: Error message if failed.
            duration_ms: Duration in milliseconds.
            user_id: User who triggered the call.
            session_id: Session ID.
            channel: Communication channel.
            chat_id: Chat/conversation ID.
            
        Returns:
            The created ToolCallRecord.
        """
        if not self._log:
            self._load()
        
        # Truncate large results to avoid huge log files
        truncated_result = self._truncate_result(result)
        
        record = ToolCallRecord(
            id=self._generate_id(),
            tool_name=tool_name,
            args=args,
            result=truncated_result,
            success=success,
            error=error,
            duration_ms=duration_ms,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            chat_id=chat_id,
        )
        
        self._log.records.append(record)
        
        # Rotate if needed
        if len(self._log.records) > self._max_records:
            excess = len(self._log.records) - self._max_records
            self._log.records = self._log.records[excess:]
            logger.debug(f"Rotated tool call log, removed {excess} old records")
        
        # Save to disk
        self._save()
        
        logger.info(f"Logged tool call: {tool_name} (id={record.id})")
        return record
    
    def _truncate_result(self, result: Any, max_length: int = 5000) -> Any:
        """Truncate a result if it's too large.
        
        Args:
            result: The result to potentially truncate.
            max_length: Maximum string length to keep.
            
        Returns:
            The truncated result.
        """
        if result is None:
            return None
        
        try:
            if isinstance(result, str):
                if len(result) > max_length:
                    return result[:max_length] + f"... [truncated, {len(result)} chars total]"
                return result
            elif isinstance(result, dict):
                result_str = json.dumps(result, default=str)
                if len(result_str) > max_length:
                    return {"_truncated": True, "_summary": result_str[:max_length] + "..."}
                return result
            elif isinstance(result, (list, tuple)):
                result_str = json.dumps(list(result), default=str)
                if len(result_str) > max_length:
                    return {"_truncated": True, "_type": type(result).__name__, "_length": len(result)}
                return result
            else:
                result_str = str(result)
                if len(result_str) > max_length:
                    return result_str[:max_length] + f"... [truncated]"
                return result_str
        except Exception:
            return str(result)[:max_length]
    
    def get_recent(self, count: int = 100) -> list[ToolCallRecord]:
        """Get the most recent tool call records.
        
        Args:
            count: Number of records to return.
            
        Returns:
            List of recent ToolCallRecords.
        """
        if not self._log:
            return []
        return self._log.records[-count:]
    
    def get_by_tool(self, tool_name: str, count: int = 100) -> list[ToolCallRecord]:
        """Get recent records for a specific tool.
        
        Args:
            tool_name: Name of the tool to filter by.
            count: Maximum number of records to return.
            
        Returns:
            List of ToolCallRecords for the specified tool.
        """
        if not self._log:
            return []
        matching = [r for r in self._log.records if r.tool_name == tool_name]
        return matching[-count:]
    
    def get_by_user(self, user_id: str, count: int = 100) -> list[ToolCallRecord]:
        """Get recent records for a specific user.
        
        Args:
            user_id: User ID to filter by.
            count: Maximum number of records to return.
            
        Returns:
            List of ToolCallRecords for the specified user.
        """
        if not self._log:
            return []
        matching = [r for r in self._log.records if r.user_id == user_id]
        return matching[-count:]


# Module-level logger instance (initialized by agent)
_tool_logger: Optional[ToolCallLogger] = None


def get_tool_logger() -> Optional[ToolCallLogger]:
    """Get the global tool call logger instance."""
    return _tool_logger


def set_tool_logger(logger: ToolCallLogger) -> None:
    """Set the global tool call logger instance."""
    global _tool_logger
    _tool_logger = logger
