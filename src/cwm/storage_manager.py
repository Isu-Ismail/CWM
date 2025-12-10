import json
import click
import shutil
import json.decoder
from pathlib import Path
from datetime import datetime

from .utils import safe_create_cwm_folder, DEFAULT_CONFIG, CWM_BANK_NAME, GLOBAL_CWM_BANK,is_safe_startup_cmd
from .schema_validator import SCHEMAS, validate

class StorageManager:
    def __init__(self):
        # 1. Setup Global Paths (Source of Truth for Data)
        self.global_bank = GLOBAL_CWM_BANK
        self.global_data = self.global_bank / "data"
        self.global_backup = self.global_data / "backup"

        # 2. Define Core Files (ALWAYS GLOBAL)
        self.saved_cmds_file = self.global_data / "saved_cmds.json"
        self.fav_file = self.global_data / "fav_cmds.json"
        self.projects_file = self.global_data / "projects.json"
        
        # 3. Detect Local Context
        self.local_root = self.find_project_root()
        self.local_bank = (self.local_root / CWM_BANK_NAME) if self.local_root else None

        # 4. Watch Session Location (Context Aware)
        # If in a project, use Local. If not, use Global fallback.
        if self.local_bank and self.local_bank.exists():
            self.watch_session_file = self.local_bank / "watch_session.json"
        else:
            self.watch_session_file = self.global_data / "watch_session.json"

        # 5. Ensure Global Bank Exists
        if not self.global_bank.exists():
            safe_create_cwm_folder(self.global_bank)

    def find_project_root(self) -> Path | None:
        """Finds the nearest parent directory containing a .cwm folder."""
        cwd = Path.cwd()
        for path in [cwd] + list(cwd.parents):
            if (path / CWM_BANK_NAME).exists():
                return path
        return None
    
    def get_bank_path(self) -> Path:
        """Returns the active bank path (Local if exists, else Global)."""
        return self.local_bank if self.local_bank else self.global_bank

    def get_project_history_path(self) -> Path:
        """Returns path to project_history.txt in the LOCAL bank."""
        if self.local_bank:
            return self.local_bank / "project_history.txt"
        return self.global_bank / "project_history.txt" # Fallback

    # =========================================================
    # RE-INDEXING & HEALING LOGIC
    # =========================================================

    def _heal_groups(self, data: dict):
        """
        Ensures Group IDs match their verify keys (aliases).
        """
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
                    data_changed = True # Remove broken link

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
        if "commands" not in data: return data
        items = data["commands"]
        current_id = 0
        for index, item in enumerate(items, start=1):
            item["id"] = index
            current_id = index
        data["last_sync_id"] = current_id
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
        elif filename == "history.json":
            return self._reindex_history(data)
        elif filename == "projects.json":
            return self._reindex_projects(data)
        return data

    # =========================================================
    # CORE LOAD/SAVE
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
                    click.echo("⚠ Self-healing: Corrected Group Links.")
                    final_data = cleaned_data

            if raw != final_data:
                # Silent repair save
                self._save_json(file, final_data)

            return final_data

        return raw

    def _save_json(self, file: Path, data: dict):
        try:
            schema = SCHEMAS.get(file.name)
            if schema:
                data = validate(data, schema)

            # Backup global files
            if file.parent == self.global_data:
                self._update_backup(file)

            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")
            raise e

    # =========================================================
    # BACKUP SYSTEM
    # =========================================================

    def _update_backup(self, file: Path):
        """Creates a backup in the GLOBAL backup folder."""
        try:
            if not self.global_backup.exists():
                self.global_backup.mkdir(parents=True, exist_ok=True)

            bak_name = f"{file.name}.bak"
            shutil.copy2(file, self.global_backup / bak_name)
        except Exception as e:
            click.echo(f"WARNING: Backup failed for {file.name}: {e}", err=True)

    def _restore_from_backup(self, file: Path, default):
        """Restores from GLOBAL backup folder."""
        bak_path = self.global_backup / f"{file.name}.bak"

        if bak_path.exists():
            try:
                content = bak_path.read_text(encoding="utf-8")
                
                # Verify JSON integrity
                if file.suffix == ".json":
                    restored_data = json.loads(content)
                    file.write_text(content, encoding="utf-8")
                    click.echo(f"✔ Restored {file.name} from backup.")
                    return restored_data
                else:
                    file.write_text(content, encoding="utf-8")
                    click.echo(f"✔ Restored {file.name} from backup.")
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
    # DATA ACCESSORS
    # =========================================================

    def get_config(self, scope: str = "global") -> dict:
        """
        Loads config. scope="global" or "local".
        """
        if scope == "local":
            if self.local_bank:
                config_path = self.local_bank / "config.json"
            else:
                return {} # No local bank
        else:
            config_path = self.global_bank / "config.json"

        default_data = {
            "history_file": None,
            "project_markers": [],
            "code_theme": "monokai",
            "ai_instruction": None
        }
        return self._load_json(config_path, default=default_data)

    def update_config(self, key: str, value, scope: str = "global"):
        """
        Updates a config key in the specified scope.
        """
        if scope == "local":
            if not self.local_bank:
                click.echo("Error: No local bank found to update config.")
                return
            config_path = self.local_bank / "config.json"
        else:
            config_path = self.global_bank / "config.json"

        # Load raw without defaults to preserve user intent
        data = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except: pass
        
        data[key] = value
        
        try:
            config_path.write_text(json.dumps(data, indent=4))
        except Exception as e:
            click.echo(f"Error saving config: {e}")

    def load_saved_cmds(self):
        return self._load_json(self.saved_cmds_file, {"last_saved_id": 0, "commands": []})

    def save_saved_cmds(self, data):
        self._save_json(self.saved_cmds_file, data)

    def load_projects(self):
        return self._load_json(self.projects_file, {"last_id": 0, "projects": [], "groups": []})

    def save_projects(self, data):
        if not self.global_data.exists():
            self.global_data.mkdir(parents=True, exist_ok=True)
        self._save_json(self.projects_file, data)

    def load_watch_session(self):
        # Watch session location is dynamic (Local or Global)
        return self._load_json(self.watch_session_file, {"isWatching": False})

    def save_watch_session(self, data):
        self._save_json(self.watch_session_file, data)

    def get_project_markers(self) -> list:
        config = self.get_config("global")
        return config.get("project_markers", DEFAULT_CONFIG["project_markers"])
    
    def _now(self):
        from datetime import datetime
        """Helper to get current timestamp string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")