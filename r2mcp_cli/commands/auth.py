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
            console.print(
                "[yellow]Token expirado. Faz logout primeiro, obtém um novo em https://rest2mcp.pages.dev/ e faz login novamente.[/yellow]"
            )
            return
        console.print("[yellow]Ja estas autenticado. Faz logout primeiro se quiseres mudar de conta.[/yellow]")
        return

    token = typer.prompt("Introduz o teu JWT do Supabase (obtem em https://rest2mcp.pages.dev/)", hide_input=True)
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
            console.print(f"[red]Erro na autenticacao: {e.detail}. Obtém um token em https://rest2mcp.pages.dev/[/red]")
            raise typer.Exit(1)
        except Exception as e:
            clear_token()
            console.print(f"[red]Erro de conexao: {e}. Obtém um token em https://rest2mcp.pages.dev/[/red]")
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
        console.print(
            "[red]ERRO: Nao autenticado. Obtém um token em https://rest2mcp.pages.dev/ e corre r2mcp login.[/red]"
        )
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(f"[red]ERRO: {msg}. Obtém um token novo em https://rest2mcp.pages.dev/[/red]")
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


PROD_URL = "https://rest2mcp.fly.dev"
LOCAL_URL = "http://localhost:8080"


@config_app.command(name="show")
def config_show():
    cfg_base = get_base_url()
    token = get_token()
    token_status = "[green]configurado[/green]" if token else "[dim]nenhum[/dim]"
    if cfg_base == PROD_URL:
        env = "[blue]producao[/blue]"
    elif cfg_base == LOCAL_URL:
        env = "[yellow]local[/yellow]"
    else:
        env = f"[magenta]custom[/magenta] ({cfg_base})"
    table = Table(box=box.SIMPLE)
    table.add_column("Configuracao", style="bold cyan")
    table.add_column("Valor")
    table.add_row("Ambiente", env)
    table.add_row("API URL", cfg_base)
    table.add_row("Token", token_status)
    console.print(table)


@config_app.command(name="set-env")
def config_set_env(
    env: str = typer.Argument(..., help="Ambiente: local ou prod"),
):
    if env == "local":
        set_base_url(LOCAL_URL)
    elif env == "prod":
        set_base_url(PROD_URL)
    else:
        console.print(f"[red]Ambiente '{env}' invalido. Usa 'local' ou 'prod'.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Ambiente alterado para {env}: {get_base_url()}[/green]")


@config_app.command(name="set-base")
def set_base(base_url: str = typer.Argument(..., help="URL base da API")):
    set_base_url(base_url)
    console.print(f"[green]URL base alterada para: {get_base_url()}[/green]")
