import click
import time
import sys
import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from .storage_manager import StorageManager
from .service_manager import ServiceManager
from .rich_help import RichHelpGroup, RichHelpCommand

console = Console()


# ==========================================================
# HELPERS
# ==========================================================

def _resolve_project_id(token, projects):
    token = str(token).strip()
    if token.isdigit():
        tid = int(token)
        if any(p["id"] == tid for p in projects):
            return tid
    for p in projects:
        if p["alias"] == token:
            return p["id"]
    return None


def _tmux_attach(session_name: str):
    os.execvp("tmux", ["tmux", "attach", "-t", session_name])


# ==========================================================
# CLI GROUP
# ==========================================================

@click.group("run", cls=RichHelpGroup)
def run_cmd():
    """Orchestrate background processes."""
    pass


# ==========================================================
# RUN PROJECT
# ==========================================================

@run_cmd.command("project", cls=RichHelpCommand)
@click.argument("target", required=False)
@click.option("-x", "--exec", is_flag=True, help="Run interactively (no tmux).")
def run_project(target, exec):
    manager = StorageManager()
    svc = ServiceManager()

    projects = manager.load_projects().get("projects", [])
    if not projects:
        console.print("[dim]No projects saved.[/dim]")
        return

    if not target:
        table = Table(box=None)
        for p in projects:
            table.add_row(str(p["id"]), p["alias"])
        console.print(table)
        target = Prompt.ask("Select project")

    pid = _resolve_project_id(target, projects)
    if pid is None:
        console.print("[red]Project not found.[/red]")
        return

    if exec:
        project = next(p for p in projects if p["id"] == pid)
        root = Path(project["path"]).resolve()
        cmd = " && ".join(project["startup_cmd"])
        subprocess.Popen(cmd, cwd=root, shell=True)
        return

    success, msg = svc.start_project(pid)
    console.print(f"[green]✔ {msg}[/green]" if success else f"[red]✘ {msg}[/red]")


# ==========================================================
# RUN GROUP (tmux panes later – safe default)
# ==========================================================

@run_cmd.command("group", cls=RichHelpCommand)
@click.argument("target")
def run_group(target):
    manager = StorageManager()
    svc = ServiceManager()

    data = manager.load_projects()
    groups = data.get("groups", [])
    projects = data.get("projects", [])

    group = next((g for g in groups if g["alias"] == target or str(g["id"]) == target), None)
    if not group:
        console.print("[red]Group not found.[/red]")
        return

    for pid in group.get("project_list", []):
        svc.start_project(pid)

    console.print("[green]✔ Group started[/green]")


# ==========================================================
# LIST
# ==========================================================

@run_cmd.command("list", cls=RichHelpCommand)
def list_running():
    svc = ServiceManager()
    state = svc.get_services_status()

    if not state:
        console.print("[dim]No running services.[/dim]")
        return

    table = Table(title="Running Services")
    table.add_column("ID")
    table.add_column("Alias")
    table.add_column("Backend")

    for info in state.values():
        table.add_row(
            str(info["project_id"]),
            info["alias"],
            info.get("backend", "fallback")
        )

    console.print(table)


# ==========================================================
# STOP
# ==========================================================

@run_cmd.command("stop", cls=RichHelpCommand)
@click.argument("target", required=False)
@click.option("--all", is_flag=True)
def stop_service(target, all):
    svc = ServiceManager()
    manager = StorageManager()
    projects = manager.load_projects().get("projects", [])

    if all:
        svc.stop_all()
        console.print("[green]✔ All stopped[/green]")
        return

    pid = _resolve_project_id(target, projects)
    if pid is None:
        console.print("[red]Project not found.[/red]")
        return

    success, msg = svc.stop_project(pid)
    console.print(f"[green]✔ {msg}[/green]" if success else f"[red]✘ {msg}[/red]")


# ==========================================================
# LOGS / ATTACH
# ==========================================================

@run_cmd.command("logs", cls=RichHelpCommand)
@click.argument("target")
def logs(target):
    svc = ServiceManager()
    manager = StorageManager()
    projects = manager.load_projects().get("projects", [])

    pid = _resolve_project_id(target, projects)
    if pid is None:
        console.print("[red]Project not found.[/red]")
        return

    project = next(p for p in projects if p["id"] == pid)

    if svc.use_tmux:
        session = f"cwm:{project['id']}:{project['alias']}"
        console.print(f"[bold cyan]Attaching to tmux session {session}[/bold cyan]")
        _tmux_attach(session)
    else:
        from .service_manager import LOG_DIR
        log = LOG_DIR / f"{pid}.log"
        if log.exists():
            os.system(f"tail -f {log}")
        else:
            console.print("[yellow]No logs found[/yellow]")


# ==========================================================
# LAUNCH (alias of logs)
# ==========================================================

@run_cmd.command("launch", cls=RichHelpCommand)
@click.argument("target")
def launch(target):
    logs(target)


# ==========================================================
# KILL
# ==========================================================

@run_cmd.command("kill", cls=RichHelpCommand)
def kill_all():
    svc = ServiceManager()
    killed, msg = svc.nuke_all()
    console.print(f"[red]{msg}[/red]")


# ==========================================================
# GUI
# ==========================================================

@run_cmd.command("gui")
def gui():
    subprocess.Popen([sys.executable, "-m", "cwm.cli", "run", "_gui-internal"])
