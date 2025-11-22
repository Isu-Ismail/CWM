# src/cwm/project_utils.py
import os
import pathspec
from pathlib import Path
from .storage_manager import StorageManager

# Heavy defaults to prevent scanning the whole computer
DEFAULT_IGNORES = [
    "Windows", "Program Files", "Program Files (x86)", "AppData",
    "node_modules", "dist", "build", "target", "vendor",
    "Downloads", "Music", "Pictures", "Videos", "Documents",
    "$Recycle.Bin", "System Volume Information", ".git", ".cwm",
    "Library", "Applications"
]

class ProjectScanner:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manager = StorageManager()
        self.markers = self.manager.get_project_markers()
        self.ignore_spec = self._load_or_create_ignore()
        self.scanned_count = 0

    def _load_or_create_ignore(self):
        ignore_path = self.root / ".cwmignore"
        
        # Create default if missing
        if not ignore_path.exists():
            try:
                with open(ignore_path, "w", encoding="utf-8") as f:
                    f.write("# --- CWM Global Ignore ---\n")
                    for folder in DEFAULT_IGNORES:
                        f.write(f"{folder}/\n")
                    f.write(".* \n") 
            except: pass
        
        # Load spec
        try:
            if ignore_path.exists():
                with open(ignore_path, "r", encoding="utf-8") as f:
                    return pathspec.PathSpec.from_lines('gitwildmatch', f.read().splitlines())
        except: pass
        
        return pathspec.PathSpec.from_lines('gitwildmatch', [f"{x}/" for x in DEFAULT_IGNORES])

    def add_to_ignore(self, rel_path: str):
        ignore_path = self.root / ".cwmignore"
        try:
            with open(ignore_path, "a", encoding="utf-8") as f:
                f.write(f"\n{rel_path}/")
            # Reload
            with open(ignore_path, "r", encoding="utf-8") as f:
                self.ignore_spec = pathspec.PathSpec.from_lines('gitwildmatch', f.read().splitlines())
        except: pass

    def is_ignored(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.root)
            check = str(rel) + "/"
            return self.ignore_spec.match_file(check)
        except ValueError:
            return True

    def scan_generator(self):
        """
        Yields Paths that are identified as projects.
        """
        stack = [self.root]

        while stack:
            current = stack.pop()
            
            try:
                # Fast scan
                entries = list(os.scandir(current))
            except PermissionError:
                continue

            self.scanned_count += 1
            dirs_to_visit = []
            is_project_folder = False

            # 1. Check for Markers
            for entry in entries:
                if entry.name in self.markers:
                    is_project_folder = True
                    break
            
            # 2. If Project found
            if is_project_folder and current != self.root:
                yield current
                continue # STOP recursion for this branch

            # 3. If NOT project
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    full_path = Path(entry.path)
                    # Optimization: Check ignore BEFORE adding to stack
                    # This prevents thousands of useless checks later
                    if not self.is_ignored(full_path):
                        dirs_to_visit.append(full_path)
            
            stack.extend(reversed(dirs_to_visit))