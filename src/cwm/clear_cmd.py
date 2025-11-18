# cwm/clear_cmd.py
import click
from datetime import datetime
from .storage_manager import StorageManager

def _perform_clear(data_obj: dict, list_key: str, id_key: str, 
                   count: int, filter_str: str, clear_all: bool) -> int:
    """
    Generic logic to clear items, re-index, and return count removed.
    """
    commands = data_obj.get(list_key, [])
    initial_count = len(commands)
    
    if clear_all:
        # Clear everything
        data_obj[list_key] = []
        data_obj[id_key] = 0
        return initial_count

    # Filter logic implies we identify what to KEEP
    items_to_keep = []
    
    # We iterate through the existing list. 
    # If it matches the delete criteria, we skip it (delete it).
    
    # Logic for -n (Clear first N / oldest N)
    # Since the list is chronological (oldest first), clearing first N is slicing
    if count > 0:
        # Remove the first 'count' items
        # If count is 5, we keep from index 5 onwards
        if count >= len(commands):
            commands = [] # Clear all
        else:
            commands = commands[count:]
    
    # Logic for -f (Filter to delete)
    # We keep items that DO NOT match the filter
    final_list = []
    for cmd in commands:
        cmd_str = cmd.get("cmd", "")
        var_str = cmd.get("var", "")
        
        should_delete = False
        if filter_str and (filter_str in cmd_str or filter_str in var_str):
            should_delete = True
            
        if not should_delete:
            final_list.append(cmd)
            
    # Re-index
    for i, cmd in enumerate(final_list):
        cmd["id"] = i + 1
        
    data_obj[list_key] = final_list
    data_obj[id_key] = len(final_list)
    
    return initial_count - len(final_list)

@click.command("clear")
@click.option("--saved", is_flag=True, help="Clear saved commands.")
@click.option("--hist", is_flag=True, help="Clear cached history.")
@click.option("-n", "count", type=int, default=0, help="Clear the first N (oldest) commands.")
@click.option("-f", "filter_str", help="Clear commands matching this string.")
@click.option("--all", "all_flag", is_flag=True, help="Clear EVERYTHING in the target.")
def clear_cmd(saved, hist, count, filter_str, all_flag):
    """
    Clear and re-index commands.
    """
    if not saved and not hist:
        raise click.UsageError("Must specify target: --saved or --hist")
    
    if saved and hist:
        raise click.UsageError("Clear one target at a time.")
        
    if not (count or filter_str or all_flag):
        raise click.UsageError("Must specify what to clear: -n, -f, or --all")

    manager = StorageManager()
    
    if saved:
        data = manager.load_saved_cmds()
        removed = _perform_clear(data, "commands", "last_saved_id", count, filter_str, all_flag)
        if removed > 0:
            manager.save_saved_cmds(data)
            click.echo(f"Removed {removed} commands from Saved list. IDs re-indexed.")
        else:
            click.echo("No commands matched criteria.")
            
    elif hist:
        data = manager.load_cached_history()
        removed = _perform_clear(data, "commands", "last_sync_id", count, filter_str, all_flag)
        if removed > 0:
            manager.save_cached_history(data)
            click.echo(f"Removed {removed} commands from History cache. IDs re-indexed.")
        else:
            click.echo("No commands matched criteria.")