# cwm/utils.py
import os
import json
from pathlib import Path
import click
import shutil
from typing import Tuple # <-- Make sure this is imported

CWM_BANK_NAME = ".cwm"

def _ensure_dir(p: Path):
    """Create folder p if not exists."""
    p.mkdir(exist_ok=True)

def safe_create_cwm_folder(folder_path: Path, repair=False) -> bool:
    """
    Creates the CWM bank structure.
    """
    try:
        data_path = folder_path / "data"
        backup_path = data_path / "backup"
        _ensure_dir(folder_path)
        _ensure_dir(data_path)
        _ensure_dir(backup_path)

        # Defines all files needed for a bank
        required_files = {
            "commands.json": {"last_command_id": 0, "commands": []},
            "saved_cmds.json": {"last_saved_id": 0, "commands": []},
            "fav_cmds.json": [],
            "history.json": {"last_sync_id": 0, "commands": []},
            "watch_session.json": {"isWatching": False, "startLine": 0}
        }

        config_file = folder_path / "config.json"
        if not config_file.exists():
            config_file.write_text("{}")
        
        for fname, default_value in required_files.items():
            file = data_path / fname
            if not file.exists():
                file.write_text(json.dumps(default_value, indent=2))
                if repair:
                    click.echo(f"{fname} missing... recreated.")
        return True
    except Exception as e:
        click.echo(f"Error creating CWM folder: {e}", err=True)
        return False


def has_write_permission(path: Path) -> bool:
    try:
        test = path / ".__cwm_test__"
        test.write_text("test")
        test.unlink()
        return True
    except:
        return False

def is_path_literally_inside_bank(path: Path) -> bool:
    current = path.resolve()
    return CWM_BANK_NAME in current.parts

def find_nearest_bank_path(start_path: Path) -> Path | None:
    current = start_path.resolve()
    for parent in [current] + list(current.parents):
        candidate = parent / CWM_BANK_NAME
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None

# --- PowerShell History functions ---

def _get_powershell_history_path() -> Path | None:
    appdata = os.getenv("APPDATA")
    home = Path.home()
    candidates = [
        Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        Path(appdata) / "Microsoft" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        home / "AppData" / "Roaming" / "Microsoft" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None

# --- THIS IS THE FIX ---
def read_powershell_history() -> Tuple[list[str], int]:
    """Load PSReadLine system history.
    
    Returns:
        (list of lines, total line count)
    """
    path = _get_powershell_history_path()
    if not path:
        click.echo("Error: Could not find PowerShell history file.", err=True)
        return [], 0
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        # Return both the lines and the original length
        return [ln.rstrip("\n") for ln in lines], len(lines)
    except Exception as e:
        click.echo(f"Error reading PowerShell history: {e}", err=True)
        return [], 0
# --- END OF FIX ---

def is_cwm_call(s: str) -> bool:
    s = s.strip()
    return s.startswith("cwm ") or s == "cwm"