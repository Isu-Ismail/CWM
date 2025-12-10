import click
import time
import sys
import os
import shutil
import subprocess

# Rich Imports
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from .storage_manager import StorageManager
from .service_manager import ServiceManager
from .rich_help import RichHelpGroup, RichHelpCommand

# Initialize Console
console = Console()

def _require_gui_deps():
    if ServiceManager is None:
        console.print("[red]✖ Error: Missing dependencies.[/red]")
        console.print("  Run: [bold]pip install cwm-cli[gui][/bold]")
        return False
    return True

def _resolve_project_id(token, projects):
    token = str(token).strip()
    if token.isdigit():
        tid = int(token)
        if any(p["id"] == tid for p in projects):
            return tid
    for p in projects:
        if p["alias"] == token:
            return p["id"]
    return None

def _resolve_group_id(token, groups):
    token = str(token).strip()
    if token.isdigit():
        gid = int(token)
        if any(g["id"] == gid for g in groups):
            return gid
    for g in groups:
        if g["alias"] == token:
            return g["id"]
    return None

def _launch_detached_gui():
    """
    Launches the GUI silently (no black window) and COMPLETELY DETACHED.
    Redirects stdout/stderr to DEVNULL so the terminal doesn't hang.
    """
    args = [sys.executable, "-m", "cwm.cli", "run", "_gui-internal"]
    is_windows = os.name == 'nt'
    
    try:
        # FIX: Redirect all streams to DEVNULL to prevent terminal freezing
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

        if is_windows:
            # CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(args, creationflags=0x08000000, **kwargs)
        else:
            if sys.platform == "darwin":
                # Mac specific open command
                cmd_str = f"'{sys.executable}' -m cwm.cli run _gui-internal"
                subprocess.Popen(["open", "-a", "Terminal", cmd_str])
            else:
                # Linux: start_new_session=True acts like setsid
                subprocess.Popen(args, start_new_session=True, **kwargs)
        
        console.print("[green]✔ Launching Dashboard...[/green]")
    except Exception as e:
        console.print(f"[red]✖ Failed to launch GUI: {e}[/red]")


@click.group("run", cls=RichHelpGroup)
def run_cmd():
    """Orchestrate background processes."""
    pass

@run_cmd.command("project", cls=RichHelpCommand, help="Run a single project in background")
@click.argument("target", required=False)
def run_project(target):
    if not _require_gui_deps(): return
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        console.print("[dim]No projects saved.[/dim]")
        return

    if not target:
        console.print("\n[bold]Available Projects[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        
        for p in sorted(projects, key=lambda x: x["id"]):
            cmd_prev = p.get('startup_cmd', '-') or "-"
            if len(cmd_prev) > 30: cmd_prev = cmd_prev[:27] + "..."
            
            table.add_row(
                f"[cyan][{p['id']}][/cyan]", 
                f"[bold white]{p['alias']}[/bold white]", 
                f"[dim]{cmd_prev}[/dim]"
            )
        
        console.print(table)
        console.print("")
        target = Prompt.ask("  [bold cyan]?[/bold cyan] Select Project ID/Alias", default="", show_default=False)
        if not target: return

    pid = _resolve_project_id(target, projects)
    if pid is None:
        console.print(f"[red]✖ Project '{target}' not found.[/red]")
        return

    
    # --- STARTUP CHECK ---
    project = next(p for p in projects if p["id"] == pid)
    if not project.get("startup_cmd"):
        console.print(f"[red]✖ Error: Project '{project['alias']}' has no startup command.[/red]")
        console.print(f"  [dim]Run 'cwm project edit -id {pid}' to add one.[/dim]")
        return

    svc = ServiceManager()
    success, msg = svc.start_project(pid)
    
    if success: 
        console.print(f"[green]✔ {msg}[/green]")
    else: 
        console.print(f"[red]✖ Failed: {msg}[/red]")


@run_cmd.command("gui", cls=RichHelpCommand)
def launch_gui_detached():
    """Public command to launch the dashboard."""
    _launch_detached_gui()

@run_cmd.command("group", cls=RichHelpCommand, help="Run group of projects")
@click.argument("target", required=False)
def run_group(target):
    if not _require_gui_deps(): return
    manager = StorageManager()
    data = manager.load_projects()
    groups = data.get("groups", [])
    projects = data.get("projects", [])
    
    if not groups:
        console.print("[dim]No groups found.[/dim]")
        return

    if not target:
        console.print("\n[bold]Available Groups[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        
        for g in sorted(groups, key=lambda x: x["id"]):
            count = len(g.get("project_list", [])) 
            table.add_row(
                f"[cyan][{g['id']}][/cyan]", 
                f"[bold white]{g['alias']}[/bold white]", 
                f"[dim]({count} projects)[/dim]"
            )
        
        console.print(table)
        console.print("")
        target = Prompt.ask("  [bold cyan]?[/bold cyan] Select Group ID/Alias", default="", show_default=False)
        if not target: return

    gid = _resolve_group_id(target, groups)
    if not gid:
        console.print(f"[red]✖ Group '{target}' not found.[/red]")
        return
        
    group = next(g for g in groups if g["id"] == gid)
    
    # Extract IDs from project_list
    pids = []
    for item in group.get("project_list", []):
        if isinstance(item, dict): pids.append(item.get("id"))
        else: pids.append(item)

    if not pids:
        console.print("[yellow]! Group is empty.[/yellow]")
        return

    # --- PRE-VALIDATION CHECK ---
    missing_cmds = []
    for pid in pids:
        proj = next((p for p in projects if p['id'] == pid), None)
        if proj and not proj.get("startup_cmd"):
            missing_cmds.append(proj['alias'])

    if missing_cmds:
        console.print(f"[bold red]✖ Aborted: The following projects have no startup command:[/bold red]")
        for alias in missing_cmds:
            console.print(f"  - [red]{alias}[/red]")
        return

    svc = ServiceManager()
    console.print(f"\n[bold]Starting group '{group['alias']}'...[/bold]")
    
    for pid in pids:
        p_alias = next((p['alias'] for p in projects if p['id'] == pid), str(pid))
        success, msg = svc.start_project(pid)
        if success:
            console.print(f"  [green]✔[/green] {p_alias:<15}: {msg}")
        else:
            console.print(f"  [red]✘[/red] {p_alias:<15}: {msg}")
    console.print("")

@run_cmd.command("stop", cls=RichHelpCommand, help="Stop bg process but maintain state")
@click.argument("target", required=False)
@click.option("--all", is_flag=True, help="Stop ALL running services.")
def stop_service(target, all):
    if not _require_gui_deps(): return
    svc = ServiceManager()
    
    if all:
        count = svc.stop_all()
        console.print(f"[green]✔ Stopped {count} services.[/green]")
        return

    if not target:
        active = svc.get_services_status()
        running_items = {k: v for k, v in active.items() if v["status"] == "running"}
        
        if not running_items:
            console.print("[yellow]! No services are currently running.[/yellow]")
            return

        console.print("\n[bold]Running Services[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        for info in running_items.values():
             table.add_row(f"[cyan][{info['project_id']}][/cyan]", info['alias'])
        console.print(table)
        console.print("")
        
        target = Prompt.ask("  [bold cyan]?[/bold cyan] Select ID/Alias to stop", default="", show_default=False)
        if not target: return

    manager = StorageManager()
    pid = _resolve_project_id(target, manager.load_projects().get("projects", []))
    
    if not pid:
        console.print("[red]✖ Project not found.[/red]")
        return

    success, msg = svc.stop_project(pid)
    if success: console.print(f"[green]✔ {msg}[/green]")
    else: console.print(f"[red]✘ {msg}[/red]")

@run_cmd.command("remove", cls=RichHelpCommand, help="Remove project from status tracker")
@click.argument("target", required=False) 
def remove_service(target):
    """
    Stop AND remove service(s) from the Orchestrator list.
    """
    if not _require_gui_deps(): return
    svc = ServiceManager()
    manager = StorageManager()
    
    if not target:
        state = svc.get_services_status()
        if not state:
            console.print("[dim]Orchestrator list is empty.[/dim]")
            return
        
        console.print("\n[bold]Orchestrator List[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        for info in state.values():
            status = info.get('status', 'stopped')
            color = "green" if status == "running" else "dim"
            table.add_row(f"[cyan][{info['project_id']}][/cyan]", info['alias'], f"[{color}]({status})[/{color}]")
        console.print(table)
        console.print("")
        
        target = Prompt.ask("  [bold cyan]?[/bold cyan] Select ID(s) to remove", default="", show_default=False)
        if not target: return

    tokens = [t.strip() for t in str(target).split(',') if t.strip()]
    projects_data = manager.load_projects().get("projects", [])

    if not tokens: return

    for token in tokens:
        pid = _resolve_project_id(token, projects_data)
        
        if not pid:
            console.print(f"[red]✖ Project '{token}' not found.[/red]")
            continue

        project_alias = next((p['alias'] for p in projects_data if p['id'] == pid), f"ID {pid}")
        success, msg = svc.remove_entry(pid)
        
        if success:
            console.print(f"[green]✔ Project '{project_alias}' removed.[/green]")
        else:
            console.print(f"[red]✖ Failed to remove '{project_alias}': {msg}[/red]")

@run_cmd.command("list", cls=RichHelpCommand, help="List running processes")
def list_running():
    if not _require_gui_deps(): return
    svc = ServiceManager()
    state = svc.get_services_status()
    
    if not state:
        console.print("[dim]Orchestrator is empty.[/dim]")
        return
        
    table = Table(title="Orchestrator Services", border_style="dim", box=None, padding=(0, 2))
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Alias", style="bold white")
    table.add_column("Status", style="bold")
    table.add_column("PID", justify="right", style="dim")
    table.add_column("Uptime", justify="right")
    
    now = time.time()
    sorted_items = sorted(state.items(), key=lambda x: (x[1]['status'] != 'running', x[1]['project_id']))

    for _, info in sorted_items:
        status = info['status'].upper()
        pid_str = str(info['pid']) if info['pid'] else "-"
        s_color = "green" if status == "RUNNING" else "red" if status == "ERROR" else "dim"
        
        uptime_str = "-"
        if status == "RUNNING":
            uptime = int(now - info["start_time"])
            m, s = divmod(uptime, 60)
            h, m = divmod(m, 60)
            uptime_str = f"{h}h {m}m" if h else f"{m}m"

        table.add_row(
            str(info['project_id']),
            info['alias'],
            f"[{s_color}]{status}[/{s_color}]",
            pid_str,
            uptime_str
        )

    console.print(table)
    console.print("")

# --- GUI / AGENT COMMANDS ---

@run_cmd.command("_watcher", hidden=True)
def internal_watcher():
    if not _require_gui_deps(): return
    try:
        svc = ServiceManager()
        svc.run_watcher_loop()
    except KeyboardInterrupt:
        pass

@run_cmd.command("_gui-internal", hidden=True)
def internal_gui_entry():
    if not _require_gui_deps(): return
    try:
        from .gui.tk_app import run_gui
        run_gui()
    except Exception as e:
        print(f"GUI Crash: {e}")
        input("Press Enter...")

# --- RAW LOGS (Using click.echo to prevent freezing/colors issues) ---
@run_cmd.command("logs", cls=RichHelpCommand)
@click.argument("target")
@click.option("-f", "--follow", is_flag=True, help="Follow the log output (Ctrl+C to stop).")
def view_logs(target, follow):
    """
    View or follow logs for a specific project.
    """
    if not _require_gui_deps(): return
    manager = StorageManager()
    
    # 1. Resolve Target
    projects = manager.load_projects().get("projects", [])
    pid = _resolve_project_id(target, projects)
    
    if not pid:
        console.print(f"[red]✖ Project '{target}' not found.[/red]")
        return

    # 2. Locate Log File
    from .service_manager import LOG_DIR
    log_path = LOG_DIR / f"{pid}.log"

    if not log_path.exists():
        console.print(f"[yellow]! No logs found for project {pid}.[/yellow]")
        return

    # 3. Read / Follow (Use click.echo for safe, raw output)
    try:
        if follow:
            console.print(f"[dim]--- Following logs for ID {pid} (Ctrl+C to stop) ---[/dim]")
            with open(log_path, "r", encoding="utf-8") as f:
                # Read existing
                existing_data = f.read()
                if existing_data:
                    click.echo(existing_data, nl=False)

                # Tail
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1) 
                        continue
                    click.echo(line, nl=False)
        else:
            # Static Dump
            console.print(f"\n[bold]Logs for ID {pid}[/bold]")
            with open(log_path, "r", encoding="utf-8") as f:
                click.echo(f.read())
                
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    except Exception as e:
        console.print(f"[red]✖ Error reading logs:[/red] {e}")


@run_cmd.command("kill", cls=RichHelpCommand)
def kill_all_processes():
    """
    EMERGENCY: Force kill all projects.
    """
    if not _require_gui_deps(): return
    svc = ServiceManager()
    
    console.print("\n[bold red]⚠ Initiating Hard Kill Sequence...[/bold red]")
    
    killed_items, w_msg = svc.nuke_all()
    
    if killed_items:
        console.print(f"  [red]✔ Terminated {len(killed_items)} active processes:[/red]")
        for item in killed_items:
            console.print(f"    - {item}", style="red")
    else:
        console.print("  [dim]• No active projects found.[/dim]")

    if "terminated" in w_msg.lower():
        console.print(f"  [red]✔ {w_msg}[/red]")
    else:
        console.print(f"  [dim]• {w_msg}[/dim]")

    console.print("\n[bold green]✔ System Cleaned.[/bold green]\n")
    
@run_cmd.command("launch", cls=RichHelpCommand)
@click.argument("target", required=False)
def launch_terminal(target):
    """
    Opens a new terminal window streaming the logs.
    """
    if not _require_gui_deps(): return
    manager = StorageManager()
    svc = ServiceManager()
    
    if not target:
        state = svc.get_services_status()
        running = {k:v for k,v in state.items() if v['status'] == 'running'}
        if not running:
            console.print("[yellow]! No running projects.[/yellow]")
            return
            
        console.print("\n[bold]Running Projects[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        for info in running.values():
            table.add_row(f"[cyan][{info['project_id']}][/cyan]", info['alias'])
        console.print(table)
        console.print("")
        target = Prompt.ask("  [bold cyan]?[/bold cyan] Select Project ID", default="", show_default=False)
        if not target: return

    projects = manager.load_projects().get("projects", [])
    pid = _resolve_project_id(target, projects)
    if not pid:
        console.print("[red]✖ Project not found.[/red]")
        return

    cmd_args = [sys.executable, "-m", "cwm.cli", "run", "logs", "-f", str(pid)]
    console.print(f"[bold cyan]➜ Launching terminal for Project {pid}...[/bold cyan]")

    try:
        proc = None
        if os.name == 'nt':
            # Windows
            proc = subprocess.Popen(cmd_args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            # Mac / Linux
            cmd_str = f"{sys.executable} -m cwm.cli run logs -f {pid}"
            if sys.platform == "darwin":
                 proc = subprocess.Popen(["open", "-a", "Terminal", cmd_str])
            elif shutil.which("gnome-terminal"):
                proc = subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{cmd_str}; exec bash"])
        
        if proc and proc.pid:
            svc.register_viewer(pid, proc.pid)
    except Exception as e:
        console.print(f"[red]✖ Failed to launch: {e}[/red]")

@run_cmd.command("clean", cls=RichHelpCommand)
def clean_logs():
    """Attempts to delete all log files."""
    if not _require_gui_deps(): return
    from .service_manager import LOG_DIR
    
    if not LOG_DIR.exists():
        console.print("[dim]No log directory found.[/dim]")
        return

    console.print("[bold cyan]Cleaning logs...[/bold cyan]")
    deleted = 0
    locked = 0

    for log_file in LOG_DIR.glob("*.log"):
        try:
            log_file.unlink()
            deleted += 1
        except PermissionError:
            locked += 1
            console.print(f"  [yellow]⚠ Locked:[/yellow] {log_file.name}")
        except Exception as e:
            console.print(f"  [red]✖ Error {log_file.name}:[/red] {e}")

    if deleted > 0:
        console.print(f"[green]✔ Deleted {deleted} log files.[/green]")
    if locked > 0:
        console.print(f"\n[red]! {locked} files locked (Close open terminals).[/red]")
    else:
        console.print("[bold green]✔ All clean.[/bold green]")