# src/cwm/project_cmd.py
import click
from pathlib import Path
from rich.console import Console
from .storage_manager import StorageManager
from .project_utils import ProjectScanner

console = Console()

def _get_unique_alias(base_name: str, existing_projects: list) -> str:
    """Prevents duplicates."""
    existing_aliases = {p['alias'] for p in existing_projects}
    if base_name not in existing_aliases:
        return base_name
    count = 2
    new_name = f"{base_name}-{count}"
    while new_name in existing_aliases:
        count += 1
        new_name = f"{base_name}-{count}"
    return new_name

@click.group("project")
def project_cmd():
    """Manage workspace projects."""
    pass

@project_cmd.command("scan")
@click.option("--root", help="Specific folder to scan (defaults to User Home).")
def scan_projects(root):
    """Auto-detect projects in your User Home directory."""
    # 1. ROOT Logic: Use flag if provided, else default to Home
    start_path = Path(root).resolve() if root else Path.home()
    
    manager = StorageManager()
    data = manager.load_projects()
    existing_paths = {p["path"] for p in data.get("projects", [])}
    
    scanner = ProjectScanner(start_path)
    
    click.echo(f"Root: {start_path}")
    click.echo("Ignores: .cwmignore list (Downloads, Windows, etc.)\n")
    
    found_candidates = []

    with console.status("[bold cyan]Scanning folders...", spinner="dots") as status:
        for proj_path in scanner.scan_generator():
            status.update(f"[bold cyan]Scanning... ({scanner.scanned_count} folders checked)")
            if str(proj_path) in existing_paths:
                continue
            found_candidates.append(proj_path)

    if not found_candidates:
        console.print("[yellow]Scan complete. No new projects found.[/yellow]")
        return

    console.print(f"[bold green]✔ Scan Complete! Found {len(found_candidates)} perfect candidates.[/bold green]")
    
    current_projects = data.get("projects", [])
    last_id = data.get("last_id", 0)
    added_count = 0

    for p in found_candidates:
        rel_path = p.relative_to(start_path)
        click.echo(f"\nCandidate: [ {rel_path} ]")
        
        action = click.prompt(
            "Add project? [y]es, [n]o (ignore forever), [s]kip", 
            type=click.Choice(['y', 'n', 's']), 
            default='y',
            show_default=False
        )
        
        if action == 's': continue
        if action == 'n':
            scanner.add_to_ignore(str(rel_path))
            click.echo(f"-> Added {rel_path} to ignore list.")
            continue
            
        if action == 'y':
            default_name = p.name
            suggested = _get_unique_alias(default_name, current_projects)
            alias = click.prompt("Alias", default=suggested)
            alias = _get_unique_alias(alias, current_projects)

            last_id += 1
            current_projects.append({
                "id": last_id, "alias": alias, "path": str(p), "hits": 0
            })
            added_count += 1
            click.echo(f"-> Saved as '{alias}'")

    if added_count > 0:
        data["projects"] = current_projects
        data["last_id"] = last_id
        manager.save_projects(data)
        click.echo(f"\nSaved {added_count} new projects!")
    else:
        click.echo("\nNo projects added.")

@project_cmd.command("add")
@click.argument("path", required=False)
@click.option("-n", "--name", help="Alias for the project.")
def add_project(path, name):
    """
    Manually add a project folder.
    Supports:  cwm project add .
    """
    manager = StorageManager()

   
    #  If no path given -> user must enter one
    
    if not path:
        path = click.prompt("Enter Project Path").strip()

   
    #  Special Case: "." means *current directory*
   
    if path == ".":
        target = Path.cwd().resolve()
    else:
        # Clean quotes (Windows users often copy with quotes)
        path = path.strip().strip('"').strip("'")
        target = Path(path).resolve()

   
    # Validate folder
    
    if not target.exists() or not target.is_dir():
        click.echo(f"Error: Invalid directory '{path}'.")
        return

    data = manager.load_projects()
    projects = data.get("projects", [])

    # Already exists?
    if any(p["path"] == str(target) for p in projects):
        click.echo("This path is already saved.")
        return

   
    #  Alias handling
    
    default_alias = _get_unique_alias(target.name, projects)

    if not name:
        name = click.prompt("Enter Project Alias", default=default_alias)

    alias = _get_unique_alias(name, projects)

    
    # Save project
   
    new_id = data.get("last_id", 0) + 1
    projects.append({
        "id": new_id,
        "alias": alias,
        "path": str(target),
        "hits": 0
    })

    data["projects"] = projects
    data["last_id"] = new_id
    manager.save_projects(data)

    click.echo(f"Added project '{alias}' → {target}")
    
@project_cmd.command("list")
def list_projects():
    """List all saved projects."""
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])
    
    if not projects:
        click.echo("No projects saved.")
        return
        
    click.echo(f"--- Saved Projects ({len(projects)}) ---")
    
    sorted_projs = sorted(projects, key=lambda x: x['id'])
    
    for p in sorted_projs:
        click.echo(f"[{p['id']}] {p['alias']:<20} : {p['path']}")



@project_cmd.command("remove")
@click.argument("target", required=False)
@click.option("-n", "count", default="10", help="Number of candidates to show (or 'all'). Default: 10.")
def remove_project(target, count):
    """
    Remove a saved project.
    Re-indexes IDs automatically to close gaps.
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        click.echo("No projects to remove.")
        return

    removed_something = False

    # --- Path A: Direct Removal (Argument provided) ---
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
            click.echo(f"Removed project: {removed['alias']}")
            removed_something = True
        else:
            click.echo(f"Project '{target}' not found.")
            return

    # --- Path B: Interactive List ---
    else:
        sorted_projs = sorted(projects, key=lambda x: (x.get("hits", 0), x["alias"]))
        
        limit = 10
        is_all = False
        
        if str(count).lower() == "all":
            limit = len(sorted_projs)
            is_all = True
        else:
            try:
                limit = int(count)
                if limit <= 0: limit = 10
            except ValueError:
                limit = 10

        display_list = sorted_projs[:limit]
        
        if is_all or limit >= len(projects):
            header = f"--- All Projects ({len(projects)}) ---"
        else:
            header = f"--- Bottom {len(display_list)} Least Used Projects ---"

        click.echo(header)

        for p in display_list:
            hits = p.get('hits', 0)
            click.echo(f"[{p['id']}] (Hits: {hits})  {p['alias']:<20} : {p['path']}")

        choice = click.prompt("\nEnter IDs/Aliases to REMOVE (comma-separated) or press Enter to cancel", default="", show_default=False)
        
        if not choice:
            return

        tokens = choice.split(',')
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

        if not to_remove_indexes:
            click.echo("No valid projects selected.")
            return

        to_remove_indexes.sort(reverse=True)
        
        count_removed = 0
        for idx in to_remove_indexes:
            removed = projects.pop(idx)
            click.echo(f"Removed: {removed['alias']}")
            count_removed += 1
        
        click.echo(f"\nSuccessfully removed {count_removed} projects.")
        removed_something = True

    # --- CRITICAL: RE-INDEX IDs ---
    if removed_something:
        click.echo("Re-indexing project IDs...")
        
        # Optional: Sort by existing ID to keep relative order stable
        # projects.sort(key=lambda x: x['id']) 
        
        for index, p in enumerate(projects):
            p["id"] = index + 1
        
        # Update the global counter
        data["last_id"] = len(projects)
        
        manager.save_projects(data)
        click.echo("Done.")