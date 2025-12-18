"""Init command for launching the interactive setup wizard."""

import getpass
import grp
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import inquirer
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from homelab_agent.config import Config
from homelab_agent.service.manager import ServiceManager, is_dev_mode, get_project_root

# Set up logging for this module
logger = logging.getLogger(__name__)

console = Console()
app = typer.Typer(help="Initialize the homelab agent with an interactive wizard.")

# Constants
DEFAULT_RUNTIME_DIR = "/var/lib/homelab-agent"
SERVICE_USER = "homelab-agent"

# LLM Provider choices
LLM_PROVIDERS = [
    ("google", "Google (Gemini)"),
    ("openai", "OpenAI (GPT)"),
]

# Model choices per provider (first is default)
GOOGLE_MODELS = [
    ("gemini-3-flash-preview", "Gemini 3 Flash (Preview)"),
    ("gemini-3-pro-preview", "Gemini 3 Pro (Preview)"),
    ("gemini-2.5-pro-preview-05-06", "Gemini 2.5 Pro (Preview)"),
    ("gemini-2.0-flash", "Gemini 2.0 Flash"),
]

OPENAI_MODELS = [
    ("gpt-4o", "GPT-4o"),
    ("gpt-4o-mini", "GPT-4o Mini"),
]

# Communication channel choices
COMMUNICATION_CHANNELS = [
    ("telegram", "Telegram Bot"),
    ("tui", "Terminal UI (local)"),
]


def print_banner() -> None:
    """Print the HAL banner."""
    banner = """
[bold cyan]╔═══════════════════════════════════════════════════════════════╗
║     ██╗  ██╗ █████╗ ██╗                                       ║
║     ██║  ██║██╔══██╗██║                                       ║
║     ███████║███████║██║                                       ║
║     ██╔══██║██╔══██║██║                                       ║
║     ██║  ██║██║  ██║███████╗                                  ║
║     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝                                  ║
║                                                               ║
║         Homelab Agent - AI-Powered Automation                 ║
╚═══════════════════════════════════════════════════════════════╝[/bold cyan]
"""
    console.print(banner)


def run_sudo(command: list[str], description: str) -> subprocess.CompletedProcess:
    """Run a command with sudo if not already root."""
    if os.geteuid() == 0:
        return subprocess.run(command, check=True)
    console.print(f"[dim]sudo: {description}[/dim]")
    return subprocess.run(["sudo"] + command, check=True)


def mask_secret(value: str) -> str:
    """Mask a secret value for display."""
    if len(value) > 8:
        return f"{value[:4]}...{value[-4:]}"
    return "***"


def load_existing_config() -> Optional[Config]:
    """Try to load existing config from default location."""
    try:
        return Config.load(Path(DEFAULT_RUNTIME_DIR))
    except FileNotFoundError:
        return None


def user_in_group(username: str, group: str) -> bool:
    """Check if a user is in a group."""
    try:
        gr = grp.getgrnam(group)
        return username in gr.gr_mem
    except KeyError:
        return False


def add_user_to_group(username: str, group: str) -> None:
    """Add a user to a group."""
    run_sudo(["usermod", "-aG", group, username], f"adding {username} to {group} group")


def build_wheel() -> Optional[Path]:
    """Build a wheel package in dev mode.
    
    In dev mode, this also creates a prerelease version to ensure
    pip sees it as a newer version for reinstallation.
    """
    project_root = get_project_root()
    if not project_root:
        logger.warning("Could not find project root for wheel build")
        return None
    
    logger.info(f"Building wheel from project root: {project_root}")
    console.print("[dim]Building package with poetry...[/dim]")
    
    try:
        # First, bump version to a prerelease with timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        logger.info(f"Creating dev prerelease version with timestamp: {timestamp}")
        
        # Read current version from pyproject.toml
        pyproject_path = project_root / "pyproject.toml"
        content = pyproject_path.read_text()
        
        # Find and parse current version
        import re
        version_match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if version_match:
            current_version = version_match.group(1)
            # Strip any existing prerelease suffix
            base_version = re.sub(r'\.dev\d+$', '', current_version)
            base_version = re.sub(r'-dev\d+$', '', base_version)
            new_version = f"{base_version}.dev{timestamp}"
            
            logger.info(f"Bumping version: {current_version} -> {new_version}")
            console.print(f"[dim]Version: {current_version} → {new_version}[/dim]")
            
            # Update pyproject.toml
            new_content = re.sub(
                r'^(version\s*=\s*["\'])([^"\']+)(["\'])',
                f'\\g<1>{new_version}\\g<3>',
                content,
                flags=re.MULTILINE,
            )
            pyproject_path.write_text(new_content)
            logger.debug(f"Updated pyproject.toml with new version")
        else:
            logger.warning("Could not find version in pyproject.toml")
        
        # Build the wheel
        logger.info("Running poetry build...")
        result = subprocess.run(
            ["poetry", "build", "-f", "wheel"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            logger.error(f"Poetry build failed: {result.stderr}")
            console.print(f"[red]Build error: {result.stderr}[/red]")
            return None
        
        logger.debug(f"Poetry build output: {result.stdout}")
        
        wheels = list((project_root / "dist").glob("*.whl"))
        if wheels:
            newest_wheel = max(wheels, key=lambda p: p.stat().st_mtime)
            logger.info(f"Built wheel: {newest_wheel}")
            return newest_wheel
        else:
            logger.error("No wheel files found after build")
            return None
            
    except subprocess.CalledProcessError as e:
        logger.exception(f"Subprocess error during wheel build: {e}")
        console.print(f"[yellow]Warning: Could not build wheel: {e}[/yellow]")
        return None
    except FileNotFoundError as e:
        logger.exception(f"File not found during wheel build: {e}")
        console.print(f"[yellow]Warning: Could not build wheel (poetry not found?): {e}[/yellow]")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during wheel build: {e}")
        console.print(f"[yellow]Warning: Could not build wheel: {e}[/yellow]")
        return None


def save_config_sudo(config: Config) -> None:
    """Save config file using sudo."""
    import json
    config_data = config.to_dict()
    config_json = json.dumps(config_data, indent=2)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(config_json)
        temp_path = f.name
    
    try:
        run_sudo(["mkdir", "-p", str(config.config_file.parent)], "creating config directory")
        run_sudo(["cp", temp_path, str(config.config_file)], "copying config file")
        run_sudo(["chmod", "640", str(config.config_file)], "setting config permissions")
        run_sudo(["chown", f"{SERVICE_USER}:{SERVICE_USER}", str(config.config_file)], "setting config ownership")
    finally:
        os.unlink(temp_path)


@app.callback(invoke_without_command=True)
def init(
    ctx: typer.Context,
    skip_service: bool = typer.Option(
        False, "--skip-service", "-s",
        help="Only save config, don't install/restart service.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging output.",
    ),
) -> None:
    """Launch the interactive wizard to configure and install the homelab agent."""
    if ctx.invoked_subcommand is not None:
        return

    # Configure logging level based on verbose flag
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    else:
        logging.basicConfig(level=logging.WARNING)

    logger.info("Starting hal init wizard")
    print_banner()
    current_user = getpass.getuser()
    logger.debug(f"Current user: {current_user}")
    
    # Check for existing configuration
    existing_config = load_existing_config()
    logger.debug(f"Existing config found: {existing_config is not None}")
    
    if existing_config:
        console.print(
            "\n[bold yellow]Existing configuration found![/bold yellow]\n"
            f"LLM Provider: [cyan]{existing_config.llm_provider}[/cyan]\n"
            f"Model: [cyan]{existing_config.llm_model}[/cyan]\n"
        )
        
        action = inquirer.prompt([
            inquirer.List(
                "action",
                message="What would you like to do?",
                choices=[
                    ("Reinstall service (keep config)", "reinstall"),
                    ("Reconfigure everything", "reset"),
                    ("Cancel", "cancel"),
                ],
            ),
        ])
        
        if not action or action["action"] == "cancel":
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)
        
        if action["action"] == "reinstall":
            _do_install(existing_config, current_user, skip_service)
            return
    
    # Fresh install wizard
    console.print(
        "\nWelcome to the [bold]HAL[/bold] setup wizard!\n"
        "Use arrow keys to navigate, Enter to select.\n"
    )

    # Basic questions
    answers = inquirer.prompt([
        inquirer.List(
            "llm_provider",
            message="Which AI provider?",
            choices=[(d, v) for v, d in LLM_PROVIDERS],
        ),
        inquirer.List(
            "channel",
            message="Communication channel?",
            choices=[(d, v) for v, d in COMMUNICATION_CHANNELS],
        ),
    ])
    
    if not answers:
        raise typer.Exit(0)

    # Model selection
    models = GOOGLE_MODELS if answers["llm_provider"] == "google" else OPENAI_MODELS
    model_answer = inquirer.prompt([
        inquirer.List(
            "model",
            message="Which model?",
            choices=[(d, v) for v, d in models],
        ),
    ])
    if not model_answer:
        raise typer.Exit(0)

    # API keys
    api_questions = []
    if answers["llm_provider"] == "google":
        api_questions.append(inquirer.Text("google_api_key", message="Google AI API key"))
    else:
        api_questions.append(inquirer.Text("openai_api_key", message="OpenAI API key"))

    if answers["channel"] == "telegram":
        api_questions.extend([
            inquirer.Text("telegram_bot_token", message="Telegram Bot token"),
            inquirer.Text("telegram_allowed_users", message="Allowed user IDs (comma-separated, empty=all)", default=""),
        ])

    api_answers = inquirer.prompt(api_questions) or {}

    # Web UI settings
    web_ui_answers = inquirer.prompt([
        inquirer.Confirm(
            "web_ui_enabled",
            message="Enable Web UI (browser-based chat interface)?",
            default=True,
        ),
    ]) or {}
    
    web_ui_enabled = web_ui_answers.get("web_ui_enabled", True)
    web_ui_port = 8080
    
    if web_ui_enabled:
        port_answer = inquirer.prompt([
            inquirer.Text(
                "web_ui_port",
                message="Web UI port",
                default="8080",
            ),
        ]) or {}
        try:
            web_ui_port = int(port_answer.get("web_ui_port", "8080"))
        except ValueError:
            web_ui_port = 8080

    # Parse telegram users
    telegram_users = []
    if api_answers.get("telegram_allowed_users"):
        telegram_users = [u.strip() for u in api_answers["telegram_allowed_users"].split(",") if u.strip()]

    # Summary
    table = Table(title="Configuration Summary")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("LLM Provider", dict(LLM_PROVIDERS)[answers["llm_provider"]])
    table.add_row("Model", model_answer["model"])
    table.add_row("Channel", dict(COMMUNICATION_CHANNELS)[answers["channel"]])
    table.add_row("Web UI", f"{'Enabled on port ' + str(web_ui_port) if web_ui_enabled else 'Disabled'}")
    
    for key in ["google_api_key", "openai_api_key", "telegram_bot_token"]:
        if api_answers.get(key):
            table.add_row(key.replace("_", " ").title(), f"[dim]{mask_secret(api_answers[key])}[/dim]")
    
    console.print(table)

    proceed_result = inquirer.prompt([inquirer.Confirm("proceed", message="Proceed?", default=True)])
    if not proceed_result or not proceed_result.get("proceed"):
        raise typer.Exit(0)

    # Create config
    config = Config(
        llm_provider=answers["llm_provider"],
        llm_model=model_answer["model"],
        communication_channel=answers["channel"],
        runtime_dir=Path(DEFAULT_RUNTIME_DIR),
        web_ui_enabled=web_ui_enabled,
        web_ui_port=web_ui_port,
        google_api_key=api_answers.get("google_api_key"),
        openai_api_key=api_answers.get("openai_api_key"),
        telegram_bot_token=api_answers.get("telegram_bot_token"),
        telegram_allowed_users=telegram_users,
    )

    _do_install(config, current_user, skip_service)


def _do_install(config: Config, current_user: str, skip_service: bool) -> None:
    """Perform the installation."""
    logger.info("Starting installation process")
    logger.debug(f"Config: provider={config.llm_provider}, model={config.llm_model}")
    logger.debug(f"Runtime dir: {config.runtime_dir}")
    logger.debug(f"Current user: {current_user}, skip_service: {skip_service}")
    
    dev_mode = is_dev_mode()
    wheel_path: Optional[Path] = None
    
    logger.info(f"Development mode: {dev_mode}")
    
    if dev_mode:
        console.print("\n[bold yellow]📦 Development mode[/bold yellow]")
        logger.info("Building wheel for dev mode installation")
        wheel_path = build_wheel()
        if wheel_path:
            console.print(f"[green]✓[/green] Built: {wheel_path.name}")
            logger.info(f"Wheel built successfully: {wheel_path}")
        else:
            logger.warning("Wheel build failed, will attempt PyPI installation")
            console.print("[yellow]⚠ Wheel build failed, will try PyPI[/yellow]")

    console.print("\n[bold]Installing...[/bold]")
    console.print("[dim]Some steps require sudo.[/dim]\n")

    try:
        # 1. Create directories
        logger.info("Step 1: Creating directories")
        console.print("[dim]Creating directories...[/dim]")
        run_sudo(["mkdir", "-p", str(config.runtime_dir)], "creating runtime dir")
        for subdir in ["venv", "config", "logs", "data"]:
            run_sudo(["mkdir", "-p", str(config.runtime_dir / subdir)], f"creating {subdir}")
            logger.debug(f"Created directory: {config.runtime_dir / subdir}")
        console.print("[green]✓[/green] Directories created")
        logger.info("Directories created successfully")

        # 2. Create system user/group
        logger.info("Step 2: Setting up system user")
        console.print("[dim]Setting up user...[/dim]")
        try:
            result = subprocess.run(["id", SERVICE_USER], check=True, capture_output=True, text=True)
            logger.debug(f"User {SERVICE_USER} exists: {result.stdout.strip()}")
        except subprocess.CalledProcessError:
            logger.info(f"Creating system user: {SERVICE_USER}")
            run_sudo([
                "useradd", "--system", "--no-create-home",
                "--shell", "/usr/sbin/nologin",
                "--home-dir", str(config.runtime_dir),
                SERVICE_USER,
            ], "creating system user")
        console.print("[green]✓[/green] System user ready")
        logger.info("System user ready")

        # 3. Add current user to group for file access
        logger.info("Step 3: Checking group membership")
        if current_user != "root" and not user_in_group(current_user, SERVICE_USER):
            logger.info(f"Adding {current_user} to {SERVICE_USER} group")
            console.print(f"[dim]Adding {current_user} to {SERVICE_USER} group...[/dim]")
            add_user_to_group(current_user, SERVICE_USER)
            console.print(f"[green]✓[/green] User {current_user} added to {SERVICE_USER} group")
            console.print("[yellow]Note: Log out and back in for group membership to take effect.[/yellow]")
        else:
            logger.debug(f"User {current_user} already in group or is root")

        # 4. Save config
        logger.info("Step 4: Saving configuration")
        console.print("[dim]Saving configuration...[/dim]")
        save_config_sudo(config)
        console.print("[green]✓[/green] Configuration saved")
        logger.info(f"Configuration saved to {config.config_file}")

        # 5. Create venv and install
        logger.info("Step 5: Setting up Python environment")
        console.print("[dim]Setting up Python environment...[/dim]")
        venv_path = config.runtime_dir / "venv"
        logger.debug(f"Venv path: {venv_path}")
        
        run_sudo(["chown", "-R", f"{os.getuid()}:{os.getgid()}", str(venv_path)], "temp venv ownership")
        
        logger.info(f"Creating venv with {sys.executable}")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)], 
            check=True, 
            capture_output=True, 
            text=True
        )
        logger.debug(f"Venv creation output: {result.stdout}")
        
        pip = venv_path / "bin" / "pip"
        logger.info("Upgrading pip")
        subprocess.run([str(pip), "install", "-q", "--upgrade", "pip"], check=True)
        
        if wheel_path:
            logger.info(f"Installing from wheel: {wheel_path}")
            console.print(f"[dim]Installing {wheel_path.name}...[/dim]")
            result = subprocess.run(
                [str(pip), "install", "--force-reinstall", str(wheel_path)], 
                capture_output=True, 
                text=True
            )
            if result.returncode != 0:
                logger.error(f"Pip install failed: {result.stderr}")
                console.print(f"[red]Pip error: {result.stderr}[/red]")
                raise subprocess.CalledProcessError(result.returncode, str(pip))
            logger.debug(f"Pip install output: {result.stdout}")
        else:
            logger.info("Installing from PyPI")
            result = subprocess.run(
                [str(pip), "install", "homelab-agent"], 
                capture_output=True, 
                text=True
            )
            if result.returncode != 0:
                logger.error(f"Pip install failed: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, str(pip))
            logger.debug(f"Pip install output: {result.stdout}")
            
        console.print("[green]✓[/green] Python environment ready")
        logger.info("Python environment ready")

        # 6. Set permissions (group-readable for current user access)
        logger.info("Step 6: Setting permissions")
        console.print("[dim]Setting permissions...[/dim]")
        run_sudo(["chown", "-R", f"{SERVICE_USER}:{SERVICE_USER}", str(config.runtime_dir)], "setting ownership")
        run_sudo(["chmod", "-R", "g+rX", str(config.runtime_dir)], "setting group read")
        run_sudo(["chmod", "g+w", str(config.runtime_dir / "data")], "data dir group write")
        run_sudo(["chmod", "g+w", str(config.runtime_dir / "logs")], "logs dir group write")
        console.print("[green]✓[/green] Permissions set")
        logger.info("Permissions set")

        if skip_service:
            logger.info("Skipping service installation (--skip-service flag)")
            console.print(Panel("[green]✓ Config saved![/green]", border_style="green"))
            return

        # 7. Install systemd service
        logger.info("Step 7: Installing systemd service")
        console.print("[dim]Installing service...[/dim]")
        manager = ServiceManager(config)
        service_content = manager._generate_service_file()
        logger.debug(f"Service file content:\n{service_content}")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.service', delete=False) as f:
            f.write(service_content)
            temp_svc = f.name
        
        try:
            run_sudo(["cp", temp_svc, manager.SERVICE_FILE], "installing service")
            logger.info(f"Service file installed to {manager.SERVICE_FILE}")
            run_sudo(["systemctl", "daemon-reload"], "reloading systemd")
            run_sudo(["systemctl", "enable", manager.SERVICE_NAME], "enabling service")
            logger.info(f"Service {manager.SERVICE_NAME} enabled")
        finally:
            os.unlink(temp_svc)
        console.print("[green]✓[/green] Service installed")

        # 8. Start service
        logger.info("Step 8: Starting service")
        console.print("[dim]Starting service...[/dim]")
        run_sudo(["systemctl", "restart", manager.SERVICE_NAME], "starting service")
        console.print("[green]✓[/green] Service started")
        logger.info(f"Service {manager.SERVICE_NAME} started")

        console.print(Panel(
            "[bold green]✓ Installation Complete![/bold green]\n\n"
            f"Runtime: [cyan]{config.runtime_dir}[/cyan]\n\n"
            "Commands:\n"
            "  • [bold]hal service status[/bold]\n"
            "  • [bold]hal service logs[/bold]\n"
            "  • [bold]hal tui[/bold]",
            title="Success",
            border_style="green",
        ))
        logger.info("Installation completed successfully")

    except subprocess.CalledProcessError as e:
        logger.exception(f"Installation failed with subprocess error: {e}")
        console.print(f"\n[bold red]✗ Failed:[/bold red] {e}")
        if hasattr(e, 'stderr') and e.stderr:
            console.print(f"[red]{e.stderr}[/red]")
            logger.error(f"Subprocess stderr: {e.stderr}")
        if hasattr(e, 'stdout') and e.stdout:
            logger.debug(f"Subprocess stdout: {e.stdout}")
        raise typer.Exit(1)
    except Exception as e:
        logger.exception(f"Installation failed with unexpected error: {e}")
        console.print(f"\n[bold red]✗ Unexpected error:[/bold red] {e}")
        raise typer.Exit(1)
