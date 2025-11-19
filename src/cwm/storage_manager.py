# cwm/storage_manager.py
import json
import click
import os
import shutil
from pathlib import Path
from datetime import datetime
import json.decoder
from .utils import safe_create_cwm_folder, find_nearest_bank_path
from typing import Tuple 

CWM_FOLDER = ".cwm"
GLOBAL_CWM_BANK = Path(click.get_app_dir("cwm"))

class StorageManager:
    def __init__(self):
        self.bank_path = self._detect_bank()
        self.data_path = self.bank_path / "data"
        self.backup_path = self.data_path / "backup"
        self.backup_limit = 10

        self.commands_file   = self.data_path / "commands.json"
        self.saved_cmds_file = self.data_path / "saved_cmds.json"
        self.fav_file        = self.data_path / "fav_cmds.json"
        self.cached_history_file = self.data_path / "history.json"
        self.watch_session_file = self.data_path / "watch_session.json"
        
        safe_create_cwm_folder(self.bank_path, repair=True)

    def _detect_bank(self) -> Path:
        local_bank = find_nearest_bank_path(Path.cwd())
        if local_bank:
            return local_bank
        if not GLOBAL_CWM_BANK.exists():
            safe_create_cwm_folder(GLOBAL_CWM_BANK, repair=False)
            click.echo(f"Created global CWM bank at:\n{GLOBAL_CWM_BANK}")
        return GLOBAL_CWM_BANK

    def _load_json(self, file: Path, default):
        """
        Load JSON safely.
        Handles:
        1. File not found -> Restore from backup.
        2. File corrupted  -> Restore from backup.
        """
        try:
            # If file exists and is valid, just return its content
            return json.loads(file.read_text())
        except FileNotFoundError:
            click.echo(f"WARNING: {file.name} is missing. Attempting to restore from backup...")
            return self._restore_from_backup(file, default)
        except json.decoder.JSONDecodeError:
            click.echo(f"ERROR: {file.name} corrupted. Restoring from backup...")
            return self._restore_from_backup(file, default)
        except Exception as e:
            # Catch other potential errors (e.g., permissions)
            click.echo(f"Unexpected error loading {file.name}: {e}. Restoring...")
            return self._restore_from_backup(file, default)


    def _save_json(self, file: Path, data):
        try:
            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")
            raise e


    def _restore_from_backup(self, file: Path, default):
        click.echo(f"Attempting to restore {file.name} from backups...")
        
        try:
            backups = sorted(
                self.backup_path.glob(f"{file.name}.*.bak"),
                key=os.path.getmtime,
                reverse=True  # Newest first
            )
        except Exception as e:
            click.echo(f"Error scanning for backups: {e}")
            backups = []

        for bak in backups:
            try:
                restored = json.loads(bak.read_text())
                file.write_text(bak.read_text()) 
                click.echo(f"Restored {file.name} from backup: {bak.name}")
                return restored
            except Exception:
                click.echo(f"Backup {bak.name} is also corrupted. Trying next...")
        
        click.echo(f"No valid backups found for {file.name}. Rebuilding from default.")
        file.write_text(json.dumps(default, indent=2))
        return default


    def _update_backup(self, file: Path):
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            bak_name = f"{file.name}.{timestamp}.bak"
            new_bak_path = self.backup_path / bak_name
            shutil.copy2(file, new_bak_path)

            backups = sorted(
                self.backup_path.glob(f"{file.name}.*.bak"),
                key=os.path.getmtime,
                reverse=True
            )
            
            if len(backups) > self.backup_limit:
                to_delete = backups[self.backup_limit:]
                for old_bak in to_delete:
                    old_bak.unlink()
                            
        except Exception as e:
            click.echo(f"WARNING: Could not update backup for {file.name}: {e}")

    def load_saved_cmds(self) -> dict:
        return self._load_json(
            self.saved_cmds_file,
            default={"last_saved_id": 0, "commands": []}
        )

    def save_saved_cmds(self, data: dict):
        try:
            self._save_json(self.saved_cmds_file, data)
            self._update_backup(self.saved_cmds_file)
        except Exception:
            click.echo("Failed to save commands. Backup not created.")

    def load_cached_history(self) -> dict:
        return self._load_json(
            self.cached_history_file,
            default={"last_sync_id": 0, "commands": []}
        )

    def save_cached_history(self, data: dict):
        try:
            self._save_json(self.cached_history_file, data)
        except Exception:
            click.echo("Failed to save history cache.")

    def load_watch_session(self) -> dict:
        return self._load_json(
            self.watch_session_file,
            default={"isWatching": False, "startLine": 0}
        )

    def save_watch_session(self, data: dict):
        try:
            self._save_json(self.watch_session_file, data)
        except Exception:
            click.echo("Failed to save watch session.")

    def load_fav_ids(self) -> list:
        return self._load_json(self.fav_file, default=[])

    def save_fav_ids(self, fav_ids: list):
        try:
            self._save_json(self.fav_file, fav_ids)
            self._update_backup(self.fav_file)
        except Exception:
            click.echo("Failed to save favorites. Backup not created.")
            
    def get_bank_path(self):
        return self.bank_path
        
    def list_backups_for_file(self, filename: str) -> list[dict]:
        backups = []
        try:
            backup_files = sorted(
                self.backup_path.glob(f"{filename}.*.bak"),
                key=os.path.getmtime,
                reverse=False  # List oldest-to-newest
            )
            
            for bak_file in backup_files:
                parts = bak_file.name.split('.')
                if len(parts) < 4:
                    continue
                
                timestamp = parts[-2]
                short_id = timestamp[-7:] # Use last 7 digits
                
                created_time = datetime.fromtimestamp(os.path.getmtime(bak_file))
                
                backups.append({
                    "id": short_id,
                    "timestamp": timestamp,
                    "full_path": bak_file,
                    "created": created_time.strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            click.echo(f"Error reading backups: {e}", err=True)
        return backups

    def find_backup_by_id(self, filename: str, short_id: str) -> Path | None:
        for bak in self.list_backups_for_file(filename):
            if bak["id"] == short_id:
                return bak["full_path"]
        return None