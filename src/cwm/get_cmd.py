import click
import pyperclip
import json
from .storage_manager import StorageManager
from .utils import get_history_file_path, tail_read_last_n_lines, is_cwm_call

from rich.console import Console
from .rich_help import RichHelpCommand

console = Console()

# --- Helper for History Logic (Unchanged) ---
def _get_history_commands(manager: StorageManager, cached: bool, active: bool):
    """
    Returns (cmd_list, None)
    """
    if cached:
        console.print("[dim]Loading from cached history...[/dim]")
        hist_obj = manager.load_cached_history()
        return hist_obj.get("commands", []), None

    if active:
        session = manager.load_watch_session()
        if not session.get("isWatching"):
            console.print("[bold red]Error:[/bold red] No active watch session. Run 'cwm watch start' first.")
            return [], None

        path = get_history_file_path()
        lines = tail_read_last_n_lines(path, 5000)
        collected = []
        found_start = False

        for line in reversed(lines):
            if "cwm watch start" in line:
                found_start = True
                break
            collected.append(line)

        collected.reverse()

        if not found_start:
            console.print("[yellow]Warning: Could not locate 'cwm watch start' in recent history.[/yellow]")
            console.print("Showing last 50 commands instead.")
            collected = collected[-50:]

        console.print(f"[dim]Showing active session: {len(collected)} commands.[/dim]")
        return [{"cmd": line} for line in collected], None

    path = get_history_file_path()
    lines = tail_read_last_n_lines(path, 5000)
    return [{"cmd": line} for line in lines], None


# --- Shared Filtering Logic (Fixed) ---
def _apply_robust_filters(commands, filter_str, exclude_str):
    """
    Applies comma-separated filters and exclusions sequentially.
    FIX: Exclusion now checks if string is IN command, not just starts with.
    """
    filtered_list = list(commands)

    # 1. Apply Exclusions first (Remove noise)
    if exclude_str:
        exclusions = [x.strip() for x in exclude_str.split(',') if x.strip()]
        for ex in exclusions:
            filtered_list = [
                item for item in filtered_list 
                # FIXED: Changed startswith(ex) to (ex in cmd)
                if ex not in item.get("cmd", "")
            ]

    # 2. Apply Filters sequentially (Drill down)
    if filter_str:
        filters = [x.strip() for x in filter_str.split(',') if x.strip()]
        for f in filters:
            filtered_list = [
                item for item in filtered_list 
                if f in item.get("cmd", "") or f in item.get("var", "")
            ]
            
    return filtered_list


# --- Helper for Filtering/Displaying History (Compact) ---
def _filter_and_display(commands: list, count: str, exclude: str, filter: str, list_only: bool):
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

    # Apply filters
    commands_to_display = _apply_robust_filters(base_list, filter, exclude)

    total_found = len(commands_to_display)
    
    # Fallback if specific filters yield nothing
    if total_found == 0 and (exclude or filter):
        console.print(f"[yellow]No history found matching filters. Defaulting...[/yellow]")
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
                raise ValueError
        except ValueError:
            console.print(f"[red]Invalid count '{count}'. Defaulting to 10.[/red]")
            commands_to_display = commands_to_display[:10]
            is_error_state = True 
    
    commands_to_display.reverse()

    if not commands_to_display:
        console.print("[yellow]No history found.[/yellow]")
        return
        
    # --- COMPACT DISPLAY ---
    console.print(f"[bold underline]History ({len(commands_to_display)}/{total_found})[/bold underline]")
    
    display_map = {}
    for i, item in enumerate(commands_to_display):
        display_num = str(i + 1)
        display_map[display_num] = item.get("cmd", "")
        
        cmd_text = item.get("cmd", "").strip()
        list_id = item.get("id")

        if list_id is not None:
            console.print(f" [cyan][{display_num}][/cyan] [dim](ID:[/dim] [green]{list_id}[/green][dim])[/dim] {cmd_text}")
        else:
            console.print(f" [cyan][{display_num}][/cyan] {cmd_text}")

    console.print("[dim]---[/dim]")
    
    if list_only or is_error_state:
        return 

    try:
        choice = click.prompt("Copy #", default="", show_default=False)
        if not choice:
            return
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            console.print(f"[bold green]Copied #{choice}![/bold green]")
        else:
            console.print(f"[red]Invalid number.[/red]")
    except click.exceptions.Abort:
        console.print("\nCancelled.")


# --- Helper: Filter Saved (Compact) ---
def _filter_and_display_saved(commands: list, count: str, exclude: str, filter: str, tag: str, skip_prompt: bool = False):
    if tag:
        commands = [item for item in commands if tag in item.get("tags", [])]

    commands_to_display = _apply_robust_filters(commands, filter, exclude)

    total_found = len(commands_to_display)
    
    if total_found == 0:
        console.print("[yellow]No saved commands found.[/yellow]")
        return

    commands_to_display.reverse()
    
    if count.lower() != "all":
        try:
            num_to_show = int(count)
            if num_to_show > 0:
                commands_to_display = commands_to_display[:num_to_show]
        except ValueError:
            commands_to_display = commands_to_display[:10]
    
    commands_to_display.reverse()

    console.print(f"[bold underline]Saved Commands ({len(commands_to_display)}/{total_found})[/bold underline]")
    
    display_map = {}
    for i, item in enumerate(commands_to_display):
        display_num = str(i + 1)
        display_map[display_num] = item.get("cmd", "")
        
        sid = item.get("id")
        var = item.get("var") or ""
        cmd = item.get("cmd", "")
        fav = "[yellow]★[/yellow] " if item.get("fav") else ""
        
        var_str = f"[bold white]{var}[/bold white] " if var else ""
        console.print(f" [cyan][{display_num}][/cyan] [dim](ID:[/dim] [green]{sid}[/green][dim])[/dim] {fav}{var_str}[dim]--[/dim] {cmd}")

    console.print("[dim]---[/dim]")

    if skip_prompt:
        return

    try:
        choice = click.prompt("Copy #", default="", show_default=False)
        if not choice:
            return
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            console.print(f"[bold green]Copied #{choice}![/bold green]")
        else:
            console.print(f"[red]Invalid number.[/red]")
    except click.exceptions.Abort:
        console.print("\nCancelled.")


# --- THE MAIN GET COMMAND ---
@click.command("get", cls=RichHelpCommand)
@click.argument("name_or_id", required=False)
@click.option("--id", "id_flag", type=int, help="Get by ID.")
@click.option("-s", "--show", "show_flag", is_flag=True, help="Show without copying.")
@click.option("-l", "list_mode", is_flag=True, help="List saved commands.")
@click.option("-t", "tag_flag", help="Filter by tag.")
@click.option("-h", "--hist", "hist_flag", is_flag=True, help="History mode.")
@click.option("-a", "--active", "active_flag", is_flag=True, help="Active session only.")
@click.option("-n", "count", default="10", help="Show last N commands.")
@click.option("-ex", "exclude", help="Exclude (comma separated).")
@click.option("-f", "filter", help="Filter (comma separated pipeline).")
@click.option("--cached", "cached_flag", is_flag=True, help="Use CWM cache.")
def get_cmd(name_or_id, id_flag, show_flag, list_mode, tag_flag,
            hist_flag, active_flag, count, exclude, filter, cached_flag):
    """
    Get saved commands or live history.
    """
    manager = StorageManager()

    # --- MODE 2: History ---
    if hist_flag or cached_flag or active_flag:
        if id_flag or name_or_id or tag_flag or show_flag:
            console.print("[red]Error: --hist cannot be used with saved command flags.[/red]")
            return
        if cached_flag and active_flag:
            console.print("[red]Error: --cached and --active flags conflict.[/red]")
            return
        
        commands_list, total_lines = _get_history_commands(manager, cached_flag, active_flag)
        _filter_and_display(commands_list, count, exclude, filter, list_only=list_mode)
        return

    # --- MODE 1: Saved Commands List ---
    if list_mode or tag_flag:
        if name_or_id or id_flag:
            console.print("[red]Error: -l or -t cannot be used with var_name or --id.[/red]")
            return
        data_obj = manager.load_saved_cmds()
        commands = data_obj.get("commands", [])
        _filter_and_display_saved(commands, count, exclude, filter, tag_flag, skip_prompt=show_flag)
        return

    # --- MODE 3: Get Specific Saved Command ---
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
        # Default action: list saved
        _filter_and_display_saved(commands, "10", None, None, None, skip_prompt=show_flag)
        return

    if not command_to_get:
        console.print(f"[red]Error: '{name_or_id or id_flag}' not found.[/red]")
        return

    if show_flag:
        console.print(command_to_get)
    else:
        pyperclip.copy(command_to_get)
        console.print(f"[bold green]Copied to clipboard![/bold green]")