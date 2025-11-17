import os
import json
from pathlib import Path
import click
import shutil

# Define the bank name as a constant
CWM_BANK_NAME = ".cwm"

def _ensure_dir(p: Path):
    """Create folder p if not exists."""
    p.mkdir(exist_ok=True)


def safe_create_cwm_folder(folder_path: Path, repair=False) -> bool:
    """
    Creates a CWM BANK structure using the new JSON document format.
    This function no longer creates meta.json.
    """
    try:
        # Ensure base folder
        _ensure_dir(folder_path)

        # Create subfolders
        data_path = folder_path / "data"
        backup_path = data_path / "backup"

        _ensure_dir(data_path)
        _ensure_dir(backup_path)  # Ensure the backup folder exists

        # --- Define required JSON files with new structure ---
        # The data and its metadata now live in the same file.
        required_files = {
            "commands.json": {"last_command_id": 0, "commands": []},
            "saved_cmds.json": {"last_saved_id": 0, "commands": []},
            "watch_history.json": {"history_last_num": 0, "history": []},
            "fav_cmds.json": [] # Favs can remain a simple list
        }

        # --- CONFIG FILE ---
        config_file = folder_path / "config.json"
        if not config_file.exists():
            if repair:
                click.echo("config.json missing... recreated.")
            config_file.write_text("{}")
        
        # --- REQUIRED DATA FILES ---
        # This loop now ONLY creates files that are missing.
        for fname, default_value in required_files.items():
            file = data_path / fname
            if not file.exists():
                file.write_text(json.dumps(default_value, indent=2))
                if repair:
                    click.echo(f"{fname} missing... recreated.")

        return True

    except PermissionError:
        click.echo("ERROR: Permission denied. CWM cannot repair or create this bank.")
        return False
    except Exception as e:
        click.echo(f"Unexpected error in safe_create_cwm_folder: {e}")
        return False


def has_write_permission(path: Path) -> bool:
    """Checks if the user can write to a given path."""
    try:
        test = path / ".__cwm_test__"
        test.write_text("test")
        test.unlink()
        return True
    except:
        return False

# --- HELPER FUNCTIONS for finding banks ---

def is_path_literally_inside_bank(path: Path) -> bool:
    """
    Checks if the given path is *literally inside* a .cwm folder.
    e.g., C:\project\.cwm\data -> True
    e.g., C:\project\subfolder -> False
    """
    current = path.resolve()
    return CWM_BANK_NAME in current.parts

def find_nearest_bank_path(start_path: Path) -> Path | None:
    """
    Looks for the nearest .cwm bank in the current or parent directories.
    Returns the Path to the .cwm folder if found, else None.
    """
    current = start_path.resolve()
    for parent in [current] + list(current.parents):
        candidate = parent / CWM_BANK_NAME
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None