"""Clone management for the homelab agent.


This module provides tools for the agent to clone itself and test
newer versions in isolated environments.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default base directory for clones
DEFAULT_CLONES_DIR = Path("/var/lib/homelab-agent/clones")

# Clone configuration filename
CLONE_CONFIG_FILE = "clone.json"


@dataclass
class CloneConfig:
    """Configuration for a clone instance."""
    
    name: str
    source: str  # Git URL or local path
    version: str  # Branch, tag, or commit
    http_port: int
    web_ui_port: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    pid: Optional[int] = None
    status: str = "stopped"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "source": self.source,
            "version": self.version,
            "http_port": self.http_port,
            "web_ui_port": self.web_ui_port,
            "created_at": self.created_at,
            "pid": self.pid,
            "status": self.status,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CloneConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            source=data["source"],
            version=data["version"],
            http_port=data["http_port"],
            web_ui_port=data["web_ui_port"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            pid=data.get("pid"),
            status=data.get("status", "stopped"),
        )


class CloneManager:
    """Manages clone instances of the homelab agent."""
    
    def __init__(
        self,
        clones_dir: Optional[Path] = None,
        base_http_port: int = 18765,
        base_webui_port: int = 18080,
    ) -> None:
        """Initialize the clone manager.
        
        Args:
            clones_dir: Directory to store clones.
            base_http_port: Starting port for HTTP API.
            base_webui_port: Starting port for Web UI.
        """
        self.clones_dir = clones_dir or DEFAULT_CLONES_DIR
        self.base_http_port = base_http_port
        self.base_webui_port = base_webui_port
    
    def _get_clone_dir(self, name: str) -> Path:
        """Get the directory for a clone."""
        return self.clones_dir / name
    
    def _get_clone_config_path(self, name: str) -> Path:
        """Get the config file path for a clone."""
        return self._get_clone_dir(name) / CLONE_CONFIG_FILE
    
    def _get_next_ports(self) -> tuple[int, int]:
        """Get the next available ports for a clone."""
        clones = self.list_clones()
        
        used_http_ports = {c.http_port for c in clones}
        used_webui_ports = {c.web_ui_port for c in clones}
        
        http_port = self.base_http_port
        while http_port in used_http_ports:
            http_port += 1
        
        webui_port = self.base_webui_port
        while webui_port in used_webui_ports:
            webui_port += 1
        
        return http_port, webui_port
    
    def list_clones(self) -> list[CloneConfig]:
        """List all clones."""
        clones = []
        
        if not self.clones_dir.exists():
            return clones
        
        for clone_dir in self.clones_dir.iterdir():
            if not clone_dir.is_dir():
                continue
            
            config_path = clone_dir / CLONE_CONFIG_FILE
            if not config_path.exists():
                continue
            
            try:
                with open(config_path) as f:
                    data = json.load(f)
                clone = CloneConfig.from_dict(data)
                
                # Update status by checking if process is running
                if clone.pid:
                    try:
                        os.kill(clone.pid, 0)
                        clone.status = "running"
                    except ProcessLookupError:
                        clone.status = "stopped"
                        clone.pid = None
                
                clones.append(clone)
                
            except Exception as e:
                logger.warning(f"Error loading clone config {config_path}: {e}")
        
        return clones
    
    def get_clone(self, name: str) -> Optional[CloneConfig]:
        """Get a clone by name."""
        config_path = self._get_clone_config_path(name)
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path) as f:
                data = json.load(f)
            clone = CloneConfig.from_dict(data)
            
            # Update status
            if clone.pid:
                try:
                    os.kill(clone.pid, 0)
                    clone.status = "running"
                except ProcessLookupError:
                    clone.status = "stopped"
                    clone.pid = None
            
            return clone
            
        except Exception as e:
            logger.error(f"Error loading clone {name}: {e}")
            return None
    
    def _save_clone_config(self, config: CloneConfig) -> None:
        """Save clone configuration."""
        config_path = self._get_clone_config_path(config.name)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
    
    async def create_clone(
        self,
        name: str,
        source: Optional[str] = None,
        version: str = "main",
    ) -> tuple[bool, str]:
        """Create a new clone.
        
        Args:
            name: Name for the clone.
            source: Git URL or local path. If None, uses current installation.
            version: Branch, tag, or commit to checkout.
            
        Returns:
            Tuple of (success, message).
        """
        logger.info(f"Creating clone: {name} from {source or 'current'} @ {version}")
        
        clone_dir = self._get_clone_dir(name)
        
        if clone_dir.exists():
            return False, f"Clone '{name}' already exists"
        
        try:
            # Create clone directory
            clone_dir.mkdir(parents=True, exist_ok=True)
            code_dir = clone_dir / "code"
            data_dir = clone_dir / "data"
            data_dir.mkdir(exist_ok=True)
            
            if source is None:
                # Clone from current installation
                # Find the source directory
                current_src = Path(__file__).parent.parent.parent.parent
                
                if (current_src / ".git").exists():
                    # It's a git repo, clone it
                    process = await asyncio.create_subprocess_exec(
                        "git", "clone", "--branch", version,
                        str(current_src), str(code_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        shutil.rmtree(clone_dir)
                        return False, f"Git clone failed: {stderr.decode()}"
                else:
                    # Copy the source
                    shutil.copytree(current_src, code_dir)
            else:
                # Clone from remote or local path
                if source.startswith(("http://", "https://", "git@")):
                    # Git clone
                    process = await asyncio.create_subprocess_exec(
                        "git", "clone", "--branch", version, source, str(code_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        shutil.rmtree(clone_dir)
                        return False, f"Git clone failed: {stderr.decode()}"
                else:
                    # Local path copy
                    source_path = Path(source).expanduser().resolve()
                    if not source_path.exists():
                        shutil.rmtree(clone_dir)
                        return False, f"Source path not found: {source}"
                    shutil.copytree(source_path, code_dir)
            
            # Create virtual environment
            logger.info(f"Creating virtual environment for {name}")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", str(clone_dir / "venv"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            
            if process.returncode != 0:
                shutil.rmtree(clone_dir)
                return False, "Failed to create virtual environment"
            
            # Install dependencies
            logger.info(f"Installing dependencies for {name}")
            pip_path = clone_dir / "venv" / "bin" / "pip"
            
            process = await asyncio.create_subprocess_exec(
                str(pip_path), "install", "-e", str(code_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                shutil.rmtree(clone_dir)
                return False, f"Failed to install dependencies: {stderr.decode()}"
            
            # Get ports
            http_port, webui_port = self._get_next_ports()
            
            # Create clone config
            config = CloneConfig(
                name=name,
                source=source or "local",
                version=version,
                http_port=http_port,
                web_ui_port=webui_port,
            )
            self._save_clone_config(config)
            
            return True, f"Clone '{name}' created (HTTP: {http_port}, WebUI: {webui_port})"
            
        except Exception as e:
            logger.exception(f"Error creating clone: {e}")
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
            return False, f"Error creating clone: {e}"
    
    async def start_clone(self, name: str) -> tuple[bool, str]:
        """Start a clone.
        
        Args:
            name: Name of the clone to start.
            
        Returns:
            Tuple of (success, message).
        """
        logger.info(f"Starting clone: {name}")
        
        config = self.get_clone(name)
        if not config:
            return False, f"Clone '{name}' not found"
        
        if config.status == "running":
            return False, f"Clone '{name}' is already running"
        
        clone_dir = self._get_clone_dir(name)
        python_path = clone_dir / "venv" / "bin" / "python"
        data_dir = clone_dir / "data"
        
        # Load main config and modify it
        try:
            from homelab_agent.config import Config
            main_config = Config.load()
            
            # Create clone-specific config
            clone_config_dir = data_dir / "config"
            clone_config_dir.mkdir(parents=True, exist_ok=True)
            clone_config_file = clone_config_dir / "config.json"
            
            clone_config_data = main_config.to_dict()
            clone_config_data["http_port"] = config.http_port
            clone_config_data["web_ui_port"] = config.web_ui_port
            clone_config_data["runtime_dir"] = str(data_dir)
            
            with open(clone_config_file, "w") as f:
                json.dump(clone_config_data, f, indent=2)
            
        except Exception as e:
            return False, f"Error creating clone config: {e}"
        
        try:
            # Start the clone process
            env = os.environ.copy()
            env["HOMELAB_AGENT_RUNTIME_DIR"] = str(data_dir)
            
            log_file = clone_dir / "clone.log"
            
            with open(log_file, "a") as log:
                process = subprocess.Popen(
                    [str(python_path), "-m", "homelab_agent.agent"],
                    cwd=str(clone_dir / "code"),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            
            # Update config
            config.pid = process.pid
            config.status = "running"
            self._save_clone_config(config)
            
            return True, f"Clone '{name}' started (PID: {process.pid}, HTTP: {config.http_port}, WebUI: {config.web_ui_port})"
            
        except Exception as e:
            logger.exception(f"Error starting clone: {e}")
            return False, f"Error starting clone: {e}"
    
    async def stop_clone(self, name: str) -> tuple[bool, str]:
        """Stop a running clone.
        
        Args:
            name: Name of the clone to stop.
            
        Returns:
            Tuple of (success, message).
        """
        logger.info(f"Stopping clone: {name}")
        
        config = self.get_clone(name)
        if not config:
            return False, f"Clone '{name}' not found"
        
        if config.status != "running" or not config.pid:
            return False, f"Clone '{name}' is not running"
        
        try:
            os.kill(config.pid, signal.SIGTERM)
            
            # Wait for process to stop
            for _ in range(10):
                await asyncio.sleep(0.5)
                try:
                    os.kill(config.pid, 0)
                except ProcessLookupError:
                    break
            else:
                # Force kill
                try:
                    os.kill(config.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            
            config.pid = None
            config.status = "stopped"
            self._save_clone_config(config)
            
            return True, f"Clone '{name}' stopped"
            
        except ProcessLookupError:
            config.pid = None
            config.status = "stopped"
            self._save_clone_config(config)
            return True, f"Clone '{name}' was already stopped"
        except Exception as e:
            logger.exception(f"Error stopping clone: {e}")
            return False, f"Error stopping clone: {e}"
    
    async def delete_clone(self, name: str) -> tuple[bool, str]:
        """Delete a clone.
        
        Args:
            name: Name of the clone to delete.
            
        Returns:
            Tuple of (success, message).
        """
        logger.info(f"Deleting clone: {name}")
        
        config = self.get_clone(name)
        if not config:
            return False, f"Clone '{name}' not found"
        
        # Stop if running
        if config.status == "running":
            await self.stop_clone(name)
        
        try:
            clone_dir = self._get_clone_dir(name)
            shutil.rmtree(clone_dir)
            return True, f"Clone '{name}' deleted"
            
        except Exception as e:
            logger.exception(f"Error deleting clone: {e}")
            return False, f"Error deleting clone: {e}"
    
    async def get_clone_logs(
        self,
        name: str,
        lines: int = 50,
    ) -> tuple[bool, str]:
        """Get logs from a clone.
        
        Args:
            name: Name of the clone.
            lines: Number of lines to return.
            
        Returns:
            Tuple of (success, logs/message).
        """
        config = self.get_clone(name)
        if not config:
            return False, f"Clone '{name}' not found"
        
        log_file = self._get_clone_dir(name) / "clone.log"
        
        if not log_file.exists():
            return False, "No logs available"
        
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                return True, "".join(all_lines[-lines:])
                
        except Exception as e:
            return False, f"Error reading logs: {e}"


# Global clone manager instance
_clone_manager: Optional[CloneManager] = None


def get_clone_manager(clones_dir: Optional[Path] = None) -> CloneManager:
    """Get the global clone manager instance."""
    global _clone_manager
    if _clone_manager is None:
        _clone_manager = CloneManager(clones_dir=clones_dir)
    return _clone_manager


# Tool functions for the agent

async def list_clones() -> str:
    """List all clone instances.
    
    This tool lists all clones of the homelab agent that have been
    created for testing purposes.
    
    Returns:
        A formatted list of clones with their status.
    """
    manager = get_clone_manager()
    clones = manager.list_clones()
    
    if not clones:
        return "No clones found. Use create_clone to create one."
    
    lines = ["📦 **Clone Instances**\n"]
    
    for clone in clones:
        status_icon = "🟢" if clone.status == "running" else "🔴"
        lines.append(
            f"{status_icon} **{clone.name}** ({clone.version})\n"
            f"   HTTP: {clone.http_port} | WebUI: {clone.web_ui_port}\n"
            f"   Created: {clone.created_at[:16]}"
        )
    
    return "\n".join(lines)


async def create_clone(
    name: str,
    source: Optional[str] = None,
    version: str = "main",
) -> str:
    """Create a clone of the homelab agent for testing.
    
    This tool creates an isolated clone of the agent that runs on
    different ports with its own database. Useful for testing new
    versions or configurations.
    
    Args:
        name: A unique name for the clone (e.g., "test-v2", "dev").
        source: Git URL or local path to clone from. If not provided,
            clones from the current installation.
        version: Git branch, tag, or commit to checkout (default: "main").
    
    Returns:
        Success or error message.
    
    Examples:
        - create_clone("test-feature", version="feature-branch")
        - create_clone("v2-test", source="https://github.com/user/repo.git", version="v2.0.0")
    """
    manager = get_clone_manager()
    success, message = await manager.create_clone(name, source, version)
    return f"{'✅' if success else '❌'} {message}"


async def start_clone(name: str) -> str:
    """Start a clone instance.
    
    This tool starts a previously created clone so it begins
    accepting messages on its configured ports.
    
    Args:
        name: The name of the clone to start.
    
    Returns:
        Success or error message.
    """
    manager = get_clone_manager()
    success, message = await manager.start_clone(name)
    return f"{'✅' if success else '❌'} {message}"


async def stop_clone(name: str) -> str:
    """Stop a running clone instance.
    
    This tool stops a running clone.
    
    Args:
        name: The name of the clone to stop.
    
    Returns:
        Success or error message.
    """
    manager = get_clone_manager()
    success, message = await manager.stop_clone(name)
    return f"{'✅' if success else '❌'} {message}"


async def delete_clone(name: str) -> str:
    """Delete a clone instance.
    
    This tool deletes a clone and all its data. The clone will
    be stopped first if it's running.
    
    Args:
        name: The name of the clone to delete.
    
    Returns:
        Success or error message.
    """
    manager = get_clone_manager()
    success, message = await manager.delete_clone(name)
    return f"{'✅' if success else '❌'} {message}"


async def get_clone_logs(
    name: str,
    lines: int = 50,
) -> str:
    """Get logs from a clone instance.
    
    This tool retrieves the recent logs from a clone to help
    debug issues.
    
    Args:
        name: The name of the clone.
        lines: Number of log lines to retrieve (default: 50).
    
    Returns:
        The log output or error message.
    """
    manager = get_clone_manager()
    success, result = await manager.get_clone_logs(name, lines)
    
    if success:
        return f"📋 **Logs for {name}** (last {lines} lines)\n```\n{result}\n```"
    else:
        return f"❌ {result}"
