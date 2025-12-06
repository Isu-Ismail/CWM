import click
from pathlib import Path
from rich.console import Console  # <--- IMPORT RICH
from .storage_manager import StorageManager
from .shell_hook import (
    detect_shell,
    get_shell_extension,
    generate_hook_script,
    install_hook,
    remove_hook,
)

# Initialize Rich Console
console = Console()

@click.group("watch")
def watch_cmd():
    """Start or stop per-project command monitoring."""
    pass

# =====================================================================================
# WATCH START
# =====================================================================================
@watch_cmd.command("start")
def start():
    """Injects a hook into your shell to record commands locally."""
    manager = StorageManager()
    
    # 1. Detect Shell
    shell_type = detect_shell()
    # Use console.print to render colors
    console.print(f"Detected shell: [cyan]{shell_type}[/cyan]")
    
    # 2. Get Project Paths
    hist_file = manager.get_project_history_path()
    project_root = hist_file.parent 
    
    # 3. Determine Hook File Name
    ext = get_shell_extension(shell_type)
    hook_file_path = project_root / f"cwm_hook{ext}"
    
    # 4. Generate Hook Content
    try:
        hook_content = generate_hook_script(shell_type, hist_file)
    except Exception as e:
        console.print(f"[red]Error generating hook:[/red] {e}")
        return

    # 5. Write Hook File locally
    project_root.mkdir(parents=True, exist_ok=True)
    hook_file_path.write_text(hook_content, encoding="utf-8")
    
    # 6. Install into System Profile
    try:
        profile_path = install_hook(shell_type, hook_file_path)
        
        # 7. Save Session State
        manager.save_watch_session({
            "isWatching": True,
            "shell": shell_type,
            "hook_file": str(hook_file_path),
            "started_at": manager._now()
        })
        
        console.print(f"[bold green]✔ Watch session started![/bold green]")
        console.print(f"  Hook saved to: [dim]{hook_file_path.name}[/dim]")
        console.print(f"  Profile updated: [dim]{profile_path}[/dim]")
        console.print("[yellow]⚠ Please restart your terminal (or run '. $PROFILE') to begin recording.[/yellow]")
        
    except Exception as e:
        console.print(f"[red]Failed to install hook:[/red] {e}")

# =====================================================================================
# WATCH STOP
# =====================================================================================
@watch_cmd.command("stop")
def stop():
    """Stops the watch session and removes hooks."""
    manager = StorageManager()
    session = manager.load_watch_session()

    if not session.get("isWatching"):
        console.print("[yellow]No active watch session.[/yellow]")
        return

    shell_type = session.get("shell")
    hook_file_str = session.get("hook_file")

    console.print(f"Stopping watch for shell: [cyan]{shell_type}[/cyan]")

    # 1. Remove from Profile
    remove_hook(shell_type)
    console.print("✔ Shell hook removed from profile.")

    # 2. Delete the temporary hook file
    if hook_file_str:
        hook_path = Path(hook_file_str)
        if hook_path.exists():
            hook_path.unlink()
            console.print(f"✔ Deleted local hook file: [dim]{hook_path.name}[/dim]")

    # 3. Reset Session
    manager.save_watch_session({"isWatching": False})
    
    console.print("[bold green]Watch session stopped.[/bold green]")
    console.print("Please restart your terminal to clear the session completely.")

# =====================================================================================
# WATCH STATUS
# =====================================================================================
@watch_cmd.command("status")
def status():
    """Display current watch session status."""
    manager = StorageManager()
    session = manager.load_watch_session()

    if session.get("isWatching"):
        console.print("[bold green]Watch session ACTIVE[/bold green]")
        console.print(f"Shell: [cyan]{session.get('shell')}[/cyan]")
        console.print(f"Hook File: [dim]{session.get('hook_file')}[/dim]")
        console.print(f"Started at: {session.get('started_at')}")
    else:
        console.print("[dim]Watch session INACTIVE[/dim]")