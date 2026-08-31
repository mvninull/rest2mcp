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
from r2mcp_cli.config import get_base_url, get_token, validate_token
from r2mcp_cli.i18n import t

console = Console()
servers_app = typer.Typer(help=t("app.servers_help"))


def _require_auth():
    token = get_token()
    if not token:
        console.print(Panel(
            f"[bold red]{t('not_auth')}[/bold red]\n{t('get_token_at')}",
            border_style="red", title=t("error"), padding=(0, 1),
        ))
        raise typer.Exit(1)
    ok, msg = validate_token(token)
    if not ok:
        console.print(Panel(
            f"[bold red]{msg}[/bold red]\n{t('get_new_token_at')}",
            border_style="red", title=t("token_invalid"), padding=(0, 1),
        ))
        raise typer.Exit(1)


def _server_table(result: dict) -> Table:
    table = Table(box=box.ROUNDED, border_style="cyan", title=f"[bold]{t('servers.created')}[/bold]", title_style="bold green")
    table.add_column(t("field"), style="bold cyan", no_wrap=True)
    table.add_column(t("value"))
    table.add_row("ID", result["server_id"])
    table.add_row(t("servers.name"), result["name"])
    table.add_row(t("me.status"), result["status"])
    table.add_row(t("servers.transport"), result["transport"])
    table.add_row(t("servers.url_mcp"), result["url_sse"])
    table.add_row(t("servers.api_key"), result["apikey"])
    return table


@servers_app.command()
def create(
    name: str = typer.Option(..., "--name", "-n", help=t("servers.create_help_name")),
    spec_url: str = typer.Option(..., "--spec-url", "-u", help=t("servers.create_help_spec")),
    transport: str = typer.Option("sse", "--transport", "-t", help=t("servers.create_help_transport")),
    force_env: str = typer.Option(None, "--env", help="Forcar ambiente: local ou prod (auto se omitido)"),
):
    _require_auth()

    from urllib.parse import urlparse
    from r2mcp_cli.config import LOCAL_GATEWAY_URL

    parsed = urlparse(spec_url)
    scheme = parsed.scheme

    if not scheme or scheme not in ("http", "https"):
        console.print(Panel(f"[red]{t('servers.spec_invalid', url=spec_url)}[/red]", border_style="red", title=t("error")))
        raise typer.Exit(1)

    if force_env and force_env not in ("local", "prod"):
        console.print(Panel(f"[red]{t('config.env_invalid', env=force_env)}[/red]", border_style="red", title=t("error")))
        raise typer.Exit(1)

    is_https = scheme == "https"
    current_base = get_base_url()

    if force_env == "local":
        base = LOCAL_GATEWAY_URL
        env_label = t("config.local")
    elif force_env == "prod":
        base = None  # default from config
        env_label = t("config.prod")
    else:
        if is_https:
            base = None  # default (prod by default)
            env_label = t("config.prod")
        else:
            base = LOCAL_GATEWAY_URL
            env_label = t("config.local")

    if base is not None and base != current_base:
        console.print(Panel(
            f"[yellow]{t('servers.using_env', env=env_label, url=base)}[/yellow]",
            border_style="yellow", padding=(0, 1),
        ))

    with console.status(f"[bold green]{t('servers.creating', name=name)}[/bold green]", spinner="dots"):
        try:
            client = APIClient(base_url=base if base else None)
            result = client.create_server(name, spec_url, transport)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
            raise typer.Exit(1)

    console.print(_server_table(result))


@servers_app.command()
def list():
    _require_auth()
    console.print(f"[bold green]{t('servers.listing')}[/bold green]")

    try:
        client = APIClient()
        servers = client.list_servers()
        client.close()
    except APIError as e:
        console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
        raise typer.Exit(1)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
        raise typer.Exit(1)

    if not servers:
        console.print(Panel(f"[yellow]{t('servers.none')}[/yellow]", border_style="yellow"))
        return

    cols = shutil.get_terminal_size().columns
    sys.stdout.write(f"\r{' ' * cols}\r")
    sys.stdout.flush()

    table = Table(box=box.ROUNDED, border_style="cyan", title=f"[bold]{t('servers.count', count=len(servers))}[/bold]", title_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column(t("servers.name"), no_wrap=True)
    table.add_column(t("me.status"), no_wrap=True)
    table.add_column(t("servers.transport"), no_wrap=True)
    table.add_column(t("servers.url_mcp"), no_wrap=True)
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
def delete(server_id: str = typer.Argument(..., help=t("servers.id_help"))):
    _require_auth()
    if not Confirm.ask(f"[yellow]{t('servers.delete_confirm', id=server_id)}[/yellow]"):
        console.print(f"[yellow]{t('servers.delete_cancel')}[/yellow]")
        return

    with console.status(f"[bold red]{t('servers.deleting', id=server_id)}[/bold red]", spinner="dots"):
        try:
            client = APIClient()
            client.delete_server(server_id)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
            raise typer.Exit(1)

    console.print(Panel(f"[green]{t('servers.deleted', id=server_id)}[/green]", border_style="green"))


@servers_app.command()
def pause(server_id: str = typer.Argument(..., help=t("servers.id_help"))):
    _require_auth()
    with console.status(f"[bold yellow]{t('servers.pausing', id=server_id)}[/bold yellow]", spinner="dots"):
        try:
            client = APIClient()
            client.update_server(server_id, {"status": "inactive"})
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
            raise typer.Exit(1)

    console.print(Panel(f"[yellow]{t('servers.paused', id=server_id)}[/yellow]", border_style="yellow"))


@servers_app.command()
def resume(server_id: str = typer.Argument(..., help=t("servers.id_help"))):
    _require_auth()
    with console.status(f"[bold green]{t('servers.resuming', id=server_id)}[/bold green]", spinner="dots"):
        try:
            client = APIClient()
            client.update_server(server_id, {"status": "active"})
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
            raise typer.Exit(1)

    console.print(Panel(f"[green]{t('servers.resumed', id=server_id)}[/green]", border_style="green"))


@servers_app.command()
def credentials(
    server_id: str = typer.Argument(..., help=t("servers.id_help")),
    key_value: List[str] = typer.Option(
        [], "--set", "-s", help=t("servers.creds_help")
    ),
):
    _require_auth()
    client = APIClient()

    if key_value:
        creds = {}
        for kv in key_value:
            if "=" not in kv:
                console.print(Panel(f"[red]{t('servers.creds_invalid', kv=kv)}[/red]", border_style="red"))
                raise typer.Exit(1)
            k, v = kv.split("=", 1)
            creds[k] = v
        try:
            result = client.set_credentials(server_id, creds)
            client.close()
            console.print(Panel(f"[green]{t('servers.creds_saved', id=server_id)}[/green]", border_style="green"))
        except APIError as e:
            client.close()
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
    else:
        try:
            info = client.check_credentials(server_id)
            client.close()
        except APIError as e:
            client.close()
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        if info.get("has_credentials"):
            console.print(Panel(f"[green]{t('servers.creds_yes', id=server_id)}[/green]", border_style="green"))
        else:
            console.print(Panel(f"[yellow]{t('servers.creds_no', id=server_id)}[/yellow]", border_style="yellow"))


PASSWORD_KEYS = {"password", "senha", "pwd", "pass", "secret", "palavra-passe", "passwd"}


@servers_app.command()
def login(
    server_id: str = typer.Argument(..., help=t("servers.id_help")),
):
    _require_auth()
    client = APIClient()
    try:
        auth_info = client.get_auth_status(server_id)
    except APIError as e:
        client.close()
        console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
        raise typer.Exit(1)

    fields = auth_info.get("required_fields", [])
    if not fields:
        console.print(Panel(f"[yellow]{t('servers.login_no_auth')}[/yellow]", border_style="yellow"))
        client.close()
        return

    if auth_info.get("authenticated"):
        console.print(Panel(f"[green]{t('servers.login_already')}[/green]", border_style="green"))
        client.close()
        return

    console.print(Panel(
        f"[bold]{t('servers.login_header', id=server_id)}[/bold]\n[dim]{t('servers.login_fields', fields=', '.join(fields))}[/dim]",
        border_style="cyan", title=t("servers.login_auth"), padding=(0, 1),
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
            console.print(Panel(f"[green]{t('servers.login_ok')}[/green]", border_style="green"))
        else:
            console.print(Panel(f"[red]{t('servers.login_unexpected')}[/red]", border_style="red"))
    except APIError as e:
        client.close()
        if "Internal Server Error" in e.detail or e.status_code == 500:
            console.print(Panel(
                f"[red]{t('servers.login_api_down')}[/red]",
                border_style="red", title=t("error"),
            ))
        else:
            console.print(Panel(f"[red]{t('servers.login_error', detail=e.detail)}[/red]", border_style="red", title=t("error")))
        raise typer.Exit(1)
