import psutil
import click
from rich.console import Console
from rich.table import Table
from rich.prompt import IntPrompt, Confirm
from .rich_help import RichHelpCommand

console = Console()

def get_process_owner(proc):
    """Safely get the user who owns the process."""
    try:
        return proc.username()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        # If we can't read the owner, it's likely a high-level system process
        return "SYSTEM"

def is_system_process(owner):
    """Check if the owner implies a critical system process."""
    # List of names that indicate a protected system process
    critical_owners = ["NT AUTHORITY\\SYSTEM", "root", "SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE", "SYSTEM/UNKNOWN"]
    # Check exact match or if "SYSTEM" is part of the name (e.g. SYSTEM/UNKNOWN)
    return owner in critical_owners or "SYSTEM" in owner

@click.command(cls=RichHelpCommand)
@click.argument("port", type=int, required=False)
@click.option("--all", "-a", is_flag=True, help="List user active ports and choose one to kill")
@click.option("--force", "-f", is_flag=True, help="Kill without asking for confirmation")
def kill_cmd(port, all, force):
    """Kills the process running on a specific PORT or lists active user ports."""

    if all:
        list_and_interactive_kill(force)
    elif port:
        kill_process_on_port(port, force)
    else:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())


def list_and_interactive_kill(force):
    console.print("[bold cyan]Scanning for active user ports...[/]")
    
    table = Table(title="Your Active Processes")
    table.add_column("Port", style="cyan", justify="right")
    table.add_column("PID", style="magenta")
    table.add_column("Process Name", style="green")
    table.add_column("User", style="white")

    active_ports = []
    
    # Scan network connections
    for conn in psutil.net_connections(kind='inet'):
        if conn.status == 'LISTEN':
            try:
                proc = psutil.Process(conn.pid)
                owner = get_process_owner(proc)
                
                # --- SAFETY FILTER ---
                # If it is a system process, skip it entirely.
                if is_system_process(owner):
                    continue
                
                table.add_row(
                    str(conn.laddr.port),
                    str(conn.pid),
                    proc.name(),
                    owner
                )
                active_ports.append(conn.laddr.port)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not active_ports:
        console.print("[yellow]No active user ports found.[/]")
        return

    console.print(table)
    
    # Interactive Prompt
    target_port = IntPrompt.ask("Enter the PORT you want to kill (or 0 to exit)", default=0)
    
    if target_port == 0:
        console.print("[yellow]Exited.[/]")
        return

    if target_port not in active_ports:
        console.print(f"[bold red]Port {target_port} is not in the list (or is a protected system port).[/]")
        return

    # Pass to the killer function
    kill_process_on_port(target_port, force)


def kill_process_on_port(port, force):
    # 1. Find the process
    target_proc = None
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port == port:
                    target_proc = proc
                    break
            if target_proc:
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not target_proc:
        console.print(f"[yellow]No process found running on port {port}.[/]")
        return

    # 2. Safety Checks
    try:
        proc_name = target_proc.name()
        proc_pid = target_proc.pid
        owner = get_process_owner(target_proc)
        
        # BLOCK KILLING SYSTEM PROCESSES
        if is_system_process(owner):
            console.print(f"[bold red]⛔ SAFETY BLOCK:[/bold red] Port {port} is used by [cyan]{proc_name}[/] (User: {owner}).")
            console.print("[red]This is a system process and cannot be killed by CWM.[/]")
            return
        
        console.print(f"\n[bold cyan]Found process:[/bold cyan] [green]{proc_name}[/] (PID: {proc_pid}) owned by '{owner}'")

    except psutil.NoSuchProcess:
        console.print("[red]Process died before we could kill it.[/]")
        return

    # 3. Confirm
    if not force:
        if not Confirm.ask(f"Kill {proc_name} on port {port}?"):
            console.print("[dim]Aborted.[/]")
            return

    # 4. Kill it
    try:
        target_proc.terminate()
        target_proc.wait(timeout=3)
        console.print(f"[bold green]✔ Process {proc_name} ({proc_pid}) terminated successfully.[/]")
    except psutil.AccessDenied:
        console.print("[bold red]❌ Access Denied. You might need Administrator/Sudo privileges.[/]")
    except Exception as e:
        console.print(f"[bold red]❌ Error: {e}[/]")

if __name__ == "__main__":
    kill_cmd()