import threading
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.index import ToolIndex
from engine.sandbox import Sandbox
from engine.stubs import generate_stubs_from_tools

from .cloud_models import ServerDB, SessionLocal
from .config import GATEWAY_HOST, GATEWAY_PORT
from .supabase_auth import require_auth
from .utils import logger

router = APIRouter(prefix="/v1/engine", tags=["engine"])

# Índice por utilizador, mantido em memória entre pedidos HTTP.
# Sem isto, cada /search e /run recalculava os embeddings de TODO o catálogo
# do utilizador a cada request — mesmo quando as tools não tinham mudado.
# ToolIndex.rebuild_if_changed() usa uma assinatura (hash) do catálogo para
# só recalcular quando algo de facto mudou (nova tool, descrição editada, etc).
_index_cache: dict[str, ToolIndex] = {}
_index_cache_lock = threading.Lock()


def _get_or_build_index(user_id: str, all_tools: list[dict]) -> ToolIndex:
    with _index_cache_lock:
        idx = _index_cache.get(user_id)
        if idx is None:
            idx = ToolIndex()
            _index_cache[user_id] = idx
    # rebuild_if_changed só recalcula embeddings se a assinatura do catálogo
    # mudou desde a última vez — caso contrário reaproveita o índice existente.
    idx.rebuild_if_changed(all_tools)
    return idx


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class RunRequest(BaseModel):
    workflow: str


def _collect_user_tools(user_id: str) -> tuple[dict[str, dict], list[dict]]:
    db = SessionLocal()
    try:
        servers = db.query(ServerDB).filter(ServerDB.user_id == user_id, ServerDB.is_active == True).all()
    finally:
        db.close()

    tool_map: dict[str, dict] = {}
    all_tools: list[dict] = []
    import json

    for server in servers:
        sid = server.server_id
        if not server.spec_data:
            continue
        try:
            spec = json.loads(server.spec_data) if isinstance(server.spec_data, str) else server.spec_data
        except Exception:
            continue

        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method, operation in methods.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                # O MCP proxy (fastmcp) gera nomes de tools assim:
                # 1. Se operationId existe → usa esse nome diretamente
                # 2. Se não → usa summary (com espaços → underscores)
                # A engine tem de gerar o mesmo nome para o _mcp_tool_name
                # corresponder ao que o proxy espera.
                raw_op_id = operation.get("operationId")
                if raw_op_id:
                    mcp_name = raw_op_id
                else:
                    mcp_name = operation.get("summary", f"{method} {path}")
                # Sanitizar: substituir caracteres inválidos em Python
                mcp_name = (
                    mcp_name.replace("/", "_").replace("-", "_").replace(" ", "_").replace("{", "_").replace("}", "_")
                )
                op_id = mcp_name
                tool_name = f"{sid}_{op_id}"
                description = operation.get("description") or operation.get("summary", "Ferramenta MCP")
                parameters = operation.get("parameters", [])
                request_body = operation.get("requestBody", {})

                input_schema = {"type": "object", "properties": {}, "required": []}
                for p in parameters:
                    pname = p.get("name", "param")
                    input_schema["properties"][pname] = p.get("schema", {"type": "string"})
                    if p.get("required", False):
                        input_schema["required"].append(pname)

                if request_body and "application/json" in (request_body.get("content") or {}):
                    body_schema = request_body["content"]["application/json"].get("schema", {})
                    for k, v in body_schema.get("properties", {}).items():
                        input_schema["properties"][k] = v
                    for r in body_schema.get("required", []):
                        if r not in input_schema["required"]:
                            input_schema["required"].append(r)

                entry = {
                    "name": tool_name,
                    "description": description,
                    "input_schema": input_schema,
                    "parameters": input_schema,
                    "_server_id": sid,
                    "_tool_key": tool_name,
                    "_method": method,
                    "_path": path,
                    "_mcp_tool_name": op_id,
                }
                all_tools.append(entry)
                tool_map[tool_name] = entry

    return tool_map, all_tools


@router.post("/search")
async def engine_search(req: SearchRequest, request: Request):
    await require_auth(request)
    user_id = request.state.user_id

    tool_map, all_tools = _collect_user_tools(user_id)
    if not all_tools:
        return {"stubs": "Nenhuma ferramenta encontrada.", "tools": []}

    idx = _get_or_build_index(user_id, all_tools)
    results = idx.search(req.query, top_k=req.top_k)
    stubs = generate_stubs_from_tools(results)
    return {"stubs": stubs, "tools": results}


@router.post("/run")
async def engine_run(req: RunRequest, request: Request):
    await require_auth(request)
    user_id = request.state.user_id

    tool_map, all_tools = _collect_user_tools(user_id)
    if not all_tools:
        raise HTTPException(status_code=400, detail="Nenhuma ferramenta disponivel")

    # Nota: /run não faz pesquisa de tools, só as executa — por isso não
    # precisa de construir/atualizar o ToolIndex aqui. Antes desta correção,
    # este endpoint reconstruía o índice (recalculando embeddings de todo o
    # catálogo) e nunca o usava — trabalho puramente desperdiçado.
    sandbox = Sandbox(tool_map=tool_map)

    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

    def caller(tool_key: str, arguments: dict) -> Any:
        info = tool_map.get(tool_key)
        if not info:
            raise ValueError(f"Tool '{tool_key}' nao encontrada")
        url = f"http://127.0.0.1:{GATEWAY_PORT}/v1/servers/{info['_server_id']}/tools/call"
        resp = httpx.post(
            url,
            json={"name": info["_mcp_tool_name"], "arguments": arguments},
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=30,
        )
        return resp.json().get("content", [])

    import asyncio, concurrent.futures

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        try:
            result = await loop.run_in_executor(pool, sandbox.execute, req.workflow, caller)
        except Exception as exc:
            logger.error(f"Engine run error: {exc}")
            return {"error": str(exc), "output": "", "result": None}

    return {
        "output": result.get("output", ""),
        "result": result.get("result"),
        "error": result.get("error"),
    }


# ─── MCP Streamable HTTP ─────────────────────────────────────────────────


class _EngineMCPServer:
    """Implementa o protocolo MCP Streamable HTTP para a engine.
    Expõe apenas 2 tools: search e run — a LLM nunca vê os servidores
    individuais, só a camada de orquestração."""

    TOOLS = [
        {
            "name": "search",
            "description": (
                "Pesquisa semanticamente ferramentas de todos os servidores "
                "MCP registados. Devolve stubs Python async para uso no run."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Descricao semântica do que procurar (ex: 'listar tarefas', 'produtos disponiveis')",
                    },
                    "top_k": {
                        "type": "number",
                        "default": 5,
                        "description": "Numero maximo de resultados",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "run",
            "description": (
                "Executa um workflow Python numa sandbox isolada com acesso "
                "a todas as ferramentas dos servidores MCP. O código deve "
                "definir `async def run_workflow(): ...` e usar `await`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "description": (
                            "Codigo Python com `async def run_workflow():` "
                            "que usa `await tool_name(...)` para chamar "
                            "ferramentas dos servidores."
                        ),
                    },
                },
                "required": ["workflow"],
            },
        },
    ]

    def __init__(self, user_id: str, bearer_token: str):
        self._user_id = user_id
        self._bearer_token = bearer_token

    def _get_tool_map(self):
        return _collect_user_tools(self._user_id)

    def handle_tools_list(self) -> dict:
        return {"tools": self.TOOLS}

    def handle_search(self, query: str, top_k: int = 5) -> dict:
        tool_map, all_tools = self._get_tool_map()
        if not all_tools:
            return {"content": [{"type": "text", "text": "Nenhuma ferramenta encontrada."}]}
        idx = _get_or_build_index(self._user_id, all_tools)
        results = idx.search(query, top_k=top_k)
        stubs = generate_stubs_from_tools(results)
        return {"content": [{"type": "text", "text": stubs}]}

    async def handle_run(self, workflow: str) -> dict:
        tool_map, all_tools = self._get_tool_map()
        if not all_tools:
            return {"content": [{"type": "text", "text": "Nenhuma ferramenta disponivel."}]}
        sandbox = Sandbox(tool_map=tool_map)

        def caller(tool_key: str, arguments: dict) -> Any:
            info = tool_map.get(tool_key)
            if not info:
                raise ValueError(f"Tool '{tool_key}' nao encontrada")
            url = f"http://127.0.0.1:{GATEWAY_PORT}/v1/servers/{info['_server_id']}/tools/call"
            resp = httpx.post(
                url,
                json={"name": info["_mcp_tool_name"], "arguments": arguments},
                headers={"Authorization": f"Bearer {self._bearer_token}"},
                timeout=30,
            )
            return resp.json().get("content", [])

        import asyncio

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, sandbox.execute, workflow, caller)
        except Exception as exc:
            logger.error(f"MCP engine run error: {exc}")
            return {"content": [{"type": "text", "text": f"Erro: {exc}"}]}

        if result.get("error"):
            return {
                "content": [{"type": "text", "text": f"Erro: {result['error']}\nOutput: {result.get('output', '')}"}]
            }
        import json

        return {"content": [{"type": "text", "text": json.dumps(result.get("result"), indent=2, default=str)}]}


@router.post("/mcp", include_in_schema=False)
async def engine_mcp(request: Request):
    """Endpoint MCP Streamable HTTP para a engine.
    A LLM/cliente MCP faz POST com JSON-RPC para listar tools
    (search, run) ou chamá-las."""
    body = await request.json()
    method = body.get("method", "")
    msg_id = body.get("id")
    params = body.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "engine", "version": "1.0.0"},
            },
        }

    if method in ("notifications/initialized",):
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    # Autenticação necessária para os métodos seguintes
    await require_auth(request)
    user_id = request.state.user_id
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
    engine = _EngineMCPServer(user_id, bearer_token)

    if method == "tools/list":
        result = engine.handle_tools_list()
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if tool_name == "search":
            result = engine.handle_search(query=args.get("query", ""), top_k=args.get("top_k", 5))
        elif tool_name == "run":
            result = await engine.handle_run(workflow=args.get("workflow", ""))
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' nao encontrada"},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method '{method}' nao suportado"},
    }
