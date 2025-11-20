# cwm/config_cmd.py
import click
import json
from pathlib import Path
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .utils import get_all_history_candidates, find_nearest_bank_path

# --- Helper to write to a specific config file ---
def _write_config(path: Path, key: str, value):
    """Updates a specific config file, creating it if necessary."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except:
            data = {} # Reset if corrupted
            
    data[key] = value
    
    # Ensure directory exists (for global)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

# --- Helper to clear a config ---
def _clear_config(path: Path):
    if path.exists():
        path.write_text("{}", encoding="utf-8")
        return True
    return False

@click.command("config")
@click.option("--shell", is_flag=True, help="Select preferred shell history file.")
@click.option("--stop-warning", is_flag=True, help="Disable the large history warning.")
@click.option("--global", "global_mode", is_flag=True, help="Target the Global config (even if inside a local bank).")
@click.option("--clear-local", is_flag=True, help="Reset local configuration to defaults.")
@click.option("--clear-global", is_flag=True, help="Reset global configuration to defaults.")
@click.option("--show", is_flag=True, help="Show configuration file locations.")
def config_cmd(shell, stop_warning, global_mode, clear_local, clear_global, show):
    """
    Manage CWM configuration.
    
    By default, changes apply to the Active Bank (Local if present, else Global).
    Use --global to force changes to the Global Bank.
    """
    manager = StorageManager()
    
    # Determine Target Config File
    target_path = manager.config_file # Default to Active
    target_name = "Active"
    
    if global_mode:
        target_path = GLOBAL_CWM_BANK / "config.json"
        target_name = "Global"

    # --- 1. SHOW INFO ---
    if show:
        click.echo("--- CWM Configuration ---")
        
        # Local info
        local_bank = find_nearest_bank_path(Path.cwd())
        if local_bank:
            local_conf = local_bank / "config.json"
            status = "Exists" if local_conf.exists() else "Not created"
            click.echo(f"Local Config:  {local_conf} ({status})")
        else:
            click.echo("Local Config:  (No local bank found)")

        # Global info
        global_conf = GLOBAL_CWM_BANK / "config.json"
        g_status = "Exists" if global_conf.exists() else "Not created"
        click.echo(f"Global Config: {global_conf} ({g_status})")
        
        # Active info
        click.echo(f"\nCurrently Active: {manager.config_file}")
        return

    # --- 2. CLEAR COMMANDS ---
    if clear_local:
        local_bank = find_nearest_bank_path(Path.cwd())
        if not local_bank:
            click.echo("Error: No local bank found to clear.")
            return
        
        if _clear_config(local_bank / "config.json"):
            click.echo("Local configuration cleared.")
        else:
            click.echo("Local configuration file not found.")
        return

    if clear_global:
        if _clear_config(GLOBAL_CWM_BANK / "config.json"):
            click.echo("Global configuration cleared.")
        else:
            click.echo("Global configuration file not found.")
        return

    # --- 3. STOP WARNING ---
    if stop_warning:
        _write_config(target_path, "suppress_history_warning", True)
        click.echo(f"History size warning disabled in {target_name} config.")
        return

    # --- 4. SHELL SELECTION ---
    if shell:
        candidates = get_all_history_candidates()
        if not candidates:
            click.echo("No history files found on this system.")
            return

        click.echo(f"Available History Files (Saving to {target_name} Config):")
        for i, path in enumerate(candidates):
            click.echo(f"  [{i+1}] {path}")
        
        try:
            selection = click.prompt("Select history file ID", type=int)
            if 1 <= selection <= len(candidates):
                selected_path = candidates[selection-1]
                
                # Write to the calculated target path
                _write_config(target_path, "history_file", str(selected_path))
                
                click.echo(f"Updated {target_name} configuration. Now using: {selected_path}")
            else:
                click.echo("Invalid selection.")
        except click.Abort:
            click.echo("\nCancelled.")
    else:
        click.echo("Usage: cwm config [OPTIONS]")
        click.echo("Try 'cwm config --help' for details.")