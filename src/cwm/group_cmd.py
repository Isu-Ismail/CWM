# src/cwm/group_cmd.py
import click
from .storage_manager import StorageManager


@click.group("group")
def group_cmd():
    """Manage project groups."""
    pass


@group_cmd.command("add")
def add_group():
    """
    Interactively create a project group with pagination.

    Rules:
      - Group must contain at least 2 projects
      - No two groups can have identical project sets
    """
    manager = StorageManager()
    data = manager.load_projects()
    projects = data.get("projects", [])

    if not projects:
        click.echo("No projects saved.")
        return

    groups = data.get("groups", [])
    last_group_id = data.get("last_group_id", 0)

    sorted_projs = sorted(projects, key=lambda x: x["id"])
    page_size = 10
    index = 0
    selected_ids = None

    while True:
        end_index = min(index + page_size, len(sorted_projs))
        click.echo(f"\n--- Projects ({index + 1}–{end_index} of {len(sorted_projs)}) ---")
        for p in sorted_projs[index:end_index]:
            grp = p.get("group")
            grp_label = f"(group: {grp})" if grp else ""
            click.echo(f"[{p['id']}] {p['alias']:<20} : {p['path']} {grp_label}")

        user_input = click.prompt(
            "\nEnter project IDs to group (comma-separated), "
            "press Enter for more, or 'q' to cancel",
            default="",
            show_default=False,
        ).strip()

        if not user_input:
            if end_index >= len(sorted_projs):
                click.echo("No more projects.")
            else:
                index += page_size
            continue

        if user_input.lower() == "q":
            click.echo("Cancelled.")
            return

        tokens = [t.strip() for t in user_input.split(",") if t.strip()]
        try:
            ids = sorted({int(t) for t in tokens})
        except ValueError:
            click.echo("Invalid input. Use comma-separated numeric IDs.")
            continue

        valid_ids = {p["id"] for p in projects}
        invalid = [i for i in ids if i not in valid_ids]
        if invalid:
            click.echo("Invalid project IDs: " + ", ".join(str(i) for i in invalid))
            continue

        selected_ids = ids
        break

    if not selected_ids:
        click.echo("No projects selected.")
        return

    # must have at least 2 projects
    if len(selected_ids) < 2:
        click.echo("A group must contain at least 2 projects.")
        return

    new_set = set(selected_ids)

    # prevent duplicate groups (same composition)
    for g in groups:
        if set(g.get("project_ids", [])) == new_set:
            click.echo(
                f"Error: A group with the same project list already exists "
                f"(id={g['id']}, alias='{g['alias']}')."
            )
            return

    new_group_id = last_group_id + 1
    existing_aliases = {g["alias"] for g in groups}
    default_alias = f"group{new_group_id}"

    while True:
        group_alias = click.prompt(
            "Enter group alias", default=default_alias, show_default=True
        ).strip()
        if not group_alias:
            click.echo("Alias cannot be empty.")
            continue
        if group_alias in existing_aliases:
            click.echo(f"Alias '{group_alias}' already exists. Choose another.")
            continue
        break

    new_group = {
        "id": new_group_id,
        "alias": group_alias,
        "project_ids": selected_ids,
    }
    groups.append(new_group)

    # assign group ID to selected projects
    for p in projects:
        if p["id"] in selected_ids:
            p["group"] = new_group_id

    data["groups"] = groups
    data["last_group_id"] = new_group_id
    data["projects"] = projects
    manager.save_projects(data)

    click.echo(
        f"Created group '{group_alias}' (id={new_group_id}) "
        f"with projects: {', '.join(str(i) for i in selected_ids)}"
    )



@group_cmd.command("list")
def list_groups():
    """List all groups with minimal project details."""
    manager = StorageManager()
    data = manager.load_projects()

    groups = data.get("groups", [])
    projects = data.get("projects", [])

    if not groups:
        click.echo("No groups created yet.")
        return

    click.echo(f"--- Groups ({len(groups)}) ---")

    proj_by_id = {p["id"]: p for p in projects}

    for g in sorted(groups, key=lambda x: x["id"]):
        pids = g.get("project_ids", [])
        count = len(pids)

        aliases = []
        for pid in pids[:3]:
            p = proj_by_id.get(pid)
            if p:
                aliases.append(p["alias"])

        if aliases:
            preview = ", ".join(aliases)
            if count > 3:
                preview += f", ... (+{count - 3} more)"
        else:
            preview = "no projects"

        click.echo(f"[{g['id']}] {g['alias']}  => {count} projects  ({preview})")



@group_cmd.command("delete")
@click.option("--id", "group_id", type=int, help="Delete a group by ID directly.")
def delete_group(group_id):
    """
    Delete project groups and re-index group IDs.
    Also clears related project.group fields.
    """
    manager = StorageManager()
    data = manager.load_projects()

    groups = data.get("groups", [])
    projects = data.get("projects", [])

    if not groups:
        click.echo("No groups exist.")
        return

    # Direct delete: cwm group delete --id 3
    if group_id is not None:
        idx = next((i for i, g in enumerate(groups) if g["id"] == group_id), None)
        if idx is None:
            click.echo(f"Group ID {group_id} not found.")
            return

        removed = groups.pop(idx)
        click.echo(f"Removed group '{removed['alias']}' (id={group_id}).")

        for p in projects:
            if p.get("group") == group_id:
                p["group"] = None

        _reindex_groups_and_save(manager, data, groups, projects)
        return

    # Interactive
    click.echo("\n--- Groups ---")
    for g in sorted(groups, key=lambda x: x["id"]):
        click.echo(f"[{g['id']}] {g['alias']}  →  {len(g.get('project_ids', []))} projects")

    user_input = click.prompt(
        "\nEnter group ID to DELETE (or press Enter to cancel)",
        default="",
        show_default=False,
    ).strip()

    if not user_input:
        click.echo("Cancelled.")
        return

    if not user_input.isdigit():
        click.echo("Invalid input. Enter a numeric ID.")
        return

    gid = int(user_input)
    idx = next((i for i, g in enumerate(groups) if g["id"] == gid), None)
    if idx is None:
        click.echo(f"Group ID {gid} not found.")
        return

    removed = groups.pop(idx)
    click.echo(f"Removed group '{removed['alias']}' (id={gid}).")

    for p in projects:
        if p.get("group") == gid:
            p["group"] = None

    _reindex_groups_and_save(manager, data, groups, projects)


def _reindex_groups_and_save(manager, data, groups, projects):
    """
    Re-index group IDs (1..N) after deletions and
    update project.group references accordingly.
    """
    if not groups:
        data["groups"] = []
        data["last_group_id"] = 0
        data["projects"] = projects
        manager.save_projects(data)
        click.echo("All groups removed.")
        return

    groups.sort(key=lambda g: g["id"])
    id_map = {}

    for new_id, g in enumerate(groups, start=1):
        old_id = g["id"]
        g["id"] = new_id
        id_map[old_id] = new_id

    for p in projects:
        old = p.get("group")
        if old in id_map:
            p["group"] = id_map[old]
        elif old not in id_map and old is not None:
            p["group"] = None

    data["groups"] = groups
    data["projects"] = projects
    data["last_group_id"] = len(groups)
    manager.save_projects(data)

    click.echo("Re-indexed group IDs.")







@group_cmd.command("edit")
@click.option("-id", "group_id", type=int, help="Group ID to edit.")
@click.option("-n", "--name", "new_alias", help="New alias for the group.")
@click.option(
    "-a",
    "--add",
    "add_ids",
    multiple=True,
    type=int,
    help="Project ID to add to the group (can be repeated).",
)
@click.option(
    "-r",
    "--remove",
    "remove_ids",
    multiple=True,
    type=int,
    help="Project ID to remove from the group (can be repeated).",
)
def edit_group(group_id, new_alias, add_ids, remove_ids):
    """
    Edit an existing project group.

    Power mode:
      cwm group edit -id 1 -n "backend" -a 3 -r 2

    Wizard mode:
      cwm group edit
      (Select group → view all projects → +ID / -ID / replace)
    """
    manager = StorageManager()
    data = manager.load_projects()
    groups = data.get("groups", [])
    projects = data.get("projects", [])

    if not groups:
        click.echo("No groups found.")
        return

    valid_project_ids = {p["id"] for p in projects}

    # -------------------------
    # Choose group (wizard if id not provided)
    # -------------------------
    if group_id is None:
        click.echo("--- Groups ---")
        for g in sorted(groups, key=lambda x: x["id"]):
            click.echo(
                f"[{g['id']}] {g['alias']}  →  {len(g.get('project_ids', []))} projects"
            )
        try:
            group_id = click.prompt("Select Group ID to edit", type=int)
        except click.Abort:
            click.echo("Cancelled.")
            return

    group = next((g for g in groups if g["id"] == group_id), None)
    if not group:
        click.echo(f"Group {group_id} not found.")
        return

    old_alias = group.get("alias", "")
    old_ids = list(group.get("project_ids", []))

    # -------------------------
    # POWER MODE
    # -------------------------
    if new_alias or add_ids or remove_ids:
        new_ids = set(old_ids)

        # validate add/remove IDs
        invalid_add = [pid for pid in add_ids if pid not in valid_project_ids]
        invalid_remove = [pid for pid in remove_ids if pid not in valid_project_ids]
        if invalid_add:
            click.echo(
                "Invalid project IDs to add: " + ", ".join(str(i) for i in invalid_add)
            )
            return
        if invalid_remove:
            click.echo(
                "Invalid project IDs to remove: "
                + ", ".join(str(i) for i in invalid_remove)
            )
            return

        for pid in add_ids:
            new_ids.add(pid)
        for pid in remove_ids:
            if pid in new_ids:
                new_ids.remove(pid)

        new_list = sorted(new_ids)

        # must have at least 2
        if len(new_list) < 2:
            click.echo("A group must contain at least 2 projects.")
            return

        # prevent duplicates within group
        if len(new_list) != len(set(new_list)):
            click.echo("Duplicate project IDs detected in group.")
            return

        # prevent duplicate composition with other groups
        new_set = set(new_list)
        for g in groups:
            if g["id"] != group_id and set(g.get("project_ids", [])) == new_set:
                click.echo(
                    f"Error: Another group (id={g['id']}, alias='{g['alias']}') "
                    f"already has the exact same project list."
                )
                return

        # alias handling
        final_alias = old_alias
        if new_alias:
            candidate = new_alias.strip()
            if not candidate:
                click.echo("Alias cannot be empty.")
                return
            other_aliases = {g["alias"] for g in groups if g["id"] != group_id}
            if candidate in other_aliases:
                click.echo(f"Alias '{candidate}' already exists.")
                return
            final_alias = candidate

        # apply
        group["alias"] = final_alias
        group["project_ids"] = new_list

        # update project.group mappings
        old_set = set(old_ids)
        for p in projects:
            pid = p["id"]
            if pid in old_set and pid not in new_set:
                p["group"] = None
            if pid in new_set:
                p["group"] = group_id

        data["groups"] = groups
        data["projects"] = projects
        manager.save_projects(data)

        click.echo("Group updated.")
        click.echo(f"Alias: {final_alias}")
        click.echo("Projects: " + ", ".join(str(i) for i in new_list))
        return

    # -------------------------
    # WIZARD MODE
    # -------------------------
    click.echo(f"\n--- Editing Group {group_id} ---")
    click.echo(f"Alias: {old_alias}")
    click.echo(
        "Current projects: "
        + (", ".join(str(i) for i in old_ids) if old_ids else "(none)")
    )

    # show all projects with mark
    click.echo("\n--- All Projects ---")
    current_set = set(old_ids)
    for p in sorted(projects, key=lambda x: x["id"]):
        mark = "*" if p["id"] in current_set else " "
        click.echo(f"[{p['id']}] {mark} {p['alias']:<20} : {p['path']}")

    click.echo(
        "\nModify project list:\n"
        "  Enter       → keep current list\n"
        "  1,2,3       → replace list\n"
        "  +7,+8       → add projects\n"
        "  -3,-4       → remove projects\n"
    )

    user_input = click.prompt("Projects", default="", show_default=False).strip()
    new_ids = list(old_ids)

    if user_input:
        tokens = [t.strip() for t in user_input.split(",") if t.strip()]
        replace_mode = any(
            not t.startswith("+") and not t.startswith("-") for t in tokens
        )

        if replace_mode:
            # completely replace
            new_ids = []
            for t in tokens:
                try:
                    pid = int(t)
                    new_ids.append(pid)
                except ValueError:
                    click.echo(f"Ignoring invalid ID: {t}")
        else:
            # incremental add/remove
            current = set(old_ids)
            for t in tokens:
                if t.startswith("+"):
                    try:
                        pid = int(t[1:])
                        current.add(pid)
                    except ValueError:
                        click.echo(f"Ignoring invalid token: {t}")
                elif t.startswith("-"):
                    try:
                        pid = int(t[1:])
                        current.discard(pid)
                    except ValueError:
                        click.echo(f"Ignoring invalid token: {t}")
            new_ids = sorted(current)

    # validations
    invalid = [pid for pid in new_ids if pid not in valid_project_ids]
    if invalid:
        click.echo("Invalid project IDs: " + ", ".join(str(i) for i in invalid))
        return

    if len(new_ids) < 2:
        click.echo("A group must contain at least 2 projects.")
        return

    if len(new_ids) != len(set(new_ids)):
        click.echo("Duplicate project IDs detected in group.")
        return

    new_set = set(new_ids)
    for g in groups:
        if g["id"] != group_id and set(g.get("project_ids", [])) == new_set:
            click.echo(
                f"Error: Another group (id={g['id']}, alias='{g['alias']}') "
                f"already has the exact same project list."
            )
            return

    # alias
    alias_input = click.prompt(
        "Alias", default=old_alias, show_default=True
    ).strip()
    final_alias = old_alias
    if alias_input != old_alias:
        if not alias_input:
            click.echo("Alias cannot be empty.")
            return
        if any(g["alias"] == alias_input and g["id"] != group_id for g in groups):
            click.echo(f"Alias '{alias_input}' already exists.")
            return
        final_alias = alias_input

    # apply
    group["alias"] = final_alias
    group["project_ids"] = new_ids

    old_set = set(old_ids)
    for p in projects:
        pid = p["id"]
        if pid in old_set and pid not in new_set:
            p["group"] = None
        if pid in new_set:
            p["group"] = group_id

    data["groups"] = groups
    data["projects"] = projects
    manager.save_projects(data)

    click.echo("\nGroup updated successfully.")
    click.echo(f"Alias: {final_alias}")
    click.echo("Projects: " + ", ".join(str(i) for i in new_ids))



