# cwm/config_cmd.py
import click
import json
from pathlib import Path
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .utils import get_all_history_candidates, find_nearest_bank_path, DEFAULT_CONFIG
from .schema_validator import validate, SCHEMAS
import re

GLOBAL_CONFIG_PATH = GLOBAL_CWM_BANK / "config.json"


# =========================================================
#   VALIDATED CONFIG LOAD/SAVE HELPERS (patched)
# =========================================================

def _load_global_config():
    """Load global config using StorageManager + validator."""
    mgr = StorageManager()
    return mgr._load_json(GLOBAL_CONFIG_PATH, DEFAULT_CONFIG)


def _save_global_config(data: dict):
    """Save global config safely with validation."""
    mgr = StorageManager()
    mgr._save_json(GLOBAL_CONFIG_PATH, data)


def _load_local_config(path: Path):
    """Load local config safely with validation."""
    mgr = StorageManager()
    return mgr._load_json(path, DEFAULT_CONFIG)


def _save_local_config(path: Path, data: dict):
    """Save local config with validation."""
    mgr = StorageManager()
    mgr._save_json(path, data)


# =========================================================
#   GENERIC WRITE HELPERS (patched)
# =========================================================

def _write_config(path: Path, key: str, value):
    """Safe config writer (auto-validate & auto-load)."""
    mgr = StorageManager()
    data = mgr._load_json(path, DEFAULT_CONFIG)
    data[key] = value
    mgr._save_json(path, data)


def _modify_config_list(path: Path, key: str, item: str, action: str):
    """Safe add/remove to list config keys."""
    mgr = StorageManager()
    data = mgr._load_json(path, DEFAULT_CONFIG)

    # Always ensure list type
    current_list = data.get(key, [])
    if not isinstance(current_list, list):
        current_list = []

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
        mgr._save_json(path, data)


def _clear_config(path: Path):
    """Reset config to empty validated object."""
    mgr = StorageManager()
    mgr._save_json(path, {})
    return True


# =========================================================
#   COMMAND LOGIC (unchanged except safe writers)
# =========================================================

@click.command("config")
@click.option("--shell", is_flag=True, help="Select preferred shell history file.")
@click.option("--stop-warning", is_flag=True, help="Disable the large history warning.")
@click.option("--global", "global_mode", is_flag=True, help="Target Global config explicitly.")
@click.option("--clear-local", is_flag=True, help="Reset local configuration.")
@click.option("--clear-global", is_flag=True, help="Reset global configuration.")
@click.option("--show", is_flag=True, help="Show configuration.")
@click.option("--editor", help="Set default editor.")
@click.option("--code-theme", help="Set code syntax highlighting theme (e.g. monokai).")
@click.option("--add-marker", help="Add project detection marker.")
@click.option("--remove-marker", help="Remove project detection marker.")
@click.option("--gemini", is_flag=True, help="Configure Gemini (Interactive).")
@click.option("--openai", is_flag=True, help="Configure OpenAI (Interactive).")
@click.option("--local-ai", is_flag=True, help="Configure Local AI (Interactive).")
@click.option("--instruction", is_flag=True, help="Set System Instruction.")
def config_cmd(shell, stop_warning, global_mode, clear_local, clear_global, show,
               editor, code_theme, add_marker, remove_marker,
               gemini, openai, local_ai, instruction):

    manager = StorageManager()

    # Determine local/global write targets
    local_bank = find_nearest_bank_path(Path.cwd())
    local_config = local_bank / "config.json" if local_bank else None

    target_path = GLOBAL_CONFIG_PATH if global_mode else (local_config or GLOBAL_CONFIG_PATH)
    target_name = "Global" if global_mode else "Active"

    def write_global(key, value):
        _write_config(GLOBAL_CONFIG_PATH, key, value)

    def write_local(key, value):
        if local_config:
            _write_config(local_config, key, value)
        else:
            write_global(key, value)

    # =========================================================
    #                  SHOW CONFIG
    # =========================================================

    if show:
        click.echo("--- CWM Configuration ---")

        if local_bank:
            local_conf = local_bank / "config.json"
            click.echo(f"Local Config:  {local_conf} ({'Exists' if local_conf.exists() else 'Not created'})")
        else:
            click.echo("Local Config:  (No local bank found)")

        click.echo(f"Global Config: {GLOBAL_CONFIG_PATH} ({'Exists' if GLOBAL_CONFIG_PATH.exists() else 'Not created'})")

        config = manager.get_config()

        click.echo(f"\n--- Effective Settings ({target_name}) ---")
        click.echo(f"History File:   {config.get('history_file', 'Auto-Detect')}")
        click.echo(f"Default Editor: {config.get('default_editor', 'code')}")
        click.echo(f"Code Theme:     {config.get('code_theme', 'monokai')}")
        click.echo(f"Markers:        {', '.join(config.get('project_markers', []))}")

        click.echo("\n--- AI Configuration ---")
        def show_key(prefix):
            g = config.get(prefix, {})
            k = g.get("key")
            if k:
                k = f"{k[:4]}...{k[-4:]}"
            click.echo(f"{prefix.capitalize()}: Model='{g.get('model')}', Key='{k}'")

        show_key("gemini")
        show_key("openai")

        l_conf = config.get("local_ai", {})
        click.echo(f"Local:  Model='{l_conf.get('model')}'")

        instr = config.get("ai_instruction")
        if instr:
            preview = instr[:50].replace("\n", " ")
            click.echo(f"Instruction: {preview}...")

        else:
            click.echo("Instruction: (Default)")

        return

    # =========================================================
    #                     AI WIZARDS
    # =========================================================

    if gemini:
        click.echo("--- Configure Gemini ---")
        data = _load_global_config()

        cur = data.get("gemini", {})
        model = click.prompt("Enter Model Name", default=cur.get("model") or "", show_default=False)
        key = click.prompt("Enter API Key", default=cur.get("key") or "", show_default=False)

        data["gemini"]["model"] = model.strip() or None
        data["gemini"]["key"] = key.strip() or None

        _save_global_config(data)
        click.echo("Gemini configuration saved.")
        return

    if openai:
        click.echo("--- Configure OpenAI ---")
        data = _load_global_config()

        cur = data.get("openai", {})
        model = click.prompt("Enter Model Name", default=cur.get("model") or "", show_default=False)
        key = click.prompt("Enter API Key", default=cur.get("key") or "", show_default=False)

        data["openai"]["model"] = model.strip() or None
        data["openai"]["key"] = key.strip() or None

        _save_global_config(data)
        click.echo("OpenAI configuration saved.")
        return

    if local_ai:
        click.echo("--- Configure Local AI ---")
        data = _load_global_config()

        cur = data.get("local_ai", {})
        model = click.prompt("Enter Model Name", default=cur.get("model") or "", show_default=False)
        data["local_ai"]["model"] = model.strip() or None

        _save_global_config(data)
        click.echo("Local AI configuration saved.")
        return

    if instruction:
        click.echo("--- Configure System Instruction ---")
        
        click.echo(
            "Tip: Enter the instruction text directly, or provide an absolute path to a text file (e.g., C:/path/file.txt)."
        )
        
        user_input = click.prompt("Input")

        # Clean quotes immediately so we don't save extra quotes to config
        cleaned_input = user_input.strip().strip('"').strip("'")
        
        path_check = Path(cleaned_input)

        # Check if it is a file, but do NOT read it yet. We only want to save the path.
        if path_check.exists() and path_check.is_file():
            click.echo(f"Valid file path detected: {path_check.name}")
            final_val = cleaned_input
        else:
            # Not a file, treat input as raw instruction text
            final_val = cleaned_input
            
        # Escape backslashes for JSON storage (C:\ becomes C:\\)
        final_val = re.sub(r'\\', r'\\\\', final_val)

        write_global("ai_instruction", final_val)
        click.echo("Instruction updated.")
        return
    # =========================================================
    #                STANDARD GLOBAL SETTINGS
    # =========================================================

    if editor:
        write_global("default_editor", editor)
        click.echo(f"Default editor set to: {editor}")
        return

    if code_theme:
        write_global("code_theme", code_theme)
        click.echo(f"Code theme set to: {code_theme}")
        return

    if add_marker:
        _modify_config_list(GLOBAL_CONFIG_PATH, "project_markers", add_marker, "add")
        return

    if remove_marker:
        _modify_config_list(GLOBAL_CONFIG_PATH, "project_markers", remove_marker, "remove")
        return

    # =========================================================
    #                   LOCAL CONTEXT SETTINGS
    # =========================================================

    if stop_warning:
        write_local("suppress_history_warning", True)
        click.echo(f"History warning disabled in {target_name} config.")
        return

    if shell:
        candidates = get_all_history_candidates()
        if not candidates:
            click.echo("No history files found.")
            return

        click.echo(f"Available History Files ({target_name}):")
        for i, path in enumerate(candidates):
            click.echo(f"  [{i+1}] {path}")

        try:
            selection = click.prompt("Select history file ID", type=int)
            if 1 <= selection <= len(candidates):
                write_local("history_file", str(candidates[selection - 1]))
                click.echo(f"Updated history source: {candidates[selection - 1]}")
            else:
                click.echo("Invalid selection.")
        except click.Abort:
            click.echo("\nCancelled.")
        return

    # =========================================================
    #                        CLEANUP
    # =========================================================

    if clear_local:
        if not local_bank:
            click.echo("Error: No local bank found.")
            return
        _clear_config(local_config)
        click.echo("Local configuration cleared.")
        return

    if clear_global:
        _clear_config(GLOBAL_CONFIG_PATH)
        click.echo("Global configuration cleared.")
        return

    click.echo("Usage: cwm config [OPTIONS]")
    click.echo("Try 'cwm config --help' for details.")
