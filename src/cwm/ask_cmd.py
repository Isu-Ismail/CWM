# src/cwm/ask_cmd.py
import os
import re
import shlex
import socket
import click
import pyperclip
import textwrap
import shutil
from pathlib import Path
from abc import ABC, abstractmethod
from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme
from rich.markdown import CodeBlock
from rich.syntax import Syntax
from pygments.styles import get_style_by_name, ClassNotFound
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.patch_stdout import patch_stdout 
from .storage_manager import StorageManager
from .utils import DEFAULT_AI_INSTRUCTION
from .rich_help import RichHelpGroup,RichHelpCommand

CURRENT_CODE_THEME = "monokai"

def _patched_code_block_console(self, console, options):
    code = str(self.text)
    
    code = code.expandtabs(4)
    code = textwrap.dedent(code)
    code = code.strip()

    lexer_name = self.lexer_name if self.lexer_name != "default" else "python"
    
    syntax = Syntax(
        code, 
        lexer_name, 
        theme=CURRENT_CODE_THEME, 
        word_wrap=True, 
        padding=0
    )
    yield syntax

CodeBlock.__rich_console__ = _patched_code_block_console


DRACULA_UI_STYLES = {
    "bot.header": "bold #bd93f9",
    "user.header": "bold #50fa7b",
    "info": "#f8f8f2",
    "warning": "#f1fa8c",
    "error": "bold #ff5555",
    "success": "bold #50fa7b",
    "metric": "#8be9fd",
    "markdown.h1": "bold #bd93f9",
    "markdown.h2": "bold #ff79c6",
    "markdown.link": "#8be9fd underline",
    "markdown.code": "#f1fa8c",
}

class UI:
    def __init__(self, theme_style=None):
        if theme_style is None: theme_style = DRACULA_UI_STYLES
        self.console = Console(theme=Theme(theme_style))

    def _flatten_code_blocks(self, text):
        
        text = re.sub(r"([^\n])\s*(```)", r"\1\n\2", text)
        
        text = re.sub(r"(```[a-zA-Z0-9]*)\s+([^\n])", r"\1\n\2", text)
        
        return text
    def print_header(self, model_name):
        self.console.print(f"[bot.header]Model:[/bot.header] {model_name}")

    def print_bot_response(self, text, code_theme, response_id):
        global CURRENT_CODE_THEME
        CURRENT_CODE_THEME = code_theme
        self.console.print(f"[bot.header]DevBot:[/bot.header] [bold #FF8800]id:{response_id}[/bold #FF8800]")
        clean_text = self._flatten_code_blocks(textwrap.dedent(text))
        self.console.print(Markdown(clean_text, code_theme=code_theme))

    def print_error(self, msg): self.console.print(f"Error: {msg}", style="error")
    def print_info(self, msg): self.console.print(msg, style="info")
    def print_success(self, msg): self.console.print(msg, style="success")
    def print_warning(self, msg): self.console.print(msg, style="warning")
    
    def check_internet(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False

class BaseProvider(ABC):
    def __init__(self, model_name, system_instruction, api_key=None):
        self.model_name = model_name
        self.system_instruction = system_instruction
        self.api_key = api_key
    @abstractmethod
    def generate(self, text): pass

class GeminiProvider(BaseProvider):
    def __init__(self, model_name, system_instruction, api_key):
        super().__init__(model_name, system_instruction, api_key)
        if not api_key:
            raise ValueError("Gemini API Key missing. Run 'cwm config --gemini'")
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Library missing. Run: pip install google-genai")
        
        self.client = genai.Client(api_key=api_key)
        self.config = types.GenerateContentConfig(system_instruction=system_instruction)

    def generate(self, text):
        out = self.client.models.generate_content(
            model=self.model_name, contents=[text], config=self.config
        )
        return out.text

class OpenAIProvider(BaseProvider):
    def __init__(self, model_name, system_instruction, api_key):
        super().__init__(model_name, system_instruction, api_key)
        if not api_key:
            raise ValueError("OpenAI API Key missing. Run 'cwm config --openai'")
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Library missing. Run: pip install openai")
        
        self.client = OpenAI(api_key=api_key)

    def generate(self, text):
        r = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "system", "content": self.system_instruction}, {"role": "user", "content": text}]
        )
        return r.choices[0].message.content

class LocalProvider(BaseProvider):
    def __init__(self, model_name, system_instruction, api_key=None):
        super().__init__(model_name, system_instruction)
        try:
            import ollama
            self.ollama_module = ollama
        except ImportError:
            raise ImportError("Library missing. Run: pip install ollama")

    def generate(self, text):
        messages = [{"role": "system", "content": self.system_instruction}, {"role": "user", "content": text}]
        try:
            response = self.ollama_module.chat(model=self.model_name, messages=messages)
            out = response['message']['content']
            out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
            return out
        except Exception as e:
            return f"Local model error: {e}"

class CommandLexer(Lexer):
    def lex_document(self, document):
        text = document.text
        tokens = []
        if text.startswith(('/', '@')):
            space_idx = text.find(' ')
            if space_idx == -1:
                tokens.append(('class:command', text))
            else:
                tokens.append(('class:command', text[:space_idx]))
                tokens.append(('', text[space_idx:]))
        else:
            tokens.append(('', text))
        return lambda i: tokens

class ChatSession:
    def __init__(self, provider, ui, code_theme="monokai"):
        self.provider = provider
        self.ui = ui
        self.code_theme = code_theme
        self.history = []
        self.last_response = ""
        self.response_counter = 0
        self.response_code_history = {} 
        
        global CURRENT_CODE_THEME
        CURRENT_CODE_THEME = code_theme
        
        self.prompt_session = PromptSession(
            history=InMemoryHistory(),
            style=Style.from_dict({'user_header': '#50fa7b bold', 'command': '#8be9fd bold'}),
            lexer=CommandLexer(),
        )

    def _extract_clean_code(self, text):
        blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
        if not blocks: return textwrap.dedent(text).strip()
        cleaned = [textwrap.dedent(b.strip('\n')) for b in blocks]
        return "\n\n".join(cleaned)

    def _clean_response(self, text):
        if "User:" in text: text = text.split("User:")[0]
        text = re.sub(r"^(Assistant|DevBot):\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
        return text.strip()

    def _get_paste_input(self):
        self.ui.console.print("\n[bold yellow]-- PASTE MODE --[/bold yellow]")
        self.ui.console.print("Paste code now. Type '@end' on a new line to submit.\n")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "@end": break
                lines.append(line)
            except EOFError: break
        return "\n".join(lines)

    def run_single(self, prompt):
        if not isinstance(self.provider, LocalProvider) and not self.ui.check_internet():
            self.ui.print_error("No internet connection.")
            return
        
        self.response_counter += 1
        with self.ui.console.status("Thinking...", spinner="dots"):
            try:
                out = self.provider.generate(prompt)
            except Exception as e:
                self.ui.print_error(str(e))
                return
        
        out = self._clean_response(out)
        self.ui.print_bot_response(out, self.code_theme, self.response_counter)
        
        code = self._extract_clean_code(out)
        if code:
            try:
                pyperclip.copy(code)
                self.ui.print_success("Code copied to clipboard.")
            except: pass

    def run_interactive(self):
        self.ui.print_info("Interactive Mode. Type 'exit' to quit.")
        self.ui.print_info("Commands: /copy <id>, /theme <name>, @paste, @file <path>")

        while True:
            try:
                with patch_stdout():
                    prompt = self.prompt_session.prompt([('class:user_header', '\nYou: ')])
                    prompt = prompt.strip()
            except KeyboardInterrupt:
                self.ui.console.print("^C", style="bold red")
                continue 
            except EOFError:
                break

            if not prompt: continue
            if prompt.lower() in ["exit", "quit"]:
                    self.ui.console.print("\n[bold #50fa7b]DevBot signing off, Happy Coding ^_^ ![/bold #50fa7b]")
                    break
            
            if prompt.lower() in ["clear", "cls", "/clear"]:
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            if prompt == "/help":
                self.ui.print_info("Available Commands:")
                self.ui.console.print("  [bold]/help[/bold]           : Show this help message")
                self.ui.console.print("  [bold]/hist[/bold]        : Show history of your prompts")
                self.ui.console.print("  [bold]/copy <id>[/bold]      : Copy code from a specific response ID")
                self.ui.console.print("  [bold]/theme <name>[/bold]   : Switch code syntax theme (e.g. monokai, fruity)")
                self.ui.console.print("  [bold]/clear[/bold]          : Clear the terminal screen")
                self.ui.console.print("  [bold]@paste[/bold]          : Enter multi-line paste mode (end with @end)")
                self.ui.console.print("  [bold]@file <path>[/bold]    : Load content from a file")
                self.ui.console.print("  [bold]exit[/bold]             : Quit the application")
                continue

            if prompt == "@paste":
                prompt = self._get_paste_input()
                if not prompt.strip(): continue
                self.ui.print_success("Paste received.")

            if prompt.startswith("/copy"):
                parts = prompt.split()
                tid = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else self.response_counter
                if tid in self.response_code_history:
                    pyperclip.copy(self.response_code_history[tid])
                    self.ui.print_success(f"Copied ID: {tid}")
                else: self.ui.print_error("ID not found.")
                continue

            if prompt == "/hist":
                user_msgs = [h['content'] for h in self.history if h['role'] == 'user']
                if not user_msgs:
                    self.ui.print_info("No prompts history found.")
                    continue
                self.ui.console.print("\n[bold]Session History:[/bold]")
                for i, msg in enumerate(user_msgs, 1):
                    preview = msg.replace('\n', ' ')
                    if len(preview) > 75: preview = preview[:72] + "..."
                    self.ui.console.print(f"  [bold #FF8800]ID:{i}[/bold #FF8800]  {preview}")
                continue

            if prompt.startswith("/theme"):
                parts = prompt.split()
                if len(parts) >= 2:
                    new_theme = parts[1]
                    try:
                        get_style_by_name(new_theme)
                        self.code_theme = new_theme
                        global CURRENT_CODE_THEME
                        CURRENT_CODE_THEME = new_theme
                        self.ui.print_success(f"Theme switched to {self.code_theme}")
                    except ClassNotFound:
                        self.ui.print_error(f"Invalid theme: {new_theme}")
                else:
                    self.ui.print_error("Usage: /theme <name>")
                continue

            if prompt.startswith("@file"):
                parts = shlex.split(prompt[5:].strip())
                if parts and os.path.isfile(parts[0]):
                    try:
                        with open(parts[0], "r", encoding="utf-8") as f: prompt = f.read()
                        self.ui.print_success(f"Loaded: {parts[0]}")
                    except Exception as e: self.ui.print_error(f"Read error: {e}")
                else: self.ui.print_error("File not found.")
                
            # --- Generate ---
            if not isinstance(self.provider, LocalProvider) and not self.ui.check_internet():
                self.ui.print_error("No internet.")
                continue

            self.history.append({"role": "user", "content": prompt})
            convo = "\n\n".join(f"{'User' if h['role']=='user' else 'Assistant'}: {h['content']}" for h in self.history)
            self.response_counter += 1
            
            with self.ui.console.status("Thinking...", spinner="dots"):
                try:
                    out = self.provider.generate(convo)
                except Exception as e:
                    err_msg = str(e)

                    if "429" in err_msg or "ResourceExhausted" in err_msg:
                        match = re.search(r"'retryDelay':\s*'([^']+)'", err_msg)
                        
                        wait_time = match.group(1) if match else "a few seconds"
                        
                        self.ui.console.print(f"\n[bold yellow]⚠ Resource exhausted. Retry after {wait_time}.[/bold yellow]")

                    elif "400" in err_msg or "InvalidArgument" in err_msg:
                        self.ui.console.print("\n[bold yellow]⚠ Invalid API Key or Request (400).[/bold yellow]")

                    else:
                        self.ui.print_error(err_msg)

                    continue

            out = self._clean_response(out)
            self.history.append({"role": "assistant", "content": out})
            self.response_code_history[self.response_counter] = self._extract_clean_code(out)
            self.ui.print_bot_response(out, self.code_theme, self.response_counter)


def _resolve_instruction(manager):
    """
    Priority for resolving the instruction:
    1. Local 'instruction.txt' in current folder (Project Specific)
    2. Global Config 'ai_instruction':
       a. If value is a valid file path, read content from that file.
       b. Otherwise, use the value as the instruction string.
    3. Hardcoded DEFAULT_AI_INSTRUCTION
    """
    
    local_instr_path = Path.cwd() / "instruction.txt"
    if local_instr_path.exists():
        try:
            return local_instr_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass 
    
    config = manager.get_config()
    ai_instruction_config_value = config.get("ai_instruction")

    if ai_instruction_config_value:
        config_path = Path(ai_instruction_config_value)
        
        if config_path.is_file():
            try:
                return config_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass 
        
        return ai_instruction_config_value
    
    return DEFAULT_AI_INSTRUCTION

def launch_chat(provider_class, model_key, single_prompt):
    ui = UI()
    manager = StorageManager()
    config = manager.get_config("global")
    
    theme = config.get("code_theme", "monokai")
    
    instruction = _resolve_instruction(manager)
    
    model_conf = config.get(model_key, {})
    model_name = model_conf.get("model")
    api_key = model_conf.get("key")
    
    if not model_name:
        ui.print_error(f"No model configured for {model_key}. Run 'cwm config --{model_key}'")
        return

    if model_key == "local_ai":
        if shutil.which("ollama") is None:
            ui.print_error("Ollama not found. Install it from ollama.com")
            return

    try:
        if model_key == "local_ai":
            provider = provider_class(model_name, instruction)
        else:
            provider = provider_class(model_name, instruction, api_key)
    except Exception as e:
        ui.print_error(str(e))
        return

    ui.print_header(f"{model_name} ({model_key})")
    session = ChatSession(provider, ui, theme)

    if single_prompt:
        session.run_single(single_prompt)
    else:
        session.run_interactive()

@click.group("ask",cls=RichHelpGroup)
def ask_cmd():
    """AI Chat Assistant."""
    pass

@ask_cmd.command("gemini",help="launch gemini",cls=RichHelpCommand)
@click.option("-s", "--single", help="One-off prompt (non-interactive).")
def chat_gemini(single):
    launch_chat(GeminiProvider, "gemini", single)

@ask_cmd.command("openai",help="launch openai",cls=RichHelpCommand)
@click.option("-s", "--single", help="One-off prompt (non-interactive).")
def chat_openai(single):
    launch_chat(OpenAIProvider, "openai", single)

@ask_cmd.command("local",help="launch local model",cls =RichHelpCommand)
@click.option("-s", "--single", help="One-off prompt (non-interactive).")
def chat_local(single):
    launch_chat(LocalProvider, "local_ai", single)