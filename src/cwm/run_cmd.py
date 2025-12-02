# src/cwm/run_cmd.py
import click
import time
import sys
import os
import shutil
import subprocess
from .storage_manager import StorageManager

# try:
from .service_manager import ServiceManager
# except ImportError:
#     ServiceManager = None

def _require_gui_deps():
    if ServiceManager is None:
        click.echo("Error: Missing dependencies.")
        click.echo("Run: pip install cwm-cli[gui]")
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
    Launches the GUI in a detached process.
    On Windows: Opens a new console window (or no window if configured in gui_app).
    On Mac/Linux: Attempts to open in a terminal emulator.
    """
    args = [sys.executable, "-m", "cwm.cli", "run", "_gui-internal"]
    is_windows = os.name == 'nt'
    
    try:
        if is_windows:
            # CREATE_NEW_CONSOLE ensures it doesn't block the current terminal
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            if sys.platform == "darwin":
                cmd_str = f"'{sys.executable}' -m cwm.cli run _gui-internal"
                subprocess.Popen(["open", "-a", "Terminal", cmd_str])
            else:
                # Linux: Try common terminal emulators
                cmd_str = f"{sys.executable} -m cwm.cli run _gui-internal; exec bash"
                if shutil.which("gnome-terminal"): 
                    subprocess.Popen(["gnome-terminal", "--", "bash", "-c", cmd_str])
                elif shutil.which("konsole"): 
                    subprocess.Popen(["konsole", "-e", "bash", "-c", cmd_str])
                elif shutil.which("xterm"): 
                    subprocess.Popen(["xterm", "-e", cmd_str])
                else:
                    click.echo("Error: No suitable terminal emulator found (gnome-terminal, konsole, xterm).")
                    return
        
        click.echo("Launching Dashboard...")
    except Exception as e:
        click.echo(f"Failed to launch GUI: {e}")

@click.group("run")
def run_cmd():
    """Orchestrate background processes."""
    pass

@run_cmd.command("project")
@click.argument("target", required=False)
def run_project(target):
    if not _require_gui_deps(): return
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        click.echo("No projects saved.")
        return

    if not target:
        click.echo("--- Available Projects ---")
        for p in sorted(projects, key=lambda x: x["id"]):
            click.echo(f"[{p['id']}] {p['alias']:<20} : {p.get('startup_cmd', '-')}")
        
        target = click.prompt("Select Project ID/Alias", default="", show_default=False)
        if not target: return

    pid = _resolve_project_id(target, projects)
    if pid is None:
        click.echo(f"Project '{target}' not found.")
        return

    svc = ServiceManager()
    success, msg = svc.start_project(pid)
    if success: click.echo(f"✔ {msg}")
    else: click.echo(f"✘ Failed: {msg}")

@run_cmd.command("group")
@click.argument("target", required=False)
def run_group(target):
    if not _require_gui_deps(): return
    manager = StorageManager()
    data = manager.load_projects()
    groups = data.get("groups", [])
    projects = data.get("projects", [])
    
    if not groups:
        click.echo("No groups found.")
        return

    if not target:
        click.echo("--- Available Groups ---")
        for g in sorted(groups, key=lambda x: x["id"]):
            count = len(g.get("project_ids", []))
            click.echo(f"[{g['id']}] {g['alias']:<20} ({count} projects)")
        
        target = click.prompt("Select Group ID/Alias", default="", show_default=False)
        if not target: return

    gid = _resolve_group_id(target, groups)
    if not gid:
        click.echo(f"Group '{target}' not found.")
        return
        
    group = next(g for g in groups if g["id"] == gid)
    pids = group.get("project_ids", [])
    
    if not pids:
        click.echo("Group is empty.")
        return

    svc = ServiceManager()
    click.echo(f"Starting group '{group['alias']}'...")
    for pid in pids:
        p_alias = next((p['alias'] for p in projects if p['id'] == pid), str(pid))
        success, msg = svc.start_project(pid)
        icon = "✔" if success else "✘"
        click.echo(f"  {icon} {p_alias:<15}: {msg}")

@run_cmd.command("stop")
@click.argument("target", required=False)
@click.option("--all", is_flag=True, help="Stop ALL running services.")
def stop_service(target, all):
    if not _require_gui_deps(): return
    svc = ServiceManager()
    
    if all:
        count = svc.stop_all()
        click.echo(f"Stopped {count} services.")
        return

    if not target:
        active = svc.get_services_status()
        running_items = {k: v for k, v in active.items() if v["status"] == "running"}
        
        if not running_items:
            click.echo("No services are currently running.")
            return

        click.echo("--- Running Services ---")
        for info in running_items.values():
             click.echo(f"[{info['project_id']}] {info['alias']}")
        
        target = click.prompt("Select ID/Alias to stop", default="", show_default=False)
        if not target: return

    manager = StorageManager()
    pid = _resolve_project_id(target, manager.load_projects().get("projects", []))
    
    if not pid:
        click.echo("Project not found.")
        return

    success, msg = svc.stop_project(pid)
    if success: click.echo(f"✔ {msg}")
    else: click.echo(f"✘ {msg}")

@run_cmd.command("remove")
@click.argument("target", required=False) 
def remove_service(target):
    """
    Stop AND remove service(s) from the Orchestrator list.
    Accepts single ID (1) or comma-separated list (1,2).
    """
    if not _require_gui_deps(): return
    svc = ServiceManager()
    manager = StorageManager()
    
    # --- 1. Interactive Mode ---
    if not target:
        state = svc.get_services_status()
        if not state:
            click.echo("Orchestrator list is empty.")
            return
        click.echo("--- Orchestrator List ---")
        for info in state.values():
            status = info.get('status', 'stopped')
            click.echo(f"[{info['project_id']}] {info['alias']} ({status})")
        
        target = click.prompt("Select ID(s) to remove (e.g. 1,3)", default="", show_default=False)
        if not target: return

    # --- 2. Process Multiple Targets ---
    tokens = [t.strip() for t in str(target).split(',') if t.strip()]
    projects_data = manager.load_projects().get("projects", [])

    if not tokens: return

    for token in tokens:
        pid = _resolve_project_id(token, projects_data)
        
        if not pid:
            click.echo(f"Project '{token}' not found.")
            continue

        project_alias = next((p['alias'] for p in projects_data if p['id'] == pid), f"ID {pid}")
        success, msg = svc.remove_entry(pid)
        
        if success:
            click.echo(f"Project '{project_alias}' removed.")
        else:
            click.echo(f"Failed to remove '{project_alias}': {msg}")

@run_cmd.command("list")
def list_running():
    if not _require_gui_deps(): return
    svc = ServiceManager()
    state = svc.get_services_status()
    
    if not state:
        click.echo("Orchestrator is empty.")
        return
        
    click.echo(f"--- Orchestrator Services ({len(state)}) ---")
    click.echo(f"{'ID':<5} {'Alias':<20} {'Status':<10} {'PID':<8} {'Uptime'}")
    
    now = time.time()
    sorted_items = sorted(state.items(), key=lambda x: (x[1]['status'] != 'running', x[1]['project_id']))

    for _, info in sorted_items:
        status = info['status'].upper()
        pid_str = str(info['pid']) if info['pid'] else "-"
        s_color = "green" if status == "RUNNING" else "red" if status == "ERROR" else "white"
        
        uptime_str = "-"
        if status == "RUNNING":
            uptime = int(now - info["start_time"])
            m, s = divmod(uptime, 60)
            h, m = divmod(m, 60)
            uptime_str = f"{h}h {m}m" if h else f"{m}m"

        click.echo(
            f"{info['project_id']:<5} "
            f"{info['alias']:<20} "
            f"{click.style(status, fg=s_color):<10} "
            f"{pid_str:<8} "
            f"{uptime_str}"
        )

# --- GUI / AGENT COMMANDS ---

@run_cmd.command("_watcher", hidden=True)
def internal_watcher():
    """Background process that monitors PIDs. REQUIRED for ServiceManager."""
    if not _require_gui_deps(): return
    try:
        svc = ServiceManager()
        svc.run_watcher_loop()
    except KeyboardInterrupt:
        pass

@run_cmd.command("_gui-internal", hidden=True)
def internal_gui_entry():
    """Actual entry point for the GUI window."""
    if not _require_gui_deps(): return
    try:
        from .gui_app import run_gui
        run_gui()
    except Exception as e:
        print(f"GUI Crash: {e}")
        input("Press Enter...")

@run_cmd.command("gui")
def launch_gui_detached():
    """Public command to launch the dashboard."""
    _launch_detached_gui()

@run_cmd.command("logs")
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
        click.echo(f"Project '{target}' not found.")
        return

    # 2. Locate Log File
    from .service_manager import LOG_DIR
    log_path = LOG_DIR / f"{pid}.log"

    if not log_path.exists():
        click.echo(f"No logs found for project {pid}.")
        return

    # 3. Read / Follow
    try:
        if follow:
            click.echo(f"--- Following logs for ID {pid} (Ctrl+C to stop) ---")
            with open(log_path, "r", encoding="utf-8") as f:
                # PHASE 1: Read existing history
                # We read everything currently in the file and print it.
                existing_data = f.read()
                if existing_data:
                    click.echo(existing_data, nl=False)

                # PHASE 2: Watch for new lines (Tail)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1) # Wait for new data
                        continue
                    click.echo(line, nl=False)
        else:
            # Static Dump
            click.echo(f"--- Logs for ID {pid} ---")
            with open(log_path, "r", encoding="utf-8") as f:
                click.echo(f.read())
                
    except KeyboardInterrupt:
        click.echo("\nStopped.")
    except Exception as e:
        click.echo(f"Error reading logs: {e}")


@run_cmd.command("kill")
def kill_all_processes():
    """
    EMERGENCY: Force kill all projects and the background watcher.
    Use this if the system gets stuck or you want a hard reset.
    """
    if not _require_gui_deps(): return
    svc = ServiceManager()
    
    click.echo(click.style("⚠ Initiating Hard Kill Sequence...", fg="yellow"))
    
    # Execute Nuke
    count, w_msg = svc.nuke_all()
    
    # Report
    if count > 0:
        click.echo(f"✔ Terminated {count} active projects.")
    else:
        click.echo("• No active projects found.")
        
    if "killed" in w_msg:
        click.echo(f"✔ {w_msg}")
    else:
        click.echo(f"• {w_msg}")

    click.echo(click.style("✔ System Cleaned.", fg="green", bold=True))

@run_cmd.command("launch")
@click.argument("target", required=False)
def launch_terminal(target):
    """
    Opens a new terminal window streaming the logs.
    """
    if not _require_gui_deps(): return
    manager = StorageManager()
    svc = ServiceManager()
    
    # 1. Interactive Selection
    if not target:
        state = svc.get_services_status()
        running = {k:v for k,v in state.items() if v['status'] == 'running'}
        if not running:
            click.echo("No running projects to view.")
            return
        click.echo("--- Running Projects ---")
        for info in running.values():
            click.echo(f"[{info['project_id']}] {info['alias']}") 
        target = click.prompt("Select Project ID", default="", show_default=False)
        if not target: return

    # 2. Resolve ID
    projects = manager.load_projects().get("projects", [])
    pid = _resolve_project_id(target, projects)
    if not pid:
        click.echo("Project not found.")
        return

    # 3. Launch the Monitor Window
    cmd_args = [sys.executable, "-m", "cwm.cli", "run", "logs", "-f", str(pid)]
    click.echo(f"Launching terminal for Project {pid}...")

    try:
        proc = None
        
        if os.name == 'nt':
            # Windows
            proc = subprocess.Popen(
                cmd_args, 
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            # Linux/Mac (Logic to detect terminal emulator)
            cmd_str = f"{sys.executable} -m cwm.cli run logs -f {pid}"
            if sys.platform == "darwin":
                 proc = subprocess.Popen(["open", "-a", "Terminal", cmd_str])
            elif shutil.which("gnome-terminal"):
                proc = subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{cmd_str}; exec bash"])
            # ... (other linux terminals) ...

        # 4. CRITICAL: Register the Viewer PID
        if proc and proc.pid:
            svc.register_viewer(pid, proc.pid)
            
    except Exception as e:
        click.echo(f"Failed to launch terminal: {e}")

@run_cmd.command("clean")
def clean_logs():
    """
    Attempts to delete all log files.
    Reports if any files are locked by open windows.
    """
    if not _require_gui_deps(): return
    from .service_manager import LOG_DIR
    
    if not LOG_DIR.exists():
        click.echo("No log directory found.")
        return

    click.echo("Cleaning logs...")
    deleted = 0
    locked = 0

    for log_file in LOG_DIR.glob("*.log"):
        try:
            log_file.unlink() # Delete file
            deleted += 1
        except PermissionError:
            locked += 1
            click.echo(f"⚠ Locked: {log_file.name} (Close open log terminals!)")
        except Exception as e:
            click.echo(f"✘ Error {log_file.name}: {e}")

    if deleted > 0:
        click.echo(f"✔ Deleted {deleted} log files.")
    
    if locked > 0:
        click.echo(f"\n{locked} files were locked. Please close any 'cwm run launch' windows.")
        click.echo("Notice:If you cant see any terminal run this 'taskkill /F /IM python.exe'",color="orange")
    else:
        click.echo("✔ All clean.")