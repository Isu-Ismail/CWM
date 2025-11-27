# cwm/config_cmd.py
import click
import json
from pathlib import Path
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .utils import get_all_history_candidates, find_nearest_bank_path, DEFAULT_CONFIG

def _write_config(path: Path, key: str, value):
    """Updates a specific config file, creating it if necessary."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except:
            data = {} 
            
    data[key] = value
    
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _modify_config_list(path: Path, key: str, item: str, action: str):
    """Adds or removes items from a list in config."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except:
            pass
            
    # Get current list, defaulting to system defaults if missing
    current_list = data.get(key, DEFAULT_CONFIG.get(key, []))
    
    modified = False
    if action == "add":
        if item not in current_list:
            current_list.append(item)
            modified = True
            click.echo(f"Added '{item}' to {key}.")
        else:
            click.echo(f"'{item}' is already in {key}.")
            
    elif action == "remove":
        if item in current_list:
            current_list.remove(item)
            modified = True
            click.echo(f"Removed '{item}' from {key}.")
        else:
            click.echo(f"'{item}' not found in {key}.")

    if modified:
        data[key] = current_list
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _clear_config(path: Path):
    if path.exists():
        path.write_text("{}", encoding="utf-8")
        return True
    return False

# Hard path for Global Settings
GLOBAL_CONFIG_PATH = GLOBAL_CWM_BANK / "config.json"

@click.command("config")
@click.option("--shell", is_flag=True, help="Select preferred shell history file.")
@click.option("--stop-warning", is_flag=True, help="Disable the large history warning.")
@click.option("--global", "global_mode", is_flag=True, help="Target the Global config explicitly.")
@click.option("--clear-local", is_flag=True, help="Reset local configuration.")
@click.option("--clear-global", is_flag=True, help="Reset global configuration.")
@click.option("--show", is_flag=True, help="Show configuration file locations and values.")
@click.option("--editor", help="Set the default editor command (e.g. 'code', 'vim').")
@click.option("--add-marker", help="Add a project detection marker (e.g. 'go.mod').")
@click.option("--remove-marker", help="Remove a project detection marker.")
def config_cmd(shell, stop_warning, global_mode, clear_local, clear_global, show, 
               editor, add_marker, remove_marker):
    """
    Manage CWM configuration.
    
    Global Settings (Editor, Markers) -> Saved to Global Bank
    Local Settings (History Source)   -> Saved to Local Bank (if exists)
    """
    manager = StorageManager()
    
    # Determine Target for History/Warning settings
    # If inside a project, use Local. If not, use Global.
    local_bank = find_nearest_bank_path(Path.cwd())
    
    # Default to active (could be local or global)
    target_path_context = manager.config_file 
    target_name = "Active"
    
    if global_mode:
        target_path_context = GLOBAL_CONFIG_PATH
        target_name = "Global"

    # --- 1. SHOW INFO ---
    if show:
        click.echo("--- CWM Configuration ---")
        
        if local_bank:
            local_conf = local_bank / "config.json"
            status = "Exists" if local_conf.exists() else "Not created"
            click.echo(f"Local Config:  {local_conf} ({status})")
        else:
            click.echo("Local Config:  (No local bank found)")

        g_status = "Exists" if GLOBAL_CONFIG_PATH.exists() else "Not created"
        click.echo(f"Global Config: {GLOBAL_CONFIG_PATH} ({g_status})")
        
        # Show Merged Values
        config = manager.get_config() # Helper gets local merged with global
        
        click.echo(f"\n--- Effective Settings ({target_name}) ---")
        click.echo(f"History File:   {config.get('history_file', 'Auto-Detect')}")
        click.echo(f"Default Editor: {config.get('default_editor', 'code')}")
        click.echo(f"Markers:        {', '.join(config.get('project_markers', []))}")
        
        # API Keys (Masked)
        for key in ["gemini_key", "openai_key", "stack_key", "google_search_key"]:
            val = config.get(key)
            if val:
                click.echo(f"{key}: {val[:4]}...{val[-4:]}")
                
        return

    # --- 2. GLOBAL SETTINGS (Always Global) ---
    # Editor and Markers apply system-wide, so we force write to GLOBAL_CONFIG_PATH
    
    if editor:
        _write_config(GLOBAL_CONFIG_PATH, "default_editor", editor)
        click.echo(f"Default editor set to: {editor} (Global)")
        return

    if add_marker:
        _modify_config_list(GLOBAL_CONFIG_PATH, "project_markers", add_marker, "add")
        return

    if remove_marker:
        _modify_config_list(GLOBAL_CONFIG_PATH, "project_markers", remove_marker, "remove")
        return

    # --- 3. CONTEXT SETTINGS (Local OR Global) ---
    # History and Warnings apply to the specific context
    
    if stop_warning:
        _write_config(target_path_context, "suppress_history_warning", True)
        click.echo(f"History warning disabled in {target_name} config.")
        return

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
                _write_config(target_path_context, "history_file", str(selected_path))
                click.echo(f"Updated {target_name} history source: {selected_path}")
            else:
                click.echo("Invalid selection.")
        except click.Abort:
            click.echo("\nCancelled.")
        return

    # --- 4. CLEAR COMMANDS ---
    if clear_local:
        if not local_bank:
            click.echo("Error: No local bank found.")
            return
        
        if _clear_config(local_bank / "config.json"):
            click.echo("Local configuration cleared.")
        else:
            click.echo("Local configuration file missing.")
        return

    if clear_global:
        if _clear_config(GLOBAL_CONFIG_PATH):
            click.echo("Global configuration cleared.")
        else:
            click.echo("Global configuration file missing.")
        return

    # Fallback Help
    click.echo("Usage: cwm config [OPTIONS]")
    click.echo("Try 'cwm config --help' for details.")