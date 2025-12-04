import tkinter as tk
from tkinter import ttk, messagebox
import sys
import subprocess
import os
import ctypes
import time
from pathlib import Path
from cwm.service_manager import ServiceManager, STATE_FILE
from cwm.storage_manager import StorageManager

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_window = tk.Frame(canvas, bg="#ffffff")

        self.scrollable_window.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_window, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas = canvas

class CwmApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CWM Orchestrator")
        self.root.geometry("700x600")
        
        self.svc = ServiceManager()
        self.storage = StorageManager()
        
        self.last_mtime = 0
        self.row_widgets = {} 
        
        self.load_logo()

        self.root.configure(bg="#f0f0f0")
        style = ttk.Style()
        try: style.theme_use('clam') 
        except: pass
        
        # Tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)

        self.tab_dashboard = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dashboard, text='  Dashboard  ')
        
        self.tab_projects = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_projects, text='  Projects  ')
        
        self.tab_groups = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_groups, text='  Groups  ')

        self.build_dashboard()
        self.build_projects()
        self.build_groups()

        self.start_watchdog()

    def load_logo(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(script_dir, "logo.png")
            if os.path.exists(logo_path):
                img = tk.PhotoImage(file=logo_path)
                self.root.iconphoto(False, img)
        except Exception:
            pass

    # ==========================
    #  TAB 1: COMPACT DASHBOARD
    # ==========================
    def build_dashboard(self):
        top_bar = tk.Frame(self.tab_dashboard, bg="#e0e0e0", height=30)
        top_bar.pack(fill="x")
        
        tk.Label(top_bar, text="ALIAS", width=25, anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)
        tk.Label(top_bar, text="STATUS", width=10, anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(top_bar, text="PID", width=8, anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(top_bar, text="CONTROLS", anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left", padx=20)

        btn_frame = tk.Frame(top_bar, bg="#e0e0e0")
        btn_frame.pack(side="right", padx=5, pady=2)

        tk.Button(btn_frame, text="⟳", bg="white", relief="flat", width=3, command=self.force_reload).pack(side="left", padx=2)
        tk.Button(btn_frame, text="☠ KILL ALL", bg="#c62828", fg="white", font=("Segoe UI", 8, "bold"), 
                  relief="flat", command=self.action_nuke).pack(side="left", padx=5)

        self.dash_scroll = ScrollableFrame(self.tab_dashboard)
        self.dash_scroll.pack(fill="both", expand=True)
        self.dash_content = self.dash_scroll.scrollable_window

    def update_dashboard_ui(self, force=False):
        try:
            if not STATE_FILE.exists(): current_mtime = 0
            else: current_mtime = os.path.getmtime(STATE_FILE)

            if not force and current_mtime == self.last_mtime: return
            self.last_mtime = current_mtime
            
            if force: state = self.svc.get_services_status()
            else: state = self.svc._load_state()

            active_ids = set()
            sorted_items = sorted(state.items(), key=lambda x: (x[1]['status'] != 'running', x[1]['alias']))

            for index, (pid_str, info) in enumerate(sorted_items):
                active_ids.add(pid_str)
                status = info.get('status', 'stopped').upper()
                pid = info.get('project_id')
                pid_txt = str(info.get('pid') or "-")
                
                if pid_str in self.row_widgets:
                    w = self.row_widgets[pid_str]
                    stat_fg = "#28a745" if status == "RUNNING" else "#dc3545"
                    w['status_lbl'].config(text=status, fg=stat_fg)
                    w['pid_lbl'].config(text=pid_txt)
                    
                    # === BUTTON VISIBILITY LOGIC ===
                    # 1. TERM (Always Visible)
                    w['term_btn'].pack(side="left", padx=2)

                    if status == "RUNNING":
                        # Running: Show Stop, Hide Start/Del
                        w['start_btn'].pack_forget()
                        w['del_btn'].pack_forget()
                        w['stop_btn'].pack(side="left", padx=2)
                    else:
                        # Stopped: Hide Stop, Show Start/Del
                        w['stop_btn'].pack_forget()
                        w['start_btn'].pack(side="left", padx=2)
                        w['del_btn'].pack(side="left", padx=2)

                else:
                    # === CREATE NEW ROW ===
                    bg_col = "#ffffff" if len(self.row_widgets) % 2 == 0 else "#f9f9f9"
                    row = tk.Frame(self.dash_content, bg=bg_col, pady=4)
                    row.pack(fill="x", padx=2, pady=1)

                    stat_fg = "#28a745" if status == "RUNNING" else "#dc3545"

                    tk.Label(row, text=info['alias'], width=25, anchor="w", bg=bg_col, font=("Segoe UI", 10)).pack(side="left", padx=10)
                    status_lbl = tk.Label(row, text=status, width=10, fg=stat_fg, anchor="w", bg=bg_col, font=("Segoe UI", 8, "bold"))
                    status_lbl.pack(side="left")
                    pid_lbl = tk.Label(row, text=pid_txt, width=8, anchor="w", bg=bg_col, fg="#666", font=("Segoe UI", 9))
                    pid_lbl.pack(side="left")

                    actions_frame = tk.Frame(row, bg=bg_col)
                    actions_frame.pack(side="left", padx=20)

                    # --- CREATE BUTTONS ---
                    # 1. TERM (Black)
                    term_btn = tk.Button(actions_frame, text="TERM", bg="#212529", fg="white", relief="flat", width=6, font=("Segoe UI", 8),
                                         command=lambda p=pid: self.action_launch(p))
                    
                    # 2. STOP (Red Text)
                    stop_btn = tk.Button(actions_frame, text="STOP", bg="#ffebee", fg="#c62828", relief="flat", width=6, font=("Segoe UI", 8),
                                         command=lambda p=pid: self.action_stop(p))
                    
                    # 3. START (Green Background)
                    start_btn = tk.Button(actions_frame, text="START", bg="#d4edda", fg="#155724", relief="flat", width=6, font=("Segoe UI", 8, "bold"),
                                          command=lambda p=pid: self.action_run(p, None, switch_tab=False))

                    # 4. DEL (Red Background)
                    del_btn = tk.Button(actions_frame, text="DEL", bg="#c62828", fg="white", relief="flat", width=6, font=("Segoe UI", 8, "bold"),
                                        command=lambda p=pid: self.action_delete(p))

                    # --- PACKING ORDER: TERM -> [START/STOP] -> DEL ---
                    term_btn.pack(side="left", padx=2)

                    if status == "RUNNING":
                        stop_btn.pack(side="left", padx=2)
                    else:
                        start_btn.pack(side="left", padx=2)
                        del_btn.pack(side="left", padx=2)

                    self.row_widgets[pid_str] = {
                        'frame': row, 'status_lbl': status_lbl, 'pid_lbl': pid_lbl,
                        'stop_btn': stop_btn, 'del_btn': del_btn, 'start_btn': start_btn, 'term_btn': term_btn
                    }

            current_ids = list(self.row_widgets.keys())
            for pid_str in current_ids:
                if pid_str not in active_ids:
                    self.row_widgets[pid_str]['frame'].destroy()
                    del self.row_widgets[pid_str]

        except Exception as e:
            print(f"UI Error: {e}")

    # ==========================
    #  TAB 2: PROJECTS
    # ==========================
    def build_projects(self):
        toolbar = tk.Frame(self.tab_projects, bg="#f0f0f0", pady=2)
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="Refresh", command=self.refresh_projects_list, width=8).pack(side="right", padx=10)

        self.proj_scroll = ScrollableFrame(self.tab_projects)
        self.proj_scroll.pack(fill="both", expand=True)
        self.proj_content = self.proj_scroll.scrollable_window
        self.refresh_projects_list()

    def refresh_projects_list(self):
        for widget in self.proj_content.winfo_children(): widget.destroy()
        data = self.storage.load_projects()
        
        for p in data.get("projects", []):
            row = tk.Frame(self.proj_content, bg="white", pady=5, highlightthickness=1, highlightbackground="#e0e0e0")
            row.pack(fill="x", padx=10, pady=2)
            
            info = tk.Frame(row, bg="white")
            info.pack(side="left", padx=10, fill="x", expand=True)
            
            tk.Label(info, text=p['alias'], bg="white", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
            cmd = p.get('startup_cmd', '')
            if isinstance(cmd, list): cmd = " ".join(cmd)
            tk.Label(info, text=f"{cmd or 'No command'}", bg="white", fg="#555", font=("Consolas", 8), anchor="w").pack(fill="x")

            tk.Button(row, text="▶ RUN", bg="#d4edda", fg="#155724", font=("Segoe UI", 9, "bold"), relief="flat", width=8,
                      command=lambda pid=p['id'], alias=p['alias']: self.action_run(pid, alias)).pack(side="right", padx=10)

    # ==========================
    #  TAB 3: GROUPS
    # ==========================
    def build_groups(self):
        toolbar = tk.Frame(self.tab_groups, bg="#f0f0f0", pady=2)
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="Refresh", command=self.refresh_groups_list, width=8).pack(side="right", padx=10)

        self.group_scroll = ScrollableFrame(self.tab_groups)
        self.group_scroll.pack(fill="both", expand=True)
        self.group_content = self.group_scroll.scrollable_window
        self.refresh_groups_list()

    def refresh_groups_list(self):
        for widget in self.group_content.winfo_children(): widget.destroy()
        data = self.storage.load_projects()
        id_to_alias = {p["id"]: p["alias"] for p in data.get("projects", [])}

        for g in data.get("groups", []):
            row = tk.Frame(self.group_content, bg="white", pady=8, highlightthickness=1, highlightbackground="#e0e0e0")
            row.pack(fill="x", padx=10, pady=4)

            info = tk.Frame(row, bg="white")
            info.pack(side="left", padx=10, fill="x", expand=True)

            p_ids = g.get('project_ids', [])
            p_names = [id_to_alias.get(pid, f"#{pid}") for pid in p_ids]
            p_names_str = ", ".join(p_names) if p_names else "(Empty)"

            tk.Label(info, text=f"{g['alias']}", bg="white", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
            tk.Label(info, text=f"Contains: {p_names_str}", bg="white", fg="#666", font=("Segoe UI", 8), anchor="w").pack(fill="x")

            tk.Button(row, text="▶ LAUNCH", bg="#cce5ff", fg="#004085", font=("Segoe UI", 9, "bold"), relief="flat", width=10,
                      command=lambda gid=g['id'], name=g['alias']: self.action_run_group_smart(gid, name)).pack(side="right", padx=10)

    # ==========================
    #  ACTIONS & LOGIC
    # ==========================
    def force_reload(self):
        self.update_dashboard_ui(force=True)

    def action_run(self, pid, alias, switch_tab=True):
        state = self.svc.get_services_status()
        if str(pid) in state and state[str(pid)]['status'] == 'running':
            messagebox.showinfo("Running", f"'{alias}' is already active.", parent=self.root)
            return

        success, msg = self.svc.start_project(pid)
        if success:
            if switch_tab: self.notebook.select(self.tab_dashboard)
            self.update_dashboard_ui(force=True)
        else:
            messagebox.showerror("Error", msg, parent=self.root)

    def action_run_group_smart(self, gid, group_alias):
        data = self.storage.load_projects()
        group = next((g for g in data.get("groups", []) if g["id"] == gid), None)
        if not group: return

        pids = group.get("project_ids", [])
        if not pids: return

        state = self.svc.get_services_status()
        to_start = []
        
        for pid in pids:
            if str(pid) not in state or state[str(pid)]['status'] != 'running':
                to_start.append(pid)
        
        if not to_start:
            messagebox.showinfo("Group Active", f"All projects in '{group_alias}' are already running.", parent=self.root)
            return

        started_count = 0
        for pid in to_start:
            success, _ = self.svc.start_project(pid)
            if success: started_count += 1
        
        if started_count > 0:
            self.notebook.select(self.tab_dashboard)
            self.update_dashboard_ui(force=True)

    def action_stop(self, pid):
        self.svc.stop_project(pid)
        self.update_dashboard_ui(force=True)

    def action_delete(self, pid):
        if messagebox.askyesno("Remove", "Stop and remove from list?", parent=self.root):
            self.svc.remove_service_entry(pid)
            self.update_dashboard_ui(force=True)

    def action_launch(self, pid):
        cmd = [sys.executable, "-m", "cwm.cli", "run", "launch", str(pid)]
        try: subprocess.Popen(cmd)
        except Exception as e: messagebox.showerror("Error", str(e), parent=self.root)

    def action_nuke(self):
        if messagebox.askyesno("KILL ALL", "Confirm: Kill ALL projects and exit?", parent=self.root):
            self.svc.nuke_all()
            self.root.destroy()
            sys.exit(0)

    def start_watchdog(self):
        self.update_dashboard_ui(force=False)
        self.root.after(500, self.start_watchdog)

def run_gui():
    if sys.platform == 'win32':
        myappid = 'cwm.orchestrator.gui.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    root = tk.Tk()
    app = CwmApp(root)
    root.mainloop()

if __name__ == "__main__":
    run_gui()