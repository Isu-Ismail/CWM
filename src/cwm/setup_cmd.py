# cwm/setup_cmd.py
import click
import os
from pathlib import Path

BASH_SYNC_LINE = 'export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"'

def _install_bash_sync(config_path: Path):
    """Helper to safely append the sync line to a config file."""
    
    # 1. Create file if it doesn't exist (common in Git Bash)
    if not config_path.exists():
        try:
            config_path.touch()
            click.echo(f"Created new config file at: {config_path}")
        except Exception as e:
            click.echo(f"Error creating file: {e}", err=True)
            return

    # 2. Check for duplicates
    try:
        content = config_path.read_text(encoding="utf-8", errors="ignore")
        if "history -a" in content and "PROMPT_COMMAND" in content:
            click.echo(f"Success: {config_path.name} is already configured for instant history!")
            return
    except Exception as e:
        click.echo(f"Warning: Could not read {config_path}: {e}")

    # 3. Append
    click.echo(f"Target Config: {config_path}")
    click.echo(f"Action: Appending history sync command.")
    
    try:
        with open(config_path, "a", encoding="utf-8") as f:
            f.write(f"\n# --- CWM History Sync ---\n{BASH_SYNC_LINE}\n")
        
        click.echo(f"Done! Please restart your terminal or run: source ~/{config_path.name}")
    except Exception as e:
        click.echo(f"Error writing to file: {e}", err=True)


@click.command("setup")
@click.option("--force", is_flag=True, help="Manually select shell and force setup.")
def setup_cmd(force):
    """
    Configures shell for instant history sync (Linux/Mac/GitBash).
    
    Standard Windows PowerShell does not need this setup.
    """
    
    home = Path.home()
    bashrc = home / ".bashrc"
    zshrc = home / ".zshrc"
    
    # --- 1. FORCE MODE (User Selection) ---
    if force:
        click.echo("--- Manual Setup ---")
        click.echo("Select your shell type:")
        click.echo("1. Bash (Linux / macOS / Windows Git Bash)")
        click.echo("2. Zsh (macOS / Linux)")
        click.echo("3. Windows PowerShell")
        
        choice = click.prompt("Enter number", type=int)
        
        if choice == 1:
            # Force Bash setup
            _install_bash_sync(bashrc)
            return
        elif choice == 2:
            # Force Zsh setup
            _install_bash_sync(zshrc)
            return
        elif choice == 3:
            click.echo("Windows PowerShell syncs history automatically. No setup needed.")
            return
        else:
            click.echo("Invalid choice.")
            return

    # --- 2. AUTO-DETECTION ---
    
    # Check for Git Bash specifically (Windows)
    is_git_bash = "MSYSTEM" in os.environ or "bash" in os.environ.get("SHELL", "").lower()

    target_conf = None
    
    # Prioritize Zsh if present, then Bash
    if zshrc.exists():
        target_conf = zshrc
    elif bashrc.exists():
        target_conf = bashrc
    elif is_git_bash:
        # If it's Git Bash but no file exists yet, default to .bashrc
        target_conf = bashrc

    # --- 3. Handle Standard Windows PowerShell ---
    # Only if NOT Git Bash and NO config files found
    if os.name == 'nt' and not is_git_bash and not target_conf:
        click.echo("Success: Windows PowerShell syncs history automatically.")
        click.echo("No setup required.")
        return

    # --- 4. Handle Bash/Zsh (Linux, Mac, Git Bash) ---
    if target_conf:
        click.echo(f"Detected compatible shell configuration.")
        _install_bash_sync(target_conf)
    else:
        # Fallback
        click.echo("Could not automatically detect a supported shell config.")
        click.echo("Try running 'cwm setup --force' to manually select your shell.")