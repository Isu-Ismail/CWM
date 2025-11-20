import click
import pyperclip
import json
from .storage_manager import StorageManager
from .utils import read_powershell_history, is_cwm_call
from typing import List, Dict, Any, Tuple
from pathlib import Path

# --- Helper for History Logic ---
def _get_history_commands(manager: StorageManager, cached: bool, active: bool) -> Tuple[list, int]:
    """
    Returns: (list_of_commands_with_ids, total_file_line_count)
    """
    start_line = 0
    
    if cached:
        click.echo("Loading from cached history...")
        hist_obj = manager.load_cached_history()
        return hist_obj.get("commands", []), 0

    lines, total_lines = read_powershell_history()

    if active:
        session = manager.load_watch_session()
        if not session.get("isWatching"):
            click.echo("Error: No active watch session. Run 'cwm watch start' first.", err=True)
            return [], 0
            
        start_line = session.get("startLine", 0)
        if start_line >= total_lines:
            click.echo("Watch session is active, but no new commands found.")
            return [], total_lines
            
        lines = lines[start_line:]
        click.echo(f"Showing active session: {len(lines)} new commands since line {start_line}.")
        
    # Construct command objects
    cmd_objs = [{"id": i+start_line+1, "cmd": line} for i, line in enumerate(lines)]
    
    return cmd_objs, total_lines

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
        list_id = item.get("id", display_num) 
        click.echo(f"  [{display_num}] (ID: {list_id}) {item.get('cmd', '')}")

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

# --- Helper: Archive Reader ---
def _get_archived_commands(manager: StorageManager, arch_val: str) -> list:
    """Reads from global archives."""
    idx_data = manager.load_archive_index()
    archives = idx_data.get("archives", [])
    
    if not archives:
        click.echo("No archives found.")
        return []

    # --- UPDATED LOGIC: Handle LIST mode ---
    if arch_val == "LIST":
        click.echo("Available History Archives:")
        for arch in archives:
            click.echo(f"  [ID: {arch['id']}] {arch['timestamp']} ({arch['count']} cmds)")
        return [] # Return empty list so _filter_and_display is skipped

    target = None

    if arch_val == "LATEST":
        if archives:
            target = archives[-1]
    else:
        try:
            target_id = int(arch_val)
            target = next((a for a in archives if a['id'] == target_id), None)
        except ValueError:
             click.echo("Error: Archive ID must be an integer.")
             return []

    if not target:
        click.echo(f"Archive not found.")
        return []
        
    path = manager.get_archive_path(target['filename'])
    if not path.exists():
        click.echo("Error: Archive file missing from disk.")
        return []
        
    click.echo(f"Loading Archive ID {target['id']} ({target['count']} cmds)...")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [{"id": i+1, "cmd": line} for i, line in enumerate(lines)]

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
@click.option("--arch", "arch_flag", required=False, is_flag=False, flag_value="LIST", help="Get from Archives. Default is latest.")
def get_cmd(name_or_id, id_flag, show_flag, list_mode, tag_flag,
            hist_flag, active_flag, count, exclude, filter, cached_flag, arch_flag):
    """
    Get saved commands, live history, or archives.
    
    Default behavior for saved commands is to COPY to clipboard.
    Use -s to only show.
    """
    manager = StorageManager()

    # --- MODE 1: Archives ---
    if arch_flag:
         commands = _get_archived_commands(manager, arch_flag)
         if commands:
             # Archive mode always lists and prompts (uses the shared filter/display)
             _filter_and_display(commands, count, exclude, filter, list_only=False)
         return

    # --- MODE 2: History ---
    if hist_flag or cached_flag or active_flag:
        if id_flag or name_or_id or tag_flag or show_flag:
            click.echo("Error: --hist cannot be used with saved command flags (like --id or -s).")
            return
        if cached_flag and active_flag:
            click.echo("Error: --cached and --active (-a) flags cannot be used together.")
            return
        
        commands_list, total_lines = _get_history_commands(manager, cached_flag, active_flag)
        
        # Check Warning (Live mode only)
        if not cached_flag:
            config = manager.get_config()
            if not config.get("suppress_history_warning"):
                if total_lines > 10000:
                    click.echo(click.style(f"WARNING: History file is large ({total_lines} lines).", fg="yellow"))
                    click.echo(click.style("Run 'cwm save --archive' to optimize.", fg="yellow"))
                    click.echo("")
        
        # History mode always lists and prompts (unless -l is used)
        # NOTE: Variable list_mode is reused here for 'list_only'
        _filter_and_display(commands_list, count, exclude, filter, list_only=list_mode)
        return

    # --- MODE 3: Saved List (Explicit) ---
    if list_mode or tag_flag:
        if name_or_id or id_flag:
            click.echo("Error: -l or -t cannot be used with a specific var_name or --id.")
            return
        data_obj = manager.load_saved_cmds()
        commands = data_obj.get("commands", [])
        # Pass show_flag as skip_prompt
        _filter_and_display_saved(commands, count, exclude, filter, tag_flag, skip_prompt=show_flag)
        return

    # --- MODE 4: Saved Fast-Path (Single Item or Default List) ---
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
        # User just typed "cwm get" OR "cwm get -s" with no args -> Default to List
        # Pass show_flag as skip_prompt here
        _filter_and_display_saved(commands, "10", None, None, None, skip_prompt=show_flag)
        return

    if not command_to_get:
        click.echo(f"Error: Command '{name_or_id or id_flag}' not found in saved commands.")
        return

    # --- Auto-Copy / Show Logic (For Single Item) ---
    if show_flag:
        click.echo(command_to_get)
    else:
        # Default: Copy + Notify
        pyperclip.copy(command_to_get)
        click.echo(f"Command '{name_or_id or id_flag}' copied to clipboard.")