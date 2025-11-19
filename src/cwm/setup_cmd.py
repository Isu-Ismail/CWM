# cwm/setup_cmd.py
import click
import os
from pathlib import Path
from .utils import is_history_sync_enabled

BASH_SYNC_LINE = 'export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"'

@click.command("setup")
def setup_cmd():
    """
    Configures your shell to sync history instantly (Linux/Mac only).
    """
    if os.name == 'nt':
        click.echo("This command is for Linux/Mac only.")
        click.echo("Windows PowerShell syncs automatically.")
        return

    if is_history_sync_enabled():
        click.echo("Success: Your shell is already configured for instant history!")
        return

    # If we get here, it's not setup. Locate .bashrc
    home = Path.home()
    bashrc = home / ".bashrc"

    if not bashrc.exists():
        click.echo(f"Error: Could not find {bashrc}")
        return

    click.echo(f"CWM needs to add a line to '{bashrc}' to enable real-time history tracking.")
    click.echo(f"Line to add: {BASH_SYNC_LINE}")
    
    if click.confirm("Do you want to continue?"):
        try:
            with open(bashrc, "a", encoding="utf-8") as f:
                f.write(f"\n# --- CWM History Sync ---\n{BASH_SYNC_LINE}\n")
            
            click.echo("Done! Please restart your terminal or run: source ~/.bashrc")
        except Exception as e:
            click.echo(f"Error writing to file: {e}", err=True)
    else:
        click.echo("Setup cancelled.")