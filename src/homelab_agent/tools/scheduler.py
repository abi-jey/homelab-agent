"""Wake-up scheduler tool for the homelab agent.

This module provides a tool that allows the agent to schedule itself to wake up
at a future time, preserving the session context so it can continue where it left off.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ScheduledWakeUp(BaseModel):
    """A scheduled wake-up request from the agent.
    
    Stores all necessary context to resume the agent at the scheduled time.
    """
    
    id: str = Field(..., description="Unique identifier for this wake-up")
    scheduled_at: datetime = Field(..., description="When this wake-up was scheduled")
    wake_up_at: datetime = Field(..., description="When the agent should wake up")
    session_id: str = Field(..., description="Session ID to resume")
    user_id: str = Field(..., description="User ID associated with the session")
    channel: str = Field(..., description="Communication channel (telegram, tui, etc.)")
    channel_chat_id: Optional[str] = Field(default=None, description="Channel-specific chat ID")
    username: Optional[str] = Field(default=None, description="Username on the channel")
    reason: Optional[str] = Field(default=None, description="Reason for the wake-up (agent-provided)")
    completed: bool = Field(default=False, description="Whether this wake-up has been processed")
    completed_at: Optional[datetime] = Field(default=None, description="When the wake-up was processed")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WakeUpSchedulerData(BaseModel):
    """Container for all scheduled wake-ups."""
    
    wake_ups: list[ScheduledWakeUp] = Field(default_factory=list)
    
    def get_pending(self) -> list[ScheduledWakeUp]:
        """Get all pending (not completed) wake-ups."""
        return [w for w in self.wake_ups if not w.completed]
    
    def get_due(self, now: Optional[datetime] = None) -> list[ScheduledWakeUp]:
        """Get all wake-ups that are due (time has passed and not completed)."""
        if now is None:
            now = datetime.now()
        return [w for w in self.wake_ups if not w.completed and w.wake_up_at <= now]
    
    def add(self, wake_up: ScheduledWakeUp) -> None:
        """Add a new wake-up to the schedule."""
        self.wake_ups.append(wake_up)
    
    def mark_completed(self, wake_up_id: str) -> bool:
        """Mark a wake-up as completed."""
        for w in self.wake_ups:
            if w.id == wake_up_id:
                w.completed = True
                w.completed_at = datetime.now()
                return True
        return False


class WakeUpScheduler:
    """Manages scheduled wake-ups for the agent.
    
    Persists wake-up data to a JSON file using Pydantic models for validation.
    """
    
    def __init__(self, data_path: Path) -> None:
        """Initialize the scheduler.
        
        Args:
            data_path: Path to the JSON file for storing wake-up data.
        """
        self._data_path = data_path
        self._data: Optional[WakeUpSchedulerData] = None
    
    def _load(self) -> WakeUpSchedulerData:
        """Load wake-up data from disk."""
        if self._data is not None:
            return self._data
            
        if self._data_path.exists():
            try:
                with open(self._data_path) as f:
                    raw_data = json.load(f)
                self._data = WakeUpSchedulerData.model_validate(raw_data)
                logger.info(f"Loaded {len(self._data.wake_ups)} scheduled wake-ups")
            except Exception as e:
                logger.error(f"Failed to load wake-up data: {e}")
                self._data = WakeUpSchedulerData()
        else:
            self._data = WakeUpSchedulerData()
        
        return self._data
    
    def _save(self) -> None:
        """Save wake-up data to disk."""
        if self._data is None:
            return
            
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._data_path, "w") as f:
            json.dump(self._data.model_dump(mode="json"), f, indent=2, default=str)
        logger.info(f"Saved {len(self._data.wake_ups)} scheduled wake-ups")
    
    def schedule(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        wake_up_at: datetime,
        channel_chat_id: Optional[str] = None,
        username: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ScheduledWakeUp:
        """Schedule a new wake-up.
        
        Args:
            session_id: The session ID to resume.
            user_id: The user ID associated with the session.
            channel: The communication channel.
            wake_up_at: When the agent should wake up.
            channel_chat_id: Channel-specific chat ID.
            username: Username on the channel.
            reason: Agent-provided reason for the wake-up.
            
        Returns:
            The created ScheduledWakeUp object.
        """
        import uuid
        
        data = self._load()
        
        wake_up = ScheduledWakeUp(
            id=str(uuid.uuid4()),
            scheduled_at=datetime.now(),
            wake_up_at=wake_up_at,
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            channel_chat_id=channel_chat_id,
            username=username,
            reason=reason,
        )
        
        data.add(wake_up)
        self._save()
        
        logger.info(
            f"Scheduled wake-up {wake_up.id} for {wake_up_at.isoformat()} "
            f"(session={session_id}, user={user_id}, channel={channel})"
        )
        
        return wake_up
    
    def get_due_wakeups(self) -> list[ScheduledWakeUp]:
        """Get all wake-ups that are due now."""
        data = self._load()
        return data.get_due()
    
    def get_pending_wakeups(self) -> list[ScheduledWakeUp]:
        """Get all pending wake-ups."""
        data = self._load()
        return data.get_pending()
    
    def mark_completed(self, wake_up_id: str) -> bool:
        """Mark a wake-up as completed.
        
        Args:
            wake_up_id: The ID of the wake-up to mark as completed.
            
        Returns:
            True if the wake-up was found and marked, False otherwise.
        """
        data = self._load()
        result = data.mark_completed(wake_up_id)
        if result:
            self._save()
        return result
    
    def reload(self) -> None:
        """Reload data from disk."""
        self._data = None
        self._load()


# Tool context for passing data between the tool and the agent
class WakeUpToolContext:
    """Context for the wake_up_in tool.
    
    This is set by the agent before the tool is called to provide
    session and channel context.
    """
    
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    channel: Optional[str] = None
    channel_chat_id: Optional[str] = None
    username: Optional[str] = None
    scheduler: Optional[WakeUpScheduler] = None


# Global context instance - set by agent before tool invocation
_tool_context = WakeUpToolContext()


def set_wake_up_context(
    scheduler: WakeUpScheduler,
    session_id: str,
    user_id: str,
    channel: str,
    channel_chat_id: Optional[str] = None,
    username: Optional[str] = None,
) -> None:
    """Set the context for the wake_up_in tool.
    
    Must be called before each agent invocation to provide the current
    session and channel context.
    """
    _tool_context.scheduler = scheduler
    _tool_context.session_id = session_id
    _tool_context.user_id = user_id
    _tool_context.channel = channel
    _tool_context.channel_chat_id = channel_chat_id
    _tool_context.username = username


def wake_up_in(
    seconds: Optional[int] = None,
    minutes: Optional[int] = None,
    hours: Optional[int] = None,
    days: Optional[int] = None,
    reason: Optional[str] = None,
) -> dict:
    """Schedule the agent to wake up and resume this session after a delay.
    
    Use this tool when you need to follow up with the user later, check on
    something after a delay, or remind the user about something. The agent
    will wake up with full context of this conversation.
    
    At least one time parameter must be provided. Parameters are additive:
    wake_up_in(hours=1, minutes=30) means 1 hour and 30 minutes from now.
    
    Args:
        seconds: Number of seconds to wait before waking up.
        minutes: Number of minutes to wait before waking up.
        hours: Number of hours to wait before waking up.
        days: Number of days to wait before waking up.
        reason: Why you want to wake up (e.g., "check backup status", 
                "remind user about meeting"). This will be shown when you wake up.
    
    Returns:
        A dictionary with the scheduled wake-up details including:
        - status: "success" or "error"
        - wake_up_at: ISO formatted datetime when the agent will wake up
        - wake_up_id: Unique identifier for this wake-up
        - message: Human-readable confirmation message
    """
    # Validate that at least one time parameter is provided
    if all(v is None for v in [seconds, minutes, hours, days]):
        return {
            "status": "error",
            "message": "At least one time parameter (seconds, minutes, hours, days) must be provided.",
        }
    
    # Validate context is set
    if _tool_context.scheduler is None:
        return {
            "status": "error", 
            "message": "Wake-up scheduler is not configured. This is an internal error.",
        }
    
    if _tool_context.session_id is None or _tool_context.user_id is None:
        return {
            "status": "error",
            "message": "Session context is not available. This is an internal error.",
        }
    
    # Calculate wake-up time
    delay = timedelta(
        seconds=seconds or 0,
        minutes=minutes or 0,
        hours=hours or 0,
        days=days or 0,
    )
    
    if delay.total_seconds() <= 0:
        return {
            "status": "error",
            "message": "Wake-up time must be in the future.",
        }
    
    now = datetime.now()
    wake_up_at = now + delay
    
    # Schedule the wake-up
    wake_up = _tool_context.scheduler.schedule(
        session_id=_tool_context.session_id,
        user_id=_tool_context.user_id,
        channel=_tool_context.channel or "unknown",
        wake_up_at=wake_up_at,
        channel_chat_id=_tool_context.channel_chat_id,
        username=_tool_context.username,
        reason=reason,
    )
    
    # Format human-readable delay
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    delay_str = ", ".join(parts) if parts else "immediately"
    
    return {
        "status": "success",
        "wake_up_id": wake_up.id,
        "wake_up_at": wake_up.wake_up_at.isoformat(),
        "scheduled_at": wake_up.scheduled_at.isoformat(),
        "delay": delay_str,
        "reason": reason,
        "message": f"I will wake up in {delay_str} at {wake_up.wake_up_at.strftime('%Y-%m-%d %H:%M:%S')}.",
    }
