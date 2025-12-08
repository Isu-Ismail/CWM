import os
import platform
import pathspec
from pathlib import Path
from .storage_manager import StorageManager


DEFAULT_IGNORES_WINDOWS = {
    "Windows", "Program Files", "Program Files (x86)", "AppData",
    "Microsoft", "$Recycle.Bin", "System Volume Information", "downloads", "documents", "desktop", "videos", "pictures", "music"
}

DEFAULT_IGNORES_LINUX = {
    "bin", "boot", "dev", "etc", "lib", "lib32", "lib64", "libx32",
    "proc", "run", "sys", "tmp", "usr", "var", "snap", "flatpak",
}

DEFAULT_IGNORES_MAC = {
    "System", "Library", "Applications", "Volumes",
}

DEFAULT_IGNORES_COMMON = {
    "node_modules", "dist", "build", "target", "vendor",
    "venv", "env", ".venv", ".env", "__pycache__",
    ".git", ".idea", ".vscode",
    "flutter", ".fvm"
}


def get_os_default_ignores():
    """Returns a combined set of folder names to ignore based on OS."""
    base = set(DEFAULT_IGNORES_COMMON)

    if os.name == "nt":
        return list(base.union(DEFAULT_IGNORES_WINDOWS))

    if platform.system() == "Darwin":
        return list(base.union(DEFAULT_IGNORES_MAC))

    return list(base.union(DEFAULT_IGNORES_LINUX))


class ProjectScanner:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manager = StorageManager()
        self.markers = self.manager.get_project_markers()

        self.os_ignores = get_os_default_ignores()

        self.skip_names = {x.lower() for x in self.os_ignores}

        self.ignore_spec = self._load_or_create_ignore()
        self.scanned_count = 0

    def _load_or_create_ignore(self):
        ignore_path = self.root / ".cwmignore"

        if not ignore_path.exists():
            try:
                with open(ignore_path, "w", encoding="utf-8") as f:
                    f.write("# --- CWM OS Specific Ignore ---\n")
                    for folder in self.os_ignores:
                        f.write(f"{folder}/\n")
            except Exception:
                pass

        lines = []
        if ignore_path.exists():
            try:
                with open(ignore_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
            except Exception:
                lines = []

        if not lines:
            lines = [f"{x}/" for x in self.os_ignores]

        return pathspec.PathSpec.from_lines('gitwildmatch', lines)

    def add_to_ignore(self, rel_path: str):
        ignore_path = self.root / ".cwmignore"

        clean_path = Path(rel_path).as_posix()
        if not clean_path.endswith("/"):
            clean_path += "/"

        try:
            existing_lines = set()
            if ignore_path.exists():
                with open(ignore_path, "r", encoding="utf-8") as f:
                    existing_lines = {line.strip()
                                      for line in f if line.strip()}

            if clean_path not in existing_lines:
                with open(ignore_path, "a", encoding="utf-8") as f:
                    f.write(f"{clean_path}\n")

                with open(ignore_path, "r", encoding="utf-8") as f:
                    self.ignore_spec = pathspec.PathSpec.from_lines(
                        'gitwildmatch', f.read().splitlines()
                    )
        except Exception:
            pass

    def is_ignored(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.root)
            check_str = rel.as_posix()

            if path.is_dir():
                check_str += "/"

            if self.ignore_spec.match_file(check_str):
                return True

            if os.name == 'nt':
                if self.ignore_spec.match_file(check_str.lower()):
                    return True

            return False
        except ValueError:
            return True

    def scan_generator(self):
        stack = [self.root]

        while stack:
            current = stack.pop()

            if current != self.root and self.is_ignored(current):
                continue

            try:
                entries = list(os.scandir(current))
            except PermissionError:
                continue

            self.scanned_count += 1
            dirs_to_visit = []
            is_project_folder = False

            for entry in entries:
                if entry.name in self.markers:
                    is_project_folder = True
                    break

            if is_project_folder and current != self.root:
                yield current
                continue

            for entry in entries:
                name = entry.name

                if name.startswith('.'):
                    continue

                if name.lower() in self.skip_names:
                    continue

                if entry.is_dir(follow_symlinks=False):
                    full_path = Path(entry.path)

                    if not self.is_ignored(full_path):
                        if self.scanned_count % 100 == 0:
                            print(f"Scanning: {full_path}")

                        dirs_to_visit.append(full_path)

            stack.extend(dirs_to_visit)


