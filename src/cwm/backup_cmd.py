# cwm/backup_cmd.py
import click
import json
import os
import shutil
from datetime import datetime
from .storage_manager import StorageManager

@click.group("backup")
def backup_cmd():
    """Manage the single safety backup."""
    pass

@backup_cmd.command("info")
def backup_info():
    """Check backup status."""
    manager = StorageManager()
    bak_path = manager.backup_path / "saved_cmds.bak"
    
    if bak_path.exists():
        mod_time = datetime.fromtimestamp(os.path.getmtime(bak_path)).strftime("%Y-%m-%d %H:%M:%S")
        size = bak_path.stat().st_size
        click.echo(f"Backup Status: EXISTS")
        click.echo(f"Path: {bak_path}")
        click.echo(f"Last Modified: {mod_time}")
        click.echo(f"Size: {size} bytes")
    else:
        click.echo("Backup Status: MISSING (No backup found yet)")

@backup_cmd.command("restore")
def restore_backup():
    """Force restore saved commands from backup."""
    manager = StorageManager()
    bak_path = manager.backup_path / "saved_cmds.bak"
    main_path = manager.saved_cmds_file
    
    if not bak_path.exists():
        click.echo("Error: No backup file found to restore.")
        return
        
    if click.confirm(f"Overwrite current saved commands with backup from {datetime.fromtimestamp(os.path.getmtime(bak_path))}?"):
        try:
            shutil.copy2(bak_path, main_path)
            click.echo("Success: Commands restored from backup.")
        except Exception as e:
            click.echo(f"Error restoring: {e}")

@backup_cmd.command("show")
def show_backup():
    """Show content of the backup file."""
    manager = StorageManager()
    bak_path = manager.backup_path / "saved_cmds.bak"
    
    if not bak_path.exists():
        click.echo("No backup found.")
        return

    try:
        data = json.loads(bak_path.read_text(encoding="utf-8"))
        cmds = data.get("commands", [])
        click.echo(f"--- Backup Content ({len(cmds)} cmds) ---")
        for item in cmds:
             click.echo(f"[{item.get('id')}] {item.get('var') or 'raw'} : {item.get('cmd')}")
    except Exception as e:
        click.echo(f"Error reading backup: {e}")