import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_base_url, get_token, set_base_url, set_token, clear_token, validate_token
from r2mcp_cli.i18n import t

console = Console()
config_app = typer.Typer(help=t("app.config_help"))

PROD_URL = "https://rest2mcp.fly.dev"
LOCAL_URL = "http://localhost:8080"


def _header(title: str, subtitle: str = ""):
    txt = Text(title, style="bold cyan")
    if subtitle:
        txt.append(f"\n{subtitle}", style="dim")
    console.print(Panel(txt, border_style="cyan", padding=(0, 1)))


def _success(msg: str):
    console.print(Panel(f"[bold green]{msg}[/bold green]", border_style="green", padding=(0, 1)))


def _error(msg: str):
    console.print(Panel(f"[bold red]{msg}[/bold red]", border_style="red", padding=(0, 1)))


def _info_table(rows: list[tuple[str, str]], title: str = "") -> Table:
    table = Table(box=box.ROUNDED, border_style="cyan", title=title, title_style="bold")
    table.add_column(t("field"), style="bold cyan", no_wrap=True)
    table.add_column(t("value"))
    for label, value in rows:
        table.add_row(label, value)
    return table


def login():
    token = get_token()
    if token:
        ok, _ = validate_token(token)
        if not ok:
            _error(t("auth.token_expired"))
            return
        _error(t("auth.already_auth"))
        return

    _header(t("auth.login_header"), t("auth.login_sub"))
    console.print()

    token = typer.prompt(t("auth.token_prompt"), hide_input=True)
    if not token:
        _error(t("auth.token_invalid"))
        raise typer.Exit(1)

    ok, msg = validate_token(token)
    if not ok:
        _error(f"{t('auth.token_invalid')}: {msg}")
        raise typer.Exit(1)

    set_token(token)

    with console.status(f"[bold green]{t('auth.testing')}[/bold green]", spinner="dots"):
        try:
            client = APIClient()
            me = client.get_me()
            client.close()
        except APIError as e:
            clear_token()
            _error(t("auth.error_auth", detail=e.detail))
            raise typer.Exit(1)
        except Exception as e:
            clear_token()
            _error(t("auth.error_connection", error=e))
            raise typer.Exit(1)

    table = _info_table([
        (t("me.email"), me.get("email", "-")),
        (t("me.plan"), me.get("plan_tier", "free")),
        (t("me.servers"), f"{me.get('servers_count', 0)} / {me.get('servers_limit', 1)}"),
    ])
    console.print(table)
    console.print()
    _success(t("auth.success"))


def logout():
    if not get_token():
        _error(t("auth.not_auth"))
        return
    clear_token()
    _success(t("auth.removed"))


def me():
    token = get_token()
    if not token:
        _error(f"{t('not_auth')}.\n{t('get_token_at')}")
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        _error(f"{msg}\n{t('get_new_token_at')}")
        raise typer.Exit(1)

    with console.status(f"[bold green]{t('me.fetching')}[/bold green]", spinner="dots"):
        try:
            client = APIClient()
            data = client.get_me()
            client.close()
        except APIError as e:
            if e.status_code in (401, 403):
                _error(t("me.not_auth"))
            else:
                _error(f"{t('error')}: {e.detail}")
            raise typer.Exit(1)
        except Exception as e:
            _error(f"{t('error_connection')}: {e}")
            raise typer.Exit(1)

    table = _info_table([
        ("ID", data.get("id", "-")),
        (t("me.email"), data.get("email", "-")),
        (t("me.name"), data.get("name", "-")),
        (t("me.status"), data.get("status", "-")),
        (t("me.plan"), data.get("plan_tier", "free")),
        (t("me.servers"), f"{data.get('servers_count', 0)} / {data.get('servers_limit', 1)}"),
    ])
    console.print(table)


@config_app.command(name="show")
def config_show():
    cfg_base = get_base_url()
    token = get_token()
    token_status = f"[green]{t('config.token_set')}[/green]" if token else f"[dim]{t('config.token_none')}[/dim]"
    if cfg_base == PROD_URL:
        env = f"[bold blue]{t('config.prod')}[/bold blue]"
    elif cfg_base == LOCAL_URL:
        env = f"[bold yellow]{t('config.local')}[/bold yellow]"
    else:
        env = f"[bold magenta]{t('config.custom')}[/bold magenta] ({cfg_base})"

    table = _info_table([
        (t("config.env"), env),
        ("API URL", cfg_base),
        ("Token", token_status),
    ], title=f"[bold]{t('config.title')}[/bold]")
    console.print(table)


@config_app.command(name="set-env")
def config_set_env(
    env: str = typer.Argument(..., help=t("config.env_help")),
):
    if env == "local":
        set_base_url(LOCAL_URL)
    elif env == "prod":
        set_base_url(PROD_URL)
    else:
        _error(t("config.env_invalid", env=env))
        raise typer.Exit(1)
    _success(t("config.env_changed", env=env, url=get_base_url()))


@config_app.command(name="set-base")
def set_base(base_url: str = typer.Argument(..., help=t("config.base_help"))):
    set_base_url(base_url)
    _success(t("config.base_changed", url=get_base_url()))
