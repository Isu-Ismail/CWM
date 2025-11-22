# src/cwm/jump_cmd.py
import click
import subprocess
import os
import shutil
import shlex
from .storage_manager import StorageManager
from difflib import get_close_matches

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
            if shutil.which("gnome-terminal"):
                subprocess.Popen(["gnome-terminal", "--working-directory", path])
            elif shutil.which("open"): # Mac
                subprocess.Popen(["open", "-a", "Terminal", path])
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

# --- COMMAND ---

@click.command("jump")
@click.argument("names", required=False)
@click.option("-t", "--terminal", is_flag=True, help="Also open a new terminal window.")
@click.option("-l", "--list", "list_mode", is_flag=True, help="Force list mode.")
@click.option("-n", "count", default="10", help="Number of projects to show (or 'all'). Default: 10.")
def jump_cmd(names, terminal, list_mode, count):
    """
    Jump to a project.
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        click.echo("No projects found. Run 'cwm project scan' first.")
        return

    raw_input = ""

    if list_mode or not names:
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
        
        if is_all or limit >= len(projects):
            header = f"--- All Projects ({len(projects)}) ---"
        else:
            header = f"--- Top {len(display_list)} Projects (Sorted by Hits) ---"

        click.echo(header)

        # --- NEW FORMATTING LOGIC ---
        for p in display_list:
            hits = p.get('hits', 0)
            pid = p['id']
            alias = p['alias']
            path = p['path']
            
            # Format: [ID] (Hits: X)   Alias ........ Path
            # {alias:<25} ensures the name takes up 25 chars for alignment
            click.echo(f" [{pid}] (Hits: {hits})  {alias:<25} : {path}")
        
        remaining = len(projects) - len(display_list)
        if remaining > 0:
            click.echo(f"...and {remaining} more. (Run 'cwm jump -n all' to see everything)")

        raw_input = click.prompt("Select IDs/Aliases (comma-separated)", default="", show_default=False)
    else:
        raw_input = names

    if not raw_input: return

    tokens = raw_input.split(',')
    valid_targets = []

    for token in tokens:
        target = _resolve_project(token, projects)
        if target:
            if target not in valid_targets:
                valid_targets.append(target)

    if not valid_targets:
        click.echo("No valid projects found.")
        return

    click.echo(f"Launching {len(valid_targets)} project(s)...")
    
    for target in valid_targets:
        target["hits"] = target.get("hits", 0) + 1
        _launch_editor(target["path"], manager)
        if terminal:
            _launch_terminal(target["path"])

    manager.save_projects(data)