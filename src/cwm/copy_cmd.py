# cwm/copy_cmd.py
import click
import pyperclip
import re
from pathlib import Path
from .file_mapper import FileMapper

# --- CONDENSER LOGIC ---
def _remove_c_comments(text):
    """Removes // and /* */ comments from C-style code."""
    pattern = r"//.*?$|/\*.*?\*/"
    # DOTALL for multiline /* */ comments, MULTILINE for // comments
    regex = re.compile(pattern, re.DOTALL | re.MULTILINE)
    return regex.sub("", text)

def _condense_c_style(content):
    """
    For C, C++, Java, JS, CSS, etc.
    Aggressive: Removes comments, newlines, and indentation.
    Result: One or very few lines.
    """
    # 1. Remove comments
    content = _remove_c_comments(content)
    
    # 2. Replace newlines/tabs with space
    # We treat newlines as spaces to avoid merging words like 'int' and 'main' -> 'intmain'
    content = content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    
    # 3. Remove multi-spaces
    content = re.sub(r'\s+', ' ', content)
    
    return content.strip()

def _condense_python(content):
    """
    For Python.
    Safe: Removes comments and empty lines.
    MUST Preserve indentation.
    """
    lines = content.splitlines()
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue # Skip empty lines
        if stripped.startswith("#"):
            continue # Skip comment lines
        
        # (Optional: We could try to strip inline comments, but that's risky with strings)
        # line = line.split(" #")[0].rstrip() 
        
        cleaned_lines.append(line)
    
    return "\n".join(cleaned_lines)

def _condense_html(content):
    """For HTML/XML."""
    # Remove comments content = re.sub(r'', '', content, flags=re.DOTALL)
    # Remove newlines and multi-spaces
    content = content.replace("\n", " ").replace("\r", " ")
    content = re.sub(r'\s+', ' ', content)
    return content.strip()

def _condense_content(content: str, filename: str) -> str:
    """
    Dispatches content to the correct minifier based on extension.
    """
    ext = Path(filename).suffix.lower()
    
    # Group 1: C-Style (Aggressive single-line)
    if ext in ['.c', '.h', '.cpp', '.hpp', '.cc', '.cs', '.java', '.js', '.ts', '.css', '.scss', '.json', '.go', '.rs', '.php']:
        return _condense_c_style(content)
    
    # Group 2: Python/Yaml (Indentation Sensitive)
    elif ext in ['.py', '.yaml', '.yml', '.gd']:
        return _condense_python(content)
    
    # Group 3: Markup
    elif ext in ['.html', '.xml', '.htm']:
        return _condense_html(content)
        
    # Default: Just remove empty lines to be safe
    lines = [line for line in content.splitlines() if line.strip()]
    return "\n".join(lines)


# --- FILE READING ---
def _read_file_safe(path: Path, condense: bool) -> str:
    """Reads text file content, optionally condensing it."""
    try:
        # Simple binary check
        with open(path, 'rb') as f:
            if b'\0' in f.read(1024):
                return f"# [Skipped Binary File: {path.name}]\n"
        
        content = path.read_text(encoding='utf-8', errors='ignore')
        
        if condense:
            return _condense_content(content, path.name)
            
        return content
    except Exception as e:
        return f"# [Error reading {path.name}: {e}]\n"


# --- COMMAND ---
@click.command("copy")
@click.option("--init", is_flag=True, help="Initialize .cwmignore.")
@click.option("--tree", is_flag=True, help="Generate and copy the file tree structure only.")
@click.option("-f", "filter_str", help="Filter the file tree display.")
@click.option("--condense", is_flag=True, help="Minify code to save tokens (removes comments/whitespace).")
@click.argument("manual_ids", required=False)
def copy_cmd(init, tree, filter_str, condense, manual_ids):
    """
    Copy project context to clipboard.
    
    Run without arguments for interactive mode.
    Use --condense to minify code for LLMs.
    """
    root = Path.cwd()
    mapper = FileMapper(root)

    if init:
        if mapper.create_ignore_file():
            click.echo("Created .cwmignore with defaults.")
        else:
            click.echo(".cwmignore already exists.")
        return

    # Always scan first
    if not tree: 
        click.echo("Scanning project...")
    mapper.scan()
    
    if not mapper.id_map:
        click.echo("No files found (check .cwmignore).")
        return

    # --- TREE MODE ---
    if tree:
        click.echo(mapper.raw_tree_str)
        pyperclip.copy(mapper.raw_tree_str)
        click.echo(click.style("\nTree structure copied to clipboard!", fg="green"))
        return

    # --- MANUAL MODE ---
    if manual_ids:
        selected_ids = manual_ids.split(',')
        files = mapper.resolve_ids(selected_ids)
        if not files:
            click.echo("No valid files found.")
            return
        
        content = ""
        for f in files:
            click.echo(f"Packing: {f.name}")
            rel_path = f.relative_to(root)
            content += f"\n# File: {rel_path}\n"
            content += _read_file_safe(f, condense) + "\n"
            
        pyperclip.copy(content)
        click.echo(f"Copied content of {len(files)} files to clipboard!")
        return

    # --- INTERACTIVE MODE ---
    click.echo("\n--- Project Tree ---")
    
    display_lines = mapper.tree_lines
    if filter_str:
        display_lines = [line for line in display_lines if filter_str.lower() in line.lower()]
    
    for line in display_lines[:100]: 
        click.echo(line)
    if len(display_lines) > 100:
        click.echo(f"... ({len(display_lines)-100} more lines hidden) ...")

    click.echo("\nTips: Enter IDs (e.g. 1,3,5). Folder IDs include all children.")
    ids = click.prompt("Enter File/Folder IDs to copy", default="", show_default=False)
    
    if not ids:
        return

    selected_ids = ids.split(',')
    files = mapper.resolve_ids(selected_ids)
    
    if not files:
        click.echo("No files resolved.")
        return

    # Build Content
    full_content = ""
    click.echo(f"\nProcessing {len(files)} files...")
    
    for f in files:
        rel_path = f.relative_to(root)
        click.echo(f"  Packing: {rel_path}")
        
        # Header (Always keep this clean)
        full_content += f"\n# File: {rel_path}\n"
        # Content (Condense if requested)
        full_content += _read_file_safe(f, condense)
        full_content += "\n"

    pyperclip.copy(full_content)
    
    success_msg = f"\nSuccess! Copied {len(files)} files."
    if condense:
        success_msg += " (Condensed Mode)"
        
    click.echo(click.style(success_msg, fg="green"))