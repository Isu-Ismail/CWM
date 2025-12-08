import click
import pyperclip
import re
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from .file_mapper import FileMapper
from .rich_help import RichHelpCommand

console = Console()


def _format_python(content):
    """
    Formats Python code using autopep8 (if installed) and removes comments.
    """
    lines = content.splitlines()
    cleaned_lines = [l for l in lines if not l.strip().startswith("#")]
    content = "\n".join(cleaned_lines)

    try:
        import autopep8
        return autopep8.fix_code(content)
    except ImportError:
        return content


def _format_generic(content):
    """
    Generic formatting: Remove C-style comments and normalize whitespace.
    """
    pattern = r"//.*?$|/\*.*?\*/"
    regex = re.compile(pattern, re.DOTALL | re.MULTILINE)
    content = regex.sub("", content)
    content = re.sub(r'\n\s*\n', '\n\n', content)
    return content.strip()


def _process_content(content: str, filename: str, mode: str) -> str:
    ext = Path(filename).suffix.lower()

    if mode == 'condense':
        if ext in ['.py', '.yaml', '.yml']:
            return _format_python(content).replace("\n", " ")
        return _format_generic(content).replace("\n", " ")

    elif mode == 'format':
        if ext == '.py':
            return _format_python(content)
        elif ext in ['.js', '.ts', '.c', '.cpp', '.java', '.cs', '.php', '.dart', '.go', '.rs']:
            return _format_generic(content)

    return content  # Raw


def _read_file_safe(path: Path, root: Path, mode: str) -> str:
    try:
        with open(path, 'rb') as f:
            if b'\0' in f.read(1024):
                return f"---- {path.name} (Binary Skipped) ----\n"

        content = path.read_text(encoding='utf-8', errors='ignore')
        processed = _process_content(content, path.name, mode)
        rel_path = path.relative_to(root)

        return f"---- {rel_path} ----\n{processed}\n--------\n"

    except Exception as e:
        return f"---- Error reading {path.name} ----\n{e}\n--------\n"


def _colorize_tree_line(line: str, mapper: FileMapper) -> str:
    """
    Applies rich color tags to the raw tree string.
    Scheme:
      - Main Branch/Root: Green
      - Tree Structure: Yellow
      - IDs: Blue
      - Files: Orange (214) / Folders: Green
    """
    line = re.sub(r'([│├──└──]+)', r'[yellow]\1[/yellow]', line)

    id_match = re.search(r'\[(\d+)\]', line)

    line = re.sub(r'(\[\d+\])', r'[bold blue]\1[/bold blue]', line)

    match = re.search(r'(\[bold blue\]\[\d+\]\[/bold blue\]\s)(.+)', line)
    if match and id_match:
        file_id = id_match.group(1)
        name = match.group(2)

        path_obj = mapper.id_map.get(file_id)

        is_folder = False
        if path_obj:
            is_folder = path_obj.is_dir()
        else:
            is_folder = name.endswith(
                "/") or (name.isupper() and "PROJECT" in name)

        if is_folder:
            line = line.replace(name, f"[bold green]{name}[/bold green]")
        else:
            line = line.replace(
                name, f"[bold color(214)]{name}[/bold color(214)]")

    return line


@click.command("copy", cls=RichHelpCommand)
@click.option("--init", is_flag=True, help="Initialize .cwmignore.")
@click.option("--tree", is_flag=True, help="Copy clean file tree only.")
@click.option("-f", "filter_str", help="Filter file tree.")
@click.option("--condense", is_flag=True, help="Minify code (save tokens).")
@click.option("--format", "format_mode", is_flag=True, help="Format code & remove comments.")
@click.argument("manual_ids", required=False)
def copy_cmd(init, tree, filter_str, condense, format_mode, manual_ids):
    """
    Copy project context (Tree + Content) to clipboard.
    """
    root = Path.cwd()
    mapper = FileMapper(root)

    proc_mode = 'raw'
    if condense:
        proc_mode = 'condense'
    if format_mode:
        proc_mode = 'format'

    if init:
        res = mapper.initialize_config()
        if res == "exists":
            console.print(
                "[yellow]! Configuration files already exist.[/yellow]")
        else:
            console.print("[green]✔ Initialized CWM Copy.[/green]")
            console.print("  [dim]Created .cwminclude & .cwmignore[/dim]")
        return

    if not (root / ".cwmignore").exists():
        console.print("[red]✖ Error: CWM Copy is not initialized.[/red]")
        console.print("  Run [bold cyan]cwm copy --init[/bold cyan] first.")
        return

    if not tree:
        with console.status("[bold cyan]Scanning project...[/bold cyan]"):
            mapper.scan()
    else:
        mapper.scan()

    if not mapper.id_map:
        console.print("[yellow]! No files found (check .cwmignore).[/yellow]")
        return

    if tree:
        pyperclip.copy(mapper.clean_tree_str)
        console.print(mapper.clean_tree_str)
        console.print(
            "\n[bold green]✔ Clean tree copied to clipboard![/bold green]")
        return

    if manual_ids:
        selected_ids = manual_ids.split(',')
        files = mapper.resolve_ids(selected_ids)
        if not files:
            console.print("[red]✖ No valid files found.[/red]")
            return

        full_content = ""
        for f in files:
            console.print(f"  [cyan]Packing:[/cyan] {f.name}")
            full_content += _read_file_safe(f, root, proc_mode)

        pyperclip.copy(full_content)
        console.print(
            f"\n[bold green]✔ Copied {len(files)} files![/bold green] ({proc_mode})")
        return

    console.print("\n[bold]Project Tree[/bold]")

    display_lines = mapper.tree_lines
    if filter_str:
        display_lines = [
            line for line in display_lines if filter_str.lower() in line.lower()]

    colored_lines = [_colorize_tree_line(
        line, mapper) for line in display_lines]

    PAGE_SIZE = 40
    total_lines = len(colored_lines)
    index = 0

    while index < total_lines:
        chunk = colored_lines[index: index + PAGE_SIZE]
        for line in chunk:
            console.print(line, highlight=False)

        index += PAGE_SIZE

        if index < total_lines:
            remaining = total_lines - index
            console.print(f"\n[dim]--- {remaining} more lines ---[/dim]")

            action = Prompt.ask(
                "  [cyan]Action[/cyan] [dim]([bold]Enter[/bold]=Next, [bold]a[/bold]=All, [bold]q[/bold]=Select)[/dim]",
                default="", show_default=False
            )

            if action.lower() == 'q':
                break
            elif action.lower() == 'a':
                for line in colored_lines[index:]:
                    console.print(line, highlight=False)
                break

    console.print(
        "\n[dim]Enter IDs (e.g. 1,3,5). Folder IDs include all children.[/dim]")
    ids = Prompt.ask("[bold cyan]?[/bold cyan] Select Files")

    if not ids:
        return

    selected_ids = ids.split(',')
    files = mapper.resolve_ids(selected_ids)

    if not files:
        console.print("[red]✖ No files resolved.[/red]")
        return

    full_content = ""
    console.print(f"\n[bold]Processing {len(files)} files...[/bold]")

    for f in files:
        rel_path = f.relative_to(root)
        console.print(f"  [dim]Packing:[/dim] {rel_path}")
        full_content += _read_file_safe(f, root, proc_mode)

    try:
        pyperclip.copy(full_content)

        msg = f"✔ Copied {len(files)} files to clipboard."
        if format_mode:
            msg += " [Formatted]"
        elif condense:
            msg += " [Condensed]"

        console.print(f"\n[bold green]{msg}[/bold green]")
    except Exception as e:
        console.print(f"\n[bold red]✖ Copy failed:[/bold red] {e}")


