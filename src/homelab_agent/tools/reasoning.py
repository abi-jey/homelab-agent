"""Reasoning tool for the homelab agent.


This module provides a tool that allows the agent to share its reasoning
and thought process with the user via the communication channel.

The agent should use this tool frequently to:
- Explain its understanding of the user's request
- Share its plan before executing actions
- Describe why it's making certain decisions
- Provide progress updates during complex tasks
- Share conclusions after analyzing information
"""

import logging
from typing import Optional, Callable, Awaitable, Any

logger = logging.getLogger(__name__)

# Type alias for the send callback
SendCallback = Callable[[str, Optional[str]], Awaitable[None]]

# Module-level context for reasoning tool
_reasoning_context: dict[str, Any] = {}


def set_reasoning_context(
    send_callback: Optional[SendCallback] = None,
    chat_id: Optional[str] = None,
    channel: Optional[str] = None,
) -> None:
    """Set the context for the reasoning tool.
    
    This must be called before the reasoning tool can be used,
    typically at the start of each message handling.
    
    Args:
        send_callback: Async function to send messages.
            Signature: async def send(content: str, chat_id: Optional[str]) -> None
        chat_id: The chat/conversation ID to send reasoning to.
        channel: The channel name (for formatting purposes).
    """
    global _reasoning_context
    _reasoning_context = {
        "send_callback": send_callback,
        "chat_id": chat_id,
        "channel": channel,
    }
    logger.debug(f"Reasoning context set: chat_id={chat_id}, channel={channel}")


def clear_reasoning_context() -> None:
    """Clear the reasoning context after message handling."""
    global _reasoning_context
    _reasoning_context = {}


async def share_reasoning(
    reasoning: str,
    category: str = "thinking",
) -> str:
    """Share your reasoning or thought process with the user.
    
    Use this tool to communicate your internal reasoning, plans, observations,
    and thought process to the user. This helps users understand your actions
    and builds transparency and trust.
    
    **When to use this tool:**
    
    1. **Before taking action**: Explain your plan
       - "I'll first check the system logs, then analyze any errors..."
    
    2. **During analysis**: Share observations
       - "I notice the CPU usage is spiking every 5 minutes, which suggests..."
    
    3. **When making decisions**: Explain your reasoning
       - "Given the disk space is at 90%, I recommend cleaning up old logs..."
    
    4. **For complex tasks**: Provide progress updates
       - "Step 1 complete. Now moving to configure the firewall rules..."
    
    5. **When uncertain**: Share your thinking
       - "I see two possible approaches here. Option A would be faster but..."
    
    Args:
        reasoning: Your reasoning, thought process, observation, or plan.
            Be clear and concise. Use markdown formatting for readability.
            Keep it focused on what helps the user understand your actions.
        category: The type of reasoning being shared:
            - "thinking": General thought process (default)
            - "plan": Your plan of action before executing
            - "observation": Something you noticed or discovered
            - "analysis": Your analysis of data or a situation
            - "decision": Explaining why you chose a particular approach
            - "progress": Update on multi-step task progress
            - "conclusion": Final thoughts after completing analysis
    
    Returns:
        Confirmation that the reasoning was shared with the user.
    
    Examples:
        Share your plan:
            share_reasoning(
                "I'll check the Docker containers first, then review the logs "
                "for any errors in the last hour.",
                category="plan"
            )
        
        Share an observation:
            share_reasoning(
                "The nginx container restarted 3 times in the last hour. "
                "This could indicate a configuration issue or resource limits.",
                category="observation"
            )
        
        Share a decision:
            share_reasoning(
                "I'm choosing to increase the memory limit rather than optimize "
                "the code because the container is consistently hitting the limit "
                "and the host has plenty of RAM available.",
                category="decision"
            )
    
    Notes:
        - Use this tool liberally - transparency improves the user experience.
        - Keep reasoning focused and relevant to the current task.
        - Don't use this for final answers; use the regular response for that.
        - The reasoning is sent immediately to the user's chat.
    """
    global _reasoning_context
    
    logger.info(f"Agent sharing reasoning [{category}]: {reasoning[:100]}...")
    
    # Get context
    send_callback = _reasoning_context.get("send_callback")
    chat_id = _reasoning_context.get("chat_id")
    
    if not send_callback or not chat_id:
        logger.warning("Cannot share reasoning: no channel context set")
        return "⚠️ Reasoning noted (could not send to channel - no context)"
    
    # Format the reasoning message with an appropriate emoji
    category_emoji = {
        "thinking": "💭",
        "plan": "📋",
        "observation": "👀",
        "analysis": "🔍",
        "decision": "⚖️",
        "progress": "📊",
        "conclusion": "✅",
    }
    
    emoji = category_emoji.get(category, "💭")
    formatted_message = f"{emoji} **{category.title()}**\n\n{reasoning}"
    
    try:
        await send_callback(formatted_message, chat_id)
        logger.debug(f"Reasoning shared successfully: {category}")
        return f"✓ Reasoning shared with user ({category})"
    except Exception as e:
        logger.error(f"Failed to share reasoning: {e}")
        return f"⚠️ Could not share reasoning: {e}"
