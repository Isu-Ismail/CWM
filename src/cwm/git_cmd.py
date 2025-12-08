import click
import pyperclip
import re
import platform
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel

from .git_utils import (
    detect_project_type,
    generate_ssh_key,
    get_gitignore_content,
    update_ssh_config,
    get_configured_accounts,
    run_git_command,
    get_git_remote_url,
    get_current_branch,
    has_commits,
    remove_ssh_keys,
    remove_from_ssh_config,
    SSH_CONFIG
)
from .rich_help import RichHelpGroup, RichHelpCommand
console = Console()


@click.group("git", cls=RichHelpGroup)
def git_cmd():
    """Manage GitHub accounts and SSH keys."""
    pass


@git_cmd.command("add", cls=RichHelpCommand)
def add_account():
    """Add new ssh acoount and generate key"""
    console.print(
        "\n[bold cyan]?[/bold cyan] [bold]Setup New Git Account[/bold]")

    alias = Prompt.ask(
        "  [cyan]Enter unique alias[/cyan] [dim](e.g. 'work', 'personal')[/dim]")
    alias = re.sub(r'[^a-z0-9_]', '', alias.lower())

    if not alias:
        console.print("  [red]✖ Invalid alias.[/red]")
        return

    email = Prompt.ask(
        f"  [cyan]Enter email for[/cyan] [bold white]{alias}[/bold white]")

    console.print(f"  [dim]Generating SSH key for '{alias}'...[/dim]")

    try:
        key_path = generate_ssh_key(alias, email)
        update_ssh_config(alias, key_path)
        pub_key_path = key_path.with_suffix(".pub")

        if pub_key_path.exists():
            pub_key = pub_key_path.read_text().strip()
            console.print(f"  [green]✔ SSH Key created.[/green]")
            console.print(f"  [green]✔ Config updated.[/green]")

            console.print(
                Panel(pub_key, title="Public Key", border_style="dim"))

            if Confirm.ask("  [cyan]? Copy public key to clipboard?[/cyan]", default=True):
                pyperclip.copy(pub_key)
                console.print(
                    "  [green]✔ Copied![/green] Go to GitHub -> Settings -> SSH Keys and add it.")
        else:
            console.print("  [red]✖ Error: Public key file not found.[/red]")
    except Exception as e:
        console.print(f"  [red]✖ Error:[/red] {e}")


@git_cmd.command("list", cls=RichHelpCommand)
def list_accounts():
    """List the available ssh accounts"""
    accounts = get_configured_accounts()
    if not accounts:
        console.print("[yellow]No CWM-managed accounts found.[/yellow]")
        return

    console.print(f"\n[dim]Config File: {SSH_CONFIG}[/dim]\n")
    console.print("[bold]Configured Accounts:[/bold]")

    for i, acc in enumerate(accounts):
        console.print(
            f"  [cyan]{i+1}.[/cyan] [bold white]{acc['alias']}[/bold white]")
        console.print(f"     [dim]Host: {acc['host']}[/dim]")
        console.print(f"     [dim]Key:  {acc['key']}[/dim]")
    console.print("")


@git_cmd.command("setup", cls=RichHelpCommand)
def setup_repo():
    """Configure current folder with a Git account."""
    console.print("")  # Spacing

    accounts = get_configured_accounts()
    if not accounts:
        console.print(
            "  [red]✖ No accounts found. Run 'cwm git add' first.[/red]")
        return

    console.print("[bold cyan]? Select Account:[/bold cyan]")
    for i, acc in enumerate(accounts):
        console.print(
            f"  [cyan]{i+1})[/cyan] {acc['alias']} [dim]({acc['host']})[/dim]")

    choices = [str(x) for x in range(1, len(accounts) + 1)]
    choice = IntPrompt.ask("  [dim]Enter number[/dim]",
                           choices=choices, show_choices=False)

    selected = accounts[choice - 1]
    alias = selected['alias']
    ssh_host = selected['host']

    if not (Path.cwd() / ".git").exists():
        console.print("")
        if Confirm.ask("  [cyan]? Initialize new Git repository here?[/cyan]", default=True):
            run_git_command(["init"])
            run_git_command(["branch", "-M", "main"])
            console.print("  [green]✔ Initialized Git repository.[/green]")

    console.print("")
    with console.status("[bold cyan]Configuring local repo settings...[/bold cyan]") as status:
        status.stop()

        name = Prompt.ask(f"  [cyan]? User Name for '{alias}'[/cyan]")
        email = Prompt.ask(f"  [cyan]? Email for '{alias}'[/cyan]")

        status.start()
        run_git_command(["config", "user.name", name])
        run_git_command(["config", "user.email", email])

        system = platform.system()
        crlf_setting = "true" if system == "Windows" else "input"
        run_git_command(["config", "core.autocrlf", crlf_setting])

        status.stop()
        console.print(f"  [green]✔ User set to {name} <{email}>[/green]")
        console.print(
            f"  [green]✔ Line endings configured ({crlf_setting}).[/green]")

    console.print("")
    raw_url = Prompt.ask("  [cyan]? Paste GitHub SSH/HTTPS URL[/cyan]")

    new_url = raw_url
    if "git@github.com:" in raw_url:
        new_url = raw_url.replace("git@github.com:", f"git@{ssh_host}:")
        console.print(f"  [dim]→ Rewriting URL to use alias: {new_url}[/dim]")

    current_remote = get_git_remote_url()

    if current_remote:
        console.print(f"  [yellow]! Current remote: {current_remote}[/yellow]")
        if Confirm.ask("  [cyan]? Replace with new URL?[/cyan]"):
            run_git_command(["remote", "set-url", "origin", new_url])
            console.print("  [green]✔ Remote updated.[/green]")
    else:
        run_git_command(["remote", "add", "origin", new_url])
        console.print("  [green]✔ Remote 'origin' added.[/green]")

    current_branch = get_current_branch()
    has_data = has_commits()

    console.print("")

    if has_data:
        push_cmd = f"git push -u origin {current_branch}"
        if Confirm.ask(f"  [cyan]? Push to remote now?[/cyan] [dim]({push_cmd})[/dim]", default=True):
            with console.status("[bold cyan]Pushing code to GitHub...[/bold cyan]"):
                success = run_git_command(
                    ["push", "-u", "origin", current_branch])

            if success:
                console.print(
                    "  [bold green]✔ Success! Project is live.[/bold green]")
            else:
                console.print(
                    "  [bold red]✖ Push failed.[/bold red] Check SSH key permissions.")
                pyperclip.copy(push_cmd)
                console.print("  [dim]Command copied to clipboard.[/dim]")
    else:
        console.print("  [yellow]! Repository has no commits yet.[/yellow]")

        if not (Path.cwd() / ".gitignore").exists():
            detected_type = detect_project_type(Path.cwd())
            if Confirm.ask(f"  [cyan]? Create .gitignore for {detected_type}?[/cyan]", default=True):
                content = get_gitignore_content(detected_type)
                (Path.cwd() / ".gitignore").write_text(content)
                console.print(f"  [green]✔ Created .gitignore.[/green]")

        if Confirm.ask("  [cyan]? Add, Commit, and Push all files?[/cyan]", default=True):
            msg = Prompt.ask("  [dim]Commit message[/dim]",
                             default="Initial commit")

            with console.status("[bold cyan]Processing git operations...[/bold cyan]") as status:
                run_git_command(["add", "."])
                status.update("[bold cyan]Committing...[/bold cyan]")
                if run_git_command(["commit", "-m", msg]):
                    status.update("[bold cyan]Pushing...[/bold cyan]")
                    if run_git_command(["push", "-u", "origin", current_branch]):
                        status.stop()
                        console.print(
                            "  [bold green]✔ Success! Project is live.[/bold green]")
                    else:
                        status.stop()
                        console.print("  [bold red]✖ Push failed.[/bold red]")
                else:
                    status.stop()
                    console.print("  [red]✖ Commit failed (empty?).[/red]")
        else:
            console.print("  [dim]Skipped automation.[/dim]")


@git_cmd.command("remove", cls=RichHelpCommand)
def remove_account():
    """Remove a Git account and its SSH keys."""
    console.print("")

    accounts = get_configured_accounts()
    if not accounts:
        console.print("  [yellow]! No accounts found to remove.[/yellow]")
        return

    console.print("[bold red]! Select Account to DELETE:[/bold red]")
    for i, acc in enumerate(accounts):
        console.print(
            f"  [cyan]{i+1})[/cyan] {acc['alias']} [dim]({acc['host']})[/dim]")

    choices = [str(x) for x in range(1, len(accounts) + 1)]
    choice = IntPrompt.ask("  [dim]Enter number[/dim]",
                           choices=choices, show_choices=False)

    selected = accounts[choice - 1]
    alias = selected['alias']
    key_path = selected['key']

    console.print(
        f"\n  [bold red]⚠ WARNING:[/bold red] This will permanently delete:")
    console.print(f"    1. SSH Config entry for '[white]{alias}[/white]'")
    console.print(f"    2. Private Key: [dim]{key_path}[/dim]")
    console.print(f"    3. Public Key:  [dim]{key_path}.pub[/dim]")

    if Confirm.ask(f"\n  [bold red]Are you sure you want to remove '{alias}'?[/bold red]"):

        remove_from_ssh_config(alias)
        deleted_keys = remove_ssh_keys(key_path)

        if deleted_keys:
            console.print(
                f"\n  [green]✔ Account '{alias}' and keys removed successfully.[/green]")
        else:
            console.print(
                f"\n  [yellow]✔ Account removed from config, but key files were missing or locked.[/yellow]")
    else:
        console.print("\n  [dim]Cancelled.[/dim]")


