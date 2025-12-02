# src/cwm/gui_app.py

import time
import threading
import flet as ft

try:
    from .service_manager import ServiceManager
except ImportError:
    ServiceManager = None


class CwmGui:
    def __init__(self, page: ft.Page):
        self.page = page
        self.svc = ServiceManager()

        self.page.title = "Job Management Dashboard"
        self.page.theme_mode = "light"
        self.page.padding = 0
        self.page.window_width = 1200
        self.page.window_height = 800
        self.page.bgcolor = "#F9FAFB"

        self.tracked_ids = set()
        self.row_controls = {}

        data = self.svc.manager.load_projects()
        self.projects = data.get("projects", [])
        self.groups = data.get("groups", [])
        self.project_map = {p["id"]: p for p in self.projects}

        active = self.svc.get_running_services()
        for info in active.values():
            self.tracked_ids.add(info["project_id"])

        self._init_dropdowns()
        self._build_shell()
        self.navigate("dashboard")

        # 🚀 FIX: polling will start only after UI is mounted
        self.page.on_resize = self._start_polling_once
        self._poll_started = False

        
    def _start_polling_once(self, e):
        if not self._poll_started:
            self._poll_started = True
            self.running = True
            self.th = threading.Thread(target=self._poll_loop, daemon=True)
            self.th.start()



    def _start_polling_after_render(self, e):
        if not hasattr(self, "_polling_started"):
            self._polling_started = True
            self.running = True
            self.th = threading.Thread(target=self._poll_loop, daemon=True)
            self.th.start()

    # -------------------------------------------------------------------------
    # Initial UI building
    # -------------------------------------------------------------------------
    def _init_dropdowns(self):
        self.project_dropdown = ft.Dropdown(
            label="Select Project",
            options=[
                ft.dropdown.Option(str(p["id"]), p["alias"]) for p in self.projects
            ],
            width=400,
            border_radius=5,
        )
        self.group_dropdown = ft.Dropdown(
            label="Select Group",
            options=[ft.dropdown.Option(str(g["id"]), g["alias"]) for g in self.groups],
            width=400,
            border_radius=5,
        )

    def _build_shell(self):
        nav_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon("grid_view", color="black"),
                            ft.Text("Job Manager", weight="bold", size=16),
                            ft.Container(width=20),
                            ft.TextButton(
                                "Dashboard",
                                on_click=lambda _: self.navigate("dashboard"),
                            ),
                            ft.TextButton(
                                "Projects",
                                on_click=lambda _: self.navigate("projects"),
                            ),
                            ft.TextButton(
                                "Groups", on_click=lambda _: self.navigate("groups")
                            ),
                        ]
                    ),
                ],
                alignment="spaceBetween",
            ),
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            bgcolor="white",
            border=ft.border.only(bottom=ft.border.BorderSide(1, "#E5E7EB")),
        )

        # Main body is centered narrow column
        self.body_container = ft.Container(
            expand=True,
            padding=20,
            alignment=ft.alignment.top_center,
        )

        self.page.add(nav_bar, self.body_container)

    def navigate(self, view_name):
        self.body_container.content = None
        if view_name == "dashboard":
            self.body_container.content = self._view_dashboard()
        elif view_name == "projects":
            self.body_container.content = self._view_projects_list()
        elif view_name == "groups":
            self.body_container.content = self._view_groups_list()
        self.page.update()

    # -------------------------------------------------------------------------
    # Dashboard view
    # -------------------------------------------------------------------------
    def _view_dashboard(self):
        self.search_field = ft.TextField(
            hint_text="Search active jobs...",
            prefix_icon="search",
            border_radius=5,
            bgcolor="white",
            border_color="#E5E7EB",
            height=40,
            expand=True,
            on_change=self.filter_table,
        )

        self.dashboard_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("JOB NAME", color="#6B7280", size=12, weight="bold")),
                ft.DataColumn(ft.Text("STATUS",   color="#6B7280", size=12, weight="bold")),
                ft.DataColumn(ft.Text("PID",      color="#6B7280", size=12, weight="bold")),
                ft.DataColumn(ft.Text("ACTIONS",  color="#6B7280", size=12, weight="bold")),
            ],
            width=float("inf"),
            heading_row_height=50,
            data_row_min_height=56,
            divider_thickness=1,
            column_spacing=20,
            bgcolor="white",
            border_radius=8,
            border=ft.border.all(1, "#E5E7EB"),
        )

        # Build rows for currently tracked projects
        self.rebuild_table_structure()

        return ft.Column(
            [
                ft.Text("Job Management", size=28, weight="bold", color="#111827"),
                ft.Container(height=10),
                ft.Row(
                    [
                        self.search_field,
                        ft.Container(width=10),
                        ft.ElevatedButton(
                            "Reload",
                            bgcolor="white",
                            color="#2563EB",
                            height=40,
                            on_click=self.reload_all,
                        ),
                    ],
                    alignment="start",
                ),
                ft.Container(height=20),
                self.dashboard_table,
            ],
            expand=True,
            scroll="auto",
        )


    def reload_all(self, e=None):
        """
        Reload projects.json and running.json from disk,
        rebuild internal state and dashboard rows.
        """
        # Reload projects & groups from storage
        data = self.svc.manager.load_projects()
        self.projects = data.get("projects", [])
        self.groups = data.get("groups", [])
        self.project_map = {p["id"]: p for p in self.projects}

        # Reload running services
        active = self.svc.get_running_services()
        self.tracked_ids = {info["project_id"] for info in active.values()}

        # Refresh dropdowns (used in dialogs, but harmless now)
        self._init_dropdowns()

        # Rebuild dashboard rows + status
        self.rebuild_table_structure()

        self.show_snack("Reloaded from disk", color="#2563EB")


    # -------------------------------------------------------------------------
    # Polling: only updates status, never rebuilds table
    # -------------------------------------------------------------------------
    def _poll_loop(self):
        while self.running:
            try:
                # DataTable not mounted yet → skip
                if (
                    not hasattr(self, "dashboard_table")
                    or self.dashboard_table is None
                    or self.dashboard_table.page is None
                ):
                    time.sleep(0.5)
                    continue

                # Get running services
                active = self.svc.get_running_services()

                # If new processes started from CLI or code:
                new_ids = {info["project_id"] for info in active.values()}
                if new_ids != self.tracked_ids:
                    # Add missing ids
                    for pid in new_ids:
                        if pid not in self.tracked_ids:
                            self.tracked_ids.add(pid)
                    # Do NOT rebuild table here (prevents flicker)

                # Update only the status fields
                self._update_status_from_state(active)

            except Exception:
                pass

            time.sleep(1)




    def _update_status_from_state(self, active):
        running_map = {i["project_id"]: i for i in active.values()}

        for pid in list(self.tracked_ids):
            ctrls = self.row_controls.get(pid)
            if not ctrls:
                continue

            # Skip until row is attached to UI
            if not ctrls["status_icon"].page:
                continue

            info = running_map.get(pid)

            if info:
                # Running
                ctrls["status_icon"].color = "#10B981"
                ctrls["status_text"].value = "Running"
                ctrls["pid_text"].value = str(info["pid"])
            else:
                # Stopped
                ctrls["status_icon"].color = "#9CA3AF"
                ctrls["status_text"].value = "Stopped"
                ctrls["pid_text"].value = "-"

            ctrls["status_icon"].update()
            ctrls["status_text"].update()
            ctrls["pid_text"].update()



    # -------------------------------------------------------------------------
    # Table structure (rows) — rebuilt only when tracked IDs or filter change
    # -------------------------------------------------------------------------
    def rebuild_table_structure(self):
        if not hasattr(self, "dashboard_table") or self.dashboard_table.page is None:
            return

        rows = []

        for pid in sorted(self.tracked_ids):
            proj = self.project_map.get(pid)
            alias = proj["alias"] if proj else f"Unknown ({pid})"

            # Create controls only once
            if pid not in self.row_controls:
                self.row_controls[pid] = {
                    "status_icon": ft.Icon(name="circle", size=10),
                    "status_text": ft.Text(weight="w500"),
                    "pid_text": ft.Text(color="#6B7280"),
                    "btn_stop": ft.IconButton(icon="stop", icon_color="red",
                                            tooltip="Stop", on_click=self.stop_click, data=pid),
                    "btn_logs": ft.IconButton(icon="description",
                                            tooltip="Logs", on_click=self.view_logs_click, data=pid),
                    "btn_delete": ft.IconButton(icon="delete", icon_color="#EF4444",
                                                tooltip="Remove", on_click=lambda e, p=pid: self.untrack(p)),
                }

            ctrls = self.row_controls[pid]

            row = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(alias, weight="bold")),
                    ft.DataCell(ft.Row([ctrls["status_icon"], ctrls["status_text"]])),
                    ft.DataCell(ctrls["pid_text"]),
                    ft.DataCell(
                        ft.Row([
                            ctrls["btn_stop"],
                            ctrls["btn_logs"],
                            ctrls["btn_delete"]
                        ])
                    ),
                ]
            )

            rows.append(row)

        self.dashboard_table.rows = rows
        self.dashboard_table.update()

    def filter_table(self, e):
        self.rebuild_table_structure()


    # -------------------------------------------------------------------------
    # Button handlers
    # -------------------------------------------------------------------------
    def start_click(self, e):
        pid = e.control.data
        self.show_snack("Starting...", color="#2563EB")
        success, msg = self.svc.start_project(pid)
        if success:
            self.show_snack("Started.", color="#10B981")
        else:
            self.show_snack(f"Error: {msg}", color="#EF4444")

        active = self.svc.get_running_services()
        self._update_status_from_state(active)

    def stop_click(self, e):
        pid = e.control.data
        success, msg = self.svc.stop_project(pid)
        if success:
            self.show_snack("Stopped.", color="#F97316")
        else:
            self.show_snack(f"Error: {msg}", color="#EF4444")

        active = self.svc.get_running_services()
        self._update_status_from_state(active)

    def restart_click(self, e):
        pid = e.control.data
        self.show_snack("Restarting...", color="#2563EB")
        self.svc.stop_project(pid)
        time.sleep(0.4)
        self.svc.start_project(pid)
        self.show_snack("Restarted.", color="#10B981")

        active = self.svc.get_running_services()
        self._update_status_from_state(active)

    def untrack(self, pid):
        """Remove row from table but DO NOT stop the underlying process."""
        if pid in self.tracked_ids:
            self.tracked_ids.remove(pid)
            # keep row_controls dict; harmless if some controls stay in memory
            self.rebuild_table_structure()

    # -------------------------------------------------------------------------
    # Dialogs: run single project / group
    # -------------------------------------------------------------------------
    def open_project_dialog(self, e):
        self.page.dialog = ft.AlertDialog(
            title=ft.Text("Start New Job"),
            content=ft.Column(
                [ft.Text("Select a project:"), self.project_dropdown], height=100
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog()),
                ft.ElevatedButton(
                    "Add & Start",
                    on_click=self.add_project_action,
                    bgcolor="#2563EB",
                    color="white",
                ),
            ],
        )
        self.page.dialog.open = True
        self.page.update()

    def open_group_dialog(self, e):
        self.page.dialog = ft.AlertDialog(
            title=ft.Text("Run Group"),
            content=ft.Column(
                [ft.Text("Select a group:"), self.group_dropdown], height=100
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog()),
                ft.ElevatedButton(
                    "Run Group",
                    on_click=self.add_group_action,
                    bgcolor="#2563EB",
                    color="white",
                ),
            ],
        )
        self.page.dialog.open = True
        self.page.update()

    def close_dialog(self):
        self.page.dialog.open = False
        self.page.update()

    def add_project_action(self, e):
        if not self.project_dropdown.value:
            return

        pid = int(self.project_dropdown.value)
        self.close_dialog()

        # Ensure UI is stable before updating
        def finalize(_):
            # Track new job
            self.tracked_ids.add(pid)

            active = self.svc.get_running_services()
            if not any(i["project_id"] == pid for i in active.values()):
                self.svc.start_project(pid)

            self.rebuild_table_structure()

            # remove callback
            self.page.on_resize = None

        # trigger after render
        self.page.on_resize = finalize
        self.page.update()



    def add_group_action(self, e):
        if not self.group_dropdown.value:
            return

        gid = int(self.group_dropdown.value)
        self.close_dialog()

        group = next((g for g in self.groups if g["id"] == gid), None)
        if not group:
            return

        def finalize(_):
            active = self.svc.get_running_services()
            running_ids = {i["project_id"] for i in active.values()}

            for pid in group.get("project_ids", []):
                self.tracked_ids.add(pid)
                if pid not in running_ids:
                    self.svc.start_project(pid)

            self.rebuild_table_structure()
            self.page.on_resize = None

        self.page.on_resize = finalize
        self.page.update()



    # -------------------------------------------------------------------------
    # Helpers: code/logs/snack
    # -------------------------------------------------------------------------
    def launch_code_click(self, e):
        pid = e.control.data
        import subprocess

        proj = self.project_map.get(pid)
        if proj:
            config = self.svc.manager.get_config()
            editor = config.get("default_editor", "code")
            try:
                subprocess.Popen(f"{editor} .", cwd=proj["path"], shell=True)
            except Exception:
                pass

    def view_logs_click(self, e):
        pid = e.control.data
        active = self.svc.get_running_services()
        info = next((i for i in active.values() if i["project_id"] == pid), None)
        content = "Service is offline."
        if info:
            try:
                with open(info["log_path"], "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                content = "No logs yet."

        bs = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            f"Output Logs: ID {pid}", weight="bold", size=18
                        ),
                        ft.Divider(),
                        ft.Container(
                            content=ft.Text(
                                content,
                                font_family="Consolas",
                                color="#D1D5DB",
                            ),
                            height=400,
                            bgcolor="#1F2937",
                            padding=15,
                            border_radius=8,
                        ),
                    ],
                    tight=True,
                ),
                padding=20,
                bgcolor="white",
            )
        )
        self.page.overlay.append(bs)
        bs.open = True
        self.page.update()

    def show_snack(self, msg, color="blue"):
        self.page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        self.page.snack_bar.open = True
        self.page.update()

    # -------------------------------------------------------------------------
    # Other views
    # -------------------------------------------------------------------------
    def _view_projects_list(self):
        rows = []

        for p in sorted(self.projects, key=lambda x: x["id"]):
            run_btn = ft.IconButton(
                icon="play_arrow",
                icon_color="#2563EB",
                tooltip="Run this project",
                data=p["id"],
                on_click=self.run_project_from_list,
            )

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(p["id"]))),
                        ft.DataCell(ft.Text(p["alias"], weight="bold")),
                        ft.DataCell(ft.Text(p["path"], size=12, color="#6B7280")),
                        ft.DataCell(
                            ft.Text(
                                str(p.get("startup_cmd") or "-"),
                                size=12,
                                italic=True,
                            )
                        ),
                        ft.DataCell(run_btn),
                    ]
                )
            )

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("ALIAS")),
                ft.DataColumn(ft.Text("PATH")),
                ft.DataColumn(ft.Text("STARTUP CMD")),
                ft.DataColumn(ft.Text("ACTIONS")),
            ],
            rows=rows,
            width=float("inf"),
            bgcolor="white",
            border_radius=8,
            border=ft.border.all(1, "#E5E7EB"),
        )

        return ft.Column(
            [
                ft.Text("All Saved Projects", size=28, weight="bold", color="#111827"),
                ft.Text(f"Total: {len(self.projects)}", color="#6B7280"),
                ft.Container(height=20),
                table,
            ],
            expand=True,
            scroll="auto",
        )
    
    def run_project_from_list(self, e):
        pid = e.control.data

        # Ensure this project appears on Dashboard
        if pid not in self.tracked_ids:
            self.tracked_ids.add(pid)
            self.rebuild_table_structure()

        self.show_snack("Starting project...", color="#2563EB")
        success, msg = self.svc.start_project(pid)

        if success:
            self.show_snack("Project started.", color="#10B981")
        else:
            # This will include the "Already running (PID: ...)" message from ServiceManager
            self.show_snack(f"Error: {msg}", color="#EF4444")

        # Refresh status on dashboard
        active = self.svc.get_running_services()
        self._update_status_from_state(active)




    def _view_groups_list(self):
        rows = []

        for g in self.groups:
            p_names = [
                self.project_map[pid]["alias"]
                for pid in g.get("project_ids", [])
                if pid in self.project_map
            ]

            run_btn = ft.IconButton(
                icon="play_arrow",
                icon_color="#2563EB",
                tooltip="Run this group",
                data=g["id"],
                on_click=self.run_group_from_list,
            )

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(g["id"]))),
                        ft.DataCell(ft.Text(g["alias"], weight="bold")),
                        ft.DataCell(ft.Text(f"{len(p_names)} Projects")),
                        ft.DataCell(
                            ft.Text(
                                ", ".join(p_names),
                                size=12,
                                color="#6B7280",
                            )
                        ),
                        ft.DataCell(run_btn),
                    ]
                )
            )

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("GROUP ALIAS")),
                ft.DataColumn(ft.Text("COUNT")),
                ft.DataColumn(ft.Text("CONTENTS")),
                ft.DataColumn(ft.Text("ACTIONS")),
            ],
            rows=rows,
            width=float("inf"),
            bgcolor="white",
            border_radius=8,
            border=ft.border.all(1, "#E5E7EB"),
        )

        return ft.Column(
            [
                ft.Text("Project Groups", size=28, weight="bold", color="#111827"),
                ft.Container(height=20),
                table,
            ],
            expand=True,
            scroll="auto",
        )
    

    def run_group_from_list(self, e):
        gid = e.control.data
        group = next((g for g in self.groups if g["id"] == gid), None)

        if not group:
            self.show_snack("Group not found.", color="#EF4444")
            return

        # Ensure all projects in this group appear on Dashboard
        for pid in group.get("project_ids", []):
            if pid not in self.tracked_ids:
                self.tracked_ids.add(pid)

        self.rebuild_table_structure()

        # Start each project (ServiceManager prevents duplicates)
        active = self.svc.get_running_services()
        running_ids = {info["project_id"] for info in active.values()}

        errors = []
        for pid in group.get("project_ids", []):
            if pid in running_ids:
                # Already running, skip silently
                continue
            success, msg = self.svc.start_project(pid)
            if not success:
                errors.append(f"{pid}: {msg}")

        if errors:
            self.show_snack("Some jobs failed. Check logs.", color="#EF4444")
        else:
            self.show_snack("Group started.", color="#10B981")

        # Refresh status on dashboard
        active = self.svc.get_running_services()
        self._update_status_from_state(active)





def main_wrapper(page: ft.Page):
    CwmGui(page)


def run_gui():
    ft.app(target=main_wrapper)
