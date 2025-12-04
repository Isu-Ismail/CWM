# src/cwm/service_manager.py
import os
import sys
import json
import time
import subprocess
import shlex
from pathlib import Path
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .project_cmd import is_safe_startup_cmd 
from .schema_validator import validate_service_entry 
from .utils import make_hidden 

try:
    import psutil
except ImportError:
    psutil = None

# --- CONSTANTS ---
ORCH_DIR = GLOBAL_CWM_BANK / "orchestrator"
STATE_FILE = ORCH_DIR / "services.json"
WATCHER_PID_FILE = ORCH_DIR / "watcher.pid"
LOG_DIR = ORCH_DIR / "logs"

class ServiceManager:
    def __init__(self):
        if not psutil:
            raise ImportError("Missing dependency 'psutil'.")
        self.manager = StorageManager()
        self._ensure_paths()

    def _ensure_paths(self):
        if not ORCH_DIR.exists(): ORCH_DIR.mkdir(parents=True)
        if not LOG_DIR.exists(): LOG_DIR.mkdir(parents=True)
        
        if not STATE_FILE.exists(): 
            STATE_FILE.write_text("{}")

    def _force_unhide(self, path):
        if os.name == 'nt' and path.exists():
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)
            except: pass

    def _load_state(self):
        try:
            if not STATE_FILE.exists(): return {}
            content = STATE_FILE.read_text()
            if not content.strip(): return {}
            data = json.loads(content)
            if not isinstance(data, dict): raise ValueError("Root must be a dictionary")
            return data
        except (json.JSONDecodeError, ValueError, Exception):
            self.nuke_all()
            self._save_state({}) 
            return {}

    def _save_state(self, data):
        try:
            self._force_unhide(STATE_FILE)
            STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error saving state: {e}")

    # --- POLLING AGENT ---
    def run_watcher_loop(self):
        current_pid = os.getpid()
        self._force_unhide(WATCHER_PID_FILE)
        WATCHER_PID_FILE.write_text(str(current_pid))

        try:
            while True:
                time.sleep(2)
                state = self._load_state()
                dirty = False
                active_count = 0

                for pid_key, info in state.items():
                    if info.get("status") == "running":
                        pid = info.get("pid")
                        is_alive = False
                        if pid:
                            try:
                                proc = psutil.Process(pid)
                                if proc.status() != psutil.STATUS_ZOMBIE:
                                    is_alive = True
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                is_alive = False
                        
                        if is_alive:
                            active_count += 1
                        else:
                            info["status"] = "stopped"
                            info["pid"] = None
                            dirty = True
                
                if dirty:
                    self._save_state(state)

                if active_count == 0:
                    break
        finally:
            if WATCHER_PID_FILE.exists():
                try: WATCHER_PID_FILE.unlink()
                except: pass

    def _ensure_watcher_running(self):
        if WATCHER_PID_FILE.exists():
            try:
                w_pid = int(WATCHER_PID_FILE.read_text().strip())
                if psutil.pid_exists(w_pid): return 
            except: pass
        
        cmd = [sys.executable, "-m", "cwm.cli", "run", "_watcher"]
        kwargs = {
            "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL,
            "cwd": str(ORCH_DIR)
        }
        if os.name == 'nt':
            kwargs["creationflags"] = 0x08000000 
            kwargs["shell"] = False 
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)

    # --- STATUS CHECK ---
    def get_services_status(self):
        state = self._load_state()
        dirty = False
        for pid_key, info in state.items():
            pid = info.get("pid")
            if info.get("status") == "running":
                if pid:
                    try:
                        proc = psutil.Process(pid)
                        if proc.status() == psutil.STATUS_ZOMBIE: raise psutil.NoSuchProcess(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        info["status"] = "stopped"
                        info["pid"] = None
                        dirty = True
                else:
                    info["status"] = "stopped"
                    dirty = True
            elif pid is not None:
                info["pid"] = None
                dirty = True
        
        if dirty: self._save_state(state)
        return state

    # --- ACTIONS ---
    def start_project(self, project_id: int):
        state = self.get_services_status()
        str_id = str(project_id)
        if str_id in state and state[str_id]["status"] == "running": return False, "Already running."

        data = self.manager.load_projects()
        proj = next((p for p in data.get("projects", []) if p["id"] == project_id), None)
        if not proj: return False, "Project ID not found."

        cmd_str = proj.get("startup_cmd")
        if not cmd_str: return False, "No startup command."
        root_path = Path(proj["path"]).resolve()

        if not is_safe_startup_cmd(cmd_str, root_path): return False, "SECURITY BLOCK: Unsafe command."

        log_file = LOG_DIR / f"{project_id}.log"
        out_file = None 
        try:
            out_file = open(log_file, "w", encoding="utf-8")
            args = cmd_str if os.name == 'nt' else shlex.split(cmd_str)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            kwargs = {"cwd": str(root_path), "stdout": out_file, "stderr": subprocess.STDOUT, "text": True, "env": env}
            if os.name == 'nt':
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
                kwargs["shell"] = True
            else:
                kwargs["start_new_session"] = True
                kwargs["shell"] = True

            proc = subprocess.Popen(args, **kwargs)
            out_file.close() 
            
            new_entry = {
                "project_id": project_id, "alias": proj["alias"], "pid": proc.pid, "viewers": [],
                "status": "running", "start_time": time.time(), "log_path": str(log_file), "cmd": cmd_str
            }
            state[str_id] = validate_service_entry(new_entry)
            self._save_state(state)
            self._ensure_watcher_running()
            return True, f"Started (PID {proc.pid})"
        except Exception as e:
            if out_file: 
                try: out_file.close() 
                except: pass
            return False, str(e)

    def register_viewer(self, project_id: int, viewer_pid: int):
        state = self._load_state()
        str_id = str(project_id)
        if str_id in state:
            viewers = state[str_id].get("viewers", [])
            if viewer_pid not in viewers:
                viewers.append(viewer_pid)
                state[str_id]["viewers"] = viewers
                self._save_state(state)

    def stop_project(self, project_id: int):
        state = self.get_services_status()
        str_id = str(project_id)
        if str_id not in state: return False, "Not found."
        
        info = state[str_id]
        main_pid = info.get("pid")
        viewers = info.get("viewers", [])

        for v_pid in viewers:
            try:
                if psutil.pid_exists(v_pid): psutil.Process(v_pid).kill()
            except: pass
        
        if main_pid:
            try:
                parent = psutil.Process(main_pid)
                for child in parent.children(recursive=True):
                    try: child.kill() 
                    except: pass
                parent.kill()
            except psutil.NoSuchProcess: pass 
        
        info["status"] = "stopped"
        info["pid"] = None
        info["viewers"] = []
        self._save_state(state)
        return True, "Stopped."

    # --- MISSING METHOD ADDED HERE ---
    def remove_entry(self, project_id: int):
        """
        Stops service and removes from JSON.
        """
        self.stop_project(project_id)
        state = self.get_services_status()
        str_id = str(project_id)
        if str_id in state:
            del state[str_id]
            self._save_state(state)
            return True, "Removed."
        return False, "Not found."
    
    # GUI Compatibility Alias
    remove_service_entry = remove_entry

    def stop_all(self):
        state = self.get_services_status()
        count = 0
        for pid_key, info in state.items():
            if info.get("status") == "running":
                self.stop_project(int(info["project_id"]))
                count += 1
        return count

    def kill_watcher(self):
        if WATCHER_PID_FILE.exists():
            try:
                pid_str = WATCHER_PID_FILE.read_text().strip()
                if not pid_str: return False, "No watcher PID found."
                pid = int(pid_str)
                if psutil.pid_exists(pid):
                    psutil.Process(pid).kill()
                    return True, f"Watcher (PID {pid}) killed."
            except Exception as e: return False, f"Failed: {e}"
            finally: 
                try: WATCHER_PID_FILE.unlink()
                except: pass
        return False, "Watcher not running."

    def _kill_cwm_ghosts(self):
        myself = os.getpid()
        killed_count = 0
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['pid'] == myself: continue
                try:
                    name = proc.info['name'].lower()
                    cmdline = proc.info['cmdline'] or []
                    cmd_str = " ".join(cmdline).lower()
                    if 'python' in name and 'cwm' in cmd_str:
                        proc.kill()
                        killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess): pass
        except: pass
        return killed_count

    def nuke_all(self):
        stopped = self.stop_all()
        _, w_msg = self.kill_watcher()
        ghosts = self._kill_cwm_ghosts()
        try: 
            self._force_unhide(STATE_FILE)
            STATE_FILE.write_text("{}")
        except: pass
        return stopped, f"{w_msg} (Cleaned {ghosts} ghosts)"