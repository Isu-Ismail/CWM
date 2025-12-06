# src/cwm/cli.py
import os
import sys
import click
import platform 
from difflib import get_close_matches
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

# Only import lightweight utilities immediately
from .utils import (
    is_history_sync_enabled,
    safe_create_cwm_folder,
    get_history_file_path ,
    is_path_literally_inside_bank,
    CWM_BANK_NAME,has_write_permission
)

GLOBAL_CWM_BANK = Path(click.get_app_dir("cwm"))

try:
    __version__ = version("cwm-cli") 
except PackageNotFoundError:
    __version__ = "2.0.0" 

# --- LAZY LOADING MAPPING ---
COMMAND_MAP = {
    # Workspace
    "jump":    (".jump_cmd", "jump_cmd"),
    "project": (".project_cmd", "project_cmd"),
    "run":     (".run_cmd", "run_cmd"),
    "group":   (".group_cmd", "group_cmd"),
    
    # Core
    "save":    (".save_cmd", "save_command"),
    "get":     (".get_cmd", "get_cmd"),
    "config":  (".config_cmd", "config_cmd"),
    "git":     (".git_cmd", "git_cmd"),
    
    # Utils
    "copy":    (".copy_cmd", "copy_cmd"),
    "watch":   (".watch_cmd", "watch_cmd"),
    "backup":  (".backup_cmd", "backup_cmd"),
    "bank":    (".bank_cmd", "bank_cmd"),
    "clear":   (".clear_cmd", "clear_cmd"),
    "setup":   (".setup_cmd", "setup_cmd"),
    "ask":     (".ask_cmd", "ask_cmd"),
}

# Define Category Order
CATEGORIES = {
    "Workspace & Navigation": ["project", "jump", "group", "run"],
    "Core & Configuration":   ["init", "hello", "config", "setup"],
    "History & Storage":      ["save", "get", "backup", "clear", "bank"],
    "Tools & Utilities":      ["ask", "git", "copy", "watch"],
}

class LazyGroup(click.Group):
    def list_commands(self, ctx):
        return sorted(list(COMMAND_MAP.keys()) + ["init", "hello"])

    def get_command(self, ctx, cmd_name):
        # 1. Handle Built-ins
        if cmd_name == "init": return init
        if cmd_name == "hello": return hello

        # 2. Handle Lazy Loaded Commands
        if cmd_name in COMMAND_MAP:
            module_name, func_name = COMMAND_MAP[cmd_name]
            try:
                mod = __import__(f"cwm{module_name}", fromlist=[func_name])
                return getattr(mod, func_name)
            except ImportError as e:
                click.echo(f"Error loading command '{cmd_name}': {e}", err=True)
                if "flet" in str(e) or "psutil" in str(e):
                    click.echo("Hint: Run 'pip install cwm-cli[gui]'", err=True)
                if "google" in str(e) or "openai" in str(e):
                    click.echo("Hint: Run 'pip install cwm-cli[ai]'", err=True)
                return None
            except AttributeError:
                return None

        # 3. Fuzzy Matching
        possibilities = list(COMMAND_MAP.keys()) + ["init", "hello"]
        close = get_close_matches(cmd_name, possibilities, n=1, cutoff=0.45)
        if close:
            ctx.fail(f"Unknown command '{cmd_name}'. Did you mean '{close[0]}'?")
        
        return None

    def format_commands(self, ctx, formatter):
        """
        Overridden method to output grouped help with COLOR.
        """
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            commands.append((subcommand, cmd))

        if not commands:
            return

        # Calculate width based on raw length to ensure alignment works with colors
        limit = formatter.width - 6 - max(len(cmd[0]) for cmd in commands)

        # Create lookup map (Command -> Category)
        cmd_to_cat = {}
        for cat, cmds in CATEGORIES.items():
            for c in cmds:
                cmd_to_cat[c] = cat

        # Bucket commands
        buckets = {cat: [] for cat in CATEGORIES}
        buckets["Other Commands"] = []

        for name, cmd in commands:
            cat = cmd_to_cat.get(name, "Other Commands")
            help_text = cmd.get_short_help_str(limit)
            buckets[cat].append((name, help_text))

        # Print Categories with Color
        for cat in CATEGORIES:
            if buckets[cat]:
                # Heading: Yellow & Bold
                heading = click.style(cat, fg="yellow", bold=True)
                with formatter.section(heading):
                    # Commands: Green
                    styled_rows = [
                        (click.style(name, fg="green"), help_text) 
                        for name, help_text in buckets[cat]
                    ]
                    formatter.write_dl(styled_rows)
        
        # Print Others
        if buckets["Other Commands"]:
            with formatter.section(click.style("Other Commands", fg="yellow", bold=True)):
                styled_rows = [
                    (click.style(name, fg="green"), help_text) 
                    for name, help_text in buckets["Other Commands"]
                ]
                formatter.write_dl(styled_rows)

CONTEXT_SETTINGS = dict(
    help_option_names=["-h", "--help"],
    max_content_width=120
)

# Footer Content
DOCS_LINK = "https://isu-ismail.github.io/cwm-docwebsite/index.html"
FOOTER = f"Developed by ISU | Docs: {DOCS_LINK}"

@click.group(
    cls=LazyGroup,
    context_settings=CONTEXT_SETTINGS,
    epilog=click.style(FOOTER, fg="blue")
)
@click.version_option(version=__version__, prog_name="cwm")
def cli():
    """
    CWM: Command Watch Manager (v2.0)

    A complete workspace and history manager for developers.
    """
    pass

# --- BUILT-IN COMMANDS ---

@cli.command()
def init():
    """Initializes a .cwm folder in the current directory."""
    current_path = Path.cwd()
    project_path = current_path / CWM_BANK_NAME

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

@click.command()
def hello():
    """System diagnostics."""
    click.echo(f"CWM v{__version__}")
    click.echo(f"System: {platform.system()} {platform.release()}")
    hist = get_history_file_path()
    click.echo(f"History: {hist if hist else 'Not Detected'}")
    
    if not is_history_sync_enabled():
        click.echo("Notice: Real-time sync not enabled (Run 'cwm setup' on Linux/Mac).")
        
    click.echo("")
    click.echo(f"Documentation: {click.style(DOCS_LINK, fg='blue', underline=True)}")
    click.echo("Developed by ISU")

if __name__ == "__main__":
    cli()