# src/cwm/service_manager.py
import os
import sys
import json
import time
import subprocess
import shlex
from pathlib import Path
from .storage_manager import StorageManager, GLOBAL_CWM_BANK
# Import the validators and security checks
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
            make_hidden(STATE_FILE) # <--- HIDE IT

    def _load_state(self):
        """
        Loads state with TAMPER DETECTION.
        If file is corrupted, it triggers a SAFETY NUKE.
        """
        try:
            content = STATE_FILE.read_text()
            if not content.strip(): return {}
            data = json.loads(content)
            
            # Basic Type Check
            if not isinstance(data, dict):
                raise ValueError("Root must be a dictionary")
            
            return data
            
        except (json.JSONDecodeError, ValueError, Exception) as e:
            # CORRUPTION DETECTED!
            # The file was tampered with or broke.
            # ACTION: Safety Nuke. Stop everything to prevent undefined behavior.
            self.nuke_all()
            
            # Reset file
            STATE_FILE.write_text("{}")
            make_hidden(STATE_FILE)
            return {}

    def _save_state(self, data):
        try:
            STATE_FILE.write_text(json.dumps(data, indent=2))
            make_hidden(STATE_FILE) # Ensure it stays hidden
        except: pass

    # ----------------------------------------
    #  POLLING AGENT (The Background Loop)
    # ----------------------------------------
    def run_watcher_loop(self):
        """
        The continuous background loop.
        1. Writes its own PID to watcher.pid
        2. Polls every 2s
        3. Updates JSON only on process death
        4. Exits if 0 processes remain
        """
        # 1. Register Self
        current_pid = os.getpid()
        WATCHER_PID_FILE.write_text(str(current_pid))

        try:
            while True:
                # 2. Poll Interval
                time.sleep(2)

                # Read latest state (to catch new starts)
                state = self._load_state()
                dirty = False
                active_count = 0

                for pid_key, info in state.items():
                    if info.get("status") == "running":
                        pid = info.get("pid")
                        
                        # Check existence
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
                            # 3. Update JSON (Only on death)
                            info["status"] = "stopped" # Changed from 'error' to 'stopped' per your flow
                            info["pid"] = None
                            dirty = True
                
                if dirty:
                    self._save_state(state)

                # 4. Suicide Check
                if active_count == 0:
                    # Double check state hasn't changed while we were writing
                    # (Edge case: user starts project right as we decide to quit)
                    # For simplicity, we quit. The next start command will respawn us.
                    break

        finally:
            # Cleanup lockfile on exit
            if WATCHER_PID_FILE.exists():
                try:
                    WATCHER_PID_FILE.unlink()
                except: pass

    def _ensure_watcher_running(self):
        """
        Checks if the watcher is running. If not, spawns it INVISIBLY.
        """
        # 1. Check if existing watcher is alive
        if WATCHER_PID_FILE.exists():
            try:
                w_pid = int(WATCHER_PID_FILE.read_text().strip())
                if psutil.pid_exists(w_pid):
                    return # Already running
            except:
                pass # Invalid file or process dead
        
        # 2. Spawn new watcher (INVISIBLE)
        cmd = [sys.executable, "-m", "cwm.cli", "run", "_watcher"]
        
        # Redirect everything to NULL so it has no reason to open a stream
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL, # Important for background tasks
            "cwd": str(ORCH_DIR)
        }

        if os.name == 'nt':
            # Windows Magic Flags for "Invisible":
            # 0x08000000 = CREATE_NO_WINDOW
            kwargs["creationflags"] = 0x08000000
            # CRITICAL: shell=False prevents cmd.exe from popping up a window wrapper
            kwargs["shell"] = False 
        else:
            # Linux/Mac Detach
            kwargs["start_new_session"] = True

        subprocess.Popen(cmd, **kwargs)

    # ----------------------------------------
    #  MANUAL CHECK (Used by 'cwm run list')
    # ----------------------------------------
    def get_services_status(self):
        """
        Passive check. Reads state, cleans up zombies immediately, returns state.
        This remains for the 'cwm run list' command to give instant feedback.
        """
        state = self._load_state()
        dirty = False

        for pid_key, info in state.items():
            # FIX: Get 'pid' here so it is available for both if/elif blocks
            pid = info.get("pid")

            if info.get("status") == "running":
                if pid:
                    try:
                        proc = psutil.Process(pid)
                        if proc.status() == psutil.STATUS_ZOMBIE:
                            raise psutil.NoSuchProcess(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        info["status"] = "stopped"
                        info["pid"] = None
                        dirty = True
                else:
                    # Running but no PID? Invalid state.
                    info["status"] = "stopped"
                    dirty = True
            
            # Fix: Now 'pid' is defined, so this check works safely
            elif pid is not None:
                info["pid"] = None
                dirty = True
        
        if dirty:
            self._save_state(state)
            
        return state
    # ----------------------------------------
    #  ACTIONS
    # ----------------------------------------
    # ... (imports remain the same) ...

    # ----------------------------------------
    #  ACTIONS (With Viewer Tracking)
    # ----------------------------------------
    def start_project(self, project_id: int):
        state = self.get_services_status()
        str_id = str(project_id)
        
        if str_id in state and state[str_id]["status"] == "running":
            return False, "Already running."

        data = self.manager.load_projects()
        proj = next((p for p in data.get("projects", []) if p["id"] == project_id), None)
        if not proj: return False, "Project ID not found."

        cmd_str = proj.get("startup_cmd")
        if not cmd_str: return False, "No startup command."

        root_path = Path(proj["path"]).resolve()

        # --- SECURITY GUARD ---
        if not is_safe_startup_cmd(cmd_str, root_path):
            return False, "SECURITY BLOCK: Command deemed unsafe."

        log_file = LOG_DIR / f"{project_id}.log"
        out_file = None 
        
        try:
            # 1. Open File Handle
            out_file = open(log_file, "w", encoding="utf-8")
            
            args = cmd_str if os.name == 'nt' else shlex.split(cmd_str)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            kwargs = {
                "cwd": str(root_path),
                "stdout": out_file,
                "stderr": subprocess.STDOUT,
                "text": True,
                "env": env
            }

            if os.name == 'nt':
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
                kwargs["shell"] = True
            else:
                kwargs["start_new_session"] = True
                kwargs["shell"] = True

            # 2. Launch Server
            proc = subprocess.Popen(args, **kwargs)
            
            # 3. Close Parent Handle (Prevents File Lock)
            out_file.close() 
            
            # 4. Save State (Initialize 'viewers' list)
            new_entry = {
                "project_id": project_id,
                "alias": proj["alias"],
                "pid": proc.pid,
                "viewers": [],  # <--- NEW: Track Viewer PIDs here
                "status": "running",
                "start_time": time.time(),
                "log_path": str(log_file),
                "cmd": cmd_str
            }
            
            validated_entry = validate_service_entry(new_entry)
            state[str_id] = validated_entry
            self._save_state(state)
            
            self._ensure_watcher_running()
            
            return True, f"Started (PID {proc.pid})"

        except Exception as e:
            if out_file: 
                try: out_file.close()
                except: pass
            return False, str(e)

    def register_viewer(self, project_id: int, viewer_pid: int):
        """
        Registers a 'launch' terminal PID so it can be killed later.
        """
        state = self._load_state() # Load fresh to avoid overwrites
        str_id = str(project_id)
        
        if str_id in state:
            # Add to list if not exists
            viewers = state[str_id].get("viewers", [])
            if viewer_pid not in viewers:
                viewers.append(viewer_pid)
                state[str_id]["viewers"] = viewers
                self._save_state(state)

    def stop_project(self, project_id: int):
        """
        Stops the project AND all associated viewer terminals.
        """
        state = self.get_services_status()
        str_id = str(project_id)
        
        if str_id not in state: return False, "Not found."
        
        info = state[str_id]
        main_pid = info.get("pid")
        viewers = info.get("viewers", [])

        # 1. Kill Viewer Terminals (Releases File Locks)
        for v_pid in viewers:
            try:
                if psutil.pid_exists(v_pid):
                    psutil.Process(v_pid).kill()
            except: pass # Already closed manually
        
        # 2. Kill Main Server Process (and children)
        if main_pid:
            try:
                parent = psutil.Process(main_pid)
                for child in parent.children(recursive=True):
                    try: child.kill()
                    except: pass
                parent.kill()
            except psutil.NoSuchProcess:
                pass 
        
        # 3. Update State
        info["status"] = "stopped"
        info["pid"] = None
        info["viewers"] = [] # Clear viewers list
        
        self._save_state(state)
        return True, "Stopped and closed terminals."

    def nuke_all(self):
        """
        HARD RESET: Stops all projects, closes all viewers, kills watcher.
        """
        # 1. Stop all projects (Calls stop_project internally -> Kills Viewers)
        stopped_count = self.stop_all()
        
        # 2. Kill the Agent (Watcher)
        w_success, w_msg = self.kill_watcher()
        
        return stopped_count, w_msg