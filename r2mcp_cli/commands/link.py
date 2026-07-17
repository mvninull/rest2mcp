import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from r2mcp_cli.api_client import APIClient, APIError
from r2mcp_cli.config import get_token

console = Console()
link_app = typer.Typer(help="Ligar servidor a editor IA")


EDITOR_CONFIGS = {
    "claude-code": {
        "paths": lambda: [
            Path.cwd() / ".mcp.json",
            Path.home() / ".claude.json",
        ],
        "key": "mcpServers",
    },
    "cursor": {
        "paths": lambda: [Path.cwd() / ".cursor" / "mcp.json", Path.home() / ".cursor" / "mcp.json"],
        "key": "mcpServers",
    },
    "vscode": {
        "paths": lambda: [Path.cwd() / ".vscode" / "mcp.json"],
        "key": "servers",
    },
    "opencode": {
        "paths": lambda: [Path.cwd() / "opencode.json"],
        "key": "mcp",
    },
}


def _require_auth():
    if not get_token():
        console.print("[red]ERRO: Nao autenticado. Por favor, corre r2mcp login primeiro.[/red]")
        raise typer.Exit(1)


def _find_server(server_id: str) -> Optional[dict]:
    client = APIClient()
    try:
        servers = client.list_servers()
        client.close()
    except APIError as e:
        client.close()
        console.print(f"[red]Erro: {e.detail}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        client.close()
        console.print(f"[red]Erro de conexao: {e}[/red]")
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


@link_app.callback(invoke_without_command=True)
def link(
    editor: str = typer.Argument(..., help="Editor: claude-code, cursor, vscode, opencode"),
    server_id: str = typer.Argument(..., help="ID do servidor"),
):
    _require_auth()

    if editor not in EDITOR_CONFIGS:
        console.print(f"[red]Editor '{editor}' nao suportado. Opcoes: {', '.join(EDITOR_CONFIGS.keys())}[/red]")
        raise typer.Exit(1)

    config_path = _resolve_config_path(editor)
    if not config_path:
        console.print(f"[red]Nao foi possivel determinar o caminho de configuracao para '{editor}'.[/red]")
        raise typer.Exit(1)

    with console.status(f"[bold green]A procurar servidor '{server_id}'..."):
        server = _find_server(server_id)

    if not server:
        console.print(f"[red]Servidor '{server_id}' nao encontrado.[/red]")
        raise typer.Exit(1)

    url = server.get("url_sse", "")
    transport = server.get("transport", "sse")
    name = server.get("name", server_id)

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

    editor_name = {
        "claude-code": "Claude Code",
        "cursor": "Cursor",
        "vscode": "VS Code",
        "opencode": "OpenCode",
    }.get(editor, editor)

    console.print(
        f"[green]Servidor ligado ao {editor_name}! Por favor, reinicia o editor para aplicar as alteracoes.[/green]"
    )
    console.print(f"  Ficheiro: [bold]{config_path}[/bold]")

    if editor == "claude-code":
        console.print(
            "[yellow]  Nota: O Claude Code usa 'mcp-remote' como bridge. "
            "Certifica-te de que o Node.js esta instalado e disponivel no PATH para correr npx.[/yellow]"
        )
