"""Version management for homelab-agent.

This module provides a single source of truth for version information.
The version is read from pyproject.toml at runtime when possible.
"""

import importlib.metadata
from pathlib import Path

# Fallback version if metadata is unavailable
_FALLBACK_VERSION = "0.1.0"


def get_version() -> str:
    """Get the package version.
    
    Tries to read from installed package metadata first,
    falls back to parsing pyproject.toml, then uses fallback.
    
    Returns:
        Version string (e.g., "0.1.0").
    """
    try:
        return importlib.metadata.version("homelab-agent")
    except importlib.metadata.PackageNotFoundError:
        # Package not installed, try reading from pyproject.toml
        try:
            pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text()
                for line in content.split("\n"):
                    if line.strip().startswith("version"):
                        # Parse: version = "0.1.0"
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            version = parts[1].strip().strip('"').strip("'")
                            return version
        except Exception:
            pass
        return _FALLBACK_VERSION


__version__ = get_version()
