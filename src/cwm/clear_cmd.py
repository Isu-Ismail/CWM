# cwm/clear_cmd.py
import click
from datetime import datetime
from .storage_manager import StorageManager
from pathlib import Path  

def _clear_system_history(filter_str: str | None, remove_invalid: bool):
    """
    Clean system history with:
    - dedupe (keep newest)
    - filter removal
    - invalid command removal
    - progress indicators
    """

    from .utils import get_history_file_path, looks_invalid_command

    # ----------------------------------------
    # STEP 1 — Load
    # ----------------------------------------
    click.echo("[1/4] Locating history file...")

    path = get_history_file_path()
    if not path or not path.exists():
        click.echo("Error: Could not locate system history file.", err=True)
        return

    click.echo(f"[1/4] Reading history from: {path}")

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        click.echo("History file is empty.")
        return

    click.echo(f"[1/4] Loaded {len(lines)} lines.")

    # ----------------------------------------
    # STEP 2 — Parse filters
    # ----------------------------------------
    click.echo("[2/4] Preparing filters...")

    filters = []
    if filter_str:
        filters = [
            f.strip().strip('"').strip("'")
            for f in filter_str.split(",") if f.strip()
        ]
        click.echo(f"Filters active: {filters}")
    else:
        click.echo("No filters enabled.")

    # ----------------------------------------
    # STEP 3 — Deduplicate bottom-up
    # ----------------------------------------
    click.echo("[3/4] Deduplicating (keep newest copies)...")

    seen = set()
    deduped = []

    for line in reversed(lines):
        if line not in seen:
            seen.add(line)
            deduped.append(line)

    deduped.reverse()
    click.echo(f"[3/4] Deduped to {len(deduped)} unique lines.")

    # ----------------------------------------
    # STEP 4 — Apply filters + remove invalid commands
    # ----------------------------------------
    click.echo("[4/4] Filtering & validating commands...")

    def matches_filter(cmd: str) -> bool:
        for f in filters:
            if cmd.startswith(f):
                return True
        return False

    final_list = []
    removed_filtered = 0
    removed_invalid_count = 0

    for cmd in deduped:

        # Filter removal
        if filters and matches_filter(cmd):
            removed_filtered += 1
            continue

        # Invalid removal
        if remove_invalid and looks_invalid_command(cmd):
            removed_invalid_count += 1
            continue

        final_list.append(cmd)

    # ----------------------------------------
    # WRITE
    # ----------------------------------------
    out_file = path.parent / "system_history_cleaned.txt"
    out_file.write_text("\n".join(final_list), encoding="utf-8")

    click.echo("")
    click.echo("Cleaning complete!")
    click.echo(f"Saved cleaned file to:")
    click.echo(f"  {out_file}")
    click.echo("")
    click.echo(f"Removed due to filters: {removed_filtered}")
    if remove_invalid:
        click.echo(f"Removed invalid commands: {removed_invalid_count}")
    click.echo("")
    click.echo("Review the cleaned file before applying to your system history.")




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

   
    items_to_keep = []
    
    
    
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

def _backup_history_file(path: Path) -> Path:
    """Create a timestamped backup of the system history."""
    backup = path.parent / f"system_history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    backup.write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    return backup


def _undo_last_backup(path: Path):
    """Restore the most recent system_history_backup_*.txt."""
    parent = path.parent
    backups = sorted(parent.glob("system_history_backup_*.txt"))

    if not backups:
        click.echo("No backups found to restore.")
        return

    last = backups[-1]
    click.echo(f"Restoring backup: {last}")

    clean_text = last.read_text(encoding="utf-8", errors="ignore")
    path.write_text(clean_text, encoding="utf-8")

    click.echo("History file restored successfully.")


def _apply_cleaned_history(path: Path):
    """Apply system_history_cleaned.txt to actual system history file."""
    cleaned_path = path.parent / "system_history_cleaned.txt"

    if not cleaned_path.exists():
        click.echo("Error: Cleaned file not found. Run --sys-hist first.", err=True)
        return

    # Backup original
    backup = _backup_history_file(path)
    click.echo(f"Created backup: {backup}")

    # Apply new cleaned file
    clean_text = cleaned_path.read_text(encoding="utf-8", errors="ignore")
    path.write_text(clean_text, encoding="utf-8")

    click.echo("System history updated safely!")


@click.command("clear")
@click.option("--saved", is_flag=True, help="Clear saved commands.")
@click.option("--hist", is_flag=True, help="Clear cached history.")
@click.option("--sys-hist", is_flag=True, help="Clean the system shell history (remove dups, filters, invalid).")
@click.option("--remove-invalid", is_flag=True, help="Remove invalid or corrupted commands.")
@click.option("--apply", "apply_flag", is_flag=True, help="Apply the cleaned history to the real system file.")
@click.option("--undo", "undo_flag", is_flag=True, help="Restore the last backed-up system history file.")
@click.option("-n", "count", type=int, default=0, help="Clear the first N (oldest) commands.")
@click.option("-f", "filter_str", help="Clear commands matching this string.")
@click.option("--all", "all_flag", is_flag=True, help="Clear EVERYTHING in the target.")
def clear_cmd(saved, hist, sys_hist, count, filter_str, all_flag,remove_invalid,undo_flag,apply_flag):

    """
    Clear and re-index commands.

    """
    from .utils import get_history_file_path

    if sys_hist:

        from .utils import get_history_file_path
        path = get_history_file_path()

        if undo_flag:
            _undo_last_backup(path)
            return

        # Perform cleaning (does NOT overwrite system file)
        _clear_system_history(filter_str, remove_invalid)

        if apply_flag:
            _apply_cleaned_history(path)

        return




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