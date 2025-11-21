# cwm/copy_cmd.py
import click
import pyperclip
import re
from pathlib import Path
from .file_mapper import FileMapper

# --- CONDENSER LOGIC (Unchanged) ---
def _remove_c_comments(text):
    pattern = r"//.*?$|/\*.*?\*/"
    regex = re.compile(pattern, re.DOTALL | re.MULTILINE)
    return regex.sub("", text)

def _condense_c_style(content):
    content = _remove_c_comments(content)
    content = content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    content = re.sub(r'\s+', ' ', content)
    return content.strip()

def _condense_python(content):
    lines = content.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped: continue 
        if stripped.startswith("#"): continue 
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def _condense_html(content):
    content = re.sub(r'', '', content, flags=re.DOTALL)
    content = content.replace("\n", " ").replace("\r", " ")
    content = re.sub(r'\s+', ' ', content)
    return content.strip()

def _condense_content(content: str, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in ['.c', '.h', '.cpp', '.hpp', '.cc', '.cs', '.java', '.js', '.ts', '.css', '.scss', '.json', '.go', '.rs', '.php', '.dart']:
        return _condense_c_style(content)
    elif ext in ['.py', '.yaml', '.yml', '.gd']:
        return _condense_python(content)
    elif ext in ['.html', '.xml', '.htm']:
        return _condense_html(content)
    lines = [line for line in content.splitlines() if line.strip()]
    return "\n".join(lines)

# --- FILE READING (Unchanged) ---
def _read_file_safe(path: Path, condense: bool) -> str:
    try:
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
@click.option("--tree", is_flag=True, help="Generate and copy the CLEAN file tree (no IDs).")
@click.option("-f", "filter_str", help="Filter the file tree display.")
@click.option("--condense", is_flag=True, help="Minify code to save tokens.")
@click.argument("manual_ids", required=False)
def copy_cmd(init, tree, filter_str, condense, manual_ids):
    """
    Copy project context to clipboard.
    """
    root = Path.cwd()
    mapper = FileMapper(root)

    # --- 1. INIT MODE ---
    if init:
        res = mapper.initialize_config()
        if res == "exists":
            click.echo("Configuration files already exist.")
        else:
            click.echo(f"Initialized CWM Copy.")
            click.echo(f"  - Created .cwminclude (Empty)")
            click.echo(f"  - Created .cwmignore (Source: {res})")
        return

    # --- 2. CHECK REQUIREMENT ---
    if not (root / ".cwmignore").exists():
        click.echo(click.style("Error: CWM Copy is not initialized.", fg="red"))
        click.echo("Please run 'cwm copy --init' to setup ignore rules.")
        return

    # --- 3. SCAN ---
    if not tree:
        click.echo("Scanning project...")
    mapper.scan()
    
    # Use correct attribute name from previous fix
    if not mapper.id_map:
        click.echo("No files found (check .cwmignore).")
        return

    # --- 4. TREE MODE ---
    if tree:
        click.echo(mapper.clean_tree_str)
        pyperclip.copy(mapper.clean_tree_str)
        click.echo(click.style("\nClean tree structure copied to clipboard!", fg="green"))
        return

    # --- 5. MANUAL MODE ---
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

    # --- 6. INTERACTIVE MODE (WITH PAGINATION) ---
    click.echo("\n--- Project Tree ---")
    
    display_lines = mapper.tree_lines
    if filter_str:
        display_lines = [line for line in display_lines if filter_str.lower() in line.lower()]
    
    # --- NEW PAGINATION LOGIC ---
    PAGE_SIZE = 50
    total_lines = len(display_lines)
    index = 0
    
    while index < total_lines:
        # Print one page
        chunk = display_lines[index : index + PAGE_SIZE]
        for line in chunk:
            click.echo(line)
        
        index += PAGE_SIZE
        
        # If there are more lines, ask the user
        if index < total_lines:
            remaining = total_lines - index
            click.echo(click.style(f"\n--- {remaining} more lines ---", fg="yellow"))
            
            action = click.prompt(
                "Press [Enter] for next page, [a] for all, or [q] to select IDs now", 
                default="", 
                show_default=False
            )
            
            if action.lower() == 'q':
                break # Stop listing, go to selection
            elif action.lower() == 'a':
                # Dump the rest immediately
                for line in display_lines[index:]:
                    click.echo(line)
                break # Done listing
            # else: Loop continues for next page
    # ----------------------------

    click.echo("\nTips: Enter IDs (e.g. 1,3,5). Folder IDs include all children.")
    ids = click.prompt("Enter File/Folder IDs to copy", default="", show_default=False)
    
    if not ids:
        return

    selected_ids = ids.split(',')
    files = mapper.resolve_ids(selected_ids)
    
    if not files:
        click.echo("No files resolved.")
        return

    full_content = ""
    click.echo(f"\nProcessing {len(files)} files...")
    
    for f in files:
        rel_path = f.relative_to(root)
        click.echo(f"  Packing: {rel_path}")
        
        full_content += f"\n{'='*50}\n"
        full_content += f"File: {rel_path}\n"
        full_content += f"{'='*50}\n\n"
        full_content += _read_file_safe(f, condense)
        full_content += "\n"

    pyperclip.copy(full_content)
    
    success_msg = f"\nSuccess! Copied content of {len(files)} files."
    if condense:
        success_msg += " (Condensed Mode)"
        
    click.echo(click.style(success_msg, fg="green"))