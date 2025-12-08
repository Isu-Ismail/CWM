import click
from pathlib import Path
from .storage_manager import StorageManager
from .rich_help import RichHelpCommand


def _clean_file_logic(target_path: Path, filter_str: str | None, remove_invalid: bool):
    """
    Clean history file (System or Local) and save to 'filename_cleaned.txt'.
    """
    from .utils import looks_invalid_command

    click.echo("[1/4] Locating history file...")
    if not target_path or not target_path.exists():
        click.echo(f"Error: Could not locate file at {target_path}", err=True)
        return

    try:
        lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:
        click.echo(f"Error reading file: {e}", err=True)
        return

    if not lines:
        click.echo("History file is empty.")
        return

    click.echo(f"[1/4] Loaded {len(lines)} lines.")
    click.echo("[2/4] Preparing filters...")

    filters = []
    if filter_str:
        filters = [f.strip().strip('"').strip("'") for f in filter_str.split(",") if f.strip()]
        click.echo(f"Filters active: {filters}")

    click.echo("[3/4] Deduplicating (keep newest copies)...")
    seen = set()
    deduped = []
    for line in reversed(lines):
        cmd = line.strip()
        if cmd and cmd not in seen:
            seen.add(cmd)
            deduped.append(cmd)
    deduped.reverse()
    click.echo(f"[3/4] Deduped to {len(deduped)} unique lines.")

    click.echo("[4/4] Filtering & validating commands...")
    final_list = []
    removed_filtered = 0
    removed_invalid_count = 0

    for cmd in deduped:
        if filters and any(cmd.startswith(f) for f in filters):
            removed_filtered += 1
            continue
        if remove_invalid and looks_invalid_command(cmd):
            removed_invalid_count += 1
            continue
        final_list.append(cmd)

    out_file = target_path.parent / f"{target_path.stem}_cleaned{target_path.suffix}"
    out_file.write_text("\n".join(final_list), encoding="utf-8")

    click.echo("\nCleaning complete!")
    click.echo(f"Saved preview to: {out_file.name}")
    click.echo(f"Removed: {removed_filtered} (filters), {removed_invalid_count} (invalid)")
    click.echo("Run with --apply to overwrite the actual history file.")


def _apply_cleaned_file(path: Path):
    """
    Backs up original -> Overwrites with cleaned version.
    """
    cleaned_path = path.parent / f"{path.stem}_cleaned{path.suffix}"

    if not cleaned_path.exists():
        click.echo(f"Error: Cleaned file '{cleaned_path.name}' not found. Run cleaning first.", err=True)
        return

    manager = StorageManager()
    
    manager._update_backup(path) 
    click.echo(f"Backup updated: {path.name}.bak")

    clean_text = cleaned_path.read_text(encoding="utf-8", errors="ignore")
    path.write_text(clean_text, encoding="utf-8")
    
    cleaned_path.unlink() # Delete the temp _cleaned file

    click.echo(f"✔ File {path.name} successfully updated!")


def _undo_cleaning(path: Path):
    """
    Restores from the standard .bak file using StorageManager logic.
    """
    manager = StorageManager()
    
    restored_data = manager._restore_from_backup(path, default="")
    
    if restored_data:
         click.echo(f"✔ Successfully undid changes to {path.name}")
    else:
         click.echo(f"⚠ Undo failed or no backup found for {path.name}")


def _get_local_history_file() -> Path | None:
    manager = StorageManager()
    root = manager.find_project_root()
    hist = root / ".cwm" / "project_history.txt"
    
    if hist.exists():
        return hist
        
    click.echo("Local History file not found (are you in a project?)")
    return None
def _perform_clear(data_obj: dict, list_key: str, id_key: str, 
                   count: int, filter_str: str, clear_all: bool) -> int:
    """Generic logic to clear items from JSON data objects."""
    commands = data_obj.get(list_key, [])
    initial_count = len(commands)
    
    if clear_all:
        data_obj[list_key] = []
        data_obj[id_key] = 0
        return initial_count

    if count > 0:
        if count >= len(commands):
            commands = []
        else:
            commands = commands[count:]
    
    final_list = []
    for cmd in commands:
        cmd_str = cmd.get("cmd", "")
        var_str = cmd.get("var", "")
        
        should_delete = False
        if filter_str and (filter_str in cmd_str or filter_str in var_str):
            should_delete = True
            
        if not should_delete:
            final_list.append(cmd)
            
    for i, cmd in enumerate(final_list):
        cmd["id"] = i + 1
        
    data_obj[list_key] = final_list
    data_obj[id_key] = len(final_list)
    
    return initial_count - len(final_list)

@click.command("clear",cls=RichHelpCommand)
@click.option("--saved", is_flag=True, help="Clear saved commands.")
@click.option("--hist", is_flag=True, help="Clear cached history.")
@click.option("--sys-hist", is_flag=True, help="Clean the system shell history.")
@click.option("--loc-hist", is_flag=True, help="Clean local project history.")
@click.option("--remove-invalid", is_flag=True, help="Remove invalid or corrupted commands.")
@click.option("--apply", "apply_flag", is_flag=True, help="Apply the cleaned history to the real file.")
@click.option("--undo", "undo_flag", is_flag=True, help="Restore from .bak file.")
@click.option("-n", "count", type=int, default=0, help="Clear the first N (oldest) commands.")
@click.option("-f", "filter_str", help="Clear commands matching this string.")
@click.option("--all", "all_flag", is_flag=True, help="Clear EVERYTHING in the target.")
def clear_cmd(saved, hist, sys_hist, loc_hist, count, filter_str, all_flag, remove_invalid, undo_flag, apply_flag):
    """
    Clear and re-index commands or clean history files.
    """
    manager = StorageManager()

    if sys_hist:
        from .utils import get_history_file_path
        path = get_history_file_path()
        if not path: return

        if undo_flag:
            _undo_cleaning(path)
            return

        _clean_file_logic(path, filter_str, remove_invalid)
        if apply_flag:
            _apply_cleaned_file(path)
        return

    if loc_hist:
        path = _get_local_history_file()
        if not path: return

        if undo_flag:
            _undo_cleaning(path)
            return

        _clean_file_logic(path, filter_str, remove_invalid)
        if apply_flag:
            _apply_cleaned_file(path)
        return

    if not saved and not hist:
        raise click.UsageError("Must specify target: --saved, --hist, --sys-hist, or --loc-hist")
    
    if saved and hist:
        raise click.UsageError("Clear one target at a time.")
        
    if not (count or filter_str or all_flag):
        raise click.UsageError("Must specify what to clear: -n, -f, or --all")

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