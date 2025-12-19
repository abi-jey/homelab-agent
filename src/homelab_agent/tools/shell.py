"""Shell command execution tools for the homelab agent.


This module provides tools for executing shell commands safely with
configurable security constraints.
"""

import asyncio
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum command output length
MAX_OUTPUT_LENGTH = 10000

# Default timeout in seconds
DEFAULT_TIMEOUT = 60

# Commands that are always blocked for safety
BLOCKED_COMMANDS = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){:|:&};:",  # Fork bomb
    "dd if=/dev/zero of=/dev/sda",
    "chmod -R 777 /",
})

# Potentially dangerous command prefixes that require confirmation
DANGEROUS_PREFIXES = frozenset({
    "rm -rf",
    "rm -r",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "systemctl stop",
    "systemctl disable",
    "iptables -F",
    "ufw disable",
})


@dataclass
class CommandResult:
    """Result of a shell command execution."""
    
    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    blocked: bool = False
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.exit_code == 0 and not self.timed_out and not self.blocked
    
    def to_response(self) -> str:
        """Convert result to a human-readable response."""
        if self.blocked:
            return f"⛔ Command blocked: {self.error_message}"
        
        if self.timed_out:
            return f"⏱️ Command timed out after execution.\nPartial output:\n{self.stdout[:1000]}"
        
        parts = [f"Exit code: {self.exit_code}"]
        
        if self.stdout:
            output = self.stdout[:MAX_OUTPUT_LENGTH]
            if len(self.stdout) > MAX_OUTPUT_LENGTH:
                output += f"\n... (truncated, {len(self.stdout)} total chars)"
            parts.append(f"Output:\n```\n{output}\n```")
        
        if self.stderr:
            stderr = self.stderr[:2000]
            if len(self.stderr) > 2000:
                stderr += f"\n... (truncated)"
            parts.append(f"Errors:\n```\n{stderr}\n```")
        
        return "\n".join(parts)


def _is_command_blocked(command: str) -> tuple[bool, Optional[str]]:
    """Check if a command is blocked for security reasons.
    
    Args:
        command: The command to check.
        
    Returns:
        Tuple of (is_blocked, reason).
    """
    normalized = command.strip().lower()
    
    # Check exact matches
    for blocked in BLOCKED_COMMANDS:
        if blocked in normalized:
            return True, f"Command contains blocked pattern: {blocked}"
    
    return False, None


def _is_command_dangerous(command: str) -> bool:
    """Check if a command is potentially dangerous.
    
    Args:
        command: The command to check.
        
    Returns:
        True if the command is potentially dangerous.
    """
    normalized = command.strip().lower()
    
    for prefix in DANGEROUS_PREFIXES:
        if normalized.startswith(prefix):
            return True
    
    return False


async def run_shell_command(
    command: str,
    working_directory: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Execute a shell command and return the result.
    
    This tool allows you to run shell commands on the host system.
    Use with caution and only for legitimate administrative tasks.
    
    Args:
        command: The shell command to execute.
        working_directory: Optional working directory for the command.
            Defaults to the user's home directory.
        timeout: Maximum execution time in seconds (default: 60).
            Use higher values for long-running commands.
    
    Returns:
        A formatted string containing the command result including
        exit code, stdout, and stderr.
    
    Examples:
        - "ls -la /home" - List directory contents
        - "docker ps" - Show running containers
        - "systemctl status nginx" - Check service status
        - "df -h" - Show disk usage
    """
    logger.info(f"Executing shell command: {command}")
    
    # Security check
    is_blocked, reason = _is_command_blocked(command)
    if is_blocked:
        logger.warning(f"Blocked command attempt: {command} - {reason}")
        result = CommandResult(
            command=command,
            exit_code=-1,
            stdout="",
            stderr="",
            blocked=True,
            error_message=reason,
        )
        return result.to_response()
    
    # Warn about dangerous commands (but allow)
    if _is_command_dangerous(command):
        logger.warning(f"Executing potentially dangerous command: {command}")
    
    # Set working directory
    cwd = working_directory or os.path.expanduser("~")
    if not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")
    
    try:
        # Run command asynchronously
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=os.environ.copy(),
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            
            result = CommandResult(
                command=command,
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
            )
            
        except asyncio.TimeoutError:
            # Kill the process if it times out
            process.kill()
            await process.wait()
            
            result = CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                timed_out=True,
            )
        
        logger.info(f"Command completed with exit code: {result.exit_code}")
        return result.to_response()
        
    except Exception as e:
        logger.exception(f"Error executing command: {e}")
        result = CommandResult(
            command=command,
            exit_code=-1,
            stdout="",
            stderr="",
            error_message=str(e),
        )
        return f"❌ Error executing command: {e}"


async def run_shell_script(
    script: str,
    working_directory: Optional[str] = None,
    timeout: int = 300,
) -> str:
    """Execute a multi-line shell script.
    
    This tool allows you to run multi-line shell scripts for complex tasks.
    The script is executed as a bash script.
    
    Args:
        script: The shell script to execute (can be multi-line).
        working_directory: Optional working directory for the script.
        timeout: Maximum execution time in seconds (default: 300 = 5 minutes).
    
    Returns:
        A formatted string containing the script result.
    
    Example:
        ```
        #!/bin/bash
        echo "Starting backup..."
        tar -czf backup.tar.gz /data
        echo "Backup complete"
        ```
    """
    logger.info(f"Executing shell script ({len(script)} chars)")
    
    # Create a temporary script file
    import tempfile
    
    cwd = working_directory or os.path.expanduser("~")
    if not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")
    
    try:
        # Write script to temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sh",
            delete=False,
            dir=cwd,
        ) as f:
            # Add bash shebang if not present
            if not script.strip().startswith("#!"):
                f.write("#!/bin/bash\nset -e\n")
            f.write(script)
            script_path = f.name
        
        # Make executable
        os.chmod(script_path, 0o755)
        
        # Execute script
        result = await run_shell_command(
            f"bash {shlex.quote(script_path)}",
            working_directory=cwd,
            timeout=timeout,
        )
        
        # Clean up
        os.unlink(script_path)
        
        return result
        
    except Exception as e:
        logger.exception(f"Error executing script: {e}")
        return f"❌ Error executing script: {e}"
