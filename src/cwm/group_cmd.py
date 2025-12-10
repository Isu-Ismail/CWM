import click
from .storage_manager import StorageManager
from .rich_help import RichHelpGroup, RichHelpCommand

# Rich Imports
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich import box

console = Console()

@click.group("group", cls=RichHelpGroup)
def group_cmd():
    """Manage project groups."""
    pass


@group_cmd.command("add", cls=RichHelpCommand)
def add_group():
    """
    Interactively create a project group with pagination.
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        console.print("[yellow]! No projects saved.[/yellow]")
        return

    groups = data.get("groups", [])
    last_group_id = data.get("last_group_id", 0)

    # Sort projects by ID for display
    sorted_projs = sorted(projects, key=lambda x: x["id"])
    page_size = 15
    index = 0
    selected_ids = None

    # --- PAGINATED SELECTION LOOP ---
    while True:
        end_index = min(index + page_size, len(sorted_projs))
        
        # Table Header
        console.print(f"\n[bold]Projects ({index + 1}–{end_index} of {len(sorted_projs)})[/bold]")
        
        # Project Table
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Alias", style="bold white")
        table.add_column("Path", style="dim")
        table.add_column("Group Info", style="magenta")

        for p in sorted_projs[index:end_index]:
            grp = p.get("group")
            grp_label = f"(G: {grp})" if grp else ""
            table.add_row(f"[{p['id']}]", p['alias'], p['path'], grp_label)
        
        console.print(table)
        console.print("")

        # Prompt
        prompt_msg = "  [bold cyan]?[/bold cyan] Enter IDs [dim](comma-separated)[/dim], [bold]Enter[/bold] for more, or [bold]q[/bold] to cancel"
        user_input = Prompt.ask(prompt_msg, default="", show_default=False).strip()

        if not user_input:
            if end_index >= len(sorted_projs):
                console.print("[dim]No more projects.[/dim]")
            else:
                index += page_size
            continue

        if user_input.lower() == "q":
            return

        # Parse IDs
        tokens = [t.strip() for t in user_input.split(",") if t.strip()]
        try:
            ids = sorted({int(t) for t in tokens})
        except ValueError:
            console.print("[red]✖ Invalid input. Use numbers.[/red]")
            continue

        valid_ids = {p["id"] for p in projects}
        invalid = [i for i in ids if i not in valid_ids]
        
        if invalid:
            console.print(f"[red]✖ Invalid IDs: {', '.join(str(i) for i in invalid)}[/red]")
            continue

        selected_ids = ids
        break

    if not selected_ids:
        return

    # --- BUILD NEW GROUP DATA ---
    new_group_items = []
    proj_lookup = {p["id"]: p for p in projects}

    for pid in selected_ids:
        proj = proj_lookup[pid]
        new_group_items.append({
            "id": pid,
            "verify": proj["alias"]  # The anchor for self-healing
        })

    # Duplicate Check (Set Comparison)
    new_id_set = set(selected_ids)
    for g in groups:
        # Extract IDs from existing groups (handling old/new format)
        existing_items = g.get("project_list", [])
        existing_ids = set()
        for item in existing_items:
            if isinstance(item, dict):
                existing_ids.add(item.get("id"))
            else:
                existing_ids.add(item) 

        if existing_ids == new_id_set:
            console.print(f"[red]✖ Error: Group '{g['alias']}' already has these exact projects.[/red]")
            return

    # --- ALIAS & SAVE ---
    new_group_id = last_group_id + 1
    existing_aliases = {g["alias"] for g in groups}
    default_alias = f"group{new_group_id}"

    while True:
        group_alias = Prompt.ask("  [bold cyan]?[/bold cyan] Name this group", default=default_alias).strip()
        if not group_alias:
            console.print("[red]Alias cannot be empty.[/red]")
            continue
        if group_alias in existing_aliases:
            console.print(f"[red]Alias '{group_alias}' already exists.[/red]")
            continue
        break

    new_group = {
        "id": new_group_id,
        "alias": group_alias,
        "project_list": new_group_items,
    }
    groups.append(new_group)

    # Link projects to this group
    for p in projects:
        if p["id"] in selected_ids:
            p["group"] = new_group_id

    data["groups"] = groups
    data["last_group_id"] = new_group_id
    data["projects"] = projects

    manager.save_projects(data)

    console.print(f"\n[bold green]✔ Created group '{group_alias}' (ID: {new_group_id})[/bold green]")
    console.print(f"  Projects: [dim]{', '.join(str(i) for i in selected_ids)}[/dim]\n")


@group_cmd.command("list", cls=RichHelpCommand)
def list_groups():
    """List all groups with minimal project details."""
    manager = StorageManager()
    data = manager.load_projects()

    groups = data.get("groups", [])
    projects = data.get("projects", [])

    if not groups:
        console.print("[dim]No groups created yet.[/dim]")
        return

    # Build Lookup
    proj_by_id = {p["id"]: p for p in projects}

    # Table
    table = Table(title="Project Groups", box=None, padding=(0, 2))
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Alias", style="bold white")
    table.add_column("Count", style="green", justify="right")
    table.add_column("Preview", style="dim")

    for g in sorted(groups, key=lambda x: x["id"]):
        # Handle new structure
        group_items = g.get("project_list", [])
        
        project_ids = []
        for item in group_items:
            if isinstance(item, dict):
                project_ids.append(item.get("id"))
            else:
                project_ids.append(item)

        count = len(project_ids)
        
        # Generate Preview String
        aliases = []
        for pid in project_ids[:3]:
            if isinstance(pid, int):
                p = proj_by_id.get(pid)
                if p: aliases.append(p["alias"])
        
        preview = ", ".join(aliases)
        if count > 3:
            preview += f", ... (+{count - 3})"
        if not aliases:
            preview = "(empty)"

        table.add_row(str(g['id']), g['alias'], str(count), preview)

    console.print(table)
    console.print("")


# ... existing imports ...

@group_cmd.command("delete", cls=RichHelpCommand)
@click.option("--id", "group_ids_arg", help="Delete group(s) by ID (e.g. 1 or 1,2).")
def delete_group(group_ids_arg):
    """
    Delete project groups and re-index group IDs.
    Supports single or comma-separated IDs.
    """
    manager = StorageManager()
    data = manager.load_projects()

    groups = data.get("groups", [])
    projects = data.get("projects", [])

    if not groups:
        console.print("[dim]No groups exist.[/dim]")
        return

    target_ids = []

    # --- DIRECT MODE (Flag) ---
    if group_ids_arg:
        try:
            target_ids = [int(x.strip()) for x in str(group_ids_arg).split(',') if x.strip()]
        except ValueError:
            console.print("[red]✖ Invalid ID format. Use numbers (e.g. 1,2).[/red]")
            return
            
        if target_ids:
            _perform_batch_delete(manager, data, groups, projects, target_ids)
        return

    # --- INTERACTIVE MODE ---
    console.print("\n[bold]Select Group(s) to Delete[/bold]")
    table = Table(box=None, show_header=False, padding=(0, 2))
    for g in sorted(groups, key=lambda x: x["id"]):
        count = len(g.get('project_list', []))
        table.add_row(f"[cyan][{g['id']}][/cyan]", f"[bold white]{g['alias']}[/bold white]", f"[dim]({count} projects)[/dim]")
    
    console.print(table)
    console.print("")

    try:
        user_input = Prompt.ask("  [bold red]✖[/bold red] Enter Group ID(s)", default="")
        if not user_input: return
        
        # Parse comma-separated input
        target_ids = [int(x.strip()) for x in user_input.split(',') if x.strip()]
        
        count_str = f"{len(target_ids)} groups" if len(target_ids) > 1 else f"Group {target_ids[0]}"
        
        if Confirm.ask(f"  Are you sure you want to delete {count_str}?"):
            _perform_batch_delete(manager, data, groups, projects, target_ids)
            
    except ValueError:
        console.print("[red]Invalid input. Please enter numbers.[/red]")


def _perform_batch_delete(manager, data, groups, projects, target_ids):
    """
    Batch removes groups by ID and then performs a single re-index.
    This prevents ID shifting errors during deletion.
    """
    ids_to_remove = set(target_ids)
    original_count = len(groups)
    
    # 1. Identify groups to keep vs remove
    groups_to_keep = []
    removed_aliases = []
    
    for g in groups:
        if g["id"] in ids_to_remove:
            removed_aliases.append(g['alias'])
        else:
            groups_to_keep.append(g)
            
    if not removed_aliases:
        console.print(f"[yellow]! No matching groups found for IDs: {target_ids}[/yellow]")
        return

    # 2. Clear group links in projects
    # We must reset any project pointing to a deleted group ID
    for p in projects:
        if p.get("group") in ids_to_remove:
            p["group"] = None

    # 3. Report
    for alias in removed_aliases:
        console.print(f"[green]✔ Removed group '{alias}'.[/green]")

    # 4. Save & Re-index
    # We pass the filtered list as the new 'groups' source
    _reindex_groups_and_save(manager, data, groups_to_keep, projects)


def _reindex_groups_and_save(manager, data, groups, projects):
    """
    Re-index group IDs (1..N) and update links.
    """
    if not groups:
        data["groups"] = []
        data["last_group_id"] = 0
        data["projects"] = projects
        manager.save_projects(data)
        console.print("[dim]All groups cleared.[/dim]")
        return

    # Sort by current ID to maintain relative order
    groups.sort(key=lambda g: g["id"])
    id_map = {} # Old ID -> New ID

    # Re-assign IDs sequentially
    for new_id, g in enumerate(groups, start=1):
        old_id = g["id"]
        g["id"] = new_id
        id_map[old_id] = new_id

    # Update project references to match new IDs
    for p in projects:
        old = p.get("group")
        if old in id_map:
            p["group"] = id_map[old]
        elif old is not None:
            # Should already be cleared, but safety first
            p["group"] = None

    data["groups"] = groups
    data["projects"] = projects
    data["last_group_id"] = len(groups)
    manager.save_projects(data)
    
    console.print("[dim]IDs re-indexed.[/dim]\n")


@group_cmd.command("edit", cls=RichHelpCommand)
@click.option("-id", "group_id", type=int, help="Group ID to edit.")
@click.option("-n", "--name", "new_alias", help="New alias for the group.")
def edit_group(group_id, new_alias):
    """
    Edit an existing project group (Wizard Mode).
    """
    manager = StorageManager()
    data = manager.load_projects()
    groups = data.get("groups", [])
    projects = data.get("projects", [])

    if not groups:
        console.print("[dim]No groups found.[/dim]")
        return

    # --- 1. SELECT GROUP ---
    if group_id is None:
        console.print("\n[bold]Select Group to Edit[/bold]")
        table = Table(box=None, show_header=False, padding=(0, 2))
        for g in sorted(groups, key=lambda x: x["id"]):
            count = len(g.get('project_list', []))
            table.add_row(f"[cyan][{g['id']}][/cyan]", f"{g['alias']}", f"[dim]{count} projects[/dim]")
        console.print(table)
        console.print("")
        
        try:
            group_id = IntPrompt.ask("  [bold cyan]?[/bold cyan] Group ID")
        except:
            return

    group = next((g for g in groups if g["id"] == group_id), None)
    if not group:
        console.print(f"[red]Group {group_id} not found.[/red]")
        return

    # Extract current IDs from project_list structure
    old_list_objs = group.get("project_list", [])
    old_ids = []
    for item in old_list_objs:
        if isinstance(item, dict): old_ids.append(item.get("id"))
        else: old_ids.append(item)

    # --- 2. SHOW STATUS ---
    console.print(f"\n[bold]Editing Group: {group['alias']}[/bold]")
    
    # --- 3. SHOW ALL PROJECTS (Selection Table) ---
    console.print("\n[bold]Projects[/bold]")
    table = Table(box=None, show_header=False, padding=(0, 2))
    
    current_set = set(old_ids)
    for p in sorted(projects, key=lambda x: x["id"]):
        mark = "[green]✔[/green]" if p["id"] in current_set else "[dim] [/dim]"
        style = "bold white" if p["id"] in current_set else "dim"
        table.add_row(f"{mark} [cyan][{p['id']}][/cyan]", f"[{style}]{p['alias']}[/{style}]", f"[dim]{p['path']}[/dim]")
    
    console.print(table)

    console.print("\n[dim]Instructions:[/dim]")
    console.print("[dim]  Enter        → Keep current list[/dim]")
    console.print("[dim]  1,2,3        → Replace list completely[/dim]")
    console.print("[dim]  +7,+8        → Add specific projects[/dim]")
    console.print("[dim]  -3,-4        → Remove specific projects[/dim]")

    user_input = Prompt.ask("\n  [bold cyan]?[/bold cyan] Modify List", default="").strip()
    
    new_ids = list(old_ids)

    if user_input:
        tokens = [t.strip() for t in user_input.split(",") if t.strip()]
        
        # Determine Mode
        replace_mode = any(not t.startswith("+") and not t.startswith("-") for t in tokens)

        if replace_mode:
            # REPLACE Logic
            temp_ids = []
            for t in tokens:
                try: temp_ids.append(int(t))
                except: pass
            new_ids = sorted(list(set(temp_ids))) # Dedupe
        else:
            # PATCH Logic (+/-)
            current = set(old_ids)
            for t in tokens:
                if t.startswith("+"):
                    try: current.add(int(t[1:]))
                    except: pass
                elif t.startswith("-"):
                    try: current.discard(int(t[1:]))
                    except: pass
            new_ids = sorted(list(current))

    # --- 4. VALIDATION & SAVE ---
    valid_pids = {p['id'] for p in projects}
    final_ids = [pid for pid in new_ids if pid in valid_pids]

    if not final_ids:
        console.print("[red]Error: Group must have at least 1 valid project.[/red]")
        return

    # Update Name?
    final_alias = group['alias']
    if new_alias:
        final_alias = new_alias
    else:
        # Optional prompt to rename
        change_name = Prompt.ask("  [bold cyan]?[/bold cyan] Rename group? (Leave empty to keep)", default="")
        if change_name.strip():
            final_alias = change_name.strip()

    # Rebuild project_list objects
    proj_lookup = {p["id"]: p for p in projects}
    new_project_list = []
    
    for pid in final_ids:
        p_obj = proj_lookup.get(pid)
        if p_obj:
            new_project_list.append({
                "id": pid,
                "verify": p_obj["alias"]
            })

    group["alias"] = final_alias
    group["project_list"] = new_project_list
    # Remove old key if present to clean up
    if "project_ids" in group: del group["project_ids"]

    # Update project links
    old_set = set(old_ids)
    new_set = set(final_ids)
    
    for p in projects:
        pid = p["id"]
        # If removed from group
        if pid in old_set and pid not in new_set:
            p["group"] = None
        # If added to group
        if pid in new_set:
            p["group"] = group_id

    manager.save_projects(data)
    
    console.print(f"\n[bold green]✔ Group Updated![/bold green]")
    console.print(f"  Alias: [white]{final_alias}[/white]")
    console.print(f"  Projects: [dim]{', '.join(str(i) for i in final_ids)}[/dim]\n")