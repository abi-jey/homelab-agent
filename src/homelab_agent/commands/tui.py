"""TUI command for launching the interactive chat interface."""

from typing import Optional

import typer
from rich.console import Console

from homelab_agent.config import Config
from homelab_agent.tui.chat import run_tui

console = Console()

app = typer.Typer(help="Launch the interactive TUI chat interface.")


@app.callback(invoke_without_command=True)
def tui(
    ctx: typer.Context,
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to the runtime directory containing config.",
    ),
) -> None:
    """
    Launch the HAL TUI chat interface.
    
    This provides an interactive terminal-based chat interface to communicate
    with your homelab agent.
    """
    if ctx.invoked_subcommand is not None:
        return

    config = None
    
    if config_path:
        from pathlib import Path
        try:
            config = Config.load(Path(config_path))
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1)
    else:
        try:
            config = Config.load()
        except FileNotFoundError:
            console.print(
                "[yellow]Warning:[/yellow] No configuration found. "
                "Run [bold]hal init[/bold] first for full functionality."
            )
            # Continue anyway with None config

    run_tui(config)
