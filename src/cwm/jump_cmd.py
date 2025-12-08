# src/cwm/jump_cmd.py
import sys
import click
import subprocess
import os
import shutil
import shlex
from .storage_manager import StorageManager
from difflib import get_close_matches
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from .rich_help import RichHelpCommand

console = Console()


def _launch_editor(path: str, manager: StorageManager):
    """Smart Launcher: Console apps -> New Window, GUI apps -> Detached."""
    config = manager.get_config()
    editor_config = config.get("default_editor", "code")
    is_windows = os.name == 'nt'
    click.echo(f"Opening {editor_config} in: {path}")

    try:
        args = shlex.split(editor_config)
        cmd_exec = args[0].lower()
        console_apps = ["jupyter", "python", "cmd", "powershell", "pwsh", "wt", "vim", "nano"]
        is_console_app = any(app in cmd_exec for app in console_apps)

        if len(args) == 1 and not is_console_app:
            args.append(".")

        if is_windows:
            executable = shutil.which(args[0])
            if is_console_app:
                if executable:
                    subprocess.Popen(args, cwd=path, creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen(args, cwd=path, shell=True)
            else:
                subprocess.Popen(args, cwd=path, shell=True)
        else:
            if not shutil.which(args[0]):
                 click.echo(f"Error: Command '{args[0]}' not found.")
                 return
            subprocess.Popen(args, cwd=path)
    except Exception as e:
        click.echo(f"Error launching editor: {e}")

def _launch_terminal(path: str):
    """Launches a new terminal window detached."""
    is_windows = os.name == 'nt'
    try:
        if is_windows:
            if shutil.which("wt"):
                subprocess.Popen(["wt", "-d", path], shell=True)
                click.echo("Opening Windows Terminal...")
            else:
                subprocess.Popen(["start", "cmd", "/k", f"cd /d {path}"], shell=True)
        else:
            # --- MAC OS ---
            if sys.platform == "darwin":
                
                if os.path.exists("/Applications/iTerm.app"):
                     subprocess.Popen(["open", "-a", "iTerm", path])
                else:
                     subprocess.Popen(["open", "-a", "Terminal", path])
            
            # --- LINUX ---
            else:
                #common terminals
                terminals = [
                    "gnome-terminal", "konsole", "xfce4-terminal", 
                    "terminator", "alacritty", "xterm"
                ]
                
                launched = False
                for term in terminals:
                    if shutil.which(term):
                        if term == "gnome-terminal":
                            subprocess.Popen([term, "--working-directory", path])
                        elif term == "konsole":
                            subprocess.Popen([term, "--workdir", path])
                        else:
                            
                            subprocess.Popen([term], cwd=path)
                        
                        click.echo(f"Opening {term}...")
                        launched = True
                        break
                
                if not launched:
                    click.echo("Could not detect a supported terminal (Gnome, Konsole, Terminator, etc).")

    except Exception as e:
        click.echo(f"Failed to launch terminal: {e}")

def _resolve_project(token: str, projects: list):
    token = token.strip()
    if not token: return None
    if token.isdigit():
        found = next((p for p in projects if p["id"] == int(token)), None)
        if found: return found
    found = next((p for p in projects if p["alias"] == token), None)
    if found: return found
    aliases = [p["alias"] for p in projects]
    matches = get_close_matches(token, aliases, n=1, cutoff=0.6)
    if matches:
        return next((p for p in projects if p["alias"] == matches[0]), None)
    return None






@click.command("jump", cls=RichHelpCommand)
@click.argument("names", required=False)
@click.option("-t", "--terminal", is_flag=True, help="Also open a new terminal window.")
@click.option("-l", "--list", "list_mode", is_flag=True, help="Force list mode.")
@click.option("-n", "count", default="10", help="Number of projects to show (or 'all').")
def jump_cmd(names, terminal, list_mode, count):
    """
    Jump to a project (Launch Editor + Terminal).
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        console.print("\n  [yellow]! No projects found. Run 'cwm project scan' first.[/yellow]\n")
        return

    raw_input = ""

    # --- 1. LIST MODE (Table View) ---
    if list_mode or not names:
        # Sort: Highest hits first, then alphabetical
        sorted_projs = sorted(projects, key=lambda x: (-x.get("hits", 0), x["alias"]))
        
        limit = 10
        is_all = False
        
        if str(count).lower() == "all":
            limit = len(sorted_projs)
            is_all = True
        else:
            try:
                limit = int(count)
                if limit <= 0: limit = 10
            except ValueError:
                limit = 10 
        
        display_list = sorted_projs[:limit]
        
        console.print("") # Spacing
        
        # Determine Title
        if is_all or limit >= len(projects):
            title = f"All Projects ({len(projects)})"
        else:
            title = f"Top {len(display_list)} Projects [dim](Sorted by Hits)[/dim]"

        # Create Clean Table
        table = Table(title=title, title_justify="left", box=None, padding=(0, 2), show_lines=False)
        table.add_column("ID", justify="right", style="green")
        table.add_column("Hits", justify="right", style="yellow")
        table.add_column("Alias", style="bold cyan")
        table.add_column("Path", style="dim white")

        for p in display_list:
            table.add_row(
                str(p['id']), 
                str(p.get('hits', 0)), 
                p['alias'], 
                str(p['path'])
            )
        
        console.print(table)
        
        remaining = len(projects) - len(display_list)
        if remaining > 0:
            console.print(f"\n  [dim]...and {remaining} more. (Run 'cwm jump -n all' to see everything)[/dim]")

        console.print("")
        raw_input = Prompt.ask("  [bold cyan]?[/bold cyan] Select IDs/Aliases [dim](comma-separated)[/dim]", default="")
    else:
        raw_input = names

    if not raw_input: 
        return

    # --- 2. RESOLVE TARGETS ---
    tokens = raw_input.split(',')
    valid_targets = []

    for token in tokens:
        target = _resolve_project(token.strip(), projects)
        if target:
            if target not in valid_targets:
                valid_targets.append(target)

    if not valid_targets:
        console.print("\n  [red]✖ No valid projects found.[/red]\n")
        return

    # --- 3. LAUNCH LOOP (Modern Style) ---
    console.print("") # Spacing
    
    for target in valid_targets:
        # Update Hits
        target["hits"] = target.get("hits", 0) + 1
        
        alias = target['alias']
        path = target['path']
        
        # STYLE: Matches your screenshot
        # ✔ Found project: my-backend-api
        # @ ~/dev/work/my-backend-api
        console.print(f"  [bold green]✔ Found project:[/bold green] [bold blue]{alias}[/bold blue]")
        console.print(f"  [dim]@[/dim] [dim]{path}[/dim]")
        console.print("")
        
        # i Launching VS Code...
        console.print(f"  [bold cyan]i[/bold cyan] Launching Editor...")
        _launch_editor(path, manager)
        
        if terminal:
            console.print(f"  [bold cyan]i[/bold cyan] Launching Terminal...")
            _launch_terminal(path)

        console.print("  [dim]Done.[/dim]\n")

    # Save hits
    manager.save_projects(data)