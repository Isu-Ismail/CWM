# cwm/backup_cmd.py
import click
import json
from .storage_manager import StorageManager
from datetime import datetime
from typing import List, Dict, Any, Tuple
from pathlib import Path

def _now_iso():
    return datetime.utcnow().isoformat()

def _perform_interactive_merge(current_data: Dict[str, Any], backup_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    current_cmds = current_data.get("commands", [])
    backup_cmds = backup_data.get("commands", [])
    current_last_id = current_data.get("last_saved_id", 0)
    
    current_exact_set = set()
    current_var_set = {}
    
    for cmd in current_cmds:
        if cmd.get("var"):
            current_exact_set.add((cmd["var"], cmd["cmd"]))
            current_var_set[cmd["var"]] = cmd["cmd"]
        else:
            current_exact_set.add((None, cmd["cmd"]))

    commands_to_add = []
    
    for cmd in backup_cmds:
        cmd_var = cmd.get("var")
        cmd_text = cmd.get("cmd")
        
        if (cmd_var, cmd_text) in current_exact_set:
            click.echo(f"  - Skipping exact duplicate: {cmd_var or 'raw'}")
            continue
            
        if cmd_var and cmd_var in current_var_set:
            click.echo(f"\nCONFLICT: Variable '{cmd_var}' already exists.")
            click.echo(f"  CURRENT:  {current_var_set[cmd_var]}")
            click.echo(f"  INCOMING: {cmd_text}")
            
            action = click.prompt(
                f"  Action for incoming '{cmd_var}': [r]ename, [d]elete, [s]kip",
                type=click.Choice(['r', 'd', 's']),
                default='s'
            )
            
            if action == 's' or action == 'd':
                click.echo(f"  - Skipping incoming '{cmd_var}'.")
                continue
            
            if action == 'r':
                while True:
                    new_name = click.prompt(f"  Enter new name for incoming '{cmd_var}'")
                    if not new_name:
                        click.echo("    Name cannot be empty.")
                        continue
                    if new_name in current_var_set:
                        click.echo(f"    Error: '{new_name}' already exists. Try another name.")
                        continue
                    
                    cmd["var"] = new_name 
                    click.echo(f"  - Renamed incoming '{cmd_var}' to '{new_name}'.")
                    current_var_set[new_name] = cmd_text
                    break 
        
        commands_to_add.append(cmd)
        
        if cmd_var:
            current_var_set[cmd_var] = cmd_text
        else:
            current_exact_set.add((None, cmd_text))

    if not commands_to_add:
        return current_data, 0

    for cmd in commands_to_add:
        current_last_id += 1
        cmd["id"] = current_last_id
        cmd["updated_at"] = _now_iso() 
        current_cmds.append(cmd)

    current_data["commands"] = current_cmds
    current_data["last_saved_id"] = current_last_id
    
    return current_data, len(commands_to_add)

def _get_sneak_peek(bak_path: Path) -> str:
    try:
        data = json.loads(bak_path.read_text(encoding="utf-8"))
        cmds = data.get("commands", [])
        if not cmds: return "(empty)"
        first = (cmds[0].get("var") or cmds[0].get("cmd", ""))[:20]
        if len(cmds) > 1:
            last = (cmds[-1].get("var") or cmds[-1].get("cmd", ""))[:20]
            return f"| {first}... {last}"
        return f"| {first}"
    except Exception:
        return "| (Corrupted)"

@click.group("backup")
def backup_cmd():
    """Manage and restore backups for saved_cmds.json."""
    pass

@backup_cmd.command("list")
def list_backups():
    """List all available backups."""
    manager = StorageManager()
    backups = manager.list_backups_for_file("saved_cmds.json")
    
    if not backups:
        click.echo("No backups found for saved_cmds.json.")
        return

    click.echo("Available backups (Oldest to Newest):")
    for i, bak in enumerate(backups):
        sneak_peek = _get_sneak_peek(bak["full_path"])
        click.echo(f"  [{i+1}] ID: {bak['id']} | {bak['created']} {sneak_peek}")

@backup_cmd.command("show")
@click.argument("backup_id", required=False)
@click.option("-n", "count", default=10, help="Number of commands to show (default 10).")
@click.option("--all", is_flag=True, help="Show all commands in the backup.")
def show_backup(backup_id, count, all):
    """
    Show contents of a specific backup (or latest if ID not provided).
    """
    manager = StorageManager()
    backup_file_path = None
    
    if backup_id:
        backup_file_path = manager.find_backup_by_id("saved_cmds.json", backup_id)
        if not backup_file_path:
            click.echo(f"Error: Backup with ID '{backup_id}' not found.")
            return
    else:
        # Default to latest
        all_backups = manager.list_backups_for_file("saved_cmds.json")
        if not all_backups:
            click.echo("No backups found.")
            return
        backup_file_path = all_backups[-1]["full_path"]
        click.echo(f"Showing Latest Backup: {all_backups[-1]['id']}")

    try:
        data_obj = json.loads(backup_file_path.read_text(encoding="utf-8"))
        saved_cmds = data_obj.get("commands", [])
    except Exception as e:
        click.echo(f"Error: Corrupted backup file. {e}")
        return

    if not saved_cmds:
        click.echo("Backup is empty.")
        return

    total = len(saved_cmds)
    
    # Show latest commands first (reverse list)
    display_cmds = list(reversed(saved_cmds))
    
    if not all:
        display_cmds = display_cmds[:count]

    click.echo(f"--- Backup Contents (Showing {len(display_cmds)}/{total}) ---")
    for item in display_cmds:
        var = item.get("var") or "(raw)"
        cmd = item.get("cmd")
        click.echo(f"  {var:<15} : {cmd}")

@backup_cmd.command("merge")
@click.argument("ids", required=False)
@click.option("-n", "limit", default=10, help="Limit list display if no ID provided.")
def merge_backup(ids, limit):
    """
    Merge commands from backups.
    
    Usage:
      cwm backup merge          (List options and prompt)
      cwm backup merge 1        (Merge specific list number)
      cwm backup merge 1,2,3    (Chain merge multiple backups)
    """
    manager = StorageManager()
    backups = manager.list_backups_for_file("saved_cmds.json")
    
    if not backups:
        click.echo("No backups found to merge.")
        return

    target_paths = []

    # --- Scenario 1: Interactive Selection (No argument provided) ---
    if not ids:
        # Show last N backups
        # We slice to get the last 'limit' items
        recent_backups = backups[-limit:]
        
        click.echo(f"--- Recent Backups (Showing last {len(recent_backups)}) ---")
        
        # Map standard 1-based index to actual backup objects
        # We map based on the full list index to keep numbers consistent with 'list' command
        display_map = {}
        
        start_idx = len(backups) - len(recent_backups) + 1
        
        for i, bak in enumerate(recent_backups):
            display_num = str(start_idx + i)
            display_map[display_num] = bak
            sneak = _get_sneak_peek(bak["full_path"])
            click.echo(f"  [{display_num}] {bak['created']} (ID: {bak['id']}) {sneak}")

        choice = click.prompt("\nEnter numbers to merge (comma-separated) e.g. '5' or '5,6'", default="", show_default=False)
        if not choice: return
        ids = choice # Pass logic to next block

    # --- Scenario 2: Process IDs (Manual or from Prompt) ---
    # The user inputs '1,2' which corresponds to the LIST INDEX shown in 'cwm backup list'
    # NOT the internal hash ID.
    
    selection_tokens = ids.split(',')
    
    for token in selection_tokens:
        token = token.strip()
        try:
            idx = int(token) - 1 # Convert 1-based to 0-based index
            if 0 <= idx < len(backups):
                target_paths.append(backups[idx]["full_path"])
            else:
                click.echo(f"Warning: Number '{token}' is out of range.")
        except ValueError:
            click.echo(f"Warning: '{token}' is not a valid number.")

    if not target_paths:
        click.echo("No valid backups selected.")
        return

    # --- Execution: Merge Loop ---
    click.echo("Loading current saved commands...")
    current_data = manager.load_saved_cmds()
    
    merged_data_in_memory = current_data
    total_added = 0
    
    for i, bak_path in enumerate(target_paths):
        click.echo(f"\n--- Merging Backup {i+1}/{len(target_paths)} ({bak_path.name}) ---")
        try:
            backup_data = json.loads(bak_path.read_text(encoding="utf-8"))
            merged_data_in_memory, num_added = _perform_interactive_merge(
                current_data=merged_data_in_memory,
                backup_data=backup_data
            )
            total_added += num_added
        except Exception as e:
            click.echo(f"Error reading backup: {e}. Skipping.")
            
    if total_added == 0:
        click.echo("\nMerge complete. No new commands were added.")
        return

    click.echo(f"\n--- Merge Complete ---")
    click.echo(f"Total new commands added: {total_added}")
    
    manager.save_saved_cmds(merged_data_in_memory)
    click.echo("Successfully saved merged commands.")