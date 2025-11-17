# cwm/save_cmd.py
import re
import json
import os
import click
from pathlib import Path
from datetime import datetime
from .storage_manager import StorageManager
from .utils import read_powershell_history, is_cwm_call

# Regex parsers
VAR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VAR_ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s?\=\s?(.+)$", flags=re.DOTALL)

def _now_iso():
    return datetime.utcnow().isoformat()

def _last_non_cwm_from_system_history():
    """Finds the last command from system history that wasn't a cwm call."""
    lines, _ = read_powershell_history() # We only need the lines
    for line in reversed(lines):
        if not line:
            continue
        if is_cwm_call(line):
            continue
        return line
    return None

#
# --- (Obsolete _last_non_cwm_from_watch_history function has been REMOVED) ---
#

# ============================================================================
# STRATEGY HANDLERS
# ============================================================================

def _handle_list_mode(manager: StorageManager, raw_payload: str):
    """Handles the cwm save -l command."""
    if raw_payload:
        raise click.UsageError("The -l flag does not accept arguments.")
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", []) 
    if not saved:
        click.echo("No saved commands found.")
        return
    click.echo(f"Saved commands (Total: {len(saved)}, Last ID: {data_obj.get('last_saved_id', 0)}):")
    for item in saved:
        sid = item.get("id")
        var = item.get("var") or "(raw)"
        cmd = item.get("cmd")
        fav = "* " if item.get("fav") else ""
        click.echo(f"[{sid}] {fav}{var} -- {cmd}")

def _handle_rename_variable(manager: StorageManager, raw_payload: str):
    """Handles the cwm save -ev old new command."""
    parts = raw_payload.split()
    if len(parts) != 2:
        raise click.UsageError("The -ev flag requires exactly 2 arguments: old_var new_var")
    old, new = parts
    if not VAR_NAME_RE.match(old) or not VAR_NAME_RE.match(new):
        raise click.UsageError("Invalid variable name. Use only letters, numbers, _, and -.")
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    found = None
    for item in saved:
        if item.get("var") == old:
            found = item
            break
    if not found:
        click.echo(f"ERROR: Variable '{old}' not found.")
        return
    for item in saved:
        if item.get("var") == new:
            click.echo(f"ERROR: Variable '{new}' already exists.")
            return
    found["var"] = new
    found["updated_at"] = _now_iso()
    manager.save_saved_cmds(data_obj)
    click.echo(f"Renamed var '{old}' to '{new}'")

def _handle_edit_value(manager: StorageManager, raw_payload: str):
    """Handles the cwm save -e var=cmd command."""
    if not raw_payload:
        raise click.UsageError("The -e flag requires var=cmd format.")
    match = VAR_ASSIGN_RE.match(raw_payload)
    if not match:
        raise click.UsageError("Invalid var=cmd syntax for -e flag.")
    varname = match.group(1).strip()
    cmdtext = match.group(2).strip()
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    found = None
    for item in saved:
        if item.get("var") == varname:
            found = item
            break
    if not found:
        click.echo(f"ERROR: Variable '{varname}' not found.")
        return
    found["cmd"] = cmdtext
    found["updated_at"] = _now_iso()
    manager.save_saved_cmds(data_obj)
    click.echo(f"Updated var '{varname}' to cmd {cmdtext}")

def _handle_save_from_history(manager: StorageManager, raw_payload: str):
    """Handles the cwm save -b var command."""
    if not raw_payload:
        raise click.UsageError("The -b flag requires a variable name.")
    varname = raw_payload.strip()
    if not VAR_NAME_RE.match(varname):
        raise click.UsageError("Invalid variable name. Use only letters, numbers, _, and -.")

    # --- THIS IS THE FIX ---
    # We ONLY check the system history.
    cmd_to_save = _last_non_cwm_from_system_history()

    if not cmd_to_save:
        click.echo("ERROR: No usable history command found.")
        return

    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    for item in saved:
        if item.get("var") == varname:
            click.echo(f"ERROR: Variable '{varname}' already exists.")
            return

    new_id = data_obj.get("last_saved_id", 0) + 1
    data_obj["last_saved_id"] = new_id
    entry = {
        "id": new_id, "type": "var_cmd", "var": varname,
        "cmd": cmd_to_save, "tags": [], "fav": False,
        "created_at": _now_iso(), "updated_at": _now_iso()
    }
    saved.append(entry)
    manager.save_saved_cmds(data_obj)
    click.echo(f"Saved history command as '{varname}': {cmd_to_save}")

def _handle_normal_save(manager: StorageManager, raw_payload: str):
    """Handles standard 'cwm save cmd' or 'cwm save var=cmd'."""
    if not raw_payload:
        raise click.UsageError("No command provided. Use 'cwm save --help' for options.")
    match = VAR_ASSIGN_RE.match(raw_payload)
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    if match:
        varname = match.group(1).strip()
        cmdtext = match.group(2).strip()
        if not VAR_NAME_RE.match(varname):
            click.echo("ERROR: Invalid variable name.")
            return
        for item in saved:
            if item.get("var") == varname:
                click.echo(f"ERROR: Variable '{varname}' already exists. Use -e to modify.")
                return
        new_id = data_obj.get("last_saved_id", 0) + 1
        data_obj["last_saved_id"] = new_id
        entry = {
            "id": new_id, "type": "var_cmd", "var": varname,
            "cmd": cmdtext, "tags": [], "fav": False,
            "created_at": _now_iso(), "updated_at": _now_iso()
        }
        saved.append(entry)
        manager.save_saved_cmds(data_obj)
        click.echo(f"Saved variable '{varname}' --> {cmdtext}")
    else:
        cmdtext = raw_payload
        for item in saved:
            if item.get("type") == "raw_cmd" and item.get("cmd") == cmdtext:
                click.echo("ERROR: This command is already saved.")
                return
        new_id = data_obj.get("last_saved_id", 0) + 1
        data_obj["last_saved_id"] = new_id
        entry = {
            "id": new_id, "type": "raw_cmd", "var": None,
            "cmd": cmdtext, "tags": [], "fav": False,
            "created_at": _now_iso(), "updated_at": _now_iso()
        }
        saved.append(entry)
        manager.save_saved_cmds(data_obj)
        click.echo(f"Saved raw command [{new_id}] --> {cmdtext}")

# --- NEW HELPER FUNCTION FOR 'save --hist' ---
def _handle_save_history(manager: StorageManager, count: str):
    """
    Read PowerShell history and save new commands to the CWM cache.
    """
    lines, _ = read_powershell_history()
    lines.reverse() # Newest-first
    
    commands_to_save = []
    seen_live = set()
    for cmd_str in lines:
        if cmd_str and cmd_str not in seen_live:
            if not is_cwm_call(cmd_str): # Exclude cwm calls
                commands_to_save.append(cmd_str)
            seen_live.add(cmd_str)
    
    if count.lower() != "all":
        try:
            num_to_save = int(count)
            if num_to_save > 0:
                commands_to_save = commands_to_save[:num_to_save]
        except ValueError:
            click.echo(f"Invalid count '{count}'. Aborting.")
            return
            
    commands_to_save.reverse() # Save in chronological order

    hist_obj = manager.load_cached_history()
    cached_commands = hist_obj.get("commands", [])
    last_id = hist_obj.get("last_sync_id", 0)
    
    seen_in_cache = set(item.get("cmd") for item in cached_commands)
    
    added_count = 0
    for cmd_str in commands_to_save:
        if cmd_str not in seen_in_cache:
            added_count += 1
            last_id += 1
            cached_commands.append({
                "id": last_id,
                "cmd": cmd_str,
                "timestamp": datetime.utcnow().isoformat()
            })
            seen_in_cache.add(cmd_str) 

    if added_count == 0:
        click.echo("History is already up to date. No new commands added.")
        return

    hist_obj["commands"] = cached_commands
    hist_obj["last_sync_id"] = last_id
    
    manager.save_cached_history(hist_obj)
    click.echo(f"Successfully saved {added_count} new commands to history cache.")

# ============================================================================
@click.command("save")
@click.option("-e", "edit_value", is_flag=True, default=False,
              help="Edit an existing variable's value: cwm save -e var=\"cmd\"")
@click.option("-ev", "edit_varname", is_flag=True, default=False,
              help="Rename a saved variable: cwm save -ev old new")
@click.option("-l", "list_mode", is_flag=True, default=False,
              help="List all saved commands")
@click.option("-b", "save_before", is_flag=True, default=False,
              help="Save the previous history command as a variable: cwm save -b var")
@click.option("--hist", "save_history_flag", is_flag=True, default=False,
              help="Save PowerShell history to CWM cache.")
@click.option("-n", "count", default="all", 
              help="[History] Save only the last N commands or 'all'. [default: all]")
@click.argument("payload", nargs=-1)
def save_command(edit_value, edit_varname, list_mode, save_before, save_history_flag, count, payload):
    """
    Save commands into the CWM bank or save PS history.
    
    Use --help for flag details. Action flags are mutually exclusive.
    """
    manager = StorageManager()
    raw = " ".join(payload).strip()
    
    active_flags = [
        name for name, active in {
            "-e": edit_value,
            "-ev": edit_varname,
            "-l": list_mode,
            "-b": save_before,
            "--hist": save_history_flag
        }.items() if active
    ]
    
    if len(active_flags) > 1:
        raise click.UsageError(
            f"Only one action flag can be used at a time. Active flags: {', '.join(active_flags)}"
        )

    try:
        if edit_value:
            _handle_edit_value(manager, raw)
        elif edit_varname:
            _handle_rename_variable(manager, raw)
        elif list_mode:
            _handle_list_mode(manager, raw)
        elif save_before:
            _handle_save_from_history(manager, raw)
        elif save_history_flag:
            _handle_save_history(manager, count)
        else:
            _handle_normal_save(manager, raw)
            
    except Exception as e:
        click.echo(f"An unexpected error occurred: {e}", err=True)