import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_base_url, get_token, validate_token

console = Console()
link_app = typer.Typer(help="Ligar servidor a editor IA")


EDITOR_CONFIGS = {
    "claude-code": {
        "paths": lambda: [
            Path.cwd() / ".mcp.json",
            Path.home() / ".claude.json",
        ],
        "key": "mcpServers",
        "label": "Claude Code",
    },
    "cursor": {
        "paths": lambda: [Path.cwd() / ".cursor" / "mcp.json", Path.home() / ".cursor" / "mcp.json"],
        "key": "mcpServers",
        "label": "Cursor",
    },
    "vscode": {
        "paths": lambda: [Path.cwd() / ".vscode" / "mcp.json"],
        "key": "servers",
        "label": "VS Code",
    },
    "opencode": {
        "paths": lambda: [Path.cwd() / "opencode.json"],
        "key": "mcp",
        "label": "OpenCode",
    },
}


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


def _find_server(server_id: str) -> Optional[dict]:
    client = APIClient()
    try:
        servers = client.list_servers()
        client.close()
    except APIError as e:
        client.close()
        console.print(Panel(f"[red]{e.detail}[/red]", border_style="red", title="Erro"))
        raise typer.Exit(1)
    except Exception as e:
        client.close()
        console.print(Panel(f"[red]{e}[/red]", border_style="red", title="Erro de conexao"))
        raise typer.Exit(1)

    for s in servers:
        if s["server_id"] == server_id:
            return s
    return None


def _resolve_config_path(editor: str) -> Optional[Path]:
    info = EDITOR_CONFIGS.get(editor)
    if not info:
        return None
    for p in info["paths"]():
        if str(p).strip():
            return p
    return None


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


@link_app.command(name="add")
def link_add(
    editor: str = typer.Argument(..., help="Editor: claude-code, cursor, vscode, opencode"),
    server_id: str = typer.Argument(..., help="ID do servidor"),
):
    _require_auth()

    if editor not in EDITOR_CONFIGS:
        supported = ", ".join(EDITOR_CONFIGS.keys())
        console.print(Panel(
            f"[red]Editor '{editor}' nao suportado[/red]\nOpcoes: [bold]{supported}[/bold]",
            border_style="red", title="Erro",
        ))
        raise typer.Exit(1)

    config_path = _resolve_config_path(editor)
    if not config_path:
        console.print(Panel(
            f"[red]Nao foi possivel determinar o caminho de configuracao para '{editor}'.[/red]",
            border_style="red", title="Erro",
        ))
        raise typer.Exit(1)

    server = _find_server(server_id)
    if not server:
        console.print(Panel(
            f"[red]Servidor '{server_id}' nao encontrado.[/red]",
            border_style="red", title="Erro",
        ))
        raise typer.Exit(1)
    if server["status"] == "active":
        try:
            client = APIClient()
            auth_info = client.get_auth_status(server_id)
            client.close()
            if auth_info.get("required_fields") and not auth_info.get("authenticated"):
                console.print(Panel(
                    "[red]Servidor precisa de autenticacao.\nFaz o login primeiro com [bold]r2mcp servers login[/bold].[/red]",
                    border_style="red", title="Erro",
                ))
                raise typer.Exit(1)
        except APIError:
            pass
    apikey = server.get("apikey", "")
    url = f"{get_base_url()}/v1/{server_id}/{apikey}/mcp"
    name = server.get("name", server_id)
    transport = "streamable-http"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = _read_json(config_path)

    if editor == "claude-code":
        mcp_url = url.replace("/sse", "/mcp") if url.endswith("/sse") else url
        key = "mcpServers"
        if key not in config:
            config[key] = {}
        config[key][name] = {
            "command": "npx",
            "args": ["-y", "mcp-remote", mcp_url],
        }

    elif editor == "cursor":
        key = "mcpServers"
        if key not in config:
            config[key] = {}
        config[key][name] = {
            "url": url,
            "transport": transport,
        }

    elif editor == "vscode":
        key = "servers"
        if key not in config:
            config[key] = {}
        config[key][name] = {
            "type": transport,
            "url": url,
        }

    elif editor == "opencode":
        key = "mcp"
        if key not in config:
            config[key] = {}
        config[key][name] = {
            "type": "remote",
            "url": url,
            "enabled": True,
        }

    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    editor_label = EDITOR_CONFIGS[editor]["label"]

    table = Table(box=box.ROUNDED, border_style="green", title="[bold]Servidor ligado![/bold]", title_style="bold green")
    table.add_column("Campo", style="bold cyan", no_wrap=True)
    table.add_column("Valor")
    table.add_row("Editor", editor_label)
    table.add_row("Servidor", name)
    table.add_row("Ficheiro", str(config_path))
    console.print(table)

    if editor == "claude-code":
        console.print(Panel(
            "[yellow]O Claude Code usa 'mcp-remote' como bridge.\nCertifica-te de que o Node.js esta instalado e disponivel no PATH para correr npx.[/yellow]",
            border_style="yellow", title="Nota",
        ))
    else:
        console.print(Panel(
            f"[green]Reinicia o {editor_label} para aplicar as alteracoes.[/green]",
            border_style="green",
        ))
