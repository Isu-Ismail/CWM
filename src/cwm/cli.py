# cwm/cli.py
import os
import click
import platform 
from difflib import get_close_matches
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from .utils import (
    has_write_permission,
    is_history_sync_enabled,
    safe_create_cwm_folder,
    is_path_literally_inside_bank,
    get_history_file_path 
)

from .save_cmd import save_command
from .backup_cmd import backup_cmd
from .get_cmd import get_cmd
from .watch_cmd import watch_cmd
from .bank_cmd import bank_cmd
from .clear_cmd import clear_cmd
from .setup_cmd import setup_cmd
from .config_cmd import config_cmd
from .copy_cmd import copy_cmd
from .git_cmd import git_cmd
from .project_cmd import project_cmd # <--- NEW
from .jump_cmd import jump_cmd
from .ask_cmd import ask_cmd
from .group_cmd import group_cmd
from .run_cmd import run_cmd


CWM_BANK = ".cwm"
GLOBAL_CWM_BANK = Path(click.get_app_dir("cwm"))

try:
    __version__ = version("cwm-cli") 
except PackageNotFoundError:
    __version__ = "0.1.0" 

class CwmGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        possibilities = list(self.commands.keys())
        close = get_close_matches(cmd_name, possibilities, n=1, cutoff=0.45)
        if close:
            ctx.fail(f"Unknown command '{cmd_name}'. Did you mean '{close[0]}'?")
        else:
            ctx.fail(f"Unknown command '{cmd_name}'. Run 'cwm --help' for a list of commands.")

CONTEXT_SETTINGS = dict(
    help_option_names=["-h", "--help" ,"hello"],
    max_content_width=2000   # SUPER IMPORTANT — prevents wrapping
)

@click.group(
    cls=CwmGroup,
    context_settings=CONTEXT_SETTINGS,
    epilog=(
        "For full documentation and issues,visit:https://isu-ismail.github.io/cwm-docwebsite/"
    )
)
@click.version_option(version=__version__, prog_name="cwm")
def cli():
    """
    CWM: Command Watch Manager

    Track, save, and retrieve your shell commands efficiently.
    """
    pass

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
        click.echo("Creating global CWM bank...")
        success = safe_create_cwm_folder(GLOBAL_CWM_BANK)
        if success:
            click.echo(f"Global CWM bank initialized at:\n{GLOBAL_CWM_BANK}")
        else:
            click.echo("ERROR: Could not create global CWM bank.")

ensure_global_folder()

@cli.command()
def hello():
    """Test command."""
    click.echo(f"Hello! Welcome to CWM (v{__version__}), your command watch manager.")
    
    os_name = platform.system()
    os_release = platform.release()
    click.echo(f"System: {os_name} {os_release}")

    hist_path = get_history_file_path()
    if hist_path:
        name = hist_path.name
        if "ConsoleHost_history" in name:
            shell = "PowerShell"
        elif ".bash_history" in name:
            shell = "Bash"
        elif ".zsh_history" in name:
            shell = "Zsh"
        else:
            shell = "Unknown Shell"
            
        click.echo(f"Detected Shell: {shell}")
        click.echo(f"History Source: {hist_path}")
    else:
        click.echo("History Source: None (Could not detect a supported shell history file)")
    
    if os.name == 'nt':
             click.echo("")
             click.echo(click.style("NOTE: Command Prompt (cmd.exe) is not supported for history features.", fg="yellow"))
             click.echo("It does not write history to a file. Please use PowerShell or Git Bash.")

    # --- CHECK SYNC STATUS ---
    if not is_history_sync_enabled():
        click.echo("")
        click.echo(click.style("NOTICE: Real-time history tracking is not enabled.", fg="yellow"))
        click.echo(click.style("Run 'cwm setup' to configure your shell automatically.", fg="yellow"))
        click.echo(click.style(""))
        click.echo("")

# ============================================================
# Register All Commands
# ============================================================
cli.add_command(save_command)
cli.add_command(backup_cmd)
cli.add_command(get_cmd)
cli.add_command(watch_cmd)
cli.add_command(bank_cmd)
cli.add_command(clear_cmd)
cli.add_command(setup_cmd)
cli.add_command(config_cmd)
cli.add_command(copy_cmd)
cli.add_command(git_cmd)
cli.add_command(project_cmd) # <--- NEW
cli.add_command(jump_cmd)
cli.add_command(ask_cmd)
cli.add_command(group_cmd)
cli.add_command(run_cmd)

if __name__ == "__main__":
    cli()