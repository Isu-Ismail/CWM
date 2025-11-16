import os 
import click
from pathlib import Path
from .utils import safe_create_cwm_folder


CWM_FOLDER = ".cwm"
GLOBAL_CWM_FOLDER = Path.home() / "cwm_global"


@click.group()
def cli():
    """CWM Command Watch Manager"""
    pass



@cli.command()
def init():
    """Initializes a .cwm folder in the current direcotry. """
    project_path = Path.cwd() /CWM_FOLDER

    if project_path.exists():
        click.echo("A .cwm folder already exists in this project")
        return

    #crete folder
    ok = safe_create_cwm_folder(project_path)

    if ok :
        click.echo("Initialized empty CWM repository in this project.")
    else:
        click.echo("CWM initialization failed")



def ensure_global_folder():
    """Ensure global fallback folder exists with safety checks."""
    if not GLOBAL_CWM_FOLDER.exists():
        click.echo("Creating global CWM folder...")
        success = safe_create_cwm_folder(GLOBAL_CWM_FOLDER)
        if not success:
            click.echo("ERROR: Could not create global .cwm_global folder.")
            return

ensure_global_folder()



@cli.command()
def hello():
    """Test command."""
    click.echo("Hello! Welcome to CWM your command watch manager.")

if __name__ == "__main__":
    cli()
