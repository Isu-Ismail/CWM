import subprocess
import platform
import re
import click
from rich.console import Console
from rich.table import Table
from .rich_help import RichHelpCommand

console = Console()

def get_current_ssid():
    """Gets the SSID of the currently connected network."""
    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"], 
            encoding="cp850", errors="ignore"
        )
        # Regex to find "    SSID                   : WiFiName"
        # Note: We look for the line starting with whitespace, then SSID, then colon
        match = re.search(r"^\s*SSID\s*:\s*(.*)$", output, re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None

def get_saved_profiles():
    """Returns a list of all saved WiFi profile names."""
    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "profiles"], 
            encoding="cp850", errors="ignore"
        )
        profiles = re.findall(r"All User Profile\s*:\s*(.*)", output)
        return [p.strip() for p in profiles]
    except subprocess.CalledProcessError:
        return []

def get_wifi_password(profile_name):
    """Gets the password for a specific saved profile."""
    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "profile", f"name={profile_name}", "key=clear"], 
            encoding="cp850", errors="ignore"
        )
        match = re.search(r"Key Content\s*:\s*(.*)", output)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None

@click.command(cls=RichHelpCommand)
@click.option("--all", "-a", is_flag=True, help="List all saved networks with passwords")
def wifi_cmd(all):
    """Show WiFi passwords."""
    
    if platform.system() != "Windows":
        console.print("[red]Error: Windows only.[/]")
        return

    # --- MODE 1: SHOW ALL SAVED PASSWORDS ---
    if all:
        profiles = get_saved_profiles()
        if not profiles:
            console.print("[yellow]No saved profiles found.[/]")
            return

        # Compact, borderless table
        table = Table(box=None, padding=(0, 2), show_edge=False)
        table.add_column("IDX", style="dim", justify="right")
        table.add_column("SSID", style="cyan bold")
        table.add_column("PASSWORD", style="green")

        with console.status("[dim]Scanning saved networks...[/dim]"):
            for i, ssid in enumerate(profiles, 1):
                password = get_wifi_password(ssid) or "[Open/Unknown]"
                table.add_row(str(i), ssid, password)

        console.print(table)
        return

    # --- MODE 2: SHOW CURRENT CONNECTION (DEFAULT) ---
    current_ssid = get_current_ssid()
    
    if not current_ssid:
        console.print("[yellow]Not connected[/]")
        return

    password = get_wifi_password(current_ssid)
    
    if password:
        console.print(f"[cyan bold]{current_ssid}[/]  [green]{password}[/]")
    else:
        console.print(f"[cyan bold]{current_ssid}[/]  [yellow](Open Network)[/]")

if __name__ == "__main__":
    wifi_cmd()