import json
import click
import shutil
import json.decoder
from pathlib import Path
from datetime import datetime

from .utils import safe_create_cwm_folder, DEFAULT_CONFIG, CWM_BANK_NAME, GLOBAL_CWM_BANK
from .schema_validator import SCHEMAS, validate

class StorageManager:
    def __init__(self):
        # 1. Setup Global Paths (Source of Truth)
        self.global_bank = GLOBAL_CWM_BANK
        self.global_config_file = self.global_bank / "config.json"
        
        self.global_data = self.global_bank / "data"
        self.global_backup = self.global_data / "backup"

        self.saved_cmds_file = self.global_data / "saved_cmds.json"
        self.projects_file = self.global_data / "projects.json"
        
        # 2. Detect Local Context
        self.local_root = self.find_project_root()
        self.local_bank = (self.local_root / CWM_BANK_NAME) if self.local_root else None

        # 3. Watch Session Location
        # Strictly Local if available, else points to a dummy global slot
        if self.local_bank and self.local_bank.exists():
            self.watch_session_file = self.local_bank / "watch_session.json"
        else:
            self.watch_session_file = self.global_data / "watch_session.json"

        # 4. Auto-Ensure Global Bank Exists
        self._ensure_global_bank()

    def find_project_root(self) -> Path | None:
        """Finds the nearest parent directory containing a .cwm folder."""
        cwd = Path.cwd()
        for path in [cwd] + list(cwd.parents):
            if (path / CWM_BANK_NAME).exists():
                return path
        return None

    # =========================================================
    # # ---------- BANK MANAGEMENT ----------
    # =========================================================

    def _ensure_global_bank(self):
        """Checks and creates the global bank structure if missing."""
        if not self.global_bank.exists() or not self.global_data.exists():
            self.create_global_bank()

    def create_global_bank(self):
        """
        Creates ~/.cwm structure:
          - config.json
          - data/
            - saved_cmds.json
            - projects.json
            - backup/
        """
        try:
            # 1. Create Directories
            safe_create_cwm_folder(self.global_bank) # Base folder
            if not self.global_data.exists():
                self.global_data.mkdir(parents=True, exist_ok=True)
            if not self.global_backup.exists():
                self.global_backup.mkdir(parents=True, exist_ok=True)

            # 2. Create Config
            if not self.global_config_file.exists():
                self.global_config_file.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")

            # 3. Create Data Files
            defaults = {
                "saved_cmds.json": {"last_saved_id": 0, "commands": []},
                "projects.json": {"last_id": 0, "projects": [], "groups": []},
                # Watch session placeholder for global context
                "watch_session.json": {"isWatching": False} 
            }

            for fname, content in defaults.items():
                f_path = self.global_data / fname
                if not f_path.exists():
                    f_path.write_text(json.dumps(content, indent=4), encoding="utf-8")

        except Exception as e:
            click.echo(f"Error creating Global Bank: {e}", err=True)

    def create_local_bank(self, target_root: Path):
        """
        Creates project/.cwm structure:
          - watch_session.json
          - project_history.txt
        """
        try:
            local_cwm = target_root / CWM_BANK_NAME
            safe_create_cwm_folder(local_cwm) # Handles hiding/attribs

            # Watch Session
            ws_file = local_cwm / "watch_session.json"
            if not ws_file.exists():
                ws_file.write_text(json.dumps({"isWatching": False}, indent=4), encoding="utf-8")

            # History File
            hist_file = local_cwm / "project_history.txt"
            if not hist_file.exists():
                hist_file.touch()

            click.echo(f"Initialized Local Bank at: {local_cwm}")
            return True
        except Exception as e:
            click.echo(f"Error creating Local Bank: {e}", err=True)
            return False

    def get_project_history_path(self) -> Path | None:
        """
        Returns path to project_history.txt in the LOCAL bank.
        Creates it if missing. Returns None if not in a valid project.
        """
        if self.local_bank and self.local_bank.exists():
            hist_file = self.local_bank / "project_history.txt"
            if not hist_file.exists():
                try: hist_file.touch()
                except: pass
            return hist_file
        return None

    # =========================================================
    # # ---------- CONFIGURATION MANAGEMENT ----------
    # =========================================================

    def get_config(self) -> dict:
        """
        Loads the centralized configuration from ~/.cwm/config.json.
        """
        default_data = {
            "history_file": None,
            "project_markers": [],
            "code_theme": "monokai",
            "ai_instruction": None
        }
        return self._load_json(self.global_config_file, default=default_data)

    def update_config(self, key: str, value):
        """
        Updates a key in the centralized global config.
        """
        data = {}
        if self.global_config_file.exists():
            try:
                data = json.loads(self.global_config_file.read_text(encoding="utf-8"))
            except: 
                pass
        
        data[key] = value
        
        try:
            self.global_config_file.write_text(json.dumps(data, indent=4), encoding="utf-8")
        except Exception as e:
            click.echo(f"Error saving config: {e}")

    def get_project_markers(self) -> list:
        config = self.get_config()
        return config.get("project_markers", DEFAULT_CONFIG["project_markers"])

    # =========================================================
    # # ---------- PROJECT & DATA MANAGEMENT ----------
    # =========================================================

    def load_saved_cmds(self):
        return self._load_json(self.saved_cmds_file, {"last_saved_id": 0, "commands": []})

    def save_saved_cmds(self, data):
        self._save_json(self.saved_cmds_file, data)

    def load_projects(self):
        return self._load_json(self.projects_file, {"last_id": 0, "projects": [], "groups": []})

    def save_projects(self, data):
        self._save_json(self.projects_file, data)

    def load_watch_session(self):
        # Reads from Local if available, else Global placeholder
        return self._load_json(self.watch_session_file, {"isWatching": False})

    def save_watch_session(self, data):
        # Writes to Local if available, else Global placeholder
        self._save_json(self.watch_session_file, data)

    # =========================================================
    # # ---------- FILE I/O & RECOVERY ----------
    # =========================================================

    def _load_json(self, file: Path, default):
        raw = None
        try:
            if file.exists():
                raw = json.loads(file.read_text(encoding="utf-8"))
            else:
                return validate(default, SCHEMAS.get(file.name, {}))
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            if file.exists():
                click.echo(f"⚠ {file.name} corrupted. Restoring from backup...")
                raw = self._restore_from_backup(file, default)
            else:
                return validate(default, SCHEMAS.get(file.name, {}))

        schema = SCHEMAS.get(file.name)
        if schema:
            is_partial = (file.name == "config.json")
            validated = validate(raw, schema, partial=is_partial)
            final_data = self._enforce_sequential_ids(file.name, validated)

            if file.name == "projects.json":
                cleaned_data, changed = self._heal_groups(final_data)
                if changed:
                    # click.echo("⚠ Self-healing: Corrected Group Links.") # Optional verbosity
                    final_data = cleaned_data

            if raw != final_data:
                self._save_json(file, final_data)

            return final_data

        return raw

    def _save_json(self, file: Path, data: dict):
        try:
            schema = SCHEMAS.get(file.name)
            if schema:
                data = validate(data, schema)

            # Backup global files only
            if file.parent == self.global_data:
                self._update_backup(file)

            # Write atomic
            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")
            raise e

    def _update_backup(self, file: Path):
        """Creates a backup in ~/.cwm/data/backup/"""
        try:
            if not self.global_backup.exists():
                self.global_backup.mkdir(parents=True, exist_ok=True)

            bak_name = f"{file.name}.bak"
            shutil.copy2(file, self.global_backup / bak_name)
        except Exception as e:
            click.echo(f"WARNING: Backup failed for {file.name}: {e}", err=True)

    def _restore_from_backup(self, file: Path, default):
        """Restores from ~/.cwm/data/backup/"""
        bak_path = self.global_backup / f"{file.name}.bak"

        if bak_path.exists():
            try:
                content = bak_path.read_text(encoding="utf-8")
                
                # Check integrity
                if file.suffix == ".json":
                    restored_data = json.loads(content)
                    file.write_text(content, encoding="utf-8")
                    click.echo(f"✔ Restored {file.name} from backup.")
                    return restored_data
                else:
                    file.write_text(content, encoding="utf-8")
                    return content

            except Exception as e:
                click.echo(f"⚠ Backup {bak_path.name} is also corrupted: {e}")

        click.echo(f"⚠ No valid backups for {file.name}. Rebuilding default.")
        if isinstance(default, (dict, list)):
            file.write_text(json.dumps(default, indent=4), encoding="utf-8")
        else:
            file.write_text(str(default), encoding="utf-8")
        return default

    # =========================================================
    # # ---------- RE-INDEXING & LOGIC ----------
    # =========================================================

    def _heal_groups(self, data: dict):
        projects = data.get("projects", [])
        groups = data.get("groups", [])
        alias_to_id_map = {p["alias"]: p["id"] for p in projects if "alias" in p}
        data_changed = False

        for grp in groups:
            new_project_list = []
            current_items = grp.get("project_list", [])

            for item in current_items:
                target_id = item.get("id")
                target_alias = item.get("verify")

                if target_alias in alias_to_id_map and alias_to_id_map[target_alias] == target_id:
                    new_project_list.append(item) 
                elif target_alias in alias_to_id_map:
                    correct_id = alias_to_id_map[target_alias]
                    new_project_list.append({"id": correct_id, "verify": target_alias})
                    data_changed = True
                else:
                    data_changed = True 

            if len(grp.get("project_list", [])) != len(new_project_list) or data_changed:
                grp["project_list"] = new_project_list
                data_changed = True

        return data, data_changed

    def _reindex_saved_cmds(self, data: dict) -> dict:
        if "commands" not in data: return data
        items = data["commands"]
        current_id = 0
        for index, item in enumerate(items, start=1):
            item["id"] = index
            current_id = index
        data["last_saved_id"] = current_id
        return data

    def _reindex_history(self, data: dict) -> dict:
        # History is gone, but keeping method sig to prevent breaks if called
        return data 

    def _reindex_projects(self, data: dict) -> dict:
        projects = data.get("projects", [])
        groups = data.get("groups", [])

        proj_map = {}
        last_proj_id = 0

        for index, proj in enumerate(projects, start=1):
            old_id = proj.get("id")
            new_id = index
            proj["id"] = new_id
            if old_id is not None:
                proj_map[old_id] = new_id
            last_proj_id = new_id

        data["last_id"] = last_proj_id

        group_map = {}
        last_group_id = 0

        for index, grp in enumerate(groups, start=1):
            old_id = grp.get("id")
            new_id = index
            grp["id"] = new_id
            if old_id is not None:
                group_map[old_id] = new_id
            last_group_id = new_id

        data["last_group_id"] = last_group_id

        for grp in groups:
            if "project_ids" in grp: del grp["project_ids"]
            
            old_list = grp.get("project_list", [])
            new_list = []
            for item in old_list:
                old_pid = item.get("id")
                if old_pid in proj_map:
                    item["id"] = proj_map[old_pid]
                    new_list.append(item)
            grp["project_list"] = new_list

        for proj in projects:
            old_grp_id = proj.get("group")
            if old_grp_id in group_map:
                proj["group"] = group_map[old_grp_id]
            else:
                proj["group"] = None

        return data

    def _enforce_sequential_ids(self, filename: str, data: dict) -> dict:
        if filename == "saved_cmds.json":
            return self._reindex_saved_cmds(data)
        elif filename == "projects.json":
            return self._reindex_projects(data)
        return data

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")