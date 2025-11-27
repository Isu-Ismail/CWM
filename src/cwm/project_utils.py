import os
import pathspec
from pathlib import Path
from .storage_manager import StorageManager

# -----------------------------
# OS-SPECIFIC DEFAULT IGNORES
# -----------------------------

DEFAULT_IGNORES_WINDOWS = [
    "Windows", "Program Files", "Program Files (x86)", "AppData",
    "Downloads", "Music", "Pictures", "Videos", "Documents","Desktops",
    "$Recycle.Bin", "System Volume Information","Contacts"
]

DEFAULT_IGNORES_LINUX = [
    "bin", "boot", "dev", "etc", "lib", "lib32", "lib64", "libx32",
    "proc", "run", "sys", "tmp", "usr", "var",
    "snap", "flatpak",
]

DEFAULT_IGNORES_MAC = [
    "System", "Library", "Applications", "Volumes",
]

# Common project junk for all OS
DEFAULT_IGNORES_COMMON = [
    "node_modules", "dist", "build", "target", "vendor",".*",
    
]

def get_os_default_ignores():
    if os.name == "nt":
        return DEFAULT_IGNORES_WINDOWS + DEFAULT_IGNORES_COMMON
    else:
        # macOS detection
        if "darwin" in os.uname().sysname.lower():
            return DEFAULT_IGNORES_MAC + DEFAULT_IGNORES_COMMON
        return DEFAULT_IGNORES_LINUX + DEFAULT_IGNORES_COMMON



class ProjectScanner:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manager = StorageManager()
        self.markers = self.manager.get_project_markers()
        self.os_ignores = get_os_default_ignores()
        self.ignore_spec = self._load_or_create_ignore()
        self.scanned_count = 0

    # ---------------------------------------------------------
    # CREATE & LOAD IGNORE FILE (WITH OS SPECIFIC ENTRIES)
    # ---------------------------------------------------------
    def _load_or_create_ignore(self):
        ignore_path = self.root / ".cwmignore"

        # Create default ignore file if missing
        if not ignore_path.exists():
            try:
                with open(ignore_path, "w", encoding="utf-8") as f:
                    f.write("# --- CWM OS Specific Ignore ---\n")
                    for folder in self.os_ignores:
                        f.write(f"{folder}/\n")
                    f.write(".*\n")  # Ignore all files
            except:
                pass

        # Load the spec
        try:
            if ignore_path.exists():
                with open(ignore_path, "r", encoding="utf-8") as f:
                    return pathspec.PathSpec.from_lines(
                        'gitwildmatch', f.read().splitlines()
                    )
        except:
            pass

        # fallback
        return pathspec.PathSpec.from_lines(
            'gitwildmatch', [f"{x}/" for x in self.os_ignores]
        )

    
    # ADD EXTRA IGNORE ENTRY
   
    def add_to_ignore(self, rel_path: str):
        ignore_path = self.root / ".cwmignore"
        try:
            with open(ignore_path, "a", encoding="utf-8") as f:
                f.write(f"\n{rel_path}/")
            # Reload
            with open(ignore_path, "r", encoding="utf-8") as f:
                self.ignore_spec = pathspec.PathSpec.from_lines(
                    'gitwildmatch', f.read().splitlines()
                )
        except:
            pass

    # ---------------------------------------------------------
    # CHECK IF IGNORED
    # ---------------------------------------------------------
    def is_ignored(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.root)
            check = str(rel) + "/"
            return self.ignore_spec.match_file(check)
        except ValueError:
            return True

    # ---------------------------------------------------------
    # SCAN PROJECTS
    # ---------------------------------------------------------
    def scan_generator(self):
        """
        Yields Paths that are identified as projects.
        """
        stack = [self.root]

        while stack:
            current = stack.pop()
            
            try:
                entries = list(os.scandir(current))
            except PermissionError:
                continue

            self.scanned_count += 1
            dirs_to_visit = []
            is_project_folder = False

            # 1. Check markers
            for entry in entries:
                if entry.name in self.markers:
                    is_project_folder = True
                    break
            
            # 2. Found project
            if is_project_folder and current != self.root:
                yield current
                continue

            # 3. Dive deeper
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    full_path = Path(entry.path)
                    if not self.is_ignored(full_path):
                        dirs_to_visit.append(full_path)
            
            stack.extend(reversed(dirs_to_visit))


    