import os
import sys
import json
import time
import subprocess
from pathlib import Path

from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .project_cmd import is_safe_startup_cmd

try:
    import psutil
except ImportError:
    psutil = None


# ==========================
# PATHS
# ==========================
ORCH_DIR = GLOBAL_CWM_BANK / "orchestrator"
STATE_FILE = ORCH_DIR / "services.json"
WATCHER_PID_FILE = ORCH_DIR / "watcher.pid"
LOG_DIR = ORCH_DIR / "logs"


# ==========================
# TMUX DETECTION
# ==========================
def _tmux_available() -> bool:
    try:
        subprocess.run(
            ["tmux", "-V"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        return True
    except Exception:
        return False


# ==========================
# TMUX ENGINE
# ==========================
class TmuxEngine:
    PREFIX = "cwm"

    def session_name(self, project_id: int, alias: str) -> str:
        return f"{self.PREFIX}:{project_id}:{alias}"

    def start(self, project: dict):
        session = self.session_name(project["id"], project["alias"])
        root = str(Path(project["path"]).resolve())

        raw_cmd = project["startup_cmd"]
        cmd = " && ".join(raw_cmd) if isinstance(raw_cmd, list) else str(raw_cmd)
        cmd = cmd.replace("$ROOT", root)

        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-c", root, cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True, f"Started tmux session '{session}'"

    def stop(self, project: dict):
        session = self.session_name(project["id"], project["alias"])
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True, "Stopped."

    def is_running(self, project: dict) -> bool:
        session = self.session_name(project["id"], project["alias"])
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0

    def list_sessions(self):
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.splitlines() if result.returncode == 0 else []

    def kill_all(self):
        subprocess.run(
            ["tmux", "kill-server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )


# ==========================
# SERVICE MANAGER
# ==========================
class ServiceManager:
    def __init__(self):
        self.manager = StorageManager()
        self.use_tmux = _tmux_available()

        if self.use_tmux:
            self.tmux = TmuxEngine()
        else:
            if not psutil:
                raise ImportError("Missing dependency 'psutil'.")
            self._ensure_paths()

    # ----------------------
    # FALLBACK ENGINE SETUP
    # ----------------------
    def _ensure_paths(self):
        ORCH_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if not STATE_FILE.exists():
            STATE_FILE.write_text("{}")

    def _load_state(self):
        try:
            if not STATE_FILE.exists():
                return {}
            return json.loads(STATE_FILE.read_text() or "{}")
        except Exception:
            return {}

    def _save_state(self, data):
        STATE_FILE.write_text(json.dumps(data, indent=2))

    # ======================
    # STATUS
    # ======================
    def get_services_status(self):
        if self.use_tmux:
            state = {}
            sessions = self.tmux.list_sessions()
            projects = self.manager.load_projects().get("projects", [])

            for p in projects:
                name = self.tmux.session_name(p["id"], p["alias"])
                if name in sessions:
                    state[str(p["id"])] = {
                        "project_id": p["id"],
                        "alias": p["alias"],
                        "status": "running",
                        "pid": None,
                        "backend": "tmux"
                    }
            return state

        # ---- fallback engine ----
        state = self._load_state()
        for info in state.values():
            pid = info.get("pid")
            if pid and not psutil.pid_exists(pid):
                info["status"] = "stopped"
                info["pid"] = None
        self._save_state(state)
        return state

    # ======================
    # START
    # ======================
    def start_project(self, project_id: int):
        data = self.manager.load_projects()
        project = next((p for p in data.get("projects", [])
                        if p["id"] == project_id), None)

        if not project:
            return False, "Project not found."

        if self.use_tmux:
            if self.tmux.is_running(project):
                return False, "Already running."
            return self.tmux.start(project)

        # ---- fallback engine ----
        state = self._load_state()
        sid = str(project_id)
        if sid in state and state[sid]["status"] == "running":
            return False, "Already running."

        raw_cmd = project.get("startup_cmd")
        if not raw_cmd:
            return False, "No startup command."

        root = Path(project["path"]).resolve()
        if not is_safe_startup_cmd(raw_cmd, root):
            return False, "Unsafe command blocked."

        cmd = " && ".join(raw_cmd) if isinstance(raw_cmd, list) else str(raw_cmd)
        cmd = cmd.replace("$ROOT", str(root))

        log_file = LOG_DIR / f"{project_id}.log"
        out = open(log_file, "w", encoding="utf-8")

        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=True,
            start_new_session=True
        )
        out.close()

        state[sid] = {
            "project_id": project_id,
            "alias": project["alias"],
            "pid": proc.pid,
            "status": "running",
            "start_time": time.time(),
            "log_path": str(log_file)
        }
        self._save_state(state)
        return True, f"Started (PID {proc.pid})"

    # ======================
    # STOP
    # ======================
    def stop_project(self, project_id: int):
        if self.use_tmux:
            data = self.manager.load_projects()
            project = next((p for p in data.get("projects", [])
                            if p["id"] == project_id), None)
            if not project:
                return False, "Project not found."
            return self.tmux.stop(project)

        state = self._load_state()
        sid = str(project_id)
        if sid not in state:
            return False, "Not running."

        pid = state[sid].get("pid")
        if pid:
            try:
                psutil.Process(pid).kill()
            except Exception:
                pass

        state[sid]["status"] = "stopped"
        state[sid]["pid"] = None
        self._save_state(state)
        return True, "Stopped."

    # ======================
    # STOP ALL
    # ======================
    def stop_all(self):
        if self.use_tmux:
            self.tmux.kill_all()
            return 0

        state = self._load_state()
        count = 0
        for info in state.values():
            if info.get("status") == "running":
                self.stop_project(info["project_id"])
                count += 1
        return count

    # ======================
    # NUKE
    # ======================
    def nuke_all(self):
        if self.use_tmux:
            self.tmux.kill_all()
            return [], "tmux server killed"

        killed = []
        state = self._load_state()
        for info in state.values():
            pid = info.get("pid")
            if pid:
                try:
                    psutil.Process(pid).kill()
                    killed.append(info["alias"])
                except Exception:
                    pass
        self._save_state({})
        return killed, "Fallback engine cleaned"
