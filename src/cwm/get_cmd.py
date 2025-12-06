import click
import pyperclip
import json
from .storage_manager import StorageManager
from .utils import get_history_file_path, tail_read_last_n_lines,is_cwm_call

from typing import List, Dict, Any, Tuple
from pathlib import Path

# --- Helper for History Logic ---
def _get_history_commands(manager: StorageManager, cached: bool, active: bool):
    """
    Returns (cmd_list, None)
    """
    # cached mode unchanged
    if cached:
        click.echo("Loading from cached history...")
        hist_obj = manager.load_cached_history()
        return hist_obj.get("commands", []), None

    # ACTIVE MODE (watch session)
    if active:
        session = manager.load_watch_session()
        
        if not session.get("isWatching"):
            click.echo("Error: No active watch session. Run 'cwm watch start' first.", err=True)
            return [], None

        # read last ~5000 lines
        path = get_history_file_path()
        lines = tail_read_last_n_lines(path, 5000)

        collected = []
        found_start = False

        # reverse scan bottom-up
        for line in reversed(lines):
            if "cwm watch start" in line:
                found_start = True
                break
            collected.append(line)

        collected.reverse()

        if not found_start:
            click.echo("Warning: Could not locate 'cwm watch start' in recent history.")
            click.echo("Showing last 50 commands instead.")
            collected = collected[-50:]

        click.echo(f"Showing active session: {len(collected)} commands.")

        return [{"cmd": line} for line in collected], None

    # NORMAL HISTORY MODE
    # Read last 5000 lines and return all
    path = get_history_file_path()
    lines = tail_read_last_n_lines(path, 5000)

    return [{"cmd": line} for line in lines], None



# --- Helper for Filtering/Displaying ---
def _filter_and_display(commands: list, count: str, exclude: str, filter: str, list_only: bool):
    """
    The core logic for filtering, displaying, and prompting for history.
    """
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
        cmd_text = item.get("cmd", "")

# If ID is None → history mode → do NOT show ID
        list_id = item.get("id")
        if list_id is None:
            click.echo(f"  [{display_num}] {cmd_text}")
        else:
            click.echo(f"  [{display_num}] (ID: {list_id}) {cmd_text}")


    click.echo("---")
    
    if list_only or is_error_state:
        return 

    try:
        choice = click.prompt("Enter number to copy (or press Enter to skip)", default="", show_default=False)
        if not choice:
            return
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            click.echo(f"Copied command {choice} to clipboard.")
        else:
            click.echo(f"Error: '{choice}' is not a valid number from the list.")
    except click.exceptions.Abort:
        click.echo("\nCancelled.")



# --- Helper: Filter Saved (UPDATED) ---
def _filter_and_display_saved(commands: list, count: str, exclude: str, filter: str, tag: str, skip_prompt: bool = False):
    """
    skip_prompt: If True, lists commands and exits without asking to copy.
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

    # --- FIX: Check skip_prompt flag ---
    if skip_prompt:
        return

    try:
        choice = click.prompt("Enter number to copy (or press Enter to skip)", default="", show_default=False)
        if not choice:
            return
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            click.echo(f"Copied command {choice}: {command_to_copy} to clipboard.")
        else:
            click.echo(f"Error: '{choice}' is not a valid number from the list.")
    except click.exceptions.Abort:
        click.echo("\nCancelled.")

# --- THE MAIN GET COMMAND ---
@click.command("get")
@click.argument("name_or_id", required=False)
@click.option("--id", "id_flag", type=int, help="Get a saved command by its unique ID.")
@click.option("-s", "--show", "show_flag", is_flag=True, help="[Saved] Show command without copying.")
@click.option("-l", "list_mode", is_flag=True, help="[Saved] List saved commands and prompt to copy.")
@click.option("-t", "tag_flag", help="[Saved List] Filter by tag.")
@click.option("-h", "--hist", "hist_flag", is_flag=True, help="Switch to HISTORY mode.")
@click.option("-a", "--active", "active_flag", is_flag=True, help="[History] Show active watch session only.")
@click.option("-n", "count", default="10", help="[List/History] Show last N commands or 'all'.")
@click.option("-ex", "exclude", help="[List/History] Exclude commands starting with this string.")
@click.option("-f", "filter", help="[List/History] Filter for commands containing this string.")
@click.option("--cached", "cached_flag", is_flag=True, help="[History] Get from CWM's saved history cache.")
def get_cmd(name_or_id, id_flag, show_flag, list_mode, tag_flag,
            hist_flag, active_flag, count, exclude, filter, cached_flag):
    """
    Get saved commands, live history
    
    Default behavior for saved commands is to COPY to clipboard.
    Use -s to only show.
    """
    manager = StorageManager()



    # --- MODE 2: History ---
    if hist_flag or cached_flag or active_flag:
        if id_flag or name_or_id or tag_flag or show_flag:
            click.echo("Error: --hist cannot be used with saved command flags (like --id or -s).")
            return
        if cached_flag and active_flag:
            click.echo("Error: --cached and --active (-a) flags cannot be used together.")
            return
        
        commands_list, total_lines = _get_history_commands(manager, cached_flag, active_flag)
        
        
        
        _filter_and_display(commands_list, count, exclude, filter, list_only=list_mode)
        return

    if list_mode or tag_flag:
        if name_or_id or id_flag:
            click.echo("Error: -l or -t cannot be used with a specific var_name or --id.")
            return
        data_obj = manager.load_saved_cmds()
        commands = data_obj.get("commands", [])
        # Pass show_flag as skip_prompt
        _filter_and_display_saved(commands, count, exclude, filter, tag_flag, skip_prompt=show_flag)
        return

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
        _filter_and_display_saved(commands, "10", None, None, None, skip_prompt=show_flag)
        return

    if not command_to_get:
        click.echo(f"Error: Command '{name_or_id or id_flag}' not found in saved commands.")
        return

    if show_flag:
        click.echo(command_to_get)
    else:
        pyperclip.copy(command_to_get)
        click.echo(f"Command '{name_or_id or id_flag}' copied to clipboard.")