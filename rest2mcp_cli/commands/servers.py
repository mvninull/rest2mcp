import shutil
import sys
from typing import List

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token

console = Console()
servers_app = typer.Typer(help="Comandos de gestao de servidores")


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


def _server_table(result: dict) -> Table:
    table = Table(box=box.ROUNDED, border_style="cyan", title="[bold]Servidor criado[/bold]", title_style="bold green")
    table.add_column("Campo", style="bold cyan", no_wrap=True)
    table.add_column("Valor")
    table.add_row("ID", result["server_id"])
    table.add_row("Nome", result["name"])
    table.add_row("Status", result["status"])
    table.add_row("Transporte", result["transport"])
    table.add_row("URL MCP", result["url_sse"])
    table.add_row("API Key", result["apikey"])
    return table


@servers_app.command()
def create(
    name: str = typer.Option(..., "--name", "-n", help="Nome do servidor"),
    spec_url: str = typer.Option(..., "--spec-url", "-u", help="URL do spec OpenAPI"),
    transport: str = typer.Option("sse", "--transport", "-t", help="Transporte (sse ou http)"),
):
    _require_auth()
    with console.status(f"[bold green]A criar servidor '{name}'...", spinner="dots"):
        try:
            client = APIClient()
            result = client.create_server(name, spec_url, transport)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    console.print(_server_table(result))


@servers_app.command()
def list():
    _require_auth()
    console.print("[bold green]A listar servidores...[/bold green]")

    try:
        client = APIClient()
        servers = client.list_servers()
        client.close()
    except APIError as e:
        console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
        raise typer.Exit(1)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
        raise typer.Exit(1)

    if not servers:
        console.print(Panel("[yellow]Nenhum servidor encontrado.[/yellow]", border_style="yellow"))
        return

    cols = shutil.get_terminal_size().columns
    sys.stdout.write(f"\r{' ' * cols}\r")
    sys.stdout.flush()

    table = Table(box=box.ROUNDED, border_style="cyan", title=f"[bold]{len(servers)} servidor(es)[/bold]", title_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Nome", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Transporte", no_wrap=True)
    table.add_column("URL MCP", no_wrap=True)
    for s in servers:
        status_style = "green" if s["status"] == "active" else "red"
        sid = s["server_id"]
        if len(sid) > 14:
            sid = sid[:11] + "..."
        url = s["url_sse"]
        url_display = url if len(url) <= 50 else url[:47] + "..."
        table.add_row(
            sid,
            s["name"],
            f"[{status_style}]{s['status']}[/{status_style}]",
            s.get("transport", "http"),
            url_display,
        )
    console.print(table)


@servers_app.command()
def delete(server_id: str = typer.Argument(..., help="ID do servidor")):
    _require_auth()
    if not Confirm.ask(f"[yellow]Tens a certeza que queres apagar o servidor '{server_id}'?[/yellow]"):
        console.print("[yellow]Operacao cancelada.[/yellow]")
        return

    with console.status(f"[bold red]A apagar servidor '{server_id}'...", spinner="dots"):
        try:
            client = APIClient()
            client.delete_server(server_id)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    console.print(Panel(f"[green]Servidor '{server_id}' apagado.[/green]", border_style="green"))


@servers_app.command()
def pause(server_id: str = typer.Argument(..., help="ID do servidor")):
    _require_auth()
    with console.status(f"[bold yellow]A pausar servidor '{server_id}'...", spinner="dots"):
        try:
            client = APIClient()
            client.update_server(server_id, {"status": "inactive"})
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    console.print(Panel(f"[yellow]Servidor '{server_id}' pausado.[/yellow]", border_style="yellow"))


@servers_app.command()
def resume(server_id: str = typer.Argument(..., help="ID do servidor")):
    _require_auth()
    with console.status(f"[bold green]A retomar servidor '{server_id}'...", spinner="dots"):
        try:
            client = APIClient()
            client.update_server(server_id, {"status": "active"})
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    console.print(Panel(f"[green]Servidor '{server_id}' retomado.[/green]", border_style="green"))


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
                console.print(Panel(f"[red]Formato invalido: '{kv}'. Use chave=valor.[/red]", border_style="red"))
                raise typer.Exit(1)
            k, v = kv.split("=", 1)
            creds[k] = v
        try:
            result = client.set_credentials(server_id, creds)
            client.close()
            console.print(Panel(f"[green]Credenciais salvas para '{server_id}'.[/green]", border_style="green"))
        except APIError as e:
            client.close()
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
    else:
        try:
            info = client.check_credentials(server_id)
            client.close()
        except APIError as e:
            client.close()
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        if info.get("has_credentials"):
            console.print(Panel(f"[green]Servidor '{server_id}' tem credenciais configuradas.[/green]", border_style="green"))
        else:
            console.print(Panel(f"[yellow]Servidor '{server_id}' nao tem credenciais configuradas.[/yellow]", border_style="yellow"))


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
        console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
        raise typer.Exit(1)

    fields = auth_info.get("required_fields", [])
    if not fields:
        console.print(Panel("[yellow]Este servidor nao requer autenticacao.[/yellow]", border_style="yellow"))
        client.close()
        return

    if auth_info.get("authenticated"):
        console.print(Panel("[green]Servidor ja esta autenticado.[/green]", border_style="green"))
        client.close()
        return

    console.print(Panel(
        f"[bold]Login no servidor [cyan]{server_id}[/cyan][/bold]\n[dim]Campos necessarios: {', '.join(fields)}[/dim]",
        border_style="cyan", title="Autenticacao", padding=(0, 1),
    ))
    console.print()

    values = {}
    for field in fields:
        is_password = field.lower() in PASSWORD_KEYS
        values[field] = Prompt.ask(f"  [bold cyan]{field}[/bold cyan]", password=is_password)

    try:
        result = client.login_server(server_id, values)
        client.close()
        if result.get("token"):
            console.print(Panel("[green]Autenticado com sucesso![/green]", border_style="green"))
        else:
            console.print(Panel("[red]Resposta inesperada do servidor.[/red]", border_style="red"))
    except APIError as e:
        client.close()
        if "Internal Server Error" in e.detail or e.status_code == 500:
            console.print(Panel(
                "[red]API do servidor nao esta acessivel ou recusou o login.\nVerifica se a API esta online.[/red]",
                border_style="red", title="Erro",
            ))
        else:
            console.print(Panel(f"[red]Erro no login: {e.detail}[/red]", border_style="red", title="Erro"))
        raise typer.Exit(1)
