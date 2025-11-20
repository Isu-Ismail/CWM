# cwm/file_mapper.py
import os
import pathspec
from pathlib import Path
from typing import List, Dict

# Default ignore patterns
# Added ".*" to ignore hidden files/folders by default
DEFAULT_IGNORE = [
    ".*",        # Ignore .git, .env, .vscode, etc.
    "__pycache__/",
    "*.pyc",
    "node_modules/",
    "venv/",
    "dist/",
    "build/",
    "*.log",
    "*.lock"
]

class FileMapper:
    def __init__(self, root_path: Path):
        self.root = root_path.resolve()
        self.ignore_spec = self._load_spec(".cwmignore", DEFAULT_IGNORE)
        self.include_spec = self._load_spec(".cwminclude", [])
        self.id_map: Dict[str, Path] = {} 
        self.tree_lines: List[str] = []
        self.raw_tree_str: str = ""

    def _load_spec(self, filename, defaults):
        path = self.root / filename
        patterns = []
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    patterns = f.read().splitlines()
            except:
                pass
        
        if not patterns:
            patterns = defaults
            
        if not patterns:
            return None
            
        return pathspec.PathSpec.from_lines('gitwildmatch', patterns)

    def _should_process(self, path: Path) -> bool:
        """Determines if a path should be included in the scan."""
        try:
            rel_path = path.relative_to(self.root)
            # Add trailing slash for directory matching consistency
            check_path = str(rel_path) + ("/" if path.is_dir() else "")
            
            # 1. Check Ignore (Exclude)
            if self.ignore_spec.match_file(check_path):
                return False
            
            # 2. Check Include (Allowlist) - ONLY if .cwminclude exists
            if self.include_spec:
                # If .cwminclude exists, file MUST match it to be shown
                if not self.include_spec.match_file(check_path):
                    return False
                    
            return True
        except ValueError:
            return False

    def scan(self):
        self.id_map = {}
        self.tree_lines = []
        current_id = 1
        
        root_name = self.root.name
        self.tree_lines.append(f"[{current_id}] {root_name}/")
        self.id_map[str(current_id)] = self.root
        current_id += 1
        
        def _walk(directory: Path, prefix: str = ""):
            nonlocal current_id
            try:
                entries = sorted(list(directory.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                return

            # Filter entries based on ignore/include rules
            entries = [e for e in entries if self._should_process(e)]
            
            count = len(entries)
            for i, entry in enumerate(entries):
                is_last = (i == count - 1)
                cid = str(current_id)
                self.id_map[cid] = entry
                current_id += 1
                
                connector = "└── " if is_last else "├── "
                self.tree_lines.append(f"{prefix}{connector}[{cid}] {entry.name}")
                
                if entry.is_dir():
                    extension = "    " if is_last else "│   "
                    _walk(entry, prefix + extension)

        _walk(self.root)
        self.raw_tree_str = "\n".join(self.tree_lines)

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
            if is_covered: continue 
            
            if p.is_dir():
                processed_roots.append(p)
                for root, _, files in os.walk(p):
                    for f in files:
                        full_path = Path(root) / f
                        # Re-check visibility for recursive files
                        if self._should_process(full_path):
                            final_files.add(full_path)
            elif p.is_file():
                final_files.add(p)
                
        return sorted(list(final_files))

    def create_ignore_file(self):
        path = self.root / ".cwmignore"
        if not path.exists():
            path.write_text("\n".join(DEFAULT_IGNORE), encoding="utf-8")
            return True
        return False