"""Logging configuration for homelab-agent using Rich.

Provides consistent, beautiful logging across the application.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# Custom theme for HAL
HAL_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "debug": "dim",
    "success": "green",
    "hal": "magenta bold",
})

# Global console instance
console = Console(theme=HAL_THEME)


def setup_logging(
    level: int = logging.INFO,
    show_path: bool = False,
    show_time: bool = True,
    rich_tracebacks: bool = True,
    log_file: Optional[Path] = None,
) -> None:
    """Configure logging with Rich handler and optional file logging.
    
    Args:
        level: Logging level (default: INFO).
        show_path: Show file path in log messages.
        show_time: Show timestamps in log messages.
        rich_tracebacks: Use Rich for exception tracebacks.
        log_file: Optional path to a log file for persistent logging.
            If provided, logs will be written to both console and file.
    """
    handlers: list[logging.Handler] = []
    
    # Create Rich handler for console output
    rich_handler = RichHandler(
        console=console,
        show_path=show_path,
        show_time=show_time,
        rich_tracebacks=rich_tracebacks,
        tracebacks_show_locals=False,
        markup=True,
        log_time_format="[%X]",
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(rich_handler)
    
    # Add file handler if log_file is specified
    if log_file:
        try:
            # Ensure log directory exists
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create rotating file handler (10MB max, keep 5 backups)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            file_handler.setLevel(level)
            handlers.append(file_handler)
        except Exception as e:
            # Log to console if file handler fails
            console.print(f"[warning]Could not set up file logging: {e}[/warning]")
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True,
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.
    
    Args:
        name: Logger name (usually __name__).
        
    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


class HalLogger:
    """Custom logger wrapper with HAL-specific methods."""
    
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)
    
    def info(self, message: str, *args, **kwargs) -> None:
        """Log an info message."""
        self._logger.info(message, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """Log a debug message."""
        self._logger.debug(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """Log a warning message."""
        self._logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """Log an error message."""
        self._logger.error(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs) -> None:
        """Log an exception with traceback."""
        self._logger.exception(message, *args, **kwargs)
    
    def hal(self, message: str) -> None:
        """Log a HAL-branded message."""
        console.print(f"[hal]🏠 HAL:[/hal] {message}")
    
    def success(self, message: str) -> None:
        """Log a success message."""
        console.print(f"[success]✓[/success] {message}")
    
    def agent_action(self, action: str, details: str = "") -> None:
        """Log an agent action."""
        if details:
            self._logger.info(f"[magenta]⚡ {action}:[/magenta] {details}")
        else:
            self._logger.info(f"[magenta]⚡ {action}[/magenta]")
