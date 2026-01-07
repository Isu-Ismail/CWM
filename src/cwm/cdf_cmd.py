import os
import sys
import click
import pyperclip
import datetime
import shutil
import shlex
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from sqlalchemy import create_engine, Column, String, Integer, DateTime, desc
from sqlalchemy.orm import declarative_base, sessionmaker

# Relative imports with fallbacks
try:
    from .rich_help import RichHelpCommand, RichHelpGroup
    from .utils import GLOBAL_CWM_BANK
    from .storage_manager import StorageManager
except (ImportError, ValueError):
    from rich_help import RichHelpCommand, RichHelpGroup
    from utils import GLOBAL_CWM_BANK
    from storage_manager import StorageManager

# --- DATABASE SETUP ---
DB_DIR = GLOBAL_CWM_BANK / "data"
DB_PATH = f"sqlite:///{DB_DIR / 'folder_index.db'}"
Base = declarative_base()
console = Console()

class Directory(Base):
    __tablename__ = 'directories'
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    path = Column(String, unique=True)
    depth = Column(Integer)

class History(Base):
    __tablename__ = 'history'
    id = Column(Integer, primary_key=True)
    path = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Ensure data directory exists
DB_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(DB_PATH)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# ==========================================================
# HELPERS
# ==========================================================

def record_history(path):
    """Saves the current path to the history table, keeping only the last 10."""
    session = Session()
    try:
        new_hist = History(path=path)
        session.add(new_hist)
        # Delete entries older than the top 10
        old_entries = session.query(History).order_by(desc(History.timestamp)).offset(10).all()
        for entry in old_entries:
            session.delete(entry)
        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()

def get_ignored_folders(root_path):
    """Reads .cwmignore and returns a set of folder names to skip."""
    ignore_file = Path(root_path) / ".cwmignore"
    ignored = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cwm"}
    if ignore_file.exists():
        try:
            lines = ignore_file.read_text().splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    ignored.add(line)
        except Exception:
            pass
    return ignored

def _launch_terminal(path: str):
    """Launches a new detached terminal window."""
    try:
        if os.name == 'nt':  # Windows
            if shutil.which("wt"):
                subprocess.Popen(["wt", "-d", path], shell=True)
            else:
                subprocess.Popen(["start", "powershell", "-NoExit", "-Command", f"cd '{path}'"], shell=True)
        elif sys.platform == "darwin":  # macOS
            subprocess.Popen(["open", "-a", "Terminal", path])
        else:  # Linux
            term = shutil.which("gnome-terminal") or shutil.which("konsole") or shutil.which("xterm")
            if term:
                subprocess.Popen([term], cwd=path)
    except Exception as e:
        console.print(f"[red]Failed to launch terminal: {e}[/red]")

def _launch_editor(path: str):
    """Launches the default editor configured in StorageManager."""
    manager = StorageManager()
    config = manager.get_config()
    editor_config = config.get("default_editor", "code")
    
    try:
        args = shlex.split(editor_config)
        if not args:
            args = ["code"]
        
        if shutil.which(args[0]):
            # Append the path to the editor command
            subprocess.Popen(args + [path], shell=(os.name == 'nt'))
        else:
            console.print(f"[yellow]Editor '{args[0]}' not found. Opening terminal instead.[/yellow]")
            _launch_terminal(path)
    except Exception as e:
        _launch_terminal(path)

# ==========================================================
# CLI COMMANDS
# ==========================================================

@click.group("cdf", cls=RichHelpGroup)
def cdf_cmd():
    """Fast directory navigation with fuzzy search and jump options."""
    pass

@cdf_cmd.command("find", cls=RichHelpCommand)
@click.argument('query')
@click.option('--depth', '-d', default='all', help="Search depth limit (integer or 'all').")
@click.option('--open', '-o', type=click.Choice(['code', 'term', 'both']), help="Directly open the folder.")
def find(query, depth, open):
    """Search for a directory and [cd] or [open] it."""
    session = Session()
    filters = [Directory.name.like(f"%{query}%")]
    if depth != 'all':
        try:
            filters.append(Directory.depth <= int(depth))
        except ValueError:
            pass

    results = session.query(Directory).filter(*filters).limit(10).all()

    if not results:
        console.print(f"[bold red]✘ No results found[/] for '{query}'.")
        return

    table = Table(title=f"CDF Results for '{query}'", box=None)
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Folder", style="magenta")
    table.add_column("Path", style="dim")

    for i, res in enumerate(results, 1):
        table.add_row(str(i), res.name, res.path)

    console.print(table)
    
    choice = click.prompt("Select ID or [q] to quit", default="q")
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(results):
            dest = results[idx].path
            record_history(os.getcwd())

            if open == 'code':
                _launch_editor(dest)
                console.print(f"[green]✔ Opening {dest} in Editor...[/green]")
            elif open == 'term':
                _launch_terminal(dest)
                console.print(f"[green]✔ Opening {dest} in New Terminal...[/green]")
            elif open == 'both':
                _launch_editor(dest)
                _launch_terminal(dest)
                console.print(f"[green]✔ Opening {dest} in Both...[/green]")
            else:
                pyperclip.copy(f"cd \"{dest}\"")
                console.print(f"[bold green]✔ Copied to clipboard![/] (cd \"{dest}\")")

@cdf_cmd.command("index", cls=RichHelpCommand)
@click.argument('path', type=click.Path(exists=True))
@click.option('--depth', '-d', default=None, help="Max depth to index.")
def index(path, depth):
    """Scan and index directories directly in this terminal."""
    session = Session()
    target = Path(path).resolve()
    base_depth = len(target.parts)
    max_d = int(depth) if depth else float('inf')
    ignored_names = get_ignored_folders(target)
    
    count = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        index_task = progress.add_task(f"[bold blue]Indexing {target.name}...", total=None)
        
        for root, dirs, _ in os.walk(target):
            current_path = Path(root)
            current_depth = len(current_path.parts) - base_depth
            
            if current_depth >= max_d:
                dirs[:] = [] 
                continue

            # In-place filter
            dirs[:] = [d for d in dirs if d not in ignored_names]

            for d in dirs:
                full_path = str(current_path / d)
                session.merge(Directory(name=d, path=full_path, depth=current_depth + 1))
                count += 1
                
                if count % 100 == 0:
                    progress.update(index_task, description=f"[bold blue]Indexed {count} folders...")
                    session.commit()
    
    session.commit()
    console.print(f"\n[bold green]✔ Success![/] Total indexed: [cyan]{count}[/cyan]")

@cdf_cmd.command("back", cls=RichHelpCommand)
@click.option('--list', '-l', is_flag=True, help="List history.")
def back(list):
    """Jump back to previous locations."""
    session = Session()
    hist_list = session.query(History).order_by(desc(History.timestamp)).all()
    
    if not hist_list:
        console.print("[yellow]No history found.[/yellow]")
        return

    if list:
        table = Table(title="Recent Locations")
        table.add_column("ID", justify="center", style="cyan")
        table.add_column("Path", style="green")
        for i, h in enumerate(hist_list):
            table.add_row(str(i+1), h.path)
        console.print(table)
        
        val = click.prompt("Select ID", type=int)
        if 1 <= val <= len(hist_list):
            dest = hist_list[val-1].path
            pyperclip.copy(f"cd \"{dest}\"")
            console.print("[green]✔ Path copied.[/green]")
    else:
        dest = hist_list[0].path
        pyperclip.copy(f"cd \"{dest}\"")
        console.print(f"[green]✔ Copied last location:[/] {dest}")

if __name__ == "__main__":
    cdf_cmd()