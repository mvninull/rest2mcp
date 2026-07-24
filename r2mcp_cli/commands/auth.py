import typer
from rich import box
from rich.console import Console
from rich.table import Table

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_base_url, get_token, set_base_url, set_token, clear_token, validate_token

console = Console()
config_app = typer.Typer(help="Gerir configuracao local")


def login():
    token = get_token()
    if token:
        ok, _ = validate_token(token)
        if not ok:
            console.print("[yellow]Token expirado. Faz logout primeiro e depois faz login novamente.[/yellow]")
            return
        console.print("[yellow]Ja estas autenticado. Faz logout primeiro se quiseres mudar de conta.[/yellow]")
        return

    token = typer.prompt("Introduz o teu JWT do Supabase", hide_input=True)
    if not token:
        console.print("[red]Token invalido.[/red]")
        raise typer.Exit(1)

    ok, msg = validate_token(token)
    if not ok:
        console.print(f"[red]Token invalido: {msg}[/red]")
        raise typer.Exit(1)

    set_token(token)

    with console.status("[bold green]A testar conexao..."):
        try:
            client = APIClient()
            me = client.get_me()
            client.close()
        except APIError as e:
            clear_token()
            console.print(f"[red]Erro na autenticacao: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            clear_token()
            console.print(f"[red]Erro de conexao: {e}[/red]")
            raise typer.Exit(1)

    table = Table(box=box.SIMPLE)
    table.add_column("Campo", style="bold cyan")
    table.add_column("Valor")
    table.add_row("Email", me.get("email", "-"))
    table.add_row("Plano", me.get("plan_tier", "free"))
    table.add_row("Servidores", f"{me.get('servers_count', 0)} / {me.get('servers_limit', 1)}")
    console.print(table)
    console.print("[green]Autenticado com sucesso![/green]")


def logout():
    if not get_token():
        console.print("[yellow]Nao estás autenticado.[/yellow]")
        return
    clear_token()
    console.print("[green]Token removido.[/green]")


def me():
    token = get_token()
    if not token:
        console.print("[red]ERRO: Nao autenticado. Corre r2mcp login primeiro.[/red]")
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(f"[red]ERRO: {msg}[/red]")
        raise typer.Exit(1)

    with console.status("[bold green]A obter informacoes do utilizador..."):
        try:
            client = APIClient()
            data = client.get_me()
            client.close()
        except APIError as e:
            if e.status_code in (401, 403):
                console.print("[red]ERRO: Nao autenticado. Por favor, corre r2mcp login primeiro.[/red]")
            else:
                console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexao: {e}[/red]")
            raise typer.Exit(1)

    table = Table(box=box.SIMPLE)
    table.add_column("Campo", style="bold cyan")
    table.add_column("Valor")
    table.add_row("ID", data.get("id", "-"))
    table.add_row("Email", data.get("email", "-"))
    table.add_row("Nome", data.get("name", "-"))
    table.add_row("Status", data.get("status", "-"))
    table.add_row("Plano", data.get("plan_tier", "free"))
    table.add_row("Servidores", f"{data.get('servers_count', 0)} / {data.get('servers_limit', 1)}")
    console.print(table)


@config_app.command(name="set-base")
def set_base(base_url: str = typer.Argument(..., help="URL base da API")):
    set_base_url(base_url)
    console.print(f"[green]URL base alterada para: {get_base_url()}[/green]")
