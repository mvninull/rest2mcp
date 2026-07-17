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
    help="CLI para gestão de servidores MCP via rest2mcp gateway",
    no_args_is_help=True,
)

app.command()(login)
app.command()(logout)
app.command()(me)
app.add_typer(config_app, name="config", help="Gerir configuração local")
app.add_typer(servers_app, name="servers", help="Gerir servidores MCP")
app.add_typer(tools_app, name="tools", help="Interagir com ferramentas MCP")
app.add_typer(link_app, name="link", help="Ligar servidor a editor IA")
app.add_typer(logs_app, name="logs", help="Ver logs de servidores")


@app.callback()
def callback():
    pass


if __name__ == "__main__":
    app()
