# cwm/save_cmd.py
import re
import json
import click
from pathlib import Path
from datetime import datetime,timezone
from .storage_manager import StorageManager
from .utils import read_powershell_history, is_cwm_call, get_history_line_count, get_clear_history_command

# ... (Regex and _now_iso UNCHANGED) ...
VAR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VAR_ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s?\=\s?(.+)$", flags=re.DOTALL)

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _last_non_cwm_from_system_history():
    lines, _ = read_powershell_history() 
    for line in reversed(lines):
        if not line: continue
        if is_cwm_call(line): continue
        return line
    return None

# ... (Keep _handle_list_mode, _handle_rename_variable, _handle_edit_value, _handle_save_from_history, _handle_normal_save UNCHANGED) ...
def _handle_list_mode(manager: StorageManager, raw_payload: str):
    if raw_payload: raise click.UsageError("The -l flag does not accept arguments.")
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
    parts = raw_payload.split()
    if len(parts) != 2: raise click.UsageError("The -ev flag requires exactly 2 arguments: old_var new_var")
    old, new = parts
    if not VAR_NAME_RE.match(old) or not VAR_NAME_RE.match(new): raise click.UsageError("Invalid variable name.")
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
    if not raw_payload: raise click.UsageError("The -e flag requires var=cmd format.")
    match = VAR_ASSIGN_RE.match(raw_payload)
    if not match: raise click.UsageError("Invalid var=cmd syntax for -e flag.")
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
    if not raw_payload: raise click.UsageError("The -b flag requires a variable name.")
    varname = raw_payload.strip()
    if not VAR_NAME_RE.match(varname): raise click.UsageError("Invalid variable name.")
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
        "id": new_id, "type": "var_cmd", "var": varname, "cmd": cmd_to_save, "tags": [], "fav": False, "created_at": _now_iso(), "updated_at": _now_iso()
    }
    saved.append(entry)
    manager.save_saved_cmds(data_obj) 
    click.echo(f"Saved history command as '{varname}': {cmd_to_save}")

def _handle_normal_save(manager: StorageManager, raw_payload: str):
    if not raw_payload: raise click.UsageError("No command provided. Use 'cwm save --help' for options.")
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
        entry = { "id": new_id, "type": "var_cmd", "var": varname, "cmd": cmdtext, "tags": [], "fav": False, "created_at": _now_iso(), "updated_at": _now_iso() }
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
        entry = { "id": new_id, "type": "raw_cmd", "var": None, "cmd": cmdtext, "tags": [], "fav": False, "created_at": _now_iso(), "updated_at": _now_iso() }
        saved.append(entry)
        manager.save_saved_cmds(data_obj) 
        click.echo(f"Saved raw command [{new_id}] --> {cmdtext}")

def _handle_save_history(manager: StorageManager, count: str):
    """Read PS history and save to CWM cache (Standard Save)."""
    lines, _ = read_powershell_history()
    lines.reverse()
    commands_to_save = []
    seen_live = set()
    for cmd_str in lines:
        if cmd_str and cmd_str not in seen_live:
            if not is_cwm_call(cmd_str):
                commands_to_save.append(cmd_str)
            seen_live.add(cmd_str)
    if count.lower() != "all":
        try:
            num_to_save = int(count)
            if num_to_save > 0: commands_to_save = commands_to_save[:num_to_save]
        except ValueError:
            click.echo(f"Invalid count '{count}'. Aborting.")
            return
    commands_to_save.reverse()
    hist_obj = manager.load_cached_history()
    cached_commands = hist_obj.get("commands", [])
    last_id = hist_obj.get("last_sync_id", 0)
    seen_in_cache = set(item.get("cmd") for item in cached_commands)
    added_count = 0
    for cmd_str in commands_to_save:
        if cmd_str not in seen_in_cache:
            added_count += 1
            last_id += 1
            cached_commands.append({ "id": last_id, "cmd": cmd_str, "timestamp": _now_iso() })
            seen_in_cache.add(cmd_str) 
    if added_count == 0:
        click.echo("History is already up to date.")
        return
    hist_obj["commands"] = cached_commands
    hist_obj["last_sync_id"] = last_id
    manager.save_cached_history(hist_obj)
    click.echo(f"Successfully saved {added_count} new commands to history cache.")

# --- NEW "FILL & SPILL" ARCHIVE LOGIC ---
def _handle_archive_creation(manager: StorageManager):
    """
    Smart Archives: Combines live history with the last ACTIVE archive.
    Fills to 10k, then spills over to a new archive.
    """
    click.echo("Processing Smart Archive...")

    # 1. Load Index & Identify Target
    idx_data = manager.load_archive_index()
    archives = idx_data.get("archives", [])
    
    target_archive = None
    is_new_file = True
    
    # Look for the last archive. Is it active?
    if archives:
        last = archives[-1]
        if last.get("status", "active") == "active":
            target_archive = last
            is_new_file = False
            click.echo(f"Merging into Active Archive ID {last['id']}...")
        else:
            click.echo(f"Last archive (ID {last['id']}) is optimized. Creating new archive...")
    
    # 2. Load Data to Combine
    # A. Existing Archive Data
    existing_lines = []
    if target_archive:
        path = manager.get_archive_path(target_archive['filename'])
        if path.exists():
            existing_lines = path.read_text(encoding="utf-8").splitlines()

    # B. Live History Data
    live_lines, source_count = read_powershell_history()
    
    # 3. Combine & Deduplicate (Preserving Order)
    # Base: Existing Archive -> Append: New unique commands from Live
    
    combined_lines = list(existing_lines) # Start with what we already archived
    seen = set(existing_lines)
    
    new_added = 0
    # Live lines come [oldest ... newest]. We iterate in order.
    for cmd in live_lines:
        if cmd and not is_cwm_call(cmd):
            if cmd not in seen:
                combined_lines.append(cmd)
                seen.add(cmd)
                new_added += 1
                
    click.echo(f"Found {new_added} new unique commands.")
    if new_added == 0 and not is_new_file:
        click.echo("Archive is up to date.")
        return

    # 4. Fill & Spill Logic
    MAX_SIZE = 10000
    
    # We have one giant list `combined_lines`. We need to chop it up.
    # The first chunk updates the `target_archive` (if it existed) or creates the first new one.
    # Subsequent chunks create new archives.
    
    # Determine starting ID
    if target_archive:
        current_id = target_archive['id']
        # Remove the old entry from metadata list so we can re-add it updated
        archives = [a for a in archives if a['id'] != current_id]
    else:
        current_id = idx_data.get("last_archive_id", 0) + 1

    # Slice data into 10k chunks
    chunks = []
    while len(combined_lines) > 0:
        chunk = combined_lines[:MAX_SIZE]
        combined_lines = combined_lines[MAX_SIZE:]
        chunks.append(chunk)

    # 5. Save Files & Update Metadata
    for i, chunk_lines in enumerate(chunks):
        this_id = current_id + i
        
        # Status Logic:
        # If chunk is full (10k) -> Optimized (Locked)
        # If chunk is partial -> Active (Open for next time)
        status = "optimized" if len(chunk_lines) >= MAX_SIZE else "active"
        
        # Write file
        path = manager.create_archive_file(chunk_lines, this_id)
        
        # Add metadata
        archives.append({
            "id": this_id,
            "filename": path.name,
            "timestamp": _now_iso(),
            "count": len(chunk_lines),
            "status": status
        })
        
        # Keep track of max ID
        if this_id > idx_data.get("last_archive_id", 0):
            idx_data["last_archive_id"] = this_id
            
        click.echo(f"-> Wrote Archive {this_id}: {len(chunk_lines)} commands ({status})")

    # 6. Save Index
    idx_data["archives"] = archives
    manager.save_archive_index(idx_data)
    
    # 7. User Instruction
    click.echo("-" * 40)
    clear_cmd = get_clear_history_command()
    if clear_cmd:
        click.echo(click.style("Archive complete! To clear your live history, run:", fg="yellow"))
        click.echo(f"\n    {clear_cmd}\n")
    else:
        click.echo("Archive complete. You can now clear your history file.")

# --- (Dispatcher is UNCHANGED) ---
@click.command("save")
@click.option("-e", "edit_value", is_flag=True, default=False, help="Edit variable")
@click.option("-ev", "edit_varname", is_flag=True, default=False, help="Rename variable")
@click.option("-l", "list_mode", is_flag=True, default=False, help="List saved")
@click.option("-b", "save_before", is_flag=True, default=False, help="Save from history")
@click.option("--hist", "save_history_flag", is_flag=True, default=False, help="Cache history")
@click.option("-n", "count", default="all", help="[History] Limit count")
@click.option("--archive", "archive_flag", is_flag=True, help="Smart Archive: Fill & Spill.")
@click.option("--arch", "arch_alias_flag", is_flag=True, help="Alias for --archive")
@click.argument("payload", nargs=-1)
def save_command(edit_value, edit_varname, list_mode, save_before, save_history_flag, count, archive_flag, arch_alias_flag, payload):
    """
    Save commands or manage history archives.
    """
    manager = StorageManager()
    raw = " ".join(payload).strip()
    
    do_archive = archive_flag or arch_alias_flag

    active_flags = [
        name for name, active in {
            "-e": edit_value, "-ev": edit_varname, "-l": list_mode,
            "-b": save_before, "--hist": save_history_flag, "--archive": do_archive
        }.items() if active
    ]
    
    if len(active_flags) > 1:
        raise click.UsageError(f"Only one action flag allowed. Active: {', '.join(active_flags)}")

    try:
        if edit_value: _handle_edit_value(manager, raw)
        elif edit_varname: _handle_rename_variable(manager, raw)
        elif list_mode: _handle_list_mode(manager, raw)
        elif save_before: _handle_save_from_history(manager, raw)
        elif save_history_flag: _handle_save_history(manager, count)
        elif do_archive: _handle_archive_creation(manager) # <-- CALLS THE NEW LOGIC
        else: _handle_normal_save(manager, raw)
    except Exception as e:
        click.echo(f"An unexpected error occurred: {e}", err=True)

