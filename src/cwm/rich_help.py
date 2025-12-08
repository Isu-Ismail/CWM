import click
from rich.console import Console
from rich.table import Table

console = Console()


class RichHelpMixin:
    """Shared logic for rendering beautiful, minimal help."""

    def format_help(self, ctx, formatter):
        usage_text = f"[bold]Usage:[/bold] [bold cyan]{ctx.command_path}[/bold cyan] [dim][OPTIONS]"

        if any(p.param_type_name == "argument" for p in self.get_params(ctx)):
            usage_text += " [ARGS]..."
        else:
            if isinstance(self, click.Group):
                usage_text += " COMMAND [ARGS]..."

        usage_text += "[/dim]"

        console.print(f"\n{usage_text}\n")

        if self.help:
            console.print(f"  {self.help}\n")

        self._print_options(ctx)

        if isinstance(self, click.Group):
            self._print_subcommands(ctx)

    def _print_options(self, ctx):
        params = self.get_params(ctx)
        options = [p for p in params if p.param_type_name == "option"]

        if not options:
            return

        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column("Flag", style="bold cyan", justify="right")
        table.add_column("Description", style="white")

        for param in options:
            names = ", ".join(param.opts)
            if param.secondary_opts:
                names += ", " + ", ".join(param.secondary_opts)

            if not param.is_flag:
                names += f" [dim]{param.make_metavar(ctx)}[/dim]"

            help_text = param.help or ""
            table.add_row(names, help_text)

        console.print("[bold]Options[/bold]")
        console.print(table)
        console.print("")  # Spacing

    def _print_subcommands(self, ctx):
        commands = self.list_commands(ctx)
        if not commands:
            return

        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column("Command", style="bold magenta", justify="right")
        table.add_column("Description", style="white")

        for cmd_name in commands:
            cmd = self.get_command(ctx, cmd_name)
            if cmd and not cmd.hidden:
                table.add_row(cmd_name, cmd.get_short_help_str() or "")

        console.print("[bold]Commands[/bold]")
        console.print(table)
        console.print("")  # Spacing


class RichHelpCommand(RichHelpMixin, click.Command):
    """Use this for standalone commands (like 'save')."""
    pass


class RichHelpGroup(RichHelpMixin, click.Group):
    """Use this for command groups (like 'git', 'bank')."""
    pass


