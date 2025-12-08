import click
from pathlib import Path
from rich.console import Console
from .storage_manager import StorageManager


console = Console()


def _prompt_project_details(target_path, projects_list, default_alias=None, pre_startup=None):
    """
    Shared logic to ask for Alias and Startup Commands.
    Returns: (alias, startup_value) OR (None, None) if validation fails.
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
        tokens = [t.strip() for t in raw_input.split(",") if t.strip()]
        safe_cmds = []
        for cmd in tokens:
            if not is_safe_startup_cmd(cmd, target_path):
                click.echo(f"⚠ Unsafe startup command blocked: {cmd}")
                return None, None  # Fail signal

            if cmd not in safe_cmds:
                safe_cmds.append(cmd)

        startup_value = _startup_collapse(safe_cmds)

    return alias, startup_value


def _startup_to_list(value):
    """Normalize startup_cmd (None | str | list[str]) into list[str]."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def _startup_collapse(values: list[str]):
    """
    Collapse list[str] back into storage form:
      - []      -> None
      - [one]   -> "one"
      - [a,b]   -> ["a","b"]
    """
    clean = [v.strip() for v in values if v.strip()]
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    return clean


DANGER_KEYWORDS = [
    "rm ", "rm -", "del ", "rd ", "rmdir",
    "format ", "fdisk", "mkfs",
    ":(){ :|:& };:",  # Fork bomb
    "sudo rm",
    "cwm ",   # Prevent recursion
]


def is_safe_startup_cmd(cmd_input, project_root: Path) -> bool:
    """
    Validator for startup commands.
    Accepts str OR list.
    Blocks dangerous keywords but allows general shell usage.
    """
    if not cmd_input:
        return False

    cmds_to_check = []
    if isinstance(cmd_input, list):
        cmds_to_check = cmd_input
    else:
        cmds_to_check = [str(cmd_input)]

    for cmd in cmds_to_check:
        cmd = cmd.strip()
        if not cmd:
            continue

        cmd_lower = cmd.lower()

        if any(bad in cmd_lower for bad in DANGER_KEYWORDS):
            return False

        parts = cmd.split()
        if len(parts) > 1 and parts[0] in ("python", "python3", "py"):
            script = parts[1]
            if not script.startswith("-"):
                try:
                    project_root = project_root.resolve()
                    if ".." in script or script.startswith("/"):
                        script_path = (project_root / script).resolve()
                        if project_root not in script_path.parents and script_path != project_root:
                            return False
                except:
                    pass

    return True


def _get_unique_alias(base_name: str, existing_projects: list) -> str:
    """Prevents duplicates among project aliases."""
    existing_aliases = {p["alias"] for p in existing_projects}
    if base_name not in existing_aliases:
        return base_name
    count = 2
    new_name = f"{base_name}-{count}"
    while new_name in existing_aliases:
        count += 1
        new_name = f"{base_name}-{count}"
    return new_name


def _normalize_startup_cmd(value):
    """Normalize startup_cmd into list or None."""
    if not value:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        return [value]
    if isinstance(value, list):
        clean = [v.strip() for v in value if v.strip()]
        return clean or None
    return None


@click.group("project")
def project_cmd():
    """Manage workspace projects."""
    pass


@project_cmd.command("scan")
@click.option("--root", help="Specific folder to scan (defaults to User Home).")
def scan_projects(root):
    from .project_utils import ProjectScanner
    import time
    """Auto-detect projects in your User Home directory."""
    start_path = Path(root).resolve() if root else Path.home()

    manager = StorageManager()
    data = manager.load_projects()

    existing_paths = {p["path"] for p in data.get("projects", [])}
    current_projects = data.get("projects", [])
    last_id = data.get("last_id", 0)

    scanner = ProjectScanner(start_path)
    found_candidates = []

    start_time = time.perf_counter()  # <--- 2. Start Timer

    with console.status("[bold cyan]Scanning folders...", spinner="dots") as status:
        for proj_path in scanner.scan_generator():
            status.update(
                f"[bold cyan]Scanning... ({scanner.scanned_count} checked)")
            if str(proj_path) in existing_paths:
                continue
            found_candidates.append(proj_path)

    end_time = time.perf_counter()  # <--- 3. Stop Timer
    duration = end_time - start_time  # <--- 4. Calculate Duration

    console.print(
        f"\n[dim]Scan Summary: Checked {scanner.scanned_count} folders in {duration:.2f} seconds.[/dim]"
    )

    if not found_candidates:
        console.print("[yellow]Scan complete. No new projects found.[/yellow]")
        return

    console.print(
        f"[bold green]✔ Found {len(found_candidates)} candidates.[/bold green]")

    added_count = 0

    for p in found_candidates:
        rel_path = p.relative_to(start_path)
        click.echo(f"\nCandidate: [ {rel_path} ]")

        action = click.prompt(
            "Add project? [y]es, [n]o (ignore), [s]kip",
            type=click.Choice(["y", "n", "s"]),
            default="y",
            show_default=False,
        )

        if action == "s":
            continue
        if action == "n":
            scanner.add_to_ignore(str(rel_path))
            click.echo(f"-> Added {rel_path} to ignore list.")
            continue

        if action == "y":
            alias, startup_cmd = _prompt_project_details(p, current_projects)

            if alias is None:
                click.echo("Skipping due to validation error.")
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
@click.option("-s", "--startup", help="Startup command(s).")
def add_project(path, name, startup):
    """Manually add a project folder."""
    manager = StorageManager()

    if not path:
        path = click.prompt("Enter Project Path").strip()

    target = Path.cwd().resolve() if path == "." else Path(path).resolve()

    if not target.exists() or not target.is_dir():
        click.echo(f"Error: Invalid directory '{path}'.")
        return

    data = manager.load_projects()
    projects = data.get("projects", [])

    if any(p["path"] == str(target) for p in projects):
        click.echo("This path is already saved.")
        return

    alias, startup_cmd = _prompt_project_details(
        target,
        projects,
        default_alias=name,
        pre_startup=startup
    )

    if alias is None:
        return  # Failed validation

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

    sorted_projs = sorted(projects, key=lambda x: x["id"])

    for p in sorted_projs:
        grp = p.get("group")
        grp_label = f"(group: {grp})" if grp else ""
        click.echo(f"[{p['id']}] {p['alias']:<20} : {p['path']} {grp_label}")


@project_cmd.command("remove")
@click.argument("target", required=False)
@click.option(
    "-n",
    "count",
    default="10",
    help="Number of candidates to show (or 'all'). Default: 10.",
)
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
        click.echo("No projects to remove.")
        return

    removed_something = False

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

    else:
        sorted_projs = sorted(
            projects, key=lambda x: (x.get("hits", 0), x["alias"])
        )

        limit = 10
        is_all = False

        if str(count).lower() == "all":
            limit = len(sorted_projs)
            is_all = True
        else:
            try:
                limit = int(count)
                if limit <= 0:
                    limit = 10
            except ValueError:
                limit = 10

        display_list = sorted_projs[:limit]

        if is_all or limit >= len(projects):
            header = f"--- All Projects ({len(projects)}) ---"
        else:
            header = f"--- Bottom {len(display_list)} Least Used Projects ---"

        click.echo(header)

        for p in display_list:
            hits = p.get("hits", 0)
            click.echo(
                f"[{p['id']}] (Hits: {hits})  {p['alias']:<20} : {p['path']}"
            )

        choice = click.prompt(
            "\nEnter IDs/Aliases to REMOVE (comma-separated) or press Enter to cancel",
            default="",
            show_default=False,
        )

        if not choice:
            return

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

        if not to_remove_indexes:
            click.echo("No valid projects selected.")
            return

        to_remove_indexes.sort(reverse=True)

        count_removed = 0
        removed_ids = set()
        for idx in to_remove_indexes:
            removed = projects.pop(idx)
            removed_ids.add(removed["id"])
            click.echo(f"Removed: {removed['alias']}")
            count_removed += 1

        for g in groups:
            g["project_ids"] = [
                pid for pid in g.get("project_ids", []) if pid not in removed_ids
            ]

        click.echo(f"\nSuccessfully removed {count_removed} projects.")
        removed_something = True

    if removed_something:
        click.echo("Re-indexing project IDs...")

        projects.sort(key=lambda x: x["id"])

        id_mapping = {}
        for index, p in enumerate(projects):
            old_id = p["id"]
            new_id = index + 1
            p["id"] = new_id
            id_mapping[old_id] = new_id

        data["last_id"] = len(projects)

        for g in groups:
            new_pids = []
            for pid in g.get("project_ids", []):
                if pid in id_mapping:
                    new_pids.append(id_mapping[pid])
            g["project_ids"] = new_pids

        data["groups"] = groups
        data["last_group_id"] = last_group_id
        data["projects"] = projects
        manager.save_projects(data)
        click.echo("Done.")


@project_cmd.command("edit")
@click.option("-id", "project_id", type=int, help="Project ID to edit.")
@click.option("-n", "--name", "new_alias", help="New alias for the project.")
@click.option("-p", "--path", "new_path", help="New path for the project.")
@click.option("-a", "--add", "add_cmds", multiple=True, help="Add startup command.")
@click.option("-r", "--remove", "remove_cmds", multiple=True, help="Remove startup command.")
def edit_project(project_id, new_alias, new_path, add_cmds, remove_cmds):
    """
    Edit a project's alias, path, and startup commands.

    Power mode:
      cwm project edit -id 2 -n api -p "./backend" -a "python app.py" -r "npm start"

    Wizard mode:
      cwm project edit
      (Lists projects → pick one → then Alias, Path, Startup)
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        click.echo("No projects saved.")
        return

    if project_id is None:
        click.echo("--- Projects ---")
        for p in sorted(projects, key=lambda x: x["id"]):
            click.echo(f"[{p['id']}] {p['alias']:<20} : {p['path']}")
        try:
            project_id = click.prompt("Select Project ID to edit", type=int)
        except click.Abort:
            click.echo("Cancelled.")
            return

    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        click.echo(f"Project {project_id} not found.")
        return

    project_root = Path(proj["path"]).resolve()
    startup_list = _startup_to_list(proj.get("startup_cmd"))

    if new_alias or new_path or add_cmds or remove_cmds:
        if new_alias:
            alias = new_alias.strip()
            if not alias:
                click.echo("Alias cannot be empty.")
                return
            if any(p["alias"] == alias and p["id"] != project_id for p in projects):
                click.echo(f"Alias '{alias}' already exists.")
                return
            proj["alias"] = alias

        if new_path:
            cleaned = new_path.strip().strip('"').strip("'")
            resolved = Path(cleaned).resolve()
            if not resolved.exists() or not resolved.is_dir():
                click.echo(f"Invalid directory: {cleaned}")
                return
            proj["path"] = str(resolved)
            project_root = resolved

        current = list(startup_list)

        for cmd in add_cmds:
            c = cmd.strip()
            if not c:
                continue
            if not is_safe_startup_cmd(c, project_root):
                click.echo(f"Unsafe startup command blocked: {c}")
                return
            if c not in current:
                current.append(c)

        for cmd in remove_cmds:
            c = cmd.strip()
            if c in current:
                current.remove(c)

        proj["startup_cmd"] = _startup_collapse(current)

        manager.save_projects(data)
        click.echo("Project updated.")
        return

    click.echo(f"\n--- Editing Project {project_id} ---")
    click.echo(f"Alias: {proj['alias']}")
    click.echo(f"Path:  {proj['path']}")
    click.echo("Startup commands:")
    if startup_list:
        for c in startup_list:
            click.echo(f"  - {c}")
    else:
        click.echo("  (none)")

    new_alias_wiz = click.prompt("New Alias", default=proj["alias"]).strip()
    if new_alias_wiz != proj["alias"]:
        if any(p["alias"] == new_alias_wiz and p["id"] != project_id for p in projects):
            click.echo(f"Alias '{new_alias_wiz}' already exists.")
            return
        proj["alias"] = new_alias_wiz

    new_path_wiz = click.prompt("New Path", default=proj["path"]).strip()
    if new_path_wiz != proj["path"]:
        cleaned = new_path_wiz.strip().strip('"').strip("'")
        resolved = Path(cleaned).resolve()
        if not resolved.exists() or not resolved.is_dir():
            click.echo("Invalid directory.")
            return
        proj["path"] = str(resolved)
        project_root = resolved

    sc_input = click.prompt(
        "Startup commands (comma-separated) or Enter to keep",
        default="",
        show_default=False,
    ).strip()

    if sc_input:
        tokens = [t.strip() for t in sc_input.split(",") if t.strip()]
        safe_cmds = []
        for cmd in tokens:
            if not is_safe_startup_cmd(cmd, project_root):
                click.echo(f"Unsafe startup command blocked: {cmd}")
                return
            if cmd not in safe_cmds:
                safe_cmds.append(cmd)
        proj["startup_cmd"] = _startup_collapse(safe_cmds)

    manager.save_projects(data)
    click.echo("Project updated.")

