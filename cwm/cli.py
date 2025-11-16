import os
import click
from difflib import get_close_matches
from pathlib import Path

from .utils import (
    has_write_permission,
    inside_cwm_bank,
    safe_create_cwm_folder,
    find_cwm_folders
)

from .save_cmd import save_command   # <-- Import SAVE COMMAND


CWM_BANK = ".cwm"
GLOBAL_CWM_BANK = Path(os.getenv("APPDATA")) / "cwm"


# ============================================================
# Custom Click Group with closest-command suggestion
# ============================================================
class CwmGroup(click.Group):

    def get_command(self, ctx, cmd_name):
        """
        Override click.Group.get_command to provide suggestions
        for unknown commands.
        """
        # Try to get command normally
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv

        # Unknown command → suggest closest one
        possibilities = list(self.commands.keys())
        close = get_close_matches(cmd_name, possibilities, n=1, cutoff=0.45)

        if close:
            ctx.fail(f"Unknown command '{cmd_name}'. Did you mean '{close[0]}'?")
        else:
            ctx.fail(f"Unknown command '{cmd_name}'. Run 'cwm --help' for a list of commands.")


# ============================================================
# Root CLI Group
# ============================================================
@click.group(cls=CwmGroup)
def cli():
    """CWM Command Watch Manager"""
    pass


# ============================================================
# INIT COMMAND
# ============================================================
@cli.command()
def init():
    """Initializes a .cwm folder in the current directory."""
    
    current_path = Path.cwd()
    project_path = current_path / CWM_BANK

    if inside_cwm_bank(current_path):
        click.echo("ERROR: Cannot create a .cwm bank inside another .cwm bank.")
        return

    if not has_write_permission(current_path):
        click.echo("ERROR: You do not have permission to create a CWM bank in this folder.")
        return

    if not project_path.exists():
        ok = safe_create_cwm_folder(project_path, repair=False)
        if ok:
            click.echo("Initialized empty CWM bank in this project.")
        else:
            click.echo("CWM initialization failed.")
        return

    safe_create_cwm_folder(project_path, repair=True)
    click.echo("A .cwm bank already exists in this project.")


# ============================================================
# Ensure Global Folder Exists
# ============================================================
def ensure_global_folder():
    """Ensure global fallback folder exists with safety checks."""
    if not GLOBAL_CWM_BANK.exists():
        click.echo("Creating global CWM bank...")
        success = safe_create_cwm_folder(GLOBAL_CWM_BANK)
        if success:
            click.echo(f"Global CWM bank initialized at:\n{GLOBAL_CWM_BANK}")
        else:
            click.echo("ERROR: Could not create global CWM bank.")

ensure_global_folder()


# ============================================================
# HELLO COMMAND
# ============================================================
@cli.command()
def hello():
    """Test command."""
    click.echo("Hello! Welcome to CWM your command watch manager.")


# ============================================================
# Register: SAVE COMMAND
# ============================================================
cli.add_command(save_command)


# ============================================================
# MAIN ENTRY
# ============================================================
if __name__ == "__main__":
    cli()
