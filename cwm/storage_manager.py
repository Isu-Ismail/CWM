import json
import click
import os
import shutil
from pathlib import Path
from datetime import datetime
import json.decoder

# Import the new helper functions
from .utils import safe_create_cwm_folder, find_nearest_bank_path

CWM_FOLDER = ".cwm"
GLOBAL_CWM_BANK = Path(os.getenv("APPDATA")) / "cwm"


class StorageManager:
    """
    Manages the CWM bank with new integrated metadata and restore-on-delete logic.
    """

    # ---------------------------------------------------------------------
    # INIT + BANK DETECTION
    # ---------------------------------------------------------------------
    def __init__(self):
        self.bank_path = self._detect_bank()
        self.data_path = self.bank_path / "data"
        self.backup_path = self.data_path / "backup"
        self.backup_limit = 10  # Max number of backups to keep per file

        

        # JSON file paths
        self.commands_file   = self.data_path / "commands.json"
        self.saved_cmds_file = self.data_path / "saved_cmds.json"
        self.cached_history_file = self.data_path / "history.json"
        self.fav_file        = self.data_path / "fav_cmds.json"
        
        # meta.json is GONE.

        # Ensure bank structure is valid
        safe_create_cwm_folder(self.bank_path, repair=True)


    # ---------------------------------------------------------------------
    # BANK DETECTION
    # ---------------------------------------------------------------------
    def _detect_bank(self) -> Path:
        """Locate nearest local bank, else fallback to global."""
        local_bank = find_nearest_bank_path(Path.cwd())
        if local_bank:
            return local_bank
        
        if not GLOBAL_CWM_BANK.exists():
            safe_create_cwm_folder(GLOBAL_CWM_BANK, repair=False)
            click.echo(f"Created global CWM bank at:\n{GLOBAL_CWM_BANK}")
        return GLOBAL_CWM_BANK


    # ---------------------------------------------------------------------
    # SAFE JSON HELPERS (REFACTORED)
    # ---------------------------------------------------------------------
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
            # This is your new "deleted file" logic
            click.echo(f"WARNING: {file.name} is missing. Attempting to restore from backup...")
            return self._restore_from_backup(file, default)
        except json.decoder.JSONDecodeError:
            # This is your "corrupted file" logic
            click.echo(f"ERROR: {file.name} corrupted. Restoring from backup...")
            return self._restore_from_backup(file, default)
        except Exception as e:
            # Catch other potential errors (e.g., permissions)
            click.echo(f"Unexpected error loading {file.name}: {e}. Restoring...")
            return self._restore_from_backup(file, default)


    def _save_json(self, file: Path, data):
        """Atomic JSON write."""
        try:
            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")
            raise e


    def _restore_from_backup(self, file: Path, default):
        """Restore file from the LATEST valid timestamped backup."""
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

        # Try loading backups in order (newest to oldest)
        for bak in backups:
            try:
                restored = json.loads(bak.read_text())
                # Found a valid one!
                file.write_text(bak.read_text())  # Restore the main file
                click.echo(f"Restored {file.name} from backup: {bak.name}")
                return restored
            except Exception:
                click.echo(f"Backup {bak.name} is also corrupted. Trying next...")
        
        # **NEW LOGIC**: If no valid backups are found, write the default.
        click.echo(f"No valid backups found for {file.name}. Rebuilding from default.")
        file.write_text(json.dumps(default, indent=2))
        return default


    def _update_backup(self, file: Path):
        """Create a new timestamped backup and prune old ones."""
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

    # ---------------------------------------------------------------------
    # API FOR DATA FILES (REFACTORED)
    # ---------------------------------------------------------------------

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

    # --- NEW CACHED HISTORY METHODS ---
    def load_cached_history(self) -> dict:
        """Loads the saved_history.json document."""
        return self._load_json(
            self.cached_history_file,
            default={"last_sync_id": 0, "commands": []}
        )

    def save_cached_history(self, data: dict):
        """Saves the saved_history.json document."""
        # We don't backup the history cache, as you specified.
        try:
            self._save_json(self.cached_history_file, data)
        except Exception:
            click.echo("Failed to save history cache.")

    def load_fav_ids(self) -> list:
        """Favorites can remain a simple list."""
        return self._load_json(self.fav_file, default=[])

    def save_fav_ids(self, fav_ids: list):
        try:
            self._save_json(self.fav_file, fav_ids)
            self._update_backup(self.fav_file)
        except Exception:
            click.echo("Failed to save favorites. Backup not created.")

    def list_backups_for_file(self, filename: str) -> list[dict]:
        """
        Scans the backup folder and returns a list of dictionaries
        for all available backups for a given file.
        """
        backups = []
        try:
            # Find all backup files that match the pattern
            backup_files = sorted(
                self.backup_path.glob(f"{filename}.*.bak"),
                key=os.path.getmtime,
                reverse=False  # List oldest-to-newest as requested
            )
            
            for bak_file in backup_files:
                # The timestamp is the part between filename and .bak
                # e.g., saved_cmds.json.20251117081847272820.bak
                parts = bak_file.name.split('.')
                if len(parts) < 4:
                    continue
                
                timestamp = parts[-2]
                short_id = timestamp[-7:] # Use last 7 digits as the "Git-like" ID
                
                # Get created time from filesystem
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
        """Finds the full backup file path from a short ID."""
        for bak in self.list_backups_for_file(filename):
            if bak["id"] == short_id:
                return bak["full_path"]
        return None

    # ---------------------------------------------------------------------
    # ID GENERATION (REMOVED)
    # All meta.json and ID generation methods are GONE.
    # This logic now lives in the command files (e.g., save_cmd.py).
    # ---------------------------------------------------------------------
    
    def get_bank_path(self):
        return self.bank_path