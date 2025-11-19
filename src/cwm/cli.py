# cwm/cli.py
import os
import click
from difflib import get_close_matches
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from .utils import (
    has_write_permission,
    safe_create_cwm_folder,
    is_path_literally_inside_bank
)

# --- COMMAND IMPORTS ---
from .save_cmd import save_command
from .backup_cmd import backup_cmd
from .get_cmd import get_cmd
from .watch_cmd import watch_cmd
from .bank_cmd import bank_cmd
from .clear_cmd import clear_cmd

CWM_BANK = ".cwm"
GLOBAL_CWM_BANK = Path(os.getenv("APPDATA")) / "cwm"

try:
    __version__ = version("cwm-cli") 
except PackageNotFoundError:
    __version__ = "0.1.0" # Fallback


# ============================================================
# Custom Click Group with closest-command suggestion
# ============================================================
class CwmGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        """
        Override click.Group.get_command to provide suggestions
        for unknown commands.
        """
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        possibilities = list(self.commands.keys())
        close = get_close_matches(cmd_name, possibilities, n=1, cutoff=0.45)
        if close:
            ctx.fail(f"Unknown command '{cmd_name}'. Did you mean '{close[0]}'?")
        else:
            ctx.fail(f"Unknown command '{cmd_name}'. Run 'cwm --help' for a list of commands.")


# ============================================================
# Root CLI Group
# ============================================================
@click.group(
    cls=CwmGroup,
    epilog="For full documentation and issues, visit: https://github.com/Isu-Ismail/cwm"
)
@click.version_option(version=__version__, prog_name="cwm")
def cli():
    """
    CWM: Command Watch Manager

    Track, save, and retrieve your shell commands efficiently.
    """
    pass


# ============================================================
# INIT COMMAND
# ============================================================
@cli.command()
def init():
    """Initializes a .cwm folder in the current directory."""
    current_path = Path.cwd()
    project_path = current_path / CWM_BANK

    if is_path_literally_inside_bank(current_path):
        click.echo(f"ERROR: Cannot create a .cwm bank inside another .cwm bank.")
        return

    if project_path.exists():
        safe_create_cwm_folder(project_path, repair=True)
        click.echo("A .cwm bank already exists in this project.")
        return

    if not has_write_permission(current_path):
        click.echo("ERROR: You do not have permission to create a CWM bank in this folder.")
        return

    ok = safe_create_cwm_folder(project_path, repair=False)
    if ok:
        click.echo("Initialized empty CWM bank in this project.")
    else:
        click.echo("CWM initialization failed.")

def ensure_global_folder():
    """Ensure global fallback folder exists with safety checks."""
    if not GLOBAL_CWM_BANK.exists():
        # Only verify permission/create if it doesn't exist to save time
        click.echo("Creating global CWM bank...")
        success = safe_create_cwm_folder(GLOBAL_CWM_BANK)
        if success:
            click.echo(f"Global CWM bank initialized at:\n{GLOBAL_CWM_BANK}")
        else:
            click.echo("ERROR: Could not create global CWM bank.")

# Run the global check on import (so it happens for every command)
ensure_global_folder()


# ============================================================
# HELLO COMMAND
# ============================================================
@cli.command()
def hello():
    """Test command."""
    click.echo(f"Hello! Welcome to CWM (v{__version__}), your command watch manager.")
    click.echo("touch some grass")


# ============================================================
# Register All Commands
# ============================================================
cli.add_command(save_command)
cli.add_command(backup_cmd)
cli.add_command(get_cmd)
cli.add_command(watch_cmd)
cli.add_command(bank_cmd)
cli.add_command(clear_cmd)


# ============================================================
# MAIN ENTRY
# ============================================================
if __name__ == "__main__":
    cli()