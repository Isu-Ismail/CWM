# cwm/save_cmd.py
import re
import json
import os
import click
from pathlib import Path
from datetime import datetime
from .storage_manager import StorageManager

# (Regex and helper functions _now_iso, _is_cwm_call, etc. are unchanged)
VAR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VAR_ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s?\=\s?(.+)$", flags=re.DOTALL)

def _now_iso():
    return datetime.utcnow().isoformat()

def _is_cwm_call(s: str) -> bool:
    s = s.strip()
    return s.startswith("cwm ") or s == "cwm"

def _read_powershell_history():
    # ... (unchanged) ...
    results = []
    appdata = os.getenv("APPDATA")
    home = Path.home()
    candidates = [
        Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        Path(appdata) / "Microsoft" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        home / "AppData" / "Roaming" / "Microsoft" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
    ]
    for path in candidates:
        try:
            if path.exists():
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                results = [ln.rstrip("\n") for ln in lines]
                break
        except:
            continue
    return results

def _last_non_cwm_from_system_history():
    # ... (unchanged) ...
    lines = _read_powershell_history()
    for line in reversed(lines):
        if not line:
            continue
        if _is_cwm_call(line):
            continue
        return line
    return None

def _last_non_cwm_from_watch_history(manager: StorageManager):
    # ... (unchanged, but now loads a document) ...
    try:
        hist_doc = manager.load_watch_history()
        hist = hist_doc.get("history", [])
    except:
        return None
    if not hist:
        return None
    for record in reversed(hist):
        cmd = record.get("cmd")
        if not cmd:
            continue
        if _is_cwm_call(cmd):
            continue
        return cmd
    return None


# ============================================================================
# STRATEGY HANDLERS (REFACTORED for new data structure)
# ============================================================================

def _handle_list_mode(manager: StorageManager, raw_payload: str):
    """Handles the cwm save -l command."""
    if raw_payload:
        raise click.UsageError("The -l flag does not accept arguments.")
        
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", []) # Get the list from the object
    
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
    manager.save_saved_cmds(data_obj) # Save the whole object back
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
    manager.save_saved_cmds(data_obj) # Save the whole object
    click.echo(f"Updated var '{varname}' to cmd {cmdtext}")


def _handle_save_from_history(manager: StorageManager, raw_payload: str):
    """Handles the cwm save -b var command."""
    if not raw_payload:
        raise click.UsageError("The -b flag requires a variable name.")

    varname = raw_payload.strip()
    if not VAR_NAME_RE.match(varname):
        raise click.UsageError("Invalid variable name. Use only letters, numbers, _, and -.")

    cmd_to_save = _last_non_cwm_from_watch_history(manager)
    if not cmd_to_save:
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

    # --- NEW ID LOGIC ---
    new_id = data_obj.get("last_saved_id", 0) + 1
    data_obj["last_saved_id"] = new_id
    
    entry = {
        "id": new_id, "type": "var_cmd", "var": varname,
        "cmd": cmd_to_save, "tags": [], "fav": False,
        "created_at": _now_iso(), "updated_at": _now_iso()
    }
    saved.append(entry)
    manager.save_saved_cmds(data_obj) # Save the whole object
    click.echo(f"Saved history command as '{varname}': {cmd_to_save}")


def _handle_normal_save(manager: StorageManager, raw_payload: str):
    """Handles standard 'cwm save cmd' or 'cwm save var=cmd'."""
    if not raw_payload:
        raise click.UsageError("No command provided. Use 'cwm save --help' for options.")

    match = VAR_ASSIGN_RE.match(raw_payload)
    
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])

    # CASE 1: var=cmd
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
        
        # --- NEW ID LOGIC ---
        new_id = data_obj.get("last_saved_id", 0) + 1
        data_obj["last_saved_id"] = new_id

        entry = {
            "id": new_id, "type": "var_cmd", "var": varname,
            "cmd": cmdtext, "tags": [], "fav": False,
            "created_at": _now_iso(), "updated_at": _now_iso()
        }
        saved.append(entry)
        manager.save_saved_cmds(data_obj) # Save the whole object
        click.echo(f"Saved variable '{varname}' --> {cmdtext}")

    # CASE 2: raw command save
    else:
        cmdtext = raw_payload

        for item in saved:
            if item.get("type") == "raw_cmd" and item.get("cmd") == cmdtext:
                click.echo("ERROR: This command is already saved.")
                return

        # --- NEW ID LOGIC ---
        new_id = data_obj.get("last_saved_id", 0) + 1
        data_obj["last_saved_id"] = new_id

        entry = {
            "id": new_id, "type": "raw_cmd", "var": None,
            "cmd": cmdtext, "tags": [], "fav": False,
            "created_at": _now_iso(), "updated_at": _now_iso()
        }
        saved.append(entry)
        manager.save_saved_cmds(data_obj) # Save the whole object
        click.echo(f"Saved raw command [{new_id}] --> {cmdtext}")


# ============================================================================
# SAVE COMMAND (The Dispatcher)
# (This main function is unchanged and remains our clean dispatcher)
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
@click.argument("payload", nargs=-1)
def save_command(edit_value, edit_varname, list_mode, save_before, payload):
    """
    Save commands into the CWM bank.
    Use --help for flag details. Only one flag can be used at a time.
    """

    manager = StorageManager()
    raw = " ".join(payload).strip()
    
    # 1. Mutual Exclusivity Check (Unchanged)
    active_flags = [
        name for name, active in {
            "-e": edit_value,
            "-ev": edit_varname,
            "-l": list_mode,
            "-b": save_before
        }.items() if active
    ]
    
    if len(active_flags) > 1:
        raise click.UsageError(
            f"Only one action flag can be used at a time. Active flags: {', '.join(active_flags)}"
        )

    # 2. Strategy Dispatch (Unchanged)
    try:
        if edit_value:
            _handle_edit_value(manager, raw)
        elif edit_varname:
            _handle_rename_variable(manager, raw)
        elif list_mode:
            _handle_list_mode(manager, raw)
        elif save_before:
            _handle_save_from_history(manager, raw)
        else:
        # 3. Default Strategy: (No flags were used)
            _handle_normal_save(manager, raw)
            
    except Exception as e:
        click.echo(f"An unexpected error occurred: {e}", err=True)