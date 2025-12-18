"""Service management commands for Homelab Agent."""

import subprocess

import typer
from rich.console import Console
from rich.table import Table

from homelab_agent.service.manager import ServiceManager

console = Console()

app = typer.Typer(help="Manage the homelab agent service.")

SERVICE_NAME = "homelab-agent"


@app.command()
def start() -> None:
    """Start the homelab agent service."""
    console.print("[bold]Starting homelab agent service...[/bold]")
    try:
        subprocess.run(["sudo", "systemctl", "start", SERVICE_NAME], check=True)
        console.print("[bold green]Service started successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Failed to start service:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def stop() -> None:
    """Stop the homelab agent service."""
    console.print("[bold]Stopping homelab agent service...[/bold]")
    try:
        subprocess.run(["sudo", "systemctl", "stop", SERVICE_NAME], check=True)
        console.print("[bold green]Service stopped successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Failed to stop service:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def restart() -> None:
    """Restart the homelab agent service."""
    console.print("[bold]Restarting homelab agent service...[/bold]")
    try:
        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=True)
        console.print("[bold green]Service restarted successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Failed to restart service:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show the status of the homelab agent service."""
    table = Table(title="Homelab Agent Service Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    # Get service status (doesn't require sudo)
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        status_text = result.stdout.strip()
        is_active = result.returncode == 0
    except Exception:
        status_text = "unknown"
        is_active = False
    
    table.add_row("Status", status_text)
    table.add_row("Active", "Yes" if is_active else "No")
    
    # Get PID if running
    try:
        result = subprocess.run(
            ["systemctl", "show", "--property=MainPID", SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        pid_line = result.stdout.strip()
        if "=" in pid_line:
            pid = int(pid_line.split("=")[1])
            table.add_row("PID", str(pid) if pid > 0 else "N/A")
        else:
            table.add_row("PID", "N/A")
    except Exception:
        table.add_row("PID", "N/A")
    
    # Try to load config for additional info (may fail if no read access)
    try:
        from homelab_agent.config import Config
        config = Config.load()
        table.add_row("Runtime Directory", str(config.runtime_dir))
        table.add_row("LLM Provider", config.llm_provider)
        table.add_row("Communication Channel", config.communication_channel)
    except Exception:
        # Config not accessible, show defaults
        table.add_row("Runtime Directory", "/var/lib/homelab-agent")
        table.add_row("LLM Provider", "[dim]unknown[/dim]")
        table.add_row("Communication Channel", "[dim]unknown[/dim]")
    
    console.print(table)


@app.command()
def logs(
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output.",
    ),
    lines: int = typer.Option(
        50,
        "--lines",
        "-n",
        help="Number of log lines to show.",
    ),
) -> None:
    """Show logs from the homelab agent service."""
    cmd = ["journalctl", "-u", SERVICE_NAME, "-n", str(lines)]
    if follow:
        cmd.append("-f")
    
    try:
        subprocess.run(cmd)
    except Exception as e:
        console.print(f"[bold red]Failed to get logs:[/bold red] {e}")
        raise typer.Exit(code=1)
