# cwm/get_cmd.py
import click
import pyperclip
from .storage_manager import StorageManager
from .utils import read_powershell_history, is_cwm_call
from typing import List, Dict, Any, Tuple # Added for helpers
from pathlib import Path # Added for helpers

# --- Helper for History Logic (UPDATED) ---
def _get_history_commands(manager: StorageManager, cached: bool, active: bool) -> list:
    """Loads commands from live PS history, cached file, or active session."""
    
    # --- THIS IS THE FIX ---
    start_line = 0  # Initialize start_line to 0
    # --- END OF FIX ---

    if cached:
        click.echo("Loading from cached history...")
        hist_obj = manager.load_cached_history()
        return hist_obj.get("commands", [])
    
    # --- Both Active and Default read from LIVE history ---
    lines, total_lines = read_powershell_history()

    if active:
        # --- NEW ACTIVE SESSION LOGIC ---
        session = manager.load_watch_session()
        if not session.get("isWatching"):
            click.echo("Error: No active watch session. Run 'cwm watch start' first.", err=True)
            return [] # Return empty list
            
        start_line = session.get("startLine", 0) # This will now be set correctly
        if start_line >= total_lines:
            click.echo("Watch session is active, but no new commands found.")
            return []
            
        lines = lines[start_line:]
        click.echo(f"Showing active session: {len(lines)} new commands since line {start_line}.")
        
    return [{"id": i+start_line+1, "cmd": line} for i, line in enumerate(lines)]

# --- (_filter_and_display helper function is UNCHANGED and still works) ---
def _filter_and_display(commands: list, count: str, exclude: str, filter: str, list_only: bool):
    """
    The core logic for filtering, displaying, and prompting for history.
    """
    # (This function is identical to the one in our previous step)
    commands.reverse()
    unique_commands = []
    seen = set()
    for item in commands:
        cmd_str = item.get("cmd")
        if cmd_str and cmd_str not in seen:
            unique_commands.append(item)
            seen.add(cmd_str)
    
    if not (filter and "cwm" in filter):
        base_list = [item for item in unique_commands if not is_cwm_call(item.get("cmd", ""))]
    else:
        base_list = unique_commands

    commands_to_display = list(base_list) 
    if exclude:
        commands_to_display = [
            item for item in commands_to_display if not item.get("cmd", "").startswith(exclude)
        ]
    if filter:
        commands_to_display = [
            item for item in commands_to_display if filter in item.get("cmd", "")
        ]

    total_found = len(commands_to_display)
    if total_found == 0 and (exclude or filter):
        click.echo(f"No history found matching your filters. Showing default list instead...")
        commands_to_display = base_list 
        count = "10" 
        total_found = len(commands_to_display)

    is_error_state = False 
    if count.lower() != "all":
        try:
            num_to_show = int(count)
            if num_to_show > 0:
                commands_to_display = commands_to_display[:num_to_show]
            else:
                raise ValueError("Count must be a positive integer.")
        except ValueError:
            click.echo(f"Invalid count '{count}'. Must be a positive integer or 'all'. Defaulting to 10.")
            commands_to_display = commands_to_display[:10]
            is_error_state = True 
    
    commands_to_display.reverse()

    if not commands_to_display:
        click.echo("No history found.")
        return
        
    click.echo(f"--- Showing {len(commands_to_display)} of {total_found} History Commands ---")
    
    display_map = {}
    for i, item in enumerate(commands_to_display):
        display_num = i + 1
        display_map[str(display_num)] = item.get("cmd", "")
        list_id = item.get("id", display_num) 
        click.echo(f"  [{display_num}] (ID: {list_id}) {item.get('cmd', '')}")

    click.echo("---")
    
    if list_only or is_error_state:
        return 

    try:
        choice = click.prompt("Enter number to copy (or press Enter to skip)", default="", show_default=False)
        if not choice:
            click.echo("Skipped.")
            return
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            click.echo(f"Copied command {choice} to clipboard.")
        else:
            click.echo(f"Error: '{choice}' is not a valid number from the list.")
    except click.exceptions.Abort:
        click.echo("\nCancelled.")

# --- The Main `get` Command (UPDATED) ---
@click.command("get")
@click.argument("name_or_id", required=False)
@click.option("--id", "id_flag", type=int, help="Get a saved command by its unique ID.")
@click.option("-c", "--copy", "copy_flag", is_flag=True, help="[Saved] Copy the found command to clipboard.")
@click.option("-l", "list_mode", is_flag=True, help="[Saved] List saved commands and prompt to copy.")
@click.option("-t", "tag_flag", help="[Saved List] Filter by tag.")
@click.option("-h", "--hist", "hist_flag", is_flag=True, help="Switch to HISTORY mode.")
@click.option("-a", "--active", "active_flag", is_flag=True, help="[History] Show active watch session only.")
@click.option("-n", "count", default="10", help="[List/History] Show last N commands or 'all'.")
@click.option("-ex", "exclude", help="[List/History] Exclude commands starting with this string.")
@click.option("-f", "filter", help="[List/History] Filter for commands containing this string.")
@click.option("--cached", "cached_flag", is_flag=True, help="[History] Get from CWM's saved history cache.")
def get_cmd(name_or_id, id_flag, copy_flag, list_mode, tag_flag,
            hist_flag, active_flag, count, exclude, filter, cached_flag):
    """
    Get saved commands or from PowerShell history.
    
    - To get a SAVED command: cwm get <var_name>
    - To LIST SAVED commands: cwm get -l
    - To get from HISTORY: cwm get --hist
    - To get from ACTIVE SESSION: cwm get --hist -a
    """
    manager = StorageManager()

    # --- MODE 1: Get from History ---
    if hist_flag or cached_flag or active_flag:
        # Check for invalid flag combinations
        if copy_flag or id_flag or name_or_id or tag_flag:
            click.echo("Error: --hist cannot be used with saved command flags (like --id or -c).")
            return
        # --cached and --active are mutually exclusive
        if cached_flag and active_flag:
            click.echo("Error: --cached and --active (-a) flags cannot be used together.")
            return
        
        commands = _get_history_commands(manager, cached_flag, active_flag)
        _filter_and_display(commands, count, exclude, filter, list_mode)
        return

    # --- MODE 2: Get from saved_cmds.json ---
    # (This entire section is unchanged from our last version)
    
    if list_mode or tag_flag:
        # (This is the _filter_and_display_saved logic, which is unchanged)
        data_obj = manager.load_saved_cmds()
        commands = data_obj.get("commands", [])
        _filter_and_display_saved(commands, count, exclude, filter, tag_flag)
        return

    # --- Sub-Mode 2b: Fast-Path (Get one) ---
    data_obj = manager.load_saved_cmds()
    commands = data_obj.get("commands", [])
    command_to_get = None

    if id_flag is not None:
        for cmd in commands:
            if cmd.get("id") == id_flag:
                command_to_get = cmd.get("cmd")
                break
    elif name_or_id is not None:
        for cmd in commands:
            if cmd.get("var") == name_or_id:
                command_to_get = cmd.get("cmd")
                break
    else:
        # User just typed "cwm get" with no args.
        _filter_and_display_saved(commands, "10", None, None, None)
        return

    if not command_to_get:
        click.echo(f"Error: Command '{name_or_id or id_flag}' not found in saved commands.")
        return

    if copy_flag:
        pyperclip.copy(command_to_get)
        click.echo(f"Command '{name_or_id or id_flag}' copied to clipboard.")
    else:
        click.echo(command_to_get)

# --- (We must add _filter_and_display_saved back in) ---
def _filter_and_display_saved(commands: list, count: str, exclude: str, filter: str, tag: str):
    """
    New logic for filtering and prompting for SAVED commands.
    """
    
    commands_to_display = list(commands) 

    if exclude:
        commands_to_display = [
            item for item in commands_to_display if not item.get("cmd", "").startswith(exclude)
        ]
    if filter:
        commands_to_display = [
            item for item in commands_to_display 
            if filter in item.get("cmd", "") or filter in item.get("var", "")
        ]
    if tag:
        commands_to_display = [
            item for item in commands_to_display if tag in item.get("tags", [])
        ]

    total_found = len(commands_to_display)
    
    if total_found == 0:
        click.echo("No saved commands found matching your filters.")
        return

    commands_to_display.reverse()
    
    if count.lower() != "all":
        try:
            num_to_show = int(count)
            if num_to_show > 0:
                commands_to_display = commands_to_display[:num_to_show]
        except ValueError:
            click.echo(f"Invalid count '{count}'. Defaulting to 10.")
            commands_to_display = commands_to_display[:10]
    
    commands_to_display.reverse()

    click.echo(f"--- Showing {len(commands_to_display)} of {total_found} Saved Commands ---")
    
    display_map = {}
    for i, item in enumerate(commands_to_display):
        display_num = i + 1
        display_map[str(display_num)] = item.get("cmd", "")
        
        sid = item.get("id")
        var = item.get("var") or "(raw)"
        cmd = item.get("cmd")
        fav = "* " if item.get("fav") else ""
        click.echo(f"  [{display_num}] (ID: {sid}) {fav}{var} -- {cmd}")

    click.echo("---")

    try:
        choice = click.prompt("Enter number to copy (or press Enter to skip)", default="", show_default=False)
        if not choice:
            click.echo("Skipped.")
            return
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            click.echo(f"Copied command {choice} to clipboard.")
        else:
            click.echo(f"Error: '{choice}' is not a valid number from the list.")
    except click.exceptions.Abort:
        click.echo("\nCancelled.")