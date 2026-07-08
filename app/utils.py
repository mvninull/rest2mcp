import asyncio
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time


# Configuração de Log Colorido
class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(ColoredFormatter("[%(levelname)s] %(message)s"))
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)


_TEMP_SERVER_TPL = '''"""
Auto-generated server for MCP Inspector.
"""
import os, sys
sys.path.insert(0, {app_dir!r})
from openapi import create_mcp_server
mcp = create_mcp_server({spec_url!r}, {name!r})
'''


def _create_temp_server(spec_url: str, name: str) -> str:
    temp_dir = tempfile.mkdtemp(prefix="rest2mcp_inspector_")
    app_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(temp_dir, "_inspector_server.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_TEMP_SERVER_TPL.format(app_dir=app_dir, spec_url=spec_url, name=name))
    return filepath, temp_dir


def _run_async(coro):
    return asyncio.run(coro)


def run_with_inspector(transport: str, spec_url: str, name: str, host: str, port: int):
    """
    Inicia o servidor e o MCP Inspector via fastmcp (STDIO) ou npx (HTTP/SSE).
    """
    logger.info("=" * 50)
    logger.info(f"MODO DESENVOLVIMENTO ({transport.upper()})")
    logger.info("=" * 50)

    filepath, temp_dir = _create_temp_server(spec_url, name)

    try:
        if transport == "stdio":
            from fastmcp.cli.cli import app as fastmcp_app
            _run_async(fastmcp_app.run_async(["dev", "inspector", filepath]))
            return 0

        # ── HTTP / SSE: start server in background ────────────────────
        if transport == "http":
            run_fn = _run_server_http
            endpoint = f"http://{host}:{port}/mcp"
            npx_transport = "http"
        elif transport == "sse":
            run_fn = _run_server_sse
            endpoint = f"http://{host}:{port}/sse"
            npx_transport = "sse"
        else:
            logger.error(f"Transporte desconhecido: {transport}")
            return 1

        exc_info = []

        def start_server():
            try:
                run_fn(spec_url, name, host, port)
            except Exception as e:
                exc_info.append(e)

        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        logger.info("Aguardando servidor iniciar...")
        deadline = time.time() + 10
        while time.time() < deadline:
            if exc_info:
                logger.error(f"Erro ao iniciar servidor: {exc_info[0]}")
                return 1
            if _is_port_open(host, port):
                logger.info("Servidor pronto!")
                break
            time.sleep(0.5)
        else:
            if exc_info:
                logger.error(f"Erro ao iniciar servidor: {exc_info[0]}")
            else:
                logger.error(f"Servidor não responde em {host}:{port}")
            return 1

        # Launch inspector via npx (using fastmcp's npx detection)
        from fastmcp.cli.cli import _get_npx_command

        npx_cmd = _get_npx_command()
        if not npx_cmd:
            logger.error("npx não encontrado. Verifique a instalação do Node.js.")
            return 1

        cmd = [
            npx_cmd,
            "@modelcontextprotocol/inspector",
            "--server-url", endpoint,
            "--transport", npx_transport,
        ]
        logger.info(f"Lançando Inspector: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, shell=(sys.platform == "win32"))
            return result.returncode
        except KeyboardInterrupt:
            logger.info("Inspector encerrado pelo usuário")
            return 0

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except OSError:
            pass


def _run_server_http(spec_url: str, name: str, host: str, port: int):
    from openapi import create_mcp_server
    mcp = create_mcp_server(spec_url, name)
    mcp.run(transport="http", host=host, port=port)


def _run_server_sse(spec_url: str, name: str, host: str, port: int):
    from openapi import create_mcp_server
    mcp = create_mcp_server(spec_url, name)
    mcp.run(transport="sse", host=host, port=port)


def _is_port_open(host: str, port: int) -> bool:
    """Verifica se uma porta está aberta (servidor rodando)."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (OSError, ConnectionRefusedError):
        return False
