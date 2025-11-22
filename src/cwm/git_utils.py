# cwm/git_utils.py
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

SSH_DIR = Path.home() / ".ssh"
SSH_CONFIG = SSH_DIR / "config"

def ensure_ssh_dir():
    """Ensures the .ssh directory exists with secure permissions."""
    if not SSH_DIR.exists():
        SSH_DIR.mkdir(mode=0o700)
    if not SSH_CONFIG.exists():
        SSH_CONFIG.touch(mode=0o600)

def run_git_command(args: List[str], cwd: Path = None) -> bool:
    """Runs a git command safely."""
    try:
        is_windows = os.name == 'nt'
        subprocess.run(
            ["git"] + args, 
            cwd=cwd, 
            check=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE, 
            shell=is_windows
        )
        return True
    except Exception:
        return False

def get_current_branch() -> str:
    """Returns the name of the current git branch (e.g., main)."""
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return res.stdout.strip() or "main"
    except:
        return "main"

def has_commits() -> bool:
    """Checks if the current repo has at least one commit."""
    try:
        # 'git rev-parse --verify HEAD' fails if there are no commits
        subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            check=True
        )
        return True
    except:
        return False

def generate_ssh_key(alias: str, email: str) -> Path:
    """Generates a new ED25519 SSH key for the alias."""
    ensure_ssh_dir()
    key_filename = f"id_ed25519_{alias}"
    key_path = SSH_DIR / key_filename
    
    if key_path.exists():
        return key_path

    cmd = [
        "ssh-keygen",
        "-t", "ed25519",
        "-C", email,
        "-f", str(key_path),
        "-N", "" 
    ]
    
    # Use direct subprocess here since ssh-keygen isn't a git command
    is_windows = os.name == 'nt'
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=is_windows)
        
    return key_path

def update_ssh_config(alias: str, key_path: Path):
    """Appends a Host entry to ~/.ssh/config."""
    ensure_ssh_dir()
    key_str = str(key_path).replace("\\", "/")
    
    host_entry = f"\n# --- CWM Account: {alias} ---\n"
    host_entry += f"Host github.com-{alias}\n"
    host_entry += f"  HostName github.com\n"
    host_entry += f"  User git\n"
    host_entry += f"  IdentityFile {key_str}\n"
    host_entry += f"  IdentitiesOnly yes\n"
    
    try:
        current_content = SSH_CONFIG.read_text(encoding="utf-8")
    except:
        current_content = ""
    
    if f"Host github.com-{alias}" in current_content:
        return 
        
    with open(SSH_CONFIG, "a", encoding="utf-8") as f:
        f.write(host_entry)

def get_configured_accounts() -> List[Dict[str, str]]:
    """Parses ~/.ssh/config to find CWM-managed accounts."""
    if not SSH_CONFIG.exists():
        return []
    accounts = []
    try:
        lines = SSH_CONFIG.read_text(encoding="utf-8").splitlines()
        current_account = None
        for line in lines:
            line = line.strip()
            if line.startswith("Host github.com-"):
                if current_account: accounts.append(current_account)
                alias = line.replace("Host github.com-", "").strip()
                current_account = {"alias": alias, "host": f"github.com-{alias}", "key": "Unknown"}
            elif current_account and line.startswith("IdentityFile"):
                parts = line.split(maxsplit=1)
                if len(parts) > 1: current_account["key"] = parts[1]
        if current_account: accounts.append(current_account)
    except Exception: pass
    return accounts

def get_git_remote_url() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"], 
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except:
        return None
    

TEMPLATES = {
    "Python": """
__pycache__/
*.py[cod]
*$py.class
venv/
.venv/
env/
.env
*.log
.idea/
.vscode/
dist/
build/
*.egg-info/
""",
    "Node": """
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
dist/
build/
.env
.DS_Store
.idea/
.vscode/
coverage/
""",
    "Flutter": """
.dart_tool/
.packages
.pub/
build/
ios/Flutter/Generated.xcconfig
android/gradle/
.idea/
.vscode/
""",
    "Go": """
bin/
pkg/
vendor/
go.sum
.idea/
.vscode/
""",
    "Rust": """
/target
**/*.rs.bk
Cargo.lock
.idea/
.vscode/
""",
    "Generic": """
.env
.DS_Store
.idea/
.vscode/
*.log
dist/
build/
"""
}

def detect_project_type(path: Path) -> str:
    """Auto-detects project type based on files."""
    if (path / "package.json").exists(): return "Node"
    if (path / "requirements.txt").exists() or (path / "pyproject.toml").exists(): return "Python"
    if (path / "pubspec.yaml").exists(): return "Flutter"
    if (path / "go.mod").exists(): return "Go"
    if (path / "Cargo.toml").exists(): return "Rust"
    return "Generic"

def get_gitignore_content(template_name: str) -> str:
    """Returns the content for the selected template."""
    return TEMPLATES.get(template_name, TEMPLATES["Generic"]).strip()