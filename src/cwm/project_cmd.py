import click
import platform
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.prompt import IntPrompt
from .storage_manager import StorageManager
from .utils import is_safe_startup_cmd, clean_token

console = Console()




def _shorten_path(full_path: str) -> Text:
    """Shortens path for display (e.g. ~/dev/project)."""
    p = Path(full_path)
    try:
        home_dir = Path.home()
        relative_path = p.relative_to(home_dir)
        parts = relative_path.parts
        if len(parts) > 2:
            display_path = Path("~") / Path(*parts[-2:])
        elif len(parts) > 0:
             display_path = Path("~") / relative_path
        else:
             display_path = p
    except ValueError:
        display_path = p
        
    link_target = f"file://{p.resolve()}"
    return Text(str(display_path), style=f"link {link_target}")

def _format_startup_cmds(value) -> str:
    """Formats startup command list for table display."""
    cmds = _startup_to_list(value)
    if not cmds:
        return "[dim](none)[/dim]"
    if len(cmds) > 2:
        return f"[yellow]{cmds[0]}[/yellow], [yellow]{cmds[1]}[/yellow] [dim](+{len(cmds) - 2} more)[/dim]"
    return " / ".join(f"[yellow]{c}[/yellow]" for c in cmds)

def _startup_to_list(value):
    if value is None: return []
    if isinstance(value, str):
        val = value.strip()
        return [val] if val else []
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return []

def _startup_collapse(values: list[str]):
    clean = [v.strip() for v in values if v.strip()]
    if not clean: return None
    if len(clean) == 1: return clean[0]
    return clean

def _get_unique_alias(base_name: str, existing_projects: list) -> str:
    existing_aliases = {p["alias"] for p in existing_projects}
    if base_name not in existing_aliases:
        return base_name
    count = 2
    new_name = f"{base_name}-{count}"
    while new_name in existing_aliases:
        count += 1
        new_name = f"{base_name}-{count}"
    return new_name

def _prompt_project_details(target_path, projects_list, default_alias=None, pre_startup=None):
    """
    Shared logic to ask for Alias and Startup Commands.
    """
    if not default_alias:
        default_alias = _get_unique_alias(target_path.name, projects_list)

    alias = click.prompt("Enter Project Alias", default=default_alias)
    alias = _get_unique_alias(alias, projects_list)

    startup_value = None

    if pre_startup:
        raw_input = pre_startup
    else:
        raw_input = click.prompt(
            "Enter startup command(s) (comma-separated) or blank",
            default="",
            show_default=False,
        ).strip()

    if raw_input:
        # FIX: Clean tokens here to remove quotes
        tokens = [clean_token(t) for t in raw_input.split(",") if t.strip()]
        
        safe_cmds = []
        for cmd in tokens:
            if not cmd: continue
            
            if not is_safe_startup_cmd(cmd, target_path):
                console.print(f"[red]⚠ Unsafe startup command blocked: {cmd}[/red]")
                return None, None 

            if cmd not in safe_cmds:
                safe_cmds.append(cmd)

        startup_value = _startup_collapse(safe_cmds)

    return alias, startup_value


# --- COMMANDS ---

@click.group("project")
def project_cmd():
    """Manage workspace projects."""
    pass

@project_cmd.command("scan")
@click.option("--root", help="Specific folder to scan (defaults to User Home).")
def scan_projects(root):
    from .project_utils import ProjectScanner
    import time
    
    start_path = Path(root).resolve() if root else Path.home()
    manager = StorageManager()
    data = manager.load_projects()

    existing_paths = {p["path"] for p in data.get("projects", [])}
    current_projects = data.get("projects", [])
    last_id = data.get("last_id", 0)

    scanner = ProjectScanner(start_path)
    found_candidates = []

    start_time = time.perf_counter()

    with console.status("[bold cyan]Scanning folders...", spinner="dots") as status:
        for proj_path in scanner.scan_generator():
            status.update(f"[bold cyan]Scanning... ({scanner.scanned_count} checked)[/bold cyan]")
            if str(proj_path) in existing_paths:
                continue
            found_candidates.append(proj_path)

    end_time = time.perf_counter()
    duration = end_time - start_time

    console.print(f"\n[dim]Scan Summary: Checked {scanner.scanned_count} folders in {duration:.2f} seconds.[/dim]")

    if not found_candidates:
        console.print("[yellow]Scan complete. No new projects found.[/yellow]")
        return

    console.print(f"[bold green]✔ Found {len(found_candidates)} candidates.[/bold green]")

    added_count = 0

    for p in found_candidates:
        rel_path = p.relative_to(start_path)
        console.print(f"\nCandidate: [bold cyan]{rel_path}[/bold cyan]")

        action = click.prompt(
            "Add project? [y]es, [n]o (ignore), [s]kip",
            type=click.Choice(["y", "n", "s"]),
            default="y",
            show_default=False,
        )

        if action == "s": continue
        if action == "n":
            scanner.add_to_ignore(str(rel_path))
            console.print(f"[dim]-> Added {rel_path} to ignore list.[/dim]")
            continue

        if action == "y":
            alias, startup_cmd = _prompt_project_details(p, current_projects)

            if alias is None:
                console.print("[yellow]Skipping due to validation error.[/yellow]")
                continue

            last_id += 1
            current_projects.append({
                "id": last_id,
                "alias": alias,
                "path": str(p),
                "hits": 0,
                "startup_cmd": startup_cmd,
                "group": None
            })
            added_count += 1
            console.print(f"[green]-> Saved as '{alias}'[/green]")

    if added_count > 0:
        data["projects"] = current_projects
        data["last_id"] = last_id
        manager.save_projects(data)
        console.print(f"\n[bold green]Saved {added_count} new projects![/bold green]")
    else:
        console.print("\n[dim]No projects added.[/dim]")


@project_cmd.command("add")
@click.argument("path", required=False)
@click.option("-n", "--name", help="Alias for the project.")
@click.option("-s", "--startup", help="Startup command(s).")
def add_project(path, name, startup):
    """Manually add a project folder."""
    manager = StorageManager()

    if not path:
        path = click.prompt("Enter Project Path").strip()

    target = Path.cwd().resolve() if path == "." else Path(path).resolve()

    if not target.exists() or not target.is_dir():
        console.print(f"[red]Error: Invalid directory '{path}'.[/red]")
        return

    data = manager.load_projects()
    projects = data.get("projects", [])

    if any(p["path"] == str(target) for p in projects):
        console.print("[yellow]This path is already saved.[/yellow]")
        return

    alias, startup_cmd = _prompt_project_details(
        target,
        projects,
        default_alias=name,
        pre_startup=startup
    )

    if alias is None: return 

    last_id = data.get("last_id", 0) + 1

    projects.append({
        "id": last_id,
        "alias": alias,
        "path": str(target),
        "hits": 0,
        "startup_cmd": startup_cmd,
        "group": None
    })

    data["projects"] = projects
    data["last_id"] = last_id
    manager.save_projects(data)

    console.print(f"[green]Added project '{alias}' → {target}[/green]")


@project_cmd.command("list")
def list_projects():
    """List all saved projects."""
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])
    groups = data.get("groups", [])
    
    group_map = {g['id']: g['alias'] for g in groups}

    if not projects:
        console.print("[dim]No projects saved.[/dim]")
        return

    console.print(f"\n[bold green]📦 Saved Projects ({len(projects)})[/bold green]")

    sorted_projs = sorted(projects, key=lambda x: x["id"])

    table = Table(
        box=None, 
        show_header=True, 
        padding=(0, 2),
        title_style="bold magenta",
        header_style="bold cyan"
    )
    
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Alias", style="bold white")
    table.add_column("Path", style="dim")
    table.add_column("Group", justify="center")
    table.add_column("Startup Cmds", justify="left")
    table.add_column("Hits", style="dim", justify="right")

    for p in sorted_projs:
        group_id = p.get("group")
        group_alias = group_map.get(group_id, "[dim]-[/dim]")
        path_text = _shorten_path(p['path'])
        startup_text = _format_startup_cmds(p.get('startup_cmd'))

        table.add_row(
            str(p['id']),
            p['alias'],
            path_text,
            group_alias,
            startup_text,
            str(p.get('hits', 0))
        )

    console.print(table)
    console.print("")


@project_cmd.command("remove")
@click.argument("target", required=False)
@click.option("-n", "count", default="10", help="Number of candidates to show.")
def remove_project(target, count):
    """
    Remove a saved project.
    Re-indexes IDs automatically to close gaps.
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])
    groups = data.get("groups", [])
    last_group_id = data.get("last_group_id", 0)

    if not projects:
        console.print("[dim]No projects to remove.[/dim]")
        return

    removed_something = False

    # --- DIRECT REMOVE ---
    if target:
        found_idx = -1
        if target.isdigit():
            tid = int(target)
            for i, p in enumerate(projects):
                if p["id"] == tid:
                    found_idx = i
                    break
        else:
            for i, p in enumerate(projects):
                if p["alias"] == target:
                    found_idx = i
                    break

        if found_idx != -1:
            removed = projects.pop(found_idx)
            console.print(f"[green]Removed project: {removed['alias']}[/green]")
            removed_something = True
        else:
            console.print(f"[red]Project '{target}' not found.[/red]")
            return

    # --- INTERACTIVE REMOVE ---
    else:
        # Sort by hits (least used first usually, or just ID)
        sorted_projs = sorted(projects, key=lambda x: (x.get("hits", 0), x["alias"]))
        
        limit = 10
        if str(count).lower() == "all": limit = len(projects)
        else:
            try: limit = int(count)
            except: pass
            
        display_list = sorted_projs[:limit]
        
        console.print("\n[bold]Select Projects to Remove[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        for p in display_list:
            table.add_row(f"[cyan][{p['id']}][/cyan]", f"{p['alias']}", f"[dim]{p['path']}[/dim]")
        
        console.print(table)
        console.print("")

        choice = click.prompt("\nEnter IDs/Aliases to REMOVE (comma-separated)", default="", show_default=False)
        if not choice: return

        tokens = choice.split(",")
        to_remove_indexes = []

        for token in tokens:
            token = token.strip()
            idx = -1
            if token.isdigit():
                tid = int(token)
                for i, p in enumerate(projects):
                    if p["id"] == tid:
                        idx = i
                        break
            else:
                for i, p in enumerate(projects):
                    if p["alias"] == token:
                        idx = i
                        break
            
            if idx != -1 and idx not in to_remove_indexes:
                to_remove_indexes.append(idx)

        if not to_remove_indexes: return

        to_remove_indexes.sort(reverse=True)
        count_removed = 0
        removed_ids = set()
        
        for idx in to_remove_indexes:
            removed = projects.pop(idx)
            removed_ids.add(removed["id"])
            console.print(f"[dim]Removed: {removed['alias']}[/dim]")
            count_removed += 1

        # Clean groups
        for g in groups:
            # Handle new group structure (list of dicts)
            new_list = []
            for item in g.get("project_list", []):
                pid = item.get("id") if isinstance(item, dict) else item
                if pid not in removed_ids:
                    new_list.append(item)
            g["project_list"] = new_list

        console.print(f"[green]Successfully removed {count_removed} projects.[/green]")
        removed_something = True

    if removed_something:
        console.print("[dim]Re-indexing project IDs...[/dim]")
        projects.sort(key=lambda x: x["id"])
        
        id_mapping = {}
        for index, p in enumerate(projects):
            old_id = p["id"]
            new_id = index + 1
            p["id"] = new_id
            id_mapping[old_id] = new_id

        data["last_id"] = len(projects)

        # Update groups with new IDs
        for g in groups:
            new_list = []
            for item in g.get("project_list", []):
                if isinstance(item, dict):
                    old_pid = item.get("id")
                    if old_pid in id_mapping:
                        item["id"] = id_mapping[old_pid]
                        new_list.append(item)
                else: # Legacy int
                    if item in id_mapping:
                        new_list.append(id_mapping[item])
            g["project_list"] = new_list

        data["groups"] = groups
        data["last_group_id"] = last_group_id
        data["projects"] = projects
        manager.save_projects(data)
        console.print("[dim]Done.[/dim]")


@project_cmd.command("edit")
@click.option("-id", "project_id", type=int, help="Project ID to edit.")
@click.option("-n", "--name", "new_alias", help="New alias for the project.")
@click.option("-p", "--path", "new_path", help="New path for the project.")
@click.option("-a", "--add", "add_cmds", multiple=True, help="Add startup command.")
@click.option("-r", "--remove", "remove_cmds", multiple=True, help="Remove startup command.")
def edit_project(project_id, new_alias, new_path, add_cmds, remove_cmds):
    """
    Edit a project's alias, path, and startup commands.
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])
    groups = data.get("groups", [])
    
    group_map = {g['id']: g['alias'] for g in groups}

    if not projects:
        console.print("[dim]No projects saved.[/dim]")
        return

    # --- WIZARD: SELECT PROJECT ---
    if project_id is None:
        console.print("\n[bold]Select Project to Edit[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column(style="bold white")
        table.add_column(style="dim")
        
        for p in sorted(projects, key=lambda x: x["id"]):
            hits_label = f"(Hits: {p.get('hits', 0)})"
            table.add_row(f"[{p['id']}]", p['alias'], hits_label)
            
        console.print(table)
        try:
            project_id = IntPrompt.ask("\n  [bold cyan]?[/bold cyan] Enter Project ID")
        except: return

    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        console.print(f"[red]Project {project_id} not found.[/red]")
        return

    # --- POWER MODE LOGIC ---
    project_root = Path(proj["path"]).resolve()
    startup_list = _startup_to_list(proj.get("startup_cmd"))

    if new_alias or new_path or add_cmds or remove_cmds:
        if new_alias:
            alias = new_alias.strip()
            if not alias: return
            if any(p["alias"] == alias and p["id"] != project_id for p in projects):
                console.print(f"[red]Alias '{alias}' already exists.[/red]")
                return
            proj["alias"] = alias

        if new_path:
            # FIX: Clean quotes from path
            cleaned = clean_token(new_path)
            resolved = Path(cleaned).resolve()
            if not resolved.exists() or not resolved.is_dir():
                console.print(f"[red]Invalid directory: {cleaned}[/red]")
                return
            proj["path"] = str(resolved)
            project_root = resolved

        current = list(startup_list)

        for cmd in add_cmds:
            # FIX: Clean quotes
            c = clean_token(cmd)
            if not c: continue
            if not is_safe_startup_cmd(c, project_root):
                console.print(f"[red]Unsafe startup command blocked: {c}[/red]")
                return
            if c not in current:
                current.append(c)

        for cmd in remove_cmds:
            c = clean_token(cmd)
            if c in current:
                current.remove(c)

        proj["startup_cmd"] = _startup_collapse(current)
        manager.save_projects(data)
        console.print(f"\n[green]✔ Project {proj['alias']} updated.[/green]")
        return

    # --- WIZARD MODE ---
    console.print(f"\n[bold yellow]--- Editing Project ID {project_id} ({proj['alias']}) ---[/bold yellow]")
    
    status_table = Table(box=None, show_header=False, padding=(0, 2))
    status_table.add_column("Key", style="bold white")
    status_table.add_column("Value")

    # Path
    current_path_text = _shorten_path(proj['path'])
    
    # Startup Commands
    cmds = _startup_to_list(proj.get("startup_cmd"))
    if cmds:
        markup_str = "\n".join([f"[dim]- {c}[/dim]" for c in cmds])
        cmd_display = Text.from_markup(markup_str)
    else:
        cmd_display = Text.from_markup("[dim](none)[/dim]")

    status_table.add_row("Alias:", f"[yellow]{proj['alias']}[/yellow]")
    status_table.add_row("Path:", current_path_text)
    status_table.add_row("Group:", group_map.get(proj.get('group'), "[dim]-[/dim]"))
    status_table.add_row("Startup Cmds:", cmd_display)
    
    console.print(status_table)

    # 1. Alias Prompt
    new_alias_wiz = click.prompt("\nNew Alias", default=proj["alias"]).strip()
    if new_alias_wiz != proj["alias"]:
        if any(p["alias"] == new_alias_wiz and p["id"] != project_id for p in projects):
            console.print(f"[red]Alias '{new_alias_wiz}' already exists.[/red]")
            return
        proj["alias"] = new_alias_wiz

    # 2. Path Prompt
    new_path_wiz = click.prompt("New Path", default=proj["path"]).strip()
    # FIX: Clean quotes
    new_path_wiz = clean_token(new_path_wiz)
    
    if new_path_wiz != proj["path"]:
        resolved = Path(new_path_wiz).resolve()
        if not resolved.exists() or not resolved.is_dir():
            console.print("[red]Invalid directory.[/red]")
            return
        proj["path"] = str(resolved)
        project_root = resolved

    # 3. Startup Command Prompt
    sc_input = click.prompt(
        "Startup commands (comma-separated) or Enter to keep",
        default="",
        show_default=False,
    ).strip()

    if sc_input:
        # FIX: Clean tokens (quotes) here too
        tokens = [clean_token(t) for t in sc_input.split(",") if t.strip()]
        safe_cmds = []
        for cmd in tokens:
            if not is_safe_startup_cmd(cmd, project_root):
                console.print(f"[red]Unsafe startup command blocked: {cmd}[/red]")
                return
            if cmd not in safe_cmds:
                safe_cmds.append(cmd)
        proj["startup_cmd"] = _startup_collapse(safe_cmds)
    elif sc_input == "":
        if not startup_list and proj.get("startup_cmd") is None:
             pass 
        elif startup_list:
             if click.confirm("Clear all startup commands?", default=False):
                 proj["startup_cmd"] = None

    manager.save_projects(data)
    console.print(f"\n[green]✔ Project {proj['alias']} updated.[/green]")