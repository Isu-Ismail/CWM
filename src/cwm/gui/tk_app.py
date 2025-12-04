import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
import subprocess
import os
import ctypes
import time
from pathlib import Path
from cwm.service_manager import ServiceManager, STATE_FILE
from cwm.storage_manager import StorageManager
from cwm.project_cmd import is_safe_startup_cmd



class CommandListEditor(tk.Frame):
    def __init__(self, parent, existing_commands=None):
        super().__init__(parent)
        self.rows = []
        
        # 1. Container for the rows (with scroll support if needed, simple frame for now)
        self.list_frame = tk.Frame(self)
        self.list_frame.pack(fill="x", expand=True)
        
        # 2. "Add Step" Button
        self.add_btn = tk.Button(self, text="+ Add Command Step", command=self.add_row, bg="#e0e0e0")
        self.add_btn.pack(pady=5, anchor="w")

        # 3. Pre-fill existing commands (Edit Mode)
        if existing_commands:
            if isinstance(existing_commands, str):
                # If it was a string (old format), split it or just add it as one
                self.add_row(existing_commands)
            elif isinstance(existing_commands, list):
                for cmd in existing_commands:
                    self.add_row(cmd)
        else:
            # Default: Start with one empty row
            self.add_row("")

    def add_row(self, text=""):
        row_frame = tk.Frame(self.list_frame)
        row_frame.pack(fill="x", pady=2)
        
        # Text Entry
        entry = tk.Entry(row_frame)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        entry.insert(0, str(text))
        
        # Remove Button (-)
        # We use a lambda to pass the specific row_frame to the remove function
        remove_btn = tk.Button(row_frame, text="-", width=3, fg="red",
                               command=lambda: self.remove_row(row_frame, entry))
        remove_btn.pack(side="right")
        
        # Store reference so we can get data later
        self.rows.append((row_frame, entry))

    def remove_row(self, frame, entry):
        # Remove from screen
        frame.destroy()
        # Remove from our data list
        self.rows = [row for row in self.rows if row[1] != entry]

    def get_data(self):
        # Collect all text from entries
        commands = []
        for row, entry in self.rows:
            val = entry.get().strip()
            if val: # Only add if not empty
                commands.append(val)
        
        # Return as a LIST (backend expects list for chaining)
        # If empty, return None or empty list
        if not commands: return []
        return commands

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
        # 1. Requested Main Window Size
        self.root.geometry("600x600")
        
        self.svc = ServiceManager()
        self.storage = StorageManager()
        
        self.last_mtime = 0
        self.row_widgets = {} 
        
        self.load_logo()

        self.root.configure(bg="#f0f0f0")
        style = ttk.Style()
        try: style.theme_use('clam') 
        except: pass
        
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
                self.root.iconphoto(True, img)
        except Exception: pass

    # ==========================
    #  TAB 1: DASHBOARD
    # ==========================



    def toggle_select_all(self):
        """Sets all row checkboxes to match the master 'Select All' checkbox."""
        state = self.select_all_var.get()
        for pid_str, var in self.row_check_vars.items():
            var.set(state)

    def action_bulk_delete(self):
        """Deletes all selected projects."""
        # Filter for checked items
        selected_ids = [pid_str for pid_str, var in self.row_check_vars.items() if var.get()]
        
        if not selected_ids:
            messagebox.showinfo("Info", "No projects selected.")
            return

        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {len(selected_ids)} projects?"):
            return

        success_count = 0
        for pid_str in selected_ids:
            try:
                # The 'remove_entry' method expects an INT, but pid_str is a STRING from JSON keys
                self.svc.remove_entry(int(pid_str))
                success_count += 1
            except Exception as e:
                print(f"Error deleting {pid_str}: {e}")

        # Refresh UI immediately
        self.force_reload()
        
        # Reset master checkbox
        self.select_all_var.set(False)

        
    def build_dashboard(self):
        # Initialize dictionary to track checkbox states { "project_id_str": BooleanVar }
        self.row_check_vars = {}

        top_bar = tk.Frame(self.tab_dashboard, bg="#e0e0e0", height=30)
        top_bar.pack(fill="x")
        
        # --- 1. Master "Select All" Checkbox ---
        self.select_all_var = tk.BooleanVar(value=False)
        self.chk_select_all = tk.Checkbutton(top_bar, variable=self.select_all_var, bg="#e0e0e0", 
                                             command=self.toggle_select_all)
        self.chk_select_all.pack(side="left", padx=(5, 0))

        # --- 2. Header Labels ---
        tk.Label(top_bar, text="ALIAS", width=20, anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        tk.Label(top_bar, text="STATUS", width=8, anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(top_bar, text="PID", width=6, anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(top_bar, text="CONTROLS", anchor="w", bg="#e0e0e0", font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)

        # --- 3. Toolbar Buttons ---
        btn_frame = tk.Frame(top_bar, bg="#e0e0e0")
        btn_frame.pack(side="right", padx=5, pady=2)

        # NEW: Bulk Delete Button
        tk.Button(btn_frame, text="🗑 Del Selected", bg="#c62828", fg="white", font=("Segoe UI", 8, "bold"), 
                  relief="flat", command=self.action_bulk_delete).pack(side="left", padx=5)

        tk.Button(btn_frame, text="⟳", bg="white", relief="flat", width=3, command=self.force_reload).pack(side="left", padx=2)
        tk.Button(btn_frame, text="☠ KILL", bg="black", fg="white", font=("Segoe UI", 8, "bold"), 
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
                    # --- Update Existing Row ---
                    w = self.row_widgets[pid_str]
                    stat_fg = "#28a745" if status == "RUNNING" else "#dc3545"
                    w['status_lbl'].config(text=status, fg=stat_fg)
                    w['pid_lbl'].config(text=pid_txt)
                    w['term_btn'].pack(side="left", padx=2)

                    if status == "RUNNING":
                        w['start_btn'].pack_forget()
                        w['del_btn'].pack_forget()
                        w['stop_btn'].pack(side="left", padx=2)
                    else:
                        w['stop_btn'].pack_forget()
                        w['start_btn'].pack(side="left", padx=2)
                        w['del_btn'].pack(side="left", padx=2)
                else:
                    # --- Create New Row ---
                    bg_col = "#ffffff" if len(self.row_widgets) % 2 == 0 else "#f9f9f9"
                    row = tk.Frame(self.dash_content, bg=bg_col, pady=4)
                    row.pack(fill="x", padx=2, pady=1)

                    # 1. Row Checkbox
                    var = tk.BooleanVar(value=False)
                    chk = tk.Checkbutton(row, variable=var, bg=bg_col)
                    chk.pack(side="left", padx=(5, 0))
                    self.row_check_vars[pid_str] = var # Register for bulk actions

                    stat_fg = "#28a745" if status == "RUNNING" else "#dc3545"

                    tk.Label(row, text=info['alias'], width=20, anchor="w", bg=bg_col, font=("Segoe UI", 10)).pack(side="left", padx=5)
                    status_lbl = tk.Label(row, text=status, width=8, fg=stat_fg, anchor="w", bg=bg_col, font=("Segoe UI", 8, "bold"))
                    status_lbl.pack(side="left")
                    pid_lbl = tk.Label(row, text=pid_txt, width=6, anchor="w", bg=bg_col, fg="#666", font=("Segoe UI", 9))
                    pid_lbl.pack(side="left")

                    actions_frame = tk.Frame(row, bg=bg_col)
                    actions_frame.pack(side="left", padx=10)

                    term_btn = tk.Button(actions_frame, text="TERM", bg="#212529", fg="white", relief="flat", width=5, font=("Segoe UI", 8),
                                         command=lambda p=pid: self.action_launch(p))
                    stop_btn = tk.Button(actions_frame, text="STOP", bg="#ffebee", fg="#c62828", relief="flat", width=5, font=("Segoe UI", 8),
                                         command=lambda p=pid: self.action_stop(p))
                    start_btn = tk.Button(actions_frame, text="START", bg="#d4edda", fg="#155724", relief="flat", width=5, font=("Segoe UI", 8, "bold"),
                                          command=lambda p=pid: self.action_run(p, None, switch_tab=False))
                    del_btn = tk.Button(actions_frame, text="DEL", bg="#c62828", fg="white", relief="flat", width=5, font=("Segoe UI", 8, "bold"),
                                        command=lambda p=pid: self.action_delete(p))

                    term_btn.pack(side="left", padx=2)
                    if status == "RUNNING": stop_btn.pack(side="left", padx=2)
                    else:
                        start_btn.pack(side="left", padx=2)
                        del_btn.pack(side="left", padx=2)

                    self.row_widgets[pid_str] = {
                        'frame': row, 
                        'status_lbl': status_lbl, 
                        'pid_lbl': pid_lbl, 
                        'stop_btn': stop_btn, 
                        'del_btn': del_btn, 
                        'start_btn': start_btn, 
                        'term_btn': term_btn
                    }

            # Cleanup Logic (Remove Deleted Rows)
            current_ids = list(self.row_widgets.keys())
            for pid_str in current_ids:
                if pid_str not in active_ids:
                    # Destroy UI
                    self.row_widgets[pid_str]['frame'].destroy()
                    del self.row_widgets[pid_str]
                    # Cleanup Checkbox Memory
                    if pid_str in self.row_check_vars:
                        del self.row_check_vars[pid_str]

        except Exception as e: print(f"UI Error: {e}")

    # ==========================
    #  TAB 2: PROJECTS
    # ==========================
    def build_projects(self):
        toolbar = tk.Frame(self.tab_projects, bg="#f0f0f0", pady=2)
        toolbar.pack(fill="x")
        
        tk.Button(toolbar, text="+ Add Project", bg="#007acc", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", 
                  command=lambda: self.action_edit_project(None)).pack(side="left", padx=10)
        
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
            info.pack(side="left", padx=5, fill="x", expand=True)
            
            tk.Label(info, text=p['alias'], bg="white", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
            
            # --- START OF CHANGE ---
            cmd = p.get('startup_cmd', '')
            if isinstance(cmd, list): cmd = " && ".join(cmd) # Join lists with readable separator
            
            # Truncate logic: If longer than 50 chars, cut it and add "..."
            cmd_str = str(cmd) if cmd else 'No command'
            if len(cmd_str) > 50:
                cmd_str = cmd_str[:47] + "..."
            
            tk.Label(info, text=cmd_str, bg="white", fg="#555", font=("Consolas", 8), anchor="w").pack(fill="x")
            # --- END OF CHANGE ---

            tk.Button(row, text="▶", bg="#d4edda", fg="#155724", font=("Segoe UI", 9, "bold"), relief="flat", width=3,
                      command=lambda pid=p['id'], alias=p['alias']: self.action_run(pid, alias)).pack(side="right", padx=2)
            
            # EDIT Button
            tk.Button(row, text="✎", bg="#e0e0e0", fg="#333", font=("Segoe UI", 9), relief="flat", width=3,
                      command=lambda pid=p['id']: self.action_edit_project(pid)).pack(side="right", padx=2)


    # ==========================
    #  TAB 3: GROUPS
    # ==========================
    def build_groups(self):
        toolbar = tk.Frame(self.tab_groups, bg="#f0f0f0", pady=2)
        toolbar.pack(fill="x")
        
        tk.Button(toolbar, text="+ Add Group", bg="#007acc", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", 
                  command=lambda: self.action_edit_group(None)).pack(side="left", padx=10)

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
            info.pack(side="left", padx=5, fill="x", expand=True)

            p_ids = g.get('project_ids', [])
            p_names = [id_to_alias.get(pid, f"#{pid}") for pid in p_ids]
            p_names_str = ", ".join(p_names) if p_names else "(Empty)"

            tk.Label(info, text=f"{g['alias']}", bg="white", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
            tk.Label(info, text=f"Contains: {p_names_str}", bg="white", fg="#666", font=("Segoe UI", 8), anchor="w").pack(fill="x")

            # LAUNCH Button
            tk.Button(row, text="▶", bg="#cce5ff", fg="#004085", font=("Segoe UI", 9, "bold"), relief="flat", width=3,
                      command=lambda gid=g['id'], name=g['alias']: self.action_run_group_smart(gid, name)).pack(side="right", padx=2)
            
            # EDIT Button
            tk.Button(row, text="✎", bg="#e0e0e0", fg="#333", font=("Segoe UI", 9), relief="flat", width=3,
                      command=lambda gid=g['id']: self.action_edit_group(gid)).pack(side="right", padx=2)
            
            # DELETE Button (Group Only)
            tk.Button(row, text="✖", bg="#ffcdd2", fg="#b71c1c", font=("Segoe UI", 9, "bold"), relief="flat", width=3,
                      command=lambda gid=g['id']: self.action_delete_group(gid)).pack(side="right", padx=2)

    # ==========================
    #  MODAL: PROJECT ADD/EDIT
    # ==========================
    def action_edit_project(self, project_id=None):
        mode = "Edit" if project_id else "Add New"
        top = tk.Toplevel(self.root)
        top.title(f"{mode} Project")
        top.geometry("500x400") # Increased height slightly for the list
        top.configure(bg="white")
        
        x = self.root.winfo_x() + (self.root.winfo_width()//2) - 250
        y = self.root.winfo_y() + (self.root.winfo_height()//2) - 200
        top.geometry(f"+{x}+{y}")

        data = self.storage.load_projects()
        projects = data.get("projects", [])
        
        current_data = {}
        if project_id:
            current_data = next((p for p in projects if p["id"] == project_id), {})
            if not current_data:
                top.destroy(); return

        # Fields
        path_var = tk.StringVar(value=current_data.get("path", ""))
        alias_var = tk.StringVar(value=current_data.get("alias", ""))
        
        # --- CHANGE 1: REMOVE THE OLD CMD VAR SETUP ---
        # (We don't need raw_cmd string logic here anymore)

        # UI Layout
        tk.Label(top, text="Project Path:", bg="white", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        path_frame = tk.Frame(top, bg="white")
        path_frame.pack(fill="x", padx=20)
        tk.Entry(path_frame, textvariable=path_var, bg="#f0f0f0").pack(side="left", fill="x", expand=True)
        
        def browse():
            d = filedialog.askdirectory(parent=top)
            if d: 
                path_var.set(d)
                if not alias_var.get(): alias_var.set(os.path.basename(d))
        
        tk.Button(path_frame, text="Browse...", command=browse).pack(side="right", padx=(5,0))

        tk.Label(top, text="Alias:", bg="white", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 5))
        tk.Entry(top, textvariable=alias_var, bg="#f0f0f0").pack(fill="x", padx=20)

        # --- CHANGE 2: USE NEW LIST EDITOR WIDGET ---
        tk.Label(top, text="Startup Commands (Steps):", bg="white", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 5))
        tk.Label(top, text='Tip: Use $ROOT for the project folder (e.g., "$ROOT\\hello.exe")', 
         bg="white", fg="#666", font=("Segoe UI", 8)).pack(anchor="w", padx=20, pady=(0, 5))
        # Load existing commands (works if it's a list or string)
        current_cmds = current_data.get("startup_cmd", [])
        cmd_editor = CommandListEditor(top, existing_commands=current_cmds)
        cmd_editor.pack(fill="x", padx=20)
        # --------------------------------------------

        def save():
            path_val = path_var.get().strip()
            alias_val = alias_var.get().strip()
            
            # --- CHANGE 3: GET DATA FROM EDITOR WIDGET ---
            cmd_val = cmd_editor.get_data() # This returns a LIST of strings
            
            if not path_val or not alias_val or not cmd_val:
                messagebox.showerror("Error", "All fields required.", parent=top); return
            
            target = Path(path_val).resolve()
            if not target.exists():
                messagebox.showerror("Error", "Directory invalid.", parent=top); return

            # Convert list to string for safety check (if your checker expects string)
            check_str = " && ".join(cmd_val) if isinstance(cmd_val, list) else str(cmd_val)
            if not is_safe_startup_cmd(check_str, target):
                messagebox.showerror("Error", "Unsafe command.", parent=top); return

            # Validation: Exclude self from checks
            for p in projects:
                if p["id"] == project_id: continue
                if p["path"] == str(target):
                    messagebox.showerror("Error", "Path already saved.", parent=top); return
                if p["alias"] == alias_val:
                    messagebox.showerror("Error", "Alias already exists.", parent=top); return

            if project_id:
                # Update
                p = next(p for p in projects if p["id"] == project_id)
                p["path"] = str(target)
                p["alias"] = alias_val
                p["startup_cmd"] = cmd_val # Saves as list
            else:
                # Create
                new_id = data.get("last_id", 0) + 1
                projects.append({
                    "id": new_id, "alias": alias_val, "path": str(target),
                    "hits": 0, "startup_cmd": cmd_val # Saves as list
                })
                data["last_id"] = new_id
            
            self.storage.save_projects(data)
            self.refresh_projects_list()
            top.destroy()

        tk.Button(top, text="Save", bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", command=save).pack(pady=20)
    # ==========================
    #  MODAL: GROUP ADD/EDIT
    # ==========================
    def action_edit_group(self, group_id=None):
        mode = "Edit" if group_id else "Add New"
        # 2. Requested 500x500 Group Window
        top = tk.Toplevel(self.root)
        top.title(f"{mode} Group")
        top.geometry("500x500")
        top.configure(bg="white")
        
        x = self.root.winfo_x() + (self.root.winfo_width()//2) - 250
        y = self.root.winfo_y() + (self.root.winfo_height()//2) - 250
        top.geometry(f"+{x}+{y}")

        data = self.storage.load_projects()
        projects = data.get("projects", [])
        groups = data.get("groups", [])
        
        if len(projects) < 2:
            messagebox.showwarning("Warning", "Need 2+ projects.", parent=top); top.destroy(); return

        current_g = {}
        if group_id:
            current_g = next((g for g in groups if g["id"] == group_id), {})
            default_alias = current_g.get("alias", "")
            current_ids = set(current_g.get("project_ids", []))
        else:
            default_alias = f"group{data.get('last_group_id', 0) + 1}"
            current_ids = set()

        tk.Label(top, text="Group Alias:", bg="white", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        alias_var = tk.StringVar(value=default_alias)
        tk.Entry(top, textvariable=alias_var, bg="#f0f0f0").pack(fill="x", padx=20)

        tk.Label(top, text="Select Projects (Min 2):", bg="white", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(15, 5))

        list_frame = tk.Frame(top, bg="white", highlightthickness=1, highlightbackground="#ccc")
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        canvas = tk.Canvas(list_frame, bg="white")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scroll_content = tk.Frame(canvas, bg="white")
        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        check_vars = {}
        for p in projects:
            var = tk.BooleanVar(value=(p["id"] in current_ids))
            chk = tk.Checkbutton(scroll_content, text=f"{p['alias']} ({p['path']})", variable=var, bg="white", anchor="w")
            chk.pack(fill="x", padx=5, pady=2)
            check_vars[p["id"]] = var

        def save():
            selected_ids = [pid for pid, var in check_vars.items() if var.get()]
            if len(selected_ids) < 2:
                messagebox.showerror("Error", "Select at least 2 projects.", parent=top); return

            new_set = set(selected_ids)
            alias_val = alias_var.get().strip()
            if not alias_val:
                messagebox.showerror("Error", "Alias required.", parent=top); return

            # Validation
            for g in groups:
                if g["id"] == group_id: continue # Skip self
                if set(g.get("project_ids", [])) == new_set:
                    messagebox.showerror("Error", "Group with these projects already exists.", parent=top); return
                if g["alias"] == alias_val:
                    messagebox.showerror("Error", "Alias already exists.", parent=top); return

            if group_id:
                # Update
                g = next(g for g in groups if g["id"] == group_id)
                g["alias"] = alias_val
                g["project_ids"] = selected_ids
                # Update links
                for p in projects:
                    if p["id"] in current_ids and p["id"] not in new_set: p["group"] = None
                    if p["id"] in new_set: p["group"] = group_id
            else:
                # Create
                new_gid = data.get("last_group_id", 0) + 1
                groups.append({"id": new_gid, "alias": alias_val, "project_ids": selected_ids})
                for p in projects:
                    if p["id"] in selected_ids: p["group"] = new_gid
                data["last_group_id"] = new_gid

            self.storage.save_projects(data)
            self.refresh_groups_list()
            top.destroy()

        tk.Button(top, text="Save Group", bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", command=save).pack(pady=20)

    # ==========================
    #  STANDARD ACTIONS
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

        for pid in to_start:
            self.svc.start_project(pid)
        self.notebook.select(self.tab_dashboard)
        self.update_dashboard_ui(force=True)

    def action_stop(self, pid):
        self.svc.stop_project(pid)
        self.update_dashboard_ui(force=True)

    def action_delete(self, pid):
        if messagebox.askyesno("Remove", "Stop and remove from list?", parent=self.root):
            self.svc.remove_service_entry(pid)
            self.update_dashboard_ui(force=True)
            
    def action_delete_group(self, gid):
        # New Delete Group action for the button
        if messagebox.askyesno("Delete Group", "Delete this group? (Projects will remain)", parent=self.root):
            data = self.storage.load_projects()
            groups = data.get("groups", [])
            projects = data.get("projects", [])
            
            # Remove
            groups = [g for g in groups if g["id"] != gid]
            # Unlink
            for p in projects:
                if p.get("group") == gid: p["group"] = None
                
            data["groups"] = groups
            self.storage.save_projects(data)
            self.refresh_groups_list()

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