import json
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.syntax import Syntax

from r2mcp_cli.config import get_base_url, get_token

console = Console()
engine_app = typer.Typer(help="Motor de orquestracao: search e run")


def _require_auth():
    if not get_token():
        console.print("[red]ERRO: Nao autenticado. Corre r2mcp login primeiro.[/red]")
        raise typer.Exit(1)


_REQ_ID = 0


def _mcp_call(method: str, params: dict | None = None) -> dict:
    global _REQ_ID
    _REQ_ID += 1
    token = get_token()
    payload = {"jsonrpc": "2.0", "id": _REQ_ID, "method": method}
    if params:
        payload["params"] = params

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{get_base_url()}/v1/engine/mcp",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"MCP error {err.get('code', '?')}: {err.get('message', str(err))}")
    return data.get("result")


def _ensure_initialized():
    _mcp_call(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "r2mcp-cli", "version": "1.0.0"},
        },
    )


@engine_app.command()
def search(
    query: str = typer.Argument(..., help="Query de pesquisa semantica"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Numero de resultados"),
):
    _require_auth()
    _ensure_initialized()

    with console.status("[bold green]A pesquisar ferramentas via MCP..."):
        result = _mcp_call(
            "tools/call",
            {
                "name": "search",
                "arguments": {"query": query, "top_k": top_k},
            },
        )

    text = ""
    for c in (result or {}).get("content", []):
        if c.get("type") == "text":
            text += c.get("text", "")

    if text:
        console.print(Syntax(text, "python", theme="monokai", line_numbers=True))
    else:
        console.print("[yellow]Nenhuma ferramenta encontrada.[/yellow]")


@engine_app.command()
def run(
    workflow: str = typer.Argument(..., help="Codigo Python do workflow ou caminho para ficheiro"),
):
    _require_auth()
    _ensure_initialized()

    if Path(workflow).is_file():
        code = Path(workflow).read_text(encoding="utf-8")
    else:
        code = workflow

    with console.status("[bold green]A executar workflow na sandbox via MCP..."):
        result = _mcp_call(
            "tools/call",
            {
                "name": "run",
                "arguments": {"workflow": code},
            },
        )

    text = ""
    for c in (result or {}).get("content", []):
        if c.get("type") == "text":
            text += c.get("text", "")

    if not text:
        console.print("[yellow]Sem resposta da engine.[/yellow]")
        return

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "error" in parsed:
            console.print(f"[red]ERRO: {parsed['error']}[/red]")
            if parsed.get("output"):
                console.print(f"[yellow]Output:[/yellow]\n{parsed['output']}")
        else:
            console.print("[green]Resultado:[/green]")
            console.print_json(text)
    except json.JSONDecodeError:
        console.print(text)
