"""Main CLI entry point for Homelab Agent."""

import typer
from rich.console import Console
from rich.table import Table

from homelab_agent.version import __version__
from homelab_agent.commands import init, service, tui

console = Console()

app = typer.Typer(
    name="hal",
    help="HAL - Your Homelab Agent for AI-powered automation.",
    rich_markup_mode="rich",
)

# Register sub-commands
app.add_typer(init.app, name="init", help="Launch the interactive setup wizard.")
app.add_typer(service.app, name="service", help="Manage the homelab agent service.")
app.add_typer(tui.app, name="tui", help="Launch the interactive TUI chat interface.")


def _get_daemon_version() -> str | None:
    """Try to get the daemon version via API."""
    try:
        from homelab_agent.api.client import AgentAPIClient
        from homelab_agent.config import load_config
        
        config = load_config()
        client = AgentAPIClient(config)
        
        # Try to get status which should include version
        import asyncio
        
        async def get_status():
            try:
                return await client.get_status()
            except Exception:
                return None
            finally:
                await client.close()
        
        status = asyncio.run(get_status())
        if status:
            return __version__  # For now, return CLI version as daemon uses same package
        return None
    except Exception:
        return None


@app.command()
def version(
    check_daemon: bool = typer.Option(False, "--daemon", "-d", help="Also check daemon version"),
) -> None:
    """Display the current version of Homelab Agent."""
    table = Table(title="🏠 HAL - Homelab Agent", show_header=True, header_style="bold cyan")
    table.add_column("Component", style="green")
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="yellow")
    
    # CLI version
    table.add_row("CLI", __version__, "✓ installed")
    
    # Daemon version
    if check_daemon:
        daemon_version = _get_daemon_version()
        if daemon_version:
            table.add_row("Daemon", daemon_version, "[green]✓ running[/green]")
        else:
            table.add_row("Daemon", "-", "[red]✗ not running[/red]")
    
    console.print(table)


@app.callback()
def main() -> None:
    """
    Homelab Agent - A CLI tool for managing homelab services with AI assistance.
    """
    pass


if __name__ == "__main__":
    app()
