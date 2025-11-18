import os
import click
from difflib import get_close_matches
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError





# Import the new, specific helpers
from .utils import (
    has_write_permission,
    safe_create_cwm_folder,
    is_path_literally_inside_bank  # <-- The only check we need
)

from .save_cmd import save_command   
from .backup_cmd import backup_cmd 
from .get_cmd import get_cmd                 
from .watch_cmd import watch_cmd  
from .bank_cmd import bank_cmd
from .clear_cmd import clear_cmd




CWM_BANK = ".cwm"
GLOBAL_CWM_BANK = Path(os.getenv("APPDATA")) / "cwm"

try:
    # Get the version of the 'cwm' package (defined in pyproject.toml)
    __version__ = version("cwm")
except PackageNotFoundError:
    # Fallback if the package is not installed (e.g., running direct)
    __version__ = "0.0.0-dev"


# ============================================================
# Custom Click Group with closest-command suggestion
# ============================================================
class CwmGroup(click.Group):
    # (This class is unchanged and correct)
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
@click.group(cls=CwmGroup)
@click.version_option(version=__version__, prog_name="cwm") 
def cli():
    """CWM Command Watch Manager"""
    pass


# ============================================================
# INIT COMMAND (REFACTORED)
# ============================================================
@cli.command()
def init():
    """Initializes a .cwm folder in the current directory."""
    
    current_path = Path.cwd()
    project_path = current_path / CWM_BANK

    # This is the *only* check required by your new logic.
    # It prevents "cwm init" inside ".cwm/data" etc.
    if is_path_literally_inside_bank(current_path):
        click.echo(f"ERROR: Cannot create a .cwm bank inside another .cwm bank.")
        return

    # If a bank already exists *at this level*, just repair it.
    if project_path.exists():
        safe_create_cwm_folder(project_path, repair=True)
        click.echo("A .cwm bank already exists in this project.")
        return

    # Check for permissions before creating
    if not has_write_permission(current_path):
        click.echo("ERROR: You do not have permission to create a CWM bank in this folder.")
        return

    # No bank exists here, and we're not inside one. We are clear to create.
    ok = safe_create_cwm_folder(project_path, repair=False)
    if ok:
        click.echo("Initialized empty CWM bank in this project.")
    else:
        click.echo("CWM initialization failed.")


# ============================================================
# Ensure Global Folder Exists
# ============================================================
def ensure_global_folder():
    """Ensure global fallback folder exists with safety checks."""
    # This function is correct and unchanged
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
    click.echo(f"Hello! Welcome to CWM (v{__version__}), your command watch manager.")
    click.echo("touch some grass.....")


# =================================S===========================
# Register: SAVE COMMAND
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