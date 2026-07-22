from typing import Any

from r2mcp_cli.api_client import APIClient
from r2mcp_cli.config import get_token

from .index import ToolIndex
from .stubs import generate_stubs_from_tools
from .sandbox import Sandbox


class Orchestrator:
    def __init__(self):
        self._client: APIClient | None = None
        self._index = ToolIndex()
        self._tool_map: dict[str, dict] = {}
        self._sandbox: Sandbox | None = None

    def _ensure_client(self):
        if not self._client:
            if not get_token():
                raise RuntimeError("Nao autenticado. Corre r2mcp login primeiro.")
            self._client = APIClient()

    def refresh(self):
        self._ensure_client()

        servers = self._client.list_servers()
        all_tools: list[dict] = []
        self._tool_map = {}

        for server in servers:
            sid = server["server_id"]
            try:
                tools = self._client.list_tools(sid)
            except Exception:
                continue

            for t in tools:
                tname = t.get("name", "unknown")
                tool_key = f"{sid}_{tname}"
                entry = {**t, "_server_id": sid, "_tool_key": tool_key}
                all_tools.append(entry)
                self._tool_map[tool_key] = entry

        # Só recalcula embeddings se o catálogo mudou desde o último refresh
        # (relevante quando o Orchestrator é reaproveitado dentro do mesmo
        # processo — ex: sessão de daemon/servidor de longa duração. Numa
        # invocação isolada de CLI por comando, cada processo arranca do
        # zero de qualquer forma, por isso o ganho aqui só se aplica a
        # processos que mantenham a mesma instância de Orchestrator viva).
        self._index.rebuild_if_changed(all_tools)
        self._sandbox = Sandbox(tool_map=self._tool_map)

    def search(self, query: str) -> str:
        results = self._index.search(query, top_k=5)
        if not results:
            return "Nenhuma ferramenta encontrada para esta pesquisa."
        return generate_stubs_from_tools(results)

    def _call_tool_via_gateway(self, tool_key: str, arguments: dict) -> Any:
        info = self._tool_map.get(tool_key)
        if not info:
            raise ValueError(f"Tool '{tool_key}' nao encontrada")
        server_id = info["_server_id"]
        tool_name = info["name"]
        result = self._client.call_tool(server_id, tool_name, arguments)
        return result.get("content", [])

    def run(self, workflow: str) -> dict:
        if not self._sandbox:
            self.refresh()
        return self._sandbox.execute(workflow, caller=self._call_tool_via_gateway)