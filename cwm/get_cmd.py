# cwm/get_cmd.py
import click
import pyperclip
from .storage_manager import StorageManager
from .utils import read_powershell_history, is_cwm_call

# --- Helper for History Logic (Unchanged) ---
def _get_history_commands(manager: StorageManager, cached: bool) -> list:
    """Loads commands from either live PS history or the cached file."""
    if cached:
        click.echo("Loading from cached history...")
        hist_obj = manager.load_cached_history()
        return hist_obj.get("commands", [])
    else:
        live_lines = read_powershell_history()
        return [{"id": i+1, "cmd": line} for i, line in enumerate(live_lines)]

# --- Helper for Filtering/Displaying (Unchanged) ---
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


# --- NEW HELPER: For Filtering/Displaying SAVED Commands ---
def _filter_and_display_saved(commands: list, count: str, exclude: str, filter: str, tag: str):
    """
    New logic for filtering and prompting for SAVED commands.
    """
    
    # 1. Apply filters
    commands_to_display = list(commands) # Make a copy

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
    
    # 2. Check for no matches (but no fallback, just show error)
    if total_found == 0:
        click.echo("No saved commands found matching your filters.")
        return

    # 3. Apply Count/Slicing
    # Show in reverse order (newest first) by default
    commands_to_display.reverse()
    
    if count.lower() != "all":
        try:
            num_to_show = int(count)
            if num_to_show > 0:
                commands_to_display = commands_to_display[:num_to_show]
            else:
                raise ValueError()
        except ValueError:
            click.echo(f"Invalid count '{count}'. Defaulting to 10.")
            commands_to_display = commands_to_display[:10]
    
    # Reverse *again* to show chronological (oldest-on-top)
    commands_to_display.reverse()

    # 4. Print the list
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

    # 5. Interactive Copy Prompt
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
@click.option("-n", "count", default="10", help="[List/History] Show last N commands or 'all'.")
@click.option("-ex", "exclude", help="[List/History] Exclude commands starting with this string.")
@click.option("-f", "filter", help="[List/History] Filter for commands containing this string.")
@click.option("--cached", "cached_flag", is_flag=True, help="[History] Get from CWM's saved history cache.")
def get_cmd(name_or_id, id_flag, copy_flag, list_mode, tag_flag,
            hist_flag, count, exclude, filter, cached_flag):
    """
    Get saved commands or from PowerShell history.
    
    - To get a SAVED command: cwm get <var_name>
    - To LIST SAVED commands: cwm get -l
    - To get from HISTORY: cwm get --hist
    """
    manager = StorageManager()

    # --- MODE 1: Get from History ---
    if hist_flag:
        # Check for invalid flag combinations
        if copy_flag or id_flag or name_or_id or tag_flag:
            click.echo("Error: --hist cannot be used with saved command flags (like --id or -c).")
            return
        
        commands = _get_history_commands(manager, cached_flag)
        # Note: We pass 'list_only=False' because `get --hist` *always* prompts
        _filter_and_display(commands, count, exclude, filter, list_only=False)
        return

    # --- MODE 2: Get from saved_cmds.json ---
    
    # Check for invalid flag combinations
    if cached_flag:
        click.echo("Error: --cached flag only works with --hist.")
        return
        
    data_obj = manager.load_saved_cmds()
    commands = data_obj.get("commands", [])

    # --- Sub-Mode 2a: List & Prompt (Your new feature) ---
    if list_mode or tag_flag:
        if name_or_id or id_flag:
            click.echo("Error: -l or -t cannot be used with a specific var_name or --id.")
            return
        
        _filter_and_display_saved(commands, count, exclude, filter, tag_flag)
        return

    # --- Sub-Mode 2b: Fast-Path (Get one) ---
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
        # We will default to showing the list.
        _filter_and_display_saved(commands, "10", None, None, None)
        return

    # --- Process the found (Fast-Path) command ---
    if not command_to_get:
        click.echo(f"Error: Command '{name_or_id or id_flag}' not found in saved commands.")
        return

    if copy_flag:
        pyperclip.copy(command_to_get)
        click.echo(f"Command '{name_or_id or id_flag}' copied to clipboard.")
    else:
        click.echo(command_to_get)