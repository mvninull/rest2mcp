import json
from typing import List, Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token
from r2mcp_cli.i18n import t

console = Console()
tools_app = typer.Typer(help=t("app.tools_help"))


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


@tools_app.command()
def list(
    server_id: str = typer.Argument(..., help=t("tools.list_help")),
):
    _require_auth()
    with console.status(f"[bold green]{t('tools.listing', id=server_id)}[/bold green]", spinner="dots"):
        try:
            client = APIClient()
            tools = client.list_tools(server_id)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
            raise typer.Exit(1)

    if not tools:
        console.print(Panel(f"[yellow]{t('tools.none')}[/yellow]", border_style="yellow"))
        return

    table = Table(box=box.ROUNDED, border_style="cyan", title=f"[bold]{t('tools.count', count=len(tools))}[/bold]", title_style="bold")
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column(t("tools.name"), style="cyan", no_wrap=True)
    table.add_column(t("tools.desc"))
    for i, tool in enumerate(tools, 1):
        desc = tool.get("description", "") or ""
        if len(desc) > 80:
            desc = desc[:77] + "..."
        table.add_row(str(i), tool.get("name", "?"), desc)
    console.print(table)


@tools_app.command()
def call(
    server_id: str = typer.Argument(..., help=t("servers.id_help")),
    tool_name: str = typer.Argument(..., help=t("tools.call_help_name")),
    args: Optional[str] = typer.Option(None, "--args", help=t("tools.call_help_args")),
    arg: List[str] = typer.Option([], "-A", help=t("tools.call_help_kv")),
):
    _require_auth()

    arguments = {}
    if args:
        try:
            arguments = json.loads(args)
        except json.JSONDecodeError as e:
            console.print(Panel(f"[red]{t('tools.json_invalid', error=e)}[/red]", border_style="red"))
            raise typer.Exit(1)
    elif arg:
        for kv in arg:
            if "=" not in kv:
                console.print(Panel(f"[red]{t('tools.kv_invalid', kv=kv)}[/red]", border_style="red"))
                raise typer.Exit(1)
            key, val = kv.split("=", 1)
            arguments[key] = val

    with console.status(f"[bold green]{t('tools.calling', name=tool_name)}[/bold green]", spinner="dots"):
        try:
            client = APIClient()
            result = client.call_tool(server_id, tool_name, arguments)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title=t("error")))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title=t("error_connection")))
            raise typer.Exit(1)

    if result.get("isError"):
        console.print(Panel(f"[red]{t('tools.call_error')}[/red]", border_style="red", title=t("error")))

    for content in result.get("content", []):
        ctype = content.get("type", "")
        text = content.get("text", "")
        if ctype == "text":
            console.print(Panel(text, border_style="dim", title=t("tools.result"), padding=(0, 1)))
        elif ctype in ("json", "json_object"):
            parsed = json.loads(text) if isinstance(text, str) else text
            syntax = Syntax(json.dumps(parsed, indent=2), "json", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, border_style="cyan", title=t("tools.result_json"), padding=(0, 1)))
        else:
            console.print(Panel(f"[{ctype}] {text}", border_style="dim", title=t("tools.result")))
