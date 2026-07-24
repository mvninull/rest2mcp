import typer
from rich import box
from rich.console import Console
from rich.table import Table

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token

console = Console()
logs_app = typer.Typer(help="Comandos de logs")


def _require_auth():
    token = get_token()
    if not token:
        console.print("[red]ERRO: Nao autenticado. Corre r2mcp login primeiro.[/red]")
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(f"[red]ERRO: {msg}[/red]")
        raise typer.Exit(1)


@logs_app.callback(invoke_without_command=True)
def logs_default(
    ctx: typer.Context,
    server_id: str = typer.Argument(..., help="ID do servidor"),
    limit: int = typer.Option(20, "--limit", "-n", help="Número de logs a mostrar"),
):
    _require_auth()
    with console.status(f"[bold green]A obter logs do servidor '{server_id}'..."):
        try:
            client = APIClient()
            entries = client.get_logs(server_id, limit)
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    if not entries:
        console.print("[yellow]Nenhum log encontrado.[/yellow]")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="dim")
    table.add_column("Timestamp")
    table.add_column("Tool")
    table.add_column("Método")
    table.add_column("Status")
    table.add_column("Duração (ms)")
    for entry in entries:
        status_style = "green" if entry.get("status_code", 0) < 400 else "red"
        table.add_row(
            str(entry.get("id", "")),
            entry.get("timestamp", ""),
            entry.get("tool_called", ""),
            entry.get("method", "") or "-",
            f"[{status_style}]{entry.get('status_code', '?')}[/{status_style}]",
            f"{entry.get('duration_ms', 0):.1f}",
        )
    console.print(table)
