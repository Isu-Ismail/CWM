# cwm/utils.py
import os
import json
import platform
from pathlib import Path
import click
import shutil
from typing import Tuple

CWM_BANK_NAME = ".cwm"

def _ensure_dir(p: Path):
    """Create folder p if not exists."""
    p.mkdir(parents=True, exist_ok=True)

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

# --- Shell History functions (OS AWARE) ---

# RENAMED to public function (removed leading underscore)
def get_history_file_path() -> Path | None:
    """Finds the active shell history file (PowerShell, Bash, or Zsh)."""
    system = platform.system()
    home = Path.home()
    candidates = []

    # --- WINDOWS PATHS ---
    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / ".bash_history") # Git Bash

    # --- LINUX & MACOS PATHS ---
    else:
        # 1. Bash (Standard Linux)
        candidates.append(home / ".bash_history")
        # 2. Zsh (Common on Mac/Linux)
        candidates.append(home / ".zsh_history")
        # 3. PowerShell Core (pwsh) fallback
        candidates.append(home / ".local" / "share" / "powershell" / "PSReadLine" / "ConsoleHost_history.txt")

    for path in candidates:
        if path.exists():
            return path
    return None

def read_powershell_history() -> Tuple[list[str], int]:
    """Load shell history (works for Bash, Zsh, and PowerShell)."""
    path = get_history_file_path() # Uses the new public name
    if not path:
        return [], 0
        
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        clean_lines = [ln.rstrip("\n") for ln in lines if ln.strip()]
        
        # Simple Zsh timestamp cleaning
        final_lines = []
        for ln in clean_lines:
            if ln.startswith(": ") and ";" in ln:
                parts = ln.split(";", 1)
                if len(parts) == 2:
                    final_lines.append(parts[1])
                else:
                    final_lines.append(ln)
            else:
                final_lines.append(ln)
                
        return final_lines, len(final_lines)
    except Exception:
        return [], 0

def is_cwm_call(s: str) -> bool:
    s = s.strip()
    return s.startswith("cwm ") or s == "cwm"


def is_history_sync_enabled() -> bool:
    """Checks if the shell is configured to sync history instantly."""
    if os.name == 'nt':
        return True # Windows (PowerShell) handles this by default
        
    home = Path.home()
    bashrc = home / ".bashrc"
    zshrc = home / ".zshrc"
    
    # Check bashrc
    if bashrc.exists():
        try:
            content = bashrc.read_text(encoding="utf-8", errors="ignore")
            if "history -a" in content and "PROMPT_COMMAND" in content:
                return True
        except:
            pass

    # Check zshrc (simple check)
    if zshrc.exists():
        try:
            content = zshrc.read_text(encoding="utf-8", errors="ignore")
            if "inc_append_history" in content.lower() or "share_history" in content.lower():
                return True
        except:
            pass
            
    return False