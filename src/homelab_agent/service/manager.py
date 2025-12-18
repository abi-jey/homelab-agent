"""Service manager for installing and managing the homelab agent systemd service."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from homelab_agent.config import Config


def is_dev_mode() -> bool:
    """Check if running in development mode (from source).
    
    Returns:
        True if running from source/editable install, False if installed as package.
    """
    # Check if we're in an editable install or running from source
    import homelab_agent
    package_path = Path(homelab_agent.__file__).parent
    
    # If pyproject.toml exists in parent directories, we're in dev mode
    for parent in package_path.parents:
        if (parent / "pyproject.toml").exists():
            return True
    
    return False


def get_project_root() -> Optional[Path]:
    """Get the project root directory if in dev mode.
    
    Returns:
        Path to project root, or None if not in dev mode.
    """
    import homelab_agent
    package_path = Path(homelab_agent.__file__).parent
    
    for parent in package_path.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    
    return None


class ServiceManager:
    """Manages the homelab agent systemd service."""

    SERVICE_NAME = "homelab-agent"
    SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"
    DEFAULT_RUNTIME_DIR = Path("/var/lib/homelab-agent")

    def __init__(self, config: Optional[Config] = None) -> None:
        """Initialize the service manager.
        
        Args:
            config: Configuration for the service. If None, attempts to load existing config.
        """
        self.config = config

    @classmethod
    def from_existing(cls) -> "ServiceManager":
        """Create a ServiceManager from existing installation.
        
        Returns:
            ServiceManager instance with loaded configuration.
            
        Raises:
            FileNotFoundError: If no existing installation is found.
        """
        config = Config.load()
        return cls(config)

    def _get_runtime_dir(self) -> Path:
        """Get the runtime directory."""
        if self.config and self.config.runtime_dir:
            return self.config.runtime_dir
        return self.DEFAULT_RUNTIME_DIR

    def _create_runtime_directory(self) -> None:
        """Create the runtime directory structure."""
        runtime_dir = self._get_runtime_dir()
        
        # Create directories
        dirs = [
            runtime_dir,
            runtime_dir / "venv",
            runtime_dir / "config",
            runtime_dir / "logs",
            runtime_dir / "data",
        ]
        
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _create_virtual_environment(self, wheel_path: Optional[Path] = None) -> None:
        """Create a Python virtual environment for the service.
        
        Args:
            wheel_path: Path to a wheel file to install. If None, installs from PyPI.
        """
        runtime_dir = self._get_runtime_dir()
        venv_path = runtime_dir / "venv"
        
        # Create virtual environment
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
        )
        
        # Install the package in the virtual environment
        pip_path = venv_path / "bin" / "pip"
        subprocess.run(
            [str(pip_path), "install", "--upgrade", "pip"],
            check=True,
        )
        
        # Install homelab-agent
        if wheel_path and wheel_path.exists():
            # Install from local wheel (dev mode)
            subprocess.run(
                [str(pip_path), "install", str(wheel_path)],
                check=True,
            )
        else:
            # Install from PyPI (production mode)
            subprocess.run(
                [str(pip_path), "install", "homelab-agent"],
                check=True,
            )

    def _generate_service_file(self) -> str:
        """Generate the systemd service file content."""
        runtime_dir = self._get_runtime_dir()
        python_path = runtime_dir / "venv" / "bin" / "python"
        
        service_content = f"""# Homelab Agent Service
[Unit]
Description=Homelab Agent - AI-powered homelab management
After=network.target

[Service]
Type=simple
User=homelab-agent
Group=homelab-agent
WorkingDirectory={runtime_dir}
Environment="PATH={runtime_dir}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HOMELAB_AGENT_RUNTIME_DIR={runtime_dir}"
ExecStart={python_path} -m homelab_agent.agent
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=homelab-agent

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths={runtime_dir}
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
"""
        return service_content

    def _create_system_user(self) -> None:
        """Create the system user for the service."""
        try:
            subprocess.run(
                ["id", "homelab-agent"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # User doesn't exist, create it
            subprocess.run(
                [
                    "useradd",
                    "--system",
                    "--no-create-home",
                    "--shell", "/usr/sbin/nologin",
                    "--home-dir", str(self._get_runtime_dir()),
                    "homelab-agent",
                ],
                check=True,
            )

    def _set_permissions(self) -> None:
        """Set proper permissions on the runtime directory.
        
        Sets ownership to homelab-agent:homelab-agent and adds group write
        permissions so group members can access runtime files.
        """
        runtime_dir = self._get_runtime_dir()
        subprocess.run(
            ["chown", "-R", "homelab-agent:homelab-agent", str(runtime_dir)],
            check=True,
        )
        # Add group write permissions for homelab-agent group members
        subprocess.run(
            ["chmod", "-R", "g+w", str(runtime_dir)],
            check=True,
        )

    def install(self) -> None:
        """Install the homelab agent as a systemd service."""
        if os.geteuid() != 0:
            raise PermissionError("Installation requires root privileges. Run with sudo.")

        # Create runtime directory
        self._create_runtime_directory()
        
        # Save configuration
        if self.config:
            self.config.save()
        
        # Create system user
        self._create_system_user()
        
        # Create virtual environment and install package
        self._create_virtual_environment()
        
        # Set permissions
        self._set_permissions()
        
        # Write service file
        service_content = self._generate_service_file()
        with open(self.SERVICE_FILE, "w") as f:
            f.write(service_content)
        
        # Reload systemd and enable service
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", self.SERVICE_NAME], check=True)

    def uninstall(self) -> None:
        """Uninstall the homelab agent service."""
        if os.geteuid() != 0:
            raise PermissionError("Uninstallation requires root privileges. Run with sudo.")

        # Stop and disable service
        subprocess.run(["systemctl", "stop", self.SERVICE_NAME], check=False)
        subprocess.run(["systemctl", "disable", self.SERVICE_NAME], check=False)
        
        # Remove service file
        if Path(self.SERVICE_FILE).exists():
            Path(self.SERVICE_FILE).unlink()
        
        # Reload systemd
        subprocess.run(["systemctl", "daemon-reload"], check=True)

    def start(self) -> None:
        """Start the service."""
        subprocess.run(["systemctl", "start", self.SERVICE_NAME], check=True)

    def stop(self) -> None:
        """Stop the service."""
        subprocess.run(["systemctl", "stop", self.SERVICE_NAME], check=True)

    def restart(self) -> None:
        """Restart the service."""
        subprocess.run(["systemctl", "restart", self.SERVICE_NAME], check=True)

    def status(self) -> dict[str, Any]:
        """Get the status of the service.
        
        Returns:
            Dictionary containing service status information.
        """
        result: dict[str, Any] = {}
        
        try:
            # Get service status
            output = subprocess.run(
                ["systemctl", "is-active", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            result["status"] = output.stdout.strip()
            result["active"] = output.returncode == 0
        except Exception:
            result["status"] = "unknown"
            result["active"] = False
        
        # Get PID if running
        try:
            output = subprocess.run(
                ["systemctl", "show", "--property=MainPID", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            pid_line = output.stdout.strip()
            if "=" in pid_line:
                pid = int(pid_line.split("=")[1])
                result["pid"] = pid if pid > 0 else None
        except Exception:
            result["pid"] = None
        
        # Add config info
        if self.config:
            result["runtime_dir"] = str(self.config.runtime_dir)
            result["llm_provider"] = self.config.llm_provider
            result["channel"] = self.config.communication_channel
        
        return result

    def logs(self, follow: bool = False, lines: int = 50) -> None:
        """Show service logs.
        
        Args:
            follow: Whether to follow the log output.
            lines: Number of lines to show.
        """
        cmd = ["journalctl", "-u", self.SERVICE_NAME, "-n", str(lines)]
        if follow:
            cmd.append("-f")
        
        subprocess.run(cmd)
