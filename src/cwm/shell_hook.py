import os
import re
import subprocess
import platform
from pathlib import Path

HOOK_START = "# >>> CWM PROJECT HOOK START >>>"
HOOK_END   = "# <<< CWM PROJECT HOOK END <<<"

# =====================================================================================
# 1. SHELL DETECTION
# =====================================================================================
def detect_shell():
    """
    Detects which shell is currently running.
    Returns: "powershell", "gitbash", "bash", "zsh"
    """
    # Try using parent process (most accurate)
    try:
        import psutil
        parent = psutil.Process(os.getppid()).name().lower()
        if "pwsh" in parent or "powershell" in parent:
            return "powershell"
        if "zsh" in parent:
            return "zsh"
        if "bash" in parent:
            # Check for Git Bash
            if "msys" in os.environ.get("MSYSTEM", "").lower():
                return "gitbash"
            return "bash"
    except ImportError:
        pass

    # Fallback to ENV
    shell_env = os.environ.get("SHELL", "").lower()
    if os.name == "nt":
        if "bash" in shell_env: return "gitbash"
        return "powershell" # Default Windows
    
    if "zsh" in shell_env: return "zsh"
    return "bash" # Default Linux/Mac

# =====================================================================================
# 2. FILE EXTENSION HELPER (Fixes the .txt issue)
# =====================================================================================
def get_shell_extension(shell_type: str) -> str:
    if shell_type == "powershell":
        return ".ps1"
    if shell_type == "zsh":
        return ".zsh"
    return ".sh" # bash/gitbash

# =====================================================================================
# 3. PROFILE PATH RESOLUTION
# =====================================================================================
def get_powershell_profile_path() -> Path:
    """Gets the CurrentUserCurrentHost profile."""
    try:
        # Ask PowerShell for the path
        cmd = ["powershell", "-NoProfile", "-Command", "Write-Host $PROFILE.CurrentUserCurrentHost"]
        output = subprocess.check_output(cmd, text=True).strip()
        path = Path(output)
        return path
    except Exception:
        # Fallback
        return Path.home() / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"

def get_profile_path(shell_type: str) -> Path | None:
    if shell_type == "powershell":
        return get_powershell_profile_path()
    
    home = Path.home()
    if shell_type in ("bash", "gitbash"):
        # GitBash/Bash often uses .bashrc, or .bash_profile on Mac
        if (home / ".bash_profile").exists():
            return home / ".bash_profile"
        return home / ".bashrc"

    if shell_type == "zsh":
        return home / ".zshrc"

    return None

# =====================================================================================
# 4. HOOK GENERATORS (CLEAN - NO TIMESTAMPS)
# =====================================================================================
def generate_powershell_hook(project_history: Path) -> str:
    hist_path = str(project_history.resolve())
    
    return f"""
# --- CWM Hook (No Timestamps) ---
$global:CWM_Last = ""

function global:prompt {{
    $historyItem = Get-History -Count 1
    if ($historyItem) {{
        $last = $historyItem.CommandLine
        # Only save if different from last command to avoid duplicates
        if ($last -and ($last -ne $global:CWM_Last)) {{
            $global:CWM_Last = $last
            # Append raw command only
            Add-Content -LiteralPath "{hist_path}" -Value $last -Encoding utf8
        }}
    }}
    "PS $((Get-Location).Path)> "
}}
"""

def generate_bash_hook(project_history: Path) -> str:
    hist_path = project_history.resolve().as_posix()
    return f"""
# --- CWM Hook (No Timestamps) ---
__cwm_log_cmd() {{
    local last
    # Get last command, strip line numbers/whitespace
    last=$(history 1 | sed -E 's/^ *[0-9]+ +//')
    
    if [[ "$last" != "$CWM_LAST" && -n "$last" ]]; then
        CWM_LAST="$last"
        printf "%s\\n" "$last" >> "{hist_path}"
    fi
}}
export PROMPT_COMMAND="__cwm_log_cmd; $PROMPT_COMMAND"
"""

def generate_zsh_hook(project_history: Path) -> str:
    hist_path = project_history.resolve().as_posix()
    return f"""
# --- CWM Hook (No Timestamps) ---
cwm_log_cmd() {{
    local last
    last=$(fc -ln -1) # Get last command raw
    
    if [[ "$last" != "$CWM_LAST" && -n "$last" ]]; then
        CWM_LAST="$last"
        echo "$last" >> "{hist_path}"
    fi
}}
precmd_functions+=(cwm_log_cmd)
"""

def generate_hook_script(shell_type: str, project_history: Path) -> str:
    if shell_type == "powershell":
        return generate_powershell_hook(project_history)
    if shell_type in ("bash", "gitbash"):
        return generate_bash_hook(project_history)
    if shell_type == "zsh":
        return generate_zsh_hook(project_history)
    raise Exception(f"Unsupported shell: {shell_type}")

# =====================================================================================
# 5. INSTALLATION & REMOVAL
# =====================================================================================
def install_hook(shell_type: str, hook_file_path: Path) -> Path:
    profile = get_profile_path(shell_type)
    if not profile:
        raise Exception("Could not determine shell profile path.")

    # Create profile and parent dirs if missing
    if not profile.exists():
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.touch()

    content = profile.read_text(encoding="utf-8")
    if HOOK_START in content:
        return profile # Already installed

    # Create source command
    path_str = hook_file_path.resolve().as_posix()
    
    if shell_type == "powershell":
        injection = f"\n{HOOK_START}\n. '{path_str}'\n{HOOK_END}\n"
    else:
        injection = f"\n{HOOK_START}\nsource '{path_str}'\n{HOOK_END}\n"

    profile.write_text(content + injection, encoding="utf-8")
    return profile

def remove_hook(shell_type: str):
    profile = get_profile_path(shell_type)
    if not profile or not profile.exists():
        return

    content = profile.read_text(encoding="utf-8")
    # Regex to remove the block
    pattern = re.compile(rf"{re.escape(HOOK_START)}.*?{re.escape(HOOK_END)}\s*", re.DOTALL)
    new_content = re.sub(pattern, "", content)
    
    profile.write_text(new_content, encoding="utf-8")