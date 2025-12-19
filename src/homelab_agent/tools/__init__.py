"""Tools for the homelab agent.

"""

from homelab_agent.tools.scheduler import (
    ScheduledWakeUp,
    WakeUpScheduler,
    wake_up_in,
    set_wake_up_context,
)
from homelab_agent.tools.instructions import (
    InstructionManager,
    get_my_instructions,
    reset_my_instructions,
    set_instruction_context,
    update_my_instructions,
)
from homelab_agent.tools.shell import (
    run_shell_command,
    run_shell_script,
)
from homelab_agent.tools.files import (
    read_file,
    write_file,
    list_directory,
    delete_file,
    file_info,
    apply_patch,
)
from homelab_agent.tools.clones import (
    CloneManager,
    get_clone_manager,
    list_clones,
    create_clone,
    start_clone,
    stop_clone,
    delete_clone,
    get_clone_logs,
)
from homelab_agent.tools.reasoning import (
    share_reasoning,
    set_reasoning_context,
    clear_reasoning_context,
)
from homelab_agent.tools.memory import (
    remember,
    recall,
    forget,
    forget_all_memories,
    list_memories,
    search_memories,
    set_memory_context,
    clear_memory_context,
)

__all__ = [
    # Scheduler
    "ScheduledWakeUp",
    "WakeUpScheduler",
    "wake_up_in",
    "set_wake_up_context",
    # Instructions
    "InstructionManager",
    "get_my_instructions",
    "reset_my_instructions",
    "set_instruction_context",
    "update_my_instructions",
    # Shell
    "run_shell_command",
    "run_shell_script",
    # Files
    "read_file",
    "write_file",
    "list_directory",
    "delete_file",
    "file_info",
    "apply_patch",
    # Clones
    "CloneManager",
    "get_clone_manager",
    "list_clones",
    "create_clone",
    "start_clone",
    "stop_clone",
    "delete_clone",
    "get_clone_logs",
    # Reasoning
    "share_reasoning",
    "set_reasoning_context",
    "clear_reasoning_context",
    # Memory
    "remember",
    "recall",
    "forget",
    "forget_all_memories",
    "list_memories",
    "search_memories",
    "set_memory_context",
    "clear_memory_context",
]
