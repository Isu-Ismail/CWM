import os
import json
import platform
from pathlib import Path
import click
from typing import Tuple
import re

GLOBAL_CWM_BANK = Path(click.get_app_dir("cwm"))
CWM_BANK_NAME = ".cwm"

DEFAULT_AI_INSTRUCTION = """You are DevBot, a senior developer's assistant. Follow these rules:
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

DEFAULT_CONFIG = {
    "history_file": None,
    "project_markers": [],
    "code_theme": "monokai",
    "ai_instruction": None
}

FILE_ATTRIBUTE_HIDDEN = 0x02

# --- VALIDATION HELPERS ---

def looks_invalid_command(cmd: str) -> bool:
    cmd = cmd.strip()
    if not cmd: return True
    if not cmd.isascii() or any(ord(c) < 32 for c in cmd): return True
    if not re.search(r"[A-Za-z0-9]", cmd): return True
    if cmd.count('"') % 2 != 0: return True
    if cmd.count("'") % 2 != 0: return True
    if cmd.startswith("|") or cmd.startswith(">") or cmd.startswith("<") or cmd.startswith("#"): return True
    if cmd.isdigit(): return True
    if "|| |" in cmd or "||| " in cmd: return True
    if re.fullmatch(r"[\W_]+", cmd): return True
    if re.search(r"[><]{3,}", cmd): return True
    return False

def clean_token(text: str) -> str:
    """Removes whitespace and surrounding quotes."""
    if not text: return ""
    return text.strip().strip('"').strip("'")

# --- FILESYSTEM HELPERS ---

def _ensure_dir(path: Path):
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

def make_hidden(path: Path):
    """Hide folder on Windows."""
    if platform.system() == "Windows":
        try:
            import ctypes
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
        except:
            pass

def safe_create_cwm_folder(folder_path: Path, repair=False) -> bool:
    """
    Creates CWM bank structure.
    - GLOBAL: Creates config.json, data/ (saved_cmds, projects, backup).
    - LOCAL: Creates ONLY .cwm/ folder and watch_session.json.
    """
    try:
        _ensure_dir(folder_path)
        make_hidden(folder_path)

        is_global = (folder_path == GLOBAL_CWM_BANK)

        # --- GLOBAL BANK SETUP ---
        if is_global:
            data_path = folder_path / "data"
            backup_path = data_path / "backup"
            
            _ensure_dir(data_path)
            _ensure_dir(backup_path)

            # Files required ONLY in Global Bank
            required_files = {
                "saved_cmds.json": {"last_saved_id": 0, "commands": []},
                "fav_cmds.json": [],
                "projects.json": {"last_id": 0, "last_group_id": 0, "projects": [], "groups": []},
                # Watch session placeholder for global context
                "watch_session.json": {"isWatching": False}
            }

            # Global Config
            config_file = folder_path / "config.json"
            if not config_file.exists():
                config_file.write_text(json.dumps(DEFAULT_CONFIG, indent=4))

            # Create Data Files
            for fname, default_value in required_files.items():
                file = data_path / fname
                if not file.exists():
                    file.write_text(json.dumps(default_value, indent=4))
                    if repair:
                        click.echo(f"Global file {fname} restored.")

        # --- LOCAL BANK SETUP ---
        else:
            # Local banks only need watch session storage
            ws_file = folder_path / "watch_session.json"
            if not ws_file.exists():
                default_session = {
                    "isWatching": False,
                    "shell": None,
                    "hook_file": None,
                    "started_at": None
                }
                ws_file.write_text(json.dumps(default_session, indent=4))

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

    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" /
                              "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / "AppData" / "Roaming" / "Microsoft" /
                          "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt")
        candidates.append(home / ".bash_history")  # Git Bash

    candidates.append(home / ".bash_history")
    candidates.append(home / ".zsh_history")
    candidates.append(home / ".local" / "share" / "powershell" /
                      "PSReadLine" / "ConsoleHost_history.txt")

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
    1. Global Config (Source of Truth)
    2. Auto-Detection (OS/Shell)
    """
    # Check Global Config
    global_bank = GLOBAL_CWM_BANK
    if global_bank.exists():
        override = _read_config_for_history(global_bank)
        if override:
            return override

    # Auto-Detect
    candidates = get_all_history_candidates()
    return candidates[0] if candidates else None

def tail_read_last_n_lines(path, n, chunk_size=4096):
    """Correct tail implementation that does NOT reverse characters."""
    if isinstance(path, Path): path = str(path)
    if not os.path.exists(path): return []

    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        data = bytearray()
        lines_found = 0
        remaining = file_size

        while remaining > 0 and lines_found <= n:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)
            data[:0] = chunk 
            lines_found += chunk.count(b"\n")

        text = data.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        return lines[-n:]

def read_powershell_history() -> Tuple[list[str], int]:
    path = get_history_file_path()
    if not path or not path.exists():
        return [], 0

    lines = tail_read_last_n_lines(path, 5000)
    try:
        total_count = sum(1 for _ in open(path, 'rb'))
    except:
        total_count = len(lines)

    cleaned = [ln.rstrip("\n") for ln in lines if ln.strip()]
    return cleaned, total_count

def is_cwm_call(s: str) -> bool:
    s = s.strip()
    return s.startswith("cwm ") or s == "cwm"

def is_history_sync_enabled() -> bool:
    if os.name == 'nt': return True 
    home = Path.home()
    bashrc = home / ".bashrc"
    zshrc = home / ".zshrc"

    if bashrc.exists():
        try:
            content = bashrc.read_text(encoding="utf-8", errors="ignore")
            if "history -a" in content and "PROMPT_COMMAND" in content:
                return True
        except: pass

    if zshrc.exists():
        try:
            content = zshrc.read_text(encoding="utf-8", errors="ignore")
            if "inc_append_history" in content.lower() or "share_history" in content.lower():
                return True
        except: pass

    return False

def get_history_line_count() -> int:
    path = get_history_file_path()
    if not path or not path.exists(): return 0
    try:
        return sum(1 for _ in open(path, 'rb'))
    except: return 0

def get_clear_history_command() -> str:
    path = get_history_file_path()
    if not path:
        if os.name == 'nt': return "Clear-Content (Get-PSReadlineOption).HistorySavePath"
        return "cat /dev/null > ~/.bash_history && history -c"

    if "ConsoleHost_history.txt" in path.name:
        return "Clear-Content (Get-PSReadLineOption).HistorySavePath -Force"
    elif ".zsh_history" in path.name:
        return f"cat /dev/null > {path}; fc -p {path}"
    else:
        return f"cat /dev/null > {path} && history -c"

# --- SAFETY LOGIC ---

BANNED_EXECUTABLES = {
    "rm", "del", "rd", "rmdir", "format", "fdisk", "mkfs", "sudo", "su"
}

DANGER_SUBSTRINGS = [
    ":(){ :|:& };:", # Fork bomb
    "> /dev/sda",    # Disk overwrite attempts
    "cwm ",          # Prevent recursion
]

def is_safe_startup_cmd(cmd_input, project_root: Path = None) -> bool:
    """
    Validator for startup commands.
    Blocks dangerous executables and specific patterns.
    """
    if not cmd_input: return False

    cmds_to_check = []
    if isinstance(cmd_input, list):
        cmds_to_check = cmd_input
    else:
        cmds_to_check = [str(cmd_input)]

    for cmd in cmds_to_check:
        # Strip whitespace AND quotes before validation
        cmd = cmd.strip().strip('"').strip("'")
        if not cmd: continue
        
        cmd_lower = cmd.lower()

        # 1. Check Substrings
        if any(bad in cmd_lower for bad in DANGER_SUBSTRINGS):
            return False

        # 2. Tokenize to check the Executable (First word)
        parts = cmd.split()
        if not parts: continue
        
        executable = parts[0].lower()
        
        # Check against banned list
        if executable in BANNED_EXECUTABLES:
            return False

        # 3. Specific Python Safety Checks
        if project_root and len(parts) > 1 and executable in ("python", "python3", "py"):
            script = parts[1]
            if not script.startswith("-"):
                try:
                    # Basic directory traversal check
                    if ".." in script:
                        return False
                except: pass

    return True