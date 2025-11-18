# cwm/bank_cmd.py
import click
import shutil
from .storage_manager import StorageManager, GLOBAL_CWM_BANK

@click.group("bank")
def bank_cmd():
    """Manage CWM bank locations."""
    pass

@bank_cmd.command("info")
def info():
    """Show the location of Local and Global banks."""
    manager = StorageManager()
    current_bank = manager.get_bank_path()
    
    click.echo("--- CWM Bank Information ---")
    
    # Local Info
    if current_bank != GLOBAL_CWM_BANK:
        click.echo(f"Active Bank (Local):  {current_bank}")
    else:
        click.echo("Active Bank (Global): (No local bank found)")
        
    click.echo(f"Global Bank Location: {GLOBAL_CWM_BANK}")


@bank_cmd.command("delete")
@click.option("--local", is_flag=True, help="Delete the LOCAL bank in this folder.")
@click.option("--global", "global_flag", is_flag=True, help="Delete the GLOBAL bank.")
def delete_bank(local, global_flag):
    """
    Delete a CWM bank (DANGER).
    
    This permanently removes all data, history, and backups for that bank.
    """
    manager = StorageManager()
    
    if not local and not global_flag:
        raise click.UsageError("You must specify --local or --global.")
    
    if local and global_flag:
        raise click.UsageError("Please delete one bank at a time.")
        
    target_path = None
    bank_type = ""
    
    if local:
        current = manager.get_bank_path()
        if current == GLOBAL_CWM_BANK:
            click.echo("Error: No local bank found in this context.")
            return
        target_path = current
        bank_type = "LOCAL"
        
    elif global_flag:
        target_path = GLOBAL_CWM_BANK
        bank_type = "GLOBAL"
        
    if not target_path.exists():
        click.echo(f"{bank_type} bank does not exist at {target_path}")
        return

    click.echo(f"WARNING: You are about to DELETE the {bank_type} bank at:")
    click.echo(f"{target_path}")
    click.echo("This will remove ALL saved commands, history, and backups.")
    
    if click.confirm("Are you sure you want to continue?"):
        try:
            shutil.rmtree(target_path)
            click.echo(f"Successfully deleted {bank_type} bank.")
        except Exception as e:
            click.echo(f"Error deleting bank: {e}", err=True)
    else:
        click.echo("Operation cancelled.")