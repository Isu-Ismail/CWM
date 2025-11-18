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


def _get_sneak_peek(bak_path: Path) -> str:
    try:
        data = json.loads(bak_path.read_text(encoding="utf-8"))
        cmds = data.get("commands", [])
        if not cmds:
            return "(empty)"
        first = (cmds[0].get("var") or cmds[0].get("cmd", ""))[:20]
        if len(cmds) > 1:
            last = (cmds[-1].get("var") or cmds[-1].get("cmd", ""))[:20]
            return f"| {first}... {last}"
        return f"| {first}"
    except Exception:
        return "| (Corrupted)"
    

def _prompt_for_backup_selection(manager: StorageManager, hide_sneak_peek: bool = False) -> Dict[str, Dict]:
    backups = manager.list_backups_for_file("saved_cmds.json")
    
    if not backups:
        return {}
    click.echo("Available backups (Oldest to Newest):")
    display_map = {}
    
    for i, bak in enumerate(backups):
        list_num_str = str(i + 1)
        display_map[list_num_str] = bak
        sneak_peek = ""
        
        if not hide_sneak_peek:
            sneak_peek = _get_sneak_peek(bak["full_path"])
        click.echo(f"  [{list_num_str}] ID: {bak['id']} | {bak['created']} {sneak_peek}")
    
    return display_map


@click.group("backup")
def backup_cmd():
    """Manage and restore backups for saved_cmds.json."""
    pass


@backup_cmd.command("list")
def list_backups():
    manager = StorageManager()
    display_map = _prompt_for_backup_selection(manager, hide_sneak_peek=False)
    if not display_map:
        click.echo("No backups found for saved_cmds.json.")


@backup_cmd.command("show")
@click.argument("backup_id", nargs=1, required=False)
@click.option("--latest", is_flag=True, help="Show the most recent backup.")
@click.option("-l", "--list", "list_mode", is_flag=True, help="List and select a backup to show.")


def show_backup(backup_id, latest, list_mode):
    manager = StorageManager()
    backup_file_path: Path | None = None
    
    methods = sum([bool(backup_id), latest, list_mode])
    if methods > 1:
        raise click.UsageError("Only one of <backup_id>, --latest, or -l is allowed.")
        
    if backup_id:
        backup_file_path = manager.find_backup_by_id("saved_cmds.json", backup_id)
        if not backup_file_path:
            click.echo(f"Error: Backup with ID '{backup_id}' not found.")
            return
    
    elif latest:
        all_backups = manager.list_backups_for_file("saved_cmds.json")
        if not all_backups:
            click.echo("No backups found.")
            return
        backup_file_path = all_backups[-1]["full_path"]
    
    elif list_mode:
        display_map = _prompt_for_backup_selection(manager, hide_sneak_peek=False)
        if not display_map:
            click.echo("No backups found.")
            return
        
        try:
            choice = click.prompt("Enter number to show (or press Enter to skip)", default="", show_default=False)
            if not choice: return
            if choice not in display_map:
                click.echo(f"Error: '{choice}' is not a valid number.")
                return
            backup_file_path = display_map[choice]["full_path"]
        except click.exceptions.Abort:
            click.echo("\nCancelled.")
            return
    else:
        click.echo("Please provide a <backup_id>, --latest, or -l to select a backup.")
        return

    try:
        data_obj = json.loads(backup_file_path.read_text(encoding="utf-8"))
        saved_cmds = data_obj.get("commands", [])
        last_id = data_obj.get("last_saved_id", 0)
    except Exception as e:
        click.echo(f"Error: Could not read corrupted backup file {backup_file_path.name}. {e}")
        return

    if not saved_cmds:
        click.echo(f"Backup {backup_file_path.name} is valid but contains no commands.")
        return

    click.echo(f"--- Commands in Backup {backup_file_path.name} (Total: {len(saved_cmds)}, Last ID: {last_id}) ---")
    for item in saved_cmds:
        sid = item.get("id")
        var = item.get("var") or "(raw)"
        cmd = item.get("cmd")
        fav = "* " if item.get("fav") else ""
        click.echo(f"  [{sid}] {fav}{var} -- {cmd}")


# ============================================================================
# MERGE COMMAND (FIXED FLAGS)
# ============================================================================
@backup_cmd.command("merge")
@click.argument("backup_id", nargs=1, required=False)
@click.option("-l", "--list", "list_mode", is_flag=True, help="List and select ONE backup to merge.")
@click.option("-cl", "--chain-list", is_flag=True, help="List and select MULTIPLE backups to merge.")
@click.option("-h", "--hide-sneak-peek", is_flag=True, help="[List] Hide command sneak peek.")
@click.option("--chain", "chain_ids", type=str, help="Merge a comma-separated chain of IDs (Manual).")
def merge_backup(backup_id, list_mode, chain_list, hide_sneak_peek, chain_ids):
    """
    Merge commands from backups.
    
    Methods:
    1. cwm backup merge <id>
    2. cwm backup merge -l        (Select one)
    3. cwm backup merge -cl       (Select chain, e.g. 1,2,3)
    4. cwm backup merge --chain "id1,id2"
    """
    manager = StorageManager()
    backup_paths_to_merge: List[Path] = []
    
    methods = sum([bool(backup_id), list_mode, chain_list, bool(chain_ids)])
    if methods == 0:
        raise click.UsageError("You must provide a merge method: <id>, -l, -cl, or --chain.")
    if methods > 1:
        raise click.UsageError("Merge methods are mutually exclusive.")
    
    display_map = {} 
    
    try:
        if backup_id:
            path = manager.find_backup_by_id("saved_cmds.json", backup_id)
            if not path:
                raise click.UsageError(f"Backup with ID '{backup_id}' not found.")
            backup_paths_to_merge.append(path)

        elif chain_ids:
            # Manual chain
            ids = [id_str.strip() for id_str in chain_ids.split(',')]
            for bid in ids:
                path = manager.find_backup_by_id("saved_cmds.json", bid)
                if not path:
                    raise click.UsageError(f"Backup with ID '{bid}' in chain not found. Did you use quotes?")
                backup_paths_to_merge.append(path)
        
        elif list_mode or chain_list:
            # Interactive modes
            display_map = _prompt_for_backup_selection(manager, hide_sneak_peek)
            if not display_map:
                raise click.UsageError("No backups found to merge.")
            
            if list_mode:
                choice = click.prompt("Enter number to merge (or press Enter to skip)", default="", show_default=False)
                if not choice: return
                if choice not in display_map:
                    raise click.UsageError(f"Error: '{choice}' is not a valid number.")
                backup_paths_to_merge.append(display_map[choice]["full_path"])
            
            elif chain_list:
                choice_str = click.prompt("Enter numbers to merge in order (e.g. 1,3,2)")
                selected_nums = []
                for part in choice_str.split(','):
                    part = part.strip()
                    if '-' in part:
                        start_s, end_s = part.split('-')
                        try:
                            start, end = int(start_s), int(end_s)
                            if start > end: raise click.UsageError(f"Invalid range: {part}")
                            selected_nums.extend(range(start, end + 1))
                        except ValueError: raise click.UsageError("Invalid range.")
                    else:
                        try:
                            selected_nums.append(int(part))
                        except ValueError: raise click.UsageError(f"Invalid number: {part}")

                for num in selected_nums:
                    num_str = str(num)
                    if num_str not in display_map:
                        raise click.UsageError(f"Invalid selection: '{num_str}'.")
                    backup_paths_to_merge.append(display_map[num_str]["full_path"])
            
    except click.UsageError as e:
        click.echo(e.message)
        return
    except click.exceptions.Abort:
        click.echo("\nCancelled.")
        return
        
    click.echo("Loading current saved commands...")
    try:
        current_data = manager.load_saved_cmds()
    except Exception as e:
        click.echo(f"Error loading current data: {e}. Aborting merge.")
        return

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
            click.echo(f"Error reading backup {bak_path.name}: {e}. Skipping.")
            continue
            
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