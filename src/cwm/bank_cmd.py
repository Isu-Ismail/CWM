import click
from rich.console import Console
from rich.prompt import Confirm
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .rich_help import RichHelpGroup,RichHelpCommand

console = Console()

@click.group("bank",cls=RichHelpGroup)
def bank_cmd():
    """Manage CWM bank locations."""
    pass

@bank_cmd.command("info",cls=RichHelpCommand)
def info():
    """Show the location of Local and Global banks."""
    manager = StorageManager()
    
    current_path = manager.get_bank_path()
    is_local_active = (current_path != GLOBAL_CWM_BANK)
    
    console.print("") # Spacing

    console.print(f"  [bold cyan]Global Bank:[/bold cyan]  {GLOBAL_CWM_BANK}")
    
    if is_local_active:
        console.print(f"  [bold magenta]Local Bank:[/bold magenta]   {current_path}  [bold green](Active)[/bold green]")
    else:
        pass
    
    console.print("")


@bank_cmd.command("delete",cls=RichHelpCommand)
@click.option("--local", is_flag=True, help="Delete the LOCAL bank in this folder.")
@click.option("--global", "global_flag", is_flag=True, help="Delete the GLOBAL bank.")
def delete_bank(local, global_flag):
    """
    Delete a CWM bank (DANGER).
    """
    manager = StorageManager()
    
    if not local and not global_flag:
        console.print("[yellow]! Please specify --local or --global.[/yellow]")
        return
    
    if local and global_flag:
        console.print("[yellow]! Please delete one bank at a time.[/yellow]")
        return
        
    target_path = None
    bank_type = ""
    
    if local:
        current = manager.get_bank_path()
        if current == GLOBAL_CWM_BANK:
            console.print("[red]✖ Error: No local bank found in this context.[/red]")
            return
        target_path = current
        bank_type = "LOCAL"
        
    elif global_flag:
        target_path = GLOBAL_CWM_BANK
        bank_type = "GLOBAL"
        
    if not target_path.exists():
        console.print(f"[yellow]! {bank_type} bank does not exist at:[/yellow] {target_path}")
        return

   
    console.print(f"\n  [bold red]⚠ WARNING:[/bold red] You are about to DELETE the [bold]{bank_type}[/bold] bank.")
    console.print(f"  [dim]Location: {target_path}[/dim]")
    console.print("  [dim]This action cannot be undone.[/dim]\n")
    
    if Confirm.ask(f"  [bold red]Are you sure you want to delete it?[/bold red]"):
        try:
            import shutil
            shutil.rmtree(target_path)
            console.print(f"\n  [bold green]✔ Deleted {bank_type} bank.[/bold green]\n")
        except Exception as e:
            console.print(f"\n  [bold red]✖ Error deleting bank:[/bold red] {e}")
    else:
        console.print("\n  [dim]Cancelled.[/dim]\n")