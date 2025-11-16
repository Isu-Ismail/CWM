import os
import json
from pathlib import Path
import click
import shutil


def _ensure_dir(p: Path):
    """Create folder p if not exists."""
    p.mkdir(exist_ok=True)


def _safe_json_load(file: Path, default):
    try:
        return json.loads(file.read_text())
    except Exception:
        return default


def _safe_json_write(file: Path, data):
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(file)


def safe_create_cwm_folder(folder_path: Path, repair=False) -> bool:
    """
    Creates or repairs a CWM BANK structure.

    Structure:
        .cwm/
            config.json
            data/
                commands.json
                saved_cmds.json
                watch_history.json
                fav_cmds.json
                meta.json
                backup/
                    *.bak
    """

    try:
        # Ensure base folder
        _ensure_dir(folder_path)

        # Create subfolders
        data_path = folder_path / "data"
        backup_path = data_path / "backup"

        _ensure_dir(data_path)
        _ensure_dir(backup_path)

        # --- Define required JSON files ---
        required_files = {
            "commands.json": [],
            "saved_cmds.json": [],
            "watch_history.json": [],
            "fav_cmds.json": [],
            "meta.json": {"last_saved_id": 0, "history_last_num": 0}
        }

        # --- CONFIG FILE ---
        config_file = folder_path / "config.json"
        if not config_file.exists():
            if repair:
                click.echo("config.json missing  recreated.")
            config_file.write_text("{}")
        else:
            try:
                json.loads(config_file.read_text())
            except:
                click.echo("config.json corrupted repaired.")
                config_file.write_text("{}")

        # --- REQUIRED DATA FILES ---
        for fname, default_value in required_files.items():
            file = data_path / fname
            backup = backup_path / (fname + ".bak")

            if not file.exists():
                file.write_text(json.dumps(default_value, indent=2))
                if repair:
                    click.echo(f"{fname} missing recreated.")

                # Create backup
                backup.write_text(json.dumps(default_value, indent=2))
                continue

            # Try load
            try:
                json.loads(file.read_text())
            except:
                click.echo(f"{fname} corrupted repairing...")

                # Try backup
                if backup.exists():
                    try:
                        data = json.loads(backup.read_text())
                        file.write_text(backup.read_text())
                        click.echo(f"Restored {fname} from backup.")
                        continue
                    except:
                        pass

                # No valid backup
                file.write_text(json.dumps(default_value, indent=2))
                click.echo(f"Rebuilt {fname} from defaults.")

            # Ensure backup always matches file
            _safe_json_write(backup, _safe_json_load(file, default_value))

        return True

    except PermissionError:
        click.echo("ERROR: Permission denied. CWM cannot repair or create this bank.")
        return False

    except Exception as e:
        click.echo(f"Unexpected error in safe_create_cwm_folder: {e}")
        return False



def has_write_permission(path: Path) -> bool:
    try:
        test = path / ".__cwm_test__"
        test.write_text("test")
        test.unlink()
        return True
    except:
        return False



def find_cwm_folders(start_path: Path):
    folders = []
    for root, dirs, files in os.walk(start_path):
        if ".cwm" in dirs:
            folders.append(Path(root) / ".cwm")
    return folders



def inside_cwm_bank(path: Path) -> bool:
    if path.name == ".cwm":
        return True

    for parent in path.parents:
        if (parent / ".cwm").exists():
            if path.is_relative_to(parent / ".cwm"):
                return True

    return False
