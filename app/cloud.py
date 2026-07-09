import asyncio
import json
import os
import re
import secrets
import socket
import string
import sys
import threading
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse


import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

try:
    from .cloud_models import Base, LogDB, ServerDB, SessionLocal, engine, get_db, init_db
    from .config import (
        FREE_TIER_MAX_SERVERS,
        FREE_TIER_RPM,
        GATEWAY_HOST,
        GATEWAY_PORT,
        PRO_TIER_MAX_SERVERS,
        PRO_TIER_RPM,
        PUBLIC_URL,
    )
    from .openapi import MCPServerManager, create_mcp_server
    from .paypal import parse_webhook_event, verify_webhook_signature
    from .supabase_auth import (
        get_cached_profile,
        get_tier_limits,
        invalidate_profile_cache,
        require_auth,
        upsert_supabase_profile,
    )
    from .utils import logger
except ImportError:
    from cloud_models import Base, LogDB, ServerDB, SessionLocal, engine, get_db, init_db
    from config import (
        GATEWAY_HOST,
        GATEWAY_PORT,
        PUBLIC_URL,
    )
    from openapi import MCPServerManager
    from paypal import parse_webhook_event, verify_webhook_signature
    from supabase_auth import (
        get_cached_profile,
        get_tier_limits,
        invalidate_profile_cache,
        require_auth,
        upsert_supabase_profile,
    )
    from utils import logger


def _make_log_func(server_id: str):
    def log_func(sid: str, tool: str, status: int, duration: float, **kwargs):
        try:
            db = SessionLocal()
            log = LogDB(
                server_id=sid or server_id,
                tool_called=str(tool),
                method=kwargs.get("method"),
                status_code=status,
                duration_ms=duration,
                request_body=kwargs.get("request_body"),
                response_body=kwargs.get("response_body"),
            )
            db.add(log)
            db.commit()
            db.close()
        except Exception:
            pass

    return log_func


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _generate_id(prefix="srv", length=8):
    chars = string.ascii_lowercase + string.digits
    return f"{prefix}_{''.join(secrets.choice(chars) for _ in range(length))}"


def _generate_apikey():
    chars = string.ascii_lowercase + string.digits
    return f"r2m_live_{''.join(secrets.choice(chars) for _ in range(16))}"


def _validate_server(server_id: str, apikey: str, db: Session):
    server = (
        db.query(ServerDB)
        .filter(
            ServerDB.server_id == server_id,
            ServerDB.apikey == apikey,
        )
        .first()
    )
    if not server:
        return None
    return server


class ActiveServer:
    def __init__(self, server: ServerDB, transport: str = "sse"):
        self.server_id = server.server_id
        self.apikey = server.apikey
        self.name = server.name
        self.spec_url = server.spec_url
        self.spec_data = server.spec_data
        self.is_merged = server.is_merged
        self.merge_config = server.merge_config
        self._transport = transport
        self.manager: MCPServerManager | None = None
        self.port: int | None = None
        self.uv_server = None
        self.sse_app = None

    async def ensure_running(self, transport: str | None = None):
        if self.uv_server is not None and not self.uv_server.should_exit:
            return
        spec_data = json.loads(self.spec_data) if self.spec_data else None
        if self.is_merged and self.merge_config:
            # Restart sandbox bridge if it died (e.g. server restart)
            bridge_id = self.merge_config.get("_bridge_id")
            if bridge_id and bridge_id not in stdio_bridges:
                stdio_cfg = self.merge_config.get("_stdio_config")
                if not stdio_cfg:
                    import re as _re

                    src_list = self.merge_config.get("sources", [])
                    sn = src_list[0].get("source_name", "") if src_list else ""
                    m = _re.match(r"^Sandbox\s*\((.+)\)$", sn)
                    if m:
                        stdio_cfg = {"command": m.group(1).strip(), "args": []}
                if stdio_cfg:
                    try:
                        new_url = await _start_stdio_bridge(stdio_cfg, bridge_id)
                        logger.info(f"Bridge {bridge_id} restarted at {new_url}")
                    except Exception as e:
                        logger.error(f"Failed to restart bridge {bridge_id}: {e}")

            sources_raw = self.merge_config.get("sources", [])
            if not sources_raw:
                old_ss = (
                    json.loads(self.merge_config["source_spec_data"])
                    if isinstance(self.merge_config.get("source_spec_data"), str)
                    else self.merge_config.get("source_spec_data")
                )
                sources_raw = [
                    {
                        "source_name": self.merge_config.get("source_name", "Source"),
                        "namespace": self.merge_config.get("namespace", ""),
                        "source_spec_data": old_ss,
                    }
                ]
            sources = []
            bridge_info = stdio_bridges.get(bridge_id) if bridge_id else None
            for s in sources_raw:
                if s.get("remote_url"):
                    runtime_url = bridge_info["url"] if bridge_info else s["remote_url"]
                    src_entry = {
                        "name": s.get("source_name", "Remote Source"),
                        "namespace": s.get("namespace", ""),
                        "remote_url": runtime_url,
                    }
                    if s.get("tools"):
                        src_entry["tools"] = s["tools"]
                    if s.get("remote_headers"):
                        src_entry["remote_headers"] = s["remote_headers"]
                    sources.append(src_entry)
                else:
                    ss = (
                        json.loads(s["source_spec_data"])
                        if isinstance(s.get("source_spec_data"), str)
                        else s.get("source_spec_data")
                    )
                    sources.append(
                        {"name": s.get("source_name", "Source"), "namespace": s.get("namespace", ""), "spec": ss}
                    )
            try:
                from .openapi import create_merged_mcp_server
            except ImportError:
                from openapi import create_merged_mcp_server

            merged_mcp = create_merged_mcp_server(
                base_spec_url=self.spec_url,
                base_name=self.name,
                base_spec=spec_data,
                sources=sources,
                server_id=self.server_id,
                log_func=_make_log_func(self.server_id),
            )
            self.manager = getattr(merged_mcp, "_manager", None)
            self.sse_app = merged_mcp.http_app(transport=transport or self._transport)
        else:
            self.manager = MCPServerManager(
                spec_url=self.spec_url,
                name=self.name,
                spec=spec_data,
                server_id=self.server_id,
                log_func=_make_log_func(self.server_id),
            )
            transport_type = transport or self._transport
            self.sse_app = self.manager.mcp.http_app(transport=transport_type)
        self.port = _find_free_port()

        config = uvicorn.Config(
            app=self.sse_app,
            host="127.0.0.1",
            port=self.port,
            log_level="error",
            timeout_keep_alive=0,
        )
        self.uv_server = uvicorn.Server(config)

        def _run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.uv_server.serve())

        t = threading.Thread(target=_run_server, daemon=True)
        t.start()

        deadline = time.time() + 10
        while time.time() < deadline:
            if getattr(self.uv_server, "started", False):
                import socket as _socket

                try:
                    s = _socket.create_connection(("127.0.0.1", self.port), timeout=1)
                    s.close()
                    break
                except (ConnectionRefusedError, OSError):
                    await asyncio.sleep(0.2)
                    continue
            await asyncio.sleep(0.1)
        logger.info(f"MCP server {self.server_id} rodando em 127.0.0.1:{self.port}")

    async def stop(self):
        if self.uv_server:
            self.uv_server.should_exit = True
            self.uv_server = None
        self.sse_app = None


active_servers: dict[str, ActiveServer] = {}

stdio_bridges: dict[str, dict] = {}

direct_inspectors: dict[str, dict] = {}

sse_sessions: dict[str, list[asyncio.Event]] = {}


async def _start_stdio_bridge(stdio_config: dict, bridge_id: str) -> str:
    """Start a stdio MCP bridge and return its SSE URL.

    Creates a subprocess from stdio_config (command/args/env), wraps it
    with FastMCP, and serves it via SSE on a local port.
    """
    from fastmcp.server import create_proxy

    if "mcpServers" not in stdio_config:
        cmd_name = os.path.basename(stdio_config.get("command", "sandbox"))
        server_entry = {
            "command": stdio_config["command"],
            "args": stdio_config.get("args", []),
        }
        if stdio_config.get("env"):
            server_entry["env"] = stdio_config["env"]
        if stdio_config.get("tools"):
            server_entry["tools"] = stdio_config["tools"]
        stdio_config = {"mcpServers": {cmd_name: server_entry}}

    port = _find_free_port()

    proxy = create_proxy(stdio_config)
    app = proxy.http_app(transport="sse")

    uv_config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    uv_server = uvicorn.Server(uv_config)

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(uv_server.serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        if getattr(uv_server, "started", False):
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=1)
                s.close()
                break
            except (ConnectionRefusedError, OSError):
                pass
        await asyncio.sleep(0.2)

    url = f"http://127.0.0.1:{port}/sse"
    stdio_bridges[bridge_id] = {
        "server": uv_server,
        "port": port,
        "thread": t,
        "url": url,
        "stdio_config": stdio_config,
    }
    logger.info(f"Stdio bridge {bridge_id} started on {url}")
    return url


def _stop_stdio_bridge(bridge_id: str):
    bridge = stdio_bridges.pop(bridge_id, None)
    if not bridge:
        return
    bridge["server"].should_exit = True
    insp_proc = bridge.get("inspector_proc")
    if insp_proc:
        try:
            insp_proc.kill()
        except Exception:
            pass
    logger.info(f"Stdio bridge {bridge_id} stopped")


def _stop_direct_inspector(server_id: str):
    entry = direct_inspectors.pop(server_id, None)
    if not entry:
        return
    proc = entry.get("proc")
    if proc:
        try:
            proc.kill()
        except Exception:
            pass
    logger.info(f"Direct inspector {server_id} stopped")


async def _start_inspector_for_server(server_id: str, url: str, transport: str = "http") -> str:
    _stop_direct_inspector(server_id)

    client_port = _find_free_port()
    server_port = _find_free_port()

    env = os.environ.copy()
    env["CLIENT_PORT"] = str(client_port)
    env["SERVER_PORT"] = str(server_port)
    env["DANGEROUSLY_OMIT_AUTH"] = "true"

    transport_type = "http" if transport in ("http", "streamable-http") else "sse"

    logger.info(
        f"Lançando inspector: npx @modelcontextprotocol/inspector --server-url {url} --transport {transport_type}"
    )

    try:
        import subprocess

        if sys.platform == "win32":
            cmd = [
                "cmd.exe",
                "/c",
                "npx.cmd",
                "-y",
                "@modelcontextprotocol/inspector",
                "--server-url",
                url,
                "--transport",
                transport_type,
            ]
        else:
            cmd = [
                "npx",
                "-y",
                "@modelcontextprotocol/inspector",
                "--server-url",
                url,
                "--transport",
                transport_type,
            ]

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        cmd_str = "npx.cmd" if sys.platform == "win32" else "npx"
        raise RuntimeError(f"Comando {cmd_str} não encontrado. Verifique se Node.js está instalado e no PATH.")
    except Exception as exc:
        raise RuntimeError(f"Falha ao lançar inspector: {type(exc).__name__}: {exc}") from exc

    direct_inspectors[server_id] = {"proc": proc, "url": url, "client_port": client_port, "server_port": server_port}

    proxy_url = f"{PUBLIC_URL}/v1/inspector/{server_id}"

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            s = socket.create_connection(("localhost", client_port), timeout=1)
            s.close()
            logger.info(f"Inspector {server_id} pronto em {proxy_url} (localhost:{client_port})")
            return proxy_url
        except Exception:
            await asyncio.sleep(0.5)

    logger.warning(f"Inspector {server_id} started but port {client_port} not ready yet")
    return proxy_url


async def _start_mcp_inspector(bridge_id: str) -> str:
    bridge = stdio_bridges.get(bridge_id)
    if not bridge:
        raise ValueError(f"Bridge {bridge_id} not found")

    insp_proc = bridge.get("inspector_proc")
    if insp_proc:
        try:
            insp_proc.kill()
        except Exception:
            pass

    client_port = _find_free_port()
    server_port = _find_free_port()

    env = os.environ.copy()
    env["CLIENT_PORT"] = str(client_port)
    env["SERVER_PORT"] = str(server_port)
    env["DANGEROUSLY_OMIT_AUTH"] = "true"

    bridge_url = bridge.get("url", "")

    logger.info(
        f"Lançando inspector (bridge): npx @modelcontextprotocol/inspector --server-url {bridge_url} --transport sse"
    )

    try:
        import subprocess

        if sys.platform == "win32":
            cmd = [
                "cmd.exe",
                "/c",
                "npx.cmd",
                "-y",
                "@modelcontextprotocol/inspector",
                "--server-url",
                bridge_url,
                "--transport",
                "sse",
            ]
        else:
            cmd = [
                "npx",
                "-y",
                "@modelcontextprotocol/inspector",
                "--server-url",
                bridge_url,
                "--transport",
                "sse",
            ]

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        cmd_str = "npx.cmd" if sys.platform == "win32" else "npx"
        raise RuntimeError(f"Comando {cmd_str} não encontrado. Verifique se Node.js está instalado e no PATH.")
    except Exception as exc:
        raise RuntimeError(f"Falha ao lançar inspector: {type(exc).__name__}: {exc}") from exc

    bridge["inspector_proc"] = proc
    bridge["client_port"] = client_port
    bridge["server_port"] = server_port

    proxy_url = f"{PUBLIC_URL}/v1/inspector/{bridge_id}"

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            s = socket.create_connection(("localhost", client_port), timeout=1)
            s.close()
            logger.info(f"MCP Inspector {bridge_id} pronto em {proxy_url} (localhost:{client_port})")
            return proxy_url
        except Exception:
            await asyncio.sleep(0.5)

    logger.warning(f"MCP Inspector {bridge_id} started but port {client_port} not ready yet")
    return proxy_url


def register_sse_session(user_id: str) -> asyncio.Event:
    exit_event = asyncio.Event()
    sse_sessions.setdefault(user_id, []).append(exit_event)
    return exit_event


def unregister_sse_session(user_id: str, event: asyncio.Event):
    if user_id in sse_sessions:
        sse_sessions[user_id] = [e for e in sse_sessions[user_id] if e is not event]


async def notify_session_termination(user_id: str):
    events = sse_sessions.get(user_id, [])
    for event in events:
        event.set()


async def cascade_guard(server_id: str, apikey: str, db: Session) -> ServerDB | None:
    server = _validate_server(server_id, apikey, db)
    if not server:
        return None
    if not server.is_active:
        return None
    user_id = server.user_id
    if not user_id:
        return server
    try:
        profile = await get_cached_profile(user_id)
    except Exception:
        return server
    if profile.get("status") != "active":
        return None
    limits = get_tier_limits(profile.get("plan_tier", "free"))
    active_count = db.query(ServerDB).filter(ServerDB.user_id == user_id, ServerDB.is_active == True).count()
    if profile.get("plan_tier") == "free" and active_count > limits["max_servers"]:
        return None
    return server


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Cloud Gateway iniciado com banco de dados SQLite")
    yield
    for key in list(active_servers.keys()):
        await active_servers[key].stop()
    active_servers.clear()


app = FastAPI(
    title="rest2mcp Cloud Gateway",
    description="API de Gestão e Gateway de Conexão para servidores MCP persistentes na nuvem",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Schemas ───────────────────────────────────────────────────────────────────


class CreateServerRequest(BaseModel):
    name: str
    spec_url: str
    transport: str = "sse"


class ServerResponse(BaseModel):
    server_id: str
    apikey: str
    name: str
    status: str
    spec_url: str
    transport: str
    url_sse: str
    created_at: str


class ServerListItem(BaseModel):
    server_id: str
    name: str
    status: str
    url_sse: str
    transport: str
    created_at: str
    is_merged: bool = False
    merge_info: str | None = None


class MergeServerRequest(BaseModel):
    source_server_id: str
    target_server_id: str | None = None
    remote_url: str | None = None
    remote_transport: str = "http"
    remote_headers: dict[str, str] | None = None
    remote_tools: dict | None = None
    stdio_config: dict | None = None
    namespace: str
    merged_name: str


class UpdateServerRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    transport: str | None = None


class ProfileResponse(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    status: str
    plan_tier: str
    servers_count: int = 0
    servers_limit: int = 1


class LogEntry(BaseModel):
    id: int
    timestamp: str
    tool_called: str
    method: str | None = None
    status_code: int
    duration_ms: float
    request_body: str | None = None
    response_body: str | None = None


# ─── Management API ────────────────────────────────────────────────────────────


@app.post("/v1/servers", status_code=201)
async def create_server(req: CreateServerRequest, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    logger.info(f"Criando servidor: {req.name} ({req.spec_url}) para user {user_id}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(req.spec_url)
            response.raise_for_status()
            spec_data = response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar spec: {e}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Spec não é um JSON válido")

    if spec_data.get("swagger") == "2.0":
        logger.info("Convertendo Swagger 2.0 → OpenAPI 3.0")
        try:
            temp = MCPServerManager(spec_url=req.spec_url, name=req.name)
            spec_data = temp.spec
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao converter Swagger 2.0: {e}")

    profile = await get_cached_profile(user_id)
    plan_tier = profile.get("plan_tier", "free")
    limits = get_tier_limits(plan_tier)
    current_count = db.query(ServerDB).filter(ServerDB.user_id == user_id).count()
    if current_count >= limits["max_servers"]:
        raise HTTPException(
            status_code=402 if plan_tier == "free" else 429,
            detail=f"Limite de {limits['max_servers']} servidores atingido para o plano {plan_tier}. Faça upgrade para Pro.",
        )

    server_id = _generate_id()
    apikey = _generate_apikey()

    parsed_url = urlparse(req.spec_url)
    target_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    if "servers" in spec_data and spec_data["servers"]:
        first = spec_data["servers"][0]["url"]
        if first.startswith("/"):
            target_url = target_url + first.rstrip("/")
        else:
            target_url = first.rstrip("/")

    transport = req.transport if hasattr(req, "transport") and req.transport in ("sse", "http") else "sse"

    record = ServerDB(
        server_id=server_id,
        apikey=apikey,
        name=req.name,
        spec_url=req.spec_url,
        spec_data=json.dumps(spec_data),
        target_url=target_url,
        transport=transport,
        is_active=True,
        user_id=user_id,
    )
    db.add(record)
    db.commit()

    suffix = "sse" if transport == "sse" else "mcp"
    url_sse = f"{PUBLIC_URL}/v1/{server_id}/{apikey}/{suffix}"
    logger.info(f"Servidor criado: {server_id} ({transport}) -> {url_sse} para user {user_id}")

    return ServerResponse(
        server_id=server_id,
        apikey=apikey,
        name=req.name,
        status="active",
        spec_url=req.spec_url,
        transport=transport,
        url_sse=url_sse,
        created_at=record.created_at.isoformat(),
    )


@app.get("/v1/servers")
async def list_servers(request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    servers = db.query(ServerDB).filter(ServerDB.user_id == user_id).order_by(desc(ServerDB.created_at)).all()
    result = []
    for s in servers:
        t = s.transport or "http"
        suffix = "sse" if t == "sse" else "mcp"
        url = f"{PUBLIC_URL}/v1/{s.server_id}/{s.apikey}/{suffix}"
        merge_info = None
        if s.is_merged and s.merge_config:
            src_list = s.merge_config.get("sources", [])
            if not src_list and s.merge_config.get("namespace"):
                src_list = [{"namespace": s.merge_config.get("namespace", "?")}]
            if src_list:
                labels = [f"{src.get('namespace', '?')}" for src in src_list]
                merge_info = f"Merged: {', '.join(labels)}"
            else:
                merge_info = "Merged"
        result.append(
            ServerListItem(
                server_id=s.server_id,
                name=s.name,
                status="active" if s.is_active else "inactive",
                transport=t,
                url_sse=url,
                created_at=s.created_at.isoformat(),
                is_merged=bool(s.is_merged),
                merge_info=merge_info,
            )
        )
    return result


def _create_merged_server(
    db: Session,
    user_id: str,
    name: str,
    sources: list[dict],
    target_spec_url: str,
    target_spec_data: dict | str,
    target_transport: str,
    target_target_url: str | None,
    target_server_id: str,
    target_name: str,
) -> ServerDB:
    server_id = _generate_id()
    apikey = _generate_apikey()
    merge_config = {
        "sources": sources,
        "target_server_id": target_server_id,
        "target_name": target_name,
    }
    t = target_transport or "http"
    record = ServerDB(
        server_id=server_id,
        apikey=apikey,
        name=name,
        spec_url=target_spec_url,
        spec_data=target_spec_data,
        target_url=target_target_url,
        transport=t,
        is_active=True,
        is_merged=True,
        merge_config=merge_config,
        user_id=user_id,
    )
    db.add(record)
    return record


@app.post("/v1/servers/merge", status_code=201)
async def merge_servers(req: MergeServerRequest, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id

    source = db.query(ServerDB).filter(ServerDB.server_id == req.source_server_id, ServerDB.user_id == user_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Servidor fonte não encontrado")
    if source.is_merged:
        raise HTTPException(status_code=400, detail="Não é possível usar um servidor merged como fonte")

    # ── REMOTE MERGE: merge local server with remote MCP URL ──────────
    if req.remote_url:
        if not req.remote_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL remota inválida. Deve começar com http:// ou https://")
        if not source.spec_data:
            raise HTTPException(status_code=400, detail="Servidor fonte precisa ter spec_data carregada")

        logger.info(f"Remote merge: {req.source_server_id} + remote {req.remote_url} for user {user_id}")

        try:
            from fastmcp.client.transports import StreamableHttpTransport

            validate_headers = dict(req.remote_headers or {})
            auth_val = validate_headers.pop("Authorization", None)
            transport = StreamableHttpTransport(
                url=req.remote_url,
                headers=validate_headers or None,
                auth=auth_val,
            )
            from fastmcp import Client

            async with Client(transport) as remote_client:
                tools = await remote_client.list_tools()
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "403" in err_msg or "Unauthorized" in err_msg or "Forbidden" in err_msg:
                raise HTTPException(
                    status_code=400,
                    detail=f"O servidor remoto rejeitou a conexão. {err_msg[:300]}. Informe um token Authorization no campo opcional.",
                )
            elif "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                pass
            else:
                logger.warning(f"Falha ao testar conexão MCP remota {req.remote_url}: {e}")

        sources = [
            {
                "namespace": req.namespace,
                "remote_url": req.remote_url,
                "remote_transport": req.remote_transport,
                "remote_headers": req.remote_headers,
                "source_name": f"Remote ({req.remote_url})",
                "source_server_id": "",
                "source_spec_data": None,
                "source_spec_url": "",
            }
        ]
        if req.remote_tools:
            sources[0]["tools"] = req.remote_tools

        record = _create_merged_server(
            db=db,
            user_id=user_id,
            name=req.merged_name,
            sources=sources,
            target_spec_url=source.spec_url,
            target_spec_data=source.spec_data,
            target_transport=source.transport,
            target_target_url=source.target_url,
            target_server_id=source.server_id,
            target_name=source.name,
        )

        db.delete(source)
        db.commit()

        suffix = "sse" if record.transport == "sse" else "mcp"
        url_sse = f"{PUBLIC_URL}/v1/{record.server_id}/{record.apikey}/{suffix}"
        logger.info(f"Servidor merged (remote) criado: {record.server_id} -> {url_sse}")

        return ServerResponse(
            server_id=record.server_id,
            apikey=record.apikey,
            name=record.name,
            status="active",
            spec_url=record.spec_url,
            transport=record.transport,
            url_sse=url_sse,
            created_at=record.created_at.isoformat(),
        )

    # ── STDIO MERGE: merge local server with sandbox stdio MCP ──────
    if req.stdio_config:
        if not source.spec_data:
            raise HTTPException(status_code=400, detail="Servidor fonte precisa ter spec_data carregada")
        if "command" not in req.stdio_config:
            raise HTTPException(status_code=400, detail="stdio_config precisa de 'command'")

        logger.info(f"Stdio merge: {req.source_server_id} + stdio_config={req.stdio_config} for user {user_id}")

        bridge_id = _generate_id(prefix="bridge", length=12)
        try:
            bridge_url = await _start_stdio_bridge(req.stdio_config, bridge_id)
        except Exception as e:
            logger.error(f"Falha ao iniciar bridge stdio: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao iniciar servidor sandbox: {e}")

        cmd_name = os.path.basename(req.stdio_config.get("command", "sandbox"))
        sources = [
            {
                "namespace": req.namespace,
                "remote_url": bridge_url,
                "remote_transport": "sse",
                "source_name": f"Sandbox ({cmd_name})",
                "source_server_id": "",
                "source_spec_data": None,
                "source_spec_url": "",
            }
        ]

        record = _create_merged_server(
            db=db,
            user_id=user_id,
            name=req.merged_name,
            sources=sources,
            target_spec_url=source.spec_url,
            target_spec_data=source.spec_data,
            target_transport=source.transport,
            target_target_url=source.target_url,
            target_server_id=source.server_id,
            target_name=source.name,
        )

        record.merge_config["_bridge_id"] = bridge_id
        record.merge_config["_stdio_config"] = req.stdio_config
        db.add(record)
        db.delete(source)
        db.commit()

        suffix = "sse" if record.transport == "sse" else "mcp"
        url_sse = f"{PUBLIC_URL}/v1/{record.server_id}/{record.apikey}/{suffix}"
        logger.info(f"Servidor merged (stdio) criado: {record.server_id} -> {url_sse}")

        return ServerResponse(
            server_id=record.server_id,
            apikey=record.apikey,
            name=record.name,
            status="active",
            spec_url=record.spec_url,
            transport=record.transport,
            url_sse=url_sse,
            created_at=record.created_at.isoformat(),
        )

    # ── LOCAL MERGE: merge two existing servers ──────────────────────
    if not req.target_server_id and not req.remote_url:
        raise HTTPException(status_code=400, detail="Informe target_server_id, remote_url ou stdio_config")

    logger.info(f"Merging servers: {req.source_server_id} -> {req.target_server_id} for user {user_id}")

    target = db.query(ServerDB).filter(ServerDB.server_id == req.target_server_id, ServerDB.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Servidor alvo não encontrado")

    if not source.spec_data or not target.spec_data:
        raise HTTPException(status_code=400, detail="Ambos servidores precisam ter spec_data carregada")

    new_source_entry = {
        "namespace": req.namespace,
        "source_server_id": req.source_server_id,
        "source_name": source.name,
        "source_spec_data": source.spec_data,
        "source_spec_url": source.spec_url,
    }

    if target.is_merged and target.merge_config:
        existing_sources = target.merge_config.get("sources", [])
        existing_sources.append(new_source_entry)
        sources = existing_sources
        base_spec_url = target.spec_url
        base_spec_data = target.spec_data
        base_transport = target.transport
        base_target_url = target.target_url
    else:
        sources = [new_source_entry]
        base_spec_url = target.spec_url
        base_spec_data = target.spec_data
        base_transport = target.transport
        base_target_url = target.target_url

    record = _create_merged_server(
        db=db,
        user_id=user_id,
        name=req.merged_name,
        sources=sources,
        target_spec_url=base_spec_url,
        target_spec_data=base_spec_data,
        target_transport=base_transport,
        target_target_url=base_target_url,
        target_server_id=target.server_id,
        target_name=target.name,
    )

    db.delete(source)
    db.delete(target)
    db.commit()

    suffix = "sse" if record.transport == "sse" else "mcp"
    url_sse = f"{PUBLIC_URL}/v1/{record.server_id}/{record.apikey}/{suffix}"
    logger.info(f"Servidor merged criado: {record.server_id} ({len(sources)} fontes) -> {url_sse}")

    return ServerResponse(
        server_id=record.server_id,
        apikey=record.apikey,
        name=record.name,
        status="active",
        spec_url=record.spec_url,
        transport=record.transport,
        url_sse=url_sse,
        created_at=record.created_at.isoformat(),
    )


@app.post("/v1/servers/{server_id}/unmerge")
async def unmerge_server(server_id: str, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    record = db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    if not record.is_merged:
        raise HTTPException(status_code=400, detail="Servidor não é merged")

    bridge_id = (record.merge_config or {}).get("_bridge_id")
    if bridge_id:
        _stop_stdio_bridge(bridge_id)
    mc = record.merge_config or {}
    sources = mc.get("sources", [])
    if not sources:
        sources = [
            {
                "source_server_id": mc.get("source_server_id", ""),
                "source_name": mc.get("source_name", "Restaurado"),
                "source_spec_data": mc.get("source_spec_data"),
                "source_spec_url": mc.get("source_spec_url", ""),
                "namespace": mc.get("namespace", ""),
            }
        ]
        mc["target_name"] = mc.get("target_name", record.name)

    restored = []
    for s in sources:
        if s.get("remote_url"):
            continue
        restored.append(
            ServerDB(
                server_id=s.get("source_server_id", _generate_id()),
                apikey=_generate_apikey(),
                name=s.get("source_name", "Restaurado"),
                spec_url=s.get("source_spec_url", ""),
                spec_data=s.get("source_spec_data"),
                target_url="",
                transport="http",
                is_active=True,
                is_merged=False,
                merge_config=None,
                user_id=user_id,
            )
        )

    target_name = mc.get("target_name", "Restaurado")
    restored.append(
        ServerDB(
            server_id=mc.get("target_server_id", _generate_id()),
            apikey=_generate_apikey(),
            name=target_name,
            spec_url=record.spec_url,
            spec_data=record.spec_data,
            target_url=record.target_url,
            transport=record.transport,
            is_active=True,
            is_merged=False,
            merge_config=None,
            user_id=user_id,
        )
    )

    for r in restored:
        db.add(r)
    db.delete(record)
    db.commit()

    logger.info(f"Unmerge {server_id}: {len(sources)} source(s) + target restaurados para user {user_id}")
    return {"ok": True, "restored": len(restored)}


@app.patch("/v1/servers/{server_id}")
async def update_server(server_id: str, req: UpdateServerRequest, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    record = db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    if req.name is not None:
        record.name = req.name
    if req.status is not None:
        if req.status not in ("active", "inactive"):
            raise HTTPException(status_code=422, detail="status deve ser 'active' ou 'inactive'")
        record.is_active = req.status == "active"
        if not record.is_active:
            key = f"{record.server_id}:{record.apikey}"
            if key in active_servers:
                await active_servers[key].stop()
                del active_servers[key]
    if req.transport is not None:
        if req.transport not in ("sse", "http"):
            raise HTTPException(status_code=422, detail="transport deve ser 'sse' ou 'http'")
        record.transport = req.transport
        key = f"{record.server_id}:{record.apikey}"
        if key in active_servers:
            await active_servers[key].stop()
            del active_servers[key]

    db.commit()

    t = record.transport or "http"
    suffix = "sse" if t == "sse" else "mcp"
    url = f"{PUBLIC_URL}/v1/{record.server_id}/{record.apikey}/{suffix}"
    return ServerListItem(
        server_id=record.server_id,
        name=record.name,
        status="active" if record.is_active else "inactive",
        transport=t,
        url_sse=url,
        created_at=record.created_at.isoformat(),
    )


@app.get("/v1/servers/{server_id}/health")
async def check_server_health(server_id: str, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    record = db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == user_id).first()
    if not record:
        return {"status": "error", "detail": "Servidor não encontrado"}

    url = record.spec_url
    if not url:
        return {"status": "error", "detail": "Servidor sem spec URL"}

    async with httpx.AsyncClient(follow_redirects=True) as hc:
        resp = await hc.get(url, headers={"User-Agent": "rest2mcp/1.0"})
        if resp.is_success:
            return {"status": "ok"}
        return {"status": "error", "detail": f"HTTP {resp.status_code}"}


@app.post("/v1/servers/{server_id}/inspector")
async def start_server_inspector(server_id: str, request: Request, db: Session = Depends(get_db)):
    """Start the MCP Inspector for any server (sandbox or regular)."""
    await require_auth(request)
    user_id = request.state.user_id
    record = db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    # Sandbox/merged server flow (stdio-based sandbox only)
    if record.is_merged and record.merge_config:
        bridge_id = record.merge_config.get("_bridge_id")
        if bridge_id:
            if bridge_id not in stdio_bridges:
                stdio_cfg = record.merge_config.get("_stdio_config")
                if not stdio_cfg:
                    sources = record.merge_config.get("sources", [])
                    src_name = sources[0].get("source_name", "") if sources else ""
                    m = re.match(r"^Sandbox\s*\((.+)\)$", src_name)
                    if m:
                        cmd = m.group(1).strip()
                        stdio_cfg = {"command": cmd, "args": []}
                        logger.info(f"Reconstructed stdio_cfg for bridge {bridge_id}: {cmd}")
                    else:
                        raise HTTPException(status_code=400, detail="Configuração sandbox perdida. Recrie o merge.")
                try:
                    await _start_stdio_bridge(stdio_cfg, bridge_id)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Falha ao reiniciar sandbox: {e}")

            try:
                inspector_url = await _start_mcp_inspector(bridge_id)
                return {"inspector_url": inspector_url}
            except Exception as e:
                logger.error(f"Falha ao iniciar inspector para {bridge_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Falha ao iniciar inspector: {e}")

    # Regular server flow — start a direct inspector with server URL pre-configured
    suffix = "mcp" if record.transport == "http" else "sse"
    server_url = f"http://127.0.0.1:{GATEWAY_PORT}/v1/{record.server_id}/{record.apikey}/{suffix}"
    logger.info(f"Starting direct inspector for {server_id} -> {server_url}")

    try:
        inspector_url = await _start_inspector_for_server(record.server_id, server_url, record.transport)
        return {"inspector_url": inspector_url}
    except Exception as e:
        logger.error(f"Falha ao iniciar inspector para {server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar inspector: {e}")


@app.api_route("/v1/inspector-api/{inspector_id}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route(
    "/v1/inspector-api/{inspector_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def inspector_api_proxy(inspector_id: str, request: Request, path: str = ""):
    entry = direct_inspectors.get(inspector_id) or stdio_bridges.get(inspector_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Inspector não encontrado ou expirou")

    server_port = entry.get("server_port") or entry.get("client_port")
    if not server_port:
        raise HTTPException(status_code=404, detail="Inspector port não disponível")

    target_path = path or ""
    target_url = f"http://localhost:{server_port}/{target_path}"
    query = request.url.query
    if query:
        target_url += f"?{query}"

    excluded_headers = {"host", "content-length", "transfer-encoding", "connection", "upgrade"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items() if k.lower() not in excluded_headers},
                content=await request.body(),
                follow_redirects=True,
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers},
                media_type=resp.headers.get("content-type"),
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Inspector backend não está respondendo")
    except Exception as exc:
        logger.error(f"Erro no proxy do inspector-api {inspector_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Erro no proxy: {exc}")


@app.api_route("/v1/inspector/{inspector_id}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route(
    "/v1/inspector/{inspector_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def inspector_proxy(inspector_id: str, request: Request, path: str = ""):
    entry = direct_inspectors.get(inspector_id) or stdio_bridges.get(inspector_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Inspector não encontrado ou expirou")

    client_port = entry.get("client_port")
    if not client_port:
        raise HTTPException(status_code=404, detail="Inspector port não disponível")

    server_port = entry.get("server_port")

    target_path = path or ""
    target_url = f"http://localhost:{client_port}/{target_path}"
    query = request.url.query
    if query:
        target_url += f"?{query}"

    excluded_headers = {"host", "content-length", "transfer-encoding", "connection", "upgrade"}
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded_headers}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=await request.body(),
                follow_redirects=True,
            )
            content = resp.content
            ct = (resp.headers.get("content-type") or "").lower()

            if resp.status_code == 200 and (
                "text/html" in ct
                or "text/javascript" in ct
                or "application/javascript" in ct
                or "application/x-javascript" in ct
            ):
                prefix = f"/v1/inspector/{inspector_id}"
                api_prefix = f"/v1/inspector-api/{inspector_id}"
                origin = str(request.base_url).rstrip("/")
                text = content.decode("utf-8")
                text = re.sub(r'(src|href|action)=([\'"])/', rf"\1=\2{prefix}/", text)
                text = re.sub(r'(url\([\'"]?)/', rf"\1{prefix}/", text)
                text = re.sub(r'(fetch\([\'"])/', rf"\1{prefix}/", text)
                if server_port:
                    text = re.sub(rf"{origin}:{server_port}", rf"{origin}{api_prefix}", text)
                    text = re.sub(rf"rest2mcp\.fly\.dev:{server_port}", rf"rest2mcp.fly.dev{api_prefix}", text)
                content = text.encode("utf-8")

            return Response(
                content=content,
                status_code=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers},
                media_type=resp.headers.get("content-type"),
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Inspector não está respondendo")
    except Exception as exc:
        logger.error(f"Erro no proxy do inspector {inspector_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Erro no proxy: {exc}")


@app.delete("/v1/servers/{server_id}", status_code=204)
async def delete_server(server_id: str, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    record = db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    _stop_direct_inspector(server_id)

    bridge_id = (record.merge_config or {}).get("_bridge_id")
    if bridge_id:
        _stop_stdio_bridge(bridge_id)

    key = f"{record.server_id}:{record.apikey}"
    if key in active_servers:
        await active_servers[key].stop()
        del active_servers[key]

    db.delete(record)
    db.commit()


# ─── Logs Endpoint ─────────────────────────────────────────────────────────────


def _log_to_entry(log: LogDB) -> LogEntry:
    return LogEntry(
        id=log.id,
        timestamp=log.timestamp.isoformat(),
        tool_called=log.tool_called,
        method=log.method,
        status_code=log.status_code,
        duration_ms=log.duration_ms,
        request_body=log.request_body,
        response_body=log.response_body,
    )


@app.get("/v1/servers/{server_id}/logs")
async def get_logs(
    server_id: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    status_min: int | None = None,
    status_max: int | None = None,
    tool: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
):
    await require_auth(request)
    server = (
        db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == request.state.user_id).first()
    )
    if not server:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    filters = [LogDB.server_id == server_id]
    if status_min is not None:
        filters.append(LogDB.status_code >= status_min)
    if status_max is not None:
        filters.append(LogDB.status_code <= status_max)
    if tool:
        filters.append(LogDB.tool_called.ilike(f"%{tool}%"))
    if from_date:
        filters.append(LogDB.timestamp >= from_date)
    if to_date:
        filters.append(LogDB.timestamp <= to_date)

    logs = db.query(LogDB).filter(and_(*filters)).order_by(desc(LogDB.timestamp)).offset(offset).limit(limit).all()

    return [_log_to_entry(log) for log in logs]


@app.get("/v1/servers/{server_id}/logs/export")
async def export_logs(
    server_id: str,
    request: Request,
    format: str = "json",
    status_min: int | None = None,
    status_max: int | None = None,
    tool: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
):
    await require_auth(request)
    server = (
        db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == request.state.user_id).first()
    )
    if not server:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    filters = [LogDB.server_id == server_id]
    if status_min is not None:
        filters.append(LogDB.status_code >= status_min)
    if status_max is not None:
        filters.append(LogDB.status_code <= status_max)
    if tool:
        filters.append(LogDB.tool_called.ilike(f"%{tool}%"))
    if from_date:
        filters.append(LogDB.timestamp >= from_date)
    if to_date:
        filters.append(LogDB.timestamp <= to_date)

    logs = db.query(LogDB).filter(and_(*filters)).order_by(desc(LogDB.timestamp)).all()
    data = [_log_to_entry(log).model_dump() for log in logs]

    if format == "csv":
        import csv
        import io

        output = io.StringIO()
        if data:
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=logs_{server_id}.csv"},
        )

    return JSONResponse(content=data, headers={"Content-Disposition": f"attachment; filename=logs_{server_id}.json"})


@app.get("/v1/servers/{server_id}/logs/{log_id}")
async def get_log_detail(server_id: str, log_id: int, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    server = (
        db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == request.state.user_id).first()
    )
    if not server:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    log = db.query(LogDB).filter(LogDB.id == log_id, LogDB.server_id == server_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    return _log_to_entry(log)


@app.delete("/v1/servers/{server_id}/logs", status_code=204)
async def clear_logs(server_id: str, request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    server = (
        db.query(ServerDB).filter(ServerDB.server_id == server_id, ServerDB.user_id == request.state.user_id).first()
    )
    if not server:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    db.query(LogDB).filter(LogDB.server_id == server_id).delete()
    db.commit()


# ─── Gateway SSE / MCP Routes ─────────────────────────────────────────────────


@app.api_route("/v1/{server_id}/{apikey}/sse", methods=["GET", "POST"])
async def sse_connection(server_id: str, apikey: str, request: Request):
    if request.method == "POST":
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Este endpoint usa SSE (Server-Sent Events), não Streamable HTTP. Use /mcp para Streamable HTTP."
            },
        )
    db = SessionLocal()
    try:
        server = await cascade_guard(server_id, apikey, db)
        if not server:
            return Response(status_code=403, content="Acesso negado: servidor inativo, suspenso ou limite excedido")
    finally:
        db.close()

    user_id = server.user_id or ""

    key = f"{server_id}:{apikey}"
    if key not in active_servers:
        active_servers[key] = ActiveServer(server)

    active = active_servers[key]
    await active.ensure_running(transport="sse")

    internal_sse_url = f"http://127.0.0.1:{active.port}/sse"

    async def event_stream():
        exit_event = register_sse_session(user_id) if user_id else None
        last_error = None
        try:
            for attempt in range(15):
                try:
                    async with httpx.AsyncClient(timeout=None) as client:
                        async with client.stream("GET", internal_sse_url) as resp:
                            if resp.status_code != 200:
                                yield f"event: error\ndata: Internal server error ({resp.status_code})\n\n"
                                return
                            async for line in resp.aiter_lines():
                                if exit_event and exit_event.is_set():
                                    yield "event: error\ndata: Sessão terminada\n\n"
                                    return
                                if line.startswith("data: /messages"):
                                    query = line.split("?", 1)[1].rstrip() if "?" in line else ""
                                    sep = "?" if query else ""
                                    yield f"data: /v1/{server_id}/{apikey}/messages{sep}{query}\n"
                                else:
                                    yield line + "\n"
                            return
                except httpx.ConnectError as e:
                    last_error = f"ConnectError: {e}"
                    logger.warning(f"SSE proxy ConnectError (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(0.5)
                    continue
                except httpx.ReadTimeout as e:
                    logger.error(f"SSE proxy ReadTimeout (attempt {attempt + 1}): {e}")
                    yield f"event: error\ndata: ReadTimeout: {e}\n\n"
                    return
                except httpx.RemoteProtocolError as e:
                    logger.error(f"SSE proxy RemoteProtocolError (attempt {attempt + 1}): {e}")
                    yield f"event: error\ndata: RemoteProtocolError: {e}\n\n"
                    return
                except httpx.TransportError as e:
                    logger.error(f"SSE proxy TransportError (attempt {attempt + 1}): {e}")
                    yield f"event: error\ndata: TransportError: {e}\n\n"
                    return
            yield f"event: error\ndata: Failed to connect: {last_error}\n\n"
        finally:
            if exit_event:
                unregister_sse_session(user_id, exit_event)
            logger.info(f"Cliente SSE desconectado: {server_id}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/v1/{server_id}/{apikey}/messages")
async def messages_endpoint(server_id: str, apikey: str, request: Request):
    db = SessionLocal()
    try:
        server = await cascade_guard(server_id, apikey, db)
        if not server:
            return Response(status_code=403, content="Acesso negado")
    finally:
        db.close()

    key = f"{server_id}:{apikey}"
    if key not in active_servers:
        active_servers[key] = ActiveServer(server)

    active = active_servers[key]
    await active.ensure_running(transport="sse")

    if not active.uv_server or active.uv_server.should_exit:
        return Response(status_code=503, content="Servidor MCP não está rodando")

    body = await request.body()
    ct = request.headers.get("content-type", "application/json")
    query = request.scope.get("query_string", b"").decode()

    url = f"http://127.0.0.1:{active.port}/messages/"
    if query:
        url += "?" + query

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.post(
            url,
            content=body,
            headers={"content-type": ct},
        )

    resp_headers = {}
    for h in ("content-type", "mcp-session-id"):
        val = resp.headers.get(h)
        if val:
            resp_headers[h] = val

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp_headers or None,
    )


async def _get_or_start_mcp(server_id: str, apikey: str):
    key = f"{server_id}:{apikey}"
    db = SessionLocal()
    try:
        server = await cascade_guard(server_id, apikey, db)
        if not server:
            return None, Response(status_code=403, content="Acesso negado")
    finally:
        db.close()

    if key not in active_servers:
        active_servers[key] = ActiveServer(server)

    active = active_servers[key]
    await active.ensure_running(transport="http")
    return active, None


@app.post("/v1/{server_id}/{apikey}/mcp")
async def mcp_endpoint(server_id: str, apikey: str, request: Request):
    active, err = await _get_or_start_mcp(server_id, apikey)
    if err:
        return err

    body = await request.body()
    sess = request.headers.get("Mcp-Session-Id", "")
    query = request.scope.get("query_string", b"").decode()

    url = f"http://127.0.0.1:{active.port}/mcp"
    if query:
        url += "?" + query

    headers = {
        "content-type": request.headers.get("content-type", "application/json"),
        "accept": request.headers.get("accept", "application/json, text/event-stream"),
    }
    if sess:
        headers["Mcp-Session-Id"] = sess

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.post(url, content=body, headers=headers)

    resp_headers = {}
    for h in ("content-type", "mcp-session-id"):
        val = resp.headers.get(h)
        if val:
            resp_headers[h] = val

    return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)


@app.get("/v1/{server_id}/{apikey}/mcp")
async def mcp_get_stream(server_id: str, apikey: str, request: Request):
    active, err = await _get_or_start_mcp(server_id, apikey)
    if err:
        return err

    query = request.scope.get("query_string", b"").decode()
    url = f"http://127.0.0.1:{active.port}/mcp"
    if query:
        url += "?" + query

    headers = {
        "accept": request.headers.get("accept", "text/event-stream"),
    }
    sess = request.headers.get("Mcp-Session-Id", "")
    if sess:
        headers["Mcp-Session-Id"] = sess

    async def proxy_stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(proxy_stream(), media_type="text/event-stream")


# ─── Health Check ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "active_servers": len(active_servers)}


# ─── MCP Server Store ──────────────────────────────────────────────────────────

# Cache for raw registry entries to support package resolution
_registry_servers_cache: dict[str, dict] = {}


@app.get("/v1/store/servers")
async def list_store_servers(cursor: str = ""):
    try:
        async with httpx.AsyncClient() as client:
            params: dict = {"version": "latest", "limit": 50}
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(
                "https://registry.modelcontextprotocol.io/v0.1/servers",
                params=params,
                headers={"User-Agent": "rest2mcp/1.0"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            registry_servers = data.get("servers", [])
            metadata = data.get("metadata", {})

            servers = []
            for entry in registry_servers:
                s = entry.get("server", {})
                meta = entry.get("_meta", {}) or {}
                official = meta.get("io.modelcontextprotocol.registry/official", {})

                if official.get("status") == "deprecated":
                    continue
                if not official.get("isLatest", False):
                    continue

                name = s.get("name", "")
                title = s.get("title") or name
                description = s.get("description", "")

                namespace, slug = "", ""
                if "/" in name:
                    parts = name.split("/", 1)
                    namespace = parts[0]
                    slug = parts[1]

                packages = s.get("packages") or []
                remotes = s.get("remotes") or []

                npm_pkg = next((p for p in packages if p.get("registryType") == "npm"), None)
                pypi_pkg = next((p for p in packages if p.get("registryType") == "pypi"), None)

                if npm_pkg:
                    pkg_id = npm_pkg["identifier"]
                    if "/" in pkg_id and pkg_id.startswith("@"):
                        pkg_ns = pkg_id.split("/")[0].lstrip("@")
                        pkg_slug = pkg_id.split("/")[1]
                    elif "/" in pkg_id:
                        pkg_ns = pkg_id.split("/")[0]
                        pkg_slug = pkg_id.split("/")[1]
                    else:
                        pkg_ns = ""
                        pkg_slug = pkg_id
                elif pypi_pkg:
                    pkg_ns = ""
                    pkg_slug = pypi_pkg["identifier"]
                else:
                    pkg_ns = ""
                    pkg_slug = ""

                has_remotes = bool(remotes)
                has_packages = bool(packages)
                attributes = []
                if has_remotes and has_packages:
                    attributes.append("hosting:hybrid")
                elif has_remotes:
                    attributes.append("hosting:remote-capable")
                elif has_packages:
                    attributes.append("hosting:local-only")

                mapped_server = {
                    "id": name,
                    "name": title,
                    "displayName": title,
                    "description": description,
                    "namespace": pkg_ns,
                    "slug": pkg_slug,
                    "version": s.get("version", ""),
                    "repository": s.get("repository") or {},
                    "websiteUrl": s.get("websiteUrl", ""),
                    "attributes": attributes,
                    "categories": [],
                    "tools": [],
                    "useCount": 0,
                }

                env_schema = _extract_env_schema(s)
                if env_schema:
                    mapped_server["environmentVariablesJsonSchema"] = env_schema

                servers.append(mapped_server)
                _registry_servers_cache[name] = entry
                for pkg in packages:
                    pkg_id = pkg.get("identifier")
                    if pkg_id and pkg_id not in _registry_servers_cache:
                        _registry_servers_cache[pkg_id] = entry

            if not cursor:
                await _enrich_servers_with_stars(servers)

            facets = _compute_store_facets(servers)

            next_cursor = metadata.get("nextCursor", "")

            result = {
                "servers": servers,
                "facets": facets,
                "pageInfo": {
                    "hasNextPage": bool(next_cursor),
                    "endCursor": next_cursor or "",
                },
            }
            return result
    except Exception as e:
        logger.warning("Store fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Falha ao carregar servidores da loja")


@app.get("/v1/store/check-package")
async def check_store_package(name: str = "", namespace: str = "", slug: str = "", repo_url: str = ""):
    pkg_target = name if name else f"{namespace}/{slug}".strip("/")

    result = _resolve_package_command(pkg_target)
    if result:
        return result

    if pkg_target.startswith("@"):
        return {"exists": True, "name": pkg_target, "command": "npx", "args": ["-y", pkg_target], "alternatives": []}

    return {
        "exists": True,
        "name": pkg_target,
        "command": "npx",
        "args": ["-y", pkg_target],
        "alternatives": [{"command": "uvx", "args": [pkg_target]}],
    }


def _extract_env_schema(server_data: dict) -> dict | None:
    all_vars: list[dict] = []

    for pkg in server_data.get("packages") or []:
        for ev in pkg.get("environmentVariables") or []:
            all_vars.append(ev)

    for remote in server_data.get("remotes") or []:
        for header in remote.get("headers") or []:
            all_vars.append(header)

    if not all_vars:
        return None

    properties = {}
    required = []
    seen = set()
    for ev in all_vars:
        name = ev.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        prop: dict = {"type": "string"}
        desc = ev.get("description", "")
        if desc:
            prop["description"] = desc
            hint = desc.split(".")[0].split(":")[0].split("(")[0].strip()
            if hint and len(hint) < 60:
                prop["placeholder"] = hint
        if ev.get("default"):
            prop["default"] = ev["default"]
        properties[name] = prop
        if ev.get("isRequired"):
            required.append(name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _resolve_package_command(pkg_target: str) -> dict | None:
    entry = _registry_servers_cache.get(pkg_target)
    if entry:
        srv = entry.get("server", {})
        packages = srv.get("packages") or []
        remotes = srv.get("remotes") or []

        npm_pkg = next((p for p in packages if p.get("registryType") == "npm"), None)
        pypi_pkg = next((p for p in packages if p.get("registryType") == "pypi"), None)

        if npm_pkg:
            pkg_id = npm_pkg["identifier"]
            hint = npm_pkg.get("runtimeHint")
            if hint:
                return {"exists": True, "name": pkg_target, "command": hint, "args": ["-y", pkg_id], "alternatives": []}
            return {"exists": True, "name": pkg_target, "command": "npx", "args": ["-y", pkg_id], "alternatives": []}
        if pypi_pkg:
            pkg_id = pypi_pkg["identifier"]
            return {"exists": True, "name": pkg_target, "command": "uvx", "args": [pkg_id], "alternatives": []}
        if remotes and not packages:
            return {
                "exists": False,
                "name": pkg_target,
                "command": "",
                "args": [],
                "alternatives": [],
                "remote_urls": [r.get("url", "") for r in remotes if r.get("url")],
            }

    return None


_star_cache: dict = {}
_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def _fetch_star_sync(owner: str, name: str) -> int:
    headers = {"User-Agent": "rest2mcp/1.0"}
    if _GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {_GITHUB_TOKEN}"
    try:
        resp = httpx.get(
            f"https://api.github.com/repos/{owner}/{name}",
            headers=headers,
            timeout=5,
        )
        if resp.status_code == 403:
            return -1
        if resp.status_code == 200:
            return resp.json().get("stargazers_count", 0)
    except Exception:
        pass
    return 0


async def _enrich_servers_with_stars(servers: list):
    batch = []
    loop = asyncio.get_event_loop()

    for s in servers:
        repo = s.get("repository", {})
        url = (repo.get("url") or "") if isinstance(repo, dict) else ""
        if "github.com" not in url:
            s["stars"] = 0
            continue
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            s["stars"] = 0
            continue
        owner, name = parts[-2], parts[-1]
        key = f"{owner}/{name}"
        if key in _star_cache:
            s["stars"] = _star_cache[key]
        else:
            batch.append((s, key, owner, name))

    if not batch:
        return

    sem = asyncio.Semaphore(5)
    rate_limited = False

    async def fetch_one(s, key, owner, name):
        nonlocal rate_limited
        if rate_limited:
            s["stars"] = 0
            return
        async with sem:
            stars = await loop.run_in_executor(None, _fetch_star_sync, owner, name)
            if stars == -1:
                rate_limited = True
                s["stars"] = 0
                return
            _star_cache[key] = stars
            s["stars"] = stars

    await asyncio.gather(*[fetch_one(s, k, o, n) for s, k, o, n in batch], return_exceptions=True)


_STORE_CATEGORIES: list[dict] = [
    {
        "id": "developer-tools",
        "name": "Developer Tools",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [r"\bdeveloper tools?\b", r"\bsdk\b", r"\bapi client\b", r"\bide\b", r"\bdev tool"]
        ],
    },
    {
        "id": "search",
        "name": "Search",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bsearch\b",
                r"\belasticsearch\b",
                r"\bmeilisearch\b",
                r"\balgolia\b",
                r"\btypesense\b",
                r"\bsolr\b",
                r"\bsplunk\b",
                r"\bfull.?text\b",
            ]
        ],
    },
    {
        "id": "app-automation",
        "name": "App Automation",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bapp automation\b",
                r"\bworkflow automation\b",
                r"\bzapier\b",
                r"\bn8n\b",
                r"\bmake\.com\b",
                r"\bintegromat\b",
            ]
        ],
    },
    {
        "id": "autonomous-agents",
        "name": "Autonomous Agents",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [r"\bautonomous agents?\b", r"\bai agents?\b", r"\bautonomous\b", r"\bmulti.?agent\b"]
        ],
    },
    {
        "id": "databases",
        "name": "Databases",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bdatabase[s]?\b",
                r"\bsql\b",
                r"\bquery\b",
                r"\bpostgres\b",
                r"\bpostgresql\b",
                r"\bmysql\b",
                r"\bmongodb\b",
                r"\bmongo\b",
                r"\bredis\b",
                r"\bdynamodb\b",
                r"\bcouchdb\b",
                r"\bmariadb\b",
                r"\bsqlite\b",
                r"\bsupabase\b",
                r"\bfirebase\b",
                r"\bprisma\b",
                r"\borm\b",
                r"\bknex\b",
                r"\bsequelize\b",
            ]
        ],
    },
    {
        "id": "finance",
        "name": "Finance",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bfinance\b",
                r"\bfinancial\b",
                r"\bstock\b",
                r"\bcurrency\b",
                r"\bexchange rate\b",
                r"\binvoice\b",
                r"\baccounting\b",
                r"\bportfolio\b",
                r"\binvesting\b",
                r"\bticker\b",
                r"\bstripe\b",
                r"\bpayment gateway\b",
                r"\bledger\b",
            ]
        ],
    },
    {
        "id": "rag-systems",
        "name": "RAG Systems",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\brag\b",
                r"\bretrieval.augmented\b",
                r"\bdocument qa\b",
                r"\bknowledge base\b",
                r"\bquestion answering\b",
                r"\bcontext retrieval\b",
            ]
        ],
    },
    {
        "id": "research-data",
        "name": "Research & Data",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bresearch\b",
                r"\bdata analysis\b",
                r"\bdata science\b",
                r"\bdataset\b",
                r"\bstatistics\b",
                r"\bstatistical\b",
                r"\bscientific\b",
                r"\bscholar\b",
                r"\bpublication\b",
                r"\bcitation\b",
            ]
        ],
    },
    {
        "id": "knowledge-memory",
        "name": "Knowledge & Memory",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bknowledge\b",
                r"\bmemory\b",
                r"\bknowledge graph\b",
                r"\bknowledge base\b",
                r"\bvector store\b",
                r"\bembeddings\b",
                r"\bsemantic\b",
                r"\blong.?term memory\b",
            ]
        ],
    },
    {
        "id": "agent-orchestration",
        "name": "Agent Orchestration",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bagent orchestration\b",
                r"\borchestrator\b",
                r"\bmulti.?agent\b",
                r"\bagent coordination\b",
                r"\bagent workflow\b",
                r"\bagent pipeline\b",
                r"\bagent routing\b",
            ]
        ],
    },
    {
        "id": "ai-ml",
        "name": "AI & Machine Learning",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bai\b",
                r"\bmachine learning\b",
                r"\bml\b",
                r"\bdeep learning\b",
                r"\bllm\b",
                r"\bgpt\b",
                r"\bchatgpt\b",
                r"\bopenai\b",
                r"\bclaude\b",
                r"\banthropic\b",
                r"\bgemini\b",
                r"\bmistral\b",
                r"\bllama\b",
                r"\bneural\b",
                r"\binference\b",
                r"\bpytorch\b",
                r"\btensorflow\b",
                r"\bhuggingface\b",
                r"\btransformers?\b",
                r"\bnatural language\b",
                r"\bnlp\b",
                r"\bclassification\b",
                r"\bregression\b",
                r"\btraining\b",
            ]
        ],
    },
    {
        "id": "web-scraping",
        "name": "Web Scraping",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bweb scrape\b",
                r"\bscraper\b",
                r"\bscraping\b",
                r"\bcrawler\b",
                r"\bspider\b",
                r"\bhtml parse\b",
                r"\bextract\b",
                r"\bbeautifulsoup\b",
                r"\bpuppeteer\b",
                r"\bplaywright\b",
                r"\bcheerio\b",
                r"\bxpath\b",
            ]
        ],
    },
    {
        "id": "security",
        "name": "Security",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bsecurity\b",
                r"\bcybersecurity\b",
                r"\bvulnerability\b",
                r"\bscanning\b",
                r"\bauthentication\b",
                r"\bauthorization\b",
                r"\boauth\b",
                r"\bjwt\b",
                r"\btoken\b",
                r"\bencryption\b",
                r"\bdecryption\b",
                r"\bhash\b",
                r"\bcipher\b",
                r"\bssl\b",
                r"\btls\b",
                r"\bfirewall\b",
                r"\baudit\b",
                r"\bcompliance\b",
                r"\bpenetration\b",
            ]
        ],
    },
    {
        "id": "cloud-platforms",
        "name": "Cloud Platforms",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcloud\b",
                r"\baws\b",
                r"\bamazon web services\b",
                r"\bazure\b",
                r"\bgoogle cloud\b",
                r"\bgcp\b",
                r"\bcloudflare\b",
                r"\bheroku\b",
                r"\bdigitalocean\b",
                r"\bserverless\b",
                r"\blambda\b",
                r"\bec2\b",
                r"\bs3\b",
                r"\bcloud compute\b",
                r"\bcloud storage\b",
            ]
        ],
    },
    {
        "id": "communication",
        "name": "Communication",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcommunication\b",
                r"\bmessaging\b",
                r"\bchat\b",
                r"\bslack\b",
                r"\bdiscord\b",
                r"\btelegram\b",
                r"\bwhatsapp\b",
                r"\bsms\b",
                r"\bmms\b",
                r"\bnotification\b",
                r"\bpush notification\b",
                r"\bwebhook\b",
                r"\breal.?time\b",
                r"\bpub.?sub\b",
                r"\bmessage queue\b",
            ]
        ],
    },
    {
        "id": "documentation",
        "name": "Documentation Access",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bdocumentation\b",
                r"\bdocs\b",
                r"\bwiki\b",
                r"\bknowledge base\b",
                r"\bmanual\b",
                r"\breference\b",
                r"\bapi docs\b",
                r"\bswagger\b",
                r"\bopenapi\b",
            ]
        ],
    },
    {
        "id": "open-data",
        "name": "Open Data",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [r"\bopen data\b", r"\bpublic data\b", r"\bpublic api\b", r"\bdata\.gov\b", r"\bopen government\b"]
        ],
    },
    {
        "id": "code-execution",
        "name": "Code Execution",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcode execution\b",
                r"\bsandbox\b",
                r"\bcode runner\b",
                r"\beval\b",
                r"\binterpreter\b",
                r"\bcompiler\b",
                r"\bruntime\b",
                r"\bcontainer\b",
                r"\bdocker\b",
                r"\brun code\b",
                r"\bfunction as a service\b",
                r"\bfaas\b",
            ]
        ],
    },
    {
        "id": "project-management",
        "name": "Project Management",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bproject management\b",
                r"\bjira\b",
                r"\basana\b",
                r"\btrello\b",
                r"\bnotion\b",
                r"\blinar\b",
                r"\btask\b",
                r"\bsprint\b",
                r"\bbacklog\b",
                r"\bissue tracking\b",
                r"\bissue tracker\b",
                r"\bkanban\b",
                r"\bscrum\b",
            ]
        ],
    },
    {
        "id": "browser-automation",
        "name": "Browser Automation",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bbrowser automation\b",
                r"\bheadless\b",
                r"\bselenium\b",
                r"\bpuppeteer\b",
                r"\bplaywright\b",
                r"\bwebdriver\b",
                r"\bchromium\b",
                r"\bfirefox\b",
            ]
        ],
    },
    {
        "id": "monitoring",
        "name": "Monitoring",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bmonitoring\b",
                r"\bmonitor\b",
                r"\balerting\b",
                r"\balert\b",
                r"\bmetrics\b",
                r"\btelemetry\b",
                r"\buptime\b",
                r"\bobservability\b",
                r"\blogging\b",
                r"\blogs\b",
                r"\bgrafana\b",
                r"\bprometheus\b",
                r"\bdatadog\b",
                r"\bsentry\b",
                r"\bnew relic\b",
                r"\bapm\b",
            ]
        ],
    },
    {
        "id": "blockchain",
        "name": "Blockchain",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bblockchain\b",
                r"\bsmart contract\b",
                r"\bethereum\b",
                r"\bsolana\b",
                r"\bnft\b",
                r"\bdefi\b",
                r"\bdecentralized\b",
                r"\bdapp\b",
                r"\bsolidity\b",
                r"\bbitcoin\b",
                r"\bwallet\b",
                r"\bdistributed ledger\b",
            ]
        ],
    },
    {
        "id": "code-analysis",
        "name": "Code Analysis",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcode analysis\b",
                r"\bstatic analysis\b",
                r"\blinter\b",
                r"\blint\b",
                r"\bcode quality\b",
                r"\bcode review\b",
                r"\bcode style\b",
                r"\btype checking\b",
                r"\btype checker\b",
                r"\beslint\b",
                r"\bprettier\b",
                r"\bsonarqube\b",
            ]
        ],
    },
    {
        "id": "government-data",
        "name": "Government Data",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bgovernment\b",
                r"\bpublic sector\b",
                r"\bcensus\b",
                r"\blegislation\b",
                r"\bregulation\b",
                r"\bfederal\b",
                r"\bcity data\b",
            ]
        ],
    },
    {
        "id": "marketing",
        "name": "Marketing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bmarketing\b",
                r"\bemail marketing\b",
                r"\bseo\b",
                r"\bsem\b",
                r"\bppc\b",
                r"\bcampaign\b",
                r"\blead\b",
                r"\bmailchimp\b",
                r"\bhubspot\b",
                r"\bmarketo\b",
                r"\ba.?b test\b",
            ]
        ],
    },
    {
        "id": "workplace-productivity",
        "name": "Workplace & Productivity",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bproductivity\b",
                r"\bspreadsheet\b",
                r"\bexcel\b",
                r"\bgoogle sheets\b",
                r"\bdocument\b",
                r"\bslide\b",
                r"\bpresentation\b",
                r"\bnote\b",
                r"\bcalendar\b",
                r"\btodo\b",
                r"\btask management\b",
                r"\btimesheet\b",
                r"\bcollaboration\b",
                r"\bworkspace\b",
            ]
        ],
    },
    {
        "id": "file-systems",
        "name": "File Systems",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bfile system\b",
                r"\bfilesystem\b",
                r"\bdirectory\b",
                r"\bfolder\b",
                r"\bdrive\b",
                r"\bnas\b",
                r"\bsamba\b",
                r"\bnfs\b",
                r"\bfile transfer\b",
                r"\bftp\b",
                r"\bsftp\b",
                r"\bpath\b",
            ]
        ],
    },
    {
        "id": "cms",
        "name": "Content Management Systems",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcms\b",
                r"\bwordpress\b",
                r"\bdrupal\b",
                r"\bjoomla\b",
                r"\bcontentful\b",
                r"\bheadless cms\b",
                r"\bwebflow\b",
                r"\bsanity\b",
                r"\bcontent management\b",
            ]
        ],
    },
    {
        "id": "ecommerce",
        "name": "E-commerce & Retail",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\becommerce\b",
                r"\be.?commerce\b",
                r"\bshopify\b",
                r"\bwoocommerce\b",
                r"\bmagento\b",
                r"\bbigcommerce\b",
                r"\bretail\b",
                r"\bmerchant\b",
                r"\border management\b",
                r"\binventory\b",
                r"\bcheckout\b",
                r"\bcart\b",
            ]
        ],
    },
    {
        "id": "image-video",
        "name": "Image & Video Processing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bimage\b",
                r"\bvideo\b",
                r"\bthumbnail\b",
                r"\bresize\b",
                r"\bcompress\b",
                r"\bconvert\b",
                r"\bocr\b",
                r"\boptical character\b",
                r"\bface detection\b",
                r"\bobject detection\b",
                r"\bimage recognition\b",
                r"\bffmpeg\b",
                r"\bopencv\b",
            ]
        ],
    },
    {
        "id": "testing-qa",
        "name": "Testing & QA Tools",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\btesting\b",
                r"\bqa\b",
                r"\bquality assurance\b",
                r"\btest automation\b",
                r"\bunit test\b",
                r"\bintegration test\b",
                r"\be2e\b",
                r"\bend to end\b",
                r"\bjest\b",
                r"\bpytest\b",
                r"\bselenium\b",
                r"\bcypress\b",
                r"\btest case\b",
                r"\btest coverage\b",
                r"\bregression\b",
            ]
        ],
    },
    {
        "id": "cryptocurrency",
        "name": "Cryptocurrency",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcryptocurrency\b",
                r"\bcrypto\b",
                r"\bbitcoin\b",
                r"\baltcoin\b",
                r"\btrading\b",
                r"\bexchange\b",
                r"\bwallet\b",
                r"\bcoin\b",
                r"\bmarket data\b",
            ]
        ],
    },
    {
        "id": "multimedia",
        "name": "Multimedia Processing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bmultimedia\b",
                r"\baudio\b",
                r"\bvideo\b",
                r"\bmedia\b",
                r"\bmp3\b",
                r"\bmp4\b",
                r"\bstreaming\b",
                r"\btranscod\w+\b",
                r"\bencod\w+\b",
                r"\bdecod\w+\b",
            ]
        ],
    },
    {
        "id": "note-taking",
        "name": "Note Taking",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bnote\b",
                r"\bnotes\b",
                r"\bnotebook\b",
                r"\bjournal\b",
                r"\bobsidian\b",
                r"\broam\b",
                r"\blogseq\b",
                r"\bevernote\b",
                r"\bnotion\b",
                r"\bmarkdown\b",
                r"\bnote taking\b",
            ]
        ],
    },
    {
        "id": "entertainment-media",
        "name": "Entertainment & Media",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bentertainment\b",
                r"\bmovie\b",
                r"\btv\b",
                r"\bshow\b",
                r"\bmusic\b",
                r"\bpodcast\b",
                r"\bgaming\b",
                r"\bnews\b",
            ]
        ],
    },
    {
        "id": "web3",
        "name": "Web3 & Decentralized Tech",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bweb3\b",
                r"\bweb 3\b",
                r"\bdecentralized\b",
                r"\bdapp\b",
                r"\bmetamask\b",
                r"\bipfs\b",
                r"\bdefi\b",
            ]
        ],
    },
    {
        "id": "version-control",
        "name": "Version Control",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bversion control\b",
                r"\bgit\b",
                r"\bgithub\b",
                r"\bgitlab\b",
                r"\bbitbucket\b",
                r"\brepository\b",
                r"\brepo\b",
                r"\bcommit\b",
                r"\bpull request\b",
                r"\bmerge\b",
                r"\bbranch\b",
                r"\bvcs\b",
                r"\bsource control\b",
            ]
        ],
    },
    {
        "id": "data-platforms",
        "name": "Data Platforms",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bdata platform\b",
                r"\bdata warehouse\b",
                r"\bdata lake\b",
                r"\bbig data\b",
                r"\betl\b",
                r"\belt\b",
                r"\bdata pipeline\b",
                r"\bdata integration\b",
                r"\bsnowflake\b",
                r"\bdatabricks\b",
                r"\bapache spark\b",
                r"\bspark\b",
                r"\bkafka\b",
                r"\bairflow\b",
                r"\bdbt\b",
                r"\bdata catalog\b",
            ]
        ],
    },
    {
        "id": "social-media",
        "name": "Social Media",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bsocial media\b",
                r"\btwitter\b",
                r"\bx\.com\b",
                r"\blinkedin\b",
                r"\bfacebook\b",
                r"\binstagram\b",
                r"\btiktok\b",
                r"\breddit\b",
                r"\bpinterest\b",
                r"\bsocial network\b",
                r"\btweet\b",
                r"\bfollower\b",
                r"\bhashtag\b",
            ]
        ],
    },
    {
        "id": "command-line",
        "name": "Command Line",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcommand line\b",
                r"\bcli\b",
                r"\bterminal\b",
                r"\bshell\b",
                r"\bconsole\b",
                r"\bbash\b",
                r"\bzsh\b",
                r"\bpowershell\b",
                r"\bstdin\b",
                r"\bstdout\b",
                r"\bstderr\b",
                r"\bsubprocess\b",
            ]
        ],
    },
    {
        "id": "location-services",
        "name": "Location Services",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\blocation\b",
                r"\bgeolocation\b",
                r"\bgeocode\b",
                r"\bgeo\b",
                r"\bmap\b",
                r"\bgps\b",
                r"\bcoordinates\b",
                r"\blatitude\b",
                r"\blongitude\b",
                r"\baddress\b",
                r"\bplace\b",
                r"\bgoogle maps\b",
                r"\bopenstreetmap\b",
            ]
        ],
    },
    {
        "id": "os-automation",
        "name": "OS Automation",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bos automation\b",
                r"\boperating system\b",
                r"\bdesktop automation\b",
                r"\bkeyboard\b",
                r"\bmouse\b",
                r"\bwindow\b",
                r"\bprocess\b",
                r"\btask\b",
                r"\bregistry\b",
            ]
        ],
    },
    {
        "id": "observability",
        "name": "Observability",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bobservability\b",
                r"\bmonitoring\b",
                r"\blogging\b",
                r"\btracing\b",
                r"\bmetrics\b",
                r"\btelemetry\b",
                r"\bapm\b",
                r"\bdistributed tracing\b",
                r"\bopentelemetry\b",
                r"\bjaeger\b",
                r"\bzipkin\b",
                r"\bgrafana\b",
                r"\bprometheus\b",
            ]
        ],
    },
    {
        "id": "shell-access",
        "name": "Shell Access",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bshell access\b",
                r"\bssh\b",
                r"\bremote access\b",
                r"\bterminal\b",
                r"\bcommand execution\b",
                r"\bremote command\b",
                r"\bssh connection\b",
            ]
        ],
    },
    {
        "id": "api-testing",
        "name": "API Testing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bapi testing\b",
                r"\brest testing\b",
                r"\bpostman\b",
                r"\binsomnia\b",
                r"\bapi test\b",
                r"\bapi client\b",
                r"\bhttp client\b",
                r"\bcurl\b",
                r"\bgraphql testing\b",
            ]
        ],
    },
    {
        "id": "legal-compliance",
        "name": "Legal & Compliance",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\blegal\b",
                r"\bcompliance\b",
                r"\bregulatory\b",
                r"\bgdpr\b",
                r"\bhipaa\b",
                r"\bsox\b",
                r"\bpci\b",
                r"\bdata privacy\b",
                r"\bcontract\b",
                r"\blaw\b",
                r"\battorney\b",
                r"\bregulation\b",
            ]
        ],
    },
    {
        "id": "weather",
        "name": "Weather Services",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bweather\b",
                r"\bforecast\b",
                r"\btemperature\b",
                r"\bclimate\b",
                r"\bmeteorolog\w+\b",
                r"\brain\b",
                r"\bsnow\b",
                r"\bwind\b",
                r"\bhumidity\b",
                r"\bopenweather\b",
            ]
        ],
    },
    {
        "id": "cicd",
        "name": "CI/CD & DevOps",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bci/cd\b",
                r"\bcontinuous integration\b",
                r"\bcontinuous deployment\b",
                r"\bdevops\b",
                r"\bpipeline\b",
                r"\bjenkins\b",
                r"\bgithub actions\b",
                r"\bgitlab ci\b",
                r"\bcircleci\b",
                r"\bbuild\b",
                r"\bdeploy\b",
                r"\brelease\b",
                r"\binfrastructure as code\b",
                r"\bterraform\b",
                r"\bansible\b",
            ]
        ],
    },
    {
        "id": "travel",
        "name": "Travel & Transportation",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\btravel\b",
                r"\btransportation\b",
                r"\bflight\b",
                r"\bhotel\b",
                r"\bbooking\b",
                r"\btrip\b",
                r"\bitinerary\b",
                r"\broute\b",
                r"\bnavigation\b",
                r"\bdirections\b",
                r"\btransit\b",
                r"\bairline\b",
                r"\blogistics\b",
                r"\bshipping\b",
            ]
        ],
    },
    {
        "id": "vector-databases",
        "name": "Vector Databases",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bvector database\b",
                r"\bvector db\b",
                r"\bvector store\b",
                r"\bsimilarity search\b",
                r"\bsemantic search\b",
                r"\bvector search\b",
                r"\bchroma\b",
                r"\bpinecone\b",
                r"\bweaviate\b",
                r"\bqdrant\b",
                r"\bmilvus\b",
                r"\bpgvector\b",
            ]
        ],
    },
    {
        "id": "education",
        "name": "Education & Learning Tools",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\beducation\b",
                r"\blearning\b",
                r"\bcourse\b",
                r"\btutorial\b",
                r"\blesson\b",
                r"\bschool\b",
                r"\buniversity\b",
                r"\bstudent\b",
                r"\bteacher\b",
                r"\btraining\b",
                r"\bquiz\b",
                r"\bexam\b",
                r"\bstudy\b",
                r"\bcurriculum\b",
                r"\bcoursera\b",
            ]
        ],
    },
    {
        "id": "games",
        "name": "Games & Gamification",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bgam(e|ing|ification)\b",
                r"\brpg\b",
                r"\bleaderboard\b",
                r"\bachievement\b",
                r"\bscore\b",
                r"\bmultiplayer\b",
                r"\bvideo game\b",
                r"\bboard game\b",
                r"\btrivia\b",
                r"\bpuzzle\b",
            ]
        ],
    },
    {
        "id": "biology-medicine",
        "name": "Biology & Medicine",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bbiolog\w+\b",
                r"\bmedicine\b",
                r"\bmedical\b",
                r"\bclinical\b",
                r"\bdrug\b",
                r"\bgenom\w*\b",
                r"\bdna\b",
                r"\brna\b",
                r"\bprotein\b",
                r"\bpatient\b",
                r"\bdiagnosis\b",
                r"\btreatment\b",
                r"\bhealthcare\b",
                r"\bbioinformatics\b",
                r"\bpharmaceutical\b",
            ]
        ],
    },
    {
        "id": "health-wellness",
        "name": "Health & Wellness",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bhealth\b",
                r"\bwellness\b",
                r"\bfitness\b",
                r"\bworkout\b",
                r"\bnutrition\b",
                r"\bdiet\b",
                r"\bmeditation\b",
                r"\bmental health\b",
                r"\bsleep\b",
                r"\byoga\b",
                r"\bheart rate\b",
                r"\bactivity\b",
            ]
        ],
    },
    {
        "id": "crm",
        "name": "CRM",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcrm\b",
                r"\bcustomer relationship\b",
                r"\bsalesforce\b",
                r"\bhubspot\b",
                r"\bzoho\b",
                r"\bsales\b",
                r"\blead management\b",
                r"\bcontact management\b",
                r"\bpipedrive\b",
                r"\baccount management\b",
            ]
        ],
    },
    {
        "id": "audio",
        "name": "Audio Processing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\baudio\b",
                r"\bsound\b",
                r"\bspeech\b",
                r"\btranscription\b",
                r"\bvoice\b",
                r"\bmusic\b",
                r"\brecord\b",
                r"\bmicrophone\b",
                r"\baudio processing\b",
                r"\bspeech to text\b",
                r"\btext to speech\b",
                r"\btts\b",
            ]
        ],
    },
    {
        "id": "design",
        "name": "Design Tools",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bdesign\b",
                r"\bfigma\b",
                r"\bsketch\b",
                r"\badobe\b",
                r"\bphotoshop\b",
                r"\billustrator\b",
                r"\bui\b",
                r"\bux\b",
                r"\buser interface\b",
                r"\buser experience\b",
                r"\bprototype\b",
                r"\bwireframe\b",
                r"\bmockup\b",
                r"\bgraphic design\b",
                r"\btypography\b",
                r"\bsvg\b",
            ]
        ],
    },
    {
        "id": "calendar",
        "name": "Calendar Management",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcalendar\b",
                r"\bgoogle calendar\b",
                r"\boutlook\b",
                r"\bschedule\b",
                r"\bappointment\b",
                r"\bevent\b",
                r"\bmeeting\b",
                r"\bavailability\b",
                r"\bbooking\b",
                r"\breservation\b",
                r"\breminder\b",
            ]
        ],
    },
    {
        "id": "coding-agents",
        "name": "Coding Agents",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcoding agent\b",
                r"\bcode agent\b",
                r"\bcode generation\b",
                r"\bcode assistant\b",
                r"\bprogramming agent\b",
                r"\bdev agent\b",
                r"\bcopilot\b",
                r"\bcodex\b",
                r"\bcode completion\b",
            ]
        ],
    },
    {
        "id": "virtualization",
        "name": "Virtualization",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bvirtualization\b",
                r"\bvirtual machine\b",
                r"\bvm\b",
                r"\bhypervisor\b",
                r"\bvmware\b",
                r"\bvirtualbox\b",
                r"\bqemu\b",
                r"\bkvm\b",
                r"\bvagrant\b",
                r"\bproxmox\b",
            ]
        ],
    },
    {
        "id": "erp",
        "name": "ERP Systems",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\berp\b",
                r"\benterprise resource\b",
                r"\bsap\b",
                r"\boracle\b",
                r"\bmicrosoft dynamics\b",
                r"\binventory management\b",
                r"\bsupply chain\b",
                r"\bmanufacturing\b",
                r"\bresource planning\b",
                r"\bodoo\b",
            ]
        ],
    },
    {
        "id": "customer-support",
        "name": "Customer Support",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcustomer support\b",
                r"\bhelp desk\b",
                r"\bticket\b",
                r"\bsupport ticket\b",
                r"\bzendesk\b",
                r"\bfreshdesk\b",
                r"\bintercom\b",
                r"\blive chat\b",
                r"\bcustomer service\b",
                r"\bsupport system\b",
            ]
        ],
    },
    {
        "id": "payments-billing",
        "name": "Payments & Billing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bpayment\b",
                r"\bbilling\b",
                r"\binvoice\b",
                r"\bstripe\b",
                r"\bpaypal\b",
                r"\bsquare\b",
                r"\brecurring\b",
                r"\bsubscription\b",
                r"\bcheckout\b",
                r"\btransaction\b",
                r"\bcharge\b",
                r"\brefund\b",
                r"\bmerchant\b",
            ]
        ],
    },
    {
        "id": "text-summarization",
        "name": "Text Summarization",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bsummarization\b",
                r"\bsummar\w+\b",
                r"\btext summarization\b",
                r"\babstract\b",
                r"\bextractive\b",
                r"\babstractive\b",
                r"\bdocument summary\b",
            ]
        ],
    },
    {
        "id": "penetration-testing",
        "name": "Penetration Testing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bpenetration test\b",
                r"\bpentest\b",
                r"\bsecurity testing\b",
                r"\bvulnerability assessment\b",
                r"\bexploit\b",
                r"\bethical hacking\b",
                r"\bred team\b",
                r"\bmetasploit\b",
                r"\bburp suite\b",
            ]
        ],
    },
    {
        "id": "email",
        "name": "Email",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bemail\b",
                r"\bsendgrid\b",
                r"\bmailgun\b",
                r"\bpostmark\b",
                r"\bsmtp\b",
                r"\bimap\b",
                r"\bpop3\b",
                r"\binbox\b",
                r"\bmail\b",
                r"\bnewsletter\b",
                r"\bemail campaign\b",
                r"\bemail delivery\b",
            ]
        ],
    },
    {
        "id": "cloud-storage",
        "name": "Cloud Storage",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bcloud storage\b",
                r"\bs3\b",
                r"\bgoogle drive\b",
                r"\bdropbox\b",
                r"\bonedrive\b",
                r"\bbox\b",
                r"\bfile storage\b",
                r"\bobject storage\b",
                r"\bblob storage\b",
                r"\bbackup\b",
                r"\bfile sync\b",
            ]
        ],
    },
    {
        "id": "home-automation",
        "name": "Home Automation & IoT",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bhome automation\b",
                r"\biot\b",
                r"\binternet of things\b",
                r"\bsmart home\b",
                r"\bsmart device\b",
                r"\bthermostat\b",
                r"\balexa\b",
                r"\bgoogle home\b",
                r"\bhome assistant\b",
                r"\bzigbee\b",
                r"\bzwave\b",
                r"\bmqtt\b",
            ]
        ],
    },
    {
        "id": "art-culture",
        "name": "Art & Culture",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bart\b",
                r"\bculture\b",
                r"\bmuseum\b",
                r"\bgallery\b",
                r"\bexhibition\b",
                r"\bartist\b",
                r"\bpainting\b",
                r"\bsculpture\b",
                r"\bphotography\b",
                r"\bcultural\b",
                r"\bheritage\b",
                r"\bcreative\b",
            ]
        ],
    },
    {
        "id": "software-architecture",
        "name": "Software Architecture",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bsoftware architecture\b",
                r"\barchitecture\b",
                r"\bdesign pattern\b",
                r"\bmicroservice\b",
                r"\bdistributed system\b",
                r"\bsystem design\b",
                r"\barchitecture decision\b",
                r"\buml\b",
                r"\bdiagram\b",
            ]
        ],
    },
    {
        "id": "networking",
        "name": "Networking & Infrastructure",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bnetworking\b",
                r"\bnetwork\b",
                r"\bdns\b",
                r"\bload balancer\b",
                r"\bproxy\b",
                r"\bgateway\b",
                r"\bcdn\b",
                r"\bfirewall\b",
                r"\bvpn\b",
                r"\brouter\b",
                r"\bswitch\b",
                r"\bsubnet\b",
                r"\bip address\b",
                r"\bbandwidth\b",
                r"\blatency\b",
            ]
        ],
    },
    {
        "id": "sports",
        "name": "Sports",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bsports\b",
                r"\bfootball\b",
                r"\bsoccer\b",
                r"\bbasketball\b",
                r"\bbaseball\b",
                r"\btennis\b",
                r"\bcricket\b",
                r"\bgolf\b",
                r"\bathlete\b",
                r"\bleague\b",
                r"\bmatch\b",
                r"\btournament\b",
            ]
        ],
    },
    {
        "id": "real-estate",
        "name": "Real Estate",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\breal estate\b",
                r"\bproperty\b",
                r"\brental\b",
                r"\bapartment\b",
                r"\bhouse\b",
                r"\bcommercial\b",
                r"\blisting\b",
                r"\bmortgage\b",
                r"\bzillow\b",
                r"\bredfin\b",
                r"\brealtor\b",
                r"\blandlord\b",
                r"\btenant\b",
                r"\blease\b",
                r"\bvaluation\b",
            ]
        ],
    },
    {
        "id": "speech",
        "name": "Speech Processing",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bspeech\b",
                r"\bspeech to text\b",
                r"\btext to speech\b",
                r"\bstt\b",
                r"\btts\b",
                r"\bvoice recognition\b",
                r"\bspeech recognition\b",
                r"\bvoice\b",
                r"\btranscription\b",
                r"\bspeech synthesis\b",
                r"\bspeaker diarization\b",
            ]
        ],
    },
    {
        "id": "data-visualization",
        "name": "Data Visualization",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bvisualization\b",
                r"\bchart\b",
                r"\bgraph\b",
                r"\bdashboard\b",
                r"\bplot\b",
                r"\bcharting\b",
                r"\bdata viz\b",
                r"\binfographic\b",
                r"\breport\b",
                r"\breporting\b",
                r"\btableau\b",
                r"\bpower bi\b",
                r"\bmatplotlib\b",
            ]
        ],
    },
    {
        "id": "bioinformatics",
        "name": "Bioinformatics",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bbioinformatics\b",
                r"\bgenomic\w*\b",
                r"\bproteomic\w*\b",
                r"\bsequencing\b",
                r"\bblast\b",
                r"\bgenom\w*\b",
                r"\bdna\b",
                r"\brna\b",
                r"\bprotein\b",
                r"\bphylogenetic\b",
                r"\balignment\b",
                r"\bvariant\b",
                r"\bmutation\b",
            ]
        ],
    },
    {
        "id": "fitness",
        "name": "Fitness Tracking",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bfitness\b",
                r"\bworkout\b",
                r"\brunning\b",
                r"\bcycling\b",
                r"\bstep\b",
                r"\bcalorie\b",
                r"\bheart rate\b",
                r"\bgym\b",
                r"\bfitness tracker\b",
                r"\bfitbit\b",
                r"\bactivity\b",
            ]
        ],
    },
    {
        "id": "language-translation",
        "name": "Language Translation",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\btranslation\b",
                r"\btranslate\b",
                r"\blanguage translation\b",
                r"\blocalization\b",
                r"\bi18n\b",
                r"\binternationalization\b",
                r"\btranslator\b",
                r"\bmultilingual\b",
                r"\bgoogle translate\b",
                r"\bdeepl\b",
                r"\bmachine translation\b",
            ]
        ],
    },
    {
        "id": "product-management",
        "name": "Product Management",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bproduct management\b",
                r"\bproduct\b",
                r"\broadmap\b",
                r"\bfeature\b",
                r"\bstakeholder\b",
                r"\bproduct manager\b",
                r"\bproduct owner\b",
                r"\bprioritization\b",
                r"\brequirements\b",
            ]
        ],
    },
    {
        "id": "tts",
        "name": "Text-to-Speech",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\btext to speech\b",
                r"\btts\b",
                r"\bspeech synthesis\b",
                r"\bvoice generation\b",
                r"\bread aloud\b",
                r"\bvoiceover\b",
            ]
        ],
    },
    {
        "id": "embedded",
        "name": "Embedded Systems",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bembedded\b",
                r"\bfirmware\b",
                r"\bmicrocontroller\b",
                r"\barduino\b",
                r"\braspberry pi\b",
                r"\besp32\b",
                r"\brespberry\b",
                r"\bsensor\b",
                r"\bactuator\b",
                r"\breal.?time\b",
                r"\brtos\b",
                r"\bhardware\b",
            ]
        ],
    },
    {
        "id": "energy",
        "name": "Energy",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\benergy\b",
                r"\belectricity\b",
                r"\bpower\b",
                r"\bsolar\b",
                r"\brenewable\b",
                r"\bwind\b",
                r"\bgrid\b",
                r"\benergy management\b",
                r"\bsmart grid\b",
                r"\bconsumption\b",
                r"\bbattery\b",
            ]
        ],
    },
    {
        "id": "aerospace",
        "name": "Aerospace & Astrodynamics",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\baerospace\b",
                r"\bastrodynamic\w*\b",
                r"\bspace\b",
                r"\bsatellite\b",
                r"\borbit\b",
                r"\brocket\b",
                r"\baviation\b",
                r"\bflight\b",
                r"\bdrone\b",
                r"\bastronom\w+\b",
                r"\bnasa\b",
                r"\bcelestial\b",
            ]
        ],
    },
    {
        "id": "feature-flags",
        "name": "Feature Flags",
        "patterns": [
            re.compile(r, re.IGNORECASE)
            for r in [
                r"\bfeature flag\b",
                r"\bfeature toggle\b",
                r"\bfeature switch\b",
                r"\blaunchdarkly\b",
                r"\bflagsmith\b",
                r"\bsplit\b",
                r"\bflag\b",
                r"\bexperimentation\b",
                r"\ba.?b testing\b",
                r"\bcanary release\b",
            ]
        ],
    },
]
_CATEGORY_NAMES = {c["id"]: c["name"] for c in _STORE_CATEGORIES}


def _compute_store_facets(servers: list) -> dict:
    hosting = set()
    categories: dict[str, int] = {}
    for s in servers:
        text_parts = []
        for field in ("name", "description", "namespace", "slug"):
            val = s.get(field)
            if val:
                text_parts.append(str(val))
        for t in s.get("tools", []):
            for field in ("name", "description"):
                val = t.get(field)
                if val:
                    text_parts.append(str(val))
        search_text = " ".join(text_parts).lower()
        matched_cats = []
        for cat in _STORE_CATEGORIES:
            for pattern in cat["patterns"]:
                if pattern.search(search_text):
                    matched_cats.append(cat["id"])
                    categories[cat["id"]] = categories.get(cat["id"], 0) + 1
                    break
        if matched_cats:
            s["categories"] = matched_cats
        for attr in s.get("attributes", []):
            if attr.startswith("hosting:"):
                hosting.add(attr.split(":")[1])
            else:
                cat = attr.split(":")[0] if ":" in attr else attr
                categories[cat] = categories.get(cat, 0) + 1
    hosting_types = sorted(hosting)
    sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
    return {
        "hostingTypes": hosting_types,
        "categories": [{"id": k, "name": _CATEGORY_NAMES.get(k, k), "count": v} for k, v in sorted_cats],
    }


@app.post("/v1/reset")
async def reset_database():
    for key in list(active_servers.keys()):
        await active_servers[key].stop()
        del active_servers[key]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Banco de dados resetado com sucesso")
    return {"status": "ok", "message": "Banco de dados resetado"}


# ─── Webhook PayPal ───────────────────────────────────────────────────────────


@app.post("/v1/webhooks/paypal")
async def paypal_webhook(request: Request):
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items() if k.lower().startswith("paypal-")}
    verified = await verify_webhook_signature(headers, body)
    if not verified:
        return JSONResponse(status_code=401, content={"detail": "Assinatura do webhook inválida"})

    event = parse_webhook_event(body)
    if not event:
        return JSONResponse(status_code=200, content={"status": "ignored"})

    user_id = event.get("custom_id", "")
    if not user_id:
        return JSONResponse(status_code=200, content={"status": "ignored", "reason": "no custom_id"})

    action = event["action"]
    logger.info(f"Webhook PayPal: {event['event_type']} para user {user_id}")

    try:
        if action == "activated":
            await upsert_supabase_profile(
                user_id,
                {
                    "plan_tier": "pro",
                    "status": "active",
                    "paypal_subscription_id": event.get("subscription_id", ""),
                },
            )
        elif action == "payment_failed":
            await upsert_supabase_profile(user_id, {"status": "suspended"})
            await sync_user_servers(user_id)
        elif action == "cancelled":
            await upsert_supabase_profile(
                user_id,
                {
                    "plan_tier": "free",
                    "paypal_subscription_id": None,
                },
            )
            await sync_user_servers(user_id)
        elif action == "reactivated":
            await upsert_supabase_profile(user_id, {"status": "active"})
            await reactivate_user_servers(user_id)

        invalidate_profile_cache(user_id)
        await notify_session_termination(user_id)
    except Exception as e:
        logger.error(f"Erro ao processar webhook PayPal: {e}")

    return JSONResponse(status_code=200, content={"status": "ok"})


async def sync_user_servers(user_id: str):
    db = SessionLocal()
    try:
        profile = await get_cached_profile(user_id)
        servers = db.query(ServerDB).filter(ServerDB.user_id == user_id).all()
        if profile.get("status") != "active":
            for s in servers:
                s.is_active = False
                key = f"{s.server_id}:{s.apikey}"
                if key in active_servers:
                    await active_servers[key].stop()
                    del active_servers[key]
        elif profile.get("plan_tier") == "free":
            limits = get_tier_limits("free")
            for i, s in enumerate(servers):
                s.is_active = i < limits["max_servers"]
                if not s.is_active:
                    key = f"{s.server_id}:{s.apikey}"
                    if key in active_servers:
                        await active_servers[key].stop()
                        del active_servers[key]
        db.commit()
    finally:
        db.close()


async def reactivate_user_servers(user_id: str):
    db = SessionLocal()
    try:
        servers = db.query(ServerDB).filter(ServerDB.user_id == user_id).all()
        for s in servers:
            s.is_active = True
        db.commit()
    finally:
        db.close()


# ─── Profile / Auth ───────────────────────────────────────────────────────────


@app.get("/v1/me")
async def get_me(request: Request, db: Session = Depends(get_db)):
    await require_auth(request)
    user_id = request.state.user_id
    profile = await get_cached_profile(user_id)
    servers = db.query(ServerDB).filter(ServerDB.user_id == user_id).all()
    active_count = sum(1 for s in servers if s.is_active)
    limits = get_tier_limits(profile.get("plan_tier", "free"))
    return ProfileResponse(
        id=user_id,
        email=profile.get("email"),
        name=profile.get("name"),
        avatar_url=profile.get("avatar_url"),
        status=profile.get("status", "active"),
        plan_tier=profile.get("plan_tier", "free"),
        servers_count=len(servers),
        servers_limit=limits["max_servers"],
    )


@app.post("/v1/auth/register")
async def auth_register(request: Request):
    await require_auth(request)
    user_id = request.state.user_id
    payload = request.state.jwt_payload
    try:
        await upsert_supabase_profile(
            user_id,
            {
                "id": user_id,
                "email": payload.get("email", ""),
                "name": payload.get("user_metadata", {}).get("full_name", ""),
                "avatar_url": payload.get("user_metadata", {}).get("avatar_url", ""),
            },
        )
        return {"status": "ok", "user_id": user_id}
    except Exception as e:
        logger.error(f"Erro ao registar utilizador {user_id}: {e}")
        return JSONResponse(status_code=500, content={"detail": "Erro ao registar utilizador"})


# ─── Entrypoint ────────────────────────────────────────────────────────────────


def main():
    logger.info(f"Iniciando Cloud Gateway em {GATEWAY_HOST}:{GATEWAY_PORT}")
    uvicorn.run(
        "app.cloud:app",
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        reload=bool(os.getenv("GATEWAY_RELOAD", "0") == "1"),
    )


if __name__ == "__main__":
    main()
