#!/usr/bin/env python3
"""
stdio_to_http_sse.py — Bridge stdio MCP servers to HTTP/SSE.

Takes any stdio-based MCP server (uvx, npx, pipx, etc.) and exposes it
as an HTTP/SSE endpoint compatible with fastmcp.Client for remote merge.

Usage:
  python stdio_to_http_sse.py --command uvx --args mcp-excel-server
  python stdio_to_http_sse.py --command npx --args @modelcontextprotocol/server-filesystem .
  python stdio_to_http_sse.py --command pipx --args mcp-server-sqlite --port 8766
  python stdio_to_http_sse.py --config server.json
  python stdio_to_http_sse.py --config claude_desktop_config.json --name excel

Config file (JSON):
  {
    "mcpServers": {
      "excel": {
        "command": "uvx",
        "args": ["mcp-excel-server"],
        "env": { "PYTHONPATH": "/path/to/your/python" }
      }
    }
  }

Integration with merge-point:
  POST /v1/servers/merge
  { "source_server_id": "srv_abc123",
    "remote_url": "http://localhost:8765/sse",
    "namespace": "excel",
    "merged_name": "Merged Excel + Loja" }
"""

import argparse
import asyncio
import json
import os
import signal
import sys

import uvicorn


def _build_config(command: str, cmd_args: list[str], env_vars: dict[str, str], server_name: str) -> dict:
    cfg: dict = {
        "mcpServers": {
            server_name: {
                "command": command,
                "args": cmd_args,
            }
        }
    }
    if env_vars:
        cfg["mcpServers"][server_name]["env"] = env_vars
    return cfg


def _resolve_config(args: argparse.Namespace) -> tuple[str, list[str], dict[str, str], str]:
    command = args.command
    cmd_args = list(args.args)
    env_vars: dict[str, str] = {}
    server_name = args.name

    for e in args.env:
        if "=" in e:
            k, v = e.split("=", 1)
            env_vars[k] = v

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
        servers = cfg.get("mcpServers") or {}
        if servers:
            names = list(servers.keys())
            chosen = names[0]
            sv = servers[chosen]
            command = sv.get("command") or command
            cmd_args = sv.get("args") or cmd_args
            env_vars = {**env_vars, **sv.get("env", {})}
            if not server_name:
                server_name = chosen
        else:
            command = cfg.get("command") or command
            cmd_args = cfg.get("args") or cmd_args
            env_vars = {**env_vars, **cfg.get("env", {})}

    if not command:
        print("Error: --command ou --config é obrigatório")
        sys.exit(1)

    if not server_name:
        server_name = f"bridged-{os.path.basename(command)}"

    return command, cmd_args, env_vars, server_name


async def _run_bridge(
    command: str,
    cmd_args: list[str],
    env_vars: dict[str, str],
    host: str,
    port: int,
    server_name: str,
):
    from fastmcp import FastMCP

    config = _build_config(command, cmd_args, env_vars, server_name)
    print(f"Starting: {command} {' '.join(cmd_args)}")
    print(f"Server:   {server_name}")

    proxy = FastMCP.as_proxy(config, name=server_name)
    app = proxy.http_app(transport="sse")

    uvicorn_cfg = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uvicorn_cfg)

    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    def _on_signal():
        if not stop.is_set():
            print("\nShutting down, cleaning up subprocess...")
            server.should_exit = True
            stop.set()

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except NotImplementedError:
                pass

    print(f"Serving on http://{host}:{port}/sse")
    print("Press Ctrl+C to stop")

    try:
        await server.serve()
    except asyncio.CancelledError:
        _on_signal()


def main():
    parser = argparse.ArgumentParser(
        description="Bridge stdio MCP servers to HTTP/SSE for merge-point"
    )
    parser.add_argument("--command", "-c", help="Command (uvx, npx, pipx, etc.)")
    parser.add_argument("--args", "-a", nargs="*", default=[], help="Args for the command")
    parser.add_argument("--env", "-e", nargs="*", default=[], help="Env vars KEY=VALUE")
    parser.add_argument("--port", "-p", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--config", "-f", help="JSON config file")
    parser.add_argument("--name", "-n", help="Server name for mcpServers config")

    args = parser.parse_args()
    command, cmd_args, env_vars, server_name = _resolve_config(args)

    try:
        asyncio.run(_run_bridge(command, cmd_args, env_vars, args.host, args.port, server_name))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
