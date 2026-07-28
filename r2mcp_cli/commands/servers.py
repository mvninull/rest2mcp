from typing import List

import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token

console = Console()
servers_app = typer.Typer(help="Comandos de gestão de servidores")


def _require_auth():
    token = get_token()
    if not token:
        console.print(
            "[red]ERRO: Nao autenticado. Obtém um token em https://rest2mcp.pages.dev/ e corre r2mcp login.[/red]"
        )
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(f"[red]ERRO: {msg}. Obtém um token novo em https://rest2mcp.pages.dev/[/red]")
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

    auth_statuses = {}
    health_statuses = {}
    active = [s for s in servers if s["status"] == "active"]
    if active:
        client = APIClient()
        for s in active:
            try:
                auth_statuses[s["server_id"]] = client.get_auth_status(s["server_id"])
            except APIError:
                pass
            try:
                health = client.get_server_health(s["server_id"])
                health_statuses[s["server_id"]] = health.get("status") == "ok"
            except APIError:
                health_statuses[s["server_id"]] = False
        client.close()

    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Nome")
    table.add_column("Status")
    table.add_column("API", no_wrap=True)
    table.add_column("Auth", no_wrap=True)
    table.add_column("Transporte")
    table.add_column("URL MCP")
    for s in servers:
        status_style = "green" if s["status"] == "active" else "red"
        auth_info = auth_statuses.get(s["server_id"], {})
        fields = auth_info.get("required_fields", [])
        authenticated = auth_info.get("authenticated", False)
        health_ok = health_statuses.get(s["server_id"])
        if health_ok:
            api_cell = "[green]\u2713[/green]"
        elif health_ok is None:
            api_cell = "[dim]\u2014[/dim]"
        else:
            api_cell = "[red]\u2717 offline[/red]"
        needs_auth = bool(fields) and not authenticated
        if fields:
            if authenticated:
                auth_cell = "[green]\u2713 autenticado[/green]"
            else:
                auth_cell = "[yellow]\u26a0 precisa auth[/yellow]"
        else:
            auth_cell = "[dim]\u2014[/dim]"
        url_cell = "[yellow]Faz login para liberar a url[/yellow]" if needs_auth else s["url_sse"]
        table.add_row(
            s["server_id"],
            s["name"],
            f"[{status_style}]{s['status']}[/{status_style}]",
            api_cell,
            auth_cell,
            s.get("transport", "http"),
            url_cell,
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


PASSWORD_KEYS = {"password", "senha", "pwd", "pass", "secret", "palavra-passe", "passwd"}


@servers_app.command()
def login(
    server_id: str = typer.Argument(..., help="ID do servidor"),
):
    _require_auth()
    client = APIClient()
    try:
        auth_info = client.get_auth_status(server_id)
    except APIError as e:
        client.close()
        console.print(f"[red]Erro: {e.detail}[/red]")
        raise typer.Exit(1)

    fields = auth_info.get("required_fields", [])
    if not fields:
        console.print("[yellow]Este servidor nao requer autenticacao.[/yellow]")
        client.close()
        return

    if auth_info.get("authenticated"):
        console.print("[green]Servidor ja esta autenticado.[/green]")
        client.close()
        return

    console.print(f"[bold]Login no servidor {server_id}[/bold]")
    console.print(f"[dim]Campos necessarios: {', '.join(fields)}[/dim]")

    values = {}
    for field in fields:
        is_password = field.lower() in PASSWORD_KEYS
        values[field] = Prompt.ask(
            field,
            password=is_password,
        )

    try:
        result = client.login_server(server_id, values)
        client.close()
        if result.get("token"):
            console.print("[green]Autenticado com sucesso![/green]")
        else:
            console.print("[red]Resposta inesperada do servidor.[/red]")
    except APIError as e:
        client.close()
        if "Internal Server Error" in e.detail or e.status_code == 500:
            console.print(
                "[red]API do servidor nao esta acessivel ou recusou o login. Verifica se a API esta online.[/red]"
            )
        else:
            console.print(f"[red]Erro no login: {e.detail}[/red]")
        raise typer.Exit(1)
