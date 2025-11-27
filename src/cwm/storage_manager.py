# cwm/storage_manager.py
import json
import click
import os
import shutil
from pathlib import Path
from datetime import datetime
import json.decoder
from .utils import safe_create_cwm_folder, find_nearest_bank_path, DEFAULT_CONFIG
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

        self.config_file = self.bank_path / "config.json"
        
        self.global_data_path = GLOBAL_CWM_BANK / "data"
        self.archives_folder = self.global_data_path / "archives"
        self.projects_file = self.global_data_path / "projects.json"
        self.archived_data_file = self.archives_folder / "archive_index.json"
        
        # --- FIX: Ensure Global Defaults Exist ---
        # We explicitly check and fix the GLOBAL config, not the active one.
        self._ensure_global_defaults()
        
        if not self.archives_folder.exists():
            self.archives_folder.mkdir(parents=True, exist_ok=True)
        
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
        try:
            return json.loads(file.read_text())
        except FileNotFoundError:
            if file.exists():
                click.echo(f"WARNING: {file.name} is missing. Attempting to restore from backup...")
            return self._restore_from_backup(file, default)
        except json.decoder.JSONDecodeError:
            click.echo(f"ERROR: {file.name} corrupted. Restoring from backup...")
            return self._restore_from_backup(file, default)
        except Exception as e:
            click.echo(f"Unexpected error loading {file.name}: {e}. Restoring...")
            return self._restore_from_backup(file, default)

    def _ensure_global_defaults(self):
        """
        Ensures the GLOBAL config has all necessary keys (Editors, Markers).
        Does NOT touch local config to keep it clean.
        """
        global_conf = GLOBAL_CWM_BANK / "config.json"
        
        if not global_conf.exists():
            # If global doesn't exist, create it with full defaults
            try:
                if not GLOBAL_CWM_BANK.exists():
                    GLOBAL_CWM_BANK.mkdir(parents=True, exist_ok=True)
                global_conf.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
            except: pass
            return

        try:
            current_data = json.loads(global_conf.read_text())
            modified = False

            # Check every key in our DEFAULT_CONFIG
            for key, default_val in DEFAULT_CONFIG.items():
                # Skip context-specific keys like history_file for global default check
                if key == "history_file": continue
                
                if key not in current_data:
                    current_data[key] = default_val
                    modified = True
            
            # Ensure markers list isn't empty/null
            if not current_data.get("project_markers"):
                current_data["project_markers"] = DEFAULT_CONFIG["project_markers"]
                modified = True

            if modified:
                global_conf.write_text(json.dumps(current_data, indent=2))
        except Exception:
            pass 

    def _save_json(self, file: Path, data):
        try:
            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")
            raise e

    def _restore_from_backup(self, file: Path, default):
        try:
            backups = sorted(
                self.backup_path.glob(f"{file.name}.*.bak"),
                key=os.path.getmtime,
                reverse=True
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

    # --- LOADERS ---
    def load_saved_cmds(self) -> dict:
        return self._load_json(self.saved_cmds_file, default={"last_saved_id": 0, "commands": []})

    def save_saved_cmds(self, data: dict):
        self._save_json(self.saved_cmds_file, data)
        self._update_backup(self.saved_cmds_file)

    def load_cached_history(self) -> dict:
        return self._load_json(self.cached_history_file, default={"last_sync_id": 0, "commands": []})

    def save_cached_history(self, data: dict):
        self._save_json(self.cached_history_file, data)

    def load_watch_session(self) -> dict:
        return self._load_json(self.watch_session_file, default={"isWatching": False, "startLine": 0})

    def save_watch_session(self, data: dict):
        self._save_json(self.watch_session_file, data)

    def load_fav_ids(self) -> list:
        return self._load_json(self.fav_file, default=[])

    def save_fav_ids(self, fav_ids: list):
        self._save_json(self.fav_file, fav_ids)
        self._update_backup(self.fav_file)
            
    def get_bank_path(self):
        return self.bank_path
        
    def list_backups_for_file(self, filename: str) -> list[dict]:
        backups = []
        try:
            backup_files = sorted(
                self.backup_path.glob(f"{filename}.*.bak"),
                key=os.path.getmtime,
                reverse=False
            )
            for bak_file in backup_files:
                parts = bak_file.name.split('.')
                if len(parts) < 4: continue
                timestamp = parts[-2]
                short_id = timestamp[-7:]
                created_time = datetime.fromtimestamp(os.path.getmtime(bak_file))
                backups.append({
                    "id": short_id, "timestamp": timestamp, "full_path": bak_file,
                    "created": created_time.strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            click.echo(f"Error reading backups: {e}", err=True)
        return backups

    def find_backup_by_id(self, filename: str, short_id: str) -> Path | None:
        for bak in self.list_backups_for_file(filename):
            if bak["id"] == short_id: return bak["full_path"]
        return None
    
    def get_config(self) -> dict:
        """
        Smart Configuration Loader.
        1. Loads GLOBAL config first (Base Layer).
        2. Loads LOCAL config second (Override Layer).
        3. Returns merged dictionary.
        """
        # 1. Base: Global Defaults
        final_config = DEFAULT_CONFIG.copy()
        
        # 2. Overlay: Global File
        global_conf = GLOBAL_CWM_BANK / "config.json"
        if global_conf.exists():
            try:
                global_data = json.loads(global_conf.read_text())
                final_config.update(global_data)
            except: pass

        # 3. Overlay: Local File (If different from Global)
        if self.config_file != global_conf and self.config_file.exists():
            try:
                local_data = json.loads(self.config_file.read_text())
                # Only update keys that exist in local (sparse override)
                final_config.update(local_data)
            except: pass
            
        return final_config

    def update_config(self, key: str, value):
        """
        Updates configuration.
        Decides target (Local vs Global) based on key type logic?
        Currently assumes updating the ACTIVE config file context.
        """
        # Load RAW file content, not merged config
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text())
            else:
                data = {}
        except: data = {}
        
        data[key] = value
        
        try:
            self.config_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            click.echo(f"Error saving config: {e}", err=True)

    # --- ARCHIVE & PROJECT METHODS ---
    def load_archive_index(self) -> dict:
        return self._load_json(self.archived_data_file, default={"last_archive_id": 0, "archives": []})

    def save_archive_index(self, data: dict):
        self._save_json(self.archived_data_file, data)

    def create_archive_file(self, lines: list, archive_id: int) -> Path:
        filename = f"archive_{archive_id}.txt"
        path = self.archives_folder / filename
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
        
    def get_archive_path(self, filename: str) -> Path:
        return self.archives_folder / filename
    
    def set_preferred_history(self, path: Path):
        # Forces update to current active config (Local if present)
        self.update_config("history_file", str(path))

    def load_projects(self) -> dict:
        return self._load_json(self.projects_file, default={"last_id": 0, "projects": []})

    def save_projects(self, data: dict):
        if not self.global_data_path.exists():
            self.global_data_path.mkdir(parents=True, exist_ok=True)
        self._save_json(self.projects_file, data)

    def get_project_markers(self) -> list:
        # Uses the smart get_config merger
        config = self.get_config()
        return config.get("project_markers", DEFAULT_CONFIG["project_markers"])