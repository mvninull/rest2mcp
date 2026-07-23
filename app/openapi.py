import importlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP

from engine.index import ToolIndex
from engine.sandbox import Sandbox
from engine.stubs import generate_stubs_from_tools

try:
    from .utils import logger
except ImportError:
    from utils import logger


def _resolve_route_map_types():
    """Localiza RouteMap + o tipo EXCLUDE, em qualquer versão do fastmcp.

    A localização e os nomes mudaram entre versões:
      - Atual:         fastmcp.server.providers.openapi.{RouteMap, MCPType}
      - Intermediária: fastmcp.server.openapi.{RouteMap, MCPType}
      - Experimental:  fastmcp.experimental.server.openapi.{RouteMap, MCPType}
      - Pré-2.5.0:     fastmcp.{RouteMap, RouteType}  (campo é route_type, não mcp_type)

    Devolve (RouteMapCls, EnumCls, nome_do_campo_no_RouteMap) ou
    (None, None, None) se nenhuma variante for encontrada — nesse caso a
    exclusão de rotas é simplesmente desativada (degrada com segurança,
    em vez de quebrar a criação do servidor).
    """
    candidates = [
        ("fastmcp.server.providers.openapi", "MCPType", "mcp_type"),
        ("fastmcp.server.openapi", "MCPType", "mcp_type"),
        ("fastmcp.experimental.server.openapi", "MCPType", "mcp_type"),
        ("fastmcp", "MCPType", "mcp_type"),
        ("fastmcp", "RouteType", "route_type"),
    ]
    for module_name, type_attr, field_name in candidates:
        try:
            mod = importlib.import_module(module_name)
            route_map_cls = getattr(mod, "RouteMap")
            enum_cls = getattr(mod, type_attr)
            return route_map_cls, enum_cls, field_name
        except (ImportError, AttributeError):
            continue
    logger.warning(
        "Não foi possível localizar RouteMap/MCPType nesta versão do fastmcp "
        "instalada — a exclusão de rotas de auth (route_maps) será desativada; "
        "tools cruas de login podem aparecer duplicadas."
    )
    return None, None, None


_RouteMapCls, _RouteMapEnum, _ROUTE_MAP_TYPE_FIELD = _resolve_route_map_types()


# Candidatos de nome de campo para o login "genérico" (schema-based).
# A ordem só importa quando o schema tem mais de um candidato ao mesmo tempo;
# se só existir um campo no schema, é esse que entra, seja qual for a posição aqui.
LOGIN_IDENTIFIER_KEYS = [
    "email",
    "username",
    "user",
    "login",
    "identifier",
    "identity",
    "phone",
    "phone_number",
    "mobile",
    "msisdn",
    "telefone",
    "celular",
    "tel",
    "api_key",
    "apikey",
]
LOGIN_PASSWORD_KEYS = ["password", "senha", "pass", "pwd"]
LOGIN_OTP_CODE_KEYS = ["code", "otp", "otp_code", "verification_code", "pin", "token"]


class LoggedTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport, log_func=None, server_id=""):
        self.inner = inner
        self.log_func = log_func
        self.server_id = server_id

    def _truncate(self, data: bytes | None, max_len: int = 5000) -> str | None:
        if not data:
            return None
        try:
            text = data.decode("utf-8", errors="replace")
            if len(text) > max_len:
                text = text[:max_len] + f"\n... [truncated {len(text)} chars]"
            return text
        except Exception:
            return None

    async def handle_async_request(self, request):
        start = time.time()
        req_body = self._truncate(request.content)
        try:
            response = await self.inner.handle_async_request(request)
            duration = (time.time() - start) * 1000
            if self.log_func:
                resp_body = None
                try:
                    raw = await response.aread()
                    resp_body = self._truncate(raw)
                except Exception:
                    resp_body = None
                self.log_func(
                    self.server_id,
                    str(request.url),
                    response.status_code,
                    duration,
                    method=request.method,
                    request_body=req_body,
                    response_body=resp_body,
                )
            return response
        except Exception:
            duration = (time.time() - start) * 1000
            if self.log_func:
                self.log_func(
                    self.server_id, str(request.url), 0, duration, method=request.method, request_body=req_body
                )
            raise


class DynamicAuth(httpx.Auth):
    def __init__(self, manager):
        self.manager = manager

    def auth_flow(self, request):
        if self.manager.token:
            request.headers["Authorization"] = f"Bearer {self.manager.token}"
        yield request


class MCPServerManager:
    def __init__(
        self,
        spec_url: str,
        name: str,
        spec: dict | None = None,
        server_id: str = "",
        log_func=None,
        credentials: dict | None = None,
    ):
        self.spec_url = spec_url
        self.name = name
        self.server_id = server_id
        self.log_func = log_func
        self.token = None
        self.credentials = credentials or {}
        self.login_required_fields = []
        self.tool_map: dict[str, dict] = {}
        self.all_tools: list[dict] = []

        if spec is not None:
            self.spec = spec
        else:
            self.spec = self.load_and_convert_spec(spec_url)

        if self.spec.get("swagger") == "2.0":
            logger.info("Convertendo Swagger 2.0 to OpenAPI 3.0")
            self.spec = self._swagger2_to_openapi3(self.spec)

        parsed = urlparse(spec_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"

        if "servers" in self.spec and self.spec["servers"]:
            server_url = self.spec["servers"][0]["url"]
            if server_url.startswith("/"):
                self.base_url = f"{self.base_url}{server_url.rstrip('/')}"
            else:
                self.base_url = server_url.rstrip("/")

        logger.info(f"Base URL configurada: {self.base_url}")

        inner = httpx.AsyncHTTPTransport()
        transport = LoggedTransport(inner, log_func=log_func, server_id=server_id)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=DynamicAuth(self),
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )

        # Detetar paths de auth
        auth_paths = self._detect_auth_paths()
        self.email_login_path = auth_paths.get("email_login_path")

        # Construir tool_map das operacoes da spec (sem as de auth)
        exclude_paths = {
            p
            for p in [
                auth_paths["email_login_path"],
                auth_paths["otp_request_path"],
                auth_paths["otp_verify_path"],
                *auth_paths["oauth_paths"].values(),
            ]
            if p
        }
        self._build_tool_map(exclude_paths)

        self.mcp = FastMCP(name=self.name)

        # Index semantico das tools deste servidor
        self.tool_index = ToolIndex()
        self.tool_index.rebuild_if_changed(self.all_tools)

        self._register_search_tool()
        self._register_run_tool()

        # Detetar campos de login para auto-auth (sem registar tools set_token/session_status)
        _email_path = auth_paths.get("email_login_path")
        if _email_path:
            _schema = self._get_body_schema(_email_path)
            _id_key = self._match_schema_key(_schema, LOGIN_IDENTIFIER_KEYS)
            _pass_key = self._match_schema_key(_schema, LOGIN_PASSWORD_KEYS)
            self.login_required_fields = [k for k in (_id_key, _pass_key) if k]

    def _build_tool_map(self, exclude_paths: set[str]):
        paths = self.spec.get("paths", {})
        for path, methods in paths.items():
            for method, operation in methods.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                if path in exclude_paths:
                    continue
                raw_op_id = operation.get("operationId")
                if raw_op_id:
                    if "__" in raw_op_id:
                        op_id = raw_op_id.split("__")[0]
                    else:
                        op_id = raw_op_id
                else:
                    op_id = operation.get("summary", f"{method} {path}")
                op_id = op_id.replace("/", "_").replace("-", "_").replace(" ", "_").replace("{", "_").replace("}", "_")
                description = operation.get("description") or operation.get("summary", "Ferramenta MCP")
                parameters = operation.get("parameters", [])
                request_body = operation.get("requestBody", {})

                input_schema = {"type": "object", "properties": {}, "required": []}
                path_params = []
                for p in parameters:
                    pname = p.get("name", "param")
                    input_schema["properties"][pname] = p.get("schema", {"type": "string"})
                    if p.get("required", False):
                        input_schema["required"].append(pname)
                    if p.get("in") == "path":
                        path_params.append(pname)

                if request_body and "application/json" in (request_body.get("content") or {}):
                    body_schema = request_body["content"]["application/json"].get("schema", {})
                    for k, v in body_schema.get("properties", {}).items():
                        input_schema["properties"][k] = v
                    for r in body_schema.get("required", []):
                        if r not in input_schema["required"]:
                            input_schema["required"].append(r)

                entry = {
                    "name": op_id,
                    "description": description,
                    "input_schema": input_schema,
                    "parameters": input_schema,
                    "_method": method,
                    "_path": path,
                    "_path_params": path_params,
                    "_mcp_tool_name": op_id,
                    "_server_id": self.server_id,
                    "_tool_key": op_id,
                }
                self.all_tools.append(entry)
                self.tool_map[op_id] = entry

    def _register_search_tool(self):
        _index = self.tool_index

        @self.mcp.tool()
        async def search(query: str, top_k: int = 5) -> str:
            results = _index.search(query, top_k=top_k)
            return generate_stubs_from_tools(results)

    def _register_run_tool(self):
        _tool_map = self.tool_map
        _base_url = self.base_url
        _manager = self  # para aceder a token e DynamicAuth

        @self.mcp.tool()
        async def run(workflow: str) -> str:
            import asyncio

            sandbox = Sandbox(tool_map=_tool_map)

            def caller(tool_key: str, arguments: dict) -> Any:
                info = _tool_map.get(tool_key)
                if not info:
                    raise ValueError(f"Tool '{tool_key}' nao encontrada")
                method = info["_method"]
                path = info["_path"]
                for k, v in arguments.items():
                    path = path.replace("{" + k + "}", str(v))
                body = {k: v for k, v in arguments.items() if k not in info.get("_path_params", [])}

                # Auto-auth if no token but credentials exist
                if not _manager.token and _manager.credentials and _manager.email_login_path:
                    try:
                        with httpx.Client(base_url=_base_url) as auth_cli:
                            auth_resp = auth_cli.post(_manager.email_login_path, json=_manager.credentials)
                            if auth_resp.status_code in (200, 201):
                                data = auth_resp.json()
                                jwt = data.get("access_token") or data.get("token") or data.get("jwt")
                                if jwt:
                                    _manager.token = jwt
                    except Exception:
                        pass

                headers = {}
                if _manager.token:
                    headers["Authorization"] = f"Bearer {_manager.token}"
                with httpx.Client(base_url=_base_url, timeout=30.0) as cli:
                    resp = cli.request(method, path, json=body if body else None, headers=headers or None)
                text = resp.text
                try:
                    parsed = resp.json()
                    text = json.dumps(parsed, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                return [{"type": "text", "text": text}]

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, sandbox.execute, workflow, caller)
            import json as _json

            output_text = result.get("output", "")
            error_text = result.get("error", "")
            result_value = result.get("result")
            if error_text:
                return f"Erro: {error_text}\nOutput: {output_text}"
            if output_text and result_value is None:
                return f"Output:\n{output_text}\n\nResultado: null"
            return _json.dumps(result_value, indent=2, default=str)

    def load_and_convert_spec(self, url: str) -> dict:
        logger.info(f"Baixando spec de: {url}")
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        spec = response.json()

        # Converte se for Swagger 2.0
        if spec.get("swagger") == "2.0":
            logger.info("Convertendo Swagger 2.0 → OpenAPI 3.0")
            return self._swagger2_to_openapi3(spec)
        return spec

    def _swagger2_to_openapi3(self, spec: dict) -> dict:
        temp_input, temp_output = "_temp_s2.json", "_temp_o3.json"
        try:
            with open(temp_input, "w", encoding="utf-8") as f:
                json.dump(spec, f)
            shell_val = sys.platform == "win32"
            subprocess.run(
                ["npx", "swagger2openapi", temp_input, "-o", temp_output],
                check=True,
                shell=shell_val,
                capture_output=True,
            )
            with open(temp_output, "r", encoding="utf-8") as f:
                return json.load(f)
        finally:
            for f in [temp_input, temp_output]:
                if os.path.exists(f):
                    os.remove(f)

    def _resolve_schema_ref(self, schema: dict) -> dict:
        if not schema or "$ref" not in schema:
            return schema
        try:
            ref_path = schema["$ref"].lstrip("#/").split("/")
            current = self.spec
            for part in ref_path:
                current = current.get(part, {})
            return current
        except Exception:
            return {}

    def _get_body_schema(self, path: str) -> dict | None:
        methods = self.spec.get("paths", {}).get(path, {})
        if not methods:
            return None
        post = methods.get("post", {})
        content = post.get("requestBody", {}).get("content", {})
        for ct in ("application/json", "application/x-www-form-urlencoded"):
            schema = content.get(ct, {}).get("schema", {})
            if schema:
                return self._resolve_schema_ref(schema)
        return None

    @staticmethod
    def _match_schema_key(schema: dict | None, candidates: list[str]) -> str | None:
        """Dado o schema do body de um endpoint, devolve o nome real do campo
        (preservando o casing original) que corresponde a um dos candidatos.
        Ex: schema tem 'Phone_Number' e a lista inclui 'phone_number' -> devolve 'Phone_Number'.
        """
        if not schema:
            return None
        props = schema.get("properties", {})
        by_lower = {k.lower(): k for k in props}
        for cand in candidates:
            if cand in by_lower:
                return by_lower[cand]
        return None

    def _detect_auth_paths(self) -> dict:
        """Varre a spec e identifica quais paths (POST) são de login, OTP
        (pedir/verificar código) e OAuth. Chamado ANTES de criar o FastMCP,
        para que esses paths possam ser excluídos da conversão automática
        em tools "cruas" — já ficam cobertos pela tool `login` customizada.
        """
        email_login_path = None
        fallback_auth_path = None
        otp_request_path = None
        otp_verify_path = None
        oauth_paths: dict[str, str] = {}
        spec_paths = self.spec.get("paths", {})
        for path, methods in spec_paths.items():
            if "post" not in methods:
                continue
            lower = path.lower()
            if "register" in lower or "signup" in lower:
                continue

            looks_otp = any(k in lower for k in ("otp", "one-time", "2fa", "mfa"))
            looks_verify = "verify" in lower or "confirm" in lower
            looks_send = "send" in lower or "resend" in lower or "request" in lower

            if looks_otp or ("code" in lower and (looks_verify or looks_send)):
                if looks_verify and otp_verify_path is None:
                    otp_verify_path = path
                    continue
                if looks_send and otp_request_path is None:
                    otp_request_path = path
                    continue

            if "login" in lower or "signin" in lower or "sign-in" in lower:
                if email_login_path is None:
                    email_login_path = path
            elif any(k in lower for k in ["token", "auth/"]):
                if fallback_auth_path is None:
                    fallback_auth_path = path
        if email_login_path is None:
            email_login_path = fallback_auth_path
        for path, methods in spec_paths.items():
            if "post" not in methods:
                continue
            lower = path.lower()
            for provider in ("google", "github", "apple"):
                if provider in lower:
                    oauth_paths[provider] = path

        return {
            "email_login_path": email_login_path,
            "otp_request_path": otp_request_path,
            "otp_verify_path": otp_verify_path,
            "oauth_paths": oauth_paths,
        }


# ESTA FUNÇÃO PRECISA ESTAR FORA DA CLASSE (NA RAIZ DO ARQUIVO)
def create_mcp_server(spec_url: str, name: str) -> FastMCP:
    manager = MCPServerManager(spec_url, name)
    return manager.mcp


async def create_merged_mcp_server(
    base_spec_url: str,
    base_name: str,
    base_spec: dict,
    sources: list[dict],
    server_id: str = "",
    log_func=None,
) -> FastMCP:
    """Cria um servidor MCP merged: monta múltiplas sources no base com namespace."""
    from fastmcp.tools import Tool, ToolResult

    class RemoteProxyTool(Tool):
        remote_url: str
        remote_headers: dict | None = None
        remote_auth: str | None = None
        remote_tool_name: str

        async def run(self, arguments: dict[str, Any]) -> ToolResult:
            from fastmcp.client.transports import StreamableHttpTransport
            from fastmcp import Client

            t = StreamableHttpTransport(
                url=self.remote_url,
                headers=self.remote_headers,
                auth=self.remote_auth,
            )
            async with Client(t) as c:
                result = await c.call_tool(self.remote_tool_name, arguments, raise_on_error=False)
            return ToolResult(
                content=result.content,
                structured_content=result.structured_content,
            )

    base_manager = MCPServerManager(
        spec_url=base_spec_url,
        name=base_name,
        spec=base_spec,
        server_id=server_id,
        log_func=log_func,
    )

    for i, src in enumerate(sources):
        if src.get("remote_url"):
            remote_url = src["remote_url"]
            try:
                from fastmcp.client.transports import StreamableHttpTransport
                from fastmcp import Client

                remote_headers = dict(src.get("remote_headers") or {})
                auth = remote_headers.pop("Authorization", None)
                namespace = src.get("namespace", "")

                transport = StreamableHttpTransport(
                    url=remote_url,
                    headers=remote_headers or None,
                    auth=auth,
                )

                async with Client(transport) as remote_client:
                    remote_tools = await remote_client.list_tools()

                for tool_def in remote_tools:
                    tool_name = f"{namespace}_{tool_def.name}" if namespace else tool_def.name
                    proxy_tool = RemoteProxyTool(
                        name=tool_name,
                        description=tool_def.description or "",
                        parameters=tool_def.inputSchema,
                        remote_url=remote_url,
                        remote_headers=remote_headers or None,
                        remote_auth=auth,
                        remote_tool_name=tool_def.name,
                    )
                    base_manager.mcp.add_tool(proxy_tool)

            except Exception as e:
                logger.warning(f"Falha ao montar remoto {remote_url}: {e}")
        elif src.get("stdio_config"):
            try:
                from fastmcp.server import create_proxy

                stdio_cfg = src["stdio_config"]
                proxy = create_proxy(stdio_cfg, name=src.get("name", f"Stdio {i}"))
                base_manager.mcp.mount(proxy, namespace=src.get("namespace", ""))
            except Exception as e:
                logger.warning(f"Falha ao montar proxy stdio: {e}")
        else:
            src_manager = MCPServerManager(
                spec_url="",
                name=src.get("name", f"Source {i}"),
                spec=src["spec"],
                server_id=f"{server_id}_src{i}",
                log_func=log_func,
            )
            base_manager.mcp.mount(src_manager.mcp, namespace=src.get("namespace", ""))

    return base_manager.mcp
