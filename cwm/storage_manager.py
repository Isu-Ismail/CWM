import json
import click
import os
from pathlib import Path

from .utils import safe_create_cwm_folder

CWM_FOLDER = ".cwm"
GLOBAL_CWM_BANK = Path(os.getenv("APPDATA")) / "cwm"


class StorageManager:
    """
    Manages the entire CWM bank system:

    - saved_cmds.json      → permanent saved commands
    - watch_history.json   → temporary watch mode history
    - fav_cmds.json        → favorite command IDs
    - meta.json            → metadata counters / sessions
    - backup/*.bak         → automatic fallback backups
    """

    # ---------------------------------------------------------------------
    # INIT + BANK DETECTION
    # ---------------------------------------------------------------------
    def __init__(self):
        self.bank_path = self._detect_bank()
        self.data_path = self.bank_path / "data"
        self.backup_path = self.data_path / "backup"

        # JSON file paths
        self.commands_file   = self.data_path / "commands.json"
        self.saved_cmds_file = self.data_path / "saved_cmds.json"
        self.history_file    = self.data_path / "watch_history.json"
        self.fav_file        = self.data_path / "fav_cmds.json"
        self.meta_file       = self.data_path / "meta.json"

        # BACKUP FILES
        self.commands_bak   = self.backup_path / "commands.json.bak"
        self.saved_cmds_bak = self.backup_path / "saved_cmds.json.bak"
        self.history_bak    = self.backup_path / "watch_history.json.bak"
        self.fav_bak        = self.backup_path / "fav_cmds.json.bak"
        self.meta_bak       = self.backup_path / "meta.json.bak"

        # Ensure bank structure is valid
        safe_create_cwm_folder(self.bank_path, repair=True)


    # ---------------------------------------------------------------------
    # BANK DETECTION
    # ---------------------------------------------------------------------
    def _detect_bank(self) -> Path:
        """Locate nearest local bank, else fallback to global."""
        current = Path.cwd()

        for parent in [current] + list(current.parents):
            candidate = parent / CWM_FOLDER
            if candidate.exists():
                return candidate

        # No local bank found → use global
        if not GLOBAL_CWM_BANK.exists():
            safe_create_cwm_folder(GLOBAL_CWM_BANK, repair=False)
            click.echo(f"Created global CWM bank at:\n{GLOBAL_CWM_BANK}")

        return GLOBAL_CWM_BANK


    # ---------------------------------------------------------------------
    # SAFE JSON HELPERS
    # ---------------------------------------------------------------------
    def _load_json(self, file: Path, default):
        """Load JSON safely; fallback to default if corrupted."""
        try:
            return json.loads(file.read_text())
        except Exception:
            click.echo(f"ERROR: {file.name} corrupted. Restoring from backup...")
            return self._restore_from_backup(file, default)


    def _save_json(self, file: Path, data):
        """Atomic JSON write."""
        try:
            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(file)
        except Exception as e:
            click.echo(f"ERROR writing {file.name}: {e}")


    def _restore_from_backup(self, file: Path, default):
        """Restore file from its .bak, or reset to default."""
        bak = self.backup_path / (file.name + ".bak")

        # Try restore backup
        if bak.exists():
            try:
                restored = json.loads(bak.read_text())
                file.write_text(bak.read_text())
                click.echo(f"Restored {file.name} from backup.")
                return restored
            except:
                click.echo(f"Backup for {file.name} corrupted too. Rebuilding...")

        # Reset to default
        file.write_text(json.dumps(default, indent=2))
        bak.write_text(json.dumps(default, indent=2))
        return default


    def _update_backup(self, file: Path):
        bak = self.backup_path / (file.name + ".bak")
        bak.write_text(file.read_text())


    # ---------------------------------------------------------------------
    # COMMAND LIST (General Commands)
    # ---------------------------------------------------------------------
    def load_commands(self) -> list:
        return self._load_json(self.commands_file, default=[])

    def save_commands(self, cmds: list):
        self._save_json(self.commands_file, cmds)
        self._update_backup(self.commands_file)


    # ---------------------------------------------------------------------
    # SAVED COMMANDS
    # ---------------------------------------------------------------------
    def load_saved_cmds(self) -> list:
        return self._load_json(self.saved_cmds_file, default=[])

    def save_saved_cmds(self, cmds: list):
        self._save_json(self.saved_cmds_file, cmds)
        self._update_backup(self.saved_cmds_file)


    # ---------------------------------------------------------------------
    # WATCH MODE HISTORY
    # ---------------------------------------------------------------------
    def load_watch_history(self) -> list:
        return self._load_json(self.history_file, default=[])

    def save_watch_history(self, history: list):
        self._save_json(self.history_file, history)
        self._update_backup(self.history_file)


    # ---------------------------------------------------------------------
    # FAVORITES
    # ---------------------------------------------------------------------
    def load_fav_ids(self) -> list:
        return self._load_json(self.fav_file, default=[])

    def save_fav_ids(self, fav_ids: list):
        self._save_json(self.fav_file, fav_ids)
        self._update_backup(self.fav_file)


    # ---------------------------------------------------------------------
    # META (IDs and counters)
    # ---------------------------------------------------------------------
    def load_meta(self) -> dict:
        return self._load_json(self.meta_file, default={
            "last_saved_id": 0,
            "history_last_num": 0
        })

    def save_meta(self, meta: dict):
        self._save_json(self.meta_file, meta)
        self._update_backup(self.meta_file)


    # ---------------------------------------------------------------------
    # GENERATE UNIQUE IDs
    # ---------------------------------------------------------------------
    def next_saved_id(self) -> int:
        meta = self.load_meta()
        meta["last_saved_id"] += 1
        self.save_meta(meta)
        return meta["last_saved_id"]

    def next_history_number(self) -> int:
        meta = self.load_meta()
        meta["history_last_num"] += 1
        self.save_meta(meta)
        return meta["history_last_num"]


    # ---------------------------------------------------------------------
    # PATH RETURN
    # ---------------------------------------------------------------------
    def get_bank_path(self):
        return self.bank_path
