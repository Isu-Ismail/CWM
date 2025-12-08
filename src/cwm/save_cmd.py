import re
import click
from datetime import datetime, timezone

# Rich Imports
from rich.console import Console
from rich.table import Table
from rich import box


from .storage_manager import StorageManager
from .utils import (
    read_powershell_history, 
    is_cwm_call, 
)
from .rich_help import RichHelpCommand

# Initialize Console
console = Console()

VAR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VAR_ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s?\=\s?(.+)$", flags=re.DOTALL)



# =========================================================
# HELPERS (Unchanged)
# =========================================================
def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _last_non_cwm_from_system_history():
    lines, _ = read_powershell_history() 
    for line in reversed(lines):
        if not line: continue
        if is_cwm_call(line): continue
        return line
    return None

# =========================================================
# HANDLERS (Unchanged - Keeping your previous logic)
# =========================================================

def _handle_list_mode(manager: StorageManager, raw_payload: str):
    if raw_payload: 
        raise click.UsageError("The -l flag does not accept arguments.")
    
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", []) 
    
    if not saved:
        console.print("\n  [yellow]! No saved commands found.[/yellow]\n")
        return

    # Modern Table
    table = Table(title="Saved Commands", box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("ID", justify="right", style="dim", width=4)
    table.add_column("Variable", style="bold cyan")
    table.add_column("Command", style="white")
    table.add_column("Fav", justify="center", style="yellow")

    for item in saved:
        sid = str(item.get("id"))
        var = item.get("var") or "[dim](raw)[/dim]"
        cmd = item.get("cmd")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        fav = "★" if item.get("fav") else ""
        table.add_row(sid, var, cmd, fav)

    console.print("")
    console.print(table)
    console.print(f"  [dim]Total: {len(saved)} | Last ID: {data_obj.get('last_saved_id', 0)}[/dim]\n")


def _handle_rename_variable(manager: StorageManager, raw_payload: str):
    parts = raw_payload.split()
    if len(parts) != 2: 
        raise click.UsageError("The -ev flag requires exactly 2 arguments: old_var new_var")
    
    old, new = parts
    if not VAR_NAME_RE.match(old) or not VAR_NAME_RE.match(new): 
        console.print("  [red]✖ Error: Invalid variable name.[/red]")
        return
        
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    found = None
    for item in saved:
        if item.get("var") == old:
            found = item
            break
            
    if not found:
        console.print(f"  [red]✖ Error: Variable '{old}' not found.[/red]")
        return
        
    for item in saved:
        if item.get("var") == new:
            console.print(f"  [red]✖ Error: Variable '{new}' already exists.[/red]")
            return
            
    found["var"] = new
    found["updated_at"] = _now_iso()
    manager.save_saved_cmds(data_obj) 
    console.print(f"\n  [green]✔ Renamed variable[/green] [dim]{old}[/dim] → [bold cyan]{new}[/bold cyan]\n")


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
        console.print(f"  [red]✖ Error: Variable '{varname}' not found.[/red]")
        return
    found["cmd"] = cmdtext
    found["updated_at"] = _now_iso()
    manager.save_saved_cmds(data_obj) 
    console.print(f"\n  [green]✔ Updated variable:[/green] [bold cyan]{varname}[/bold cyan]")
    console.print(f"  [dim]New Value:[/dim] \"{cmdtext}\"\n")


def _handle_save_from_history(manager: StorageManager, raw_payload: str):
    if not raw_payload: raise click.UsageError("The -b flag requires a variable name.")
    varname = raw_payload.strip()
    if not VAR_NAME_RE.match(varname): 
        console.print("  [red]✖ Error: Invalid variable name.[/red]")
        return
    cmd_to_save = _last_non_cwm_from_system_history()
    if not cmd_to_save:
        console.print("  [yellow]! No usable history command found.[/yellow]")
        return
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    for item in saved:
        if item.get("var") == varname:
            console.print(f"  [red]✖ Error: Variable '{varname}' already exists.[/red]")
            return
    new_id = data_obj.get("last_saved_id", 0) + 1
    data_obj["last_saved_id"] = new_id
    entry = { "id": new_id, "type": "var_cmd", "var": varname, "cmd": cmd_to_save, "tags": [], "fav": False, "created_at": _now_iso(), "updated_at": _now_iso() }
    saved.append(entry)
    manager.save_saved_cmds(data_obj) 
    console.print(f"\n  [green]✔ Captured history command as:[/green] [bold cyan]{varname}[/bold cyan]")
    console.print(f"  [dim]Value:[/dim] \"{cmd_to_save}\"\n")


def _handle_normal_save(manager: StorageManager, raw_payload: str):
    if not raw_payload: raise click.UsageError("No command provided.")
    match = VAR_ASSIGN_RE.match(raw_payload)
    data_obj = manager.load_saved_cmds()
    saved = data_obj.get("commands", [])
    
    if match:
        varname = match.group(1).strip()
        cmdtext = match.group(2).strip()
        if not VAR_NAME_RE.match(varname):
            console.print("  [red]✖ Error: Invalid variable name.[/red]")
            return
        for item in saved:
            if item.get("var") == varname:
                console.print(f"  [red]✖ Error: Variable '{varname}' already exists.[/red] [dim](Use -e to edit)[/dim]")
                return
        new_id = data_obj.get("last_saved_id", 0) + 1
        data_obj["last_saved_id"] = new_id
        entry = { "id": new_id, "type": "var_cmd", "var": varname, "cmd": cmdtext, "tags": [], "fav": False, "created_at": _now_iso(), "updated_at": _now_iso() }
        saved.append(entry)
        manager.save_saved_cmds(data_obj) 
        console.print(f"\n  [green]✔ Saved variable:[/green] [bold cyan]{varname}[/bold cyan]")
        console.print(f"  [dim]Value:[/dim] \"{cmdtext}\"")
        console.print(f"\n  [dim]Tip: Run it with[/dim] [white]cwm get {varname}[/white]\n")
    else:
        cmdtext = raw_payload
        for item in saved:
            if item.get("type") == "raw_cmd" and item.get("cmd") == cmdtext:
                console.print("  [yellow]! This command is already saved.[/yellow]")
                return
        new_id = data_obj.get("last_saved_id", 0) + 1
        data_obj["last_saved_id"] = new_id
        entry = { "id": new_id, "type": "raw_cmd", "var": None, "cmd": cmdtext, "tags": [], "fav": False, "created_at": _now_iso(), "updated_at": _now_iso() }
        saved.append(entry)
        manager.save_saved_cmds(data_obj) 
        console.print(f"\n  [green]✔ Saved raw command #[/green][bold cyan]{new_id}[/bold cyan]")
        console.print(f"  [dim]Value:[/dim] \"{cmdtext}\"\n")


def _handle_save_history(manager: StorageManager, count: str):
    with console.status("[bold cyan]Scanning shell history...[/bold cyan]"):
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
                console.print(f"  [red]✖ Invalid count '{count}'.[/red]")
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
            console.print("  [green]✔ History is already up to date.[/green]")
            return
        hist_obj["commands"] = cached_commands
        hist_obj["last_sync_id"] = last_id
        manager.save_cached_history(hist_obj)
    console.print(f"\n  [green]✔ Sync complete.[/green] Added [bold white]{added_count}[/bold white] new commands to cache.\n")


# =========================================================
# MAIN COMMAND (Using Custom Help Class)
# =========================================================
@click.command("save", cls=RichHelpCommand)
@click.option("-e", "edit_value", is_flag=True, default=False, help="Edit variable")
@click.option("-ev", "edit_varname", is_flag=True, default=False, help="Rename variable")
@click.option("-l", "list_mode", is_flag=True, default=False, help="List saved")
@click.option("-b", "save_before", is_flag=True, default=False, help="Save from history")
@click.option("--hist", "save_history_flag", is_flag=True, default=False, help="Cache history")
@click.option("-n", "count", default="all", help="[History] Limit count")
@click.argument("payload", nargs=-1)
def save_command(edit_value, edit_varname, list_mode, save_before, save_history_flag, count,  payload):
    """
    Save commands or manage history archives.
    """
    manager = StorageManager()
    raw = " ".join(payload).strip()
    
    active_flags = [
        name for name, active in {
            "-e": edit_value, "-ev": edit_varname, "-l": list_mode,
            "-b": save_before, "--hist": save_history_flag,
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
        else: _handle_normal_save(manager, raw)
    except Exception as e:
        console.print(f"  [red]✖ Unexpected error:[/red] {e}")