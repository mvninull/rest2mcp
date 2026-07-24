from typing import List

import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token

console = Console()
servers_app = typer.Typer(help="Comandos de gestão de servidores")


def _require_auth():
    token = get_token()
    if not token:
        console.print("[red]ERRO: Nao autenticado. Corre r2mcp login primeiro.[/red]")
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(f"[red]ERRO: {msg}[/red]")
        raise typer.Exit(1)


@servers_app.command()
def create(
    name: str = typer.Option(..., "--name", "-n", help="Nome do servidor"),
    spec_url: str = typer.Option(..., "--spec-url", "-u", help="URL do spec OpenAPI"),
    transport: str = typer.Option("sse", "--transport", "-t", help="Transporte (sse ou http)"),
):
    _require_auth()
    with console.status(f"[bold green]A criar servidor '{name}'..."):
        try:
            client = APIClient()
            result = client.create_server(name, spec_url, transport)
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    table = Table(box=box.SIMPLE)
    table.add_column("Campo", style="bold cyan")
    table.add_column("Valor")
    table.add_row("ID", result["server_id"])
    table.add_row("Nome", result["name"])
    table.add_row("Status", result["status"])
    table.add_row("Transporte", result["transport"])
    table.add_row("URL MCP", result["url_sse"])
    table.add_row("API Key", result["apikey"])
    console.print(table)
    console.print("[green]Servidor criado![/green]")


@servers_app.command()
def list():
    _require_auth()
    with console.status("[bold green]A listar servidores..."):
        try:
            client = APIClient()
            servers = client.list_servers()
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    if not servers:
        console.print("[yellow]Nenhum servidor encontrado.[/yellow]")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Nome")
    table.add_column("Status")
    table.add_column("Transporte")
    table.add_column("URL MCP")
    for s in servers:
        status_style = "green" if s["status"] == "active" else "red"
        table.add_row(
            s["server_id"],
            s["name"],
            f"[{status_style}]{s['status']}[/{status_style}]",
            s.get("transport", "http"),
            s["url_sse"],
        )
    console.print(table)


@servers_app.command()
def delete(server_id: str = typer.Argument(..., help="ID do servidor")):
    _require_auth()
    if not Confirm.ask(f"[yellow]Tens a certeza que queres apagar o servidor '{server_id}'?[/yellow]"):
        console.print("[yellow]Operação cancelada.[/yellow]")
        return

    with console.status(f"[bold red]A apagar servidor '{server_id}'..."):
        try:
            client = APIClient()
            client.delete_server(server_id)
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[green]Servidor '{server_id}' apagado.[/green]")


@servers_app.command()
def pause(server_id: str = typer.Argument(..., help="ID do servidor")):
    _require_auth()
    with console.status(f"[bold yellow]A pausar servidor '{server_id}'..."):
        try:
            client = APIClient()
            client.update_server(server_id, {"status": "inactive"})
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[green]Servidor '{server_id}' pausado.[/green]")


@servers_app.command()
def resume(server_id: str = typer.Argument(..., help="ID do servidor")):
    _require_auth()
    with console.status(f"[bold green]A retomar servidor '{server_id}'..."):
        try:
            client = APIClient()
            client.update_server(server_id, {"status": "active"})
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[green]Servidor '{server_id}' retomado.[/green]")


@servers_app.command()
def credentials(
    server_id: str = typer.Argument(..., help="ID do servidor"),
    key_value: List[str] = typer.Option(
        [], "--set", "-s", help="Par chave=valor (ex: -s username=admin -s password=123456)"
    ),
):
    _require_auth()
    client = APIClient()

    if key_value:
        creds = {}
        for kv in key_value:
            if "=" not in kv:
                console.print(f"[red]Formato invalido: '{kv}'. Use chave=valor.[/red]")
                raise typer.Exit(1)
            k, v = kv.split("=", 1)
            creds[k] = v
        try:
            result = client.set_credentials(server_id, creds)
            client.close()
            console.print(f"[green]Credenciais salvas para '{server_id}'.[/green]")
        except APIError as e:
            client.close()
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
    else:
        try:
            info = client.check_credentials(server_id)
            client.close()
        except APIError as e:
            client.close()
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        if info.get("has_credentials"):
            console.print(f"[green]Servidor '{server_id}' tem credenciais configuradas.[/green]")
        else:
            console.print(f"[yellow]Servidor '{server_id}' nao tem credenciais configuradas.[/yellow]")
