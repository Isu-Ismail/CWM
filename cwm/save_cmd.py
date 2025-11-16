# cwm/save_cmd.py
import re
import json
import os
import click
from pathlib import Path
from datetime import datetime

from .storage_manager import StorageManager

# Allowed variable name
VAR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# var=cmd parser (only allow 0 or 1 space around '=')
VAR_ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s?\=\s?(.+)$", flags=re.DOTALL)


def _now_iso():
    return datetime.utcnow().isoformat()


def _is_cwm_call(s: str) -> bool:
    s = s.strip()
    return s.startswith("cwm ") or s == "cwm"


def _read_powershell_history():
    """Load PSReadLine system history for last executed non-cwm commands."""
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
    lines = _read_powershell_history()
    for line in reversed(lines):
        if not line:
            continue
        if _is_cwm_call(line):
            continue
        return line
    return None


def _last_non_cwm_from_watch_history(manager: StorageManager):
    try:
        hist = manager.load_watch_history()
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
# SAVE COMMAND
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

    Supported:
      cwm save "cmd"
      cwm save var="cmd"
      cwm save -e var="cmd"
      cwm save -ev old new
      cwm save -l
      cwm save -b var
    """

    manager = StorageManager()

    # Normalize payload
    raw = " ".join(payload).strip()

    # ----------------------------------------------------------------------
    # LIST MODE
    # ----------------------------------------------------------------------
    if list_mode:
        if raw:
            click.echo("ERROR: -l does not accept arguments.")
            return
        saved = manager.load_saved_cmds()
        if not saved:
            click.echo("No saved commands found.")
            return

        click.echo("Saved commands:")
        for item in saved:
            sid = item.get("id")
            var = item.get("var") or "(raw)"
            cmd = item.get("cmd")
            fav = "* " if item.get("fav") else ""
            click.echo(f"[{sid}] {fav}{var} -- {cmd}")

        return

    # ----------------------------------------------------------------------
    # EDIT VARIABLE NAME
    # ----------------------------------------------------------------------
    if edit_varname:
        parts = raw.split()

        if len(parts) != 2:
            click.echo("ERROR: -ev requires exactly 2 arguments: old new")
            return

        old, new = parts

        if not VAR_NAME_RE.match(old) or not VAR_NAME_RE.match(new):
            click.echo("ERROR: Invalid variable name.")
            return

        saved = manager.load_saved_cmds()
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
        manager.save_saved_cmds(saved)

        click.echo(f"Renamed var '{old}' to '{new}'")
        return

    # ----------------------------------------------------------------------
    # EDIT VALUE OF EXISTING VARIABLE
    # ----------------------------------------------------------------------
    if edit_value:
        if not raw:
            click.echo("ERROR: -e requires var=cmd format.")
            return

        match = VAR_ASSIGN_RE.match(raw)
        if not match:
            click.echo("ERROR: Invalid var=cmd syntax.")
            return

        varname = match.group(1).strip()
        cmdtext = match.group(2).strip()

        saved = manager.load_saved_cmds()
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
        manager.save_saved_cmds(saved)
        click.echo(f"Updated var '{varname}' to cmd {cmdtext}")
        return

    # ----------------------------------------------------------------------
    # SAVE FROM HISTORY (-b)
    # ----------------------------------------------------------------------
    if save_before:
        if not raw:
            click.echo("ERROR: -b requires a variable name.")
            return

        varname = raw.strip()
        if not VAR_NAME_RE.match(varname):
            click.echo("ERROR: Invalid variable name.")
            return

        # Try watch history first
        cmd_to_save = _last_non_cwm_from_watch_history(manager)

        # If not found, try system history
        if not cmd_to_save:
            cmd_to_save = _last_non_cwm_from_system_history()

        if not cmd_to_save:
            click.echo("ERROR: No usable history command found.")
            return

        saved = manager.load_saved_cmds()

        for item in saved:
            if item.get("var") == varname:
                click.echo(f"ERROR: Variable '{varname}' already exists.")
                return

        new_id = manager.next_saved_id()

        entry = {
            "id": new_id,
            "type": "var_cmd",
            "var": varname,
            "cmd": cmd_to_save,
            "tags": [],
            "fav": False,
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        }

        saved.append(entry)
        manager.save_saved_cmds(saved)

        click.echo(f"Saved history command as '{varname}': {cmd_to_save}")
        return

    # ----------------------------------------------------------------------
    # NO FLAGS → NORMAL SAVE
    # ----------------------------------------------------------------------
    if not raw:
        click.echo("ERROR: No command provided.")
        return

    match = VAR_ASSIGN_RE.match(raw)

    # ----------------------------------------------------------
    # CASE 1: var=cmd
    # ----------------------------------------------------------
    if match:
        varname = match.group(1).strip()
        cmdtext = match.group(2).strip()

        if not VAR_NAME_RE.match(varname):
            click.echo("ERROR: Invalid variable name.")
            return

        saved = manager.load_saved_cmds()

        for item in saved:
            if item.get("var") == varname:
                click.echo(f"ERROR: Variable '{varname}' already exists. Use -e to modify.")
                return

        new_id = manager.next_saved_id()

        entry = {
            "id": new_id,
            "type": "var_cmd",
            "var": varname,
            "cmd": cmdtext,
            "tags": [],
            "fav": False,
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        }

        saved.append(entry)
        manager.save_saved_cmds(saved)

        click.echo(f"Saved variable '{varname}' --> {cmdtext}")
        return

    # ----------------------------------------------------------
    # CASE 2: raw command save
    # ----------------------------------------------------------
    cmdtext = raw

    saved = manager.load_saved_cmds()

    for item in saved:
        if item.get("type") == "raw_cmd" and item.get("cmd") == cmdtext:
            click.echo("ERROR: This command is already saved.")
            return

    new_id = manager.next_saved_id()

    entry = {
        "id": new_id,
        "type": "raw_cmd",
        "var": None,
        "cmd": cmdtext,
        "tags": [],
        "fav": False,
        "created_at": _now_iso(),
        "updated_at": _now_iso()
    }

    saved.append(entry)
    manager.save_saved_cmds(saved)

    click.echo(f"Saved raw command [{new_id}] --> {cmdtext}")
