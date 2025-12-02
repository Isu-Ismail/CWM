# cwm/setup_cmd.py
import click
import os
import platform
from pathlib import Path

# --- CONFIGURATION BLOCKS ---

# Bash: Instant Sync + Ignore Duplicates/Spaces
BASH_CONFIG = """
# --- CWM History Setup ---
# Append to history file immediately, don't overwrite
shopt -s histappend
# Instant write to disk after every command
export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"
# Ignore duplicate commands and commands starting with space
export HISTCONTROL=ignoreboth
"""

# Zsh: The specific optimization block you requested
ZSH_CONFIG = """
# --- CWM History Setup ---
HISTFILE="$HOME/.zsh_history"
# Keep 50k commands in memory and on disk
HISTSIZE=50000
SAVEHIST=50000
# Write commands immediately after each execution
setopt INC_APPEND_HISTORY
# Ignore duplicates and commands starting with space
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
# Disable extended timestamp format (Clean raw commands)
unsetopt EXTENDED_HISTORY
setopt NO_EXTENDED_HISTORY
"""

# PowerShell: Native Deduplication & Incremental Save
PWSH_CONFIG = """
# --- CWM History Setup ---
# Ensure commands are saved immediately
Set-PSReadLineOption -HistorySaveStyle SaveIncrementally
# Prevent duplicates in history
Set-PSReadLineOption -HistoryNoDuplicates
"""

def _append_config_block(file_path: Path, block: str, shell_name: str):
    """Generic helper to append config blocks safely."""
    
    # 1. Create file if missing
    if not file_path.exists():
        try:
            if not file_path.parent.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
            click.echo(f"Created configuration file: {file_path}")
        except Exception as e:
            click.echo(f"Error creating file {file_path}: {e}", err=True)
            return

    # 2. Check for existing setup
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if "# --- CWM History Setup ---" in content:
            click.echo(f"Success: {shell_name} is already configured in {file_path.name}.")
            return
    except Exception as e:
        click.echo(f"Warning: Could not read {file_path}: {e}")

    # 3. Append
    click.echo(f"Configuring {shell_name} at: {file_path}")
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n" + block + "\n")
        click.echo(f"Done! Please restart your {shell_name} terminal.")
    except Exception as e:
        click.echo(f"Error writing to file: {e}", err=True)


def _setup_powershell():
    """Locates and configures the PowerShell profile."""
    # Standard location for current user, current host
    # Windows: Documents\PowerShell\Microsoft.PowerShell_profile.ps1
    
    docs = Path.home() / "Documents"
    
    # Check for 'PowerShell' vs 'WindowsPowerShell' folder (PS Core vs Legacy)
    # We prioritize PowerShell (Core/v7) if folder exists, else WindowsPowerShell
    ps_path = docs / "PowerShell"
    legacy_path = docs / "WindowsPowerShell"
    
    target_profile = None
    
    if ps_path.exists():
        target_profile = ps_path / "Microsoft.PowerShell_profile.ps1"
    else:
        # Default to legacy if Core folder missing, or create Core if on modern OS?
        # Let's try to find where the user actually is.
        # Since we can't easily ask the running shell process for $PROFILE from python easily without subprocess,
        # We will create the Legacy one as fallback which usually works for built-in PS.
        target_profile = legacy_path / "Microsoft.PowerShell_profile.ps1"

    _append_config_block(target_profile, PWSH_CONFIG, "PowerShell")


@click.command("setup")
@click.option("--force", is_flag=True, help="Manually select shell and force setup.")
def setup_cmd(force):
    """
    Configures shell for instant history sync & deduplication.
    Supports: Bash, Zsh, and PowerShell.
    """
    home = Path.home()
    bashrc = home / ".bashrc"
    zshrc = home / ".zshrc"
    
    # --- 1. FORCE MODE ---
    if force:
        click.echo("--- Manual Setup ---")
        click.echo("1. Bash (Linux / Mac / Git Bash)")
        click.echo("2. Zsh (Linux / Mac)")
        click.echo("3. PowerShell (Windows)")
        
        try:
            choice = click.prompt("Select shell", type=int)
            if choice == 1:
                _append_config_block(bashrc, BASH_CONFIG, "Bash")
            elif choice == 2:
                _append_config_block(zshrc, ZSH_CONFIG, "Zsh")
            elif choice == 3:
                _setup_powershell()
            else:
                click.echo("Invalid choice.")
        except:
            pass
        return

    # --- 2. AUTO-DETECTION ---
    system = platform.system()
    
    # A. Windows Handling
    if system == "Windows":
        is_git_bash = "MSYSTEM" in os.environ or "bash" in os.environ.get("SHELL", "").lower()
        
        if is_git_bash:
            click.echo("Detected Git Bash.")
            _append_config_block(bashrc, BASH_CONFIG, "Git Bash")
        else:
            click.echo("Detected Windows System.")
            # Configure PowerShell
            _setup_powershell()
            return

    # B. Linux / Mac Handling
    else:
        # Check Shell Env
        shell_env = os.environ.get("SHELL", "")
        
        if "zsh" in shell_env:
            click.echo("Detected Zsh.")
            _append_config_block(zshrc, ZSH_CONFIG, "Zsh")
        elif "bash" in shell_env:
            click.echo("Detected Bash.")
            _append_config_block(bashrc, BASH_CONFIG, "Bash")
        else:
            # Fallback: Check files existence if ENV is ambiguous
            if zshrc.exists():
                click.echo("Found .zshrc, configuring Zsh...")
                _append_config_block(zshrc, ZSH_CONFIG, "Zsh")
            elif bashrc.exists():
                click.echo("Found .bashrc, configuring Bash...")
                _append_config_block(bashrc, BASH_CONFIG, "Bash")
            else:
                click.echo("Could not auto-detect shell config file.")
                click.echo("Run 'cwm setup --force' to choose manually.")