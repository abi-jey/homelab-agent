"""Configuration management for Homelab Agent."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Configuration for the homelab agent."""

    llm_provider: str = "google"
    llm_model: str = "gemini-3-flash-preview"
    communication_channel: str = "telegram"
    runtime_dir: Path = field(default_factory=lambda: Path("/var/lib/homelab-agent"))
    http_port: int = 8765
    
    # Web UI settings
    web_ui_enabled: bool = True
    web_ui_port: int = 8080
    
    # Speech-to-text settings
    stt_enabled: bool = True
    stt_model: str = "gemini-2.5-flash"
    
    # Provider-specific settings
    google_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_allowed_users: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure runtime_dir is a Path object."""
        if isinstance(self.runtime_dir, str):
            self.runtime_dir = Path(self.runtime_dir)

    @property
    def config_file(self) -> Path:
        """Get the path to the configuration file."""
        return self.runtime_dir / "config" / "config.json"

    @property
    def database_path(self) -> Path:
        """Get the path to the SQLite database."""
        return self.runtime_dir / "data" / "sessions.db"

    def to_dict(self) -> dict:
        """Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration.
        """
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "communication_channel": self.communication_channel,
            "runtime_dir": str(self.runtime_dir),
            "http_port": self.http_port,
            "web_ui_enabled": self.web_ui_enabled,
            "web_ui_port": self.web_ui_port,
            "stt_enabled": self.stt_enabled,
            "stt_model": self.stt_model,
            "google_api_key": self.google_api_key,
            "openai_api_key": self.openai_api_key,
            "telegram_bot_token": self.telegram_bot_token,
            "telegram_allowed_users": self.telegram_allowed_users,
        }

    def save(self) -> None:
        """Save the configuration to disk."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        
        # Set permissions: owner read/write, group read (for homelab-agent group members)
        os.chmod(self.config_file, 0o640)

    @classmethod
    def load(cls, runtime_dir: Optional[Path] = None) -> "Config":
        """Load configuration from disk.
        
        Args:
            runtime_dir: Override runtime directory. If None, uses default or env var.
            
        Returns:
            Loaded Config instance.
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist.
        """
        if runtime_dir is None:
            runtime_dir = Path(
                os.environ.get("HOMELAB_AGENT_RUNTIME_DIR", "/var/lib/homelab-agent")
            )
        
        config_file = runtime_dir / "config" / "config.json"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}. "
                "Run 'homelab-agent install setup' first."
            )
        
        with open(config_file) as f:
            data = json.load(f)
        
        return cls(
            llm_provider=data.get("llm_provider", "google"),
            llm_model=data.get("llm_model", "gemini-3-flash-preview"),
            communication_channel=data.get("communication_channel", "telegram"),
            runtime_dir=Path(data.get("runtime_dir", str(runtime_dir))),
            http_port=data.get("http_port", 8765),
            web_ui_enabled=data.get("web_ui_enabled", True),
            web_ui_port=data.get("web_ui_port", 8080),
            stt_enabled=data.get("stt_enabled", True),
            stt_model=data.get("stt_model", "gemini-2.5-flash"),
            google_api_key=data.get("google_api_key"),
            openai_api_key=data.get("openai_api_key"),
            telegram_bot_token=data.get("telegram_bot_token"),
            telegram_allowed_users=data.get("telegram_allowed_users", []),
        )
