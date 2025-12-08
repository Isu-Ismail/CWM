import os
import pathspec
from pathlib import Path
from typing import List, Dict

ALWAYS_IGNORE = [
    ".git/",
    ".cwm/",
    ".env",
    ".DS_Store",
    "Thumbs.db"
]

BASE_GENERATED_IGNORE = [
    "# --- CWM Global ---",
    ".git/",
    ".cwm/",
    ".env",
    ".DS_Store",
    "Thumbs.db",
    "*.log"
]

SMART_RULES = {
    "package.json": ["\n# --- Node.js ---", "node_modules/", "dist/", "build/", "coverage/", "npm-debug.log*", "yarn-error.log*"],
    "requirements.txt": ["\n# --- Python ---", "__pycache__/", "*.pyc", "venv/", ".venv/", "env/", "dist/", "build/", "*.egg-info/", ".pytest_cache/", ".coverage"],
    "pyproject.toml": ["\n# --- Python (Modern) ---", "__pycache__/", "*.pyc", "venv/", ".venv/", "dist/", "build/", "*.egg-info/"],
    "pubspec.yaml": ["\n# --- Flutter/Dart ---", ".dart_tool/", ".idea/", "build/", "ios/Flutter/Generated.xcconfig", "*.iml"],
    "pom.xml": ["\n# --- Java (Maven) ---", "target/", "*.class", ".idea/"],
    "Cargo.toml": ["\n# --- Rust ---", "target/", "Cargo.lock"],
    "go.mod": ["\n# --- Go ---", "bin/", "vendor/"]
}

PROJECT_MARKERS = {
    "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "node": ["package.json", "yarn.lock", "package-lock.json"],
    "flutter": ["pubspec.yaml"],
    "java": ["pom.xml", "build.gradle"],
    "go": ["go.mod"],
    "rust": ["Cargo.toml"]
}


class FileMapper:
    def __init__(self, root_path: Path):
        self.root = root_path.resolve()
        self.safety_spec = pathspec.PathSpec.from_lines(
            'gitwildmatch', ALWAYS_IGNORE)

        self.ignore_spec = self._load_spec(".cwmignore")
        self.include_paths = self._load_include_paths()  # Returns list of Paths

        self.id_map: Dict[str, Path] = {}
        self.tree_lines: List[str] = []
        self.clean_tree_str: str = ""

    def _load_spec(self, filename):
        path = self.root / filename
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    patterns = f.read().splitlines()
                return pathspec.PathSpec.from_lines('gitwildmatch', patterns)
            except:
                pass
        return None

    def _load_include_paths(self) -> List[Path]:
        """
        Loads .cwminclude and accepts ONLY valid folder paths.

        - Ignores file names completely (like __init__.py)
        - Ignores plain text or unknown keywords
        - Requires trailing slash
        - Normalizes hidden characters (BOM, CRLF, zero-width)
        - Converts Windows slashes to POSIX
        - Ensures path exists and is a directory
        """

        include_file = self.root / ".cwminclude"
        if not include_file.exists():
            return []

        valid_folders = []

        try:
            with open(include_file, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()

            for raw in lines:

                line = (
                    raw.replace("\ufeff", "")    # BOM
                    .replace("\u200b", "")    # zero-width space
                    .replace("\t", "")        # tabs
                    .strip()
                )

                if not line or line.startswith("#"):
                    continue

                if not line.endswith("/"):
                    print(f"✗ Skipped (not a folder): '{raw}'")
                    continue

                line = line.replace("\\", "/")

                line = line.rstrip("\r").rstrip("\n").strip()

                if not line.endswith("/"):
                    line += "/"

                target = (self.root / line).resolve()

                if target.exists() and target.is_dir():
                    valid_folders.append(target)
                    print(f"✓ Folder added: '{line}'")
                else:
                    print(f"✗ Not a valid folder: '{raw}'")

        except Exception as e:
            print("ERROR reading .cwminclude:", e)

        return valid_folders

    def _detect_project_type(self) -> str:
        for lang, markers in PROJECT_MARKERS.items():
            for marker in markers:
                if (self.root / marker).exists():
                    return lang
        return "generic"

    def _is_ignored(self, path: Path) -> bool:
        try:
            rel_path = path.relative_to(self.root)
            check_path = str(rel_path) + ("/" if path.is_dir() else "")

            if self.safety_spec.match_file(check_path):
                return True
            if self.ignore_spec and self.ignore_spec.match_file(check_path):
                return True
            return False
        except ValueError:
            return True

    def scan(self):
        """
        Targeted Scan: Only scans folders in .cwminclude (or root if empty).
        Reconstructs tree showing relative paths for clarity.
        """
        self.id_map = {}
        self.tree_lines = []
        clean_lines = []

        valid_files = []

        scan_targets = self.include_paths
        if not scan_targets:
            scan_targets = [self.root]

        for target in scan_targets:
            for root, dirs, files in os.walk(target):
                dirs[:] = [
                    d for d in dirs if not self._is_ignored(Path(root) / d)]

                for f in files:
                    full_path = Path(root) / f
                    if not self._is_ignored(full_path):
                        valid_files.append(full_path)

        valid_files.sort(key=lambda p: (len(p.parts), p.name))

        if not valid_files:
            return

        tree_structure = {}
        for path in valid_files:
            rel_path = path.relative_to(self.root)
            parts = rel_path.parts
            current_level = tree_structure
            for part in parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]

        current_id = 1

        self.id_map[str(current_id)] = self.root
        self.tree_lines.append(f"[{current_id}] {self.root.name}/")
        clean_lines.append(f"{self.root.name}/")
        current_id += 1

        def _render_node(node: dict, prefix: str, current_path: Path):
            nonlocal current_id

            keys = list(node.keys())
            keys.sort(key=lambda x: (
                0 if (current_path / x).is_dir() else 1, x.lower()))

            count = len(keys)
            for i, name in enumerate(keys):
                is_last = (i == count - 1)
                full_child_path = current_path / name

                cid = str(current_id)
                self.id_map[cid] = full_child_path
                current_id += 1

                connector = "└── " if is_last else "├── "

                self.tree_lines.append(f"{prefix}{connector}[{cid}] {name}")
                clean_lines.append(f"{prefix}{connector}{name}")

                children = node[name]
                if children:  # It is a directory
                    extension = "    " if is_last else "│   "
                    _render_node(children, prefix + extension, full_child_path)

        _render_node(tree_structure, "", self.root)
        self.clean_tree_str = "\n".join(clean_lines)

    def resolve_ids(self, id_list: List[str]) -> List[Path]:
        selected_paths = set()
        for i in id_list:
            i = i.strip()
            if i in self.id_map:
                selected_paths.add(self.id_map[i])

        final_files = set()
        sorted_paths = sorted(list(selected_paths), key=lambda p: len(p.parts))
        processed_roots = []

        for p in sorted_paths:
            is_covered = False
            for root in processed_roots:
                if root in p.parents:
                    is_covered = True
                    break
            if is_covered:
                continue

            if p.is_dir():
                processed_roots.append(p)
                for root, _, files in os.walk(p):
                    for f in files:
                        full_path = Path(root) / f
                        if not self._is_ignored(full_path):
                            final_files.add(full_path)
            elif p.is_file():
                final_files.add(p)
        return sorted(list(final_files))

    def initialize_config(self) -> str:
        """Creates .cwmignore and .cwminclude with instructions."""
        ignore_target = self.root / ".cwmignore"
        include_target = self.root / ".cwminclude"

        if not include_target.exists():
            include_content = [
                "# --- CWM Include File ---",
                "# Specify folders to include in the scan.",
                "# If populated, CWM will ONLY scan these folders.",
                "# Instructions:",
                "# 1. Enter relative paths from project root.",
                "# 2. Folders MUST end with a trailing slash (/).",
                "# Example:",
                "# src/",
                ""
            ]
            include_target.write_text(
                "\n".join(include_content), encoding="utf-8")

        if ignore_target.exists():
            return "exists"

        content_lines = []
        source_type = "default"

        gitignore = self.root / ".gitignore"
        if gitignore.exists():
            try:
                content_lines = gitignore.read_text(
                    encoding='utf-8').splitlines()
                source_type = ".gitignore"
            except:
                pass

        if not content_lines:
            content_lines = list(BASE_GENERATED_IGNORE)
            found_any = False
            for marker, rules in SMART_RULES.items():
                if (self.root / marker).exists():
                    content_lines.extend(rules)
                    found_any = True
            if not found_any:
                source_type = "Generic Defaults"
                content_lines.extend(
                    ["node_modules/", "venv/", "__pycache__/"])

        ignore_target.write_text("\n".join(content_lines), encoding="utf-8")
        return source_type

