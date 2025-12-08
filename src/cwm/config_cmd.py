import click
import re
import json
from pathlib import Path

# Rich Imports
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, IntPrompt, Confirm

from .storage_manager import StorageManager, GLOBAL_CWM_BANK, find_nearest_bank_path
from .rich_help import RichHelpCommand
from .utils import get_all_history_candidates

console = Console()
GLOBAL_CONFIG_PATH = GLOBAL_CWM_BANK / "config.json"

# =========================================================
# HELPERS (Private)
# =========================================================
def _load_global_config():
    if not GLOBAL_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(GLOBAL_CONFIG_PATH.read_text())
    except:
        return {}

def _save_global_config(data):
    if not GLOBAL_CWM_BANK.exists():
        GLOBAL_CWM_BANK.mkdir(parents=True, exist_ok=True)
    GLOBAL_CONFIG_PATH.write_text(json.dumps(data, indent=4))

def _write_config(path: Path, key: str, value):
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except:
            pass
    
    data[key] = value
    path.write_text(json.dumps(data, indent=4))

def _clear_config(path: Path):
    if path and path.exists():
        path.unlink()

def _modify_config_list(path: Path, key: str, value: str, action: str):
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except: pass
        
    current_list = data.get(key, [])
    if not isinstance(current_list, list): current_list = []
    
    if action == "add":
        if value not in current_list:
            current_list.append(value)
            console.print(f"  [green]✔ Added '{value}' to {key}.[/green]")
        else:
            console.print(f"  [yellow]! '{value}' is already in {key}.[/yellow]")
    elif action == "remove":
        if value in current_list:
            current_list.remove(value)
            console.print(f"  [green]✔ Removed '{value}' from {key}.[/green]")
        else:
            console.print(f"  [yellow]! '{value}' not found in {key}.[/yellow]")
            
    data[key] = current_list
    path.write_text(json.dumps(data, indent=4))


# =========================================================
# MAIN COMMAND
# =========================================================
@click.command("config", help="Edit configuration settings.", cls=RichHelpCommand)
@click.option("--shell", is_flag=True, help="Select preferred shell history file.")
@click.option("--global", "global_mode", is_flag=True, help="Target Global config explicitly.")
@click.option("--clear-local", is_flag=True, help="Reset local configuration.")
@click.option("--clear-global", is_flag=True, help="Reset global configuration.")
@click.option("--show", is_flag=True, help="Show configuration.")
@click.option("--editor", help="Set default editor.")
@click.option("--code-theme", help="Set code syntax highlighting theme.")
@click.option("--add-marker", help="Add project detection marker.")
@click.option("--remove-marker", help="Remove project detection marker.")
@click.option("--gemini", is_flag=True, help="Configure Gemini (Interactive).")
@click.option("--openai", is_flag=True, help="Configure OpenAI (Interactive).")
@click.option("--local-ai", is_flag=True, help="Configure Local AI (Interactive).")
@click.option("--instruction", is_flag=True, help="Set System Instruction.")
def config_cmd(shell, global_mode, clear_local, clear_global, show,
               editor, code_theme, add_marker, remove_marker,
               gemini, openai, local_ai, instruction):

    manager = StorageManager()

    # Determine local/global write targets
    local_bank = find_nearest_bank_path(Path.cwd())
    local_config = local_bank / "config.json" if local_bank else None

    # Logic: If global flag set, ignore local. Else prefer local if available.
    target_path = GLOBAL_CONFIG_PATH if global_mode else (local_config or GLOBAL_CONFIG_PATH)
    target_name = "Global" if global_mode else ("Local" if local_config and not global_mode else "Global")

    def write_global(key, value):
        _write_config(GLOBAL_CONFIG_PATH, key, value)

    def write_local(key, value):
        if local_config:
            _write_config(local_config, key, value)
        else:
            # Fallback if no local config exists yet
            write_global(key, value)

    # =========================================================
    # SHOW CONFIG
    # =========================================================
    if show:
        console.print("")
        config = manager.get_config() # This gets merged/effective config usually

        # 1. Paths Info
        path_text = Text()
        path_text.append("Global Config: ", style="dim")
        path_text.append(f"{GLOBAL_CONFIG_PATH}\n", style="cyan")
        
        path_text.append("Local Config:  ", style="dim")
        if local_bank:
            l_path = local_bank / "config.json"
            status = "[green](Active)[/green]" if l_path.exists() else "[dim](Not created)[/dim]"
            path_text.append(f"{l_path} {status}", style="magenta")
        else:
            path_text.append("(No local bank detected)", style="dim")

        console.print(Panel(path_text, title="[bold]Configuration Sources[/bold]", border_style="dim"))

        # 2. Settings Info
        settings_text = Text()
        settings_text.append(f"Target:         {target_name}\n", style="bold yellow")
        settings_text.append(f"History File:   {config.get('history_file', 'Auto-Detect')}\n")
        settings_text.append(f"Default Editor: {config.get('default_editor', 'code')}\n")
        settings_text.append(f"Code Theme:     {config.get('code_theme', 'monokai')}\n")
        
        markers = config.get('project_markers', [])
        settings_text.append(f"Markers:        {', '.join(markers) if markers else 'None'}")

        console.print(Panel(settings_text, title="[bold]General Settings[/bold]", border_style="blue"))

        # 3. AI Info
        ai_text = Text()
        
        def format_key(k): return f"{k[:4]}...{k[-4:]}" if k else "Not Set"

        # Gemini
        g = config.get("gemini", {})
        ai_text.append("Gemini:   ", style="bold cyan")
        ai_text.append(f"Model='{g.get('model') or 'None'}'  Key='{format_key(g.get('key'))}'\n")

        # OpenAI
        o = config.get("openai", {})
        ai_text.append("OpenAI:   ", style="bold green")
        ai_text.append(f"Model='{o.get('model') or 'None'}'  Key='{format_key(o.get('key'))}'\n")

        # Local
        l = config.get("local_ai", {})
        ai_text.append("Local AI: ", style="bold magenta")
        ai_text.append(f"Model='{l.get('model') or 'None'}'\n\n")

        # Instruction
        instr = config.get("ai_instruction")
        if instr:
            preview = instr[:60].replace("\n", " ") + "..." if len(instr) > 60 else instr
            ai_text.append(f"Instruction: [dim]{preview}[/dim]")
        else:
            ai_text.append("Instruction: [dim](Default)[/dim]")

        console.print(Panel(ai_text, title="[bold]AI Configuration[/bold]", border_style="magenta"))
        console.print("")
        return

    # =========================================================
    # AI WIZARDS
    # =========================================================
    if gemini:
        console.print("\n[bold cyan]?[/bold cyan] [bold]Configure Gemini[/bold]")
        data = _load_global_config()
        cur = data.get("gemini", {})
        
        model = Prompt.ask("  [cyan]Model Name[/cyan]", default=cur.get("model") or "gemini-pro")
        key = Prompt.ask("  [cyan]API Key[/cyan]", default=cur.get("key") or "", password=True)

        data.setdefault("gemini", {})
        data["gemini"]["model"] = model.strip() or None
        data["gemini"]["key"] = key.strip() or None

        _save_global_config(data)
        console.print("  [green]✔ Gemini configuration saved.[/green]\n")
        return

    if openai:
        console.print("\n[bold green]?[/bold green] [bold]Configure OpenAI[/bold]")
        data = _load_global_config()
        cur = data.get("openai", {})
        
        model = Prompt.ask("  [green]Model Name[/green]", default=cur.get("model") or "gpt-4")
        key = Prompt.ask("  [green]API Key[/green]", default=cur.get("key") or "", password=True)

        data.setdefault("openai", {})
        data["openai"]["model"] = model.strip() or None
        data["openai"]["key"] = key.strip() or None

        _save_global_config(data)
        console.print("  [green]✔ OpenAI configuration saved.[/green]\n")
        return

    if local_ai:
        console.print("\n[bold magenta]?[/bold magenta] [bold]Configure Local AI[/bold]")
        data = _load_global_config()
        cur = data.get("local_ai", {})
        
        model = Prompt.ask("  [magenta]Model Name[/magenta]", default=cur.get("model") or "llama3")
        
        data.setdefault("local_ai", {})
        data["local_ai"]["model"] = model.strip() or None

        _save_global_config(data)
        console.print("  [green]✔ Local AI configuration saved.[/green]\n")
        return

    if instruction:
        console.print("\n[bold cyan]?[/bold cyan] [bold]System Instruction[/bold]")
        console.print("  [dim]Tip: Enter text directly OR path to a file (e.g. C:/prompts/coder.txt)[/dim]\n")
        
        user_input = Prompt.ask("  [cyan]Input[/cyan]")
        cleaned_input = user_input.strip().strip('"').strip("'")
        
        path_check = Path(cleaned_input)
        final_val = cleaned_input

        if path_check.exists() and path_check.is_file():
            console.print(f"  [green]✔ File detected:[/green] {path_check.name}")
        
        # Escape backslashes for JSON storage
        final_val = re.sub(r'\\', r'\\\\', final_val)

        write_global("ai_instruction", final_val)
        console.print("  [green]✔ Instruction updated.[/green]\n")
        return

    # =========================================================
    # STANDARD SETTINGS
    # =========================================================
    if editor:
        write_global("default_editor", editor)
        console.print(f"  [green]✔ Default editor set to:[/green] {editor}")
        return

    if code_theme:
        write_global("code_theme", code_theme)
        console.print(f"  [green]✔ Code theme set to:[/green] {code_theme}")
        return

    if add_marker:
        _modify_config_list(GLOBAL_CONFIG_PATH, "project_markers", add_marker, "add")
        return

    if remove_marker:
        _modify_config_list(GLOBAL_CONFIG_PATH, "project_markers", remove_marker, "remove")
        return

    # =========================================================
    # SHELL SELECTION
    # =========================================================
    if shell:
        candidates = get_all_history_candidates()
        if not candidates:
            console.print("  [yellow]! No history files found.[/yellow]")
            return

        console.print(f"\n[bold]Select History File[/bold] [dim]({target_name})[/dim]")
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, path in enumerate(candidates):
            table.add_row(f"[cyan]{i+1})[/cyan]", str(path))
        
        console.print(table)
        console.print("")

        choices = [str(x) for x in range(1, len(candidates) + 1)]
        selection = IntPrompt.ask("  [cyan]Enter number[/cyan]", choices=choices, show_choices=False)
        
        selected_path = candidates[selection - 1]
        write_local("history_file", str(selected_path))
        
        console.print(f"  [green]✔ History source updated:[/green] {selected_path.name}")
        return

    # =========================================================
    # CLEANUP
    # =========================================================
    if clear_local:
        if not local_bank:
            console.print("  [red]✖ Error: No local bank found.[/red]")
            return
        _clear_config(local_config)
        console.print("  [green]✔ Local configuration cleared.[/green]")
        return

    if clear_global:
        _clear_config(GLOBAL_CONFIG_PATH)
        console.print("  [green]✔ Global configuration cleared.[/green]")
        return

    # Fallback Help
    console.print("\n[dim]Usage: cwm config [OPTIONS][/dim]")
    console.print("[dim]Try 'cwm config --help' for details.[/dim]\n")