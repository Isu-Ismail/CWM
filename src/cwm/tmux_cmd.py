import click
import libtmux
from pathlib import Path
from rich.console import Console
from rich.tree import Tree
import os
import subprocess

# Importing your actual project modules
from .storage_manager import StorageManager
from .rich_help import RichHelpCommand, RichHelpGroup

console = Console()

# The main "Mother Ship" session
VIEWER_SESSION_NAME = "cwm_viewer"

@click.group("tmux", cls=RichHelpGroup)
def tmux_cmd():
    """Manage tmux sessions, windows, and the server."""
    pass


# =================================================
# 1. GROUP (New Command)
# =================================================
@tmux_cmd.command("group", cls=RichHelpCommand)
@click.argument("selection", required=False)
@click.option("-t", "--to", help="Target Session Name")
@click.option("-w", "--win", help="Target Window Name")
@click.option("-l", "--launch", is_flag=True, help="Immediately launch after starting.")
def tmux_group(selection, to, win, launch):
    """
    Start a pre-defined Group of projects.
    """
    manager = StorageManager()
    data = manager.load_projects()
    groups = data.get("groups", [])
    all_projects = data.get("projects", [])

    if not groups:
        console.print("[yellow]No groups defined in projects.json[/yellow]")
        return

    # --- 1. Select Group ---
    target_group = None
    
    # Logic to resolve selection (ID or Alias)
    if selection:
        # Try finding by Alias first
        target_group = next((g for g in groups if g["alias"] == selection), None)
        # Try finding by ID
        if not target_group and selection.isdigit():
            target_group = next((g for g in groups if str(g["id"]) == selection), None)
            
        if not target_group:
            console.print(f"[red]Group '{selection}' not found.[/red]")
            return
    else:
        # Interactive Selection
        console.print("\n[bold cyan]Select Group[/bold cyan]")
        for i, g in enumerate(groups, 1):
            # Count projects in group
            count = len(g.get('project_list', []))
            console.print(f"[{i}] {g['alias']} [dim]({count} projects)[/dim]")
        
        sel_idx = click.prompt("\nSelection", type=int)
        if 1 <= sel_idx <= len(groups):
            target_group = groups[sel_idx - 1]
        else:
            return

    # --- 2. Resolve Projects in Group ---
    # Map all projects by ID for easy lookup
    project_map = {p['id']: p for p in all_projects}
    resolved_projects = []
    
    for item in target_group.get('project_list', []):
        pid = item.get('id')
        if pid in project_map:
            resolved_projects.append(project_map[pid])
        else:
            console.print(f"[yellow]Warning: Project ID {pid} in group not found.[/yellow]")

    if not resolved_projects:
        console.print("[red]No valid projects found in this group.[/red]")
        return

    # --- 3. Determine Target Session ---
    server = libtmux.Server()
    target_session_name = to

    if not target_session_name:
        # Wizard: Ask for Session
        console.print("\n[bold cyan]Target Session[/bold cyan]")
        options = [{"name": "+ Create New Session", "value": "NEW"}]
        for s in server.sessions:
            options.append({"name": s.name, "value": s.name})
            
        for i, opt in enumerate(options, 1):
            console.print(f"[{i}] {opt['name']}")
            
        s_idx = click.prompt("\nSelect Session", type=int, default=1)
        
        if options[s_idx - 1]["value"] == "NEW":
            target_session_name = click.prompt("Enter new session name")
        else:
            target_session_name = options[s_idx - 1]["value"]

    # --- 4. Determine Target Window ---
    target_window_name = win
    if not target_window_name and not win: # Only ask if flag not provided
        # Default to Group Alias
        default_name = target_group['alias']
        target_window_name = click.prompt("Window Name", default=default_name)

    # --- 5. Execute Launch ---
    _orchestrate_power_launch(server, resolved_projects, target_session_name, target_window_name, launch)


# =================================================
# 2. PROJECT (Updated to use Shared Logic)
# =================================================
@tmux_cmd.command("project", cls=RichHelpCommand)
@click.argument("selection", required=False)
@click.option("-t", "--to", help="Target Session Name (Power User Mode)")
@click.option("-w", "--win", help="Target Window Name (requires --to)")
@click.option("-l", "--launch", is_flag=True, help="Immediately launch after starting.")
@click.option("--local", is_flag=True, help="Run immediately in THIS terminal (Foreground).")
def tmux_project(selection, to, win, launch, local):
    """
    Start projects.
    Default: Starts them as floating background sessions.
    Power Mode: Use --to and --win to start and attach immediately.
    """
    manager = StorageManager()
    projects = manager.load_projects().get("projects", [])

    if not projects:
        console.print("[yellow]No projects found.[/yellow]")
        return

    # Foreground Local Mode
    if local:
        _run_local_project(projects, selection)
        return

    # Selection Logic
    if not selection:
        console.print("\n[bold cyan]Select Project to Start[/bold cyan]")
        for i, p in enumerate(projects, start=1):
            console.print(f"[{i}] {p['alias']}")
        selection = click.prompt("\nSelection", type=str)

    indices = _parse_selection(selection, len(projects))
    selected_projects = [projects[i] for i in indices]

    if not selected_projects:
        return

    server = libtmux.Server()
    _configure_tmux_server(server)

    # --- Power User Mode (Direct Attach) ---
    if to:
        win_name = win or "projects"
        _orchestrate_power_launch(server, selected_projects, to, win_name, launch)
        return

    # --- Default Mode (Floating) ---
    existing_sessions = {s.name for s in server.sessions} if server.sessions else set()
    for proj in selected_projects:
        alias = proj["alias"]
        if alias in existing_sessions:
            console.print(f"[yellow]Skipping '{alias}' (already running).[/yellow]")
            continue
            
        console.print(f"[blue]Starting '{alias}'...[/blue]")
        _start_floating_pane(server, proj)
    
    console.print("[green]Projects started. Use 'cwm tmux attach' to organize them.[/green]")


# =================================================
# 3. HELPER: The Power Launch Engine
# =================================================
def _orchestrate_power_launch(server, projects, session_name, window_name, launch_flag):
    """
    Shared logic to Start Floating Sessions -> Move them to Target Window -> Layout -> Launch.
    """
    # A. Ensure Target Session Exists
    if server.has_session(session_name):
        target_session = server.sessions.get(session_name=session_name)
    else:
        target_session = server.new_session(session_name=session_name, detach=True)
        console.print(f"[green]Created session '{session_name}'[/green]")

    # B. Ensure Target Window Exists
    target_window = target_session.windows.get(window_name=window_name, default=None)
    
    is_new_window = False
    if not target_window:
        # Create new window (attach=True makes it current, easier to join to)
        target_window = target_session.new_window(window_name=window_name, attach=True)
        is_new_window = True

    # C. Start & Move Loop
    console.print(f"[blue]Launching {len(projects)} projects into '{session_name}:{window_name}'...[/blue]")
    
    panes_added = 0
    for proj in projects:
        alias = proj["alias"]
        
        # 1. Start as floating (temp)
        _start_floating_pane(server, proj)
        
        # 2. Find that temp session
        # We need a small retry/wait? usually libtmux is fast enough
        if server.has_session(alias):
            temp_session = server.sessions.get(session_name=alias)
            temp_pane_id = temp_session.active_window.active_pane.id
            
            # 3. Move it to target
            try:
                target_window.cmd("join-pane", "-s", temp_pane_id)
                panes_added += 1
            except Exception as e:
                console.print(f"[red]Failed to move {alias}: {e}[/red]")
        else:
             console.print(f"[red]Could not start {alias}[/red]")

    # D. Cleanup: Kill the empty shell pane if we created a NEW window
    # A new window starts with 1 shell pane. If we added projects, that shell pane is likely index 0.
    if is_new_window and len(target_window.panes) > panes_added:
        # Kill the first pane (usually the shell)
        target_window.panes[0].cmd("kill-pane")

    target_window.select_layout("tiled")
    console.print(f"[green]Done.[/green]")

    if launch_flag:
        _launch_in_current_terminal(target_window)


# =================================================
# 4. EXISTING COMMANDS (Status, Attach, Stop, etc.)
# =================================================

@tmux_cmd.command("status", cls=RichHelpCommand)
def tmux_status():
    """Show a visual tree of all running Sessions, Windows, and Panes."""
    server = libtmux.Server()
    _configure_tmux_server(server)
    try:
        if not server.sessions:
            console.print("[yellow]No Tmux server running.[/yellow]")
            return
    except:
        console.print("[yellow]No Tmux server found.[/yellow]")
        return

    tree = Tree(f"[bold green]Tmux Server[/bold green] (PID: {os.getpid()})")

    for session in server.sessions:
        is_attached = str(getattr(session, "session_attached", "0")) == "1"
        style = "bold green" if is_attached else "bold blue"
        status_txt = "(ACTIVE)" if is_attached else "(Detached)"
        
        session_node = tree.add(f"[{style}]Session: {session.name}[/{style}] [dim]{status_txt}[/dim]")

        for window in session.windows:
            win_txt = f"Window {window.index}: [bold white]{window.name}[/bold white]"
            window_node = session_node.add(win_txt)

            for pane in window.panes:
                cmd = getattr(pane, "pane_current_command", "shell")
                path = getattr(pane, "pane_current_path", "")
                if str(Path.home()) in path:
                    path = path.replace(str(Path.home()), "~")
                window_node.add(f"Pane {pane.index}: [yellow]{cmd}[/yellow] [dim]({path})[/dim]")

    console.print(tree)

@tmux_cmd.command("switch", cls=RichHelpCommand)
@click.argument("target", required=False)
def tmux_switch(target):
    """Switch to a specific Session or Window."""
    server = libtmux.Server()
    _configure_tmux_server(server)
    
    if target:
        _switch_to_target(server, target)
        return

    # Wizard Mode
    options = [{"type": "action", "name": "[bold green]+ Create New Session[/bold green]", "id": "new"}]
    for s in server.sessions:
        options.append({"type": "session", "name": f"Session: {s.name}", "obj": s})
    
    if server.has_session(VIEWER_SESSION_NAME):
        viewer = server.sessions.get(session_name=VIEWER_SESSION_NAME)
        for w in viewer.windows:
            options.append({"type": "window", "name": f"Window : {w.name} (in viewer)", "obj": w})

    console.print("\n[bold cyan]Switch / Start[/bold cyan]")
    for i, opt in enumerate(options, 1):
        console.print(f"[{i}] {opt['name']}")

    selection = click.prompt("\nSelect option", type=int, default=1)
    
    if 1 <= selection <= len(options):
        choice = options[selection - 1]
        if choice.get('id') == 'new':
            new_name = click.prompt("Enter new session name")
            if not server.has_session(new_name):
                server.new_session(session_name=new_name, detach=True)
            _attach_session(new_name)
        elif choice['type'] == 'session':
            _attach_session(choice['obj'].name)
        elif choice['type'] == 'window':
            _launch_in_current_terminal(choice['obj'])
@tmux_cmd.command("attach", cls=RichHelpCommand)
@click.option("-l", "--launch", is_flag=True, help="Immediately launch.")
def tmux_attach(launch):
    """
    Organize floating projects into a Target Session.
    Only lists known projects (from projects.json) as candidates.
    """
    server = libtmux.Server()
    _configure_tmux_server(server)
    
    # 1. LOAD PROJECT ALIASES (The Filter)
    manager = StorageManager()
    known_aliases = {p['alias'] for p in manager.load_projects().get("projects", [])}

    # 2. IDENTIFY FLOATING CANDIDATES
    # Rule: A session is a "floating project" ONLY IF its name is in projects.json
    candidates = []
    if server.sessions:
        candidates = [
            s for s in server.sessions 
            if s.name in known_aliases and s.name != VIEWER_SESSION_NAME
        ]
    
    if not candidates:
        console.print("[yellow]No free floating projects found.[/yellow]")
        console.print("[dim](All active sessions seem to be Groups or Custom Sessions)[/dim]")
        return

    # 3. SELECT PROJECTS
    console.print("\n[bold cyan]1. Select Projects to Move[/bold cyan]")
    for i, s in enumerate(candidates, start=1):
        console.print(f"[{i}] {s.name}")

    selection = click.prompt("\nSelection (e.g. 1,2)", type=str)
    indices = _parse_selection(selection, len(candidates))
    selected_sessions = [candidates[i] for i in indices]

    if not selected_sessions: return

    # 4. TARGET SESSION SELECTION
    target_session = None
    
    # Auto-detect if inside tmux
    if os.environ.get("TMUX"):
         for s in server.sessions:
             if str(getattr(s, "session_attached", "0")) == "1":
                 target_session = s
                 break
    
    if not target_session:
        # Don't show the sessions we are about to move as destinations
        selected_names = {s.name for s in selected_sessions}
        
        # Destination Candidates: Any session that ISN'T in the move list
        dest_candidates = [s for s in server.sessions if s.name not in selected_names]
        
        has_viewer = any(s.name == VIEWER_SESSION_NAME for s in dest_candidates)
        
        console.print("\n[bold cyan]2. Select Destination Session[/bold cyan]")
        
        # Option 0: Viewer (Default)
        if not has_viewer: 
            console.print(f"[0] {VIEWER_SESSION_NAME} (Default View)")
            
        for i, s in enumerate(dest_candidates, start=1):
            console.print(f"[{i}] {s.name}")

        dest_idx = click.prompt("\nSelect Destination", type=int, default=1 if dest_candidates else 0)
        
        if not has_viewer and dest_idx == 0:
            target_session = server.new_session(session_name=VIEWER_SESSION_NAME, detach=True)
            target_session.windows[0].rename_window("shell")
        elif 1 <= dest_idx <= len(dest_candidates):
            target_session = dest_candidates[dest_idx - 1]
        else:
            return

    # 5. WINDOW SELECTION
    existing_windows = target_session.windows
    console.print(f"\n[bold cyan]3. Destination Window in '{target_session.name}'[/bold cyan]")
    console.print("[0] [green]+ New Window[/green]")
    for i, w in enumerate(existing_windows, start=1):
        console.print(f"[{i}] {w.name} ({len(w.panes)} panes)")

    win_dest = click.prompt("Select", type=int, default=0)
    target_window = None
    is_new = False

    if win_dest == 0:
        default_name = f"{selected_sessions[0].name}_group"
        name = click.prompt("Window Name", default=default_name)
        target_window = target_session.new_window(window_name=name, attach=True)
        is_new = True
    elif 1 <= win_dest <= len(existing_windows):
        target_window = existing_windows[win_dest-1]
    
    # 6. MERGE
    for src_session in selected_sessions:
        try:
            src_pane_id = src_session.active_window.active_pane.id
            target_window.cmd("join-pane", "-s", src_pane_id, "-t", target_window.id)
        except Exception: pass

    if is_new and len(target_window.panes) > 1:
        target_window.panes[0].cmd("kill-pane")
    
    target_window.select_layout("tiled")
    console.print(f"[green]Projects merged into '{target_session.name}'.[/green]")

    if launch: _launch_in_current_terminal(target_window)


@tmux_cmd.command("launch", cls=RichHelpCommand)
def tmux_launch():
    """
    List windows from ANY session and open them.
    """
    server = libtmux.Server()
    _configure_tmux_server(server)
    if not server.sessions:
        console.print("[yellow]No active tmux sessions found.[/yellow]")
        return

    # 1. Select Session (If more than one exists)
    sessions = server.sessions
    target_session = None

    if len(sessions) == 1:
        # If only one session exists, assume that's the one
        target_session = sessions[0]
    else:
        console.print("\n[bold cyan]Select Session to Launch from[/bold cyan]")
        for i, s in enumerate(sessions, 1):
             console.print(f"[{i}] {s.name}")
        
        try:
            sel = click.prompt("\nSelection", type=int)
            if 1 <= sel <= len(sessions):
                target_session = sessions[sel-1]
            else:
                console.print("[red]Invalid selection.[/red]")
                return
        except:
            return

    # 2. Select Window in that Session
    windows = target_session.windows
    if not windows:
        console.print(f"[yellow]Session '{target_session.name}' has no windows.[/yellow]")
        return

    console.print(f"\n[bold cyan]Windows in '{target_session.name}'[/bold cyan]")
    for i, w in enumerate(windows, start=1):
        console.print(f"[{i}] [bold]{w.name}[/bold] ({len(w.panes)} panes)")

    selection = click.prompt("\nSelect window to launch", type=int)
    
    if 1 <= selection <= len(windows):
        _launch_in_current_terminal(windows[selection - 1])
    else:
        console.print("[red]Invalid selection.[/red]")

@tmux_cmd.command("stop", cls=RichHelpCommand)
@click.option("--all", "kill_all", is_flag=True, help="Kill the entire Tmux server immediately.")
def tmux_stop(kill_all):
    """
    Stop Panes, Windows, or Sessions.
    Displays a tree. Enter numbers to kill (e.g. "1, 5").
    """
    server = libtmux.Server()
    

    # --- 1. HANDLE --ALL FLAG ---
    if kill_all:
        if click.confirm("[bold red]WARNING: This will kill ALL tmux sessions. Continue?[/bold red]"):
            try:
                server.kill_server()
                console.print("[green]Tmux server killed.[/green]")
            except Exception as e:
                console.print(f"[red]Error killing server: {e}[/red]")
        return

    # --- 2. CHECK SERVER STATE ---
    try:
        if not server.sessions:
            console.print("[yellow]No active sessions found.[/yellow]")
            return
    except:
        console.print("[yellow]Tmux server is not running.[/yellow]")
        return

    # --- 3. BUILD SELECTABLE TREE ---
    tree = Tree("[bold red]Select items to STOP (Kill)[/bold red]")
    
    # Map index -> Object (Storing IDs is safer than storing objects)
    selection_map = {}
    counter = 1

    for session in server.sessions:
        # A. Register Session
        s_id = counter
        selection_map[s_id] = {'type': 'session', 'obj': session, 'id': session.id, 'name': session.name}
        counter += 1
        
        is_attached = str(getattr(session, "session_attached", "0")) == "1"
        style = "bold green" if is_attached else "bold blue"
        session_node = tree.add(f"[{s_id}] [{style}]Session: {session.name}[/{style}]")

        for window in session.windows:
            # B. Register Window
            w_id = counter
            selection_map[w_id] = {'type': 'window', 'obj': window, 'id': window.id, 'name': window.name, 'session_id': session.id}
            counter += 1
            
            window_node = session_node.add(f"[{w_id}] Window: {window.name}")

            for pane in window.panes:
                # C. Register Pane
                p_id = counter
                selection_map[p_id] = {'type': 'pane', 'obj': pane, 'id': pane.id, 'window_id': window.id}
                counter += 1
                
                cmd = getattr(pane, "pane_current_command", "shell")
                path = getattr(pane, "pane_current_path", "")
                if str(Path.home()) in path: path = path.replace(str(Path.home()), "~")
                
                window_node.add(f"[{p_id}] Pane: [yellow]{cmd}[/yellow] [dim]({path})[/dim]")

    console.print(tree)

    # --- 4. PROMPT USER ---
    selection_input = click.prompt("\nEnter numbers to kill (e.g. 1, 3)", type=str)
    
    try:
        indices = [int(x.strip()) for x in selection_input.split(",") if x.strip().isdigit()]
    except ValueError:
        console.print("[red]Invalid input format.[/red]")
        return

    if not indices: return

    # --- 5. EXECUTE KILL LOGIC ---
    # We collect IDs to kill to avoid object staleness
    sessions_to_kill = set()
    windows_to_kill = set()
    panes_to_kill = []

    for idx in indices:
        item = selection_map.get(idx)
        if not item: continue
        
        if item['type'] == 'session':
            sessions_to_kill.add(item['id']) # Store Session ID ($0, $1 etc)
        elif item['type'] == 'window':
            windows_to_kill.add(item['id'])  # Store Window ID (@0, @1 etc)
        elif item['type'] == 'pane':
            panes_to_kill.append(item)       # Store full item for pane logic

    # 1. Kill Panes
    # Only kill pane if its window AND session are safe
    for p in panes_to_kill:
        # Check if parent window or session is marked for death
        p_obj = p['obj']
        try:
            parent_win_id = p['window_id']
            # We need to find the session ID for this pane's window (looked up from map or object)
            parent_sess_id = p_obj.window.session.id 

            if parent_win_id in windows_to_kill: continue
            if parent_sess_id in sessions_to_kill: continue
            
            p_obj.cmd("kill-pane")
            console.print(f"[green]Killed Pane {p_obj.index}[/green]")
        except Exception as e:
            console.print(f"[red]Error killing pane: {e}[/red]")

    # 2. Kill Windows
    # Only kill window if its parent session is safe
    for w_idx, item in selection_map.items():
        if item['type'] == 'window' and item['id'] in windows_to_kill:
            if item['session_id'] in sessions_to_kill: continue
            
            try:
                server.cmd("kill-window", "-t", item['id'])
                console.print(f"[green]Killed Window: {item['name']}[/green]")
            except Exception as e:
                console.print(f"[red]Error killing window {item['name']}: {e}[/red]")

    # 3. Kill Sessions (Using raw command for robustness)
    for s_id in sessions_to_kill:
        try:
            # Use the raw server command, it is much more reliable than s.kill_session()
            server.cmd("kill-session", "-t", s_id)
            console.print(f"[green]Killed Session {s_id}[/green]")
        except Exception as e:
            console.print(f"[red]Error killing session {s_id}: {e}[/red]")

    console.print("[bold]Done.[/bold]")


# =================================================
# Helpers
# =================================================

def _launch_in_current_terminal(target_window):
    target = f"{target_window.session.name}:{target_window.id}"
    console.print(f"[green]Launching...[/green]")
    if os.environ.get("TMUX"):
        libtmux.Server().cmd("switch-client", "-t", target)
    else:
        os.execvp("tmux", ["tmux", "attach-session", "-t", target])

def _attach_session(session_name):
    if os.environ.get("TMUX"):
        libtmux.Server().cmd("switch-client", "-t", session_name)
    else:
        os.execvp("tmux", ["tmux", "attach", "-t", session_name])

def _switch_to_target(server, target_name):
    if server.has_session(target_name):
        _attach_session(target_name)
    elif server.has_session(VIEWER_SESSION_NAME):
        viewer = server.sessions.get(session_name=VIEWER_SESSION_NAME)
        w = viewer.windows.get(window_name=target_name, default=None)
        if w: _launch_in_current_terminal(w)

def _start_floating_pane(server, project):
    alias = project["alias"]
    path = Path(project["path"]).expanduser()
    cmd = project.get("startup_cmd")
    session = server.new_session(session_name=alias, window_name=alias, start_directory=str(path), detach=True)
    pane = session.active_window.active_pane
    if cmd:
        full_cmd = " && ".join(cmd) if isinstance(cmd, list) else cmd
        pane.send_keys(full_cmd)
    pane.cmd("select-pane", "-T", alias)

def _run_local_project(projects, selection):
    """
    Runs a single project in the current terminal (Blocking).
    Used when --local flag is passed.
    """
    # 1. Ask for selection if not provided
    if not selection:
        console.print("\n[bold cyan]Select Project to Run Locally[/bold cyan]")
        for i, p in enumerate(projects, start=1):
            console.print(f"[{i}] {p['alias']}")
        
        # If no selection provided via CLI, prompt now
        try:
            selection = click.prompt("\nSelection", type=str)
        except click.Abort:
            return

    # 2. Parse selection
    indices = _parse_selection(selection, len(projects))
    
    # Local mode restriction: Can only run ONE project at a time in the foreground
    if len(indices) != 1:
        console.print("[red]Local mode only supports 1 project at a time.[/red]")
        return

    project = projects[indices[0]]
    
    # 3. Prepare Command
    cmd = project.get("startup_cmd")
    if not cmd:
        console.print(f"[yellow]Project '{project['alias']}' has no startup_cmd defined.[/yellow]")
        return

    path = Path(project["path"]).expanduser()
    full_cmd = " && ".join(cmd) if isinstance(cmd, list) else cmd
    
    # 4. Execute
    console.print(f"[green]Running '{project['alias']}' in current terminal...[/green]")
    console.print(f"[dim]Path: {path}[/dim]")
    console.print(f"[dim]Cmd : {full_cmd}[/dim]\n")
    
    try:
        os.chdir(path)
        subprocess.run(full_cmd, shell=True)
    except Exception as e:
        console.print(f"[red]Error running project: {e}[/red]")


def _parse_selection(text: str, max_len: int):
    try:
        nums = [int(x.strip()) for x in text.split(",")]
        return sorted({n - 1 for n in nums if 1 <= n <= max_len})
    except: return []

def _configure_tmux_server(server):
    """
    Apply global 'Gold Standard' configurations to make tmux
    look neat and behave intuitively (Mouse + Titles).
    """
    try:
        # 1. Enable Mouse (Scroll, Click, Resize)
        server.cmd("set", "-g", "mouse", "on")
        
        # 2. Enable Pane Titles (The "Neat" Look)
        # 'top' puts a bar above every pane
        server.cmd("set", "-g", "pane-border-status", "top")
        
        # 3. Format the Title
        # Format: [Index] Title (Command)
        # This makes it look like: " [1] backend (python) "
        fmt = " [#{pane_index}] #{pane_title} (#{pane_current_command}) "
        server.cmd("set", "-g", "pane-border-format", fmt)
        
        # 4. Colorize Active Border (Optional: Makes active pane pop)
        server.cmd("set", "-g", "pane-active-border-style", "fg=green,bold")
        
    except Exception:
        # If server is not running or other error, strictly ignore.
        pass


if __name__ == "__main__":
    tmux_cmd()