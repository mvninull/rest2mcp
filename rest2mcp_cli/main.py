import shutil
import typer
from rich.console import Console

from r2mcp_cli.commands.auth import login, logout, me, config_app
from r2mcp_cli.commands.servers import servers_app
from r2mcp_cli.commands.tools import tools_app
from r2mcp_cli.commands.link import link_app
from r2mcp_cli.commands.logs import logs_app

console = Console()

app = typer.Typer(
    name="r2mcp",
    help="CLI para gestao de servidores MCP via rest2mcp gateway",
    add_completion=False,
)

app.command()(login)
app.command()(logout)
app.command()(me)
app.add_typer(config_app, name="config", help="Gerir configuracao local")
app.add_typer(servers_app, name="servers", help="Gerir servidores MCP")
app.add_typer(tools_app, name="tools", help="Interagir com ferramentas MCP")
app.add_typer(link_app, name="link", help="Ligar servidor a editor IA")
app.add_typer(logs_app, name="logs", help="Ver logs de servidores")


def _banner():
    w = shutil.get_terminal_size().columns
    line = "r2mcp v0.2.0".center(w)
    sub = "rest2mcp - Convert any REST API to MCP".center(w)
    console.print(f"[dim]{line}[/dim]")
    console.print(f"[dim]{sub}[/dim]")
    console.print()


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        _banner()
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
