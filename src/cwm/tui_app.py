# src/cwm/tui_app.py
import time
import subprocess
import os
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Label, Log
from textual.screen import Screen
from textual import on

try:
    from .service_manager import ServiceManager
except ImportError:
    ServiceManager = None

class LogsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, project_id: int, log_path: str, alias: str):
        super().__init__()
        self.project_id = project_id
        self.log_path = log_path
        self.alias = alias
        self.log_view = Log(highlight=True, id="log_view")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label(f" [LOGS] {self.alias} ", id="log_header")
        yield self.log_view
        yield Footer()

    def on_mount(self) -> None:
        self.update_logs()
        self.set_interval(1.0, self.update_logs)

    def update_logs(self) -> None:
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                self.log_view.clear()
                self.log_view.write(content)
        except:
            self.log_view.write("Waiting for logs...")

class CwmTui(App):
    CSS = """
    Screen { background: #1e1e1e; color: #d4d4d4; }
    DataTable { height: 1fr; border-top: solid #007acc; }
    DataTable > .datatable--header { background: #252526; color: #569cd6; text-style: bold; }
    DataTable > .datatable--cursor { background: #094771; color: white; }
    #log_header { background: #007acc; color: white; width: 100%; padding: 1; text-align: center; text-style: bold; }
    #status_bar { dock: bottom; height: 1; background: #007acc; color: white; padding-left: 1; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self.svc = ServiceManager()
        self.projects = []
        self.row_keys = set() 

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(cursor_type="row")
        yield Label(" Loading...", id="status_bar")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "CWM Manager"
        table = self.query_one(DataTable)
        table.add_columns("ID", "Project", "Status", "PID", "Power", "Logs", "Code")
        self._load_initial_rows()
        self.set_interval(1.0, self._update_rows)

    def _load_initial_rows(self):
        table = self.query_one(DataTable)
        data = self.svc.manager.load_projects()
        self.projects = sorted(data.get("projects", []), key=lambda x: x["id"])
        
        for p in self.projects:
            key = str(p["id"])
            if key not in self.row_keys:
                table.add_row(
                    str(p["id"]), p["alias"], "...", "-", "[...]", "[LOGS]", "[CODE]", key=key
                )
                self.row_keys.add(key)
        self._update_rows()

    def _update_rows(self):
        table = self.query_one(DataTable)
        active = self.svc.get_running_services()
        active_map = {info["project_id"]: info for info in active.values()}
        running_count = 0

        for p in self.projects:
            pid = p["id"]
            key = str(pid)
            info = active_map.get(pid)
            
            if info:
                status = Text(" [ACTIVE] ", style="bold green reverse")
                sys_pid = str(info["pid"])
                power_btn = Text(" [STOP] ", style="bold red")
                running_count += 1
            else:
                status = Text(" [OFFLINE]", style="dim white")
                sys_pid = "-"
                power_btn = Text(" [START]", style="bold green")

            table.update_cell(key, "Status", status)
            table.update_cell(key, "PID", sys_pid)
            table.update_cell(key, "Power", power_btn)
            
        sb = self.query_one("#status_bar")
        sb.update(f" Services: {running_count}/{len(self.projects)} | Press 'q' to Quit")

    @on(DataTable.CellSelected)
    def handle_click(self, event: DataTable.CellSelected):
        row_key = event.row_key.value
        col_index = event.coordinate.column
        project_id = int(row_key)
        
        proj = next((p for p in self.projects if p["id"] == project_id), None)
        if not proj: return

        active = self.svc.get_running_services()
        is_running = any(info["project_id"] == project_id for info in active.values())

        if col_index == 4: # POWER
            if is_running:
                self.svc.stop_project(project_id)
                self.notify(f"Stopped {proj['alias']}")
            else:
                success, msg = self.svc.start_project(project_id)
                if success: self.notify(f"Started {proj['alias']}")
                else: self.notify(f"Error: {msg}", severity="error")
            self._update_rows()

        elif col_index == 5: # LOGS
            info = next((i for i in active.values() if i["project_id"] == project_id), None)
            if info: self.push_screen(LogsScreen(project_id, info["log_path"], proj["alias"]))
            else: self.notify("Project offline.", severity="warning")

        elif col_index == 6: # CODE
            path = proj["path"]
            config = self.svc.manager.get_config()
            editor = config.get("default_editor", "code")
            try:
                if os.name == 'nt':
                    subprocess.Popen(f'start "" {editor} .', cwd=path, shell=True)
                else:
                    subprocess.Popen([editor, "."], cwd=path)
                self.notify("Editor Launched")
            except: self.notify("Launch failed", severity="error")

def run_tui():
    app = CwmTui()
    app.run()