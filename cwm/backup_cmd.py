# cwm/backup_cmd.py
import click
import json
from .storage_manager import StorageManager
from datetime import datetime
from typing import List, Dict, Any, Tuple
from pathlib import Path

# ============================================================================
# BACKUP COMMAND GROUP
# ============================================================================
@click.group("backup")
def backup_cmd():
    """Manage and restore backups for saved_cmds.json."""
    pass

# ============================================================================
# LIST COMMAND
# ============================================================================
@backup_cmd.command("list")
def list_backups():
    """
    Lists available backups for saved_cmds.json.
    """
    manager = StorageManager()
    backups = manager.list_backups_for_file("saved_cmds.json")
    
    if not backups:
        click.echo("No backups found for saved_cmds.json.")
        return
        
    click.echo("Available backups (Oldest to Newest):")
    for bak in backups:
        try:
            data = json.loads(bak["full_path"].read_text(encoding="utf-8"))
            count = len(data.get("commands", []))
            count_str = f"{count} commands"
        except Exception:
            count_str = "Corrupted"
            
        click.echo(f"  ID: {bak['id']} | {bak['created']} | {count_str}")

# ============================================================================
# SHOW COMMAND (NOW WITH HEAD/TAIL)
# ============================================================================
@backup_cmd.command("show")
@click.argument("backup_id", nargs=1, required=False)
@click.option("--head", "head_flag", is_flag=True, help="Select backup from HEAD (oldest). Use with -n.")
@click.option("--tail", "tail_flag", is_flag=True, help="Select backup from TAIL (newest). Use with -n.")
@click.option("-n", "n_count", type=int, default=1, show_default=True, help="Select the Nth item for --head or --tail.")
def show_backup(backup_id, head_flag, tail_flag, n_count):
    """Shows the commands inside a specific backup file."""
    manager = StorageManager()

    # --- 1. Validate Flags and Get List of Backups ---
    show_methods = [bool(backup_id), head_flag, tail_flag]
    if sum(show_methods) == 0:
        raise click.UsageError("You must provide a method: an ID, --head, or --tail.")
    if sum(show_methods) > 1:
        raise click.UsageError("Methods (ID, --head, --tail) are mutually exclusive.")

    all_backups = manager.list_backups_for_file("saved_cmds.json")
    if not all_backups:
        click.echo("No backups found.")
        return

    backup_file_path: Path | None = None
    try:
        if backup_id:
            backup_file_path = manager.find_backup_by_id("saved_cmds.json", backup_id)
            if not backup_file_path:
                raise click.UsageError(f"Backup with ID '{backup_id}' not found.")

        elif head_flag:
            if not (1 <= n_count <= len(all_backups)):
                raise click.UsageError(f"Invalid index {n_count}. Must be between 1 and {len(all_backups)}.")
            backup_file_path = all_backups[n_count - 1]["full_path"] # Oldest is at index 0

        elif tail_flag:
            if not (1 <= n_count <= len(all_backups)):
                raise click.UsageError(f"Invalid index {n_count}. Must be between 1 and {len(all_backups)}.")
            backup_file_path = all_backups[-n_count]["full_path"] # Newest is at index -1
            
    except click.UsageError as e:
        click.echo(e.message)
        return
    
    if not backup_file_path:
        click.echo("Error: Could not determine which backup to show.")
        return

    # --- 2. Load and parse the backup file ---
    try:
        data_obj = json.loads(backup_file_path.read_text(encoding="utf-8"))
        saved_cmds = data_obj.get("commands", [])
        last_id = data_obj.get("last_saved_id", 0)
    except Exception as e:
        click.echo(f"Error: Could not read corrupted backup file {backup_file_path.name}. {e}")
        return

    # --- 3. Display the commands ---
    if not saved_cmds:
        click.echo(f"Backup file {backup_file_path.name} is valid but contains no commands.")
        return

    click.echo(f"--- Commands in Backup {backup_file_path.name} (Total: {len(saved_cmds)}, Last ID: {last_id}) ---")
    for item in saved_cmds:
        sid = item.get("id")
        var = item.get("var") or "(raw)"
        cmd = item.get("cmd")
        fav = "* " if item.get("fav") else ""
        click.echo(f"  [{sid}] {fav}{var} -- {cmd}")


# ============================================================================
# MERGE COMMAND (Unchanged, but remember to use quotes!)
# ============================================================================
@backup_cmd.command("merge")
@click.argument("backup_id", nargs=1, required=False)
@click.option("--head", "head_flag", is_flag=True, help="Select backup from HEAD (oldest). Use with -n.")
@click.option("--tail", "tail_flag", is_flag=True, help="Select backup from TAIL (newest). Use with -n.")
@click.option("-n", "n_count", type=int, default=1, show_default=True, help="Select the Nth item for --head or --tail.")
@click.option("--chain", "chain_ids", type=str, help="Merge a comma-separated chain of IDs sequentially. MUST USE QUOTES.")
def merge_backup(backup_id, head_flag, tail_flag, n_count, chain_ids):
    """
    Merge commands from one or more backups into the current saved commands.
    
    You must provide ONE merge method:
    1.  By ID: cwm backup merge <backup_id>
    2.  By Position: cwm backup merge --head -n 2
    3.  By Chain: cwm backup merge --chain "id1,id2,id3"
    """
    manager = StorageManager()
    
    # --- 1. Validate Flags and Get List of Backups ---
    
    merge_methods = [bool(backup_id), head_flag, tail_flag, bool(chain_ids)]
    if sum(merge_methods) == 0:
        raise click.UsageError("You must provide a merge method: an ID, --head, --tail, or --chain.")
    if sum(merge_methods) > 1:
        raise click.UsageError("Merge methods (ID, --head, --tail, --chain) are mutually exclusive.")

    backup_paths_to_merge: List[Path] = []
    
    all_backups = manager.list_backups_for_file("saved_cmds.json")
    if not all_backups:
        click.echo("No backups found to merge.")
        return

    try:
        if backup_id:
            path = manager.find_backup_by_id("saved_cmds.json", backup_id)
            if not path:
                raise click.UsageError(f"Backup with ID '{backup_id}' not found.")
            backup_paths_to_merge.append(path)

        elif head_flag:
            if not (1 <= n_count <= len(all_backups)):
                raise click.UsageError(f"Invalid index {n_count}. Must be between 1 and {len(all_backups)}.")
            backup_paths_to_merge.append(all_backups[n_count - 1]["full_path"]) # Oldest is at index 0

        elif tail_flag:
            if not (1 <= n_count <= len(all_backups)):
                raise click.UsageError(f"Invalid index {n_count}. Must be between 1 and {len(all_backups)}.")
            backup_paths_to_merge.append(all_backups[-n_count]["full_path"]) # Newest is at index -1
            
        elif chain_ids:
            # We split by comma, which handles "id1,id2" and "id1, id2" (with strip)
            ids = [id_str.strip() for id_str in chain_ids.split(',')]
            if not ids:
                raise click.UsageError("Chain cannot be empty.")
                
            for bid in ids:
                path = manager.find_backup_by_id("saved_cmds.json", bid)
                if not path:
                    # This is where your error was happening.
                    # It's because the 'bid' your shell sent was '164646', not '0164646'.
                    # Using quotes like --chain "0164646" fixes this.
                    raise click.UsageError(f"Backup with ID '{bid}' in chain not found. Did you use quotes?")
                backup_paths_to_merge.append(path)
                
    except click.UsageError as e:
        click.echo(e.message)
        return
        
    # --- 2. Load Current Data ---
    click.echo("Loading current saved commands...")
    try:
        current_data = manager.load_saved_cmds()
    except Exception as e:
        click.echo(f"Error loading current data: {e}. Aborting merge.")
        return

    # --- 3. Perform Sequential Merge ---
    
    merged_data_in_memory = current_data
    total_added = 0
    
    for i, bak_path in enumerate(backup_paths_to_merge):
        click.echo(f"\n--- Merging Backup {i+1} of {len(backup_paths_to_merge)} ({bak_path.name}) ---")
        try:
            backup_data = json.loads(bak_path.read_text(encoding="utf-8"))
            
            merged_data_in_memory, num_added = _perform_interactive_merge(
                current_data=merged_data_in_memory,
                backup_data=backup_data
            )
            total_added += num_added
            
        except Exception as e:
            click.echo(f"Error reading backup {bak_path.name}: {e}. Skipping this file.")
            continue
            
    # --- 4. Finalize and Save (Only once!) ---
    if total_added == 0:
        click.echo("\nMerge complete. No new commands were added.")
        return

    click.echo(f"\n--- Merge Complete ---")
    click.echo(f"Total new commands added: {total_added}")
    
    try:
        manager.save_saved_cmds(merged_data_in_memory)
        click.echo("Successfully saved merged commands and created new backup.")
    except Exception as e:
        click.echo(f"CRITICAL ERROR: Failed to save final merged data: {e}")

# ============================================================================
# MERGE HELPER FUNCTION (CORE LOGIC)
# ============================================================================

def _perform_interactive_merge(current_data: Dict[str, Any], backup_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Performs the core merge logic between two data objects.
    Handles duplicates, conflicts, and re-indexing.
    Returns the new merged data object and the number of commands added.
    """
    
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
        click.echo("This backup contained no new commands.")
        return current_data, 0

    for cmd in commands_to_add:
        current_last_id += 1
        cmd["id"] = current_last_id
        cmd["updated_at"] = _now_iso() 
        current_cmds.append(cmd)

    current_data["commands"] = current_cmds
    current_data["last_saved_id"] = current_last_id
    
    return current_data, len(commands_to_add)


def _now_iso():
    """Helper for timestamps."""
    return datetime.utcnow().isoformat()