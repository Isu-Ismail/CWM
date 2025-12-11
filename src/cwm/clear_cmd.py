import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from .storage_manager import StorageManager
from .rich_help import RichHelpCommand

console = Console()

# --- HELPERS ---

def _clean_file_logic(target_path: Path, filter_str: str | None, remove_invalid: bool):
    """
    Clean history file logic (System or Local).
    """
    from .utils import looks_invalid_command

    console.print(f"[bold cyan][1/4][/bold cyan] Locating history file...")
    if not target_path or not target_path.exists():
        console.print(f"[red]Error: Could not locate file at {target_path}[/red]")
        return

    try:
        lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        return

    if not lines:
        console.print("[yellow]History file is empty.[/yellow]")
        return

    console.print(f"[dim]Loaded {len(lines)} lines.[/dim]")
    console.print("[bold cyan][2/4][/bold cyan] Preparing filters...")

    filters = []
    if filter_str:
        filters = [f.strip().strip('"').strip("'") for f in filter_str.split(",") if f.strip()]
        console.print(f"  [dim]Filters active: {filters}[/dim]")

    console.print("[bold cyan][3/4][/bold cyan] Deduplicating (keep newest copies)...")
    seen = set()
    deduped = []
    for line in reversed(lines):
        cmd = line.strip()
        if cmd and cmd not in seen:
            seen.add(cmd)
            deduped.append(cmd)
    deduped.reverse()
    console.print(f"  [dim]Deduped to {len(deduped)} unique lines.[/dim]")

    console.print("[bold cyan][4/4][/bold cyan] Filtering & validating commands...")
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

    console.print("\n[bold green]✔ Cleaning complete![/bold green]")
    console.print(f"  Saved preview to: [cyan]{out_file.name}[/cyan]")
    console.print(f"  Removed: [red]{removed_filtered}[/red] (filters), [red]{removed_invalid_count}[/red] (invalid)")
    console.print("  [dim]Run with --apply to overwrite the actual history file.[/dim]")


def _apply_cleaned_file(path: Path):
    cleaned_path = path.parent / f"{path.stem}_cleaned{path.suffix}"

    if not cleaned_path.exists():
        console.print(f"[red]Error: Cleaned file '{cleaned_path.name}' not found. Run cleaning first.[/red]")
        return

    manager = StorageManager()
    
    # Use internal method to backup
    manager._update_backup(path) 
    console.print(f"[dim]Backup created: {path.name}.bak[/dim]")

    clean_text = cleaned_path.read_text(encoding="utf-8", errors="ignore")
    path.write_text(clean_text, encoding="utf-8")
    
    cleaned_path.unlink()

    console.print(f"[bold green]✔ File {path.name} successfully updated![/bold green]")


def _undo_cleaning(path: Path):
    manager = StorageManager()
    restored_data = manager._restore_from_backup(path, default="")
    
    if restored_data:
         console.print(f"[bold green]✔ Successfully undid changes to {path.name}[/bold green]")
    else:
         console.print(f"[red]⚠ Undo failed or no backup found for {path.name}[/red]")


def _get_local_history_file() -> Path | None:
    manager = StorageManager()
    root = manager.find_project_root()
    if not root:
        console.print("[red]Local History file not found (are you in a project?)[/red]")
        return None
    
    hist = root / ".cwm" / "project_history.txt"
    if hist.exists():
        return hist
        
    console.print("[red]Local History file does not exist yet.[/red]")
    return None

# --- NEW SAVED COMMAND LOGIC ---

def _delete_saved_wizard(manager):
    """Interactive wizard to delete saved commands."""
    data = manager.load_saved_cmds()
    commands = data.get("commands", [])

    if not commands:
        console.print("[dim]No saved commands to clear.[/dim]")
        return

    # 1. Display Table
    console.print("\n[bold]Saved Commands[/bold]")
    table = Table(box=None, show_header=True, padding=(0, 2))
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Variable", style="bold white")
    table.add_column("Command", style="dim")

    for cmd in commands:
        c_str = cmd.get('cmd', '-')
        if len(c_str) > 50: c_str = c_str[:47] + "..."
        table.add_row(str(cmd['id']), cmd.get('var', 'N/A'), c_str)
    
    console.print(table)
    console.print("")

    # 2. Prompt
    ids_input = Prompt.ask("  [bold red]✖[/bold red] Enter IDs to delete [dim](comma-separated)[/dim]", default="")
    if not ids_input: return

    try:
        target_ids = {int(x.strip()) for x in ids_input.split(',') if x.strip()}
    except ValueError:
        console.print("[red]Invalid input. Use numbers.[/red]")
        return

    # 3. Process
    new_list = [c for c in commands if c['id'] not in target_ids]
    removed_count = len(commands) - len(new_list)

    if removed_count > 0:
        # Re-index
        for i, cmd in enumerate(new_list, start=1):
            cmd["id"] = i
        
        data["commands"] = new_list
        data["last_saved_id"] = len(new_list)
        manager.save_saved_cmds(data)
        console.print(f"[green]✔ Removed {removed_count} commands.[/green]")
    else:
        console.print("[yellow]No matching IDs found.[/yellow]")


def _delete_saved_direct(manager, target_ids=None, target_vars=None):
    """Direct deletion by ID or Variable list."""
    data = manager.load_saved_cmds()
    commands = data.get("commands", [])
    initial_len = len(commands)
    
    if not commands:
        console.print("[dim]No saved commands.[/dim]")
        return

    new_list = []
    
    # Filter
    for cmd in commands:
        # If ID matches target_ids, skip (delete)
        if target_ids and cmd['id'] in target_ids:
            continue
        # If Var matches target_vars, skip (delete)
        if target_vars and cmd.get('var') in target_vars:
            continue
        new_list.append(cmd)

    removed_count = initial_len - len(new_list)

    if removed_count > 0:
        # Re-index
        for i, cmd in enumerate(new_list, start=1):
            cmd["id"] = i
            
        data["commands"] = new_list
        data["last_saved_id"] = len(new_list)
        manager.save_saved_cmds(data)
        console.print(f"[green]✔ Removed {removed_count} commands.[/green]")
    else:
        console.print("[yellow]No matching commands found.[/yellow]")


# --- MAIN COMMAND ---

@click.command("clear", cls=RichHelpCommand)
@click.option("--saved", is_flag=True, help="Clear saved commands (Wizard or Direct).")
@click.option("-id", "target_id", help="Target ID(s) for saved commands (e.g. 1 or 1,2).")
@click.option("-v", "target_var", help="Target Variable(s) for saved commands.")
@click.option("--sys-hist", is_flag=True, help="Clean the system shell history.")
@click.option("--loc-hist", is_flag=True, help="Clean local project history.")
@click.option("--remove-invalid", is_flag=True, help="Remove invalid or corrupted commands.")
@click.option("--apply", "apply_flag", is_flag=True, help="Apply the cleaned history to the real file.")
@click.option("--undo", "undo_flag", is_flag=True, help="Restore from .bak file.")
# Kept for History cleaning compatibility
@click.option("-f", "filter_str", help="Filter string for history cleaning.")
@click.option("-n", "count", type=int, default=0, help="Clear first N (oldest) history lines.")
def clear_cmd(saved, target_id, target_var, sys_hist, loc_hist, 
              count, filter_str, remove_invalid, undo_flag, apply_flag):
    """
    Clear saved commands or clean history files.
    """
    manager = StorageManager()

    # --- 1. SAVED COMMANDS LOGIC ---
    if saved:
        # Direct Mode (Flags provided)
        if target_id or target_var:
            t_ids = set()
            t_vars = set()
            
            if target_id:
                try:
                    t_ids = {int(x.strip()) for x in str(target_id).split(',') if x.strip()}
                except ValueError:
                    console.print("[red]Invalid ID format.[/red]")
                    return
            
            if target_var:
                t_vars = {x.strip() for x in str(target_var).split(',') if x.strip()}

            _delete_saved_direct(manager, target_ids=t_ids, target_vars=t_vars)
            return
        
        # Wizard Mode (No flags)
        _delete_saved_wizard(manager)
        return

    # --- 2. SYSTEM HISTORY ---
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

    # --- 3. LOCAL HISTORY ---
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

    # Fallback if no main flag selected
    console.print("[yellow]Please specify what to clear:[/yellow]")
    console.print("  [cyan]--saved[/cyan]     Saved Commands (Interactive)")
    console.print("  [cyan]--sys-hist[/cyan]  System Shell History")
    console.print("  [cyan]--loc-hist[/cyan]  Local Project History")