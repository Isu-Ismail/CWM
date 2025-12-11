import click
import pyperclip
from .storage_manager import StorageManager
from .utils import get_history_file_path, tail_read_last_n_lines, is_cwm_call

from rich.console import Console
from rich.table import Table
from .rich_help import RichHelpCommand

console = Console()

def _get_history_commands(manager: StorageManager, active: bool):
    """
    Returns list of command objects [{"cmd": "..."}].
    """
    if active:
        # 1. Local Project History
        path = manager.get_project_history_path()
        
        if not path:
            console.print("[red]Error: Not in a CWM project (or no local bank found).[/red]")
            return [], None
            
        if not path.exists():
            console.print("[yellow]! Local history file is empty/missing.[/yellow]")
            return [], None

        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            lines = [l for l in lines if l.strip()]
            # Removed the "Loaded X commands" print to save space
            return [{"cmd": line} for line in lines], None
        except Exception as e:
            console.print(f"[red]Error reading local history: {e}[/red]")
            return [], None

    else:
        # 2. System Shell History
        path = get_history_file_path()
        if not path or not path.exists():
            console.print("[yellow]! System history file not detected.[/yellow]")
            return [], None
            
        lines = tail_read_last_n_lines(path, 5000)
        return [{"cmd": line} for line in lines], None


def _apply_robust_filters(commands, filter_str, exclude_str):
    """Applies filters to the command list."""
    filtered_list = list(commands)

    if exclude_str:
        exclusions = [x.strip() for x in exclude_str.split(',') if x.strip()]
        for ex in exclusions:
            filtered_list = [item for item in filtered_list if ex not in item.get("cmd", "")]

    if filter_str:
        filters = [x.strip() for x in filter_str.split(',') if x.strip()]
        for f in filters:
            filtered_list = [
                item for item in filtered_list
                if f in item.get("cmd", "") or f in item.get("var", "")
            ]

    return filtered_list


def _display_table(items, columns, title):
    """Generic Rich Table Display."""
    # FIX: title_justify="left" keeps the title aligned with the content
    table = Table(title=title, title_justify="left", box=None, show_header=True, padding=(0, 2))
    
    for col_name, style, justify in columns:
        table.add_column(col_name, style=style, justify=justify)

    display_map = {}
    
    for i, item in enumerate(items):
        display_num = str(i + 1)
        display_map[display_num] = item.get("cmd", "")
        
        row_data = []
        row_data.append(f"{display_num}")
        
        if len(columns) == 3: 
            var = item.get("var") or "-"
            cmd = item.get("cmd", "").strip()
            row_data.append(var)
            row_data.append(cmd)
        else:
            cmd = item.get("cmd", "").strip()
            row_data.append(cmd)

        table.add_row(*row_data)

    console.print(table)
    console.print("")
    return display_map


def _filter_and_display(commands: list, count: str, exclude: str, filter: str, list_only: bool, mode: str):
    unique_commands = []
    seen = set()
    for item in reversed(commands):
        cmd_str = item.get("cmd")
        if cmd_str and cmd_str not in seen:
            unique_commands.append(item)
            seen.add(cmd_str)
    unique_commands.reverse()

    if mode == "history" and not (filter and "cwm" in filter):
        base_list = [item for item in unique_commands if not is_cwm_call(item.get("cmd", ""))]
    else:
        base_list = unique_commands

    filtered_list = _apply_robust_filters(base_list, filter, exclude)
    total_found = len(filtered_list)

    if total_found == 0:
        console.print("[yellow]No commands found matching criteria.[/yellow]")
        return

    final_list = filtered_list
    if count.lower() != "all":
        try:
            num = int(count)
            if num > 0: final_list = filtered_list[-num:]
        except:
            final_list = filtered_list[-10:]

    if mode == "saved":
        cols = [
            ("ID", "cyan", "right"),
            ("Var", "bold white", "left"),
            ("Command", "green", "left")
        ]
        title = f"Saved Commands ({len(final_list)}/{total_found})"
    else:
        cols = [
            ("ID", "cyan", "right"),
            ("Command", "green", "left")
        ]
        title = f"History ({len(final_list)}/{total_found})"

    display_map = _display_table(final_list, cols, title)

    if list_only:
        return

    try:
        choice = click.prompt("Copy (ID)", default="", show_default=False)
        if not choice: return
        
        if choice in display_map:
            command_to_copy = display_map[choice]
            pyperclip.copy(command_to_copy)
            console.print(f"[bold green]✔ Copied command #{choice}->[/bold green][cyan]{command_to_copy}[/cyan]")
        else:
            console.print("[red]Invalid number.[/red]")
    except:
        console.print("\n[dim]Cancelled.[/dim]")


@click.command("get", cls=RichHelpCommand)
@click.argument("name_or_id", required=False)
@click.option("--id", "id_flag", type=int, help="Get saved command by database ID.")
@click.option("-s", "--show", "show_flag", is_flag=True, help="Show without copying.")
@click.option("-l", "list_mode", is_flag=True, help="List saved commands without prompt.")
@click.option("-h", "--hist", "hist_flag", is_flag=True, help="System History mode.")
@click.option("-a", "--active", "active_flag", is_flag=True, help="Local Project History mode.")
@click.option("-n", "count", default="10", help="Show last N commands.")
@click.option("-ex", "exclude", help="Exclude (comma separated).")
@click.option("-f", "filter", help="Filter (comma separated).")
def get_cmd(name_or_id, id_flag, show_flag, list_mode, 
            hist_flag, active_flag, count, exclude, filter):
    """
    Get saved commands or history.
    """
    manager = StorageManager()

    # --- 1. HISTORY MODES ---
    if hist_flag or active_flag:
        if id_flag or name_or_id or show_flag:
            console.print("[red]Error: Cannot mix history flags with specific ID/Name selection.[/red]")
            return

        commands_list, _ = _get_history_commands(manager, active_flag)
        if not commands_list: return

        _filter_and_display(commands_list, count, exclude, filter, list_mode, mode="history")
        return

    # --- 2. SAVED COMMANDS ---
    data_obj = manager.load_saved_cmds()
    commands = data_obj.get("commands", [])

    if list_mode or (not name_or_id and not id_flag):
        _filter_and_display(commands, count, exclude, filter, list_mode, mode="saved")
        return

    # --- 3. SINGLE FETCH ---
    command_to_get = None

    if id_flag is not None:
        for cmd in commands:
            if cmd.get("id") == id_flag:
                command_to_get = cmd.get("cmd")
                break
    elif name_or_id is not None:
        for cmd in commands:
            if cmd.get("var") == name_or_id:
                command_to_get = cmd.get("cmd")
                break
        
        if not command_to_get and name_or_id.isdigit():
            tid = int(name_or_id)
            for cmd in commands:
                if cmd.get("id") == tid:
                    command_to_get = cmd.get("cmd")
                    break

    if not command_to_get:
        console.print(f"[red]Error: Command '{name_or_id or id_flag}' not found.[/red]")
        return

    if show_flag:
        console.print(command_to_get)
    else:
        pyperclip.copy(command_to_get)
        console.print(f"[bold green]✔ Copied to clipboard![/bold green]->[cyan]{command_to_get}[/cyan]")