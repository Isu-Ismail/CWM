# cwm/watch_cmd.py
import click
from .storage_manager import StorageManager
from .utils import read_powershell_history, is_cwm_call
from datetime import datetime

@click.group("watch")
def watch_cmd():
    """Start or stop a command watch session."""
    pass

@watch_cmd.command("start")
def start():
    """
    Start a new watch session.
    This marks the current history line as the starting point.
    """
    manager = StorageManager()
    
    # Condition: Must be in a bank
    if manager.get_bank_path() == manager.GLOBAL_CWM_BANK:
        click.echo("Error: 'cwm watch' can only be run inside a CWM bank (run 'cwm init').", err=True)
        return
        
    lines, line_count = read_powershell_history()
    
    session = manager.load_watch_session()
    
    if session.get("isWatching"):
        click.echo("Watch session already active. Restarting from current line...")
    else:
        click.echo("Watch session started.")

    # Save the *next* line number as the starting point
    session["isWatching"] = True
    session["startLine"] = line_count
    manager.save_watch_session(session)
    click.echo(f"Watching for new commands after line {line_count}.")

@watch_cmd.command("stop")
@click.option("--save", "save_flag", is_flag=True, help="Save the captured session to CWM history.")
@click.option("-ex", "exclude", help="[Save] Exclude commands starting with this string.")
@click.option("-f", "filter", help="[Save] Filter for commands containing this string.")
def stop(save_flag, exclude, filter):
    """
    Stop the current watch session.
    """
    manager = StorageManager()
    session = manager.load_watch_session()
    
    if not session.get("isWatching"):
        click.echo("Watch session is already stopped.")
        return

    start_line = session.get("startLine", 0)
    
    if save_flag:
        # --- Save Logic ---
        click.echo("Saving captured session to history...")
        lines, _ = read_powershell_history()
        
        # Get only the new commands from the live session
        commands_to_save = lines[start_line:]
        
        # Filter this new list
        if exclude:
            commands_to_save = [cmd for cmd in commands_to_save if not cmd.startswith(exclude)]
        if filter:
            commands_to_save = [cmd for cmd in commands_to_save if filter in cmd]
            
        # Load cached history to append
        hist_obj = manager.load_cached_history()
        cached_commands = hist_obj.get("commands", [])
        last_id = hist_obj.get("last_sync_id", 0)
        seen_in_cache = set(item.get("cmd") for item in cached_commands)
        
        added_count = 0
        for cmd_str in commands_to_save:
            # Silently skip duplicates and cwm calls
            if cmd_str and cmd_str not in seen_in_cache and not is_cwm_call(cmd_str):
                added_count += 1
                last_id += 1
                cached_commands.append({
                    "id": last_id,
                    "cmd": cmd_str,
                    "timestamp": datetime.utcnow().isoformat()
                })
                seen_in_cache.add(cmd_str)
        
        hist_obj["commands"] = cached_commands
        hist_obj["last_sync_id"] = last_id
        manager.save_cached_history(hist_obj)
        click.echo(f"Saved {added_count} new commands.")

    # --- Stop the session ---
    session["isWatching"] = False
    session["startLine"] = 0
    manager.save_watch_session(session)
    click.echo("Watch session stopped.")

@watch_cmd.command("status")
def status():
    """Checks if a watch session is active."""
    manager = StorageManager()
    session = manager.load_watch_session()
    
    if session.get("isWatching"):
        start_line = session.get("startLine", 0)
        click.echo(f"Watch session is ACTIVE (tracking since line {start_line}).")
    else:
        click.echo("Watch session is INACTIVE.")