import os
import json
from pathlib import Path
import click


def safe_create_cwm_folder(folder_path: Path) -> bool:
    """
    Safely creates a CWM folder with fallback handling.
    Returns True if creation succeeded, False if failed.
    """

    try:
        # Create main folder
        folder_path.mkdir(exist_ok=True)

        # Create commands.json
        commands_file = folder_path / "commands.json"
        if not commands_file.exists():
            commands_file.write_text("[]")

        # Create config.json
        config_file = folder_path / "config.json"
        if not config_file.exists():
            config_file.write_text("{}")

        return True

    except PermissionError:
        click.echo("ERROR: Permission denied. Cannot create CWM folder here.")
        return False

    except OSError as e:
        click.echo(f"ERROR: Could not create CWM folder ({e}).")
        return False

    except Exception as e:
        click.echo(f"Unexpected error: {e}")
        return False
