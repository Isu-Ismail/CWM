import click
import platform 
from difflib import get_close_matches
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from .utils import (
    is_history_sync_enabled,
    safe_create_cwm_folder,
    get_history_file_path,
    is_path_literally_inside_bank,
    CWM_BANK_NAME, has_write_permission
)
from .rich_help import RichHelpCommand,RichHelpGroup
from rich.console import Console

console = Console()

GLOBAL_CWM_BANK = Path(click.get_app_dir("cwm"))

try:
    __version__ = version("cwm-cli") 
except PackageNotFoundError:
    __version__ = "2.0.0" 

COMMAND_MAP = {
    # Workspace
    "jump":    (".jump_cmd", "jump_cmd", "Jump to a project"),
    "project": (".project_cmd", "project_cmd", "Manage project scanning & aliases"),
    "run":     (".run_cmd", "run_cmd", "Run scripts from project config"),
    "group":   (".group_cmd", "group_cmd", "Manage project groups"),
    
    # Core
    "save":    (".save_cmd", "save_command", "Save commands or variables"),
    "get":     (".get_cmd", "get_cmd", "Retrieve saved commands"),
    "config":  (".config_cmd", "config_cmd", "Manage configuration"),
    "git":     (".git_cmd", "git_cmd", "Manage GitHub accounts & SSH"),
    
    # Utils
    "copy":    (".copy_cmd", "copy_cmd", "Copy file contents to clipboard"),
    "watch":   (".watch_cmd", "watch_cmd", "Record project-specific history"),
    "bank":    (".bank_cmd", "bank_cmd", "Manage storage locations"),
    "clear":   (".clear_cmd", "clear_cmd", "Clear/clean history & data"),
    "setup":   (".setup_cmd", "setup_cmd", "Install shell hooks"),
    "ask":     (".ask_cmd", "ask_cmd", "Ask AI for command help"),
}

CATEGORIES = {
    "Workspace & Navigation": ["project", "jump", "group", "run"],
    "Core & Configuration":   ["init", "hello", "config", "setup"],
    "History & Storage":      ["save", "get", "clear", "bank"],
    "Tools & Utilities":      ["ask", "git", "copy", "watch"],
}

class LazyGroup(click.Group):
    def list_commands(self, ctx):
        return sorted(list(COMMAND_MAP.keys()) + ["init", "hello"])

    def get_command(self, ctx, cmd_name):
        # 1. Handle Built-ins
        if cmd_name == "init": return init
        if cmd_name == "hello": return hello

        if cmd_name in COMMAND_MAP:
            module_name, func_name, _ = COMMAND_MAP[cmd_name] # Ignore desc here
            try:
                mod = __import__(f"cwm{module_name}", fromlist=[func_name])
                return getattr(mod, func_name)
            except ImportError as e:
                # Error handling remains the same...
                click.echo(f"Error loading command '{cmd_name}': {e}", err=True)
                return None
            except AttributeError:
                return None

        possibilities = list(COMMAND_MAP.keys()) + ["init", "hello"]
        close = get_close_matches(cmd_name, possibilities, n=1, cutoff=0.45)
        if close:
            ctx.fail(f"Unknown command '{cmd_name}'. Did you mean '{close[0]}'?")
        
        return None

    def format_commands(self, ctx, formatter):
        """
        FAST HELP: Reads descriptions from COMMAND_MAP instead of importing modules.
        """
        commands = [
            ("init", init.get_short_help_str()),
            ("hello", hello.get_short_help_str())
        ]

        for name, data in COMMAND_MAP.items():
            desc = data[2] # Index 2 is the description
            commands.append((name, desc))

        if not commands:
            return


        cmd_to_cat = {}
        for cat, cmds in CATEGORIES.items():
            for c in cmds:
                cmd_to_cat[c] = cat

        buckets = {cat: [] for cat in CATEGORIES}
        buckets["Other Commands"] = []

        for name, help_text in commands:
            cat = cmd_to_cat.get(name, "Other Commands")
            buckets[cat].append((name, help_text))

        for cat in CATEGORIES:
            if buckets[cat]:
                heading = click.style(cat, fg="yellow", bold=True)
                with formatter.section(heading):
                    styled_rows = [
                        (click.style(name, fg="green"), help_text) 
                        for name, help_text in sorted(buckets[cat])
                    ]
                    formatter.write_dl(styled_rows)
        
        if buckets["Other Commands"]:
            with formatter.section(click.style("Other Commands", fg="yellow", bold=True)):
                styled_rows = [
                    (click.style(name, fg="green"), help_text) 
                    for name, help_text in sorted(buckets["Other Commands"])
                ]
                formatter.write_dl(styled_rows)

CONTEXT_SETTINGS = dict(
    help_option_names=["-h", "--help"],
    max_content_width=120
)

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
    if not GLOBAL_CWM_BANK.exists():
        safe_create_cwm_folder(GLOBAL_CWM_BANK)


@cli.command(cls=RichHelpCommand)
def init():
    """Initializes a .cwm folder in the current directory."""
    current_path = Path.cwd()
    project_path = current_path / CWM_BANK_NAME

    if is_path_literally_inside_bank(current_path):
        console.print(f"[red]ERROR:[/red] Cannot create a .cwm bank inside another .cwm bank.")
        return

    if project_path.exists():
        safe_create_cwm_folder(project_path, repair=True)
        console.print("[yellow]A .cwm bank already exists in this project.[/yellow]")
        return

    if not has_write_permission(current_path):
        console.print("[red]ERROR:[/red] You do not have permission to create a CWM bank in this folder.")
        return

    ok = safe_create_cwm_folder(project_path, repair=False)
    if ok:
        console.print("[green]Initialized empty CWM bank in this project.[/green]")
    else:
        console.print("[red]CWM initialization failed.[/red]")

@cli.command(cls=RichHelpCommand)
def hello():
    """System diagnostics."""
    console.print(f"[bold green]CWM v{__version__}[/bold green]")
    
    # System Info
    console.print(f"[bold blue]System:[/bold blue]  {platform.system()} {platform.release()}")
    
    # History File
    hist = get_history_file_path()
    hist_status = f"[white]{hist}[/white]" if hist else "[red]Not Detected[/red]"
    console.print(f"[bold blue]History:[/bold blue] {hist_status}")
    
    # Sync Warning
    if not is_history_sync_enabled():
        console.print("[yellow]! Notice: Real-time sync not enabled (Run 'cwm setup' on Linux/Mac).[/yellow]")
        
    console.print("")
    
    # Documentation Link (Clickable in modern terminals)
    console.print(f"[bold]Documentation:[/bold] [blue underline link={DOCS_LINK}]{DOCS_LINK}[/blue underline link]")
    
    # Footer
    console.print("[cyan]Developed by ISU[/cyan]")

if __name__ == "__main__":
    cli()