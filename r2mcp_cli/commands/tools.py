import json
from typing import List, Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token, validate_token

console = Console()
tools_app = typer.Typer(help="Comandos de interação com ferramentas")


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


@tools_app.command()
def list(
    server_id: str = typer.Argument(..., help="ID do servidor"),
):
    _require_auth()
    with console.status(f"[bold green]A listar tools do servidor '{server_id}'..."):
        try:
            client = APIClient()
            tools = client.list_tools(server_id)
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    if not tools:
        console.print("[yellow]Nenhuma tool encontrada.[/yellow]")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim")
    table.add_column("Nome", style="cyan")
    table.add_column("Descrição")
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
    arg: List[str] = typer.Option([], "-A", help="Argumentos key=value (pode usar múltiplas vezes)"),
):
    _require_auth()

    arguments = {}
    if args:
        try:
            arguments = json.loads(args)
        except json.JSONDecodeError as e:
            console.print(f"[red]JSON inválido em --args: {e}[/red]")
            raise typer.Exit(1)
    elif arg:
        for kv in arg:
            if "=" not in kv:
                console.print(f"[red]Formato inválido: '{kv}'. Esperado key=value.[/red]")
                raise typer.Exit(1)
            key, val = kv.split("=", 1)
            arguments[key] = val

    with console.status(f"[bold green]A chamar tool '{tool_name}'..."):
        try:
            client = APIClient()
            result = client.call_tool(server_id, tool_name, arguments)
            client.close()
        except APIError as e:
            console.print(f"[red]Erro: {e.detail}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Erro de conexão: {e}[/red]")
            raise typer.Exit(1)

    if result.get("isError"):
        console.print("[red]A tool retornou um erro:[/red]")

    for content in result.get("content", []):
        ctype = content.get("type", "")
        text = content.get("text", "")
        if ctype == "text":
            console.print(text)
        elif ctype in ("json", "json_object"):
            parsed = json.loads(text) if isinstance(text, str) else text
            syntax = Syntax(json.dumps(parsed, indent=2), "json", theme="monokai")
            console.print(syntax)
        else:
            console.print(f"[{ctype}] {text}")
