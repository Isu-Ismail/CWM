import os
import json
import platform
from pathlib import Path
import click
from typing import Tuple

CWM_BANK_NAME = ".cwm"
INSTRUCTION_FILE = "instruction.txt"  #

DEFAULT_AI_INSTRUCTION="""You are DevBot, a senior developer's assistant. Follow these rules:
*if user aks hello reply hello how can i help you today like this polite and simple.
*Keep responses short, precise, and actionable.
* Use bullet points or numbered steps for instructions.
* When code is needed, show only the command or code on the next line without specifying language.
* If something must be run in terminal, say "run this in terminal:" above the code.
* No long intros, no long explanations unless asked.
* If user gives code, analyze it and give direct fixes.
* Do not use words like "comments" in explanations.
* Do not use bold or extra markdown styling.
* If a link is needed for download, include the link directly.
* For navigation steps, use arrows like: settings -> display -> wallpaper.
* For errors, check context similar to StackOverflow or official docs and give the simplest fix.
* If user asks general questions (time, date, simple facts), give a one-line answer.
* If no answer is found, say: no answer found.
* Keep output token usage low while keeping enough detail to understand.
"""

# Master Defaults (Used by StorageManager for fallbacks)
DEFAULT_CONFIG = {
    "history_file": None,
    "project_markers": [".git", ".cwm", ".cwm-project.txt"],
    "default_editor": "code",
    "default_terminal": None,
    "suppress_history_warning": False,
    "code_theme": "monokai",
    
    # --- AI Configuration (Nested) ---
    "gemini": {
        "model": None,
        "key": None
    },
    "openai": {
        "model": None,
        "key": None
    },
    "local_ai": {
        "model": None
    },
    "ai_instruction": DEFAULT_AI_INSTRUCTION
}

FILE_ATTRIBUTE_HIDDEN = 0x02


def _ensure_dir(path: Path):
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

def make_hidden(path: Path):
    """
    Sets the 'Hidden' attribute on Windows.
    Safe to call repeatedly on folders or files.
    """
    if os.name == 'nt':
        try:
            import ctypes
            # Convert Path to string and set attribute
            # This hides the folder from standard Explorer views
            ret = ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            pass

def safe_create_cwm_folder(folder_path: Path, repair=False) -> bool:
    """
    Creates the CWM bank structure and ensures it is HIDDEN.
    Works for both Global (AppData) and Local (.cwm) banks.
    """
    try:
        # 1. Create the main folder
        _ensure_dir(folder_path)
        
        # 2. FORCE HIDE IT (Applies to both Global and Local)
        make_hidden(folder_path)

        data_path = folder_path / "data"
        backup_path = data_path / "backup"
        
        _ensure_dir(data_path)
        _ensure_dir(backup_path)

        required_files = {
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

# --- HISTORY HELPERS ---

def get_all_history_candidates() -> list[Path]:
    """Returns a list of all valid history files found on the system."""
    system = platform.system()
    home = Path.home()
    candidates = []

    # --- Windows Candidates ---
    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / ".bash_history") # Git Bash

    # --- Linux/Mac Candidates ---
    candidates.append(home / ".bash_history")
    candidates.append(home / ".zsh_history")
    candidates.append(home / ".local" / "share" / "powershell" / "PSReadLine" / "ConsoleHost_history.txt")
    
    # Filter for existence
    existing_files = []
    seen = set()
    for p in candidates:
        if p.exists() and str(p) not in seen:
            existing_files.append(p)
            seen.add(str(p))
            
    return existing_files

def _read_config_for_history(bank_path: Path) -> Path | None:
    """Helper to read history_file from a specific bank's config."""
    try:
        config_path = bank_path / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
            configured = config.get("history_file")
            if configured:
                p = Path(configured)
                if p.exists():
                    return p
    except Exception:
        pass
    return None

def get_history_file_path() -> Path | None:
    """
    Finds the active history file.
    Priority:
    1. Config in Local Bank
    2. Config in Global Bank (The Fix!)
    3. Auto-Detection (OS/Shell)
    """
    
    # 1. Check Local Bank Config
    local_bank = find_nearest_bank_path(Path.cwd())
    if local_bank:
        override = _read_config_for_history(local_bank)
        if override: return override

    # 2. Check Global Bank Config (FIX)
    global_bank = Path(click.get_app_dir("cwm"))
    if global_bank.exists():
        override = _read_config_for_history(global_bank)
        if override: return override

    # 3. Auto-Detection (Fallback)
    system = platform.system()
    home = Path.home()
    candidates = []

    if system == "Windows":
        # Check for Git Bash environment variable
        is_git_bash = "MSYSTEM" in os.environ or "bash" in os.environ.get("SHELL", "").lower()
        
        if is_git_bash:
            candidates.append(home / ".bash_history")
        
        # PowerShell
        appdata = os.getenv("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        
        # Fallback Bash
        if not is_git_bash:
            candidates.append(home / ".bash_history")

    else:
        # Linux/Mac Logic
        shell = os.environ.get("SHELL", "")
        if "zsh" in shell:
            candidates.append(home / ".zsh_history")
            candidates.append(home / ".bash_history")
        else:
            candidates.append(home / ".bash_history")
            candidates.append(home / ".zsh_history")
        candidates.append(home / ".local" / "share" / "powershell" / "PSReadLine" / "ConsoleHost_history.txt")

    for path in candidates:
        if path.exists():
            return path
            
    return None

def read_powershell_history() -> Tuple[list[str], int]:
    """
    Reads the history file ONCE and returns both content and count.
    Returns: (list_of_lines, total_line_count)
    """
    path = get_history_file_path()
    if not path:
        return [], 0
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        # Return the lines (stripped) AND the raw count
        return [ln.rstrip("\n") for ln in lines], len(lines)
    except Exception:
        return [], 0

def is_cwm_call(s: str) -> bool:
    s = s.strip()
    return s.startswith("cwm ") or s == "cwm"

# --- Sync Check for Linux ---
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

# --- NEW: Get History Line Count (Optimized) ---
def get_history_line_count() -> int:
    """Fast check of history file length."""
    path = get_history_file_path()
    if not path or not path.exists():
        return 0
    try:
        # Quick line count without loading entire file into memory
        return sum(1 for _ in open(path, 'rb'))
    except:
        return 0

# --- NEW: Get Clear History Command ---
def get_clear_history_command() -> str:
    """Returns the command to clear history based on the active shell."""
    path = get_history_file_path()
    
    if not path:
        if os.name == 'nt':
            return "Clear-Content (Get-PSReadlineOption).HistorySavePath"
        return "cat /dev/null > ~/.bash_history && history -c"

    if "ConsoleHost_history.txt" in path.name:
        return "Clear-Content (Get-PSReadLineOption).HistorySavePath -Force"
    elif ".zsh_history" in path.name:
        return f"cat /dev/null > {path}; fc -p {path}"
    else:
        return f"cat /dev/null > {path} && history -c"