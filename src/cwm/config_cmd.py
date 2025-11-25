# cwm/config_cmd.py
import click
import json
from pathlib import Path
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .utils import get_all_history_candidates, find_nearest_bank_path, DEFAULT_CONFIG

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

# --- Helper to modify list settings (like markers) ---
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

# --- Helper to clear a config ---
def _clear_config(path: Path):
    if path.exists():
        path.write_text("{}", encoding="utf-8")
        return True
    return False

global_config_path = GLOBAL_CWM_BANK/"config.json"


@click.command("config")
@click.option("--shell", is_flag=True, help="Select preferred shell history file.")
@click.option("--stop-warning", is_flag=True, help="Disable the large history warning.")
@click.option("--global", "global_mode", is_flag=True, help="Target the Global config (even if inside a local bank).")
@click.option("--clear-local", is_flag=True, help="Reset local configuration to defaults.")
@click.option("--clear-global", is_flag=True, help="Reset global configuration to defaults.")
@click.option("--show", is_flag=True, help="Show configuration file locations and values.")
# --- NEW OPTIONS ---
@click.option("--editor", help="Set the default editor command (e.g. 'code', 'vim').")
@click.option("--add-marker", help="Add a project detection marker (e.g. 'go.mod').")
@click.option("--remove-marker", help="Remove a project detection marker.")
#new api options
# @click.option("--gemini-key", help="Set the Gemini API key.")
# @click.option("--openai-key", help="Set the OpenAI API key.")
# @click.option("--stack-key", help="Set the Stack API key.")
# @click.option("--google-search-key", help="Set the Google Search API key.")

def config_cmd(shell, stop_warning, global_mode, clear_local, clear_global, show, 
               editor, add_marker, remove_marker):
            #    gemini_key,openai_key,stack_key,google_search_key)
    """
    Manage CWM configuration.
    
    Control history settings, editors, and project detection rules.
    By default, changes apply to the Active Bank (Local if present, else Global).
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
        
        # Current Values (Read from Target)
        try:
            data = json.loads(target_path.read_text()) if target_path.exists() else {}
        except: data = {}

       

        custom_markers ={
        "history_file":"History FIle Path",
        "default_editor":"Default Code editor",
        "default_terminal":"Default Terminal",
        "project_markers":"Project Markers",
        "gemini_key":"Gemini API key",
        "openai_key":"OpenAi API key",
        "stack_key":"StackOverflow API key",
        "google_search_key":"Google Search API key"
        }

        mask =["gemini_key","openai_key","stack_key","google_search_key"]

        for key,value in data.items() :
            if key in custom_markers and key in mask :
                click.echo(f"{custom_markers[key]} : {value[1:10]}...")
            else:
                click.echo(f"{custom_markers[key]} : {value}")
        return

    # --- 2. HANDLE NEW OPTIONS ---
    if editor:
        _write_config(target_path, "default_editor", editor)
        click.echo(f"Default editor set to: {editor}")
        return

    if add_marker:
        _modify_config_list(target_path, "project_markers", add_marker, "add")
        return

    if remove_marker:
        _modify_config_list(target_path, "project_markers", remove_marker, "remove")
        return
    
    #api-key setting logic
    # API-key setting logic (direct only – no prompts)
    # api_key_updates = {
    #     "gemini_key": gemini_key,
    #     "openai_key": openai_key,
    #     "stack_key": stack_key,
    #     "google_search_key": google_search_key,
    # }

    # key_was_set = False

    # for key_name, key_value in api_key_updates.items():

    #     # Only accept API keys explicitly given by user
    #     if key_value is None or key_value == "":
    #         continue  # User did NOT use this option, skip it

    #     # Clean the value (remove quotes if user wrapped them)
    #     value_to_store = key_value.strip('"').strip("'")

    #     click.echo(f"Setting {key_name} from command line argument.")

    #     # Save to Global Config
    #     _write_config(global_config_path, key_name, value_to_store)

    #     click.echo(f"{key_name} successfully set in Global config.")
    #     key_was_set = True

    # if key_was_set:
    #     return


    # --- 3. CLEAR COMMANDS ---
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

    # --- 4. STOP WARNING ---
    if stop_warning:
        _write_config(target_path, "suppress_history_warning", True)
        click.echo(f"History size warning disabled in {target_name} config.")
        return

    # --- 5. SHELL SELECTION ---
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
                _write_config(target_path, "history_file", str(selected_path))
                click.echo(f"Updated {target_name} configuration. Now using: {selected_path}")
            else:
                click.echo("Invalid selection.")
        except click.Abort:
            click.echo("\nCancelled.")

    else:
        # If no options matched, show help prompt
        # (Only check this if we haven't already returned from logic above)
        click.echo("Usage: cwm config [OPTIONS]")
        click.echo("Try 'cwm config --help' for details.")