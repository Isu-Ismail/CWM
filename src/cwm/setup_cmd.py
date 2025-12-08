import click
import os
import platform
from pathlib import Path

# Rich Imports
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.text import Text

from .rich_help import RichHelpCommand

console = Console()

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
            console.print(f"[dim]Created configuration file:[/dim] {file_path}")
        except Exception as e:
            console.print(f"[red]✖ Error creating file {file_path}:[/red] {e}")
            return

    # 2. Check for existing setup
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if "# --- CWM History Setup ---" in content:
            console.print(f"[green]✔ Success:[/green] {shell_name} is already configured in [bold]{file_path.name}[/bold].")
            return
    except Exception as e:
        console.print(f"[yellow]! Warning:[/yellow] Could not read {file_path}: {e}")

    # 3. Append
    console.print(f"[bold cyan]➜ Configuring {shell_name}...[/bold cyan]")
    console.print(f"  [dim]Target: {file_path}[/dim]")
    
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n" + block + "\n")
        console.print(f"[bold green]✔ Done![/bold green] Please restart your {shell_name} terminal.")
    except Exception as e:
        console.print(f"[red]✖ Error writing to file:[/red] {e}")


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
        # Default to legacy if Core folder missing
        target_profile = legacy_path / "Microsoft.PowerShell_profile.ps1"

    _append_config_block(target_profile, PWSH_CONFIG, "PowerShell")


@click.command("setup", cls=RichHelpCommand)
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
        console.print("\n[bold]Manual Setup Mode[/bold]")
        console.print("  [cyan]1)[/cyan] Bash [dim](Linux / Mac / Git Bash)[/dim]")
        console.print("  [cyan]2)[/cyan] Zsh [dim](Linux / Mac)[/dim]")
        console.print("  [cyan]3)[/cyan] PowerShell [dim](Windows)[/dim]")
        console.print("")
        
        try:
            choice = IntPrompt.ask("Select shell", choices=["1", "2", "3"])
            
            if choice == 1:
                _append_config_block(bashrc, BASH_CONFIG, "Bash")
            elif choice == 2:
                _append_config_block(zshrc, ZSH_CONFIG, "Zsh")
            elif choice == 3:
                _setup_powershell()
        except:
            pass
        return

    # --- 2. AUTO-DETECTION ---
    system = platform.system()
    
    # A. Windows Handling
    if system == "Windows":
        is_git_bash = "MSYSTEM" in os.environ or "bash" in os.environ.get("SHELL", "").lower()
        
        if is_git_bash:
            console.print("[bold cyan]➜ Detected Git Bash.[/bold cyan]")
            _append_config_block(bashrc, BASH_CONFIG, "Git Bash")
        else:
            console.print("[bold cyan]➜ Detected Windows System.[/bold cyan]")
            # Configure PowerShell
            _setup_powershell()
            return

    # B. Linux / Mac Handling
    else:
        # Check Shell Env
        shell_env = os.environ.get("SHELL", "")
        
        if "zsh" in shell_env:
            console.print("[bold cyan]➜ Detected Zsh.[/bold cyan]")
            _append_config_block(zshrc, ZSH_CONFIG, "Zsh")
        elif "bash" in shell_env:
            console.print("[bold cyan]➜ Detected Bash.[/bold cyan]")
            _append_config_block(bashrc, BASH_CONFIG, "Bash")
        else:
            # Fallback: Check files existence if ENV is ambiguous
            if zshrc.exists():
                console.print("[dim]Found .zshrc, configuring Zsh...[/dim]")
                _append_config_block(zshrc, ZSH_CONFIG, "Zsh")
            elif bashrc.exists():
                console.print("[dim]Found .bashrc, configuring Bash...[/dim]")
                _append_config_block(bashrc, BASH_CONFIG, "Bash")
            else:
                console.print("[yellow]! Could not auto-detect shell config file.[/yellow]")
                console.print("  Run [bold]cwm setup --force[/bold] to choose manually.")