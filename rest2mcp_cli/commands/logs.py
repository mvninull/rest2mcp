import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token

console = Console()
logs_app = typer.Typer(help="Comandos de logs")


def _require_auth():
    token = get_token()
    if not token:
        console.print(Panel(
            "[bold red]Nao autenticado[/bold red]\nObtem um token em [bold]https://rest2mcp.pages.dev/[/bold] e corre [bold]r2mcp login[/bold]",
            border_style="red", title="Erro", padding=(0, 1),
        ))
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(Panel(
            f"[bold red]{msg}[/bold red]\nObtem um token novo em [bold]https://rest2mcp.pages.dev/[/bold]",
            border_style="red", title="Token invalido", padding=(0, 1),
        ))
        raise typer.Exit(1)


@logs_app.command(name="get")
def logs_get(
    server_id: str = typer.Argument(..., help="ID do servidor"),
    limit: int = typer.Option(20, "--limit", "-n", help="Numero de logs a mostrar"),
):
    _require_auth()
    with console.status(f"[bold green]A obter logs do servidor '{server_id}'...", spinner="dots"):
        try:
            client = APIClient()
            entries = client.get_logs(server_id, limit)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    if not entries:
        console.print(Panel("[yellow]Nenhum log encontrado.[/yellow]", border_style="yellow"))
        return

    table = Table(box=box.ROUNDED, border_style="cyan", title=f"[bold]{len(entries)} log(s)[/bold]", title_style="bold")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Timestamp", no_wrap=True)
    table.add_column("Tool", no_wrap=True)
    table.add_column("Metodo", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Duracao (ms)", justify="right", no_wrap=True)
    for entry in entries:
        status = entry.get("status_code", 0)
        status_style = "green" if status < 400 else "red"
        dur = entry.get("duration_ms", 0)
        dur_style = "green" if dur < 500 else "yellow" if dur < 2000 else "red"
        table.add_row(
            str(entry.get("id", "")),
            entry.get("timestamp", ""),
            entry.get("tool_called", ""),
            entry.get("method", "") or "-",
            f"[{status_style}]{entry.get('status_code', '?')}[/{status_style}]",
            f"[{dur_style}]{dur:.1f}[/{dur_style}]",
        )
    console.print(table)
