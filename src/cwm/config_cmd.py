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

from .storage_manager import StorageManager, GLOBAL_CWM_BANK
from .rich_help import RichHelpCommand
from .utils import get_all_history_candidates

console = Console()
GLOBAL_CONFIG_PATH = GLOBAL_CWM_BANK / "config.json"

# =========================================================
# HELPERS (Simplified - Global Only)
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

def _write_config(key: str, value):
    data = _load_global_config()
    data[key] = value
    _save_global_config(data)

def _clear_config():
    if GLOBAL_CONFIG_PATH.exists():
        GLOBAL_CONFIG_PATH.unlink()
        # Re-create empty to avoid errors
        GLOBAL_CONFIG_PATH.write_text("{}")

def _modify_config_list(key: str, value: str, action: str):
    data = _load_global_config()
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
    _save_global_config(data)


# =========================================================
# MAIN COMMAND
# =========================================================
@click.command("config", help="Edit global configuration settings.", cls=RichHelpCommand)
@click.option("--shell", is_flag=True, help="Select preferred shell history file.")
@click.option("--clear-config", is_flag=True, help="Reset configuration to defaults.")
@click.option("--show", is_flag=True, help="Show configuration.")
@click.option("--editor", help="Set default editor.")
@click.option("--code-theme", help="Set code syntax highlighting theme.")
@click.option("--add-marker", help="Add project detection marker.")
@click.option("--remove-marker", help="Remove project detection marker.")
@click.option("--gemini", is_flag=True, help="Configure Gemini (Interactive).")
@click.option("--openai", is_flag=True, help="Configure OpenAI (Interactive).")
@click.option("--local-ai", is_flag=True, help="Configure Local AI (Interactive).")
@click.option("--instruction", is_flag=True, help="Set System Instruction.")
def config_cmd(shell, clear_config, show,
               editor, code_theme, add_marker, remove_marker,
               gemini, openai, local_ai, instruction):

    manager = StorageManager()

    # =========================================================
    # SHOW CONFIG
    # =========================================================
    # =========================================================
    # SHOW CONFIG
    # =========================================================
    if show:
        config = manager.get_config()
        console.print("")

        # 1. Configuration Source
        console.print("[bold blue ]Configuration Source[/bold blue]")
        status = "[green](Active)[/green]" if GLOBAL_CONFIG_PATH.exists() else "[dim](Not created)[/dim]"
        console.print(f"  [dim]Path:[/dim] {GLOBAL_CONFIG_PATH} {status}")
        console.print("")

        # 2. General Settings
        console.print("[bold green ]General Settings[/bold green ]")
        console.print(f"  [dim]History File:[/dim]   {config.get('history_file', 'Auto-Detect')}")
        console.print(f"  [dim]Default Editor:[/dim] {config.get('default_editor', 'code')}")
        console.print(f"  [dim]Code Theme:[/dim]     {config.get('code_theme', 'monokai')}")
        
        markers = config.get('project_markers', [])
        marker_str = ", ".join(markers) if markers else "None"
        console.print(f"  [dim]Markers:[/dim]        {marker_str}")
        console.print("")

        # 3. AI Configuration
        console.print("[bold green]AI Configuration[/bold green]")
        
        def format_key(k): return f"{k[:4]}...{k[-4:]}" if k else "Not Set"

        # Gemini
        g = config.get("gemini", {})
        console.print(f"  [bold cyan]Gemini:[/bold cyan]   Model='{g.get('model') or 'None'}'  Key='{format_key(g.get('key'))}'")

        # OpenAI
        o = config.get("openai", {})
        console.print(f"  [bold yellow2]OpenAI:[/bold yellow2]   Model='{o.get('model') or 'None'}'  Key='{format_key(o.get('key'))}'")

        # Local
        l = config.get("local_ai", {})
        console.print(f"  [bold magenta]Local AI:[/bold magenta] Model='{l.get('model') or 'None'}'")

        # Instruction
        instr = config.get("ai_instruction")
        console.print("")
        if instr:
            preview = instr[:80].replace("\n", " ") + "..." if len(instr) > 80 else instr
            console.print(f"  [white]Instruction:[/white] [dim]{preview}[/dim]")
        else:
            console.print("  [bold]Instruction:[/bold] [dim](Default)[/dim]")

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

        _write_config("ai_instruction", final_val)
        console.print("  [green]✔ Instruction updated.[/green]\n")
        return

    # =========================================================
    # STANDARD SETTINGS
    # =========================================================
    if editor:
        _write_config("default_editor", editor)
        console.print(f"  [green]✔ Default editor set to:[/green] {editor}")
        return

    if code_theme:
        _write_config("code_theme", code_theme)
        console.print(f"  [green]✔ Code theme set to:[/green] {code_theme}")
        return

    if add_marker:
        _modify_config_list("project_markers", add_marker, "add")
        return

    if remove_marker:
        _modify_config_list("project_markers", remove_marker, "remove")
        return

    # =========================================================
    # SHELL SELECTION
    # =========================================================
    if shell:
        candidates = get_all_history_candidates()
        if not candidates:
            console.print("  [yellow]! No history files found.[/yellow]")
            return

        console.print(f"\n[bold]Select History File[/bold]")
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, path in enumerate(candidates):
            table.add_row(f"[cyan]{i+1})[/cyan]", str(path))
        
        console.print(table)
        console.print("")

        choices = [str(x) for x in range(1, len(candidates) + 1)]
        selection = IntPrompt.ask("  [cyan]Enter number[/cyan]", choices=choices, show_choices=False)
        
        selected_path = candidates[selection - 1]
        _write_config("history_file", str(selected_path))
        
        console.print(f"  [green]✔ History source updated:[/green] {selected_path.name}")
        return

    # =========================================================
    # CLEANUP
    # =========================================================
    if clear_config:
        if Confirm.ask("Are you sure you want to reset all configurations?"):
            _clear_config()
            console.print("  [green]✔ Configuration reset to defaults.[/green]")
        return

    # Fallback Help
    console.print("\n[dim]Usage: cwm config [OPTIONS][/dim]")
    console.print("[dim]Try 'cwm config --help' for details.[/dim]\n")