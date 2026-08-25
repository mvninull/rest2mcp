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

console = Console()
tools_app = typer.Typer(help="Comandos de interacao com ferramentas")


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


@tools_app.command()
def list(
    server_id: str = typer.Argument(..., help="ID do servidor"),
):
    _require_auth()
    with console.status(f"[bold green]A listar tools do servidor '{server_id}'...", spinner="dots"):
        try:
            client = APIClient()
            tools = client.list_tools(server_id)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    if not tools:
        console.print(Panel("[yellow]Nenhuma tool encontrada.[/yellow]", border_style="yellow"))
        return

    table = Table(box=box.ROUNDED, border_style="cyan", title=f"[bold]{len(tools)} tool(s)[/bold]", title_style="bold")
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Nome", style="cyan", no_wrap=True)
    table.add_column("Descricao")
    for i, t in enumerate(tools, 1):
        desc = t.get("description", "") or ""
        if len(desc) > 80:
            desc = desc[:77] + "..."
        table.add_row(str(i), t.get("name", "?"), desc)
    console.print(table)


@tools_app.command()
def call(
    server_id: str = typer.Argument(..., help="ID do servidor"),
    tool_name: str = typer.Argument(..., help="Nome da tool"),
    args: Optional[str] = typer.Option(None, "--args", help="JSON string de argumentos"),
    arg: List[str] = typer.Option([], "-A", help="Argumentos key=value (pode usar multiplas vezes)"),
):
    _require_auth()

    arguments = {}
    if args:
        try:
            arguments = json.loads(args)
        except json.JSONDecodeError as e:
            console.print(Panel(f"[red]JSON invalido em --args: {e}[/red]", border_style="red"))
            raise typer.Exit(1)
    elif arg:
        for kv in arg:
            if "=" not in kv:
                console.print(Panel(f"[red]Formato invalido: '{kv}'. Esperado key=value.[/red]", border_style="red"))
                raise typer.Exit(1)
            key, val = kv.split("=", 1)
            arguments[key] = val

    with console.status(f"[bold green]A chamar tool '{tool_name}'...", spinner="dots"):
        try:
            client = APIClient()
            result = client.call_tool(server_id, tool_name, arguments)
            client.close()
        except APIError as e:
            console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
            raise typer.Exit(1)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
            raise typer.Exit(1)

    if result.get("isError"):
        console.print(Panel("[red]A tool retornou um erro:[/red]", border_style="red", title="Erro"))

    for content in result.get("content", []):
        ctype = content.get("type", "")
        text = content.get("text", "")
        if ctype == "text":
            console.print(Panel(text, border_style="dim", title="Resultado", padding=(0, 1)))
        elif ctype in ("json", "json_object"):
            parsed = json.loads(text) if isinstance(text, str) else text
            syntax = Syntax(json.dumps(parsed, indent=2), "json", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, border_style="cyan", title="Resultado (JSON)", padding=(0, 1)))
        else:
            console.print(Panel(f"[{ctype}] {text}", border_style="dim", title="Resultado"))
