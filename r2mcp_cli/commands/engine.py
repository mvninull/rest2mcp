import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.syntax import Syntax

from r2mcp_cli.config import get_token

console = Console()
engine_app = typer.Typer(help="Motor de orquestracao: search e run")


def _require_auth():
    if not get_token():
        console.print("[red]ERRO: Nao autenticado. Corre r2mcp login primeiro.[/red]")
        raise typer.Exit(1)


@engine_app.command()
def search(
    query: str = typer.Argument(..., help="Query de pesquisa semanticas"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Numero de resultados"),
):
    _require_auth()
    from engine import Orchestrator

    with console.status("[bold green]A pesquisar ferramentas..."):
        orch = Orchestrator()
        orch.refresh()
        result = orch.search(query)

    console.print(Syntax(result, "python", theme="monokai", line_numbers=True))


@engine_app.command()
def run(
    workflow: str = typer.Argument(..., help="Codigo Python do workflow ou caminho para ficheiro"),
):
    _require_auth()
    from engine import Orchestrator

    if Path(workflow).is_file():
        code = Path(workflow).read_text(encoding="utf-8")
    else:
        code = workflow

    with console.status("[bold green]A executar workflow na sandbox..."):
        orch = Orchestrator()
        orch.refresh()
        result = orch.run(code)

    if result.get("error"):
        console.print(f"[red]ERRO: {result['error']}[/red]")
    if result.get("output"):
        console.print("[yellow]Output:[/yellow]")
        console.print(result["output"])
    if result.get("result") is not None:
        console.print("[green]Resultado:[/green]")
        console.print(result["result"])
