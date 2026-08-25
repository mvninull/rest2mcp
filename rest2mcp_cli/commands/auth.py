import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_base_url, get_token, set_base_url, set_token, clear_token, validate_token

console = Console()
config_app = typer.Typer(help="Gerir configuracao local")

PROD_URL = "https://rest2mcp.fly.dev"
LOCAL_URL = "http://localhost:8080"


def _header(title: str, subtitle: str = ""):
    t = Text(title, style="bold cyan")
    if subtitle:
        t.append(f"\n{subtitle}", style="dim")
    console.print(Panel(t, border_style="cyan", padding=(0, 1)))


def _success(msg: str):
    console.print(Panel(f"[bold green]{msg}[/bold green]", border_style="green", padding=(0, 1)))


def _error(msg: str):
    console.print(Panel(f"[bold red]{msg}[/bold red]", border_style="red", padding=(0, 1)))


def _info_table(rows: list[tuple[str, str]], title: str = "") -> Table:
    table = Table(box=box.ROUNDED, border_style="cyan", title=title, title_style="bold")
    table.add_column("Campo", style="bold cyan", no_wrap=True)
    table.add_column("Valor")
    for label, value in rows:
        table.add_row(label, value)
    return table


def login():
    token = get_token()
    if token:
        ok, _ = validate_token(token)
        if not ok:
            _error("Token expirado.\nFaz [bold]r2mcp logout[/bold], obtém um novo em\nhttps://rest2mcp.pages.dev/ e faz login novamente.")
            return
        _error("Ja estas autenticado.\nFaz [bold]r2mcp logout[/bold] primeiro se quiseres mudar de conta.")
        return

    _header("r2mcp login", "Autenticar com o gateway rest2mcp")
    console.print()

    token = typer.prompt("Introduz o teu JWT do Supabase\nhttps://rest2mcp.pages.dev/", hide_input=True)
    if not token:
        _error("Token invalido.")
        raise typer.Exit(1)

    ok, msg = validate_token(token)
    if not ok:
        _error(f"Token invalido: {msg}")
        raise typer.Exit(1)

    set_token(token)

    with console.status("[bold green]A testar conexao...", spinner="dots"):
        try:
            client = APIClient()
            me = client.get_me()
            client.close()
        except APIError as e:
            clear_token()
            _error(f"Erro na autenticacao: {e.detail}\nObtém um token em https://rest2mcp.pages.dev/")
            raise typer.Exit(1)
        except Exception as e:
            clear_token()
            _error(f"Erro de conexao: {e}\nObtém um token em https://rest2mcp.pages.dev/")
            raise typer.Exit(1)

    table = _info_table([
        ("Email", me.get("email", "-")),
        ("Plano", me.get("plan_tier", "free")),
        ("Servidores", f"{me.get('servers_count', 0)} / {me.get('servers_limit', 1)}"),
    ])
    console.print(table)
    console.print()
    _success("Autenticado com sucesso!")


def logout():
    if not get_token():
        _error("Nao estás autenticado.")
        return
    clear_token()
    _success("Token removido.")


def me():
    token = get_token()
    if not token:
        _error("Nao autenticado.\nObtém um token em https://rest2mcp.pages.dev/ e corre [bold]r2mcp login[/bold].")
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        _error(f"{msg}\nObtém um token novo em https://rest2mcp.pages.dev/")
        raise typer.Exit(1)

    with console.status("[bold green]A obter informacoes do utilizador...", spinner="dots"):
        try:
            client = APIClient()
            data = client.get_me()
            client.close()
        except APIError as e:
            if e.status_code in (401, 403):
                _error("Nao autenticado.\nCorre [bold]r2mcp login[/bold] primeiro.")
            else:
                _error(f"Erro: {e.detail}")
            raise typer.Exit(1)
        except Exception as e:
            _error(f"Erro de conexao: {e}")
            raise typer.Exit(1)

    table = _info_table([
        ("ID", data.get("id", "-")),
        ("Email", data.get("email", "-")),
        ("Nome", data.get("name", "-")),
        ("Status", data.get("status", "-")),
        ("Plano", data.get("plan_tier", "free")),
        ("Servidores", f"{data.get('servers_count', 0)} / {data.get('servers_limit', 1)}"),
    ])
    console.print(table)


@config_app.command(name="show")
def config_show():
    cfg_base = get_base_url()
    token = get_token()
    token_status = "[green]configurado[/green]" if token else "[dim]nenhum[/dim]"
    if cfg_base == PROD_URL:
        env = "[bold blue]producao[/bold blue]"
    elif cfg_base == LOCAL_URL:
        env = "[bold yellow]local[/bold yellow]"
    else:
        env = f"[bold magenta]custom[/bold magenta] ({cfg_base})"

    table = _info_table([
        ("Ambiente", env),
        ("API URL", cfg_base),
        ("Token", token_status),
    ], title="[bold]Configuracao[/bold]")
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
        _error(f"Ambiente '{env}' invalido. Usa 'local' ou 'prod'.")
        raise typer.Exit(1)
    _success(f"Ambiente alterado para [bold]{env}[/bold]: {get_base_url()}")


@config_app.command(name="set-base")
def set_base(base_url: str = typer.Argument(..., help="URL base da API")):
    set_base_url(base_url)
    _success(f"URL base alterada para: [bold]{get_base_url()}[/bold]")
