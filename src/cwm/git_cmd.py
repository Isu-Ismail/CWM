# cwm/git_cmd.py
import click
import pyperclip
import re
from pathlib import Path
from .git_utils import (
    generate_ssh_key, 
    update_ssh_config, 
    get_configured_accounts,
    run_git_command,
    get_git_remote_url,
    get_current_branch,
    has_commits,
    SSH_CONFIG
)

@click.group("git")
def git_cmd():
    """Manage GitHub accounts and SSH keys."""
    pass

@git_cmd.command("add")
def add_account():
    click.echo("--- CWM Git Account Wizard ---")
    alias = click.prompt("Enter a unique alias (e.g. 'work', 'personal')")
    alias = re.sub(r'[^a-z0-9_]', '', alias.lower())
    if not alias:
        click.echo("Invalid alias.")
        return
    email = click.prompt("Enter the email for this account")
    click.echo(f"Generating SSH key for '{alias}'...")
    try:
        key_path = generate_ssh_key(alias, email)
        update_ssh_config(alias, key_path)
        pub_key_path = key_path.with_suffix(".pub")
        if pub_key_path.exists():
            pub_key = pub_key_path.read_text().strip()
            click.echo(click.style("\nSUCCESS: SSH Key created and Config updated.", fg="green"))
            click.echo(f"Key: {key_path}")
            click.echo("-" * 60)
            click.echo(pub_key)
            click.echo("-" * 60)
            if click.confirm("Copy public key to clipboard?", default=True):
                pyperclip.copy(pub_key)
                click.echo("Copied! Go to GitHub -> Settings -> SSH Keys and add it.")
        else:
             click.echo("Error: Public key file not found.")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

@git_cmd.command("list")
def list_accounts():
    accounts = get_configured_accounts()
    if not accounts:
        click.echo("No CWM-managed accounts found in ~/.ssh/config")
        return
    click.echo(f"Config File: {SSH_CONFIG}")
    click.echo("Configured Accounts:")
    for i, acc in enumerate(accounts):
        click.echo(f"  [{i+1}] {acc['alias']}")
        click.echo(f"      Host: {acc['host']}")
        click.echo(f"      Key:  {acc['key']}")
        click.echo("")

@git_cmd.command("setup")
def setup_repo():
    """Configure current folder with a Git account."""
    # 1. Select Account
    accounts = get_configured_accounts()
    if not accounts:
        click.echo("No accounts found. Run 'cwm git add' first.")
        return
        
    click.echo("Select account to use for this repo:")
    for i, acc in enumerate(accounts):
        click.echo(f"  [{i+1}] {acc['alias']} ({acc['host']})")
        
    try:
        choice = click.prompt("Enter number", type=int)
        if choice < 1 or choice > len(accounts):
            click.echo("Invalid selection.")
            return
    except:
        return
        
    selected = accounts[choice - 1]
    alias = selected['alias']
    ssh_host = selected['host'] 
    
    # 2. Init Repo Logic
    if not (Path.cwd() / ".git").exists():
        if click.confirm("Initialize new Git repository here?", default=True):
            run_git_command(["init"])
            # --- FIX: Rename to main immediately ---
            run_git_command(["branch", "-M", "main"])
            click.echo("Initialized Git repository (branch set to 'main').")
    
    # 3. Configure User
    # (Skip prompt if already configured locally? No, usually good to confirm for multi-account)
    click.echo(f"\nConfiguring local user for '{alias}'...")
    name = click.prompt(f"Enter User Name for '{alias}'")
    email = click.prompt(f"Enter Email for '{alias}'")
    run_git_command(["config", "user.name", name])
    run_git_command(["config", "user.email", email])
    click.echo("Local git config updated.")
    
    # 4. Configure Remote
    click.echo("\n--- Remote Setup ---")
    click.echo("Go to GitHub, create a repo, and copy the SSH URL.")
    raw_url = click.prompt("Paste URL")
    
    if "git@github.com:" in raw_url:
        new_url = raw_url.replace("git@github.com:", f"git@{ssh_host}:")
        click.echo(f"Rewriting URL to use alias: {new_url}")
    else:
        click.echo("Warning: URL format not standard. Using as-is.")
        new_url = raw_url
        
    current_remote = get_git_remote_url()
    
    if current_remote:
        click.echo(f"Current remote 'origin': {current_remote}")
        if click.confirm(f"Replace with new URL?"):
            run_git_command(["remote", "set-url", "origin", new_url])
            click.echo("Remote updated.")
    else:
        run_git_command(["remote", "add", "origin", new_url])
        click.echo("Remote 'origin' added.")
    
    # 5. Finalize and Check Commits
    current_branch = get_current_branch()
    has_data = has_commits()
    
    click.echo(click.style(f"\nSetup Complete! Repo linked to '{alias}'.", fg="green"))
    
    if has_data:
        # Ready to push
        push_cmd = f"git push -u origin {current_branch}"
        click.echo(f"Repository is ready. Run:\n  {push_cmd}")
    else:
        # Needs commit first
        click.echo(click.style("Notice: You have no commits yet.", fg="yellow"))
        click.echo("Run these commands to upload your code:")
        click.echo("  1. git add .")
        click.echo("  2. git commit -m \"Initial commit\"")
        push_cmd = f"git push -u origin {current_branch}"
        click.echo(f"  3. {push_cmd}")

    # Auto-Copy the push command for convenience
    if click.confirm(f"Copy '{push_cmd}' to clipboard?", default=True):
        pyperclip.copy(push_cmd)
        click.echo("Copied!")