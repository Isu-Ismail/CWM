import json
import click
import shutil
from pathlib import Path
import json.decoder
from .utils import safe_create_cwm_folder, find_nearest_bank_path, DEFAULT_CONFIG
from .schema_validator import SCHEMAS, validate

CWM_FOLDER = ".cwm"
GLOBAL_CWM_BANK = Path(click.get_app_dir("cwm"))


class StorageManager:
    def __init__(self):
        self.bank_path = self._detect_bank()
        self.data_path = self.bank_path / "data"
        self.backup_path = self.data_path / "backup"

        self.saved_cmds_file = self.data_path / "saved_cmds.json"
        self.fav_file = self.data_path / "fav_cmds.json"
        self.cached_history_file = self.data_path / "history.json"
        self.watch_session_file = self.data_path / "watch_session.json"

        self.config_file = self.bank_path / "config.json"

        self.global_data_path = GLOBAL_CWM_BANK / "data"
        self.projects_file = self.global_data_path / "projects.json"

        self._ensure_global_defaults()

        safe_create_cwm_folder(self.bank_path, repair=True)

        if not self.backup_path.exists():
            self.backup_path.mkdir(parents=True, exist_ok=True)

    def _detect_bank(self) -> Path:
        local_bank = find_nearest_bank_path(Path.cwd())
        if local_bank:
            return local_bank
        if not GLOBAL_CWM_BANK.exists():
            safe_create_cwm_folder(GLOBAL_CWM_BANK, repair=False)
            click.echo(f"Created global CWM bank at:\n{GLOBAL_CWM_BANK}")
        return GLOBAL_CWM_BANK

    def _heal_groups(self, data: dict) -> dict:
        """
        Ensures Group IDs match their verify keys (aliases).
        If an ID points to the wrong project, it finds the correct ID
        using the alias and updates the group automatically.
        """
        projects = data.get("projects", [])
        groups = data.get("groups", [])

        alias_to_id_map = {p["alias"]: p["id"]
                           for p in projects if "alias" in p}

        data_changed = False

        for grp in groups:
            new_project_list = []

            current_items = grp.get("project_list", [])

            for item in current_items:
                target_id = item.get("id")
                target_alias = item.get("verify")

                if target_alias in alias_to_id_map and alias_to_id_map[target_alias] == target_id:
                    new_project_list.append(item)  # It's correct, keep it.

                elif target_alias in alias_to_id_map:
                    correct_id = alias_to_id_map[target_alias]
                    new_project_list.append(
                        {"id": correct_id, "verify": target_alias})
                    data_changed = True

                else:
                    data_changed = True

            if len(grp.get("project_list", [])) != len(new_project_list) or data_changed:
                grp["project_list"] = new_project_list
                data_changed = True

        return data, data_changed

    def _reindex_saved_cmds(self, data: dict) -> dict:
        """
        Fixes saved_cmds.json:
        - Flattens IDs to 1, 2, 3...
        - Removes duplicate '0' IDs by giving them new numbers.
        - Updates 'last_saved_id'.
        """
        if "commands" not in data:
            return data

        items = data["commands"]
        current_id = 0

        for index, item in enumerate(items, start=1):
            item["id"] = index
            current_id = index

        data["last_saved_id"] = current_id
        return data

    def _reindex_history(self, data: dict) -> dict:
        """
        Fixes history.json (sync history):
        - Flattens IDs to 1, 2, 3...
        - Updates 'last_sync_id'.
        """
        if "commands" not in data:
            return data

        items = data["commands"]
        current_id = 0

        for index, item in enumerate(items, start=1):
            item["id"] = index
            current_id = index

        data["last_sync_id"] = current_id
        return data

    def _reindex_projects(self, data: dict) -> dict:
        """
        Fixes projects.json:
        - Re-indexes Projects (1..N) and maps {Old -> New}.
        - Re-indexes Groups (1..N) and maps {Old -> New}.
        - UPDATES the 'group' field in each Project.
        - UPDATES the 'project_list' in each Group (Updating IDs, Removing dead links).
        - REMOVES the legacy 'project_ids' field entirely.
        """
        projects = data.get("projects", [])
        groups = data.get("groups", [])

        proj_map = {}  # { old_id: new_id }
        last_proj_id = 0

        for index, proj in enumerate(projects, start=1):
            old_id = proj.get("id")
            new_id = index

            proj["id"] = new_id

            if old_id is not None:
                proj_map[old_id] = new_id

            last_proj_id = new_id

        data["last_id"] = last_proj_id

        group_map = {}  # { old_id: new_id }
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
            if "project_ids" in grp:
                del grp["project_ids"]

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
        """
        Routes the data to the correct re-indexer based on filename.
        """
        if filename == "saved_cmds.json":
            return self._reindex_saved_cmds(data)

        elif filename == "history.json":
            return self._reindex_history(data)

        elif filename == "projects.json":
            return self._reindex_projects(data)

        return data

    def _load_json(self, file: Path, default):
        raw = None
        try:
            if file.exists():
                raw = json.loads(file.read_text(encoding="utf-8"))
            else:
                return validate(default, SCHEMAS.get(file.name, {}))

        except (FileNotFoundError, json.decoder.JSONDecodeError):
            if file.exists():
                click.echo(
                    f"⚠ {file.name} corrupted. Restoring from backup...")
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
                    click.echo(
                        "⚠ Self-healing: Corrected Group Links due to ID mismatch.")
                    final_data = cleaned_data

            if raw != final_data:
                click.echo(
                    f"⚠ Detected corruption/schema mismatch in {file.name}. Saving repairs...")
                self._save_json(file, final_data)

            return final_data

        return raw

    def load_projects(self) -> dict:
        data = self._load_json(self.projects_file, default={
                               "last_id": 0, "projects": []})
        projects = data.get("projects", [])

        needs_save = False
        existing_ids = set()
        max_id = data.get("last_id", 0)

        for p in projects:
            pid = p.get("id")
            if pid == 0 or pid in existing_ids:
                needs_save = True
            existing_ids.add(pid)
            if pid > max_id:
                max_id = pid

        if needs_save:
            click.echo(
                "⚠ Re-indexing projects due to ID collision/corruption...")

            new_list = []
            current_id = 1

            for p in projects:
                p["id"] = current_id
                new_list.append(p)
                current_id += 1

            data["projects"] = new_list
            data["last_id"] = current_id - 1

            self.save_projects(data)
            click.echo("✔ Projects re-indexed successfully.")

        return data

    def _ensure_global_defaults(self):
        """
        Ensures the GLOBAL config has all necessary keys.
        """
        global_conf = GLOBAL_CWM_BANK / "config.json"

        if not global_conf.exists():
            try:
                if not GLOBAL_CWM_BANK.exists():
                    GLOBAL_CWM_BANK.mkdir(parents=True, exist_ok=True)
                global_conf.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
            except:
                pass
            return

        try:
            current_data = json.loads(global_conf.read_text())
            modified = False

            for key, default_val in DEFAULT_CONFIG.items():
                if key == "history_file":
                    continue

                if key not in current_data:
                    current_data[key] = default_val
                    modified = True

            if not current_data.get("project_markers"):
                current_data["project_markers"] = DEFAULT_CONFIG["project_markers"]
                modified = True

            if modified:
                global_conf.write_text(json.dumps(current_data, indent=2))
        except Exception:
            pass

    def _save_json(self, file: Path, data):
        try:
            schema = SCHEMAS.get(file.name)
            if schema:
                data = validate(data, schema)

            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")
            raise e

    def _restore_from_backup(self, file: Path, default):
        """
        Restores from {filename}.bak in the SAME DIRECTORY.
        """
        bak_path = file.parent / f"{file.name}.bak"

        if bak_path.exists():
            try:
                content = bak_path.read_text(encoding="utf-8")

                if file.suffix == ".json":
                    restored_data = json.loads(content)
                    file.write_text(content, encoding="utf-8")
                    click.echo(
                        f"✔ Restored {file.name} from backup successfully.")
                    return restored_data
                else:
                    file.write_text(content, encoding="utf-8")
                    click.echo(
                        f"✔ Restored {file.name} from backup successfully.")
                    return content  # Or whatever return type needed

            except Exception as e:
                click.echo(f"⚠ Backup {bak_path.name} is also corrupted: {e}")

        click.echo(
            f"⚠ No valid backups found for {file.name}. Rebuilding default.")

        if isinstance(default, (dict, list)):
            file.write_text(json.dumps(default, indent=4), encoding="utf-8")
        else:
            file.write_text(str(default), encoding="utf-8")

        return default

    def _update_backup(self, file: Path):
        """
        Creates a single backup copy in the SAME DIRECTORY: 
        filename.json -> filename.json.bak
        """
        try:

            backup_dir = file.parent

            bak_name = f"{file.name}.bak"
            new_bak_path = backup_dir / bak_name

            shutil.copy2(file, new_bak_path)

        except Exception as e:
            click.echo(
                f"WARNING: Could not update backup for {file.name}: {e}", err=True)

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

    def get_config(self, scope: str = "global") -> dict:
        """
        Loads a specific configuration file without merging.

        Args:
            scope (str): "global" for ~/.cwm/config.json 
                         "local"  for current_project/.cwm/config.json
        """
        if scope == "local":
            root = self.find_project_root()
            config_path = root / ".cwm" / "config.json"
        else:
            config_path = GLOBAL_CWM_BANK / "config.json"

        default_data = {
            "history_file": None,
            "project_markers": [],
            "code_theme": "monokai"
        }

        return self._load_json(config_path, default=default_data)

    def update_config(self, key: str, value):
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text())
            else:
                data = {}
        except:
            data = {}

        data[key] = value

        try:
            self.config_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            click.echo(f"Error saving config: {e}", err=True)

    def set_preferred_history(self, path: Path):
        self.update_config("history_file", str(path))

    def save_projects(self, data: dict):
        if not self.global_data_path.exists():
            self.global_data_path.mkdir(parents=True, exist_ok=True)
        self._save_json(self.projects_file, data)
        self._update_backup(self.projects_file)

    def get_project_markers(self) -> list:
        config = self.get_config()
        return config.get("project_markers", DEFAULT_CONFIG["project_markers"])

    def get_project_history_path(self) -> Path:
        """
        Returns the path to the local project history file.
        e.g., C:/MyProject/.cwm/project_history.txt
        """
        root = self.find_project_root()
        cwm_dir = root / ".cwm"

        if not cwm_dir.exists():
            cwm_dir.mkdir(parents=True)

        return cwm_dir / "project_history.txt"

    def find_project_root(self) -> Path:
        """
        Searches upwards from CWD to find an existing .cwm folder.
        If not found, returns current working directory.
        """
        cwd = Path.cwd()

        for path in [cwd] + list(cwd.parents):
            if (path / ".cwm").exists():
                return path

        markers = self.get_project_markers()
        for path in [cwd] + list(cwd.parents):
            if any((path / m).exists() for m in markers):
                return path

        return cwd

    def _now(self):
        from datetime import datetime
        """Helper to get current timestamp string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

